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
