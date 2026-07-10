from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from backend.app.agents.audit import AuditTrail
from backend.app.agents.llm_provider import get_llm_provider
from backend.app.agents.state import AgentState
from backend.app.agents.tool_registry import (
    PLANNING_TOOL_REGISTRY,
    PLANNING_TOOL_SCHEMAS,
)

logger = logging.getLogger(__name__)

MAX_PLANNING_STEPS = 5


def _grounded_fallback(state: AgentState, audit: AuditTrail) -> None:
    """Keep Copilot useful when the hosted LLM is temporarily unreachable."""
    from backend.app.services.inspection_priority_service import get_inspection_priorities

    priorities = get_inspection_priorities(state.city, top_k=max(3, state.top_k))
    ranked = priorities.get("ranked_stations", [])
    audit.record_tool_call("tool_get_inspection_priorities", {"city": state.city, "top_k": max(3, state.top_k)}, True)
    state.structured_data = {"inspection_priorities": priorities}
    if ranked:
        highest = ranked[0]
        others = ", ".join(
            f"{item['station_name']} ({item['risk_category']})" for item in ranked[1:3]
        )
        state.response = (
            f"The highest current monitoring priority is {highest['station_name']}. "
            f"Its next PM2.5 estimate is {highest['predicted_pm25']:.0f} µg/m³, "
            f"which is {highest['risk_category'].lower()} on the project’s scale. "
            f"The recommended check is: {highest['recommended_inspection_focus']} "
            + (f"Other areas to watch are {others}. " if others else "")
            + "This is a monitoring-based priority, not proof of a source at a particular site."
        )
    else:
        state.response = "Live station priorities are unavailable right now. Please try again shortly."
    state.llm_status = "fallback"
    state.fallback_used = True
    state.warnings.append("The LLM was temporarily unavailable; this answer uses live deterministic monitoring data.")


class PlanningGraphState(TypedDict, total=False):
    query: str
    results: dict[str, Any]
    called_pairs: list[tuple[str, str]]
    step: int
    decision: dict[str, Any]
    answer: str
    finished: bool
    warnings: list[str]


def _build_planning_graph(llm: Any, audit: AuditTrail):
    """Create the LLM planner → tool executor → planner LangGraph loop."""
    def plan(graph_state: PlanningGraphState) -> PlanningGraphState:
        step = graph_state.get("step", 0) + 1
        decision = llm.plan_next_step(
            query=graph_state["query"], tool_schemas=PLANNING_TOOL_SCHEMAS,
            tool_results_so_far=graph_state.get("results", {}), step_number=step,
            max_steps=MAX_PLANNING_STEPS,
        )
        result: PlanningGraphState = {"step": step}
        if decision is None:
            result["finished"] = True
            result["answer"] = "I couldn't complete the reasoning step. Please try again."
            return result

        action = decision.get("action")
        if action is None:
            result["finished"] = True
            result["answer"] = "I couldn't parse the planning decision. Please try rephrasing your question."
            result["warnings"] = ["The LLM returned a decision without an 'action' field."]
            return result

        if action == "final_answer" or step >= MAX_PLANNING_STEPS:
            result["finished"] = True
            result["decision"] = decision
            result["answer"] = decision.get("text", "I gathered the available evidence but could not complete the plan.")
            if step >= MAX_PLANNING_STEPS:
                result["warnings"] = [f"Dynamic planning step cap ({MAX_PLANNING_STEPS}) reached; response may be incomplete."]
            return result

        if action != "call_tool":
            result["finished"] = True
            result["answer"] = "I couldn't parse the planning decision. Please try rephrasing your question."
            result["warnings"] = [f"The LLM returned an unrecognized planning action '{action}'."]
            return result

        result["decision"] = decision
        result["finished"] = False
        return result

    def execute_tool(graph_state: PlanningGraphState) -> PlanningGraphState:
        decision = graph_state["decision"]
        tool_name = decision.get("tool")
        if not tool_name:
            audit.record_tool_call("unknown", {}, False)
            return {"results": {"_tool_error": "Tool call missing 'tool' field in LLM decision."}}
        arguments = decision.get("arguments", {})
        key = (tool_name, json_dumps_sort(arguments))
        results = dict(graph_state.get("results", {}))
        called = list(graph_state.get("called_pairs", []))
        if key in called or tool_name not in PLANNING_TOOL_REGISTRY:
            results[f"step_{graph_state['step']}_{tool_name}"] = {"_tool_error": "Tool call was invalid or repeated."}
            audit.record_tool_call(tool_name, arguments, False)
        else:
            try:
                result = PLANNING_TOOL_REGISTRY[tool_name](**arguments)
            except Exception as exc:
                result = {"_tool_error": str(exc), "_error_type": type(exc).__name__}
            audit.record_tool_call(tool_name, arguments, "_tool_error" not in result and "error" not in result)
            results[f"step_{graph_state['step']}_{tool_name}"] = result
            called.append(key)
        return {"results": results, "called_pairs": called}

    graph = StateGraph(PlanningGraphState)
    graph.add_node("plan", plan)
    graph.add_node("execute_tool", execute_tool)
    graph.set_entry_point("plan")
    graph.add_conditional_edges("plan", lambda s: END if s.get("finished") else "execute_tool", {END: END, "execute_tool": "execute_tool"})
    graph.add_edge("execute_tool", "plan")
    return graph.compile()


def run_dynamic_planning_agent(state: AgentState, audit: AuditTrail) -> None:
    query = state.user_query
    llm = get_llm_provider()

    if not llm.is_available:
        _grounded_fallback(state, audit)
        return

    graph = _build_planning_graph(llm, audit)
    output = graph.invoke({"query": query, "results": {}, "called_pairs": [], "step": 0})
    tool_results_so_far = output.get("results", {})

    # Propagate warnings from the graph (step cap, malformed decisions, etc.)
    graph_warnings = output.get("warnings", [])
    state.warnings.extend(graph_warnings)

    has_answer = bool(output.get("answer"))
    answer_is_ok = (
        has_answer
        and output["answer"] != "I couldn't complete the reasoning step. Please try again."
        and not graph_warnings
    )

    if answer_is_ok:
        state.response = output["answer"]
        state.structured_data = tool_results_so_far
        state.tool_results = tool_results_so_far
        state.llm_status = "hosted"
        return

    # If the graph produced an answer alongside warnings (step cap / malformed
    # decision), still surface the answer but mark it as fallback.
    if has_answer and graph_warnings:
        state.response = output["answer"]
        state.structured_data = tool_results_so_far
        state.tool_results = tool_results_so_far
        state.llm_status = "fallback"
        state.fallback_used = True
        return

    # A provider failure must never surface as a generic retry message.
    _grounded_fallback(state, audit)
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
