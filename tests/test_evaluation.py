import json

from ml.common import get_paths
from ml.evaluate import evaluate_models
from ml.train_lightgbm import train_lightgbm
from ml.train_persistence_baseline import train_persistence_baseline
from pipeline.build_features import build_features
from pipeline.generate_demo_data import generate_demo_data


def test_evaluation_metrics_json_is_created(tmp_path):
    paths = get_paths(tmp_path)
    generate_demo_data(paths.raw_data, days=180)
    build_features(paths.raw_data, paths.processed_features)
    train_persistence_baseline(tmp_path)
    train_lightgbm(tmp_path)
    metrics = evaluate_models(tmp_path)

    assert paths.evaluation_metrics.exists()
    saved = json.loads(paths.evaluation_metrics.read_text(encoding="utf-8"))
    assert saved["task"] == "PM2.5 24-hour forecasting"
    assert saved["test_rows"] > 0
    assert saved["model_selected_for_serving"] in {"lightgbm", "persistence"}
    assert metrics == saved
