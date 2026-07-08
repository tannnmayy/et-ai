from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest

from backend.app.services.attribution_service import (
    _bearing_deg,
    _cosine_weight,
    _haversine_distance_m,
    compute_attribution_for_hexagon,
    compute_fusion_for_hexagon,
)


def test_haversine_distance_known_values():
    d = _haversine_distance_m(0, 0, 0, 1)
    assert abs(d - 111195.1) < 1000, f"Expected ~111km, got {d}"

    d2 = _haversine_distance_m(12.9716, 77.5946, 12.9716, 77.5946)
    assert d2 == 0.0


def test_bearing_known_values():
    b = _bearing_deg(0, 0, 1, 0)
    assert abs(b - 0) < 0.1, f"Bearing North should be 0, got {b}"

    b2 = _bearing_deg(0, 0, 0, 1)
    assert abs(b2 - 90) < 0.1, f"Bearing East should be 90, got {b2}"

    b3 = _bearing_deg(0, 0, -1, 0)
    assert abs(b3 - 180) < 0.1, f"Bearing South should be 180, got {b3}"

    b4 = _bearing_deg(0, 0, 0, -1)
    assert abs(b4 - 270) < 0.1, f"Bearing West should be 270, got {b4}"


def test_cosine_weight_downwind_higher_than_upwind():
    w_downwind = _cosine_weight(0, 180)
    w_upwind = _cosine_weight(0, 0)
    assert w_downwind > w_upwind, "Source upwind (wind coming from source direction) should get higher weight"

    assert w_upwind == 0.0, "Source directly downwind should get zero weight"


def test_cosine_weight_crosswind():
    w_crosswind = _cosine_weight(90, 0)
    assert abs(w_crosswind) < 1e-15, "Crosswind (perpendicular) should get near-zero weight"

    w_at_45 = _cosine_weight(45, 180)
    expected = max(0, math.cos(math.radians(45)))
    assert abs(w_at_45 - expected) < 1e-10


def test_cosine_weight_identical_direction():
    w = _cosine_weight(90, 270)
    assert abs(w - 1.0) < 1e-10, "Directly upwind should get weight 1"


def test_compute_attribution_hex_not_found():
    result = compute_attribution_for_hexagon("nonexistent_cell")
    assert result["method"] == "unavailable" or result["source_hexagons_contributing"] == 0


def test_compute_attribution_sums_to_100():
    hex_df = _make_synthetic_hex_features(10)
    target = hex_df.iloc[0]["h3_cell"]
    wind_data = {"direction_deg": 180, "speed_kmh": 10, "retrieved_at": "2026-07-08T12:00:00Z"}
    result = compute_attribution_for_hexagon(
        target, hex_df=hex_df, wind_data=wind_data, search_radius_m=50000,
    )
    attr = result["source_attribution"]
    total = attr["traffic"] + attr["industrial"] + attr["construction"] + attr["burning"]
    assert abs(total - 1.0) < 0.01, f"Attribution should sum to ~1.0, got {total}"


def test_burning_from_firms_data():
    hex_df = _make_synthetic_hex_features(5)
    target = hex_df.iloc[0]["h3_cell"]
    firms_lookup = {row["h3_cell"]: i * 3 for i, (_, row) in enumerate(hex_df.iterrows())}
    wind_data = {"direction_deg": 180, "speed_kmh": 10, "retrieved_at": "2026-07-08T12:00:00Z"}
    result = compute_attribution_for_hexagon(
        target, hex_df=hex_df, wind_data=wind_data, firms_lookup=firms_lookup, search_radius_m=50000,
    )
    attr = result["source_attribution"]
    assert attr["burning"] > 0, "Burning should be non-zero with FIRMS data"
    total = attr["traffic"] + attr["industrial"] + attr["construction"] + attr["burning"]
    assert abs(total - 1.0) < 0.01


def test_firms_unavailable_fallback():
    hex_df = _make_synthetic_hex_features(5)
    target = hex_df.iloc[0]["h3_cell"]
    result_with = compute_attribution_for_hexagon(
        target, hex_df=hex_df, wind_data=None, firms_lookup={}, search_radius_m=50000,
    )
    result_without = compute_attribution_for_hexagon(
        target, hex_df=hex_df, wind_data=None, firms_lookup=None, search_radius_m=50000,
    )
    for key in ["traffic", "industrial", "construction", "burning"]:
        assert abs(result_with["source_attribution"][key] - result_without["source_attribution"][key]) < 1e-6


def test_no2_modulates_traffic():
    hex_df = _make_synthetic_hex_features(10, seed=1)
    target = hex_df.iloc[0]["h3_cell"]
    wind_data = {"direction_deg": 180, "speed_kmh": 10, "retrieved_at": "2026-07-08T12:00:00Z"}

    low_no2 = {row["h3_cell"]: 0.0001 for _, row in hex_df.iterrows()}
    high_no2 = {row["h3_cell"]: 0.01 for _, row in hex_df.iterrows()}

    result_low = compute_attribution_for_hexagon(
        target, hex_df=hex_df, wind_data=wind_data, no2_lookup=low_no2, search_radius_m=50000,
    )
    result_high = compute_attribution_for_hexagon(
        target, hex_df=hex_df, wind_data=wind_data, no2_lookup=high_no2, search_radius_m=50000,
    )
    assert result_high["source_intensities"]["traffic_raw"] >= result_low["source_intensities"]["traffic_raw"]


def test_calm_wind_fallback_triggered():
    hex_df = _make_synthetic_hex_features(10)
    target = hex_df.iloc[0]["h3_cell"]
    calm_wind = {"direction_deg": 180, "speed_kmh": 0.5, "retrieved_at": "2026-07-08T12:00:00Z"}
    result = compute_attribution_for_hexagon(
        target, hex_df=hex_df, wind_data=calm_wind, search_radius_m=50000,
    )
    assert result["method"] == "calm_fallback", f"Expect calm_fallback, got {result['method']}"


def test_wind_weighted_when_enough_wind():
    hex_df = _make_synthetic_hex_features(10)
    target = hex_df.iloc[0]["h3_cell"]
    windy = {"direction_deg": 180, "speed_kmh": 15.0, "retrieved_at": "2026-07-08T12:00:00Z"}
    result = compute_attribution_for_hexagon(
        target, hex_df=hex_df, wind_data=windy, search_radius_m=50000,
    )
    assert result["method"] == "wind_weighted", f"Expect wind_weighted, got {result['method']}"


def test_attribution_no_sources_in_range():
    hex_df = _make_synthetic_hex_features(3)
    target = hex_df.iloc[2]["h3_cell"]
    windy = {"direction_deg": 180, "speed_kmh": 15.0, "retrieved_at": "2026-07-08T12:00:00Z"}
    result = compute_attribution_for_hexagon(
        target, hex_df=hex_df, wind_data=windy, search_radius_m=0.001,
    )
    assert result["source_hexagons_contributing"] == 0


def test_fusion_empty_df_returns_defaults():
    result = compute_fusion_for_hexagon("any_cell", hex_df=pd.DataFrame())
    assert result["fused_pm25"] is None
    assert result["stations_contributing"] == 0


def test_fusion_stations_out_of_range_returns_defaults():
    hex_df = _make_synthetic_hex_features(5)
    target = hex_df.iloc[0]["h3_cell"]
    result = compute_fusion_for_hexagon(target, hex_df=hex_df, station_range_m=0.001)
    assert result["stations_contributing"] == 0


def test_distance_self_is_zero():
    d = _haversine_distance_m(12.97, 77.59, 12.97, 77.59)
    assert d == 0.0


def _make_synthetic_hex_features(n: int = 5, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    import h3 as _h3

    # Create hexagon cells near Bengaluru center
    base_lat, base_lon = 12.97, 77.59
    offset = 0.01

    rows = []
    for i in range(n):
        lat = base_lat + rng.uniform(-offset, offset)
        lon = base_lon + rng.uniform(-offset, offset)
        cell = _h3.latlng_to_cell(lat, lon, 9)

        road_density = rng.uniform(0, 0.05)
        industrial_frac = rng.uniform(0, 0.3)
        commercial_frac = rng.uniform(0, 0.3)
        residential_frac = rng.uniform(0, 0.3)
        green_frac = rng.uniform(0, 0.3)
        other_frac = 1.0 - industrial_frac - commercial_frac - residential_frac - green_frac
        other_frac = max(0, other_frac)

        rows.append({
            "h3_cell": cell,
            "center_lat": lat,
            "center_lon": lon,
            "road_density_m_per_sq_m": road_density,
            "industrial_fraction": industrial_frac,
            "commercial_fraction": commercial_frac,
            "residential_fraction": residential_frac,
            "green_space_fraction": green_frac,
            "other_landuse_fraction": other_frac,
            "construction_feature_count": int(rng.integers(0, 10)),
            "industrial_facility_count": int(rng.integers(0, 5)),
            "road_length_m": rng.uniform(100, 1000),
            "industrial_area_sq_m": rng.uniform(0, 5000),
            "commercial_area_sq_m": rng.uniform(0, 5000),
            "residential_area_sq_m": rng.uniform(0, 5000),
            "green_space_area_sq_m": rng.uniform(0, 5000),
            "other_landuse_area_sq_m": rng.uniform(0, 5000),
        })

    return pd.DataFrame(rows)
