from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class AuditTrail:
    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        self.timestamp = datetime.now(tz=timezone.utc).isoformat()
        self.intent: str = "unsupported"
        self.selected_agent: str = ""
        self.tools_called: list[dict[str, Any]] = []
        self.llm_mode: str = "deterministic"
        self.fallback_used: bool = False
        self.warnings: list[str] = []

    def record_tool_call(self, tool_name: str, arguments: dict[str, Any], success: bool) -> None:
        self.tools_called.append({
            "tool": tool_name,
            "arguments": arguments,
            "success": success,
        })

    def set_intent(self, intent: str) -> None:
        self.intent = intent

    def set_agent(self, agent: str) -> None:
        self.selected_agent = agent

    def set_llm_mode(self, mode: str) -> None:
        self.llm_mode = mode

    def set_fallback(self, used: bool) -> None:
        self.fallback_used = used

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "detected_intent": self.intent,
            "selected_agent": self.selected_agent,
            "tools_called": self.tools_called,
            "llm_mode": self.llm_mode,
            "fallback_used": self.fallback_used,
            "warnings": self.warnings,
        }
