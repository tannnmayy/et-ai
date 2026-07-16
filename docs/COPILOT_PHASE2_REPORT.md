# AQI Sentinel Copilot — Phase 2 Report

**Date:** 2026-07-17  
**Status:** Complete  
**Scope:** Map context integration · Semantic/smart caching · Frontend UX & resilience

---

## 1. Summary of Changes

Phase 2 builds on the Phase 1 native tool-calling agent to make the Copilot feel more **contextual**, **efficient**, and **production-grade** for both enforcement officers and citizens.

| Area | What changed |
|------|----------------|
| **Map context** | Optional `station_id` / `h3_cell` preferred by agent; system prompt + tool injection + heuristic path respect context |
| **Semantic cache** | Synonym-folded fingerprints so similar questions share answers; tool-result cache; audit metadata |
| **Frontend UX** | Mode badges, cache indicators, rotating loading states, better errors, double-submit guard, limited-response styling, clearer audit trail |
| **Quality** | Stronger system prompt; REST explicit intents restored; grounding retained; fast path remains narrow |

---

## 2. Map Context Integration

### How it works

1. **API (already accepted, now fully wired)**  
   `POST /copilot/query` body may include:
   - `station_id` (optional) — e.g. `cpcb_peenya`
   - `h3_cell` (optional) — H3 cell from Map / Enforcement selection

2. **Orchestrator**  
   - Sets `AgentState.h3_cell`, `map_context_provided=True` when either field is present.  
   - Records a route reasoning step: *“Client Map context provided — prefer over resolve_location”*.  
   - Includes map scope in the **cache key** so context-bound answers do not pollute generic city answers.

3. **Tool-calling agent**  
   - Appends a structured context block to the user message (`preferred station_id`, `preferred h3_cell`, skip-resolve instruction).  
   - Injects missing `station_id` / `h3_cell` into `get_forecast`, `get_forecast_confidence`, `get_attribution`, `get_causal_explanation` when the model omits them.  
   - If the model still calls `resolve_location` for the **same** place as Map context, returns a synthetic `map_context` resolution instead of re-geocoding.  
   - Still calls `resolve_location` when the user asks about a **different** place.

4. **Heuristic fallback**  
   - With Map context, skips `resolve_location` and uses provided station/h3 for attribution/forecast tools.

5. **Frontend client**  
   - `CopilotSendPayload` supports `station_id` and `h3_cell`.  
   - Copilot page reads `?station_id=` / `?h3_cell=` query params (ready for Map wiring).  
   - Banner shows **MAP CTX** when context is active.

### Behavior without context

Unchanged: free-text uses `resolve_location` + tools as in Phase 1.

### Backward compatibility

Existing clients that omit `station_id` / `h3_cell` behave exactly as before.

---

## 3. Semantic / Smart Caching

### Design (lightweight, no extra embedding service)

| Layer | Mechanism |
|-------|-----------|
| **Exact key** | SHA-256 of normalized query + city + station + h3 + profile + language + mode |
| **Semantic key** | Synonym fold + stopword removal + sorted unique tokens + same scope → `sem:…` fingerprint |
| **Tool cache** | Short-TTL cache of individual tool results (skip `resolve_location`) |

**Example semantic match**

- “Why is air quality **poor** near Peenya right now?”  
- “Why is air quality **bad** near Peenya?”  

→ same semantic key after `poor`/`bad` folding.

### Lookup order

1. Exact key hit → `cache_kind: exact`  
2. Else semantic index hit → `cache_kind: semantic`  
3. Else miss → run agent, store both keys

### Audit / response metadata

```json
{
  "cache_hit": true,
  "audit_trail": {
    "cache_hit": true,
    "cache_key": "<sha or mapped key>",
    "cache_kind": "exact | semantic | miss",
    "response_mode": "tool_agent | heuristic_fallback | fast_path",
    "warnings": ["served_from_response_cache", "served_from_semantic_cache?"]
  },
  "response_mode": "tool_agent"
}
```

### TTL environment variables

| Variable | Default | Role |
|----------|---------|------|
| `AQI_SENTINEL_COPILOT_CACHE_TTL` | 180s | Default answer TTL |
| `AQI_SENTINEL_COPILOT_CACHE_TTL_POLICY` | 600s | Policy / guideline answers |
| `AQI_SENTINEL_COPILOT_CACHE_TTL_LIVE` | 90s | Live AQI / enforcement / forecast |
| `AQI_SENTINEL_COPILOT_CACHE_TTL_TOOL` | 60s | Per-tool result cache |
| `AQI_SENTINEL_COPILOT_SEMANTIC_CACHE` | `1` | Enable semantic index (`0` to disable) |
| `AQI_SENTINEL_COPILOT_CACHE_MAX` | 160 | Max full-answer entries |
| `AQI_SENTINEL_COPILOT_TOOL_CACHE_MAX` | 256 | Max tool-result entries |

### API surface

- `get_cached_response(key)` → payload only (backward compatible)  
- `lookup_cached_response(key, semantic_key=…)` → `(payload, meta)`  
- `GET /copilot/cache/stats` → entries, TTLs, hit counters, semantic flag  

### Deviations / design notes

- **No dense embeddings** for answer cache: synonym + token fingerprint is deterministic, fast, and dependency-free. Dense RAG remains used for policy search only.  
- Generic refuse answers are still not stored for long (same Phase 1 rule).

---

## 4. Frontend UX & Resilience

| Improvement | Detail |
|-------------|--------|
| **Mode badges** | Tool Agent · Heuristic Fallback · Fast Path |
| **Cache badge** | “Cache” or “Cache · similar” (semantic) |
| **Loading** | Rotating hints (resolve → tools → ground → compose) + progress dots; spin on send button |
| **Errors** | Timeout / network / 5xx / 422 messages via `formatCopilotError` |
| **Double-submit** | `submittingRef` + mutation pending + disabled inputs/suggestions |
| **Limited answers** | Orange panel + “Limited / partial response” for generic refuses |
| **Reasoning UI** | Tool args preview, type labels, grounding/cache icons, taller scroll |
| **Map context** | Query-param bootstrap; banner indicator |
| **Deep mode** | Disabled while request in flight |

---

## 5. Updated Tool-Calling Behavior

- System prompt expanded: Map context rules, multi-part questions, ambiguous places, officer vs citizen tone.  
- Context injection before tool execution.  
- Synthetic skip of redundant `resolve_location` when Map context matches.  
- Tool-result cache hits recorded in audit (`cache` reasoning steps).  
- Grounding check **unchanged** from Phase 1 (relative % tolerance, retry, deterministic summary).  
- **Narrow fast path** unchanged: only simple forecast/confidence with station; deny-list still blocks “why/poor/near…”.

### REST explicit intents restored

Dedicated agents for:

- `/stations/{id}/explain` → forecast evidence  
- `/stations/{id}/guidance` → citizen advisory  
- `/cities/{city}/inspection-plan` → enforcement planning  
- `/cities/{city}/briefing` → city briefing  

Free-text still defaults to the native tool agent.

---

## 6. New / Documented Environment Variables

See §3 and `.env.example`. Phase 1 Groq/Gemini keys unchanged.

---

## 7. Test Results

```
pytest tests/test_copilot_phase1.py tests/test_copilot_phase2.py tests/test_copilot.py
→ 72 passed
```

### New coverage (`tests/test_copilot_phase2.py`)

- Semantic normalize / synonym folding  
- Exact + semantic cache hits  
- Cache stats fields  
- Map context recorded on heuristic path  
- No-context enforcement still uses tool agent  
- Fast path → `response_mode: fast_path`  
- Orchestrator cache hit + semantic hit end-to-end  

### Queries that work better

| Query | Why better |
|-------|------------|
| “Why is air quality poor near Peenya?” then “Why is air quality bad near Peenya?” | Semantic cache share |
| Free-text with `station_id=cpcb_peenya` | Skips redundant resolve; attribution uses station/h3 |
| Simple “What is the forecast for this station?” + station | Fast path + mode badge |
| LLM down + place name | Heuristic multi-tool with resolve-first (Phase 1) still works |
| Repeat identical question | Exact cache + violet Cache badge |

---

## 8. Remaining Limitations

1. **Map UI auto-wire** — API + query-param ready; Map page does not yet push selection into Copilot state automatically.  
2. **Semantic cache** is synonym/token based, not true embeddings — paraphrases with very different wording may miss.  
3. **No streaming** of intermediate tool steps to the UI (loading hints are client-side rotation only).  
4. **In-memory cache** — not shared across multi-worker processes.  
5. **Conversation memory** — still single-turn; no multi-message thread state.  
6. **h3_cell validation** — not strictly validated as a real H3 index (invalid cells fail at tool time with a tool error).  
7. **Tool cache** may briefly serve slightly stale live data (TTL 60s by default).

---

## 9. Honest Assessment — How Much Better After Phase 2?

| Dimension | Phase 1 | Phase 2 | Delta |
|-----------|---------|---------|-------|
| Free-text grounding | Strong | Strong | Maintained |
| Map-aware answers | Manual station only | Prefer station + h3 | **High** for Map/Enforcement flows |
| Repeat / similar Q latency | Exact string only | Exact + semantic | **Medium–High** for common paraphrases |
| Operator trust / transparency | Basic trace | Mode + cache badges + clearer audit | **High** UX |
| Resilience under failure | Heuristic fallback | Same + clearer limited UI | **Medium** |
| Production polish | Good MVP | Feels more product-like | **Meaningful** |

**Overall:** Phase 2 is a solid production step—not a revolution of intelligence (that was Phase 1’s tool-calling leap), but a clear upgrade in **context awareness**, **cache quality**, and **operator-facing UX**. With Map wiring in the UI, officer workflows will feel distinctly tighter.

---

## 10. Recommended Phase 3 Focus

1. **Map ↔ Copilot live wiring** — selected hex/station from Map/Enforcement auto-injected into every Copilot query.  
2. **Streaming tool progress** — SSE or WebSocket so the UI shows real tool names as they run.  
3. **Session memory** — short multi-turn context (last N Q/A + map selection).  
4. **Optional embedding semantic cache** — MiniLM similarity if synonym folding proves too weak in the field.  
5. **Redis / shared cache** for multi-worker deploys.  
6. **Evaluation harness** — fixed golden set (Peenya why-polluted, enforcement, policy, map-context) with regression scoring.  
7. **Citizen vs officer tone profiles** — explicit profile switch that changes answer framing without changing tools.

---

## 11. Key Files Touched

| File | Role |
|------|------|
| `backend/app/services/copilot_cache_service.py` | Semantic + tool cache |
| `backend/app/agents/orchestrator.py` | Context, cache meta, REST intents, modes |
| `backend/app/agents/grounded_tool_agent.py` | Context inject, resolve skip, tool cache |
| `backend/app/agents/native_tool_schemas.py` | System prompt Phase 2 |
| `backend/app/agents/state.py` / `audit.py` / `schemas/copilot.py` | h3 + cache fields |
| `frontend/src/services/copilotService.ts` | Context payload, mode helpers, errors |
| `frontend/src/pages/CopilotPage.tsx` | Full UX pass |
| `frontend/src/types.ts` | Meta fields |
| `tests/test_copilot_phase2.py` | New tests |
| `.env.example` | Cache env vars |

---

*End of Phase 2 report.*
