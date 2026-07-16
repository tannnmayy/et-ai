# Copilot ↔ Map Bidirectional Integration — Report

**Date:** 2026-07-17  
**Status:** Complete

---

## How bidirectional integration works

```
┌─────────────┐   station_id / h3_cell / label    ┌─────────────┐
│  Map page   │ ───────────────────────────────► │  Copilot    │
│             │   (setMapContext + query)          │             │
│             │ ◄─────────────────────────────── │             │
└─────────────┘   map_actions (highlights/focus) └─────────────┘
        ▲                                                    │
        │              sessionStorage bridge                 │
        └──────────── MapCopilotContext ─────────────────────┘
```

### Map → Copilot
1. User selects a hex on the Map and taps **Ask Copilot about this area**.
2. `setMapContext({ h3_cell, label })` persists to React context + `sessionStorage`.
3. Navigation to `/copilot?h3_cell=…`.
4. Copilot sends `station_id` / `h3_cell` on `POST /copilot/query`.
5. Agent prefers that context and skips redundant `resolve_location`.

### Copilot → Map
1. After tools run, backend `extract_map_actions()` builds:
   - `highlight_h3_cells`
   - `highlight_stations`
   - `focus_on` (optional primary target)
2. Response includes optional top-level `map_actions`.
3. CopilotPage calls `applyMapActions(...)`.
4. Map page reads highlights, rings hex markers (fuchsia), pans focus, selects primary hex.
5. User can open Map via **View on Map** / highlight chip.

---

## Backend changes

| Item | Detail |
|------|--------|
| `CopilotMapActions` / `MapFocusTarget` | New fields on `CopilotResponse` |
| `backend/app/agents/map_actions.py` | Deterministic extraction from tool results + state |
| `orchestrator._finalize` | Attaches `map_actions`; audit step type `map` |
| System prompt | Map → context rules + “call spatial tools so Map can highlight” |
| Context block | Stronger MAP CONTEXT language for the agent |

**Sources for highlights:** enforcement ranked hexes, attribution/causal/what-if, resolve_location, forecast stations, plus client map context as fallback.

**Backward compatible:** `map_actions` is optional (`null` when no spatial anchors).

---

## Frontend changes

| Item | Detail |
|------|--------|
| `MapCopilotContext` | Bidirectional: context in + `mapActions` out; sessionStorage for both |
| `MapContainer` | `highlightedHexIds`, `focusCenter`, fuchsia ring + “Copilot” label |
| `MapPage` | Merges priorities into visible hexes; chips for Copilot highlights + Map Context Active |
| `CopilotPage` | Applies `map_actions`; **Map Context Active** chip; View on Map; no Deep Mode |

---

## How map highlighting is triggered

1. Ask Copilot e.g. *“Where should officers inspect for construction dust today?”*
2. Tool agent / heuristic calls `get_enforcement_priority`.
3. Response includes e.g.:
   ```json
   {
     "map_actions": {
       "highlight_h3_cells": ["8960…", "…"],
       "highlight_stations": [],
       "focus_on": { "h3_cell": "8960…", "label": "…", "lat": 13.0, "lng": 77.5 }
     }
   }
   ```
4. Frontend stores actions → Map markers glow purple for those H3 ids.

---

## UI changes

- **Deep Mode toggle:** already removed; not reintroduced.
- **Map Context Active** chip on Copilot when `station_id` / `h3_cell` is set (clearable).
- **Copilot highlights** chip on Map (clearable).
- **View on Map** badge on answers that applied map actions.

---

## Tests

```text
pytest tests/test_copilot_map_actions.py tests/test_copilot_final.py \
       tests/test_copilot_phase1.py tests/test_copilot_phase2.py
→ 38 passed
```

---

## Limitations

1. Highlights only render for hexes present in Map data pools (extremes + priorities). Hexes outside those sets won’t draw a marker (focus pan may still work if lat/lng present).
2. Station markers are not separate map layers yet—stations appear as `highlight_stations` in data / focus, with primary visual on H3.
3. No live push while staying on Map without refresh/navigation; actions are applied via shared context when Copilot responds or when returning to Map.
4. Agent does not emit free-form JSON for map_actions; extraction is **deterministic from tools** (reliable, grounded).

---

*End of report.*
