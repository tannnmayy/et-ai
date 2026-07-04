from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib
import pandas as pd

from ml.common import DATASET_REAL_MULTISTATION, DATASET_SYNTHETIC, TARGET_COLUMN, chronological_split, get_paths, load_feature_data, load_selected_feature_columns

logger = logging.getLogger(__name__)


def encode_station_id(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    station_ids = sorted(frame["station_id"].dropna().unique())
    encoded_cols: list[str] = []
    for sid in station_ids:
        col_name = f"is_station_{sid}"
        frame[col_name] = (frame["station_id"] == sid).astype(int)
        encoded_cols.append(col_name)
    return frame, encoded_cols


def train_lightgbm(project_root: Path | None = None, dataset: str = DATASET_SYNTHETIC):
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise ImportError("LightGBM is not installed. Run: pip install -r requirements.txt") from exc

    paths = get_paths(project_root, dataset=dataset)
    paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
    features = load_feature_data(project_root=project_root, dataset=dataset)
    feature_columns = load_selected_feature_columns(project_root, dataset=dataset)

    station_encoded_cols: list[str] = []
    if dataset == DATASET_REAL_MULTISTATION:
        features, station_encoded_cols = encode_station_id(features)
        training_feature_columns = list(feature_columns) + station_encoded_cols
    else:
        training_feature_columns = list(feature_columns)

    train, validation, _ = chronological_split(features)

    model = lgb.LGBMRegressor(
        objective="regression",
        n_estimators=1000,
        learning_rate=0.03,
        num_leaves=31,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        verbosity=-1,
    )

    fit_kwargs = {
        "X": train[training_feature_columns],
        "y": train[TARGET_COLUMN],
        "eval_set": [(validation[training_feature_columns], validation[TARGET_COLUMN])],
        "eval_metric": "rmse",
    }
    try:
        model.fit(**fit_kwargs, callbacks=[lgb.early_stopping(50, verbose=False)])
    except TypeError:
        logger.warning("Installed LightGBM does not support callback-based early stopping; fitting without it.")
        model.fit(**fit_kwargs)

    joblib.dump(model, paths.lightgbm_model)
    with paths.feature_columns.open("w", encoding="utf-8") as file:
        json.dump(feature_columns, file, indent=2)
    if station_encoded_cols:
        station_cols_path = paths.artifacts_dir / "station_feature_columns.json"
        with station_cols_path.open("w", encoding="utf-8") as file:
            json.dump(station_encoded_cols, file, indent=2)
        logger.info("Wrote station feature columns to %s", station_cols_path)
    logger.info("Wrote LightGBM model to %s", paths.lightgbm_model)
    if station_encoded_cols:
        logger.info("Encoded station_id as %d one-hot features: %s", len(station_encoded_cols), station_encoded_cols)
    return model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the LightGBM PM2.5 24-hour model.")
    parser.add_argument("--dataset", default=DATASET_SYNTHETIC, choices=["synthetic", "real_hebbal", "real_multistation"])
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    train_lightgbm(dataset=args.dataset)
