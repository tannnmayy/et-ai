from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Intent(str, Enum):
    station_explanation = "station_explanation"
    station_confidence = "station_confidence"
    inspection_plan = "inspection_plan"
    citizen_guidance = "citizen_guidance"
    city_briefing = "city_briefing"
    policy_guidance = "policy_guidance"
    weather_forecast = "weather_forecast"
    travel_readiness = "travel_readiness"
    spatial_context = "spatial_context"
    spatial_intelligence = "spatial_intelligence"
    neighbourhood_comparison = "neighbourhood_comparison"
    dynamic_planning = "dynamic_planning"
    unsupported = "unsupported"


@dataclass
class AgentState:
    request_id: str
    user_query: str = ""
    city: str = "bengaluru"
    station_id: str = ""
    intent: Intent = Intent.unsupported
    profile: str = "general"
    language: str = "en"
    top_k: int = 5
    tool_results: dict[str, Any] = field(default_factory=dict)
    selected_agent: str = ""
    response: str = ""
    structured_data: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    audit_events: list[dict] = field(default_factory=list)
    llm_status: str = "deterministic"
    fallback_used: bool = False
