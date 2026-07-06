from __future__ import annotations

from typing import Any

from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
)
from backend.app.services.citizen_advisory_service import get_citizen_advisory
from backend.app.services.city_briefing_service import get_city_briefing
from backend.app.services.confidence_service import get_forecast_confidence
from backend.app.services.forecast_evidence_service import get_forecast_evidence
from backend.app.services.inspection_priority_service import get_inspection_priorities


def tool_get_forecast_evidence(station_id: str, city: str = "bengaluru") -> dict[str, Any]:
    try:
        return get_forecast_evidence(station_id, city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError) as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_forecast_confidence(station_id: str, city: str = "bengaluru") -> dict[str, Any]:
    try:
        return get_forecast_confidence(station_id, city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError) as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_inspection_priorities(city: str = "bengaluru", top_k: int = 5) -> dict[str, Any]:
    try:
        return get_inspection_priorities(city, top_k=top_k)
    except UnsupportedCityError as e:
        return {"_tool_error": str(e), "_error_type": "UnsupportedCityError"}


def tool_get_citizen_advisory(
    station_id: str, profile: str = "general", language: str = "en", city: str = "bengaluru"
) -> dict[str, Any]:
    try:
        return get_citizen_advisory(station_id, profile=profile, language=language, city=city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError) as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_city_briefing(city: str = "bengaluru") -> dict[str, Any]:
    try:
        return get_city_briefing(city)
    except UnsupportedCityError as e:
        return {"_tool_error": str(e), "_error_type": "UnsupportedCityError"}


def tool_search_policy_guidance(
    query: str,
    city: str | None = None,
    source_types: list[str] | None = None,
    top_k: int = 3,
) -> dict[str, Any]:
    from backend.app.services.policy_guidance_service import search_policy_guidance
    try:
        return search_policy_guidance(query, city=city, source_types=source_types, top_k=top_k)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_weather_forecast(
    city: str = "bengaluru",
    horizon_hours: int = 72,
    refresh: bool = False,
) -> dict[str, Any]:
    from backend.app.services.weather_forecast_service import get_weather_forecast
    try:
        return get_weather_forecast(city=city, horizon_hours=horizon_hours, refresh=refresh)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_weather_summary(
    city: str = "bengaluru",
    period: str = "next_24h",
    refresh: bool = False,
) -> dict[str, Any]:
    from backend.app.services.weather_forecast_service import get_weather_summary
    try:
        return get_weather_summary(city=city, period=period, refresh=refresh)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_travel_readiness(
    city: str = "bengaluru",
    profile: str = "general",
    period: str = "next_24h",
    refresh_weather: bool = False,
) -> dict[str, Any]:
    from backend.app.services.travel_readiness_service import get_travel_readiness
    try:
        return get_travel_readiness(
            city=city, profile=profile, period=period, refresh_weather=refresh_weather,
        )
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}
