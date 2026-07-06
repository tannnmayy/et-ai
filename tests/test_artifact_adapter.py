from __future__ import annotations

import pytest

from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
    get_city_station_snapshots,
    get_lightgbm_explanation_context,
    get_station_evaluation,
    get_station_quality,
    get_station_recent_observations,
    get_station_snapshot,
    list_station_snapshots,
)


class TestGetStationSnapshot:
    def test_valid_station(self) -> None:
        snap = get_station_snapshot("cpcb_hebbal")
        assert snap["station_id"] == "cpcb_hebbal"
        assert snap["city"] == "Bengaluru"
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
        from pipeline.station_registry import BENGALURU_STATIONS
        for config in BENGALURU_STATIONS:
            snap = get_station_snapshot(config.station_id)
            assert snap["station_id"] == config.station_id
            assert snap["station_name"] == config.station_name


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


class TestGetLightgbmExplanationContext:
    def test_persistence_returns_none(self) -> None:
        result = get_lightgbm_explanation_context("cpcb_hebbal")
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
