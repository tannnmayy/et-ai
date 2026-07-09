from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.agents.audit import AuditTrail
from backend.app.agents.dynamic_planning_agent import (
    MAX_PLANNING_STEPS,
    run_dynamic_planning_agent,
)
from backend.app.agents.llm_provider import LLMProvider
from backend.app.agents.orchestrator import (
    _detect_intent,
    _is_compound_query,
    run_orchestrator,
)
from backend.app.agents.state import AgentState, Intent
from backend.app.agents.tools import (
    tool_get_attribution,
    tool_get_enforcement_priority,
)


# =========================================================================
# _is_compound_query tests
# =========================================================================


class TestCompoundQuery:
    def test_single_intent_not_compound(self) -> None:
        assert _is_compound_query("why is Whitefield bad") is False

    def test_two_intents_is_compound(self) -> None:
        assert _is_compound_query("why is Whitefield bad and what are the inspection priorities") is True

    def test_weather_and_travel_compound(self) -> None:
        assert _is_compound_query("is it going to rain and should I travel today") is True

    def test_empty_query_not_compound(self) -> None:
        assert _is_compound_query("") is False

    def test_policy_and_briefing_compound(self) -> None:
        assert _is_compound_query("what does CPCB say about bengaluru air quality overview") is True

    def test_gibberish_not_compound(self) -> None:
        assert _is_compound_query("asdf qwerty zxcvbnm") is False

    def test_explain_and_enforce_compound(self) -> None:
        assert _is_compound_query("explain why enforcement is needed at Peenya") is True


# =========================================================================
# tool_get_attribution tests
# =========================================================================


class TestAttributionTool:
    def test_valid_city_grid_attribution(self) -> None:
        result = tool_get_attribution(city="bengaluru", include_fusion=False)
        assert "_tool_error" not in result
        assert result.get("city") == "bengaluru"
        assert "hexagon_count" in result
        assert "hexagons" in result

    def test_unsupported_city_attribution(self) -> None:
        result = tool_get_attribution(city="mumbai", include_fusion=False)
        assert "_tool_error" in result

    def test_h3_cell_attribution(self) -> None:
        result = tool_get_attribution(city="bengaluru", h3_cell="89c98a4254fffff", include_fusion=False)
        assert "_tool_error" not in result or "error" in result
        if "_tool_error" not in result:
            assert "source_attribution" in result

    def test_lat_lng_attribution(self) -> None:
        result = tool_get_attribution(city="bengaluru", lat=12.9716, lon=77.5946, include_fusion=False)
        assert "_tool_error" not in result or "error" in result
        if "_tool_error" not in result:
            assert "h3_cell" in result

    def test_unknown_hexagon_returns_empty(self) -> None:
        result = tool_get_attribution(city="bengaluru", h3_cell="INVALID_CELL_LONG", include_fusion=False)
        attr = result.get("source_attribution", {})
        assert attr.get("traffic") == 0.0
        assert attr.get("industrial") == 0.0
        assert attr.get("construction") == 0.0
        assert attr.get("burning") == 0.0


# =========================================================================
# tool_get_enforcement_priority tests
# =========================================================================


class TestEnforcementPriorityTool:
    def test_valid_city_enforcement(self) -> None:
        result = tool_get_enforcement_priority(city="bengaluru", top_k=3)
        assert "_tool_error" not in result
        assert "ranked_hexagons" in result
        assert "total_hexagons" in result

    def test_unsupported_city_enforcement(self) -> None:
        result = tool_get_enforcement_priority(city="mumbai", top_k=3)
        assert "_tool_error" in result


# =========================================================================
# plan_next_step tests
# =========================================================================


class MockLLM:
    def __init__(self, responses: list[str], available: bool = True):
        self.responses = responses
        self.index = 0
        self._available = available

    @property
    def is_available(self) -> bool:
        return self._available

    def plan_next_step(self, query: str, tool_schemas: dict, tool_results_so_far: dict, step_number: int, max_steps: int) -> dict | None:
        if self.index >= len(self.responses):
            return None
        import json
        raw = self.responses[self.index]
        self.index += 1
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def summarize(self, prompt: str, structured_data: dict) -> str | None:
        return "LLM summary of gathered data."


def _make_fake_tool_registry() -> dict:
    def fake_tool(**kwargs) -> dict:
        return {"result": "ok", **kwargs}
    from backend.app.agents import tool_registry as tr
    return {name: fake_tool for name in tr.PLANNING_TOOL_REGISTRY}


class TestPlanNextStep:
    def test_plan_next_step_uses_planning_system_prompt(self) -> None:
        from backend.app.agents.llm_provider import _SUMMARIZER_SYSTEM_PROMPT
        llm = LLMProvider()
        call_records: list[dict] = []

        def mock_call_llm(prompt, structured_data, system_prompt=None):
            call_records.append({"prompt": prompt, "system_prompt": system_prompt})
            return '{"action": "final_answer", "text": "Paris."}'

        with patch.object(llm, "_available", True):
            with patch.object(llm, "_call_llm", side_effect=mock_call_llm):
                result = llm.plan_next_step(
                    query="What is the capital of France?",
                    tool_schemas={"tool_get_city_briefing": {"description": "Get city briefing", "parameters": {}}},
                    tool_results_so_far={},
                    step_number=1,
                    max_steps=5,
                )

        assert result == {"action": "final_answer", "text": "Paris."}
        assert len(call_records) == 1
        sp = call_records[0]["system_prompt"]
        assert sp is not None
        assert sp != _SUMMARIZER_SYSTEM_PROMPT
        assert "tool" in sp.lower()
    def test_dynamic_planning_agent_executes_sequence(self) -> None:
        mock = MockLLM([
            '{"action": "call_tool", "tool": "tool_get_forecast_evidence", "arguments": {"station_id": "cpcb_peenya"}}',
            '{"action": "call_tool", "tool": "tool_get_geospatial_context", "arguments": {"station_id": "cpcb_peenya"}}',
            '{"action": "call_tool", "tool": "tool_get_attribution", "arguments": {"city": "bengaluru", "h3_cell": "89c8a4254abffff"}}',
            '{"action": "call_tool", "tool": "tool_get_enforcement_priority", "arguments": {"city": "bengaluru", "top_k": 5}}',
            '{"action": "final_answer", "text": "Based on the evidence and enforcement priorities, Peenya needs immediate attention."}',
        ])
        state = AgentState(
            request_id="test-dynamic-001",
            user_query="why is Whitefield bad and what are the inspection priorities",
            city="bengaluru",
            station_id="",
        )
        audit = AuditTrail("test-dynamic-001")
        fake_reg = _make_fake_tool_registry()

        with patch("backend.app.agents.dynamic_planning_agent.get_llm_provider", return_value=mock):
            with patch("backend.app.agents.dynamic_planning_agent.PLANNING_TOOL_REGISTRY", fake_reg):
                run_dynamic_planning_agent(state, audit)

        assert state.response == "Based on the evidence and enforcement priorities, Peenya needs immediate attention."
        tool_names = [t["tool"] for t in audit.tools_called]
        assert "tool_get_forecast_evidence" in tool_names
        assert "tool_get_geospatial_context" in tool_names
        assert "tool_get_attribution" in tool_names
        assert "tool_get_enforcement_priority" in tool_names

    def test_malformed_llm_output_graceful_fallback(self) -> None:
        mock = MockLLM([
            'not valid json at all',
        ])
        state = AgentState(
            request_id="test-malformed",
            user_query="why is Peenya bad",
            city="bengaluru",
            station_id="",
        )
        audit = AuditTrail("test-malformed")
        fake_reg = _make_fake_tool_registry()

        with patch("backend.app.agents.dynamic_planning_agent.get_llm_provider", return_value=mock):
            with patch("backend.app.agents.dynamic_planning_agent.PLANNING_TOOL_REGISTRY", fake_reg):
                run_dynamic_planning_agent(state, audit)

        assert state.response != ""
        assert state.response is not None
        assert state.fallback_used is True

    def test_malformed_json_structure_graceful(self) -> None:
        mock = MockLLM([
            '{"action": "unknown_action"}',
        ])
        state = AgentState(
            request_id="test-malformed-json",
            user_query="what is aqi",
            city="bengaluru",
            station_id="",
        )
        audit = AuditTrail("test-malformed-json")
        fake_reg = _make_fake_tool_registry()

        with patch("backend.app.agents.dynamic_planning_agent.get_llm_provider", return_value=mock):
            with patch("backend.app.agents.dynamic_planning_agent.PLANNING_TOOL_REGISTRY", fake_reg):
                run_dynamic_planning_agent(state, audit)

        assert state.response != ""
        assert state.response is not None
        assert state.fallback_used is True

    def test_step_cap_exhaustion(self) -> None:
        responses = [
            '{"action": "call_tool", "tool": "tool_get_forecast_evidence", "arguments": {"station_id": "cpcb_peenya"}}'
            for _ in range(MAX_PLANNING_STEPS + 1)
        ]
        mock = MockLLM(responses)
        state = AgentState(
            request_id="test-exhaust",
            user_query="keep calling tools forever",
            city="bengaluru",
            station_id="",
        )
        audit = AuditTrail("test-exhaust")
        fake_reg = _make_fake_tool_registry()

        with patch("backend.app.agents.dynamic_planning_agent.get_llm_provider", return_value=mock):
            with patch("backend.app.agents.dynamic_planning_agent.PLANNING_TOOL_REGISTRY", fake_reg):
                run_dynamic_planning_agent(state, audit)

        assert state.response != ""
        assert state.response is not None
        assert "step cap" in state.warnings[0].lower() or "budget" in state.warnings[0].lower()

    def test_repeated_call_guard(self) -> None:
        mock = MockLLM([
            '{"action": "call_tool", "tool": "tool_get_forecast_evidence", "arguments": {"station_id": "cpcb_peenya"}}',
            '{"action": "call_tool", "tool": "tool_get_forecast_evidence", "arguments": {"station_id": "cpcb_peenya"}}',
            '{"action": "final_answer", "text": "Done."}',
        ])
        state = AgentState(
            request_id="test-repeat",
            user_query="check forecast twice",
            city="bengaluru",
            station_id="",
        )
        audit = AuditTrail("test-repeat")
        fake_reg = _make_fake_tool_registry()

        with patch("backend.app.agents.dynamic_planning_agent.get_llm_provider", return_value=mock):
            with patch("backend.app.agents.dynamic_planning_agent.PLANNING_TOOL_REGISTRY", fake_reg):
                run_dynamic_planning_agent(state, audit)

        assert state.response == "Done."
        evidence_calls = [t for t in audit.tools_called if t["tool"] == "tool_get_forecast_evidence"]
        assert len(evidence_calls) == 2
        assert evidence_calls[0]["success"] is True
        assert evidence_calls[1]["success"] is False

    def test_llm_not_available_uses_current_behavior(self) -> None:
        llm = LLMProvider()
        if not llm.is_available:
            result = run_orchestrator(
                query="Explain forecast",
                station_id="cpcb_hebbal",
                explicit_intent="station_explanation",
            )
            assert result["selected_agent"] == "forecast_evidence_agent"
            assert result["intent"] == "station_explanation"

    def test_unsupported_without_llm_uses_deterministic(self) -> None:
        llm = LLMProvider()
        if not llm.is_available:
            result = run_orchestrator(
                query="What is the capital of France?",
                station_id="",
            )
            assert result["intent"] == "unsupported"
            assert result["llm_mode"] in ("deterministic", "fallback")

    def test_unsupported_with_llm_dynamic_planning(self) -> None:
        mock = MockLLM([
            '{"action": "final_answer", "text": "The capital of France is Paris."}',
        ])
        with patch("backend.app.agents.dynamic_planning_agent.get_llm_provider", return_value=mock):
            with patch("backend.app.agents.orchestrator.get_llm_provider", return_value=mock):
                result = run_orchestrator(
                    query="What is the capital of France?",
                    station_id="",
                )
        assert result["intent"] == "dynamic_planning"
        assert result["answer"] is not None


# =========================================================================
# Groq provider tests
# =========================================================================


class TestGroqProvider:
    def test_groq_uses_correct_base_url_and_model_fallback(self) -> None:
        import openai as openai_module
        constructor_kwargs = {}

        def mock_constructor(api_key=None, base_url=None):
            constructor_kwargs["api_key"] = api_key
            constructor_kwargs["base_url"] = base_url
            raise ImportError("stop before real call")

        with patch.object(openai_module, "OpenAI", side_effect=mock_constructor):
            llm = LLMProvider()
            with patch.object(llm, "_available", True):
                llm.model = ""
                result = llm._call_groq("test prompt", {}, system_prompt=None)

        assert result is None  # ImportError re-raised as None
        assert constructor_kwargs["base_url"] == "https://api.groq.com/openai/v1"
        assert constructor_kwargs["api_key"] is not None

    def test_groq_model_fallback_when_empty(self) -> None:
        import openai as openai_module
        create_kwargs = {}

        class FakeResponse:
            class Choice:
                def __init__(self):
                    self.message = type("Msg", (), {"content": "ok"})()
            choices = [Choice()]

        def fake_create(*args, **kwargs):
            create_kwargs.update(kwargs)
            return FakeResponse()

        class FakeClient:
            chat = type("Chat", (), {"completions": type("Comp", (), {"create": fake_create})})()

        with patch.object(openai_module, "OpenAI", return_value=FakeClient()):
            llm = LLMProvider()
            with patch.object(llm, "_available", True):
                llm.model = ""
                result = llm._call_groq("test", {})

        assert result == "ok"
        assert create_kwargs.get("model") == "openai/gpt-oss-120b"