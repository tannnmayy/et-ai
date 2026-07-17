"""Copilot orchestrator — Phase 2.

Architecture:
  1. Semantic + exact response cache
  2. Narrow deterministic fast path
     (explicit station_id + simple forecast/confidence/explain only)
  3. DEFAULT: grounded native tool-calling agent (Groq-primary)
  4. Grounding recorded in audit; never bare generic refuse when tools can help
  5. Optional Map context (station_id / h3_cell) preferred over re-resolving

Legacy keyword routing is NOT used for free-text anymore.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from backend.app.agents.audit import AuditTrail
from backend.app.agents.citizen_advisory_agent import run_citizen_advisory_agent
from backend.app.agents.city_briefing_agent import run_city_briefing_agent
from backend.app.agents.conversation_fallback import (
    infer_station_id,
    is_compound_query,
    is_follow_up_query,
)
from backend.app.agents.enforcement_planning_agent import run_enforcement_planning_agent
from backend.app.agents.forecast_evidence_agent import run_forecast_evidence_agent
from backend.app.agents.grounded_tool_agent import run_grounded_tool_agent
from backend.app.agents.llm_provider import get_llm_provider
from backend.app.agents.state import AgentState, Intent
from backend.app.config import (
    ADVISORY_PROFILES,
    SUPPORTED_CITIES,
    SUPPORTED_LANGUAGES,
    TRAVEL_PROFILES,
)
from backend.app.services.artifact_adapter import UnknownStationError, _validate_station

logger = logging.getLogger(__name__)

# Re-export for callers/tests that import is_compound_query from orchestrator
__all__ = ["run_orchestrator", "is_compound_query", "_is_simple_station_query", "_detect_intent"]


def _is_simple_station_query(query: str) -> bool:
    """Conservative fast-path gate: only pure forecast / confidence reads.

    Must NOT match 'Why is air quality poor near Peenya right now?' even when
    a station_id was inferred — those need attribution / tool agent.
    """
    q = query.lower().strip()
    if not q or len(q) > 120:
        return False

    # Hard exclude: causal, sources, enforcement, policy, multi-clause
    deny = (
        "why",
        "reason",
        "because",
        "cause",
        "source",
        "pollut",
        "poor",
        "bad",
        "worse",
        "worst",
        "near ",
        " around",
        "enforce",
        "inspect",
        "officer",
        "dispatch",
        "hotspot",
        "priority",
        "policy",
        "cpcb",
        "kspcb",
        "ncap",
        "guideline",
        "regulation",
        "compare",
        "neighbourhood",
        "neighborhood",
        "attribution",
        "traffic",
        "construction",
        "industrial",
        "burning",
        "dust",
        "where should",
        " and ",
        " also ",
        " vs ",
        "versus",
        "what if",
        "what-if",
        "counterfactual",
        "scenario",
        "if we",
        "reduce by",
        "drop by",
    )
    if any(w in q for w in deny):
        return False
    if is_compound_query(q):
        return False

    # Allow only clear forecast / confidence phrasing
    allow = (
        "forecast",
        "prediction",
        "predicted",
        "next 24",
        "24h",
        "24-hour",
        "24 hour",
        "confidence",
        "reliable",
        "reliability",
        "trust the",
        "data quality",
        "what is the pm",
        "what is pm",
        "pm2.5 reading",
        "pm25 reading",
        "current reading",
        "station reading",
        "explain forecast",
        "what will the pm",
        "what will pm",
    )
    return any(w in q for w in allow)


def _validate_input(state: AgentState) -> list[str]:
    warnings: list[str] = []

    if state.city.lower().strip() not in SUPPORTED_CITIES:
        warnings.append(f"City '{state.city}' is not supported. Using default: bengaluru")
        state.city = "bengaluru"

    if state.station_id:
        try:
            _validate_station(state.station_id)
        except UnknownStationError:
            warnings.append(f"Station '{state.station_id}' is unknown")
            state.station_id = ""

    all_profiles = list(set(ADVISORY_PROFILES + TRAVEL_PROFILES))
    if state.profile not in all_profiles:
        warnings.append(f"Profile '{state.profile}' is not valid. Using default: general")
        state.profile = "general"

    # Normalize case (EN → en) and validate
    state.language = (state.language or "en").strip().lower()
    if state.language not in SUPPORTED_LANGUAGES:
        warnings.append(f"Language '{state.language}' is not supported. Using default: en")
        state.language = "en"

    return warnings


def _infer_response_mode(state: AgentState, audit: AuditTrail) -> str:
    """Derive UI-facing response mode badge."""
    if audit.response_mode:
        return audit.response_mode
    agent = (state.selected_agent or "").lower()
    path = ""
    if isinstance(state.structured_data, dict):
        path = str(state.structured_data.get("path") or "")
    if path == "heuristic_fallback" or (
        state.fallback_used and agent == "grounded_tool_agent" and state.llm_status == "deterministic"
    ):
        return "heuristic_fallback"
    if agent == "forecast_evidence_agent" and state.llm_status == "deterministic":
        return "fast_path"
    if agent == "grounded_tool_agent":
        return "tool_agent"
    if agent:
        return agent
    return "unknown"


def _normalize_history(
    conversation_history: list[dict[str, Any]] | None,
    *,
    max_turns: int = 6,
) -> list[dict[str, str]]:
    """Keep last N user/assistant turns; drop empty / invalid roles."""
    if not conversation_history:
        return []
    cleaned: list[dict[str, str]] = []
    for item in conversation_history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        cleaned.append({"role": role, "content": content[:2000]})
    return cleaned[-max_turns:]


def run_orchestrator(
    station_id: str = "",
    city: str = "bengaluru",
    query: str = "",
    profile: str = "general",
    language: str = "en",
    top_k: int = 5,
    explicit_intent: str | None = None,
    force_dynamic_planning: bool = False,
    h3_cell: str | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    history = _normalize_history(conversation_history)
    # Canonical language for cache + agent (accept EN/HI/KN from clients)
    language = (language or "en").strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        language = "en"

    # --- Cache (exact + semantic) ---
    # Skip cache only for genuine follow-ups (not merely because history array is non-empty).
    # Standalone questions remain cache-eligible even when the client sends prior turns.
    ckey: str | None = None
    skey: str | None = None
    try:
        from backend.app.services.copilot_cache_service import (
            cache_key,
            lookup_cached_response,
            semantic_cache_key,
            set_cached_response,
        )

        follow_up = bool(history) and is_follow_up_query(query, history)
        if not follow_up:
            ckey = cache_key(
                query,
                city=city,
                station_id=station_id,
                h3_cell=h3_cell,
                profile=profile,
                language=language,
                force_dynamic_planning=force_dynamic_planning,
            )
            skey = semantic_cache_key(
                query,
                city=city,
                station_id=station_id,
                h3_cell=h3_cell,
                profile=profile,
                language=language,
                force_dynamic_planning=force_dynamic_planning,
            )
            cached, cache_meta = lookup_cached_response(ckey, semantic_key=skey)
        else:
            cached, cache_meta = None, {}
        if cached is not None:
            cached = dict(cached)
            cached["request_id"] = str(uuid.uuid4())
            trail = dict(cached.get("audit_trail") or {})
            trail["request_id"] = cached["request_id"]
            trail["cache_hit"] = True
            trail["cache_key"] = cache_meta.get("cache_key") or ckey
            trail["cache_kind"] = cache_meta.get("cache_kind") or "exact"
            # Preserve original mode; label as cached for UI
            original_mode = trail.get("response_mode") or cached.get("response_mode")
            trail["response_mode"] = original_mode or "tool_agent"
            warnings = list(trail.get("warnings") or [])
            if "served_from_response_cache" not in warnings:
                warnings.append("served_from_response_cache")
            kind = cache_meta.get("cache_kind") or "exact"
            if kind == "semantic" and "served_from_semantic_cache" not in warnings:
                warnings.append("served_from_semantic_cache")
            trail["warnings"] = warnings
            trace = list(trail.get("reasoning_trace") or [])
            trace.insert(
                0,
                {
                    "type": "cache",
                    "detail": (
                        f"Served from Copilot response cache ({kind})"
                        + (f" key={trail['cache_key'][:12]}…" if trail.get("cache_key") else "")
                    ),
                    "cache_key": trail.get("cache_key"),
                    "cache_kind": kind,
                },
            )
            trail["reasoning_trace"] = trace
            cached["audit_trail"] = trail
            cached["warnings"] = list(
                dict.fromkeys(
                    list(cached.get("warnings") or [])
                    + ["served_from_response_cache"]
                    + (["served_from_semantic_cache"] if kind == "semantic" else [])
                )
            )
            cached["cache_hit"] = True
            cached["response_mode"] = trail.get("response_mode")
            return cached
    except Exception as exc:
        logger.debug("Response cache lookup skipped: %s", exc)
        ckey = None
        skey = None

    request_id = str(uuid.uuid4())
    client_station = (station_id or "").strip()
    client_h3 = (h3_cell or "").strip() or None
    map_context = bool(client_station or client_h3)

    state = AgentState(
        request_id=request_id,
        user_query=query,
        city=city,
        station_id=client_station,
        h3_cell=client_h3,
        profile=profile,
        language=language,
        top_k=top_k,
        map_context_provided=map_context,
        conversation_history=history,
    )
    audit = AuditTrail(request_id)
    if ckey:
        audit.cache_key = ckey
        audit.cache_hit = False
        audit.cache_kind = "miss"
    if history:
        audit.set_memory_turns(len(history))
    if session_id:
        audit.record_reasoning("route", f"Client session_id={session_id[:36]}")

    # Map / Enforcement context — prefer over re-resolve
    if map_context:
        bits = []
        if client_station:
            bits.append(f"station_id={client_station}")
        if client_h3:
            bits.append(f"h3_cell={client_h3}")
        audit.record_reasoning(
            "route",
            "Client Map context provided — prefer over resolve_location: " + ", ".join(bits),
        )
        state.structured_data = {
            "map_context": {
                "station_id": client_station or None,
                "h3_cell": client_h3,
            }
        }

    # Soft station recovery for fast path only when no client station
    if not state.station_id:
        inferred = infer_station_id(query)
        if inferred:
            state.station_id = inferred
            audit.record_reasoning("route", f"Inferred station_id={inferred} from query text")

    for w in _validate_input(state):
        state.warnings.append(w)
        audit.add_warning(w)

    llm = get_llm_provider()

    # Explicit REST intents — dedicated agents (backward compatible API)
    if explicit_intent == "station_explanation" and state.station_id:
        state.intent = Intent.station_explanation
        state.selected_agent = "forecast_evidence_agent"
        audit.set_intent(state.intent.value)
        audit.set_agent(state.selected_agent)
        run_forecast_evidence_agent(state, audit)
        state.llm_status = "deterministic"
        audit.set_llm_mode("deterministic")
        audit.set_fallback(False)
        audit.set_response_mode("fast_path")
        return _finalize(state, audit, ckey, skey)

    if explicit_intent == "station_confidence" and state.station_id:
        state.intent = Intent.station_confidence
        state.selected_agent = "forecast_evidence_agent"
        audit.set_intent(state.intent.value)
        audit.set_agent(state.selected_agent)
        run_forecast_evidence_agent(state, audit)
        state.llm_status = "deterministic"
        audit.set_llm_mode("deterministic")
        audit.set_fallback(False)
        audit.set_response_mode("fast_path")
        return _finalize(state, audit, ckey, skey)

    if explicit_intent == "citizen_guidance" and state.station_id:
        state.intent = Intent.citizen_guidance
        state.selected_agent = "citizen_advisory_agent"
        audit.set_intent(state.intent.value)
        audit.set_agent(state.selected_agent)
        run_citizen_advisory_agent(state, audit)
        state.llm_status = "deterministic"
        audit.set_llm_mode("deterministic")
        audit.set_fallback(False)
        audit.set_response_mode("fast_path")
        return _finalize(state, audit, ckey, skey)

    if explicit_intent == "inspection_plan":
        state.intent = Intent.inspection_plan
        state.selected_agent = "enforcement_planning_agent"
        audit.set_intent(state.intent.value)
        audit.set_agent(state.selected_agent)
        run_enforcement_planning_agent(state, audit)
        state.llm_status = "deterministic"
        audit.set_llm_mode("deterministic")
        audit.set_fallback(False)
        audit.set_response_mode("fast_path")
        return _finalize(state, audit, ckey, skey)

    if explicit_intent == "city_briefing":
        state.intent = Intent.city_briefing
        state.selected_agent = "city_briefing_agent"
        audit.set_intent(state.intent.value)
        audit.set_agent(state.selected_agent)
        run_city_briefing_agent(state, audit)
        state.llm_status = "deterministic"
        audit.set_llm_mode("deterministic")
        audit.set_fallback(False)
        audit.set_response_mode("fast_path")
        return _finalize(state, audit, ckey, skey)

    # --- Narrow deterministic fast path ---
    use_fast = (
        bool(state.station_id)
        and not force_dynamic_planning
        and explicit_intent in (None, "station_explanation", "station_confidence")
        and _is_simple_station_query(query)
    )
    if use_fast:
        audit.record_reasoning(
            "route",
            "Fast path: explicit/inferred station + simple forecast/explain query",
        )
        state.intent = (
            Intent.station_confidence
            if any(w in query.lower() for w in ("confidence", "reliable", "trust"))
            else Intent.station_explanation
        )
        state.selected_agent = "forecast_evidence_agent"
        audit.set_intent(state.intent.value)
        audit.set_agent(state.selected_agent)
        run_forecast_evidence_agent(state, audit)
        # Phase 1: do NOT LLM-rewrite grounded deterministic answers
        state.llm_status = "deterministic"
        audit.set_llm_mode("deterministic")
        audit.set_fallback(False)
        audit.set_response_mode("fast_path")
        return _finalize(state, audit, ckey, skey)

    # --- DEFAULT: native tool-calling agent ---
    if force_dynamic_planning:
        audit.record_reasoning("route", "Deep mode requested — tool-calling agent (native)")
    else:
        audit.record_reasoning(
            "route",
            "Default free-text path — native tool-calling agent (Groq-primary)",
        )

    run_grounded_tool_agent(state, audit)

    # Mode: heuristic vs tool agent (agent sets path in structured_data)
    path = ""
    if isinstance(state.structured_data, dict):
        path = str(state.structured_data.get("path") or "")
    if path == "heuristic_fallback":
        audit.set_response_mode("heuristic_fallback")
    else:
        audit.set_response_mode("tool_agent")

    audit.set_llm_mode(state.llm_status)
    audit.set_fallback(state.fallback_used)
    audit.set_llm_meta(
        getattr(llm, "last_provider", None),
        getattr(llm, "last_gemini_key_index", None)
        or getattr(llm, "last_groq_key_index", None),
    )

    return _finalize(state, audit, ckey, skey)


def _finalize(
    state: AgentState,
    audit: AuditTrail,
    ckey: str | None,
    skey: str | None = None,
) -> dict[str, Any]:
    if not (state.response or "").strip():
        state.response = (
            "I could not produce an answer from available tools. "
            "Try asking about enforcement priorities, a named Bengaluru locality "
            "(e.g. Peenya), a city briefing, weather, or CPCB construction dust rules."
        )
        state.fallback_used = True
        audit.set_fallback(True)

    mode = _infer_response_mode(state, audit)
    audit.set_response_mode(mode)

    # Preserve map context in structured_data if agent overwrote it
    sd = state.structured_data if isinstance(state.structured_data, dict) else {}
    if state.map_context_provided and "map_context" not in sd:
        sd = {
            **sd,
            "map_context": {
                "station_id": state.station_id or None,
                "h3_cell": state.h3_cell,
            },
        }
        state.structured_data = sd

    # Copilot → Map: structured highlight / focus instructions
    map_actions = None
    try:
        from backend.app.agents.map_actions import extract_map_actions

        map_actions = extract_map_actions(
            tool_results=state.tool_results or (sd.get("tool_results") if sd else None),
            state_station_id=state.station_id or "",
            state_h3_cell=state.h3_cell,
            structured_data=sd if isinstance(sd, dict) else None,
        )
        if map_actions:
            audit.record_reasoning(
                "map",
                (
                    f"Map actions: {len(map_actions.get('highlight_h3_cells') or [])} hex(es), "
                    f"{len(map_actions.get('highlight_stations') or [])} station(s)"
                ),
            )
            if isinstance(sd, dict):
                sd = {**sd, "map_actions": map_actions}
                state.structured_data = sd
    except Exception as exc:
        logger.debug("map_actions extraction skipped: %s", exc)
        map_actions = None

    response = {
        "request_id": state.request_id,
        "intent": state.intent.value if state.intent else "tool_agent",
        "selected_agent": state.selected_agent,
        "answer": state.response,
        "structured_data": state.structured_data,
        "warnings": state.warnings,
        "audit_trail": audit.to_dict(),
        "llm_mode": state.llm_status,
        "fallback_used": state.fallback_used,
        "cache_hit": False,
        "response_mode": mode,
        "map_actions": map_actions,
    }

    try:
        from backend.app.services.copilot_cache_service import set_cached_response

        # Don't cache empty / hard-fallback refuse for long
        if ckey and response.get("answer") and not _is_generic_refuse(response["answer"]):
            set_cached_response(ckey, response, query=state.user_query, semantic_key=skey)
    except Exception as exc:
        logger.debug("Response cache store skipped: %s", exc)

    return response


def _is_generic_refuse(text: str) -> bool:
    t = (text or "").lower()
    return "could not answer that question specifically from the available" in t


# Keep for tests that import _detect_intent — maps to a minimal compatibility shim
def _detect_intent(
    query: str,
    explicit_intent: str | None = None,
    station_id: str = "",
) -> Intent:
    """Compatibility shim for unit tests. Production free-text uses tool agent."""
    if explicit_intent:
        intent_map = {
            "station_explanation": Intent.station_explanation,
            "station_confidence": Intent.station_confidence,
            "inspection_plan": Intent.inspection_plan,
            "citizen_guidance": Intent.citizen_guidance,
            "city_briefing": Intent.city_briefing,
            "policy_guidance": Intent.policy_guidance,
            "weather_forecast": Intent.weather_forecast,
            "travel_readiness": Intent.travel_readiness,
            "spatial_context": Intent.spatial_context,
            "spatial_intelligence": Intent.spatial_intelligence,
            "neighbourhood_comparison": Intent.neighbourhood_comparison,
        }
        return intent_map.get(explicit_intent, Intent.unsupported)

    q = (query or "").lower().strip()
    if not q:
        return Intent.unsupported

    # Expanded keywords so existing tests and suggested-question regression still pass
    if station_id and any(w in q for w in ("confidence", "reliable", "trust")):
        return Intent.station_confidence
    if station_id and any(w in q for w in ("why", "explain", "forecast", "evidence")):
        return Intent.station_explanation
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
            "where should",
        )
    ):
        return Intent.inspection_plan
    if any(w in q for w in ("policy", "cpcb", "kspcb", "ncap", "guideline", "regulation")):
        return Intent.policy_guidance
    # Health / citizen advisory before travel ("safe to go outside")
    if any(
        w in q
        for w in (
            "safe to",
            "health",
            "advisory",
            "sensitive group",
            "asthma",
            "mask",
            "outdoor activity",
            "is it safe",
        )
    ):
        return Intent.citizen_guidance
    if any(w in q for w in ("travel", "commute", "bike", "outing", "readiness")):
        return Intent.travel_readiness
    if any(w in q for w in ("go outside",)) and station_id:
        return Intent.citizen_guidance
    if any(w in q for w in ("weather", "rain", "temperature", "humidity", "wind")):
        return Intent.weather_forecast
    if any(w in q for w in ("neighbourhood", "neighborhood", "where to live", "compare")):
        return Intent.neighbourhood_comparison
    if any(w in q for w in ("briefing", "overview", "situation")) or "bengaluru" in q:
        return Intent.city_briefing
    if station_id:
        return Intent.station_explanation
    # No AQI/city signal → unsupported (shim); production free-text uses tool agent directly
    aqi_ish = any(
        w in q
        for w in (
            "aqi",
            "pm2",
            "pollut",
            "air",
            "dust",
            "smog",
            "station",
            "hex",
            "peenya",
            "forecast",
        )
    )
    if not aqi_ish:
        return Intent.unsupported
    return Intent.dynamic_planning
