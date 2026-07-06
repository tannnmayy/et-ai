from __future__ import annotations

import pytest

from backend.app.config import ADVISORY_PROFILES, MEDICAL_DISCLAIMER
from backend.app.services.citizen_advisory_service import get_citizen_advisory
from backend.app.services.artifact_adapter import UnknownStationError, UnsupportedCityError


class TestGetCitizenAdvisory:
    def test_general_profile(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal", profile="general", language="en")
        assert result["station_id"] == "cpcb_hebbal"
        assert result["profile"] == "general"
        assert result["language_requested"] == "en"
        assert result["language_served"] == "en"
        assert result["translation_fallback"] is False
        assert len(result["recommendations"]) > 0

    def test_all_risk_categories(self) -> None:
        from backend.app.services.artifact_adapter import list_station_snapshots
        snaps = list_station_snapshots()
        for snap in snaps:
            result = get_citizen_advisory(snap["station_id"])
            assert result["forecast_risk_category"] == snap["risk_category"]

    def test_child_profile(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal", profile="child")
        assert result["profile"] == "child"
        assert any("children" in r.lower() or "school" in r.lower() for r in result["recommendations"])

    def test_elderly_profile(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal", profile="elderly")
        assert result["profile"] == "elderly"
        assert any("older" in r.lower() or "elderly" in r.lower() for r in result["recommendations"])

    def test_respiratory_profile(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal", profile="respiratory")
        assert result["profile"] == "respiratory"
        assert any("respiratory" in r.lower() or "asthma" in r.lower() for r in result["recommendations"])

    def test_outdoor_worker_profile(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal", profile="outdoor_worker")
        assert result["profile"] == "outdoor_worker"
        assert any("outdoor" in r.lower() or "worker" in r.lower() for r in result["recommendations"])

    def test_school_profile(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal", profile="school")
        assert result["profile"] == "school"
        assert any("school" in r.lower() or "sport" in r.lower() for r in result["recommendations"])

    def test_hindi_fallback(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal", language="hi")
        assert result["language_requested"] == "hi"
        assert result["language_served"] == "en"
        assert result["translation_fallback"] is True

    def test_kannada_fallback(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal", language="kn")
        assert result["language_requested"] == "kn"
        assert result["language_served"] == "en"
        assert result["translation_fallback"] is True

    def test_english_served(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal", language="en")
        assert result["language_served"] == "en"
        assert result["translation_fallback"] is False

    def test_medical_disclaimer(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal")
        assert result["medical_disclaimer"] == MEDICAL_DISCLAIMER

    def test_confidence_level_in_response(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal")
        assert result["confidence_level"] in ("High", "Medium", "Low", "Unavailable")

    def test_data_quality_note(self) -> None:
        result = get_citizen_advisory("cpcb_hebbal")
        assert isinstance(result["data_quality_note"], str)

    def test_unknown_station(self) -> None:
        with pytest.raises(UnknownStationError):
            get_citizen_advisory("nonexistent")

    def test_unsupported_city(self) -> None:
        with pytest.raises(UnsupportedCityError):
            get_citizen_advisory("cpcb_hebbal", city="delhi")
