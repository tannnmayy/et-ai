from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.station_registry import BENGALURU_STATIONS, all_station_ids, station_output_dir

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

MANDATORY_REAL_FEATURES = [
    "pm25_lag_1h",
    "pm25_lag_3h",
    "pm25_lag_6h",
    "pm25_lag_12h",
    "pm25_lag_24h",
    "hour",
    "weekday",
    "month",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
]

OPTIONAL_REAL_FEATURES = [
    "pm10_lag_1h",
    "pm10_lag_24h",
    "no2_lag_1h",
    "no2_lag_24h",
    "temperature_c",
    "relative_humidity",
    "wind_speed_mps",
    "rainfall_mm",
    "pm25_roll_mean_3h",
    "pm25_roll_mean_6h",
    "pm25_roll_mean_24h",
    "pm25_roll_std_24h",
]

DATASET_SYNTHETIC = "synthetic"
DATASET_REAL_HEBBAL = "real_hebbal"
DATASET_REAL_MULTISTATION = "real_multistation"
SUPPORTED_DATASETS = {DATASET_SYNTHETIC, DATASET_REAL_HEBBAL, DATASET_REAL_MULTISTATION}


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    dataset: str
    raw_data: Path
    processed_features: Path
    processed_hourly: Path | None
    cleaned_15min: Path | None
    artifacts_dir: Path
    lightgbm_model: Path
    feature_columns: Path
    feature_metadata: Path | None
    persistence_artifact: Path
    evaluation_metrics: Path
    test_predictions: Path
    data_quality_summary: Path | None
    quality_report_csv: Path | None
    quality_report_md: Path | None
    per_station_features: dict[str, Path] | None = None


def get_project_root() -> Path:
    configured = os.getenv("AQI_SENTINEL_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[1]


def get_paths(project_root: Path | None = None, dataset: str = DATASET_SYNTHETIC) -> ProjectPaths:
    root = Path(project_root or get_project_root()).resolve()
    if dataset not in SUPPORTED_DATASETS:
        raise ValueError(f"Unsupported dataset: {dataset}. Expected one of: {', '.join(sorted(SUPPORTED_DATASETS))}")

    if dataset == DATASET_REAL_HEBBAL:
        artifacts = root / "ml" / "artifacts" / "real_hebbal"
        return ProjectPaths(
            project_root=root,
            dataset=dataset,
            raw_data=root / "data" / "raw" / "cpcb" / "hebbal_bengaluru_kspcb_15m.csv",
            processed_features=root / "data" / "processed" / "real" / "hebbal_station_features_24h.parquet",
            processed_hourly=root / "data" / "processed" / "real" / "hebbal_station_hourly.parquet",
            cleaned_15min=root / "data" / "processed" / "real" / "hebbal_15min_clean.parquet",
            artifacts_dir=artifacts,
            lightgbm_model=artifacts / "lightgbm_pm25_24h.joblib",
            feature_columns=artifacts / "feature_columns.json",
            feature_metadata=artifacts / "feature_metadata.json",
            persistence_artifact=artifacts / "persistence_baseline.json",
            evaluation_metrics=artifacts / "evaluation_metrics.json",
            test_predictions=artifacts / "test_predictions.csv",
            data_quality_summary=artifacts / "data_quality_summary.json",
            quality_report_csv=root / "data" / "reports" / "hebbal_cpcb_data_quality.csv",
            quality_report_md=root / "data" / "reports" / "hebbal_cpcb_data_quality.md",
        )

    if dataset == DATASET_REAL_MULTISTATION:
        artifacts = root / "ml" / "artifacts" / "multistation"
        per_station = {
            sid: station_output_dir(root, sid) / f"{sid}_features_24h.parquet"
            for sid in all_station_ids()
        }
        return ProjectPaths(
            project_root=root,
            dataset=dataset,
            raw_data=root / "data" / "raw" / "cpcb",
            processed_features=root / "data" / "processed" / "real" / "bengaluru_multistation_features_24h.parquet",
            processed_hourly=None,
            cleaned_15min=None,
            artifacts_dir=artifacts,
            lightgbm_model=artifacts / "lightgbm_pm25_24h.joblib",
            feature_columns=artifacts / "feature_columns.json",
            feature_metadata=artifacts / "feature_metadata.json",
            persistence_artifact=artifacts / "persistence_baseline.json",
            evaluation_metrics=artifacts / "evaluation_metrics.json",
            test_predictions=artifacts / "test_predictions.csv",
            data_quality_summary=artifacts / "data_quality_summary.json",
            quality_report_csv=None,
            quality_report_md=None,
            per_station_features=per_station,
        )

    artifacts = root / "ml" / "artifacts"
    return ProjectPaths(
        project_root=root,
        dataset=dataset,
        raw_data=root / "data" / "raw" / "bengaluru_hourly_air_quality_demo.csv",
        processed_features=root / "data" / "processed" / "station_features_24h.parquet",
        processed_hourly=None,
        cleaned_15min=None,
        artifacts_dir=artifacts,
        lightgbm_model=artifacts / "lightgbm_pm25_24h.joblib",
        feature_columns=artifacts / "feature_columns.json",
        feature_metadata=None,
        persistence_artifact=artifacts / "persistence_baseline.json",
        evaluation_metrics=artifacts / "evaluation_metrics.json",
        test_predictions=artifacts / "test_predictions.csv",
        data_quality_summary=None,
        quality_report_csv=None,
        quality_report_md=None,
    )


def load_feature_data(
    path: Path | None = None,
    project_root: Path | None = None,
    dataset: str = DATASET_SYNTHETIC,
) -> pd.DataFrame:
    paths = get_paths(project_root, dataset=dataset)
    feature_path = Path(path or paths.processed_features)
    if not feature_path.exists():
        cmd_map = {
            DATASET_REAL_HEBBAL: "python -m pipeline.build_real_features",
            DATASET_REAL_MULTISTATION: "python -m pipeline.merge_multistation",
        }
        cmd = cmd_map.get(dataset, "python -m pipeline.build_features")
        raise FileNotFoundError(
            f"Feature data not found: {feature_path}. Run {cmd} first."
        )
    frame = pd.read_parquet(feature_path)
    timestamp_column = "timestamp_utc" if "timestamp_utc" in frame.columns else "timestamp"
    if timestamp_column not in frame.columns:
        raise ValueError("Feature data must include timestamp or timestamp_utc.")

    if dataset in (DATASET_REAL_HEBBAL, DATASET_REAL_MULTISTATION):
        with paths.feature_columns.open("r", encoding="utf-8") as file:
            selected_features = json.load(file)
        required = set(selected_features + [TARGET_COLUMN, "pm25_lag_24h", timestamp_column, "station_id"])
    else:
        required = set(FEATURE_COLUMNS + [TARGET_COLUMN, "pm25_lag_24h", "timestamp", "station_id"])

    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Feature data is missing required columns: {', '.join(missing)}")

    frame[timestamp_column] = pd.to_datetime(frame[timestamp_column], utc=True)
    if timestamp_column != "timestamp":
        frame["timestamp"] = frame[timestamp_column]
    return frame.sort_values(["timestamp", "station_id"]).reset_index(drop=True)


def load_selected_feature_columns(project_root: Path | None = None, dataset: str = DATASET_SYNTHETIC) -> list[str]:
    paths = get_paths(project_root, dataset=dataset)
    if dataset in (DATASET_REAL_HEBBAL, DATASET_REAL_MULTISTATION):
        if not paths.feature_columns.exists():
            raise FileNotFoundError("Real feature_columns.json is missing. Run python -m pipeline.build_real_features first.")
        with paths.feature_columns.open("r", encoding="utf-8") as file:
            return json.load(file)
    return FEATURE_COLUMNS.copy()


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
