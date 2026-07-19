# Enforcement Detail Expand — Implementation Report

**Status:** Complete  
**Date:** 2026-07-18

---

## How the expand action works

1. User opens **Enforcement** and selects any list row (or map hex).
2. The **right-side panel** (desktop) or **FluidSheet** (mobile) shows a **quick preview** — unchanged content and behavior.
3. Expand is available via:
   - **Expand** icon (top-right of the panel, next to close)
   - **“Open full detail page”** button under the header
   - **Click on the panel body** (non-interactive areas only; What-If slider, buttons, chart, links do not navigate)
4. Navigation goes to:
   ```
   #/enforcement/detail/<h3_cell>
   ```
   with:
   - `location.state.hex` (instant)
   - `sessionStorage` cache (`aqi_enforcement_detail_hex`) as backup
5. Full page reuses `EnforcementDetailPanel` with `variant="page"`:
   - Location + priority badge  
   - Score / Rank / Risk-adjusted  
   - PM2.5, Primary Source, Exposure  
   - Rank Impact + Risk Adjustment  
   - Attribution confidence (Enforcement)  
   - What-If Analysis (slider + presets)  
   - Full recommendations  
   - Evidence & metadata  
   - Copy Brief + Dispatch Unit  
6. **Back to list:** header **“Enforcement”** button or the panel close (X) on the full page → `#/enforcement`.

Dispatch and What-If work on both preview and full page.

---

## New route

| Hash route | Component |
|------------|-----------|
| `/enforcement` | `EnforcementPage` — list, map, quick preview |
| `/enforcement/detail/:h3Cell` | `EnforcementDetailPage` — full detail |

Registered in `App.tsx` under `MainLayout` (HashRouter).

---

## Data loading (fast path)

| Priority | Source |
|----------|--------|
| 1 | `location.state.hex` from expand click |
| 2 | `sessionStorage` via `enforcementDetailCache` |
| 3 | Any warm React Query `enforcement-priorities` cache |
| 4 | **Only if still missing:** fetch top-100 priorities (`enabled: needsFetch`) |

Expanding from a selected row almost never hits the network.

---

## Files modified / added

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Lazy route `enforcement/detail/:h3Cell` |
| `frontend/src/pages/EnforcementDetailPage.tsx` | **New** full-page shell + resolve hex |
| `frontend/src/components/enforcement/EnforcementDetailPanel.tsx` | Expand UX, `variant: 'panel' \| 'page'`, spacious page layout |
| `frontend/src/services/enforcementDetailCache.ts` | **New** sessionStorage helper |
| `frontend/src/pages/EnforcementPage.tsx` | Passes `variant="panel"`; keeps docked preview |
| `docs/ENFORCEMENT_DETAIL_EXPAND_REPORT.md` | This report |

---

## Constraints satisfied

| Requirement | Status |
|-------------|--------|
| Keep right-side preview panel | Yes |
| Expand icon top-right | Yes |
| Body click expands (safe for controls) | Yes |
| Full content on dedicated page | Yes |
| Back to list | Yes |
| Reuse panel component | Yes (`variant`) |
| No break Dispatch / What-If | Yes |
| Works for every selected row | Yes (uses that row’s `hex`) |
| No unnecessary API if data available | Yes (`enabled: needsFetch`) |

---

## Limitations

1. Deep-link to an H3 **not** in top-100 and never selected may show “Location not in current queue”.
2. Body-click expand intentionally ignores interactive controls (sliders, buttons, chart).
3. Risk-adjusted scores on the full page reflect the hex snapshot at expand time (same object as the list), not a separate re-fetch with `risk_adjusted=true` unless that mode was already used when loading the queue.

---

## How to verify

```powershell
cd E:\1ETAI\frontend
npm run dev
```

1. Open `#/enforcement`  
2. Select any row → preview panel appears  
3. Click **Expand** → full page at `#/enforcement/detail/...`  
4. Use What-If + **Copy Brief** / **Dispatch**  
5. Click **Enforcement** to return to the list  
