from __future__ import annotations

from backend.app.agents.fallback_renderer import (
    render_neighbourhood_comparison,
    render_spatial_intelligence,
)
from backend.app.agents.orchestrator import _detect_intent, run_orchestrator
from backend.app.agents.state import Intent
from backend.app.agents.tools import (
    tool_compare_neighbourhoods,
    tool_get_location_intelligence,
    tool_get_station_intelligence,
    tool_resolve_location,
)


class TestNewIntents:
    def test_spatial_intelligence_intent_exists(self) -> None:
        assert hasattr(Intent, "spatial_intelligence")
        assert Intent.spatial_intelligence.value == "spatial_intelligence"

    def test_neighbourhood_comparison_intent_exists(self) -> None:
        assert hasattr(Intent, "neighbourhood_comparison")
        assert Intent.neighbourhood_comparison.value == "neighbourhood_comparison"

    def test_detect_spatial_intelligence_keywords(self) -> None:
        intent = _detect_intent("spatial intelligence around Peenya", station_id="cpcb_peenya")
        assert intent == Intent.spatial_intelligence

    def test_detect_neighbourhood_comparison_keywords(self) -> None:
        intent = _detect_intent("compare Jayanagar and HSR Layout for a family", station_id="")
        assert intent == Intent.neighbourhood_comparison

    def test_explicit_intent_spatial_intelligence(self) -> None:
        intent = _detect_intent("some query", explicit_intent="spatial_intelligence")
        assert intent == Intent.spatial_intelligence

    def test_explicit_intent_neighbourhood_comparison(self) -> None:
        intent = _detect_intent("some query", explicit_intent="neighbourhood_comparison")
        assert intent == Intent.neighbourhood_comparison


class TestNewTools:
    def test_resolve_location_tool(self) -> None:
        result = tool_resolve_location(latitude=12.97, longitude=77.59)
        assert result["success"] is True

    def test_station_intelligence_tool(self) -> None:
        result = tool_get_station_intelligence("cpcb_hebbal")
        assert result["station_id"] == "cpcb_hebbal"

    def test_location_intelligence_tool(self) -> None:
        result = tool_get_location_intelligence(latitude=12.97, longitude=77.59)
        assert result["resolution_method"] == "direct_coordinates"

    def test_compare_neighbourhoods_tool(self) -> None:
        candidates = [{"query": "Jayanagar"}]
        workplace = {"query": "MG Road"}
        result = tool_compare_neighbourhoods(
            candidate_queries=candidates,
            workplace_query=workplace,
        )
        assert "candidates" in result
        assert "disclaimer" in result


class TestFallbackRenderer:
    def test_render_spatial_intelligence(self) -> None:
        data = {
            "station_id": "cpcb_hebbal",
            "forecast_evidence": {
                "predicted_pm25": 55.5,
                "risk_category": "Moderate",
                "forecast_engine": "lightgbm",
            },
            "forecast_confidence": {
                "confidence_level": "High",
                "confidence_score": 85,
            },
            "limitations": ["Test disclaimer"],
        }
        output = render_spatial_intelligence(data)
        assert "cpcb_hebbal" in output
        assert "55.5" in output
        assert "High" in output

    def test_render_neighbourhood_comparison(self) -> None:
        data = {
            "candidates": [
                {
                    "candidate_label": "Jayanagar",
                    "overall_score": 0.75,
                    "partial_assessment": False,
                },
                {
                    "candidate_label": "HSR Layout",
                    "overall_score": 0.65,
                    "partial_assessment": False,
                },
            ],
            "ranking": [0, 1],
        }
        output = render_neighbourhood_comparison(data)
        assert "Jayanagar" in output
        assert "HSR Layout" in output
        assert "0.75" in output

    def test_render_empty_candidates(self) -> None:
        output = render_neighbourhood_comparison({"candidates": [], "ranking": None})
        assert "No candidate areas" in output


class TestCopilotRouting:
    def test_spatial_intelligence_routes_to_correct_agent(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal",
            query="spatial intelligence around this station",
            explicit_intent="spatial_intelligence",
        )
        assert result["selected_agent"] == "spatial_intelligence_agent"
        assert result["intent"] == "spatial_intelligence"

    def test_neighbourhood_comparison_routes_to_correct_agent(self) -> None:
        result = run_orchestrator(
            query="compare Jayanagar and HSR for a family",
            explicit_intent="neighbourhood_comparison",
        )
        assert result["selected_agent"] == "neighbourhood_decision_agent"
        assert result["intent"] == "neighbourhood_comparison"

    def test_spatial_intelligence_fallback_renderer(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal",
            query="spatial intelligence",
            explicit_intent="spatial_intelligence",
        )
        assert result["answer"] is not None
        assert len(result["answer"]) > 0

    def test_audit_trail_contains_new_intents(self) -> None:
        result = run_orchestrator(
            station_id="cpcb_hebbal",
            query="spatial intelligence",
            explicit_intent="spatial_intelligence",
        )
        audit = result["audit_trail"]
        assert audit["detected_intent"] == "spatial_intelligence"
