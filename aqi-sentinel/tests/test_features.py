import pandas as pd

from pipeline.build_features import create_features


def _known_raw(hours: int = 60) -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-01T00:00:00Z", periods=hours, freq="h")
    pm25 = list(range(hours))
    return pd.DataFrame(
        {
            "timestamp": timestamps.astype(str),
            "station_id": "TEST",
            "station_name": "Known Station",
            "latitude": 12.0,
            "longitude": 77.0,
            "pm25": pm25,
            "pm10": [value * 2 for value in pm25],
            "no2": [value + 10 for value in pm25],
            "temperature_c": 25.0,
            "relative_humidity": 60.0,
            "wind_speed_mps": 2.0,
            "rainfall_mm": 0.0,
            "hour": timestamps.hour,
            "weekday": timestamps.weekday,
            "month": timestamps.month,
        }
    )


def test_target_pm25_24h_uses_future_target_only():
    features = create_features(_known_raw())
    row = features.loc[features["timestamp"] == pd.Timestamp("2025-01-02T00:00:00Z")].iloc[0]
    assert row["pm25_lag_24h"] == 0
    assert row["target_pm25_24h"] == 48


def test_rolling_features_use_only_past_values():
    raw = _known_raw()
    raw.loc[24, "pm25"] = 999
    features = create_features(raw)
    row = features.loc[features["timestamp"] == pd.Timestamp("2025-01-02T00:00:00Z")].iloc[0]
    assert row["pm25_roll_mean_3h"] == 22
    assert row["pm25_roll_mean_3h"] != (21 + 22 + 999) / 3
