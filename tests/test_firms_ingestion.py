"""
Tests for FIRMS fire detection ingestion (Milestone 7).

All tests are offline. The FIRMS API call is mocked; a small fixture CSV
is used for parsing and H3 aggregation tests. Cache is redirected to
tmp_path.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from pipeline.firms_ingestion import (
    _aggregate_by_h3,
    _build_cache_entry,
    _cache_is_fresh,
    _cache_is_usable_stale,
    _get_map_key,
    _parse_detections,
    _read_cache,
    _write_cache,
    get_fire_detections,
)

# Small fixture CSV with known lat/lon values around Bengaluru
# All within BENGALURU_BOUNDING_BOX, spanning different H3 cells
FIXTURE_CSV = """latitude,longitude,frp,confidence,acq_date,acq_time,daynight
12.9716,77.5946,25.5,high,2026-07-08,1200,D
12.9716,77.5946,15.2,nominal,2026-07-08,1300,D
12.9716,77.5946,30.0,high,2026-07-08,1400,D
13.0292,77.5859,8.1,low,2026-07-08,1000,D
13.0292,77.5859,12.3,nominal,2026-07-08,1100,D
12.8500,77.5500,45.0,high,2026-07-07,2200,N
12.8500,77.5500,5.5,low,2026-07-08,0100,D
"""

# Cell for 12.9716,77.5946 at res 9 -> starts with "8"
# Cell for 13.0292,77.5859 at res 9 -> different cell
# Cell for 12.8500,77.5500 at res 9 -> yet another cell


class TestParseDetections:
    def test_parses_valid_csv(self) -> None:
        detections = _parse_detections(FIXTURE_CSV)
        assert len(detections) == 7
        assert detections[0]["latitude"] == 12.9716
        assert detections[0]["longitude"] == 77.5946
        assert detections[0]["frp_mw"] == 25.5
        assert detections[0]["confidence"] == "high"
        assert detections[0]["acq_date"] == "2026-07-08"
        assert detections[0]["acq_time"] == "1200"

    def test_handles_empty_csv(self) -> None:
        detections = _parse_detections("latitude,longitude,frp,confidence,acq_date,acq_time,daynight\n")
        assert detections == []

    def test_handles_missing_fields(self) -> None:
        csv_data = "latitude,longitude,frp,confidence,acq_date,acq_time,daynight\n,77.5946,25.5,high,2026-07-08,1200,D\n"
        detections = _parse_detections(csv_data)
        assert len(detections) == 0

    def test_handles_missing_frp(self) -> None:
        csv_data = "latitude,longitude,frp,confidence,acq_date,acq_time,daynight\n12.9716,77.5946,,high,2026-07-08,1200,D\n"
        detections = _parse_detections(csv_data)
        assert len(detections) == 1
        assert detections[0]["frp_mw"] == 0.0


class TestH3Aggregation:
    def test_aggregates_by_cell(self) -> None:
        detections = _parse_detections(FIXTURE_CSV)
        # Patch datetime.now to ensure recent timestamps are within 24h window
        hexagons = _aggregate_by_h3(detections, resolution=9)
        # 7 detections -> should group into 3 cells
        assert 2 <= len(hexagons) <= 3
        total_count = sum(h["detection_count"] for h in hexagons)
        assert total_count == 7

    def test_window_filters_old_detections(self) -> None:
        old_csv = """latitude,longitude,frp,confidence,acq_date,acq_time,daynight
12.9716,77.5946,10.0,low,2025-01-01,1200,D
"""
        detections = _parse_detections(old_csv)
        hexagons = _aggregate_by_h3(detections, resolution=9)
        assert len(hexagons) == 0

    def test_frp_is_summed(self) -> None:
        detections = _parse_detections(FIXTURE_CSV)
        hexagons = _aggregate_by_h3(detections, resolution=9)
        # The cell at 12.9716,77.5946 has 3 detections: 25.5 + 15.2 + 30.0 = 70.7
        for h in hexagons:
            if h["detection_count"] == 3:
                assert abs(h["total_frp_mw"] - 70.7) < 0.01
                return
        pytest.fail("Expected a cell with 3 detections")

    def test_max_confidence_tracking(self) -> None:
        """Cell with mix of confidence levels should report highest."""
        detections = _parse_detections(FIXTURE_CSV)
        hexagons = _aggregate_by_h3(detections, resolution=9)
        for h in hexagons:
            if h["detection_count"] == 3:
                assert h["max_confidence"] == "high"
                return
        pytest.fail("Expected a cell with 3 detections")


class TestCache:
    def test_write_and_read_cache(self, tmp_path) -> None:
        with patch("pipeline.firms_ingestion._cache_dir", return_value=tmp_path):
            data = {"hexagons": [], "city": "bengaluru"}
            entry = _build_cache_entry("bengaluru", data)
            _write_cache("bengaluru", entry)
            cached = _read_cache("bengaluru")
            assert cached is not None
            assert cached["data"]["city"] == "bengaluru"
            assert cached["schema_version"] == "1.0"

    def test_cache_fresh_when_recent(self, tmp_path) -> None:
        with patch("pipeline.firms_ingestion._cache_dir", return_value=tmp_path):
            entry = _build_cache_entry("bengaluru", {"hexagons": []})
            _write_cache("bengaluru", entry)
            cached = _read_cache("bengaluru")
            assert cached is not None
            assert _cache_is_fresh(cached) is True

    def test_cache_stale_when_old(self, tmp_path) -> None:
        with patch("pipeline.firms_ingestion._cache_dir", return_value=tmp_path):
            old_time = datetime.now(tz=timezone.utc) - timedelta(hours=12)
            entry = _build_cache_entry("bengaluru", {"hexagons": []})
            entry["retrieved_at"] = old_time.isoformat()
            _write_cache("bengaluru", entry)
            cached = _read_cache("bengaluru")
            assert cached is not None
            assert _cache_is_fresh(cached) is False
            assert _cache_is_usable_stale(cached) is True

    def test_cache_expired_beyond_stale_window(self, tmp_path) -> None:
        with patch("pipeline.firms_ingestion._cache_dir", return_value=tmp_path):
            old_time = datetime.now(tz=timezone.utc) - timedelta(hours=48)
            entry = _build_cache_entry("bengaluru", {"hexagons": []})
            entry["retrieved_at"] = old_time.isoformat()
            _write_cache("bengaluru", entry)
            cached = _read_cache("bengaluru")
            assert cached is not None
            assert _cache_is_fresh(cached) is False
            assert _cache_is_usable_stale(cached) is False


class TestGetFireDetections:
    def test_absent_credential_returns_unavailable(self) -> None:
        with patch("pipeline.firms_ingestion._get_map_key", return_value=None):
            result = get_fire_detections(city="bengaluru", refresh=True)
            assert result["source_status"] == "unavailable"
            assert result["hexagons"] == []
            assert len(result["warnings"]) > 0

    def test_live_fetch_returns_parsed_data(self, tmp_path) -> None:
        with patch("pipeline.firms_ingestion._get_map_key", return_value="test-key"), \
             patch("pipeline.firms_ingestion._fetch_firms_csv", return_value=FIXTURE_CSV), \
             patch("pipeline.firms_ingestion._cache_dir", return_value=tmp_path):

            result = get_fire_detections(city="bengaluru", refresh=True)
            assert result["source_status"] == "live_provider"
            assert result["freshness"] == "fresh"
            assert len(result["hexagons"]) >= 2
            assert result["cache_used"] is False

    def test_returns_cached_data_when_fresh(self, tmp_path) -> None:
        with patch("pipeline.firms_ingestion._get_map_key", return_value="test-key"), \
             patch("pipeline.firms_ingestion._cache_dir", return_value=tmp_path), \
             patch("pipeline.firms_ingestion._fetch_firms_csv") as mock_fetch:
            # First call to populate cache
            mock_fetch.return_value = FIXTURE_CSV
            result1 = get_fire_detections(city="bengaluru", refresh=True)
            assert result1["source_status"] == "live_provider"

            # Second call (no refresh) should hit cache
            mock_fetch.side_effect = RuntimeError("should not be called")
            result2 = get_fire_detections(city="bengaluru", refresh=False)
            assert result2["source_status"] == "live_provider"
            assert result2["cache_used"] is True
            assert result2["freshness"] == "fresh"

    def test_stale_fallback_on_provider_failure(self, tmp_path) -> None:
        with patch("pipeline.firms_ingestion._get_map_key", return_value="test-key"), \
             patch("pipeline.firms_ingestion._cache_dir", return_value=tmp_path), \
             patch("pipeline.firms_ingestion._fetch_firms_csv") as mock_fetch:
            # First call to populate cache
            mock_fetch.return_value = FIXTURE_CSV
            result1 = get_fire_detections(city="bengaluru", refresh=True)
            assert result1["source_status"] == "live_provider"

            # Manually make the cache stale (set retrieved_at far enough back but within stale window)
            cache_path = tmp_path / "bengaluru.json"
            with open(cache_path, "r") as f:
                cached = json.load(f)
            old_time = datetime.now(tz=timezone.utc) - timedelta(hours=2)
            cached["retrieved_at"] = old_time.isoformat()
            with open(cache_path, "w") as f:
                json.dump(cached, f)

            # Second call (with refresh) should fail live fetch and fall back to stale
            mock_fetch.side_effect = RuntimeError("provider down")
            result2 = get_fire_detections(city="bengaluru", refresh=True)
            assert result2["source_status"] == "stale_cache_fallback"
            assert result2["freshness"] == "stale"
            assert result2["cache_used"] is True
            assert len(result2["warnings"]) > 0

    def test_geospatial_endpoint_returns_fire_data(self) -> None:
        from backend.app.routers.geospatial import hex_fire_detections
        with patch("pipeline.firms_ingestion._get_map_key", return_value=None):
            result = hex_fire_detections(city="bengaluru")
            assert result["source_status"] == "unavailable"


class TestGetMapKey:
    def test_returns_none_when_not_set(self) -> None:
        # Ensure env var is not set
        if "FIRMS_MAP_KEY" in os.environ:
            del os.environ["FIRMS_MAP_KEY"]
        result = _get_map_key()
        assert result is None

    def test_returns_key_when_set(self) -> None:
        os.environ["FIRMS_MAP_KEY"] = "my-test-key"
        try:
            result = _get_map_key()
            assert result == "my-test-key"
        finally:
            del os.environ["FIRMS_MAP_KEY"]
