from __future__ import annotations

import logging

from backend.app.agents.audit import AuditTrail
from backend.app.agents.state import AgentState
from backend.app.agents.tools import (
    tool_get_forecast_evidence,
    tool_get_forecast_confidence,
    tool_get_geospatial_context,
    tool_get_inspection_priorities,
)
from backend.app.services.spatial_intelligence_service import (
    get_station_intelligence,
    get_location_intelligence,
)

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = [
    "tool_get_forecast_evidence",
    "tool_get_forecast_confidence",
    "tool_get_geospatial_context",
    "tool_get_inspection_priorities",
]

SPATIAL_INTELLIGENCE_DISCLAIMER = (
    "Spatial intelligence aggregates forecast evidence, confidence, inspection priorities, "
    "and mapped spatial features. It does not claim that a mapped road, industry, "
    "construction site, or facility caused pollution."
)


def run_spatial_intelligence_agent(state: AgentState, audit: AuditTrail) -> None:
    station_id = state.station_id
    city = state.city

    if station_id:
        audit.record_tool_call(
            "tool_get_forecast_evidence",
            {"station_id": station_id, "city": city},
            True,
        )
        audit.record_tool_call(
            "tool_get_forecast_confidence",
            {"station_id": station_id, "city": city},
            True,
        )
        audit.record_tool_call(
            "tool_get_geospatial_context",
            {"station_id": station_id, "city": city},
            True,
        )

        try:
            intelligence = get_station_intelligence(station_id, city=city)
            state.structured_data = intelligence
            state.tool_results = {"station_intelligence": intelligence}

            lines = [
                f"Spatial Intelligence for Station: {station_id}",
                "",
            ]

            fe = intelligence.get("forecast_evidence", {})
            if fe:
                lines.append(f"Forecast PM2.5: {fe.get('predicted_pm25', 'N/A')} ug/m3 ({fe.get('risk_category', 'N/A')})")
                lines.append(f"Forecast engine: {fe.get('forecast_engine', 'N/A')}")
                lines.append("")

            fc = intelligence.get("forecast_confidence", {})
            if fc:
                lines.append(f"Confidence: {fc.get('confidence_level', 'N/A')} ({fc.get('confidence_score', 'N/A')}/100)")
                lines.append("")

            ip = intelligence.get("inspection_priority", {})
            if ip:
                lines.append(f"Inspection priority: {ip.get('priority_level', 'N/A')} (score: {ip.get('priority_score', 'N/A')})")
                lines.append(f"Focus: {ip.get('recommended_inspection_focus', 'N/A')}")
                lines.append("")

            geo = intelligence.get("geospatial_context", {})
            if geo:
                lines.append("Geospatial context:")
                build_status = geo.get("build_status", "unknown")
                lines.append(f"  Build status: {build_status}")
                rc = geo.get("road_context", {}) or {}
                rd = rc.get("road_density_m_per_sq_km")
                if rd is not None:
                    lines.append(f"  Road density: {rd:.1f} m/km2")
                lc = geo.get("landuse_context", {}) or {}
                gs = lc.get("green_space_fraction")
                if gs is not None:
                    lines.append(f"  Green space fraction: {gs:.2%}")
                lines.append("")

            limitations = intelligence.get("limitations", [])
            if limitations:
                lines.append("Limitations:")
                for lim in limitations:
                    lines.append(f"- {lim}")

            state.response = "\n".join(lines)

        except Exception as e:
            state.warnings.append(f"Spatial intelligence error: {e}")
            audit.add_warning(f"Spatial intelligence error: {e}")
            state.response = f"Spatial intelligence unavailable: {e}"
            state.structured_data = {"_error": str(e)}
    else:
        state.response = (
            "Spatial intelligence requires a station ID. "
            "Use /spatial-intelligence/location for address-based queries."
        )
        state.structured_data = {}
