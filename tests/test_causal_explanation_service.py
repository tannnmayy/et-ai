from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.services.causal_explanation_service import generate_causal_explanation


class TestGenerateCausalExplanation:
    _SAMPLE_ATTRIBUTION = {
        "h3_cell": "8fff99999999999",
        "source_attribution": {
            "traffic": 0.45,
            "industrial": 0.30,
            "construction": 0.15,
            "burning": 0.10,
        },
        "method": "wind_weighted",
        "wind_used": {
            "direction_deg": 180,
            "speed_kmh": 12.5,
            "retrieved_at": "2025-06-01T10:00:00Z",
        },
        "source_hexagons_contributing": 8,
        "max_distance_m": 4500.0,
        "fused_pm25": 85.3,
        "baseline_pm25": 40.0,
        "residual_correction": -2.1,
        "stations_contributing": 3,
        "nearest_station_id": "cpcb_hebbal",
        "nearest_station_distance_m": 1200.0,
        "city": "bengaluru",
    }

    def test_deterministic_english(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_get.return_value.is_available = False
            result = generate_causal_explanation(self._SAMPLE_ATTRIBUTION, language="en")
            assert result["language"] == "en"
            assert result["generated_by"] == "template"
            assert result["wind_method"] == "wind_weighted"
            assert "traffic" in result["explanation"].lower()
            assert "45%" in result["explanation"] or "45" in result["explanation"]

    def test_deterministic_hindi(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_get.return_value.is_available = False
            result = generate_causal_explanation(self._SAMPLE_ATTRIBUTION, language="hi")
            assert result["language"] == "hi"
            assert result["generated_by"] == "template"

    def test_deterministic_kannada(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_get.return_value.is_available = False
            result = generate_causal_explanation(self._SAMPLE_ATTRIBUTION, language="kn")
            assert result["language"] == "kn"
            assert result["generated_by"] == "template"

    def test_fallback_to_english_for_unsupported_language(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_get.return_value.is_available = False
            result = generate_causal_explanation(self._SAMPLE_ATTRIBUTION, language="fr")
            assert result["language"] == "en"

    def test_calm_method(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_get.return_value.is_available = False
            attr = {**self._SAMPLE_ATTRIBUTION, "method": "calm_fallback"}
            result = generate_causal_explanation(attr)
            assert result["wind_method"] == "calm_fallback"

    def test_llm_generation_when_available(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_llm = mock_get.return_value
            mock_llm.is_available = True
            mock_llm.summarize.return_value = (
                "Traffic is the dominant source at this location, contributing 45% of PM2.5. "
                "Industrial activity adds 30%, with construction and burning making up the rest. "
                "Winds from the south at 12.5 km/h carry emissions from nearby areas."
            )
            result = generate_causal_explanation(self._SAMPLE_ATTRIBUTION, language="en")
            assert result["generated_by"] == "llm"
            assert "traffic" in result["explanation"].lower()
            mock_llm.summarize.assert_called_once()

    def test_llm_uses_causal_explanation_system_prompt(self) -> None:
        from backend.app.agents.llm_provider import (
            _CAUSAL_EXPLANATION_SYSTEM_PROMPT,
            _SUMMARIZER_SYSTEM_PROMPT,
            _PLANNING_SYSTEM_PROMPT,
        )

        call_records: list[dict] = []

        def mock_call_llm(prompt, structured_data, system_prompt=None):
            call_records.append({"system_prompt": system_prompt})
            return "Mocked causal explanation."

        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            llm = mock_get.return_value
            llm.is_available = True
            with patch.object(llm, "_call_llm", side_effect=mock_call_llm):
                generate_causal_explanation(self._SAMPLE_ATTRIBUTION, language="en")

        assert len(call_records) == 1
        sp = call_records[0]["system_prompt"]
        assert sp is not None
        assert sp == _CAUSAL_EXPLANATION_SYSTEM_PROMPT
        assert sp != _SUMMARIZER_SYSTEM_PROMPT
        assert sp != _PLANNING_SYSTEM_PROMPT

    def test_llm_fallback_on_empty_response(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_llm = mock_get.return_value
            mock_llm.is_available = True
            mock_llm.summarize.return_value = None
            result = generate_causal_explanation(self._SAMPLE_ATTRIBUTION, language="en")
            assert result["generated_by"] == "template"

    def test_empty_source_attribution(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_get.return_value.is_available = False
            attr = {**self._SAMPLE_ATTRIBUTION, "source_attribution": {}}
            result = generate_causal_explanation(attr)
            assert result["generated_by"] == "template"

    def test_missing_fused_pm25(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_get.return_value.is_available = False
            attr = {**self._SAMPLE_ATTRIBUTION, "fused_pm25": None}
            result = generate_causal_explanation(attr)
            assert result["generated_by"] == "template"

    def test_no_wind_data(self) -> None:
        with patch(
            "backend.app.services.causal_explanation_service.get_llm_provider"
        ) as mock_get:
            mock_get.return_value.is_available = False
            attr = {**self._SAMPLE_ATTRIBUTION, "wind_used": {}}
            result = generate_causal_explanation(attr)
            assert result["generated_by"] == "template"
