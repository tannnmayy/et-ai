from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.attribution import SourceAttribution


class ScoringBreakdown(BaseModel):
    exposure_weight: float = Field(description="Population/vulnerability exposure weight")
    attributable_magnitude: float = Field(description="Pollution magnitude attributable to actionable sources")
    actionability_weight: float = Field(description="How directly enforceable the dominant source category is")
    risk_confidence_factor: float | None = Field(
        default=None,
        description="0.35–1.0 factor from attribution confidence used in risk-adjusted score",
    )
    # Deprecated for Map UI (often inconsistent); still used by Enforcement risk-adjust.
    attribution_confidence_score: int | None = Field(
        default=None,
        description="0–100 attribution reliability score",
    )


class Explanation(BaseModel):
    text: str
    generated_by: str


class RankedHexagon(BaseModel):
    h3_cell: str
    name: str | None = None
    location_name: str | None = Field(
        default=None,
        description="Human-readable locality (preferred display label over h3_cell)",
    )
    center_lat: float | None = None
    center_lon: float | None = None
    priority_score: float
    risk_adjusted_score: float | None = Field(
        default=None,
        description="base_priority × confidence_factor (risk-adjusted)",
    )
    base_rank: int | None = Field(
        default=None,
        description="Rank under unadjusted priority_score (for comparison)",
    )
    rank: int
    scoring_breakdown: ScoringBreakdown
    fused_pm25: float | None = None
    source_attribution: SourceAttribution
    method: str
    explanation: Explanation = Field(description="Actionable enforcement guidance for this hexagon")
    # Optional traffic enhancement metadata (backward compatible)
    traffic_corridor_score: float | None = Field(default=None, description="0–1 major-road corridor density score")
    is_major_road_corridor: bool | None = Field(default=None, description="Hex overlaps significant major roads")
    is_traffic_corridor: bool | None = Field(
        default=None,
        description="True when traffic_corridor_score > 0.4 or major-road corridor flag is set",
    )
    traffic_time_multiplier: float | None = Field(default=None, description="Peak-hour traffic multiplier applied")
    is_peak_hour: bool | None = Field(default=None)
    traffic_hour_local: int | None = Field(default=None)
    traffic_corridor_applied: bool | None = Field(default=None)
    # Attribution confidence — kept for Enforcement risk-adjust; deprecated on Map UI
    attribution_confidence_score: int | None = Field(
        default=None,
        description="Deprecated for Map UI; 0–100 reliability used by risk-adjusted enforcement",
    )
    attribution_confidence_level: str | None = Field(
        default=None,
        description="Deprecated for Map UI; High/Medium/Low/Very Low",
    )
    confidence_explanation: str | None = Field(
        default=None,
        description="Deprecated for Map UI",
    )
    confidence_flags: list[str] | None = Field(
        default=None,
        description="Deprecated for Map UI",
    )
    risk_confidence_factor: float | None = None
    nearest_station_distance_m: float | None = None


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
    risk_adjusted_ranking: bool | None = None
    risk_adjustment_formula: str | None = None
    counterfactual_construction_scale: float | None = None
