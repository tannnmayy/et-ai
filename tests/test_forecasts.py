from fastapi.testclient import TestClient

from backend.app.main import app
from ml.common import get_paths
from ml.evaluate import evaluate_models
from ml.train_lightgbm import train_lightgbm
from ml.train_persistence_baseline import train_persistence_baseline
from pipeline.build_features import build_features
from pipeline.generate_demo_data import generate_demo_data


def test_forecast_endpoint_gracefully_errors_without_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("AQI_SENTINEL_PROJECT_ROOT", str(tmp_path))
    response = TestClient(app).get("/forecast/stations")
    assert response.status_code == 503
    assert "missing" in response.json()["detail"].lower()


def test_forecast_endpoint_returns_forecasts_after_pipeline_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("AQI_SENTINEL_PROJECT_ROOT", str(tmp_path))
    paths = get_paths(tmp_path)
    generate_demo_data(paths.raw_data, days=180)
    build_features(paths.raw_data, paths.processed_features)
    train_persistence_baseline(tmp_path)
    train_lightgbm(tmp_path)
    evaluate_models(tmp_path)

    response = TestClient(app).get("/forecast/stations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["city"] == "Bengaluru"
    assert payload["data_mode"] == "local_demo_data"
    assert payload["forecast_engine"] in {"lightgbm", "persistence_fallback"}
    assert len(payload["forecasts"]) == 3
    assert {item["station_name"] for item in payload["forecasts"]} == {"BTM Layout", "Whitefield", "Peenya"}
