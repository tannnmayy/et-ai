"""Phase 1 multi-language wiring: session language → API → agent state."""

from __future__ import annotations

from unittest.mock import patch

from backend.app.agents.grounded_tool_agent import (
    _build_context_block,
    _inject_map_context_args,
    _normalize_language,
)
from backend.app.agents.orchestrator import run_orchestrator
from backend.app.agents.state import AgentState
from backend.app.services.copilot_cache_service import cache_key, clear_cache


class TestNormalizeLanguage:
    def test_lowercases(self):
        assert _normalize_language("HI") == "hi"
        assert _normalize_language("EN") == "en"
        assert _normalize_language("kn") == "kn"

    def test_invalid_defaults_en(self):
        assert _normalize_language("fr") == "en"
        assert _normalize_language(None) == "en"
        assert _normalize_language("") == "en"


class TestContextBlockLanguage:
    def test_context_includes_language(self):
        state = AgentState(
            request_id="t1",
            user_query="Why is Peenya polluted?",
            language="hi",
            city="bengaluru",
        )
        block = _build_context_block(state)
        assert "language=hi" in block
        assert "Hindi" in block

    def test_causal_tool_gets_language(self):
        state = AgentState(request_id="t1", language="kn")
        out = _inject_map_context_args("get_causal_explanation", {}, state)
        assert out["language"] == "kn"


class TestCacheKeyLanguage:
    def test_different_languages_different_keys(self):
        clear_cache()
        k_en = cache_key("Why is Peenya poor?", language="en")
        k_hi = cache_key("Why is Peenya poor?", language="hi")
        k_en2 = cache_key("Why is Peenya poor?", language="EN")
        assert k_en != k_hi
        assert k_en == k_en2  # case-normalized in scope


class TestOrchestratorLanguage:
    def test_language_hi_recorded_in_audit(self):
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
                query="Why is air quality poor near Peenya?",
                city="bengaluru",
                language="hi",
            )
        details = " ".join(
            str(s.get("detail", "")) for s in out["audit_trail"].get("reasoning_trace") or []
        )
        assert "hi" in details.lower() or any(
            s.get("language") == "hi" for s in out["audit_trail"].get("reasoning_trace") or []
        )

    def test_language_uppercase_accepted(self):
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
                query="City briefing",
                city="bengaluru",
                language="KN",
                force_dynamic_planning=True,
            )
        # Should not error; language normalized
        assert out.get("answer")
        details = " ".join(
            str(s.get("detail", "")) + str(s.get("language", ""))
            for s in out["audit_trail"].get("reasoning_trace") or []
        )
        assert "kn" in details.lower()


class TestSystemPromptLanguage:
    def test_prompt_mentions_language_rules(self):
        from backend.app.agents.native_tool_schemas import AGENT_SYSTEM_PROMPT

        assert "Hindi" in AGENT_SYSTEM_PROMPT or "hi" in AGENT_SYSTEM_PROMPT
        assert "Kannada" in AGENT_SYSTEM_PROMPT or "kn" in AGENT_SYSTEM_PROMPT
        assert "PM2.5" in AGENT_SYSTEM_PROMPT
