from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.geospatial import (
    CityCoverageSummary,
    FireDetectionResponse,
    NO2ColumnResponse,
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


@router.get(
    "/fire-detections",
    response_model=FireDetectionResponse,
    summary="Per-hexagon fire/burning detections from NASA FIRMS",
    description="Returns VIIRS NOAA-20 active fire detection data aggregated per H3 "
    "resolution-9 cell over a rolling 24-hour window. Data source: NASA FIRMS. "
    "Credentials: FIRMS_MAP_KEY environment variable.",
)
def hex_fire_detections(city: str = "bengaluru") -> FireDetectionResponse:
    """Get FIRMS fire detection data per H3 hexagon."""
    from pipeline.firms_ingestion import get_fire_detections

    return get_fire_detections(city=city)


@router.get(
    "/no2-column-density",
    response_model=NO2ColumnResponse,
    summary="Per-hexagon NO2 column density from Sentinel-5P TROPOMI",
    description="Returns mean tropospheric NO2 column density (mol/m²) per H3 "
    "resolution-9 cell from the Copernicus Sentinel-5P TROPOMI sensor "
    "(COPERNICUS/S5P/OFFL_L3_NO2). Data source: Google Earth Engine. "
    "Credentials: GEE_SERVICE_ACCOUNT_KEY_PATH environment variable.",
)
def hex_no2_column_density(city: str = "bengaluru") -> NO2ColumnResponse:
    """Get Sentinel-5P NO2 column density per H3 hexagon.

    Design note: Fire and NO2 are kept as separate endpoint responses
    rather than merged, because they have fundamentally different update
    cadences (FIRMS: ~3h, Sentinel-5P: ~daily) and availability profiles.
    A combined response would force both to share the worst freshness status.
    """
    from pipeline.sentinel5p_ingestion import get_no2_column_density

    return get_no2_column_density(city=city)
