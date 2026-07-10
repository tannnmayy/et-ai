# AQI Sentinel

**AI-Powered Urban Air Quality Intelligence for Smart City Intervention**

Built for the ET AI Hackathon — Problem Statement 5: *Smart Cities / Environmental Intelligence / Geospatial Analytics / Public Health*

> India's air-quality crisis is not a Delhi problem — it is a national urban crisis, and the data already exists across 900+ monitoring stations. What's missing is the intelligence layer to act on it: knowing *why* a location is polluted right now, *what it will look like tomorrow*, and *where to send an inspector* — not just another dashboard showing a number.

AQI Sentinel is a working answer to that gap for Bengaluru, built as a real, running system rather than a mockup: a FastAPI backend, a physics-informed attribution engine, a dynamic AI agent layer, and a full REST API surface, all backed by real satellite, weather, and monitoring-station data — no synthetic placeholders standing in for the parts that matter.

---

## Why this exists

City administrators today have dashboards. They don't have decisions. A number that says "AQI is 218" tells you the air is bad — it doesn't tell you whether that's construction dust from a site two kilometers upwind, a waste-burning event flagged by satellite twenty minutes ago, or evening traffic that will clear by morning. Without that distinction, there's nothing actionable to do with the number except worry about it.

AQI Sentinel is built around a different question than most air-quality tools ask. Instead of *"what will the number be,"* it asks *"given what we can physically observe right now — wind direction, satellite fire detections, traffic-linked NO2, land use — which sources are plausibly responsible, and what should a city actually do about it."* The forecasting layer still exists and still matters, but it's treated as one input into a larger reasoning system, not the whole product.

---

## What it actually does

### 🔍 Geospatial Source Attribution
For any point in the city, AQI Sentinel computes — in real time, from real wind data — which nearby areas are physically upwind right now, and what they're doing: traffic, industry, construction, or open burning. This isn't a machine-learned correlation between "near a road" and "pollution" — it's a directional, physics-informed calculation using live wind bearing, satellite-detected fires (NASA VIIRS/FIRMS), traffic-linked NO2 column density (Sentinel-5P via Google Earth Engine), and OpenStreetMap land-use data. When wind is too calm to give a directional signal, the system says so explicitly rather than quietly guessing — every attribution result is labeled `wind_weighted` or `calm_fallback`, so nobody mistakes a low-confidence estimate for a confident one.

### 📈 Hyperlocal Forecasting
A LightGBM model forecasts PM2.5 24 hours ahead at each monitored station, with station-specific interaction features so the model actually learns that different neighbourhoods behave differently — not just a single number nudged by a location dummy variable. Critically, a naive "tomorrow looks like today" baseline is tracked alongside it, and whichever one genuinely performs better on real held-out data is what gets served — the system will tell you honestly when persistence beats the model, rather than serving a fancier number that's actually worse.

### 🏙️ City-Wide Fusion
Only a handful of physical monitoring stations exist, but pollution doesn't stop at station boundaries. A fusion layer spreads real station readings across the full city hex-grid (H3, ~174m resolution), correcting the attribution-based estimate toward ground truth wherever a real reading is nearby — turning nine fixed points into a continuous, city-wide air-quality surface.

### 🚔 Enforcement Prioritization
Given a live attribution map, the system ranks locations for inspection priority using a transparent, decomposed formula — actionability (can an inspector actually do something here?) × exposure (how many people are affected?) × magnitude (how bad is it?) — rather than a black-box score. A traffic jam and an unlicensed brick kiln both contribute to pollution, but only one of them is something an inspector can act on today, and the scoring reflects that distinction explicitly.

### 🧭 Neighbourhood Suitability
For anyone comparing where to live, send their kids to school, or commute to work from, the system scores candidate locations across real air quality, land-use, and commute-burden signals — including live Google Maps travel-time integration — with an honest "partial assessment" flag whenever a component's underlying data wasn't available, rather than a false sense of completeness.

### 🤖 Dynamic AI Orchestration
A dynamic planning layer — powered by Groq — chains multiple tools together to answer compound questions a fixed script couldn't: *"why is this area bad right now, and what should the city do about it?"* triggers a real, multi-step reasoning chain (forecast evidence → geospatial context → source attribution → enforcement priority → policy guidance), decided dynamically by the model rather than hardcoded in advance. Every tool call in that chain is logged and auditable — the system can show its work, not just its answer. Simpler, single-intent questions are still handled by a fast, fully deterministic router that works even with no AI model configured at all, so the system never goes offline just because an LLM call fails.

### 🗣️ Multilingual Citizen Guidance
Health advisories and plain-language causal explanations — *"why is the air bad near me"* — are available in English, Hindi, and Kannada, with a built-in fallback to template-based explanations whenever a live model call isn't available, so nobody using the system ever sees a blank response.

---

## What makes this different from a typical hackathon prototype

**It never silently substitutes a fake answer for a missing one.** Across the entire system, every module that could plausibly run out of data — a dead sensor, missing satellite coverage, an unavailable AI model, calm wind with no directional signal — returns an explicit status saying so, rather than quietly interpolating something that looks fine. A city official or a citizen reading a response can always tell the difference between "here's real evidence" and "here's our best guess because the real thing wasn't available."

**Every simplification is a disclosed trade-off, not a hidden one.** Full atmospheric plume-dispersion modelling and full kriging interpolation were deliberately not built — not because they're impossible, but because they'd need emission-inventory data that doesn't reliably exist yet for Indian cities, and a more "sophisticated"-looking model on the same amount of real evidence would just be more confident-sounding, not more correct. Wind-direction weighting and inverse-distance correction were chosen instead, and that choice is documented, not buried.

**It degrades gracefully instead of breaking.** No AI model configured? The deterministic router still answers every standard query. No live weather data? The system flags it and falls back to a template. This isn't an application that only works in the happy path demoed on stage.

---

## Architecture

```
                     ┌─────────────────────────────────────────┐
                     │              Data Sources                │
                     │  CPCB/KSPCB stations · Open-Meteo winds   │
                     │  NASA FIRMS (fire detection, satellite)   │
                     │  Sentinel-5P NO2 (Google Earth Engine)    │
                     │  OpenStreetMap (land use, roads)          │
                     └───────────────────┬───────────────────────┘
                                         │
                     ┌───────────────────▼───────────────────────┐
                     │         Forecasting & Attribution          │
                     │  LightGBM 24h PM2.5 forecast (per station) │
                     │  Wind-weighted source attribution engine   │
                     │  Fusion: station residuals → full hex grid │
                     └───────────────────┬───────────────────────┘
                                         │
                     ┌───────────────────▼───────────────────────┐
                     │          Decision Intelligence              │
                     │  Enforcement priority scoring (actionable)  │
                     │  Neighbourhood suitability (7-component)    │
                     │  Causal explanation generation (multilingual)│
                     └───────────────────┬───────────────────────┘
                                         │
                     ┌───────────────────▼───────────────────────┐
                     │           Agentic Orchestration             │
                     │  Deterministic router (fast, always works)  │
                     │  Dynamic multi-tool planner (Groq-powered)  │
                     │  Full audit trail of every tool call made   │
                     └───────────────────┬───────────────────────┘
                                         │
                     ┌───────────────────▼───────────────────────┐
                     │              FastAPI Service                │
                     │   30+ REST endpoints across 12 routers      │
                     └─────────────────────────────────────────────┘
```

---

## API surface

The backend exposes a full REST API, grouped by capability:

| Area | Prefix | What it covers |
|---|---|---|
| Forecasting | `/forecast` | Station-level and multi-station PM2.5 forecasts, model status |
| Intelligence | `/intelligence` | Combined structured intelligence for a station or location |
| Copilot | `/copilot` | Natural-language query interface — deterministic + dynamic planning |
| Attribution | `/attribution` | Single-hexagon and city-wide source attribution + fusion |
| Guidance | `/guidance` | Grounded health and policy guidance |
| Geospatial | `/geospatial` | OSM/H3 context for any location |
| Neighbourhoods | `/neighbourhoods` | Suitability comparison, grid-wide suitability |
| Weather | `/weather` | Forecast weather, travel-readiness signals |
| Maps | `/maps` | Google Maps-backed geocoding and place lookups |
| Stations | `/stations` | Station registry and metadata |

Interactive API documentation is available at `/docs` once the server is running.

---

## Technology

- **Backend**: FastAPI, Python
- **Forecasting**: LightGBM, scikit-learn, pandas
- **Geospatial**: H3 (Uber's hexagonal grid), OSMnx, GeoPandas, Shapely
- **Satellite data**: NASA FIRMS (VIIRS fire detection), Sentinel-5P TROPOMI (via Google Earth Engine)
- **Weather**: Open-Meteo
- **AI orchestration**: Groq (fast open-weight LLM inference), with a fully deterministic fallback path requiring no AI model at all
- **Maps**: Google Maps JavaScript API, Places API

---

## Getting started

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in your Groq API key and Google Maps API keys in .env

# Build geospatial artifacts (required for enforcement and attribution endpoints)
python pipeline/build_hexagon_features.py

# Run the backend
uvicorn backend.app.main:app --reload

# Run the test suite
python -m pytest -q
```

Visit `http://localhost:8000/docs` for the interactive API explorer.

---

## Judging criteria alignment

| Criteria | Weight | How this project addresses it |
|---|---:|---|
| Innovation | 25% | Physics-informed, wind-weighted source attribution rather than a purely statistical correlation model; a dynamic multi-tool AI planner that reasons across forecasting, attribution, and enforcement rather than a single fixed pipeline |
| Business Impact | 25% | A decomposed, inspectable enforcement-priority score that municipal authorities can act on directly, not just another number to monitor |
| Technical Excellence | 20% | Real satellite and weather data throughout, no synthetic stand-ins for core signals; every component that can fail declares its own failure explicitly instead of masking it |
| Scalability | 15% | City-agnostic attribution and fusion architecture; adding a new city is a data-onboarding problem, not a redesign |
| User Experience | 15% | Multilingual (English, Hindi, Kannada) citizen guidance; graceful degradation everywhere, so the system is never fully unavailable |

---

## Disclaimer

AQI Sentinel is a decision-support and hackathon prototype. Attribution, forecasting, and suitability outputs are estimates built from real but incomplete data sources, and are not a substitute for certified regulatory monitoring or medical advice. Where the underlying data doesn't support a confident answer, the system is designed to say so rather than guess.
# Run the application

Start the API from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

In a second terminal, start the web app:

```powershell
cd frontend
npm run dev
```

Open the URL shown by Vite (normally http://localhost:5173). The frontend proxies `/api` requests to FastAPI automatically. The existing root `.env` browser Maps key is detected for local development; never expose the server Maps key.
