"""Global pytest fixtures for AQI Sentinel tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def geospatial_test_env(tmp_path, monkeypatch):
    """Patch all geospatial directories to temporary paths and reset service caches.

    Yields a dict with keys:
      raw         -- temporary OSM cache root (replaces OSM_CACHE_DIR)
      processed   -- temporary processed/geospatial root
      reports     -- temporary reports/geospatial root
    """
    raw_dir = tmp_path / "raw" / "geospatial" / "osm"
    processed_dir = tmp_path / "processed" / "geospatial"
    reports_dir = tmp_path / "reports" / "geospatial"

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Reset service module globals before test
    _reset_service_caches()

    # Monkeypatch is preferred over unittest.mock.patch here because
    # monkeypatch.apply_tranformed_paths correctly handles Path objects
    # and it automatically cleans up after the test
    monkeypatch.setattr("backend.app.config.OSM_CACHE_DIR", str(raw_dir), raising=False)
    monkeypatch.setattr("backend.app.config.GEOSPATIAL_PROCESSED_DIR", str(processed_dir), raising=False)
    monkeypatch.setattr("backend.app.config.GEOSPATIAL_REPORTS_DIR", str(reports_dir), raising=False)

    yield {
        "raw": raw_dir,
        "osm_cache": raw_dir,
        "processed": processed_dir,
        "reports": reports_dir,
    }

    # Reset service module globals after test
    _reset_service_caches()


def _reset_service_caches() -> None:
    """Reset module-level cached paths/dataframes in geospatial_evidence_service."""
    import backend.app.services.geospatial_evidence_service as svc

    svc._parquet_path = None
    svc._metadata_path = None
    svc._parquet_mtime = 0.0
    svc._metadata_mtime = 0.0
    svc._cached_df = None
    svc._cached_meta = None
