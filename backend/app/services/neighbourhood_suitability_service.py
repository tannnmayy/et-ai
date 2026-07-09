from __future__ import annotations

import logging
from typing import Any

import h3
import pandas as pd

from backend.app.config import (
    ADVISORY_PROFILES,
    H3_RESOLUTION,
    MEDICAL_DISCLAIMER,
    NEIGHBOURHOOD_MIN_STATION_COVERAGE,
    NEIGHBOURHOOD_SCORE_WEIGHTS,
    NEIGHBOURHOOD_SUITABILITY_DISCLAIMER,
    TRAVEL_PROFILES,
)
from backend.app.services.attribution_service import (
    _load_hexagon_features,
    get_city_grid_attribution,
    get_single_hexagon_attribution,
)
from backend.app.services.commute_service import compute_commute_burden
from backend.app.services.location_service import resolve_location
from backend.app.services.spatial_intelligence_service import (
    _find_nearby_stations,
    _get_station_coords,
    _haversine_km,
)
from backend.app.services.weather_forecast_service import get_weather_summary
from pipeline.station_registry import BENGALURU_STATIONS

logger = logging.getLogger(__name__)


# Real CPCB National AQI PM2.5 sub-index breakpoints (24-hr avg, µg/m³)
_PM25_AQI_BANDS: list[tuple[float, float, float, str]] = [
    (0, 30, 1.00, "Good"),
    (30, 60, 0.80, "Satisfactory"),
    (60, 90, 0.60, "Moderate"),
    (90, 120, 0.40, "Poor"),
    (120, 250, 0.20, "Very Poor"),
    (250, float("inf"), 0.05, "Severe"),
]


def _pm25_to_score(pm25: float) -> tuple[float, str]:
    for lo, hi, score, label in _PM25_AQI_BANDS:
        if lo <= pm25 < hi:
            return score, label
    return 0.05, "Severe"


_GRID_STATS_CACHE: dict[str, Any] = {}


def _get_grid_normalization_stats() -> dict[str, float] | None:
    if "stats" in _GRID_STATS_CACHE:
        return _GRID_STATS_CACHE["stats"]
    hex_df = _load_hexagon_features()
    if hex_df.empty:
        _GRID_STATS_CACHE["stats"] = None
        return None
    stats = {
        "green_space_fraction_p95": float(hex_df["green_space_fraction"].quantile(0.95)) or 0.01,
        "road_density_p95": float(hex_df["road_density_m_per_sq_m"].quantile(0.95)) or 0.01,
    }
    _GRID_STATS_CACHE["stats"] = stats
    return stats


def _find_hexagon_row(lat: float, lng: float, hex_df: pd.DataFrame) -> pd.Series | None:
    cell = h3.latlng_to_cell(lat, lng, H3_RESOLUTION)
    match = hex_df[hex_df["h3_cell"] == cell]
    if match.empty:
        return None
    return match.iloc[0]


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

    # Air quality component (fused PM2.5 estimate when available)
    candidate_h3_cell = h3.latlng_to_cell(lat, lng, H3_RESOLUTION)
    attribution_result = get_single_hexagon_attribution(candidate_h3_cell, include_fusion=True)
    fused_pm25 = attribution_result.get("fused_pm25") if "error" not in attribution_result else None
    air_quality_score, air_explanation = _score_air_quality(nearby, fused_pm25=fused_pm25)

    confidence_score, conf_explanation = _score_forecast_confidence(lat, lng)

    hex_df = _load_hexagon_features()
    hex_row = _find_hexagon_row(lat, lng, hex_df) if not hex_df.empty else None
    green_space_fraction = float(hex_row["green_space_fraction"]) if hex_row is not None else None
    road_density = float(hex_row["road_density_m_per_sq_m"]) if hex_row is not None else None
    green_score, green_explanation = _score_green_space_proxy(green_space_fraction)
    road_score, road_explanation = _score_road_mobility_proxy(road_density)
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


def _score_air_quality(
    nearby_stations: list[dict[str, Any]],
    fused_pm25: float | None = None,
) -> tuple[float | None, str]:
    if fused_pm25 is not None:
        score, label = _pm25_to_score(fused_pm25)
        return (
            score,
            f"Fused PM2.5 estimate at this location: {fused_pm25:.1f} "
            f"ug/m3 ({label}, CPCB band).",
        )
    if not nearby_stations:
        return (0.5, "No nearby stations and no fused PM2.5 estimate available.")
    distances = [s["distance_km"] for s in nearby_stations]
    min_dist = min(distances)
    if min_dist <= 2:
        proxy_score = 0.8
    elif min_dist <= 5:
        proxy_score = 0.6
    elif min_dist <= 10:
        proxy_score = 0.4
    else:
        proxy_score = 0.2
    return (
        proxy_score,
        f"No fused PM2.5 estimate available for this location; falling "
        f"back to station-proximity proxy (nearest station "
        f"{min_dist:.1f} km away).",
    )


def _score_forecast_confidence(lat: float, lng: float) -> tuple[float, str]:
    eligible_distances: list[float] = []
    for station in BENGALURU_STATIONS:
        if not station.forecast_eligible:
            continue
        coords = _get_station_coords(station.station_id)
        if coords is None:
            continue
        s_lat, s_lng = coords
        eligible_distances.append(_haversine_km(lat, lng, s_lat, s_lng))

    if not eligible_distances:
        return (0.3, "No forecast-eligible stations found in registry.")

    min_dist = min(eligible_distances)
    if min_dist <= 2:
        return (0.9, f"Nearest forecast-eligible station is {min_dist:.1f} km away.")
    elif min_dist <= 5:
        return (0.7, f"Nearest forecast-eligible station is {min_dist:.1f} km away.")
    elif min_dist <= 10:
        return (0.5, f"Nearest forecast-eligible station is {min_dist:.1f} km away.")
    return (
        0.3,
        f"Nearest forecast-eligible station is {min_dist:.1f} km away "
        f"— confidence is low this far from real forecasting infrastructure.",
    )


def _score_green_space_proxy(green_space_fraction: float | None) -> tuple[float, str]:
    stats = _get_grid_normalization_stats()
    if green_space_fraction is None or stats is None:
        return (0.6, "Hexagon land-use data unavailable; using neutral default.")
    p95 = stats["green_space_fraction_p95"]
    score = min(green_space_fraction / p95, 1.0) if p95 > 0 else 0.6
    return (
        round(score, 3),
        f"Green space covers {green_space_fraction * 100:.1f}% of this "
        f"hexagon's area (scored relative to the city-wide distribution).",
    )


def _score_road_mobility_proxy(road_density: float | None) -> tuple[float, str]:
    stats = _get_grid_normalization_stats()
    if road_density is None or stats is None:
        return (0.6, "Hexagon road-density data unavailable; using neutral default.")
    p95 = stats["road_density_p95"]
    normalized = min(road_density / p95, 1.0) if p95 > 0 else 0.5
    score = round(1.0 - normalized, 3)
    return (
        score,
        f"Road density here is in the "
        f"{'top' if normalized > 0.5 else 'bottom'} half of the city's "
        f"range; scored for traffic-pollution exposure risk, not "
        f"connectivity.",
    )


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


def get_grid_suitability(city: str = "bengaluru") -> dict[str, Any]:
    grid_attribution = get_city_grid_attribution(city, include_fusion=True)
    if "error" in grid_attribution:
        return {"error": grid_attribution["error"]}

    hex_df = _load_hexagon_features()
    if hex_df.empty:
        return {"error": "Hexagon features not available. Run pipeline/build_hexagon_features.py first."}

    hex_features_by_cell = hex_df.set_index("h3_cell").to_dict("index")
    stats = _get_grid_normalization_stats()

    weather_summary = get_weather_summary(period="tomorrow")
    weather_risk = weather_summary.get("weather_risk_level", "Moderate")
    weather_available = weather_summary.get("source_status") != "unavailable"
    weather_score, weather_explanation = _score_weather(weather_risk, weather_available)

    results = []
    for hex_result in grid_attribution["hexagons"]:
        h3_cell = hex_result["h3_cell"]
        lat = hex_result["center_lat"]
        lng = hex_result["center_lon"]
        fused_pm25 = hex_result.get("fused_pm25")

        features = hex_features_by_cell.get(h3_cell, {})
        green_space_fraction = features.get("green_space_fraction")
        road_density = features.get("road_density_m_per_sq_m")

        nearby = _find_nearby_stations(lat, lng, max_results=3)

        air_score, air_explanation = _score_air_quality(nearby, fused_pm25=fused_pm25)
        conf_score, conf_explanation = _score_forecast_confidence(lat, lng)
        green_score, green_explanation = _score_green_space_proxy(green_space_fraction)
        road_score, road_explanation = _score_road_mobility_proxy(road_density)
        coverage_score, coverage_explanation = _score_data_coverage(nearby)

        components = {
            "air_quality_component": _make_component(air_score, NEIGHBOURHOOD_SCORE_WEIGHTS["air_quality_component"], True, air_explanation),
            "forecast_confidence_component": _make_component(conf_score, NEIGHBOURHOOD_SCORE_WEIGHTS["forecast_confidence_component"], True, conf_explanation),
            "green_space_proxy_component": _make_component(green_score, NEIGHBOURHOOD_SCORE_WEIGHTS["green_space_proxy_component"], True, green_explanation),
            "road_mobility_proxy_component": _make_component(road_score, NEIGHBOURHOOD_SCORE_WEIGHTS["road_mobility_proxy_component"], True, road_explanation),
            "weather_disruption_component": _make_component(weather_score, NEIGHBOURHOOD_SCORE_WEIGHTS["weather_disruption_component"], weather_available, weather_explanation),
            "data_coverage_component": _make_component(coverage_score, NEIGHBOURHOOD_SCORE_WEIGHTS["data_coverage_component"], True, coverage_explanation),
        }

        grid_only_weights = {k: v for k, v in NEIGHBOURHOOD_SCORE_WEIGHTS.items() if k != "commute_component"}
        total_weight = sum(grid_only_weights[name] for name, c in components.items() if c["available"])
        weighted_sum = sum(c["score"] * grid_only_weights[name] for name, c in components.items() if c["available"] and c["score"] is not None)
        overall_score = round(weighted_sum / total_weight, 4) if total_weight > 0 else None

        results.append({
            "h3_cell": h3_cell,
            "center_lat": lat,
            "center_lon": lng,
            **components,
            "overall_score": overall_score,
        })

    return {
        "city": city,
        "computed_at": grid_attribution["computed_at"],
        "hexagon_count": len(results),
        "hexagons": results,
        "warnings": [
            "commute_component is not included in grid-wide scores; it requires a specific workplace/school and is only computed by compare_neighbourhoods().",
        ],
    }
