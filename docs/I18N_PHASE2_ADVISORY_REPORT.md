# Multi-language Phase 2 — Citizen Advisory + Copilot Language Quality

**Date:** 2026-07-17  
**Depends on:** Phase 1 language wire (`en` / `hi` / `kn` end-to-end)

---

## 1. Citizen Advisory translations

### Structure

All content lives in `backend/app/services/citizen_advisory_service.py`:

| Structure | Purpose |
|-----------|---------|
| `_ADVISORY_EN` / `_ADVISORY_HI` / `_ADVISORY_KN` | Risk-band templates: `headline`, `recommendations[]`, `caution_note` |
| `_ADVISORY_BY_LANG` | Lookup `lang → risk → content` |
| `_PROFILE_MODIFIERS_*` + `_PROFILE_BY_LANG` | Profile add-ons (child, elderly, respiratory, outdoor_worker, school) |
| `MEDICAL_DISCLAIMER_BY_LANG` | Localized medical disclaimer |
| `_NOTES` | Confidence / unavailable / data-quality helper phrases |

### Risk bands covered (all three languages)

Good · Satisfactory · Moderate · Poor · Very Poor · Severe

### Behavior

- Request `language=hi` or `kn` → `language_served` matches request  
- `translation_fallback: false` when the risk band exists in that language (all bands covered)  
- Technical categorical labels (e.g. confidence `High`/`Medium`/`Low`) stay English as system enums  
- Station names stay as provided by data (often English)

### Example (Hindi, Moderate band)

- Headline: «मध्यम वायु गुणवत्ता।»  
- Recommendations + caution in Devanagari  
- Disclaimer: «यह सामान्य वायु-गुणवत्ता संबंधी मार्गदर्शन है…»

---

## 2. Copilot language quality

### System prompt (`native_tool_schemas.py`)

Strengthened **LANGUAGE** block:

- Always answer in session language (`hi` → Hindi Devanagari, `kn` → Kannada script)
- Keep PM2.5, AQI, CPCB, station/H3 IDs in English
- Mixed-language inputs: still answer in session language
- Do not switch to English mid-answer unless asked
- Always pass `language` into `get_causal_explanation`

### Tool path

- User context still injects `language=hi (Hindi)…` (Phase 1)
- Step-limit summarize forces answer language explicitly

### Heuristic / deterministic fallback (`grounding.py`)

- Prefer localized **citizen advisory** tool text when present  
- Prefer **causal explanation** text when present  
- Otherwise English tool summary + HI/KN note that full localization needs LLM  

Example note (Hindi):  
`(नोट: विस्तृत उपकरण सारांश अंग्रेज़ी में है। पूर्ण हिंदी उत्तर के लिए LLM उपलब्ध होने पर पुनः प्रयास करें।)`

### Renderer

- `render_citizen_advisory` uses `medical_disclaimer` from payload (localized)

---

## 3. Test results

```text
pytest tests/test_citizen_advisory_service.py \
       tests/test_i18n_phase2_advisory.py \
       tests/test_copilot_language_wire.py
→ 30 passed
```

Highlights:

- HI/KN no longer assert `translation_fallback=True`  
- Devanagari / Kannada script checks on headlines and recommendations  
- All risk bands present in HI/KN tables  
- Deterministic summary HI note + advisory-tool preference  

---

## 4. Limitations

1. **LLM Hindi/Kannada quality** still model-dependent (Groq/Gemini).  
2. **Heuristic enforcement/forecast summaries** remain mostly English with a localized note (not full prose translation).  
3. **UI chrome** still English (Phase 3).  
4. **Profile English tests** still match English keywords (`children`, `school`) for `en` default profiles.  
5. Civic wording is **prototype-quality**; native speaker review recommended before production legal/health claims.

---

## 5. Recommendations for Phase 3 (Light UI Chrome)

1. Add `frontend/src/i18n/strings.ts` + `useT()` for:  
   - Landing roles/CTAs  
   - TopNav section names  
   - Copilot empty state, errors, chips (“Map Context Active”, mode badges)  
2. Show language badge on Copilot answers (`language_served` if returned).  
3. Optional: bilingual suggestion chips (EN questions OK short-term).  
4. Leave dense Map/Enforcement analytics English in v1 chrome.  
5. Human review pass on HI/KN advisory + chrome strings.

---

## Key files

| File | Role |
|------|------|
| `backend/app/services/citizen_advisory_service.py` | Full HI/KN advisory content |
| `backend/app/agents/native_tool_schemas.py` | Stronger LANGUAGE prompt |
| `backend/app/agents/grounding.py` | Localized fallback summary behavior |
| `backend/app/agents/grounded_tool_agent.py` | Pass language into deterministic paths |
| `backend/app/agents/fallback_renderer.py` | Use localized disclaimer |
| `tests/test_citizen_advisory_service.py` | Updated HI/KN expectations |
| `tests/test_i18n_phase2_advisory.py` | New coverage |
