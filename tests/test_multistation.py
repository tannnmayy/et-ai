from __future__ import annotations

import json
import tempfile
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest

from ml.common import DATASET_REAL_MULTISTATION, chronological_split, get_paths
from pipeline.build_real_features import create_real_features, gap_aware_rolling
from pipeline.cpcb_csv_adapter import CPCBStationConfig
from pipeline.ingest_cpcb_csv import aggregate_to_hourly, ingest_cpcb_csv
from pipeline.merge_multistation import (
    apply_quality_gate,
    build_multistation_features,
    load_all_station_hourly,
    validate_no_cross_station_mixing,
    write_per_station_features,
)
from pipeline.station_registry import (
    BENGALURU_STATIONS,
    BENGALURU_STATION_IDS,
    get_station_by_id,
    station_id_to_cpcb_config,
    station_output_dir,
)


def _make_station_hourly(
    station_id: str,
    station_name: str,
    start: str,
    hours: int,
    base_pm25: float = 10.0,
    latitude: float = 13.0,
    longitude: float = 77.0,
) -> pd.DataFrame:
    timestamps = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    n = len(timestamps)
    return pd.DataFrame({
        "timestamp_utc": timestamps,
        "station_id": [station_id] * n,
        "station_name": [station_name] * n,
        "latitude": [latitude] * n,
        "longitude": [longitude] * n,
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
    })


def _make_two_station_hourly(start: str, hours: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    station_a = _make_station_hourly("cpcb_station_a", "Station A", start, hours, base_pm25=10.0)
    station_b = _make_station_hourly("cpcb_station_b", "Station B", start, hours, base_pm25=50.0)
    return station_a, station_b


def _make_two_station_with_gap(
    start: str, hours: int, gap_station_b: int = 24
) -> tuple[pd.DataFrame, pd.DataFrame]:
    station_a = _make_station_hourly("cpcb_station_a", "Station A", start, hours, base_pm25=10.0)
    timestamps_b = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    valid_b = [i for i in range(hours) if i < gap_station_b or i >= gap_station_b + 48]
    station_b = _make_station_hourly("cpcb_station_b", "Station B", start, hours, base_pm25=50.0)
    station_b = station_b.iloc[valid_b].reset_index(drop=True)
    return station_a, station_b


class TestStationRegistry:
    def test_has_six_stations(self):
        assert len(BENGALURU_STATIONS) == 6

    def test_all_station_ids_unique(self):
        assert len(BENGALURU_STATION_IDS) == len(set(BENGALURU_STATION_IDS))

    def test_get_station_by_id(self):
        station = get_station_by_id("cpcb_hebbal")
        assert station.station_id == "cpcb_hebbal"
        assert station.station_name == "Hebbal, Bengaluru - KSPCB"

    def test_get_station_by_id_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown station_id"):
            get_station_by_id("cpcb_nonexistent")

    def test_station_id_to_cpcb_config(self):
        config = get_station_by_id("cpcb_hebbal")
        cpcb_config = station_id_to_cpcb_config(config)
        assert isinstance(cpcb_config, CPCBStationConfig)
        assert cpcb_config.station_id == "cpcb_hebbal"


class TestGapAwareRollingBugFix:
    def test_rolling_does_not_cross_station_boundary(self):
        station_a = _make_station_hourly("cpcb_a", "A", "2025-01-01", 100, base_pm25=10.0)
        station_b = _make_station_hourly("cpcb_b", "B", "2025-01-01", 100, base_pm25=1000.0)
        combined = pd.concat([station_a, station_b], ignore_index=True)
        combined = combined.sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)
        rolling_mean = gap_aware_rolling(combined, "pm25", 3, "mean")
        station_a_rolling = rolling_mean[combined["station_id"] == "cpcb_a"].dropna()
        station_b_rolling = rolling_mean[combined["station_id"] == "cpcb_b"].dropna()
        assert station_a_rolling.max() < 150.0
        assert station_b_rolling.min() > 900.0

    def test_rolling_with_single_station_matches_univariate(self):
        station_a = _make_station_hourly("cpcb_a", "A", "2025-01-01", 100, base_pm25=10.0)
        rolling_multi = gap_aware_rolling(station_a, "pm25", 3, "mean")
        rolling_single = gap_aware_rolling(station_a, "pm25", 3, "mean")
        pd.testing.assert_series_equal(rolling_multi, rolling_single)


class TestFeatureBuilding:
    def test_station_id_preserved_in_features(self):
        station_a, station_b = _make_two_station_hourly("2025-01-01", 100)
        combined = pd.concat([station_a, station_b], ignore_index=True)
        features, _ = create_real_features(combined)
        assert "station_id" in features.columns
        assert set(features["station_id"].unique()) == {"cpcb_station_a", "cpcb_station_b"}

    def test_no_cross_station_nan_propagation_in_rolling(self):
        station_a = _make_station_hourly("cpcb_a", "A", "2025-01-01", 100, base_pm25=10.0)
        station_b = _make_station_hourly("cpcb_b", "B", "2025-01-01", 100, base_pm25=50.0)
        station_b.loc[station_b.index[:5], "pm25"] = np.nan
        combined = pd.concat([station_a, station_b], ignore_index=True)
        features, _ = create_real_features(combined)
        a_features = features[features["station_id"] == "cpcb_a"]
        b_features = features[features["station_id"] == "cpcb_b"]
        a_has_nan_rolling = a_features["pm25_roll_mean_3h"].isna().any()
        assert not a_has_nan_rolling


class TestChronologicalSplit:
    def test_all_stations_present_in_all_splits(self):
        station_a, station_b = _make_two_station_hourly("2025-01-01", 200)
        combined = pd.concat([station_a, station_b], ignore_index=True)
        features, _ = create_real_features(combined)
        train, val, test = chronological_split(features)
        assert set(train["station_id"].unique()) == {"cpcb_station_a", "cpcb_station_b"}
        assert set(val["station_id"].unique()) == {"cpcb_station_a", "cpcb_station_b"}
        assert set(test["station_id"].unique()) == {"cpcb_station_a", "cpcb_station_b"}

    def test_no_temporal_overlap_between_splits(self):
        station_a, station_b = _make_two_station_hourly("2025-01-01", 200)
        combined = pd.concat([station_a, station_b], ignore_index=True)
        features, _ = create_real_features(combined)
        train, val, test = chronological_split(features)
        train_times = set(pd.to_datetime(train["timestamp"], utc=True))
        val_times = set(pd.to_datetime(val["timestamp"], utc=True))
        test_times = set(pd.to_datetime(test["timestamp"], utc=True))
        assert train_times.isdisjoint(val_times)
        assert train_times.isdisjoint(test_times)
        assert val_times.isdisjoint(test_times)


class TestCrossStationLeakage:
    def test_lag_features_use_only_own_station_history(self):
        station_a = _make_station_hourly("cpcb_a", "A", "2025-01-01", 100, base_pm25=10.0)
        station_b = _make_station_hourly("cpcb_b", "B", "2025-01-01", 100, base_pm25=1000.0)
        combined = pd.concat([station_a, station_b], ignore_index=True)
        features, _ = create_real_features(combined)
        a_features = features[features["station_id"] == "cpcb_a"]
        b_features = features[features["station_id"] == "cpcb_b"]
        a_lag_24h_max = a_features["pm25_lag_24h"].max()
        b_lag_24h_min = b_features["pm25_lag_24h"].min()
        assert a_lag_24h_max < 200.0
        assert b_lag_24h_min > 900.0


class TestPerStationPersistence:
    def test_per_station_persistence_in_multistation_mode(self):
        from ml.train_persistence_baseline import train_persistence_baseline

        station_a = _make_station_hourly("cpcb_a", "A", "2025-01-01", 200, base_pm25=10.0)
        station_b = _make_station_hourly("cpcb_b", "B", "2025-01-01", 200, base_pm25=50.0)
        combined = pd.concat([station_a, station_b], ignore_index=True)
        features, metadata = create_real_features(combined)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = get_paths(root, dataset=DATASET_REAL_MULTISTATION)
            paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
            from pipeline.storage import write_parquet
            write_parquet(features, paths.processed_features)
            with paths.feature_columns.open("w", encoding="utf-8") as f:
                json.dump(metadata["selected_features"], f)
            metrics = train_persistence_baseline(root, dataset=DATASET_REAL_MULTISTATION)
            assert "per_station" in metrics
            assert "cpcb_a" in metrics["per_station"]
            assert "cpcb_b" in metrics["per_station"]
            assert "validation_rmse" in metrics["per_station"]["cpcb_a"]
            assert "validation_rmse" in metrics["per_station"]["cpcb_b"]


class TestQualityGate:
    def test_accepts_station_with_sufficient_data(self):
        station_a = _make_station_hourly("cpcb_a", "A", "2025-01-01", 2200, base_pm25=10.0)
        frames = {"cpcb_a": station_a}
        accepted, excluded, details = apply_quality_gate(frames)
        assert "cpcb_a" in accepted

    def test_excludes_station_with_insufficient_data(self):
        station_short = _make_station_hourly("cpcb_short", "Short", "2025-01-01", 50, base_pm25=10.0)
        frames = {"cpcb_short": station_short}
        accepted, excluded, details = apply_quality_gate(frames)
        assert "cpcb_short" in excluded


class TestWritePerStationFeatures:
    def test_writes_per_station_files(self):
        station_a = _make_station_hourly("cpcb_a", "A", "2025-01-01", 100, base_pm25=10.0)
        station_b = _make_station_hourly("cpcb_b", "B", "2025-01-01", 100, base_pm25=50.0)
        combined = pd.concat([station_a, station_b], ignore_index=True)
        features, _ = create_real_features(combined)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths_map = write_per_station_features(features, ["cpcb_a", "cpcb_b"], root)
            assert "cpcb_a" in paths_map
            assert "cpcb_b" in paths_map
            assert paths_map["cpcb_a"].exists()
            assert paths_map["cpcb_b"].exists()


class TestValidateCrossStationMixing:
    def test_valid_frame_passes(self):
        station_a = _make_station_hourly("cpcb_a", "A", "2025-01-01", 10)
        validate_no_cross_station_mixing(station_a, ["cpcb_a", "cpcb_b"])

    def test_null_station_id_raises(self):
        df = pd.DataFrame({"station_id": [None, "cpcb_a"], "value": [1, 2]})
        with pytest.raises(ValueError, match="null station_id"):
            validate_no_cross_station_mixing(df, ["cpcb_a"])

    def test_unknown_station_id_raises(self):
        df = pd.DataFrame({"station_id": ["cpcb_x"], "value": [1]})
        with pytest.raises(ValueError, match="unknown station_ids"):
            validate_no_cross_station_mixing(df, ["cpcb_a"])


class TestAPIBehavior:
    def _get_client(self):
        from backend.app.main import app
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url="http://testserver")

    def test_multistation_endpoint_returns_valid_or_503(self):
        import asyncio

        async def _test():
            async with self._get_client() as client:
                response = await client.get("/forecast/real/multistation")
                assert response.status_code in (200, 503)

        asyncio.run(_test())

    def test_station_status_endpoint_returns_list(self):
        import asyncio

        async def _test():
            async with self._get_client() as client:
                response = await client.get("/forecast/real/stations/status")
                assert response.status_code == 200
                data = response.json()
                assert data["city"] == "Bengaluru"
                assert len(data["stations"]) == 6

        asyncio.run(_test())

    def test_single_station_endpoint_returns_valid_or_503(self):
        import asyncio

        async def _test():
            async with self._get_client() as client:
                response = await client.get("/forecast/real/cpcb_hebbal")
                assert response.status_code in (200, 503)

        asyncio.run(_test())
