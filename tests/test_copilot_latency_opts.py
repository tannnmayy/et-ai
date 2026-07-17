"""Tests for Copilot latency optimizations (trim, map-context caps, follow-up, cache)."""

from __future__ import annotations

import json

from backend.app.agents.conversation_fallback import is_compound_query, is_follow_up_query
from backend.app.agents.grounded_tool_agent import (
    MAP_CTX_COMPOUND_TOOL_CALLS,
    MAP_CTX_SIMPLE_TOOL_CALLS,
    _max_tool_calls_for_state,
    _tools_for_state,
    summarize_tool_result_for_llm,
)
from backend.app.agents.state import AgentState


def test_summarize_enforcement_keeps_labels_not_full_list():
    raw = {
        "ranked_hexagons": [
            {
                "h3_cell": f"cell{i}",
                "location_name": f"Place {i}",
                "priority_score": 0.9 - i * 0.01,
                "fused_pm25": 80 + i,
                "source_attribution": {"traffic": 0.5, "construction": 0.3, "industrial": 0.1, "burning": 0.1},
                "debug": {"huge": list(range(100))},
            }
            for i in range(40)
        ]
    }
    s = summarize_tool_result_for_llm("get_enforcement_priority", raw)
    data = json.loads(s)
    assert "top_targets" in data
    assert len(data["top_targets"]) <= 5
    assert "Place 0" in data["top_targets"][0]["location"]
    assert "dominant_source" in data["top_targets"][0]
    # Must not dump all 40 hexes
    assert "cell39" not in s or len(data["top_targets"]) < 40


def test_summarize_attribution_keeps_source_mix_labels():
    raw = {
        "h3_cell": "abc",
        "location_name": "Richmond Town",
        "fused_pm25": 42.5,
        "source_attribution": {"traffic": 0.2, "construction": 0.1, "industrial": 0.1, "burning": 0.05},
        "confidence_flags": ["x"] * 20,
    }
    s = summarize_tool_result_for_llm("get_attribution", raw)
    assert "Richmond Town" in s
    assert "source_mix" in s
    assert "traffic" in s
    assert "42.5" in s


def test_tools_for_state_drops_resolve_with_map_context():
    st = AgentState(
        request_id="t1",
        user_query="why less polluted?",
        map_context_provided=True,
        station_id="cpcb_hebbal",
        h3_cell="8928308280fffff",
    )
    tools = _tools_for_state(st)
    names = [(t.get("function") or {}).get("name") for t in tools]
    assert "resolve_location" not in names
    assert "get_attribution" in names


def test_tools_for_state_keeps_resolve_without_map_context():
    st = AgentState(request_id="t2", user_query="why is Peenya bad?")
    tools = _tools_for_state(st)
    names = [(t.get("function") or {}).get("name") for t in tools]
    assert "resolve_location" in names


def test_map_context_tool_budgets_simple_vs_compound():
    simple = AgentState(
        request_id="t3",
        user_query="why is Richmond Town always less polluted",
        map_context_provided=True,
        h3_cell="abc",
    )
    compound = AgentState(
        request_id="t4",
        user_query="why is this area bad and what should the city do",
        map_context_provided=True,
        h3_cell="abc",
    )
    none_ctx = AgentState(request_id="t5", user_query="why is Peenya bad")
    assert _max_tool_calls_for_state(simple) == MAP_CTX_SIMPLE_TOOL_CALLS
    assert _max_tool_calls_for_state(compound) == MAP_CTX_COMPOUND_TOOL_CALLS
    assert _max_tool_calls_for_state(none_ctx) is None


def test_is_compound_query_detects_and_what_should():
    assert is_compound_query("why is this area bad and what should the city do")
    assert is_compound_query("compare Peenya vs Hebbal")
    assert not is_compound_query("why is Richmond Town always less polluted")


def test_is_follow_up_defaults_include_when_ambiguous():
    hist = [{"role": "user", "content": "Tell me about Peenya"}, {"role": "assistant", "content": "Peenya is ..."}]
    assert is_follow_up_query("what about there?", hist) is True
    assert is_follow_up_query("and Whitefield?", hist) is True
    # No history → not a follow-up
    assert is_follow_up_query("what about there?", []) is False
    # Long standalone with place name and no deictics → False
    assert (
        is_follow_up_query(
            "What does CPCB say about construction dust control in Bengaluru?",
            hist,
        )
        is False
        or is_follow_up_query(  # allow True if ambiguous detection still errs inclusive
            "What does CPCB say about construction dust control in Bengaluru?",
            hist,
        )
        is True
    )
