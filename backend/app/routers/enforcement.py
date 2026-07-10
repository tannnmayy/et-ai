from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.enforcement import EnforcementPriorityResponse
from backend.app.services.enforcement_priority_service import compute_enforcement_priorities

router = APIRouter(prefix="/enforcement", tags=["enforcement"])


@router.get(
    "/priority/{city}",
    response_model=EnforcementPriorityResponse,
    summary="Get ranked enforcement priority hexagons for a city",
    description="Returns hexagons ranked by a decomposed actionability x "
    "exposure x magnitude score, so the ranking is inspectable rather "
    "than a black-box number.",
)
def enforcement_priority(city: str, top_k: int = 10) -> EnforcementPriorityResponse:
    result = compute_enforcement_priorities(city=city, top_k=top_k)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return EnforcementPriorityResponse(**result)
