from __future__ import annotations

import pytest

from backend.app.services.forecast_evidence_service import get_forecast_evidence
from backend.app.services.artifact_adapter import UnknownStationError, UnsupportedCityError


class TestGetForecastEvidence:
    def test_persistence_station(self) -> None:
        result = get_forecast_evidence("cpcb_hebbal")
        assert result["station_id"] == "cpcb_hebbal"
        assert result["forecast_engine"] == "persistence"
        assert result["explanation_method"] == "exact_24h_reference"
        assert result["predicted_pm25"] >= 0
        assert len(result["evidence_items"]) > 0

    def test_lightgbm_station(self) -> None:
        result = get_forecast_evidence("cpcb_peenya")
        assert result["station_id"] == "cpcb_peenya"
        assert result["forecast_engine"] == "lightgbm"
        assert result["explanation_method"] == "model_context_fallback"
        assert len(result["evidence_items"]) > 0

    def test_expected_change_direction(self) -> None:
        result = get_forecast_evidence("cpcb_hebbal")
        assert result["expected_change_direction"] in ("improving", "stable", "worsening", "unavailable")

    def test_risk_category_present(self) -> None:
        result = get_forecast_evidence("cpcb_hebbal")
        assert result["risk_category"] in ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe")

    def test_model_validation_summary(self) -> None:
        result = get_forecast_evidence("cpcb_hebbal")
        assert "Selected engine" in result["model_validation_summary"]

    def test_persistence_wording(self) -> None:
        result = get_forecast_evidence("cpcb_hebbal")
        for item in result["evidence_items"]:
            if item["factor"] == "forecast_engine":
                assert "Persistence was selected" in item["description"]
                assert "outperformed or matched" in item["description"]

    def test_no_causal_overclaim(self) -> None:
        result = get_forecast_evidence("cpcb_hebbal")
        for item in result["evidence_items"]:
            desc = item["description"].lower()
            assert "caused" not in desc
            assert "traffic" not in desc
            assert "industry" not in desc

    def test_caveats_present(self) -> None:
        result = get_forecast_evidence("cpcb_hebbal")
        assert isinstance(result["caveats"], list)

    def test_data_quality_fields(self) -> None:
        result = get_forecast_evidence("cpcb_hebbal")
        assert len(result["data_quality_classification"]) > 0
        assert len(result["data_quality_note"]) > 0

    def test_unknown_station(self) -> None:
        with pytest.raises(UnknownStationError):
            get_forecast_evidence("nonexistent")

    def test_unsupported_city(self) -> None:
        with pytest.raises(UnsupportedCityError):
            get_forecast_evidence("cpcb_hebbal", city="delhi")
