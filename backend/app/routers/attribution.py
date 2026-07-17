from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.attribution import (
    CityExtremesResponse,
    CityGridAttributionResponse,
    CityGridFusionResponse,
    SingleHexagonResponse,
)
from backend.app.services.attribution_service import (
    get_city_extremes,
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
    "or fell back to pure inverse-distance ('calm_fallback') due to near-zero wind. "
    "Optional simulated_hour (0–23) overrides Bengaluru local time for traffic peak weighting.",
)
def hexagon_attribution(
    h3_cell: str,
    city: str = "bengaluru",
    include_fusion: bool = True,
    simulated_hour: int | None = Query(
        default=None,
        ge=0,
        le=23,
        description="Optional Bengaluru local hour (0–23) for traffic time-of-day simulation",
    ),
) -> SingleHexagonResponse:
    result = get_single_hexagon_attribution(
        h3_cell,
        city=city,
        include_fusion=include_fusion,
        simulated_hour=simulated_hour,
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return SingleHexagonResponse(**result)


@router.get(
    "/city/{city}",
    response_model=CityGridAttributionResponse,
    summary="Get source attribution for all hexagons in a city",
    description="Returns wind-weighted source-category breakdown for every H3 resolution-9 "
    "hexagon in the city. Can optionally include fused PM2.5 estimates. "
    "Optional simulated_hour (0–23) overrides Bengaluru local time for traffic peak weighting.",
)
def city_grid_attribution(
    city: str = "bengaluru",
    include_fusion: bool = False,
    max_hexagons: int | None = Query(
        default=2000,
        ge=-1,
        le=9999,
        description="Evenly sampled grid size (default 2000 for interactive maps; pass -1 for full grid)",
    ),
    simulated_hour: int | None = Query(
        default=None,
        ge=0,
        le=23,
        description="Optional Bengaluru local hour (0–23) for traffic time-of-day simulation",
    ),
) -> CityGridAttributionResponse:
    result = get_city_grid_attribution(
        city=city,
        include_fusion=include_fusion,
        max_hexagons=None if max_hexagons == -1 else max_hexagons,
        simulated_hour=simulated_hour,
    )
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
    max_hexagons: int | None = Query(
        default=2000,
        ge=-1,
        le=9999,
        description="Evenly sampled grid size (default 2000 for interactive maps; pass -1 for full grid)",
    ),
) -> CityGridFusionResponse:
    result = get_city_grid_fusion_only(
        city=city, max_hexagons=None if max_hexagons == -1 else max_hexagons
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return CityGridFusionResponse(**result)


@router.get(
    "/city/{city}/extremes",
    response_model=CityExtremesResponse,
    summary="Get best and worst hexagons by fused PM2.5",
    description="Returns the top N cleanest and top N most polluted hexagons in a city. "
    "Only hexagons with a real fused estimate are included. "
    "mode=global: absolute highest fused PM2.5 (may cluster around one high station). "
    "mode=local_peaks: worst K hexes per station catchment, merged — operational city-wide peaks. "
    "Optional simulated_hour (0–23) overrides Bengaluru local time for traffic peak weighting.",
)
def city_extremes(
    city: str = "bengaluru",
    n: int = Query(default=15, ge=1, le=100, description="Number of best/worst hexagons to return"),
    mode: str = Query(
        default="global",
        description="Worst ranking: 'global' (absolute) or 'local_peaks' (per-station catchments)",
    ),
    peak_k: int = Query(
        default=8,
        ge=1,
        le=20,
        description="Per-station worst-hex count when mode=local_peaks",
    ),
    simulated_hour: int | None = Query(
        default=None,
        ge=0,
        le=23,
        description="Optional Bengaluru local hour (0–23) for traffic time-of-day simulation",
    ),
) -> CityExtremesResponse:
    result = get_city_extremes(
        city=city,
        n=n,
        simulated_hour=simulated_hour,
        mode=mode,
        peak_k=peak_k,
    )
    if "error" in result:
        # Invalid mode → 400; data missing → 503
        detail = result["error"]
        status = 400 if "Unsupported extremes mode" in str(detail) else 503
        raise HTTPException(status_code=status, detail=detail)
    return CityExtremesResponse(**result)
