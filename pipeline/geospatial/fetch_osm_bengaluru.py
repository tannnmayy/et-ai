"""
Explicit CLI to fetch all required OSM layers for Bengaluru.

Usage:
    python -m pipeline.geospatial.fetch_osm_bengaluru
    python -m pipeline.geospatial.fetch_osm_bengaluru --refresh
    python -m pipeline.geospatial.fetch_osm_bengaluru --allow-partial
    python -m pipeline.geospatial.fetch_osm_bengaluru --dry-run
    python -m pipeline.geospatial.fetch_osm_bengaluru --timeout-seconds 120
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.geospatial.osm_client import (
    OSM_TAGS,
    _snapshot_geojson_path,
    _snapshot_metadata_path,
    _validate_geojson,
    fetch_all_categories,
    fetch_osm_category,
    get_all_snapshot_metadata,
    _osm_cache_dir,
)

logger = logging.getLogger(__name__)

REQUIRED_LAYERS = list(OSM_TAGS.keys())


def _cache_valid_for_full_build(gjson_path: Path) -> tuple[bool, str]:
    """Check whether a cached GeoJSON is valid for a full build.

    Returns (is_valid_for_full_build, reason).
    A file must be parseable, be a FeatureCollection, and have feature_count > 0.
    """
    parseable, reason = _validate_geojson(gjson_path)
    if not parseable:
        return False, reason
    count = _count_features(gjson_path)
    if count is None:
        return False, "unable_to_count_features"
    if count == 0:
        return False, "empty_feature_collection"
    return True, f"ok ({count} features)"


def _all_layers_valid() -> dict[str, Any]:
    """Check each required layer: whether cached GeoJSON is valid for a full build.

    Returns a dict with per-layer status and overall validity.
    Separates syntactically-parseable from build-useful cache.
    """
    meta = get_all_snapshot_metadata()
    results: dict[str, Any] = {}
    all_valid = True
    for layer in REQUIRED_LAYERS:
        gjson_path = _snapshot_geojson_path(layer)
        layer_meta = meta.get(layer, {})
        cache_status = layer_meta.get("cache_status", "none")
        parseable, parse_reason = _validate_geojson(gjson_path)
        feature_count = _count_features(gjson_path) if parseable else None
        cache_valid, build_reason = _cache_valid_for_full_build(gjson_path) if parseable else (False, parse_reason)
        results[layer] = {
            "geojson_exists": gjson_path.exists(),
            "geojson_parseable": parseable,
            "cache_valid_for_full_build": cache_valid,
            "feature_count": feature_count,
            "cache_status": cache_status,
            "snapshot_timestamp": layer_meta.get("snapshot_timestamp"),
            "validation_reason": build_reason,
        }
        if not cache_valid:
            all_valid = False
    results["_all_layers_valid"] = all_valid
    return results


def _count_features(path: Path) -> int | None:
    """Return feature count from a valid GeoJSON file."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data.get("features", []))
    except (json.JSONDecodeError, IOError):
        return None


def _write_snapshot_manifest(results: dict[str, Any], partial: bool) -> dict[str, Any]:
    """Write a snapshot manifest JSON to the OSM cache directory."""
    all_full_valid = all(
        results.get(layer, {}).get("cache_valid_for_full_build", False)
        for layer in REQUIRED_LAYERS
    )
    succeeded_count = sum(
        1 for layer in REQUIRED_LAYERS
        if results.get(layer, {}).get("cache_valid_for_full_build", False)
    )
    failed_count = len(REQUIRED_LAYERS) - succeeded_count

    manifest = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "source": "OpenStreetMap via OSMnx",
        "bounding_box": {
            "north": 13.15, "south": 12.85,
            "east": 77.75, "west": 77.45,
        },
        "layers": {},
        "all_layers_valid": all_full_valid,
        "partial_build": partial or not all_full_valid,
        "layers_expected": len(REQUIRED_LAYERS),
        "layers_succeeded": succeeded_count,
        "layers_failed": failed_count,
    }
    for layer in REQUIRED_LAYERS:
        manifest["layers"][layer] = {
            "feature_count": results.get(layer, {}).get("feature_count"),
            "geojson_parseable": results.get(layer, {}).get("geojson_parseable", False),
            "cache_valid_for_full_build": results.get(layer, {}).get("cache_valid_for_full_build", False),
            "cache_status": results.get(layer, {}).get("cache_status", "none"),
            "snapshot_timestamp": results.get(layer, {}).get("snapshot_timestamp"),
        }

    manifest_path = _osm_cache_dir() / "osm_snapshot_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    return manifest


def run_fetch(
    refresh: bool = False,
    allow_partial: bool = False,
    timeout_seconds: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute the full OSM fetch for Bengaluru.

    Returns a summary dict.
    """
    if dry_run:
        logger.info("DRY RUN: checking current cache state without fetching")
        results = _all_layers_valid()
        manifest = _write_snapshot_manifest(results, partial=False)
        return {
            "status": "dry_run",
            "message": "Dry run completed. No data was fetched.",
            "all_layers_valid": results.get("_all_layers_valid", False),
            "layers": results,
            "manifest": manifest,
        }

    # Check current cache state
    precheck = _all_layers_valid()
    if precheck.get("_all_layers_valid") and not refresh:
        logger.info("All OSM layers are cached and valid. Use --refresh to re-fetch.")
        manifest = _write_snapshot_manifest(precheck, partial=False)
        return {
            "status": "cached",
            "message": "All layers are already cached and valid.",
            "all_layers_valid": True,
            "layers": precheck,
            "manifest": manifest,
        }

    # Fetch each layer
    results: dict[str, Any] = {}
    failed_layers: list[str] = []
    succeeded_layers: list[str] = []

    for layer in REQUIRED_LAYERS:
        logger.info("Fetching OSM layer: %s", layer)
        try:
            if timeout_seconds:
                # Set OSMnx timeout
                import osmnx as ox
                old_timeout = ox.settings.requests_timeout

                ox.settings.requests_timeout = timeout_seconds

            meta = fetch_osm_category(layer, refresh=True, quiet=False)

            if timeout_seconds:
                ox.settings.requests_timeout = old_timeout

            gjson_path = _snapshot_geojson_path(layer)
            parseable, parse_reason = _validate_geojson(gjson_path)
            feature_count = _count_features(gjson_path) if parseable else None
            cache_valid, build_reason = _cache_valid_for_full_build(gjson_path) if parseable else (False, parse_reason)

            results[layer] = {
                "geojson_exists": gjson_path.exists(),
                "geojson_parseable": parseable,
                "cache_valid_for_full_build": cache_valid,
                "feature_count": feature_count,
                "cache_status": meta.get("cache_status", "unknown"),
                "snapshot_timestamp": meta.get("snapshot_timestamp"),
                "validation_reason": build_reason,
            }
            if cache_valid:
                succeeded_layers.append(layer)
            else:
                failed_layers.append(layer)
                results[layer]["error"] = build_reason
            logger.info(
                "Layer '%s': cache_valid_for_full_build=%s, features=%s, reason=%s",
                layer, cache_valid, feature_count, build_reason,
            )
        except Exception as exc:
            logger.error("Failed to fetch layer '%s': %s", layer, exc)
            failed_layers.append(layer)
            results[layer] = {
                "geojson_exists": False,
                "geojson_parseable": False,
                "cache_valid_for_full_build": False,
                "feature_count": None,
                "cache_status": "error",
                "error": str(exc),
                "validation_reason": "fetch_exception",
            }

    results["_all_layers_valid"] = len(failed_layers) == 0
    results["_succeeded_layers"] = succeeded_layers
    results["_failed_layers"] = failed_layers

    partial = len(failed_layers) > 0

    if partial and not allow_partial:
        # Write whatever we have to preserve cache, but exit with error
        manifest = _write_snapshot_manifest(results, partial=True)
        results["manifest"] = manifest
        results["status"] = "partial_failure"
        results["message"] = (
            f"Some layers failed: {failed_layers}. "
            "Use --allow-partial to write a partial snapshot anyway."
        )
        return results

    manifest = _write_snapshot_manifest(results, partial=partial)
    results["manifest"] = manifest
    results["status"] = "partial" if partial else "success"
    results["message"] = (
        f"Fetched {len(succeeded_layers)}/{len(REQUIRED_LAYERS)} layers. "
        f"{'Partial build.' if partial else 'All layers valid.'}"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Bengaluru OSM data and cache locally. "
        "First run requires internet and may take several minutes."
    )
    parser.add_argument(
        "--refresh", "-r",
        action="store_true",
        help="Bypass cache and re-download all layers",
    )
    parser.add_argument(
        "--allow-partial", "-p",
        action="store_true",
        help="Allow partial snapshot (some layers may fail)",
    )
    parser.add_argument(
        "--timeout-seconds", "-t",
        type=int, default=None,
        help="OSMnx/Overpass timeout in seconds",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Check cache state without fetching anything",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    result = run_fetch(
        refresh=args.refresh,
        allow_partial=args.allow_partial,
        timeout_seconds=args.timeout_seconds,
        dry_run=args.dry_run,
    )

    print("\n" + json.dumps(result, indent=2, default=str))

    if result.get("status") == "partial_failure":
        sys.exit(1)


if __name__ == "__main__":
    main()
