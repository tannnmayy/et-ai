"""Tool registry + planner-facing schemas for LangGraph dynamic planning.

Descriptions are intentionally specific so the LLM can route without guessing.
"""

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
    "tool_search_policy_guidance": {
        "description": (
            "MANDATORY for any regulation / guideline / legal-standard question. "
            "Runs dense RAG over the local knowledge base (CPCB pollution-control law, "
            "construction dust control practices, KSPCB / Karnataka State Action Plan, "
            "NCAP city guidance, WHO air-quality guidelines, vehicle emission norms). "
            "Call this FIRST when the user asks 'what does CPCB say', 'dust control rules', "
            "'emission norms', 'NCAP', 'KSPCB', 'official guidance', or similar. "
            "Returns ranked passages with titles and scores — quote carefully; never invent "
            "statute text that is not in the results."
        ),
        "parameters": {
            "query": "string (required) — natural language search, e.g. 'CPCB construction dust control'",
            "city": "string (optional)",
            "source_types": "list of strings (optional)",
            "top_k": "integer (optional, default 3, use 4–5 for broad policy questions)",
        },
    },
    "tool_get_enforcement_priority": {
        "description": (
            "PRIMARY Enforcement Intelligence tool (hexagon-level). "
            "Returns a ranked list of H3 cells with priority score, exposure, attributable "
            "magnitude, actionability, dominant source category (traffic / industrial / "
            "construction / burning), and recommended inspector actions. "
            "Use for: 'what should we inspect', 'top enforcement targets', 'dispatch list', "
            "'construction dust hotspots', 'where should officers go'. "
            "Prefer this over tool_get_inspection_priorities (station-only heuristic)."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "top_k": "integer (optional, default 10)",
        },
    },
    "tool_get_attribution": {
        "description": (
            "Source-attribution breakdown for a location: share of traffic, industrial, "
            "construction, and burning contributions, optionally with fused PM2.5. "
            "Includes major-road corridor and peak-hour traffic weighting when available. "
            "Use for: 'why is it polluted', 'is traffic or construction worse', "
            "'what is driving PM2.5 here'. Requires h3_cell OR lat+lon when possible."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "h3_cell": "string (optional) — H3 cell id",
            "lat": "float (optional)",
            "lon": "float (optional)",
            "include_fusion": "boolean (optional, default true)",
        },
    },
    "tool_get_causal_explanation": {
        "description": (
            "Plain-language explanation of pollution sources at a hex/location for citizens. "
            "Internally uses attribution + wind context. Languages: en, hi, kn. "
            "Use when the user wants a readable 'why is the air bad' story rather than raw scores."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "h3_cell": "string (optional)",
            "lat": "float (optional)",
            "lon": "float (optional)",
            "language": "string (optional, default 'en') — en | hi | kn",
        },
    },
    "tool_get_city_extremes": {
        "description": (
            "Cleanest vs dirtiest hexagons by fused PM2.5 (station-influenced coverage only). "
            "Use for city map overlays or 'best/worst areas in Bengaluru' questions."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "n": "integer (optional, default 15)",
        },
    },
    "tool_get_forecast_evidence": {
        "description": (
            "PRIMARY station PM2.5 forecast tool. Returns predicted PM2.5 (µg/m³), risk "
            "category, model used (LightGBM vs persistence), and evidence narrative. "
            "Station ids: cpcb_peenya, cpcb_bapujinagar, cpcb_hebbal, cpcb_silkboard, etc. "
            "Use for tomorrow's air quality at a named monitoring station."
        ),
        "parameters": {
            "station_id": "string (required) — e.g. 'cpcb_peenya'",
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_get_forecast_confidence": {
        "description": (
            "Forecast trustworthiness for a station (confidence level + coverage). "
            "Use when the user asks 'can I trust this forecast' or 'is data incomplete'."
        ),
        "parameters": {
            "station_id": "string (required)",
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_get_inspection_priorities": {
        "description": (
            "LEGACY station-level inspection ranking (~6–12 stations). "
            "Prefer tool_get_enforcement_priority for modern hexagon Enforcement Intelligence. "
            "Use only if the user explicitly wants station monitoring priorities."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "top_k": "integer (optional, default 5)",
        },
    },
    "tool_get_citizen_advisory": {
        "description": (
            "Health-oriented outdoor activity guidance for a station and profile "
            "(general / child / elderly / respiratory / outdoor_worker). "
            "Use for 'is it safe to go outside', 'should kids play outdoors'."
        ),
        "parameters": {
            "station_id": "string (required)",
            "profile": "string (optional) — general | child | elderly | respiratory | outdoor_worker",
            "language": "string (optional, default 'en')",
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_get_city_briefing": {
        "description": (
            "City-wide executive briefing: overall risk, multi-station snapshot, "
            "operational notes, and explicit data limitations. "
            "Use for 'brief me', 'situation report', 'city overview'."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_get_weather_forecast": {
        "description": (
            "Multi-hour weather forecast (temperature, humidity, wind, precipitation). "
            "Pair with air-quality tools when the user asks about rain clearing pollution "
            "or outdoor conditions over the next day."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "horizon_hours": "integer (optional, default 72)",
            "refresh": "boolean (optional, default false)",
        },
    },
    "tool_get_weather_summary": {
        "description": (
            "Condensed weather summary for a period (e.g. next_24h, tomorrow). "
            "Good for travel or outdoor activity planning alongside AQI."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "period": "string (optional, default 'next_24h')",
            "refresh": "boolean (optional, default false)",
        },
    },
    "tool_get_travel_readiness": {
        "description": (
            "Combined AQI + weather readiness for outdoor travel / commute modes. "
            "Use for bike, two-wheeler, walk, or 'should I go out' questions."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
            "profile": "string (optional, default 'general')",
            "period": "string (optional, default 'next_24h')",
            "refresh_weather": "boolean (optional, default false)",
        },
    },
    "tool_get_geospatial_context": {
        "description": (
            "Station geospatial context: road density, land use, green space, nearby "
            "industrial/construction facilities. Use to explain why a station area is risky."
        ),
        "parameters": {
            "station_id": "string (required)",
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_get_geospatial_city_coverage": {
        "description": (
            "City-level geospatial coverage: hex counts, monitored vs unmonitored areas, "
            "spatial data quality. Use when discussing map coverage limits."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_resolve_location": {
        "description": (
            "Resolve a place name or lat/lon into station ids, city, and H3 cells. "
            "Call before attribution/enforcement tools when the user names a locality "
            "but you do not yet have coordinates."
        ),
        "parameters": {
            "query": "string (optional) — e.g. 'Whitefield, Bengaluru'",
            "latitude": "float (optional)",
            "longitude": "float (optional)",
        },
    },
    "tool_compute_commute_burden": {
        "description": (
            "Estimate commute air-quality burden between origin and workplace "
            "(optional schools, travel mode). Use for neighbourhood comparison / relocate decisions."
        ),
        "parameters": {
            "origin_lat": "float (required)",
            "origin_lng": "float (required)",
            "workplace_lat": "float (required)",
            "workplace_lng": "float (required)",
            "travel_mode": "string (optional, default 'DRIVE')",
            "school_locations": "list of dicts (optional)",
        },
    },
    "tool_get_station_intelligence": {
        "description": (
            "One-shot bundle: forecast + confidence + inspection context + geospatial "
            "for a monitoring station. Efficient when the user wants 'everything about Peenya station'."
        ),
        "parameters": {
            "station_id": "string (required)",
            "city": "string (optional, default 'bengaluru')",
        },
    },
    "tool_get_location_intelligence": {
        "description": (
            "Intelligence for a free-text location or coordinates (forecast + context). "
            "Use when the user names a neighbourhood without a station id."
        ),
        "parameters": {
            "query": "string (optional)",
            "latitude": "float (optional)",
            "longitude": "float (optional)",
        },
    },
    "tool_compare_neighbourhoods": {
        "description": (
            "Compare candidate neighbourhoods for livability given workplace/schools and profile. "
            "Use for 'where should I live' multi-area comparisons."
        ),
        "parameters": {
            "candidate_queries": "list of dicts (required) — candidates with lat/lng",
            "workplace_query": "dict with lat/lng (required)",
            "school_queries": "list of dicts (optional)",
            "profile": "string (optional, default 'general')",
            "travel_mode": "string (optional, default 'DRIVE')",
            "period": "string (optional, default 'tomorrow')",
        },
    },
    "tool_get_grid_suitability": {
        "description": (
            "City-wide hex suitability scores (AQI, green space, road exposure, weather, coverage). "
            "Commute is excluded — needs a specific workplace. Use for map-wide livability heatmaps."
        ),
        "parameters": {
            "city": "string (optional, default 'bengaluru')",
        },
    },
}
