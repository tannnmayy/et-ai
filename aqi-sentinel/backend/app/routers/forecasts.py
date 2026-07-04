from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas.forecast import (
    ForecastResponse,
    MultiStationForecastResponse,
    MultiStationStationForecast,
    RealHebbalForecastResponse,
    StationStatusResponse,
)
from backend.app.services.forecast_service import (
    get_multistation_forecasts,
    get_real_hebbal_forecast,
    get_real_station_forecast,
    get_station_forecasts,
    get_station_status,
)

router = APIRouter(prefix="/forecast", tags=["forecasts"])


@router.get("/stations", response_model=ForecastResponse)
def station_forecasts() -> ForecastResponse:
    return get_station_forecasts()


@router.get("/real/hebbal", response_model=RealHebbalForecastResponse)
def real_hebbal_forecast() -> RealHebbalForecastResponse:
    return get_real_hebbal_forecast()


@router.get("/real/multistation", response_model=MultiStationForecastResponse)
def real_multistation_forecast() -> MultiStationForecastResponse:
    return get_multistation_forecasts()


@router.get("/real/stations/status", response_model=StationStatusResponse)
def real_station_status() -> StationStatusResponse:
    return get_station_status()


@router.get("/real/{station_id}", response_model=MultiStationStationForecast)
def real_station_forecast(station_id: str) -> MultiStationStationForecast:
    return get_real_station_forecast(station_id)
