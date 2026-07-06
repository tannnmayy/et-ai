from __future__ import annotations

import pytest

from backend.app.services.confidence_service import get_forecast_confidence
from backend.app.services.artifact_adapter import UnknownStationError, UnsupportedCityError


class TestGetForecastConfidence:
    def test_returns_valid_structure(self) -> None:
        result = get_forecast_confidence("cpcb_hebbal")
        assert result["station_id"] == "cpcb_hebbal"
        assert result["confidence_level"] in ("High", "Medium", "Low", "Unavailable")
        assert isinstance(result["reasons"], list)
        assert isinstance(result["blockers"], list)

    def test_no_persistence_penalty(self) -> None:
        result_p = get_forecast_confidence("cpcb_hebbal")
        result_l = get_forecast_confidence("cpcb_peenya")
        for r in [result_p, result_l]:
            for reason in r["reasons"]:
                assert "persistence" not in reason.lower()

    def test_score_range(self) -> None:
        result = get_forecast_confidence("cpcb_hebbal")
        if result["confidence_score"] is not None:
            assert 0 <= result["confidence_score"] <= 100

    def test_level_matches_score(self) -> None:
        result = get_forecast_confidence("cpcb_hebbal")
        score = result["confidence_score"]
        level = result["confidence_level"]
        if level == "High":
            assert score is not None and score >= 80
        elif level == "Medium":
            assert score is not None and 55 <= score < 80
        elif level == "Low":
            assert score is not None and 25 <= score < 55
        else:
            assert score is None

    def test_has_quality_classification(self) -> None:
        result = get_forecast_confidence("cpcb_hebbal")
        assert len(result["quality_classification"]) > 0

    def test_has_selected_engine(self) -> None:
        result = get_forecast_confidence("cpcb_hebbal")
        assert result["selected_engine"] in ("persistence", "lightgbm")

    def test_observation_age_computed(self) -> None:
        result = get_forecast_confidence("cpcb_hebbal")
        assert result["latest_observation_age_hours"] is not None
        assert result["latest_observation_age_hours"] >= 0

    def test_completeness_computed(self) -> None:
        result = get_forecast_confidence("cpcb_hebbal")
        assert result["recent_pm25_completeness_percent"] is not None
        assert 0 <= result["recent_pm25_completeness_percent"] <= 100

    def test_unknown_station(self) -> None:
        with pytest.raises(UnknownStationError):
            get_forecast_confidence("nonexistent")

    def test_unsupported_city(self) -> None:
        with pytest.raises(UnsupportedCityError):
            get_forecast_confidence("cpcb_hebbal", city="delhi")
