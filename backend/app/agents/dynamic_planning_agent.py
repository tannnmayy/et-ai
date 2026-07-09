from __future__ import annotations

import logging
from typing import Any

from backend.app.agents.audit import AuditTrail
from backend.app.agents.llm_provider import get_llm_provider
from backend.app.agents.state import AgentState
from backend.app.agents.tool_registry import (
    PLANNING_TOOL_REGISTRY,
    PLANNING_TOOL_SCHEMAS,
)

logger = logging.getLogger(__name__)

MAX_PLANNING_STEPS = 5


def run_dynamic_planning_agent(state: AgentState, audit: AuditTrail) -> None:
    query = state.user_query
    llm = get_llm_provider()

    if not llm.is_available:
        state.response = (
            "Dynamic planning requires an LLM to be configured. "
            "Please set AQI_SENTINEL_LLM_API_KEY, AQI_SENTINEL_LLM_PROVIDER, "
            "and AQI_SENTINEL_LLM_MODEL environment variables."
        )
        state.structured_data = {}
        state.llm_status = "deterministic"
        state.fallback_used = True
        return

    tool_results_so_far: dict[str, Any] = {}
    called_pairs: list[tuple[str, str]] = []

    for step in range(1, MAX_PLANNING_STEPS + 1):
        decision = llm.plan_next_step(
            query=query,
            tool_schemas=PLANNING_TOOL_SCHEMAS,
            tool_results_so_far=tool_results_so_far,
            step_number=step,
            max_steps=MAX_PLANNING_STEPS,
        )

        if decision is None:
            if tool_results_so_far:
                state.structured_data = tool_results_so_far
                summary = llm.summarize(
                    f"The user asked: '{query}'. The planning agent encountered an error. "
                    f"Summarize the information gathered so far.",
                    tool_results_so_far,
                )
                state.response = summary or (
                    "An error occurred during dynamic planning. "
                    "Here is what was gathered: " + str(tool_results_so_far)
                )
            else:
                state.response = (
                    "Dynamic planning was unavailable for this query. "
                    "Please rephrase as a single specific question about air quality."
                )
                state.structured_data = {}
            state.llm_status = "fallback"
            audit.set_fallback(True)
            state.fallback_used = True
            return

        if decision["action"] == "final_answer":
            state.response = decision["text"]
            state.structured_data = tool_results_so_far
            state.llm_status = "hosted"
            return

        if decision["action"] == "call_tool":
            tool_name = decision["tool"]
            arguments = decision.get("arguments", {})

            call_key = (tool_name, json_dumps_sort(arguments))
            if call_key in called_pairs:
                previous_result = tool_results_so_far.get(
                    f"step_{called_pairs.index(call_key) + 1}_{tool_name}",
                    "unknown",
                )
                tool_results_so_far[f"step_{step}_{tool_name}_repeat"] = {
                    "_note": f"Already called with these arguments. Previous result was: {previous_result}"
                }
                audit.record_tool_call(tool_name, arguments, False)
                continue

            if tool_name not in PLANNING_TOOL_REGISTRY:
                tool_results_so_far[f"step_{step}_{tool_name}"] = {
                    "_tool_error": f"Unknown tool '{tool_name}'. Available tools: {list(PLANNING_TOOL_REGISTRY.keys())}",
                    "_error_type": "UnknownToolError",
                }
                audit.record_tool_call(tool_name, arguments, False)
                continue

            tool_fn = PLANNING_TOOL_REGISTRY[tool_name]
            try:
                result = tool_fn(**arguments)
            except Exception as e:
                result = {"_tool_error": str(e), "_error_type": type(e).__name__}

            is_success = "_tool_error" not in result and "error" not in result
            audit.record_tool_call(tool_name, arguments, is_success)

            tool_results_so_far[f"step_{step}_{tool_name}"] = result
            state.tool_results = tool_results_so_far
            called_pairs.append(call_key)

    state.structured_data = tool_results_so_far
    budget_exhausted_prompt = (
        f"The user asked: '{query}'. The step budget of {MAX_PLANNING_STEPS} steps was reached "
        f"without a final answer. Summarize what was gathered so far below."
    )
    summary = llm.summarize(budget_exhausted_prompt, tool_results_so_far)
    state.response = summary or "The planning step budget was reached. Here is what was gathered: " + str(tool_results_so_far)
    state.warnings.append(f"Dynamic planning step cap ({MAX_PLANNING_STEPS}) reached; response may be incomplete.")
    state.llm_status = "fallback"
    audit.set_fallback(True)
    state.fallback_used = True


def json_dumps_sort(obj: Any) -> str:
    import json
    return json.dumps(obj, sort_keys=True, default=str)