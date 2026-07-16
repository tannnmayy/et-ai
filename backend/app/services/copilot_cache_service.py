"""In-memory response + tool-result cache for the Copilot (Phase 2).

Features
--------
* Exact key: SHA-256 of normalized query + city/station/h3/profile/language/mode
* Semantic key: intent tokens + place tokens after synonym folding so similar
  questions (e.g. "Why is air quality poor near Peenya?" vs
  "Air pollution issues in Peenya area") can share cache entries
* Separate tool-result cache (short TTL) to speed multi-step agent runs
* Configurable TTLs via environment variables
* Cache metadata helpers for audit trails (cache_hit, cache_key, cache_kind)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL configuration (seconds)
# ---------------------------------------------------------------------------
_TTL_DEFAULT = int(os.getenv("AQI_SENTINEL_COPILOT_CACHE_TTL", str(3 * 60)))  # 3 min
_TTL_POLICY = int(os.getenv("AQI_SENTINEL_COPILOT_CACHE_TTL_POLICY", str(10 * 60)))
_TTL_LIVE = int(os.getenv("AQI_SENTINEL_COPILOT_CACHE_TTL_LIVE", str(90)))  # 90s
_TTL_TOOL = int(os.getenv("AQI_SENTINEL_COPILOT_CACHE_TTL_TOOL", str(60)))  # tool results
_SEMANTIC_ENABLED = os.getenv("AQI_SENTINEL_COPILOT_SEMANTIC_CACHE", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
_MAX_ENTRIES = int(os.getenv("AQI_SENTINEL_COPILOT_CACHE_MAX", "160"))
_MAX_TOOL_ENTRIES = int(os.getenv("AQI_SENTINEL_COPILOT_TOOL_CACHE_MAX", "256"))

# response key -> (timestamp, payload, ttl_seconds, meta)
_CACHE: dict[str, tuple[float, dict[str, Any], float, dict[str, Any]]] = {}
# semantic fingerprint -> response key (latest writer wins)
_SEMANTIC_INDEX: dict[str, str] = {}
# tool cache key -> (timestamp, payload, ttl)
_TOOL_CACHE: dict[str, tuple[float, dict[str, Any], float]] = {}
_LOCK = threading.RLock()
_PREFETCH_STARTED = False

# Stats counters (process lifetime)
_STATS = {
    "hits_exact": 0,
    "hits_semantic": 0,
    "misses": 0,
    "stores": 0,
    "tool_hits": 0,
    "tool_misses": 0,
}

# ---------------------------------------------------------------------------
# Synonym / stop-word folding for semantic fingerprints
# ---------------------------------------------------------------------------
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "from",
        "with",
        "about",
        "into",
        "over",
        "after",
        "before",
        "me",
        "my",
        "i",
        "we",
        "you",
        "your",
        "please",
        "can",
        "could",
        "would",
        "should",
        "what",
        "which",
        "who",
        "whom",
        "how",
        "when",
        "where",
        "does",
        "do",
        "did",
        "give",
        "show",
        "tell",
        "get",
        "right",
        "now",
        "today",
        "currently",
        "current",
        "area",
        "region",
        "locality",
        "zone",
        "near",
        "around",
        "nearby",
        "close",
        "this",
        "that",
        "there",
        "here",
        "some",
        "any",
        "and",
        "or",
        "but",
        "if",
        "then",
        "so",
        "just",
        "also",
        "very",
        "really",
        "quite",
    }
)

# Multi-word phrases first (order matters — longer first)
_PHRASE_SYNONYMS: list[tuple[str, str]] = [
    (r"\bair quality\b", "aqi"),
    (r"\bair pollution\b", "pollution"),
    (r"\bpollution issues?\b", "pollution"),
    (r"\bpollution problems?\b", "pollution"),
    (r"\bconstruction dust\b", "construction"),
    (r"\bpm\s*2\.5\b", "pm25"),
    (r"\bpm2\.5\b", "pm25"),
    (r"\bnext 24\s*h(?:ours?)?\b", "forecast"),
    (r"\b24[\s\-]?hour\b", "forecast"),
    (r"\b24h\b", "forecast"),
    (r"\bright now\b", "now"),
    (r"\bas of now\b", "now"),
]

_WORD_SYNONYMS: dict[str, str] = {
    "poor": "bad",
    "worse": "bad",
    "worst": "bad",
    "bad": "bad",
    "unhealthy": "bad",
    "hazardous": "bad",
    "severe": "bad",
    "high": "elevated",
    "elevated": "elevated",
    "polluted": "pollution",
    "pollution": "pollution",
    "pollutant": "pollution",
    "pollutants": "pollution",
    "smog": "pollution",
    "why": "cause",
    "reason": "cause",
    "reasons": "cause",
    "cause": "cause",
    "causes": "cause",
    "because": "cause",
    "driving": "cause",
    "driven": "cause",
    "source": "source",
    "sources": "source",
    "attribution": "source",
    "forecast": "forecast",
    "prediction": "forecast",
    "predicted": "forecast",
    "outlook": "forecast",
    "confidence": "confidence",
    "reliable": "confidence",
    "reliability": "confidence",
    "trust": "confidence",
    "enforce": "enforcement",
    "enforcement": "enforcement",
    "inspect": "enforcement",
    "inspection": "enforcement",
    "officer": "enforcement",
    "officers": "enforcement",
    "dispatch": "enforcement",
    "hotspot": "enforcement",
    "hotspots": "enforcement",
    "priority": "enforcement",
    "priorities": "enforcement",
    "policy": "policy",
    "guideline": "policy",
    "guidelines": "policy",
    "regulation": "policy",
    "regulations": "policy",
    "cpcb": "policy",
    "kspcb": "policy",
    "ncap": "policy",
    "weather": "weather",
    "rain": "weather",
    "wind": "weather",
    "temperature": "weather",
    "humidity": "weather",
    "travel": "travel",
    "commute": "travel",
    "bike": "travel",
    "outing": "travel",
    "briefing": "briefing",
    "overview": "briefing",
    "situation": "briefing",
    "summary": "briefing",
    "issues": "pollution",
    "issue": "pollution",
    "problem": "pollution",
    "problems": "pollution",
}

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
    {
        "id": "whatif-construction",
        "category": "What-If",
        "question": "What if construction activity reduces by 50% near Peenya?",
    },
    {
        "id": "whatif-traffic",
        "category": "What-If",
        "question": "What if we reduce traffic emissions by 30% on major corridors?",
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
    """Light normalize for exact-key matching (punctuation-tolerant)."""
    q = (query or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[?.!,;:]+$", "", q)
    q = re.sub(r"[\"'`]", "", q)
    return q


def semantic_normalize(query: str) -> str:
    """Fold synonyms / stopwords into a stable token fingerprint string."""
    q = _normalize_query(query)
    for pattern, replacement in _PHRASE_SYNONYMS:
        q = re.sub(pattern, replacement, q)
    # Strip remaining punctuation to spaces
    q = re.sub(r"[^\w\s\-]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    tokens: list[str] = []
    for raw in q.split():
        t = raw.strip("-_")
        if not t or t in _STOPWORDS:
            continue
        t = _WORD_SYNONYMS.get(t, t)
        if t in _STOPWORDS:
            continue
        tokens.append(t)
    # Sorted unique keeps order-independent similarity
    return " ".join(sorted(set(tokens)))


def _scope_blob(
    *,
    city: str,
    station_id: str,
    h3_cell: str | None,
    profile: str,
    language: str,
    force_dynamic_planning: bool,
) -> str:
    return "|".join(
        [
            (city or "bengaluru").lower().strip(),
            (station_id or "").strip().lower(),
            (h3_cell or "").strip().lower(),
            profile or "general",
            language or "en",
            "deep" if force_dynamic_planning else "std",
        ]
    )


def cache_key(
    query: str,
    *,
    city: str = "bengaluru",
    station_id: str = "",
    h3_cell: str | None = None,
    profile: str = "general",
    language: str = "en",
    force_dynamic_planning: bool = False,
) -> str:
    """Exact cache key (normalized query + scope)."""
    blob = "|".join(
        [
            _normalize_query(query),
            _scope_blob(
                city=city,
                station_id=station_id,
                h3_cell=h3_cell,
                profile=profile,
                language=language,
                force_dynamic_planning=force_dynamic_planning,
            ),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def semantic_cache_key(
    query: str,
    *,
    city: str = "bengaluru",
    station_id: str = "",
    h3_cell: str | None = None,
    profile: str = "general",
    language: str = "en",
    force_dynamic_planning: bool = False,
) -> str:
    """Semantic fingerprint key — similar questions share this when scope matches."""
    blob = "|".join(
        [
            semantic_normalize(query),
            _scope_blob(
                city=city,
                station_id=station_id,
                h3_cell=h3_cell,
                profile=profile,
                language=language,
                force_dynamic_planning=force_dynamic_planning,
            ),
        ]
    )
    return "sem:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _ttl_for_response(response: dict[str, Any], query: str = "") -> float:
    """Shorter TTL for live enforcement / forecast / attribution answers."""
    q = (query or "").lower()
    tools: list[str] = []
    try:
        tools = [
            t.get("tool", "")
            for t in (response.get("audit_trail") or {}).get("tools_called") or []
        ]
    except Exception:
        tools = []
    live_tools = {
        "get_enforcement_priority",
        "get_forecast",
        "get_attribution",
        "get_causal_explanation",
        "get_city_briefing",
        "get_weather",
        "get_travel_readiness",
        "tool_get_enforcement_priority",
        "tool_get_forecast_evidence",
    }
    if any(t in live_tools for t in tools):
        return float(_TTL_LIVE)
    if any(
        w in q
        for w in (
            "enforce",
            "inspect",
            "priority",
            "forecast",
            "pm2.5",
            "right now",
            "today",
            "pollut",
            "aqi",
        )
    ):
        return float(_TTL_LIVE)
    if any(w in q for w in ("cpcb", "kspcb", "ncap", "policy", "guideline", "who ")):
        return float(_TTL_POLICY)
    agent = (response.get("selected_agent") or "").lower()
    if agent in ("grounded_tool_agent", "forecast_evidence_agent"):
        return float(_TTL_LIVE)
    return float(_TTL_DEFAULT)


def lookup_cached_response(
    key: str,
    *,
    semantic_key: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Lookup response cache with metadata.

    Returns (payload_or_None, meta) where meta has:
      cache_hit, cache_kind (exact|semantic|miss), cache_key
    """
    meta: dict[str, Any] = {
        "cache_hit": False,
        "cache_kind": "miss",
        "cache_key": key,
        "semantic_key": semantic_key,
    }
    with _LOCK:
        hit = _CACHE.get(key)
        if hit:
            ts, payload, ttl, _entry_meta = hit if len(hit) == 4 else (hit[0], hit[1], hit[2], {})
            if time.time() - ts <= ttl:
                _STATS["hits_exact"] += 1
                meta.update({"cache_hit": True, "cache_kind": "exact", "cache_key": key})
                return dict(payload), meta
            _CACHE.pop(key, None)

        if _SEMANTIC_ENABLED and semantic_key:
            mapped = _SEMANTIC_INDEX.get(semantic_key)
            if mapped and mapped != key:
                hit2 = _CACHE.get(mapped)
                if hit2:
                    ts, payload, ttl, _entry_meta = (
                        hit2 if len(hit2) == 4 else (hit2[0], hit2[1], hit2[2], {})
                    )
                    if time.time() - ts <= ttl:
                        _STATS["hits_semantic"] += 1
                        meta.update(
                            {
                                "cache_hit": True,
                                "cache_kind": "semantic",
                                "cache_key": mapped,
                                "semantic_key": semantic_key,
                            }
                        )
                        return dict(payload), meta
                    _CACHE.pop(mapped, None)
                    _SEMANTIC_INDEX.pop(semantic_key, None)

        _STATS["misses"] += 1
        return None, meta


def get_cached_response(
    key: str,
    *,
    semantic_key: str | None = None,
) -> dict[str, Any] | None:
    """Backward-compatible lookup — returns payload only (or None).

    Prefer ``lookup_cached_response`` when you need cache_hit / cache_kind metadata.
    """
    payload, _meta = lookup_cached_response(key, semantic_key=semantic_key)
    return payload


def set_cached_response(
    key: str,
    response: dict[str, Any],
    query: str = "",
    *,
    semantic_key: str | None = None,
) -> None:
    with _LOCK:
        if not response or not response.get("answer"):
            return
        ttl = _ttl_for_response(response, query=query)
        entry_meta = {
            "semantic_key": semantic_key,
            "query_norm": _normalize_query(query),
            "semantic_norm": semantic_normalize(query) if query else "",
            "ttl": ttl,
        }
        _CACHE[key] = (time.time(), dict(response), ttl, entry_meta)
        if _SEMANTIC_ENABLED and semantic_key:
            _SEMANTIC_INDEX[semantic_key] = key
        _STATS["stores"] += 1
        if len(_CACHE) > _MAX_ENTRIES:
            oldest = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[:40]
            for k, _ in oldest:
                _CACHE.pop(k, None)
            # prune semantic index orphans
            live = set(_CACHE.keys())
            dead = [sk for sk, rk in _SEMANTIC_INDEX.items() if rk not in live]
            for sk in dead:
                _SEMANTIC_INDEX.pop(sk, None)


# ---------------------------------------------------------------------------
# Tool-result cache
# ---------------------------------------------------------------------------
def tool_cache_key(tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    blob = json.dumps(
        {"tool": tool_name, "args": arguments or {}},
        sort_keys=True,
        default=str,
    )
    return "tool:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def get_cached_tool_result(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any] | None:
    key = tool_cache_key(tool_name, arguments)
    with _LOCK:
        hit = _TOOL_CACHE.get(key)
        if not hit:
            _STATS["tool_misses"] += 1
            return None
        ts, payload, ttl = hit
        if time.time() - ts > ttl:
            _TOOL_CACHE.pop(key, None)
            _STATS["tool_misses"] += 1
            return None
        _STATS["tool_hits"] += 1
        return dict(payload)


def set_cached_tool_result(
    tool_name: str,
    arguments: dict[str, Any] | None,
    result: dict[str, Any],
    *,
    ttl: float | None = None,
) -> None:
    if not result or result.get("_tool_error"):
        return
    # Don't cache huge city-grid dumps forever — still OK with short TTL
    key = tool_cache_key(tool_name, arguments)
    use_ttl = float(ttl if ttl is not None else _TTL_TOOL)
    with _LOCK:
        _TOOL_CACHE[key] = (time.time(), dict(result), use_ttl)
        if len(_TOOL_CACHE) > _MAX_TOOL_ENTRIES:
            oldest = sorted(_TOOL_CACHE.items(), key=lambda kv: kv[1][0])[:64]
            for k, _ in oldest:
                _TOOL_CACHE.pop(k, None)


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _SEMANTIC_INDEX.clear()
        _TOOL_CACHE.clear()


def cache_stats() -> dict[str, Any]:
    with _LOCK:
        return {
            "entries": len(_CACHE),
            "semantic_index_entries": len(_SEMANTIC_INDEX),
            "tool_entries": len(_TOOL_CACHE),
            "ttl_default_seconds": _TTL_DEFAULT,
            "ttl_policy_seconds": _TTL_POLICY,
            "ttl_live_seconds": _TTL_LIVE,
            "ttl_tool_seconds": _TTL_TOOL,
            "semantic_enabled": _SEMANTIC_ENABLED,
            "hits_exact": _STATS["hits_exact"],
            "hits_semantic": _STATS["hits_semantic"],
            "misses": _STATS["misses"],
            "stores": _STATS["stores"],
            "tool_hits": _STATS["tool_hits"],
            "tool_misses": _STATS["tool_misses"],
        }


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
        for q in PREFETCH_QUERIES:
            try:
                retrieve_relevant_context(q, top_k=4)
            except Exception as exc:
                logger.debug("RAG prefetch retrieve failed for %r: %s", q, exc)
    except Exception as exc:
        logger.warning("RAG warm-up failed: %s", exc)
        results["rag"] = {"ready": False, "error": str(exc)}

    try:
        from backend.app.agents.orchestrator import run_orchestrator

        for q in PREFETCH_QUERIES[:3]:
            try:
                key = cache_key(q, city=city, force_dynamic_planning=False)
                sem = semantic_cache_key(q, city=city, force_dynamic_planning=False)
                cached, _meta = lookup_cached_response(key, semantic_key=sem)
                if cached:
                    results["queries"].append({"query": q, "status": "already_cached"})
                    continue
                resp = run_orchestrator(
                    query=q,
                    city=city,
                    force_dynamic_planning=False,
                )
                if isinstance(resp.get("audit_trail"), dict):
                    warnings = list(resp["audit_trail"].get("warnings") or [])
                    warnings.append("response_prefetched")
                    resp["audit_trail"]["warnings"] = warnings
                set_cached_response(key, resp, query=q, semantic_key=sem)
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
