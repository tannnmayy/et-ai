"""Phase 1 default Copilot path: native tool-calling agent + grounding.

Flow:
  1. Seed messages with system prompt + user query (+ optional context)
  2. Loop (max MAX_STEPS / map-context tool-call caps): chat_with_tools → execute tools
  3. Append **trimmed** tool summaries to LLM messages; keep full results for grounding/map/audit
  4. When model returns final text (no tool_calls), run grounding check
  5. If grounding fails, retry once with stronger instruction OR deterministic summary
  6. If all LLM providers fail, run heuristic multi-tool deterministic plan
  7. On tool-call cap without final text: best-effort prose + partial_response
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.app.agents.audit import AuditTrail
from backend.app.agents.conversation_fallback import is_compound_query, is_follow_up_query
from backend.app.agents.grounding import (
    check_answer_grounding,
    deterministic_summary_from_tools,
)
from backend.app.agents.llm_provider import get_llm_provider
from backend.app.agents.native_tool_schemas import (
    AGENT_SYSTEM_PROMPT,
    NATIVE_TOOL_DISPATCH,
    OPENAI_TOOLS,
)
from backend.app.agents.state import AgentState, Intent

logger = logging.getLogger(__name__)

# Default loop ceiling without map context (LLM turns, each may call tools)
MAX_TOOL_STEPS = 6
# Map-context tool-call budgets (actual tool executions, not LLM turns)
MAP_CTX_SIMPLE_TOOL_CALLS = 2
MAP_CTX_COMPOUND_TOOL_CALLS = 4


def summarize_tool_result_for_llm(tool_name: str, result: dict[str, Any]) -> str:
    """Minimal but narrative-capable tool summary for the LLM conversation history.

    Full ``result`` is still kept for grounding, map_actions, and audit.
    Summaries keep short labels next to numbers so the model can write specific prose.
    """
    if not isinstance(result, dict):
        return json.dumps({"tool": tool_name, "value": result}, default=str)[:2000]

    if result.get("_tool_error"):
        return json.dumps(
            {
                "tool": tool_name,
                "error": result.get("_tool_error"),
                "error_type": result.get("_error_type"),
            },
            default=str,
        )

    name = tool_name
    out: dict[str, Any] = {"tool": name}

    if name == "resolve_location":
        for k in (
            "station_id",
            "nearest_station_id",
            "h3_cell",
            "h3",
            "latitude",
            "lat",
            "longitude",
            "lon",
            "lng",
            "resolved_name",
            "display_name",
            "locality",
            "resolution_method",
            "note",
        ):
            if result.get(k) is not None:
                out[k] = result[k]
        return json.dumps(out, default=str)

    if name in ("get_enforcement_priority", "tool_get_enforcement_priority"):
        ranked = result.get("ranked_hexagons") or result.get("hexagons") or []
        tops: list[dict[str, Any]] = []
        for h in ranked[:5]:
            if not isinstance(h, dict):
                continue
            sa = h.get("source_attribution") or {}
            dom = None
            if isinstance(sa, dict) and sa:
                try:
                    dom = max(sa, key=lambda k: float(sa.get(k) or 0))
                except Exception:
                    dom = None
            tops.append(
                {
                    "rank": h.get("rank") or len(tops) + 1,
                    "location": h.get("location_name") or h.get("name") or h.get("h3_cell"),
                    "h3_cell": h.get("h3_cell") or h.get("id"),
                    "priority_score": h.get("priority_score"),
                    "fused_pm25": h.get("fused_pm25") or h.get("pm25"),
                    "dominant_source": dom or h.get("primary_source") or h.get("sourceType"),
                    "action_tier": h.get("action_tier") or h.get("actionTier"),
                }
            )
        out["top_targets"] = tops
        out["note"] = f"Showing top {len(tops)} of {len(ranked)} ranked hexes"
        return json.dumps(out, default=str)

    if name in ("get_attribution", "get_causal_explanation", "run_whatif_scenario"):
        for k in (
            "h3_cell",
            "station_id",
            "nearest_station_id",
            "location_name",
            "location_label",
            "fused_pm25",
            "method",
            "text",
            "explanation",
            "summary",
            "is_simulation",
            "disclaimer",
            "baseline_pm25",
            "simulated_pm25",
            "pm25_delta",
            "uncertainty_band",
        ):
            if result.get(k) is not None:
                out[k] = result[k]
        sa = result.get("source_attribution") or (result.get("attribution") or {}).get(
            "source_attribution"
        )
        if isinstance(sa, dict) and sa:
            # Keep labeled shares (not bare floats) for prose
            out["source_mix"] = {
                k: f"{float(v) * 100:.0f}%" if float(v) <= 1.01 else f"{float(v):.0f}%"
                for k, v in sa.items()
                if v is not None
            }
        conf = result.get("attribution_confidence_score") or result.get("confidence")
        if conf is not None:
            out["attribution_confidence"] = conf
        if name == "run_whatif_scenario":
            for k in ("scenario_text", "scales_applied", "source_mix_after", "enforcement_delta"):
                if result.get(k) is not None:
                    out[k] = result[k]
        return json.dumps(out, default=str)

    if name in ("get_forecast", "get_forecast_confidence"):
        for k in (
            "station_id",
            "station_name",
            "display_name",
            "predicted_pm25",
            "risk_category",
            "forecast_engine",
            "confidence",
            "confidence_level",
            "confidence_score",
            "horizon_hours",
            "model_selected",
            "persistence_rmse",
            "lightgbm_rmse",
            "interpretation",
        ):
            if result.get(k) is not None:
                out[k] = result[k]
        # Keep a short forecast series sample if present
        series = result.get("forecast") or result.get("series") or result.get("predictions")
        if isinstance(series, list) and series:
            out["forecast_sample"] = series[:4]
        return json.dumps(out, default=str)

    if name == "search_policy_guidance":
        hits = result.get("results") or result.get("chunks") or []
        slim_hits = []
        for h in hits[:4]:
            if not isinstance(h, dict):
                continue
            slim_hits.append(
                {
                    "title": h.get("title") or h.get("source") or h.get("doc_id"),
                    "excerpt": (h.get("text") or h.get("content") or h.get("chunk") or "")[:400],
                    "source": h.get("source") or h.get("filename"),
                }
            )
        out["results"] = slim_hits
        out["retrieval_backend"] = result.get("retrieval_backend")
        return json.dumps(out, default=str)

    if name in ("get_city_briefing", "get_weather", "get_travel_readiness"):
        # Keep top-level scalars and small nested dicts; drop huge lists
        for k, v in result.items():
            if k.startswith("_"):
                continue
            if isinstance(v, list):
                out[k] = v[:5]
            elif isinstance(v, dict):
                # Flatten one level of scalars
                nested = {
                    nk: nv
                    for nk, nv in list(v.items())[:12]
                    if not isinstance(nv, (list, dict)) or (isinstance(nv, list) and len(nv) <= 3)
                }
                out[k] = nested
            else:
                out[k] = v
        text = json.dumps(out, default=str)
        if len(text) > 2500:
            return text[:2480] + '..."truncated"}'
        return text

    # Generic: drop bulky/debug keys, cap lists
    skip_keys = {
        "debug",
        "timestamps",
        "raw",
        "hexagons",
        "all_hexagons",
        "grid",
        "full_payload",
        "traceback",
        "_from_tool_cache",
    }
    for k, v in result.items():
        if k in skip_keys or k.startswith("_"):
            continue
        if isinstance(v, list):
            out[k] = v[:5]
        elif isinstance(v, dict):
            out[k] = {
                nk: nv
                for nk, nv in list(v.items())[:15]
                if not isinstance(nv, (list, dict))
            }
        else:
            out[k] = v
    text = json.dumps(out, default=str)
    if len(text) > 2800:
        return text[:2760] + '..."truncated"}'
    return text


def _tools_for_state(state: AgentState) -> list[dict[str, Any]]:
    """Drop resolve_location from the schema when Map context supplies location."""
    if state.map_context_provided and (state.station_id or state.h3_cell):
        filtered = [
            t
            for t in OPENAI_TOOLS
            if (t.get("function") or {}).get("name") != "resolve_location"
        ]
        return filtered
    return OPENAI_TOOLS


def _max_tool_calls_for_state(state: AgentState) -> int | None:
    """Map-context tiered tool-call budget; None = use MAX_TOOL_STEPS turns only."""
    if not (state.map_context_provided and (state.station_id or state.h3_cell)):
        return None
    if is_compound_query(state.user_query or ""):
        return MAP_CTX_COMPOUND_TOOL_CALLS
    return MAP_CTX_SIMPLE_TOOL_CALLS


def _compose_partial_answer(
    state: AgentState,
    audit: AuditTrail,
    llm: Any,
    tool_results: dict[str, Any],
    *,
    reason: str,
) -> str:
    """Best-effort natural-language answer when the tool-call cap is hit (no final model text)."""
    audit.mark_partial_response(reason)
    lang = _normalize_language(state.language)
    lang_name = {"en": "English", "hi": "Hindi", "kn": "Kannada"}.get(lang, "English")
    # Prefer a final LLM composition from **trimmed** evidence for prose quality
    slim_for_compose = {
        k: json.loads(summarize_tool_result_for_llm(k, v))
        if isinstance(v, dict)
        else v
        for k, v in tool_results.items()
    }
    summary = None
    if llm is not None and getattr(llm, "is_available", False):
        summary = llm.summarize(
            (
                "You have a limited set of tool results (the tool budget was reached). "
                f"Write a coherent natural-language answer in {lang_name} (language={lang}) "
                f"to the user query: {state.user_query!r}. "
                "Use only the provided tool data. Do not invent numbers. "
                "Write 2–5 short paragraphs or clear sentences — not raw JSON or a data dump. "
                "If evidence is incomplete, say what you found and what is missing. "
                "Keep PM2.5, AQI, CPCB, station IDs, and H3 IDs in English."
            ),
            {"tool_results": slim_for_compose, "language": lang, "partial": True},
            system_prompt=AGENT_SYSTEM_PROMPT,
        )
    if summary and summary.strip():
        return summary.strip()
    # Deterministic prose from full tool results (still natural language)
    prose = deterministic_summary_from_tools(
        state.user_query, tool_results, language=state.language
    )
    if prose and prose.strip():
        return prose.strip()
    return (
        "I gathered some location-aware air-quality evidence for this area but could not "
        "complete a full multi-tool analysis within the time budget. "
        "Please try a more specific question (for example: source mix, forecast, or enforcement priorities)."
    )


def _execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    use_cache: bool = True,
) -> dict[str, Any]:
    fn = NATIVE_TOOL_DISPATCH.get(name)
    if not fn:
        return {"_tool_error": f"Unknown tool: {name}", "_error_type": "UnknownTool"}
    # Filter unexpected kwargs
    try:
        import inspect

        sig = inspect.signature(fn)
        accepted = {
            k: v
            for k, v in (arguments or {}).items()
            if k in sig.parameters or any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())
        }
        # Map common aliases
        if name == "get_forecast" and "station_id" not in accepted and "stationId" in (arguments or {}):
            accepted["station_id"] = arguments["stationId"]

        # Phase 2: short-TTL tool result cache (skip resolve_location — cheap/offline)
        if use_cache and name != "resolve_location":
            try:
                from backend.app.services.copilot_cache_service import (
                    get_cached_tool_result,
                    set_cached_tool_result,
                )

                cached = get_cached_tool_result(name, accepted)
                if cached is not None:
                    out = dict(cached)
                    out["_from_tool_cache"] = True
                    return out
            except Exception:
                pass

        result = fn(**accepted)

        if use_cache and name != "resolve_location" and isinstance(result, dict) and "_tool_error" not in result:
            try:
                from backend.app.services.copilot_cache_service import set_cached_tool_result

                set_cached_tool_result(name, accepted, result)
            except Exception:
                pass

        return result
    except TypeError as exc:
        return {"_tool_error": f"Bad arguments for {name}: {exc}", "_error_type": "TypeError"}
    except Exception as exc:
        return {"_tool_error": str(exc), "_error_type": type(exc).__name__}


def _normalize_language(code: str | None) -> str:
    c = (code or "en").strip().lower()
    if c in ("en", "hi", "kn"):
        return c
    return "en"


def _language_instruction(lang: str) -> str:
    names = {"en": "English", "hi": "Hindi", "kn": "Kannada"}
    label = names.get(lang, "English")
    return (
        f"language={lang} ({label}). "
        f"Respond in {label}. Keep PM2.5, AQI, CPCB, station IDs, and H3 cell IDs in English; "
        "translate only the natural-language explanation."
    )


def _build_context_block(state: AgentState) -> str:
    """User-message appendix: preferred Map context + language for the tool agent."""
    lines: list[str] = []
    lang = _normalize_language(state.language)
    lines.append(_language_instruction(lang))
    if state.station_id:
        lines.append(f"preferred station_id={state.station_id}")
    if state.h3_cell:
        lines.append(f"preferred h3_cell={state.h3_cell}")
    if state.map_context_provided:
        lines.append(
            "MAP CONTEXT is authoritative for location tools unless the user asks about a different place. "
            "Skip resolve_location for this location. "
            "Use these ids in get_attribution / get_forecast / run_whatif_scenario so the Map can highlight them."
        )
    if state.city:
        lines.append(f"city={state.city}")
    return "(Context: " + "; ".join(lines) + ")"


def _inject_map_context_args(
    name: str,
    args: dict[str, Any],
    state: AgentState,
) -> dict[str, Any]:
    """Fill missing location args from client Map context / resolved state."""
    out = dict(args or {})
    if name in ("get_forecast", "get_forecast_confidence"):
        if not out.get("station_id") and state.station_id:
            out["station_id"] = state.station_id
    if name in ("get_attribution", "get_causal_explanation", "run_whatif_scenario"):
        if not out.get("h3_cell") and state.h3_cell:
            out["h3_cell"] = state.h3_cell
        if name == "run_whatif_scenario" and not out.get("station_id") and state.station_id:
            out["station_id"] = state.station_id
    # User-facing text tools: inject session language when model omits it
    if name == "get_causal_explanation":
        if not out.get("language"):
            out["language"] = _normalize_language(state.language)
    return out


def _extract_place_hint(query: str) -> str | None:
    """Best-effort place string for resolve_location (offline registry first)."""
    q = (query or "").lower()
    # Prefer longest locality key match from the expanded map
    try:
        from backend.app.agents.conversation_fallback import _LOCALITY_CENTRES

        hits = [name for name in _LOCALITY_CENTRES if name in q]
        if hits:
            return max(hits, key=len)
    except Exception:
        pass
    # Station-ish tokens
    for token in (
        "peenya",
        "whitefield",
        "hebbal",
        "koramangala",
        "indiranagar",
        "yeshwanthpur",
        "silk board",
        "btm",
        "manyata",
        "jayanagar",
        "marathahalli",
        "bellandur",
        "electronic city",
        "hsr",
        "bapuji",
        "kasturi",
        "hombegowda",
        "rvce",
    ):
        if token in q:
            return token
    # "near X" / "in X" capture
    m = re.search(
        r"\b(?:near|around|in|at|for)\s+([a-z][a-z0-9\s\-]{2,40}?)(?:\s+(?:right|today|now|area|please)|\?|$)",
        q,
    )
    if m:
        return m.group(1).strip()
    return None


def _heuristic_tool_plan(query: str, city: str) -> list[tuple[str, dict[str, Any]]]:
    """When LLM is down: pick tools from simple keywords (better than empty).

    Always puts resolve_location first when a place name is present.
    """
    q = query.lower()
    plan: list[tuple[str, dict[str, Any]]] = []
    place_hint = _extract_place_hint(query)

    # Critical: resolve first so later tools use lat/h3/station — not brittle alone
    if place_hint:
        plan.append(("resolve_location", {"query": place_hint}))

    if any(
        w in q
        for w in (
            "enforce",
            "inspect",
            "officer",
            "dispatch",
            "hotspot",
            "priority",
            "construction dust",
        )
    ):
        plan.append(("get_enforcement_priority", {"city": city, "top_k": 10}))

    if any(w in q for w in ("policy", "cpcb", "kspcb", "ncap", "guideline", "regulation", "who ")):
        plan.append(("search_policy_guidance", {"query": query, "top_k": 4}))

    if any(w in q for w in ("weather", "rain", "wind", "temperature")):
        plan.append(("get_weather", {"city": city}))

    if any(w in q for w in ("travel", "commute", "go outside", "bike", "outing")):
        plan.append(("get_travel_readiness", {"city": city}))

    if any(w in q for w in ("briefing", "overview", "situation", "city status", "summary")):
        plan.append(("get_city_briefing", {"city": city}))

    if any(
        w in q
        for w in (
            "what if",
            "what-if",
            "counterfactual",
            "scenario",
            "if we reduce",
            "if construction",
            "if traffic",
            "if industrial",
            "how would pollution",
            "how would pm",
            "reduce by",
            "drop by",
            "if emissions",
        )
    ):
        plan.append(
            (
                "run_whatif_scenario",
                {"city": city, "scenario_text": query, "include_enforcement_delta": True},
            )
        )

    if any(w in q for w in ("pollut", "source", "why", "attribution", "traffic", "construction", "poor")):
        # Placeholder — real lat/h3 filled after resolve in _run_heuristic_fallback
        if place_hint or "run_whatif_scenario" not in [n for n, _ in plan]:
            plan.append(("get_attribution", {"city": city}))
            plan.append(("get_causal_explanation", {"city": city}))

    if not plan:
        plan.append(("get_city_briefing", {"city": city}))
        plan.append(("get_enforcement_priority", {"city": city, "top_k": 5}))

    return plan


def _run_heuristic_fallback(state: AgentState, audit: AuditTrail) -> None:
    """Deterministic multi-tool plan when native tool-calling LLM is unavailable."""
    audit.record_reasoning(
        "fallback",
        "LLM tool-calling unavailable — running heuristic multi-tool plan",
    )
    city = state.city or "bengaluru"
    plan = _heuristic_tool_plan(state.user_query, city)
    tool_results: dict[str, Any] = {}
    lat = lon = None
    h3 = state.h3_cell
    station_id = state.station_id or ""

    # Prefer Map context — skip resolve when client already sent station/h3
    place_hint = _extract_place_hint(state.user_query)
    skip_resolve = bool(state.map_context_provided and (station_id or h3))
    if skip_resolve:
        audit.record_reasoning(
            "route",
            "Heuristic: using Map context (skip resolve_location)",
        )
        # Drop resolve steps from plan
        plan = [(n, a) for n, a in plan if n != "resolve_location"]
    else:
        ordered: list[tuple[str, dict[str, Any]]] = []
        if place_hint and not any(n == "resolve_location" for n, _ in plan):
            ordered.append(("resolve_location", {"query": place_hint}))
        ordered.extend([(n, a) for n, a in plan if n == "resolve_location"])
        ordered.extend([(n, a) for n, a in plan if n != "resolve_location"])
        seen: set[str] = set()
        plan = []
        for n, a in ordered:
            key = n + json.dumps(a, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            plan.append((n, a))

    for name, args in plan:
        if name == "resolve_location":
            res = _execute_tool(name, args)
            tool_results[name] = res
            audit.record_tool_call(name, args, "_tool_error" not in res)
            if "_tool_error" not in res:
                station_id = (
                    res.get("station_id")
                    or res.get("nearest_station_id")
                    or station_id
                )
                lat = res.get("latitude") or res.get("lat") or lat
                lon = res.get("longitude") or res.get("lon") or res.get("lng") or lon
                h3 = res.get("h3_cell") or res.get("h3") or h3
                if station_id:
                    state.station_id = station_id
                if h3:
                    state.h3_cell = h3
            continue

        if name == "get_forecast":
            if not station_id:
                continue
            args = {**args, "station_id": station_id, "city": city}
        if name in ("get_causal_explanation", "get_attribution"):
            args = {"city": city}
            if h3:
                args["h3_cell"] = h3
            elif lat is not None and lon is not None:
                args["lat"] = lat
                args["lon"] = lon
            else:
                continue
            if name == "get_causal_explanation":
                args["language"] = _normalize_language(state.language)
        if name == "run_whatif_scenario":
            args = {**args, "city": city, "scenario_text": args.get("scenario_text") or state.user_query}
            if h3:
                args["h3_cell"] = h3
            if station_id:
                args["station_id"] = station_id
            elif lat is not None and lon is not None:
                args["lat"] = lat
                args["lon"] = lon
        args = _inject_map_context_args(name, args, state)

        res = _execute_tool(name, args, use_cache=name != "run_whatif_scenario")
        tool_results[name] = res
        audit.record_tool_call(name, args, "_tool_error" not in res)
        if name == "run_whatif_scenario" and "_tool_error" not in res:
            audit.mark_whatif()

    # Enrich after resolve / map context
    if station_id and "get_forecast" not in tool_results:
        res = _execute_tool("get_forecast", {"station_id": station_id, "city": city})
        tool_results["get_forecast"] = res
        audit.record_tool_call(
            "get_forecast", {"station_id": station_id}, "_tool_error" not in res
        )
    if (h3 or (lat is not None and lon is not None)) and "get_attribution" not in tool_results:
        args = {"city": city}
        if h3:
            args["h3_cell"] = h3
        else:
            args["lat"] = lat
            args["lon"] = lon
        res = _execute_tool("get_attribution", args)
        tool_results["get_attribution"] = res
        audit.record_tool_call("get_attribution", args, "_tool_error" not in res)

    lang = _normalize_language(state.language)
    answer = deterministic_summary_from_tools(
        state.user_query, tool_results, language=lang
    )
    grounding = check_answer_grounding(answer, tool_results)
    state.response = answer
    state.structured_data = {
        "tool_results": tool_results,  # FULL results for map_actions / audit consumers
        "grounding": grounding,
        "path": "heuristic_fallback",
        "language": lang,
        "map_context": {
            "station_id": state.station_id or None,
            "h3_cell": state.h3_cell,
        }
        if state.map_context_provided
        else None,
    }
    state.tool_results = tool_results
    state.llm_status = "deterministic"
    state.fallback_used = True
    state.intent = Intent.dynamic_planning
    state.selected_agent = "grounded_tool_agent"
    audit.record_reasoning(
        "grounding",
        f"Heuristic path grounding: {'PASS' if grounding.get('passed') else 'FAIL'} ({grounding.get('reason')})",
        **{k: grounding.get(k) for k in ("passed", "reason", "unverified") if k in grounding},
    )


def run_grounded_tool_agent(state: AgentState, audit: AuditTrail) -> None:
    """Default free-text path: native tool-calling LLM with grounding."""
    state.selected_agent = "grounded_tool_agent"
    state.intent = Intent.dynamic_planning
    audit.set_agent("grounded_tool_agent")
    audit.set_intent("tool_agent")
    audit.record_reasoning("route", "Default path: native tool-calling agent (Phase 2)")
    state.language = _normalize_language(state.language)
    audit.record_reasoning(
        "language",
        f"Response language: {state.language}",
        language=state.language,
    )

    llm = get_llm_provider()
    if not llm.is_available:
        _run_heuristic_fallback(state, audit)
        return

    raw_history = list(state.conversation_history or [])[-6:]
    # Conditional history: only inject when follow-up detection says so (ambiguous → include)
    include_history = bool(raw_history) and is_follow_up_query(
        state.user_query or "", raw_history
    )
    history = raw_history if include_history else []
    if history and not audit.memory_turns_used:
        audit.set_memory_turns(len(history))
    elif raw_history and not include_history:
        audit.record_reasoning(
            "memory",
            "Prior turns present but query treated as standalone — history not injected",
            turns_available=len(raw_history),
        )

    tools = _tools_for_state(state)
    max_tool_calls = _max_tool_calls_for_state(state)
    if max_tool_calls is not None:
        audit.record_reasoning(
            "plan",
            f"Map-context tool-call budget: max {max_tool_calls} "
            f"({'compound' if is_compound_query(state.user_query or '') else 'simple'})",
            max_tool_calls=max_tool_calls,
        )
        if state.map_context_provided:
            audit.record_reasoning(
                "route",
                "resolve_location removed from tool schema (map context active)",
            )

    user_bits = [state.user_query]
    ctx = _build_context_block(state)
    if ctx:
        user_bits.append(ctx)
    if state.map_context_provided and (state.station_id or state.h3_cell):
        user_bits.append(
            "Use the provided Map context station_id/h3_cell directly for location tools. "
            "Do not call resolve_location for this place."
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    ]
    for turn in history:
        role = (turn.get("role") or "").strip().lower()
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role not in ("user", "assistant"):
            role = "user" if role != "assistant" else "assistant"
        if len(content) > 1200:
            content = content[:1180] + "…"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": "\n".join(user_bits)})

    tool_results: dict[str, Any] = {}  # FULL results (grounding / map_actions)
    tool_calls_executed = 0
    final_text: str | None = None
    hit_tool_cap = False

    for step in range(1, MAX_TOOL_STEPS + 1):
        budget_note = (
            f", tool_calls={tool_calls_executed}/{max_tool_calls}"
            if max_tool_calls is not None
            else ""
        )
        audit.record_reasoning(
            "plan", f"Tool-calling step {step}/{MAX_TOOL_STEPS}{budget_note}"
        )
        turn = llm.chat_with_tools(messages, tools)
        audit.set_llm_meta(
            getattr(llm, "last_provider", None),
            getattr(llm, "last_gemini_key_index", None)
            or getattr(llm, "last_groq_key_index", None),
        )
        if getattr(llm, "last_fallback_note", None):
            audit.record_reasoning("llm", str(llm.last_fallback_note))

        if turn is None:
            audit.record_reasoning(
                "llm_error", "chat_with_tools returned None — heuristic fallback"
            )
            _run_heuristic_fallback(state, audit)
            return

        content = turn.get("content")
        tool_calls = turn.get("tool_calls") or []

        if not tool_calls:
            final_text = (content or "").strip()
            audit.record_reasoning("final_answer", "Model returned final text (no tool calls)")
            break

        # Append assistant message with tool_calls (OpenAI format)
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments") or {}),
                    },
                }
                for tc in tool_calls
            ],
        }
        messages.append(assistant_msg)

        for tc in tool_calls:
            # Enforce map-context tool-call budget before executing more tools
            if max_tool_calls is not None and tool_calls_executed >= max_tool_calls:
                hit_tool_cap = True
                audit.record_reasoning(
                    "plan",
                    f"Tool-call budget {max_tool_calls} reached — stopping further tools",
                )
                break

            name = tc["name"]
            args = dict(tc.get("arguments") or {})

            # Hard block resolve_location when map context active (schema already filtered)
            if (
                name == "resolve_location"
                and state.map_context_provided
                and (state.station_id or state.h3_cell)
            ):
                synthetic = {
                    "success": True,
                    "station_id": state.station_id or None,
                    "h3_cell": state.h3_cell,
                    "resolution_method": "map_context",
                    "note": "Map context active; resolve_location not available — using provided ids",
                }
                audit.record_tool_call(name, {**args, "_skipped": "map_context"}, True)
                tool_results[name] = synthetic
                tool_calls_executed += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": summarize_tool_result_for_llm(name, synthetic),
                    }
                )
                continue

            if "city" not in args and name not in ("resolve_location", "search_policy_guidance"):
                args = {**args, "city": state.city or "bengaluru"}
            args = _inject_map_context_args(name, args, state)
            if "top_k" in args:
                try:
                    args["top_k"] = max(1, min(20, int(args["top_k"])))
                except (TypeError, ValueError):
                    args["top_k"] = 10
            if name == "run_whatif_scenario" and not args.get("scenario_text"):
                args["scenario_text"] = state.user_query

            res = _execute_tool(name, args, use_cache=name != "run_whatif_scenario")
            if not isinstance(res, dict):
                res = {"result": res}
            success = "_tool_error" not in res
            from_cache = bool(res.get("_from_tool_cache"))
            audit.record_tool_call(name, args, success)
            tool_calls_executed += 1
            if from_cache:
                audit.record_reasoning("cache", f"Tool result cache hit: {name}")
            if name == "run_whatif_scenario" and success:
                audit.mark_whatif()
            # FULL result for grounding / map_actions
            tool_results[name] = res

            if name == "resolve_location" and success:
                sid = res.get("station_id") or res.get("nearest_station_id")
                if sid:
                    state.station_id = sid
                h3 = res.get("h3_cell") or res.get("h3")
                if h3:
                    state.h3_cell = h3

            # TRIMMED summary for LLM history only
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": summarize_tool_result_for_llm(name, res),
                }
            )

        if hit_tool_cap or (
            max_tool_calls is not None and tool_calls_executed >= max_tool_calls
        ):
            hit_tool_cap = True
            final_text = _compose_partial_answer(
                state,
                audit,
                llm,
                tool_results,
                reason=(
                    f"Map-context tool-call budget ({max_tool_calls}) reached after "
                    f"{tool_calls_executed} tool call(s); best-effort answer composed"
                ),
            )
            break

        if step >= MAX_TOOL_STEPS:
            audit.record_reasoning(
                "plan",
                f"Step cap {MAX_TOOL_STEPS} reached — requesting final answer",
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have reached the tool step limit. Produce your final natural-language "
                        "answer NOW using only the tool results above. Do not invent numbers. "
                        "Write coherent prose, not a JSON dump."
                    ),
                }
            )
            lang = _normalize_language(state.language)
            lang_name = {"en": "English", "hi": "Hindi", "kn": "Kannada"}.get(lang, "English")
            slim = {
                k: json.loads(summarize_tool_result_for_llm(k, v))
                if isinstance(v, dict)
                else v
                for k, v in tool_results.items()
            }
            summary = llm.summarize(
                "Using only the tool data provided, write the final natural-language answer "
                f"to the user query: {state.user_query!r}. Do not invent numbers. "
                f"Write the answer in {lang_name} (language={lang}). "
                "Keep PM2.5, AQI, CPCB, station IDs, and H3 IDs in English. "
                "Write coherent prose, not raw JSON.",
                {"tool_results": slim, "language": lang},
                system_prompt=AGENT_SYSTEM_PROMPT,
            )
            if summary:
                final_text = summary.strip()
                audit.mark_partial_response(
                    f"LLM step cap {MAX_TOOL_STEPS} — composed final answer from gathered tools"
                )
            elif content:
                final_text = content.strip()
                audit.mark_partial_response(f"LLM step cap {MAX_TOOL_STEPS} — used last content")
            else:
                final_text = _compose_partial_answer(
                    state,
                    audit,
                    llm,
                    tool_results,
                    reason=f"LLM step cap {MAX_TOOL_STEPS} without final text",
                )
            break

    if not final_text:
        final_text = _compose_partial_answer(
            state,
            audit,
            llm,
            tool_results,
            reason="No final model text after tool loop — best-effort composition",
        )
        audit.record_reasoning("fallback", "No final model text — partial/deterministic composition")

    # Grounding check uses FULL tool_results (not trimmed)
    grounding = check_answer_grounding(final_text, tool_results)
    audit.record_reasoning(
        "grounding",
        f"Grounding {'PASS' if grounding.get('passed') else 'FAIL'}: {grounding.get('reason')}",
        passed=grounding.get("passed"),
        unverified=grounding.get("unverified"),
    )

    if not grounding.get("passed"):
        audit.record_reasoning("grounding", "Retry: strict ground-only instruction")
        messages.append({"role": "assistant", "content": final_text})
        messages.append(
            {
                "role": "user",
                "content": (
                    "GROUNDING FAILURE: your previous answer used numbers not present in tool data "
                    f"(unverified: {grounding.get('unverified')}). "
                    "Rewrite using ONLY numbers that appear in the tool results. "
                    "Write natural-language prose. If you cannot, summarize the tool results factually."
                ),
            }
        )
        slim = {
            k: json.loads(summarize_tool_result_for_llm(k, v))
            if isinstance(v, dict)
            else v
            for k, v in tool_results.items()
        }
        retry_text = llm.summarize(
            (
                "GROUNDING FAILURE: rewrite the answer using ONLY numbers present in tool_results. "
                f"Unverified tokens were: {grounding.get('unverified')}. "
                f"User query: {state.user_query!r}. Write coherent natural-language prose."
            ),
            {"tool_results": slim, "previous_answer": final_text},
            system_prompt=AGENT_SYSTEM_PROMPT,
        )
        if retry_text:
            retry_text = retry_text.strip()
            g2 = check_answer_grounding(retry_text, tool_results)
            audit.record_reasoning(
                "grounding",
                f"Retry grounding {'PASS' if g2.get('passed') else 'FAIL'}",
                passed=g2.get("passed"),
            )
            if g2.get("passed"):
                final_text = retry_text
                grounding = g2
            else:
                final_text = deterministic_summary_from_tools(
                    state.user_query, tool_results, language=state.language
                )
                grounding = check_answer_grounding(final_text, tool_results)
                state.fallback_used = True
                audit.record_reasoning(
                    "fallback", "Grounding failed twice — deterministic tool summary"
                )
        else:
            final_text = deterministic_summary_from_tools(
                state.user_query, tool_results, language=state.language
            )
            grounding = check_answer_grounding(final_text, tool_results)
            state.fallback_used = True

    state.response = final_text
    state.structured_data = {
        "tool_results": tool_results,  # FULL for map_actions extractors
        "grounding": grounding,
        "path": "native_tool_agent",
        "language": state.language,
        "provider": getattr(llm, "last_provider", None),
        "tool_calls_executed": tool_calls_executed,
        "partial_response": audit.partial_response,
        "map_context": {
            "station_id": state.station_id or None,
            "h3_cell": state.h3_cell,
        }
        if state.map_context_provided
        else None,
    }
    state.tool_results = tool_results
    state.llm_status = "hosted" if not state.fallback_used else "deterministic"
    if tool_results.get("search_policy_guidance", {}).get("results") or tool_results.get(
        "search_policy_guidance", {}
    ).get("retrieval_backend"):
        audit.set_knowledge(
            True,
            backend=tool_results.get("search_policy_guidance", {}).get("retrieval_backend"),
            chunk_count=len(tool_results.get("search_policy_guidance", {}).get("results") or []),
        )
