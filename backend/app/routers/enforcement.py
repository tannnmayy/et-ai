from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.enforcement import EnforcementPriorityResponse
from backend.app.services.enforcement_priority_service import compute_enforcement_priorities, get_enforcement_map

router = APIRouter(prefix="/enforcement", tags=["enforcement"])


@router.get("/map/{city}", summary="Get a map-ready current air-quality risk surface")
def enforcement_map(city: str, max_cells: int = 900) -> dict:
    result = get_enforcement_map(city=city, max_cells=max_cells)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get(
    "/priority/{city}",
    response_model=EnforcementPriorityResponse,
    summary="Get ranked enforcement priority hexagons for a city",
    description="Returns hexagons ranked by a decomposed actionability x "
    "exposure x magnitude score, so the ranking is inspectable rather "
    "than a black-box number. Optional simulated_hour (0–23) applies "
    "Bengaluru peak-hour traffic weighting for demos.",
)
def enforcement_priority(
    city: str,
    top_k: int = Query(default=10, ge=1, le=500),
    simulated_hour: int | None = Query(
        default=None,
        ge=0,
        le=23,
        description="Optional Bengaluru local hour for traffic time-of-day simulation",
    ),
) -> EnforcementPriorityResponse:
    result = compute_enforcement_priorities(
        city=city, top_k=top_k, simulated_hour=simulated_hour
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return EnforcementPriorityResponse(**result)
