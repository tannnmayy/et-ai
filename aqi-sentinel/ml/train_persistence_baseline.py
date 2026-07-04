from __future__ import annotations

import json
import logging
from pathlib import Path

from ml.common import TARGET_COLUMN, chronological_split, get_paths, load_feature_data, mae, rmse

logger = logging.getLogger(__name__)


def train_persistence_baseline(project_root: Path | None = None) -> dict:
    paths = get_paths(project_root)
    paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
    features = load_feature_data(project_root=project_root)
    _, validation, _ = chronological_split(features)
    predictions = validation["pm25_lag_24h"]
    metrics = {
        "model": "persistence_baseline",
        "rule": "prediction at t+24h equals observed PM2.5 at t",
        "validation_rows": int(len(validation)),
        "validation_rmse": rmse(validation[TARGET_COLUMN], predictions),
        "validation_mae": mae(validation[TARGET_COLUMN], predictions),
    }
    with paths.persistence_artifact.open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2)
    logger.info("Wrote persistence baseline artifact to %s", paths.persistence_artifact)
    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    train_persistence_baseline()
