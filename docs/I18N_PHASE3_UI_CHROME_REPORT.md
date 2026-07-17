# Multi-language Phase 3 — Light UI Chrome

**Date:** 2026-07-17  
**Depends on:** Phase 1 language wire · Phase 2 advisory content

---

## How i18n is set up

**Lightweight custom system** (no `i18next` dependency — keeps the stack light).

| Piece | Path |
|-------|------|
| Locale catalogs | `frontend/src/i18n/locales/en.json`, `hi.json`, `kn.json` |
| Core translate | `frontend/src/i18n/translate.ts` — `translate(key, lang, params?)` |
| React hook | `frontend/src/i18n/useT.ts` — reactive to `SessionContext.language` |
| Barrel | `frontend/src/i18n/index.ts` |
| Language codes | `frontend/src/i18n/lang.ts` (`en` \| `hi` \| `kn`) |

**API**

```ts
const { t, language } = useT();
t('copilot.send');
t('copilot.memory', { count: 3 }); // {{count}} interpolation
```

- Missing key → English catalog → raw key  
- Language changes re-render all `useT()` consumers immediately  
- Session language remains in `SessionContext` + `localStorage` (Phase 1)

---

## What was translated (high-impact chrome)

### Landing
- Hero badge, subtitle, bullets  
- Enter / Explore CTAs  
- What We Do + four feature cards  
- Data We Use + five source cards  
- Role cards + secure entry  
- Form labels, terms checkbox, continue/entering, validation errors  

### TopNav
- App name, citizen mode label  
- Tabs: Map, Enforcement, Copilot, Neighbourhoods, Insights  
- Neighbourhood finder (citizen)  
- Role labels, sign out, change role, guest/session  

### Copilot
- Empty state title/body + map hints  
- Placeholders (idle / map context / busy)  
- Suggested questions chrome  
- Loading spinner + rotating hints  
- Mode badges (Tool Agent / Heuristic / Fast Path)  
- Cache / What-If / Memory / Fallback badges  
- Map context chip, View on Map, dismiss  
- Quick action chips labels  
- Errors (timeout, network, empty, limited)  

### Left in English (by design)
- Map analytics / legends  
- Enforcement tables & metrics  
- Insights charts  
- Suggested question **text** from API (still English content)  
- Terms of use legal block on landing (English for legal safety)  
- Technical tokens (PM2.5, AQI, H3, station IDs)

---

## Components updated

- `frontend/src/pages/LandingPage.tsx`  
- `frontend/src/components/TopNav.tsx`  
- `frontend/src/pages/CopilotPage.tsx`  
- `frontend/src/services/copilotService.ts` (`formatCopilotError` uses locale)

---

## Testing

- Manual: switch EN → HI → KN in TopNav/Landing; Landing + Copilot chrome update without reload.  
- Typecheck: CopilotPage duplicate `title` fixed; remaining `tsc` issues are pre-existing (InsightsPage, prefetchService), not from i18n.  
- Backend i18n tests unchanged (Phase 2 still green if re-run).

**How to verify quickly**
1. Open Landing → switch to हिंदी → hero and roles switch to Devanagari.  
2. Enter app → TopNav tabs in Hindi.  
3. Open Copilot → empty state + placeholder in Hindi.  
4. Switch to ಕನ್ನಡ → UI updates live.  
5. Switch to EN → full English restored.

---

## Limitations

1. Suggested **question chips** from backend are still English (content, not chrome).  
2. Map / Enforcement / Insights pages not localized.  
3. No pluralization rules beyond simple `{{count}}`.  
4. No RTL (not needed for HI/KN).  
5. Prototype-quality civic translations — native review recommended.  
6. `roleLabel()` helper in SessionContext still English if used elsewhere; TopNav uses `t('role.*')` instead.

---

## Next steps (optional)

- Localize Map page short chips (“Ask Copilot”, “Map Context Active” on Map side).  
- Backend-localized suggestion lists per language.  
- Optional i18next migration later if catalogs grow large.
