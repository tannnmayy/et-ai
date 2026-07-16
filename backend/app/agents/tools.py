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
    """Search policy KB — FAISS dense RAG first, then legacy TF-IDF."""
    try:
        from backend.app.services.rag_service import retrieve_relevant_context

        rag = retrieve_relevant_context(query, top_k=top_k)
        if rag.get("used") and rag.get("chunks"):
            return {
                "query": query,
                "retrieval_backend": rag.get("backend"),
                "embedding_model": rag.get("model"),
                "results": [
                    {
                        "title": c.get("title"),
                        "snippet": c.get("text"),
                        "score": c.get("score"),
                        "organization": c.get("organization"),
                        "source_type": c.get("source_type"),
                        "allowed_for_citation": c.get("allowed_for_citation"),
                    }
                    for c in rag["chunks"]
                ],
                "context_block": rag.get("context_block"),
                "knowledge_base_used": True,
            }
    except Exception:
        pass

    from backend.app.services.policy_guidance_service import search_policy_guidance
    try:
        result = search_policy_guidance(query, city=city, source_types=source_types, top_k=top_k)
        result["knowledge_base_used"] = bool(result.get("results"))
        result["retrieval_backend"] = result.get("retrieval_backend") or "tfidf"
        return result
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
    """Resolve free-text place → station / coords / H3.

    Order: coordinates → station/locality registry match → Google geocode (if key).
    Always tries offline registry first so Copilot works without Maps keys.
    """
    import re
    from math import asin, cos, radians, sin, sqrt

    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return 2 * r * asin(min(1.0, sqrt(a)))

    try:
        # 1) Direct coordinates
        if latitude is not None and longitude is not None:
            from backend.app.services.location_service import resolve_location

            base = resolve_location(query="", latitude=latitude, longitude=longitude)
            if base.get("success"):
                import h3 as _h3

                lat, lon = float(base["latitude"]), float(base["longitude"])
                h3_cell = _h3.latlng_to_cell(lat, lon, 9)
                # nearest station
                from pipeline.station_registry import get_registry_stations

                best = None
                best_d = 1e9
                for s in get_registry_stations():
                    if s.latitude is None or s.longitude is None:
                        continue
                    d = _haversine_km(lat, lon, float(s.latitude), float(s.longitude))
                    if d < best_d:
                        best_d = d
                        best = s
                base["h3_cell"] = h3_cell
                base["resolved_name"] = base.get("label")
                if best:
                    base["nearest_station_id"] = best.station_id
                    base["station_id"] = best.station_id if best_d <= 3.5 else None
                    base["nearest_station_name"] = getattr(best, "display_name", None) or best.station_name
                    base["nearest_station_distance_km"] = round(best_d, 2)
                    base["confidence"] = "high" if best_d <= 1.5 else "medium" if best_d <= 3.5 else "low"
                return base

        q = (query or "").strip()
        if not q:
            return {"_tool_error": "Empty location query", "_error_type": "ParameterError"}

        norm = re.sub(r"\s+", " ", q.lower())
        norm = re.sub(r"\b(near|around|in|at|area|bengaluru|bangalore|station)\b", " ", norm).strip()

        # 2) Station registry substring match
        from pipeline.station_registry import get_registry_stations

        stations = list(get_registry_stations())
        best_station = None
        best_score = 0
        for s in stations:
            candidates = [
                s.station_id.replace("cpcb_", "").replace("_", " "),
                getattr(s, "display_name", None) or "",
                getattr(s, "station_name", None) or "",
            ]
            for c in candidates:
                c_norm = re.sub(r"\b(bengaluru|kspcb|cpcb|station)\b", "", (c or "").lower()).strip()
                if not c_norm:
                    continue
                if c_norm in norm or norm in c_norm:
                    score = len(c_norm)
                    if score > best_score:
                        best_score = score
                        best_station = s

        if best_station and best_station.latitude is not None:
            import h3 as _h3

            lat, lon = float(best_station.latitude), float(best_station.longitude)
            return {
                "success": True,
                "resolved_name": getattr(best_station, "display_name", None)
                or best_station.station_name,
                "label": getattr(best_station, "display_name", None) or best_station.station_name,
                "station_id": best_station.station_id,
                "nearest_station_id": best_station.station_id,
                "nearest_station_name": getattr(best_station, "display_name", None)
                or best_station.station_name,
                "nearest_station_distance_km": 0.0,
                "latitude": lat,
                "longitude": lon,
                "h3_cell": _h3.latlng_to_cell(lat, lon, 9),
                "resolution_method": "station_registry",
                "confidence": "high",
                "city_scope": "bengaluru",
            }

        # 3) Locality centroids (offline list)
        from backend.app.agents.conversation_fallback import _LOCALITY_CENTRES

        for name, (lat, lon) in _LOCALITY_CENTRES.items():
            if name in norm or norm in name:
                import h3 as _h3

                # nearest station to locality
                best = None
                best_d = 1e9
                for s in stations:
                    if s.latitude is None or s.longitude is None:
                        continue
                    d = _haversine_km(lat, lon, float(s.latitude), float(s.longitude))
                    if d < best_d:
                        best_d = d
                        best = s
                out = {
                    "success": True,
                    "resolved_name": name.title(),
                    "label": name.title(),
                    "locality": name.title(),
                    "latitude": lat,
                    "longitude": lon,
                    "h3_cell": _h3.latlng_to_cell(lat, lon, 9),
                    "resolution_method": "locality_centroid",
                    "confidence": "medium",
                    "city_scope": "bengaluru",
                }
                if best:
                    out["nearest_station_id"] = best.station_id
                    out["station_id"] = best.station_id if best_d <= 4.0 else None
                    out["nearest_station_name"] = (
                        getattr(best, "display_name", None) or best.station_name
                    )
                    out["nearest_station_distance_km"] = round(best_d, 2)
                return out

        # 4) Google geocode fallback
        from backend.app.services.location_service import resolve_location

        geo = resolve_location(query=q)
        if geo.get("success"):
            import h3 as _h3

            lat, lon = float(geo["latitude"]), float(geo["longitude"])
            geo["h3_cell"] = _h3.latlng_to_cell(lat, lon, 9)
            geo["resolved_name"] = geo.get("label")
            best = None
            best_d = 1e9
            for s in stations:
                if s.latitude is None or s.longitude is None:
                    continue
                d = _haversine_km(lat, lon, float(s.latitude), float(s.longitude))
                if d < best_d:
                    best_d = d
                    best = s
            if best:
                geo["nearest_station_id"] = best.station_id
                geo["station_id"] = best.station_id if best_d <= 3.5 else None
                geo["nearest_station_name"] = (
                    getattr(best, "display_name", None) or best.station_name
                )
                geo["nearest_station_distance_km"] = round(best_d, 2)
                geo["confidence"] = "medium"
            return geo

        return {
            "_tool_error": f"Could not resolve location: {q}",
            "_error_type": "UnresolvedLocation",
            "query": q,
            "success": False,
        }
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
            result = get_city_grid_attribution(city=city, include_fusion=include_fusion, max_hexagons=2000)
        if "error" in result:
            return {"_tool_error": result["error"], "_error_type": "ServiceError"}
        return result
    except Exception as e:
        return {"_tool_error": str(e), "_error_type": type(e).__name__}


def tool_get_city_extremes(city: str = "bengaluru", n: int = 15) -> dict[str, Any]:
    from backend.app.services.attribution_service import get_city_extremes
    try:
        result = get_city_extremes(city=city, n=n)
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


def tool_run_whatif_scenario(
    city: str = "bengaluru",
    h3_cell: str | None = None,
    station_id: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    traffic_scale: float | None = None,
    industrial_scale: float | None = None,
    construction_scale: float | None = None,
    burning_scale: float | None = None,
    traffic_reduction_percent: float | None = None,
    industrial_reduction_percent: float | None = None,
    construction_reduction_percent: float | None = None,
    burning_reduction_percent: float | None = None,
    traffic_increase_percent: float | None = None,
    industrial_increase_percent: float | None = None,
    construction_increase_percent: float | None = None,
    burning_increase_percent: float | None = None,
    scenario_text: str | None = None,
    include_enforcement_delta: bool = True,
) -> dict[str, Any]:
    """Counterfactual what-if simulation (attribution-based, not a forecast)."""
    from backend.app.services.whatif_scenario_service import run_whatif_scenario

    try:
        return run_whatif_scenario(
            city=city,
            h3_cell=h3_cell,
            station_id=station_id,
            lat=lat,
            lon=lon,
            traffic_scale=traffic_scale,
            industrial_scale=industrial_scale,
            construction_scale=construction_scale,
            burning_scale=burning_scale,
            traffic_reduction_percent=traffic_reduction_percent,
            industrial_reduction_percent=industrial_reduction_percent,
            construction_reduction_percent=construction_reduction_percent,
            burning_reduction_percent=burning_reduction_percent,
            traffic_increase_percent=traffic_increase_percent,
            industrial_increase_percent=industrial_increase_percent,
            construction_increase_percent=construction_increase_percent,
            burning_increase_percent=burning_increase_percent,
            scenario_text=scenario_text,
            include_enforcement_delta=include_enforcement_delta,
        )
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
