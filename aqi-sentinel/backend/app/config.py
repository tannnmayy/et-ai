from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    configured = os.getenv("AQI_SENTINEL_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[2]


def get_data_mode() -> str:
    return "local_demo_data"


SERVICE_NAME = "aqi-sentinel-api"
