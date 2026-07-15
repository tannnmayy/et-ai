"""In-memory response cache + prefetch helpers for the Copilot.

Caches full orchestrator responses for identical (or normalized) queries so
common policy / enforcement questions feel instant on repeat.

Also exposes a curated list of suggested questions used by the UI and by the
background prefetch warm-up.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LOCK = threading.RLock()
_TTL_SECONDS = 10 * 60  # 10 minutes
_MAX_ENTRIES = 128
_PREFETCH_STARTED = False

# Curated suggestions shown in the Copilot UI (grouped by category).
SUGGESTED_QUESTIONS: list[dict[str, str]] = [
    {
        "id": "policy-dust",
        "category": "Policy",
        "question": "What does CPCB say about construction dust control?",
    },
    {
        "id": "policy-ncap",
        "category": "Policy",
        "question": "Give me a summary of NCAP guidelines for Bengaluru",
    },
    {
        "id": "enforce-priorities",
        "category": "Enforcement",
        "question": "Show me the top enforcement priorities in Bengaluru right now",
    },
    {
        "id": "enforce-area",
        "category": "Enforcement",
        "question": "Where should officers inspect for construction dust today?",
    },
    {
        "id": "aqi-why",
        "category": "General AQI",
        "question": "Why is air quality poor near Peenya right now?",
    },
    {
        "id": "traffic-peak",
        "category": "Weather + Pollution",
        "question": "What are the peak traffic hours affecting pollution in Bengaluru?",
    },
]

# Prefetch subset — expensive deep planning is intentionally excluded.
PREFETCH_QUERIES: list[str] = [
    "What does CPCB say about construction dust control?",
    "Give me a summary of NCAP guidelines for Bengaluru",
    "Show me the top enforcement priorities in Bengaluru right now",
    "City briefing for Bengaluru",
]


def _normalize_query(query: str) -> str:
    q = (query or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[?.!]+$", "", q)
    return q


def cache_key(
    query: str,
    *,
    city: str = "bengaluru",
    station_id: str = "",
    profile: str = "general",
    language: str = "en",
    force_dynamic_planning: bool = False,
) -> str:
    blob = "|".join([
        _normalize_query(query),
        city.lower().strip(),
        (station_id or "").strip().lower(),
        profile,
        language,
        "deep" if force_dynamic_planning else "fast",
    ])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def get_cached_response(key: str) -> dict[str, Any] | None:
    with _LOCK:
        hit = _CACHE.get(key)
        if not hit:
            return None
        ts, payload = hit
        if time.time() - ts > _TTL_SECONDS:
            _CACHE.pop(key, None)
            return None
        # Return a shallow copy so callers can mutate safely
        return dict(payload)


def set_cached_response(key: str, response: dict[str, Any]) -> None:
    with _LOCK:
        # Don't cache hard failures / empty answers
        if not response or not response.get("answer"):
            return
        _CACHE[key] = (time.time(), dict(response))
        if len(_CACHE) > _MAX_ENTRIES:
            oldest = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[:32]
            for k, _ in oldest:
                _CACHE.pop(k, None)


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def cache_stats() -> dict[str, Any]:
    with _LOCK:
        return {"entries": len(_CACHE), "ttl_seconds": _TTL_SECONDS}


def get_suggested_questions() -> list[dict[str, str]]:
    return list(SUGGESTED_QUESTIONS)


def run_prefetch(*, city: str = "bengaluru") -> dict[str, Any]:
    """Warm RAG index + optionally cache common full answers.

    Safe to call from a background thread. Full-answer prefetch is best-effort
    and will not raise to the caller.
    """
    global _PREFETCH_STARTED
    results: dict[str, Any] = {"rag": None, "queries": []}

    try:
        from backend.app.services.rag_service import warm_rag_index, retrieve_relevant_context

        results["rag"] = warm_rag_index()
        # Warm retrieve cache for policy suggestions
        for q in PREFETCH_QUERIES:
            try:
                retrieve_relevant_context(q, top_k=4)
            except Exception as exc:
                logger.debug("RAG prefetch retrieve failed for %r: %s", q, exc)
    except Exception as exc:
        logger.warning("RAG warm-up failed: %s", exc)
        results["rag"] = {"ready": False, "error": str(exc)}

    # Full answer prefetch (deterministic path only — force_dynamic_planning=False)
    try:
        from backend.app.agents.orchestrator import run_orchestrator

        for q in PREFETCH_QUERIES[:3]:
            try:
                key = cache_key(q, city=city, force_dynamic_planning=False)
                if get_cached_response(key):
                    results["queries"].append({"query": q, "status": "already_cached"})
                    continue
                resp = run_orchestrator(
                    query=q,
                    city=city,
                    force_dynamic_planning=False,
                )
                # Mark as prefetched in audit so UI can show it if needed
                if isinstance(resp.get("audit_trail"), dict):
                    warnings = list(resp["audit_trail"].get("warnings") or [])
                    warnings.append("response_prefetched")
                    resp["audit_trail"]["warnings"] = warnings
                set_cached_response(key, resp)
                results["queries"].append({"query": q, "status": "cached"})
            except Exception as exc:
                logger.warning("Prefetch query failed for %r: %s", q, exc)
                results["queries"].append({"query": q, "status": "error", "error": str(exc)})
    except Exception as exc:
        logger.warning("Prefetch orchestrator import/run failed: %s", exc)

    _PREFETCH_STARTED = True
    return results


def start_background_prefetch(*, city: str = "bengaluru") -> bool:
    """Fire-and-forget prefetch once per process."""
    global _PREFETCH_STARTED
    if _PREFETCH_STARTED:
        return False

    def _worker() -> None:
        try:
            run_prefetch(city=city)
        except Exception as exc:
            logger.warning("Background prefetch crashed: %s", exc)

    t = threading.Thread(target=_worker, name="copilot-prefetch", daemon=True)
    t.start()
    return True
