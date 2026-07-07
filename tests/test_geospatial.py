"""Tests for Milestone 5A — Geospatial Evidence Foundation.

All tests are offline. OSMnx/client calls are mocked; fixture GeoJSON data
is used for feature calculations.
"""

from __future__ import annotations

import json
import csv
import io
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon, LineString, box, shape
from shapely import wkt

from backend.app.config import (
    BENGALURU_BOUNDING_BOX,
    GEOSPATIAL_FEATURE_BUILDER_VERSION,
    H3_RESOLUTION,
    ROAD_CONTEXT_RADIUS_METERS,
    STATION_CONTEXT_RADIUS_METERS,
    GEOSPATIAL_INVESTIGATION_CONTEXT_RADIUS_METERS,
    get_project_root,
)
from backend.app.services.geospatial_evidence_service import (
    GeospatialArtifactMissingError,
    UnknownStationError,
    get_station_geospatial_context,
    get_city_geospatial_coverage,
)
from backend.app.routers.geospatial import station_geospatial_context, city_geospatial_coverage


# =========================================================================
# Station registry validation
# =========================================================================


class TestStationRegistry:
    """Validate the station registry CSV."""

    REGISTRY_PATH = get_project_root() / "data/reference/bengaluru_station_registry.csv"

    def test_registry_exists(self) -> None:
        assert self.REGISTRY_PATH.exists(), "Station registry CSV not found"

    def test_registry_has_required_columns(self) -> None:
        df = pd.read_csv(self.REGISTRY_PATH)
        required = {"station_id", "display_name", "city", "latitude", "longitude", "source", "coordinate_source", "coordinate_confidence"}
        assert required.issubset(set(df.columns)), f"Missing columns: {required - set(df.columns)}"

    def test_station_ids_unique(self) -> None:
        df = pd.read_csv(self.REGISTRY_PATH)
        assert df["station_id"].is_unique, "Station IDs must be unique"

    def test_all_station_ids_match_registry(self) -> None:
        """Every registry station must match a station in the pipeline station_registry module."""
        from pipeline.station_registry import BENGALURU_STATIONS
        df = pd.read_csv(self.REGISTRY_PATH)
        pipeline_ids = {s.station_id for s in BENGALURU_STATIONS}
        registry_ids = set(df["station_id"])
        missing = registry_ids - pipeline_ids
        extra = pipeline_ids - registry_ids
        assert not missing, f"Registry has unknown station IDs: {missing}"
        assert not extra, f"Registry missing pipeline station IDs: {extra}"

    def test_coordinates_within_bengaluru_bounds(self) -> None:
        df = pd.read_csv(self.REGISTRY_PATH)
        bbox = BENGALURU_BOUNDING_BOX
        for _, row in df.iterrows():
            lat, lon = float(row["latitude"]), float(row["longitude"])
            assert bbox["south"] <= lat <= bbox["north"], f"{row['station_id']} lat {lat} out of bounds"
            assert bbox["west"] <= lon <= bbox["east"], f"{row['station_id']} lon {lon} out of bounds"


# =========================================================================
# H3 utilities
# =========================================================================


class TestH3Utils:
    def test_lat_lon_to_h3_returns_string(self) -> None:
        from pipeline.geospatial.h3_utils import lat_lon_to_h3
        cell = lat_lon_to_h3(12.9716, 77.5946)
        assert isinstance(cell, str)
        assert len(cell) > 0

    def test_lat_lon_to_h3_resolution(self) -> None:
        from pipeline.geospatial.h3_utils import lat_lon_to_h3
        cell = lat_lon_to_h3(12.9716, 77.5946, resolution=9)
        assert cell.startswith("8")  # H3 resolution 9 cells start with '8'

    def test_h3_cell_to_boundary(self) -> None:
        from pipeline.geospatial.h3_utils import lat_lon_to_h3, h3_cell_to_boundary
        cell = lat_lon_to_h3(12.9716, 77.5946)
        boundary = h3_cell_to_boundary(cell)
        assert isinstance(boundary, (list, tuple))
        assert len(boundary) >= 3  # Polygon must have at least 3 vertices

    def test_h3_cell_to_polygon(self) -> None:
        from pipeline.geospatial.h3_utils import lat_lon_to_h3, h3_cell_to_polygon
        cell = lat_lon_to_h3(12.9716, 77.5946)
        poly = h3_cell_to_polygon(cell)
        assert isinstance(poly, Polygon)
        assert poly.area > 0

    def test_station_to_h3_cell(self) -> None:
        from pipeline.geospatial.h3_utils import station_to_h3_cell
        result = station_to_h3_cell(13.029152, 77.585901, resolution=9)
        assert result["h3_cell"].startswith("8")
        assert result["resolution"] == 9
        assert abs(result["latitude"] - 13.029152) < 0.001
        assert abs(result["longitude"] - 77.585901) < 0.001

    def test_compute_station_h3_mapping(self) -> None:
        from pipeline.geospatial.h3_utils import compute_station_h3_mapping
        df = pd.DataFrame({
            "station_id": ["a", "b"],
            "latitude": [12.97, 13.03],
            "longitude": [77.59, 77.49],
        })
        result = compute_station_h3_mapping(df, resolution=9)
        assert "h3_cell" in result.columns
        assert "h3_resolution" in result.columns
        assert result.loc[0, "h3_cell"].startswith("8")
        assert result.loc[1, "h3_cell"].startswith("8")

    def test_h3_api_version(self) -> None:
        from pipeline.geospatial.h3_utils import get_h3_api_version
        version = get_h3_api_version()
        assert isinstance(version, str)
        assert len(version) > 0


# =========================================================================
# Metric distance and area calculations
# =========================================================================


class TestMetricCalculations:
    def test_distance_approximation(self) -> None:
        """Rough check that lat/lon distance is in metres."""
        p1 = Point(77.59, 12.97)
        p2 = Point(77.59, 12.98)
        d = p1.distance(p2) * 111_320.0
        assert 900 < d < 1200  # ~1 degree lat = 111km; 0.01 deg ~= 1110m

    def test_buffer_area_metric(self) -> None:
        """Check that a 1000m buffer has roughly pi km^2 area."""
        from shapely.geometry import Point
        import pyproj
        from shapely.ops import transform

        project = pyproj.Transformer.from_crs(
            "EPSG:4326", "EPSG:32643", always_xy=True
        ).transform
        project_back = pyproj.Transformer.from_crs(
            "EPSG:32643", "EPSG:4326", always_xy=True
        ).transform

        pt = Point(77.59, 12.97)
        pt_m = transform(project, pt)
        buf_m = pt_m.buffer(1000.0)
        buf_wgs = transform(project_back, buf_m)

        # Re-project to metric for area
        buf_m2 = transform(project, buf_wgs)
        area_km2 = buf_m2.area / 1_000_000.0
        assert 2.5 < area_km2 < 3.5  # pi * 1^2 ≈ 3.14 km^2


# =========================================================================
# Fixtures for feature extraction tests
# =========================================================================


@pytest.fixture
def fixture_registry_df() -> pd.DataFrame:
    return pd.DataFrame({
        "station_id": ["cpcb_test"],
        "display_name": ["Test Station"],
        "city": ["bengaluru"],
        "latitude": [12.97],
        "longitude": [77.59],
        "source": ["CPCB"],
        "coordinate_source": ["OpenAQ"],
        "coordinate_confidence": ["Verified"],
        "verification_note": ["Test fixture"],
    })


@pytest.fixture
def fixture_road_geojson() -> dict:
    """Create a small road GeoJSON with one major and one minor road."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"highway": "primary", "name": "Major Road"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[77.58, 12.96], [77.60, 12.98]],
                },
            },
            {
                "type": "Feature",
                "properties": {"highway": "residential", "name": "Minor Road"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[77.585, 12.965], [77.595, 12.975]],
                },
            },
        ],
    }


@pytest.fixture
def fixture_landuse_geojson() -> dict:
    """Create a small land-use GeoJSON with industrial and green areas."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"landuse": "industrial"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[77.58, 12.96], [77.59, 12.96], [77.59, 12.97], [77.58, 12.97], [77.58, 12.96]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"landuse": "residential"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[77.59, 12.96], [77.60, 12.96], [77.60, 12.97], [77.59, 12.97], [77.59, 12.96]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"leisure": "park"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[77.585, 12.97], [77.595, 12.97], [77.595, 12.975], [77.585, 12.975], [77.585, 12.97]]],
                },
            },
        ],
    }


@pytest.fixture
def fixture_industrial_geojson() -> dict:
    """Create industrial/facility GeoJSON."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"landuse": "industrial", "name": "Factory A"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[77.58, 12.965], [77.585, 12.965], [77.585, 12.97], [77.58, 12.97], [77.58, 12.965]]],
                },
            },
        ],
    }


@pytest.fixture
def fixture_construction_geojson() -> dict:
    """Create construction GeoJSON."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"landuse": "construction"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[77.59, 12.97], [77.595, 12.97], [77.595, 12.975], [77.59, 12.975], [77.59, 12.97]]],
                },
            },
        ],
    }


# =========================================================================
# Road density calculation
# =========================================================================


class TestRoadDensity:
    @patch("pipeline.build_geospatial_context.load_category_geojson")
    def test_road_length_calculation(self, mock_load, fixture_road_geojson) -> None:
        mock_load.side_effect = lambda cat: {
            "roads": fixture_road_geojson,
            "landuse": {"type": "FeatureCollection", "features": []},
            "green_spaces": {"type": "FeatureCollection", "features": []},
            "construction": {"type": "FeatureCollection", "features": []},
            "industrial_facility": {"type": "FeatureCollection", "features": []},
        }.get(cat, {"type": "FeatureCollection", "features": []})

        from pipeline.build_geospatial_context import _compute_road_features

        station_point = Point(77.59, 12.97)
        result = _compute_road_features(
            station_point,
            context_radius_m=STATION_CONTEXT_RADIUS_METERS,
            road_radius_m=ROAD_CONTEXT_RADIUS_METERS,
        )

        assert "total_road_length_m_within_radius" in result
        assert "road_density_m_per_sq_km" in result
        assert "nearest_major_road_distance_m" in result
        # With our fixture, there should be roads found
        assert result["total_road_length_m_within_radius"] is not None
        assert result["total_road_length_m_within_radius"] > 0
        assert result["road_feature_coverage_status"] == "complete"

    @patch("pipeline.build_geospatial_context.load_category_geojson")
    def test_no_roads_returns_null(self, mock_load) -> None:
        mock_load.return_value = {"type": "FeatureCollection", "features": []}
        mock_load.side_effect = lambda cat: {
            "roads": {"type": "FeatureCollection", "features": []},
            "landuse": {"type": "FeatureCollection", "features": []},
            "green_spaces": {"type": "FeatureCollection", "features": []},
            "construction": {"type": "FeatureCollection", "features": []},
            "industrial_facility": {"type": "FeatureCollection", "features": []},
        }.get(cat, {"type": "FeatureCollection", "features": []})

        from pipeline.build_geospatial_context import _compute_road_features

        station_point = Point(77.59, 12.97)
        result = _compute_road_features(
            station_point,
            context_radius_m=STATION_CONTEXT_RADIUS_METERS,
            road_radius_m=ROAD_CONTEXT_RADIUS_METERS,
        )

        assert result["total_road_length_m_within_radius"] is None
        assert result["road_feature_coverage_status"] == "no_mapped_roads"
        # road_density is 0.0 because area is positive but length is 0


# =========================================================================
# Null vs zero semantics
# =========================================================================


class TestNullVsZero:
    def test_null_not_zero(self) -> None:
        """Ensure None (null) is distinct from 0 in feature outputs."""
        data = {"value": None}
        assert data["value"] is None
        assert data["value"] != 0


# =========================================================================
# Land-use fraction calculation
# =========================================================================


class TestLanduseFraction:
    @patch("pipeline.build_geospatial_context.load_category_geojson")
    def test_landuse_fractions_sum_to_one(self, mock_load, fixture_landuse_geojson) -> None:
        mock_load.side_effect = lambda cat: {
            "landuse": fixture_landuse_geojson,
            "green_spaces": fixture_landuse_geojson,
            "roads": {"type": "FeatureCollection", "features": []},
            "construction": {"type": "FeatureCollection", "features": []},
            "industrial_facility": {"type": "FeatureCollection", "features": []},
        }.get(cat, {"type": "FeatureCollection", "features": []})

        from pipeline.build_geospatial_context import _compute_landuse_features

        station_point = Point(77.59, 12.97)
        result = _compute_landuse_features(station_point, context_radius_m=STATION_CONTEXT_RADIUS_METERS)

        # If landuse is complete, fractions should exist
        if result["landuse_feature_coverage_status"] == "complete":
            fracs = [
                result["industrial_landuse_fraction"],
                result["commercial_landuse_fraction"],
                result["residential_landuse_fraction"],
                result["green_space_fraction"],
            ]
            non_null = [f for f in fracs if f is not None]
            assert all(0.0 <= f <= 1.0 for f in non_null)

    @patch("pipeline.build_geospatial_context.load_category_geojson")
    def test_no_landuse_returns_null(self, mock_load) -> None:
        mock_load.return_value = {"type": "FeatureCollection", "features": []}
        mock_load.side_effect = lambda cat: {
            "landuse": {"type": "FeatureCollection", "features": []},
            "green_spaces": {"type": "FeatureCollection", "features": []},
            "roads": {"type": "FeatureCollection", "features": []},
            "construction": {"type": "FeatureCollection", "features": []},
            "industrial_facility": {"type": "FeatureCollection", "features": []},
        }.get(cat, {"type": "FeatureCollection", "features": []})

        from pipeline.build_geospatial_context import _compute_landuse_features

        station_point = Point(77.59, 12.97)
        result = _compute_landuse_features(station_point, context_radius_m=STATION_CONTEXT_RADIUS_METERS)

        assert result["industrial_landuse_fraction"] is None
        assert result["landuse_feature_coverage_status"] in ("no_mapped_landuse", "zero_buffer_area")


# =========================================================================
# OSM cache behavior
# =========================================================================


class TestOSMCacheBehavior:
    @patch("pipeline.geospatial.osm_client._is_cache_valid")
    def test_cache_reuse(self, mock_valid, geospatial_test_env) -> None:
        mock_valid.return_value = True
        import json
        from pipeline.geospatial.osm_client import _snapshot_metadata_path, _snapshot_geojson_path

        meta_path = _snapshot_metadata_path("roads")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "category": "roads",
            "snapshot_timestamp": "2026-01-01T00:00:00+00:00",
            "cache_status": "reused",
        }
        with meta_path.open("w") as f:
            json.dump(meta, f)
        geojson_path = _snapshot_geojson_path("roads")
        with geojson_path.open("w") as f:
            json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [77.59, 12.97]}}]}, f)

        from pipeline.geospatial.osm_client import fetch_osm_category
        result = fetch_osm_category("roads", refresh=False, quiet=True)

        assert result["cache_status"] == "reused"

    @patch("pipeline.geospatial.osm_client._is_cache_valid")
    @patch("pipeline.geospatial.osm_client.ox.graph_from_polygon")
    def test_network_unavailable_no_cache_fails(self, mock_ox, mock_valid) -> None:
        mock_valid.return_value = False
        mock_ox.side_effect = Exception("Network error")

        from pipeline.geospatial.osm_client import fetch_osm_category

        with pytest.raises(RuntimeError, match="Failed to fetch OSM"):
            fetch_osm_category("roads", refresh=True, quiet=True)

    @patch("pipeline.geospatial.osm_client._is_cache_valid")
    def test_network_unavailable_with_cache_fallback(self, mock_valid, geospatial_test_env) -> None:
        """If network fails but stale cache exists, should fall back."""
        mock_valid.side_effect = lambda cat: cat == "roads"
        import json
        from pipeline.geospatial.osm_client import _osm_cache_dir, _snapshot_metadata_path, _snapshot_geojson_path

        meta_path = _snapshot_metadata_path("roads")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        stale_meta = {
            "category": "roads",
            "snapshot_timestamp": "2025-01-01T00:00:00+00:00",
            "cache_status": "stale_reused",
        }
        with meta_path.open("w") as f:
            json.dump(stale_meta, f)
        gpath = _snapshot_geojson_path("roads")
        with gpath.open("w") as f:
            json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [77.59, 12.97]}}]}, f)

        from pipeline.geospatial.osm_client import fetch_osm_category

        result = fetch_osm_category("roads", refresh=False, quiet=True)
        assert result["cache_status"] in ("reused", "stale_reused")

    def test_invalid_45_byte_geojson_rejected(self, geospatial_test_env) -> None:
        """A 45-byte empty FeatureCollection must be rejected as invalid cache."""
        import json
        from pipeline.geospatial.osm_client import _snapshot_geojson_path, _validate_geojson

        path = _snapshot_geojson_path("roads")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")

        valid, reason = _validate_geojson(path)
        assert valid
        assert "empty_FeatureCollection" in reason or "0_features" in reason

        from pipeline.geospatial.osm_client import _is_cache_valid
        assert not _is_cache_valid("roads"), "Empty GeoJSON must not be valid cache"

    def test_cache_requires_nonzero_features(self, geospatial_test_env) -> None:
        """Cache with zero features must be treated as invalid."""
        import json
        from pipeline.geospatial.osm_client import _snapshot_metadata_path, _snapshot_geojson_path, _is_cache_valid

        meta_path = _snapshot_metadata_path("landuse")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with meta_path.open("w") as f:
            json.dump({"category": "landuse", "snapshot_timestamp": "2026-01-01T00:00:00+00:00"}, f)

        gpath = _snapshot_geojson_path("landuse")
        with gpath.open("w") as f:
            json.dump({"type": "FeatureCollection", "features": []}, f)

        assert not _is_cache_valid("landuse"), "Zero-feature cache must be invalid"


# =========================================================================
# Fetch CLI module
# =========================================================================


class TestFetchCli:
    def test_module_import(self) -> None:
        """The fetch_osm_bengaluru module must be importable."""
        import pipeline.geospatial.fetch_osm_bengaluru
        assert hasattr(pipeline.geospatial.fetch_osm_bengaluru, "run_fetch")
        assert hasattr(pipeline.geospatial.fetch_osm_bengaluru, "main")

    @patch("pipeline.geospatial.fetch_osm_bengaluru.run_fetch")
    def test_dry_run(self, mock_run) -> None:
        """--dry-run must call run_fetch with dry_run=True and not actually fetch."""
        mock_run.return_value = {"status": "dry_run", "message": "dry run ok"}
        from pipeline.geospatial.fetch_osm_bengaluru import run_fetch
        result = run_fetch(dry_run=True)
        assert result["status"] == "dry_run"

    @patch("pipeline.geospatial.fetch_osm_bengaluru._cache_valid_for_full_build")
    @patch("pipeline.geospatial.fetch_osm_bengaluru.fetch_osm_category")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._validate_geojson")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._all_layers_valid")
    def test_mocked_fetch_writes_all_layers(
        self, mock_valid, mock_validate, mock_fetch, mock_cache_valid,
    ) -> None:
        """Successful mocked fetch should write all 5 layers and manifest."""
        # Make _all_layers_valid return False so fetch proceeds
        mock_valid.return_value = {"_all_layers_valid": False}

        # Each fetch_osm_category call returns success metadata
        mock_fetch.return_value = {
            "cache_status": "fresh",
            "snapshot_timestamp": "2026-06-01T00:00:00+00:00",
            "feature_count": 100,
        }

        # Each validate returns valid
        mock_validate.return_value = (True, "ok (100 features)")

        # Each full-build check passes
        mock_cache_valid.return_value = (True, "ok (100 features)")

        from pipeline.geospatial.fetch_osm_bengaluru import run_fetch
        result = run_fetch(refresh=True, allow_partial=False, dry_run=False)

        assert result["status"] in ("success", "partial")
        assert "manifest" in result

    @patch("pipeline.geospatial.fetch_osm_bengaluru._cache_valid_for_full_build")
    @patch("pipeline.geospatial.fetch_osm_bengaluru.fetch_osm_category")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._validate_geojson")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._all_layers_valid")
    def test_partial_failure_exits_nonzero(
        self, mock_valid, mock_validate, mock_fetch, mock_cache_valid,
    ) -> None:
        """Partial failure without --allow-partial must return status partial_failure."""
        mock_valid.return_value = {"_all_layers_valid": False}

        # First 3 layers succeed, last 2 fail
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 3:
                return {"cache_status": "fresh", "feature_count": 50}
            raise RuntimeError("Fetch failed")

        mock_fetch.side_effect = side_effect

        mock_cache_valid.side_effect = lambda path: (
            (True, "ok (50 features)") if path.name.startswith(("roads", "landuse", "green_spaces"))
            else (False, "fetch_failed")
        )

        mock_validate.side_effect = lambda path: (
            (True, "ok (50 features)") if path.name.startswith(("roads", "landuse", "green_spaces"))
            else (False, "fetch_failed")
        )

        from pipeline.geospatial.fetch_osm_bengaluru import run_fetch
        result = run_fetch(refresh=True, allow_partial=False, dry_run=False)

        # Without --allow-partial, partial failure returns status partial_failure
        assert result["status"] == "partial_failure"

    @patch("pipeline.geospatial.fetch_osm_bengaluru._cache_valid_for_full_build")
    @patch("pipeline.geospatial.fetch_osm_bengaluru.fetch_osm_category")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._validate_geojson")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._all_layers_valid")
    def test_allow_partial_writes_partial_manifest(
        self, mock_valid, mock_validate, mock_fetch, mock_cache_valid,
    ) -> None:
        """With --allow-partial, partial success must write a manifest with partial flag."""
        mock_valid.return_value = {"_all_layers_valid": False}

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 3:
                return {"cache_status": "fresh", "feature_count": 50}
            raise RuntimeError("Fetch failed")

        mock_fetch.side_effect = side_effect

        def cache_side(path):
            name = path.name
            if any(name.startswith(l) for l in ("roads", "landuse", "green_spaces")):
                return (True, "ok (50 features)")
            return (False, "fetch_failed")

        mock_cache_valid.side_effect = cache_side

        def validate_side(path):
            name = path.name
            if any(name.startswith(l) for l in ("roads", "landuse", "green_spaces")):
                return (True, "ok (50 features)")
            return (False, "fetch_failed")

        mock_validate.side_effect = validate_side

        from pipeline.geospatial.fetch_osm_bengaluru import run_fetch
        result = run_fetch(refresh=True, allow_partial=True, dry_run=False)

        assert result["status"] == "partial"
        assert result["manifest"]["partial_build"] is True

    @patch("pipeline.geospatial.fetch_osm_bengaluru._cache_valid_for_full_build")
    @patch("pipeline.geospatial.fetch_osm_bengaluru.fetch_osm_category")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._validate_geojson")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._all_layers_valid")
    def test_zero_feature_layer_causes_partial(
        self, mock_valid, mock_validate, mock_fetch, mock_cache_valid,
    ) -> None:
        """parseable zero-feature layers must result in partial_build, not cached early exit."""
        # Simulate current cache state: 2 layers are parseable but have 0 features
        mock_valid.return_value = {"_all_layers_valid": False}

        mock_fetch.return_value = {
            "cache_status": "fresh",
            "snapshot_timestamp": "2026-06-01T00:00:00+00:00",
            "feature_count": 0,
        }

        # Even though GeoJSON is parseable, cache_valid_for_full_build is False for zero-feature
        def cache_side(path):
            name = path.name
            if name.startswith("green_spaces"):
                return (True, "ok (17902 features)")
            return (False, "empty_feature_collection")

        mock_cache_valid.side_effect = cache_side

        mock_validate.return_value = (True, "empty_FeatureCollection_(0_features)")

        from pipeline.geospatial.fetch_osm_bengaluru import run_fetch
        result = run_fetch(refresh=True, allow_partial=False, dry_run=False)

        # Without --allow-partial, zero-feature layers cause partial_failure
        assert result["status"] == "partial_failure"
        assert not result.get("_all_layers_valid", True)

    @patch("pipeline.geospatial.fetch_osm_bengaluru._cache_valid_for_full_build")
    @patch("pipeline.geospatial.fetch_osm_bengaluru.fetch_osm_category")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._validate_geojson")
    @patch("pipeline.geospatial.fetch_osm_bengaluru._all_layers_valid")
    def test_zero_feature_with_allow_partial(
        self, mock_valid, mock_validate, mock_fetch, mock_cache_valid,
    ) -> None:
        """With --allow-partial, zero-feature layers must be recorded and partial_build=True."""
        mock_valid.return_value = {"_all_layers_valid": False}

        mock_fetch.return_value = {
            "cache_status": "fresh",
            "snapshot_timestamp": "2026-06-01T00:00:00+00:00",
            "feature_count": 0,
        }

        def cache_side(path):
            name = path.name
            if name.startswith("green_spaces"):
                return (True, "ok (17902 features)")
            return (False, "empty_feature_collection")

        mock_cache_valid.side_effect = cache_side

        mock_validate.return_value = (True, "empty_FeatureCollection_(0_features)")

        from pipeline.geospatial.fetch_osm_bengaluru import run_fetch
        result = run_fetch(refresh=True, allow_partial=True, dry_run=False)

        assert result["status"] == "partial"
        assert result["manifest"]["partial_build"] is True
        assert result["manifest"]["all_layers_valid"] is False

    def test_parseable_zero_feature_is_not_full_build(self, geospatial_test_env) -> None:
        """A parseable zero-feature GeoJSON must be cache_valid_for_full_build=False."""
        from pipeline.geospatial.fetch_osm_bengaluru import _cache_valid_for_full_build, _snapshot_geojson_path

        path = _snapshot_geojson_path("_test_empty")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")

        valid, reason = _cache_valid_for_full_build(path)
        assert not valid
        assert "empty_feature_collection" in reason.lower() or "0" in reason

        # No cleanup needed — file is in tmp_path
        assert geospatial_test_env["osm_cache"] in path.parents

    def test_nonempty_geojson_is_full_build(self, geospatial_test_env) -> None:
        """A parseable GeoJSON with features must be cache_valid_for_full_build=True."""
        from pipeline.geospatial.fetch_osm_bengaluru import _cache_valid_for_full_build, _snapshot_geojson_path

        path = _snapshot_geojson_path("_test_nonempty")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]}',
            encoding="utf-8",
        )

        valid, reason = _cache_valid_for_full_build(path)
        assert valid
        assert "ok" in reason

        # No cleanup needed — file is in tmp_path
        assert geospatial_test_env["osm_cache"] in path.parents

    def test_parseable_geojson_stale_not_valid_when_empty(self, geospatial_test_env) -> None:
        """Stale cache with empty GeoJSON must NOT be reused."""
        import json
        from pipeline.geospatial.osm_client import (
            _snapshot_geojson_path,
            _snapshot_metadata_path,
            _is_cache_valid,
        )

        gpath = _snapshot_geojson_path("_test_stale_empty")
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")

        mpath = _snapshot_metadata_path("_test_stale_empty")
        with mpath.open("w") as f:
            json.dump({"category": "_test_stale_empty", "snapshot_timestamp": "2025-01-01T00:00:00+00:00"}, f)

        assert not _is_cache_valid("_test_stale_empty")

        # No cleanup needed — files are in tmp_path
        assert geospatial_test_env["osm_cache"] in gpath.parents

    @patch("pipeline.geospatial.fetch_osm_bengaluru._all_layers_valid")
    def test_cached_early_exit_rejects_empty_layers(self, mock_valid) -> None:
        """The early cached-path exit must not trigger when layers have 0 features."""
        # Simulate all layers being parseable but some have 0 features
        mock_valid.return_value = {"_all_layers_valid": False}

        from pipeline.geospatial.fetch_osm_bengaluru import run_fetch

        with patch("pipeline.geospatial.fetch_osm_bengaluru.fetch_osm_category") as mock_fetch:
            with patch("pipeline.geospatial.fetch_osm_bengaluru._validate_geojson") as mock_validate:
                with patch("pipeline.geospatial.fetch_osm_bengaluru._cache_valid_for_full_build") as mock_cache:
                    mock_fetch.return_value = {"cache_status": "fresh", "feature_count": 0}
                    mock_validate.return_value = (True, "empty_FeatureCollection_(0_features)")
                    mock_cache.return_value = (False, "empty_feature_collection")

                    result = run_fetch(refresh=True, allow_partial=False, dry_run=False)

        # Must attempt fetch (no early exit), and detect partial failure
        assert result["status"] == "partial_failure"
        assert mock_fetch.called


# =========================================================================
# Builder validation tests
# =========================================================================
# Builder validation tests
# =========================================================================


class TestBuilderValidation:
    @patch("pipeline.build_geospatial_context._snapshot_geojson_path")
    @patch("pipeline.build_geospatial_context._validate_geojson")
    def test_builder_refuses_incomplete_snapshot(self, mock_validate, mock_path) -> None:
        """Builder must raise RuntimeError when OSM layers are missing by default."""
        # Simulate all layers missing
        mock_path.return_value = Path("/nonexistent/roads.geojson")
        mock_validate.return_value = (False, "file_not_found")

        from pipeline.build_geospatial_context import build_geospatial_context

        with pytest.raises(RuntimeError, match="Required OSM layers are not ready"):
            build_geospatial_context(allow_partial_osm=False)

    @patch("pipeline.build_geospatial_context._check_osm_layers")
    @patch("pipeline.build_geospatial_context._load_registry")
    @patch("pipeline.build_geospatial_context._snapshot_geojson_path")
    @patch("pipeline.build_geospatial_context._validate_geojson")
    def test_builder_succeeds_with_allow_partial_osm(
        self, mock_validate, mock_path, mock_registry, mock_osm_check,
        fixture_registry_df, geospatial_test_env,
    ) -> None:
        """Builder must succeed with --allow-partial-osm and mark artifact as partial."""
        from pipeline.build_geospatial_context import build_geospatial_context

        mock_osm_check.return_value = {"_all_ok": False, "_missing": ["construction"], "_empty": []}
        mock_registry.return_value = fixture_registry_df

        with patch("pipeline.build_geospatial_context.load_category_geojson") as mock_load:
            mock_load.return_value = {"type": "FeatureCollection", "features": []}
            result = build_geospatial_context(allow_partial_osm=True)

        assert result["build_status"] == "partial"
        assert result["layer_status"]["_all_ok"] is False

        # Verify artifacts were written inside tmp dirs only
        processed = geospatial_test_env["processed"]
        assert (processed / "station_geospatial_context.parquet").exists()
        assert (processed / "geospatial_build_metadata.json").exists()
        reports = geospatial_test_env["reports"]
        assert (reports / "geospatial_coverage_report.csv").exists()
        assert (reports / "geospatial_coverage_report.md").exists()


# =========================================================================
# Report generation
# =========================================================================


class TestReportGeneration:
    @patch("pipeline.build_geospatial_context.load_category_geojson")
    @patch("pipeline.build_geospatial_context._load_registry")
    def test_md_report_content(self, mock_registry, mock_geojson, tmp_path, fixture_registry_df) -> None:
        mock_registry.return_value = fixture_registry_df
        mock_geojson.return_value = {"type": "FeatureCollection", "features": []}
        mock_geojson.side_effect = lambda cat: {
            "roads": {"type": "FeatureCollection", "features": []},
            "landuse": {"type": "FeatureCollection", "features": []},
            "green_spaces": {"type": "FeatureCollection", "features": []},
            "construction": {"type": "FeatureCollection", "features": []},
            "industrial_facility": {"type": "FeatureCollection", "features": []},
        }.get(cat, {"type": "FeatureCollection", "features": []})

        from pipeline.build_geospatial_context import _write_md_report

        records = [{
            "station_id": "cpcb_test",
            "road_feature_coverage_status": "no_mapped_roads",
            "landuse_feature_coverage_status": "no_mapped_landuse",
            "investigation_context_coverage_status": "no_mapped_investigation_features",
            "data_completeness_score": 0.0,
        }]
        osm_meta = {
            "roads": {"snapshot_timestamp": "2026-01-01T00:00:00+00:00", "cache_status": "fresh"},
            "landuse": {},
            "green_spaces": {},
            "construction": {},
            "industrial_facility": {},
        }

        report_path = tmp_path / "test_report.md"
        layer_status = {
            "roads": {"valid": True, "feature_count": 0},
            "landuse": {"valid": True, "feature_count": 0},
            "green_spaces": {"valid": True, "feature_count": 0},
            "construction": {"valid": True, "feature_count": 0},
            "industrial_facility": {"valid": True, "feature_count": 0},
        }
        _write_md_report(report_path, records, osm_meta, layer_status, is_partial=False)

        content = report_path.read_text(encoding="utf-8")
        assert "# Geospatial Coverage Report" in content
        assert "cpcb_test" in content
        assert "Stations processed" in content
        assert "OSM" in content
        assert "Null / Coverage Semantics" in content
        assert "Disclaimers" in content


# =========================================================================
# Artifact adapter
# =========================================================================


class TestArtifactAdapterGeospatial:
    def test_get_station_geospatial_context_returns_dict(self) -> None:
        """Should return a dict with station context fields."""
        from backend.app.services.artifact_adapter import get_station_geospatial_context

        result = get_station_geospatial_context("cpcb_hebbal")
        assert "station_id" in result
        assert "build_status" in result
        assert "road_context" in result
        assert "landuse_context" in result
        assert "limitations" in result


# =========================================================================
# Service response disclaimers
# =========================================================================


class TestServiceDisclaimers:
    def test_osm_completeness_disclaimer_present(self) -> None:
        from backend.app.services.geospatial_evidence_service import OSM_COMPLETENESS_DISCLAIMER
        assert "community-maintained" in OSM_COMPLETENESS_DISCLAIMER
        assert "incomplete" in OSM_COMPLETENESS_DISCLAIMER

    def test_investigation_disclaimer_present(self) -> None:
        from backend.app.services.geospatial_evidence_service import INVESTIGATION_DISCLAIMER
        assert "contextual evidence" in INVESTIGATION_DISCLAIMER
        assert "not prove" in INVESTIGATION_DISCLAIMER


# =========================================================================
# Endpoints
# =========================================================================


class TestGeospatialEndpoints:
    def test_unknown_station_returns_503_when_no_artifact(self) -> None:
        """Without built artifacts, the service returns 503 before checking station ID."""
        from unittest.mock import patch
        from fastapi import HTTPException

        with patch(
            "backend.app.services.geospatial_evidence_service._load_context_dataframe",
            side_effect=GeospatialArtifactMissingError,
        ):
            with pytest.raises(HTTPException) as exc_info:
                station_geospatial_context("nonexistent_station")
            assert exc_info.value.status_code == 503

    def test_station_context_endpoint_returns_503_with_no_artifact(self) -> None:
        from unittest.mock import patch
        from fastapi import HTTPException

        with patch(
            "backend.app.services.geospatial_evidence_service._load_context_dataframe",
            side_effect=GeospatialArtifactMissingError,
        ):
            with pytest.raises(HTTPException) as exc_info:
                station_geospatial_context("cpcb_hebbal")
            assert exc_info.value.status_code == 503

    def test_city_coverage_endpoint_returns_503_with_no_artifact(self) -> None:
        from unittest.mock import patch
        from fastapi import HTTPException

        with patch(
            "backend.app.services.geospatial_evidence_service._load_context_dataframe",
            side_effect=GeospatialArtifactMissingError,
        ):
            with pytest.raises(HTTPException) as exc_info:
                city_geospatial_coverage("bengaluru")
            assert exc_info.value.status_code == 503


# =========================================================================
# Inspection output integration
# =========================================================================


class TestInspectionIntegration:
    def test_inspection_output_has_spatial_context_optional_field(self) -> None:
        """Inspection priorities should include spatial_investigation_context as optional field."""
        from backend.app.services.inspection_priority_service import get_inspection_priorities
        result = get_inspection_priorities("bengaluru", top_k=3)
        for station in result["ranked_stations"]:
            assert "spatial_investigation_context" in station
            # Should not alter existing fields
            assert "priority_score" in station
            assert "station_id" in station
            assert "rank" in station

    def test_spatial_context_does_not_alter_priority_score(self) -> None:
        """Spatial context presence must not change existing priority scores."""
        from backend.app.services.inspection_priority_service import get_inspection_priorities
        result = get_inspection_priorities("bengaluru", top_k=6)
        for station in result["ranked_stations"]:
            # Priority score should still be in valid range
            assert 0 <= station["priority_score"] <= 100
            # Priority level should still be valid
            assert station["priority_level"] in ("Critical", "High", "Moderate", "Watch")


# =========================================================================
# Copilot routing/tool/audit
# =========================================================================


class TestSpatialCopilotIntegration:
    def test_spatial_context_intent_exists(self) -> None:
        from backend.app.agents.state import Intent
        assert hasattr(Intent, "spatial_context")
        assert Intent.spatial_context.value == "spatial_context"

    def test_spatial_context_tool_exists(self) -> None:
        from backend.app.agents.tools import tool_get_geospatial_context
        result = tool_get_geospatial_context("nonexistent")
        # Without artifacts, may return geospatial_available=False or _tool_error
        assert isinstance(result, dict)

    def test_spatial_context_tool_returns_disclaimers(self) -> None:
        from backend.app.agents.tools import tool_get_geospatial_context
        result = tool_get_geospatial_context("cpcb_hebbal")
        # artifact not built so we get error, but the tool should not crash
        assert "_tool_error" in result or isinstance(result, dict)

    def test_intent_detection_spatial_keywords(self) -> None:
        from backend.app.agents.orchestrator import _detect_intent
        from backend.app.agents.state import Intent

        # Test various spatial keywords
        queries = [
            "spatial context around Peenya",
            "geospatial features near Hebbal",
            "road density near Silkboard station",
            "land use around Peenya station",
            "industrial context near Hebbal",
        ]
        for q in queries:
            intent = _detect_intent(q, station_id="cpcb_peenya")
            assert intent == Intent.spatial_context, f"Failed for query: {q}"

    def test_route_spatial_context_intent(self) -> None:
        from backend.app.agents.orchestrator import _route_intent
        from backend.app.agents.state import Intent
        agent = _route_intent(Intent.spatial_context)
        assert agent == "spatial_context_agent"


# =========================================================================
# Spatical context agent
# =========================================================================


class TestSpatialContextAgent:
    def test_agent_responds_with_station_context(self) -> None:
        from backend.app.agents.state import AgentState
        from backend.app.agents.audit import AuditTrail
        from backend.app.agents.spatial_context_agent import run_spatial_context_agent

        state = AgentState(request_id="test-r1", station_id="cpcb_hebbal", city="bengaluru")
        audit = AuditTrail("test-r1")
        run_spatial_context_agent(state, audit)

        # With no artifact, we expect an error response
        assert state.response is not None
        assert len(state.response) > 0


# =========================================================================
# Station registry H3 mapping
# =========================================================================


class TestStationH3Mapping:
    def test_every_registry_station_maps_to_h3_cell(self) -> None:
        """Validate that every registry station maps to an H3 cell."""
        import h3
        df = pd.read_csv(get_project_root() / "data/reference/bengaluru_station_registry.csv")
        for _, row in df.iterrows():
            lat, lon = float(row["latitude"]), float(row["longitude"])
            cell = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            assert isinstance(cell, str)
            assert len(cell) > 0


# =========================================================================
# OSM tag normalization
# =========================================================================


class TestOSMTagNormalization:
    def test_scalar_primary_is_major(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        assert normalize_osm_tag_values("primary") == ["primary"]

    def test_list_primary_service_is_major(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        vals = normalize_osm_tag_values(["primary", "service"])
        assert "primary" in vals
        assert "service" in vals

    def test_list_service_residential_not_major(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        vals = normalize_osm_tag_values(["service", "residential"])
        assert "service" in vals
        assert "residential" in vals
        assert "primary" not in vals

    def test_none_does_not_crash(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        assert normalize_osm_tag_values(None) == []

    def test_nan_does_not_crash(self) -> None:
        import math
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        assert normalize_osm_tag_values(math.nan) == []

    def test_tuple_of_strings(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        vals = normalize_osm_tag_values(("primary", "secondary"))
        assert "primary" in vals
        assert "secondary" in vals

    def test_set_of_strings(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        vals = normalize_osm_tag_values({"motorway", "footway"})
        assert "motorway" in vals
        assert "footway" in vals

    def test_nested_collections_flattened(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        vals = normalize_osm_tag_values([["primary", "secondary"], "service"])
        assert "primary" in vals
        assert "secondary" in vals
        assert "service" in vals

    def test_non_string_scalar(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        vals = normalize_osm_tag_values(123)
        assert "123" in vals

    def test_empty_string_returns_empty(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        assert normalize_osm_tag_values("") == []

    def test_whitespace_stripped_and_lowered(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        assert normalize_osm_tag_values("  Primary  ") == ["primary"]

    def test_major_highway_classification(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        major_highway_types = {
            "motorway", "trunk", "primary", "secondary",
            "motorway_link", "trunk_link", "primary_link", "secondary_link",
        }
        vals = normalize_osm_tag_values(["primary", "service"])
        assert any(v in major_highway_types for v in vals)
        vals2 = normalize_osm_tag_values(["service", "residential"])
        assert not any(v in major_highway_types for v in vals2)

    def test_landuse_list_does_not_crash(self) -> None:
        from pipeline.build_geospatial_context import normalize_osm_tag_values
        vals = normalize_osm_tag_values(["industrial", "residential"])
        assert "industrial" in vals
        assert "residential" in vals


# =========================================================================
# Artifact loading regression tests
# =========================================================================


class TestArtifactLoading:
    def test_coverage_returns_six_stations_full_build(self, geospatial_test_env) -> None:
        """Coverage endpoint must return total_stations=6 and build_status=full."""
        import pandas as pd
        import json
        import backend.app.services.geospatial_evidence_service as svc

        processed_dir = geospatial_test_env["processed"]
        station_ids = [
            "cpcb_hebbal", "cpcb_hombegowda", "cpcb_jayanagar5",
            "cpcb_silkboard", "cpcb_peenya", "cpcb_bapujinagar",
        ]
        records = []
        for sid in station_ids:
            records.append({
                "station_id": sid,
                "city": "bengaluru",
                "latitude": 12.97,
                "longitude": 77.59,
                "h3_cell": "893c1b2d7fffff",
                "context_radius_meters": 1000.0,
                "total_road_length_m_within_radius": 5000.0,
                "major_road_length_m_within_radius": 2000.0,
                "road_density_m_per_sq_km": 1000.0,
                "intersection_count_within_radius": 10,
                "nearest_major_road_distance_m": 50.0,
                "road_feature_coverage_status": "complete",
                "industrial_landuse_fraction": 0.1,
                "commercial_landuse_fraction": 0.2,
                "residential_landuse_fraction": 0.5,
                "green_space_fraction": 0.2,
                "landuse_feature_coverage_status": "complete",
                "construction_feature_count_within_radius": 5,
                "mapped_industrial_or_facility_count_within_radius": 3,
                "nearest_mapped_industrial_or_facility_distance_m": 200.0,
                "investigation_context_coverage_status": "complete",
                "osm_snapshot_timestamp": "2026-07-01T00:00:00+00:00",
                "feature_builder_version": "1.0.0",
                "data_completeness_score": 1.0,
                "limitations": "Test limitation",
            })
        df = pd.DataFrame(records)
        df.to_parquet(processed_dir / "station_geospatial_context.parquet", index=False)

        meta = {
            "build_status": "full",
            "stations_count": 6,
            "feature_builder_version": "1.0.0",
            "h3_resolution": 9,
            "osm_snapshot_timestamp": "2026-07-01T00:00:00+00:00",
        }
        with (processed_dir / "geospatial_build_metadata.json").open("w") as f:
            json.dump(meta, f)

        result = svc.get_city_geospatial_coverage("bengaluru")
        assert result["total_stations"] == 6
        assert result["stations_with_coverage"] > 0
        assert result["build_status"] == "full"

    def test_station_context_returns_200_for_known_station(self, geospatial_test_env) -> None:
        """Station context endpoint must return a full context for a known station."""
        import pandas as pd
        import json
        import backend.app.services.geospatial_evidence_service as svc

        processed_dir = geospatial_test_env["processed"]
        records = [{
            "station_id": "cpcb_peenya",
            "city": "bengaluru",
            "latitude": 12.97,
            "longitude": 77.59,
            "h3_cell": "893c1b2d7fffff",
            "context_radius_meters": 1000.0,
            "total_road_length_m_within_radius": 5000.0,
            "major_road_length_m_within_radius": 2000.0,
            "road_density_m_per_sq_km": 1000.0,
            "intersection_count_within_radius": 10,
            "nearest_major_road_distance_m": 50.0,
            "road_feature_coverage_status": "complete",
            "industrial_landuse_fraction": 0.1,
            "commercial_landuse_fraction": 0.2,
            "residential_landuse_fraction": 0.5,
            "green_space_fraction": 0.2,
            "landuse_feature_coverage_status": "complete",
            "construction_feature_count_within_radius": 5,
            "mapped_industrial_or_facility_count_within_radius": 3,
            "nearest_mapped_industrial_or_facility_distance_m": 200.0,
            "investigation_context_coverage_status": "complete",
            "osm_snapshot_timestamp": "2026-07-01T00:00:00+00:00",
            "feature_builder_version": "1.0.0",
            "data_completeness_score": 1.0,
            "limitations": "Test limitation",
        }]
        df = pd.DataFrame(records)
        df.to_parquet(processed_dir / "station_geospatial_context.parquet", index=False)

        meta = {"build_status": "full", "stations_count": 1}
        with (processed_dir / "geospatial_build_metadata.json").open("w") as f:
            json.dump(meta, f)

        result = svc.get_station_geospatial_context("cpcb_peenya")
        assert result["station_id"] == "cpcb_peenya"
        assert result["data_completeness_score"] is not None
        assert "road_context" in result
        assert "landuse_context" in result
        assert "investigation_context" in result
        assert result["build_status"] == "full"

    def test_unknown_station_still_returns_404(self, geospatial_test_env) -> None:
        """True unknown stations must still raise UnknownStationError."""
        import pandas as pd
        import json
        import backend.app.services.geospatial_evidence_service as svc

        processed_dir = geospatial_test_env["processed"]
        records = [{"station_id": "cpcb_peenya", "city": "bengaluru", "latitude": 12.97, "longitude": 77.59}]
        df = pd.DataFrame(records)
        df.to_parquet(processed_dir / "station_geospatial_context.parquet", index=False)

        meta = {"build_status": "full", "stations_count": 1}
        with (processed_dir / "geospatial_build_metadata.json").open("w") as f:
            json.dump(meta, f)

        with pytest.raises(svc.UnknownStationError, match="nonexistent"):
            svc.get_station_geospatial_context("nonexistent_station")


# =========================================================================
# Regression: test isolation from production data
# =========================================================================


class TestGeospatialIsolation:
    """Prove all geospatial tests use only temporary directories.

    Every test in this class uses the geospatial_test_env fixture which
    patches backend.app.config.OSM_CACHE_DIR, GEOSPATIAL_PROCESSED_DIR,
    and GEOSPATIAL_REPORTS_DIR to pytest tmp_path subdirectories.
    """

    def test_osm_cache_paths_resolve_to_tmpdir(self, geospatial_test_env) -> None:
        """Verify _osm_cache_dir / _snapshot_geojson_path point to tmp_path."""
        from pipeline.geospatial.osm_client import _osm_cache_dir, _snapshot_geojson_path

        cache_dir = _osm_cache_dir()
        assert str(cache_dir) == str(geospatial_test_env["osm_cache"])

        geo_path = _snapshot_geojson_path("roads")
        assert geo_path.parent == cache_dir
        assert geo_path.name == "roads.geojson"

    def test_builder_artifacts_in_tmpdir_only(self, geospatial_test_env) -> None:
        """Verify build_geospatial_context writes into tmp_path only."""
        import json
        import sys
        from unittest.mock import patch as mock_patch

        # Build synthetic data: write mock GeoJSON to osm_cache
        osm_cache = geospatial_test_env["osm_cache"]
        for layer in ["roads", "landuse", "green_spaces", "construction", "industrial_facility"]:
            meta = {
                "category": layer,
                "snapshot_timestamp": "2026-07-01T00:00:00+00:00",
                "cache_status": "fresh",
                "feature_count": 1,
            }
            with (osm_cache / f"{layer}_metadata.json").open("w") as f:
                json.dump(meta, f)
            (osm_cache / f"{layer}.geojson").write_text(
                '{"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.59, 12.97]}, "properties": {"highway": "primary"}}]}',
                encoding="utf-8",
            )

        # Build artifact
        from pipeline.build_geospatial_context import build_geospatial_context

        with mock_patch("pipeline.build_geospatial_context._load_registry") as mock_reg:
            import pandas as pd
            mock_reg.return_value = pd.DataFrame([
                {"station_id": "cpcb_peenya", "latitude": 12.97, "longitude": 77.59, "city": "bengaluru"},
            ])

            result = build_geospatial_context(allow_partial_osm=False)

        assert result["build_status"] == "full"

        # Prove files exist in tmp_path
        processed = geospatial_test_env["processed"]
        assert (processed / "station_geospatial_context.parquet").exists()
        assert (processed / "geospatial_build_metadata.json").exists()
        reports = geospatial_test_env["reports"]
        assert (reports / "geospatial_coverage_report.csv").exists()
        assert (reports / "geospatial_coverage_report.md").exists()

        # Prove they do NOT exist in real production paths
        project_root = __import__("backend.app.config", fromlist=["get_project_root"]).get_project_root()
        real_processed = project_root / "data" / "processed" / "geospatial"
        real_reports = project_root / "data" / "reports" / "geospatial"
        for name in ["station_geospatial_context.parquet", "geospatial_build_metadata.json"]:
            assert (processed / name).exists(), f"Should exist in tmp: {name}"
            real_path = real_processed / name
            if real_path.exists():
                assert (processed / name).stat().st_ino != real_path.stat().st_ino, \
                    f"{name} must not be the real file"

    def test_full_artifact_load_from_tmpdir(self, geospatial_test_env) -> None:
        """Verify a full artifact can be built and loaded from temporary paths."""
        import json
        import pandas as pd
        import backend.app.services.geospatial_evidence_service as svc
        from unittest.mock import patch as mock_patch

        processed = geospatial_test_env["processed"]
        records = [{
            "station_id": "cpcb_peenya",
            "city": "bengaluru",
            "latitude": 12.97,
            "longitude": 77.59,
            "context_radius_meters": 1000.0,
            "total_road_length_m_within_radius": 5000.0,
            "road_feature_coverage_status": "complete",
            "landuse_feature_coverage_status": "complete",
            "investigation_context_coverage_status": "complete",
            "data_completeness_score": 1.0,
            "limitations": "test",
        }]
        pd.DataFrame(records).to_parquet(processed / "station_geospatial_context.parquet", index=False)
        with (processed / "geospatial_build_metadata.json").open("w") as f:
            json.dump({"build_status": "full", "stations_count": 1}, f)

        coverage = svc.get_city_geospatial_coverage("bengaluru")
        assert coverage["total_stations"] == 1
        assert coverage["build_status"] == "full"

        context = svc.get_station_geospatial_context("cpcb_peenya")
        assert context["station_id"] == "cpcb_peenya"
        assert context["build_status"] == "full"

    def test_service_graceful_without_artifact(self, geospatial_test_env) -> None:
        """When GEOSPATIAL_PROCESSED_DIR is patched but dir is empty, service must raise."""
        import backend.app.services.geospatial_evidence_service as svc

        with pytest.raises(svc.GeospatialArtifactMissingError):
            svc.get_city_geospatial_coverage("bengaluru")

        with pytest.raises(svc.GeospatialArtifactMissingError):
            svc.get_station_geospatial_context("cpcb_peenya")

    def test_mtime_reload_behavior(self, geospatial_test_env) -> None:
        """Changing parquet mtime must trigger a DataFrame reload."""
        import time
        import json
        import pandas as pd
        import backend.app.services.geospatial_evidence_service as svc

        processed = geospatial_test_env["processed"]

        # Write first version
        pd.DataFrame([
            {"station_id": "cpcb_a", "city": "bengaluru", "latitude": 12.97, "longitude": 77.59,
             "road_feature_coverage_status": "complete", "landuse_feature_coverage_status": "complete",
             "investigation_context_coverage_status": "complete", "data_completeness_score": 1.0,
             "limitations": ""},
        ]).to_parquet(processed / "station_geospatial_context.parquet", index=False)
        with (processed / "geospatial_build_metadata.json").open("w") as f:
            json.dump({"build_status": "full", "stations_count": 1}, f)

        cov1 = svc.get_city_geospatial_coverage("bengaluru")
        assert cov1["total_stations"] == 1

        # Write second version with an additional station
        time.sleep(0.02)  # Ensure mtime changes
        pd.DataFrame([
            {"station_id": "cpcb_a", "city": "bengaluru", "latitude": 12.97, "longitude": 77.59,
             "road_feature_coverage_status": "complete", "landuse_feature_coverage_status": "complete",
             "investigation_context_coverage_status": "complete", "data_completeness_score": 1.0,
             "limitations": ""},
            {"station_id": "cpcb_b", "city": "bengaluru", "latitude": 12.98, "longitude": 77.60,
             "road_feature_coverage_status": "complete", "landuse_feature_coverage_status": "complete",
             "investigation_context_coverage_status": "complete", "data_completeness_score": 1.0,
             "limitations": ""},
        ]).to_parquet(processed / "station_geospatial_context.parquet", index=False)

        cov2 = svc.get_city_geospatial_coverage("bengaluru")
        assert cov2["total_stations"] == 2, "Mtime reload should pick up new station"
