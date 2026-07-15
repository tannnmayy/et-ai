from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.geospatial import (
    CityCoverageSummary,
    FireDetectionResponse,
    NO2ColumnResponse,
    ReverseGeocodeResponse,
    StationGeospatialContext,
)
from backend.app.services.geospatial_evidence_service import (
    GeospatialArtifactMissingError,
    UnknownStationError,
    get_city_geospatial_coverage,
    get_station_geospatial_context,
)

router = APIRouter(prefix="/geospatial", tags=["geospatial"])

_REVERSE_GEOCODE_CACHE: dict[str, dict[str, Any]] = {}


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
    "(COPERNICUS/S5P/OFFL/L3_NO2). Data source: Google Earth Engine. "
    "Credentials: GEE_SERVICE_ACCOUNT_KEY_PATH (+ optional GEE_PROJECT_ID). "
    "Pass refresh=true to force a live GEE re-fetch.",
)
def hex_no2_column_density(
    city: str = "bengaluru",
    refresh: bool = Query(default=False, description="Force live GEE re-fetch"),
) -> NO2ColumnResponse:
    """Get Sentinel-5P NO2 column density per H3 hexagon.

    Design note: Fire and NO2 are kept as separate endpoint responses
    rather than merged, because they have fundamentally different update
    cadences (FIRMS: ~3h, Sentinel-5P: ~daily) and availability profiles.
    A combined response would force both to share the worst freshness status.
    """
    from pipeline.sentinel5p_ingestion import get_no2_column_density

    return get_no2_column_density(city=city, refresh=refresh)


@router.get(
    "/reverse-geocode",
    response_model=ReverseGeocodeResponse,
    summary="Reverse geocode coordinates to a locality name",
    description="Resolves latitude/longitude to a locality or sublocality name using the "
    "Google Geocoding API. Results are cached in-memory by H3 cell ID. "
    "Only hexagons within Bengaluru bounds are supported.",
)
def reverse_geocode(
    lat: float = Query(..., description="Latitude of the point to reverse geocode"),
    lon: float = Query(..., description="Longitude of the point to reverse geocode"),
) -> ReverseGeocodeResponse:
    import h3 as _h3

    h3_cell = _h3.latlng_to_cell(lat, lon, 9)

    cached = _REVERSE_GEOCODE_CACHE.get(h3_cell)
    if cached is not None:
        return ReverseGeocodeResponse(**cached, source_status="cached")

    from backend.app.services.google_maps_client import reverse_geocode as _reverse_geocode

    try:
        result = _reverse_geocode(lat, lon)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("error", "Reverse geocoding failed."))

    data = result["data"]
    entry = {
        "h3_cell": "",
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "locality": data["label"],
        "formatted_address": data["formatted_address"],
        "source_status": "fresh",
    }
    _REVERSE_GEOCODE_CACHE[h3_cell] = entry
    return ReverseGeocodeResponse(h3_cell=h3_cell, **entry)
