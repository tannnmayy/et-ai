from __future__ import annotations

import logging
from typing import Any

from backend.app.agents.audit import AuditTrail
from backend.app.agents.fallback_renderer import render_station_explanation, render_confidence_summary
from backend.app.agents.state import AgentState, Intent
from backend.app.agents.tools import tool_get_forecast_evidence, tool_get_forecast_confidence

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = ["tool_get_forecast_evidence", "tool_get_forecast_confidence"]


def run_forecast_evidence_agent(state: AgentState, audit: AuditTrail) -> None:
    station_id = state.station_id
    city = state.city
    intent = state.intent

    evidence_data = tool_get_forecast_evidence(station_id, city)
    audit.record_tool_call("tool_get_forecast_evidence", {"station_id": station_id, "city": city}, "_tool_error" not in evidence_data)

    conf_data = tool_get_forecast_confidence(station_id, city)
    audit.record_tool_call("tool_get_forecast_confidence", {"station_id": station_id, "city": city}, "_tool_error" not in conf_data)

    combined: dict[str, Any] = dict(evidence_data)
    if "_tool_error" not in conf_data:
        combined["confidence"] = conf_data
        combined["confidence_level"] = conf_data.get("confidence_level", "Unavailable")
        combined["confidence_score"] = conf_data.get("confidence_score")

    warnings: list[str] = []
    if "_tool_error" in evidence_data:
        warnings.append(f"Evidence tool error: {evidence_data['_tool_error']}")
    if "_tool_error" in conf_data:
        warnings.append(f"Confidence tool error: {conf_data['_tool_error']}")

    state.warnings.extend(warnings)
    for w in warnings:
        audit.add_warning(w)

    if intent == Intent.station_confidence:
        answer = render_confidence_summary(conf_data if "_tool_error" not in conf_data else combined)
    else:
        answer = render_station_explanation(combined)

    state.response = answer
    state.structured_data = combined
    state.tool_results = {
        "evidence": evidence_data,
        "confidence": conf_data,
    }
