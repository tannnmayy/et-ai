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
from backend.app.services.weather_forecast_service import get_weather_forecast
from pipeline.firms_ingestion import get_fire_detections
from pipeline.sentinel5p_ingestion import get_no2_column_density
from pipeline.station_registry import BENGALURU_STATIONS, get_station_by_id

logger = logging.getLogger(__name__)

_EARTH_RADIUS_M = 6_371_000.0
_CACHE: dict[str, pd.DataFrame | None] = {}


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


def compute_attribution_for_hexagon(
    target_h3: str,
    hex_df: pd.DataFrame | None = None,
    wind_data: dict[str, Any] | None = None,
    firms_lookup: dict[str, int] | None = None,
    no2_lookup: dict[str, float] | None = None,
    search_radius_m: float = ATTRIBUTION_SEARCH_RADIUS_METERS,
) -> dict[str, Any]:
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

    traffic_raw = no2_mod * (src_df["road_density_m_per_sq_m"].values * 0.7 + 0.3)
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

    traffic_contrib = np.sum(traffic_raw * combined_weights)
    industrial_contrib = np.sum(industrial_raw * combined_weights)
    construction_contrib = np.sum(construction_raw * combined_weights)
    burning_contrib = np.sum(burning_raw * combined_weights)

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
        attribution_result = compute_attribution_for_hexagon(target_h3, hex_df, wind_data, firms_lookup=firms_lookup, no2_lookup=no2_lookup)

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
            s_attr = compute_attribution_for_hexagon(station_h3, hex_df, wind_data, firms_lookup=firms_lookup, no2_lookup=no2_lookup)
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
) -> dict[str, Any]:
    if city not in SUPPORTED_CITIES:
        return {"error": f"Unsupported city: '{city}'", "h3_cell": h3_cell}

    hex_df = _load_hexagon_features()
    if hex_df.empty:
        return {"error": "Hexagon features not available. Run pipeline/build_hexagon_features.py first.", "h3_cell": h3_cell}

    wind_data = _get_current_wind(city)
    firms_lookup = _build_firms_lookup(city)
    no2_lookup = _build_no2_lookup(city)
    attribution = compute_attribution_for_hexagon(h3_cell, hex_df, wind_data, firms_lookup=firms_lookup, no2_lookup=no2_lookup)

    result = {
        "h3_cell": h3_cell,
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

    if include_fusion:
        fusion = compute_fusion_for_hexagon(h3_cell, hex_df, wind_data, attribution, firms_lookup=firms_lookup, no2_lookup=no2_lookup)
        result.update(fusion)
        result["computed_at"] = datetime.now(tz=timezone.utc).isoformat()

    return result


def get_city_grid_attribution(
    city: str = "bengaluru",
    include_fusion: bool = True,
    max_hexagons: int | None = None,
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
        attr = compute_attribution_for_hexagon(h3_cell, hex_df, wind_data, firms_lookup=firms_lookup, no2_lookup=no2_lookup)
        if include_fusion:
            fusion = compute_fusion_for_hexagon(h3_cell, hex_df, wind_data, attr, firms_lookup=firms_lookup, no2_lookup=no2_lookup)
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
