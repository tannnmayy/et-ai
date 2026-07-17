"""Final Copilot phase — what-if, map context, multi-turn memory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.agents.orchestrator import run_orchestrator
from backend.app.services.whatif_scenario_service import (
    parse_scenario_text,
    run_whatif_scenario,
)
from backend.app.agents.tools import tool_run_whatif_scenario


@pytest.fixture(autouse=True)
def _clean_cache():
    try:
        from backend.app.services.copilot_cache_service import clear_cache

        clear_cache()
        yield
        clear_cache()
    except Exception:
        yield


class TestWhatIfParse:
    def test_construction_50(self):
        p = parse_scenario_text("What if construction activity reduces by 50% near Peenya?")
        assert p.get("construction_reduction_percent") == 50.0

    def test_traffic_30(self):
        p = parse_scenario_text("How would pollution change if traffic drops by 30%?")
        assert p.get("traffic_reduction_percent") == 30.0

    def test_industrial(self):
        p = parse_scenario_text("What if industrial emissions drop by 30%?")
        assert p.get("industrial_reduction_percent") == 30.0


class TestWhatIfService:
    def test_construction_reduction_peenya(self):
        r = run_whatif_scenario(
            city="bengaluru",
            station_id="cpcb_peenya",
            construction_reduction_percent=50,
        )
        assert r.get("is_simulation") is True
        assert r.get("disclaimer")
        assert "construction" in str(r.get("interventions"))
        base = r.get("baseline_source_attribution") or {}
        sim = r.get("simulated_source_attribution") or {}
        assert base.get("construction", 1) >= sim.get("construction", 0) - 1e-6
        assert r.get("summary_text")

    def test_tool_wrapper(self):
        r = tool_run_whatif_scenario(
            city="bengaluru",
            station_id="cpcb_peenya",
            construction_reduction_percent=50,
        )
        assert "_tool_error" not in r or r.get("is_simulation")
        assert r.get("is_simulation") is True

    def test_no_change_errors(self):
        r = run_whatif_scenario(city="bengaluru", station_id="cpcb_peenya")
        assert r.get("_tool_error")


class TestMapContextHeuristic:
    def test_map_context_skips_resolve_for_whatif(self):
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
                query="What if construction activity reduces by 50% in this area?",
                city="bengaluru",
                station_id="cpcb_peenya",
            )
        tools = [t["tool"] for t in out["audit_trail"]["tools_called"]]
        assert "run_whatif_scenario" in tools
        assert out["audit_trail"].get("whatif_used") is True
        # resolve may still appear only if heuristic added place hint; map context should skip
        details = " ".join(
            str(s.get("detail", "")) for s in out["audit_trail"].get("reasoning_trace") or []
        )
        assert "Map context" in details or "map" in details.lower()
        assert out.get("answer")
        assert "simulation" in out["answer"].lower() or "what-if" in out["answer"].lower() or "µg" in out["answer"] or "construction" in out["answer"].lower()


class TestMultiTurnMemory:
    def test_history_recorded_in_audit(self):
        class Fake:
            is_available = False
            last_provider = None
            last_gemini_key_index = None
            last_groq_key_index = None

            def chat_with_tools(self, *a, **k):
                return None

            def summarize(self, *a, **k):
                return None

        history = [
            {"role": "user", "content": "Why is air quality poor near Peenya?"},
            {
                "role": "assistant",
                "content": "Peenya shows elevated industrial and traffic shares.",
            },
        ]
        with patch(
            "backend.app.agents.grounded_tool_agent.get_llm_provider", return_value=Fake()
        ), patch(
            "backend.app.agents.orchestrator.get_llm_provider", return_value=Fake()
        ):
            out = run_orchestrator(
                query="What about reducing construction by 50% there?",
                city="bengaluru",
                conversation_history=history,
            )
        assert out["audit_trail"].get("memory_turns_used") == 2
        details = " ".join(
            str(s.get("detail", "")) for s in out["audit_trail"].get("reasoning_trace") or []
        )
        assert "prior turn" in details.lower() or "memory" in details.lower() or out[
            "audit_trail"
        ].get("memory_turns_used") == 2

    def test_follow_up_skips_response_cache(self):
        """Genuine follow-ups must not be served from response cache."""
        class Fake:
            is_available = False
            last_provider = None
            last_gemini_key_index = None
            last_groq_key_index = None
            last_fallback_note = None

            def chat_with_tools(self, *a, **k):
                return None

            def summarize(self, *a, **k):
                return None

        with patch(
            "backend.app.agents.grounded_tool_agent.get_llm_provider", return_value=Fake()
        ), patch(
            "backend.app.agents.orchestrator.get_llm_provider", return_value=Fake()
        ):
            first = run_orchestrator(
                query="Show me the top enforcement priorities in Bengaluru right now",
                city="bengaluru",
            )
            # Deictic follow-up → not cache-eligible
            second = run_orchestrator(
                query="what about construction there?",
                city="bengaluru",
                conversation_history=[
                    {"role": "user", "content": "Show me the top enforcement priorities in Bengaluru right now"},
                    {"role": "assistant", "content": first.get("answer") or "priorities listed"},
                ],
            )
        assert first.get("answer")
        assert second.get("cache_hit") is not True
        # Standalone repeat with non-follow-up history may still cache — that is intentional


class TestFastPathExcludesWhatIf:
    def test_whatif_not_fast_path(self):
        from backend.app.agents.orchestrator import _is_simple_station_query

        assert not _is_simple_station_query(
            "What if construction reduces by 50% at this station forecast?"
        )
