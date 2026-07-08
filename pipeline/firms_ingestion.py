"""
NASA FIRMS fire/burning detection ingestion for AQI Sentinel.

Fetches VIIRS NOAA-20 NRT (375m resolution) active fire detections from
NASA FIRMS API, caches to disk with stale-fallback, and aggregates per
H3 res-9 cell over a rolling 24h window.

Data source:
  https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{bbox}/{day_range}

Requires FIRMS_MAP_KEY environment variable (one-time free signup at
https://firms.modaps.eosdis.nasa.gov/). Detections arrive ~3h after
satellite pass.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import h3
import requests

import backend.app.config as _config

logger = logging.getLogger(__name__)

FIRMS_CACHE_SCHEMA_VERSION = "1.0"
FIRMS_SOURCE = "VIIRS_NOAA20_NRT"

# Lazy-evaluated env var with one-time warning
_FIRMS_KEY_WARNED = False


def _get_map_key() -> str | None:
    global _FIRMS_KEY_WARNED
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key and not _FIRMS_KEY_WARNED:
        logger.warning(
            "FIRMS_MAP_KEY environment variable not set. "
            "Fire detection data will be unavailable. "
            "Set FIRMS_MAP_KEY in your .env file or environment."
        )
        _FIRMS_KEY_WARNED = True
    return key or None


# ---------------------------------------------------------------------------
# Cache helpers (same pattern as weather_forecast_service.py)
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    root = _config.get_project_root()
    return root / _config.FIRMS_CACHE_DIR


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
        logger.warning("Failed to read FIRMS cache for %s: %s", city, e)
        return None


def _write_cache(city: str, data: dict[str, Any]) -> None:
    path = _cache_path(city)
    try:
        fd, tmp_path_str = tempfile.mkstemp(
            suffix=".json", prefix="firms_cache_", dir=str(path.parent)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path_str, str(path))
    except OSError as e:
        logger.warning("Failed to write FIRMS cache for %s: %s", city, e)


def _build_cache_entry(
    city: str, data: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": FIRMS_CACHE_SCHEMA_VERSION,
        "retrieved_at": datetime.now(tz=timezone.utc).isoformat(),
        "city": city,
        "source": FIRMS_SOURCE,
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
    return age.total_seconds() < _config.FIRMS_CACHE_TTL_MINUTES * 60


def _cache_is_usable_stale(entry: dict[str, Any]) -> bool:
    retrieved_str = entry.get("retrieved_at", "")
    if not retrieved_str:
        return False
    try:
        retrieved = datetime.fromisoformat(retrieved_str)
    except (ValueError, TypeError):
        return False
    age = datetime.now(tz=timezone.utc) - retrieved
    return age.total_seconds() < _config.FIRMS_STALE_CACHE_MAX_HOURS * 3600


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
# FIRMS API client
# ---------------------------------------------------------------------------


def _bbox_param(bbox: dict[str, float]) -> str:
    """Format BENGALURU_BOUNDING_BOX as 'west,south,east,north'."""
    return f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}"


def _fetch_firms_csv(
    map_key: str, bbox: dict[str, float], days: int = 3
) -> str:
    """Fetch raw CSV from NASA FIRMS API.

    Returns the CSV text.
    Raises RuntimeError on failure.
    """
    bbox_str = _bbox_param(bbox)
    url = (
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{map_key}/{FIRMS_SOURCE}/{bbox_str}/{days}"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        raise RuntimeError(f"FIRMS API request failed: {e}") from e


# ---------------------------------------------------------------------------
# Parsing & H3 aggregation
# ---------------------------------------------------------------------------

_EXPECTED_FIRMS_FIELDS = {
    "latitude", "longitude", "frp", "confidence",
    "acq_date", "acq_time", "daynight",
}

# Confidence mapping for FIRMS categorical values
_CONFIDENCE_RANK = {
    "low": 0,
    "nominal": 1,
    "high": 2,
}


def _parse_detections(csv_text: str) -> list[dict[str, Any]]:
    """Parse FIRMS CSV into a list of detection dicts.

    Filters to valid rows with required fields.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    detections: list[dict[str, Any]] = []
    for row in reader:
        lat = _safe_float(row.get("latitude"))
        lon = _safe_float(row.get("longitude"))
        frp = _safe_float(row.get("frp"))
        confidence_raw = (row.get("confidence") or "").strip().lower()
        acq_date = (row.get("acq_date") or "").strip()
        acq_time_raw = (row.get("acq_time") or "").strip()
        daynight = (row.get("daynight") or "").strip().upper()

        if lat is None or lon is None:
            continue

        detections.append({
            "latitude": lat,
            "longitude": lon,
            "frp_mw": frp if frp is not None else 0.0,
            "confidence": confidence_raw,
            "acq_date": acq_date,
            "acq_time": acq_time_raw,
            "daynight": daynight,
        })
    return detections


def _parse_acq_datetime(acq_date: str, acq_time: str) -> datetime | None:
    """Parse FIRMS acquisition date/time into a UTC datetime.

    FIRMS acq_time is formatted as HHMM (24h) or -9999 for unknown.
    """
    if not acq_date:
        return None
    try:
        dt_date = datetime.strptime(acq_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    if not acq_time or acq_time in ("-9999", ""):
        return datetime.combine(dt_date, datetime.min.time(), tzinfo=timezone.utc)
    try:
        hh = int(acq_time[:2])
        mm = int(acq_time[2:4])
        return datetime(
            dt_date.year, dt_date.month, dt_date.day, hh, mm, tzinfo=timezone.utc
        )
    except (ValueError, IndexError):
        return datetime.combine(dt_date, datetime.min.time(), tzinfo=timezone.utc)


def _aggregate_by_h3(
    detections: list[dict[str, Any]], resolution: int
) -> list[dict[str, Any]]:
    """Aggregate detections per H3 cell over a rolling 24h UTC window.

    Returns list of dicts with h3_cell, detection_count, total_frp_mw,
    max_confidence, window_end_utc.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

    cells: dict[str, dict[str, Any]] = {}
    for d in detections:
        acq_dt = _parse_acq_datetime(d["acq_date"], d["acq_time"])
        if acq_dt is None or acq_dt < cutoff:
            continue

        cell = h3.latlng_to_cell(d["latitude"], d["longitude"], resolution)
        if cell not in cells:
            cells[cell] = {
                "h3_cell": cell,
                "detection_count": 0,
                "total_frp_mw": 0.0,
                "max_confidence": None,
            }
        entry = cells[cell]
        entry["detection_count"] += 1
        entry["total_frp_mw"] += d["frp_mw"]

        # Track highest-confidence detection
        rank = _CONFIDENCE_RANK.get(d["confidence"], -1)
        current_max = _CONFIDENCE_RANK.get(entry["max_confidence"], -1)
        if rank > current_max:
            entry["max_confidence"] = d["confidence"]

    result = sorted(cells.values(), key=lambda x: x["detection_count"], reverse=True)
    for r in result:
        r["total_frp_mw"] = round(r["total_frp_mw"], 4)
        r["window_end_utc"] = datetime.now(tz=timezone.utc).isoformat()
    return result


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        v = float(val)
        if v != v:
            return None
        return v
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_fire_detections(
    city: str = "bengaluru",
    days: int = 3,
    refresh: bool = False,
) -> dict[str, Any]:
    """Get FIRMS fire detection data aggregated per H3 cell.

    Follows the same cache/stale-fallback pattern as weather_forecast_service.

    Parameters
    ----------
    city : str       City key (default 'bengaluru').
    days : int       Days of history to fetch from API (default 3).
    refresh : bool   Force a live fetch even if cache is fresh.

    Returns
    -------
    dict with keys: hexagons, city, source, source_status, freshness,
    age_minutes, warnings, retrieved_at.
    """
    map_key = _get_map_key()
    if not map_key:
        return _unavailable_response(
            city, "FIRMS_MAP_KEY not configured. Fire detection data unavailable."
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
        csv_text = _fetch_firms_csv(map_key, _config.BENGALURU_BOUNDING_BOX, days=days)
        detections = _parse_detections(csv_text)
        hexagons = _aggregate_by_h3(detections, resolution)
        result = {
            "hexagons": hexagons,
            "city": city_key,
            "source": FIRMS_SOURCE,
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
        logger.warning("FIRMS provider unavailable: %s", e)
        entry = _read_cache(city_key)
        if entry and _cache_is_usable_stale(entry):
            data = entry["data"]
            data["source_status"] = "stale_cache_fallback"
            data["cache_used"] = True
            data["freshness"] = "stale"
            data["age_minutes"] = _age_minutes(entry)
            warning = (
                f"Live FIRMS provider unavailable. "
                f"Showing cached data from {_age_minutes(entry):.0f} minutes ago."
            )
            data.setdefault("warnings", []).append(warning)
            return dict(data)
        return _unavailable_response(
            city, f"Fire detection data unavailable: {e}"
        )


def _unavailable_response(city: str, reason: str) -> dict[str, Any]:
    return {
        "hexagons": [],
        "city": city,
        "source": FIRMS_SOURCE,
        "source_status": "unavailable",
        "cache_used": False,
        "freshness": "unavailable",
        "age_minutes": None,
        "retrieved_at": "",
        "warnings": [reason],
    }
