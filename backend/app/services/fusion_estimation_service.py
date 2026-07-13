from __future__ import annotations

"""Shared, range-limited station interpolation for map-ranking services."""

import numpy as np
import pandas as pd

from backend.app.config import FUSION_STATION_RANGE_METERS
from backend.app.services.artifact_adapter import get_latest_station_reading
from pipeline.station_registry import get_registry_stations

_EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(lat1: float, lon1: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Vectorised distance in metres from one location to many locations."""
    dlat = np.radians(lats - lat1)
    dlon = np.radians(lons - lon1)
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lats)) * np.sin(dlon / 2) ** 2
    )
    return _EARTH_RADIUS_M * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def estimate_fused_pm25(hex_df: pd.DataFrame) -> np.ndarray:
    """IDW-estimate PM2.5 only where at least one live station is in range.

    A ``NaN`` is intentional: it means the hexagon is outside the configured
    fusion range and must not be represented as a live, station-informed value.
    """
    station_lats: list[float] = []
    station_lons: list[float] = []
    station_vals: list[float] = []

    for station in get_registry_stations():
        if not station.forecast_eligible or station.latitude is None or station.longitude is None:
            continue
        reading = get_latest_station_reading(station.station_id, "pm25")
        if not reading.get("available") or reading.get("value") is None:
            continue
        station_lats.append(station.latitude)
        station_lons.append(station.longitude)
        station_vals.append(float(reading["value"]))

    n_hex = len(hex_df)
    if not station_vals:
        return np.full(n_hex, np.nan)

    hex_lats = hex_df["center_lat"].to_numpy()
    hex_lons = hex_df["center_lon"].to_numpy()
    s_lats = np.asarray(station_lats)
    s_lons = np.asarray(station_lons)
    s_vals = np.asarray(station_vals)
    distances = np.stack(
        [_haversine_m(s_lats[i], s_lons[i], hex_lats, hex_lons) for i in range(len(s_lats))],
        axis=0,
    )
    in_range = distances <= FUSION_STATION_RANGE_METERS
    weights = np.where(in_range, 1.0 / np.maximum(distances, 1.0), 0.0)
    weight_sum = weights.sum(axis=0)
    numerator = (s_vals[:, None] * weights).sum(axis=0)
    return np.divide(numerator, weight_sum, out=np.full(n_hex, np.nan), where=weight_sum > 0)
