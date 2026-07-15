from __future__ import annotations

from typing import Any, Callable

from backend.app.agents.tools import (
    tool_compare_neighbourhoods,
    tool_compute_commute_burden,
    tool_get_attribution,
    tool_get_causal_explanation,
    tool_get_citizen_advisory,
    tool_get_city_briefing,
    tool_get_city_extremes,
    tool_get_enforcement_priority,
    tool_get_forecast_confidence,
    tool_get_forecast_evidence,
    tool_get_geospatial_city_coverage,
    tool_get_geospatial_context,
    tool_get_grid_suitability,
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
    "tool_get_city_extremes": tool_get_city_extremes,
    "tool_get_enforcement_priority": tool_get_enforcement_priority,
    "tool_get_causal_explanation": tool_get_causal_explanation,
    "tool_get_grid_suitability": tool_get_grid_suitability,
}

PLANNING_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "tool_get_forecast_evidence": {
        "description": (
            "PRIMARY tool for station-specific PM2.5 forecasts. Returns predicted PM2.5 (µg/m³), "
            "risk category (Good/Satisfactory/Moderate/Poor/…), which model was used (LightGBM vs "
            "persistence), and a short evidence narrative. Use when the user asks 'what will air "
            "quality be', 'tomorrow's PM2.5', or 'why is the forecast changing' for a known station "
            "(ids like cpcb_peenya, cpcb_bapujinagar, cpcb_hebbal)."
        ),
        "parameters": {
            "station_id": "string (required) — e.g. 'cpcb_peenya'",
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_get_forecast_confidence": {
        "description": (
            "Returns how trustworthy a station forecast is (confidence score + coverage status). "
            "Use when the user asks if they can trust the prediction or whether data is incomplete."
        ),
        "parameters": {
            "station_id": "string (required)",
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_get_inspection_priorities": {
        "description": (
            "Station-level inspection ranking (older 6–12 station heuristic). Prefer "
            "tool_get_enforcement_priority for hexagon-level Enforcement Intelligence. "
            "Use only if the user explicitly wants station-based monitoring priorities."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "top_k": "integer (optional, default 5)",
        },
    },
    "tool_get_citizen_advisory": {
        "description": (
            "Health-oriented outdoor activity guidance for a station and citizen profile "
            "(general / child / elderly / respiratory). Use for 'is it safe to go outside', "
            "'should kids play outdoors', etc."
        ),
        "parameters": {
            "station_id": "string (required)",
            "profile": "string (optional) — 'general', 'child', 'elderly', 'respiratory', 'outdoor_worker'",
            "language": "string (optional, default 'en')",
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_get_city_briefing": {
        "description": (
            "City-wide executive briefing: overall risk, operational notes, data limitations, "
            "and multi-station snapshot. Use for 'city overview', 'situation report', 'brief me'."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_search_policy_guidance": {
        "description": (
            "CRITICAL for policy/regulatory questions. Searches the official knowledge base "
            "(CPCB guidelines, construction dust control, KSPCB/Karnataka action plans, WHO "
            "guidance, vehicle emission norms). Always call this for questions about rules, "
            "standards, enforcement procedures, legal dust controls, or 'what does CPCB say'. "
            "Returns snippets with citation metadata — do not invent regulation text."
        ),
        "parameters": {
            "query": "string (required) — e.g. 'construction dust control CPCB'",
            "city": "string (optional)",
            "source_types": "list of strings (optional) — e.g. ['cpcb', 'who']",
            "top_k": "integer (optional, default 3)",
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
        "description": (
            "Source-attribution breakdown (traffic / industrial / construction / burning) "
            "for a hexagon, optionally with fused PM2.5. Prefer this when the user asks "
            "'why is it polluted', 'what is the source', or 'is traffic or construction worse'. "
            "Supports major-road corridor and peak-hour traffic weighting when available."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "h3_cell": "string (optional) — H3 cell ID",
            "lat": "float (optional)",
            "lon": "float (optional)",
            "include_fusion": "boolean (optional, default true)",
        },
    },
    "tool_get_enforcement_priority": {
        "description": (
            "PRIMARY tool for Enforcement Intelligence. Returns ranked hexagons with "
            "priority score, exposure, attributable magnitude, actionability, primary "
            "source mix, and recommended actions. Use for 'what should we inspect', "
            "'top enforcement targets', 'construction hotspots', or officer dispatch lists. "
            "Prefer this over tool_get_inspection_priorities."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "top_k": "integer (optional, default 10)",
        },
    },
    "tool_get_city_extremes": {
        "description": (
            "Best/worst hexagons by fused PM2.5 for city maps or 'cleanest vs dirtiest' questions. "
            "Only includes hexes with real station-influenced fusion coverage."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "n": "integer (optional, default 15)",
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
    "tool_get_grid_suitability": {
        "description": "Get a city-wide grid suitability assessment for every hexagon, scoring air quality (fused PM2.5 where available), forecast confidence, green space, road-density-based pollution exposure risk, weather disruption, and data coverage. Commute is excluded — it requires a specific workplace/school address.",
        "parameters": {
            "city": "string (optional, default 'bengaluru') — city name",
        },
    },
}