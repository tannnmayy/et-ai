from __future__ import annotations

from typing import Any

from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
    get_station_geospatial_context,
)
from backend.app.services.citizen_advisory_service import get_citizen_advisory
from backend.app.services.city_briefing_service import get_city_briefing
from backend.app.services.confidence_service import get_forecast_confidence
from backend.app.services.forecast_evidence_service import get_forecast_evidence
from backend.app.services.inspection_priority_service import get_inspection_priorities


def tool_get_forecast_evidence(station_id: str, city: str = "bengaluru") -> dict[str, Any]:
    try:
        return get_forecast_evidence(station_id, city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError) as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_forecast_confidence(station_id: str, city: str = "bengaluru") -> dict[str, Any]:
    try:
        return get_forecast_confidence(station_id, city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError) as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_inspection_priorities(city: str = "bengaluru", top_k: int = 5) -> dict[str, Any]:
    try:
        return get_inspection_priorities(city, top_k=top_k)
    except UnsupportedCityError as e:
        return {"_tool_error": str(e), "_error_type": "UnsupportedCityError"}


def tool_get_citizen_advisory(
    station_id: str, profile: str = "general", language: str = "en", city: str = "bengaluru"
) -> dict[str, Any]:
    try:
        return get_citizen_advisory(station_id, profile=profile, language=language, city=city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError) as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_city_briefing(city: str = "bengaluru") -> dict[str, Any]:
    try:
        return get_city_briefing(city)
    except UnsupportedCityError as e:
        return {"_tool_error": str(e), "_error_type": "UnsupportedCityError"}


def tool_search_policy_guidance(
    query: str,
    city: str | None = None,
    source_types: list[str] | None = None,
    top_k: int = 3,
) -> dict[str, Any]:
    from backend.app.services.policy_guidance_service import search_policy_guidance
    try:
        return search_policy_guidance(query, city=city, source_types=source_types, top_k=top_k)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_weather_forecast(
    city: str = "bengaluru",
    horizon_hours: int = 72,
    refresh: bool = False,
) -> dict[str, Any]:
    from backend.app.services.weather_forecast_service import get_weather_forecast
    try:
        return get_weather_forecast(city=city, horizon_hours=horizon_hours, refresh=refresh)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_weather_summary(
    city: str = "bengaluru",
    period: str = "next_24h",
    refresh: bool = False,
) -> dict[str, Any]:
    from backend.app.services.weather_forecast_service import get_weather_summary
    try:
        return get_weather_summary(city=city, period=period, refresh=refresh)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_geospatial_context(station_id: str, city: str = "bengaluru") -> dict[str, Any]:
    """Get geospatial context for a station."""
    try:
        return get_station_geospatial_context(station_id, city=city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError) as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_geospatial_city_coverage(city: str = "bengaluru") -> dict[str, Any]:
    """Get geospatial coverage summary for a city."""
    from backend.app.services.geospatial_evidence_service import get_city_geospatial_coverage
    try:
        return get_city_geospatial_coverage(city)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_travel_readiness(
    city: str = "bengaluru",
    profile: str = "general",
    period: str = "next_24h",
    refresh_weather: bool = False,
) -> dict[str, Any]:
    from backend.app.services.travel_readiness_service import get_travel_readiness
    try:
        return get_travel_readiness(
            city=city, profile=profile, period=period, refresh_weather=refresh_weather,
        )
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_resolve_location(
    query: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    from backend.app.services.location_service import resolve_location
    try:
        return resolve_location(query=query, latitude=latitude, longitude=longitude)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_compute_commute_burden(
    origin_lat: float,
    origin_lng: float,
    workplace_lat: float,
    workplace_lng: float,
    travel_mode: str = "DRIVE",
    school_locations: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    from backend.app.services.commute_service import compute_commute_burden
    try:
        return compute_commute_burden(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            workplace_lat=workplace_lat,
            workplace_lng=workplace_lng,
            travel_mode=travel_mode,
            school_locations=school_locations,
        )
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_station_intelligence(
    station_id: str,
    city: str = "bengaluru",
) -> dict[str, Any]:
    from backend.app.services.spatial_intelligence_service import get_station_intelligence
    try:
        return get_station_intelligence(station_id, city=city)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_location_intelligence(
    query: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    from backend.app.services.spatial_intelligence_service import get_location_intelligence
    try:
        return get_location_intelligence(query=query, latitude=latitude, longitude=longitude)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_attribution(city: str = "bengaluru", h3_cell: str | None = None, lat: float | None = None, lon: float | None = None, include_fusion: bool = True) -> dict[str, Any]:
    """Get source attribution for a hexagon or the whole city grid."""
    from backend.app.services.attribution_service import (
        get_city_grid_attribution,
        get_single_hexagon_attribution,
    )
    import h3 as _h3
    try:
        if h3_cell:
            result = get_single_hexagon_attribution(h3_cell, city=city, include_fusion=include_fusion)
        elif lat is not None and lon is not None:
            cell = _h3.latlng_to_cell(lat, lon, 9)
            result = get_single_hexagon_attribution(cell, city=city, include_fusion=include_fusion)
        else:
            result = get_city_grid_attribution(city=city, include_fusion=include_fusion)
        if "error" in result:
            return {"_tool_error": result["error"], "_error_type": "ServiceError"}
        return result
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_enforcement_priority(city: str = "bengaluru", top_k: int = 10) -> dict[str, Any]:
    from backend.app.services.enforcement_priority_service import compute_enforcement_priorities
    try:
        result = compute_enforcement_priorities(city=city, top_k=top_k)
        if "error" in result:
            return {"_tool_error": result["error"], "_error_type": "ServiceError"}
        return result
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_causal_explanation(
    city: str = "bengaluru",
    h3_cell: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    language: str = "en",
) -> dict[str, Any]:
    from backend.app.services.attribution_service import get_single_hexagon_attribution
    from backend.app.services.causal_explanation_service import generate_causal_explanation
    import h3 as _h3
    try:
        if h3_cell:
            attribution = get_single_hexagon_attribution(h3_cell, city=city)
        elif lat is not None and lon is not None:
            cell = _h3.latlng_to_cell(lat, lon, 9)
            attribution = get_single_hexagon_attribution(cell, city=city)
        else:
            return {"_tool_error": "Either h3_cell or lat+lon is required", "_error_type": "ParameterError"}
        if "error" in attribution:
            return {"_tool_error": attribution["error"], "_error_type": "ServiceError"}
        return generate_causal_explanation(attribution, language=language)
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_compare_neighbourhoods(
    candidate_queries: list[dict[str, Any]],
    workplace_query: dict[str, Any],
    school_queries: list[dict[str, Any]] | None = None,
    profile: str = "general",
    travel_mode: str = "DRIVE",
    period: str = "tomorrow",
) -> dict[str, Any]:
    from backend.app.services.neighbourhood_suitability_service import compare_neighbourhoods
    try:
        return compare_neighbourhoods(
            candidate_queries=candidate_queries,
            workplace_query=workplace_query,
            school_queries=school_queries,
            profile=profile,
            travel_mode=travel_mode,
            period=period,
        )
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_grid_suitability(city: str = "bengaluru") -> dict[str, Any]:
    from backend.app.services.neighbourhood_suitability_service import get_grid_suitability
    try:
        result = get_grid_suitability(city=city)
        if "error" in result:
            return {"_tool_error": result["error"], "_error_type": "ServiceError"}
        return result
    except Exception as exc:
        return {"_tool_error": str(exc), "_error_type": type(exc).__name__}
