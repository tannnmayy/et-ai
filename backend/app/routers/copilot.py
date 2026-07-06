from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.app.agents.orchestrator import run_orchestrator
from backend.app.config import ADVISORY_PROFILES, SUPPORTED_CITIES, SUPPORTED_LANGUAGES, TRAVEL_PROFILES
from backend.app.schemas.copilot import CopilotQueryRequest, CopilotResponse
from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
    _validate_station,
)

router = APIRouter(prefix="/copilot", tags=["copilot"])


def _validate_city(city: str) -> None:
    key = city.lower().strip()
    if key not in SUPPORTED_CITIES:
        raise HTTPException(status_code=404, detail=f"Unsupported city: {city}")


def _validate_station_id(station_id: str) -> None:
    try:
        _validate_station(station_id)
    except UnknownStationError:
        raise HTTPException(status_code=404, detail=f"Unknown station: {station_id}")


def _handle_agent_errors(func, *args, **kwargs) -> dict[str, Any]:
    try:
        return func(*args, **kwargs)
    except UnsupportedCityError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnknownStationError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MissingArtifactError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except NoValidForecastError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post(
    "/query",
    response_model=CopilotResponse,
    summary="Send a natural language query to the AQI copilot",
    description="Routes the query to the appropriate agent based on intent detection. "
    "Returns a structured response with audit trail.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "query": "Why is Peenya a priority tomorrow?",
                        "city": "bengaluru",
                        "station_id": "cpcb_peenya",
                        "profile": "general",
                        "language": "en",
                    }
                }
            }
        }
    },
)
def copilot_query(body: CopilotQueryRequest) -> CopilotResponse:
    _validate_city(body.city)

    if body.station_id:
        _validate_station_id(body.station_id)

    all_profiles = list(set(ADVISORY_PROFILES + TRAVEL_PROFILES))
    if body.profile not in all_profiles:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid profile '{body.profile}'. Supported: {', '.join(sorted(all_profiles))}",
        )
    if body.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid language '{body.language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}",
        )

    result = _handle_agent_errors(
        run_orchestrator,
        station_id=body.station_id,
        city=body.city,
        query=body.query,
        profile=body.profile,
        language=body.language,
        top_k=body.top_k,
    )
    return CopilotResponse(**result)


@router.get(
    "/stations/{station_id}/explain",
    response_model=CopilotResponse,
    summary="Get forecast explanation for a station",
)
def copilot_station_explain(station_id: str) -> CopilotResponse:
    _validate_station_id(station_id)
    result = _handle_agent_errors(
        run_orchestrator,
        station_id=station_id,
        city="bengaluru",
        query="Explain forecast for this station",
        explicit_intent="station_explanation",
    )
    return CopilotResponse(**result)


@router.get(
    "/stations/{station_id}/guidance",
    response_model=CopilotResponse,
    summary="Get citizen health guidance for a station",
)
def copilot_station_guidance(
    station_id: str,
    profile: str = Query(default="general", description="Advisory profile"),
    language: str = Query(default="en", description="Language code"),
) -> CopilotResponse:
    _validate_station_id(station_id)
    all_profiles = list(set(ADVISORY_PROFILES + TRAVEL_PROFILES))
    if profile not in all_profiles:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid profile '{profile}'. Supported: {', '.join(sorted(all_profiles))}",
        )
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid language '{language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}",
        )

    result = _handle_agent_errors(
        run_orchestrator,
        station_id=station_id,
        city="bengaluru",
        query=f"Health guidance for this station",
        profile=profile,
        language=language,
        explicit_intent="citizen_guidance",
    )
    return CopilotResponse(**result)


@router.get(
    "/cities/{city}/inspection-plan",
    response_model=CopilotResponse,
    summary="Get inspection plan for a city",
)
def copilot_city_inspection_plan(
    city: str,
    top_k: int = Query(default=5, ge=1, le=20, description="Number of top stations"),
) -> CopilotResponse:
    _validate_city(city)
    result = _handle_agent_errors(
        run_orchestrator,
        city=city,
        query=f"Inspection plan for {city}",
        top_k=top_k,
        explicit_intent="inspection_plan",
    )
    return CopilotResponse(**result)


@router.get(
    "/cities/{city}/briefing",
    response_model=CopilotResponse,
    summary="Get city briefing",
)
def copilot_city_briefing(city: str) -> CopilotResponse:
    _validate_city(city)
    result = _handle_agent_errors(
        run_orchestrator,
        city=city,
        query=f"Briefing for {city}",
        explicit_intent="city_briefing",
    )
    return CopilotResponse(**result)
