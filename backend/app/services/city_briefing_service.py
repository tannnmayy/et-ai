from __future__ import annotations

from datetime import timezone

import pandas as pd

from backend.app.config import (
    CITY_RISK_POOR_MIN_POOR_STATIONS,
    CITY_RISK_SEVERE_IF_ANY_SEVERE,
    CITY_RISK_SEVERE_MIN_VERY_POOR_STATIONS,
    CITY_RISK_VERY_POOR_MIN_POOR_OR_WORSE_STATIONS,
    PM25_RISK_THRESHOLDS,
    SUPPORTED_CITIES,
)
from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    UnsupportedCityError,
    _validate_city,
    get_city_station_snapshots,
    get_station_geospatial_context,
)
from backend.app.services.confidence_service import get_forecast_confidence

import logging

logger = logging.getLogger(__name__)

_RISK_ORDER = ["Severe", "Very Poor", "Poor", "Moderate", "Satisfactory", "Good"]

_RISK_WORSE_THAN_OR_EQUAL = {
    "Severe": ["Severe"],
    "Very Poor": ["Severe", "Very Poor"],
    "Poor": ["Severe", "Very Poor", "Poor"],
    "Moderate": ["Severe", "Very Poor", "Poor", "Moderate"],
    "Satisfactory": ["Severe", "Very Poor", "Poor", "Moderate", "Satisfactory"],
    "Good": ["Severe", "Very Poor", "Poor", "Moderate", "Satisfactory", "Good"],
}


def _count_at_or_worse(risk_categories: list[str], threshold: str) -> int:
    worse_set = set(_RISK_WORSE_THAN_OR_EQUAL.get(threshold, []))
    return sum(1 for rc in risk_categories if rc in worse_set)


def _determine_city_risk(risk_categories: list[str]) -> str:
    if not risk_categories:
        return "Unavailable"

    if CITY_RISK_SEVERE_IF_ANY_SEVERE and "Severe" in risk_categories:
        return "Severe"

    very_poor_or_worse = _count_at_or_worse(risk_categories, "Very Poor")
    if very_poor_or_worse >= CITY_RISK_SEVERE_MIN_VERY_POOR_STATIONS:
        return "Severe"

    poor_or_worse = _count_at_or_worse(risk_categories, "Poor")
    if poor_or_worse >= CITY_RISK_VERY_POOR_MIN_POOR_OR_WORSE_STATIONS:
        return "Very Poor"

    if poor_or_worse >= CITY_RISK_POOR_MIN_POOR_STATIONS:
        return "Poor"

    mean_pm25 = 0
    if risk_categories:
        return "Moderate"

    return "Unavailable"


def _executive_summary(
    city_risk: str, station_count: int, worst_name: str, best_name: str,
    lgbm_count: int, persist_count: int, low_conf_count: int,
) -> str:
    if city_risk == "Severe":
        return (
            f"Severe air quality detected across {station_count} monitored stations. "
            f"Worst conditions at {worst_name}. Emergency health precautions advised. "
            f"{lgbm_count} stations use LightGBM, {persist_count} use persistence. "
            f"{low_conf_count} station(s) have low or unavailable confidence."
        )
    if city_risk == "Very Poor":
        return (
            f"Very poor air quality across {station_count} monitored stations. "
            f"Worst conditions at {worst_name}. Limit outdoor activities. "
            f"{lgbm_count} stations use LightGBM, {persist_count} use persistence."
        )
    if city_risk == "Poor":
        return (
            f"Poor air quality across {station_count} monitored stations. "
            f"Worst conditions at {worst_name}. Sensitive groups should reduce outdoor exertion."
        )
    if city_risk == "Moderate":
        return (
            f"Moderate air quality across {station_count} monitored stations. "
            f"Best conditions at {best_name}."
        )
    if city_risk == "Good":
        return (
            f"Good air quality across {station_count} monitored stations. "
            "Enjoy outdoor activities."
        )
    return f"No valid forecast data available for {station_count} stations."


def _operational_recommendations(
    city_risk: str, top_priorities: list[dict],
    low_conf_stations: list[str], persist_stations: list[str],
) -> list[str]:
    recs = []
    if city_risk in ("Severe", "Very Poor", "Poor"):
        recs.append(f"Prioritize inspection at highest-risk stations: {', '.join(p['station_id'] for p in top_priorities[:3])}.")
        recs.append("Communicate public health advisories for Poor or worse conditions.")
    elif city_risk == "Moderate":
        recs.append("Monitor stations for worsening conditions.")
    else:
        recs.append("Continue routine monitoring.")

    if low_conf_stations:
        recs.append(
            f"Verify data quality at low-confidence stations: {', '.join(low_conf_stations)}."
        )
    if persist_stations:
        recs.append(
            f"Note: {len(persist_stations)} station(s) use persistence model: {', '.join(persist_stations)}."
        )
    return recs


def _data_limitations(
    total_stations: int, low_conf_stations: list[str], persist_stations: list[str],
    stale_stations: list[str],
) -> list[str]:
    limitations = [
        f"Results represent {total_stations} monitored stations, not full citywide coverage.",
    ]
    if low_conf_stations:
        limitations.append(
            f"{len(low_conf_stations)} station(s) have low or unavailable confidence: {', '.join(low_conf_stations)}."
        )
    if persist_stations:
        limitations.append(
            f"{len(persist_stations)} station(s) use persistence model (not LightGBM): {', '.join(persist_stations)}."
        )
    if stale_stations:
        limitations.append(
            f"{len(stale_stations)} station(s) have stale or missing recent observations: {', '.join(stale_stations)}."
        )
    return limitations


def get_city_briefing(city: str = "bengaluru") -> dict:
    """Generate a deterministic city operational briefing."""
    _validate_city(city)
    display_name = SUPPORTED_CITIES[city.lower().strip()]["display_name"]
    snapshots = get_city_station_snapshots(city)

    if not snapshots:
        return {
            "city": display_name,
            "generated_at": pd.Timestamp.now(tz=timezone.utc).isoformat(),
            "stations_with_forecasts": 0,
            "stations_by_risk_category": {},
            "stations_by_confidence_level": {},
            "lightgbm_selected_count": 0,
            "persistence_selected_count": 0,
            "top_priorities": [],
            "city_risk_level": "Unavailable",
            "executive_summary": f"No valid forecast data available for {display_name}.",
            "operational_recommendations": ["Ensure data pipeline is operational."],
            "data_limitations": ["No station data available."],
            "station_summaries": [],
        }

    risk_categories = [s["risk_category"] for s in snapshots]
    city_risk = _determine_city_risk(risk_categories)

    stations_by_risk: dict[str, list[str]] = {}
    for s in snapshots:
        rc = s["risk_category"]
        stations_by_risk.setdefault(rc, []).append(s["station_id"])

    lgbm_count = sum(1 for s in snapshots if s["forecast_engine"] == "lightgbm")
    persist_count = sum(1 for s in snapshots if s["forecast_engine"] == "persistence")

    conf_data_map: dict[str, dict] = {}
    for s in snapshots:
        try:
            conf_data_map[s["station_id"]] = get_forecast_confidence(s["station_id"], city=city)
        except Exception:
            conf_data_map[s["station_id"]] = {"confidence_level": "Unavailable"}

    stations_by_conf: dict[str, list[str]] = {}
    low_conf_stations: list[str] = []
    stale_stations: list[str] = []
    for s in snapshots:
        sid = s["station_id"]
        conf_level = conf_data_map.get(sid, {}).get("confidence_level", "Unavailable")
        stations_by_conf.setdefault(conf_level, []).append(sid)
        if conf_level in ("Low", "Unavailable"):
            low_conf_stations.append(sid)
        age = conf_data_map.get(sid, {}).get("latest_observation_age_hours")
        if age is not None and age > 24:
            stale_stations.append(sid)

    worst = max(snapshots, key=lambda x: x["predicted_pm25"])
    best = min(snapshots, key=lambda x: x["predicted_pm25"])

    top_priorities = []
    for s in sorted(snapshots, key=lambda x: x["predicted_pm25"], reverse=True):
        top_priorities.append({
            "station_id": s["station_id"],
            "station_name": s["station_name"],
            "predicted_pm25": s["predicted_pm25"],
            "risk_category": s["risk_category"],
            "confidence_level": conf_data_map.get(s["station_id"], {}).get("confidence_level", "Unavailable"),
        })

    station_summaries = []
    for s in snapshots:
        sid = s["station_id"]
        conf_level = conf_data_map.get(sid, {}).get("confidence_level", "Unavailable")
        station_summaries.append({
            "station_id": sid,
            "station_name": s["station_name"],
            "predicted_pm25": s["predicted_pm25"],
            "risk_category": s["risk_category"],
            "forecast_engine": s["forecast_engine"],
            "confidence_level": conf_level,
            "data_quality_classification": s["quality_classification"],
            "expected_change_pm25": None,
        })

    exec_summary = _executive_summary(
        city_risk, len(snapshots), worst["station_name"], best["station_name"],
        lgbm_count, persist_count, len(low_conf_stations),
    )
    op_recs = _operational_recommendations(city_risk, top_priorities, low_conf_stations, persist_stations=[])
    limitations = _data_limitations(len(snapshots), low_conf_stations, [s["station_id"] for s in snapshots if s["forecast_engine"] == "persistence"], stale_stations)

    # Compact aggregate spatial-coverage note
    spatial_coverage_note = None
    try:
        geo_sample = get_station_geospatial_context(snapshots[0]["station_id"])
        if "road_context" in geo_sample:
            spatial_coverage_note = (
                "Geospatial context available for station-area analysis. "
                "OpenStreetMap-based road, land-use, and investigation features "
                "are mapped contextual signals, not verified emission sources."
            )
    except Exception:
        pass

    return {
        "city": display_name,
        "generated_at": pd.Timestamp.now(tz=timezone.utc).isoformat(),
        "stations_with_forecasts": len(snapshots),
        "stations_by_risk_category": stations_by_risk,
        "stations_by_confidence_level": stations_by_conf,
        "lightgbm_selected_count": lgbm_count,
        "persistence_selected_count": persist_count,
        "top_priorities": top_priorities,
        "city_risk_level": city_risk,
        "executive_summary": exec_summary,
        "operational_recommendations": op_recs,
        "data_limitations": limitations,
        "station_summaries": station_summaries,
        "spatial_coverage_note": spatial_coverage_note,
    }
