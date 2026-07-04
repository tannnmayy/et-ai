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
