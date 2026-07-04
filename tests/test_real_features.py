from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from ml.common import DATASET_REAL_HEBBAL, get_paths
from ml.evaluate import evaluate_models
from ml.train_lightgbm import train_lightgbm
from ml.train_persistence_baseline import train_persistence_baseline
from pipeline.build_real_features import create_real_features
from pipeline.cpcb_csv_adapter import CPCBStationConfig
from pipeline.ingest_cpcb_csv import aggregate_to_hourly, ingest_cpcb_csv


def _hourly_fixture() -> pd.DataFrame:
    timestamps = pd.to_datetime(
        [
            "2025-01-01T00:00:00Z",
            "2025-01-01T01:00:00Z",
            "2025-01-01T02:00:00Z",
            "2025-01-02T00:00:00Z",
            "2025-01-02T01:00:00Z",
            "2025-01-02T02:00:00Z",
        ],
        utc=True,
    )
    return pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "station_id": ["cpcb_hebbal"] * len(timestamps),
            "station_name": ["Hebbal, Bengaluru - KSPCB"] * len(timestamps),
            "latitude": [13.0358] * len(timestamps),
            "longitude": [77.5970] * len(timestamps),
            "pm25": [10, 20, 30, 40, 50, 60],
            "pm10": [20, 30, 40, 50, 60, 70],
            "no2": [5, 6, 7, 8, 9, 10],
            "temperature_c": [25, 25, 26, 24, 24, 23],
            "relative_humidity": [60, 61, 62, 63, 64, 65],
            "wind_speed_mps": [1, 1.1, 1.2, 1.3, 1.4, 1.5],
            "rainfall_mm": [0, 0, 0, 0, 0, 0],
            "observations_per_hour": [4] * len(timestamps),
            "pm25_observations_per_hour": [4] * len(timestamps),
            "pm10_observations_per_hour": [4] * len(timestamps),
            "no2_observations_per_hour": [4] * len(timestamps),
            "weather_observations_per_hour": [4] * len(timestamps),
            "source": ["CPCB/KSPCB 15-minute station export"] * len(timestamps),
        }
    )


def _make_continuous_hourly(start: str, hours: int, base_pm25: float = 10.0) -> pd.DataFrame:
    timestamps = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    n = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "station_id": ["cpcb_hebbal"] * n,
            "station_name": ["Hebbal, Bengaluru - KSPCB"] * n,
            "latitude": [13.0358] * n,
            "longitude": [77.5970] * n,
            "pm25": [base_pm25 + i for i in range(n)],
            "pm10": [base_pm25 + 10 + i for i in range(n)],
            "no2": [5 + (i % 10) for i in range(n)],
            "temperature_c": [25.0] * n,
            "relative_humidity": [60.0] * n,
            "wind_speed_mps": [1.0] * n,
            "rainfall_mm": [0.0] * n,
            "observations_per_hour": [4] * n,
            "pm25_observations_per_hour": [4] * n,
            "pm10_observations_per_hour": [4] * n,
            "no2_observations_per_hour": [4] * n,
            "weather_observations_per_hour": [4] * n,
            "source": ["CPCB/KSPCB 15-minute station export"] * n,
        }
    )


def test_hourly_pm25_median_aggregation():
    cleaned = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(
                [
                    "2025-01-01T00:00:00Z",
                    "2025-01-01T00:15:00Z",
                    "2025-01-01T00:30:00Z",
                    "2025-01-01T00:45:00Z",
                ],
                utc=True,
            ),
            "station_id": ["cpcb_hebbal"] * 4,
            "station_name": ["Hebbal"] * 4,
            "latitude": [13.0] * 4,
            "longitude": [77.0] * 4,
            "source": ["test"] * 4,
            "pm25": [10, 20, 30, 100],
            "pm10": [20, 20, 20, 20],
            "no2": [1, 1, 1, 1],
            "temperature_c": [25, 25, 25, 25],
            "relative_humidity": [60, 60, 60, 60],
            "wind_speed_mps": [1, 1, 1, 1],
            "rainfall_mm": [0, 0, 0, 0],
            "is_plausibility_flagged": [False] * 4,
            "source_timestamp": ["x"] * 4,
            "source_timezone": ["Asia/Kolkata"] * 4,
        }
    )
    hourly, excluded = aggregate_to_hourly(cleaned, min_pm25_observations_per_hour=2)
    assert excluded == 0
    assert hourly.iloc[0]["pm25"] == 25


def test_hour_excluded_when_fewer_than_two_pm25_observations():
    cleaned = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-01T00:15:00Z"], utc=True),
            "station_id": ["cpcb_hebbal"] * 2,
            "station_name": ["Hebbal"] * 2,
            "latitude": [13.0] * 2,
            "longitude": [77.0] * 2,
            "source": ["test"] * 2,
            "pm25": [10, pd.NA],
            "pm10": [20, 20],
            "no2": [1, 1],
            "temperature_c": [25, 25],
            "relative_humidity": [60, 60],
            "wind_speed_mps": [1, 1],
            "rainfall_mm": [0, 0],
            "is_plausibility_flagged": [False, False],
            "source_timestamp": ["x", "x"],
            "source_timezone": ["Asia/Kolkata"] * 2,
        }
    )
    hourly, excluded = aggregate_to_hourly(cleaned, min_pm25_observations_per_hour=2)
    assert excluded == 1
    assert pd.isna(hourly.iloc[0]["pm25"])


def test_exact_24h_lag_does_not_cross_gap():
    hourly = _make_continuous_hourly("2025-01-01T00:00:00Z", 97)
    features, _ = create_real_features(hourly)
    row = features.loc[features["timestamp_utc"] == pd.Timestamp("2025-01-02T12:00:00Z")].iloc[0]
    assert row["pm25_lag_24h"] == 22.0


def test_exact_24h_target_does_not_cross_gap():
    hourly = _make_continuous_hourly("2025-01-01T00:00:00Z", 97)
    features, _ = create_real_features(hourly)
    row = features.loc[features["timestamp_utc"] == pd.Timestamp("2025-01-02T12:00:00Z")].iloc[0]
    assert row["target_pm25_24h"] == 70.0


def test_rolling_features_exclude_current_value():
    hourly = _make_continuous_hourly("2025-01-01T00:00:00Z", 97)
    features, _ = create_real_features(hourly)
    row = features.loc[features["timestamp_utc"] == pd.Timestamp("2025-01-02T00:00:00Z")].iloc[0]
    assert row["pm25_roll_mean_3h"] == pytest.approx(32.0)


def test_real_artifacts_written_only_under_real_hebbal(tmp_path, monkeypatch):
    monkeypatch.setenv("AQI_SENTINEL_PROJECT_ROOT", str(tmp_path))
    paths = get_paths(tmp_path, dataset=DATASET_REAL_HEBBAL)

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "Timestamp,PM2.5 (µg/m³),PM10 (µg/m³),NO (µg/m³),NO2 (µg/m³),AT (°C),RH (%),WS (m/s),RF (mm)\n"
        + "\n".join(
            f"2025-01-{(day % 28) + 1:02d} {hour:02d}:{minute:02d}:00,{40 + hour},{80 + hour},NA,{10 + hour},25,60,1.0,0.0"
            for day in range(30)
            for hour in range(24)
            for minute in (0, 15, 30, 45)
        ),
        encoding="utf-8",
    )

    station = CPCBStationConfig(station_id="cpcb_hebbal", station_name="Hebbal, Bengaluru - KSPCB")
    ingest_cpcb_csv(
        input_path=csv_path,
        station=station,
        output_15min=paths.cleaned_15min,
        output_hourly=paths.processed_hourly,
        report_csv=paths.quality_report_csv,
        report_md=paths.quality_report_md,
        quality_summary=paths.data_quality_summary,
    )

    from pipeline.build_real_features import build_real_features

    build_real_features()
    train_persistence_baseline(tmp_path, dataset=DATASET_REAL_HEBBAL)
    train_lightgbm(tmp_path, dataset=DATASET_REAL_HEBBAL)
    evaluate_models(tmp_path, dataset=DATASET_REAL_HEBBAL)

    assert paths.lightgbm_model.exists()
    assert paths.lightgbm_model.parent.name == "real_hebbal"
    assert (tmp_path / "ml" / "artifacts" / "real_hebbal" / "evaluation_metrics.json").exists()


def test_real_hebbal_endpoint_returns_503_without_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("AQI_SENTINEL_PROJECT_ROOT", str(tmp_path))
    response = TestClient(app).get("/forecast/real/hebbal")
    assert response.status_code == 503
    assert "ingest_cpcb_csv" in response.json()["detail"]


def test_real_hebbal_endpoint_returns_valid_response_after_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("AQI_SENTINEL_PROJECT_ROOT", str(tmp_path))
    paths = get_paths(tmp_path, dataset=DATASET_REAL_HEBBAL)
    raw_csv = paths.raw_data
    raw_csv.parent.mkdir(parents=True, exist_ok=True)
    raw_csv.write_text(
        "Timestamp,PM2.5 (µg/m³),PM10 (µg/m³),NO (µg/m³),NO2 (µg/m³),AT (°C),RH (%),WS (m/s),RF (mm)\n"
        + "\n".join(
            f"2025-01-{(day % 28) + 1:02d} {hour:02d}:{minute:02d}:00,{40 + hour},{80 + hour},NA,{10 + hour},25,60,1.0,0.0"
            for day in range(30)
            for hour in range(24)
            for minute in (0, 15, 30, 45)
        ),
        encoding="utf-8",
    )
    station = CPCBStationConfig(station_id="cpcb_hebbal", station_name="Hebbal, Bengaluru - KSPCB")
    ingest_cpcb_csv(
        input_path=raw_csv,
        station=station,
        output_15min=paths.cleaned_15min,
        output_hourly=paths.processed_hourly,
        report_csv=paths.quality_report_csv,
        report_md=paths.quality_report_md,
        quality_summary=paths.data_quality_summary,
    )
    from pipeline.build_real_features import build_real_features

    build_real_features(project_root=tmp_path)
    train_persistence_baseline(tmp_path, dataset=DATASET_REAL_HEBBAL)
    train_lightgbm(tmp_path, dataset=DATASET_REAL_HEBBAL)
    evaluate_models(tmp_path, dataset=DATASET_REAL_HEBBAL)

    response = TestClient(app).get("/forecast/real/hebbal")
    assert response.status_code == 200
    payload = response.json()
    assert payload["station_id"] == "cpcb_hebbal"
    assert payload["data_mode"] == "real_cpcb_kspcb_csv"
    assert payload["forecast_engine"] in {"lightgbm", "persistence_fallback"}
    assert payload["data_quality_classification"]
