# Multi-language Phase 1 — Language Wire Report

**Date:** 2026-07-17  
**Scope:** End-to-end language flow only (no UI string translation, no advisory HI/KN content yet)

---

## What changed

### Frontend

| File | Change |
|------|--------|
| `frontend/src/i18n/lang.ts` | **New** — `en\|hi\|kn` types, `normalizeLanguage`, labels |
| `frontend/src/context/SessionContext.tsx` | Stores **lowercase** `en\|hi\|kn`; migrates legacy `EN/HI/KN` on load; exposes `apiLanguage` |
| `frontend/src/components/TopNav.tsx` | Switcher uses `en/hi/kn` |
| `frontend/src/pages/LandingPage.tsx` | Language pills use `en/hi/kn` |
| `frontend/src/services/copilotService.ts` | Sends `language` from payload (no hardcode `en`) |
| `frontend/src/pages/CopilotPage.tsx` | Passes `sessionLanguage` on every Copilot request |

### Backend

| File | Change |
|------|--------|
| `schemas/copilot.py` | Documents `en\|hi\|kn` (case-insensitive) |
| `routers/copilot.py` | Normalizes language before orchestrator |
| `routers/intelligence.py` | Same for citizen advisory |
| `routers/persistence.py` | Default language `en` |
| `orchestrator.py` | Canonical lowercase language for cache + state |
| `copilot_cache_service.py` | Scope blob lowercases language (EN ≡ en) |
| `native_tool_schemas.py` | **LANGUAGE** block in system prompt |
| `grounded_tool_agent.py` | Context injects language; audit `language` step; `get_causal_explanation` gets `language=` |

---

## Language flow (now)

```
TopNav / Landing → setLanguage('hi')
        ↓
SessionContext.language = 'hi'  (localStorage, migrated from legacy EN/HI/KN)
        ↓
CopilotPage → useSendMessage({ language: sessionLanguage, ... })
        ↓
POST /copilot/query  { "language": "hi", "query": "..." }
        ↓
Router normalizes → orchestrator(language="hi")
        ↓
cache_key(..., language="hi")   // separate cache from en
AgentState.language = "hi"
        ↓
grounded_tool_agent:
  - audit: language=hi
  - user context: language=hi (Hindi). Respond in Hindi...
  - system prompt LANGUAGE rules
  - get_causal_explanation(language="hi") when called
```

Default remains **`en`** if missing/invalid.

---

## System prompt update

Added block:

- Respond in user’s language (`en` / `hi` / `kn`)
- Keep PM2.5, AQI, CPCB, station IDs, H3 IDs in English
- Only translate natural-language explanation
- Pass same language into `get_causal_explanation`

Per-request user context also includes:
`language=hi (Hindi). Respond in Hindi...`

---

## Caching

Verified: `cache_key` / `semantic_cache_key` include language in scope; case-normalized so `EN` and `en` share a key; `hi` ≠ `en`.

---

## Tests

```text
pytest tests/test_copilot_language_wire.py tests/test_copilot_phase1.py tests/test_copilot_phase2.py
→ 30 passed
```

Coverage:
- Language normalize
- Context block / causal inject
- Cache keys differ by language
- Orchestrator audit records hi/kn
- System prompt language rules present

---

## Limitations (Phase 1)

1. **No HI/KN advisory content yet** — `translation_fallback` still true for static advisories (Phase 2).
2. **UI chrome still English** — switcher works; labels/pages not translated (Phase 2/3).
3. **LLM quality** for Hindi/Kannada varies; depends on Groq/Gemini model.
4. **Heuristic fallback** summaries remain English-oriented when LLM is down.
5. **Manual UI test** (switch language → ask Copilot) recommended with live LLM keys.

---

## Manual check

1. Open app → set **हिंदी** in TopNav.  
2. Open Copilot → ask “Why is air quality poor near Peenya?”  
3. Confirm network request body has `"language":"hi"`.  
4. With LLM available, answer should be primarily Hindi (technical terms in English).  
5. Repeat for **ಕನ್ನಡ** (`kn`) and **EN** (`en`).
