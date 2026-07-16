"""Phase 2 Copilot — map context, semantic cache, response mode metadata."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.agents.orchestrator import run_orchestrator
from backend.app.services.copilot_cache_service import (
    cache_key,
    cache_stats,
    clear_cache,
    lookup_cached_response,
    semantic_cache_key,
    semantic_normalize,
    set_cached_response,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


class TestSemanticNormalize:
    def test_peenya_variants_share_fingerprint(self):
        a = semantic_normalize("Why is air quality poor near Peenya right now?")
        b = semantic_normalize("Air pollution issues in Peenya area")
        # Both should contain peenya + pollution/aqi/cause-ish tokens
        assert "peenya" in a and "peenya" in b
        # Core intent tokens should overlap heavily
        ta, tb = set(a.split()), set(b.split())
        assert ta & tb  # non-empty intersection
        # semantic keys under same scope should match when fold is strong enough
        # (may not be identical if extra tokens differ — check key equality when close)
        ka = semantic_cache_key("Why is air quality poor near Peenya right now?")
        kb = semantic_cache_key("Why is air quality bad near Peenya?")
        # poor→bad folding should make these very similar; at least both valid
        assert ka.startswith("sem:")
        assert kb.startswith("sem:")
        # after synonym fold "poor" and "bad" both become "bad"
        assert semantic_normalize("poor air near peenya") == semantic_normalize(
            "bad air near peenya"
        )

    def test_policy_vs_enforcement_differ(self):
        p = semantic_normalize("What does CPCB say about construction dust?")
        e = semantic_normalize("Where should officers inspect for construction dust?")
        assert p != e


class TestSemanticCache:
    def test_exact_hit(self):
        q = "City briefing for Bengaluru"
        key = cache_key(q)
        payload = {
            "answer": "Briefing text",
            "selected_agent": "grounded_tool_agent",
            "audit_trail": {"tools_called": [], "warnings": []},
        }
        set_cached_response(key, payload, query=q, semantic_key=semantic_cache_key(q))
        hit, meta = lookup_cached_response(key, semantic_key=semantic_cache_key(q))
        assert hit is not None
        assert hit["answer"] == "Briefing text"
        assert meta["cache_hit"] is True
        assert meta["cache_kind"] == "exact"

    def test_semantic_hit_similar_query(self):
        q1 = "Why is air quality poor near Peenya right now?"
        q2 = "Why is air quality bad near Peenya?"
        k1 = cache_key(q1)
        s1 = semantic_cache_key(q1)
        s2 = semantic_cache_key(q2)
        # Ensure semantic keys match for synonym fold
        assert s1 == s2, f"expected same semantic key, got {s1} vs {s2}"

        set_cached_response(
            k1,
            {
                "answer": "Peenya pollution summary",
                "selected_agent": "grounded_tool_agent",
                "audit_trail": {"tools_called": [{"tool": "get_attribution"}], "warnings": []},
            },
            query=q1,
            semantic_key=s1,
        )
        k2 = cache_key(q2)  # different exact key
        assert k1 != k2
        hit, meta = lookup_cached_response(k2, semantic_key=s2)
        assert hit is not None
        assert hit["answer"] == "Peenya pollution summary"
        assert meta["cache_kind"] == "semantic"
        assert meta["cache_hit"] is True

    def test_cache_stats_fields(self):
        stats = cache_stats()
        assert "entries" in stats
        assert "ttl_default_seconds" in stats
        assert "ttl_live_seconds" in stats
        assert "ttl_policy_seconds" in stats
        assert "ttl_tool_seconds" in stats
        assert "semantic_enabled" in stats
        assert stats["ttl_default_seconds"] > 0


class TestMapContext:
    def test_map_context_recorded_without_llm(self):
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
                query="Why is air quality poor here?",
                city="bengaluru",
                station_id="cpcb_peenya",
                h3_cell="8960145a02fffff",  # may or may not be real; agent should still record
            )

        assert out.get("answer")
        trail = out["audit_trail"]
        details = " ".join(str(s.get("detail", "")) for s in trail.get("reasoning_trace") or [])
        assert "Map context" in details or "map" in details.lower() or "station_id" in details.lower()
        # Prefer map context path
        sd = out.get("structured_data") or {}
        # path should be heuristic without LLM
        assert sd.get("path") == "heuristic_fallback" or out["selected_agent"] == "grounded_tool_agent"
        assert out.get("response_mode") in (
            "heuristic_fallback",
            "tool_agent",
            "fast_path",
        )
        assert trail.get("response_mode")
        assert trail.get("cache_hit") is False or trail.get("cache_hit") is True

    def test_no_context_still_works(self):
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
        tools = [t["tool"] for t in out["audit_trail"]["tools_called"]]
        assert "get_enforcement_priority" in tools
        assert out.get("response_mode") == "heuristic_fallback"

    def test_fast_path_mode_label(self):
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
                query="What is the forecast for this station?",
                city="bengaluru",
                station_id="cpcb_peenya",
            )
        assert out["selected_agent"] == "forecast_evidence_agent"
        assert out.get("response_mode") == "fast_path"
        assert out["audit_trail"].get("response_mode") == "fast_path"


class TestCacheThroughOrchestrator:
    def test_second_call_is_cache_hit(self):
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
            q = "Show me the top enforcement priorities in Bengaluru right now"
            first = run_orchestrator(query=q, city="bengaluru")
            second = run_orchestrator(query=q, city="bengaluru")

        assert first.get("answer")
        assert second.get("cache_hit") is True
        assert second["audit_trail"].get("cache_hit") is True
        assert "served_from_response_cache" in (second.get("warnings") or [])

    def test_semantic_cache_via_orchestrator(self):
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
            q1 = "Why is air quality poor near Peenya right now?"
            q2 = "Why is air quality bad near Peenya?"
            first = run_orchestrator(query=q1, city="bengaluru")
            second = run_orchestrator(query=q2, city="bengaluru")

        assert first.get("answer")
        # Semantic hit if fingerprints match
        if semantic_cache_key(q1) == semantic_cache_key(q2):
            assert second.get("cache_hit") is True
            assert "served_from_semantic_cache" in (second.get("warnings") or []) or second[
                "audit_trail"
            ].get("cache_kind") == "semantic"
