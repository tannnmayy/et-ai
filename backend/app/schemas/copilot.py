from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.config import ADVISORY_PROFILES, SUPPORTED_LANGUAGES


class CopilotQueryRequest(BaseModel):
    query: str = Field(description="User's natural language query")
    city: str = Field(default="bengaluru", description="City name")
    station_id: str = Field(default="", description="Station ID (required for station-specific queries)")
    profile: str = Field(default="general", description="Advisory profile")
    language: str = Field(default="en", description="Language code")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of top results")
    force_dynamic_planning: bool = Field(default=False, description="Opt into multi-step AI planning (slower, more thorough)")


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


class AgentErrorResponse(BaseModel):
    detail: str
    error_type: str | None = None


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
