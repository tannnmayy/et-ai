from __future__ import annotations

import json
import logging
from datetime import timezone
from pathlib import Path

import pandas as pd

from backend.app.config import (
    PM25_RISK_THRESHOLDS,
    SUPPORTED_CITIES,
    get_project_root,
)
from ml.common import DATASET_REAL_MULTISTATION, get_paths, load_selected_feature_columns
from pipeline.station_registry import (
    BENGALURU_STATIONS,
    get_station_by_id,
    station_output_dir,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain errors
# ---------------------------------------------------------------------------

class UnsupportedCityError(Exception):
    def __init__(self, city: str) -> None:
        super().__init__(f"No validated station dataset is registered for city '{city}'.")
        self.city = city


class UnknownStationError(Exception):
    def __init__(self, station_id: str) -> None:
        super().__init__(f"Unknown station_id: {station_id}.")
        self.station_id = station_id


class MissingArtifactError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NoValidForecastError(Exception):
    def __init__(self, station_id: str) -> None:
        super().__init__(f"No valid forecast available for station '{station_id}'.")
        self.station_id = station_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | list:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _risk_category(pm25: float) -> str:
    for name, threshold in PM25_RISK_THRESHOLDS.items():
        if pm25 <= threshold:
            return name
    return "Severe"


def _validate_city(city: str) -> str:
    key = city.lower().strip()
    if key not in SUPPORTED_CITIES:
        raise UnsupportedCityError(city)
    return key


def _validate_station(station_id: str) -> None:
    try:
        get_station_by_id(station_id)
    except KeyError:
        raise UnknownStationError(station_id)


def _get_project_and_paths():
    project_root = get_project_root()
    paths = get_paths(project_root, dataset=DATASET_REAL_MULTISTATION)
    return project_root, paths


def _load_all_artifacts():
    project_root, paths = _get_project_and_paths()
    if not paths.processed_features.exists():
        raise MissingArtifactError(
            "Multi-station artifacts are missing. Run: "
            "python -m pipeline.ingest_cpcb_csv --multi-station; "
            "python -m pipeline.merge_multistation"
        )
    eval_metrics = _load_json(paths.evaluation_metrics)
    manifest = _load_json(project_root / "ml" / "artifacts" / "multistation" / "station_manifest.json")
    persistence = _load_json(paths.persistence_artifact)
    features = pd.read_parquet(paths.processed_features)
    return project_root, paths, eval_metrics, manifest, persistence, features


def _get_station_quality(station_id: str, manifest: dict) -> dict:
    details = manifest.get("quality_details", {}).get(station_id, {})
    return {
        "station_id": station_id,
        "classification": details.get("classification", "Unknown"),
        "recommendation": details.get("recommendation", ""),
        "hourly_row_count": details.get("hourly_row_count", 0),
        "pm25_completeness_percent": details.get("pm25_completeness_percent", 0.0),
        "longest_continuous_pm25_run_hours": details.get("longest_continuous_pm25_run_hours", 0),
        "pm25_gaps_longer_than_24h": details.get("pm25_gaps_longer_than_24h", 0),
    }


def _get_station_eval(station_id: str, eval_metrics: dict, persistence: dict) -> dict:
    per_station = eval_metrics.get("per_station", {})
    persist_per = persistence.get("per_station", {})
    station_eval = per_station.get(station_id, {})
    station_persist = persist_per.get(station_id, {})
    return {
        "station_id": station_id,
        "model_selected_for_serving": station_eval.get("model_selected_for_serving", "persistence"),
        "persistence_rmse": station_eval.get("persistence_rmse", station_persist.get("validation_rmse", 0)),
        "persistence_mae": station_eval.get("persistence_mae", station_persist.get("validation_mae", 0)),
        "lightgbm_rmse": station_eval.get("lightgbm_rmse"),
        "lightgbm_mae": station_eval.get("lightgbm_mae"),
        "rmse_improvement_percent": station_eval.get("rmse_improvement_percent"),
        "test_rows": station_eval.get("test_rows", 0),
    }


def _build_snapshot(
    station_id: str,
    station_config,
    features: pd.DataFrame,
    eval_metrics: dict,
    manifest: dict,
    persistence: dict,
    city_key: str,
) -> dict:
    station_features = features[features["station_id"] == station_id]
    if station_features.empty:
        raise NoValidForecastError(station_id)

    latest = station_features.sort_values("timestamp").tail(1).iloc[0]

    if pd.isna(latest["pm25_lag_24h"]):
        raise NoValidForecastError(station_id)

    eval_data = _get_station_eval(station_id, eval_metrics, persistence)
    quality = _get_station_quality(station_id, manifest)

    predicted_pm25 = max(0.0, float(latest["pm25_lag_24h"]))
    forecast_engine = eval_data["model_selected_for_serving"]

    origin = pd.Timestamp(latest["timestamp"])
    if origin.tzinfo is None:
        origin = origin.tz_localize("UTC")
    forecast_for = origin + pd.Timedelta(hours=24)

    latest_observed_pm25 = None
    latest_observed_at = None
    if not pd.isna(latest.get("pm25", float("nan"))):
        latest_observed_pm25 = float(latest["pm25"])
        ts_obs = pd.Timestamp(latest["timestamp"])
        if ts_obs.tzinfo is None:
            ts_obs = ts_obs.tz_localize("UTC")
        latest_observed_at = ts_obs.isoformat()

    artifact_status = {
        "features_available": True,
        "evaluation_available": station_eval_available(station_id, eval_metrics),
        "quality_available": station_id in manifest.get("quality_details", {}),
        "model_available": True,
    }

    return {
        "station_id": station_id,
        "station_name": station_config.station_name,
        "city": SUPPORTED_CITIES[city_key]["display_name"],
        "forecast_engine": forecast_engine,
        "prediction_origin": origin.isoformat(),
        "forecast_for": forecast_for.isoformat(),
        "predicted_pm25": round(predicted_pm25, 2),
        "latest_observed_pm25": round(latest_observed_pm25, 2) if latest_observed_pm25 is not None else None,
        "latest_observed_at": latest_observed_at,
        "risk_category": _risk_category(predicted_pm25),
        "quality_classification": quality["classification"],
        "quality_note": quality["recommendation"],
        "evaluation_metrics": eval_data,
        "artifact_status": artifact_status,
    }


def station_eval_available(station_id: str, eval_metrics: dict) -> bool:
    return station_id in eval_metrics.get("per_station", {})


# ---------------------------------------------------------------------------
# Public API (spec-required signatures)
# ---------------------------------------------------------------------------

def get_station_snapshot(station_id: str, city: str = "bengaluru") -> dict:
    """Return a normalized snapshot for one station.

    Reads: unified features parquet, evaluation_metrics.json,
    persistence_baseline.json, station_manifest.json, station registry.
    """
    _validate_station(station_id)
    city_key = _validate_city(city)
    _, paths, eval_metrics, manifest, persistence, features = _load_all_artifacts()
    config = get_station_by_id(station_id)
    return _build_snapshot(station_id, config, features, eval_metrics, manifest, persistence, city_key)


def list_station_snapshots(city: str | None = None) -> list[dict]:
    """Return snapshots for all accepted stations in a city (or all cities if None)."""
    if city is not None:
        _validate_city(city)
    _, paths, eval_metrics, manifest, persistence, features = _load_all_artifacts()

    results = []
    for config in BENGALURU_STATIONS:
        sid = config.station_id
        try:
            snap = _build_snapshot(sid, config, features, eval_metrics, manifest, persistence, "bengaluru")
            results.append(snap)
        except (NoValidForecastError, KeyError):
            continue
    return results


def get_city_station_snapshots(city: str) -> list[dict]:
    """Return snapshots for all accepted stations in the given city."""
    _validate_city(city)
    return list_station_snapshots(city=city)


def get_station_recent_observations(
    station_id: str, lookback_hours: int = 72
) -> list[dict]:
    """Return recent raw observations for a station.

    Reads: per-station features parquet. Returns actual measured values
    (pm25, pm10, no2, temperature_c, relative_humidity, rainfall_mm) from
    the most recent timestamps, without forward-fill or imputation.
    """
    _validate_station(station_id)
    project_root, paths = _get_project_and_paths()
    per_station_path = paths.per_station_features.get(station_id) if paths.per_station_features else None
    if per_station_path is None or not per_station_path.exists():
        raise MissingArtifactError(f"Per-station features for {station_id} not found.")

    df = pd.read_parquet(per_station_path)
    df = df.sort_values("timestamp")
    latest_ts = df["timestamp"].max()
    cutoff = latest_ts - pd.Timedelta(hours=lookback_hours)
    recent = df[df["timestamp"] > cutoff]

    obs_cols = ["timestamp", "pm25", "pm10", "no2", "temperature_c", "relative_humidity", "rainfall_mm"]
    available_cols = [c for c in obs_cols if c in recent.columns]
    records = recent[available_cols].to_dict(orient="records")

    cleaned = []
    for rec in records:
        entry = {}
        for k, v in rec.items():
            if pd.isna(v):
                entry[k] = None
            elif isinstance(v, pd.Timestamp):
                entry[k] = v.isoformat()
            else:
                entry[k] = round(float(v), 4) if isinstance(v, (int, float)) else v
        cleaned.append(entry)
    return cleaned


def get_station_quality(station_id: str) -> dict:
    """Return structured quality data for a station.

    Reads: station_manifest.json quality_details.
    """
    _validate_station(station_id)
    project_root, _, _, manifest, _, _ = _load_all_artifacts()
    return _get_station_quality(station_id, manifest)


def get_station_evaluation(station_id: str) -> dict:
    """Return structured evaluation metrics for a station.

    Reads: evaluation_metrics.json per_station, persistence_baseline.json per_station.
    """
    _validate_station(station_id)
    _, _, eval_metrics, _, persistence, _ = _load_all_artifacts()
    return _get_station_eval(station_id, eval_metrics, persistence)


def get_lightgbm_explanation_context(station_id: str) -> dict | None:
    """Return model context for LightGBM forecasts (model_context_fallback mode).

    Returns None for persistence-selected stations.

    Reads: per-station features parquet for recent lag values, rolling stats,
    temporal features, and available pollutant/weather context.
    """
    _validate_station(station_id)
    _, _, eval_metrics, _, _, features = _load_all_artifacts()

    eval_data = _get_station_eval(station_id, eval_metrics, {})
    if eval_data["model_selected_for_serving"] != "lightgbm":
        return None

    station_features = features[features["station_id"] == station_id]
    if station_features.empty:
        return None
    latest = station_features.sort_values("timestamp").iloc[-1]

    context = {
        "explanation_method": "model_context_fallback",
        "lag_values": {},
        "rolling_values": {},
        "temporal_context": {},
        "pollutant_weather_context": {},
    }

    lag_cols = ["pm25_lag_1h", "pm25_lag_3h", "pm25_lag_6h", "pm25_lag_12h", "pm25_lag_24h"]
    for col in lag_cols:
        if col in latest.index and not pd.isna(latest[col]):
            context["lag_values"][col] = round(float(latest[col]), 4)

    rolling_cols = ["pm25_roll_mean_3h", "pm25_roll_mean_6h", "pm25_roll_mean_24h", "pm25_roll_std_24h"]
    for col in rolling_cols:
        if col in latest.index and not pd.isna(latest[col]):
            context["rolling_values"][col] = round(float(latest[col]), 4)

    temporal_cols = ["hour", "weekday", "month", "hour_sin", "hour_cos", "weekday_sin", "weekday_cos"]
    for col in temporal_cols:
        if col in latest.index and not pd.isna(latest[col]):
            context["temporal_context"][col] = round(float(latest[col]), 4)

    weather_cols = ["pm10_lag_1h", "no2_lag_1h", "temperature_c", "relative_humidity", "rainfall_mm"]
    for col in weather_cols:
        if col in latest.index and not pd.isna(latest[col]):
            context["pollutant_weather_context"][col] = round(float(latest[col]), 4)

    return context
