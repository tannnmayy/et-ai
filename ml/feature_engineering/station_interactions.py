from __future__ import annotations

import pandas as pd

INTERACTION_BASE_FEATURES = [
    "no2_lag_1h",
    "no2_lag_24h",
    "pm25_roll_std_24h",
    "hour_sin",
    "temperature_c",
]


def add_station_interaction_features(
    frame: pd.DataFrame,
    station_encoded_cols: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    interaction_cols: list[str] = []
    for feature in INTERACTION_BASE_FEATURES:
        if feature not in frame.columns:
            continue
        for dummy_col in station_encoded_cols:
            col_name = f"{feature}_x_{dummy_col}"
            frame[col_name] = frame[feature].fillna(0.0).where(frame[dummy_col] == 1, other=0.0)
            interaction_cols.append(col_name)
    return frame, interaction_cols
