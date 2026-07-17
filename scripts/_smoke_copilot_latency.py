"""Smoke: map-context simple + compound queries with Fake LLM counting tool loops."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

from backend.app.agents.grounded_tool_agent import (
    MAP_CTX_COMPOUND_TOOL_CALLS,
    MAP_CTX_SIMPLE_TOOL_CALLS,
    run_grounded_tool_agent,
    summarize_tool_result_for_llm,
)
from backend.app.agents.audit import AuditTrail
from backend.app.agents.state import AgentState


class CountingFakeLLM:
    """Returns tool calls then final answer; tracks chat_with_tools rounds."""

    is_available = True
    last_provider = "fake"
    last_gemini_key_index = None
    last_groq_key_index = None
    last_fallback_note = None

    def __init__(self, tool_plan: list[list[dict[str, Any]]]):
        self.tool_plan = tool_plan
        self.round = 0
        self.chat_rounds = 0
        self.summarize_calls = 0
        self.tools_seen: list[str] = []

    def chat_with_tools(self, messages, tools, **kwargs):
        self.chat_rounds += 1
        names = [(t.get("function") or {}).get("name") for t in tools]
        self.tools_seen = names
        if self.round < len(self.tool_plan):
            calls = self.tool_plan[self.round]
            self.round += 1
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": f"c{self.round}_{i}",
                        "name": c["name"],
                        "arguments": c.get("arguments") or {},
                    }
                    for i, c in enumerate(calls)
                ],
                "provider": "fake",
            }
        return {
            "content": (
                "Based on the station-fused attribution for this area, local source mix and "
                "fused PM2.5 indicate relatively lower pollution pressure than industrial north "
                "corridors. This is investigation evidence only, not a legal finding."
            ),
            "tool_calls": [],
            "provider": "fake",
        }

    def summarize(self, prompt, structured_data, system_prompt=None):
        self.summarize_calls += 1
        return (
            "Partial evidence suggests this map area has a moderate fused PM2.5 reading with a "
            "mixed source profile. Officers should verify on site before any action."
        )


def _run(query: str, *, h3: str, tool_plan) -> dict[str, Any]:
    fake = CountingFakeLLM(tool_plan)
    state = AgentState(
        request_id="smoke",
        user_query=query,
        city="bengaluru",
        h3_cell=h3,
        map_context_provided=True,
    )
    audit = AuditTrail("smoke")
    t0 = time.time()
    with patch(
        "backend.app.agents.grounded_tool_agent.get_llm_provider", return_value=fake
    ), patch(
        "backend.app.agents.grounded_tool_agent._execute_tool",
        side_effect=lambda name, args, use_cache=True: {
            "h3_cell": h3,
            "location_name": "Richmond Town",
            "fused_pm25": 48.0,
            "source_attribution": {
                "traffic": 0.35,
                "construction": 0.25,
                "industrial": 0.25,
                "burning": 0.15,
            },
            "text": "Local sources are mixed with moderate traffic contribution.",
            "ranked_hexagons": [
                {
                    "h3_cell": h3,
                    "location_name": "Richmond Town",
                    "priority_score": 0.4,
                    "fused_pm25": 48,
                    "source_attribution": {"traffic": 0.4, "construction": 0.3, "industrial": 0.2, "burning": 0.1},
                }
            ],
        },
    ):
        run_grounded_tool_agent(state, audit)
    elapsed = time.time() - t0
    return {
        "answer": state.response,
        "tool_calls": len(audit.tools_called),
        "chat_rounds": fake.chat_rounds,
        "tools_in_schema": fake.tools_seen,
        "partial": audit.partial_response,
        "elapsed_s": round(elapsed, 3),
        "resolve_in_schema": "resolve_location" in (fake.tools_seen or []),
        "mode": audit.response_mode,
        "path": (state.structured_data or {}).get("path"),
    }


def main() -> None:
    h3 = "8928308280fffff"
    simple_plan = [
        [{"name": "get_attribution", "arguments": {"h3_cell": h3}}],
        [{"name": "get_causal_explanation", "arguments": {"h3_cell": h3}}],
        # would be a 3rd call if budget allowed
        [{"name": "get_enforcement_priority", "arguments": {"top_k": 5}}],
    ]
    r1 = _run(
        "why is Richmond Town always less polluted",
        h3=h3,
        tool_plan=simple_plan,
    )
    print("=== SIMPLE map-context (Richmond-equivalent) ===")
    print(r1)
    assert r1["tool_calls"] <= MAP_CTX_SIMPLE_TOOL_CALLS, r1
    assert r1["resolve_in_schema"] is False
    assert r1["answer"] and len(r1["answer"]) > 40
    assert "{" not in r1["answer"][:20]  # not raw JSON dump

    compound_plan = [
        [{"name": "get_attribution", "arguments": {"h3_cell": h3}}],
        [{"name": "get_causal_explanation", "arguments": {"h3_cell": h3}}],
        [{"name": "get_enforcement_priority", "arguments": {"top_k": 5}}],
        [{"name": "search_policy_guidance", "arguments": {"query": "dust"}}],
        [{"name": "get_city_briefing", "arguments": {}}],  # 5th — should hit compound cap of 4
    ]
    r2 = _run(
        "why is this area bad and what should the city do",
        h3=h3,
        tool_plan=compound_plan,
    )
    print("=== COMPOUND map-context ===")
    print(r2)
    assert r2["tool_calls"] <= MAP_CTX_COMPOUND_TOOL_CALLS, r2
    assert r2["tool_calls"] >= MAP_CTX_SIMPLE_TOOL_CALLS  # should use more than simple
    assert r2["answer"]

    # Trimming size check
    big = {"ranked_hexagons": [{"h3_cell": str(i), "location_name": f"L{i}", "priority_score": 1, "fused_pm25": 90, "source_attribution": {"traffic": 0.5}} for i in range(100)]}
    slim = summarize_tool_result_for_llm("get_enforcement_priority", big)
    print("trim_ratio", len(slim), "vs", len(str(big)))
    assert len(slim) < len(str(big)) // 2
    print("SMOKE_OK")


if __name__ == "__main__":
    main()
