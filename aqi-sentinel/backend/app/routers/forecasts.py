from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas.forecast import ForecastResponse
from backend.app.services.forecast_service import get_station_forecasts

router = APIRouter(prefix="/forecast", tags=["forecasts"])


@router.get("/stations", response_model=ForecastResponse)
def station_forecasts() -> ForecastResponse:
    return get_station_forecasts()
