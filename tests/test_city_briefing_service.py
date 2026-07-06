from __future__ import annotations

import pytest

from backend.app.services.city_briefing_service import get_city_briefing
from backend.app.services.artifact_adapter import UnsupportedCityError


class TestGetCityBriefing:
    def test_bengaluru_briefing(self) -> None:
        result = get_city_briefing("bengaluru")
        assert result["city"] == "Bengaluru"
        assert result["stations_with_forecasts"] == 6
        assert result["city_risk_level"] in ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe", "Unavailable")

    def test_stations_by_risk_category(self) -> None:
        result = get_city_briefing("bengaluru")
        by_risk = result["stations_by_risk_category"]
        assert isinstance(by_risk, dict)
        total = sum(len(v) for v in by_risk.values())
        assert total == 6

    def test_stations_by_confidence_level(self) -> None:
        result = get_city_briefing("bengaluru")
        by_conf = result["stations_by_confidence_level"]
        assert isinstance(by_conf, dict)
        total = sum(len(v) for v in by_conf.values())
        assert total == 6

    def test_engine_counts(self) -> None:
        result = get_city_briefing("bengaluru")
        total = result["lightgbm_selected_count"] + result["persistence_selected_count"]
        assert total == 6

    def test_top_priorities(self) -> None:
        result = get_city_briefing("bengaluru")
        assert isinstance(result["top_priorities"], list)
        assert len(result["top_priorities"]) > 0

    def test_executive_summary(self) -> None:
        result = get_city_briefing("bengaluru")
        assert len(result["executive_summary"]) > 0

    def test_operational_recommendations(self) -> None:
        result = get_city_briefing("bengaluru")
        assert isinstance(result["operational_recommendations"], list)
        assert len(result["operational_recommendations"]) > 0

    def test_data_limitations(self) -> None:
        result = get_city_briefing("bengaluru")
        assert isinstance(result["data_limitations"], list)
        assert any("coverage" in lim.lower() for lim in result["data_limitations"])

    def test_station_summaries(self) -> None:
        result = get_city_briefing("bengaluru")
        assert len(result["station_summaries"]) == 6
        for s in result["station_summaries"]:
            assert "station_id" in s
            assert "risk_category" in s
            assert "confidence_level" in s

    def test_unsupported_city(self) -> None:
        with pytest.raises(UnsupportedCityError):
            get_city_briefing("delhi")

    def test_low_confidence_stations_in_limitations(self) -> None:
        result = get_city_briefing("bengaluru")
        low_conf_stations = result["stations_by_confidence_level"].get("Low", []) + \
            result["stations_by_confidence_level"].get("Unavailable", [])
        if low_conf_stations:
            assert any("low" in lim.lower() or "unavailable" in lim.lower() for lim in result["data_limitations"])
