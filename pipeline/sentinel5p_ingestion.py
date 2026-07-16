"""
Sentinel-5P TROPOMI NO2 column density ingestion for AQI Sentinel.

Fetches tropospheric NO2 column density (mol/m²) from Copernicus Sentinel-5P
via Google Earth Engine, caches to disk with stale-fallback, and maps values
onto H3 resolution-9 cells for Bengaluru.

Collection
----------
COPERNICUS/S5P/OFFL/L3_NO2  (offline-reprocessed; preferred over NRTI)

Why OFFL: better calibration / QA. ~1–2 day latency is fine for attribution
context (not same-day alerts).

Pixel scale
-----------
TROPOMI NO2 is ~3.5 × 5.5 km at nadir. Sampling H3 res-9 polygons (~174 m)
with ``scale=1000`` yields almost no pixel centers inside each hex → empty
results. We therefore sample the composite at **cell centroids** with
``scale≈3500`` so every hex gets the overlying satellite pixel value.

Requires GEE_SERVICE_ACCOUNT_KEY_PATH (and preferably GEE_PROJECT_ID).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import h3

import backend.app.config as _config

logger = logging.getLogger(__name__)

SENTINEL5P_CACHE_SCHEMA_VERSION = "1.1"
SENTINEL5P_COLLECTION = "COPERNICUS/S5P/OFFL/L3_NO2"
NO2_BAND = "tropospheric_NO2_column_number_density"
# Native-ish TROPOMI ground sampling distance (metres)
TROPOMI_SCALE_M = 3500
# Offline product: look back far enough to guarantee coverage
LOOKBACK_DAYS = 30
# Chunk size for GEE sampleRegions (points are cheap; keep batches modest)
CHUNK_SIZE = 1500

_GEE_KEY_WARNED = False


def _get_service_account_path() -> str | None:
    """Return absolute path to GEE service-account JSON, or None."""
    global _GEE_KEY_WARNED
    path = (os.environ.get("GEE_SERVICE_ACCOUNT_KEY_PATH") or "").strip()
    if not path:
        if not _GEE_KEY_WARNED:
            logger.warning(
                "GEE_SERVICE_ACCOUNT_KEY_PATH not set. "
                "Sentinel-5P NO2 data will be unavailable."
            )
            _GEE_KEY_WARNED = True
        return None

    p = Path(path)
    if not p.is_absolute():
        p = _config.get_project_root() / p
    resolved = str(p.resolve())
    if not p.exists():
        logger.warning("GEE service account file not found: %s", resolved)
        # Still return the configured path so callers can surface a clear auth error
        return path if Path(path).is_absolute() else resolved
    return resolved


def _get_gee_project() -> str | None:
    return (os.environ.get("GEE_PROJECT_ID") or "").strip() or None


# ---------------------------------------------------------------------------
# Cache helpers
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


def _build_cache_entry(city: str, data: dict[str, Any]) -> dict[str, Any]:
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
    # Never treat empty successful caches as fresh — force re-fetch
    data = entry.get("data") or {}
    if not data.get("hexagons"):
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
    data = entry.get("data") or {}
    if not data.get("hexagons"):
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
# H3 grid over Bengaluru bbox
# ---------------------------------------------------------------------------


def _get_h3_cells_in_bbox(bbox: dict[str, float], resolution: int) -> list[str]:
    """All H3 cells at ``resolution`` whose centroids lie within the bbox."""
    from h3 import latlng_to_cell

    cells: set[str] = set()
    # res-9 edge ~174 m → step ~0.002° (~220 m) for full coverage
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


def _extract_no2_value(props: dict[str, Any]) -> float | None:
    """Parse mean NO2 from reduceRegions / sampleRegions property bags."""
    for key in (
        NO2_BAND,
        f"{NO2_BAND}_mean",
        "mean",
        "tropospheric_NO2_column_number_density_mean",
    ):
        val = props.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


# ---------------------------------------------------------------------------
# GEE fetch
# ---------------------------------------------------------------------------


def _fetch_gee_no2(
    service_account_path: str,
    bbox: dict[str, float],
    h3_cells: list[str],
    collection: str = SENTINEL5P_COLLECTION,
) -> dict[str, float]:
    """Query GEE for mean NO2 column density per H3 cell (centroid sample).

    Returns dict mapping h3_cell -> mean_no2 (mol/m²). Raises RuntimeError on failure.
    """
    try:
        import ee
    except ImportError as e:
        raise RuntimeError(
            "earthengine-api package is not installed. Run: pip install earthengine-api"
        ) from e

    try:
        credentials = ee.ServiceAccountCredentials(None, service_account_path)
        project = _get_gee_project()
        if project:
            ee.Initialize(credentials, project=project)
        else:
            ee.Initialize(credentials)
    except Exception as e:
        raise RuntimeError(f"GEE authentication failed: {e}") from e

    try:
        region = ee.Geometry.Rectangle(
            [bbox["west"], bbox["south"], bbox["east"], bbox["north"]]
        )
        end = datetime.now(tz=timezone.utc)
        start = end - timedelta(days=LOOKBACK_DAYS)
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        image_collection = (
            ee.ImageCollection(collection)
            .filterBounds(region)
            .filterDate(start_str, end_str)
            .select(NO2_BAND)
        )

        n_images = int(image_collection.size().getInfo() or 0)
        if n_images == 0:
            logger.warning(
                "No Sentinel-5P images for %s → %s over Bengaluru", start_str, end_str
            )
            return {}

        logger.info(
            "Sentinel-5P: %d OFFL scenes %s→%s; sampling %d H3 cells",
            n_images,
            start_str,
            end_str,
            len(h3_cells),
        )

        # Mean composite of available offline scenes
        composite = image_collection.mean()

        # Sanity: region-level mean must be non-null
        region_stats = composite.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=TROPOMI_SCALE_M,
            maxPixels=1e9,
            bestEffort=True,
        ).getInfo()
        region_mean = _extract_no2_value(region_stats or {})
        if region_mean is None:
            logger.warning(
                "Sentinel-5P region composite has no valid NO2 pixels "
                "(stats=%s). Check QA / date window.",
                region_stats,
            )
            return {}

        result: dict[str, float] = {}

        for i in range(0, len(h3_cells), CHUNK_SIZE):
            chunk = h3_cells[i : i + CHUNK_SIZE]
            features = []
            for cell in chunk:
                lat, lon = h3.cell_to_latlng(cell)
                point = ee.Geometry.Point([lon, lat])
                features.append(ee.Feature(point, {"h3_cell": cell}))

            feature_collection = ee.FeatureCollection(features)

            # Centroid sampling at TROPOMI scale — polygons at res-9 under-sample
            sampled = composite.sampleRegions(
                collection=feature_collection,
                scale=TROPOMI_SCALE_M,
                geometries=False,
            )
            sampled_info = sampled.getInfo() or {}
            features_out = sampled_info.get("features") or []

            for feature in features_out:
                props = feature.get("properties") or {}
                cell = props.get("h3_cell")
                mean_val = _extract_no2_value(props)
                if cell is not None and mean_val is not None:
                    result[str(cell)] = mean_val

        logger.info(
            "Sentinel-5P: filled %d / %d H3 cells (region mean=%.3e mol/m²)",
            len(result),
            len(h3_cells),
            region_mean,
        )
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

    Same cache / stale-fallback pattern as FIRMS and weather services.
    """
    service_account_path = _get_service_account_path()
    if not service_account_path:
        return _unavailable_response(
            city,
            "GEE_SERVICE_ACCOUNT_KEY_PATH not configured or file missing. "
            "Sentinel-5P NO2 data unavailable.",
        )

    city_key = city.lower().strip()
    resolution = _config.H3_RESOLUTION

    if not refresh:
        entry = _read_cache(city_key)
        if entry and _cache_is_fresh(entry):
            data = dict(entry["data"])
            data["source_status"] = "live_provider"
            data["cache_used"] = True
            data["freshness"] = "fresh"
            data["age_minutes"] = _age_minutes(entry)
            return data

    try:
        h3_cells = _get_h3_cells_in_bbox(_config.BENGALURU_BOUNDING_BOX, resolution)
        no2_data = _fetch_gee_no2(
            service_account_path, _config.BENGALURU_BOUNDING_BOX, h3_cells
        )
        if not no2_data:
            # Do not cache empty as fresh success
            entry = _read_cache(city_key)
            if entry and _cache_is_usable_stale(entry) and (entry.get("data") or {}).get("hexagons"):
                data = dict(entry["data"])
                data["source_status"] = "stale_cache_fallback"
                data["cache_used"] = True
                data["freshness"] = "stale"
                data["age_minutes"] = _age_minutes(entry)
                data.setdefault("warnings", []).append(
                    "Live Sentinel-5P fetch returned no hex values; using stale cache."
                )
                return data
            return _unavailable_response(
                city,
                "Live Sentinel-5P fetch returned no valid NO2 pixels for Bengaluru.",
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
            "hexagon_count": len(hexagons),
            "lookback_days": LOOKBACK_DAYS,
            "sample_scale_m": TROPOMI_SCALE_M,
        }
        cache_entry = _build_cache_entry(city_key, result)
        _write_cache(city_key, cache_entry)
        return dict(result)
    except RuntimeError as e:
        logger.warning("Sentinel-5P provider unavailable: %s", e)
        entry = _read_cache(city_key)
        if entry and _cache_is_usable_stale(entry):
            data = dict(entry["data"])
            data["source_status"] = "stale_cache_fallback"
            data["cache_used"] = True
            data["freshness"] = "stale"
            data["age_minutes"] = _age_minutes(entry)
            warning = (
                f"Live Sentinel-5P provider unavailable. "
                f"Showing cached data from {_age_minutes(entry):.0f} minutes ago."
            )
            data.setdefault("warnings", []).append(warning)
            return data
        return _unavailable_response(city, f"NO2 column density data unavailable: {e}")


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


def main() -> None:
    """CLI: python -m pipeline.sentinel5p_ingestion [--refresh]"""
    import argparse
    import sys

    from dotenv import load_dotenv

    load_dotenv(_config.get_project_root() / ".env")
    parser = argparse.ArgumentParser(description="Fetch Sentinel-5P NO2 for Bengaluru")
    parser.add_argument("--refresh", action="store_true", help="Force live GEE fetch")
    parser.add_argument("--city", default="bengaluru")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = get_no2_column_density(city=args.city, refresh=args.refresh)
    n = len(result.get("hexagons") or [])
    print(
        f"status={result.get('source_status')} hexagons={n} "
        f"freshness={result.get('freshness')} warnings={result.get('warnings')}"
    )
    if n:
        vals = [h["no2_column_density_mean"] for h in result["hexagons"]]
        print(f"NO2 mol/m² min={min(vals):.3e} max={max(vals):.3e} mean={sum(vals)/len(vals):.3e}")
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
