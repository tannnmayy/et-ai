from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Artifact adapter models
# ---------------------------------------------------------------------------

class StationSnapshot(BaseModel):
    station_id: str
    station_name: str
    city: str
    forecast_engine: str
    prediction_origin: str
    forecast_for: str
    predicted_pm25: float = Field(ge=0)
    latest_observed_pm25: float | None = None
    latest_observed_at: str | None = None
    risk_category: str
    quality_classification: str
    quality_note: str
    evaluation_metrics: dict
    artifact_status: dict


class QualitySnapshot(BaseModel):
    station_id: str
    classification: str
    recommendation: str
    hourly_row_count: int
    pm25_completeness_percent: float
    longest_continuous_pm25_run_hours: int
    pm25_gaps_longer_than_24h: int


class EvaluationSnapshot(BaseModel):
    station_id: str
    model_selected_for_serving: str
    persistence_rmse: float
    persistence_mae: float
    lightgbm_rmse: float | None = None
    lightgbm_mae: float | None = None
    rmse_improvement_percent: float | None = None
    test_rows: int


# ---------------------------------------------------------------------------
# Forecast evidence
# ---------------------------------------------------------------------------

class EvidenceItem(BaseModel):
    factor: str
    direction: str = Field(description="'for' or 'against' the forecast")
    weight: float = Field(ge=0, le=1)
    description: str


class ForecastEvidenceResponse(BaseModel):
    station_id: str
    station_name: str
    city: str
    forecast_engine: str
    explanation_method: str
    prediction_origin: str
    forecast_for: str
    predicted_pm25: float = Field(ge=0)
    latest_observed_pm25: float | None = None
    latest_observed_at: str | None = None
    expected_change_pm25: float | None = None
    expected_change_direction: str = Field(
        description="improving, stable, worsening, or unavailable"
    )
    risk_category: str
    model_validation_summary: str
    evidence_items: list[EvidenceItem]
    caveats: list[str]
    data_quality_classification: str
    data_quality_note: str


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

class ForecastConfidenceResponse(BaseModel):
    station_id: str
    station_name: str
    city: str
    confidence_level: str = Field(description="High, Medium, Low, or Unavailable")
    confidence_score: int | None = Field(
        ge=0, le=100, description="0-100 or null when unavailable"
    )
    latest_observation_age_hours: float | None = None
    recent_pm25_completeness_percent: float | None = None
    recent_gap_hours: int | None = None
    selected_engine: str
    quality_classification: str
    reasons: list[str]
    blockers: list[str]


# ---------------------------------------------------------------------------
# Inspection priority
# ---------------------------------------------------------------------------

class InspectionPriorityItem(BaseModel):
    rank: int
    station_id: str
    station_name: str
    city: str
    priority_score: int = Field(ge=0, le=100)
    priority_level: str = Field(description="Critical, High, Moderate, or Watch")
    predicted_pm25: float
    risk_category: str
    expected_change_pm25: float | None = None
    forecast_engine: str
    confidence_level: str
    data_quality_classification: str
    scoring_breakdown: dict
    recommended_inspection_focus: str
    rationale: str
    caveats: list[str]
    investigation_disclaimer: str


class InspectionPriorityResponse(BaseModel):
    city: str
    generated_at: str
    total_stations: int
    top_k: int
    ranked_stations: list[InspectionPriorityItem]


# ---------------------------------------------------------------------------
# Citizen advisory
# ---------------------------------------------------------------------------

class CitizenAdvisoryResponse(BaseModel):
    station_id: str
    station_name: str
    city: str
    profile: str
    language_requested: str
    language_served: str
    translation_fallback: bool
    forecast_risk_category: str
    predicted_pm25: float
    confidence_level: str
    headline: str
    recommendations: list[str]
    caution_note: str
    data_quality_note: str
    medical_disclaimer: str


# ---------------------------------------------------------------------------
# City briefing
# ---------------------------------------------------------------------------

class StationSummary(BaseModel):
    station_id: str
    station_name: str
    predicted_pm25: float
    risk_category: str
    forecast_engine: str
    confidence_level: str
    data_quality_classification: str
    expected_change_pm25: float | None = None


class CityBriefingResponse(BaseModel):
    city: str
    generated_at: str
    stations_with_forecasts: int
    stations_by_risk_category: dict[str, list[str]]
    stations_by_confidence_level: dict[str, list[str]]
    lightgbm_selected_count: int
    persistence_selected_count: int
    top_priorities: list[dict]
    city_risk_level: str
    executive_summary: str
    operational_recommendations: list[str]
    data_limitations: list[str]
    station_summaries: list[StationSummary]
