# Map Dual Mode Report — Global Highest vs Local Peaks

**Date:** 2026-07-17  
**Feature:** P3 dual ranking for Map “Polluted” view

---

## How dual mode works

| Mode | API `mode` | Worst-list rule | When to use |
|------|------------|-----------------|-------------|
| **Global highest** | `global` (default) | Absolute top-N by fused PM2.5 among hexes with station fusion | Scientific “who is worst city-wide among covered hexes” |
| **Local peaks** | `local_peaks` | For each eligible PM2.5 station: take worst **K=8** fused hexes within ~**5 km**; merge/de-dupe; sort by fused PM; cap at N | Operational “dirty pocket near each sensor” |

**Unchanged**

- Fusion math (IDW, 5 km range)  
- Cleanest list (always absolute lowest fused PM)  
- Hexes without fusion never enter either list  

**Why Global looks north-only:** one station (e.g. Hebbal at 96) creates a large tie plateau (~696 hexes). Top 100 is a subset of that plateau.

**Why Local Peaks spreads:** each station contributes at most K hexes, so south stations (Jayanagar, Silk Board, …) appear even when their PM is below the Hebbal plateau.

---

## API changes

`GET /api/attribution/city/{city}/extremes`

| Query | Default | Description |
|-------|---------|-------------|
| `n` | 15 | Max best/worst size (1–100) |
| `mode` | `global` | `global` \| `local_peaks` |
| `peak_k` | 8 | Per-station worst count for local_peaks (1–20) |
| `simulated_hour` | null | Existing TOD override |

**New response fields**

- `mode`, `mode_description`  
- `peak_k` (local_peaks only)  
- `fusion_range_m`  
- `max_fused_pm25`, `tie_count_at_max`, `max_station_id`  
- `ranking_note` (coverage honesty)

**Files**

- `backend/app/services/attribution_service.py` — `_select_local_peaks_worst`, mode on `get_city_extremes`  
- `backend/app/routers/attribution.py` — query params  
- `backend/app/schemas/attribution.py` — `CityExtremesResponse` fields  

**Bug fixed during implementation:** Local Peaks initially used `BENGALURU_STATIONS` whose objects often have **null lat/lon**, so the selector fell back to absolute ranking. Now uses **`get_registry_stations()`** (verified coordinates).

---

## Frontend UI

**Polluted ranking** control (when Hex view is **Polluted** or **Both**):

- Segmented: **Global highest** | **Local peaks**  
- Depth select: Top 15 / 30 / 50 / 100 (still client-side slice of fetched 100)  
- Banner:
  - Global: absolute fused PM + tie-plateau note when `tieCountAtMax` is large  
  - Local peaks: “worst hexes near each station (~5 km), merged…”  
- Coverage line: `Ranked among N fused hexes of M grid · ~5 km range`  
- Prefetch both modes on landing for fast toggle  

**Files**

- `frontend/src/services/geospatialService.ts` — `mode` param, `CityExtremesResult`, `useCityExtremes(mode)`  
- `frontend/src/services/prefetchService.ts` — prefetch global + local_peaks  
- `frontend/src/pages/MapPage.tsx` — ranking toggle + honesty banners  

---

## Smoke test results (live data)

| Metric | Global | Local peaks |
|--------|--------|-------------|
| worst count (n=30) | 30 | 30 |
| lat span | ~13.00–13.02 (north plateau) | **~12.88–13.06** (city-wide) |
| max fused | 96 | (mixed; includes lower peaks) |
| ties at max | 696 | — |
| schema | ok | ok |

---

## Remaining notes

1. Full extremes still recompute attribution over the scored grid (~12–15s cold); mode switch reuses React Query cache after first load of each mode.  
2. Local peaks can still rank high-Hebbal hexes first within the merged list; south appears once N exceeds northern per-station slots (or when using lower Top depth after higher southern peaks fill). With peak_k=8 and ~9 stations, Top 30+ typically includes multiple catchments.  
3. Default remains **global** for backward compatibility; demo can switch to Local peaks in one click.

---

## How to verify manually

1. Open Map → Hex view **Polluted** → Top 100.  
2. **Global highest** → expect northern cluster when Hebbal leads.  
3. **Local peaks** → expect markers near multiple stations (south/west/east).  
4. Read banner + coverage line for judge-facing honesty.
