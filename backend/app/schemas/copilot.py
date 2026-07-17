from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.config import ADVISORY_PROFILES, SUPPORTED_LANGUAGES


class ConversationMessage(BaseModel):
    role: str = Field(description="user | assistant")
    content: str = Field(description="Message text")


class CopilotQueryRequest(BaseModel):
    query: str = Field(description="User's natural language query")
    city: str = Field(default="bengaluru", description="City name")
    station_id: str = Field(default="", description="Station ID (optional context from Map)")
    h3_cell: str | None = Field(
        default=None,
        description="Optional H3 cell context from Map / Enforcement selection",
    )
    profile: str = Field(default="general", description="Advisory profile")
    language: str = Field(
        default="en",
        description="Language code: en | hi | kn (case-insensitive; default en)",
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Number of top results")
    force_dynamic_planning: bool = Field(
        default=False,
        description="Legacy flag — free-text always uses tool agent; kept for API compatibility",
    )
    conversation_history: list[ConversationMessage] = Field(
        default_factory=list,
        description="Prior turns in this chat session (last 4–6 messages). Not persisted server-side.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional client session id for audit only (memory is still request-scoped).",
    )


class AgentToolResult(BaseModel):
    tool: str
    arguments: dict[str, Any]
    success: bool


class CopilotAuditEvent(BaseModel):
    tool: str
    arguments: dict[str, Any]
    success: bool


class CopilotReasoningStep(BaseModel):
    type: str = Field(description="route | agent | tool | knowledge_base | llm | fallback")
    detail: str = ""
    tool: str | None = None
    success: bool | None = None
    provider: str | None = None
    backend: str | None = None
    chunk_count: int | None = None
    gemini_key_index: int | None = None
    arguments: dict[str, Any] | None = None


class CopilotAuditTrail(BaseModel):
    request_id: str
    timestamp: str
    detected_intent: str
    selected_agent: str
    tools_called: list[CopilotAuditEvent]
    llm_mode: str
    fallback_used: bool
    warnings: list[str]
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_base_used: bool = False
    knowledge_backend: str | None = None
    llm_provider_used: str | None = None
    gemini_key_index: int | None = None
    # Phase 2 cache / mode metadata
    cache_hit: bool = False
    cache_key: str | None = None
    cache_kind: str | None = None
    response_mode: str | None = None
    # Final phase
    memory_turns_used: int = 0
    whatif_used: bool = False


class AgentErrorResponse(BaseModel):
    detail: str
    error_type: str | None = None


class MapFocusTarget(BaseModel):
    """Optional camera / selection target for the Map UI."""

    h3_cell: str | None = None
    station_id: str | None = None
    lat: float | None = None
    lng: float | None = None
    label: str | None = None


class CopilotMapActions(BaseModel):
    """Structured instructions for the Map (Copilot → Map).

    Backward compatible: omitted or null when no spatial tools produced locations.
    """

    highlight_h3_cells: list[str] = Field(
        default_factory=list,
        description="H3 cells the Map should highlight",
    )
    highlight_stations: list[str] = Field(
        default_factory=list,
        description="Station IDs the Map should highlight",
    )
    focus_on: MapFocusTarget | None = Field(
        default=None,
        description="Optional primary location to center/select on the Map",
    )


class CopilotResponse(BaseModel):
    request_id: str
    intent: str
    selected_agent: str
    answer: str
    structured_data: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    audit_trail: CopilotAuditTrail
    llm_mode: str
    fallback_used: bool
    # Phase 2 top-level convenience (also present in audit_trail)
    cache_hit: bool = False
    response_mode: str | None = None
    # Bidirectional Map integration (Copilot → Map)
    map_actions: CopilotMapActions | None = None
