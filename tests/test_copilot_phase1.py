"""Phase 1 Copilot redesign — routing, resolve_location, grounding."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.agents.grounding import check_answer_grounding, extract_answer_numbers
from backend.app.agents.orchestrator import _is_simple_station_query, run_orchestrator
from backend.app.agents.tools import tool_resolve_location


class TestResolveLocation:
    def test_peenya_station_registry(self):
        r = tool_resolve_location(query="Peenya")
        assert r.get("success") is True
        assert r.get("station_id") == "cpcb_peenya"
        assert r.get("h3_cell")
        assert r.get("resolution_method") == "station_registry"

    def test_whitefield_locality(self):
        r = tool_resolve_location(query="near Whitefield area")
        assert r.get("success") is True
        assert r.get("h3_cell")
        assert r.get("latitude") is not None


class TestGrounding:
    def test_numbers_from_tools_pass(self):
        g = check_answer_grounding(
            "PM2.5 is 55 µg/m³ and rank 1",
            {"get_forecast": {"predicted_pm25": 55.2}},
        )
        assert g["passed"] is True

    def test_rounded_percent_matches_fraction(self):
        # tool 0.587 → ~58.7%; model says "approximately 60%"
        g = check_answer_grounding(
            "approximately 60% traffic",
            {"get_attribution": {"source_attribution": {"traffic": 0.587, "construction": 0.3}}},
            max_unverified=0,
        )
        assert g["passed"] is True
        assert "60" in g["verified"]

    def test_invented_large_number_fails(self):
        g = check_answer_grounding(
            "PM2.5 is 999 and score 88.5%",
            {"get_forecast": {"predicted_pm25": 40.0}},
            max_unverified=0,
        )
        assert g["passed"] is False
        assert "999" in g["unverified"] or "88.5" in g["unverified"]

    def test_extract_skips_years(self):
        nums = extract_answer_numbers("In 2024 PM2.5 was 42")
        assert "2024" not in nums
        assert "42" in nums


class TestFastPath:
    def test_simple_forecast_is_fast(self):
        assert _is_simple_station_query("What is the forecast for this station?")

    def test_enforcement_not_fast(self):
        assert not _is_simple_station_query(
            "Where should officers inspect for construction dust today?"
        )

    def test_why_polluted_not_fast(self):
        assert not _is_simple_station_query(
            "Why is air quality poor near Peenya right now?"
        )

    def test_why_alone_not_fast(self):
        assert not _is_simple_station_query("Why is Peenya high?")

    def test_confidence_is_fast(self):
        assert _is_simple_station_query("How reliable is the Peenya forecast confidence?")


class TestOrchestratorNoLlm:
    def test_enforcement_question_uses_tool_agent(self):
        class Fake:
            is_available = False
            last_provider = None
            last_gemini_key_index = None
            last_groq_key_index = None

            def chat_with_tools(self, *a, **k):
                return None

            def summarize(self, *a, **k):
                return None

        with patch(
            "backend.app.agents.grounded_tool_agent.get_llm_provider", return_value=Fake()
        ), patch(
            "backend.app.agents.orchestrator.get_llm_provider", return_value=Fake()
        ):
            out = run_orchestrator(
                query="Where should officers inspect for construction dust today?",
                city="bengaluru",
            )
        assert out["selected_agent"] == "grounded_tool_agent"
        assert out.get("answer")
        assert "could not answer that question specifically" not in out["answer"].lower()
        tools = [t["tool"] for t in out["audit_trail"]["tools_called"]]
        assert "get_enforcement_priority" in tools
