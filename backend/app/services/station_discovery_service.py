from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import backend.app.config as _config
from backend.app.schemas.stations import StationInfo
from pipeline.station_registry import get_registry_stations

logger = logging.getLogger(__name__)

EXCLUDED_IDS: set[str] = {"cpcb_jigani"}


def _forecast_available(station_id: str) -> bool:
    root = _config.get_project_root()
    processed_dir = root / "data" / "processed" / "real" / station_id
    forecast_file = processed_dir / f"{station_id}_features_24h.parquet"
    return forecast_file.exists()


def _geospatial_available(station_id: str) -> bool:
    root = _config.get_project_root()
    geospatial_dir = root / _config.GEOSPATIAL_PROCESSED_DIR
    context_file = geospatial_dir / "station_geospatial_context.parquet"
    if not context_file.exists():
        return False
    try:
        import pandas as pd
        df = pd.read_parquet(context_file)
        return station_id in df["station_id"].values
    except Exception:
        return False


def list_stations(city: str = "bengaluru", include_inactive: bool = False) -> list[dict[str, Any]]:
    stations = get_registry_stations()
    result: list[StationInfo] = []

    for s in stations:
        if s.station_id in EXCLUDED_IDS:
            continue
        if s.city.lower() != city.lower():
            continue
        if not include_inactive and not s.active:
            continue

        forecast_avail = _forecast_available(s.station_id)
        geo_avail = _geospatial_available(s.station_id)
        limitations: list[str] = []
        data_status = "active" if s.active else "inactive"

        if not forecast_avail:
            limitations.append("Forecast artifacts not yet built")
        if not geo_avail:
            limitations.append("Geospatial context not yet built")

        result.append(StationInfo(
            station_id=s.station_id,
            display_name=s.display_name or s.station_name or s.station_id,
            city=s.city,
            latitude=s.latitude,
            longitude=s.longitude,
            source_authority=s.source,
            forecast_available=forecast_avail,
            geospatial_available=geo_avail,
            data_status=data_status,
            limitations=limitations,
        ))

    return [r.model_dump() for r in result]
