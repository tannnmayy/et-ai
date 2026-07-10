from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.attribution import SourceAttribution


class ScoringBreakdown(BaseModel):
    exposure_weight: float = Field(description="Population/vulnerability exposure weight")
    attributable_magnitude: float = Field(description="Pollution magnitude attributable to actionable sources")
    actionability_weight: float = Field(description="How directly enforceable the dominant source category is")


class RankedHexagon(BaseModel):
    h3_cell: str
    priority_score: float
    rank: int
    scoring_breakdown: ScoringBreakdown
    fused_pm25: float | None = None
    source_attribution: SourceAttribution
    method: str


class EnforcementPriorityResponse(BaseModel):
    city: str
    computed_at: str
    total_hexagons: int
    top_k: int
    ranked_hexagons: list[RankedHexagon]
