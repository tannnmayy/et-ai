# AQI Sentinel

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

Generate synthetic data:

```powershell
python -m pipeline.generate_demo_data
```

Build leakage-safe features:

```powershell
python -m pipeline.build_features
```

Train the persistence baseline:

```powershell
python -m ml.train_persistence_baseline
```

Train LightGBM:

```powershell
python -m ml.train_lightgbm
```

Evaluate both models on the same chronological test set:

```powershell
python -m ml.evaluate
```

Run tests:

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
  - `AQI_SENTINEL_LLM_API_KEY` — API key
  - `AQI_SENTINEL_LLM_PROVIDER` — `openai`, `anthropic`, or `google`
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
$env:AQI_SENTINEL_LLM_PROVIDER = "openai"     # openai, anthropic, or google
$env:AQI_SENTINEL_LLM_MODEL = "gpt-4o-mini"
```

Or add to a `.env` file (never committed):

```text
AQI_SENTINEL_LLM_API_KEY=your-api-key
AQI_SENTINEL_LLM_PROVIDER=openai
AQI_SENTINEL_LLM_MODEL=gpt-4o-mini
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
