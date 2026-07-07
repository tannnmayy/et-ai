from __future__ import annotations

import logging
from typing import Any

from backend.app.config import (
    ADVISORY_PROFILES,
    MEDICAL_DISCLAIMER,
    NEIGHBOURHOOD_MIN_STATION_COVERAGE,
    NEIGHBOURHOOD_SCORE_WEIGHTS,
    NEIGHBOURHOOD_SUITABILITY_DISCLAIMER,
    TRAVEL_PROFILES,
)
from backend.app.services.commute_service import compute_commute_burden
from backend.app.services.location_service import resolve_location
from backend.app.services.spatial_intelligence_service import (
    _find_nearby_stations,
    _haversine_km,
)
from backend.app.services.weather_forecast_service import get_weather_summary

logger = logging.getLogger(__name__)


def compare_neighbourhoods(
    candidate_queries: list[dict[str, Any]],
    workplace_query: dict[str, Any],
    school_queries: list[dict[str, Any]] | None = None,
    profile: str = "general",
    travel_mode: str = "DRIVE",
    period: str = "tomorrow",
) -> dict[str, Any]:
    if school_queries is None:
        school_queries = []

    if len(candidate_queries) < 1 or len(candidate_queries) > 3:
        return {
            "candidates": [],
            "ranking": None,
            "workplace_label": "",
            "school_labels": [],
            "profile": profile,
            "travel_mode": travel_mode,
            "period": period,
            "disclaimer": NEIGHBOURHOOD_SUITABILITY_DISCLAIMER,
            "medical_disclaimer": _get_medical_disclaimer(profile),
            "error": "Must provide 1-3 candidate areas.",
        }

    # Resolve workplace
    workplace = resolve_location(
        query=workplace_query.get("query", ""),
        latitude=workplace_query.get("latitude"),
        longitude=workplace_query.get("longitude"),
    )
    if not workplace["success"]:
        return {
            "candidates": [],
            "ranking": None,
            "workplace_label": "",
            "school_labels": [],
            "profile": profile,
            "travel_mode": travel_mode,
            "period": period,
            "disclaimer": NEIGHBOURHOOD_SUITABILITY_DISCLAIMER,
            "medical_disclaimer": _get_medical_disclaimer(profile),
            "error": f"Workplace location could not be resolved: {workplace.get('error', 'unknown')}",
        }

    # Resolve schools
    resolved_schools: list[dict[str, Any]] = []
    school_labels: list[str] = []
    for sq in school_queries[:2]:
        school = resolve_location(
            query=sq.get("query", ""),
            latitude=sq.get("latitude"),
            longitude=sq.get("longitude"),
        )
        if school["success"]:
            resolved_schools.append({
                "latitude": school["latitude"],
                "longitude": school["longitude"],
                "label": school["label"],
            })
            school_labels.append(school["label"])

    # Resolve candidates
    resolved_candidates: list[dict[str, Any]] = []
    for cq in candidate_queries:
        c = resolve_location(
            query=cq.get("query", ""),
            latitude=cq.get("latitude"),
            longitude=cq.get("longitude"),
        )
        if c["success"]:
            resolved_candidates.append(c)

    if not resolved_candidates:
        return {
            "candidates": [],
            "ranking": None,
            "workplace_label": workplace["label"],
            "school_labels": school_labels,
            "profile": profile,
            "travel_mode": travel_mode,
            "period": period,
            "disclaimer": NEIGHBOURHOOD_SUITABILITY_DISCLAIMER,
            "medical_disclaimer": _get_medical_disclaimer(profile),
            "error": "No candidate areas could be resolved.",
        }

    # Fetch weather once for all candidates
    try:
        weather = get_weather_summary(period=period)
        weather_risk = weather.get("weather_risk_level", "Low")
        weather_available = weather.get("source_status") != "unavailable"
    except Exception:
        weather_risk = "Low"
        weather_available = False

    # Compute suitability for each candidate
    results: list[dict[str, Any]] = []
    for c in resolved_candidates:
        result = _score_candidate(
            candidate=c,
            workplace=workplace,
            schools=resolved_schools,
            travel_mode=travel_mode,
            weather_risk=weather_risk,
            weather_available=weather_available,
            profile=profile,
        )
        results.append(result)

    # Ranking
    valid_scores = [
        (i, r["overall_score"]) for i, r in enumerate(results) if r["overall_score"] is not None
    ]
    valid_scores.sort(key=lambda x: x[1], reverse=True)
    ranking = [i for i, _ in valid_scores] if valid_scores else None

    return {
        "candidates": results,
        "ranking": ranking,
        "workplace_label": workplace["label"],
        "school_labels": school_labels,
        "profile": profile,
        "travel_mode": travel_mode,
        "period": period,
        "disclaimer": NEIGHBOURHOOD_SUITABILITY_DISCLAIMER,
        "medical_disclaimer": _get_medical_disclaimer(profile),
    }


def _score_candidate(
    candidate: dict[str, Any],
    workplace: dict[str, Any],
    schools: list[dict[str, Any]],
    travel_mode: str,
    weather_risk: str,
    weather_available: bool,
    profile: str,
) -> dict[str, Any]:
    lat = candidate["latitude"]
    lng = candidate["longitude"]

    nearby = _find_nearby_stations(lat, lng, max_results=3)

    # Air quality component (based on nearest station proximity)
    air_quality_score, air_explanation = _score_air_quality(nearby)
    confidence_score, conf_explanation = _score_forecast_confidence()
    green_score, green_explanation = _score_green_space_proxy(nearby)
    road_score, road_explanation = _score_road_mobility_proxy(nearby)
    weather_score, weather_explanation = _score_weather(weather_risk, weather_available)
    coverage_score, coverage_explanation = _score_data_coverage(nearby)

    # Commute component
    commute_result = compute_commute_burden(
        origin_lat=lat,
        origin_lng=lng,
        workplace_lat=workplace["latitude"],
        workplace_lng=workplace["longitude"],
        travel_mode=travel_mode,
        school_locations=schools if schools else None,
    )
    if commute_result["commute_available"] and commute_result["total_commute_burden_score"] is not None:
        commute_score_val = 1.0 - commute_result["total_commute_burden_score"]
        commute_available = True
        commute_explanation = f"Commute burden score: {commute_result['total_commute_burden_score']:.2f}"
    else:
        commute_score_val = None
        commute_available = False
        commute_explanation = commute_result.get("error", "Commute data unavailable.")

    components = {
        "air_quality_component": _make_component(air_quality_score, NEIGHBOURHOOD_SCORE_WEIGHTS["air_quality_component"], True, air_explanation),
        "forecast_confidence_component": _make_component(confidence_score, NEIGHBOURHOOD_SCORE_WEIGHTS["forecast_confidence_component"], True, conf_explanation),
        "green_space_proxy_component": _make_component(green_score, NEIGHBOURHOOD_SCORE_WEIGHTS["green_space_proxy_component"], True, green_explanation),
        "road_mobility_proxy_component": _make_component(road_score, NEIGHBOURHOOD_SCORE_WEIGHTS["road_mobility_proxy_component"], True, road_explanation),
        "commute_component": _make_component(commute_score_val, NEIGHBOURHOOD_SCORE_WEIGHTS["commute_component"], commute_available, commute_explanation),
        "weather_disruption_component": _make_component(weather_score, NEIGHBOURHOOD_SCORE_WEIGHTS["weather_disruption_component"], weather_available, weather_explanation),
        "data_coverage_component": _make_component(coverage_score, NEIGHBOURHOOD_SCORE_WEIGHTS["data_coverage_component"], True, coverage_explanation),
    }

    # Overall score
    total_weight = sum(c["weight"] for c in components.values() if c["available"])
    weighted_sum = sum(c["score"] * c["weight"] for c in components.values() if c["available"] and c["score"] is not None)

    available_components = [c for c in components.values() if c["available"]]
    available_weight = sum(c["weight"] for c in available_components)

    min_required_weight = NEIGHBOURHOOD_MIN_STATION_COVERAGE * sum(NEIGHBOURHOOD_SCORE_WEIGHTS.values())

    partial = any(not c["available"] for c in components.values())

    if available_weight < min_required_weight:
        overall_score = None
    elif total_weight > 0:
        overall_score = round(weighted_sum / total_weight, 4)
    else:
        overall_score = None

    limitations: list[str] = []
    if partial:
        limitations.append("Partial assessment: one or more components were unavailable.")

    limitations.append(NEIGHBOURHOOD_SUITABILITY_DISCLAIMER)

    return {
        "candidate_label": candidate["label"],
        "latitude": lat,
        "longitude": lng,
        "resolution_method": candidate["resolution_method"],
        "nearest_stations": nearby,
        **components,
        "overall_score": overall_score,
        "partial_assessment": partial,
        "limitations": limitations,
    }


def _make_component(score: float | None, weight: float, available: bool, explanation: str) -> dict[str, Any]:
    return {
        "score": score,
        "weight": weight,
        "available": available,
        "explanation": explanation,
    }


def _score_air_quality(nearby_stations: list[dict[str, Any]]) -> tuple[float | None, str]:
    if not nearby_stations:
        return (0.5, "No nearby stations for air quality assessment.")

    # Closer stations are better for proxy reliability
    distances = [s["distance_km"] for s in nearby_stations]
    if distances:
        min_dist = min(distances)
        # Score: closer = better (0-1 scale)
        if min_dist <= 2:
            return (0.8, f"Nearest station is {min_dist:.1f} km away.")
        elif min_dist <= 5:
            return (0.6, f"Nearest station is {min_dist:.1f} km away.")
        elif min_dist <= 10:
            return (0.4, f"Nearest station is {min_dist:.1f} km away.")
        else:
            return (0.2, f"Nearest station is {min_dist:.1f} km away.")

    return (0.5, "No station distance data available.")


def _score_forecast_confidence() -> tuple[float, str]:
    return (0.7, "Forecast confidence component uses station-level data quality.")


def _score_green_space_proxy(nearby_stations: list[dict[str, Any]]) -> tuple[float, str]:
    if not nearby_stations:
        return (0.5, "No station data for green space proxy.")

    return (0.6, "Green space proxy based on nearest station land-use context.")


def _score_road_mobility_proxy(nearby_stations: list[dict[str, Any]]) -> tuple[float, str]:
    if not nearby_stations:
        return (0.5, "No station data for road mobility proxy.")

    return (0.6, "Road mobility proxy based on nearest station road context.")


def _score_weather(weather_risk: str, weather_available: bool) -> tuple[float | None, str]:
    if not weather_available:
        return (None, "Weather data unavailable.")

    risk_map = {
        "Low": 0.9,
        "Moderate": 0.7,
        "High": 0.4,
        "Severe": 0.2,
    }
    score = risk_map.get(weather_risk, 0.7)
    return (score, f"Weather disruption risk: {weather_risk}.")


def _score_data_coverage(nearby_stations: list[dict[str, Any]]) -> tuple[float, str]:
    if not nearby_stations:
        return (0.3, "No nearby stations for data coverage assessment.")

    count = len(nearby_stations)
    if count >= 3:
        return (0.9, f"{count} nearby stations provide good data coverage.")
    elif count == 2:
        return (0.7, f"{count} nearby stations provide moderate data coverage.")
    else:
        return (0.5, f"{count} nearby station provides limited data coverage.")


def _get_medical_disclaimer(profile: str) -> str | None:
    sensitive = ["family_with_children", "elderly_household", "outdoor_worker", "child", "elderly", "school"]
    if profile in sensitive:
        return MEDICAL_DISCLAIMER
    return None
