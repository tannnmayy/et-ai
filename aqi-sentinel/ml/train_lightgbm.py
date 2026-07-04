from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib

from ml.common import FEATURE_COLUMNS, TARGET_COLUMN, chronological_split, get_paths, load_feature_data

logger = logging.getLogger(__name__)


def train_lightgbm(project_root: Path | None = None):
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise ImportError("LightGBM is not installed. Run: pip install -r requirements.txt") from exc

    paths = get_paths(project_root)
    paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
    features = load_feature_data(project_root=project_root)
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
        "X": train[FEATURE_COLUMNS],
        "y": train[TARGET_COLUMN],
        "eval_set": [(validation[FEATURE_COLUMNS], validation[TARGET_COLUMN])],
        "eval_metric": "rmse",
    }
    try:
        model.fit(**fit_kwargs, callbacks=[lgb.early_stopping(50, verbose=False)])
    except TypeError:
        logger.warning("Installed LightGBM does not support callback-based early stopping; fitting without it.")
        model.fit(**fit_kwargs)

    joblib.dump(model, paths.lightgbm_model)
    with paths.feature_columns.open("w", encoding="utf-8") as file:
        json.dump(FEATURE_COLUMNS, file, indent=2)
    logger.info("Wrote LightGBM model to %s", paths.lightgbm_model)
    return model


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    train_lightgbm()
