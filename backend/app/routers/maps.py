from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.maps import GeocodeResponse, GeocodeResult, RouteRequest, RouteResponse, RouteResult
from backend.app.services.google_maps_client import (
    GoogleMapsUnavailableError,
    GoogleMapsValidationError,
    GoogleMapsProviderError,
    GoogleMapsOutOfScopeError,
    geocode_address,
    compute_routes,
)
from backend.app.services.location_service import resolve_location

router = APIRouter(prefix="/maps", tags=["maps"])


@router.get(
    "/geocode",
    response_model=GeocodeResponse,
    summary="Geocode a free-text address or place query",
    description="Resolves a text query to coordinates using the Google Geocoding API. "
    "Requires the server API key to be configured.",
)
def geocode(
    q: str = Query(..., description="Free-text address or place query"),
) -> GeocodeResponse:
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty.")

    try:
        result = geocode_address(q)
    except GoogleMapsUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except GoogleMapsValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except GoogleMapsProviderError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except GoogleMapsOutOfScopeError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not result["success"]:
        return GeocodeResponse(
            success=False,
            data=None,
            provider_status=result.get("provider_status", "ERROR"),
            source_status=result.get("source_status", "unavailable"),
            resolution_method="geocoding",
            limitations=[result.get("error", "Geocoding failed.")],
        )

    data = result["data"]
    return GeocodeResponse(
        success=True,
        data=GeocodeResult(
            label=data["label"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            formatted_address=data["formatted_address"],
            place_id=data.get("place_id"),
        ),
        provider_status=result["provider_status"],
        source_status=result["source_status"],
        resolution_method="geocoding",
    )


@router.post(
    "/route",
    response_model=RouteResponse,
    summary="Compute a route between two locations",
    description="Computes driving, transit, or walking route using Google Routes API. "
    "Returns distance, duration, and traffic-aware duration if available.",
)
def route(body: RouteRequest) -> RouteResponse:
    supported_modes = ["DRIVE", "TWO_WHEELER", "TRANSIT", "WALK"]
    if body.travel_mode.upper() not in supported_modes:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported travel mode '{body.travel_mode}'. Supported: {', '.join(supported_modes)}",
        )

    try:
        result = compute_routes(
            origin_lat=body.origin.latitude,
            origin_lng=body.origin.longitude,
            destination_lat=body.destination.latitude,
            destination_lng=body.destination.longitude,
            travel_mode=body.travel_mode,
        )
    except GoogleMapsUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except GoogleMapsValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except GoogleMapsProviderError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except GoogleMapsOutOfScopeError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not result["success"]:
        return RouteResponse(
            success=False,
            data=None,
            error=result.get("error", "Route computation failed."),
        )

    data = result["data"]
    return RouteResponse(
        success=True,
        data=RouteResult(
            distance_meters=data["distance_meters"],
            duration_seconds=data["duration_seconds"],
            duration_in_traffic_seconds=data.get("duration_in_traffic_seconds"),
            travel_mode=data["travel_mode"],
            provider_status=data["provider_status"],
            source_status=data["source_status"],
            obtained_at=data["obtained_at"],
            limitations=data.get("limitations", []),
        ),
    )
