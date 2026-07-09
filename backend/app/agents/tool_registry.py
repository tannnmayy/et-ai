from __future__ import annotations

from typing import Any, Callable

from backend.app.agents.tools import (
    tool_compare_neighbourhoods,
    tool_compute_commute_burden,
    tool_get_attribution,
    tool_get_causal_explanation,
    tool_get_citizen_advisory,
    tool_get_city_briefing,
    tool_get_enforcement_priority,
    tool_get_forecast_confidence,
    tool_get_forecast_evidence,
    tool_get_geospatial_city_coverage,
    tool_get_geospatial_context,
    tool_get_inspection_priorities,
    tool_get_location_intelligence,
    tool_get_station_intelligence,
    tool_get_travel_readiness,
    tool_get_weather_forecast,
    tool_get_weather_summary,
    tool_resolve_location,
    tool_search_policy_guidance,
)

PLANNING_TOOL_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "tool_get_forecast_evidence": tool_get_forecast_evidence,
    "tool_get_forecast_confidence": tool_get_forecast_confidence,
    "tool_get_inspection_priorities": tool_get_inspection_priorities,
    "tool_get_citizen_advisory": tool_get_citizen_advisory,
    "tool_get_city_briefing": tool_get_city_briefing,
    "tool_search_policy_guidance": tool_search_policy_guidance,
    "tool_get_weather_forecast": tool_get_weather_forecast,
    "tool_get_weather_summary": tool_get_weather_summary,
    "tool_get_geospatial_context": tool_get_geospatial_context,
    "tool_get_geospatial_city_coverage": tool_get_geospatial_city_coverage,
    "tool_get_travel_readiness": tool_get_travel_readiness,
    "tool_resolve_location": tool_resolve_location,
    "tool_compute_commute_burden": tool_compute_commute_burden,
    "tool_get_station_intelligence": tool_get_station_intelligence,
    "tool_get_location_intelligence": tool_get_location_intelligence,
    "tool_compare_neighbourhoods": tool_compare_neighbourhoods,
    "tool_get_attribution": tool_get_attribution,
    "tool_get_enforcement_priority": tool_get_enforcement_priority,
    "tool_get_causal_explanation": tool_get_causal_explanation,
}

PLANNING_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "tool_get_forecast_evidence": {
        "description": "Get the air quality forecast evidence for a specific monitoring station, including predicted PM2.5, risk category, forecast engine used, and explanation of expected changes.",
        "parameters": {
            "station_id": "string (required) — station identifier like 'cpcb_peenya'",
            "city": "string (optional, default 'bengaluru') — city name",
        },
    },
    "tool_get_forecast_confidence": {
        "description": "Get the confidence level and score for a station's air quality forecast, indicating how reliable the prediction is.",
        "parameters": {
            "station_id": "string (required) — station identifier",
            "city": "string (optional, default 'bengaluru') — city name",
        },
    },
    "tool_get_inspection_priorities": {
        "description": "List inspection priority rankings for stations in a city, sorted by urgency. Returns ranked stations with priority levels, scores, and recommended inspection focus areas.",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
            "top_k": "integer (optional, default 5) — number of top results",
        },
    },
    "tool_get_citizen_advisory": {
        "description": "Get health advisory guidance for a specific station, including personalized recommendations based on the user's profile and language preferences.",
        "parameters": {
            "station_id": "string (required) — station identifier",
            "profile": "string (optional, default 'general') — user profile like 'general', 'sensitive', 'child', 'elderly'",
            "language": "string (optional, default 'en') — response language",
            "city": "string (optional, default 'bengaluru') — city name",
        },
    },
    "tool_get_city_briefing": {
        "description": "Get an executive city-level air quality briefing covering overall risk, operational recommendations, data limitations, and per-station summaries.",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
        },
    },
    "tool_search_policy_guidance": {
        "description": "Search for official air quality policy guidance documents, regulations, or standards. Supports filtering by city and source type.",
        "parameters": {
            "query": "string (required) — search query for policy content",
            "city": "string (optional) — city name to narrow search",
            "source_types": "list of strings (optional) — e.g. ['cpcb', 'who', 'moefcc']",
            "top_k": "integer (optional, default 3) — number of results",
        },
    },
    "tool_get_weather_forecast": {
        "description": "Get a multi-hour weather forecast for a city including temperature, humidity, wind speed/direction, and precipitation probability.",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
            "horizon_hours": "integer (optional, default 72) — forecast horizon in hours",
            "refresh": "boolean (optional, default false) — force refresh from API",
        },
    },
    "tool_get_weather_summary": {
        "description": "Get a condensed weather summary for a city over a specified period, ideal for travel or outdoor activity planning.",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
            "period": "string (optional, default 'next_24h') — period like 'next_24h' or 'tomorrow'",
            "refresh": "boolean (optional, default false) — force refresh from API",
        },
    },
    "tool_get_geospatial_context": {
        "description": "Get detailed geospatial context for a monitoring station including road density, land use, green space fraction, build status, and nearby facilities.",
        "parameters": {
            "station_id": "string (required) — station identifier",
            "city": "string (optional, default 'bengaluru') — city name",
        },
    },
    "tool_get_geospatial_city_coverage": {
        "description": "Get a city-level summary of geospatial coverage including total hexagons, monitored vs unmonitored areas, and spatial data quality assessment.",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
        },
    },
    "tool_get_travel_readiness": {
        "description": "Get travel readiness assessment for a city based on air quality and weather, including whether it's safe for outdoor activities, commuting, or specific travel modes.",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
            "profile": "string (optional, default 'general') — user health profile",
            "period": "string (optional, default 'next_24h') — time period",
            "refresh_weather": "boolean (optional, default false) — force weather refresh",
        },
    },
    "tool_resolve_location": {
        "description": "Resolve a textual location query or latitude/longitude coordinates into structured location data including station IDs, city, and H3 cells.",
        "parameters": {
            "query": "string (optional) — text query like 'Whitefield, Bengaluru'",
            "latitude": "float (optional) — latitude coordinate",
            "longitude": "float (optional) — longitude coordinate",
        },
    },
    "tool_compute_commute_burden": {
        "description": "Compute commute burden between an origin and workplace, factoring in air quality along the route, optional school locations, and travel mode.",
        "parameters": {
            "origin_lat": "float (required) — origin latitude",
            "origin_lng": "float (required) — origin longitude",
            "workplace_lat": "float (required) — workplace latitude",
            "workplace_lng": "float (required) — workplace longitude",
            "travel_mode": "string (optional, default 'DRIVE') — travel mode",
            "school_locations": "list of dicts (optional) — school lat/lng coordinates",
        },
    },
    "tool_get_station_intelligence": {
        "description": "Get consolidated intelligence about a monitoring station combining forecast evidence, confidence, inspection priority, and geospatial context into one result.",
        "parameters": {
            "station_id": "string (required) — station identifier",
            "city": "string (optional, default 'bengaluru') — city name",
        },
    },
    "tool_get_location_intelligence": {
        "description": "Get intelligence for a location (by text query or coordinates) combining forecast, confidence, and geospatial context into one result.",
        "parameters": {
            "query": "string (optional) — text location query",
            "latitude": "float (optional) — latitude coordinate",
            "longitude": "float (optional) — longitude coordinate",
        },
    },
    "tool_compare_neighbourhoods": {
        "description": "Compare multiple candidate neighbourhoods for suitability based on air quality, commute burden, schools, and user profile preferences.",
        "parameters": {
            "candidate_queries": "list of dicts (required) — candidate locations with lat/lng",
            "workplace_query": "dict with lat/lng (required) — workplace location",
            "school_queries": "list of dicts (optional) — school locations",
            "profile": "string (optional, default 'general') — user profile",
            "travel_mode": "string (optional, default 'DRIVE') — transport mode",
            "period": "string (optional, default 'tomorrow') — evaluation period",
        },
    },
    "tool_get_attribution": {
        "description": "Get source attribution analysis for air pollution in a specific hexagon or the entire city grid. Use h3_cell for a known hexagon, lat+lon to convert coordinates, or no location for city-wide attribution. Returns traffic/industrial/construction/burning source fractions plus optional fusion PM2.5 estimate.",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
            "h3_cell": "string (optional) — H3 cell ID for a specific hexagon",
            "lat": "float (optional) — latitude to convert to H3 cell",
            "lon": "float (optional) — longitude to convert to H3 cell",
            "include_fusion": "boolean (optional, default true) — include fused PM2.5 estimate from nearby stations",
        },
    },
    "tool_get_enforcement_priority": {
        "description": "Compute enforcement priority rankings across hexagons in a city, combining exposure weight (vulnerable populations), attributable magnitude (enforceable pollution fraction), and actionability (how actionable each source category is).",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
            "top_k": "integer (optional, default 10) — number of top-ranked hexagons to return",
        },
    },
    "tool_get_causal_explanation": {
        "description": "Get a plain-language causal explanation of pollution sources at a specific hexagon location. Internally fetches source attribution and wind data, then generates an explanation in the requested language. Supports English, Hindi, and Kannada.",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
            "h3_cell": "string (optional) — H3 cell ID for a specific hexagon",
            "lat": "float (optional) — latitude to convert to H3 cell",
            "lon": "float (optional) — longitude to convert to H3 cell",
            "language": "string (optional, default 'en') — output language; en, hi, or kn",
        },
    },
}