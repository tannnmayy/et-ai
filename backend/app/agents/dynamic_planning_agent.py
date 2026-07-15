"""LangGraph multi-step planning agent for Copilot deep-reasoning mode.

Flow:
  1. Retrieve knowledge-base context (Chroma → TF-IDF fallback)
  2. Plan → execute tool → plan loop (max MAX_PLANNING_STEPS)
  3. On LLM failure after multi-key retries → deterministic grounded fallback
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from backend.app.agents.audit import AuditTrail
from backend.app.agents.conversation_fallback import run_query_aware_fallback
from backend.app.agents.llm_provider import get_llm_provider
from backend.app.agents.state import AgentState
from backend.app.agents.tool_registry import (
    PLANNING_TOOL_REGISTRY,
    PLANNING_TOOL_SCHEMAS,
)

logger = logging.getLogger(__name__)

MAX_PLANNING_STEPS = 5


def json_dumps_sort(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def _grounded_fallback(state: AgentState, audit: AuditTrail) -> None:
    """Keep Copilot useful when the hosted LLM is temporarily unreachable."""
    run_query_aware_fallback(state, audit, deep=True)


class PlanningGraphState(TypedDict, total=False):
    query: str
    results: dict[str, Any]
    called_pairs: list[tuple[str, str]]
    step: int
    decision: dict[str, Any]
    answer: str
    finished: bool
    warnings: list[str]


def _build_planning_graph(llm: Any, audit: AuditTrail, knowledge_context: str = ""):
    """Create the LLM planner → tool executor → planner LangGraph loop."""

    def plan(graph_state: PlanningGraphState) -> PlanningGraphState:
        step = graph_state.get("step", 0) + 1
        audit.record_reasoning("plan", f"Planning step {step}/{MAX_PLANNING_STEPS}")
        decision = llm.plan_next_step(
            query=graph_state["query"],
            tool_schemas=PLANNING_TOOL_SCHEMAS,
            tool_results_so_far=graph_state.get("results", {}),
            step_number=step,
            max_steps=MAX_PLANNING_STEPS,
            knowledge_context=knowledge_context,
        )
        # Capture which provider/key succeeded for the UI trace
        audit.set_llm_meta(
            getattr(llm, "last_provider", None),
            getattr(llm, "last_gemini_key_index", None),
        )
        result: PlanningGraphState = {"step": step}
        if decision is None:
            result["finished"] = True
            result["answer"] = "I couldn't complete the reasoning step. Please try again."
            audit.record_reasoning(
                "llm_error",
                "Planner returned no decision (provider failure or parse error)",
            )
            return result

        action = decision.get("action")
        if action is None:
            result["finished"] = True
            result["answer"] = (
                "I couldn't parse the planning decision. Please try rephrasing your question."
            )
            result["warnings"] = ["The LLM returned a decision without an 'action' field."]
            return result

        if action == "final_answer" or step >= MAX_PLANNING_STEPS:
            result["finished"] = True
            result["decision"] = decision
            result["answer"] = decision.get(
                "text",
                "I gathered the available evidence but could not complete the plan.",
            )
            if step >= MAX_PLANNING_STEPS:
                result["warnings"] = [
                    f"Dynamic planning step cap ({MAX_PLANNING_STEPS}) reached; response may be incomplete."
                ]
            audit.record_reasoning("final_answer", "Planner produced a final answer")
            return result

        if action != "call_tool":
            result["finished"] = True
            result["answer"] = (
                "I couldn't parse the planning decision. Please try rephrasing your question."
            )
            result["warnings"] = [
                f"The LLM returned an unrecognized planning action '{action}'."
            ]
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
            results[f"step_{graph_state['step']}_{tool_name}"] = {
                "_tool_error": "Tool call was invalid or repeated."
            }
            audit.record_tool_call(tool_name, arguments, False)
        else:
            try:
                result = PLANNING_TOOL_REGISTRY[tool_name](**arguments)
            except Exception as exc:
                result = {"_tool_error": str(exc), "_error_type": type(exc).__name__}
            audit.record_tool_call(
                tool_name,
                arguments,
                "_tool_error" not in result and "error" not in result,
            )
            results[f"step_{graph_state['step']}_{tool_name}"] = result
            called.append(key)
        return {"results": results, "called_pairs": called}

    graph = StateGraph(PlanningGraphState)
    graph.add_node("plan", plan)
    graph.add_node("execute_tool", execute_tool)
    graph.set_entry_point("plan")
    graph.add_conditional_edges(
        "plan",
        lambda s: END if s.get("finished") else "execute_tool",
        {END: END, "execute_tool": "execute_tool"},
    )
    graph.add_edge("execute_tool", "plan")
    return graph.compile()


def run_dynamic_planning_agent(state: AgentState, audit: AuditTrail) -> None:
    query = state.user_query
    llm = get_llm_provider()

    # Retrieve knowledge-base context before planning (Chroma → TF-IDF fallback)
    knowledge_context = ""
    try:
        from backend.app.services.knowledge_rag_service import retrieve_knowledge

        rag = retrieve_knowledge(query, top_k=4)
        if rag.get("used"):
            knowledge_context = rag.get("context_block") or ""
            audit.set_knowledge(
                True,
                backend=rag.get("backend"),
                chunk_count=len(rag.get("chunks") or []),
            )
            # Seed tool_results so the planner sees KB evidence without a free tool call
            state.tool_results = {
                **(state.tool_results or {}),
                "knowledge_base": {
                    "backend": rag.get("backend"),
                    "chunks": rag.get("chunks"),
                },
            }
        else:
            audit.set_knowledge(False, backend="none", chunk_count=0)
    except Exception as exc:
        logger.warning("RAG retrieve failed in dynamic planner: %s", exc)
        audit.set_knowledge(False, backend="error", chunk_count=0)

    if not llm.is_available:
        audit.record_reasoning(
            "llm_unavailable",
            "No LLM providers configured — grounded fallback",
        )
        _grounded_fallback(state, audit)
        return

    graph = _build_planning_graph(llm, audit, knowledge_context=knowledge_context)
    initial_results = dict(state.tool_results or {})
    output = graph.invoke({
        "query": query,
        "results": initial_results,
        "called_pairs": [],
        "step": 0,
    })
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
        audit.set_llm_meta(
            getattr(llm, "last_provider", None),
            getattr(llm, "last_gemini_key_index", None),
        )
        return

    # If the graph produced an answer alongside warnings (step cap / malformed
    # decision), still surface the answer but mark it as fallback.
    if has_answer and graph_warnings:
        state.response = output["answer"]
        state.structured_data = tool_results_so_far
        state.tool_results = tool_results_so_far
        state.llm_status = "fallback"
        state.fallback_used = True
        audit.set_fallback(True)
        return

    # A provider failure must never surface as a generic retry message.
    audit.record_reasoning(
        "fallback",
        "Deep planning failed after multi-key LLM attempts — using deterministic grounded data",
    )
    _grounded_fallback(state, audit)
