from __future__ import annotations

import logging

from backend.app.agents.audit import AuditTrail
from backend.app.agents.fallback_renderer import render_citizen_advisory
from backend.app.agents.state import AgentState
from backend.app.agents.tools import tool_get_citizen_advisory, tool_get_forecast_confidence
from backend.app.config import MEDICAL_DISCLAIMER

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = ["tool_get_citizen_advisory", "tool_get_forecast_confidence"]


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

    state.response = render_citizen_advisory(advisory_data)
    state.structured_data = advisory_data
    state.tool_results = {"advisory": advisory_data, "confidence": conf_data if "_tool_error" not in conf_data else {}}
