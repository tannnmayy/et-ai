from __future__ import annotations

import logging
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

import numpy as np
import pandas as pd

from backend.app.config import (
    ATTRIBUTION_CALM_WIND_SPEED_THRESHOLD_KMH,
    ATTRIBUTION_SEARCH_RADIUS_METERS,
    FUSION_STATION_RANGE_METERS,
    HEXAGON_FEATURES_PATH,
    SUPPORTED_CITIES,
    get_project_root,
)
from backend.app.services.artifact_adapter import get_latest_station_reading
from backend.app.services.fusion_estimation_service import estimate_fused_pm25
from backend.app.services.traffic_service import traffic_time_metadata
from backend.app.services.weather_forecast_service import get_weather_forecast
from pipeline.firms_ingestion import get_fire_detections
from pipeline.sentinel5p_ingestion import get_no2_column_density
from pipeline.station_registry import BENGALURU_STATIONS, get_registry_stations, get_station_by_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature flags — traffic attribution enhancements
#
# When False, behaviour matches the pre-enhancement engine (road_density × NO2
# only, no time-of-day modulation). Safe defaults are True so demos get the
# improved traffic signal; flip to False for A/B comparison or regressions.
# ---------------------------------------------------------------------------
USE_TRAFFIC_CORRIDOR_SCORE: bool = True
USE_TIME_OF_DAY_TRAFFIC: bool = True

# Blend for corridor-aware traffic density (only when corridor column exists
# and USE_TRAFFIC_CORRIDOR_SCORE is True). Weights sum to 1.0.
#   road_density 0.6 — preserves existing all-roads signal
#   corridor     0.4 — elevates hexes on motorway/trunk/primary/secondary
CORRIDOR_ROAD_DENSITY_WEIGHT: float = 0.6
CORRIDOR_SCORE_WEIGHT: float = 0.4

_EARTH_RADIUS_M = 6_371_000.0
_CACHE: dict[str, pd.DataFrame | None] = {}
_CORRIDOR_LOGGED: bool = False


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return _EARTH_RADIUS_M * 2 * asin(sqrt(a))


def _haversine_distance_m_vectorized(
    lat1: float, lon1: float, lats2: np.ndarray, lons2: np.ndarray
) -> np.ndarray:
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lats2_r, lons2_r = np.radians(lats2), np.radians(lons2)
    dlat = lats2_r - lat1_r
    dlon = lons2_r - lon1_r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_r) * np.cos(lats2_r) * np.sin(dlon / 2.0) ** 2
    return 2 * _EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlon = radians(lon2 - lon1)
    y = sin(dlon) * cos(radians(lat2))
    x = cos(radians(lat1)) * sin(radians(lat2)) - sin(radians(lat1)) * cos(radians(lat2)) * cos(dlon)
    bearing = (np.degrees(np.arctan2(y, x)) + 360) % 360
    return bearing


def _bearing_deg_vectorized(
    lat1: float, lon1: float, lats2: np.ndarray, lons2: np.ndarray
) -> np.ndarray:
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lats2_r, lons2_r = np.radians(lats2), np.radians(lons2)
    dlon = lons2_r - lon1_r
    y = np.sin(dlon) * np.cos(lats2_r)
    x = np.cos(lat1_r) * np.sin(lats2_r) - np.sin(lat1_r) * np.cos(lats2_r) * np.cos(dlon)
    return (np.degrees(np.arctan2(y, x)) + 360) % 360


def _cosine_weight(
    bearing_source_to_target_deg: float,
    wind_direction_met_deg: float,
) -> float:
    air_movement_dir = (wind_direction_met_deg + 180) % 360
    angle_diff_rad = radians(bearing_source_to_target_deg - air_movement_dir)
    return max(0.0, cos(angle_diff_rad))


def _cosine_weight_vectorized(
    bearings: np.ndarray,
    wind_direction_met_deg: float,
) -> np.ndarray:
    air_movement_dir = (wind_direction_met_deg + 180) % 360
    angle_diff_rad = np.radians(bearings - air_movement_dir)
    return np.maximum(0.0, np.cos(angle_diff_rad))


def _load_hexagon_features() -> pd.DataFrame:
    if "features" in _CACHE and _CACHE["features"] is not None:
        return _CACHE["features"]
    root = get_project_root()
    path = root / HEXAGON_FEATURES_PATH
    if not path.exists():
        logger.warning("Hexagon features not found at %s", path)
        _CACHE["features"] = pd.DataFrame()
        return _CACHE["features"]
    df = pd.read_parquet(str(path))
    _CACHE["features"] = df
    logger.info("Loaded %d hexagon features", len(df))
    return df


def _get_current_wind(city: str = "bengaluru") -> dict[str, Any]:
    forecast = get_weather_forecast(city=city, refresh=False)
    hourly = forecast.get("hourly", [])
    if not hourly:
        return {"direction_deg": None, "speed_kmh": None, "retrieved_at": None}

    first = hourly[0]
    wd = first.get("wind_direction_deg")
    ws = first.get("wind_speed_kmh")
    retrieved = forecast.get("retrieved_at", "")

    if wd is None or ws is None:
        return {"direction_deg": None, "speed_kmh": None, "retrieved_at": retrieved}

    return {"direction_deg": float(wd), "speed_kmh": float(ws), "retrieved_at": retrieved}


def _traffic_density_proxy(src_df: pd.DataFrame) -> tuple[np.ndarray, bool]:
    """Build per-source-hex traffic density proxy.

    Legacy formula (flag off or corridor column missing)::

        road_density_m_per_sq_m

    Corridor-aware formula (flag on and column present)::

        0.6 * road_density + 0.4 * traffic_corridor_score

    Returns (density_array, corridor_applied).
    """
    global _CORRIDOR_LOGGED
    road_density = src_df["road_density_m_per_sq_m"].fillna(0.0).to_numpy(dtype=float)

    has_corridor_col = "traffic_corridor_score" in src_df.columns
    if USE_TRAFFIC_CORRIDOR_SCORE and has_corridor_col:
        corridor = src_df["traffic_corridor_score"].fillna(0.0).to_numpy(dtype=float)
        density = (
            CORRIDOR_ROAD_DENSITY_WEIGHT * road_density
            + CORRIDOR_SCORE_WEIGHT * corridor
        )
        if not _CORRIDOR_LOGGED:
            logger.info(
                "Traffic corridor score applied (road_density×%.2f + corridor×%.2f)",
                CORRIDOR_ROAD_DENSITY_WEIGHT,
                CORRIDOR_SCORE_WEIGHT,
            )
            _CORRIDOR_LOGGED = True
        return density, True

    if USE_TRAFFIC_CORRIDOR_SCORE and not has_corridor_col and not _CORRIDOR_LOGGED:
        logger.info(
            "USE_TRAFFIC_CORRIDOR_SCORE is True but traffic_corridor_score column "
            "missing from hexagon features — falling back to road_density only. "
            "Run: python -m pipeline.augment_hexagon_traffic_corridors"
        )
        _CORRIDOR_LOGGED = True
    return road_density, False


def compute_attribution_for_hexagon(
    target_h3: str,
    hex_df: pd.DataFrame | None = None,
    wind_data: dict[str, Any] | None = None,
    firms_lookup: dict[str, int] | None = None,
    no2_lookup: dict[str, float] | None = None,
    search_radius_m: float = ATTRIBUTION_SEARCH_RADIUS_METERS,
    simulated_hour: int | None = None,
) -> dict[str, Any]:
    """Wind-weighted multi-source attribution for one H3 cell.

    Parameters
    ----------
    simulated_hour:
        Optional 0–23 hour (Bengaluru local) for demo/A-B of the
        time-of-day traffic multiplier. ``None`` uses current local time
        when ``USE_TIME_OF_DAY_TRAFFIC`` is enabled.
    """
    if hex_df is None:
        hex_df = _load_hexagon_features()
    if hex_df.empty:
        return _empty_attribution_result(target_h3, "hexagon_features_unavailable")

    target_row = hex_df[hex_df["h3_cell"] == target_h3]
    if target_row.empty:
        return _empty_attribution_result(target_h3, "unknown_hexagon")

    tlat = target_row.iloc[0]["center_lat"]
    tlon = target_row.iloc[0]["center_lon"]

    if wind_data is None:
        wind_data = _get_current_wind()
    wd = wind_data.get("direction_deg")
    ws = wind_data.get("speed_kmh")

    lats_arr = hex_df["center_lat"].to_numpy()
    lons_arr = hex_df["center_lon"].to_numpy()
    distances_m = _haversine_distance_m_vectorized(tlat, tlon, lats_arr, lons_arr)
    within_range = (distances_m <= search_radius_m) & (distances_m > 0)
    source_indices = np.where(within_range)[0]
    source_distances = distances_m[source_indices]

    if len(source_indices) == 0:
        return _empty_attribution_result(target_h3, "no_sources_in_range")

    is_calm = ws is not None and ws <= ATTRIBUTION_CALM_WIND_SPEED_THRESHOLD_KMH
    method = "calm_fallback" if (is_calm or wd is None) else "wind_weighted"

    src_df = hex_df.iloc[source_indices]
    src_cells = src_df["h3_cell"].values

    if no2_lookup:
        no2_vals = np.array([no2_lookup.get(c, 0.0) for c in src_cells], dtype=float)
        no2_min, no2_max = no2_vals.min(), no2_vals.max()
        if no2_max > no2_min:
            no2_norm = (no2_vals - no2_min) / (no2_max - no2_min)
        else:
            no2_norm = np.full_like(no2_vals, 0.5)
        no2_mod = 0.5 + no2_norm
    else:
        no2_mod = np.ones(len(src_cells))

    # --- Traffic intensity -------------------------------------------------
    # Base: road density (+ optional major-road corridor blend) × NO2 modulator.
    # Same structural form as the legacy formula so results stay continuous
    # when corridor score is 0 everywhere.
    traffic_density, corridor_applied = _traffic_density_proxy(src_df)
    traffic_raw = no2_mod * (traffic_density * 0.7 + 0.3)

    industrial_raw = no2_mod * (src_df["industrial_fraction"].values * 0.8 + src_df["industrial_facility_count"].values * 0.2 + 0.1)
    construction_raw = src_df["construction_feature_count"].values.astype(float) + 0.1

    if firms_lookup:
        burning_raw = np.array([firms_lookup.get(c, 0) for c in src_cells], dtype=float) + 0.01
    else:
        burning_raw = np.ones(len(src_cells)) * 0.01

    idw_weights = 1.0 / np.maximum(source_distances, 1.0)

    if method == "wind_weighted" and wd is not None:
        src_lats = src_df["center_lat"].to_numpy()
        src_lons = src_df["center_lon"].to_numpy()
        bearings_target_to_source = _bearing_deg_vectorized(tlat, tlon, src_lats, src_lons)
        bearings = (bearings_target_to_source + 180) % 360
        dir_weights = _cosine_weight_vectorized(bearings, wd)
        combined_weights = idw_weights * dir_weights
    else:
        combined_weights = idw_weights

    traffic_contrib = float(np.sum(traffic_raw * combined_weights))
    industrial_contrib = float(np.sum(industrial_raw * combined_weights))
    construction_contrib = float(np.sum(construction_raw * combined_weights))
    burning_contrib = float(np.sum(burning_raw * combined_weights))

    # --- Time-of-day traffic multiplier ------------------------------------
    # Applied only to the traffic channel before renormalisation so industrial
    # / construction / burning fractions adjust inversely (zero-sum fractions).
    time_meta: dict[str, Any]
    if USE_TIME_OF_DAY_TRAFFIC:
        time_meta = traffic_time_metadata(simulated_hour)
        mult = float(time_meta["traffic_time_multiplier"])
        traffic_contrib *= mult
    else:
        time_meta = {
            "traffic_time_multiplier": 1.0,
            "is_peak_hour": False,
            "traffic_hour_local": None,
            "traffic_timezone": "Asia/Kolkata",
        }

    total = traffic_contrib + industrial_contrib + construction_contrib + burning_contrib
    if total <= 0:
        return _empty_attribution_result(target_h3, "zero_total_weight")

    result = {
        "source_attribution": {
            "traffic": round(traffic_contrib / total, 4),
            "industrial": round(industrial_contrib / total, 4),
            "construction": round(construction_contrib / total, 4),
            "burning": round(burning_contrib / total, 4),
        },
        "source_intensities": {
            "traffic_raw": round(float(traffic_contrib), 4),
            "industrial_raw": round(float(industrial_contrib), 4),
            "construction_raw": round(float(construction_contrib), 4),
            "burning_raw": round(float(burning_contrib), 4),
        },
        "method": method,
        "wind_used": {
            "direction_deg": wd,
            "speed_kmh": ws,
            "retrieved_at": wind_data.get("retrieved_at"),
        },
        "source_hexagons_contributing": int(len(source_indices)),
        "max_distance_m": round(float(np.max(source_distances)), 1),
        # Optional metadata for Enforcement UI (non-breaking extras)
        "traffic_time_multiplier": time_meta["traffic_time_multiplier"],
        "is_peak_hour": time_meta["is_peak_hour"],
        "traffic_hour_local": time_meta.get("traffic_hour_local"),
        "traffic_corridor_applied": corridor_applied,
    }
    return result


def _empty_attribution_result(h3_cell: str, reason: str) -> dict[str, Any]:
    return {
        "source_attribution": {"traffic": 0.0, "industrial": 0.0, "construction": 0.0, "burning": 0.0},
        "source_intensities": {"traffic_raw": 0.0, "industrial_raw": 0.0, "construction_raw": 0.0, "burning_raw": 0.0},
        "method": "unavailable",
        "wind_used": {"direction_deg": None, "speed_kmh": None, "retrieved_at": None},
        "source_hexagons_contributing": 0,
        "max_distance_m": 0.0,
        "traffic_time_multiplier": 1.0,
        "is_peak_hour": False,
        "traffic_hour_local": None,
        "traffic_corridor_applied": False,
    }


def _get_station_attribution(station_id: str, hex_df: pd.DataFrame, wind_data: dict[str, Any]) -> dict[str, Any]:
    station = get_station_by_id(station_id)
    if station.latitude is None or station.longitude is None:
        return _empty_attribution_result("", "no_station_coordinates")
    station_h3 = _lat_lon_to_h3_cell(station.latitude, station.longitude)
    return compute_attribution_for_hexagon(station_h3, hex_df, wind_data)


def _lat_lon_to_h3_cell(lat: float, lon: float) -> str:
    import h3 as _h3
    return _h3.latlng_to_cell(lat, lon, 9)


def compute_fusion_for_hexagon(
    target_h3: str,
    hex_df: pd.DataFrame | None = None,
    wind_data: dict[str, Any] | None = None,
    attribution_result: dict[str, Any] | None = None,
    firms_lookup: dict[str, int] | None = None,
    no2_lookup: dict[str, float] | None = None,
    station_range_m: float = FUSION_STATION_RANGE_METERS,
    simulated_hour: int | None = None,
) -> dict[str, Any]:
    if hex_df is None:
        hex_df = _load_hexagon_features()
    if hex_df.empty:
        return _empty_fusion_result()

    target_row = hex_df[hex_df["h3_cell"] == target_h3]
    if target_row.empty:
        return _empty_fusion_result()
    tlat = target_row.iloc[0]["center_lat"]
    tlon = target_row.iloc[0]["center_lon"]

    if attribution_result is None:
        attribution_result = compute_attribution_for_hexagon(
            target_h3, hex_df, wind_data,
            firms_lookup=firms_lookup, no2_lookup=no2_lookup,
            simulated_hour=simulated_hour,
        )

    if wind_data is None:
        wind_data = _get_current_wind()

    station_attribs: list[dict[str, Any]] = []
    station_readings: list[dict[str, Any]] = []

    for station in BENGALURU_STATIONS:
        if not station.forecast_eligible or station.latitude is None or station.longitude is None:
            continue
        reading = get_latest_station_reading(station.station_id, "pm25")
        if not reading.get("available") or reading.get("value") is None:
            continue
        dist = _haversine_distance_m(tlat, tlon, station.latitude, station.longitude)
        if dist <= station_range_m:
            station_h3 = _lat_lon_to_h3_cell(station.latitude, station.longitude)
            s_attr = compute_attribution_for_hexagon(
                station_h3, hex_df, wind_data,
                firms_lookup=firms_lookup, no2_lookup=no2_lookup,
                simulated_hour=simulated_hour,
            )
            station_attribs.append({
                "station_id": station.station_id,
                "distance_m": dist,
                "reading": reading["value"],
                "attribution": s_attr["source_attribution"],
                "h3_cell": station_h3,
            })
            station_readings.append({
                "station_id": reading["station_id"],
                "value": reading["value"],
                "distance_m": dist,
            })

    if not station_readings:
        return _empty_fusion_result()

    t_attr = attribution_result["source_attribution"]
    t_vec = np.array([t_attr["traffic"], t_attr["industrial"], t_attr["construction"], t_attr["burning"]])

    sim_weights: list[float] = []
    for s in station_attribs:
        s_vec = np.array([s["attribution"]["traffic"], s["attribution"]["industrial"],
                          s["attribution"]["construction"], s["attribution"]["burning"]])
        l1_dist = np.sum(np.abs(t_vec - s_vec))
        sim = 1.0 - l1_dist / 2.0
        sim_weights.append(max(sim, 0.0))

    sim_weights_arr = np.array(sim_weights)
    if sim_weights_arr.sum() <= 0:
        baseline = float(np.mean([r["value"] for r in station_readings]))
    else:
        baseline = float(np.average([r["value"] for r in station_readings], weights=sim_weights_arr))

    for s in station_attribs:
        s_h3 = s["h3_cell"]
        s_base = baseline
        if sim_weights_arr.sum() > 0:
            s_vec_for = np.array([s["attribution"]["traffic"], s["attribution"]["industrial"],
                                  s["attribution"]["construction"], s["attribution"]["burning"]])
            s_sim_weights = []
            for other_s in station_attribs:
                other_vec = np.array([other_s["attribution"]["traffic"], other_s["attribution"]["industrial"],
                                      other_s["attribution"]["construction"], other_s["attribution"]["burning"]])
                l1_so = np.sum(np.abs(s_vec_for - other_vec))
                s_sim_weights.append(max(1.0 - l1_so / 2.0, 0.0))
            s_sim_arr = np.array(s_sim_weights)
            if s_sim_arr.sum() > 0:
                s_base = float(np.average([r["value"] for r in station_readings], weights=s_sim_arr))
        resid = s["reading"] - s_base
        s["residual"] = resid

    idw_numer = 0.0
    idw_denom = 0.0
    for s in station_attribs:
        w = 1.0 / max(s["distance_m"], 1.0)
        resid = s.get("residual", 0.0)
        idw_numer += resid * w
        idw_denom += w

    correction = idw_numer / idw_denom if idw_denom > 0 else 0.0
    fused = baseline + correction

    nearest = min(station_readings, key=lambda r: r["distance_m"])
    nearest_id = nearest["station_id"]
    nearest_dist = nearest["distance_m"]

    return {
        "fused_pm25": round(fused, 2),
        "baseline_pm25": round(baseline, 2),
        "residual_correction": round(correction, 2),
        "stations_contributing": len(station_readings),
        "nearest_station_id": nearest_id,
        "nearest_station_distance_m": round(nearest_dist, 1),
        "fusion_method": "idw_attribution_baseline",
    }


def _empty_fusion_result() -> dict[str, Any]:
    return {
        "fused_pm25": None,
        "baseline_pm25": None,
        "residual_correction": None,
        "stations_contributing": 0,
        "nearest_station_id": None,
        "nearest_station_distance_m": None,
        "fusion_method": "unavailable",
    }


def _build_firms_lookup(city: str) -> dict[str, int]:
    result = get_fire_detections(city=city)
    return {h["h3_cell"]: h["detection_count"] for h in result.get("hexagons", [])}


def _build_no2_lookup(city: str) -> dict[str, float]:
    result = get_no2_column_density(city=city)
    return {h["h3_cell"]: h["no2_column_density_mean"] for h in result.get("hexagons", []) if h.get("no2_column_density_mean") is not None}


def get_single_hexagon_attribution(
    h3_cell: str,
    city: str = "bengaluru",
    include_fusion: bool = True,
    simulated_hour: int | None = None,
) -> dict[str, Any]:
    if city not in SUPPORTED_CITIES:
        return {"error": f"Unsupported city: '{city}'", "h3_cell": h3_cell}

    hex_df = _load_hexagon_features()
    if hex_df.empty:
        return {"error": "Hexagon features not available. Run pipeline/build_hexagon_features.py first.", "h3_cell": h3_cell}

    wind_data = _get_current_wind(city)
    firms_lookup = _build_firms_lookup(city)
    no2_lookup = _build_no2_lookup(city)
    attribution = compute_attribution_for_hexagon(
        h3_cell, hex_df, wind_data,
        firms_lookup=firms_lookup, no2_lookup=no2_lookup,
        simulated_hour=simulated_hour,
    )

    target_row = hex_df[hex_df["h3_cell"] == h3_cell]
    center_lat = float(target_row.iloc[0]["center_lat"]) if not target_row.empty else 0.0
    center_lon = float(target_row.iloc[0]["center_lon"]) if not target_row.empty else 0.0

    result = {
        "h3_cell": h3_cell,
        "center_lat": center_lat,
        "center_lon": center_lon,
        **attribution,
        "fused_pm25": None,
        "baseline_pm25": None,
        "residual_correction": None,
        "stations_contributing": 0,
        "nearest_station_id": None,
        "nearest_station_distance_m": None,
        "fusion_method": "unavailable",
        "computed_at": datetime.now(tz=timezone.utc).isoformat(),
        "city": city,
    }
    # Confidence attached after fusion merge below when include_fusion=True;
    # baseline attach here so partial responses still carry reliability.

    if include_fusion:
        fusion = compute_fusion_for_hexagon(
            h3_cell, hex_df, wind_data, attribution,
            firms_lookup=firms_lookup, no2_lookup=no2_lookup,
            simulated_hour=simulated_hour,
        )
        result.update(fusion)
        result["computed_at"] = datetime.now(tz=timezone.utc).isoformat()

    from backend.app.services.attribution_confidence_service import attach_confidence_to_hex_payload

    attach_confidence_to_hex_payload(
        result, wind_speed_kmh=wind_data.get("speed_kmh")
    )
    return result


def get_city_grid_attribution(
    city: str = "bengaluru",
    include_fusion: bool = True,
    max_hexagons: int | None = None,
    simulated_hour: int | None = None,
) -> dict[str, Any]:
    if city not in SUPPORTED_CITIES:
        return {"error": f"Unsupported city: '{city}'"}

    hex_df = _load_hexagon_features()
    if hex_df.empty:
        return {"error": "Hexagon features not available. Run pipeline/build_hexagon_features.py first."}

    # The full city grid has nearly 10k cells. An interactive map only needs a
    # representative, evenly distributed mesh; sampling both targets and
    # source context avoids an O(n²) request on the API event loop.
    if max_hexagons is not None and len(hex_df) > max_hexagons:
        indices = np.linspace(0, len(hex_df) - 1, max_hexagons, dtype=int)
        hex_df = hex_df.iloc[indices].reset_index(drop=True)

    wind_data = _get_current_wind(city)
    firms_lookup = _build_firms_lookup(city)
    no2_lookup = _build_no2_lookup(city)
    computed_at = datetime.now(tz=timezone.utc).isoformat()

    hexagon_results: list[dict[str, Any]] = []
    for _, row in hex_df.iterrows():
        h3_cell = row["h3_cell"]
        attr = compute_attribution_for_hexagon(
            h3_cell, hex_df, wind_data,
            firms_lookup=firms_lookup, no2_lookup=no2_lookup,
            simulated_hour=simulated_hour,
        )
        if include_fusion:
            fusion = compute_fusion_for_hexagon(
                h3_cell, hex_df, wind_data, attr,
                firms_lookup=firms_lookup, no2_lookup=no2_lookup,
                simulated_hour=simulated_hour,
            )
            attr.update(fusion)
        attr["h3_cell"] = h3_cell
        attr["center_lat"] = row["center_lat"]
        attr["center_lon"] = row["center_lon"]
        hexagon_results.append(attr)

    return {
        "city": city,
        "computed_at": computed_at,
        "hexagon_count": len(hexagon_results),
        "wind_used": {
            "direction_deg": wind_data.get("direction_deg"),
            "speed_kmh": wind_data.get("speed_kmh"),
            "retrieved_at": wind_data.get("retrieved_at"),
        },
        "hexagons": hexagon_results,
        "warnings": [],
    }


def get_city_grid_fusion_only(
    city: str = "bengaluru",
    max_hexagons: int | None = None,
) -> dict[str, Any]:
    if city not in SUPPORTED_CITIES:
        return {"error": f"Unsupported city: '{city}'"}

    hex_df = _load_hexagon_features()
    if hex_df.empty:
        return {"error": "Hexagon features not available. Run pipeline/build_hexagon_features.py first."}

    if max_hexagons is not None and len(hex_df) > max_hexagons:
        indices = np.linspace(0, len(hex_df) - 1, max_hexagons, dtype=int)
        hex_df = hex_df.iloc[indices].reset_index(drop=True)

    wind_data = _get_current_wind(city)
    firms_lookup = _build_firms_lookup(city)
    no2_lookup = _build_no2_lookup(city)
    computed_at = datetime.now(tz=timezone.utc).isoformat()

    station_readings_used = 0
    hexagon_results: list[dict[str, Any]] = []
    for _, row in hex_df.iterrows():
        h3_cell = row["h3_cell"]
        attr = compute_attribution_for_hexagon(h3_cell, hex_df, wind_data, firms_lookup=firms_lookup, no2_lookup=no2_lookup)
        fusion = compute_fusion_for_hexagon(h3_cell, hex_df, wind_data, attr, firms_lookup=firms_lookup, no2_lookup=no2_lookup)
        if fusion["stations_contributing"] > station_readings_used:
            station_readings_used = fusion["stations_contributing"]
        hexagon_results.append(fusion)

    return {
        "city": city,
        "computed_at": computed_at,
        "hexagon_count": len(hexagon_results),
        "wind_used": {
            "direction_deg": wind_data.get("direction_deg"),
            "speed_kmh": wind_data.get("speed_kmh"),
            "retrieved_at": wind_data.get("retrieved_at"),
        },
        "station_readings_used": station_readings_used,
        "hexagons": hexagon_results,
        "warnings": [],
    }


def _estimate_fused_pm25_for_grid(hex_df: pd.DataFrame) -> np.ndarray:
    """Compatibility wrapper around the shared range-limited fusion estimator."""
    return estimate_fused_pm25(hex_df)


# Worst-hex count pulled per station catchment for Local Peaks mode.
LOCAL_PEAKS_PER_STATION_K: int = 8

EXTREMES_MODE_GLOBAL = "global"
EXTREMES_MODE_LOCAL_PEAKS = "local_peaks"
EXTREMES_MODES = frozenset({EXTREMES_MODE_GLOBAL, EXTREMES_MODE_LOCAL_PEAKS})

_MODE_DESCRIPTIONS = {
    EXTREMES_MODE_GLOBAL: (
        "Global highest fused PM2.5 among hexes with station fusion "
        f"(within ~{int(FUSION_STATION_RANGE_METERS / 1000)} km of an eligible PM2.5 station). "
        "A single high station can create a large tied plateau of identical worst ranks."
    ),
    EXTREMES_MODE_LOCAL_PEAKS: (
        "Local peaks: for each eligible PM2.5 station, take the worst "
        f"{LOCAL_PEAKS_PER_STATION_K} fused hexes in its ~{int(FUSION_STATION_RANGE_METERS / 1000)} km "
        "catchment, merge/de-dupe, then rank by fused PM2.5. Surfaces dirty pockets city-wide "
        "without inventing values outside fusion range."
    ),
}


def _haversine_m_scalar(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two points."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return _EARTH_RADIUS_M * 2 * asin(sqrt(min(1.0, a)))


def _select_local_peaks_worst(
    scored: list[dict[str, Any]],
    *,
    n: int,
    peak_k: int = LOCAL_PEAKS_PER_STATION_K,
    range_m: float = FUSION_STATION_RANGE_METERS,
) -> list[dict[str, Any]]:
    """Per-station top-K worst fused hexes, merged and re-ranked.

    Only hexes already in ``scored`` (real fused PM2.5) are considered.
    Stations without a live PM2.5 reading are skipped so catchments match fusion.
    """
    if not scored or n <= 0:
        return []

    # Prefer registry stations (verified lat/lon). BENGALURU_STATIONS may omit coordinates.
    stations_live: list[tuple[str, float, float]] = []
    registry = list(get_registry_stations())
    station_iter = registry if registry else list(BENGALURU_STATIONS)
    for station in station_iter:
        if not getattr(station, "forecast_eligible", True):
            continue
        lat = getattr(station, "latitude", None)
        lon = getattr(station, "longitude", None)
        if lat is None or lon is None:
            continue
        reading = get_latest_station_reading(station.station_id, "pm25")
        if not reading.get("available") or reading.get("value") is None:
            continue
        stations_live.append((station.station_id, float(lat), float(lon)))

    if not stations_live:
        # Fallback: absolute ranking if no live stations with coordinates
        ordered = sorted(scored, key=lambda h: float(h.get("fused_pm25") or 0), reverse=True)
        return ordered[:n]

    by_cell: dict[str, dict[str, Any]] = {}
    for sid, slat, slon in stations_live:
        in_catchment: list[dict[str, Any]] = []
        for h in scored:
            try:
                hlat = float(h["center_lat"])
                hlon = float(h["center_lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if _haversine_m_scalar(slat, slon, hlat, hlon) <= range_m:
                in_catchment.append(h)
        in_catchment.sort(key=lambda h: float(h.get("fused_pm25") or 0), reverse=True)
        for h in in_catchment[:peak_k]:
            cell = str(h.get("h3_cell") or "")
            if not cell:
                continue
            prev = by_cell.get(cell)
            if prev is None or float(h.get("fused_pm25") or 0) > float(
                prev.get("fused_pm25") or 0
            ):
                # Annotate which station catchment contributed (for UI honesty)
                tagged = dict(h)
                tagged["local_peak_station_id"] = sid
                by_cell[cell] = tagged

    merged = list(by_cell.values())
    merged.sort(key=lambda h: float(h.get("fused_pm25") or 0), reverse=True)
    return merged[:n]


def get_city_extremes(
    city: str = "bengaluru",
    n: int = 15,
    simulated_hour: int | None = None,
    mode: str = EXTREMES_MODE_GLOBAL,
    peak_k: int = LOCAL_PEAKS_PER_STATION_K,
) -> dict[str, Any]:
    if city not in SUPPORTED_CITIES:
        return {"error": f"Unsupported city: '{city}'"}

    mode_norm = (mode or EXTREMES_MODE_GLOBAL).strip().lower().replace("-", "_")
    if mode_norm in ("local", "peaks", "localpeaks"):
        mode_norm = EXTREMES_MODE_LOCAL_PEAKS
    if mode_norm not in EXTREMES_MODES:
        return {
            "error": (
                f"Unsupported extremes mode '{mode}'. "
                f"Use '{EXTREMES_MODE_GLOBAL}' or '{EXTREMES_MODE_LOCAL_PEAKS}'."
            )
        }

    peak_k = max(1, min(20, int(peak_k or LOCAL_PEAKS_PER_STATION_K)))

    hex_df = _load_hexagon_features()
    if hex_df.empty:
        return {"error": "Hexagon features not available. Run pipeline/build_hexagon_features.py first."}

    wind_data = _get_current_wind(city)
    firms_lookup = _build_firms_lookup(city)
    no2_lookup = _build_no2_lookup(city)

    fused_arr = _estimate_fused_pm25_for_grid(hex_df)

    # Pre-compute nearest eligible station distance for confidence decay
    from backend.app.services.attribution_confidence_service import (
        attach_confidence_to_hex_payload,
        nearest_station_distances_m,
    )

    st_lats: list[float] = []
    st_lons: list[float] = []
    st_ids: list[str] = []
    for station in get_registry_stations():
        if not getattr(station, "forecast_eligible", True):
            continue
        lat = getattr(station, "latitude", None)
        lon = getattr(station, "longitude", None)
        if lat is None or lon is None:
            continue
        st_lats.append(float(lat))
        st_lons.append(float(lon))
        st_ids.append(station.station_id)
    nearest_d, nearest_i = nearest_station_distances_m(
        hex_df["center_lat"].to_numpy(),
        hex_df["center_lon"].to_numpy(),
        st_lats,
        st_lons,
    )

    hexagon_results: list[dict[str, Any]] = []
    # fused_arr is aligned to hex_df row order (0..n-1)
    for pos, (_, row) in enumerate(hex_df.iterrows()):
        h3_cell = row["h3_cell"]
        attr = compute_attribution_for_hexagon(
            h3_cell, hex_df, wind_data,
            firms_lookup=firms_lookup, no2_lookup=no2_lookup,
            simulated_hour=simulated_hour,
        )
        fusion_val = float(fused_arr[pos]) if pos < len(fused_arr) else float("nan")
        nd = float(nearest_d[pos]) if pos < len(nearest_d) else float("nan")
        ni = int(nearest_i[pos]) if pos < len(nearest_i) else -1
        # Cap distance for "in range" messaging using fusion range
        in_range = not np.isnan(nd) and nd <= FUSION_STATION_RANGE_METERS
        entry = {
            **attr,
            "h3_cell": h3_cell,
            "center_lat": row["center_lat"],
            "center_lon": row["center_lon"],
            "fused_pm25": None if np.isnan(fusion_val) else round(fusion_val, 2),
            "baseline_pm25": None,
            "residual_correction": None,
            "stations_contributing": 1 if (not np.isnan(fusion_val) and in_range) else 0,
            "nearest_station_id": (
                st_ids[ni] if in_range and 0 <= ni < len(st_ids) else None
            ),
            "nearest_station_distance_m": round(nd, 1) if in_range else None,
            "fusion_method": "idw_nearest_station" if not np.isnan(fusion_val) else "unavailable",
        }
        attach_confidence_to_hex_payload(
            entry, wind_speed_kmh=wind_data.get("speed_kmh")
        )
        hexagon_results.append(entry)

    scored = [h for h in hexagon_results if h.get("fused_pm25") is not None]
    scored_asc = sorted(scored, key=lambda h: float(h["fused_pm25"]))
    # Cleanest: always absolute lowest fused (same for both modes)
    best = scored_asc[:n]

    # Global worst: absolute highest fused (unchanged math)
    worst_global = list(reversed(scored_asc[-n:])) if n else []
    # Local peaks worst: per-station catchment top-K merge
    worst_local = _select_local_peaks_worst(scored, n=n, peak_k=peak_k)

    if mode_norm == EXTREMES_MODE_LOCAL_PEAKS:
        worst = worst_local
    else:
        worst = worst_global

    # Prefer locality registry names (fast) over reverse-geocode for every extreme
    from backend.app.services.locality_naming import resolve_location_name

    def _add_names(hexagons: list[dict[str, Any]]) -> None:
        for hexagon in hexagons:
            try:
                hexagon["name"] = resolve_location_name(
                    float(hexagon["center_lat"]),
                    float(hexagon["center_lon"]),
                    h3_cell=str(hexagon.get("h3_cell") or ""),
                )
                hexagon["location_name"] = hexagon["name"]
            except Exception as exc:
                logger.debug("Could not name %s: %s", hexagon["h3_cell"], exc)
                hexagon["name"] = None

    _add_names(best)
    _add_names(worst)

    max_fused = float(scored_asc[-1]["fused_pm25"]) if scored_asc else None
    tie_count = 0
    max_station_id = None
    if max_fused is not None:
        tie_count = sum(
            1 for h in scored if abs(float(h["fused_pm25"]) - max_fused) < 0.05
        )
        # Dominant station among global plateau (nearest station of max hexes)
        max_hexes = [
            h for h in scored if abs(float(h["fused_pm25"]) - max_fused) < 0.05
        ]
        counts: dict[str, int] = {}
        for h in max_hexes:
            sid = h.get("nearest_station_id")
            if sid:
                counts[str(sid)] = counts.get(str(sid), 0) + 1
        if counts:
            max_station_id = max(counts, key=counts.get)

    return {
        "city": city,
        "computed_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": mode_norm,
        "mode_description": _MODE_DESCRIPTIONS[mode_norm],
        "peak_k": peak_k if mode_norm == EXTREMES_MODE_LOCAL_PEAKS else None,
        "best": best,
        "worst": worst,
        "total_hexagons_with_data": len(scored),
        "total_hexagons_in_grid": len(hexagon_results),
        "fusion_range_m": FUSION_STATION_RANGE_METERS,
        "max_fused_pm25": max_fused,
        "tie_count_at_max": tie_count,
        "max_station_id": max_station_id,
        "ranking_note": (
            "Only hexes with real fused PM2.5 (station in range) are ranked. "
            "Uncovered grid cells are not scored as clean — they are unmeasured."
        ),
    }
