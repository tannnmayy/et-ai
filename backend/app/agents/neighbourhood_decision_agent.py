from __future__ import annotations

import logging

from backend.app.agents.audit import AuditTrail
from backend.app.agents.state import AgentState
from backend.app.agents.tools import (
    tool_get_weather_summary,
)
from backend.app.services.commute_service import compute_commute_burden
from backend.app.services.location_service import resolve_location
from backend.app.services.neighbourhood_suitability_service import compare_neighbourhoods
from backend.app.services.spatial_intelligence_service import _find_nearby_stations

logger = logging.getLogger(__name__)

PERMITTED_TOOLS = [
    "tool_get_weather_summary",
    "resolve_location",
    "compute_commute_burden",
    "compare_neighbourhoods",
]

NEIGHBOURHOOD_DISCLAIMER = (
    "Neighbourhood suitability decision-support estimate. "
    "This comparison uses nearby monitored-station evidence and mapped contextual proxies. "
    "It is not a direct pollution measurement at a home, school, or workplace address."
)


def run_neighbourhood_decision_agent(state: AgentState, audit: AuditTrail) -> None:
    query = state.user_query.lower()

    # Parse candidate areas, workplace, schools from query
    lines = [
        "Neighbourhood Comparison",
        "",
    ]

    # Try to extract basic info from query
    station_id = state.station_id

    # Use the neighbourhood service if station context is available
    if station_id:
        try:
            nearby = _find_nearby_stations(
                *(_get_station_coords(station_id) or (0, 0))
            )
            lines.append(f"Nearby stations for {station_id}:")
            for s in nearby:
                lines.append(f"  - {s['station_name']} ({s['distance_km']} km)")
            lines.append("")
        except Exception:
            pass

    lines.append(
        "To compare neighbourhoods, use POST /neighbourhoods/compare "
        "with candidate areas, workplace, and optional school locations."
    )
    lines.append("")
    lines.append(f"Disclaimer: {NEIGHBOURHOOD_DISCLAIMER}")

    state.response = "\n".join(lines)
    state.structured_data = {
        "query": query,
        "station_id": station_id,
        "disclaimer": NEIGHBOURHOOD_DISCLAIMER,
    }


def _get_station_coords(station_id: str) -> tuple[float, float] | None:
    import pandas as pd
    from backend.app.config import get_project_root
    path = get_project_root() / "data/reference/bengaluru_station_registry.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    matches = df[df["station_id"] == station_id]
    if matches.empty:
        return None
    row = matches.iloc[0]
    lat, lng = row["latitude"], row["longitude"]
    if pd.isna(lat) or pd.isna(lng):
        return None
    return (float(lat), float(lng))
