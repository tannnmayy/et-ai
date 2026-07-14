"""Tests for time-of-day traffic multipliers and corridor-aware attribution."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.app.services import attribution_service
from backend.app.services.attribution_service import compute_attribution_for_hexagon
from backend.app.services.traffic_service import (
    get_traffic_time_multiplier,
    is_peak_hour,
    traffic_time_metadata,
)
from pipeline.traffic_features import (
    is_major_highway,
    normalize_highway_tag,
    score_from_major_length,
)


class TestTrafficTimeMultiplier:
    def test_peak_morning(self) -> None:
        assert get_traffic_time_multiplier(8) == 1.4
        assert is_peak_hour(8) is True

    def test_peak_evening(self) -> None:
        assert get_traffic_time_multiplier(18) == 1.4
        assert is_peak_hour(18) is True

    def test_daytime(self) -> None:
        assert get_traffic_time_multiplier(12) == 1.1
        assert is_peak_hour(12) is False

    def test_night(self) -> None:
        assert get_traffic_time_multiplier(2) == 0.7
        assert is_peak_hour(2) is False

    def test_metadata_bundle(self) -> None:
        meta = traffic_time_metadata(8)
        assert meta["traffic_time_multiplier"] == 1.4
        assert meta["is_peak_hour"] is True
        assert meta["traffic_hour_local"] == 8


class TestHighwayNormalization:
    def test_plain_string(self) -> None:
        assert normalize_highway_tag("primary") == "primary"
        assert is_major_highway("primary") is True
        assert is_major_highway("residential") is False

    def test_stringified_list(self) -> None:
        assert normalize_highway_tag("['secondary']") == "secondary"
        assert is_major_highway("[trunk]") is True

    def test_corridor_score_bounds(self) -> None:
        score, flag = score_from_major_length(0.0, 100_000.0)
        assert score == 0.0
        assert flag is False
        score_hi, flag_hi = score_from_major_length(10_000.0, 100_000.0)
        assert score_hi == 1.0
        assert flag_hi is True


def _make_hex_df_with_corridor(n: int = 8, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    import h3 as _h3

    base_lat, base_lon = 12.97, 77.59
    rows = []
    for i in range(n):
        lat = base_lat + rng.uniform(-0.01, 0.01)
        lon = base_lon + rng.uniform(-0.01, 0.01)
        cell = _h3.latlng_to_cell(lat, lon, 9)
        # First half: strong corridor; second half: none
        corridor = 0.9 if i < n // 2 else 0.0
        rows.append({
            "h3_cell": cell,
            "center_lat": lat,
            "center_lon": lon,
            "road_density_m_per_sq_m": 0.02,
            "traffic_corridor_score": corridor,
            "is_major_road_corridor": corridor >= 0.25,
            "industrial_fraction": 0.05,
            "commercial_fraction": 0.05,
            "residential_fraction": 0.3,
            "green_space_fraction": 0.1,
            "other_landuse_fraction": 0.5,
            "construction_feature_count": 1,
            "industrial_facility_count": 0,
            "road_length_m": 500.0,
            "industrial_area_sq_m": 100.0,
            "commercial_area_sq_m": 100.0,
            "residential_area_sq_m": 1000.0,
            "green_space_area_sq_m": 200.0,
            "other_landuse_area_sq_m": 500.0,
        })
    return pd.DataFrame(rows)


class TestCorridorAttribution:
    def test_corridor_raises_traffic_when_flag_on(self) -> None:
        hex_df = _make_hex_df_with_corridor()
        target = hex_df.iloc[0]["h3_cell"]
        wind = {"direction_deg": 180, "speed_kmh": 12.0, "retrieved_at": "t"}

        prev_corridor = attribution_service.USE_TRAFFIC_CORRIDOR_SCORE
        prev_tod = attribution_service.USE_TIME_OF_DAY_TRAFFIC
        attribution_service.USE_TRAFFIC_CORRIDOR_SCORE = True
        attribution_service.USE_TIME_OF_DAY_TRAFFIC = False
        attribution_service._CORRIDOR_LOGGED = False
        try:
            with_corridor = compute_attribution_for_hexagon(
                target, hex_df=hex_df, wind_data=wind, search_radius_m=50_000,
                simulated_hour=12,
            )
            # Zero out corridor scores → should reduce traffic intensity
            hex_no = hex_df.copy()
            hex_no["traffic_corridor_score"] = 0.0
            without = compute_attribution_for_hexagon(
                target, hex_df=hex_no, wind_data=wind, search_radius_m=50_000,
                simulated_hour=12,
            )
            assert with_corridor["traffic_corridor_applied"] is True
            assert (
                with_corridor["source_intensities"]["traffic_raw"]
                >= without["source_intensities"]["traffic_raw"]
            )
        finally:
            attribution_service.USE_TRAFFIC_CORRIDOR_SCORE = prev_corridor
            attribution_service.USE_TIME_OF_DAY_TRAFFIC = prev_tod

    def test_missing_corridor_column_falls_back(self) -> None:
        hex_df = _make_hex_df_with_corridor().drop(
            columns=["traffic_corridor_score", "is_major_road_corridor"]
        )
        target = hex_df.iloc[0]["h3_cell"]
        wind = {"direction_deg": 180, "speed_kmh": 12.0, "retrieved_at": "t"}
        prev = attribution_service.USE_TRAFFIC_CORRIDOR_SCORE
        attribution_service.USE_TRAFFIC_CORRIDOR_SCORE = True
        attribution_service._CORRIDOR_LOGGED = False
        try:
            result = compute_attribution_for_hexagon(
                target, hex_df=hex_df, wind_data=wind, search_radius_m=50_000,
            )
            assert result["traffic_corridor_applied"] is False
            total = sum(result["source_attribution"].values())
            assert abs(total - 1.0) < 0.01
        finally:
            attribution_service.USE_TRAFFIC_CORRIDOR_SCORE = prev

    def test_peak_hour_increases_traffic_fraction(self) -> None:
        hex_df = _make_hex_df_with_corridor()
        target = hex_df.iloc[0]["h3_cell"]
        wind = {"direction_deg": 180, "speed_kmh": 12.0, "retrieved_at": "t"}

        prev_tod = attribution_service.USE_TIME_OF_DAY_TRAFFIC
        prev_cor = attribution_service.USE_TRAFFIC_CORRIDOR_SCORE
        attribution_service.USE_TIME_OF_DAY_TRAFFIC = True
        attribution_service.USE_TRAFFIC_CORRIDOR_SCORE = False
        try:
            peak = compute_attribution_for_hexagon(
                target, hex_df=hex_df, wind_data=wind, search_radius_m=50_000,
                simulated_hour=8,
            )
            night = compute_attribution_for_hexagon(
                target, hex_df=hex_df, wind_data=wind, search_radius_m=50_000,
                simulated_hour=2,
            )
            assert peak["is_peak_hour"] is True
            assert night["is_peak_hour"] is False
            assert peak["traffic_time_multiplier"] == 1.4
            assert night["traffic_time_multiplier"] == 0.7
            assert peak["source_attribution"]["traffic"] >= night["source_attribution"]["traffic"]
        finally:
            attribution_service.USE_TIME_OF_DAY_TRAFFIC = prev_tod
            attribution_service.USE_TRAFFIC_CORRIDOR_SCORE = prev_cor
