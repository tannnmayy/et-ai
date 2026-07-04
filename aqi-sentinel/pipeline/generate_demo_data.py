from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ml.common import get_paths
from pipeline.storage import write_csv

logger = logging.getLogger(__name__)

STATIONS = [
    {"station_id": "BLR_BTM", "station_name": "BTM Layout", "latitude": 12.9166, "longitude": 77.6101, "base_pm25": 48.0},
    {"station_id": "BLR_WFD", "station_name": "Whitefield", "latitude": 12.9698, "longitude": 77.7500, "base_pm25": 42.0},
    {"station_id": "BLR_PNY", "station_name": "Peenya", "latitude": 13.0285, "longitude": 77.5197, "base_pm25": 58.0},
]


def _rush_peak(hour: np.ndarray, center: float, width: float, amplitude: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((hour - center) / width) ** 2)


def generate_demo_data(output_path: Path | None = None, days: int = 180, seed: int = 42) -> pd.DataFrame:
    if days < 180:
        raise ValueError("Synthetic demo data must cover at least 180 days.")

    rng = np.random.default_rng(seed)
    timestamps = pd.date_range("2025-01-01T00:00:00Z", periods=days * 24, freq="h")
    rows: list[pd.DataFrame] = []

    for station in STATIONS:
        hour = timestamps.hour.to_numpy()
        weekday = timestamps.weekday.to_numpy()
        month = timestamps.month.to_numpy()
        is_weekend = weekday >= 5

        morning = _rush_peak(hour, 8, 2.0, 18.0)
        evening = _rush_peak(hour, 19, 2.4, 22.0)
        weekday_boost = np.where(is_weekend, -6.0, 5.0)
        seasonal = 8.0 * np.cos((month - 1) / 12 * 2 * np.pi)

        temperature = 25.0 + 3.5 * np.sin((hour - 7) / 24 * 2 * np.pi) + rng.normal(0, 1.2, len(timestamps))
        humidity = 62.0 - 8.0 * np.sin((hour - 7) / 24 * 2 * np.pi) + rng.normal(0, 6.0, len(timestamps))
        humidity = np.clip(humidity, 35.0, 96.0)

        monsoon_probability = np.where(np.isin(month, [6, 7, 8, 9]), 0.22, 0.06)
        rain_event = rng.random(len(timestamps)) < monsoon_probability
        rainfall = np.where(rain_event, rng.gamma(shape=1.8, scale=2.2, size=len(timestamps)), 0.0)
        rainfall = np.round(np.clip(rainfall, 0.0, 28.0), 2)

        wind = 2.2 + 1.0 * np.sin((hour - 13) / 24 * 2 * np.pi) + rng.normal(0, 0.45, len(timestamps))
        wind = np.clip(wind, 0.2, 6.5)

        spikes = np.where(rng.random(len(timestamps)) < 0.025, rng.uniform(18.0, 55.0, len(timestamps)), 0.0)
        noise = rng.normal(0, 5.0, len(timestamps))
        pm25 = (
            station["base_pm25"]
            + morning
            + evening
            + weekday_boost
            + seasonal
            - 3.8 * rainfall
            - 4.2 * wind
            + spikes
            + noise
        )
        pm25 = np.clip(pm25, 8.0, 220.0)

        pm10 = np.clip(pm25 * 1.65 + rng.normal(0, 9.0, len(timestamps)) + rng.uniform(0, 12, len(timestamps)), 18.0, 360.0)
        no2 = np.clip(
            18.0 + 0.42 * morning + 0.55 * evening + np.where(is_weekend, -2.5, 3.5) + rng.normal(0, 3.2, len(timestamps)),
            5.0,
            95.0,
        )

        rows.append(
            pd.DataFrame(
                {
                    "timestamp": timestamps.astype(str),
                    "station_id": station["station_id"],
                    "station_name": station["station_name"],
                    "latitude": station["latitude"],
                    "longitude": station["longitude"],
                    "pm25": np.round(pm25, 2),
                    "pm10": np.round(pm10, 2),
                    "no2": np.round(no2, 2),
                    "temperature_c": np.round(temperature, 2),
                    "relative_humidity": np.round(humidity, 2),
                    "wind_speed_mps": np.round(wind, 2),
                    "rainfall_mm": rainfall,
                    "hour": hour,
                    "weekday": weekday,
                    "month": month,
                }
            )
        )

    data = pd.concat(rows, ignore_index=True).sort_values(["station_id", "timestamp"]).reset_index(drop=True)
    duplicate_count = data.duplicated(["station_id", "timestamp"]).sum()
    if duplicate_count:
        raise ValueError(f"Generated data contains {duplicate_count} duplicate station-hour rows.")

    output_path = Path(output_path or get_paths().raw_data)
    write_csv(data, output_path)
    logger.info("Wrote %s rows of synthetic air-quality data to %s", len(data), output_path)
    return data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    generate_demo_data()
