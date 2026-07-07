from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.config import (
    COMMUTE_MAX_DESTINATIONS,
    COMMUTE_SUPPORTED_MODES,
    GOOGLE_MAPS_SERVER_API_KEY,
)
from backend.app.services.google_maps_client import (
    GoogleMapsUnavailableError,
    GoogleMapsProviderError,
    GoogleMapsValidationError,
    GoogleMapsOutOfScopeError,
    compute_routes,
)


def compute_commute_burden(
    origin_lat: float,
    origin_lng: float,
    workplace_lat: float,
    workplace_lng: float,
    travel_mode: str = "DRIVE",
    school_locations: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    travel_mode_key = travel_mode.upper()
    if travel_mode_key not in COMMUTE_SUPPORTED_MODES:
        travel_mode_key = "DRIVE"

    if school_locations is None:
        school_locations = []

    if len(school_locations) > 2:
        school_locations = school_locations[:2]

    if not GOOGLE_MAPS_SERVER_API_KEY:
        return {
            "commute_available": False,
            "routes": [],
            "total_commute_burden_score": None,
            "error": "Google Maps server API key is not configured.",
            "source_status": "unavailable",
        }

    routes: list[dict[str, Any]] = []
    partial = False
    all_unavailable = True

    # Workplace route
    try:
        route = compute_routes(origin_lat, origin_lng, workplace_lat, workplace_lng, travel_mode_key)
        routes.append({
            "destination_type": "workplace",
            "destination_label": "Workplace",
            **route.get("data", {}),
            "success": route["success"],
        })
        if route["success"]:
            all_unavailable = False
        else:
            partial = True
    except (GoogleMapsUnavailableError, GoogleMapsProviderError, GoogleMapsValidationError, GoogleMapsOutOfScopeError) as e:
        routes.append({
            "destination_type": "workplace",
            "destination_label": "Workplace",
            "success": False,
            "error": str(e),
        })
        partial = True

    # School routes
    for i, school in enumerate(school_locations):
        try:
            route = compute_routes(
                origin_lat, origin_lng,
                school["latitude"], school["longitude"],
                travel_mode_key,
            )
            routes.append({
                "destination_type": "school",
                "destination_label": school.get("label", f"School {i + 1}"),
                **route.get("data", {}),
                "success": route["success"],
            })
            if route["success"]:
                all_unavailable = False
            else:
                partial = True
        except (GoogleMapsUnavailableError, GoogleMapsProviderError, GoogleMapsValidationError, GoogleMapsOutOfScopeError) as e:
            routes.append({
                "destination_type": "school",
                "destination_label": school.get("label", f"School {i + 1}"),
                "success": False,
                "error": str(e),
            })
            partial = True

    if all_unavailable:
        return {
            "commute_available": False,
            "routes": routes,
            "total_commute_burden_score": None,
            "error": "No commute routes could be computed.",
            "source_status": "unavailable",
        }

    # Compute total commute burden score
    total_duration = 0.0
    valid_route_count = 0
    for route in routes:
        if route.get("success") and route.get("duration_seconds") is not None:
            total_duration += route["duration_seconds"]
            valid_route_count += 1

    burden_score = _compute_burden_score(total_duration, valid_route_count)

    limitations: list[str] = []
    if partial:
        limitations.append("One or more route results were unavailable. Burden score is partial.")

    return {
        "commute_available": True,
        "routes": routes,
        "total_commute_burden_score": burden_score,
        "partial_assessment": partial,
        "source_status": "fresh",
        "limitations": limitations,
    }


def _compute_burden_score(total_duration_seconds: float, route_count: int) -> float:
    if route_count == 0 or total_duration_seconds <= 0:
        return 1.0

    avg_duration_minutes = total_duration_seconds / 60.0 / route_count

    # Score 0 (best) to 1 (worst), using a sigmoid-like mapping
    # <15 min avg -> score near 0, >60 min avg -> score near 1
    score = min(1.0, avg_duration_minutes / 60.0)

    return round(score, 4)
