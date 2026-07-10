from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.attribution import (
    CityGridAttributionResponse,
    CityGridFusionResponse,
    SingleHexagonResponse,
)
from backend.app.services.attribution_service import (
    get_city_grid_attribution,
    get_city_grid_fusion_only,
    get_single_hexagon_attribution,
)

router = APIRouter(prefix="/attribution", tags=["attribution"])


@router.get(
    "/hexagon/{h3_cell}",
    response_model=SingleHexagonResponse,
    summary="Get source attribution and fused PM2.5 for a single hexagon",
    description="Returns wind-weighted source-category breakdown (traffic, industrial, construction, burning) "
    "and optionally a fused PM2.5 estimate via IDW interpolation of nearby station readings. "
    "The method field indicates whether directional weighting was used ('wind_weighted') "
    "or fell back to pure inverse-distance ('calm_fallback') due to near-zero wind.",
)
def hexagon_attribution(
    h3_cell: str,
    city: str = "bengaluru",
    include_fusion: bool = True,
) -> SingleHexagonResponse:
    result = get_single_hexagon_attribution(h3_cell, city=city, include_fusion=include_fusion)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return SingleHexagonResponse(**result)


@router.get(
    "/city/{city}",
    response_model=CityGridAttributionResponse,
    summary="Get source attribution for all hexagons in a city",
    description="Returns wind-weighted source-category breakdown for every H3 resolution-9 "
    "hexagon in the city. Can optionally include fused PM2.5 estimates.",
)
def city_grid_attribution(
    city: str = "bengaluru",
    include_fusion: bool = False,
    max_hexagons: int | None = Query(default=None, ge=1, le=2000, description="Optional evenly sampled grid size for interactive maps"),
) -> CityGridAttributionResponse:
    result = get_city_grid_attribution(city=city, include_fusion=include_fusion, max_hexagons=max_hexagons)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return CityGridAttributionResponse(**result)


@router.get(
    "/city/{city}/fusion",
    response_model=CityGridFusionResponse,
    summary="Get fused PM2.5 estimates for all hexagons in a city",
    description="Returns per-hexagon fused PM2.5 estimates using IDW interpolation of "
    "station reading residuals applied to an attribution-similarity-weighted baseline. "
    "Includes method/status flags for each hexagon's fusion.",
)
def city_grid_fusion(
    city: str = "bengaluru",
) -> CityGridFusionResponse:
    result = get_city_grid_fusion_only(city=city)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return CityGridFusionResponse(**result)
