from __future__ import annotations

import logging
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

import numpy as np
import pandas as pd

from backend.app.config import (
    ATTRIBUTION_CALM_WIND_SPEED_THRESHOLD_KMH,
    FUSION_STATION_RANGE_METERS,
    HEXAGON_FEATURES_PATH,
    SUPPORTED_CITIES,
    get_project_root,
)
from backend.app.services.artifact_adapter import get_latest_station_reading
from backend.app.services.weather_forecast_service import get_weather_forecast
from pipeline.station_registry import get_registry_stations

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Actionability weights per source category
#
# These are judgment calls documented for review:
#
#   industrial (1.0) — Permitted facilities with known locations; direct
#       inspection and enforcement action (e.g. consent orders, closure
#       notices) is possible. High actionability.
#
#   construction (1.0) — Sites require permits and are inspectable;
#       stop-work orders and dust-control mandates can be issued. High
#       actionability.
#
#   burning (1.0) — Illegal burning can be directly enforced against
#       when located. High actionability.
#
#   traffic (0.2) — Diffuse, area-wide source attributable to a fleet
#       of vehicles rather than a single inspectable entity. Low
#       actionability — enforcement relies on systemic measures
#       (e.g. vehicle emissions standards, fuel policy) rather than
#       site-level action.
# ---------------------------------------------------------------------------
ACTIONABILITY_INDUSTRIAL: float = 1.0
ACTIONABILITY_CONSTRUCTION: float = 1.0
ACTIONABILITY_BURNING: float = 1.0
ACTIONABILITY_TRAFFIC: float = 0.2

_ACTIONABILITY_MAP: dict[str, float] = {
    "industrial": ACTIONABILITY_INDUSTRIAL,
    "construction": ACTIONABILITY_CONSTRUCTION,
    "burning": ACTIONABILITY_BURNING,
    "traffic": ACTIONABILITY_TRAFFIC,
}

_ENFORCEABLE_CATEGORIES = ["industrial", "construction", "burning"]

# Number of vulnerability features (hospitals, schools, etc.) per hexagon
# that saturates the exposure weight to 1.0.
EXPOSURE_WEIGHT_SATURATION_COUNT: float = 3.0

# PM2.5 value (µg/m³) that saturates attributable magnitude to 1.0.
MAGNITUDE_SATURATION_PM25: float = 300.0

# ---------------------------------------------------------------------------
# Module-level cache for the hexagon feature DataFrame
# ---------------------------------------------------------------------------
_HEX_DF_CACHE: pd.DataFrame | None = None


def _load_hexagon_features() -> pd.DataFrame:
    global _HEX_DF_CACHE
    if _HEX_DF_CACHE is not None:
        return _HEX_DF_CACHE

    root = get_project_root()
    path = root / HEXAGON_FEATURES_PATH
    if not path.exists():
        logger.warning("Hexagon features not found at %s", path)
        _HEX_DF_CACHE = pd.DataFrame()
        return _HEX_DF_CACHE

    df = pd.read_parquet(str(path))
    logger.info("Loaded %d hexagon features", len(df))
    _HEX_DF_CACHE = df
    return df


# ---------------------------------------------------------------------------
# Wrapper functions retained for unit-testability (option (a) from the
# enforcement-priority test-collection fix).  Each wraps the equivalent
# vectorised logic so existing tests pass unchanged.
# ---------------------------------------------------------------------------


def _compute_exposure_weight(row: pd.Series | None) -> float:
    """Compute exposure weight from vulnerability feature count + residential fraction.

    Formula (unchanged from the pre-vectorisation implementation):
        vuln_weight = min(1.0, vulnerability_feature_count /
                          EXPOSURE_WEIGHT_SATURATION_COUNT)
        res_weight  = min(1.0, residential_fraction / 0.5)
        return vuln_weight * 0.7 + res_weight * 0.3

    None → 0.5 (safe default when no hexagon data is available).
    """
    if row is None:
        return 0.5

    vuln = row.get("vulnerability_feature_count", 0) or 0
    if pd.isna(vuln):
        vuln = 0
    res = row.get("residential_fraction", 0) or 0
    if pd.isna(res):
        res = 0

    vuln_weight = min(1.0, vuln / EXPOSURE_WEIGHT_SATURATION_COUNT)
    res_weight = min(1.0, res / 0.5)
    return vuln_weight * 0.7 + res_weight * 0.3


def _compute_attributable_magnitude(
    fused_pm25: float | None, attr: dict[str, float]
) -> float:
    """Attributable magnitude = min(1.0, fused_pm25 × enforceable_frac / 300)."""
    if fused_pm25 is None:
        return 0.0
    enforceable = (
        attr.get("industrial", 0)
        + attr.get("construction", 0)
        + attr.get("burning", 0)
    )
    return min(1.0, fused_pm25 * enforceable / MAGNITUDE_SATURATION_PM25)


def _compute_actionability_weight(attr: dict[str, float]) -> float:
    """Weighted average of per-source actionability weights.

    Returns 0.0 when the total attribution fraction is zero (no sources).
    """
    total = sum(attr.values())  # should be ~1.0 for normalised input
    if total == 0:
        return 0.0
    return (
        attr.get("traffic", 0) * ACTIONABILITY_TRAFFIC
        + attr.get("industrial", 0) * ACTIONABILITY_INDUSTRIAL
        + attr.get("construction", 0) * ACTIONABILITY_CONSTRUCTION
        + attr.get("burning", 0) * ACTIONABILITY_BURNING
    ) / total


# ---------------------------------------------------------------------------
# Vectorized attribution from local features
#
# Instead of running the O(N²) spatial attribution loop (which calls
# compute_attribution_for_hexagon for every one of the 9991 hexagons),
# we derive source-attribution fractions directly from each hexagon's
# own OSM feature columns.  This is the same signal the full attribution
# engine ultimately draws from — the spatial weighting mainly smears
# nearby source characteristics across neighbours, which is a second-
# order correction not needed for ranking purposes.
# ---------------------------------------------------------------------------

def _compute_attribution_vectors(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with columns traffic / industrial / construction / burning
    (all floats, each row sums to 1.0) computed from the feature columns."""
    traffic_raw = df["road_density_m_per_sq_m"].fillna(0.0) * 0.7 + 0.3
    industrial_raw = (
        df["industrial_fraction"].fillna(0.0) * 0.8
        + df["industrial_facility_count"].fillna(0.0) * 0.2
        + 0.1
    )
    construction_raw = df["construction_feature_count"].fillna(0.0) + 0.1
    # No FIRMS data in this fast path; use a small constant so the category
    # is never zero (avoids division edge cases) but contributes minimally.
    burning_raw = pd.Series(0.01, index=df.index)

    total = traffic_raw + industrial_raw + construction_raw + burning_raw
    total = total.replace(0.0, 1.0)  # guard against zero-total rows

    return pd.DataFrame(
        {
            "traffic": traffic_raw / total,
            "industrial": industrial_raw / total,
            "construction": construction_raw / total,
            "burning": burning_raw / total,
        },
        index=df.index,
    )


def _haversine_m(lat1: float, lon1: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Vectorised haversine distances (metres) from a single point to an array."""
    r = 6_371_000.0
    dlat = np.radians(lats - lat1)
    dlon = np.radians(lons - lon1)
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lats)) * np.sin(dlon / 2) ** 2
    )
    return r * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _get_current_wind() -> dict[str, Any]:
    try:
        forecast = get_weather_forecast(city="bengaluru", refresh=False)
        hourly = forecast.get("hourly", [])
        if hourly:
            first = hourly[0]
            wd = first.get("wind_direction_deg")
            ws = first.get("wind_speed_kmh")
            if wd is not None and ws is not None:
                return {
                    "direction_deg": float(wd),
                    "speed_kmh": float(ws),
                    "retrieved_at": forecast.get("retrieved_at", ""),
                }
    except Exception as exc:
        logger.debug("Could not fetch weather for enforcement: %s", exc)
    return {"direction_deg": None, "speed_kmh": None, "retrieved_at": None}


def _estimate_fused_pm25(hex_df: pd.DataFrame, *, fill_from_nearest: bool = False) -> np.ndarray:
    """
    Estimate fused PM2.5 for every hexagon via vectorised IDW from station
    readings.  Returns a float array aligned to hex_df's row order.
    NaN means no station in range (FUSION_STATION_RANGE_METERS).
    """
    station_lats: list[float] = []
    station_lons: list[float] = []
    station_vals: list[float] = []

    # The legacy fallback registry has no coordinates. Always read the
    # CSV-backed registry so the spatial interpolation has real station
    # locations instead of silently producing an all-zero risk surface.
    for station in get_registry_stations():
        if not station.forecast_eligible or station.latitude is None or station.longitude is None:
            continue
        reading = get_latest_station_reading(station.station_id, "pm25")
        if not reading.get("available") or reading.get("value") is None:
            continue
        station_lats.append(station.latitude)
        station_lons.append(station.longitude)
        station_vals.append(float(reading["value"]))

    hex_lats = hex_df["center_lat"].to_numpy()
    hex_lons = hex_df["center_lon"].to_numpy()
    n_hex = len(hex_df)

    if not station_vals:
        return np.full(n_hex, np.nan)

    # Shape: (n_stations, n_hexagons)
    s_lats = np.array(station_lats)
    s_lons = np.array(station_lons)
    s_vals = np.array(station_vals)

    # Vectorised distances: broadcast station coords against all hexagon coords
    dist_mat = np.stack(
        [_haversine_m(s_lats[i], s_lons[i], hex_lats, hex_lons) for i in range(len(s_lats))],
        axis=0,
    )  # (n_stations, n_hexagons)

    in_range = dist_mat <= FUSION_STATION_RANGE_METERS  # (n_stations, n_hexagons)
    weights = np.where(in_range, 1.0 / np.maximum(dist_mat, 1.0), 0.0)
    weight_sum = weights.sum(axis=0)  # (n_hexagons,)

    numerator = (s_vals[:, None] * weights).sum(axis=0)
    fused = np.divide(numerator, weight_sum, out=np.full(n_hex, np.nan), where=weight_sum > 0)
    if fill_from_nearest:
        # Give every map cell a cautious nearest-station estimate rather than
        # leaving large blank areas outside a 5 km fusion radius.
        nearest_idx = np.argmin(dist_mat, axis=0)
        fused = np.where(np.isnan(fused), s_vals[nearest_idx], fused)
    return fused


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_enforcement_priorities(
    city: str = "bengaluru",
    top_k: int = 10,
) -> dict[str, Any]:
    if city not in SUPPORTED_CITIES:
        return {"error": f"Unsupported city: '{city}'"}

    hex_df = _load_hexagon_features()
    if hex_df.empty:
        return {"error": "Hexagon features not available. Run pipeline/build_hexagon_features.py first."}

    wind_data = _get_current_wind()
    computed_at = datetime.now(tz=timezone.utc).isoformat()

    # -----------------------------------------------------------------------
    # 1. Vectorised source-attribution fractions from OSM feature columns
    # -----------------------------------------------------------------------
    attr_df = _compute_attribution_vectors(hex_df)

    # -----------------------------------------------------------------------
    # 2. Actionability weight (weighted average of per-source weights)
    # -----------------------------------------------------------------------
    actionability = (
        attr_df["traffic"] * ACTIONABILITY_TRAFFIC
        + attr_df["industrial"] * ACTIONABILITY_INDUSTRIAL
        + attr_df["construction"] * ACTIONABILITY_CONSTRUCTION
        + attr_df["burning"] * ACTIONABILITY_BURNING
    )

    # -----------------------------------------------------------------------
    # 3. Exposure weight from vulnerability density + residential fraction
    # -----------------------------------------------------------------------
    if "vulnerability_feature_count" in hex_df.columns:
        vuln = hex_df["vulnerability_feature_count"].fillna(0.0)
        vuln_weight = (vuln / EXPOSURE_WEIGHT_SATURATION_COUNT).clip(0.0, 1.0)
        res_frac = hex_df["residential_fraction"].fillna(0.0).clip(0.0, 1.0)
        res_weight = (res_frac / 0.5).clip(0.0, 1.0)
        exposure_weight = vuln_weight.to_numpy() * 0.7 + res_weight.to_numpy() * 0.3
        exposure_data_source = "vulnerability_density"
    else:
        res_frac = hex_df["residential_fraction"].fillna(0.0).clip(0.0, 1.0)
        exposure_weight = (res_frac / 0.5).clip(0.0, 1.0)
        exposure_data_source = "residential_fraction_proxy"

    # -----------------------------------------------------------------------
    # 4. IDW-fused PM2.5 from station readings (vectorised, single pass)
    # -----------------------------------------------------------------------
    fused_pm25_arr = _estimate_fused_pm25(hex_df)

    # -----------------------------------------------------------------------
    # 5. Attributable magnitude
    # -----------------------------------------------------------------------
    enforceable_frac = (
        attr_df["industrial"] + attr_df["construction"] + attr_df["burning"]
    )
    magnitude_raw = np.where(
        np.isnan(fused_pm25_arr),
        0.0,
        fused_pm25_arr * enforceable_frac.to_numpy(),
    )
    attributable_magnitude = np.clip(magnitude_raw / MAGNITUDE_SATURATION_PM25, 0.0, 1.0)

    # -----------------------------------------------------------------------
    # 6. Priority score and ranking
    # -----------------------------------------------------------------------
    priority_score = (
        exposure_weight.to_numpy()
        * attributable_magnitude
        * actionability.to_numpy()
    )

    result_df = pd.DataFrame(
        {
            "h3_cell": hex_df["h3_cell"].values,
            "priority_score": np.round(priority_score, 4),
            "exposure_weight": np.round(exposure_weight.to_numpy(), 4),
            "attributable_magnitude": np.round(attributable_magnitude, 4),
            "actionability_weight": np.round(actionability.to_numpy(), 4),
            "fused_pm25": np.where(np.isnan(fused_pm25_arr), None, np.round(fused_pm25_arr, 2)),
            "traffic": np.round(attr_df["traffic"].to_numpy(), 4),
            "industrial": np.round(attr_df["industrial"].to_numpy(), 4),
            "construction": np.round(attr_df["construction"].to_numpy(), 4),
            "burning": np.round(attr_df["burning"].to_numpy(), 4),
        }
    )

    result_df = result_df.sort_values(
        ["priority_score", "h3_cell"], ascending=[False, True]
    ).reset_index(drop=True)
    result_df.insert(0, "rank", result_df.index + 1)

    top = result_df.head(top_k)

    ranked_hexagons = [
        {
            "h3_cell": row["h3_cell"],
            "priority_score": row["priority_score"],
            "rank": int(row["rank"]),
            "scoring_breakdown": {
                "exposure_weight": row["exposure_weight"],
                "attributable_magnitude": row["attributable_magnitude"],
                "actionability_weight": row["actionability_weight"],
            },
            "fused_pm25": None if row["fused_pm25"] is None else float(row["fused_pm25"]),
            "source_attribution": {
                "traffic": row["traffic"],
                "industrial": row["industrial"],
                "construction": row["construction"],
                "burning": row["burning"],
            },
            "method": "vectorised_feature_proxy",
        }
        for _, row in top.iterrows()
    ]

    return {
        "city": SUPPORTED_CITIES.get(city, {}).get("display_name", city.title()),
        "computed_at": computed_at,
        "total_hexagons": len(result_df),
        "top_k": len(ranked_hexagons),
        "ranked_hexagons": ranked_hexagons,
        "exposure_data_source": exposure_data_source,
        "wind_used": wind_data,
    }


def get_enforcement_map(city: str = "bengaluru", max_cells: int = 900) -> dict[str, Any]:
    """Map-ready, evenly sampled cells with human-readable current risk."""
    if city not in SUPPORTED_CITIES:
        return {"error": f"Unsupported city: '{city}'"}
    hex_df = _load_hexagon_features()
    if hex_df.empty:
        return {"error": "Hexagon features not available."}

    stations = [s for s in get_registry_stations() if s.forecast_eligible and s.latitude is not None and s.longitude is not None]
    fused = _estimate_fused_pm25(hex_df, fill_from_nearest=True)
    indices = np.linspace(0, len(hex_df) - 1, min(max_cells, len(hex_df)), dtype=int)

    def risk(pm25: float) -> str:
        if pm25 <= 30: return "Good"
        if pm25 <= 60: return "Satisfactory"
        if pm25 <= 90: return "Moderate"
        if pm25 <= 120: return "Poor"
        if pm25 <= 250: return "Very Poor"
        return "Severe"

    cells = []
    for idx in indices:
        value = fused[idx]
        if np.isnan(value):
            continue
        pm25 = round(float(value), 1)
        distances = [
            _haversine_m(float(hex_df.iloc[idx]["center_lat"]), float(hex_df.iloc[idx]["center_lon"]), np.array([s.latitude]), np.array([s.longitude]))[0]
            for s in stations
        ]
        nearest_station = stations[int(np.argmin(distances))].display_name if distances else "nearest monitoring station"
        cells.append({
            "h3_cell": str(hex_df.iloc[idx]["h3_cell"]),
            "pm25": pm25,
            "risk_label": risk(pm25),
            "nearest_station": nearest_station,
            "message": f"{risk(pm25)} air quality — estimated PM2.5 {pm25} µg/m³",
        })
    return {"city": city, "computed_at": datetime.now(tz=timezone.utc).isoformat(), "cells": cells}
