# Map Page Polish Report

**Date:** 2026-07-17  
**Scope:** Glowing blue layer removal, sensor markers, real nearby AQI, right-side controls

---

## 1. What was removed (glowing blue / plume effects)

| Removed | Why |
|---------|-----|
| Station diamond **blue glow** (`box-shadow: 0 0 12px rgba(10,132,255,0.7)`) | Looked like a debug bloom, not a clean marker |
| Hex **confidence glow** box-shadows and outer SVG glow polygons | Created a blue/green “diagram bloom” over the map |
| Mock **Local Wind Vector** compass (“Sensor array Alpha-2”, hardcoded East, 12 km/h) | Fake plume-style diagram, not connected to live wind |
| **“Local Plume Analysis”** title | Plume-era framing; replaced with **Area detail** |
| Heavy **blue gradient confidence card** glow in the detail panel | Softened to neutral glass border |
| Duplicate floating **Copilot chips** stacked over Hex View | Merged into one right-side control card |

Kept: Copilot fuchsia **ring** on highlighted hexes (functional, not a city-wide blue layer).

---

## 2. Sensor markers updated

- **Style:** Clean **blue diamond** (rotated square): solid `#0A84FF` outer, white inner facet, light drop shadow only (no neon glow).
- **Labels:** Short station name (CPCB/KSPCB stripped) + station AQI under the diamond.
- **Simulation mode:** Matching diamond + label drawn on the SVG grid.
- Visually distinct from rectangular H3 hex cards.

---

## 3. Nearby AQI around sensors (real data only)

- Removed synthetic formula: `station.aqi * (0.82 + …) + offset`.
- New `buildNearbySamples()`:
  - Pool = cleanest extremes + polluted extremes + enforcement priorities (real fused PM2.5).
  - For each official station, pick **≥5 nearest hexes** within **~4.5 km** with `pm25 > 0`.
  - Renders small AQI chips (dot + value) at those hex coordinates.
- Legend note: *“Nearby samples = real fused hexes within ~4.5 km of a station — not synthetic.”*

**Caveat:** Samples come from the extremes/priorities pool already loaded for the map (~200 hexes max), not a full-city fusion pull. Stations in sparse areas may show fewer than 5 if the pool has no nearby cells.

---

## 4. Right-side UI cleanup

Single vertical stack (`top-4 right-4`, max width ~288px):

1. **Hex view card**
   - Cleanest / Both / Polluted segmented control  
   - Polluted depth select when needed  
   - Count summary + sensor count  
   - Copilot highlights + map context **inside the same card** (no second floating box)
2. **Area detail panel** (when a hex is selected)
   - Below controls, max height ~58vh, internal scroll  
   - Close (X) button  
   - No full-height panel covering the map controls  

Left: AQI | Confidence toggle only.  
Legend: bottom-left, includes sensor diamond + nearby-chip key (no glowing legend dots).

---

## Files modified

- `frontend/src/components/MapContainer.tsx` — full marker/sample/glow pass
- `frontend/src/pages/MapPage.tsx` — layout, sample pool, legend, detail panel
- `docs/MAP_POLISH_REPORT.md` — this report

---

## Remaining small visual notes

1. **Nearby sample density** depends on extremes/priorities coverage; a dedicated “hexes near station” API would make every sensor reliably show 5+.
2. Station labels can still crowd at city zoom — names are truncated; zoom-in improves readability.
3. Live Google Map vs simulation still depends on `VITE_GOOGLE_MAPS_API_KEY`.
4. Detail panel still auto-selects first hex so “Area detail” is often open; user can close with X.

---

## Verification

- `npx tsc --noEmit` passes after changes.
- Existing features retained: AQI/Confidence layer, Hex view depths, Copilot highlight/focus, Ask Copilot, Dispatch.
