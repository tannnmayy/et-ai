# AQI Sentinel
''
AQI Sentinel is an AI-powered urban air-quality intelligence platform for Bengaluru, India. Milestone 1 builds the local forecasting foundation: synthetic station data, leakage-safe features, a 24-hour PM2.5 model, a persistence baseline, evaluation artifacts, and a FastAPI endpoint for latest station forecasts.

This milestone intentionally does not include Docker, databases, frontend maps, paid APIs, external API keys, agents, or LLM calls.

## Architecture

```text
Synthetic station generator
        |
        v
data/raw/bengaluru_hourly_air_quality_demo.csv
        |
        v
Leakage-safe feature builder
        |
        v
data/processed/station_features_24h.parquet
        |
        +--> Persistence baseline: prediction(t+24h) = PM2.5(t)
        |
        +--> LightGBM 24-hour PM2.5 regressor
        |
        v
ml/artifacts/
        |
        v
FastAPI /forecast/stations
```

## Folder Structure

```text
aqi-sentinel/
|-- backend/app/
|   |-- main.py
|   |-- config.py
|   |-- schemas/
|   |-- routers/
|   `-- services/
|-- pipeline/
|   |-- generate_demo_data.py
|   |-- build_features.py
|   `-- storage.py
|-- ml/
|   |-- common.py
|   |-- train_persistence_baseline.py
|   |-- train_lightgbm.py
|   |-- evaluate.py
|   `-- artifacts/
|-- data/
|   |-- raw/
|   `-- processed/
|-- tests/
|-- requirements.txt
|-- .env.example
|-- .gitignore
`-- README.md
```

## Prerequisites

- Windows PowerShell
- Python 3.11

## Commands

Run these from the repository root:

```powershell
cd E:\1ETAI\aqi-sentinel
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Files already committed (present on clone, nothing to do)

- Station registry, pipeline code, schemas, ML model binaries, and geospatial context files are tracked and ready to use after `pip install`.

## Required build steps (must run in this order)

Some artifacts are too large or too machine-specific to commit. Run these steps to create them locally:

1. **Generate synthetic demo data** (if no real CPCB data is available):
   ```powershell
   python -m pipeline.generate_demo_data
   ```

2. **Build geospatial context** (required for station-level geospatial endpoints):
   ```powershell
   python -m pipeline.build_geospatial_context
   ```

3. **Build leakage-safe features**:
   ```powershell
   python -m pipeline.build_features
   ```

4. **Train the persistence baseline**:
   ```powershell
   python -m ml.train_persistence_baseline
   ```

5. **Train LightGBM**:
   ```powershell
   python -m ml.train_lightgbm
   ```

6. **Evaluate both models** on the same chronological test set:
   ```powershell
   python -m ml.evaluate
   ```

## Run tests

```powershell
pytest
```

Start FastAPI:

```powershell
uvicorn backend.app.main:app --reload
```

Open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/forecast/stations`
- `http://127.0.0.1:8000/docs`

## Why the Persistence Baseline Matters

The persistence baseline is the simplest defensible 24-hour forecast: PM2.5 tomorrow equals PM2.5 now. LightGBM is useful only if it beats that baseline on the same held-out test rows. This prevents a flashy model from being accepted without evidence.

## Why Chronological Splitting Is Used

Air-quality forecasting is a time-series problem. Random splitting would let future patterns leak into training and overstate model quality. The project splits by unique timestamp: first 70% for training, next 15% for validation, final 15% for testing. All stations share the same time boundaries.

## Leakage Controls

- Lag features use positive shifts within each station.
- Rolling PM2.5 features shift by 1 hour before rolling, so the current value is excluded.
- The target is `pm25` shifted by -24 hours within each station.
- Rows with incomplete features or target values are dropped.
- Tests verify target alignment and rolling-feature leakage prevention.

## Serving Fallback

Evaluation writes `ml/artifacts/evaluation_metrics.json` with the selected serving model. If LightGBM has lower test RMSE than persistence, the API serves LightGBM. If LightGBM is not selected, cannot load, or cannot predict, the API automatically returns persistence forecasts with `forecast_engine = "persistence_fallback"`.

If processed data or evaluation artifacts do not exist, the API returns a clear 503 response telling you which pipeline step is missing.

## Milestone 2A - OpenAQ Real Data Audit

This phase discovers and audits real OpenAQ v3 monitoring data for Bengaluru. It answers whether OpenAQ has enough PM2.5 history, continuity, and pollutant completeness to support a later real-data forecasting milestone.

This phase does not retrain the model, replace synthetic data, change the serving API, add ERA5/CDS weather, use OSM/H3, build a frontend, add agents, or introduce a database.

### Secure Setup

Create a local `.env` from `.env.example`:

```powershell
cd E:\1ETAI\aqi-sentinel
Copy-Item .env.example .env
notepad .env
```

Set these variables locally:

```text
OPENAQ_API_KEY=
OPENAQ_BASE_URL=https://api.openaq.org/v3
OPENAQ_TIMEOUT_SECONDS=30
OPENAQ_MAX_RETRIES=4
OPENAQ_LOOKBACK_DAYS=365
```

Never commit `.env`. API keys are read from environment variables only and sent through the documented OpenAQ `X-API-Key` request header.

### Audit Commands

Run the default 365-day audit:

```powershell
E:\1ETAI\.venv\Scripts\python.exe -m pipeline.audit_openaq_bengaluru --lookback-days 365
```

Run a shorter audit and bypass cached raw responses:

```powershell
E:\1ETAI\.venv\Scripts\python.exe -m pipeline.audit_openaq_bengaluru --lookback-days 180 --refresh
```

Run all tests, including Milestone 1:

```powershell
E:\1ETAI\.venv\Scripts\python.exe -m pytest
```

### Generated Files

```text
data/raw/openaq/*.json
data/processed/bengaluru_openaq_station_hourly.parquet
data/reports/openaq_bengaluru_locations.csv
data/reports/openaq_bengaluru_sensors.csv
data/reports/openaq_bengaluru_station_audit.csv
data/reports/openaq_bengaluru_station_audit.md
```

Raw JSON responses are cached by resource, run timestamp, and page. Cached files are reused unless `--refresh` is passed. Raw saved payloads contain response bodies only, never request headers or authorization details.

### Classification Rules

Recommended:
- covered days >= 180
- PM2.5 completeness >= 70%
- longest continuous PM2.5 run >= 30 days

Usable with caveats:
- covered days >= 90
- PM2.5 completeness >= 50%
- longest continuous PM2.5 run >= 7 days

Not suitable:
- anything below those thresholds

No model retraining happens here because this phase only audits whether real station data is suitable. Real-data training belongs in Milestone 2B after station selection is defensible.

### Troubleshooting

API key missing: create `.env` from `.env.example` and set `OPENAQ_API_KEY`.

HTTP 429/rate limit: rerun later, reduce lookback, or rely on cached raw responses. The client uses bounded retries and respects `Retry-After`.

No Bengaluru stations returned: verify the bounding box, API key, and current OpenAQ coverage. OpenAQ may not include all official station data.

Insufficient historical coverage: try a longer lookback or import official CPCB CSV data for comparison.

API schema mismatch: parsing is isolated in `pipeline/openaq_client.py` and `pipeline/audit_openaq_bengaluru.py`; update those adapters if OpenAQ changes field names.

## Future Phases

Later milestones will use audited OpenAQ observations for real-data training, then add ERA5 weather, OSM road and land-use signals, H3 spatial grids, map views, inspection-priority intelligence, evidence attribution, and multilingual public-health advisories.

## Milestone 3A - Forecast Intelligence and Deterministic Decision Support

This milestone adds a deterministic intelligence layer on top of the existing forecast system. It converts validated station forecasts into structured evidence, confidence assessments, inspection rankings, citizen advisories, and city briefings. All outputs are fully deterministic, offline-testable, and require no LLM, agent, MCP, RAG/vector databases, external APIs, or paid services.

### Architecture

```text
Existing forecast system (Milestones 1-2C)
            |
            v
  artifact_adapter.py (single source of truth)
            |
            +--> forecast_evidence_service.py
            +--> confidence_service.py
            +--> inspection_priority_service.py
            +--> citizen_advisory_service.py
            +--> city_briefing_service.py
            |
            v
  routers/intelligence.py (FastAPI endpoints)
```

### Artifact Adapter (`backend/app/services/artifact_adapter.py`)

The artifact adapter is the intelligence layer's single source of truth. Every Milestone 3A service reads existing model/data/quality artifacts only through this adapter. No other service independently parses model artifacts, processed parquet files, quality reports, or evaluation files.

**Adapter methods and their artifact sources:**

| Method | Reads From |
|--------|-----------|
| `get_station_snapshot(station_id)` | `evaluation_metrics.json`, `persistence_baseline.json`, `station_manifest.json`, per-station features parquet |
| `list_station_snapshots(city)` | Same as above, iterates all stations |
| `get_city_station_snapshots(city)` | Same as above, filters by city |
| `get_station_recent_observations(station_id, lookback_hours)` | Per-station features parquet (pm25, pm10, no2, temperature_c, relative_humidity, rainfall_mm columns) |
| `get_station_quality(station_id)` | `station_manifest.json` quality_details |
| `get_station_evaluation(station_id)` | `evaluation_metrics.json` per_station + `persistence_baseline.json` per_station |
| `get_lightgbm_explanation_context(station_id)` | Per-station features parquet (lag values, rolling stats, temporal features, weather context) |

**Domain errors:** `UnsupportedCityError`, `UnknownStationError`, `MissingArtifactError`, `NoValidForecastError`

### SHAP Decision

SHAP is not installed in the current environment. The project-wide explanation mode is **`model_context_fallback`**. For LightGBM forecasts, recent PM2.5 trends, lag values, rolling statistics, temporal context, and available pollutant/weather data are returned as transparent model context (not causal drivers). For persistence forecasts, the explanation method is **`exact_24h_reference`**. This decision is consistent across all stations.

### Forecast Evidence (`/intelligence/stations/{station_id}/evidence`)

Returns structured evidence explaining each station's forecast including:
- `explanation_method`: "exact_24h_reference" (persistence) or "model_context_fallback" (LightGBM)
- `expected_change_pm25`: predicted minus latest observed PM2.5
- `expected_change_direction`: improving / stable / worsening / unavailable
- `model_validation_summary`: selected engine, test rows, RMSE improvement
- `evidence_items`: structured for/against items with factors and weights
- `caveats`: data quality and model uncertainty warnings
- Persistence evidence explicitly states it was selected because it outperformed LightGBM on held-out data

### Forecast Confidence (`/intelligence/stations/{station_id}/confidence`)

Data-reliability confidence scoring (start at 100):
- **Freshness penalty:** >3h: -20, >12h: -35 (highest applicable only)
- **Completeness penalty:** <75%: -15, <50%: -25 (highest applicable only)
- **Gap penalty:** >6h: -20, >24h: -30 (highest applicable only)
- **Quality penalty:** "Usable with caveats": -15, "Not suitable": -40
- **No penalty for persistence selection**
- Levels: High (>=80), Medium (55-79), Low (25-54), Unavailable (<25)

### Inspection Priority (`/intelligence/cities/{city}/inspection-priorities`)

Deterministic municipal inspection ranking scoring 0-100:
- **Forecast severity (max 45):** Good=0, Satisfactory=8, Moderate=18, Poor=30, Very Poor=40, Severe=45
- **Worsening (max 20):** >=40ug/m3: 20, >=25: 15, >=10: 8
- **Recent elevated PM2.5 (max 15):** >=150: 15, >=100: 10, >=60: 5
- **Confidence adjustment:** High=+10, Medium=+5, Low=-10, Unavailable=-20
- **Quality adjustment:** "Usable with caveats"=-5, "Not suitable"=-20
- Priority levels: Critical (>=70), High (50-69), Moderate (30-49), Watch (<30)

Every result includes a mandatory `investigation_disclaimer`:
> "Suggested inspection focus is an investigation hypothesis based on forecast and station signals. It is not proof that a specific source caused the pollution."

Station-specific inspection focus (e.g., Peenya: industrial compliance; Silk Board: traffic congestion) is configured centrally in `config.py`.

### Citizen Advisory (`/intelligence/stations/{station_id}/advisory`)

Deterministic health advisory with 6 profiles: general, child, elderly, respiratory, outdoor_worker, school.

Languages: English (mandatory), Hindi, Kannada. Hindi and Kannada currently fall back to English with `translation_fallback = true`.

Each response includes: `headline`, `recommendations`, `caution_note`, `data_quality_note`, `confidence_level`, and `medical_disclaimer` ("This is general air-quality guidance, not medical advice.").

### City Briefing (`/intelligence/cities/{city}/briefing`)

Deterministic city operational briefing including:
- `city_risk_level`: uses configured precedence (Severe > Very Poor > Poor > Moderate > Good > Unavailable)
- `stations_by_risk_category`, `stations_by_confidence_level`
- `lightgbm_selected_count`, `persistence_selected_count`
- `top_priorities`: ranked station list
- `operational_recommendations`: prioritization, verification, communication actions
- `data_limitations`: low-confidence stations, persistence stations, stale observations, coverage disclaimer
- `station_summaries`: per-station snapshot with engine, confidence, quality

### City Registry (Multi-City Ready)

`SUPPORTED_CITIES` in `config.py` currently contains only Bengaluru. All services accept a `city` parameter. Unsupported cities return 404: "No validated station dataset is registered for this city."

### New Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /intelligence/stations/{station_id}/evidence` | Forecast evidence and explanation |
| `GET /intelligence/stations/{station_id}/confidence` | Forecast confidence score |
| `GET /intelligence/stations/{station_id}/advisory?profile=general&language=en` | Citizen health advisory |
| `GET /intelligence/cities/{city}/inspection-priorities?top_k=5` | Inspection priority ranking |
| `GET /intelligence/cities/{city}/briefing` | City operational briefing |
| `GET /intelligence/inspection-priorities?top_k=5` | Bengaluru convenience alias |
| `GET /intelligence/city-briefing` | Bengaluru convenience alias |

### Safety Limitations

- No LLM, LangGraph, MCP, RAG, external APIs, or paid services are used.
- No persistence confidence penalty exists.
- Every inspection result contains the required investigation disclaimer.
- Advisory language never claims causation.
- All thresholds are centralized in `config.py`.
- Existing synthetic and real forecast endpoints are unchanged.

### Commands

Run the full test suite:

```powershell
cd E:\1ETAI
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -q
```

Start the API:

```powershell
cd E:\1ETAI
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload
```

Open Swagger docs: `http://127.0.0.1:8000/docs`

Test intelligence endpoints:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/intelligence/stations/cpcb_hebbal/evidence
Invoke-RestMethod http://127.0.0.1:8000/intelligence/stations/cpcb_hebbal/confidence
Invoke-RestMethod "http://127.0.0.1:8000/intelligence/stations/cpcb_hebbal/advisory?profile=elderly&language=en"
Invoke-RestMethod "http://127.0.0.1:8000/intelligence/cities/bengaluru/inspection-priorities?top_k=5"
Invoke-RestMethod http://127.0.0.1:8000/intelligence/cities/bengaluru/briefing
```

## Milestone 3B — Agentic Intelligence Layer

This milestone adds a small, credible multi-agent system on top of the deterministic Milestone 3A services. The agent layer makes AQI Sentinel visibly agentic while remaining evidence-first, testable, and safe.

### Architecture

```text
User Query
     |
     v
Orchestrator (intent detection + routing)
     |
     +--> Forecast Evidence Agent
     |      - tool_get_forecast_evidence()
     |      - tool_get_forecast_confidence()
     |      - fallback_renderer (default)
     |
     +--> Enforcement Planning Agent
     |      - tool_get_inspection_priorities()
     |      - tool_get_forecast_evidence() / confidence()
     |      - investigation disclaimer enforced
     |
     +--> Citizen Advisory Agent
     |      - tool_get_citizen_advisory()
     |      - tool_get_forecast_confidence()
     |      - medical disclaimer enforced
     |
     +--> City Briefing Agent
            - tool_get_city_briefing()
            - tool_get_inspection_priorities()
            - data limitations enforced
```

### Five-Role Architecture

| Role | Agent | Purpose |
|------|-------|---------|
| Orchestrator | `orchestrator.py` | Intent detection, input validation, routing, response validation |
| Forecast Evidence | `forecast_evidence_agent.py` | Forecast explanation and confidence |
| Enforcement Planning | `enforcement_planning_agent.py` | Ranked inspection priorities |
| Citizen Advisory | `citizen_advisory_agent.py` | Health guidance by profile/language |
| City Briefing | `city_briefing_agent.py` | City operational summary |

### Deterministic Intent Routing

Intent detection uses explicit keyword rules and route-based delegation — no LLM required. Supported intents:

- `station_explanation` — "why is Peenya forecast to worsen?"
- `station_confidence` — "how reliable is Silk Board's forecast?"
- `inspection_plan` — "what are the inspection priorities?"
- `citizen_guidance` — "is it safe to go outside?"
- `city_briefing` — "give me a Bengaluru briefing"
- `unsupported` — fallback for unrecognized queries

### Direct Python Tool Calls

All agents call existing Milestone 3A services directly (not via HTTP):

| Tool | Service Function | Source |
|------|-----------------|--------|
| `tool_get_forecast_evidence(station_id)` | `get_forecast_evidence()` | `forecast_evidence_service.py` |
| `tool_get_forecast_confidence(station_id)` | `get_forecast_confidence()` | `confidence_service.py` |
| `tool_get_inspection_priorities(city, top_k)` | `get_inspection_priorities()` | `inspection_priority_service.py` |
| `tool_get_citizen_advisory(station_id, profile, language)` | `get_citizen_advisory()` | `citizen_advisory_service.py` |
| `tool_get_city_briefing(city)` | `get_city_briefing()` | `city_briefing_service.py` |

### LLM Abstraction

`backend/app/agents/llm_provider.py` provides a provider-agnostic abstraction:

- **Deterministic mode** (default): No LLM call. Uses `fallback_renderer.py` for natural-language responses from structured data.
- **Hosted LLM mode** (optional): Reads config from environment variables only. No keys are hardcoded.
  - `AQI_SENTINEL_LLM_API_KEY` — API key (Groq)
  - `AQI_SENTINEL_LLM_MODEL` — model name

If no key is present, deterministic mode is used automatically. If an LLM call fails, the system falls back to deterministic rendering.

The LLM may only summarize structured tool output. It never receives unrestricted file, shell, database, or network access.

### Deterministic Fallback (Default Offline Mode)

`backend/app/agents/fallback_renderer.py` generates polished but strictly bounded answers from tool results:

- **Station explanation**: station name, PM2.5, risk category, engine, explanation method, expected change, confidence, caveats. Never invents causes.
- **Inspection plan**: ranked stations with scores/risk/forecast, investigation focus, mandatory disclaimer.
- **Citizen guidance**: advisory headline, recommendations, confidence note, medical disclaimer.
- **City briefing**: city risk, station coverage, top priorities, data limitations.

### Audit Trail

Every request returns an audit trail with:

- `request_id` — unique request identifier
- `timestamp` — UTC timestamp
- `detected_intent` — identified intent
- `selected_agent` — routed agent name
- `tools_called` — list of tool names, arguments, and success/failure
- `llm_mode` — `deterministic`, `hosted`, or `fallback`
- `fallback_used` — whether fallback rendering was triggered
- `warnings` — validation warnings

Chain-of-thought or hidden reasoning is never exposed.

### Guardrails

Every agent response retains:
- `forecast_engine` when a forecast is discussed
- `confidence_level` when a forecast is discussed
- `data-quality caveat` where present
- Investigation disclaimer for enforcement outputs
- Medical disclaimer for citizen outputs
- Data limitations for city outputs

The system never:
- Changes predicted PM2.5 values
- Changes RMSE/model selection
- Invents a forecast
- States source attribution as fact
- Gives diagnosis or medical treatment
- Claims citywide coverage beyond available stations
- Hides language fallback
- Omits a required disclaimer

A response validator checks required fields before returning output. If validation fails, the deterministic fallback renderer is used.

### New Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/copilot/query` | Natural language query to the AQI copilot |
| GET | `/copilot/stations/{station_id}/explain` | Forecast explanation for a station |
| GET | `/copilot/stations/{station_id}/guidance` | Citizen health guidance for a station |
| GET | `/copilot/cities/{city}/inspection-plan` | Inspection plan for a city |
| GET | `/copilot/cities/{city}/briefing` | City briefing |

### Files Added

```
backend/app/agents/
├── __init__.py
├── state.py                 # Typed state object
├── llm_provider.py          # LLM provider abstraction
├── fallback_renderer.py     # Deterministic response rendering
├── tools.py                 # Tool layer (direct service calls)
├── audit.py                 # Audit trail
├── orchestrator.py          # Intent routing + orchestration
├── forecast_evidence_agent.py
├── enforcement_planning_agent.py
├── citizen_advisory_agent.py
└── city_briefing_agent.py

backend/app/schemas/copilot.py   # Copilot Pydantic models
backend/app/routers/copilot.py   # Copilot FastAPI routes
tests/test_copilot.py            # Comprehensive agent tests
```

### Safety Limitations

- No LLM, LangGraph, MCP, RAG, external APIs, or paid services are required for default operation.
- No forecasting values are generated by an LLM.
- No external API is required for default operation.
- No MCP, RAG, frontend, Docker, database, deployment, or paid service was added.
- LLM, when enabled, only summarizes structured tool output.
- All existing forecasting and intelligence services are unchanged semantically.

### Commands

Run the full test suite (Milestones 1-3B, zero failures):

```powershell
cd E:\1ETAI
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -q
```

Start the API:

```powershell
cd E:\1ETAI
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload
```

Test copilot endpoints:

```powershell
# POST query
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/copilot/query -Body '{"query":"Why is Peenya a priority?","station_id":"cpcb_peenya","city":"bengaluru"}' -ContentType "application/json" | ConvertTo-Json -Depth 10

# Station explanation
Invoke-RestMethod http://127.0.0.1:8000/copilot/stations/cpcb_peenya/explain | ConvertTo-Json -Depth 10

# Station guidance
Invoke-RestMethod "http://127.0.0.1:8000/copilot/stations/cpcb_hebbal/guidance?profile=elderly&language=en" | ConvertTo-Json -Depth 10

# City inspection plan
Invoke-RestMethod "http://127.0.0.1:8000/copilot/cities/bengaluru/inspection-plan?top_k=3" | ConvertTo-Json -Depth 10

# City briefing
Invoke-RestMethod http://127.0.0.1:8000/copilot/cities/bengaluru/briefing | ConvertTo-Json -Depth 10
```

### Enabling Optional Hosted LLM Mode

Set environment variables (do not commit secrets):

```powershell
$env:AQI_SENTINEL_LLM_API_KEY = "your-api-key"
$env:AQI_SENTINEL_LLM_MODEL = "openai/gpt-oss-120b"
```

Or add to a `.env` file (never committed):

```text
AQI_SENTINEL_LLM_API_KEY=your-api-key
AQI_SENTINEL_LLM_MODEL=openai/gpt-oss-120b
```

If no key is present, the system operates in fully offline deterministic mode.

## Milestone 3C — Grounded Policy and Health Knowledge Service

This milestone adds a local, curated policy and health knowledge service. It retrieves relevant passages from authoritative source documents and returns structured citations for agents and APIs.

This is a **grounded retrieval system**, not a general web-search system and not an LLM knowledge substitute. The system never invents citations, never cites documents that were not retrieved, and never claims an official source supports a statement if it does not.

### Why a Curated Local Corpus

Rather than searching the web at runtime, AQI Sentinel maintains a deliberately small, curated local corpus of official documents. This ensures:
- All citations are traceable to source organization and title.
- No external web calls or paid APIs at runtime.
- Documents must be manually approved by the developer before they become citable.
- Demo documents (used for testing) are clearly marked and never appear in user-facing citations.

### Document Eligibility Rules

Every document has two eligibility flags:
- `demo_only: true/false` — Demo documents are used only for pipeline and test validation.
- `allowed_for_citation: true/false` — Documents must have this set to `true` to appear in user-facing results.

A document is retrievable for citation only when both conditions are met:
- `allowed_for_citation = true`
- `demo_only = false`

### Semantic vs Lexical Retrieval

Two retrieval modes are supported:

1. **Semantic mode** (`KNOWLEDGE_RETRIEVAL_MODE=semantic`):
   - Uses `sentence-transformers/all-MiniLM-L6-v2` for embedding.
   - Requires the model to be cached locally (downloaded once on first index build).
   - Cosine similarity ranking.

2. **Lexical fallback mode** (`KNOWLEDGE_RETRIEVAL_MODE=lexical`, **default**):
   - Uses scikit-learn TF-IDF vectorization.
   - Works fully offline with no model download.
   - Cosine similarity ranking on TF-IDF vectors.

The project defaults to lexical mode for immediate offline operation. To switch to semantic mode, set `KNOWLEDGE_RETRIEVAL_MODE=semantic` in `backend/app/config.py`.

### Adding a Real Official Document

1. Place the document file (`.pdf`, `.txt`, or `.md`) in `knowledge_base/raw/`.
2. Register it in `knowledge_base/manifests/corpus_manifest.json` with complete metadata.
3. Set `demo_only: false` and `allowed_for_citation: true`.
4. Compute the SHA-256 hash and set the `sha256` field.
5. Rebuild the index:

```powershell
cd E:\1ETAI
python -m pipeline.build_knowledge_index
```

### Required Manifest Metadata

```json
{
  "document_id": "unique_id",
  "title": "Full Document Title",
  "organization": "Publishing Organization",
  "source_type": "policy | health_guidance | standard | advisory",
  "jurisdiction": "India | Karnataka | Bengaluru | Global",
  "publication_date": "2023-01-15",
  "source_url": "https://example.org/doc",
  "local_path": "filename.pdf",
  "sha256": "64-character-hex-hash",
  "language": "en",
  "demo_only": false,
  "allowed_for_citation": true,
  "notes": "Optional notes"
}
```

### Index Build Command

```powershell
cd E:\1ETAI
python -m pipeline.build_knowledge_index
```

Artifacts created:
```
knowledge_base/processed/chunks.jsonl        # All chunks with metadata
knowledge_base/indexes/index_metadata.json    # Index metadata
knowledge_base/indexes/tfidf_vectorizer.joblib # TF-IDF vectorizer (lexical mode)
knowledge_base/indexes/tfidf_matrix.joblib    # TF-IDF matrix (lexical mode)
knowledge_base/indexes/chunk_data.joblib      # Chunk data for retrieval
knowledge_base/reports/index_report.json      # Structured report
knowledge_base/reports/index_report.md        # Human-readable report
```

### Retrieval Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/guidance/search?q={query}&top_k=3` | Search for policy/health guidance |
| GET | `/guidance/documents` | List citation-eligible documents |
| GET | `/guidance/status` | Knowledge base index status |

### Agent Integration

Agents now call `tool_search_policy_guidance()` to retrieve supporting guidance:

| Agent | When Guidance Is Retrieved | Behavior When None Found |
|-------|---------------------------|--------------------------|
| Citizen Advisory | Builds a focused query from risk category + profile | States no authoritative source was found; preserves advisory + disclaimer |
| Enforcement Planning | Builds query from investigation focus (dust/traffic/industrial) | No change to inspection plan; disclaimer remains |
| City Briefing | Only when city risk is Poor or worse | Data limitations and coverage disclaimer remain |

A new **Policy Guidance Agent** handles the `policy_guidance` intent for standalone queries like "What does CPCB say about outdoor activity?"

### Safety Limitations

- No web scraping or external runtime calls were added.
- Demo-only documents cannot appear as official citations.
- No LLM generates citations.
- Retrieved sources support guidance but do not prove station-level pollution causes.
- Existing forecasting, intelligence, and agent behavior remains semantically unchanged.
- This milestone does not yet add weather, traffic, routing, MCP, frontend, or external API calls.

### New Files

```
knowledge_base/
├── raw/                           # Place official documents here
│   ├── README.md
│   ├── demo_cpcb_aqi_guidelines.md
│   ├── demo_who_air_quality.md
│   ├── demo_ncap_programme.md
│   └── demo_only_sample.md
├── processed/
│   └── chunks.jsonl
├── manifests/
│   └── corpus_manifest.json
├── indexes/
│   ├── index_metadata.json
│   ├── tfidf_vectorizer.joblib
│   ├── tfidf_matrix.joblib
│   └── chunk_data.joblib
├── reports/
│   ├── index_report.json
│   └── index_report.md
└── schemas/
    └── source_metadata.schema.json

pipeline/build_knowledge_index.py           # Index build pipeline
backend/app/services/policy_guidance_service.py  # Retrieval service
backend/app/schemas/guidance.py             # Pydantic models
backend/app/routers/guidance.py             # FastAPI endpoints
backend/app/agents/policy_guidance_agent.py # Policy guidance agent
tests/test_knowledge_base.py               # 40+ tests
```

### Commands

Run full test suite (all milestones, zero failures):
```powershell
cd E:\1ETAI
python -m pytest tests/ -q
```

Start FastAPI:
```powershell
cd E:\1ETAI
uvicorn backend.app.main:app --reload
```

Test guidance endpoints:
```powershell
# Index status
Invoke-RestMethod http://127.0.0.1:8000/guidance/status | ConvertTo-Json -Depth 3

# Search guidance
Invoke-RestMethod "http://127.0.0.1:8000/guidance/search?q=air+quality+guidelines&top_k=3" | ConvertTo-Json -Depth 10

# List eligible documents
Invoke-RestMethod http://127.0.0.1:8000/guidance/documents | ConvertTo-Json -Depth 3
```

## Milestone 3C — Activated with Authoritative Documents

The knowledge service now contains three citation-eligible authoritative documents alongside the existing demo documents.

### Authoritative Sources

| Document | Organization | Intended Use | Limitation |
|----------|-------------|-------------|------------|
| WHO Global Air Quality Guidelines 2021 | World Health Organization | Health context, exposure reduction, PM2.5/PM10 guidelines | Does not replace Indian AQI/CPCB thresholds |
| State Action Plan on Air Pollution for Karnataka 2022 | EMPRI / Government of Karnataka | City context, sector analysis, investigation hypotheses | Does not prove station-level causality |
| Pollution Control Acts, Rules and Notifications, 7th Edition 2021 | CPCB / MoEFCC | General regulatory context, legal framework | Not legal advice; no compliance verdicts |

### Source Guardrails

Every citation returned by the system enforces source-specific guardrails at the service layer:

- **WHO content**: Health-evidence context only. Must not change Indian AQI categories or thresholds. `permitted_for_indian_aqi_thresholds: false`
- **Karnataka SAPAP-K**: Context and investigation hypotheses. Must not claim source attribution or causality. `permitted_for_source_attribution: false`
- **CPCB Law Series**: General regulatory context only. Must not provide legal advice, compliance verdicts, or penalty predictions. `legal_context_only: true`

### Adding a Future Document

1. Place the file (`.pdf`, `.txt`, or `.md`) in `knowledge_base/raw/`
2. Register it in `knowledge_base/manifests/corpus_manifest.json` with metadata
3. Set `demo_only: false` and `allowed_for_citation: true` for citation-eligible documents
4. Set appropriate guardrail fields (see schema)
5. Compute SHA-256 hash and set the `sha256` field
6. Rebuild the index:

```powershell
cd E:\1ETAI
python -m pipeline.build_knowledge_index
```

### Build Command

```powershell
cd E:\1ETAI
python -m pipeline.build_knowledge_index
```

## Milestone 4A — Weather Enrichment + Travel Readiness

### What It Does

Adds a real weather forecast layer (via Open-Meteo) and a deterministic travel-readiness assessment that combines weather conditions with existing city-level air-quality data. The system answers questions like "What will Bengaluru weather be like tomorrow?" and "Is tomorrow suitable for outdoor travel?"

### Provider

- **Open-Meteo** (free, no API key required, no paid tier).
- No Google Maps, Google Traffic, OpenWeatherMap, or any other paid API.
- Coordinates: Bengaluru (12.9716°N, 77.5946°E).
- Forecast horizon: next 72 hours of hourly data.

### Weather Fields

| Field | Unit |
|-------|------|
| Temperature | °C |
| Apparent temperature | °C |
| Relative humidity | % |
| Precipitation probability | % |
| Precipitation, rain, showers | mm |
| Snowfall | cm |
| Weather code (WMO) | integer |
| Wind speed, wind gusts | km/h |

### Cache and Fallback

- Local JSON file cache (`cache/weather/`).
- TTL: 30 minutes for fresh cache.
- Stale cache usable up to 6 hours if provider is unavailable.
- Cache metadata records age, source, freshness.
- Provider failures return stale cache with an explicit warning, or a controlled unavailable response.

### Travel-Readiness Categories

1. **Suitable** — Low weather risk + good/satisfactory AQI.
2. **Suitable with precautions** — Mild weather or moderate AQI concerns.
3. **Caution advised** — Elevated weather risk or poor AQI.
4. **Avoid non-essential outdoor travel** — Severe weather or very-poor/severe AQI.

Decision is based on a transparent 4×6 matrix configured in `config.py`.

### Supported Profiles

- `general`, `elderly`, `child`, `outdoor_worker`, `school`, `two_wheeler`

Each profile receives deterministic, rule-based precautions (e.g., rain gear for two-wheeler, heat caution for outdoor worker).

### Scope Limitations

- No live traffic, route ETA, road closures, or public-transit disruptions.
- Air-quality assessment reflects monitored-station forecasts, not full citywide coverage.
- Weather forecasts may change; check again closer to departure.

### API Endpoints

```
GET /weather/forecast?city=bengaluru&horizon_hours=72&refresh=false
GET /weather/summary?city=bengaluru&period=tomorrow&refresh=false
GET /travel/readiness?city=bengaluru&profile=general&period=tomorrow&refresh_weather=false
```

### Example Commands

```powershell
cd E:\1ETAI

# Weather forecast
curl "http://127.0.0.1:8000/weather/forecast?city=bengaluru"

# Weather summary for tomorrow
curl "http://127.0.0.1:8000/weather/summary?city=bengaluru&period=tomorrow"

# Travel readiness
curl "http://127.0.0.1:8000/travel/readiness?city=bengaluru&profile=general&period=tomorrow"

# Elderly profile
curl "http://127.0.0.1:8000/travel/readiness?city=bengaluru&profile=elderly&period=tomorrow"
```

### Copilot Integration

The deterministic copilot recognises weather and travel intents:

- "What will Bengaluru weather be like tomorrow?" → `weather_forecast`
- "Is tomorrow good for outdoor travel?" → `travel_readiness`
- "Should an elderly person travel outdoors tomorrow?" → `travel_readiness`
- "Should I ride a two-wheeler tomorrow morning?" → `travel_readiness`

No LLM key is required. LLMs may only summarise structured output; they cannot alter weather values, AQI values, readiness categories, limitations, or warnings.

### How to Refresh Weather Cache

Pass `refresh=true` to bypass cache:

```powershell
curl "http://127.0.0.1:8000/weather/forecast?city=bengaluru&refresh=true"
```

### How to Run Weather/Travel Tests

```powershell
cd E:\1ETAI
python -m pytest tests/test_weather.py -v
python -m pytest tests/test_travel_readiness.py -v
python -m pytest tests/test_copilot_weather_travel.py -v
```

### Test Commands

Run knowledge base tests:
```powershell
cd E:\1ETAI
python -m pytest tests/test_knowledge_base.py -v
```

Run full test suite:
```powershell
cd E:\1ETAI
python -m pytest tests/ -q
```

### Honest Limitations and Future Extension Possibilities

- **City support**: Only Bengaluru. Adding cities requires config updates and provider support.
- **Traffic/transit**: No live traffic, route ETA, road closures, or public-transit disruptions. This is a city-level outdoor readiness feature, not navigation.
- **AQI coverage**: Reflects monitored-station forecasts only. Does not represent complete citywide coverage.
- **Weather accuracy**: Weather forecasts may change; check again closer to departure.
- **No causal claims**: Travel readiness is a bounded assessment of known weather and AQI signals. It does not claim route safety, road safety, or health safety.
- **Medical disclaimer**: Applied for elderly, child, school, and outdoor-worker profiles. This is general guidance, not medical advice.
- **No real-time weather observations**: Weather data is from Open-Meteo forecast models unless explicitly returned and labeled as observed data.

## Milestone 5A — Geospatial Evidence Foundation for AQI Sentinel

### What It Does

Builds a bounded, reproducible geospatial evidence layer using OpenStreetMap and H3 hexagonal spatial indexing. It provides station-area context for enforcement hypotheses and future multimodal forecasting, without claiming causality.

### Data Sources

| Source | Purpose | API Key Required |
|--------|---------|-----------------|
| OpenStreetMap via OSMnx | Roads, land-use, green spaces, construction, industrial/facility context | No |
| H3 (Uber) | Hexagonal spatial indexing at resolution 9 (~0.1 km² hexagons) | No |
| Station registry | Canonical station coordinates from OpenAQ location audit | No |

**No Google Maps, Google Air Quality, or any Google API is used in this milestone.**

### Spatial Feature Principles

- Spatial features are **contextual evidence and investigation signals only**.
- The system never claims a specific industry, construction site, road, facility, or mapped object caused pollution.
- The system never claims a legal violation, emission breach, or compliance failure.
- Every enforcement-facing response includes the existing investigation disclaimer.
- Every response discloses that OpenStreetMap coverage/tags can be incomplete or outdated.
- The system distinguishes "mapped nearby context" from "verified registered emission source."

### Files Added/Changed

```
NEW:  data/reference/bengaluru_station_registry.csv
NEW:  pipeline/geospatial/__init__.py
NEW:  pipeline/geospatial/h3_utils.py
NEW:  pipeline/geospatial/osm_client.py
NEW:  pipeline/build_geospatial_context.py
NEW:  backend/app/schemas/geospatial.py
NEW:  backend/app/services/geospatial_evidence_service.py
NEW:  backend/app/routers/geospatial.py
NEW:  backend/app/agents/spatial_context_agent.py
NEW:  tests/test_geospatial.py
MOD:  requirements.txt
MOD:  backend/app/config.py
MOD:  backend/app/main.py
MOD:  backend/app/services/artifact_adapter.py
MOD:  backend/app/services/inspection_priority_service.py
MOD:  backend/app/services/city_briefing_service.py
MOD:  backend/app/agents/state.py
MOD:  backend/app/agents/tools.py
MOD:  backend/app/agents/orchestrator.py
```

### Dependencies Added and Compatibility

| Package | Version | Notes |
|---------|---------|-------|
| h3 | 4.5.0 | H3 core library for hexagonal spatial indexing |
| osmnx | 2.1.0 | OSM data acquisition and caching |
| geopandas | 1.1.4 | GeoDataFrame support (pulled by OSMnx) |
| shapely | 2.1.2 | Geometry operations (pulled by OSMnx) |
| pyproj | 3.7.2 | CRS transformations for metric area/distance |

All dependencies are pinned conservatively and compatible with Python 3.11.

### Station Registry

`data/reference/bengaluru_station_registry.csv` contains 6 supported Bengaluru stations:

| station_id | display_name | latitude | longitude | source |
|-----------|-------------|----------|-----------|--------|
| cpcb_hebbal | Hebbal Bengaluru - KSPCB | 13.029152 | 77.585901 | OpenAQ location_id 6984 |
| cpcb_hombegowda | Hombegowda Nagar - KSPCB | 12.938539 | 77.590100 | OpenAQ location_id 6983 |
| cpcb_jayanagar5 | Jayanagar 5th Block - KSPCB | 12.920984 | 77.584908 | OpenAQ location_id 6973 |
| cpcb_silkboard | Silk Board - KSPCB | 12.917348 | 77.622813 | OpenAQ location_id 6975 |
| cpcb_peenya | Peenya - CPCB | 13.027020 | 77.494094 | OpenAQ location_id 5607 |
| cpcb_bapujinagar | Bapuji Nagar - KSPCB | 12.951913 | 77.539784 | OpenAQ location_id 6974 |

**Validation:** Station IDs are unique, all 6 match the pipeline station registry, all coordinates are within Bengaluru bounds, and every station maps to a valid H3 cell.

### H3 Resolution

**Resolution 9** (~0.1 km² hexagons, ~174 m edge length) is selected for neighbourhood-scale analysis. This is balanced between spatial granularity and computational efficiency for 6 stations.

### OSM Acquisition Strategy

**Acquisition:** OSM data is downloaded only through an explicit CLI build command (`python -m pipeline.geospatial.osm_client`), never at FastAPI request time.

**Cache Behaviour:**
- Raw snapshots are cached under `data/raw/geospatial/osm/` by category.
- Valid snapshots (TTL: 30 days) are reused by default.
- `--refresh` flag bypasses cache and re-downloads.
- Network failure with no cache raises a clear error.
- Network failure with stale cache falls back to cached data with a warning.
- Categories: `roads`, `landuse`, `green_spaces`, `construction`, `industrial_facility`.

### Feature Definitions and Null/Coverage Semantics

#### Road / Mobility Proxies

| Feature | Definition | Null When |
|---------|-----------|-----------|
| `total_road_length_m_within_radius` | Sum length of mapped roads within station context radius | No roads intersect buffer |
| `major_road_length_m_within_radius` | Sum length of major roads (motorway/trunk/primary/secondary) | No major roads intersect |
| `road_density_m_per_sq_km` | Total road length / buffer area | Buffer area is zero |
| `nearest_major_road_distance_m` | Distance to nearest mapped major road | No major roads found |
| `road_feature_coverage_status` | `'complete'` or reason for absence | Always populated |

#### Land-Use Context

| Feature | Definition | Null When |
|---------|-----------|-----------|
| `industrial_landuse_fraction` | Industrial area / total mapped land-use area | No land-use features mapped |
| `commercial_landuse_fraction` | Commercial area / total mapped land-use area | No land-use features mapped |
| `residential_landuse_fraction` | Residential area / total mapped land-use area | No land-use features mapped |
| `green_space_fraction` | Green area (parks, forests, etc.) / total mapped area | No green features mapped |
| `landuse_feature_coverage_status` | `'complete'` or reason for absence | Always populated |

#### Investigation Context

| Feature | Definition | Null When |
|---------|-----------|-----------|
| `construction_feature_count_within_radius` | Count of OSM construction-tagged features | No construction features |
| `mapped_industrial_or_facility_count_within_radius` | Count of OSM industrial/facility features | No industrial features |
| `nearest_mapped_industrial_or_facility_distance_m` | Distance to nearest industrial feature | No industrial features |
| `investigation_context_coverage_status` | `'complete'` or reason for absence | Always populated |

**Key rule:** No mapped object → `None` value + coverage status starting with `no_`. Never silently substitute zero.

### Generated Artifacts and Reports

| Artifact | Path | Description |
|----------|------|-------------|
| Parquet | `data/processed/geospatial/station_geospatial_context.parquet` | Per-station feature records |
| Metadata | `data/processed/geospatial/geospatial_build_metadata.json` | Build version, H3 config, OSM snapshot |
| CSV report | `data/reports/geospatial/geospatial_coverage_report.csv` | Per-station coverage status |
| MD report | `data/reports/geospatial/geospatial_coverage_report.md` | Human-readable coverage report with feature definitions and disclaimers |

### API Endpoints

```
GET /geospatial/stations/{station_id}/context?city=bengaluru
GET /geospatial/cities/{city}/coverage
```

**Example response** (station context):
```json
{
  "station_id": "cpcb_peenya",
  "city": "bengaluru",
  "h3_cell": "8...",
  "road_context": {
    "road_density_m_per_sq_km": 12345.67,
    "nearest_major_road_distance_m": 150.0,
    "road_feature_coverage_status": "complete"
  },
  "landuse_context": {
    "industrial_landuse_fraction": 0.35,
    "green_space_fraction": 0.05,
    "landuse_feature_coverage_status": "complete"
  },
  "investigation_context": {
    "construction_feature_count_within_radius": 3,
    "mapped_industrial_or_facility_count_within_radius": 5,
    "investigation_context_coverage_status": "complete"
  },
  "data_completeness_score": 1.0,
  "limitations": [
    "OpenStreetMap data is community-maintained and may be incomplete...",
    "Spatial features are contextual evidence and investigation signals only..."
  ]
}
```

### Intelligence Integration

**Inspection priority output** (`/intelligence/cities/{city}/inspection-priorities`) includes an optional `spatial_investigation_context` section for each station. This section is explanatory only:
- Road-density context
- Land-use context
- Mapped construction/facility context
- Coverage quality
- Limitations

**The presence of spatial context does not alter priority scores or ranking order.**

**City briefing** (`/intelligence/cities/{city}/briefing`) may include a compact `spatial_coverage_note` field when geospatial artifacts are available.

### Copilot Integration

A new `spatial_context` intent and `spatial_context_agent` handle queries like:
- "What spatial context exists around Peenya?"
- "Why is road density relevant near this station?"
- "Are there mapped construction or industrial-context features near Hebbal?"
- "What is the geospatial coverage for Bengaluru stations?"

The agent calls the geospatial evidence service through a direct tool wrapper (`tool_get_geospatial_context` / `tool_get_geospatial_city_coverage`), never via HTTP.

All responses include:
- OSM completeness disclaimer
- Non-causality disclaimer
- Coverage quality and limitations

### Build Sequence

Run these commands from the repository root:

```powershell
# 1. Install geospatial dependencies (first time only)
pip install -r requirements.txt

# 2. Fetch OSM data for Bengaluru (requires internet, first build)
python -m pipeline.geospatial.osm_client

# 3. Build geospatial context artifacts
python -m pipeline.build_geospatial_context

# 4. Run tests (all offline, no network calls)
python -m pytest tests/ -q

# 5. Start the API
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

> **Note:** Step 2 requires internet access for the initial OSM download. Steps 3–5 use local cached data only.

### Test Commands

```powershell
# Run all geospatial tests
python -m pytest tests/test_geospatial.py -v

# Run full test suite (376+ tests, all offline)
python -m pytest tests/ -q
```

### Manual Validation

After building artifacts and starting the API:

```powershell
# Station geospatial context
Invoke-RestMethod http://127.0.0.1:8010/geospatial/stations/cpcb_peenya/context | ConvertTo-Json -Depth 10

# City coverage summary
Invoke-RestMethod http://127.0.0.1:8010/geospatial/cities/bengaluru/coverage | ConvertTo-Json -Depth 5

# Inspection priorities with spatial context
Invoke-RestMethod "http://127.0.0.1:8010/intelligence/cities/bengaluru/inspection-priorities?top_k=3" | ConvertTo-Json -Depth 10

# City briefing with spatial coverage note
Invoke-RestMethod http://127.0.0.1:8010/intelligence/cities/bengaluru/briefing | ConvertTo-Json -Depth 5
```

### What This Milestone Does Not Do

- Does not integrate Google Maps APIs or Google keys.
- Does not add a frontend, Docker, database, or MCP server.
- Does not use satellite imagery, FIRMS, or live traffic.
- Does not retrain forecast models, alter confidence scoring, or change selected model engines.
- Does not claim a specific industry, construction site, road, or facility caused pollution.
- Does not claim legal violations, emission breaches, or compliance failures.
- Does not provide citywide hyperlocal predictions.
- Does not claim satellite, live traffic, industrial registry, or source-attribution capabilities.
- Does not claim that mapped facilities are verified registered emission sources.
- Does not claim that construction tags are a permit registry.
- Does not claim road density is live traffic.
- Does not claim spatial context proves pollution causality.
- Does not make external calls during import, service execution, API requests, or tests (after OSM snapshot is cached).
- Does not commit raw massive OSM downloads (`.gitignore` protects `data/raw/geospatial/`).
- Does not modify existing forecast, evidence, or confidence scoring semantics.
- Does not touch or expose Google API keys.

## Milestone 5B — Map-Ready Spatial Intelligence and Neighbourhood Comparison

### Architecture

Milestone 5B adds an optional Google Maps-backed layer for geocoding, route computation, spatial intelligence aggregation, and neighbourhood suitability comparison. No Google API keys are required for application startup or existing endpoints.

```
User Query / API Request
        |
        v
  +-----+------+       +------------------+
  |  Copilot   | ----> | Intent Detection |
  +-----+------+       +------------------+
        |                      |
        v                      v
  +-----+------+       +------------------+
  | Agent      | ----> | Service Layer    |
  +-----+------+       +------------------+
        |                      |
        v                      v
  +-----+------+       +------------------+
  | Fallback   |       | Google Maps      |
  | Renderer   |       | Client (httpx)   |
  +------------+       +------------------+
                              |
                              v
                        Geocoding / Routes API
```

### New Files

| File | Purpose |
|------|---------|
| `backend/app/schemas/maps.py` | Geocode, route, and location request/response schemas |
| `backend/app/schemas/neighbourhood.py` | Neighbourhood comparison and spatial intelligence schemas |
| `backend/app/services/google_maps_client.py` | Isolated HTTP client for Geocoding, Routes, and Places APIs |
| `backend/app/services/location_service.py` | Location resolution (direct coordinates or geocoding) |
| `backend/app/services/commute_service.py` | Commute burden calculation between locations |
| `backend/app/services/spatial_intelligence_service.py` | Station and location intelligence aggregation |
| `backend/app/services/neighbourhood_suitability_service.py` | Multi-candidate suitability scoring |
| `backend/app/routers/maps.py` | `/maps/geocode`, `/maps/route` endpoints |
| `backend/app/routers/neighbourhoods.py` | `/neighbourhoods/compare`, `/spatial-intelligence/*` endpoints |
| `backend/app/agents/spatial_intelligence_agent.py` | Copilot agent for spatial intelligence queries |
| `backend/app/agents/neighbourhood_decision_agent.py` | Copilot agent for neighbourhood comparison queries |

### Required Google Cloud APIs

For the **server API key** (backend):
- **Geocoding API** — resolve addresses to coordinates
- **Routes API** (or Directions API) — compute routes between locations

For the **browser API key** (future frontend):
- **Maps JavaScript API** — display maps
- **Places API (New)** — place search and autocomplete

### Environment Variables

Create a `.env` file in the project root:

```env
# Google Maps API Keys (Milestone 5B)
# Browser key (for future frontend): Maps JavaScript API, Places API (New)
GOOGLE_MAPS_BROWSER_API_KEY=
# Server key (for backend): Geocoding API, Routes API
GOOGLE_MAPS_SERVER_API_KEY=
```

Both keys are optional. If `GOOGLE_MAPS_SERVER_API_KEY` is not set:
- Direct coordinate inputs still work
- Free-text address lookup returns an unavailable status (not fabricated coordinates)
- Route computation returns unavailable
- Neighbourhood comparison proceeds with partial assessment

### API Endpoints

#### `GET /maps/geocode?q=...`
Resolves a free-text address to coordinates using Google Geocoding API.

#### `POST /maps/route`
Computes a route between two coordinates. Returns distance, duration, and traffic-aware duration if available.

```json
{
  "origin": {"latitude": 12.97, "longitude": 77.59},
  "destination": {"latitude": 13.02, "longitude": 77.58},
  "travel_mode": "DRIVE"
}
```

#### `POST /neighbourhoods/compare`
Compares 1-3 candidate areas for a person with a workplace and optional school locations.

```json
{
  "candidate_areas": [{"query": "Jayanagar"}, {"query": "HSR Layout"}],
  "workplace": {"query": "Manyata Tech Park"},
  "schools": [{"query": "School A"}],
  "profile": "family_with_children",
  "travel_mode": "DRIVE",
  "period": "tomorrow"
}
```

#### `GET /spatial-intelligence/stations/{station_id}`
Aggregates forecast evidence, confidence, inspection priority, and geospatial context for a station.

#### `POST /spatial-intelligence/location`
Returns nearby monitoring stations and spatial context for an arbitrary address or coordinate.

### Copilot Intents

Two new intents are supported:

- **`spatial_intelligence`** — triggered by keywords like "spatial intelligence", "station intelligence"
- **`neighbourhood_comparison`** — triggered by keywords like "compare", "neighbourhood", "suitability", "where to live"

### Scoring Components

Neighbourhood suitability uses the following configurable weighted components:

| Component | Default Weight | Description |
|-----------|---------------|-------------|
| `air_quality_component` | 0.30 | Based on nearest station proximity |
| `forecast_confidence_component` | 0.10 | Station-level forecast confidence proxy |
| `green_space_proxy_component` | 0.10 | Green space fraction from nearest station OSM context |
| `road_mobility_proxy_component` | 0.10 | Road density from nearest station OSM context |
| `commute_component` | 0.20 | Commute burden score (lower is better) |
| `weather_disruption_component` | 0.10 | Weather risk level |
| `data_coverage_component` | 0.10 | Number of nearby stations |

If Google Maps is unavailable, commute and weather components are marked `available: false` and a partial assessment is returned. The overall score is `null` when minimum required coverage is not met.

### Testing

All 6 new test files are fully offline and use mocked `httpx` responses:

```powershell
python -m pytest tests/test_google_maps_client.py -q
python -m pytest tests/test_location_service.py -q
python -m pytest tests/test_commute_service.py -q
python -m pytest tests/test_neighbourhood_suitability.py -q
python -m pytest tests/test_spatial_intelligence.py -q
python -m pytest tests/test_copilot_spatial_neighbourhood.py -q
```

### Scope Limitations

- Google Maps provides geocoding, route calculation, and future map visualization — it does NOT provide AQI truth, weather truth, satellite evidence, verified emission sources, or causal source attribution.
- No satellite imagery or thermal anomaly processing.
- If traffic-aware routing is unavailable, commute data is appropriately labeled.
- No frontend is included in this milestone.
- No external API calls occur in tests.
- API keys are never logged, printed, returned in responses, or committed to git.
- `.env` is git-ignored; only placeholder variable names are in `.env.example`.

### Manual PowerShell Commands

With server key configured:
```powershell
# Geocode
Invoke-RestMethod "http://127.0.0.1:8010/maps/geocode?q=Jayanagar,Bengaluru" | ConvertTo-Json -Depth 5

# Route
$body = @{origin=@{latitude=12.97;longitude=77.59};destination=@{latitude=13.02;longitude=77.58};travel_mode="DRIVE"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8010/maps/route" -Body $body -ContentType "application/json" | ConvertTo-Json -Depth 5

# Neighbourhood comparison
$body = @{candidate_areas=@(@{query="Jayanagar"},@{query="HSR Layout"});workplace=@{query="Manyata Tech Park"};profile="general";travel_mode="DRIVE"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8010/neighbourhoods/compare" -Body $body -ContentType "application/json" | ConvertTo-Json -Depth 10

# Station intelligence
Invoke-RestMethod "http://127.0.0.1:8010/spatial-intelligence/stations/cpcb_peenya" | ConvertTo-Json -Depth 10

# Location intelligence
$body = @{latitude=12.97;longitude=77.59} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8010/spatial-intelligence/location" -Body $body -ContentType "application/json" | ConvertTo-Json -Depth 5
```

Without server key, geocoding and route endpoints return 503 errors. Direct coordinate inputs and station intelligence still work.
