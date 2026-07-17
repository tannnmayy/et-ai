# Copilot Latency Optimizations Report

**Date:** 2026-07-17  
**Scope:** Grounded tool-calling loop — trim, map-context caps, 429, history, cache TTL  
**Constraint:** No new fast path; no system-prompt rewrite; grounding + map_actions preserved

---

## Baseline tests (before)

```
tests/test_copilot.py + phase1 + phase2 + final + map_actions + language_wire
96 passed, 3 warnings in 89.29s
```

(PowerShell exit code 1 was only from a DeprecationWarning on stderr, not test failures.)

---

## After tests

```
same suite + tests/test_copilot_latency_opts.py
103 passed, 3 warnings in 38.89s
```

**+7 new tests** in `tests/test_copilot_latency_opts.py`.  
**Updated:** `tests/test_copilot_final.py::test_follow_up_skips_response_cache`  
(old name `test_history_skips_response_cache` — history alone no longer forces cache skip).

---

## 1. Tool result trimming (Req 1 + 7)

**Function:** `summarize_tool_result_for_llm(tool_name, result)` in `grounded_tool_agent.py`.

| Destination | Payload |
|-------------|---------|
| LLM tool messages | **Trimmed** summary JSON (top 3–5 items, labeled numbers) |
| `tool_results` on state | **Full** untrimmed dict |
| Grounding | Full `tool_results` |
| `map_actions` extract | Full `tool_results` |
| Audit `tools_called` | Full args + success flags |

**Per-tool behaviour (balance with prose quality):**

- **Enforcement:** top 5 targets with `location`, `priority_score`, `fused_pm25`, `dominant_source` (not 100 hex dumps)
- **Attribution / causal / what-if:** location label + `source_mix` as **percent strings** + key PM numbers + short text fields
- **Forecast:** station, PM, risk, engine, short series sample
- **Policy:** top 4 excerpts (≤400 chars each) with title/source
- **Errors:** compact error object only

Trim keeps **labels next to numbers** so the model can write specific sentences, not bare figures.

Smoke trim size: enforcement 100-hex payload **12201 → 783 chars**.

---

## 2. Drop `resolve_location` when map context active (Req 2)

`_tools_for_state(state)` filters `OPENAI_TOOLS` when `map_context_provided` and (`station_id` or `h3_cell`).

User message still instructs: use map ids directly; do not call resolve.

Hard block remains if the model somehow names the tool (synthetic map_context payload).

**Smoke:** `resolve_in_schema: False` for Richmond-equivalent and compound map-context runs.

---

## 3. Tiered tool-call cap + graceful degradation (Req 3)

| Context | Cap |
|---------|-----|
| Map context + **simple** query | **2** tool calls |
| Map context + **compound** query | **4** tool calls |
| No map context | Unchanged **6 LLM steps** (`MAX_TOOL_STEPS`) |

**Compound detection:** `is_compound_query()` in `conversation_fallback.py` (multi-clause markers shared with orchestrator simple-query deny list: ` and `, `compare`, `what should`, multi-`?`, etc.).

**Cap hit without final text:** `_compose_partial_answer()`:

1. Mark `audit.partial_response = true` (+ warning `partial_response`)
2. Prefer LLM `summarize` over **trimmed** evidence for natural prose
3. Else `deterministic_summary_from_tools` (also prose-oriented)
4. Else short English honesty sentence

Pattern mirrors dynamic-planning step-cap exhaustion (finalize with what you have).

---

## 4. Rate-limit 429 handling (Req 4)

| Path | Behaviour |
|------|-----------|
| Groq tools | On 429 → trip per-key circuit, **no sleep/retry**, next key; then next provider |
| Gemini text | On 429 → **no backoff on same key**, next key immediately |
| All tools fail | `last_fallback_note = all_tool_providers_exhausted_heuristic` → agent heuristic |

Logged distinctly via `last_fallback_note` values such as:

- `429_groq_key_N_to_next_key`
- `429_gemini_key_N_to_next_key`
- `groq_tools_exhausted_try_next_provider`
- `all_tool_providers_exhausted_heuristic`

Order remains: **(a) next key → (b) next provider → (c) heuristic**.

---

## 5. Conditional conversation history (Req 5)

`is_follow_up_query(query, history)` in `conversation_fallback.py`:

- Detects pronouns (`it`, `there`, `that`, …), phrases (`compare`, `what about`, `and …`), short replies
- **Ambiguous → True** (include history)
- Clear long standalone questions without deictics → False

Grounded agent only injects prior turns when follow-up is true.

---

## 6. Wider cache eligibility + TTL (Req 6)

**Before:** any non-empty `conversation_history` disabled response cache.  
**After:** cache skipped only when `is_follow_up_query` is true.

**TTL (explicit, env-overridable):**

| Kind | Default |
|------|---------|
| Live AQI / enforcement / attribution answers | **15 minutes** (`AQI_SENTINEL_COPILOT_CACHE_TTL_LIVE`) |
| Default responses | **15 minutes** |
| Policy-heavy | **30 minutes** |
| Tool-result cache | **90 seconds** |

Rationale: weather/OSM snapshots ~30m; 15m is stricter so live pollution answers are not oversold as fresher than data cadence. Expired entries are misses (existing `time.time() - ts <= ttl` check).

---

## 7. Natural language output (Req 7)

- Final answers still go through model text or `deterministic_summary_from_tools` / partial compose — all produce **sentences**, not JSON dumps.
- Deterministic enforcement summary rewritten as prose (“leading targets include …”).
- Cap-exhaustion path explicitly asks the model for “coherent natural-language” prose.

---

## Richmond Town–equivalent smoke (mandatory)

**Query:** `why is Richmond Town always less polluted`  
**Context:** `h3_cell` set, map context active, no explicit intent, simple phrasing.

| Metric | Before (design/live issue) | After (instrumented smoke) |
|--------|----------------------------|----------------------------|
| `resolve_location` in schema | Available (wasted calls) | **Removed** |
| Tool calls | Often 4–6+ rounds → **timeout** on Groq | **2** (simple cap) |
| Chat rounds | Many | **2** |
| Completes | Timed out live | **Yes** (`SMOKE_OK`) |
| Latency (mocked tools/LLM) | N/A (hung live) | **~0.001 s** harness |
| Answer | None / timeout | Natural-language partial prose |
| `partial_response` | N/A | **true** when model kept requesting tools past budget |

**Compound:** `why is this area bad and what should the city do`

| Metric | After |
|--------|--------|
| Cap | **4** tool calls |
| Observed tool calls | **4** |
| Completes | Yes |
| resolve in schema | False |

---

## Files changed

| File | Change |
|------|--------|
| `backend/app/agents/grounded_tool_agent.py` | Trim, caps, tools filter, partial compose, conditional history |
| `backend/app/agents/conversation_fallback.py` | `is_follow_up_query`, `is_compound_query` |
| `backend/app/agents/orchestrator.py` | Cache eligibility via follow-up detection |
| `backend/app/agents/llm_provider.py` | 429 no same-key backoff; clearer fallback logging |
| `backend/app/agents/audit.py` | `partial_response` |
| `backend/app/schemas/copilot.py` | `partial_response` on audit schema |
| `backend/app/services/copilot_cache_service.py` | 15m live TTL |
| `backend/app/agents/grounding.py` | Prose-style deterministic summaries |
| `tests/test_copilot_latency_opts.py` | New |
| `tests/test_copilot_final.py` | Follow-up cache test updated |
| `scripts/_smoke_copilot_latency.py` | Richmond + compound harness |
| `docs/COPILOT_LATENCY_OPTS_REPORT.md` | This report |

---

## Remaining risks / limitations

1. **Partial answers** when the model never emits a final no-tool turn before the budget — intentional; marked `partial_response`.
2. **Live Groq latency** still depends on network/key health; caps reduce rounds but cannot eliminate all 429s under total quota exhaustion (heuristic remains last resort).
3. **Follow-up detection** errs toward including history — modest extra tokens on edge cases.
4. **15m cache** can still serve slightly stale live numbers within the TTL window — same honesty tradeoff as other 15–30m environmental caches in the project.
5. No model cascade / small-model planner (explicitly out of scope).

---

## How to re-verify

```bash
set PYTHONPATH=E:\1ETAI
python -m pytest tests/test_copilot_latency_opts.py tests/test_copilot_final.py -q
python scripts/_smoke_copilot_latency.py
```
