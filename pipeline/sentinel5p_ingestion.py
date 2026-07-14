"""
Sentinel-5P TROPOMI NO2 column density ingestion for AQI Sentinel.

Fetches NO2 column density (mol/m²) from the Copernicus Sentinel-5P
TROPOMI sensor via Google Earth Engine, caches to disk with
stale-fallback, and reduces the raster to per-H3-cell mean values.

Collection choice:
  COPERNICUS/S5P/OFFL_L3_NO2  (offline-reprocessed)
  vs. COPERNICUS/S5P/NRTI/L3_NO2  (near-real-time)

  OFFL is preferred because it has undergone offline reprocessing with
  better calibration, fewer artefacts, and more reliable quality
  assurance. NRTI is noisier and primarily intended for same-day
  applications. Since Bengaluru's NO2 column is used for contextual
  fusion (not real-time alerts), the OFFL product's ~1-2 day latency
  is acceptable and its higher reliability outweighs the freshness
  advantage of NRTI.

Requires GEE_SERVICE_ACCOUNT_KEY_PATH environment variable pointing
to a GEE service account JSON key file.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h3

import backend.app.config as _config

logger = logging.getLogger(__name__)

SENTINEL5P_CACHE_SCHEMA_VERSION = "1.0"
SENTINEL5P_COLLECTION = "COPERNICUS/S5P/OFFL/L3_NO2"
CHUNK_SIZE = 750

# Lazy-evaluated env var with one-time warning
_GEE_KEY_WARNED = False


def _get_service_account_path() -> str | None:
    global _GEE_KEY_WARNED
    path = os.environ.get("GEE_SERVICE_ACCOUNT_KEY_PATH", "").strip()
    if not path and not _GEE_KEY_WARNED:
        logger.warning(
            "GEE_SERVICE_ACCOUNT_KEY_PATH environment variable not set. "
            "Sentinel-5P NO2 data will be unavailable. "
            "Set GEE_SERVICE_ACCOUNT_KEY_PATH in your .env file or environment."
        )
        _GEE_KEY_WARNED = True
    return path or None


# ---------------------------------------------------------------------------
# Cache helpers (same pattern as firms_ingestion.py / weather_forecast_service.py)
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    root = _config.get_project_root()
    return root / _config.SENTINEL5P_CACHE_DIR


def _cache_path(city: str) -> Path:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{city.lower().strip()}.json"


def _read_cache(city: str) -> dict[str, Any] | None:
    path = _cache_path(city)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read Sentinel-5P cache for %s: %s", city, e)
        return None


def _write_cache(city: str, data: dict[str, Any]) -> None:
    path = _cache_path(city)
    try:
        fd, tmp_path_str = tempfile.mkstemp(
            suffix=".json", prefix="sentinel5p_cache_", dir=str(path.parent)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path_str, str(path))
    except OSError as e:
        logger.warning("Failed to write Sentinel-5P cache for %s: %s", city, e)


def _build_cache_entry(
    city: str, data: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": SENTINEL5P_CACHE_SCHEMA_VERSION,
        "retrieved_at": datetime.now(tz=timezone.utc).isoformat(),
        "city": city,
        "collection": SENTINEL5P_COLLECTION,
        "data": data,
    }


def _cache_is_fresh(entry: dict[str, Any]) -> bool:
    retrieved_str = entry.get("retrieved_at", "")
    if not retrieved_str:
        return False
    try:
        retrieved = datetime.fromisoformat(retrieved_str)
    except (ValueError, TypeError):
        return False
    age = datetime.now(tz=timezone.utc) - retrieved
    return age.total_seconds() < _config.SENTINEL5P_CACHE_TTL_HOURS * 3600


def _cache_is_usable_stale(entry: dict[str, Any]) -> bool:
    retrieved_str = entry.get("retrieved_at", "")
    if not retrieved_str:
        return False
    try:
        retrieved = datetime.fromisoformat(retrieved_str)
    except (ValueError, TypeError):
        return False
    age = datetime.now(tz=timezone.utc) - retrieved
    return age.total_seconds() < _config.SENTINEL5P_STALE_CACHE_MAX_HOURS * 3600


def _age_minutes(entry: dict[str, Any]) -> float:
    retrieved_str = entry.get("retrieved_at", "")
    if not retrieved_str:
        return 0.0
    try:
        retrieved = datetime.fromisoformat(retrieved_str)
        age = datetime.now(tz=timezone.utc) - retrieved
        return age.total_seconds() / 60.0
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# GEE data fetching (thin, separately-testable layer)
# ---------------------------------------------------------------------------


def _get_h3_cells_in_bbox(
    bbox: dict[str, float], resolution: int
) -> list[str]:
    """Return all H3 cells at given resolution whose centroids lie within the bounding box."""
    from h3 import latlng_to_cell

    cells: set[str] = set()
    # Sample grid within bounding box at ~1/4 of cell edge length steps
    # res 9 edge ~174m, so step lat/lon by ~0.002 (~220m) for overlap
    lat_step = 0.002
    lon_step = 0.002
    lat = bbox["south"]
    while lat <= bbox["north"]:
        lon = bbox["west"]
        while lon <= bbox["east"]:
            cells.add(latlng_to_cell(lat, lon, resolution))
            lon += lon_step
        lat += lat_step
    return sorted(cells)


def _fetch_gee_no2(
    service_account_path: str,
    bbox: dict[str, float],
    h3_cells: list[str],
    collection: str = SENTINEL5P_COLLECTION,
) -> dict[str, float]:
    """Query GEE for mean NO2 column density per H3 cell.

    This function is intentionally thin so it can be easily mocked in tests.
    Returns dict mapping h3_cell -> mean_no2_value (mol/m²).

    Only cells with valid data are included in the result.

    Raises RuntimeError on failure.
    """
    try:
        import ee
    except ImportError:
        raise RuntimeError(
            "earthengine-api package is not installed. "
            "Run: pip install earthengine-api"
        )

    try:
        credentials = ee.ServiceAccountCredentials(
            None, service_account_path
        )
        ee.Initialize(credentials)
    except Exception as e:
        raise RuntimeError(f"GEE authentication failed: {e}") from e

    try:
        region = ee.Geometry.Rectangle(
            [bbox["west"], bbox["south"], bbox["east"], bbox["north"]]
        )
        # Filter to recent imagery (last 14 days for OFFL)
        end = datetime.now(tz=timezone.utc)
        start = end - __import__("datetime").timedelta(days=14)
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        image_collection = (
            ee.ImageCollection(collection)
            .filterBounds(region)
            .filterDate(start_str, end_str)
            .select("tropospheric_NO2_column_number_density")
        )

        if image_collection.size().getInfo() == 0:
            logger.warning("No Sentinel-5P images found for the period %s to %s", start_str, end_str)
            return {}

        # Composite: mean of available images
        composite = image_collection.mean()

        result: dict[str, float] = {}
        band_name = "tropospheric_NO2_column_number_density"

        for start in range(0, len(h3_cells), CHUNK_SIZE):
            chunk = h3_cells[start:start + CHUNK_SIZE]
            features = []
            for cell in chunk:
                boundary = h3.cell_to_boundary(cell)
                coords = [[lon, lat] for lat, lon in boundary]
                polygon = ee.Geometry.Polygon([coords])
                features.append(ee.Feature(polygon, {"h3_cell": cell}))

            feature_collection = ee.FeatureCollection(features)

            reduced = composite.reduceRegions(
                collection=feature_collection,
                reducer=ee.Reducer.mean(),
                scale=1000,
            )

            reduced_info = reduced.getInfo()

            if reduced_info["features"]:
                print(reduced_info["features"][0]["properties"])

            for feature in reduced_info["features"]:
                props = feature["properties"]
                cell = props.get("h3_cell")
                mean_val = props.get(band_name)
                if cell is not None and mean_val is not None:
                    result[cell] = float(mean_val)

        return result
    except Exception as e:
        raise RuntimeError(f"GEE query failed: {e}") from e


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_no2_column_density(
    city: str = "bengaluru",
    refresh: bool = False,
) -> dict[str, Any]:
    """Get Sentinel-5P NO2 column density aggregated per H3 cell.

    Follows the same cache/stale-fallback pattern as FIRMS and weather services.

    Parameters
    ----------
    city : str       City key (default 'bengaluru').
    refresh : bool   Force a live fetch even if cache is fresh.

    Returns
    -------
    dict with keys: hexagons, city, collection, source_status, freshness,
    age_minutes, warnings, retrieved_at.
    """
    service_account_path = _get_service_account_path()
    if not service_account_path:
        return _unavailable_response(
            city,
            "GEE_SERVICE_ACCOUNT_KEY_PATH not configured. "
            "Sentinel-5P NO2 data unavailable.",
        )

    city_key = city.lower().strip()
    resolution = _config.H3_RESOLUTION

    if not refresh:
        entry = _read_cache(city_key)
        if entry and _cache_is_fresh(entry):
            data = entry["data"]
            data["source_status"] = "live_provider"
            data["cache_used"] = True
            data["freshness"] = "fresh"
            data["age_minutes"] = _age_minutes(entry)
            return dict(data)

    try:
        h3_cells = _get_h3_cells_in_bbox(_config.BENGALURU_BOUNDING_BOX, resolution)
        no2_data = _fetch_gee_no2(
            service_account_path, _config.BENGALURU_BOUNDING_BOX, h3_cells
        )
        hexagons = [
            {
                "h3_cell": cell,
                "no2_column_density_mean": value,
            }
            for cell, value in sorted(no2_data.items())
        ]
        result = {
            "hexagons": hexagons,
            "city": city_key,
            "collection": SENTINEL5P_COLLECTION,
            "source_status": "live_provider",
            "cache_used": False,
            "freshness": "fresh",
            "age_minutes": 0.0,
            "warnings": [],
            "retrieved_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        cache_entry = _build_cache_entry(city_key, result)
        _write_cache(city_key, cache_entry)
        return dict(result)
    except RuntimeError as e:
        logger.warning("Sentinel-5P provider unavailable: %s", e)
        entry = _read_cache(city_key)
        if entry and _cache_is_usable_stale(entry):
            data = entry["data"]
            data["source_status"] = "stale_cache_fallback"
            data["cache_used"] = True
            data["freshness"] = "stale"
            data["age_minutes"] = _age_minutes(entry)
            warning = (
                f"Live Sentinel-5P provider unavailable. "
                f"Showing cached data from {_age_minutes(entry):.0f} minutes ago."
            )
            data.setdefault("warnings", []).append(warning)
            return dict(data)
        return _unavailable_response(
            city, f"NO2 column density data unavailable: {e}"
        )


def _unavailable_response(city: str, reason: str) -> dict[str, Any]:
    return {
        "hexagons": [],
        "city": city,
        "collection": SENTINEL5P_COLLECTION,
        "source_status": "unavailable",
        "cache_used": False,
        "freshness": "unavailable",
        "age_minutes": None,
        "retrieved_at": "",
        "warnings": [reason],
    }
