"""Spatial context agent.

Provides natural-language responses about geospatial evidence around monitoring
stations. All responses disclaim that OSM data is community-maintained and that
mapped features are not verified emission sources.
"""

from __future__ import annotations

import logging

from backend.app.agents.audit import AuditTrail
from backend.app.agents.state import AgentState
from backend.app.agents.tools import (
    tool_get_geospatial_city_coverage,
    tool_get_geospatial_context,
)

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = ["tool_get_geospatial_context", "tool_get_geospatial_city_coverage"]

OSM_DISCLAIMER = (
    "OpenStreetMap data is community-maintained and may be incomplete, "
    "outdated, or inconsistently tagged. Mapped features are contextual "
    "evidence only and do not represent verified registered emission sources."
)

NON_CAUSALITY_NOTE = (
    "Spatial features are contextual evidence and investigation signals only. "
    "They do not prove that a specific industry, construction site, road, "
    "facility, or mapped object caused pollution at a specific station."
)


def run_spatial_context_agent(state: AgentState, audit: AuditTrail) -> None:
    """Run the spatial context agent for a station or city query."""
    station_id = state.station_id
    city = state.city

    if station_id:
        context_data = tool_get_geospatial_context(station_id, city=city)
        audit.record_tool_call(
            "tool_get_geospatial_context",
            {"station_id": station_id, "city": city},
            "_tool_error" not in context_data,
        )

        if "_tool_error" in context_data:
            state.warnings.append(f"Geospatial tool error: {context_data['_tool_error']}")
            audit.add_warning(f"Geospatial tool error: {context_data['_tool_error']}")
            state.response = f"Geospatial context unavailable: {context_data['_tool_error']}"
            state.structured_data = context_data
            return

        lines = [
            f"Geospatial Context for Station: {station_id} ({context_data.get('city', 'bengaluru').title()})",
            f"H3 cell: {context_data.get('h3_cell', 'N/A')}",
            f"Completeness score: {context_data.get('data_completeness_score', 0):.2f}",
            "",
        ]

        road = context_data.get("road_context", {})
        lines.append("Road/Mobility:")
        rd = road.get("road_density_m_per_sq_km")
        if rd is not None:
            lines.append(f"  Road density: {rd:.1f} m/km\u00B2")
        nr = road.get("nearest_major_road_distance_m")
        if nr is not None:
            lines.append(f"  Nearest major road: {nr:.0f}m")
        lines.append(f"  Coverage: {road.get('road_feature_coverage_status', 'unavailable')}")
        lines.append("")

        landuse = context_data.get("landuse_context", {})
        lines.append("Land-use context:")
        ind = landuse.get("industrial_landuse_fraction")
        if ind is not None:
            lines.append(f"  Industrial fraction: {ind:.2%}")
        grn = landuse.get("green_space_fraction")
        if grn is not None:
            lines.append(f"  Green space fraction: {grn:.2%}")
        lines.append(f"  Coverage: {landuse.get('landuse_feature_coverage_status', 'unavailable')}")
        lines.append("")

        inv = context_data.get("investigation_context", {})
        lines.append("Investigation context:")
        cc = inv.get("construction_feature_count_within_radius")
        if cc is not None:
            lines.append(f"  Mapped construction features: {cc}")
        ic = inv.get("mapped_industrial_or_facility_count_within_radius")
        if ic is not None:
            lines.append(f"  Mapped industrial/facility features: {ic}")
        lines.append(f"  Coverage: {inv.get('investigation_context_coverage_status', 'unavailable')}")
        lines.append("")

        readings = context_data.get("current_readings") or {}
        if readings:
            lines.append("Current pollutant readings:")
            for poll, r in readings.items():
                if r.get("available"):
                    lines.append(f"  {poll}: {r['value']} µg/m³ at {r.get('timestamp', 'N/A')}")
                else:
                    lines.append(f"  {poll}: {r.get('note', 'Not available')}")
            lines.append("")

        limitations = context_data.get("limitations", [])
        if limitations:
            lines.append("Limitations:")
            for lim in limitations:
                lines.append(f"- {lim}")
        else:
            lines.append(f"- {OSM_DISCLAIMER}")
            lines.append(f"- {NON_CAUSALITY_NOTE}")

        state.response = "\n".join(lines)
        state.structured_data = context_data
        state.tool_results = {"geospatial_context": context_data}

    else:
        coverage_data = tool_get_geospatial_city_coverage(city)
        audit.record_tool_call(
            "tool_get_geospatial_city_coverage",
            {"city": city},
            "_tool_error" not in coverage_data,
        )

        if "_tool_error" in coverage_data:
            state.warnings.append(f"Geospatial coverage error: {coverage_data['_tool_error']}")
            audit.add_warning(f"Geospatial coverage error: {coverage_data['_tool_error']}")
            state.response = f"Geospatial coverage unavailable: {coverage_data['_tool_error']}"
            state.structured_data = coverage_data
            return

        lines = [
            f"Geospatial Coverage Summary for {city.title()}",
            f"Stations with context: {coverage_data.get('stations_with_coverage', 0)} / {coverage_data.get('total_stations', 0)}",
            f"Stations with complete coverage: {coverage_data.get('stations_with_complete_coverage', 0)}",
            f"OSM snapshot: {coverage_data.get('osm_snapshot_timestamp', 'N/A')}",
            f"Feature builder: v{coverage_data.get('feature_builder_version', 'N/A')}",
            f"H3 resolution: {coverage_data.get('h3_resolution', 'N/A')}",
            "",
        ]

        for d in coverage_data.get("disclaimers", []):
            lines.append(f"- {d}")

        state.response = "\n".join(lines)
        state.structured_data = coverage_data
        state.tool_results = {"geospatial_coverage": coverage_data}
