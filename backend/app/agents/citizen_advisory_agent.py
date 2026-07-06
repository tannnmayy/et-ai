from __future__ import annotations

import logging

from backend.app.agents.audit import AuditTrail
from backend.app.agents.fallback_renderer import render_citizen_advisory
from backend.app.agents.state import AgentState
from backend.app.agents.tools import tool_get_citizen_advisory, tool_get_forecast_confidence, tool_search_policy_guidance
from backend.app.config import MEDICAL_DISCLAIMER

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = ["tool_get_citizen_advisory", "tool_get_forecast_confidence", "tool_search_policy_guidance"]


def _build_advisory_query(advisory_data: dict, profile: str) -> str:
    risk = advisory_data.get("forecast_risk_category", "Moderate")
    return f"health guidance {risk} air quality {profile} outdoor activity precautions"


def run_citizen_advisory_agent(state: AgentState, audit: AuditTrail) -> None:
    station_id = state.station_id
    city = state.city
    profile = state.profile
    language = state.language

    advisory_data = tool_get_citizen_advisory(station_id, profile=profile, language=language, city=city)
    audit.record_tool_call(
        "tool_get_citizen_advisory",
        {"station_id": station_id, "profile": profile, "language": language, "city": city},
        "_tool_error" not in advisory_data,
    )

    if "_tool_error" in advisory_data:
        state.warnings.append(f"Advisory tool error: {advisory_data['_tool_error']}")
        audit.add_warning(f"Advisory tool error: {advisory_data['_tool_error']}")
        state.response = f"Advisory unavailable: {advisory_data['_tool_error']}"
        state.structured_data = advisory_data
        return

    if "medical_disclaimer" not in advisory_data or not advisory_data["medical_disclaimer"]:
        advisory_data["medical_disclaimer"] = MEDICAL_DISCLAIMER

    conf_data = tool_get_forecast_confidence(station_id, city)
    audit.record_tool_call("tool_get_forecast_confidence", {"station_id": station_id, "city": city}, "_tool_error" not in conf_data)

    if "_tool_error" not in conf_data:
        advisory_data["confidence_level"] = conf_data.get("confidence_level", advisory_data.get("confidence_level", "Unavailable"))

    guidance_query = _build_advisory_query(advisory_data, profile)
    guidance_data = tool_search_policy_guidance(guidance_query, top_k=3)
    audit.record_tool_call(
        "tool_search_policy_guidance",
        {"query": guidance_query, "top_k": 3},
        "_tool_error" not in guidance_data,
    )

    citations: list[dict] = []
    if "_tool_error" not in guidance_data and not guidance_data.get("no_authoritative_result"):
        citations = guidance_data.get("results", [])
        advisory_data["citations"] = [
            {
                "citation_label": c.get("citation_label"),
                "title": c.get("title"),
                "organization": c.get("organization"),
                "excerpt": c.get("excerpt", "")[:200],
            }
            for c in citations
        ]
    else:
        advisory_data["citations"] = []
        advisory_data["citation_note"] = "No additional authoritative source was found in the local guidance corpus for this specific advisory."

    state.response = render_citizen_advisory(advisory_data)
    state.structured_data = advisory_data
    state.tool_results = {
        "advisory": advisory_data,
        "confidence": conf_data if "_tool_error" not in conf_data else {},
        "policy_guidance": guidance_data if "_tool_error" not in guidance_data else {},
    }
