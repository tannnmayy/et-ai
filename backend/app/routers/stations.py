from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.stations import StationInfo, StationListResponse
from backend.app.services.station_discovery_service import list_stations

router = APIRouter(tags=["stations"])


@router.get(
    "/stations",
    response_model=StationListResponse,
    summary="List monitoring stations",
    description="Returns active monitoring stations with their availability status.",
)
def get_stations(city: str = "bengaluru", include_inactive: bool = False) -> StationListResponse:
    stations_data = list_stations(city=city, include_inactive=include_inactive)
    return StationListResponse(
        city=city,
        total_stations=len(stations_data),
        stations=[StationInfo(**s) for s in stations_data],
    )
