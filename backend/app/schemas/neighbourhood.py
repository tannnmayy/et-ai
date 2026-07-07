from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class CandidateArea(BaseModel):
    query: str | None = Field(None, description="Free-text location query")
    latitude: float | None = Field(None, description="Direct latitude input")
    longitude: float | None = Field(None, description="Direct longitude input")
    label: str | None = Field(None, description="Optional label for the candidate")

    @model_validator(mode="after")
    def _validate_resolution_mode(self) -> "CandidateArea":
        has_query = self.query is not None
        has_lat = self.latitude is not None
        has_lng = self.longitude is not None

        if has_query and (has_lat or has_lng):
            raise ValueError("Provide either a query OR coordinates, not both")

        if not has_query and not (has_lat and has_lng):
            if has_lat != has_lng:
                raise ValueError("Both latitude and longitude must be provided together")
            raise ValueError("Either a query or a latitude/longitude pair must be provided")

        return self


class NeighbourhoodCompareRequest(BaseModel):
    candidate_areas: list[CandidateArea] = Field(
        min_length=1, max_length=3, description="1-3 candidate areas to compare"
    )
    workplace: CandidateArea = Field(description="Workplace location")
    schools: list[CandidateArea] = Field(
        default=[], max_length=2, description="0-2 school locations"
    )
    profile: str = Field(
        default="general",
        description="general, family_with_children, elderly_household, outdoor_worker",
    )
    travel_mode: str = Field(default="DRIVE", description="DRIVE, TWO_WHEELER, TRANSIT, or WALK")
    period: str = Field(default="tomorrow", description="next_24h or tomorrow")


class ComponentScore(BaseModel):
    score: float | None = Field(None, ge=0.0, le=1.0, description="Component score 0-1")
    weight: float = Field(ge=0.0, le=1.0, description="Component weight")
    available: bool = Field(description="Whether the component data was available")
    explanation: str | None = Field(None, description="Human-readable explanation")


class SuitabilityResult(BaseModel):
    candidate_label: str = Field(description="Resolved label for the candidate")
    latitude: float = Field(description="Candidate latitude")
    longitude: float = Field(description="Candidate longitude")
    resolution_method: str = Field(description="direct_coordinates or geocoding")

    nearest_stations: list[dict] = Field(
        default_factory=list, description="Nearest 1-3 monitored stations with distance"
    )

    air_quality_component: ComponentScore
    forecast_confidence_component: ComponentScore
    green_space_proxy_component: ComponentScore
    road_mobility_proxy_component: ComponentScore
    commute_component: ComponentScore
    weather_disruption_component: ComponentScore
    data_coverage_component: ComponentScore

    overall_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Weighted overall score or null if minimum coverage not met"
    )
    partial_assessment: bool = Field(
        description="True if one or more component was unavailable"
    )
    limitations: list[str] = Field(default_factory=list)


class NeighbourhoodCompareResponse(BaseModel):
    candidates: list[SuitabilityResult] = Field(description="Suitability results for each candidate")
    ranking: list[int] | None = Field(
        None, description="Ranked indices (0-based) into candidates list, best first; null if comparison invalid"
    )
    workplace_label: str = Field(description="Resolved workplace label")
    school_labels: list[str] = Field(default_factory=list, description="Resolved school labels")
    profile: str = Field(description="Profile used")
    travel_mode: str = Field(description="Travel mode used")
    period: str = Field(description="Period used")
    disclaimer: str = Field(description="Neighbourhood suitability disclaimer")
    medical_disclaimer: str | None = Field(None, description="Medical disclaimer for sensitive profiles")


class SpatialIntelligenceStationRequest(BaseModel):
    station_id: str = Field(description="Station identifier")


class SpatialIntelligenceLocationRequest(BaseModel):
    query: str = Field(default="", description="Free-text address or place query")
    latitude: float | None = Field(None, description="Direct latitude input")
    longitude: float | None = Field(None, description="Direct longitude input")
    label: str | None = Field(None, description="Optional label")


class NearbyStation(BaseModel):
    station_id: str
    station_name: str
    distance_km: float = Field(description="Geodesic distance in km")


class SpatialIntelligenceLocationResponse(BaseModel):
    resolved_label: str | None = Field(None, description="Resolved location label")
    latitude: float | None = Field(None, description="Resolved latitude")
    longitude: float | None = Field(None, description="Resolved longitude")
    resolution_method: str = Field(description="direct_coordinates or geocoding")
    nearby_stations: list[NearbyStation] = Field(
        default_factory=list, description="Nearest 1-3 monitored stations"
    )
    station_evidence_proxy_note: str = Field(
        description="Disclaimer that station evidence is a proximity-supported estimate"
    )
    limitations: list[str] = Field(default_factory=list)
