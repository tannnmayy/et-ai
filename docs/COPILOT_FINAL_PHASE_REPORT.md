# AQI Sentinel Copilot — Final Phase Report

**Date:** 2026-07-17  
**Status:** Complete  
**Builds on:** Phase 1 (native tool-calling) · Phase 2 (map context API, semantic cache, UX badges)

---

## 1. Executive Summary

This phase makes the Copilot a **decision-support product**, not just a Q&A shell:

| Capability | Status |
|------------|--------|
| **What-If / counterfactual simulation** | New `run_whatif_scenario` tool + service |
| **Map → Copilot context (one-way)** | Map “Ask Copilot” + shared context + agent preference |
| **Multi-turn memory (session)** | Last 4–6 turns in request; agent + audit |
| **UI cleanup** | Deep Mode removed; What-If / memory badges; Map banner |

**Tests:** `82 passed` across `test_copilot_final`, `test_copilot_phase1`, `test_copilot_phase2`, `test_copilot`.

---

## 2. What-If Implementation

### How it works

1. **Service** — `backend/app/services/whatif_scenario_service.py`
   - Loads **baseline source attribution** (traffic / industrial / construction / burning) for an H3 cell or station.
   - Applies **scales** or **reduction/increase percentages** per source.
   - Renormalizes the mix.
   - Estimates **PM2.5 change** with a **linear source-contribution model**:
     - retained ≈ 1 − Σ share_s × (1 − scale_s)
     - simulated_pm25 ≈ baseline_pm25 × retained
     - uncertainty band ≈ ±30% of |ΔPM2.5|
   - Baseline PM2.5 from fusion when available, else **station forecast** fallback.
   - Optional **city enforcement re-rank** when construction scale ≠ 1 (uses existing `construction_scale` in enforcement priority).
   - Always returns `is_simulation: true` + a clear **disclaimer**.

2. **Tool** — `run_whatif_scenario` (native OpenAI-style schema)
   - Registered in `NATIVE_TOOL_DISPATCH` / `OPENAI_TOOLS`.
   - Heuristic fallback also invokes it for “what if / reduce by / scenario…” queries.
   - Not tool-result-cached (scenarios should recompute).

3. **Agent prompt**
   - What-If is a **core strength**: model must call the tool, label simulations, and surface uncertainty.

4. **Audit**
   - `audit_trail.whatif_used: true`
   - Reasoning step type `whatif`

### Example questions

| Question | Behavior |
|----------|----------|
| “What if construction activity reduces by 50% near Peenya?” | Parse 50% construction ↓ → simulate at Peenya / nearest hex |
| “What if we reduce traffic emissions by 30% on major corridors?” | Traffic scale 0.7; optional city-level ranking note |
| “How would pollution change if industrial emissions drop by 30%?” | Industrial reduction scenario |
| With Map hex selected: “What if construction drops 50% in this area?” | Uses `h3_cell` from Map context; skips resolve |

### Limitations (honest)

- **Linear model** — not a full atmospheric dispersion / chemistry model.
- Construction-only path for **enforcement re-rank** delta (other sources affect local PM estimate).
- Uncertainty band is **illustrative**, not a statistical CI.
- Results are **not legal proof** and not a CPCB forecast.

---

## 3. Map → Copilot Context (One-Directional)

### Flow

```
Map (select hex) → “Ask Copilot about this area”
  → sessionStorage + MapCopilotContext (h3_cell, label)
  → navigate /copilot?h3_cell=…
  → POST /copilot/query { h3_cell, station_id? }
  → Agent prefers context; skips resolve_location for same place
```

### Components

| Piece | Role |
|-------|------|
| `MapCopilotContext` | Shared React context + `sessionStorage` |
| Map page button | Sets context, navigates to Copilot |
| Copilot banner | Shows active MAP context; clear (X) |
| Backend (Phase 2+) | `station_id` / `h3_cell` on request; inject into tools including what-if |
| Heuristic path | Skips resolve when map context present |

### Not in scope (by design)

- Copilot → Map highlighting / camera move (bidirectional) — deferred.

---

## 4. Multi-Turn Conversation Memory

### Design

- **Client-owned history:** frontend sends `conversation_history: [{role, content}, …]` (last **6** turns).
- **No server persistence** across chats (session-scoped only).
- **Optional `session_id`** for audit correlation only.
- **Cache:** response cache is **skipped** when history is present (follow-ups are context-dependent).
- Agent injects prior turns into the chat messages before the latest user query.
- Audit: `memory_turns_used`, reasoning type `memory`.

### Follow-up examples

- “What about the area we discussed earlier?”
- “Compare that with Whitefield”
- “What if construction drops 50% **there**?” (after a Peenya thread)

---

## 5. UI Changes

| Change | Detail |
|--------|--------|
| **Removed Deep Mode** | Toggle, deep-mode loading branch, `force_dynamic_planning` from UI sends |
| **Removed** | Attachment / voice placeholders clutter (simplified input) |
| **What-If quick action** | “What-If 50% Construction” chip |
| **What-If suggestions** | Category + backend list |
| **Mode badges** | Tool Agent / Heuristic Fallback / Fast Path (styled) |
| **Cache badge** | Exact / similar |
| **What-If badge** | When simulation tool used |
| **Memory badge** | Shows turn count |
| **Map banner** | Active context + clear |
| **Loading** | Rotating tool-agent hints (no deep-mode wording) |

Legacy API field `force_dynamic_planning` remains accepted for backward compatibility but is not exposed in the UI.

---

## 6. New Tools & Prompt Changes

### New tool

- `run_whatif_scenario` → `tool_run_whatif_scenario` → `run_whatif_scenario()` service

### System prompt (high level)

- Map context rules strengthened  
- Conversation memory rules  
- What-If as mandatory tool path for hypotheticals  
- Simulation / uncertainty language required  

### Other backend

- Fast path **denies** what-if / scenario phrasing  
- Grounding deterministic summary includes what-if `summary_text`  
- Schema: `conversation_history`, `session_id`; audit `whatif_used`, `memory_turns_used`

---

## 7. Test Results

```text
pytest tests/test_copilot_final.py \
       tests/test_copilot_phase1.py \
       tests/test_copilot_phase2.py \
       tests/test_copilot.py
→ 82 passed
```

### Final-phase coverage (`test_copilot_final.py`)

- Scenario text parsing (construction / traffic / industrial)  
- Service + tool construction −50% at Peenya  
- Map context + what-if on heuristic path  
- Multi-turn memory audit  
- History disables naive cache hit path  
- Fast path exclusion of what-if  

---

## 8. Honest Assessment — Current State of the Copilot

### Strengths

1. **Native tool-calling** (Phase 1) remains the default intelligence layer.  
2. **Grounding** still constrains invented numbers.  
3. **What-If** is now a first-class, structured capability officers can use in planning discussions.  
4. **Map-aware** answers without re-geocoding when context is set.  
5. **Short memory** enables natural follow-ups inside a session.  
6. **UX** is clearer (modes, cache, simulation, memory) without obsolete Deep Mode.

### Gaps remaining

1. What-If physics is **simple linear** — good for directionality, not for regulatory modeling.  
2. No **streaming** of live tool steps.  
3. Memory is **short and client-sent** only (no server session store / summarization).  
4. No Copilot → Map feedback loop.  
5. Multi-worker cache still in-process.  
6. LLM quality still depends on Groq/Gemini availability (heuristic fallback is solid but less fluent).

### Bottom line

The Copilot is **product-ready for demos and operational assistance**: grounded free-text, map-scoped questions, follow-ups, and transparent what-if scenarios with uncertainty. It is **not** a replacement for full air-quality models or legal determinations — and it says so.

---

## 9. Key Files

| File | Role |
|------|------|
| `backend/app/services/whatif_scenario_service.py` | Simulation engine |
| `backend/app/agents/tools.py` | `tool_run_whatif_scenario` |
| `backend/app/agents/native_tool_schemas.py` | Tool schema + system prompt |
| `backend/app/agents/grounded_tool_agent.py` | History, map inject, what-if heuristic |
| `backend/app/agents/orchestrator.py` | History, cache skip, fast-path deny |
| `backend/app/schemas/copilot.py` | Request/response fields |
| `frontend/src/context/MapCopilotContext.tsx` | Map → Copilot context |
| `frontend/src/pages/MapPage.tsx` | “Ask Copilot” CTA |
| `frontend/src/pages/CopilotPage.tsx` | UI without Deep Mode + memory |
| `frontend/src/services/copilotService.ts` | History + context payload |
| `tests/test_copilot_final.py` | New tests |

---

## 10. Optional Next Steps (beyond this phase)

1. Bidirectional Map ↔ Copilot (highlight hex from answer).  
2. SSE streaming of tool steps.  
3. Richer what-if (multi-hex corridors, time-of-day).  
4. Server-side session store with summarization for long chats.  
5. Golden-set eval harness for what-if + follow-ups.

---

*End of final phase report.*
