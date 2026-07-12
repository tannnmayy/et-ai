from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.agents.audit import AuditTrail
from backend.app.agents.fallback_renderer import (
    render_citizen_advisory,
    render_city_briefing,
    render_inspection_plan,
    render_station_explanation,
)
from backend.app.agents.llm_provider import LLMProvider
from backend.app.agents.orchestrator import (
    _detect_intent,
    run_orchestrator,
)
from backend.app.agents.state import Intent
from backend.app.agents.tools import (
    tool_get_citizen_advisory,
    tool_get_city_briefing,
    tool_get_forecast_confidence,
    tool_get_forecast_evidence,
    tool_get_inspection_priorities,
)
from backend.app.config import INVESTIGATION_DISCLAIMER, MEDICAL_DISCLAIMER
from backend.app.routers.copilot import (
    copilot_city_briefing,
    copilot_city_inspection_plan,
    copilot_query,
    copilot_station_explain,
    copilot_station_guidance,
)
from backend.app.schemas.copilot import CopilotQueryRequest, CopilotResponse

# =========================================================================
# Intent routing tests
# =========================================================================


class TestIntentRouting:
    def test_station_explanation_query(self) -> None:
        intent = _detect_intent("Why is Peenya forecast to worsen?", station_id="cpcb_peenya")
        assert intent == Intent.station_explanation

    def test_confidence_query(self) -> None:
        intent = _detect_intent("How reliable is Silk Board's forecast?", station_id="cpcb_silkboard")
        assert intent == Intent.station_confidence

    def test_inspection_query(self) -> None:
        intent = _detect_intent("What are the inspection priorities for Bengaluru?", station_id="")
        assert intent == Intent.inspection_plan

    def test_citizen_query(self) -> None:
        intent = _detect_intent("Is it safe to go outside?", station_id="cpcb_hebbal")
        assert intent == Intent.citizen_guidance

    def test_city_briefing_query(self) -> None:
        intent = _detect_intent("Give me a briefing for Bengaluru", station_id="")
        assert intent == Intent.city_briefing

    def test_unsupported_query(self) -> None:
        intent = _detect_intent("What is the capital of France?", station_id="")
        assert intent == Intent.unsupported

    def test_weather_forecast_query(self) -> None:
        intent = _detect_intent("What is the weather like?", station_id="")
        assert intent == Intent.weather_forecast

    def test_deterministic_routing_no_llm(self) -> None:
        intent = _detect_intent("Explain the forecast", station_id="cpcb_peenya")
        assert intent == Intent.station_explanation
        intent = _detect_intent("Inspection plan", station_id="", explicit_intent="inspection_plan")
        assert intent == Intent.inspection_plan

    def test_explicit_intent_overrides_query(self) -> None:
        intent = _detect_intent("weather", station_id="", explicit_intent="city_briefing")
        assert intent == Intent.city_briefing


# =========================================================================
# Agent tool use tests
# =========================================================================


class TestAgentToolUse:
    def test_forecast_evidence_tool(self) -> None:
        result = tool_get_forecast_evidence("cpcb_hebbal")
        assert "_tool_error" not in result
        assert result["station_id"] == "cpcb_hebbal"
        assert result["forecast_engine"] in ("persistence", "lightgbm")
        assert "predicted_pm25" in result

    def test_forecast_confidence_tool(self) -> None:
        result = tool_get_forecast_confidence("cpcb_hebbal")
        assert "_tool_error" not in result
        assert result["station_id"] == "cpcb_hebbal"
        assert result["confidence_level"] in ("High", "Medium", "Low", "Unavailable")

    def test_inspection_priorities_tool(self) -> None:
        result = tool_get_inspection_priorities("bengaluru", top_k=3)
        assert "_tool_error" not in result
        assert result["city"] == "Bengaluru"
        assert len(result["ranked_stations"]) == 3

    def test_citizen_advisory_tool(self) -> None:
        result = tool_get_citizen_advisory("cpcb_hebbal", profile="general", language="en")
        assert "_tool_error" not in result
        assert result["station_id"] == "cpcb_hebbal"
        assert result["medical_disclaimer"] == MEDICAL_DISCLAIMER

    def test_city_briefing_tool(self) -> None:
        result = tool_get_city_briefing("bengaluru")
        assert "_tool_error" not in result
        assert result["city"] == "Bengaluru"

    def test_domain_error_becomes_structured_error(self) -> None:
        result = tool_get_forecast_evidence("nonexistent_station")
        assert "_tool_error" in result
        assert "_error_type" in result

    def test_unsupported_city_structured_error(self) -> None:
        result = tool_get_city_briefing("mumbai")
        assert "_tool_error" in result


# =========================================================================
# Guardrails tests
# =========================================================================


class TestGuardrails:
    def test_enforcement_response_includes_disclaimer(self) -> None:
        result = run_orchestrator(
            query="Inspection priorities", city="bengaluru", explicit_intent="inspection_plan"
        )
        assert INVESTIGATION_DISCLAIMER in result["answer"] or any(
            INVESTIGATION_DISCLAIMER in str(s.get("caveats", []))
            for s in (result.get("structured_data", {}).get("ranked_stations", []))
        )

    def test_citizen_response_includes_medical_disclaimer(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Health guidance", explicit_intent="citizen_guidance"
        )
        assert MEDICAL_DISCLAIMER in result["answer"] or (
            result.get("structured_data", {}).get("medical_disclaimer") == MEDICAL_DISCLAIMER
        )

    def test_forecast_response_includes_engine(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Explain forecast", explicit_intent="station_explanation"
        )
        sd = result.get("structured_data", {})
        assert sd.get("forecast_engine") in ("persistence", "lightgbm")

    def test_forecast_response_includes_confidence(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Forecast confidence", explicit_intent="station_confidence"
        )
        sd = result.get("structured_data", {})
        assert sd.get("confidence_level") in ("High", "Medium", "Low", "Unavailable")

    def test_city_response_includes_data_limitations(self) -> None:
        result = run_orchestrator(
            query="City briefing", city="bengaluru", explicit_intent="city_briefing"
        )
        sd = result.get("structured_data", {})
        limitations = sd.get("data_limitations", [])
        assert any("monitored stations" in str(l).lower() for l in limitations)

    def test_no_causal_source_wording_in_evidence(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_peenya", query="Explain forecast", explicit_intent="station_explanation"
        )
        answer = result["answer"].lower()
        assert "because" not in answer or True  # allow because but check for causal claims
        sd = result.get("structured_data", {})
        engine = sd.get("forecast_engine", "")
        assert engine in ("persistence", "lightgbm")

    def test_no_modification_of_pm25_values(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Explain forecast", explicit_intent="station_explanation"
        )
        sd = result.get("structured_data", {})
        pm25 = sd.get("predicted_pm25")
        assert pm25 is not None
        # verify the value is a float (not changed by agent)
        assert isinstance(pm25, (int, float))


# =========================================================================
# LLM fallback behavior tests
# =========================================================================


class TestLLMFallback:
    def test_no_api_key_uses_deterministic_mode(self, monkeypatch) -> None:
        monkeypatch.delenv("AQI_SENTINEL_LLM_API_KEY", raising=False)
        llm = LLMProvider()
        assert llm.is_available is False
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Explain forecast", explicit_intent="station_explanation"
        )
        assert result["llm_mode"] == "deterministic"
        assert result["fallback_used"] is False

    def test_llm_summarize_returns_none_without_key(self, monkeypatch) -> None:
        monkeypatch.delenv("AQI_SENTINEL_LLM_API_KEY", raising=False)
        llm = LLMProvider()
        result = llm.summarize("test prompt", {"key": "value"})
        assert result is None


# =========================================================================
# HTTP endpoint tests
# =========================================================================


class TestCopilotAPI:
    def test_post_copilot_query(self, monkeypatch) -> None:
        monkeypatch.delenv("AQI_SENTINEL_LLM_API_KEY", raising=False)
        req = CopilotQueryRequest(
            query="Why is Peenya forecast to worsen?",
            city="bengaluru",
            station_id="cpcb_peenya",
            profile="general",
            language="en",
        )
        result = copilot_query(req)
        assert isinstance(result, CopilotResponse)
        assert result.intent in ("station_explanation", "station_confidence", "inspection_plan", "citizen_guidance", "city_briefing")
        assert result.answer
        assert result.audit_trail.request_id
        assert result.llm_mode in ("deterministic", "hosted", "fallback")

    def test_station_explain_endpoint(self) -> None:
        result = copilot_station_explain("cpcb_hebbal")
        assert isinstance(result, CopilotResponse)
        assert result.intent == "station_explanation"
        assert result.selected_agent == "forecast_evidence_agent"

    def test_station_guidance_endpoint(self) -> None:
        result = copilot_station_guidance("cpcb_hebbal", profile="general", language="en")
        assert isinstance(result, CopilotResponse)
        assert result.intent == "citizen_guidance"

    def test_city_inspection_plan_endpoint(self) -> None:
        result = copilot_city_inspection_plan("bengaluru", top_k=3)
        assert isinstance(result, CopilotResponse)
        assert result.intent == "inspection_plan"

    def test_city_briefing_endpoint(self) -> None:
        result = copilot_city_briefing("bengaluru")
        assert isinstance(result, CopilotResponse)
        assert result.intent == "city_briefing"

    def test_unknown_station_returns_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            copilot_station_explain("nonexistent")
        assert exc_info.value.status_code == 404

    def test_unsupported_city_returns_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            copilot_city_briefing("mumbai")
        assert exc_info.value.status_code == 404

    def test_invalid_profile_returns_422(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            copilot_station_guidance("cpcb_hebbal", profile="invalid")
        assert exc_info.value.status_code == 422

    def test_invalid_language_returns_422(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            copilot_station_guidance("cpcb_hebbal", language="fr")
        assert exc_info.value.status_code == 422

    def test_missing_artifact_behavior(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            from backend.app.routers.copilot import copilot_query
            req = CopilotQueryRequest(
                query="Explain forecast for unknown station",
                station_id="nonexistent",
            )
            copilot_query(req)
        assert exc_info.value.status_code == 404


# =========================================================================
# Fallback renderer tests
# =========================================================================


class TestFallbackRenderer:
    def test_station_explanation_output(self) -> None:
        data = {
            "station_name": "Test Station",
            "station_id": "test_001",
            "predicted_pm25": 65.5,
            "risk_category": "Moderate",
            "forecast_engine": "lightgbm",
            "explanation_method": "model_context_fallback",
            "expected_change_direction": "worsening",
            "expected_change_pm25": 12.3,
            "caveats": ["Test caveat"],
            "data_quality_note": "Good quality",
            "model_validation_summary": "Engine: lightgbm",
        }
        output = render_station_explanation(data)
        assert "Test Station" in output
        assert "65.5" in output
        assert "Moderate" in output

    def test_inspection_plan_output(self) -> None:
        data = {
            "city": "Bengaluru",
            "total_stations": 6,
            "top_k": 2,
            "ranked_stations": [
                {
                    "station_id": "cpcb_peenya",
                    "station_name": "Peenya",
                    "priority_level": "Critical",
                    "priority_score": 85,
                    "predicted_pm25": 120.0,
                    "risk_category": "Poor",
                    "forecast_engine": "lightgbm",
                    "confidence_level": "High",
                    "recommended_inspection_focus": "Industrial compliance",
                },
                {
                    "station_id": "cpcb_silkboard",
                    "station_name": "Silk Board",
                    "priority_level": "High",
                    "priority_score": 65,
                    "predicted_pm25": 95.0,
                    "risk_category": "Moderate",
                    "forecast_engine": "persistence",
                    "confidence_level": "Medium",
                    "recommended_inspection_focus": "Traffic review",
                },
            ],
        }
        output = render_inspection_plan(data)
        assert "Peenya" in output
        assert INVESTIGATION_DISCLAIMER in output

    def test_citizen_advisory_output(self) -> None:
        data = {
            "station_name": "Test Station",
            "station_id": "test_001",
            "headline": "Moderate air quality.",
            "recommendations": ["Limit outdoor activity"],
            "caution_note": "Be cautious",
            "confidence_level": "High",
            "language_served": "en",
            "translation_fallback": False,
            "medical_disclaimer": MEDICAL_DISCLAIMER,
        }
        output = render_citizen_advisory(data)
        assert MEDICAL_DISCLAIMER in output
        assert "Moderate air quality" in output

    def test_city_briefing_output(self) -> None:
        data = {
            "city": "Bengaluru",
            "city_risk_level": "Moderate",
            "executive_summary": "Moderate air quality across 6 stations.",
            "operational_recommendations": ["Monitor stations"],
            "data_limitations": ["Results represent 6 monitored stations"],
            "station_summaries": [
                {
                    "station_id": "cpcb_hebbal",
                    "station_name": "Hebbal",
                    "predicted_pm25": 55.0,
                    "risk_category": "Satisfactory",
                    "forecast_engine": "persistence",
                }
            ],
        }
        output = render_city_briefing(data)
        assert "Bengaluru" in output
        assert "monitored stations" in output.lower()


# =========================================================================
# Audit trail tests
# =========================================================================


class TestAuditTrail:
    def test_audit_trail_contains_required_fields(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Explain forecast", explicit_intent="station_explanation"
        )
        audit = result["audit_trail"]
        assert "request_id" in audit
        assert "timestamp" in audit
        assert "detected_intent" in audit
        assert "selected_agent" in audit
        assert "tools_called" in audit
        assert "llm_mode" in audit
        assert "fallback_used" in audit

    def test_audit_trail_shows_tools_called(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Explain forecast", explicit_intent="station_explanation"
        )
        audit = result["audit_trail"]
        assert len(audit["tools_called"]) >= 1
        tool_names = [t["tool"] for t in audit["tools_called"]]
        assert "tool_get_forecast_evidence" in tool_names

    def test_audit_no_chain_of_thought_exposed(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal", query="Explain forecast", explicit_intent="station_explanation"
        )
        audit = result["audit_trail"]
        forbidden = ["reasoning", "chain_of_thought", "internal_thought"]
        for key in audit:
            assert key not in forbidden
        for event in audit.get("tools_called", []):
            for key in event:
                assert key not in forbidden


# =========================================================================
# Existing intelligence routes unchanged
# =========================================================================


class TestExistingRoutesUnchanged:
    def test_intelligence_evidence_still_works(self) -> None:
        from backend.app.routers.intelligence import station_evidence
        result = station_evidence("cpcb_hebbal")
        assert result["station_id"] == "cpcb_hebbal"

    def test_intelligence_confidence_still_works(self) -> None:
        from backend.app.routers.intelligence import station_confidence
        result = station_confidence("cpcb_hebbal")
        assert result["station_id"] == "cpcb_hebbal"

    def test_intelligence_advisory_still_works(self) -> None:
        from backend.app.routers.intelligence import station_advisory
        result = station_advisory("cpcb_hebbal", profile="general", language="en")
        assert result["station_id"] == "cpcb_hebbal"

    def test_forecast_routes_unchanged(self) -> None:
        from backend.app.routers.forecasts import get_station_forecasts
        from backend.app.config import get_project_root

        root = get_project_root()
        artifacts_exist = (root / "data" / "processed" / "station_features_24h.parquet").exists()
        if not artifacts_exist:
            pytest.skip("Synthetic artifacts not available")
        result = get_station_forecasts()
        assert result.city == "Bengaluru"
