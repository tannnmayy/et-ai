from __future__ import annotations

from typing import Any

from backend.app.config import BENGALURU_BOUNDING_BOX, GOOGLE_MAPS_SERVER_API_KEY
from backend.app.services.google_maps_client import (
    GoogleMapsUnavailableError,
    GoogleMapsValidationError,
    GoogleMapsOutOfScopeError,
    geocode_address,
)


def resolve_location(query: str = "", latitude: float | None = None, longitude: float | None = None) -> dict[str, Any]:
    if not query and (latitude is None or longitude is None):
        return {
            "success": False,
            "error": "Either a query or coordinates must be provided.",
            "source_status": "unavailable",
        }

    if latitude is not None and longitude is not None:
        try:
            lat = float(latitude)
            lng = float(longitude)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": "Invalid coordinates.",
                "source_status": "unavailable",
            }

        bbox = BENGALURU_BOUNDING_BOX
        if not (bbox["south"] <= lat <= bbox["north"]):
            return {
                "success": False,
                "error": f"Latitude {lat} is outside Bengaluru bounds.",
                "source_status": "out_of_scope",
            }
        if not (bbox["west"] <= lng <= bbox["east"]):
            return {
                "success": False,
                "error": f"Longitude {lng} is outside Bengaluru bounds.",
                "source_status": "out_of_scope",
            }

        return {
            "success": True,
            "label": f"{lat:.4f}, {lng:.4f}",
            "latitude": lat,
            "longitude": lng,
            "resolution_method": "direct_coordinates",
            "city_scope": "bengaluru",
            "source_status": "fresh",
            "limitations": [],
        }

    if not query or not query.strip():
        return {
            "success": False,
            "error": "Query must not be empty.",
            "source_status": "unavailable",
        }

    if not GOOGLE_MAPS_SERVER_API_KEY:
        return {
            "success": False,
            "error": "Google Maps server API key is not configured. Geocoding unavailable.",
            "source_status": "unavailable",
        }

    try:
        geo_result = geocode_address(query)

        if not geo_result["success"]:
            return {
                "success": False,
                "error": geo_result.get("error", "Geocoding failed."),
                "source_status": geo_result.get("source_status", "unavailable"),
            }

        data = geo_result["data"]
        return {
            "success": True,
            "label": data["label"],
            "latitude": data["latitude"],
            "longitude": data["longitude"],
            "resolution_method": "geocoding",
            "city_scope": "bengaluru",
            "source_status": "fresh",
            "limitations": [],
        }
    except (GoogleMapsUnavailableError, GoogleMapsValidationError, GoogleMapsOutOfScopeError) as e:
        return {
            "success": False,
            "error": str(e),
            "source_status": "unavailable",
        }


def resolve_location_or_raise(query: str = "", latitude: float | None = None, longitude: float | None = None) -> dict[str, Any]:
    result = resolve_location(query=query, latitude=latitude, longitude=longitude)
    if not result["success"]:
        raise GoogleMapsValidationError(result.get("error", "Location resolution failed."))
    return result
