from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib
import pandas as pd

from ml.common import DATASET_REAL_HEBBAL, DATASET_REAL_MULTISTATION, DATASET_SYNTHETIC, TARGET_COLUMN, chronological_split, get_paths, load_feature_data, load_selected_feature_columns, mae, rmse

logger = logging.getLogger(__name__)


def _load_quality_summary(paths) -> dict:
    if paths.data_quality_summary and paths.data_quality_summary.exists():
        with paths.data_quality_summary.open("r", encoding="utf-8") as file:
            return json.load(file)
    return {}


def evaluate_models(project_root: Path | None = None, dataset: str = DATASET_SYNTHETIC) -> dict:
    paths = get_paths(project_root, dataset=dataset)
    if not paths.lightgbm_model.exists() or not paths.feature_columns.exists():
        raise FileNotFoundError(
            f"LightGBM artifacts are missing under {paths.artifacts_dir}. "
            f"Run python -m ml.train_lightgbm --dataset {dataset} first."
        )

    features = load_feature_data(project_root=project_root, dataset=dataset)
    feature_columns = load_selected_feature_columns(project_root, dataset=dataset)
    train, validation, test = chronological_split(features)
    quality = _load_quality_summary(paths)

    model = joblib.load(paths.lightgbm_model)

    if dataset == DATASET_REAL_MULTISTATION:
        return _evaluate_multistation(paths, features, train, validation, test, model, feature_columns, quality)
    return _evaluate_single_station(paths, test, model, feature_columns, quality, dataset, train, validation)


def _evaluate_single_station(paths, test, model, feature_columns, quality, dataset, train, validation):
    persistence_predictions = test["pm25_lag_24h"].astype(float)
    lightgbm_predictions = model.predict(test[feature_columns])
    actual = test[TARGET_COLUMN].astype(float)

    persistence_rmse_val = rmse(actual, persistence_predictions)
    lightgbm_rmse_val = rmse(actual, lightgbm_predictions)
    improvement = ((persistence_rmse_val - lightgbm_rmse_val) / persistence_rmse_val) * 100 if persistence_rmse_val else 0.0
    selected = "lightgbm" if lightgbm_rmse_val < persistence_rmse_val else "persistence"

    timestamps = sorted(pd.to_datetime(test["timestamp"], utc=True).unique())
    metrics = {
        "task": "PM2.5 24-hour forecasting",
        "dataset": dataset,
        "city": "Bengaluru",
        "data_source": quality.get("source", "local_demo_data" if dataset == DATASET_SYNTHETIC else "CPCB/KSPCB 15-minute station export"),
        "station_id": quality.get("station_id"),
        "station_name": quality.get("station_name"),
        "date_range": {
            "start": quality.get("earliest_timestamp_utc") or str(timestamps[0]),
            "end": quality.get("latest_timestamp_utc") or str(timestamps[-1]),
        },
        "valid_rows": int(len(test) + len(train) + len(validation)),
        "split_strategy": "chronological 70/15/15 by unique timestamp",
        "split_boundaries": {
            "train_end": str(sorted(pd.to_datetime(train["timestamp"], utc=True).unique())[-1]),
            "validation_end": str(sorted(pd.to_datetime(validation["timestamp"], utc=True).unique())[-1]),
            "test_end": str(timestamps[-1]),
        },
        "selected_features": feature_columns,
        "test_rows": int(len(test)),
        "persistence": {
            "rmse": round(float(persistence_rmse_val), 4),
            "mae": round(float(mae(actual, persistence_predictions)), 4),
        },
        "lightgbm": {
            "rmse": round(float(lightgbm_rmse_val), 4),
            "mae": round(float(mae(actual, lightgbm_predictions)), 4),
        },
        "rmse_improvement_percent": round(float(improvement), 2),
        "model_selected_for_serving": selected,
        "data_quality_classification": quality.get("dataset_suitability_classification"),
        "data_quality_note": quality.get("recommendation"),
    }

    paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
    with paths.evaluation_metrics.open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2)

    predictions = pd.DataFrame(
        {
            "timestamp": test["timestamp"].astype(str),
            "station_id": test["station_id"].astype(str),
            "actual_pm25": actual.astype(float),
            "persistence_prediction": persistence_predictions.astype(float),
            "lightgbm_prediction": lightgbm_predictions.astype(float),
        }
    )
    predictions.to_csv(paths.test_predictions, index=False)
    logger.info("Wrote evaluation metrics to %s", paths.evaluation_metrics)
    logger.info("Wrote test predictions to %s", paths.test_predictions)
    return metrics


def _evaluate_multistation(paths, features, train, validation, test, model, feature_columns, quality):
    from ml.train_lightgbm import encode_station_id
    from ml.feature_engineering.station_interactions import add_station_interaction_features

    test_encoded, station_cols = encode_station_id(test.copy())

    interaction_cols: list[str] = []
    interaction_cols_path = paths.artifacts_dir / "station_interaction_columns.json"
    if interaction_cols_path.exists():
        with interaction_cols_path.open("r", encoding="utf-8") as f:
            interaction_cols = json.load(f)
        if interaction_cols:
            test_encoded, _ = add_station_interaction_features(test_encoded, station_cols)

    all_feature_cols = list(feature_columns) + station_cols + interaction_cols

    actual = test_encoded[TARGET_COLUMN].astype(float)
    persistence_predictions = test_encoded["pm25_lag_24h"].astype(float)
    lightgbm_predictions = model.predict(test_encoded[all_feature_cols])

    per_station: dict[str, dict] = {}
    for station_id, group in test_encoded.groupby("station_id"):
        s_actual = group[TARGET_COLUMN].astype(float)
        s_persist_pred = group["pm25_lag_24h"].astype(float)
        s_lgbm_pred = pd.Series(
            model.predict(group[all_feature_cols]),
            index=group.index,
        )
        s_persist_rmse = rmse(s_actual, s_persist_pred)
        s_lgbm_rmse = rmse(s_actual, s_lgbm_pred)
        s_improvement = ((s_persist_rmse - s_lgbm_rmse) / s_persist_rmse) * 100 if s_persist_rmse else 0.0
        s_selected = "lightgbm" if s_lgbm_rmse < s_persist_rmse else "persistence"
        per_station[station_id] = {
            "test_rows": int(len(group)),
            "persistence_rmse": round(float(s_persist_rmse), 4),
            "persistence_mae": round(float(mae(s_actual, s_persist_pred)), 4),
            "lightgbm_rmse": round(float(s_lgbm_rmse), 4),
            "lightgbm_mae": round(float(mae(s_actual, s_lgbm_pred)), 4),
            "rmse_improvement_percent": round(float(s_improvement), 2),
            "model_selected_for_serving": s_selected,
        }

    overall_persist_rmse = rmse(actual, persistence_predictions)
    overall_lgbm_rmse = rmse(actual, lightgbm_predictions)
    overall_improvement = ((overall_persist_rmse - overall_lgbm_rmse) / overall_persist_rmse) * 100 if overall_persist_rmse else 0.0
    lgbm_wins = sum(1 for s in per_station.values() if s["model_selected_for_serving"] == "lightgbm")
    persist_wins = sum(1 for s in per_station.values() if s["model_selected_for_serving"] == "persistence")

    timestamps = sorted(pd.to_datetime(test["timestamp"], utc=True).unique())
    metrics = {
        "task": "PM2.5 24-hour forecasting",
        "dataset": "real_multistation",
        "city": "Bengaluru",
        "split_strategy": "chronological 70/15/15 by unique timestamp (global)",
        "split_boundaries": {
            "train_end": str(sorted(pd.to_datetime(train["timestamp"], utc=True).unique())[-1]),
            "validation_end": str(sorted(pd.to_datetime(validation["timestamp"], utc=True).unique())[-1]),
            "test_end": str(timestamps[-1]),
        },
        "selected_features": all_feature_cols,
        "total_test_rows": int(len(test)),
        "overall_persistence": {
            "rmse": round(float(overall_persist_rmse), 4),
            "mae": round(float(mae(actual, persistence_predictions)), 4),
        },
        "overall_lightgbm": {
            "rmse": round(float(overall_lgbm_rmse), 4),
            "mae": round(float(mae(actual, lightgbm_predictions)), 4),
        },
        "overall_rmse_improvement_percent": round(float(overall_improvement), 2),
        "lgbm_wins_count": lgbm_wins,
        "persistence_wins_count": persist_wins,
        "per_station": per_station,
        "station_count": len(per_station),
    }

    paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
    with paths.evaluation_metrics.open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2)

    predictions = pd.DataFrame(
        {
            "timestamp": test_encoded["timestamp"].astype(str),
            "station_id": test_encoded["station_id"].astype(str),
            "actual_pm25": actual.astype(float),
            "persistence_prediction": persistence_predictions.astype(float),
            "lightgbm_prediction": lightgbm_predictions.astype(float),
        }
    )
    predictions.to_csv(paths.test_predictions, index=False)
    logger.info("Wrote multi-station evaluation metrics to %s", paths.evaluation_metrics)
    logger.info("Wrote test predictions to %s", paths.test_predictions)
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate persistence and LightGBM on the held-out test split.")
    parser.add_argument("--dataset", default=DATASET_SYNTHETIC, choices=["synthetic", "real_hebbal", "real_multistation"])
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    evaluate_models(dataset=args.dataset)
