from __future__ import annotations

import logging
from typing import Any

from backend.app.agents.audit import AuditTrail
from backend.app.agents.fallback_renderer import render_inspection_plan
from backend.app.agents.state import AgentState
from backend.app.agents.tools import tool_get_inspection_priorities, tool_get_forecast_evidence, tool_get_forecast_confidence
from backend.app.config import INVESTIGATION_DISCLAIMER

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = ["tool_get_inspection_priorities", "tool_get_forecast_evidence", "tool_get_forecast_confidence"]


def run_enforcement_planning_agent(state: AgentState, audit: AuditTrail) -> None:
    city = state.city
    top_k = state.top_k

    inspection_data = tool_get_inspection_priorities(city, top_k=top_k)
    audit.record_tool_call("tool_get_inspection_priorities", {"city": city, "top_k": top_k}, "_tool_error" not in inspection_data)

    if "_tool_error" in inspection_data:
        state.warnings.append(f"Inspection tool error: {inspection_data['_tool_error']}")
        audit.add_warning(f"Inspection tool error: {inspection_data['_tool_error']}")
        state.response = f"Inspection plan unavailable: {inspection_data['_tool_error']}"
        state.structured_data = inspection_data
        return

    ranked = inspection_data.get("ranked_stations", [])
    for station in ranked:
        sid = station.get("station_id")
        if sid:
            ev_data = tool_get_forecast_evidence(sid, city)
            audit.record_tool_call("tool_get_forecast_evidence", {"station_id": sid, "city": city}, "_tool_error" not in ev_data)
            station["_evidence"] = ev_data if "_tool_error" not in ev_data else {}

            conf_data = tool_get_forecast_confidence(sid, city)
            audit.record_tool_call("tool_get_forecast_confidence", {"station_id": sid, "city": city}, "_tool_error" not in conf_data)
            station["_confidence"] = conf_data if "_tool_error" not in conf_data else {}

    for station in ranked:
        caveats = station.get("caveats", [])
        if INVESTIGATION_DISCLAIMER not in caveats:
            caveats.append(INVESTIGATION_DISCLAIMER)

    state.response = render_inspection_plan(inspection_data)
    state.structured_data = inspection_data
    state.tool_results = {"inspection_priorities": inspection_data}
