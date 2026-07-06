from __future__ import annotations

import logging

from backend.app.agents.audit import AuditTrail
from backend.app.agents.fallback_renderer import render_city_briefing
from backend.app.agents.state import AgentState
from backend.app.agents.tools import (
    tool_get_city_briefing,
    tool_get_inspection_priorities,
    tool_search_policy_guidance,
)

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = ["tool_get_city_briefing", "tool_get_inspection_priorities", "tool_search_policy_guidance"]


def run_city_briefing_agent(state: AgentState, audit: AuditTrail) -> None:
    city = state.city
    top_k = state.top_k

    briefing_data = tool_get_city_briefing(city)
    audit.record_tool_call("tool_get_city_briefing", {"city": city}, "_tool_error" not in briefing_data)

    if "_tool_error" in briefing_data:
        state.warnings.append(f"Briefing tool error: {briefing_data['_tool_error']}")
        audit.add_warning(f"Briefing tool error: {briefing_data['_tool_error']}")
        state.response = f"City briefing unavailable: {briefing_data['_tool_error']}"
        state.structured_data = briefing_data
        return

    priorities_data = tool_get_inspection_priorities(city, top_k=top_k)
    audit.record_tool_call("tool_get_inspection_priorities", {"city": city, "top_k": top_k}, "_tool_error" not in priorities_data)

    if "_tool_error" not in priorities_data:
        briefing_data["top_priorities_detail"] = priorities_data.get("ranked_stations", [])

    city_risk = briefing_data.get("city_risk_level", "Unavailable")
    if city_risk in ("Poor", "Very Poor", "Severe"):
        guidance_query = f"health guidance {city_risk} air quality public advisory"
        guidance_data = tool_search_policy_guidance(guidance_query, top_k=2)
        audit.record_tool_call(
            "tool_search_policy_guidance",
            {"query": guidance_query, "top_k": 2},
            "_tool_error" not in guidance_data,
        )
        if "_tool_error" not in guidance_data and not guidance_data.get("no_authoritative_result"):
            citations = []
            for r in guidance_data.get("results", []):
                citations.append({
                    "citation_label": r.get("citation_label"),
                    "title": r.get("title"),
                    "organization": r.get("organization"),
                    "excerpt": r.get("excerpt", "")[:200],
                })
            briefing_data["guidance_sources"] = citations

    state.response = render_city_briefing(briefing_data)
    state.structured_data = briefing_data
    state.tool_results = {
        "briefing": briefing_data,
        "inspection_priorities": priorities_data if "_tool_error" not in priorities_data else {},
    }
