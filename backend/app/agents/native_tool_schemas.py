"""OpenAI-compatible tool schemas for native function calling (Groq / OpenRouter).

Only tools registered here can be invoked by the grounded tool-calling agent.
"""

from __future__ import annotations

from typing import Any, Callable

from backend.app.agents.tools import (
    tool_get_attribution,
    tool_get_causal_explanation,
    tool_get_city_briefing,
    tool_get_enforcement_priority,
    tool_get_forecast_confidence,
    tool_get_forecast_evidence,
    tool_get_travel_readiness,
    tool_get_weather_forecast,
    tool_resolve_location,
    tool_run_whatif_scenario,
    tool_search_policy_guidance,
)

# Map OpenAI function name → Python callable
NATIVE_TOOL_DISPATCH: dict[str, Callable[..., dict[str, Any]]] = {
    "resolve_location": tool_resolve_location,
    "get_enforcement_priority": tool_get_enforcement_priority,
    "get_attribution": tool_get_attribution,
    "get_forecast": tool_get_forecast_evidence,
    "get_forecast_confidence": tool_get_forecast_confidence,
    "search_policy_guidance": tool_search_policy_guidance,
    "get_city_briefing": tool_get_city_briefing,
    "get_weather": tool_get_weather_forecast,
    "get_travel_readiness": tool_get_travel_readiness,
    "get_causal_explanation": tool_get_causal_explanation,
    "run_whatif_scenario": tool_run_whatif_scenario,
}

# OpenAI tools array for chat.completions
OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "resolve_location",
            "description": (
                "Resolve a free-text place name in Bengaluru to a monitoring station, "
                "H3 cell, coordinates, and locality. Call this FIRST when the user "
                "mentions a place AND no Map context (station_id/h3_cell) is already provided. "
                "Skip if Map context already supplies the location."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Place name or area description",
                    },
                    "latitude": {"type": "number", "description": "Optional lat"},
                    "longitude": {"type": "number", "description": "Optional lon"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_enforcement_priority",
            "description": (
                "Hexagon-level enforcement priorities for Bengaluru. Returns ranked H3 cells "
                "with priority scores, dominant pollution sources, exposure, and PM2.5. "
                "Use for: where should officers inspect, construction dust hotspots, dispatch targets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "default": "bengaluru"},
                    "top_k": {
                        "type": "integer",
                        "description": "Number of top hexes (default 10, max 20)",
                        "default": 10,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_attribution",
            "description": (
                "Source attribution mix (traffic / industrial / construction / burning) "
                "for a hex or lat/lon. Prefer after resolve_location when user asks why "
                "an area is polluted or what drives PM2.5."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "default": "bengaluru"},
                    "h3_cell": {"type": "string"},
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "include_fusion": {"type": "boolean", "default": True},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": (
                "24h PM2.5 forecast evidence for a monitoring station "
                "(e.g. cpcb_peenya, cpcb_hebbal). Requires station_id from resolve_location "
                "or known CPCB/KSPCB id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "station_id": {"type": "string"},
                    "city": {"type": "string", "default": "bengaluru"},
                },
                "required": ["station_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast_confidence",
            "description": "Data reliability / confidence score for a station forecast.",
            "parameters": {
                "type": "object",
                "properties": {
                    "station_id": {"type": "string"},
                    "city": {"type": "string", "default": "bengaluru"},
                },
                "required": ["station_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy_guidance",
            "description": (
                "Search official CPCB / KSPCB / NCAP / WHO / dust-control knowledge base. "
                "MANDATORY for regulation, guideline, legal, or 'what does CPCB say' questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_city_briefing",
            "description": "City-wide air-quality situation overview for Bengaluru.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "default": "bengaluru"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Hourly weather forecast (wind, rain, temperature) for the city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "default": "bengaluru"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_travel_readiness",
            "description": "Whether outdoor travel/commute is advisable given AQI + weather.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "default": "bengaluru"},
                    "profile": {"type": "string", "default": "general"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_causal_explanation",
            "description": (
                "Citizen-readable explanation of pollution sources at a hex/lat-lon. "
                "Use after resolve_location for 'why is the air bad here'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "default": "bengaluru"},
                    "h3_cell": {"type": "string"},
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "language": {"type": "string", "default": "en"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_whatif_scenario",
            "description": (
                "WHAT-IF / COUNTERFACTUAL simulation. Use when the user asks hypotheticals like: "
                "'What if construction drops 50%?', 'What if traffic enforcement increases?', "
                "'How would PM2.5 change if industrial emissions fall 30%?'. "
                "Uses current source attribution + linear contribution model. "
                "ALWAYS state that results are simulations with uncertainty, not forecasts. "
                "Prefer Map context h3_cell/station_id when provided."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "default": "bengaluru"},
                    "h3_cell": {"type": "string"},
                    "station_id": {"type": "string"},
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "construction_reduction_percent": {
                        "type": "number",
                        "description": "e.g. 50 = construction activity half of baseline",
                    },
                    "traffic_reduction_percent": {"type": "number"},
                    "industrial_reduction_percent": {"type": "number"},
                    "burning_reduction_percent": {"type": "number"},
                    "construction_scale": {
                        "type": "number",
                        "description": "1.0 baseline; 0.5 = half construction",
                    },
                    "traffic_scale": {"type": "number"},
                    "industrial_scale": {"type": "number"},
                    "burning_scale": {"type": "number"},
                    "traffic_increase_percent": {"type": "number"},
                    "scenario_text": {
                        "type": "string",
                        "description": "Optional free-text scenario to help parse intent",
                    },
                    "include_enforcement_delta": {
                        "type": "boolean",
                        "default": True,
                        "description": "Also re-rank city enforcement under construction scale",
                    },
                },
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """You are AQI Sentinel Copilot for Bengaluru urban air quality.

ROLE
- Help citizens and enforcement officers with grounded, natural-language answers about PM2.5,
  pollution sources, forecasts, enforcement priorities, weather, official policy
  (CPCB / KSPCB / NCAP / WHO), and WHAT-IF scenario analysis.
- Prefer clarity and honesty over length. Sound like a reliable operational assistant.

LANGUAGE (en | hi | kn) — CRITICAL
- ALWAYS respond in the user's selected language from context (language=en|hi|kn).
  * en → English, hi → Hindi (Devanagari), kn → Kannada (Kannada script).
- Default is English only if language is missing.
- Keep technical terms in English / Latin script: PM2.5, AQI, CPCB, KSPCB, NCAP, WHO,
  station IDs (e.g. cpcb_peenya), H3 cell IDs. Only translate natural-language explanation.
- Numbers, units (µg/m³), ranks, and percentages stay as digits from tool results.
- When calling get_causal_explanation, ALWAYS set language to the same user language code.
- Mixed-language user questions (e.g. Hindi + English place names): still answer fully in the
  selected session language; place names may stay in Latin script.
- Do not switch to English mid-answer unless the user explicitly asks for English.
- Civic tone: clear and practical (not overly literary).

MAP / CLIENT CONTEXT (Map → Copilot)
- The user message may include preferred station_id and/or h3_cell from the Map UI.
- When station_id or h3_cell is provided:
  * Strongly prefer those values for get_forecast, get_attribution, get_causal_explanation, run_whatif_scenario.
  * Do NOT call resolve_location to re-discover the same place.
  * Only call resolve_location if the user clearly asks about a different location.
- When NO map context is provided and the user names a place, call resolve_location early.

MAP HIGHLIGHTS (Copilot → Map)
- The server automatically builds map_actions (highlight_h3_cells, highlight_stations, focus_on)
  from your tool results — especially get_enforcement_priority, get_attribution, resolve_location,
  run_whatif_scenario, and get_forecast.
- For enforcement / "why polluted" / spatial answers, call tools that return h3_cell or station_id
  so the Map can highlight the relevant places. Prefer concrete tool locations over vague prose only.

CONVERSATION MEMORY
- Prior turns may be included above the latest user question.
- Use them for follow-ups ("that area", "compare with Whitefield", "what about construction?").
- Do not invent prior context that is not in the history.

WHAT-IF / COUNTERFACTUAL (CORE STRENGTH)
- For hypotheticals about reducing/increasing construction, traffic, industrial, or burning —
  call run_whatif_scenario with the right reduction_percent or scale and location.
- Always label results as a SIMULATION with uncertainty (tool returns disclaimer + ranges).
- Never present simulated PM2.5 as a real forecast or legal finding.
- You may combine get_attribution + run_whatif_scenario for richer answers.

TOOL SELECTION
1. Prefer tools over guessing. Never invent PM2.5, ranks, %, or statute text.
2. Enforcement / inspect / officers / hotspots / dispatch → get_enforcement_priority.
3. Why polluted / sources → get_attribution and/or get_causal_explanation.
4. What-if / "what if" / "if we reduce" / "how would pollution change" → run_whatif_scenario.
5. Policy / CPCB / KSPCB / NCAP / WHO → search_policy_guidance.
6. Station forecasts → get_forecast; reliability → get_forecast_confidence.
7. City overview → get_city_briefing; weather → get_weather; outdoor travel → get_travel_readiness.
8. Multi-part questions: call tools for each part, answer all parts once.

QUALITY RULES
9. Be concise (2–6 short paragraphs or bullets), concrete, honest about gaps.
10. Source attribution is investigation signal, NOT legal proof of a polluter.
11. When tools error, say so and use partial data — never invent fillers.
12. Final answer numbers must appear in tool results (grounding is enforced).
13. Officers: lead with actionable location/source/priority; citizens: plain-language health context.

OUTPUT
- Clear natural language (no JSON dumps). Include place names, PM2.5 µg/m³, source shares, ranks when in tools.
- For simulations: lead with intervention, show baseline → simulated PM2.5 and uncertainty range, then caveats.
"""
