from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.geospatial import (
    CityCoverageSummary,
    StationGeospatialContext,
)
from backend.app.services.geospatial_evidence_service import (
    GeospatialArtifactMissingError,
    UnknownStationError,
    get_city_geospatial_coverage,
    get_station_geospatial_context,
)

router = APIRouter(prefix="/geospatial", tags=["geospatial"])


def _handle_errors(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except UnknownStationError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except GeospatialArtifactMissingError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get(
    "/stations/{station_id}/context",
    response_model=StationGeospatialContext,
    summary="Get geospatial context for a station",
    description="Returns road, land-use, and investigation-context features derived "
    "from OpenStreetMap and H3 spatial indexing for a monitoring station.",
)
def station_geospatial_context(
    station_id: str,
    city: str = "bengaluru",
) -> StationGeospatialContext:
    return _handle_errors(get_station_geospatial_context, station_id, city=city)


@router.get(
    "/cities/{city}/coverage",
    response_model=CityCoverageSummary,
    summary="Get geospatial coverage summary for a city",
    description="Returns a summary of geospatial data coverage across all stations in a city.",
)
def city_geospatial_coverage(city: str = "bengaluru") -> CityCoverageSummary:
    return _handle_errors(get_city_geospatial_coverage, city)
