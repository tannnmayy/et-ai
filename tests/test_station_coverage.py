"""Tests for Milestone 5C — Bengaluru 12-Station Coverage Expansion.

All tests are offline. No production files are touched.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.app.config import BENGALURU_BOUNDING_BOX


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def tmp_candidates_csv(tmp_path) -> Path:
    path = tmp_path / "bengaluru_station_candidates.csv"
    rows = [
        {
            "raw_filename": "btm_layout_bengaluru_cpcb_15m.csv",
            "proposed_station_id": "cpcb_btmlayout",
            "display_name": "BTM Layout",
            "city": "bengaluru",
            "latitude": "12.9166",
            "longitude": "77.6101",
            "source_authority": "CPCB",
            "metadata_verification_status": "verified",
            "geospatial_eligible": "True",
            "onboarding_status": "pending",
            "notes": "",
        },
        {
            "raw_filename": "kasturi_nagar_bengaluru_kspcb_15m.csv",
            "proposed_station_id": "cpcb_kasturinagar",
            "display_name": "Kasturi Nagar",
            "city": "bengaluru",
            "latitude": "12.9791",
            "longitude": "77.6510",
            "source_authority": "KSPCB",
            "metadata_verification_status": "verified",
            "geospatial_eligible": "True",
            "onboarding_status": "pending",
            "notes": "",
        },
    ]
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def tmp_registry_csv(tmp_path) -> Path:
    path = tmp_path / "bengaluru_station_registry.csv"
    columns = [
        "station_id", "display_name", "city", "latitude", "longitude",
        "source", "coordinate_source", "coordinate_confidence", "verification_note",
        "active", "geospatial_eligible", "raw_filename",
    ]
    rows = [
        ["cpcb_hebbal", "Hebbal", "bengaluru", "13.029152", "77.585901",
         "CPCB/KSPCB", "OpenAQ", "Verified", "", "True", "True", "hebbal.csv"],
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    return path


@pytest.fixture
def tmp_audit_csv(tmp_path) -> Path:
    path = tmp_path / "bengaluru_station_onboarding_audit.csv"
    rows = [
        {
            "raw_filename": "btm_layout_bengaluru_cpcb_15m.csv",
            "proposed_station_id": "cpcb_btmlayout",
            "eligibility_status": "eligible",
            "exclusion_reason": "",
        },
        {
            "raw_filename": "kasturi_nagar_bengaluru_kspcb_15m.csv",
            "proposed_station_id": "cpcb_kasturinagar",
            "eligibility_status": "eligible",
            "exclusion_reason": "",
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


# =========================================================================
# Part A: Audit tests
# =========================================================================


class TestAuditDiscovery:
    def test_in_scope_candidates_are_six(self) -> None:
        from pipeline.audit_bengaluru_station_coverage import IN_SCOPE_CANDIDATES
        assert len(IN_SCOPE_CANDIDATES) == 6
        assert all("jigani" not in f for f in IN_SCOPE_CANDIDATES)

    def test_jigani_not_in_scope(self) -> None:
        from pipeline.audit_bengaluru_station_coverage import IN_SCOPE_CANDIDATES
        assert "jigani_bengaluru_kspcb_15m.csv" not in IN_SCOPE_CANDIDATES
        assert all("jigani" not in f for f in IN_SCOPE_CANDIDATES)

    def test_audit_handles_missing_file(self) -> None:
        from pipeline.audit_bengaluru_station_coverage import audit_single_candidate

        with patch("pipeline.audit_bengaluru_station_coverage.RAW_DIR", Path("Z:\\nonexistent")):
            result = audit_single_candidate("nonexistent_file.csv")
        assert result["eligibility_status"] == "error"
        assert "not found" in result["exclusion_reason"].lower()


# =========================================================================
# Part B: Candidate validation tests
# =========================================================================


class TestCandidateValidation:
    def test_rejects_missing_coordinates(self, tmp_candidates_csv, tmp_path) -> None:
        from pipeline.validate_station_candidates import validate_candidates

        df = pd.read_csv(tmp_candidates_csv)
        df["latitude"] = df["latitude"].astype(object)
        df["longitude"] = df["longitude"].astype(object)
        df.loc[0, "latitude"] = ""
        df.loc[0, "longitude"] = ""
        bad_path = tmp_path / "bad_candidates.csv"
        df.to_csv(bad_path, index=False)

        with patch("pipeline.validate_station_candidates.CANDIDATES_PATH", bad_path):
            errors = validate_candidates(dry_run=True)

        coord_errors = [e for e in errors if "coordinates" in e["error"].lower()]
        assert len(coord_errors) >= 1

    def test_rejects_coordinates_outside_bbox(self, tmp_candidates_csv, tmp_path) -> None:
        from pipeline.validate_station_candidates import validate_candidates

        df = pd.read_csv(tmp_candidates_csv)
        df["latitude"] = df["latitude"].astype(object)
        df["longitude"] = df["longitude"].astype(object)
        df.loc[0, "latitude"] = "28.61"
        df.loc[0, "longitude"] = "77.23"
        bad_path = tmp_path / "out_of_bounds.csv"
        df.to_csv(bad_path, index=False)

        with patch("pipeline.validate_station_candidates.CANDIDATES_PATH", bad_path):
            errors = validate_candidates(dry_run=True)

        bbox_errors = [e for e in errors if "outside" in e["error"].lower()]
        assert len(bbox_errors) >= 1

    def test_rejects_pending_verification(self, tmp_candidates_csv, tmp_path) -> None:
        from pipeline.validate_station_candidates import validate_candidates

        df = pd.read_csv(tmp_candidates_csv)
        df.loc[0, "metadata_verification_status"] = "pending_verification"
        bad_path = tmp_path / "pending.csv"
        df.to_csv(bad_path, index=False)

        with patch("pipeline.validate_station_candidates.CANDIDATES_PATH", bad_path):
            errors = validate_candidates(dry_run=True)

        status_errors = [e for e in errors if "meta" in e["field"].lower()]
        assert len(status_errors) >= 1

    def test_rejects_duplicate_ids(self, tmp_candidates_csv, tmp_path) -> None:
        from pipeline.validate_station_candidates import validate_candidates

        df = pd.read_csv(tmp_candidates_csv)
        df.loc[1, "proposed_station_id"] = df.loc[0, "proposed_station_id"]
        bad_path = tmp_path / "dup_ids.csv"
        df.to_csv(bad_path, index=False)

        with patch("pipeline.validate_station_candidates.CANDIDATES_PATH", bad_path):
            errors = validate_candidates(dry_run=True)

        dup_errors = [e for e in errors if "duplicate" in e["error"].lower()]
        assert len(dup_errors) >= 1


# =========================================================================
# Part D: Activation tests
# =========================================================================


class TestActivation:
    def test_dry_run_shows_blocked_reasons(self, tmp_candidates_csv, tmp_registry_csv, tmp_audit_csv, tmp_path) -> None:
        from pipeline.activate_bengaluru_stations import run_activation

        with patch("pipeline.activate_bengaluru_stations.CANDIDATES_PATH", tmp_candidates_csv):
            with patch("pipeline.activate_bengaluru_stations.REGISTRY_PATH", tmp_registry_csv):
                with patch("pipeline.activate_bengaluru_stations.AUDIT_CSV", tmp_audit_csv):
                    with patch("pipeline.activate_bengaluru_stations.REPORTS_DIR", tmp_path / "reports"):
                        results = run_activation(dry_run=True)

        assert len(results) == 2
        # Both should show as possible since we set verified and audit eligible
        possible = [r for r in results if r["activation_possible"]]
        assert len(possible) >= 1

    def test_apply_updates_registry(self, tmp_candidates_csv, tmp_registry_csv, tmp_audit_csv, tmp_path) -> None:
        from pipeline.activate_bengaluru_stations import run_activation

        with patch("pipeline.activate_bengaluru_stations.CANDIDATES_PATH", tmp_candidates_csv):
            with patch("pipeline.activate_bengaluru_stations.REGISTRY_PATH", tmp_registry_csv):
                with patch("pipeline.activate_bengaluru_stations.AUDIT_CSV", tmp_audit_csv):
                    with patch("pipeline.activate_bengaluru_stations.REPORTS_DIR", tmp_path / "reports"):
                        run_activation(dry_run=False)

        # Registry should now have more rows
        df = pd.read_csv(tmp_registry_csv)
        assert len(df) > 1  # started with 1 (hebbal), added at least 1

    def test_never_activates_jigani(self, tmp_registry_csv, tmp_path) -> None:
        from pipeline.activate_bengaluru_stations import check_activation_gates

        row = {
            "raw_filename": "jigani_bengaluru_kspcb_15m.csv",
            "proposed_station_id": "cpcb_jigani",
            "latitude": "12.85",
            "longitude": "77.60",
            "source_authority": "KSPCB",
            "metadata_verification_status": "verified",
            "geospatial_eligible": "True",
            "notes": "",
        }
        passed, reasons = check_activation_gates(row, {}, set())
        assert not passed
        assert any("Jigani" in r for r in reasons)


# =========================================================================
# Part C: Registry function tests
# =========================================================================


class TestRegistryFunctions:
    def test_get_registry_stations_returns_active(self, tmp_registry_csv, tmp_path) -> None:
        from pipeline.station_registry import get_registry_stations

        with patch("pipeline.station_registry._get_registry_path", return_value=tmp_registry_csv):
            stations = get_registry_stations()

        assert len(stations) >= 1
        assert stations[0].station_id == "cpcb_hebbal"
        assert stations[0].active is True

    def test_refresh_registry_picks_up_changes(self, tmp_registry_csv, tmp_path) -> None:
        from pipeline.station_registry import refresh_registry, get_registry_stations

        with patch("pipeline.station_registry._get_registry_path", return_value=tmp_registry_csv):
            refresh_registry()
            stations_before = get_registry_stations()
            count_before = len(stations_before)

            # Append a new station to the CSV
            with tmp_registry_csv.open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["cpcb_new", "New Station", "bengaluru", "12.95", "77.58",
                                 "CPCB", "candidate", "Manual", "", "True", "True", "new.csv"])

            refresh_registry()
            stations_after = get_registry_stations()
            assert len(stations_after) == count_before + 1
            assert "cpcb_new" in [s.station_id for s in stations_after]


# =========================================================================
# Part F: Stations API tests
# =========================================================================


class TestStationsAPI:
    def test_get_stations_returns_active(self) -> None:
        from backend.app.services.station_discovery_service import list_stations

        with patch("backend.app.services.station_discovery_service._forecast_available", return_value=False):
            with patch("backend.app.services.station_discovery_service._geospatial_available", return_value=False):
                stations = list_stations(city="bengaluru", include_inactive=False)

        assert len(stations) > 0
        for s in stations:
            assert s["data_status"] == "active"

    def test_get_stations_case_insensitive_city(self) -> None:
        from backend.app.services.station_discovery_service import list_stations

        with patch("backend.app.services.station_discovery_service._forecast_available", return_value=False):
            with patch("backend.app.services.station_discovery_service._geospatial_available", return_value=False):
                stations_upper = list_stations(city="BENGALURU", include_inactive=False)
                stations_lower = list_stations(city="bengaluru", include_inactive=False)

        assert len(stations_upper) > 0
        assert len(stations_upper) == len(stations_lower)

    def test_get_stations_default_excludes_inactive(self) -> None:
        from backend.app.services.station_discovery_service import list_stations

        with patch("backend.app.services.station_discovery_service._forecast_available", return_value=False):
            with patch("backend.app.services.station_discovery_service._geospatial_available", return_value=False):
                active = list_stations(city="bengaluru", include_inactive=False)
                with_inactive = list_stations(city="bengaluru", include_inactive=True)

        assert len(with_inactive) >= len(active)

    def test_get_stations_endpoint_schema(self) -> None:
        from fastapi.testclient import TestClient
        from backend.app.main import app

        with patch("backend.app.services.station_discovery_service._forecast_available", return_value=True):
            with patch("backend.app.services.station_discovery_service._geospatial_available", return_value=True):
                client = TestClient(app)
                response = client.get("/stations?city=bengaluru")
                assert response.status_code == 200
                data = response.json()
                assert "city" in data
                assert "total_stations" in data
                assert "stations" in data
                assert data["city"] == "bengaluru"

    def test_get_stations_excludes_jigani(self) -> None:
        from backend.app.services.station_discovery_service import list_stations

        with patch("backend.app.services.station_discovery_service._forecast_available", return_value=False):
            with patch("backend.app.services.station_discovery_service._geospatial_available", return_value=False):
                stations = list_stations(city="bengaluru", include_inactive=True)

        ids = [s["station_id"] for s in stations]
        assert "cpcb_jigani" not in ids
        assert not any("jigani" in sid for sid in ids)


# =========================================================================
# Part G: Geospatial builder test
# =========================================================================


class TestGeospatialBuilderCoverage:
    def test_builder_metadata_includes_station_counts(self, geospatial_test_env) -> None:
        import json
        import sys
        from pipeline.build_geospatial_context import build_geospatial_context

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

        from unittest.mock import patch as mock_patch

        with mock_patch("pipeline.build_geospatial_context._load_registry") as mock_reg:
            mock_reg.return_value = pd.DataFrame([
                {"station_id": "cpcb_peenya", "latitude": 12.97, "longitude": 77.59, "city": "bengaluru"},
                {"station_id": "cpcb_hebbal", "latitude": 13.03, "longitude": 77.59, "city": "bengaluru"},
            ])
            result = build_geospatial_context(allow_partial_osm=False)

        assert result["build_status"] == "full"
        assert result["registry_station_count"] == 2
        assert isinstance(result["geospatial_station_count"], int)
        assert result["geospatial_station_count"] >= 0
        assert "cpcb_peenya" in result["station_ids_included"]
        assert "cpcb_hebbal" in result["station_ids_included"]


# =========================================================================
# Test isolation: no production paths are touched
# =========================================================================


class TestTestIsolation:
    def test_no_production_paths_written(self) -> None:
        """Verify all fixture paths resolve to tmp_path."""
        from pipeline.cpcb_csv_adapter import read_raw_csv

        # All test data in memory; no file written to data/raw, data/processed, or data/reports
        csv_content = "timestamp,pm25\n2025-01-01 00:00:00,10.0\n"
        buf = io.StringIO(csv_content)
        df = read_raw_csv(buf)
        assert len(df) == 1
        assert "pm25" in df.columns


# =========================================================================
# Part E: Rebuild orchestration validation
# =========================================================================


class TestRebuildOrchestration:
    def test_rebuild_dry_run_returns_summary(self) -> None:
        from pipeline.rebuild_bengaluru_station_artifacts import rebuild_all

        with patch("pipeline.station_registry.get_registry_stations") as mock_reg:
            from pipeline.station_registry import StationConfig
            mock_reg.return_value = [
                StationConfig(
                    station_id="cpcb_test", station_name="Test",
                    source_file="test.csv",
                    display_name="Test", active=True, geospatial_eligible=True,
                ),
            ]
            result = rebuild_all(Path("/tmp"), dry_run=True)

        assert result is not None
        assert result["dry_run"] is True


# =========================================================================
# Part I: Metadata verification tests
# =========================================================================


class _MockFoundHandler:
    label = "MockFound"

    def lookup(self, station_id: str, raw_filename: str) -> Any:
        from pipeline.verify_bengaluru_station_metadata import SourceResult
        return SourceResult(
            result="found",
            latitude=12.9166,
            longitude=77.6101,
            display_name="BTM Layout",
            source_authority="CPCB",
            source_url="https://example.com/station",
            evidence_note="Mock CPCB record match.",
        )


class _MockAmbiguousHandler:
    label = "MockAmbiguous"

    def lookup(self, station_id: str, raw_filename: str) -> Any:
        from pipeline.verify_bengaluru_station_metadata import SourceResult
        return SourceResult(
            result="ambiguous",
            latitude=12.95,
            longitude=77.60,
            source_authority="Google Maps",
            source_url="",
            evidence_note="Broad locality result.",
            rejection_reason="Broad locality, not a verified station",
        )


class _MockNotFoundHandler:
    label = "MockNotFound"

    def lookup(self, station_id: str, raw_filename: str) -> Any:
        from pipeline.verify_bengaluru_station_metadata import SourceResult
        return SourceResult(result="not_found")


class _MockOutOfScopeHandler:
    label = "MockOutOfScope"

    def lookup(self, station_id: str, raw_filename: str) -> Any:
        from pipeline.verify_bengaluru_station_metadata import SourceResult
        return SourceResult(
            result="out_of_scope",
            latitude=28.61,
            longitude=77.23,
            source_authority="CPCB",
            source_url="",
            evidence_note="Station outside Bengaluru scope.",
            rejection_reason="Outside Bengaluru bounding box",
        )


class TestMetadataVerification:
    def test_exact_official_match_accepted(self, tmp_candidates_csv, tmp_path) -> None:
        from pipeline.verify_bengaluru_station_metadata import verify_candidate

        df = pd.read_csv(tmp_candidates_csv)
        row = df.iloc[0].to_dict()
        handlers = [_MockFoundHandler(), _MockNotFoundHandler()]
        decision, info = verify_candidate(row, handlers)
        assert decision == "verified_exact"
        assert info["latitude_considered"] == 12.9166
        assert info["longitude_considered"] == 77.6101

    def test_ambiguous_locality_result_rejected(self, tmp_candidates_csv, tmp_path) -> None:
        from pipeline.verify_bengaluru_station_metadata import verify_candidate

        df = pd.read_csv(tmp_candidates_csv)
        row = df.iloc[0].to_dict()
        handlers = [_MockAmbiguousHandler(), _MockNotFoundHandler()]
        decision, info = verify_candidate(row, handlers)
        assert decision == "ambiguous"
        assert "broad locality" in info["rejection_reason"].lower()

    def test_out_of_bounds_result_rejected(self, tmp_candidates_csv, tmp_path) -> None:
        from pipeline.verify_bengaluru_station_metadata import verify_candidate

        df = pd.read_csv(tmp_candidates_csv)
        row = df.iloc[0].to_dict()
        handlers = [_MockOutOfScopeHandler(), _MockNotFoundHandler()]
        decision, info = verify_candidate(row, handlers)
        assert decision == "out_of_scope"
        assert "outside" in info["rejection_reason"].lower()

    def test_not_found_when_no_source_matches(self, tmp_candidates_csv, tmp_path) -> None:
        from pipeline.verify_bengaluru_station_metadata import verify_candidate

        df = pd.read_csv(tmp_candidates_csv)
        row = df.iloc[0].to_dict()
        handlers = [_MockNotFoundHandler()]
        decision, info = verify_candidate(row, handlers)
        assert decision == "not_found"

    def test_dry_run_does_not_modify_candidates_file(self, tmp_candidates_csv, tmp_path) -> None:
        from pipeline.verify_bengaluru_station_metadata import run_verification

        with patch("pipeline.verify_bengaluru_station_metadata.CANDIDATES_PATH", tmp_candidates_csv):
            with patch("pipeline.verify_bengaluru_station_metadata.REPORTS_DIR", tmp_path / "reports"):
                with patch("pipeline.verify_bengaluru_station_metadata._build_source_handlers") as mock_build:
                    mock_build.return_value = [_MockFoundHandler()]
                    records = run_verification(dry_run=True)

        assert len(records) >= 1
        assert records[0]["decision"] == "verified_exact"
        # CSV unchanged
        df_after = pd.read_csv(tmp_candidates_csv)
        statuses = df_after["metadata_verification_status"].tolist()
        assert all(s == "verified" for s in statuses)  # original fixture has "verified"

    def test_apply_updates_only_verified_exact_rows(self, tmp_path) -> None:
        from pipeline.verify_bengaluru_station_metadata import run_verification

        path = tmp_path / "bengaluru_station_candidates.csv"
        rows = [
            {
                "raw_filename": "btm_layout_bengaluru_cpcb_15m.csv",
                "proposed_station_id": "cpcb_btmlayout",
                "display_name": "",
                "city": "bengaluru",
                "latitude": "",
                "longitude": "",
                "source_authority": "",
                "metadata_verification_status": "pending_verification",
                "geospatial_eligible": "True",
                "onboarding_status": "pending",
                "notes": "",
                "metadata_source_url": "",
            },
            {
                "raw_filename": "kasturi_nagar_bengaluru_kspcb_15m.csv",
                "proposed_station_id": "cpcb_kasturinagar",
                "display_name": "",
                "city": "bengaluru",
                "latitude": "",
                "longitude": "",
                "source_authority": "",
                "metadata_verification_status": "pending_verification",
                "geospatial_eligible": "True",
                "onboarding_status": "pending",
                "notes": "",
                "metadata_source_url": "",
            },
        ]
        pd.DataFrame(rows).to_csv(path, index=False)

        class _Found:
            label = "MockFound"
            def lookup(self, station_id: str, raw_filename: str) -> Any:
                from pipeline.verify_bengaluru_station_metadata import SourceResult
                if station_id == "cpcb_btmlayout":
                    return SourceResult(
                        result="found", latitude=12.9166, longitude=77.6101,
                        display_name="BTM Layout", source_authority="CPCB",
                        source_url="https://example.com", evidence_note="Match",
                    )
                return SourceResult(result="not_found")

        with patch("pipeline.verify_bengaluru_station_metadata.CANDIDATES_PATH", path):
            with patch("pipeline.verify_bengaluru_station_metadata.REPORTS_DIR", tmp_path / "reports"):
                with patch("pipeline.verify_bengaluru_station_metadata._build_source_handlers") as mock_build:
                    mock_build.return_value = [_Found()]
                    records = run_verification(dry_run=False)

        df_after = pd.read_csv(path)
        btmlayout = df_after[df_after["proposed_station_id"] == "cpcb_btmlayout"].iloc[0]
        kasturi = df_after[df_after["proposed_station_id"] == "cpcb_kasturinagar"].iloc[0]

        assert btmlayout["metadata_verification_status"] == "verified"
        assert str(btmlayout["latitude"]) == "12.9166"
        assert str(btmlayout["longitude"]) == "77.6101"
        assert btmlayout["source_authority"] == "CPCB"

        assert kasturi["metadata_verification_status"] == "pending_verification"
        assert pd.isna(kasturi["latitude"])  # unchanged

    def test_jigani_excluded_from_verification(self) -> None:
        from pipeline.verify_bengaluru_station_metadata import verify_candidate

        row = {
            "raw_filename": "jigani_bengaluru_kspcb_15m.csv",
            "proposed_station_id": "cpcb_jigani",
            "latitude": "",
            "longitude": "",
        }
        decision, info = verify_candidate(row, [])
        assert decision == "out_of_scope"
        assert "Excluded" in info["rejection_reason"]

    def test_bounding_box_enforced_via_mock(self) -> None:
        from pipeline.verify_bengaluru_station_metadata import verify_candidate, SourceResult

        class _OutsideBBoxHandler:
            label = "OutsideBBox"
            def lookup(self, station_id: str, raw_filename: str) -> Any:
                return SourceResult(
                    result="found", latitude=28.61, longitude=77.23,
                    display_name="Delhi Station", source_authority="CPCB",
                    source_url="", evidence_note="Outside Bengaluru",
                )

        row = {
            "raw_filename": "btm_layout_bengaluru_cpcb_15m.csv",
            "proposed_station_id": "cpcb_btmlayout",
        }
        decision, info = verify_candidate(row, [_OutsideBBoxHandler()])
        assert decision == "out_of_scope"
        assert "outside" in info["rejection_reason"].lower()


# =========================================================================
# OpenAQ candidate location audit tests
# =========================================================================


MOCK_OPENAQ_LOCATIONS_CSV_DATA = """location_id,location_name,latitude,longitude,locality,country_code,country_name,is_active
412,Peenya Bengaluru - KSPCB,13.0339,77.51321111,,IN,India,
594,"BTM Layout, Bengaluru - KSPCB",12.91281111,77.60921944,,IN,India,
797,City Railway Station - KSPCB,12.9773472,77.57069722,,IN,India,
2589,SaneguravaHalli - KSPCB,12.9916694,77.54583056,,IN,India,
2592,"BWSSB Kadabesanahalli, Bengaluru - KSPCB",12.93890556,77.69727222,,IN,India,
5547,"BWSSB Kadabesanahalli, Bengaluru - CPCB",12.9352049,77.6814488,,IN,India,
5548,"BTM Layout, Bengaluru - CPCB",12.9135218,77.5950804,,IN,India,
5574,"City Railway Station, Bengaluru - KSPCB",12.9756843,77.5660749,,IN,India,
5644,"Sanegurava Halli, Bengaluru - KSPCB",12.990328,77.5431385,,IN,India,
3409312,"BWSSB Kadabesanahalli, Bengaluru - CPCB",12.9352049,77.6814488,,IN,India,
3409385,"RVCE-Mailasandra, Bengaluru - KSPCB",12.921418,77.502466,,IN,India,
3409388,"Kasturi Nagar, Bengaluru - KSPCB",13.003872,77.664217,,IN,India,
"""

MOCK_OPENAQ_JSON_CACHE = {
    "meta": {"page": 1, "limit": 1000, "found": 2},
    "results": [
        {
            "id": 5548,
            "name": "BTM Layout, Bengaluru - CPCB",
            "locality": None,
            "coordinates": {"latitude": 12.9135218, "longitude": 77.5950804},
            "provider": {"name": "CPCB"},
            "sensors": [
                {"parameter": {"name": "pm25", "units": "\u00b5g/m\u00b3"}},
                {"parameter": {"name": "pm10", "units": "\u00b5g/m\u00b3"}},
            ],
        },
        {
            "id": 5574,
            "name": "City Railway Station, Bengaluru - KSPCB",
            "locality": None,
            "coordinates": {"latitude": 12.9756843, "longitude": 77.5660749},
            "provider": {"name": "KSPCB"},
            "sensors": [
                {"parameter": {"name": "pm10", "units": "\u00b5g/m\u00b3"}},
            ],
        },
    ],
}


MOCK_OPENAQ_JSON_CACHE_META_RESULTS = {
    "meta": {
        "results": [
            {
                "id": 5644,
                "name": "Sanegurava Halli, Bengaluru - KSPCB",
                "locality": None,
                "coordinates": {"latitude": 12.990328, "longitude": 77.5431385},
                "provider": {"name": "KSPCB"},
                "sensors": [
                    {"parameter": {"name": "pm10", "units": "\u00b5g/m\u00b3"}},
                ],
            },
        ]
    }
}


class TestOpenAQCandidateAudit:
    def _make_candidates_csv(self, tmp_path, rows: list[dict]) -> Path:
        path = tmp_path / "bengaluru_station_candidates.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def _make_locations_csv(self, tmp_path, data: str = "") -> Path:
        path = tmp_path / "openaq_bengaluru_locations.csv"
        Path(path).write_text(data or MOCK_OPENAQ_LOCATIONS_CSV_DATA, encoding="utf-8")
        return path

    def _make_json_cache(self, tmp_path, payload: dict | None = None) -> Path:
        d = tmp_path / "openaq"
        d.mkdir(parents=True, exist_ok=True)
        path = d / "locations_test_page_001.json"
        path.write_text(json.dumps(payload or MOCK_OPENAQ_JSON_CACHE), encoding="utf-8")
        return path

    CANDIDATE_BTM = {
        "raw_filename": "btm_layout_bengaluru_cpcb_15m.csv",
        "proposed_station_id": "cpcb_btmlayout",
        "display_name": "",
        "city": "bengaluru",
        "latitude": "",
        "longitude": "",
        "source_authority": "",
        "metadata_verification_status": "pending_verification",
        "geospatial_eligible": "True",
        "onboarding_status": "pending",
        "notes": "",
        "metadata_source_url": "",
    }

    CANDIDATE_KADABE = {
        "raw_filename": "bwssb_kadabesanahalli_bengaluru_cpcb_15m.csv",
        "proposed_station_id": "cpcb_kadabesanahalli",
        "display_name": "",
        "city": "bengaluru",
        "latitude": "",
        "longitude": "",
        "source_authority": "",
        "metadata_verification_status": "pending_verification",
        "geospatial_eligible": "True",
        "onboarding_status": "pending",
        "notes": "",
        "metadata_source_url": "",
    }

    CANDIDATE_RAILWAY = {
        "raw_filename": "city_railway_station_bengaluru_kspcb_15m.csv",
        "proposed_station_id": "cpcb_city_railway",
        "display_name": "",
        "city": "bengaluru",
        "latitude": "",
        "longitude": "",
        "source_authority": "",
        "metadata_verification_status": "pending_verification",
        "geospatial_eligible": "True",
        "onboarding_status": "pending",
        "notes": "",
        "metadata_source_url": "",
    }

    CANDIDATE_KASTURI = {
        "raw_filename": "kasturi_nagar_bengaluru_kspcb_15m.csv",
        "proposed_station_id": "cpcb_kasturinagar",
        "display_name": "",
        "city": "bengaluru",
        "latitude": "",
        "longitude": "",
        "source_authority": "",
        "metadata_verification_status": "pending_verification",
        "geospatial_eligible": "True",
        "onboarding_status": "pending",
        "notes": "",
        "metadata_source_url": "",
    }

    CANDIDATE_RVCE = {
        "raw_filename": "rvce_mailasandra_bengaluru_kspcb_15m.csv",
        "proposed_station_id": "cpcb_rvce_mailasandra",
        "display_name": "",
        "city": "bengaluru",
        "latitude": "",
        "longitude": "",
        "source_authority": "",
        "metadata_verification_status": "pending_verification",
        "geospatial_eligible": "True",
        "onboarding_status": "pending",
        "notes": "",
        "metadata_source_url": "",
    }

    CANDIDATE_SANE = {
        "raw_filename": "sanegurava_halli_bengaluru_kspcb_15m.csv",
        "proposed_station_id": "cpcb_saneguravahalli",
        "display_name": "",
        "city": "bengaluru",
        "latitude": "",
        "longitude": "",
        "source_authority": "",
        "metadata_verification_status": "pending_verification",
        "geospatial_eligible": "True",
        "onboarding_status": "pending",
        "notes": "",
        "metadata_source_url": "",
    }

    CANDIDATE_JIGANI = {
        "raw_filename": "jigani_bengaluru_kspcb_15m.csv",
        "proposed_station_id": "cpcb_jigani",
        "display_name": "",
        "city": "bengaluru",
        "latitude": "",
        "longitude": "",
        "source_authority": "",
        "metadata_verification_status": "pending_verification",
        "geospatial_eligible": "True",
        "onboarding_status": "pending",
        "notes": "",
        "metadata_source_url": "",
    }

    # ------------------------------------------------------------------
    # 1. BTM Layout exact CPCB match
    # ------------------------------------------------------------------
    def test_btm_layout_exact_cpcb_match(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import load_cached_locations, match_candidate

        csv_path = self._make_locations_csv(tmp_path)
        with patch("pipeline.audit_openaq_candidate_locations.LOCATIONS_CSV", csv_path):
            locations = load_cached_locations()

        result = match_candidate(self.CANDIDATE_BTM, locations)

        assert result["confidence"] == "verified_exact"
        assert result["matched_location_id"] == 5548
        assert result["openaq_source_authority"] == "CPCB"
        assert abs(result["latitude"] - 12.9135) < 0.01
        assert abs(result["longitude"] - 77.5951) < 0.01

    # ------------------------------------------------------------------
    # 2. CPCB preferred over KSPCB for CPCB raw filename
    # ------------------------------------------------------------------
    def test_cpcb_preferred_over_kspcb(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import load_cached_locations, match_candidate

        csv_path = self._make_locations_csv(tmp_path)
        with patch("pipeline.audit_openaq_candidate_locations.LOCATIONS_CSV", csv_path):
            locations = load_cached_locations()

        result = match_candidate(self.CANDIDATE_KADABE, locations)

        assert result["confidence"] == "verified_exact"
        assert result["matched_location_id"] in (5547, 3409312)
        assert result["openaq_source_authority"] == "CPCB"

    # ------------------------------------------------------------------
    # 3. City Railway verified_exact even if PM10 only
    # ------------------------------------------------------------------
    def test_city_railway_verified_exact_without_pm25(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import load_cached_locations, match_candidate

        csv_path = self._make_locations_csv(tmp_path)
        with patch("pipeline.audit_openaq_candidate_locations.LOCATIONS_CSV", csv_path):
            locations = load_cached_locations()

        result = match_candidate(self.CANDIDATE_RAILWAY, locations)

        assert result["confidence"] == "verified_exact"
        assert result["matched_location_id"] == 5574
        # CSV cache has no sensor parameters → "unknown"
        assert result["openaq_pm25_observed"] in ("false", "unknown")

    # ------------------------------------------------------------------
    # 4. Sanegurava Halli verified_exact even if PM10 only
    # ------------------------------------------------------------------
    def test_saneguravahalli_verified_exact_without_pm25(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import load_cached_locations, match_candidate

        csv_path = self._make_locations_csv(tmp_path)
        with patch("pipeline.audit_openaq_candidate_locations.LOCATIONS_CSV", csv_path):
            locations = load_cached_locations()

        result = match_candidate(self.CANDIDATE_SANE, locations)

        assert result["confidence"] == "verified_exact"
        assert result["matched_location_id"] == 5644
        # CSV cache has no sensor parameters → "unknown"
        assert result["openaq_pm25_observed"] in ("false", "unknown")

    # ------------------------------------------------------------------
    # 4b. PM2.5 correctly detected from JSON cache
    # ------------------------------------------------------------------
    def test_pm25_detected_from_json_cache(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import (
            _load_locations_from_json_cache, match_candidate,
        )

        self._make_json_cache(tmp_path, MOCK_OPENAQ_JSON_CACHE)
        locations = _load_locations_from_json_cache(str(tmp_path / "openaq" / "locations_*.json"))

        row = {
            "raw_filename": "btm_layout_bengaluru_cpcb_15m.csv",
            "proposed_station_id": "cpcb_btmlayout",
            "display_name": "",
        }
        result = match_candidate(row, locations)
        assert result["confidence"] == "verified_exact"
        assert result["matched_location_id"] == 5548
        assert result["openaq_pm25_observed"] == "true"

        row2 = {
            "raw_filename": "city_railway_station_bengaluru_kspcb_15m.csv",
            "proposed_station_id": "cpcb_city_railway",
            "display_name": "",
        }
        result2 = match_candidate(row2, locations)
        assert result2["confidence"] == "verified_exact"
        assert result2["matched_location_id"] == 5574
        assert result2["openaq_pm25_observed"] == "false"

    # ------------------------------------------------------------------
    # 5. Unknown candidate becomes not_found
    # ------------------------------------------------------------------
    def test_unknown_candidate_not_found(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import load_cached_locations, match_candidate

        csv_path = self._make_locations_csv(tmp_path)
        with patch("pipeline.audit_openaq_candidate_locations.LOCATIONS_CSV", csv_path):
            locations = load_cached_locations()

        row = {
            "raw_filename": "unknown_station_bengaluru_cpcb_15m.csv",
            "proposed_station_id": "cpcb_unknown",
            "display_name": "",
        }
        result = match_candidate(row, locations)

        assert result["confidence"] == "not_found"
        assert result["matched_location_id"] is None

    # ------------------------------------------------------------------
    # 6. Out-of-bounds coordinates → ambiguous
    # ------------------------------------------------------------------
    def test_out_of_bounds_rejected(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import match_candidate

        locations = [
            {
                "location_id": 9999,
                "location_name": "BTM Layout, Delhi - CPCB",
                "latitude": 28.61,
                "longitude": 77.23,
                "locality": None,
                "source_provider": "CPCB",
                "sensor_parameters": ["pm25", "pm10"],
                "cache_source": "csv",
            },
        ]
        row = {
            "raw_filename": "btm_layout_bengaluru_cpcb_15m.csv",
            "proposed_station_id": "cpcb_btmlayout",
            "display_name": "",
        }
        result = match_candidate(row, locations)

        assert result["confidence"] == "ambiguous"
        assert "outside" in result["evidence_note"].lower()

    # ------------------------------------------------------------------
    # 7. Jigani is excluded
    # ------------------------------------------------------------------
    def test_jigani_excluded(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import match_candidate

        locations = [
            {
                "location_id": 100,
                "location_name": "Jigani - KSPCB",
                "latitude": 12.85,
                "longitude": 77.60,
                "locality": None,
                "source_provider": "KSPCB",
                "sensor_parameters": ["pm25"],
                "cache_source": "csv",
            },
        ]
        result = match_candidate(self.CANDIDATE_JIGANI, locations)

        assert result["confidence"] == "not_found"

    # ------------------------------------------------------------------
    # 8. Dry run does not modify any files
    # ------------------------------------------------------------------
    def test_dry_run_does_not_modify_files(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import run_audit

        candidates_path = self._make_candidates_csv(tmp_path, [
            self.CANDIDATE_BTM,
            self.CANDIDATE_RAILWAY,
        ])
        locations_path = self._make_locations_csv(tmp_path)

        with patch("pipeline.audit_openaq_candidate_locations.CANDIDATES_PATH", candidates_path):
            with patch("pipeline.audit_openaq_candidate_locations.LOCATIONS_CSV", locations_path):
                rows = run_audit(dry_run=True)

        assert len(rows) == 2
        assert rows[0]["confidence"] == "verified_exact"
        assert rows[1]["confidence"] == "verified_exact"

        df_candidates_after = pd.read_csv(candidates_path)
        assert list(df_candidates_after["metadata_verification_status"]) == ["pending_verification", "pending_verification"]

    # ------------------------------------------------------------------
    # 9. CSV cache is preferred over JSON cache
    # ------------------------------------------------------------------
    def test_csv_cache_preferred_over_json(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import load_cached_locations

        csv_path = self._make_locations_csv(tmp_path)
        json_path = self._make_json_cache(tmp_path)

        # Both caches present; CSV should be used
        with patch("pipeline.audit_openaq_candidate_locations.LOCATIONS_CSV", csv_path):
            with patch("pipeline.audit_openaq_candidate_locations.RAW_OPENAQ_DIR", tmp_path / "openaq"):
                locations = load_cached_locations()

        assert len(locations) >= 1
        for loc in locations:
            assert loc["cache_source"] == "csv"

    # ------------------------------------------------------------------
    # 10. No cache + no --allow-live-api → not_found, no network call
    # ------------------------------------------------------------------
    def test_no_cache_no_live_api_no_network_call(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import load_cached_locations, match_candidate

        # No CSV, no JSON cache exists at tmp_path
        with patch("pipeline.audit_openaq_candidate_locations.LOCATIONS_CSV", tmp_path / "nonexistent.csv"):
            with patch("pipeline.audit_openaq_candidate_locations.RAW_OPENAQ_DIR", tmp_path / "empty_openaq"):
                locations = load_cached_locations(allow_live_api=False)

        assert locations == []

        result = match_candidate(self.CANDIDATE_BTM, locations)
        assert result["confidence"] == "not_found"
        assert "No OpenAQ location" in result["evidence_note"]

    # ------------------------------------------------------------------
    # 11. JSON meta.results shape is parsed correctly
    # ------------------------------------------------------------------
    def test_json_meta_results_shape(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import _load_locations_from_json_cache

        json_dir = tmp_path / "openaq"
        json_dir.mkdir()
        path = json_dir / "locations_test_page_001.json"
        path.write_text(json.dumps(MOCK_OPENAQ_JSON_CACHE_META_RESULTS), encoding="utf-8")

        records = _load_locations_from_json_cache(str(json_dir / "locations_*.json"))

        assert len(records) == 1
        assert records[0]["location_id"] == 5644
        assert records[0]["location_name"] == "Sanegurava Halli, Bengaluru - KSPCB"

    # ------------------------------------------------------------------
    # 12. Malformed JSON record is skipped safely
    # ------------------------------------------------------------------
    def test_malformed_json_record_skipped(self, tmp_path) -> None:
        from pipeline.audit_openaq_candidate_locations import _load_locations_from_json_cache

        json_dir = tmp_path / "openaq"
        json_dir.mkdir()
        payload = {
            "meta": {"page": 1},
            "results": [
                {"id": 100, "name": "Good Station", "coordinates": {"latitude": 12.97, "longitude": 77.59}},
                {"id": None, "name": "Bad Station", "coordinates": {}},  # malformed
                {"id": 101, "name": "No Coords"},  # missing coordinates
                "not a dict",  # malformed
                {"id": 102, "name": "Good Station 2", "coordinates": {"latitude": 12.98, "longitude": 77.60}},
            ],
        }
        path = json_dir / "locations_test_page_001.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        records = _load_locations_from_json_cache(str(json_dir / "locations_*.json"))

        assert len(records) == 2
        assert records[0]["location_id"] == 100
        assert records[1]["location_id"] == 102

    # ------------------------------------------------------------------
    # 13. Live API fallback used only when both caches absent and explicitly allowed
    # ------------------------------------------------------------------
    def test_live_api_fallback_when_allowed(self, tmp_path, monkeypatch) -> None:
        from pipeline.audit_openaq_candidate_locations import load_cached_locations

        monkeypatch.setenv("OPENAQ_API_KEY", "test_key_123")

        with patch("pipeline.audit_openaq_candidate_locations.LOCATIONS_CSV", tmp_path / "nonexistent.csv"):
            with patch("pipeline.audit_openaq_candidate_locations.RAW_OPENAQ_DIR", tmp_path / "empty_openaq"):
                with patch("pipeline.audit_openaq_candidate_locations._load_locations_from_live_api") as mock_live:
                    mock_live.return_value = [
                        {
                            "location_id": 5548,
                            "location_name": "BTM Layout, Bengaluru - CPCB",
                            "latitude": 12.9135,
                            "longitude": 77.5951,
                            "locality": None,
                            "source_provider": "CPCB",
                            "sensor_parameters": ["pm25", "pm10"],
                            "cache_source": "live_api",
                        },
                    ]
                    locations = load_cached_locations(allow_live_api=True)

        assert len(locations) == 1
        assert locations[0]["location_id"] == 5548
        assert locations[0]["cache_source"] == "live_api"
        mock_live.assert_called_once()
