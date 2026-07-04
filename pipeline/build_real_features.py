from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ml.common import (
    DATASET_REAL_HEBBAL,
    MANDATORY_REAL_FEATURES,
    OPTIONAL_REAL_FEATURES,
    TARGET_COLUMN,
    get_paths,
)
from pipeline.storage import read_parquet, write_parquet

logger = logging.getLogger(__name__)

PM25_LAG_HOURS = [1, 3, 6, 12, 24]
POLLUTANT_LAGS = {"pm10": [1, 24], "no2": [1, 24]}
ROLL_WINDOWS = [3, 6, 24]


def exact_lag(frame: pd.DataFrame, column: str, hours: int) -> pd.Series:
    lookup = frame[["timestamp_utc", "station_id", column]].rename(
        columns={column: f"{column}_lag_{hours}h", "timestamp_utc": "lookup_timestamp"}
    )
    lookup["timestamp_utc"] = lookup["lookup_timestamp"] + pd.Timedelta(hours=hours)
    merged = frame[["timestamp_utc", "station_id"]].merge(
        lookup[["timestamp_utc", "station_id", f"{column}_lag_{hours}h"]],
        on=["timestamp_utc", "station_id"],
        how="left",
    )
    return merged[f"{column}_lag_{hours}h"]


def exact_target(frame: pd.DataFrame) -> pd.Series:
    lookup = frame[["timestamp_utc", "station_id", "pm25"]].rename(columns={"pm25": TARGET_COLUMN})
    lookup["timestamp_utc"] = lookup["timestamp_utc"] - pd.Timedelta(hours=24)
    merged = frame[["timestamp_utc", "station_id"]].merge(
        lookup,
        on=["timestamp_utc", "station_id"],
        how="left",
    )
    return merged[TARGET_COLUMN]


def gap_aware_rolling(frame: pd.DataFrame, column: str, window_hours: int, statistic: str) -> pd.Series:
    result = pd.Series(np.nan, index=frame.index)
    for _station_id, group in frame.groupby("station_id"):
        values: list[float | None] = []
        indexed = group.sort_values("timestamp_utc").set_index("timestamp_utc")
        for timestamp in indexed.index:
            window_start = timestamp - pd.Timedelta(hours=window_hours)
            prior_end = timestamp - pd.Timedelta(hours=1)
            window_values = indexed.loc[(indexed.index >= window_start) & (indexed.index <= prior_end), column].dropna()
            if len(window_values) < window_hours:
                values.append(np.nan)
            elif statistic == "mean":
                values.append(float(window_values.mean()))
            elif statistic == "std":
                values.append(float(window_values.std(ddof=0)))
            else:
                raise ValueError(f"Unsupported rolling statistic: {statistic}")
        station_result = pd.Series(values, index=group.sort_values("timestamp_utc").index)
        result.loc[station_result.index] = station_result
    return result


def select_training_features(
    candidate_rows: pd.DataFrame,
    completeness_threshold_percent: float = 60.0,
) -> tuple[list[str], dict[str, str]]:
    selected = list(MANDATORY_REAL_FEATURES)
    excluded: dict[str, str] = {}
    threshold = completeness_threshold_percent / 100.0
    for feature in OPTIONAL_REAL_FEATURES:
        if feature not in candidate_rows.columns:
            excluded[feature] = "column not built"
            continue
        completeness = candidate_rows[feature].notna().mean()
        if completeness >= threshold:
            selected.append(feature)
        else:
            excluded[feature] = f"completeness {completeness * 100:.1f}% below {completeness_threshold_percent:.0f}% threshold"
    return selected, excluded


def create_real_features(hourly: pd.DataFrame, completeness_threshold_percent: float = 60.0) -> tuple[pd.DataFrame, dict]:
    frame = hourly.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    frame = frame.sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)

    for hours in PM25_LAG_HOURS:
        frame[f"pm25_lag_{hours}h"] = exact_lag(frame, "pm25", hours)
    for column, lags in POLLUTANT_LAGS.items():
        for hours in lags:
            frame[f"{column}_lag_{hours}h"] = exact_lag(frame, column, hours)

    for window in ROLL_WINDOWS:
        frame[f"pm25_roll_mean_{window}h"] = gap_aware_rolling(frame, "pm25", window, "mean")
    frame["pm25_roll_std_24h"] = gap_aware_rolling(frame, "pm25", 24, "std")

    local = frame["timestamp_utc"].dt.tz_convert("Asia/Kolkata")
    frame["hour"] = local.dt.hour
    frame["weekday"] = local.dt.weekday
    frame["month"] = local.dt.month
    frame["hour_sin"] = np.sin(2 * np.pi * frame["hour"] / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * frame["hour"] / 24)
    frame["weekday_sin"] = np.sin(2 * np.pi * frame["weekday"] / 7)
    frame["weekday_cos"] = np.cos(2 * np.pi * frame["weekday"] / 7)
    frame[TARGET_COLUMN] = exact_target(frame)
    frame["timestamp"] = frame["timestamp_utc"]

    candidate_rows = frame.dropna(subset=[TARGET_COLUMN] + MANDATORY_REAL_FEATURES).copy()
    selected_features, excluded_features = select_training_features(candidate_rows, completeness_threshold_percent)
    required = [TARGET_COLUMN] + MANDATORY_REAL_FEATURES
    features = candidate_rows.dropna(subset=required).reset_index(drop=True)

    metadata = {
        "dataset": DATASET_REAL_HEBBAL,
        "selected_features": selected_features,
        "excluded_features": excluded_features,
        "completeness_threshold_percent": completeness_threshold_percent,
        "timestamp_gap_policy": "exact timestamp alignment; no forward fill",
    }
    return features, metadata


def build_real_features(
    input_path: Path | None = None,
    output_path: Path | None = None,
    metadata_path: Path | None = None,
    feature_columns_path: Path | None = None,
    completeness_threshold_percent: float = 60.0,
    project_root: Path | None = None,
) -> pd.DataFrame:
    paths = get_paths(project_root, dataset=DATASET_REAL_HEBBAL)
    input_path = Path(input_path or paths.processed_hourly)
    output_path = Path(output_path or paths.processed_features)
    metadata_path = Path(metadata_path or paths.feature_metadata)
    feature_columns_path = Path(feature_columns_path or paths.feature_columns)

    hourly = read_parquet(input_path)
    features, metadata = create_real_features(hourly, completeness_threshold_percent=completeness_threshold_percent)
    write_parquet(features, output_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    feature_columns_path.write_text(json.dumps(metadata["selected_features"], indent=2), encoding="utf-8")
    logger.info("Wrote %s real feature rows to %s", len(features), output_path)
    return features


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build gap-aware real-data PM2.5 features.")
    parser.add_argument("--completeness-threshold-percent", type=float, default=60.0)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    build_real_features(completeness_threshold_percent=args.completeness_threshold_percent)


if __name__ == "__main__":
    main()
