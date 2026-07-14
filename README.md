# AQI Sentinel — Complete Project Documentation

*A full, exhaustive reference: what this project is, why every decision was made,
exactly how every part works, and precisely where things stand right now. Written
to be usable by a teammate, a judge, or future-you with zero prior context.*

---

## Part 1 — The Problem This Exists to Solve

### 1.1 The real-world problem

India's air quality crisis is not a Delhi problem — it's a national urban crisis.
CPCB's 2024 National Air Quality data shows 24 of India's 50 most polluted cities
are Tier 1/Tier 2 urban centres. The Lancet Planetary Health journal estimates 1.67
million premature deaths annually in India from air pollution. Despite India
operating 900+ Continuous Ambient Air Quality Monitoring Stations (CAAQMS) under
the National Clean Air Programme, a 2024 CAG audit found only 31% of cities with
monitoring data had any actionable, multi-agency response protocol linked to those
readings. **The data exists. The intelligence layer to act on it does not.**

### 1.2 The hackathon problem statement (Problem Statement 5)

The ET AI Hackathon challenge asks for an AI-powered Urban Air Quality Intelligence
platform that fuses monitoring station data, satellite imagery, mobility feeds,
meteorological forecasts, and geospatial land-use layers to move cities from
**reactive monitoring** to **proactive, evidence-based intervention**. Explicitly
named suggested capabilities:

- **Geospatial Pollution Source Attribution** — multi-modal analysis of spatial-
  temporal AQI against land use, traffic, construction, industrial stacks, and
  satellite-detected thermal anomalies, attributing pollution by source category
  with confidence scores.
- **Hyperlocal Predictive AQI Forecasting** — 24-72h forecasts at ~1km grid
  resolution, not just at physical station locations.
- **Enforcement Intelligence & Prioritisation** — evidence-backed, prioritized
  recommendations correlating pollution hotspots with registered emission sources.
- **Multi-City Comparative Dashboard** — explicitly listed as illustrative-only,
  not a core requirement.
- **Citizen Health Risk Advisory** — ward-level risk alerts, personalized
  advisories pushed through mobile apps, public displays, and IVR, in regional
  languages ("Bengaluru in Kannada" is the problem statement's own example).

Judging weights: **Innovation 25%, Business Impact 25%, Technical Excellence 20%,
Scalability 15%, User Experience 15%.**

---

## Part 2 — Project History: How This Evolved

### 2.1 The starting point

Before this collaboration, "AQI Sentinel" already existed as a well-engineered but
narrowly-scoped Bengaluru PM2.5 forecasting API: LightGBM + persistence baseline,
a deterministic multi-agent copilot, geospatial context via OSM/H3, and a
neighbourhood-suitability comparison feature. Independent review (pulling the real
GitHub repo, not trusting self-reported summaries) found the architecture excellent
— but only ~30% aligned with what the problem statement actually asked for. The
core ask — *why* is a location polluted, not just *what* the number will be — was
explicitly disclaimed in the code. There was no satellite data, no frontend, and
the "multi-agent" system, on inspection, was keyword-matched routing, not genuine
autonomous orchestration.

### 2.2 The strategic pivot

Rather than bolt attribution onto the existing station-centric forecaster, the
project was rebuilt around a different thesis: **model where pollution sources are,
use real wind conditions to reason about how pollution physically moves, and use
real ground stations only to correct that physical estimate — not generate it from
scratch.** This is a deliberately simplified version of how real operational
systems (CAMS, Google's Environmental Insights Explorer) work: a physical prior
corrected by sparse real observations. The alternative — full Gaussian-plume
atmospheric physics — was explicitly rejected as over-engineering: it would need
real per-source emission-rate data that doesn't exist as reliable public data for
Indian cities, and would look more "scientific" while resting on the same amount of
real evidence.

### 2.3 The verification discipline

Every substantial change in this project — whether written by a human or a coding
agent — was independently re-verified: cloning the actual repo, running the actual
test suite, and in many cases hand-computing real numbers from raw data rather than
trusting a summary. This wasn't ceremony. It caught, among others:

- A **gitignore blind spot** that recurred **five separate times** across
  different milestones — a newly-created required file sitting inside a
  blanket-ignored directory, silently never committed, leaving a test suite that
  passed locally while the live API would crash on a fresh clone.
- A **statistics bug** in a self-generated diagnostic report: a headline finding
  ("target volatility explains why the model underperforms," claimed 0.94
  correlation) was computed from the wrong slice of data. Recomputed correctly,
  the correlation dropped to 0.14 — the finding was wrong, and only caught by
  independent recomputation.
- A **frontend data-fabrication system**: a request interceptor that, on any
  backend failure, silently substituted fully fabricated data (including a
  hexagon literally named "Okhla Phase II" — a real Delhi neighbourhood, in a
  Bengaluru-only app) behind a spoofed HTTP 200 status, indistinguishable from a
  real response to any calling component.
- A **hardcoded UI panel** showing frozen "45% Construction / 30% Traffic" values
  regardless of which real hexagon was selected, sitting directly beside genuinely
  live PM2.5 data.
- A **sign/direction bug** in a vectorized bearing-calculation rewrite that, if
  wrong, would have silently inverted the entire attribution engine's directional
  logic — caught by manually re-deriving the trigonometry, not by trusting that
  the rewrite's own tests passed.
- A **one-character typo** in a Google Earth Engine dataset path
  (`COPERNICUS/S5P/OFFL_L3_NO2` vs the correct `COPERNICUS/S5P/OFFL/L3_NO2`) that
  silently broke all Sentinel-5P NO2 ingestion until directly diagnosed.
- **Two parallel enforcement-priority systems** left in the codebase
  simultaneously — an old 6-station heuristic and the new hexagon-based real
  engine — with the LLM copilot silently able to call either one, causing
  identical, location-blind answers regardless of what was actually asked.

The throughline: this project treats "the tests pass" and "the coding agent said
it's done" as claims to verify, never as proof.

---

## Part 3 — System Architecture

### 3.1 The six layers

```
External data sources (CPCB, Open-Meteo, FIRMS, Sentinel-5P, OSM)
        ↓
Ingestion & feature store (station registry, H3 hexagon grid)
        ↓
Forecast, attribution & fusion (LightGBM, wind-weighted attribution)
        ↓
Enforcement priority scoring (exposure × magnitude × actionability)
        ↓
Orchestration layer (deterministic router + opt-in agentic reasoning)
        ↓
FastAPI backend + React frontend(s)
```

### 3.2 The one non-negotiable rule

**Never fabricate a value when real data is missing.** Every service in this
project reports an explicit "unavailable," "stale," or "estimated" status rather
than silently substituting a plausible-looking number. This rule exists because it
was violated once (the frontend interceptor above) and fixing it required ripping
out and rebuilding a meaningful part of the frontend's data layer. It is now the
single most enforced invariant across every new feature, including Citizen Mode's
`aqiIsEstimated`/`rentIsEstimated` flags.

---

## Part 4 — Data Layer

| Source | What it provides | Real / Verified Status |
|---|---|---|
| **CPCB/KSPCB station CSVs** | PM2.5, PM10, NO2, temperature, humidity, wind speed/direction at 12 physical Bengaluru stations, 15-min resolution | ✅ Real, ingested |
| **Open-Meteo** | Forecast weather (wind speed/direction, temperature), 72h horizon, one city-centre point | ✅ Real, ingested |
| **NASA FIRMS (VIIRS satellite)** | Fire/burning detection points with Fire Radiative Power, per H3 hexagon | ✅ Confirmed live — `source_status: live_provider` independently verified against the real NASA API; zero detections observed is a genuine, plausible "no fires today" result, not a broken integration |
| **Sentinel-5P NO2 (Google Earth Engine)** | Satellite NO2 column density, a real traffic/industrial proxy | ✅ Fixed and confirmed — was broken by a one-character asset-path typo (`OFFL_L3_NO2` vs `OFFL/L3_NO2`); also had a severe performance bug (a per-hexagon `.getInfo()` loop, ~10,146 individual network calls) that was rewritten into a single batched `reduceRegions()` call |
| **OpenStreetMap** | Road density, land-use fractions, industrial/construction facility counts, hospital/school/elderly-care ("vulnerability") POI density, green-space fraction | ✅ Real, ingested, columns confirmed present in `hexagon_features.parquet` |
| **MagicBricks rental listings** (`rent_dataset_generator/`) | 12,951 real rental listings: rent, locality, BHK, property type, furnishing, lat/lon | ✅ Real, independently verified row-for-row against its own documentation (median rent ₹50,000, 97.19% lat/lon coverage, 1,497 raw locality strings) |

### 4.1 The station capability model

Not every station can support every feature. Rather than silently failing or
excluding a station, each of the 12 registered stations carries three explicit
fields: `forecast_eligible`, `available_pollutants`, and
`pm25_forecast_coverage_status` (`complete` / `insufficient_pm25_history` /
`pm25_sensor_unavailable`).

**9 of 12 stations are forecast-eligible.** Two of the remaining three
(`cpcb_city_railway`, `cpcb_saneguravahalli`) have a permanently dead PM2.5 sensor
but genuinely excellent NO2/PM10 data — used for attribution and geospatial
context, never for PM2.5 forecasting. The third
(`cpcb_kadabesanahalli`) has PM2.5 data too gap-riddled for reliable 24h-ahead
forecasting, served as a stale "last known reading" advisory instead.

---

## Part 5 — Forecasting Layer

A single LightGBM model trained across all 9 forecast-eligible stations combined
(not one model per station). Station identity is encoded two ways: a one-hot dummy
per station (found to be nearly useless on its own — the model barely used it), and
**interaction features** — 5 specific predictors (`no2_lag_1h`, `no2_lag_24h`,
`pm25_roll_std_24h`, `hour_sin`, `temperature_c`) multiplied against each station's
dummy, letting the model learn genuinely different relationships per station. This
was added after diagnosing (and, on first attempt, mis-diagnosing due to a stats
bug that was independently caught and corrected) that LightGBM was losing to a
naive "persistence" baseline at 4 of 6 originally-served stations. Fixing the
interaction features flipped one station from a loss to a win and substantially
improved the worst performer.

**Persistence is always computed alongside**, and whichever model actually
performs better on a given station's held-out test data is the one served —
tracked explicitly as `model_selected_for_serving`. Some stations are genuinely
served by persistence, not LightGBM, and the API discloses this honestly.

Three newly-added stations (`btmlayout`, `kasturinagar`, `rvce_mailasandra`) were
folded into the retrained model but never received the same underperformance
diagnosis the original four got — this remains an open item.

**Known gap:** forecast horizon is 24h only. 72h (named in the problem statement)
was never built.

---

## Part 6 — Geospatial Layer

H3 hexagon grid, resolution 9 (~174m across, ~9,991 hexagons covering Bengaluru).
Every hexagon carries real OSM-derived features:
`road_density_m_per_sq_m`, `industrial_fraction`, `commercial_fraction`,
`residential_fraction`, `green_space_fraction`, `construction_feature_count`,
`industrial_facility_count`, `vulnerability_feature_count`,
`vulnerability_feature_density_per_sq_km` (hospitals/schools/elderly-care combined
into one POI-density signal). Every station additionally carries the same class of
context at station-level granularity via a separate, earlier-built pipeline.

---

## Part 7 — The Attribution Engine

`compute_attribution_for_hexagon()` answers: *given the wind right now, which
nearby hexagons are physically upwind, and what's their pollution-source profile?*

```
weight = max(0, cosine_similarity(bearing_to_target, wind_blowing_toward_direction))
         × (1 / distance)
         × source_hexagon's traffic/industrial/construction/burning density
```

Every candidate source hexagon within a 3km radius contributes a weighted amount
per category (traffic, industrial, construction, burning); contributions are
summed and normalized to a percentage breakdown. Traffic/industrial density draws
on real OSM + Sentinel-5P NO2; burning draws on real FIRMS detections; construction
on OSM tags.

**This is explicitly a simplified directional-weighting proxy, not full
atmospheric physics** — a deliberate, documented trade-off, not a limitation
hidden from the design.

**Calm-wind handling:** below 1 km/h, directional weighting is mathematically
meaningless, so the engine falls back to pure inverse-distance weighting and marks
the response `method: "calm_fallback"` instead of `"wind_weighted"` — meant to be
visible in the UI, not just the API, so directional confidence is never overstated.

**The meteorological convention correctness** (wind direction is reported as
"blowing FROM," requiring a +180° correction before comparing to a bearing) was
independently re-derived and confirmed correct during a vectorization rewrite — the
one place a silent sign error would have inverted the entire engine without
necessarily failing any test.

**Performance:** originally an O(n²) computation using Python-level `.iterrows()`
loops (two separate ones — haversine distance and bearing calculation, in
different functions), taking upward of 20+ seconds for the full city grid.
Vectorized with NumPy array operations; the real, measured HTTP-path latency
(2,000-hexagon default) is **~3 seconds**.

---

## Part 8 — The Fusion Layer

Bridges "9 real PM2.5 readings" to "a continuous estimate across ~9,991 hexagons."
At each real station, a residual (actual reading minus what the attribution-derived
baseline predicts) is computed using attribution-profile similarity to other
stations as a proxy for "should behave alike," then spread to nearby hexagons via
inverse-distance weighting. Result: `fused_pm25` per hexagon — the
attribution-informed baseline, corrected toward reality wherever a real station is
near.

---

## Part 9 — Enforcement Priority System

A decomposed, explainable score, never a black-box number:

```
priority_score = exposure_weight × attributable_magnitude × actionability_weight
```

- **Exposure weight**: real vulnerability-POI density (hospitals/schools/elderly
  care) near the hexagon — or, when that specific artifact is unavailable, an
  honestly-disclosed `residential_fraction` proxy (`exposure_data_source` field
  always states which was used).
- **Attributable magnitude**: fused PM2.5 multiplied only by the *enforceable*
  attribution share — industrial, construction, burning. **Traffic is
  deliberately excluded** from this term entirely; a purely traffic-attributed
  hexagon scores zero here regardless of exposure, because diffuse traffic isn't
  something an inspector can be sent to fix.
- **Actionability weight**: industrial/construction/burning weighted high
  (permitted, inspectable, stoppable); traffic weighted near zero.

**Known duplicate-system issue:** an older, pre-hexagon 6-station heuristic
priority system (`inspection_priority_service.py`) still exists in the codebase
alongside the real one (`enforcement_priority_service.py`), and was found to still
be reachable by the LLM copilot's tool registry — causing identical, query-blind
answers ("Jayanagar 5th Block is the top priority") regardless of what location
was actually asked about. Diagnosed; fix (removing the old tool from the LLM's
registry) was in progress as of the last verified state.

---

## Part 10 — Orchestration and Copilot Layer

### 10.1 Nine deterministic agents

`backend/app/agents/`: `forecast_evidence_agent`, `enforcement_planning_agent`,
`citizen_advisory_agent`, `city_briefing_agent`, `policy_guidance_agent`,
`spatial_context_agent`, `spatial_intelligence_agent`,
`neighbourhood_decision_agent`, `travel_readiness_agent`. Each is dispatched by
plain substring keyword matching against 11 fixed intents in `orchestrator.py` —
no model, no API call, fully offline-capable for the common case.

### 10.2 The opt-in agentic path

`dynamic_planning_agent.py` runs a genuine LangGraph `StateGraph` — at each step,
an LLM (Groq) decides `call_tool` or `final_answer` based on everything gathered
so far, bounded by a max-step cap and duplicate-call detection. This is real,
autonomous multi-step reasoning, not a hardcoded sequence, and directly answers the
problem statement's "Multi-Agent AI Systems" suggested technology. It was
deliberately made **opt-in** (a "Deep Reasoning Mode" toggle, plus automatic
escalation only for genuinely ambiguous/compound queries) after an earlier,
unscoped change had made it the silent default for every query the moment an LLM
key existed — reverted specifically because unpredictable multi-second latency on
every query is a worse live-demo experience than a fast, honest deterministic
answer for the common case.

### 10.3 Known reliability gaps in this layer

- The Groq client originally had no request timeout (defaulting to 600 seconds) —
  fixed, capped at 15 seconds.
- Malformed LLM decision JSON originally crashed the graph with an unhandled
  `KeyError` instead of degrading gracefully — fixed.
- The LLM-unreachable fallback (`_grounded_fallback()`) **ignores the actual query
  text entirely** and doesn't disclose that it's a degraded response — this is the
  root cause of the "identical answer every time" symptom observed in testing, and
  was still open as of the last verified state, pending confirmation of whether the
  Groq key/quota itself was also a contributing factor.
- `tool_resolve_location` exists in the tool registry (free-text place-name
  resolution) but reliable, consistent use of it by the planner is unconfirmed.

---

## Part 11 — Frontend

### 11.1 Design system

Dark-mode, Apple Human Interface Guidelines-inspired: clarity over decoration,
deference to data, 44×44pt minimum tap targets, visible feedback on every
interaction. Black background (`#000000`), dark-charcoal cards (`#1C1C1E`), an
iOS-matching brand palette (blue `#0A84FF`, red `#ff453a`, orange `#FF9F0A`, green
`#34C759`), Inter for UI text, JetBrains Mono specifically for numeric data.

### 11.2 The four pages (main `frontend/` app)

- **Map** — city-wide hexagon grid via Google Maps + `h3-js`, source attribution
  and fused PM2.5 per hexagon, with `wind_weighted` vs `calm_fallback` meant to be
  visually distinguished.
- **Enforcement** — full ranked priority list with the decomposed
  exposure/magnitude/actionability breakdown always visible.
- **Copilot** — natural-language query interface with the deterministic/deep-
  reasoning toggle.
- **Neighbourhoods** — citizen-facing locality comparison; **still contains
  hardcoded example data** (Koramangala/Indiranagar/HSR Layout with fabricated
  scores) behind otherwise-real loading/error states — a known, not-yet-fixed
  instance of the same fabrication pattern already removed elsewhere.

### 11.3 A serious, real fabrication bug that was found and removed

`axiosClient.ts` originally contained a request interceptor that, on any backend
failure, silently substituted fabricated data (stations, enforcement priorities,
fire detections, NO2 density, a fake analytics dashboard, even fake copilot chat
history) behind a spoofed HTTP 200 response — completely indistinguishable from a
real response to any calling component, with only a `console.warn()` as any trace.
This was found, confirmed precisely (including the "Okhla Phase II" Delhi-in-
Bengaluru detail), and fully removed; `mockData.ts` is now quarantined to a
clearly-marked dev-only path with zero production imports.

### 11.4 A real structural problem: two separate frontend apps

`citizen mode frontend/` (Google AI Studio-generated) is a **completely separate,
standalone Vite project** — its own `package.json`, build, and navigation — sitting
alongside the main `frontend/` app, with a **space in its directory name**. It has
no shared navigation, routing, or design-token connection to the main City
Admin/Map/Enforcement/Copilot app. This needs to be merged into the main frontend
before final submission; treated as a known, deferred task, not yet fixed.

---

## Part 12 — Citizen Mode

### 12.1 The vision

Extends AQI Sentinel beyond monitoring into answering: *"Which Bengaluru
neighbourhood should I live in, given my budget, health, family, and commute?"*
Every locality gets a feature vector (AQI, rent, hospital/school/park scores,
metro distance, noise, construction activity); every user gets a matching profile
(budget, family size, health conditions, workplace location, commute tolerance,
priorities); a radius pre-filter narrows candidates before a transparent, weighted
matching engine ranks them — every recommendation shows *why*, never a bare score.

### 12.2 Real data secured

A genuine 12,951-row MagicBricks rental dataset (independently verified — median
rent ₹50,000, 97.19% real lat/lon coverage), obtained deliberately *without*
relying on live scraping of commercial portals as an ongoing production pipeline —
consistent with this project's preference for defensible, citable data sources
over fragile or ToS-risky ones for anything demo-critical.

### 12.3 Frontend built, contract locked

A real, working React app (separate from the main frontend, see 11.4) with its
exact TypeScript contract already implemented: `CitizenProfile` in,
`NeighbourhoodMatch[]` out via `POST /citizen/matches`, including the
`aqiIsEstimated`/`rentIsEstimated` honesty flags built directly into the type
system, and a properly-quarantined mock-data file that never silently substitutes
for a real API failure.

### 12.4 Backend — architecture decided, implementation in progress

An offline-build + fast-online-matching architecture: locality canonicalization
(1,497 raw locality strings collapse to ~25-40 well-supported canonical
localities), per-locality environmental aggregation reusing the real, already-
verified attribution/fusion/OSM data (explicitly avoiding a new Google Places API
dependency where OSM data already covers the need), rent aggregation from the real
dataset with honest per-BHK confidence thresholds, and a transparent weighted
matching engine whose scoring logic is documented, not hidden.

---

## Part 13 — Twilio WhatsApp and Multi-Language (planned)

**WhatsApp, reactive-first:** a citizen texts a question; the webhook reuses
`run_orchestrator()` directly — the same pipeline the web copilot already uses.
Because Twilio retries a webhook that doesn't acknowledge fast enough, the design
deliberately separates immediate acknowledgment from asynchronous reply via a
FastAPI `BackgroundTask`, avoiding the same class of timeout risk this project
already hit once with the copilot itself. Proactive push is intentionally
sequenced second, and will need a phone-number-to-profile registry that doesn't
exist yet.

**Multi-language:** `language` is already wired end-to-end through the request
schema, router, and orchestrator, with `en`/`hi`/`kn` already declared supported —
the only missing piece is the actual Groq translation call on the final answer
text, plus a real language selector in the web copilot UI (the API field is
already there, currently hardcoded to `'en'` on the frontend).

---

## Part 14 — Complete Current Issue Inventory

**Actively affecting the demo:**
1. LLM-unreachable fallback ignores query text and doesn't disclose degradation.
2. Two parallel enforcement-priority systems, old one still reachable by the LLM.
3. Reverse geocoding incomplete — some hexagons show real names, others show raw
   grid IDs.
4. Enforcement detail panel possibly not refreshing per-hexagon-click.

**Diagnosed, fix scoped, not yet fully confirmed pushed/verified:**
5. Dormant silent-coordinate-fallback risk in `geospatialService.ts`.
6. `NeighbourhoodsPage.tsx` hardcoded example data.
7. Wrong-tool-selection reliability once Groq is confirmed working.

**Known, honest data-completeness gaps (not bugs):**
8. Sentinel-5P now fixed (typo + performance rewrite) — re-verification of live
   NO2 signal reaching attribution output still pending as of the last check.
9. Three newer stations (`btmlayout`, `kasturinagar`, `rvce_mailasandra`) never
   individually diagnosed for underperformance the way the original four were.
10. `cpcb_bapujinagar`'s evaluation remains statistically unreliable (37 test rows).

**Maintenance, low urgency:**
11. Six date-fragile tests (hardcoded fixture dates vs. real `datetime.now()`).
12. No comprehensive one-time gitignore/artifact audit has ever been done — each
    of the five known instances was caught reactively, individually.
13. The "Deep Reasoning Mode" toggle can silently misrepresent which path is
    actually taken for unsupported queries.

**Structural, deferred:**
14. Two separate frontend applications need merging into one.
15. No database — not a cause of any diagnosed bug, but a real scalability gap.

**Planned, not yet built:**
16. Citizen Mode backend (architecture decided, implementation prompt issued).
17. Twilio WhatsApp integration.
18. Web copilot multi-language translation layer.
19. 72-hour forecast horizon.
20. Multi-city dashboard (deliberately out of scope).

---

## Part 15 — Problem Statement Alignment, Final Summary

| Requirement | Status |
|---|---|
| Source attribution | ✅ Built, real, physically-motivated |
| Hyperlocal forecast grid | ✅ Built (finer than the 1km ask); ❌ still 24h horizon only |
| Enforcement intelligence | ✅ Built, decomposed, explainable (pending the duplicate-system fix) |
| Satellite imagery | ✅ FIRMS and Sentinel-5P both genuinely integrated and fixed |
| Citizen health advisories | ✅ Exist in English; ❌ regional-language delivery not yet built |
| Multi-Agent AI Systems | ✅ Genuinely agentic (LangGraph), correctly scoped as opt-in |
| Working prototype | ✅ Built, real pages, consistent design system; ⚠️ split across two apps |
| Multi-city dashboard | Deliberately out of scope (illustrative-only per the problem statement) |

---

## Part 16 — Repository Layout

```
et-ai/
├── backend/app/           FastAPI application
│   ├── agents/             9 deterministic agents + LangGraph dynamic planner
│   ├── routers/             HTTP endpoint definitions
│   ├── schemas/             Pydantic request/response models
│   └── services/           Core business logic (forecast, attribution, fusion,
│                           enforcement, commute, weather, geospatial)
├── pipeline/               Offline data ingestion and feature-building scripts
│   ├── firms_ingestion.py, sentinel5p_ingestion.py, cpcb_csv_adapter.py
│   ├── build_geospatial_context.py, build_hexagon_features.py
│   └── station_registry.py, station_capability computation
├── ml/                     LightGBM training, evaluation, diagnostics
├── data/                   Raw and processed data artifacts
├── frontend/               Main React app (Map, Enforcement, Copilot,
│                           Neighbourhoods)
├── citizen mode frontend/  SEPARATE standalone React app (Citizen Mode) —
│                           needs merging into frontend/ before submission
├── rent_dataset_generator/ Real MagicBricks rental scrape + output data
├── knowledge_base/         Curated policy/health documents (WHO, CPCB, Karnataka)
└── tests/                  Full backend test suite
```

---

*This document reflects the verified state of the project as of the most recent
independently-confirmed check. Anything marked "in progress" or "planned" should be
re-verified before being treated as done — that discipline is the reason this
project is in the shape it's in.*