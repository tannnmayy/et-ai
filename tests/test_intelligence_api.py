from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.config import INVESTIGATION_DISCLAIMER
from backend.app.routers.intelligence import (
    station_evidence,
    station_confidence,
    station_advisory,
    city_inspection_priorities,
    city_briefing,
    bengaluru_inspection_priorities,
    bengaluru_city_briefing,
)


class TestStationEvidenceEndpoint:
    def test_valid_station(self) -> None:
        result = station_evidence("cpcb_hebbal")
        assert isinstance(result, dict)
        assert result["station_id"] == "cpcb_hebbal"
        assert result["explanation_method"] in ("exact_24h_reference", "model_context_fallback")

    def test_unknown_station_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            station_evidence("nonexistent")
        assert exc_info.value.status_code == 404


class TestStationConfidenceEndpoint:
    def test_valid_station(self) -> None:
        result = station_confidence("cpcb_hebbal")
        assert isinstance(result, dict)
        assert result["station_id"] == "cpcb_hebbal"
        assert result["confidence_level"] in ("High", "Medium", "Low", "Unavailable")

    def test_unknown_station_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            station_confidence("nonexistent")
        assert exc_info.value.status_code == 404


class TestStationAdvisoryEndpoint:
    def test_valid_station(self) -> None:
        result = station_advisory("cpcb_hebbal", profile="general", language="en")
        assert isinstance(result, dict)
        assert result["station_id"] == "cpcb_hebbal"
        assert result["profile"] == "general"

    def test_invalid_profile_raises_422(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            station_advisory("cpcb_hebbal", profile="invalid")
        assert exc_info.value.status_code == 422

    def test_invalid_language_raises_422(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            station_advisory("cpcb_hebbal", language="fr")
        assert exc_info.value.status_code == 422


class TestCityInspectionPrioritiesEndpoint:
    def test_valid_city(self) -> None:
        result = city_inspection_priorities("bengaluru", top_k=3)
        assert isinstance(result, dict)
        assert result["city"] == "Bengaluru"
        assert len(result["ranked_stations"]) == 3

    def test_all_stations_have_disclaimer(self) -> None:
        result = city_inspection_priorities("bengaluru", top_k=6)
        for s in result["ranked_stations"]:
            assert INVESTIGATION_DISCLAIMER in s["investigation_disclaimer"]


class TestCityBriefingEndpoint:
    def test_valid_city(self) -> None:
        result = city_briefing("bengaluru")
        assert isinstance(result, dict)
        assert result["city"] == "Bengaluru"


class TestConvenienceAliases:
    def test_bengaluru_inspection_priorities(self) -> None:
        result = bengaluru_inspection_priorities(top_k=3)
        assert result["city"] == "Bengaluru"
        assert len(result["ranked_stations"]) == 3

    def test_bengaluru_city_briefing(self) -> None:
        result = bengaluru_city_briefing()
        assert result["city"] == "Bengaluru"
