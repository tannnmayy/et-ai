from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.neighbourhood import (
    CandidateArea,
    NeighbourhoodCompareRequest,
    NeighbourhoodCompareResponse,
    SuitabilityResult,
    ComponentScore,
    SpatialIntelligenceLocationRequest,
    SpatialIntelligenceLocationResponse,
    NearbyStation,
)
from backend.app.services.neighbourhood_suitability_service import compare_neighbourhoods
from backend.app.services.spatial_intelligence_service import (
    get_station_intelligence,
    get_location_intelligence,
)

router = APIRouter(tags=["neighbourhoods"])


@router.post(
    "/neighbourhoods/compare",
    response_model=NeighbourhoodCompareResponse,
    summary="Compare neighbourhood suitability",
    description="Compares 1-3 candidate areas for a person with a workplace and optional school locations. "
    "Returns scored and ranked suitability results.",
)
def neighbourhood_compare(body: NeighbourhoodCompareRequest) -> NeighbourhoodCompareResponse:
    supported_modes = ["DRIVE", "TWO_WHEELER", "TRANSIT", "WALK"]
    if body.travel_mode.upper() not in supported_modes:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported travel mode '{body.travel_mode}'. Supported: {', '.join(supported_modes)}",
        )

    valid_profiles = ["general", "family_with_children", "elderly_household", "outdoor_worker"]
    if body.profile not in valid_profiles:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid profile '{body.profile}'. Supported: {', '.join(valid_profiles)}",
        )

    if body.period not in ("next_24h", "tomorrow"):
        raise HTTPException(
            status_code=422,
            detail="Invalid period. Supported: 'next_24h' or 'tomorrow'",
        )

    def _build_location_dict(c: CandidateArea) -> dict:
        d: dict = {"label": c.label}
        if c.query is not None:
            d["query"] = c.query
        else:
            d["latitude"] = c.latitude
            d["longitude"] = c.longitude
        return d

    candidates_data = [_build_location_dict(c) for c in body.candidate_areas]
    workplace_data = _build_location_dict(body.workplace)
    schools_data = [_build_location_dict(s) for s in body.schools]

    result = compare_neighbourhoods(
        candidate_queries=candidates_data,
        workplace_query=workplace_data,
        school_queries=schools_data,
        profile=body.profile,
        travel_mode=body.travel_mode.upper(),
        period=body.period,
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    candidates_out = []
    for c in result["candidates"]:
        candidates_out.append(
            SuitabilityResult(
                candidate_label=c["candidate_label"],
                latitude=c["latitude"],
                longitude=c["longitude"],
                resolution_method=c["resolution_method"],
                nearest_stations=c.get("nearest_stations", []),
                air_quality_component=ComponentScore(**c["air_quality_component"]),
                forecast_confidence_component=ComponentScore(**c["forecast_confidence_component"]),
                green_space_proxy_component=ComponentScore(**c["green_space_proxy_component"]),
                road_mobility_proxy_component=ComponentScore(**c["road_mobility_proxy_component"]),
                commute_component=ComponentScore(**c["commute_component"]),
                weather_disruption_component=ComponentScore(**c["weather_disruption_component"]),
                data_coverage_component=ComponentScore(**c["data_coverage_component"]),
                overall_score=c.get("overall_score"),
                partial_assessment=c.get("partial_assessment", False),
                limitations=c.get("limitations", []),
            )
        )

    return NeighbourhoodCompareResponse(
        candidates=candidates_out,
        ranking=result.get("ranking"),
        workplace_label=result["workplace_label"],
        school_labels=result.get("school_labels", []),
        profile=result["profile"],
        travel_mode=result["travel_mode"],
        period=result["period"],
        disclaimer=result["disclaimer"],
        medical_disclaimer=result.get("medical_disclaimer"),
    )


@router.get(
    "/spatial-intelligence/stations/{station_id}",
    summary="Get map-ready station intelligence",
    description="Aggregates forecast evidence, confidence, inspection priority, and geospatial context "
    "for a single monitoring station.",
)
def spatial_intelligence_station(station_id: str, city: str = "bengaluru") -> dict:
    try:
        return get_station_intelligence(station_id, city=city)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post(
    "/spatial-intelligence/location",
    response_model=SpatialIntelligenceLocationResponse,
    summary="Get spatial intelligence for an arbitrary location",
    description="Resolves a location (by query or coordinates) and returns nearby monitoring stations "
    "and spatial context. Does not produce an exact AQI prediction for the address.",
)
def spatial_intelligence_location(body: SpatialIntelligenceLocationRequest) -> SpatialIntelligenceLocationResponse:
    result = get_location_intelligence(
        query=body.query,
        latitude=body.latitude,
        longitude=body.longitude,
    )

    return SpatialIntelligenceLocationResponse(
        resolved_label=result.get("resolved_label"),
        latitude=result.get("latitude"),
        longitude=result.get("longitude"),
        resolution_method=result.get("resolution_method", "failed"),
        nearby_stations=[
            NearbyStation(**s) for s in result.get("nearby_stations", [])
        ],
        station_evidence_proxy_note=result.get("station_evidence_proxy_note", ""),
        limitations=result.get("limitations", []),
    )
