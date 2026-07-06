from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.config import SUPPORTED_CITIES, WEATHER_FORECAST_HORIZON_HOURS, WEATHER_SUMMARY_PERIODS
from backend.app.schemas.weather import WeatherForecastResponse, WeatherSummaryResponse
from backend.app.services.weather_forecast_service import (
    WeatherDataError,
    WeatherProviderError,
    get_weather_forecast,
    get_weather_summary,
)

router = APIRouter(prefix="/weather", tags=["weather"])


def _handle_errors(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except (WeatherProviderError, WeatherDataError) as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get(
    "/forecast",
    response_model=WeatherForecastResponse,
    summary="Get weather forecast for a city",
    description="Returns normalized hourly weather forecast from Open-Meteo. "
    "Supports caching and stale-cache fallback.",
)
def weather_forecast(
    city: str = Query(default="bengaluru", description="City name"),
    horizon_hours: int = Query(
        default=WEATHER_FORECAST_HORIZON_HOURS,
        ge=1,
        le=WEATHER_FORECAST_HORIZON_HOURS,
        description="Forecast horizon in hours",
    ),
    refresh: bool = Query(default=False, description="Bypass cache and fetch fresh data"),
) -> WeatherForecastResponse:
    if city.lower().strip() not in SUPPORTED_CITIES:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported city: {city}. Only 'bengaluru' is supported.",
        )
    result = _handle_errors(get_weather_forecast, city=city, horizon_hours=horizon_hours, refresh=refresh)
    if result.get("source_status") == "unavailable":
        raise HTTPException(status_code=503, detail=result.get("warnings", ["Weather data unavailable"])[0])
    hourly = result.get("hourly", [])
    result["hourly_count"] = len(hourly)

    summary_periods = {}
    for period in WEATHER_SUMMARY_PERIODS:
        try:
            summary = get_weather_summary(city=city, period=period, refresh=False)
            if summary.get("source_status") != "unavailable":
                summary_periods[period] = summary
        except Exception:
            pass
    result["summary_periods"] = summary_periods
    return WeatherForecastResponse(**result)


@router.get(
    "/summary",
    response_model=WeatherSummaryResponse,
    summary="Get deterministic weather summary for a period",
    description="Returns aggregated weather summary (temperature range, precipitation, "
    "wind, risk level) for the requested period.",
)
def weather_summary(
    city: str = Query(default="bengaluru", description="City name"),
    period: str = Query(default="next_24h", description="Summary period: next_24h or tomorrow"),
    refresh: bool = Query(default=False, description="Bypass cache and fetch fresh data"),
) -> WeatherSummaryResponse:
    if city.lower().strip() not in SUPPORTED_CITIES:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported city: {city}. Only 'bengaluru' is supported.",
        )
    if period not in WEATHER_SUMMARY_PERIODS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid period '{period}'. Supported: {', '.join(WEATHER_SUMMARY_PERIODS)}",
        )
    result = _handle_errors(get_weather_summary, city=city, period=period, refresh=refresh)
    if result.get("source_status") == "unavailable":
        raise HTTPException(status_code=503, detail=result.get("warnings", ["Weather data unavailable"])[0])
    return WeatherSummaryResponse(**result)
