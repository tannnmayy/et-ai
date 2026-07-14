from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.attribution import SourceAttribution


class ScoringBreakdown(BaseModel):
    exposure_weight: float = Field(description="Population/vulnerability exposure weight")
    attributable_magnitude: float = Field(description="Pollution magnitude attributable to actionable sources")
    actionability_weight: float = Field(description="How directly enforceable the dominant source category is")


class Explanation(BaseModel):
    text: str
    generated_by: str


class RankedHexagon(BaseModel):
    h3_cell: str
    name: str | None = None
    priority_score: float
    rank: int
    scoring_breakdown: ScoringBreakdown
    fused_pm25: float | None = None
    source_attribution: SourceAttribution
    method: str
    explanation: Explanation = Field(description="Actionable enforcement guidance for this hexagon")
    # Optional traffic enhancement metadata (backward compatible)
    traffic_corridor_score: float | None = Field(default=None, description="0–1 major-road corridor density score")
    is_major_road_corridor: bool | None = Field(default=None, description="Hex overlaps significant major roads")
    traffic_time_multiplier: float | None = Field(default=None, description="Peak-hour traffic multiplier applied")
    is_peak_hour: bool | None = Field(default=None)
    traffic_hour_local: int | None = Field(default=None)
    traffic_corridor_applied: bool | None = Field(default=None)


class EnforcementPriorityResponse(BaseModel):
    city: str
    computed_at: str
    total_hexagons: int
    top_k: int
    ranked_hexagons: list[RankedHexagon]
    traffic_time_multiplier: float | None = None
    is_peak_hour: bool | None = None
    traffic_hour_local: int | None = None
    traffic_corridor_applied: bool | None = None
