from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.app.config import (
    BENGALURU_BOUNDING_BOX,
    GOOGLE_MAPS_BENGALURU_ONLY,
    GOOGLE_MAPS_GEOCODING_ENABLED,
    GOOGLE_MAPS_MAX_RETRIES,
    GOOGLE_MAPS_PLACES_ENABLED,
    GOOGLE_MAPS_ROUTES_ENABLED,
    GOOGLE_MAPS_SERVER_API_KEY,
    GOOGLE_MAPS_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class GoogleMapsUnavailableError(Exception):
    def __init__(self, detail: str = "Google Maps API is unavailable.") -> None:
        super().__init__(detail)
        self.detail = detail


class GoogleMapsValidationError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class GoogleMapsProviderError(Exception):
    def __init__(self, detail: str, status_code: int = 500) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class GoogleMapsOutOfScopeError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


# ---------------------------------------------------------------------------
# Bounding-box validation
# ---------------------------------------------------------------------------


def _validate_bengaluru_coordinates(latitude: float, longitude: float) -> None:
    if not GOOGLE_MAPS_BENGALURU_ONLY:
        return
    bbox = BENGALURU_BOUNDING_BOX
    if not (bbox["south"] <= latitude <= bbox["north"]):
        raise GoogleMapsOutOfScopeError(
            f"Latitude {latitude} is outside Bengaluru bounds "
            f"({bbox['south']} to {bbox['north']})."
        )
    if not (bbox["west"] <= longitude <= bbox["east"]):
        raise GoogleMapsOutOfScopeError(
            f"Longitude {longitude} is outside Bengaluru bounds "
            f"({bbox['west']} to {bbox['east']})."
        )


# ---------------------------------------------------------------------------
# HTTP client helpers
# ---------------------------------------------------------------------------


def _get_server_key() -> str:
    if not GOOGLE_MAPS_SERVER_API_KEY:
        raise GoogleMapsUnavailableError(
            "Google Maps server API key is not configured."
        )
    return GOOGLE_MAPS_SERVER_API_KEY


def _build_client() -> httpx.Client:
    return httpx.Client(timeout=GOOGLE_MAPS_TIMEOUT_SECONDS)


def _normalize_geocode_response(raw: dict[str, Any]) -> dict[str, Any]:
    status = raw.get("status", "")
    if status != "OK":
        if status in ("ZERO_RESULTS",):
            return {
                "success": False,
                "provider_status": status,
                "source_status": "unavailable",
                "error": "No geocoding results found.",
            }
        return {
            "success": False,
            "provider_status": status,
            "source_status": "unavailable",
            "error": f"Geocoding API error: {status}",
        }

    results = raw.get("results", [])
    if not results:
        return {
            "success": False,
            "provider_status": status,
            "source_status": "unavailable",
            "error": "Empty geocoding results.",
        }

    first = results[0]
    geometry = first.get("geometry", {})
    location = geometry.get("location", {})

    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        return {
            "success": False,
            "provider_status": status,
            "source_status": "unavailable",
            "error": "Geocoding result missing coordinates.",
        }

    try:
        _validate_bengaluru_coordinates(float(lat), float(lng))
    except GoogleMapsOutOfScopeError:
        return {
            "success": False,
            "provider_status": status,
            "source_status": "out_of_scope",
            "error": "Geocoding result is outside Bengaluru bounds.",
        }

    return {
        "success": True,
        "provider_status": status,
        "source_status": "fresh",
        "data": {
            "label": first.get("formatted_address", str(lat)),
            "latitude": float(lat),
            "longitude": float(lng),
            "formatted_address": first.get("formatted_address", ""),
            "place_id": first.get("place_id"),
        },
    }


def _parse_duration_string(duration: str) -> int | None:
    """Parse '1234s' to integer seconds."""
    if not isinstance(duration, str) or not duration.endswith("s"):
        return None
    try:
        return int(duration[:-1])
    except ValueError:
        return None


def _normalize_routes_v2_response(raw: dict[str, Any], travel_mode: str) -> dict[str, Any]:
    routes = raw.get("routes", [])
    if not routes:
        return {
            "success": False,
            "provider_status": "ZERO_RESULTS",
            "source_status": "unavailable",
            "error": "No routes returned.",
        }

    first_route = routes[0]
    duration_str = first_route.get("duration", "")
    distance = first_route.get("distanceMeters")

    if not duration_str or distance is None:
        return {
            "success": False,
            "provider_status": "ERROR",
            "source_status": "unavailable",
            "error": "Route missing duration or distance.",
        }

    duration_seconds = _parse_duration_string(duration_str)
    if duration_seconds is None:
        return {
            "success": False,
            "provider_status": "ERROR",
            "source_status": "unavailable",
            "error": f"Could not parse duration: {duration_str}",
        }

    limitations: list[str] = [
        "Duration reflects live traffic conditions via TRAFFIC_AWARE routing preference."
    ]

    return {
        "success": True,
        "provider_status": "OK",
        "source_status": "fresh",
        "data": {
            "distance_meters": float(distance),
            "duration_seconds": float(duration_seconds),
            "duration_in_traffic_seconds": None,
            "travel_mode": travel_mode,
            "provider_status": "OK",
            "source_status": "fresh",
            "obtained_at": datetime.now(tz=timezone.utc).isoformat(),
            "limitations": limitations,
        },
    }


def _validate_provider_response(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise GoogleMapsValidationError("Provider response is not a valid JSON object.")
    if "status" not in raw:
        raise GoogleMapsValidationError("Provider response missing 'status' field.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def geocode_address(query: str) -> dict[str, Any]:
    if not GOOGLE_MAPS_GEOCODING_ENABLED:
        raise GoogleMapsUnavailableError("Geocoding is disabled.")

    if not query or not query.strip():
        raise GoogleMapsValidationError("Geocoding query must not be empty.")

    key = _get_server_key()

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": query.strip(),
        "key": key,
        "region": "in",
        "components": "country:IN",
    }

    last_error: Exception | None = None
    for attempt in range(1 + GOOGLE_MAPS_MAX_RETRIES):
        try:
            with _build_client() as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                raw = response.json()
                _validate_provider_response(raw)
                return _normalize_geocode_response(raw)
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning("Geocoding timeout (attempt %d/%d)", attempt + 1, 1 + GOOGLE_MAPS_MAX_RETRIES)
        except httpx.HTTPStatusError as e:
            raise GoogleMapsProviderError(
                f"Geocoding API HTTP error: {e.response.status_code}",
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            last_error = e
            logger.warning("Geocoding request error (attempt %d/%d): %s", attempt + 1, 1 + GOOGLE_MAPS_MAX_RETRIES, e)

    raise GoogleMapsUnavailableError(
        f"Geocoding unavailable after {1 + GOOGLE_MAPS_MAX_RETRIES} attempts: {last_error}"
    )


def _extract_locality(results: list[dict[str, Any]]) -> str | None:
    for result in results:
        for component in result.get("address_components", []):
            types = component.get("types", [])
            if "sublocality" in types or "locality" in types:
                return component.get("long_name")
    return None


def reverse_geocode(latitude: float, longitude: float) -> dict[str, Any]:
    if not GOOGLE_MAPS_GEOCODING_ENABLED:
        raise GoogleMapsUnavailableError("Geocoding is disabled.")

    _validate_bengaluru_coordinates(latitude, longitude)
    key = _get_server_key()

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{latitude},{longitude}",
        "key": key,
        "region": "in",
        "result_type": "sublocality|locality|political",
    }

    last_error: Exception | None = None
    for attempt in range(1 + GOOGLE_MAPS_MAX_RETRIES):
        try:
            with _build_client() as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                raw = response.json()
                _validate_provider_response(raw)

                status = raw.get("status", "")
                if status != "OK":
                    return {
                        "success": False,
                        "provider_status": status,
                        "source_status": "unavailable",
                        "error": f"Reverse geocoding API error: {status}",
                    }

                results = raw.get("results", [])
                if not results:
                    return {
                        "success": False,
                        "provider_status": status,
                        "source_status": "unavailable",
                        "error": "No reverse geocoding results found.",
                    }

                locality = _extract_locality(results)
                if not locality:
                    locality = results[0].get("formatted_address", "Unknown Area")

                return {
                    "success": True,
                    "provider_status": status,
                    "source_status": "fresh",
                    "data": {
                        "label": locality,
                        "latitude": latitude,
                        "longitude": longitude,
                        "formatted_address": results[0].get("formatted_address", ""),
                        "place_id": results[0].get("place_id"),
                    },
                }
        except GoogleMapsOutOfScopeError:
            raise
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning("Reverse geocoding timeout (attempt %d/%d)", attempt + 1, 1 + GOOGLE_MAPS_MAX_RETRIES)
        except httpx.HTTPStatusError as e:
            raise GoogleMapsProviderError(
                f"Reverse geocoding API HTTP error: {e.response.status_code}",
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            last_error = e
            logger.warning("Reverse geocoding request error (attempt %d/%d): %s", attempt + 1, 1 + GOOGLE_MAPS_MAX_RETRIES, e)

    raise GoogleMapsUnavailableError(
        f"Reverse geocoding unavailable after {1 + GOOGLE_MAPS_MAX_RETRIES} attempts: {last_error}"
    )


def _build_routes_v2_body(
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    travel_mode: str,
) -> dict[str, Any]:
    mode_mapping: dict[str, str] = {
        "DRIVE": "DRIVE",
        "TWO_WHEELER": "DRIVE",
        "TRANSIT": "TRANSIT",
        "WALK": "WALK",
        "BICYCLE": "BICYCLE",
    }
    api_mode = mode_mapping.get(travel_mode.upper(), "DRIVE")

    return {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": origin_lat,
                    "longitude": origin_lng,
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": destination_lat,
                    "longitude": destination_lng,
                }
            }
        },
        "travelMode": api_mode,
        "routingPreference": "TRAFFIC_AWARE",
    }


def _parse_routes_v2_error(response: httpx.Response) -> str:
    try:
        error_body = response.json()
        error_info = error_body.get("error", {})
        status = error_info.get("status", "UNKNOWN")
        message = error_info.get("message", "")
        code = error_info.get("code", 0)
        detail = f"{status} ({code})"
        if message:
            detail += f" - {message}"
        return f"Routes API error: {detail}"
    except Exception:
        return f"Routes API HTTP error: {response.status_code}"


def compute_routes(
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    travel_mode: str = "DRIVE",
) -> dict[str, Any]:
    if not GOOGLE_MAPS_ROUTES_ENABLED:
        raise GoogleMapsUnavailableError("Routes API is disabled.")

    _validate_bengaluru_coordinates(origin_lat, origin_lng)
    _validate_bengaluru_coordinates(destination_lat, destination_lng)

    key = _get_server_key()

    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.staticDuration,routes.routeLabels",
    }
    body = _build_routes_v2_body(origin_lat, origin_lng, destination_lat, destination_lng, travel_mode)

    last_error: Exception | None = None
    for attempt in range(1 + GOOGLE_MAPS_MAX_RETRIES):
        try:
            with _build_client() as client:
                response = client.post(url, headers=headers, json=body)
                response.raise_for_status()
                raw = response.json()
                result = _normalize_routes_v2_response(raw, travel_mode.upper())
                if result["success"]:
                    limitations = result["data"]["limitations"]
                    if travel_mode.upper() == "TWO_WHEELER":
                        limitations.append(
                            "Route calculated using driving mode with two-wheeler label. "
                            "Actual two-wheeler route may differ."
                        )
                return result
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning("Routes timeout (attempt %d/%d)", attempt + 1, 1 + GOOGLE_MAPS_MAX_RETRIES)
        except httpx.HTTPStatusError as e:
            error_detail = _parse_routes_v2_error(e.response)
            raise GoogleMapsProviderError(
                error_detail,
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            last_error = e
            logger.warning("Routes request error (attempt %d/%d): %s", attempt + 1, 1 + GOOGLE_MAPS_MAX_RETRIES, e)

    raise GoogleMapsUnavailableError(
        f"Routes API unavailable after {1 + GOOGLE_MAPS_MAX_RETRIES} attempts: {last_error}"
    )


def resolve_place(query: str) -> dict[str, Any]:
    if not GOOGLE_MAPS_PLACES_ENABLED:
        raise GoogleMapsUnavailableError("Places API is disabled.")

    if not query or not query.strip():
        raise GoogleMapsValidationError("Places query must not be empty.")

    key = _get_server_key()

    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": query.strip(),
        "inputtype": "textquery",
        "fields": "formatted_address,geometry,name,place_id",
        "key": key,
    }

    last_error: Exception | None = None
    for attempt in range(1 + GOOGLE_MAPS_MAX_RETRIES):
        try:
            with _build_client() as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                raw = response.json()
                _validate_provider_response(raw)

                status = raw.get("status", "")
                if status != "OK":
                    return {
                        "success": False,
                        "provider_status": status,
                        "source_status": "unavailable",
                        "error": f"Places API error: {status}",
                    }

                candidates = raw.get("candidates", [])
                if not candidates:
                    return {
                        "success": False,
                        "provider_status": status,
                        "source_status": "unavailable",
                        "error": "No place results found.",
                    }

                first = candidates[0]
                geometry = first.get("geometry", {})
                location = geometry.get("location", {})
                lat = location.get("lat")
                lng = location.get("lng")

                if lat is not None and lng is not None:
                    _validate_bengaluru_coordinates(float(lat), float(lng))

                return {
                    "success": True,
                    "provider_status": status,
                    "source_status": "fresh",
                    "data": {
                        "label": first.get("name", query.strip()),
                        "latitude": float(lat) if lat is not None else None,
                        "longitude": float(lng) if lng is not None else None,
                        "formatted_address": first.get("formatted_address", ""),
                        "place_id": first.get("place_id"),
                    },
                }
        except GoogleMapsOutOfScopeError:
            raise
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning("Places timeout (attempt %d/%d)", attempt + 1, 1 + GOOGLE_MAPS_MAX_RETRIES)
        except httpx.HTTPStatusError as e:
            raise GoogleMapsProviderError(
                f"Places API HTTP error: {e.response.status_code}",
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            last_error = e
            logger.warning("Places request error (attempt %d/%d): %s", attempt + 1, 1 + GOOGLE_MAPS_MAX_RETRIES, e)

    raise GoogleMapsUnavailableError(
        f"Places API unavailable after {1 + GOOGLE_MAPS_MAX_RETRIES} attempts: {last_error}"
    )
