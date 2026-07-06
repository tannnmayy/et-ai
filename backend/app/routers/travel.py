from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.config import SUPPORTED_CITIES, TRAVEL_PROFILES
from backend.app.schemas.travel import TravelReadinessResponse
from backend.app.services.travel_readiness_service import get_travel_readiness

router = APIRouter(prefix="/travel", tags=["travel"])


@router.get(
    "/readiness",
    response_model=TravelReadinessResponse,
    summary="Get travel readiness assessment",
    description="Combines weather forecast and air-quality data into a deterministic "
    "travel-readiness recommendation. Supports profile-specific precautions.",
)
def travel_readiness(
    city: str = Query(default="bengaluru", description="City name"),
    profile: str = Query(default="general", description="User profile for tailored precautions"),
    period: str = Query(
        default="tomorrow", description="Time period: next_24h or tomorrow",
    ),
    refresh_weather: bool = Query(default=False, description="Bypass weather cache"),
) -> TravelReadinessResponse:
    if city.lower().strip() not in SUPPORTED_CITIES:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported city: {city}. Only 'bengaluru' is supported.",
        )
    if profile.lower().strip() not in TRAVEL_PROFILES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid profile '{profile}'. Supported: {', '.join(TRAVEL_PROFILES)}",
        )
    if period not in ("next_24h", "tomorrow"):
        raise HTTPException(
            status_code=422,
            detail="Invalid period. Supported: 'next_24h' or 'tomorrow'",
        )
    result = get_travel_readiness(
        city=city, profile=profile, period=period, refresh_weather=refresh_weather,
    )
    if result.get("readiness_basis") == "unavailable":
        raise HTTPException(status_code=503, detail=result.get("warnings", ["Data unavailable"])[0])
    return TravelReadinessResponse(**result)
