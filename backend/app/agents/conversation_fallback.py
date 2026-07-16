"""Query-aware deterministic answers when hosted planning is unavailable."""

from __future__ import annotations

import re

from backend.app.agents.audit import AuditTrail
from backend.app.agents.state import AgentState
from backend.app.services.inspection_priority_service import get_inspection_priorities
from backend.app.services.spatial_intelligence_service import _find_nearby_stations, get_station_intelligence
from pipeline.station_registry import get_registry_stations


# Used only to select the nearest monitoring station when a user names a
# common locality without a monitor ID. These are not exact local readings.
_LOCALITY_CENTRES: dict[str, tuple[float, float]] = {
    "whitefield": (12.9698, 77.7500),
    "indiranagar": (12.9784, 77.6408),
    "koramangala": (12.9352, 77.6245),
    "marathahalli": (12.9592, 77.6974),
    "bellandur": (12.9260, 77.6762),
    "electronic city": (12.8456, 77.6603),
    "hsr layout": (12.9116, 77.6389),
    "hsr": (12.9116, 77.6389),
    "jayanagar": (12.9299, 77.5828),
    "peenya": (13.0285, 77.5190),
    "hebbal": (13.0358, 77.5970),
    "btm": (12.9166, 77.6101),
    "yeshwanthpur": (13.0280, 77.5400),
    "yeshvantpur": (13.0280, 77.5400),
    "manyata": (13.0475, 77.6210),
    "manyata tech park": (13.0475, 77.6210),
    "silk board": (12.9177, 77.6238),
    "kormangala": (12.9352, 77.6245),  # common misspelling
    "mg road": (12.9750, 77.6063),
    "majestic": (12.9767, 77.5713),
    "airport": (13.1986, 77.7066),
    "kempegowda": (13.1986, 77.7066),
    "banashankari": (12.9255, 77.5468),
    "rajajinagar": (12.9911, 77.5540),
    "malleshwaram": (13.0035, 77.5640),
}


def infer_station_id(query: str) -> str | None:
    """Match a user-facing station/locality name to the registered station."""
    normalized = _normalise(query)
    for station in get_registry_stations():
        for candidate in (station.station_id.replace("cpcb_", "").replace("_", " "), station.display_name, station.station_name):
            candidate = re.sub(r"\b(bengaluru|kspcb|cpcb|station)\b", "", _normalise(candidate)).strip()
            if candidate and candidate in normalized:
                return station.station_id
    return None


def run_query_aware_fallback(state: AgentState, audit: AuditTrail, *, deep: bool = False) -> None:
    """Answer common copilot questions using current project data, not canned text."""
    query = state.user_query.lower()
    station_id = state.station_id or infer_station_id(query)
    if station_id:
        state.station_id = station_id
        _answer_station_question(state, audit, station_id, deep=deep)
    elif _contains_any(query, ("worst", "highest", "most polluted", "lowest aqi", "bad aqi")):
        _answer_monitored_extreme(state, audit)
    else:
        locality = next((name for name in _LOCALITY_CENTRES if name in query), None)
        if locality:
            _answer_unmonitored_locality(state, audit, locality, deep=deep)
        elif _contains_any(query, ("good aqi", "safe aqi", "what is a good")):
            state.response = (
                "AQI Sentinel currently reports PM2.5 concentration rather than a full pollutant AQI. "
                "On the project scale, up to 30 µg/m³ is Good, 31–60 is Satisfactory, 61–90 is Moderate, "
                "91–120 is Poor, and above 120 is Very Poor."
            )
            state.structured_data = {"pm25_thresholds_ug_m3": {"Good": 30, "Satisfactory": 60, "Moderate": 90, "Poor": 120, "Very Poor": 250}}
        else:
            state.response = (
                "I could not answer that question specifically from the available air-quality data. "
                "Try asking about the cleanest or most polluted monitored area, why air quality is elevated near a named Bengaluru locality, "
                "a health precaution, weather, or an enforcement priority."
            )
            state.structured_data = {}

    state.llm_status = "deterministic_deep" if deep else "deterministic"
    state.fallback_used = deep
    if deep:
        state.warnings.append("Hosted deep planning was unavailable; this answer uses a query-aware multi-source deterministic plan.")


def _answer_monitored_extreme(state: AgentState, audit: AuditTrail) -> None:
    priorities = get_inspection_priorities(state.city, top_k=max(3, state.top_k))
    audit.record_tool_call("tool_get_inspection_priorities", {"city": state.city, "top_k": max(3, state.top_k)}, True)
    ranked = priorities.get("ranked_stations", [])
    if not ranked:
        state.response = "Current monitored-station priorities are unavailable, so I cannot identify a worst monitored area right now."
        state.structured_data = {"inspection_priorities": priorities}
        return
    highest = ranked[0]
    state.response = (
        f"Among AQI Sentinel's monitored stations, {highest['station_name']} is currently the highest priority. "
        f"Its next PM2.5 estimate is {highest['predicted_pm25']:.0f} µg/m³ ({highest['risk_category']}). "
        "This is a monitored-station ranking, not a claim that it is the single worst point in all of Bengaluru."
    )
    state.structured_data = {"inspection_priorities": priorities}


def _answer_station_question(state: AgentState, audit: AuditTrail, station_id: str, *, deep: bool) -> None:
    intelligence = get_station_intelligence(station_id, city=state.city)
    audit.record_tool_call("tool_get_station_intelligence", {"station_id": station_id, "city": state.city}, True)
    evidence = intelligence.get("forecast_evidence", {})
    geo = intelligence.get("geospatial_context", {})
    station = next((s for s in get_registry_stations() if s.station_id == station_id), None)
    station_name = station.display_name if station else station_id
    pm25, risk = evidence.get("predicted_pm25"), evidence.get("risk_category", "Unavailable")
    parts = [f"For {station_name}, the current next-period PM2.5 estimate is {pm25 if pm25 is not None else 'unavailable'} µg/m³ ({risk})."]
    road = (geo.get("road_context") or {}).get("road_density_m_per_sq_km")
    landuse = geo.get("landuse_context") or {}
    investigation = geo.get("investigation_context") or {}
    signals: list[str] = []
    if road is not None:
        signals.append(f"road-density context is {road:.0f} m/km²")
    industrial = landuse.get("industrial_landuse_fraction")
    if industrial is not None:
        signals.append(f"mapped industrial land-use share is {industrial:.1%}")
    construction = investigation.get("construction_feature_count_within_radius")
    if construction is not None:
        signals.append(f"{construction} mapped construction features are nearby")
    if signals:
        parts.append("Relevant mapped context: " + "; ".join(signals) + ".")
    parts.append("These are investigation signals and station-proximate context, not proof that a specific road, factory, or site caused pollution.")
    if deep:
        priority = intelligence.get("inspection_priority", {})
        if priority:
            focus = str(priority.get("recommended_inspection_focus", "not available")).rstrip(".")
            parts.append(f"Operational priority: {priority.get('priority_level', 'unavailable')}; focus: {focus}.")
    state.response = " ".join(parts)
    state.structured_data = intelligence


def _answer_unmonitored_locality(state: AgentState, audit: AuditTrail, locality: str, *, deep: bool) -> None:
    lat, lon = _LOCALITY_CENTRES[locality]
    nearby = _find_nearby_stations(lat, lon, max_results=1)
    audit.record_tool_call("tool_get_location_intelligence", {"locality": locality}, bool(nearby))
    if not nearby:
        state.response = f"I could not find a nearby monitored station to ground an answer for {locality.title()}."
        state.structured_data = {"locality": locality, "nearby_stations": []}
        return
    proxy = nearby[0]
    state.station_id = proxy["station_id"]
    _answer_station_question(state, audit, proxy["station_id"], deep=deep)
    state.response += f" This is based on the nearest monitored station, {proxy['station_name']} ({proxy['distance_km']:.1f} km away), so it is not an exact measurement for {locality.title()}."


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", value.lower()).strip()


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)
