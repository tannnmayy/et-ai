from __future__ import annotations

import json
import logging
from datetime import timezone

import joblib
import pandas as pd
from fastapi import HTTPException

from backend.app.config import get_data_mode, get_project_root
from backend.app.schemas.forecast import ForecastResponse, StationForecast
from ml.common import FEATURE_COLUMNS, get_paths
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
