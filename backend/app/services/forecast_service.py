from __future__ import annotations

import json
import logging
from datetime import timezone
from pathlib import Path

import joblib
import pandas as pd
from fastapi import HTTPException

from backend.app.config import get_data_mode, get_project_root
from backend.app.schemas.forecast import (
    ForecastResponse,
    MultiStationForecastResponse,
    MultiStationStationForecast,
    RealHebbalForecastResponse,
    StationForecast,
    StationStatusItem,
    StationStatusResponse,
)
from ml.common import DATASET_REAL_HEBBAL, DATASET_REAL_MULTISTATION, FEATURE_COLUMNS, get_paths, load_selected_feature_columns
from pipeline.station_registry import BENGALURU_STATIONS, get_station_by_id, station_output_dir
from pipeline.storage import validate_columns

logger = logging.getLogger(__name__)


def _risk_category(pm25: float) -> str:
    if pm25 <= 30:
        return "Good"
    if pm25 <= 60:
        return "Satisfactory"
    if pm25 <= 90:
        return "Moderate"
    if pm25 <= 120:
        return "Poor"
    if pm25 <= 250:
        return "Very Poor"
    return "Severe"


def _load_metrics(metrics_path) -> dict:
    if not metrics_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Model metrics are missing. Run data generation, feature building, training, and evaluation first.",
        )
    with metrics_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _latest_rows(features: pd.DataFrame) -> pd.DataFrame:
    required = {
        "timestamp",
        "station_id",
        "station_name",
        "latitude",
        "longitude",
        "pm25_lag_24h",
        *FEATURE_COLUMNS,
    }
    validate_columns(features, required, "processed feature data")
    rows = (
        features.sort_values(["station_id", "timestamp"])
        .groupby("station_id", as_index=False)
        .tail(1)
        .sort_values("station_id")
        .reset_index(drop=True)
    )
    if rows.empty:
        raise HTTPException(status_code=503, detail="Processed feature data exists but contains no forecastable rows.")
    return rows


def _predict_lightgbm(rows: pd.DataFrame, paths) -> list[float]:
    model = joblib.load(paths.lightgbm_model)
    with paths.feature_columns.open("r", encoding="utf-8") as file:
        feature_columns = json.load(file)
    validate_columns(rows, feature_columns, "latest forecast rows")
    predictions = model.predict(rows[feature_columns])
    return [max(0.0, float(value)) for value in predictions]


def get_station_forecasts() -> ForecastResponse:
    project_root = get_project_root()
    paths = get_paths(project_root)

    if not paths.processed_features.exists():
        raise HTTPException(
            status_code=503,
            detail="Processed Parquet data is missing. Run data generation and feature building first.",
        )

    metrics = _load_metrics(paths.evaluation_metrics)

    try:
        features = pd.read_parquet(paths.processed_features)
    except Exception as exc:
        logger.exception("Could not read processed feature data.")
        raise HTTPException(status_code=503, detail=f"Could not read processed feature data: {exc}") from exc

    rows = _latest_rows(features)
    selected = metrics.get("model_selected_for_serving", "persistence")
    forecast_engine = "persistence_fallback"
    predictions = [max(0.0, float(value)) for value in rows["pm25_lag_24h"]]

    if selected == "lightgbm":
        try:
            if not paths.lightgbm_model.exists() or not paths.feature_columns.exists():
                raise FileNotFoundError("LightGBM model or feature_columns.json is missing.")
            predictions = _predict_lightgbm(rows, paths)
            forecast_engine = "lightgbm"
        except Exception:
            logger.exception("LightGBM serving failed; falling back to persistence.")
            forecast_engine = "persistence_fallback"

    generated_at = pd.Timestamp.now(tz=timezone.utc).isoformat()
    forecasts: list[StationForecast] = []
    for row, prediction in zip(rows.to_dict(orient="records"), predictions):
        origin = pd.Timestamp(row["timestamp"])
        if origin.tzinfo is None:
            origin = origin.tz_localize("UTC")
        forecast_for = origin + pd.Timedelta(hours=24)
        forecasts.append(
            StationForecast(
                station_id=str(row["station_id"]),
                station_name=str(row["station_name"]),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                prediction_origin=origin.isoformat(),
                forecast_for=forecast_for.isoformat(),
                predicted_pm25=round(float(prediction), 2),
                risk_category=_risk_category(float(prediction)),
            )
        )

    return ForecastResponse(
        city="Bengaluru",
        data_mode=get_data_mode(),
        forecast_engine=forecast_engine,
        generated_at=generated_at,
        forecasts=forecasts,
    )


def _real_hebbal_missing_detail(missing_steps: list[str]) -> str:
    commands = "; ".join(missing_steps)
    return (
        "Real Hebbal forecast artifacts are missing. "
        f"Run these commands from the repository root: {commands}"
    )


def get_real_hebbal_forecast() -> RealHebbalForecastResponse:
    project_root = get_project_root()
    paths = get_paths(project_root, dataset=DATASET_REAL_HEBBAL)
    missing_steps: list[str] = []

    if not paths.raw_data.exists():
        missing_steps.append(
            "place the raw CSV at data/raw/cpcb/hebbal_bengaluru_kspcb_15m.csv"
        )
    if not paths.processed_features.exists():
        missing_steps.append(
            "python -m pipeline.ingest_cpcb_csv --input .\\data\\raw\\cpcb\\hebbal_bengaluru_kspcb_15m.csv "
            "--station-id cpcb_hebbal --station-name \"Hebbal, Bengaluru - KSPCB\" --source-timezone Asia/Kolkata"
        )
        missing_steps.append("python -m pipeline.build_real_features")
    if not paths.evaluation_metrics.exists():
        missing_steps.extend(
            [
                "python -m ml.train_persistence_baseline --dataset real_hebbal",
                "python -m ml.train_lightgbm --dataset real_hebbal",
                "python -m ml.evaluate --dataset real_hebbal",
            ]
        )

    if missing_steps:
        raise HTTPException(status_code=503, detail=_real_hebbal_missing_detail(missing_steps))

    quality = {}
    if paths.data_quality_summary and paths.data_quality_summary.exists():
        with paths.data_quality_summary.open("r", encoding="utf-8") as file:
            quality = json.load(file)

    metrics = _load_metrics(paths.evaluation_metrics)

    try:
        features = pd.read_parquet(paths.processed_features)
    except Exception as exc:
        logger.exception("Could not read real Hebbal feature data.")
        raise HTTPException(status_code=503, detail=f"Could not read real Hebbal feature data: {exc}") from exc

    required = {
        "timestamp",
        "timestamp_utc",
        "station_id",
        "station_name",
        "pm25_lag_24h",
    }
    validate_columns(features, required, "real Hebbal feature data")
    latest = features.sort_values("timestamp").tail(1)
    if latest.empty:
        raise HTTPException(status_code=503, detail="Real Hebbal feature data exists but contains no forecastable rows.")

    row = latest.iloc[0]
    if pd.isna(row["pm25_lag_24h"]):
        raise HTTPException(
            status_code=503,
            detail="Real Hebbal forecast requires an exact 24-hour PM2.5 lag at the latest timestamp; none is available.",
        )

    selected = metrics.get("model_selected_for_serving", "persistence")
    forecast_engine = "persistence_fallback"
    prediction = max(0.0, float(row["pm25_lag_24h"]))

    if selected == "lightgbm":
        try:
            if not paths.lightgbm_model.exists() or not paths.feature_columns.exists():
                raise FileNotFoundError("Real LightGBM artifacts are missing.")
            feature_columns = load_selected_feature_columns(project_root, dataset=DATASET_REAL_HEBBAL)
            validate_columns(latest, feature_columns, "latest real Hebbal forecast row")
            model = joblib.load(paths.lightgbm_model)
            prediction = max(0.0, float(model.predict(latest[feature_columns])[0]))
            forecast_engine = "lightgbm"
        except Exception:
            logger.exception("Real Hebbal LightGBM serving failed; falling back to exact 24-hour persistence.")
            forecast_engine = "persistence_fallback"

    origin = pd.Timestamp(row["timestamp"])
    if origin.tzinfo is None:
        origin = origin.tz_localize("UTC")
    forecast_for = origin + pd.Timedelta(hours=24)

    return RealHebbalForecastResponse(
        city="Bengaluru",
        station_id=str(row["station_id"]),
        station_name=str(row["station_name"]),
        data_mode="real_cpcb_kspcb_csv",
        source=str(quality.get("source", "CPCB/KSPCB 15-minute station export")),
        forecast_engine=forecast_engine,
        prediction_origin=origin.isoformat(),
        forecast_for=forecast_for.isoformat(),
        predicted_pm25=round(prediction, 2),
        risk_category=_risk_category(prediction),
        data_quality_classification=str(
            metrics.get("data_quality_classification")
            or quality.get("dataset_suitability_classification")
            or "Unknown"
        ),
        data_quality_note=str(metrics.get("data_quality_note") or quality.get("recommendation") or ""),
    )


def _load_multistation_artifacts(project_root: Path):
    paths = get_paths(project_root, dataset=DATASET_REAL_MULTISTATION)
    missing_steps: list[str] = []
    if not paths.processed_features.exists():
        missing_steps.append("python -m pipeline.ingest_cpcb_csv --multi-station")
        missing_steps.append("python -m pipeline.merge_multistation")
    if not paths.lightgbm_model.exists():
        missing_steps.extend([
            "python -m ml.train_persistence_baseline --dataset real_multistation",
            "python -m ml.train_lightgbm --dataset real_multistation",
            "python -m ml.evaluate --dataset real_multistation",
        ])
    if missing_steps:
        raise HTTPException(
            status_code=503,
            detail=f"Multi-station artifacts are missing. Run: {'; '.join(missing_steps)}",
        )
    return paths


def _predict_station_forecast(
    latest_row: pd.DataFrame,
    model,
    feature_columns: list[str],
    station_id: str,
    station_name: str,
    source: str,
    project_root: Path | None = None,
) -> MultiStationStationForecast:
    paths = get_paths(project_root, dataset=DATASET_REAL_MULTISTATION)
    station_cols_path = paths.artifacts_dir / "station_feature_columns.json"
    all_station_cols: list[str] = []
    if station_cols_path.exists():
        with station_cols_path.open("r", encoding="utf-8") as f:
            all_station_cols = json.load(f)

    encoded_row = latest_row.copy()
    for col in all_station_cols:
        encoded_row[col] = 0
    target_col = f"is_station_{station_id}"
    if target_col in all_station_cols:
        encoded_row[target_col] = 1

    all_cols = list(feature_columns) + all_station_cols
    prediction = max(0.0, float(model.predict(encoded_row[all_cols])[0]))

    origin = pd.Timestamp(latest_row["timestamp"].iloc[0])
    if origin.tzinfo is None:
        origin = origin.tz_localize("UTC")
    forecast_for = origin + pd.Timedelta(hours=24)

    return MultiStationStationForecast(
        station_id=station_id,
        station_name=station_name,
        data_mode="real_cpcb_kspcb_csv",
        source=source,
        forecast_engine="lightgbm",
        prediction_origin=origin.isoformat(),
        forecast_for=forecast_for.isoformat(),
        predicted_pm25=round(prediction, 2),
        risk_category=_risk_category(prediction),
    )


def get_multistation_forecasts() -> MultiStationForecastResponse:
    project_root = get_project_root()
    paths = _load_multistation_artifacts(project_root)

    features = pd.read_parquet(paths.processed_features)
    feature_columns = load_selected_feature_columns(project_root, dataset=DATASET_REAL_MULTISTATION)
    model = joblib.load(paths.lightgbm_model)

    eval_metrics: dict = {}
    if paths.evaluation_metrics.exists():
        with paths.evaluation_metrics.open("r", encoding="utf-8") as f:
            eval_metrics = json.load(f)
    per_station_eval = eval_metrics.get("per_station", {})

    forecasts: list[MultiStationStationForecast] = []
    for station_id in sorted(features["station_id"].unique()):
        station_rows = features[features["station_id"] == station_id]
        if station_rows.empty:
            continue
        station_config = get_station_by_id(station_id)
        latest = station_rows.sort_values("timestamp").tail(1)
        if pd.isna(latest["pm25_lag_24h"].iloc[0]):
            continue
        s_metrics = per_station_eval.get(station_id, {})
        forecast = _predict_station_forecast(
            latest, model, feature_columns, station_id, station_config.station_name, station_config.source,
            project_root=project_root,
        )
        forecast.model_rmse_on_test = s_metrics.get("lightgbm_rmse")
        forecasts.append(forecast)

    return MultiStationForecastResponse(
        city="Bengaluru",
        data_mode="real_cpcb_kspcb_csv",
        generated_at=pd.Timestamp.now(tz=timezone.utc).isoformat(),
        station_count=len(forecasts),
        model_selection_strategy="per-station: pooled LightGBM vs persistence baseline",
        forecasts=forecasts,
    )


def get_real_station_forecast(station_id: str) -> MultiStationStationForecast:
    project_root = get_project_root()
    paths = _load_multistation_artifacts(project_root)

    station_config = get_station_by_id(station_id)
    features = pd.read_parquet(paths.processed_features)
    station_features = features[features["station_id"] == station_id]
    if station_features.empty:
        raise HTTPException(
            status_code=503,
            detail=f"No feature data for station {station_id}. Station may have been excluded by quality gate.",
        )

    feature_columns = load_selected_feature_columns(project_root, dataset=DATASET_REAL_MULTISTATION)
    model = joblib.load(paths.lightgbm_model)

    latest = station_features.sort_values("timestamp").tail(1)
    if pd.isna(latest["pm25_lag_24h"].iloc[0]):
        raise HTTPException(
            status_code=503,
            detail=f"No exact 24-hour PM2.5 lag available at the latest timestamp for {station_id}.",
        )

    return _predict_station_forecast(
        latest, model, feature_columns, station_id, station_config.station_name, station_config.source,
        project_root=project_root,
    )


def get_station_status() -> StationStatusResponse:
    project_root = get_project_root()
    paths = get_paths(project_root, dataset=DATASET_REAL_MULTISTATION)
    stations: list[StationStatusItem] = []
    for config in BENGALURU_STATIONS:
        out_dir = station_output_dir(project_root, config.station_id)
        hourly_path = out_dir / f"{config.station_id}_hourly.parquet"
        feature_path = out_dir / f"{config.station_id}_features_24h.parquet"
        quality_path = out_dir / f"{config.station_id}_quality_summary.json"
        quality_class = None
        if quality_path.exists():
            with quality_path.open("r", encoding="utf-8") as f:
                quality_class = json.load(f).get("dataset_suitability_classification")
        stations.append(StationStatusItem(
            station_id=config.station_id,
            station_name=config.station_name,
            data_available=hourly_path.exists(),
            hourly_available=hourly_path.exists(),
            features_available=feature_path.exists(),
            model_available=paths.lightgbm_model.exists(),
            quality_classification=quality_class,
            forecast_eligible=config.forecast_eligible,
            pm25_forecast_coverage_status=config.pm25_forecast_coverage_status,
            available_pollutants=config.available_pollutants,
        ))
    return StationStatusResponse(
        city="Bengaluru",
        station_count=len(stations),
        stations=stations,
    )
