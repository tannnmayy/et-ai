from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.common import DATASET_REAL_MULTISTATION, get_paths
from ml.feature_engineering.station_interactions import (
    INTERACTION_BASE_FEATURES,
    add_station_interaction_features,
)
from ml.train_lightgbm import (
    _compute_per_station_metrics,
    _load_old_evaluation,
    _print_comparison,
    encode_station_id,
    train_lightgbm,
)

FORECAST_ELIGIBLE_IDS = [
    "cpcb_hebbal",
    "cpcb_hombegowda",
    "cpcb_jayanagar5",
    "cpcb_silkboard",
    "cpcb_peenya",
    "cpcb_bapujinagar",
    "cpcb_btmlayout",
    "cpcb_kasturinagar",
    "cpcb_rvce_mailasandra",
]


def _make_synthetic_multistation_features(
    station_ids: list[str],
    n_timestamps: int = 200,
    base_pm25: float = 30.0,
) -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-01", periods=n_timestamps, freq="h", tz="UTC")
    rows: list[dict] = []
    for i, ts in enumerate(timestamps):
        for sid in station_ids:
            noise = np.random.default_rng(seed=hash(f"{sid}_{i}") % (2**31)).normal(0, 5)
            pm25_val = base_pm25 + noise + 10 * (i % 24)
            rows.append({
                "timestamp": ts,
                "station_id": sid,
                "pm25_lag_1h": pm25_val - 1,
                "pm25_lag_3h": pm25_val - 3,
                "pm25_lag_6h": pm25_val - 6,
                "pm25_lag_12h": pm25_val - 12,
                "pm25_lag_24h": pm25_val - 24,
                "pm10_lag_1h": pm25_val * 1.5,
                "pm10_lag_24h": pm25_val * 1.5 - 10,
                "no2_lag_1h": pm25_val * 0.3,
                "no2_lag_24h": pm25_val * 0.3 - 2,
                "temperature_c": 25.0 + np.sin(i / 24 * 2 * np.pi) * 5,
                "relative_humidity": 60.0,
                "rainfall_mm": 0.0,
                "hour_sin": np.sin(i / 24 * 2 * np.pi),
                "hour_cos": np.cos(i / 24 * 2 * np.pi),
                "weekday_sin": np.sin(i / 7 * 2 * np.pi),
                "weekday_cos": np.cos(i / 7 * 2 * np.pi),
                "hour": i % 24,
                "weekday": i % 7,
                "month": 1,
                "pm25_roll_mean_3h": pm25_val - 2,
                "pm25_roll_mean_6h": pm25_val - 4,
                "pm25_roll_mean_24h": pm25_val - 8,
                "pm25_roll_std_24h": 5.0 + np.random.default_rng(seed=hash(f"std_{sid}_{i}") % (2**31)).random() * 3,
                "target_pm25_24h": pm25_val + 2,
            })
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values(["timestamp", "station_id"]).reset_index(drop=True)


class TestStationInteractionFeatures:

    def test_add_station_interaction_features_produces_correct_columns(self):
        station_ids = ["cpcb_a", "cpcb_b"]
        n = 20
        frame = pd.DataFrame({
            "station_id": station_ids * n,
            "no2_lag_1h": range(n * 2),
            "no2_lag_24h": range(10, n * 2 + 10),
            "pm25_roll_std_24h": range(20, n * 2 + 20),
            "hour_sin": [0.5] * (n * 2),
            "temperature_c": [25.0] * (n * 2),
            "dummy": [0] * (n * 2),
        })
        frame.loc[:n - 1, "station_id"] = "cpcb_a"
        frame.loc[n:, "station_id"] = "cpcb_b"

        encoded_frame, station_cols = encode_station_id(frame, station_ids=station_ids)
        result_frame, interaction_cols = add_station_interaction_features(encoded_frame, station_cols)

        expected_count = len(INTERACTION_BASE_FEATURES) * len(station_ids)
        assert len(interaction_cols) == expected_count

        for feature in INTERACTION_BASE_FEATURES:
            for dummy in station_cols:
                col_name = f"{feature}_x_{dummy}"
                assert col_name in result_frame.columns

        row_a = result_frame[result_frame["is_station_cpcb_a"] == 1].iloc[0]
        row_b = result_frame[result_frame["is_station_cpcb_b"] == 1].iloc[0]

        assert row_a["no2_lag_1h_x_is_station_cpcb_a"] == row_a["no2_lag_1h"]
        assert row_a["no2_lag_1h_x_is_station_cpcb_b"] == 0.0
        assert row_b["no2_lag_1h_x_is_station_cpcb_b"] == row_b["no2_lag_1h"]
        assert row_b["no2_lag_1h_x_is_station_cpcb_a"] == 0.0

    def test_add_station_interaction_features_nan_handling(self):
        frame = pd.DataFrame({
            "station_id": ["cpcb_a", "cpcb_b"],
            "no2_lag_1h": [5.0, 10.0],
            "no2_lag_24h": [3.0, 8.0],
            "pm25_roll_std_24h": [4.0, 6.0],
            "hour_sin": [0.0, 1.0],
            "temperature_c": [float("nan"), 25.0],
        })
        encoded_frame, station_cols = encode_station_id(frame, station_ids=["cpcb_a", "cpcb_b"])
        result_frame, interaction_cols = add_station_interaction_features(encoded_frame, station_cols)

        row_a = result_frame[result_frame["is_station_cpcb_a"] == 1].iloc[0]
        assert row_a["temperature_c_x_is_station_cpcb_a"] == 0.0
        assert not np.isnan(row_a["temperature_c_x_is_station_cpcb_a"])

        row_b = result_frame[result_frame["is_station_cpcb_b"] == 1].iloc[0]
        assert row_b["temperature_c_x_is_station_cpcb_b"] == 25.0


class TestEncodeStationId:

    def test_encode_station_id_explicit_list(self):
        frame = pd.DataFrame({"station_id": ["cpcb_x", "cpcb_y", "cpcb_z"]})
        encoded, cols = encode_station_id(frame, station_ids=["cpcb_y", "cpcb_x"])
        assert cols == ["is_station_cpcb_x", "is_station_cpcb_y"]
        assert "is_station_cpcb_z" not in frame.columns

    def test_encode_station_id_fallback_warning(self):
        frame = pd.DataFrame({"station_id": ["cpcb_a", "cpcb_b"]})
        encoded, cols = encode_station_id(frame)
        assert set(cols) == {"is_station_cpcb_a", "is_station_cpcb_b"}


class TestComparisonOutput:

    def test_comparison_flags_rmse_regression(self, capsys):
        old_eval = {
            "per_station": {
                "station_A": {"lightgbm_rmse": 10.0, "model_selected_for_serving": "lightgbm"},
                "station_B": {"lightgbm_rmse": 15.0, "model_selected_for_serving": "persistence"},
            },
        }
        new_frozen = {
            "per_station": {
                "station_A": {"lightgbm_rmse": 15.0, "model_selected_for_serving": "persistence"},
                "station_B": {"lightgbm_rmse": 12.0, "model_selected_for_serving": "lightgbm"},
            },
        }
        new_natural = {
            "per_station": {
                "station_A": {"lightgbm_rmse": 14.5, "model_selected_for_serving": "lightgbm"},
                "station_B": {"lightgbm_rmse": 11.5, "model_selected_for_serving": "lightgbm"},
            },
        }
        _print_comparison(old_eval, new_frozen, new_natural, frozen_station_ids={"station_A", "station_B"})
        captured = capsys.readouterr().out
        assert "[REGRESSION]" in captured
        assert "station_A" in captured

    def test_comparison_no_regression_when_improved(self, capsys):
        old_eval = {
            "per_station": {
                "station_A": {"lightgbm_rmse": 10.0, "model_selected_for_serving": "lightgbm"},
            },
        }
        new_frozen = {
            "per_station": {
                "station_A": {"lightgbm_rmse": 8.0, "model_selected_for_serving": "lightgbm"},
            },
        }
        new_natural = {
            "per_station": {
                "station_A": {"lightgbm_rmse": 7.5, "model_selected_for_serving": "lightgbm"},
            },
        }
        _print_comparison(old_eval, new_frozen, new_natural, frozen_station_ids={"station_A"})
        captured = capsys.readouterr().out
        assert "[REGRESSION]" not in captured

    def test_comparison_flags_win_flip_regression(self, capsys):
        old_eval = {
            "per_station": {
                "station_X": {"lightgbm_rmse": 10.0, "model_selected_for_serving": "lightgbm"},
            },
        }
        new_frozen = {
            "per_station": {
                "station_X": {"lightgbm_rmse": 9.5, "model_selected_for_serving": "persistence"},
            },
        }
        new_natural = {
            "per_station": {
                "station_X": {"lightgbm_rmse": 9.0, "model_selected_for_serving": "lightgbm"},
            },
        }
        _print_comparison(old_eval, new_frozen, new_natural, frozen_station_ids={"station_X"})
        captured = capsys.readouterr().out
        assert "[REGRESSION]" in captured

    def test_comparison_handles_new_stations(self, capsys):
        old_eval = {
            "per_station": {
                "station_old": {"lightgbm_rmse": 10.0, "model_selected_for_serving": "lightgbm"},
            },
        }
        new_frozen = {
            "per_station": {
                "station_old": {"lightgbm_rmse": 9.0, "model_selected_for_serving": "lightgbm"},
                "station_new": {"lightgbm_rmse": 12.0, "model_selected_for_serving": "lightgbm"},
            },
        }
        new_natural = {
            "per_station": {
                "station_old": {"lightgbm_rmse": 8.5, "model_selected_for_serving": "lightgbm"},
                "station_new": {"lightgbm_rmse": 11.0, "model_selected_for_serving": "lightgbm"},
            },
        }
        _print_comparison(old_eval, new_frozen, new_natural, frozen_station_ids={"station_old", "station_new"})
        captured = capsys.readouterr().out
        assert "station_old" in captured
        assert "station_new" in captured
        assert "—" in captured or "old" in captured.lower()


class TestNineStationTraining:

    def test_all_9_forecast_eligible_stations_in_evaluation(self):
        features = _make_synthetic_multistation_features(
            FORECAST_ELIGIBLE_IDS, n_timestamps=300,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = get_paths(root, dataset=DATASET_REAL_MULTISTATION)
            paths.artifacts_dir.mkdir(parents=True, exist_ok=True)

            feature_cols = [
                "pm25_lag_1h", "pm25_lag_3h", "pm25_lag_6h", "pm25_lag_12h", "pm25_lag_24h",
                "hour", "weekday", "month", "hour_sin", "hour_cos",
                "weekday_sin", "weekday_cos",
                "pm10_lag_1h", "pm10_lag_24h", "no2_lag_1h", "no2_lag_24h",
                "temperature_c", "relative_humidity", "rainfall_mm",
                "pm25_roll_mean_3h", "pm25_roll_mean_6h", "pm25_roll_mean_24h", "pm25_roll_std_24h",
            ]

            from pipeline.storage import write_parquet
            write_parquet(features, paths.processed_features)
            with paths.feature_columns.open("w", encoding="utf-8") as f:
                json.dump(feature_cols, f)

            train_lightgbm(root, dataset=DATASET_REAL_MULTISTATION)

            assert paths.evaluation_metrics.exists()
            with paths.evaluation_metrics.open("r", encoding="utf-8") as f:
                metrics = json.load(f)

            assert metrics["station_count"] == 9
            assert set(metrics["per_station"].keys()) == set(FORECAST_ELIGIBLE_IDS)

            interaction_cols_path = paths.artifacts_dir / "station_interaction_columns.json"
            assert interaction_cols_path.exists()
            with interaction_cols_path.open("r", encoding="utf-8") as f:
                interaction_cols = json.load(f)

            expected_count = len(INTERACTION_BASE_FEATURES) * 9
            assert len(interaction_cols) == expected_count


class TestLoadOldEvaluation:

    def test_load_old_evaluation_no_files(self, tmp_path):
        old_eval, timestamps = _load_old_evaluation(get_paths(tmp_path))
        assert old_eval == {}
        assert timestamps == set()

    def test_load_old_evaluation_with_files(self, tmp_path):
        paths = get_paths(tmp_path)
        paths.artifacts_dir.mkdir(parents=True, exist_ok=True)

        mock_eval = {"per_station": {"A": {"rmse": 10.0}}}
        with paths.evaluation_metrics.open("w", encoding="utf-8") as f:
            json.dump(mock_eval, f)

        pd.DataFrame({
            "timestamp": ["2025-01-01 00:00:00+00:00", "2025-01-01 01:00:00+00:00"],
            "station_id": ["A", "B"],
            "actual_pm25": [10.0, 20.0],
            "persistence_prediction": [12.0, 22.0],
            "lightgbm_prediction": [11.0, 21.0],
        }).to_csv(paths.test_predictions, index=False)

        old_eval, timestamps = _load_old_evaluation(paths)
        assert old_eval == mock_eval
        assert len(timestamps) == 2
