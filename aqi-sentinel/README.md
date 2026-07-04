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

## Future Phases

Later milestones can add OpenAQ observations, ERA5 weather, OSM road and land-use signals, H3 spatial grids, map views, inspection-priority agents, evidence attribution, and multilingual public health advisories.
