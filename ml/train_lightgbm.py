from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib
import pandas as pd

from ml.common import (
    DATASET_REAL_MULTISTATION,
    DATASET_SYNTHETIC,
    TARGET_COLUMN,
    chronological_split,
    get_paths,
    load_feature_data,
    load_selected_feature_columns,
    mae,
    rmse,
)
from ml.feature_engineering.station_interactions import add_station_interaction_features

logger = logging.getLogger(__name__)


def encode_station_id(
    frame: pd.DataFrame,
    station_ids: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    if station_ids is not None:
        ids = sorted(station_ids)
        logger.info("Encoding %d stations from explicit list", len(ids))
    else:
        ids = sorted(frame["station_id"].dropna().unique())
        logger.warning(
            "encode_station_id: no explicit station_ids provided, "
            "falling back to frame data (%d stations) — "
            "may mismatch training-time station list",
            len(ids),
        )
    encoded_cols: list[str] = []
    for sid in ids:
        col_name = f"is_station_{sid}"
        frame[col_name] = (frame["station_id"] == sid).astype(int)
        encoded_cols.append(col_name)
    return frame, encoded_cols


def _load_old_evaluation(paths) -> tuple[dict, set]:
    old_eval: dict = {}
    old_test_timestamps: set = set()
    old_eval_path = paths.evaluation_metrics
    if old_eval_path.exists():
        with old_eval_path.open("r", encoding="utf-8") as f:
            old_eval = json.load(f)
        old_test_csv = paths.artifacts_dir / "test_predictions.csv"
        if old_test_csv.exists():
            old_test_df = pd.read_csv(old_test_csv)
            parsed = pd.to_datetime(old_test_df["timestamp"], utc=True, errors="coerce")
            old_test_timestamps = set(parsed.dropna())
    return old_eval, old_test_timestamps


def _compute_per_station_metrics(
    test: pd.DataFrame,
    feature_cols: list[str],
    model,
) -> dict:
    actual = test[TARGET_COLUMN].astype(float)
    persistence_predictions = test["pm25_lag_24h"].astype(float)
    lightgbm_predictions = model.predict(test[feature_cols])

    per_station: dict[str, dict] = {}
    for station_id, group in test.groupby("station_id"):
        s_actual = group[TARGET_COLUMN].astype(float)
        s_persist_pred = group["pm25_lag_24h"].astype(float)
        s_lgbm_pred = pd.Series(
            model.predict(group[feature_cols]),
            index=group.index,
        )
        s_persist_rmse = rmse(s_actual, s_persist_pred)
        s_lgbm_rmse = rmse(s_actual, s_lgbm_pred)
        s_improvement = ((s_persist_rmse - s_lgbm_rmse) / s_persist_rmse * 100) if s_persist_rmse else 0.0
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
    overall_improvement = ((overall_persist_rmse - overall_lgbm_rmse) / overall_persist_rmse * 100) if overall_persist_rmse else 0.0
    lgbm_wins = sum(1 for s in per_station.values() if s["model_selected_for_serving"] == "lightgbm")
    persist_wins = sum(1 for s in per_station.values() if s["model_selected_for_serving"] == "persistence")

    return {
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


def _print_comparison(
    old_eval: dict,
    new_frozen_metrics: dict,
    new_natural_metrics: dict,
    frozen_station_ids: set[str],
) -> None:
    old_per_station = old_eval.get("per_station", {})
    new_frozen_per = new_frozen_metrics.get("per_station", {})
    new_natural_per = new_natural_metrics.get("per_station", {})

    all_sids = sorted(set(list(old_per_station.keys()) + list(new_natural_per.keys())))

    print("=" * 120)
    print("  STATION COMPARISON — Old vs New (interaction features + 9 stations)")
    if frozen_station_ids:
        print("  New model evaluated on frozen old test-set timestamps (*) for fair comparison.")
    print("=" * 120)
    header = (
        f"{'Station':<28} {'Old RMSE':>10} {'Old Winner':>14} "
        f"{'New RMSE*':>10} {'New Winner*':>14} {'Official RMSE':>14} Flag"
    )
    print(header)
    print("-" * 120)

    for sid in all_sids:
        old_ps = old_per_station.get(sid, {})
        frozen_ps = new_frozen_per.get(sid, {})
        natural_ps = new_natural_per.get(sid, {})

        old_rmse = old_ps.get("lightgbm_rmse")
        old_winner = old_ps.get("model_selected_for_serving", "—")

        new_rmse_frozen = frozen_ps.get("lightgbm_rmse")
        new_winner_frozen = frozen_ps.get("model_selected_for_serving", "—")

        official_rmse = natural_ps.get("lightgbm_rmse")

        old_rmse_str = f"{old_rmse:.2f}" if old_rmse is not None else "—"
        new_rmse_str = f"{new_rmse_frozen:.2f}" if new_rmse_frozen is not None else "—"
        official_rmse_str = f"{official_rmse:.2f}" if official_rmse is not None else "—"

        flag = ""
        if (
            sid in frozen_station_ids
            and old_rmse is not None
            and new_rmse_frozen is not None
        ):
            rmse_worse = new_rmse_frozen > old_rmse + 0.005
            win_flip = old_winner == "lightgbm" and new_winner_frozen == "persistence"
            if rmse_worse or win_flip:
                flag = " [REGRESSION]"

        print(
            f"{sid:<28} {old_rmse_str:>10} {old_winner:>14} "
            f"{new_rmse_str:>10} {new_winner_frozen:>14} {official_rmse_str:>14}{flag}",
        )

    if frozen_station_ids:
        print("-" * 120)
        print(" * Evaluated on frozen old test-set timestamps for direct comparison")
    print("=" * 120)


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
    interaction_cols: list[str] = []
    old_eval: dict = {}
    old_test_timestamps: set = set()

    if dataset == DATASET_REAL_MULTISTATION:
        from pipeline.station_registry import get_registry_stations

        stations = [s for s in get_registry_stations() if s.forecast_eligible]
        station_ids = sorted(s.station_id for s in stations)
        logger.info(
            "Using %d forecast-eligible stations from registry: %s",
            len(station_ids), station_ids,
        )

        features, station_encoded_cols = encode_station_id(features, station_ids=station_ids)
        features, interaction_cols = add_station_interaction_features(features, station_encoded_cols)

        training_feature_columns = list(feature_columns) + station_encoded_cols + interaction_cols

        old_eval, old_test_timestamps = _load_old_evaluation(paths)
    else:
        training_feature_columns = list(feature_columns)
        features, station_encoded_cols = encode_station_id(features)

    train, validation, test = chronological_split(features)

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

    if dataset == DATASET_REAL_MULTISTATION:
        new_natural_metrics = _compute_per_station_metrics(test, training_feature_columns, model)

        new_frozen_metrics: dict = {"per_station": {}}
        frozen_station_ids: set = set()
        if old_test_timestamps:
            frozen_mask = features["timestamp"].isin(old_test_timestamps)
            frozen_test = features[frozen_mask].copy()
            if not frozen_test.empty:
                frozen_station_ids = set(frozen_test["station_id"].unique())
                new_frozen_metrics = _compute_per_station_metrics(
                    frozen_test, training_feature_columns, model,
                )

        _print_comparison(old_eval, new_frozen_metrics, new_natural_metrics, frozen_station_ids)

        timestamps = sorted(pd.to_datetime(test["timestamp"], utc=True).unique())
        split_boundaries = {
            "train_end": str(sorted(pd.to_datetime(train["timestamp"], utc=True).unique())[-1]),
            "validation_end": str(sorted(pd.to_datetime(validation["timestamp"], utc=True).unique())[-1]),
            "test_end": str(timestamps[-1]),
        }

        eval_metrics = {
            "task": "PM2.5 24-hour forecasting",
            "dataset": "real_multistation",
            "city": "Bengaluru",
            "split_strategy": "chronological 70/15/15 by unique timestamp (global)",
            "split_boundaries": split_boundaries,
            "selected_features": training_feature_columns,
            "total_test_rows": int(len(test)),
            **new_natural_metrics,
        }

        with paths.evaluation_metrics.open("w", encoding="utf-8") as f:
            json.dump(eval_metrics, f, indent=2)

        with paths.feature_columns.open("w", encoding="utf-8") as f:
            json.dump(feature_columns, f, indent=2)

        station_cols_path = paths.artifacts_dir / "station_feature_columns.json"
        with station_cols_path.open("w", encoding="utf-8") as f:
            json.dump(station_encoded_cols, f, indent=2)

        interaction_cols_path = paths.artifacts_dir / "station_interaction_columns.json"
        with interaction_cols_path.open("w", encoding="utf-8") as f:
            json.dump(interaction_cols, f, indent=2)

        predictions = pd.DataFrame({
            "timestamp": test["timestamp"].astype(str),
            "station_id": test["station_id"].astype(str),
            "actual_pm25": test[TARGET_COLUMN].astype(float),
            "persistence_prediction": test["pm25_lag_24h"].astype(float),
            "lightgbm_prediction": model.predict(test[training_feature_columns]).astype(float),
        })
        predictions.to_csv(paths.test_predictions, index=False)

        logger.info("Wrote multi-station evaluation metrics to %s", paths.evaluation_metrics)
        logger.info(
            "Wrote %d interaction columns to %s",
            len(interaction_cols), interaction_cols_path,
        )
    else:
        with paths.feature_columns.open("w", encoding="utf-8") as f:
            json.dump(feature_columns, f, indent=2)
        if station_encoded_cols:
            station_cols_path = paths.artifacts_dir / "station_feature_columns.json"
            with station_cols_path.open("w", encoding="utf-8") as f:
                json.dump(station_encoded_cols, f, indent=2)

    joblib.dump(model, paths.lightgbm_model)
    logger.info("Wrote LightGBM model to %s", paths.lightgbm_model)
    if station_encoded_cols:
        logger.info(
            "Encoded station_id as %d one-hot features: %s",
            len(station_encoded_cols), station_encoded_cols,
        )
    if interaction_cols:
        logger.info(
            "Added %d station interaction features",
            len(interaction_cols),
        )
    return model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the LightGBM PM2.5 24-hour model.")
    parser.add_argument("--dataset", default=DATASET_SYNTHETIC, choices=["synthetic", "real_hebbal", "real_multistation"])
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    train_lightgbm(dataset=args.dataset)
