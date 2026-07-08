from __future__ import annotations

import logging
from typing import Any

from backend.app.config import (
    BENGALURU_BOUNDING_BOX,
    NEIGHBOURHOOD_SUITABILITY_DISCLAIMER,
    STATION_CONTEXT_RADIUS_METERS,
)
from backend.app.services.artifact_adapter import get_latest_station_reading, get_station_snapshot
from pipeline.station_registry import get_station_by_id
from backend.app.services.confidence_service import get_forecast_confidence
from backend.app.services.forecast_evidence_service import get_forecast_evidence
from backend.app.services.geospatial_evidence_service import (
    OSM_COMPLETENESS_DISCLAIMER,
    get_station_geospatial_context as get_geo_context,
)
from backend.app.services.inspection_priority_service import get_inspection_priorities
from backend.app.services.location_service import resolve_location
import pandas as pd

from backend.app.config import get_project_root
from pipeline.station_registry import BENGALURU_STATIONS

logger = logging.getLogger(__name__)

_REGISTRY_DF: pd.DataFrame | None = None


def _get_registry() -> pd.DataFrame:
    global _REGISTRY_DF
    if _REGISTRY_DF is None:
        path = get_project_root() / "data/reference/bengaluru_station_registry.csv"
        if path.exists():
            _REGISTRY_DF = pd.read_csv(path)
        else:
            _REGISTRY_DF = pd.DataFrame(columns=["station_id", "latitude", "longitude"])
    return _REGISTRY_DF


def _get_station_coords(station_id: str) -> tuple[float, float] | None:
    df = _get_registry()
    matches = df[df["station_id"] == station_id]
    if matches.empty:
        return None
    row = matches.iloc[0]
    lat, lng = row["latitude"], row["longitude"]
    if pd.isna(lat) or pd.isna(lng):
        return None
    return (float(lat), float(lng))


STATION_EVIDENCE_PROXY_NOTE: str = (
    "Station-based evidence is a proximity-supported estimate, "
    "not a direct local monitor reading at the specified address."
)

NON_CAUSALITY_NOTE: str = (
    "Spatial features are contextual evidence and investigation signals only. "
    "They do not prove that a specific industry, construction site, road, "
    "facility, or mapped object caused pollution at this station."
)


def get_station_intelligence(station_id: str, city: str = "bengaluru") -> dict[str, Any]:
    try:
        evidence = get_forecast_evidence(station_id, city)
    except Exception as e:
        evidence = {"_error": str(e)}

    try:
        confidence = get_forecast_confidence(station_id, city)
    except Exception as e:
        confidence = {"_error": str(e)}

    try:
        geo = get_geo_context(station_id, city=city)
    except Exception as e:
        geo = {"_error": str(e)}

    try:
        priorities = get_inspection_priorities(city, top_k=6)
        station_priority = None
        for s in priorities.get("ranked_stations", []):
            if s["station_id"] == station_id:
                station_priority = s
                break
    except Exception:
        station_priority = None

    result: dict[str, Any] = {
        "station_id": station_id,
    }

    if "_error" not in evidence:
        result["forecast_evidence"] = {
            "predicted_pm25": evidence.get("predicted_pm25"),
            "risk_category": evidence.get("risk_category"),
            "forecast_engine": evidence.get("forecast_engine"),
            "expected_change_direction": evidence.get("expected_change_direction"),
        }

    if "_error" not in confidence:
        result["forecast_confidence"] = {
            "confidence_level": confidence.get("confidence_level"),
            "confidence_score": confidence.get("confidence_score"),
        }

    if "_error" not in geo and "station_id" in geo:
        current_readings: dict[str, dict] = {}
        try:
            config = get_station_by_id(station_id)
            for pollutant in config.available_pollutants:
                current_readings[pollutant] = get_latest_station_reading(station_id, pollutant)
        except UnknownStationError:
            pass
        except Exception as exc:
            logger.warning("Failed to fetch current readings for %s: %s", station_id, exc)

        result["geospatial_context"] = {
            "build_status": geo.get("build_status", "unknown"),
            "road_context": geo.get("road_context"),
            "landuse_context": geo.get("landuse_context"),
            "investigation_context": geo.get("investigation_context"),
            "data_completeness_score": geo.get("data_completeness_score"),
            "current_readings": current_readings or None,
        }

    if station_priority:
        result["inspection_priority"] = {
            "priority_level": station_priority.get("priority_level"),
            "priority_score": station_priority.get("priority_score"),
            "recommended_inspection_focus": station_priority.get("recommended_inspection_focus"),
        }

    limitations: list[str] = []
    if geo and "_error" not in geo:
        limitations.extend(geo.get("limitations", []))
    if OSM_COMPLETENESS_DISCLAIMER not in limitations:
        limitations.append(OSM_COMPLETENESS_DISCLAIMER)
    if NON_CAUSALITY_NOTE not in limitations:
        limitations.append(NON_CAUSALITY_NOTE)
    result["limitations"] = limitations

    return result


def get_location_intelligence(
    query: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    location = resolve_location(query=query, latitude=latitude, longitude=longitude)

    if not location["success"]:
        return {
            "resolved_label": None,
            "latitude": None,
            "longitude": None,
            "resolution_method": "failed",
            "nearby_stations": [],
            "station_evidence_proxy_note": STATION_EVIDENCE_PROXY_NOTE,
            "limitations": [location.get("error", "Location could not be resolved.")],
            "source_status": location.get("source_status", "unavailable"),
        }

    lat = location["latitude"]
    lng = location["longitude"]

    nearby = _find_nearby_stations(lat, lng, max_results=3)

    return {
        "resolved_label": location["label"],
        "latitude": lat,
        "longitude": lng,
        "resolution_method": location["resolution_method"],
        "nearby_stations": nearby,
        "station_evidence_proxy_note": STATION_EVIDENCE_PROXY_NOTE,
        "limitations": [
            STATION_EVIDENCE_PROXY_NOTE,
            OSM_COMPLETENESS_DISCLAIMER,
            NON_CAUSALITY_NOTE,
        ],
        "source_status": "fresh",
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _find_nearby_stations(lat: float, lng: float, max_results: int = 3) -> list[dict[str, Any]]:
    registry = _get_registry()
    stations = []
    for s in BENGALURU_STATIONS:
        coords = _get_station_coords(s.station_id)
        if coords is None:
            continue
        s_lat, s_lng = coords
        dist = _haversine_km(lat, lng, s_lat, s_lng)
        stations.append({
            "station_id": s.station_id,
            "station_name": s.station_name,
            "distance_km": round(dist, 2),
        })

    stations.sort(key=lambda x: x["distance_km"])
    return stations[:max_results]
