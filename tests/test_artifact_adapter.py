from __future__ import annotations

import pytest

from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
    get_city_station_snapshots,
    get_latest_station_reading,
    get_lightgbm_explanation_context,
    get_station_evaluation,
    get_station_geospatial_context,
    get_station_quality,
    get_station_recent_observations,
    get_station_snapshot,
    list_station_snapshots,
)
from pipeline.station_registry import refresh_registry


NON_ELIGIBLE_STATIONS = [
    ("cpcb_kadabesanahalli", "insufficient_pm25_history", ["pm10", "no2"]),
    ("cpcb_city_railway", "pm25_sensor_unavailable", ["pm10", "no2"]),
    ("cpcb_saneguravahalli", "pm25_sensor_unavailable", ["pm10", "no2"]),
]


class TestGetStationSnapshot:
    def test_valid_station(self) -> None:
        snap = get_station_snapshot("cpcb_hebbal")
        assert snap["station_id"] == "cpcb_hebbal"
        assert snap["city"] == "Bengaluru"
        assert snap["forecast_eligible"] is True
        assert snap["forecast_engine"] in ("persistence", "lightgbm")
        assert snap["predicted_pm25"] >= 0
        assert snap["risk_category"] in ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe")
        assert "quality_classification" in snap
        assert "evaluation_metrics" in snap
        assert "artifact_status" in snap

    def test_unknown_station_raises(self) -> None:
        with pytest.raises(UnknownStationError):
            get_station_snapshot("nonexistent_station")

    def test_unsupported_city_raises(self) -> None:
        with pytest.raises(UnsupportedCityError):
            get_station_snapshot("cpcb_hebbal", city="delhi")

    def test_all_stations_have_snapshots(self) -> None:
        refresh_registry()
        from pipeline.station_registry import BENGALURU_STATIONS
        for config in BENGALURU_STATIONS:
            snap = get_station_snapshot(config.station_id)
            assert snap["station_id"] == config.station_id
            if config.forecast_eligible:
                assert snap["forecast_eligible"] is True
                assert snap["station_name"] == config.station_name
                assert "forecast_engine" in snap
            else:
                assert snap["forecast_eligible"] is False
                assert "pm25_forecast_coverage_status" in snap
                assert "available_pollutants" in snap

    def test_non_eligible_station_returns_structured_response(self) -> None:
        for station_id, expected_status, expected_pollutants in NON_ELIGIBLE_STATIONS:
            snap = get_station_snapshot(station_id)
            assert snap["station_id"] == station_id
            assert snap["forecast_eligible"] is False
            assert snap["pm25_forecast_coverage_status"] == expected_status
            assert snap["available_pollutants"] == expected_pollutants


class TestListStationSnapshots:
    def test_returns_all_stations(self) -> None:
        snaps = list_station_snapshots()
        assert len(snaps) == 6

    def test_each_has_required_fields(self) -> None:
        snaps = list_station_snapshots()
        for snap in snaps:
            assert "station_id" in snap
            assert "forecast_engine" in snap
            assert "predicted_pm25" in snap
            assert "risk_category" in snap


class TestGetCityStationSnapshots:
    def test_bengaluru(self) -> None:
        snaps = get_city_station_snapshots("bengaluru")
        assert len(snaps) == 6

    def test_unsupported_city(self) -> None:
        with pytest.raises(UnsupportedCityError):
            get_city_station_snapshots("delhi")


class TestGetStationRecentObservations:
    def test_returns_observations(self) -> None:
        obs = get_station_recent_observations("cpcb_hebbal", lookback_hours=48)
        assert isinstance(obs, list)
        assert len(obs) > 0
        assert "timestamp" in obs[0]
        assert "pm25" in obs[0]

    def test_unknown_station(self) -> None:
        with pytest.raises(UnknownStationError):
            get_station_recent_observations("nonexistent")


class TestGetStationQuality:
    def test_returns_quality(self) -> None:
        q = get_station_quality("cpcb_hebbal")
        assert q["station_id"] == "cpcb_hebbal"
        assert "classification" in q
        assert "recommendation" in q
        assert "pm25_completeness_percent" in q

    def test_unknown_station(self) -> None:
        with pytest.raises(UnknownStationError):
            get_station_quality("nonexistent")


class TestGetStationEvaluation:
    def test_returns_evaluation(self) -> None:
        e = get_station_evaluation("cpcb_hebbal")
        assert e["station_id"] == "cpcb_hebbal"
        assert "model_selected_for_serving" in e
        assert "persistence_rmse" in e
        assert e["model_selected_for_serving"] in ("persistence", "lightgbm")

    def test_unknown_station(self) -> None:
        with pytest.raises(UnknownStationError):
            get_station_evaluation("nonexistent")


class TestNonEligibleStationServices:
    def test_confidence_for_non_eligible(self) -> None:
        from backend.app.services.confidence_service import get_forecast_confidence
        for station_id, status, _ in NON_ELIGIBLE_STATIONS:
            result = get_forecast_confidence(station_id)
            assert result["station_id"] == station_id
            assert result["forecast_eligible"] is False
            assert result["confidence_level"] == "Unavailable"
            assert result["pm25_forecast_coverage_status"] == status

    def test_evidence_for_non_eligible(self) -> None:
        from backend.app.services.forecast_evidence_service import get_forecast_evidence
        for station_id, status, pollutants in NON_ELIGIBLE_STATIONS:
            result = get_forecast_evidence(station_id)
            assert result["station_id"] == station_id
            assert result["forecast_eligible"] is False
            assert result["forecast_engine"] == "unavailable"
            assert result["pm25_forecast_coverage_status"] == status
            assert result["available_pollutants"] == pollutants

    def test_advisory_for_non_eligible(self) -> None:
        from backend.app.services.citizen_advisory_service import get_citizen_advisory
        for station_id, status, _ in NON_ELIGIBLE_STATIONS:
            result = get_citizen_advisory(station_id)
            assert result["station_id"] == station_id
            assert result["forecast_eligible"] is False
            assert result["pm25_forecast_coverage_status"] == status


class TestComputeStationCapabilityClassification:
    def test_complete_classification(self) -> None:
        from pipeline.compute_station_capability import (
            compute_available_pollutants,
            compute_pm25_coverage_status,
        )
        project_root = None
        try:
            from backend.app.config import get_project_root
            project_root = get_project_root()
        except ImportError:
            import os
            project_root = Path(__file__).resolve().parents[1]
        from pathlib import Path

        quality_path = project_root / "data" / "processed" / "real" / "cpcb_hebbal" / "cpcb_hebbal_quality_summary.json"
        import json
        with quality_path.open("r", encoding="utf-8") as f:
            quality = json.load(f)
        assert compute_pm25_coverage_status(quality) == "complete"
        pollutants = compute_available_pollutants(quality)
        assert "pm25" in pollutants
        assert "pm10" in pollutants
        assert "no2" in pollutants

    def test_insufficient_pm25_history(self) -> None:
        from pipeline.compute_station_capability import (
            compute_available_pollutants,
            compute_pm25_coverage_status,
        )
        try:
            from backend.app.config import get_project_root
            project_root = get_project_root()
        except ImportError:
            from pathlib import Path
            project_root = Path(__file__).resolve().parents[1]
        from pathlib import Path

        quality_path = project_root / "data" / "processed" / "real" / "cpcb_kadabesanahalli" / "cpcb_kadabesanahalli_quality_summary.json"
        import json
        with quality_path.open("r", encoding="utf-8") as f:
            quality = json.load(f)
        assert compute_pm25_coverage_status(quality) == "insufficient_pm25_history"
        pollutants = compute_available_pollutants(quality)
        assert "pm25" not in pollutants
        assert "pm10" in pollutants
        assert "no2" in pollutants

    def test_pm25_sensor_unavailable(self) -> None:
        from pipeline.compute_station_capability import (
            compute_available_pollutants,
            compute_pm25_coverage_status,
        )
        try:
            from backend.app.config import get_project_root
            project_root = get_project_root()
        except ImportError:
            from pathlib import Path
            project_root = Path(__file__).resolve().parents[1]
        from pathlib import Path

        for sid in ("cpcb_city_railway", "cpcb_saneguravahalli"):
            quality_path = project_root / "data" / "processed" / "real" / sid / f"{sid}_quality_summary.json"
            import json
            with quality_path.open("r", encoding="utf-8") as f:
                quality = json.load(f)
            assert compute_pm25_coverage_status(quality) == "pm25_sensor_unavailable"
            pollutants = compute_available_pollutants(quality)
            assert "pm25" not in pollutants
            assert "pm10" in pollutants
            assert "no2" in pollutants


class TestGetLatestStationReading:
    def test_city_railway_no2_returns_real_value(self) -> None:
        result = get_latest_station_reading("cpcb_city_railway", "no2")
        assert result["station_id"] == "cpcb_city_railway"
        assert result["pollutant"] == "no2"
        assert result["available"] is True
        assert result["value"] is not None
        assert result["value"] > 0
        assert result["timestamp"] is not None

    def test_saneguravahalli_pm10_returns_real_value(self) -> None:
        result = get_latest_station_reading("cpcb_saneguravahalli", "pm10")
        assert result["station_id"] == "cpcb_saneguravahalli"
        assert result["pollutant"] == "pm10"
        assert result["available"] is True
        assert result["value"] is not None
        assert result["value"] > 0
        assert result["timestamp"] is not None

    def test_city_railway_pm25_returns_not_available(self) -> None:
        result = get_latest_station_reading("cpcb_city_railway", "pm25")
        assert result["station_id"] == "cpcb_city_railway"
        assert result["pollutant"] == "pm25"
        assert result["available"] is False
        assert result["value"] is None
        assert result["note"] is not None
        assert "not available" in result["note"].lower() or "No valid" in result["note"]

    def test_hebbal_pm25_returns_real_value(self) -> None:
        result = get_latest_station_reading("cpcb_hebbal", "pm25")
        assert result["station_id"] == "cpcb_hebbal"
        assert result["pollutant"] == "pm25"
        assert result["available"] is True
        assert result["value"] is not None
        assert result["value"] > 0
        assert result["timestamp"] is not None

    def test_unknown_station_raises(self) -> None:
        with pytest.raises(UnknownStationError):
            get_latest_station_reading("nonexistent", "pm25")


class TestGetStationGeospatialContextWithReadings:
    def test_saneguravahalli_includes_pm10_no2_readings(self) -> None:
        geo = get_station_geospatial_context("cpcb_saneguravahalli")
        assert "station_id" in geo
        assert geo["station_id"] == "cpcb_saneguravahalli"
        assert "current_readings" in geo
        readings = geo["current_readings"]
        assert "pm10" in readings
        assert readings["pm10"]["available"] is True
        assert readings["pm10"]["value"] is not None
        assert readings["pm10"]["value"] > 0
        assert "no2" in readings
        assert readings["no2"]["available"] is True
        assert readings["no2"]["value"] is not None
        assert readings["no2"]["value"] > 0
        assert "pm25" not in readings
        assert "landuse_context" in geo
        assert "road_context" in geo


class TestGetLightgbmExplanationContext:
    def test_persistence_returns_none(self) -> None:
        result = get_lightgbm_explanation_context("cpcb_silkboard")
        assert result is None

    def test_lightgbm_returns_context(self) -> None:
        result = get_lightgbm_explanation_context("cpcb_peenya")
        assert result is not None
        assert result["explanation_method"] == "model_context_fallback"
        assert "lag_values" in result
        assert "rolling_values" in result
        assert "temporal_context" in result

    def test_unknown_station(self) -> None:
        with pytest.raises(UnknownStationError):
            get_lightgbm_explanation_context("nonexistent")
