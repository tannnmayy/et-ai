from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from ml.common import DATASET_REAL_MULTISTATION, DATASET_SYNTHETIC, TARGET_COLUMN, chronological_split, get_paths, load_feature_data, mae, rmse

logger = logging.getLogger(__name__)


def train_persistence_baseline(project_root: Path | None = None, dataset: str = DATASET_SYNTHETIC) -> dict:
    paths = get_paths(project_root, dataset=dataset)
    paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
    features = load_feature_data(project_root=project_root, dataset=dataset)
    _, validation, _ = chronological_split(features)

    predictions = validation["pm25_lag_24h"]
    metrics: dict = {
        "model": "persistence_baseline",
        "dataset": dataset,
        "rule": "prediction at t+24h equals observed PM2.5 at t",
        "validation_rows": int(len(validation)),
        "validation_rmse": rmse(validation[TARGET_COLUMN], predictions),
        "validation_mae": mae(validation[TARGET_COLUMN], predictions),
    }

    if dataset == DATASET_REAL_MULTISTATION:
        per_station: dict[str, dict] = {}
        for station_id, group in validation.groupby("station_id"):
            station_preds = group["pm25_lag_24h"]
            station_actuals = group[TARGET_COLUMN]
            per_station[station_id] = {
                "validation_rows": int(len(group)),
                "validation_rmse": round(float(rmse(station_actuals, station_preds)), 4),
                "validation_mae": round(float(mae(station_actuals, station_preds)), 4),
            }
        metrics["per_station"] = per_station
        logger.info("Computed per-station persistence for %d stations", len(per_station))

    with paths.persistence_artifact.open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2)
    logger.info("Wrote persistence baseline artifact to %s", paths.persistence_artifact)
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train/evaluate the persistence baseline artifact.")
    parser.add_argument("--dataset", default=DATASET_SYNTHETIC, choices=["synthetic", "real_hebbal", "real_multistation"])
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    train_persistence_baseline(dataset=args.dataset)
