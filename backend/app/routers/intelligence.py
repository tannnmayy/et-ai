from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.config import ADVISORY_PROFILES, SUPPORTED_CITIES, SUPPORTED_LANGUAGES
from backend.app.schemas.intelligence import (
    CitizenAdvisoryResponse,
    CityBriefingResponse,
    ForecastConfidenceResponse,
    ForecastEvidenceResponse,
    InspectionPriorityResponse,
)
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

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _handle_errors(func, *args, **kwargs):
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


# ---------------------------------------------------------------------------
# Per-station endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/stations/{station_id}/evidence",
    response_model=ForecastEvidenceResponse,
    summary="Get forecast evidence for a station",
    description="Returns structured evidence explaining the forecast, including model validation, "
    "recent observations, and data quality context.",
)
def station_evidence(station_id: str) -> ForecastEvidenceResponse:
    return _handle_errors(get_forecast_evidence, station_id)


@router.get(
    "/stations/{station_id}/confidence",
    response_model=ForecastConfidenceResponse,
    summary="Get forecast confidence for a station",
    description="Returns a data-reliability confidence score based on freshness, completeness, "
    "gaps, and quality classification. No penalty for persistence selection.",
)
def station_confidence(station_id: str) -> ForecastConfidenceResponse:
    return _handle_errors(get_forecast_confidence, station_id)


@router.get(
    "/stations/{station_id}/advisory",
    response_model=CitizenAdvisoryResponse,
    summary="Get citizen health advisory for a station",
    description="Returns a deterministic health advisory based on forecast risk category, "
    "user profile, and requested language. English fallback for untranslated languages.",
)
def station_advisory(
    station_id: str,
    profile: str = Query(default="general", description="Advisory profile"),
    language: str = Query(default="en", description="Language code (en, hi, kn)"),
) -> CitizenAdvisoryResponse:
    if profile not in ADVISORY_PROFILES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid profile '{profile}'. Supported: {', '.join(ADVISORY_PROFILES)}",
        )
    lang = (language or "en").strip().lower()
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid language '{language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}",
        )
    return _handle_errors(get_citizen_advisory, station_id, profile=profile, language=lang)


# ---------------------------------------------------------------------------
# City endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/cities/{city}/inspection-priorities",
    response_model=InspectionPriorityResponse,
    summary="Get inspection priority ranking for a city",
    description="Deterministic ranking of stations for MPCB inspection based on "
    "forecast severity, confidence, data quality, and recent observations.",
)
def city_inspection_priorities(
    city: str,
    top_k: int = Query(default=5, ge=1, le=20, description="Number of top stations to return"),
) -> InspectionPriorityResponse:
    return _handle_errors(get_inspection_priorities, city, top_k=top_k)


@router.get(
    "/cities/{city}/briefing",
    response_model=CityBriefingResponse,
    summary="Get city operational briefing",
    description="Deterministic city-wide operational briefing with risk assessment, "
    "executive summary, and operational recommendations.",
)
def city_briefing(city: str) -> CityBriefingResponse:
    return _handle_errors(get_city_briefing, city)


# ---------------------------------------------------------------------------
# Convenience aliases (Bengaluru)
# ---------------------------------------------------------------------------

@router.get(
    "/inspection-priorities",
    response_model=InspectionPriorityResponse,
    summary="Get inspection priority ranking for Bengaluru (convenience alias)",
)
def bengaluru_inspection_priorities(
    top_k: int = Query(default=5, ge=1, le=20, description="Number of top stations to return"),
) -> InspectionPriorityResponse:
    return _handle_errors(get_inspection_priorities, "bengaluru", top_k=top_k)


@router.get(
    "/city-briefing",
    response_model=CityBriefingResponse,
    summary="Get Bengaluru city briefing (convenience alias)",
)
def bengaluru_city_briefing() -> CityBriefingResponse:
    return _handle_errors(get_city_briefing, "bengaluru")
