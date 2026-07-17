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
        # Extended reasoning trace for Deep Reasoning / UI
        self.reasoning_trace: list[dict[str, Any]] = []
        self.knowledge_base_used: bool = False
        self.knowledge_backend: str | None = None
        self.llm_provider_used: str | None = None
        self.gemini_key_index: int | None = None
        # Phase 2 cache / mode metadata
        self.cache_hit: bool = False
        self.cache_key: str | None = None
        self.cache_kind: str | None = None  # exact | semantic | miss
        self.response_mode: str | None = None  # tool_agent | heuristic_fallback | fast_path
        self.memory_turns_used: int = 0
        self.whatif_used: bool = False
        # True when tool-loop cap forced a best-effort answer from partial tool results
        self.partial_response: bool = False

    def record_tool_call(self, tool_name: str, arguments: dict[str, Any], success: bool) -> None:
        event = {
            "tool": tool_name,
            "arguments": arguments,
            "success": success,
        }
        self.tools_called.append(event)
        self.reasoning_trace.append({
            "type": "tool",
            "tool": tool_name,
            "success": success,
            "arguments": {k: v for k, v in list(arguments.items())[:6]},
            "detail": f"{'OK' if success else 'FAILED'}: {tool_name}",
        })

    def record_reasoning(self, step_type: str, detail: str, **extra: Any) -> None:
        entry = {"type": step_type, "detail": detail, **extra}
        self.reasoning_trace.append(entry)

    def set_intent(self, intent: str) -> None:
        self.intent = intent
        self.record_reasoning("route", f"Detected intent: {intent}")

    def set_agent(self, agent: str) -> None:
        self.selected_agent = agent
        self.record_reasoning("agent", f"Selected agent: {agent}")

    def set_llm_mode(self, mode: str) -> None:
        self.llm_mode = mode

    def set_fallback(self, used: bool) -> None:
        self.fallback_used = used
        if used:
            self.record_reasoning("fallback", "Deterministic / grounded fallback path used")

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)

    def set_knowledge(self, used: bool, backend: str | None = None, chunk_count: int = 0) -> None:
        self.knowledge_base_used = used
        self.knowledge_backend = backend
        if used:
            self.record_reasoning(
                "knowledge_base",
                f"Retrieved {chunk_count} chunk(s) via {backend or 'unknown'}",
                backend=backend,
                chunk_count=chunk_count,
            )

    def set_llm_meta(self, provider: str | None, gemini_key_index: int | None = None) -> None:
        self.llm_provider_used = provider
        self.gemini_key_index = gemini_key_index
        if provider:
            detail = f"LLM provider: {provider}"
            if gemini_key_index:
                detail += f" (Gemini key #{gemini_key_index})"
            self.record_reasoning("llm", detail, provider=provider, gemini_key_index=gemini_key_index)

    def set_cache_meta(
        self,
        *,
        cache_hit: bool,
        cache_key: str | None = None,
        cache_kind: str | None = None,
    ) -> None:
        self.cache_hit = cache_hit
        self.cache_key = cache_key
        self.cache_kind = cache_kind
        if cache_hit:
            self.record_reasoning(
                "cache",
                f"Cache hit ({cache_kind or 'exact'})",
                cache_key=cache_key,
                cache_kind=cache_kind,
            )

    def set_response_mode(self, mode: str) -> None:
        self.response_mode = mode

    def set_memory_turns(self, n: int) -> None:
        self.memory_turns_used = max(0, int(n))
        if self.memory_turns_used:
            self.record_reasoning(
                "memory",
                f"Using {self.memory_turns_used} prior turn(s) from conversation history",
                turns=self.memory_turns_used,
            )

    def mark_whatif(self) -> None:
        self.whatif_used = True
        self.record_reasoning("whatif", "What-if / counterfactual simulation tool used")

    def mark_partial_response(self, detail: str = "Tool-loop cap reached; best-effort answer") -> None:
        self.partial_response = True
        self.warnings.append("partial_response")
        self.record_reasoning("partial", detail, partial_response=True)

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
            "reasoning_trace": self.reasoning_trace,
            "knowledge_base_used": self.knowledge_base_used,
            "knowledge_backend": self.knowledge_backend,
            "llm_provider_used": self.llm_provider_used,
            "gemini_key_index": self.gemini_key_index,
            "cache_hit": self.cache_hit,
            "cache_key": self.cache_key,
            "cache_kind": self.cache_kind,
            "response_mode": self.response_mode,
            "memory_turns_used": self.memory_turns_used,
            "whatif_used": self.whatif_used,
            "partial_response": self.partial_response,
        }
