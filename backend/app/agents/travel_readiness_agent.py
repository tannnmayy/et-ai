from __future__ import annotations

import logging

from backend.app.agents.audit import AuditTrail
from backend.app.agents.fallback_renderer import render_travel_readiness
from backend.app.agents.state import AgentState
from backend.app.agents.tools import (
    tool_get_travel_readiness,
    tool_get_weather_summary,
)
from backend.app.config import MEDICAL_DISCLAIMER

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = ["tool_get_weather_summary", "tool_get_travel_readiness"]


def run_travel_readiness_agent(state: AgentState, audit: AuditTrail) -> None:
    city = state.city
    profile = state.profile
    period = "next_24h"

    if state.user_query and "tomorrow" in state.user_query.lower():
        period = "tomorrow"

    weather_data = tool_get_weather_summary(city=city, period=period)
    audit.record_tool_call(
        "tool_get_weather_summary",
        {"city": city, "period": period},
        "_tool_error" not in weather_data,
    )

    travel_data = tool_get_travel_readiness(
        city=city, profile=profile, period=period,
    )
    audit.record_tool_call(
        "tool_get_travel_readiness",
        {"city": city, "profile": profile, "period": period},
        "_tool_error" not in travel_data,
    )

    if "_tool_error" in travel_data:
        state.warnings.append(f"Travel readiness tool error: {travel_data['_tool_error']}")
        audit.add_warning(f"Travel readiness tool error: {travel_data['_tool_error']}")
        state.response = f"Travel readiness unavailable: {travel_data['_tool_error']}"
        state.structured_data = travel_data
        return

    if "_tool_error" in weather_data:
        travel_data["weather_component"]["weather_available"] = False
        travel_data["weather_component"]["weather_risk_level"] = None
        travel_data["weather_component"]["weather_summary"] = None

    if profile in ("elderly", "child", "school", "outdoor_worker"):
        if not travel_data.get("medical_disclaimer"):
            travel_data["medical_disclaimer"] = MEDICAL_DISCLAIMER

    state.response = render_travel_readiness(travel_data)
    state.structured_data = travel_data
    state.tool_results = {
        "weather_summary": weather_data if "_tool_error" not in weather_data else {},
        "travel_readiness": travel_data,
    }
