from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ml.common import FEATURE_COLUMNS, TARGET_COLUMN, get_paths
from pipeline.storage import read_csv, validate_columns, write_parquet

logger = logging.getLogger(__name__)

RAW_COLUMNS = {
    "timestamp",
    "station_id",
    "station_name",
    "latitude",
    "longitude",
    "pm25",
    "pm10",
    "no2",
    "temperature_c",
    "relative_humidity",
    "wind_speed_mps",
    "rainfall_mm",
    "hour",
    "weekday",
    "month",
}


def _shifted_rolling(frame: pd.DataFrame, column: str, window: int, statistic: str) -> pd.Series:
    grouped = frame.groupby("station_id", group_keys=False)
    shifted = grouped[column].shift(1)
    roller = shifted.groupby(frame["station_id"]).rolling(window=window, min_periods=window)
    if statistic == "mean":
        values = roller.mean()
    elif statistic == "std":
        values = roller.std()
    else:
        raise ValueError(f"Unsupported rolling statistic: {statistic}")
    return values.reset_index(level=0, drop=True)


def assert_no_future_leakage(raw: pd.DataFrame, features: pd.DataFrame) -> None:
    if features.empty:
        raise ValueError("Feature builder produced no rows after dropping incomplete lags/targets.")

    indexed = raw.set_index(["station_id", "timestamp"]).sort_index()
    sample = features.groupby("station_id", group_keys=False).head(3)
    for row in sample.itertuples(index=False):
        lag_24_timestamp = row.timestamp - pd.Timedelta(hours=24)
        target_timestamp = row.timestamp + pd.Timedelta(hours=24)
        expected_lag_24 = indexed.loc[(row.station_id, lag_24_timestamp), "pm25"]
        expected_target = indexed.loc[(row.station_id, target_timestamp), "pm25"]
        if not np.isclose(row.pm25_lag_24h, expected_lag_24):
            raise AssertionError("pm25_lag_24h does not match the value 24 hours before the prediction origin.")
        if not np.isclose(row.target_pm25_24h, expected_target):
            raise AssertionError("target_pm25_24h does not match the value 24 hours after the prediction origin.")


def create_features(raw: pd.DataFrame) -> pd.DataFrame:
    validate_columns(raw, RAW_COLUMNS, "raw air-quality data")
    frame = raw.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values(["station_id", "timestamp"]).reset_index(drop=True)

    duplicate_count = frame.duplicated(["station_id", "timestamp"]).sum()
    if duplicate_count:
        raise ValueError(f"Raw data contains {duplicate_count} duplicate station-hour rows.")

    grouped = frame.groupby("station_id", group_keys=False)
    for lag in [1, 3, 6, 12, 24]:
        frame[f"pm25_lag_{lag}h"] = grouped["pm25"].shift(lag)
    for column in ["pm10", "no2"]:
        frame[f"{column}_lag_1h"] = grouped[column].shift(1)
        frame[f"{column}_lag_24h"] = grouped[column].shift(24)

    frame["pm25_roll_mean_3h"] = _shifted_rolling(frame, "pm25", 3, "mean")
    frame["pm25_roll_mean_6h"] = _shifted_rolling(frame, "pm25", 6, "mean")
    frame["pm25_roll_mean_24h"] = _shifted_rolling(frame, "pm25", 24, "mean")
    frame["pm25_roll_std_24h"] = _shifted_rolling(frame, "pm25", 24, "std")

    frame["hour_sin"] = np.sin(2 * np.pi * frame["hour"] / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * frame["hour"] / 24)
    frame["weekday_sin"] = np.sin(2 * np.pi * frame["weekday"] / 7)
    frame["weekday_cos"] = np.cos(2 * np.pi * frame["weekday"] / 7)
    frame[TARGET_COLUMN] = grouped["pm25"].shift(-24)

    required_complete = FEATURE_COLUMNS + [TARGET_COLUMN, "pm25_lag_24h"]
    features = frame.dropna(subset=required_complete).reset_index(drop=True)
    assert_no_future_leakage(frame, features)
    return features


def build_features(input_path: Path | None = None, output_path: Path | None = None) -> pd.DataFrame:
    paths = get_paths()
    input_path = Path(input_path or paths.raw_data)
    output_path = Path(output_path or paths.processed_features)
    raw = read_csv(input_path, RAW_COLUMNS)
    features = create_features(raw)
    write_parquet(features, output_path)
    logger.info("Wrote %s feature rows to %s", len(features), output_path)
    return features


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_features()
