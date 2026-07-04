from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import pandas as pd

from ml.common import TARGET_COLUMN, chronological_split, get_paths, load_feature_data, mae, rmse

logger = logging.getLogger(__name__)


def evaluate_models(project_root: Path | None = None) -> dict:
    paths = get_paths(project_root)
    if not paths.lightgbm_model.exists() or not paths.feature_columns.exists():
        raise FileNotFoundError("LightGBM artifacts are missing. Run python -m ml.train_lightgbm first.")

    features = load_feature_data(project_root=project_root)
    _, _, test = chronological_split(features)

    model = joblib.load(paths.lightgbm_model)
    with paths.feature_columns.open("r", encoding="utf-8") as file:
        feature_columns = json.load(file)

    persistence_predictions = test["pm25_lag_24h"].astype(float)
    lightgbm_predictions = model.predict(test[feature_columns])
    actual = test[TARGET_COLUMN].astype(float)

    persistence_rmse = rmse(actual, persistence_predictions)
    lightgbm_rmse = rmse(actual, lightgbm_predictions)
    improvement = ((persistence_rmse - lightgbm_rmse) / persistence_rmse) * 100
    selected = "lightgbm" if lightgbm_rmse < persistence_rmse else "persistence"

    metrics = {
        "task": "PM2.5 24-hour forecasting",
        "city": "Bengaluru",
        "split_strategy": "chronological 70/15/15 by unique timestamp",
        "test_rows": int(len(test)),
        "persistence": {
            "rmse": round(float(persistence_rmse), 4),
            "mae": round(float(mae(actual, persistence_predictions)), 4),
        },
        "lightgbm": {
            "rmse": round(float(lightgbm_rmse), 4),
            "mae": round(float(mae(actual, lightgbm_predictions)), 4),
        },
        "rmse_improvement_percent": round(float(improvement), 2),
        "model_selected_for_serving": selected,
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    evaluate_models()
