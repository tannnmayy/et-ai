"""
Tests for Sentinel-5P NO2 column density ingestion (Milestone 7).

All tests are offline. The GEE API call is mocked via a thin
_fetch_gee_no2 patch. Cache is redirected to tmp_path.

The ingestion function is structured so the GEE-calling code is a thin,
separately-testable layer (_fetch_gee_no2). Everything else (parsing,
H3 aggregation, caching, stale-fallback) is tested against a fixture
that simulates its output shape.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from pipeline.sentinel5p_ingestion import (
    _build_cache_entry,
    _cache_is_fresh,
    _cache_is_usable_stale,
    _get_h3_cells_in_bbox,
    _get_service_account_path,
    _read_cache,
    _write_cache,
    get_no2_column_density,
)

FIXTURE_NO2_DATA: dict[str, float] = {
    "893c1b2d7ffffff": 3.5e-5,
    "893c1b2d7fffffe": 4.2e-5,
    "893c1b2d7fffffd": 2.8e-5,
}


class TestH3CellsInBBox:
    def test_returns_list_of_cells(self) -> None:
        from backend.app.config import BENGALURU_BOUNDING_BOX

        cells = _get_h3_cells_in_bbox(BENGALURU_BOUNDING_BOX, resolution=9)
        assert len(cells) > 0
        assert all(isinstance(c, str) for c in cells)
        assert all(c.startswith("8") for c in cells)


class TestCache:
    def test_write_and_read_cache(self, tmp_path) -> None:
        with patch("pipeline.sentinel5p_ingestion._cache_dir", return_value=tmp_path):
            data = {"hexagons": [], "city": "bengaluru"}
            entry = _build_cache_entry("bengaluru", data)
            _write_cache("bengaluru", entry)
            cached = _read_cache("bengaluru")
            assert cached is not None
            assert cached["data"]["city"] == "bengaluru"
            assert cached["schema_version"] == "1.0"

    def test_cache_fresh_when_recent(self, tmp_path) -> None:
        with patch("pipeline.sentinel5p_ingestion._cache_dir", return_value=tmp_path):
            entry = _build_cache_entry("bengaluru", {"hexagons": []})
            _write_cache("bengaluru", entry)
            cached = _read_cache("bengaluru")
            assert _cache_is_fresh(cached) is True

    def test_cache_stale_when_old(self, tmp_path) -> None:
        with patch("pipeline.sentinel5p_ingestion._cache_dir", return_value=tmp_path):
            old_time = datetime.now(tz=timezone.utc) - timedelta(hours=36)
            entry = _build_cache_entry("bengaluru", {"hexagons": []})
            entry["retrieved_at"] = old_time.isoformat()
            _write_cache("bengaluru", entry)
            cached = _read_cache("bengaluru")
            assert _cache_is_fresh(cached) is False
            assert _cache_is_usable_stale(cached) is True

    def test_cache_expired_beyond_stale_window(self, tmp_path) -> None:
        with patch("pipeline.sentinel5p_ingestion._cache_dir", return_value=tmp_path):
            old_time = datetime.now(tz=timezone.utc) - timedelta(hours=72)
            entry = _build_cache_entry("bengaluru", {"hexagons": []})
            entry["retrieved_at"] = old_time.isoformat()
            _write_cache("bengaluru", entry)
            cached = _read_cache("bengaluru")
            assert _cache_is_fresh(cached) is False
            assert _cache_is_usable_stale(cached) is False


class TestGetServiceAccountPath:
    def test_returns_none_when_not_set(self) -> None:
        if "GEE_SERVICE_ACCOUNT_KEY_PATH" in os.environ:
            del os.environ["GEE_SERVICE_ACCOUNT_KEY_PATH"]
        result = _get_service_account_path()
        assert result is None

    def test_returns_path_when_set(self) -> None:
        os.environ["GEE_SERVICE_ACCOUNT_KEY_PATH"] = "/path/to/key.json"
        try:
            result = _get_service_account_path()
            assert result == "/path/to/key.json"
        finally:
            del os.environ["GEE_SERVICE_ACCOUNT_KEY_PATH"]


class TestGetNO2ColumnDensity:
    def test_absent_credential_returns_unavailable(self) -> None:
        with patch("pipeline.sentinel5p_ingestion._get_service_account_path", return_value=None):
            result = get_no2_column_density(city="bengaluru", refresh=True)
            assert result["source_status"] == "unavailable"
            assert result["hexagons"] == []
            assert len(result["warnings"]) > 0

    def test_live_fetch_returns_parsed_data(self, tmp_path) -> None:
        with patch("pipeline.sentinel5p_ingestion._get_service_account_path", return_value="/fake/path"), \
             patch("pipeline.sentinel5p_ingestion._cache_dir", return_value=tmp_path), \
             patch("pipeline.sentinel5p_ingestion._fetch_gee_no2", return_value=FIXTURE_NO2_DATA):
            result = get_no2_column_density(city="bengaluru", refresh=True)
            assert result["source_status"] == "live_provider"
            assert result["freshness"] == "fresh"
            assert len(result["hexagons"]) == 3
            assert result["cache_used"] is False

    def test_returns_cached_data_when_fresh(self, tmp_path) -> None:
        with patch("pipeline.sentinel5p_ingestion._get_service_account_path", return_value="/fake/path"), \
             patch("pipeline.sentinel5p_ingestion._cache_dir", return_value=tmp_path), \
             patch("pipeline.sentinel5p_ingestion._fetch_gee_no2") as mock_fetch:
            mock_fetch.return_value = FIXTURE_NO2_DATA
            result1 = get_no2_column_density(city="bengaluru", refresh=True)
            assert result1["source_status"] == "live_provider"

            mock_fetch.side_effect = RuntimeError("should not be called")
            result2 = get_no2_column_density(city="bengaluru", refresh=False)
            assert result2["source_status"] == "live_provider"
            assert result2["cache_used"] is True
            assert result2["freshness"] == "fresh"

    def test_stale_fallback_on_provider_failure(self, tmp_path) -> None:
        with patch("pipeline.sentinel5p_ingestion._get_service_account_path", return_value="/fake/path"), \
             patch("pipeline.sentinel5p_ingestion._cache_dir", return_value=tmp_path), \
             patch("pipeline.sentinel5p_ingestion._fetch_gee_no2") as mock_fetch:
            mock_fetch.return_value = FIXTURE_NO2_DATA
            result1 = get_no2_column_density(city="bengaluru", refresh=True)
            assert result1["source_status"] == "live_provider"

            cache_path = tmp_path / "bengaluru.json"
            with open(cache_path, "r") as f:
                cached = json.load(f)
            old_time = datetime.now(tz=timezone.utc) - timedelta(hours=12)
            cached["retrieved_at"] = old_time.isoformat()
            with open(cache_path, "w") as f:
                json.dump(cached, f)

            mock_fetch.side_effect = RuntimeError("provider down")
            result2 = get_no2_column_density(city="bengaluru", refresh=True)
            assert result2["source_status"] == "stale_cache_fallback"
            assert result2["freshness"] == "stale"
            assert result2["cache_used"] is True
            assert len(result2["warnings"]) > 0

    def test_empty_fetch_returns_empty_hexagons(self, tmp_path) -> None:
        with patch("pipeline.sentinel5p_ingestion._get_service_account_path", return_value="/fake/path"), \
             patch("pipeline.sentinel5p_ingestion._cache_dir", return_value=tmp_path), \
             patch("pipeline.sentinel5p_ingestion._fetch_gee_no2", return_value={}):
            result = get_no2_column_density(city="bengaluru", refresh=True)
            assert result["source_status"] == "live_provider"
            assert result["hexagons"] == []

    def test_geospatial_endpoint_returns_no2_data(self) -> None:
        from backend.app.routers.geospatial import hex_no2_column_density
        with patch("pipeline.sentinel5p_ingestion._get_service_account_path", return_value=None):
            result = hex_no2_column_density(city="bengaluru")
            assert result["source_status"] == "unavailable"
