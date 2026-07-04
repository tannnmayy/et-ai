from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

TARGET_COLUMN = "target_pm25_24h"

FEATURE_COLUMNS = [
    "pm25_lag_1h",
    "pm25_lag_3h",
    "pm25_lag_6h",
    "pm25_lag_12h",
    "pm25_lag_24h",
    "pm10_lag_1h",
    "pm10_lag_24h",
    "no2_lag_1h",
    "no2_lag_24h",
    "temperature_c",
    "relative_humidity",
    "wind_speed_mps",
    "rainfall_mm",
    "hour",
    "weekday",
    "month",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
    "pm25_roll_mean_3h",
    "pm25_roll_mean_6h",
    "pm25_roll_mean_24h",
    "pm25_roll_std_24h",
]


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    raw_data: Path
    processed_features: Path
    artifacts_dir: Path
    lightgbm_model: Path
    feature_columns: Path
    persistence_artifact: Path
    evaluation_metrics: Path
    test_predictions: Path


def get_project_root() -> Path:
    configured = os.getenv("AQI_SENTINEL_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[1]


def get_paths(project_root: Path | None = None) -> ProjectPaths:
    root = Path(project_root or get_project_root()).resolve()
    artifacts = root / "ml" / "artifacts"
    return ProjectPaths(
        project_root=root,
        raw_data=root / "data" / "raw" / "bengaluru_hourly_air_quality_demo.csv",
        processed_features=root / "data" / "processed" / "station_features_24h.parquet",
        artifacts_dir=artifacts,
        lightgbm_model=artifacts / "lightgbm_pm25_24h.joblib",
        feature_columns=artifacts / "feature_columns.json",
        persistence_artifact=artifacts / "persistence_baseline.json",
        evaluation_metrics=artifacts / "evaluation_metrics.json",
        test_predictions=artifacts / "test_predictions.csv",
    )


def load_feature_data(path: Path | None = None, project_root: Path | None = None) -> pd.DataFrame:
    feature_path = Path(path or get_paths(project_root).processed_features)
    if not feature_path.exists():
        raise FileNotFoundError(f"Feature data not found: {feature_path}. Run python -m pipeline.build_features first.")
    frame = pd.read_parquet(feature_path)
    missing = sorted(set(FEATURE_COLUMNS + [TARGET_COLUMN, "timestamp", "pm25_lag_24h"]) - set(frame.columns))
    if missing:
        raise ValueError(f"Feature data is missing required columns: {', '.join(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values(["timestamp", "station_id"]).reset_index(drop=True)


def chronological_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    timestamps = np.array(sorted(pd.to_datetime(frame["timestamp"], utc=True).unique()))
    if len(timestamps) < 10:
        raise ValueError("Need at least 10 unique timestamps for chronological 70/15/15 splitting.")

    train_end = int(len(timestamps) * 0.70)
    validation_end = int(len(timestamps) * 0.85)
    train_times = set(timestamps[:train_end])
    validation_times = set(timestamps[train_end:validation_end])
    test_times = set(timestamps[validation_end:])

    train = frame[frame["timestamp"].isin(train_times)].copy()
    validation = frame[frame["timestamp"].isin(validation_times)].copy()
    test = frame[frame["timestamp"].isin(test_times)].copy()
    if train.empty or validation.empty or test.empty:
        raise ValueError("Chronological split produced an empty train, validation, or test set.")
    return train, validation, test


def rmse(actual: pd.Series | np.ndarray, predicted: pd.Series | np.ndarray) -> float:
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    return float(np.sqrt(np.mean((actual_values - predicted_values) ** 2)))


def mae(actual: pd.Series | np.ndarray, predicted: pd.Series | np.ndarray) -> float:
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    return float(np.mean(np.abs(actual_values - predicted_values)))
