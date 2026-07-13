from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.app.agents.audit import AuditTrail
from backend.app.agents.citizen_advisory_agent import run_citizen_advisory_agent
from backend.app.agents.city_briefing_agent import run_city_briefing_agent
from backend.app.agents.conversation_fallback import infer_station_id, run_query_aware_fallback
from backend.app.agents.dynamic_planning_agent import run_dynamic_planning_agent
from backend.app.agents.enforcement_planning_agent import run_enforcement_planning_agent
from backend.app.agents.forecast_evidence_agent import run_forecast_evidence_agent
from backend.app.agents.llm_provider import get_llm_provider
from backend.app.agents.neighbourhood_decision_agent import run_neighbourhood_decision_agent
from backend.app.agents.policy_guidance_agent import run_policy_guidance_agent
from backend.app.agents.spatial_context_agent import run_spatial_context_agent
from backend.app.agents.spatial_intelligence_agent import run_spatial_intelligence_agent
from backend.app.agents.travel_readiness_agent import run_travel_readiness_agent
from backend.app.agents.state import AgentState, Intent
from backend.app.config import (
    ADVISORY_PROFILES,
    SUPPORTED_CITIES,
    SUPPORTED_LANGUAGES,
    TRAVEL_PROFILES,
)
from backend.app.services.artifact_adapter import UnknownStationError, _validate_station

logger = logging.getLogger(__name__)


_TRIGGER_GROUPS: list[tuple[str, list[str]]] = [
    ("why_explain", ["why", "explain", "evidence", "how is", "forecast", "change"]),
    ("confidence", ["confidence", "reliable", "trust", "reliability"]),
    ("advisory", ["advisory", "guidance", "health", "breathe", "should i", "safe"]),
    ("inspection", ["inspection", "priority", "enforce", "plan", "rank"]),
    ("spatial_intel", ["spatial intelligence", "intelligence around", "map-ready", "station intelligence"]),
    ("spatial_context", ["spatial", "geospatial", "road density", "land use", "land-use", "industrial context", "construction near", "facility near", "mapped", "nearest road"]),
    ("briefing", ["briefing", "summary", "overview", "situation", "status"]),
    ("travel", ["travel", "go outside", "go out", "bike", "two-wheeler", "two wheeler", "commute", "outing", "ride"]),
    ("weather", ["weather", "rain", "temperature", "humidity", "windy", "wind speed", "sunny", "storm", "thunder"]),
    ("neighbourhood", ["compare", "neighbourhood", "neighborhood", "suitability", "where to live", "best area", "candidate"]),
    ("policy", ["policy", "official source", "official guidance", "cpcb says", "who says", "guidance support", "what does", "show the policy"]),
]


def _is_compound_query(query: str) -> bool:
    q = query.lower().strip()
    if not q:
        return False
    matched_groups: set[str] = set()
    for group_name, triggers in _TRIGGER_GROUPS:
        if any(w in q for w in triggers):
            matched_groups.add(group_name)
    return len(matched_groups) >= 2


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
            "policy_guidance": Intent.policy_guidance,
            "weather_forecast": Intent.weather_forecast,
            "travel_readiness": Intent.travel_readiness,
            "spatial_context": Intent.spatial_context,
            "spatial_intelligence": Intent.spatial_intelligence,
            "neighbourhood_comparison": Intent.neighbourhood_comparison,
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

    if any(w in q for w in ["spatial intelligence", "intelligence around", "map-ready", "station intelligence"]):
        return Intent.spatial_intelligence

    if any(w in q for w in ["spatial", "geospatial", "road density", "land use", "land-use", "industrial context", "construction near", "facility near", "mapped", "nearest road"]):
        return Intent.spatial_context

    if has_city_query and any(w in q for w in ["briefing", "summary", "overview", "situation", "status"]):
        return Intent.city_briefing

    if has_station and not has_city_query:
        return Intent.station_explanation

    if any(w in q for w in ["travel", "go outside", "go out", "bike", "two-wheeler", "two wheeler", "commute", "outing", "ride"]):
        return Intent.travel_readiness

    if any(w in q for w in ["weather", "rain", "temperature", "humidity", "windy", "wind speed", "sunny", "storm", "thunder"]):
        return Intent.weather_forecast

    if any(w in q for w in ["compare", "neighbourhood", "neighborhood", "suitability", "where to live", "best area", "candidate"]):
        return Intent.neighbourhood_comparison

    if any(w in q for w in ["policy", "official source", "official guidance", "cpcb says", "who says", "guidance support", "what does", "show the policy"]):
        return Intent.policy_guidance

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
        Intent.policy_guidance: "policy_guidance_agent",
        Intent.weather_forecast: "travel_readiness_agent",
        Intent.travel_readiness: "travel_readiness_agent",
        Intent.spatial_context: "spatial_context_agent",
        Intent.spatial_intelligence: "spatial_intelligence_agent",
        Intent.neighbourhood_comparison: "neighbourhood_decision_agent",
        Intent.dynamic_planning: "dynamic_planning_agent",
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

    all_profiles = list(set(ADVISORY_PROFILES + TRAVEL_PROFILES))
    if state.profile not in all_profiles:
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
    force_dynamic_planning: bool = False,
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

    # The web client sends free text only. Recover a station from a locality
    # name (for example, "Peenya") before routing instead of requiring a
    # station_id that the UI never supplies.
    if not state.station_id:
        state.station_id = infer_station_id(query) or ""

    input_warnings = _validate_input(state)
    for w in input_warnings:
        state.warnings.append(w)
        audit.add_warning(w)

    intent = _detect_intent(query, explicit_intent, state.station_id)
    state.intent = intent
    audit.set_intent(intent.value)

    llm = get_llm_provider()

    # Explicit override: user opted into deep reasoning
    if force_dynamic_planning:
        intent = Intent.dynamic_planning
        state.intent = intent
        audit.set_intent(intent.value)

    # Automatic planning is reserved for compound questions. Unmatched short
    # questions are handled immediately by the query-aware fallback instead of
    # waiting for a provider that may be temporarily unreachable.
    elif not explicit_intent and llm.is_available and _is_compound_query(query):
        intent = Intent.dynamic_planning
        state.intent = intent
        audit.set_intent(intent.value)

    if intent == Intent.unsupported:
        state.selected_agent = "query_aware_fallback"
        audit.set_agent(state.selected_agent)
        run_query_aware_fallback(state, audit)
        audit.set_llm_mode(state.llm_status)
        audit.set_fallback(state.fallback_used)
        return _build_response(state, audit)

    # A free-text "why is it polluted near <station>" question needs the
    # station's mapped context, not merely a generic forecast explanation.
    if (
        not explicit_intent
        and intent != Intent.dynamic_planning
        and state.station_id
        and any(term in query.lower() for term in ("pollut", "why is the air", "reason for aqi", "reason for air"))
    ):
        state.selected_agent = "query_aware_fallback"
        audit.set_agent(state.selected_agent)
        run_query_aware_fallback(state, audit)
        audit.set_llm_mode(state.llm_status)
        audit.set_fallback(state.fallback_used)
        return _build_response(state, audit)

    agent_name = _route_intent(intent)
    state.selected_agent = agent_name
    audit.set_agent(agent_name)

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
    elif intent == Intent.policy_guidance:
        run_policy_guidance_agent(state, audit)
    elif intent == Intent.spatial_context:
        run_spatial_context_agent(state, audit)
    elif intent == Intent.spatial_intelligence:
        run_spatial_intelligence_agent(state, audit)
    elif intent == Intent.neighbourhood_comparison:
        run_neighbourhood_decision_agent(state, audit)
    elif intent == Intent.dynamic_planning:
        run_dynamic_planning_agent(state, audit)
    elif intent == Intent.weather_forecast or intent == Intent.travel_readiness:
        run_travel_readiness_agent(state, audit)

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
                render_neighbourhood_comparison,
                render_spatial_intelligence,
                render_station_explanation,
                render_travel_readiness,
                render_weather_forecast,
                render_weather_summary,
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
            elif intent == Intent.weather_forecast:
                state.response = render_weather_forecast(state.structured_data or {})
            elif intent == Intent.travel_readiness:
                state.response = render_travel_readiness(state.structured_data or {})
            elif intent == Intent.spatial_intelligence:
                state.response = render_spatial_intelligence(state.structured_data or {})
            elif intent == Intent.neighbourhood_comparison:
                state.response = render_neighbourhood_comparison(state.structured_data or {})

    if llm.is_available and not response_warnings and intent != Intent.dynamic_planning:
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
    elif intent == Intent.dynamic_planning:
        llm_mode = state.llm_status
        fallback_used = state.fallback_used
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






    
