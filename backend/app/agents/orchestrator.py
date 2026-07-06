from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.app.agents.audit import AuditTrail
from backend.app.agents.citizen_advisory_agent import run_citizen_advisory_agent
from backend.app.agents.city_briefing_agent import run_city_briefing_agent
from backend.app.agents.enforcement_planning_agent import run_enforcement_planning_agent
from backend.app.agents.forecast_evidence_agent import run_forecast_evidence_agent
from backend.app.agents.llm_provider import get_llm_provider
from backend.app.agents.state import AgentState, Intent
from backend.app.config import ADVISORY_PROFILES, SUPPORTED_CITIES, SUPPORTED_LANGUAGES
from backend.app.services.artifact_adapter import UnknownStationError, _validate_station

logger = logging.getLogger(__name__)


def _detect_intent(
    query: str,
    explicit_intent: str | None = None,
    station_id: str = "",
) -> Intent:
    if explicit_intent:
        intent_map = {
            "station_explanation": Intent.station_explanation,
            "station_confidence": Intent.station_confidence,
            "inspection_plan": Intent.inspection_plan,
            "citizen_guidance": Intent.citizen_guidance,
            "city_briefing": Intent.city_briefing,
        }
        return intent_map.get(explicit_intent, Intent.unsupported)

    q = query.lower().strip()

    if not q:
        return Intent.unsupported

    has_station = bool(station_id)
    has_city_query = any(c in q for c in ["city", "bengaluru"])

    if has_station and any(w in q for w in ["confidence", "reliable", "trust", "reliability"]):
        return Intent.station_confidence

    if has_station and any(w in q for w in ["why", "explain", "evidence", "how is", "forecast", "change"]):
        return Intent.station_explanation

    if has_station and any(w in q for w in ["advisory", "guidance", "health", "breathe", "should i", "safe"]):
        return Intent.citizen_guidance

    if has_city_query and any(w in q for w in ["inspection", "priority", "enforce", "plan", "rank"]):
        return Intent.inspection_plan

    if has_city_query and any(w in q for w in ["briefing", "summary", "overview", "situation", "status"]):
        return Intent.city_briefing

    if has_station and not has_city_query:
        return Intent.station_explanation

    if has_city_query:
        return Intent.city_briefing

    return Intent.unsupported


def _route_intent(intent: Intent) -> str:
    mapping = {
        Intent.station_explanation: "forecast_evidence_agent",
        Intent.station_confidence: "forecast_evidence_agent",
        Intent.inspection_plan: "enforcement_planning_agent",
        Intent.citizen_guidance: "citizen_advisory_agent",
        Intent.city_briefing: "city_briefing_agent",
    }
    return mapping.get(intent, "unknown")


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

    if state.profile not in ADVISORY_PROFILES:
        warnings.append(f"Profile '{state.profile}' is not valid. Using default: general")
        state.profile = "general"

    if state.language not in SUPPORTED_LANGUAGES:
        warnings.append(f"Language '{state.language}' is not supported. Using default: en")
        state.language = "en"

    return warnings


def _validate_response(state: AgentState) -> list[str]:
    warnings: list[str] = []
    data = state.structured_data or {}

    if state.intent in (Intent.station_explanation, Intent.station_confidence):
        if data.get("forecast_engine"):
            pass
        else:
            warnings.append("Response missing forecast_engine field")
        if data.get("confidence_level"):
            pass
        elif "confidence" in data and data["confidence"].get("confidence_level"):
            pass
        else:
            warnings.append("Response missing confidence_level")

    if state.intent == Intent.inspection_plan:
        import re
        from backend.app.config import INVESTIGATION_DISCLAIMER
        has_disclaimer = False
        if state.response:
            has_disclaimer = INVESTIGATION_DISCLAIMER in state.response
        if not has_disclaimer:
            ranked = data.get("ranked_stations", [])
            has_disclaimer = any(
                INVESTIGATION_DISCLAIMER in str(s.get("caveats", []))
                for s in ranked
            )
        if not has_disclaimer:
            warnings.append("Response missing investigation disclaimer")

    if state.intent == Intent.citizen_guidance:
        from backend.app.config import MEDICAL_DISCLAIMER
        if state.response and MEDICAL_DISCLAIMER not in state.response:
            if data.get("medical_disclaimer") != MEDICAL_DISCLAIMER:
                warnings.append("Response missing medical disclaimer")

    if state.intent == Intent.city_briefing:
        limitations = data.get("data_limitations", [])
        if not limitations:
            warnings.append("Response missing data limitations")
        has_coverage = any("monitored stations" in str(l).lower() for l in limitations)
        if not has_coverage:
            warnings.append("Response missing citywide coverage disclaimer")

    return warnings


def run_orchestrator(
    station_id: str = "",
    city: str = "bengaluru",
    query: str = "",
    profile: str = "general",
    language: str = "en",
    top_k: int = 5,
    explicit_intent: str | None = None,
) -> dict[str, Any]:

    request_id = str(uuid.uuid4())

    state = AgentState(
        request_id=request_id,
        user_query=query,
        city=city,
        station_id=station_id,
        profile=profile,
        language=language,
        top_k=top_k,
    )

    audit = AuditTrail(request_id)

    input_warnings = _validate_input(state)
    for w in input_warnings:
        state.warnings.append(w)
        audit.add_warning(w)

    intent = _detect_intent(query, explicit_intent, station_id)
    state.intent = intent
    audit.set_intent(intent.value)

    if intent == Intent.unsupported:
        state.selected_agent = "none"
        state.response = "I could not determine what you are asking about. Please ask about air quality forecasts, evidence, confidence, inspection priorities, health advisories, or city briefings."
        state.structured_data = {}
        audit.set_agent("none")
        llm = get_llm_provider()

        if llm.is_available:
            audit.set_llm_mode("hosted")
            llm_response = llm.summarize(
                f"The user asked: '{query}'. This query could not be routed to any air quality agent. Provide a helpful response suggesting available capabilities.",
                {"available_intents": [e.value for e in Intent if e != Intent.unsupported]},
            )
            if llm_response:
                state.response = llm_response
                state.llm_status = "hosted"
            else:
                state.llm_status = "fallback"
                audit.set_fallback(True)
                state.fallback_used = True
        else:
            audit.set_llm_mode("deterministic")
            state.llm_status = "deterministic"

        return _build_response(state, audit)

    agent_name = _route_intent(intent)
    state.selected_agent = agent_name
    audit.set_agent(agent_name)

    llm = get_llm_provider()
    llm_mode = "deterministic"
    fallback_used = False

    if intent == Intent.station_explanation or intent == Intent.station_confidence:
        run_forecast_evidence_agent(state, audit)
    elif intent == Intent.inspection_plan:
        run_enforcement_planning_agent(state, audit)
    elif intent == Intent.citizen_guidance:
        run_citizen_advisory_agent(state, audit)
    elif intent == Intent.city_briefing:
        run_city_briefing_agent(state, audit)

    response_warnings = _validate_response(state)
    for w in response_warnings:
        state.warnings.append(w)
        audit.add_warning(w)

    if response_warnings:
        if llm.is_available:
            llm_mode = "fallback"
            fallback_used = True
        else:
            llm_mode = "deterministic"
            from backend.app.agents.fallback_renderer import (
                render_citizen_advisory,
                render_city_briefing,
                render_inspection_plan,
                render_station_explanation,
            )
            if intent == Intent.station_explanation:
                state.response = render_station_explanation(state.structured_data or {})
            elif intent == Intent.station_confidence:
                state.response = render_confidence_summary(state.structured_data or {})
            elif intent == Intent.inspection_plan:
                state.response = render_inspection_plan(state.structured_data or {})
            elif intent == Intent.citizen_guidance:
                state.response = render_citizen_advisory(state.structured_data or {})
            elif intent == Intent.city_briefing:
                state.response = render_city_briefing(state.structured_data or {})

    if llm.is_available and not response_warnings:
        llm_response = llm.summarize(
            f"Create a concise natural language response for: '{query}'",
            state.structured_data or {},
        )
        if llm_response:
            state.response = llm_response
            state.llm_status = "hosted"
            llm_mode = "hosted"
        else:
            llm_mode = "deterministic"
            state.llm_status = "deterministic"
    else:
        state.llm_status = llm_mode

    audit.set_llm_mode(llm_mode)
    audit.set_fallback(fallback_used)
    state.fallback_used = fallback_used

    return _build_response(state, audit)


def _render_confidence_summary(data):
    from backend.app.agents.fallback_renderer import render_confidence_summary
    return render_confidence_summary(data)


def _build_response(state: AgentState, audit: AuditTrail) -> dict[str, Any]:
    return {
        "request_id": state.request_id,
        "intent": state.intent.value,
        "selected_agent": state.selected_agent,
        "answer": state.response,
        "structured_data": state.structured_data,
        "warnings": state.warnings,
        "audit_trail": audit.to_dict(),
        "llm_mode": state.llm_status,
        "fallback_used": state.fallback_used,
    }
