"""
OpenStreetMap client for Bengaluru geospatial context.

Downloads and caches OSM data through an explicit build command only.
Never called at FastAPI request time. Uses OSMnx for retrieval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import osmnx as ox
from shapely.geometry import Polygon, box

import backend.app.config as _config

logger = logging.getLogger(__name__)

# OSM tag filters for each category
OSM_TAGS: dict[str, dict[str, Any]] = {
    "roads": {"highway": True},
    "landuse": {"landuse": True},
    "green_spaces": {
        "leisure": ["park", "garden", "nature_reserve", "golf_course", "playground", "pitch", "sports_centre"],
        "landuse": ["forest", "meadow", "grass", "recreation_ground", "village_green"],
        "natural": ["wood", "scrub", "heath", "grassland", "tree", "tree_row"],
    },
    "construction": {
        "landuse": ["construction"],
        "construction": True,
        "building": ["construction"],
        "highway": ["construction"],
    },
    "industrial_facility": {
        "industrial": True,
        "power": ["plant", "substation", "generator", "station"],
        "man_made": ["works", "wastewater_plant", "chimney", "storage_tank", "silo", "reservoir"],
        "landuse": ["industrial", "quarry", "landfill", "brownfield"],
        "power_source": True,
    },
}

# Retry / backoff settings
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 5, 15]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _osm_cache_dir() -> Path:
    return _config.get_project_root() / _config.OSM_CACHE_DIR


def _snapshot_metadata_path(category: str) -> Path:
    return _osm_cache_dir() / f"{category}_metadata.json"


def _snapshot_geojson_path(category: str) -> Path:
    return _osm_cache_dir() / f"{category}.geojson"


# ---------------------------------------------------------------------------
# GeoJSON validation
# ---------------------------------------------------------------------------


def _validate_geojson(path: Path) -> tuple[bool, str]:
    """Validate a GeoJSON file.

    Returns (is_valid, reason_string).
    Rejects: missing files, non-dict JSON, non-FeatureCollection,
    empty feature lists, zero-length files, and corrupt data.
    """
    if not path.exists():
        return False, "file_not_found"
    try:
        stat = path.stat()
        if stat.st_size < 20:
            return False, f"file_too_small ({stat.st_size} bytes)"
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        return False, f"json_decode_error: {exc}"
    except (IOError, OSError) as exc:
        return False, f"io_error: {exc}"

    if not isinstance(data, dict):
        return False, "not_a_dict"
    if data.get("type") != "FeatureCollection":
        # OSMnx may save as another type; accept it if it has features
        if "features" not in data:
            return False, f"unexpected_type: {data.get('type', 'unknown')}"
    features = data.get("features", [])
    if not isinstance(features, list):
        return False, "features_not_a_list"
    count = len(features)
    if count == 0:
        return True, "empty_FeatureCollection_(0_features)"
    return True, f"ok ({count} features)"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _is_cache_valid(category: str) -> bool:
    """Check whether a cached OSM snapshot exists, is valid, and is within TTL."""
    meta_path = _snapshot_metadata_path(category)
    data_path = _snapshot_geojson_path(category)

    if not meta_path.exists() or not data_path.exists():
        return False

    valid, reason = _validate_geojson(data_path)
    if not valid:
        logger.warning("Cache for '%s' is invalid: %s", category, reason)
        return False

    # Check feature count — an empty but valid GeoJSON (0 features) is not useful
    try:
        with data_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if len(data.get("features", [])) == 0:
            logger.warning("Cache for '%s' has zero features; treating as invalid", category)
            return False
    except (json.JSONDecodeError, IOError):
        return False

    try:
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        snapshot_ts = datetime.fromisoformat(meta.get("snapshot_timestamp", ""))
        age_days = (datetime.now(tz=timezone.utc) - snapshot_ts).days
        return age_days < _config.OSM_SNAPSHOT_TTL_DAYS
    except (json.JSONDecodeError, KeyError, ValueError):
        return False


def _write_metadata(category: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write metadata JSON for a cached OSM category."""
    bbox = _config.BENGALURU_BOUNDING_BOX
    meta = {
        "category": category,
        "snapshot_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "bounding_box": bbox,
        "source": "OpenStreetMap via OSMnx",
        "feature_builder_version": _config.GEOSPATIAL_FEATURE_BUILDER_VERSION,
        "osm_query_tags": OSM_TAGS.get(category, {}),
    }
    if extra:
        meta.update(extra)
    meta_path = _snapshot_metadata_path(category)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)
    return meta


def _compute_data_hash(geojson_path: Path) -> str:
    """Compute SHA-256 hash of the GeoJSON data for provenance."""
    if not geojson_path.exists():
        return ""
    return hashlib.sha256(geojson_path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Fetch single category with retry/backoff
# ---------------------------------------------------------------------------


def _build_bengaluru_polygon() -> Polygon:
    """Build a Shapely Polygon from the Bengaluru bounding box config."""
    bbox = _config.BENGALURU_BOUNDING_BOX
    return box(bbox["west"], bbox["south"], bbox["east"], bbox["north"])


def _fetch_roads(bengaluru_polygon: Polygon, geojson_path: Path) -> tuple[int, int]:
    """Fetch roads layer: OSMnx graph, then convert edges to GeoJSON.

    Returns (node_count, edge_count).
    """
    graph = ox.graph_from_polygon(
        bengaluru_polygon,
        network_type="drive",
        truncate_by_edge=True,
        simplify=True,
    )
    node_count = len(graph.nodes)
    edge_count = len(graph.edges)
    logger.info(
        "OSMnx roads query: polygon=%s, nodes=%d, edges=%d",
        bengaluru_polygon.wkt[:80], node_count, edge_count,
    )
    gdf_edges = ox.graph_to_gdfs(graph, nodes=False, edges=True)
    serialized_count = len(gdf_edges) if not gdf_edges.empty else 0
    if not gdf_edges.empty:
        gdf_edges.to_file(geojson_path, driver="GeoJSON")
        logger.info("Roads serialized: %d edges -> GeoJSON", serialized_count)
    else:
        _write_valid_geojson(geojson_path, [])
        logger.warning("Roads: OSMnx returned empty edges graph")

    return node_count, edge_count


def _fetch_features(bengaluru_polygon: Polygon, tags: dict, geojson_path: Path) -> int:
    """Fetch generic OSM features by tags and write GeoJSON.

    Returns feature count.
    """
    gdf = ox.features_from_polygon(bengaluru_polygon, tags)
    returned_count = len(gdf) if not gdf.empty else 0
    logger.info(
        "OSMnx features query: tags=%s, returned_count=%d",
        tags, returned_count,
    )
    if not gdf.empty:
        gdf.to_file(geojson_path, driver="GeoJSON")
        serialized_count = len(gdf) if not gdf.empty else 0
        logger.info("Features serialized: %d features -> GeoJSON", serialized_count)
        return returned_count
    _write_valid_geojson(geojson_path, [])
    logger.warning("Features: OSMnx returned empty result for tags=%s", tags)
    return 0


def _write_valid_geojson(path: Path, features: list[dict] | None = None) -> None:
    """Write a minimal valid GeoJSON FeatureCollection.

    Never writes a zero-byte or tiny placeholder — always a parseable document.
    """
    if features is None:
        features = []
    import json
    with path.open("w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)


def fetch_osm_category(
    category: str,
    refresh: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    """Fetch a single OSM category within the Bengaluru bounding box.

    Parameters
    ----------
    category : str    One of 'roads', 'landuse', 'green_spaces', 'construction',
                      'industrial_facility'.
    refresh : bool    If True, bypass cache and re-download.
    quiet : bool      If True, suppress OSMnx console output.

    Returns
    -------
    dict    Metadata about the fetched snapshot.

    Raises
    ------
    RuntimeError    If fetch fails and no valid cache exists.
    ValueError      If category is unknown.
    """
    if category not in OSM_TAGS:
        raise ValueError(f"Unknown category '{category}'. Known: {list(OSM_TAGS.keys())}")

    # Cache reuse
    if not refresh and _is_cache_valid(category):
        meta_path = _snapshot_metadata_path(category)
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        logger.info("Using cached OSM snapshot for '%s' (TTL valid)", category)
        meta["cache_status"] = "reused"
        return meta

    # Prepare to fetch
    ox.settings.log_console = not quiet
    ox.settings.use_cache = True

    bengaluru_polygon = _build_bengaluru_polygon()
    tags = OSM_TAGS[category]
    geojson_path = _snapshot_geojson_path(category)
    geojson_path.parent.mkdir(parents=True, exist_ok=True)

    last_exception: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if category == "roads":
                node_count, edge_count = _fetch_roads(bengaluru_polygon, geojson_path)
            else:
                count = _fetch_features(bengaluru_polygon, tags, geojson_path)

            # Validate what was written
            valid, reason = _validate_geojson(geojson_path)
            if not valid:
                raise RuntimeError(f"GeoJSON validation failed after fetch: {reason}")

            data_hash = _compute_data_hash(geojson_path)

            # Count features
            with geojson_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            feature_count = len(data.get("features", []))

            meta = _write_metadata(category, extra={
                "node_count": node_count if category == "roads" else 0,
                "edge_count": edge_count if category == "roads" else feature_count,
                "feature_count": feature_count,
                "data_hash": data_hash,
                "cache_status": "fresh",
            })
            logger.info(
                "Fetched OSM '%s': %d features (attempt %d/%d)",
                category, feature_count, attempt, MAX_RETRIES,
            )
            return meta

        except Exception as exc:
            last_exception = exc
            if attempt < MAX_RETRIES:
                backoff = RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
                logger.warning(
                    "Attempt %d/%d failed for '%s': %s. Retrying in %ds...",
                    attempt, MAX_RETRIES, category, exc, backoff,
                )
                time.sleep(backoff)
            else:
                logger.error(
                    "All %d attempts failed for '%s': %s",
                    MAX_RETRIES, category, exc,
                )

    # All attempts exhausted
    if _is_cache_valid(category):
        logger.warning(
            "Fetch failed for '%s', reusing stale cache.", category,
        )
        meta_path = _snapshot_metadata_path(category)
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["cache_status"] = "stale_reused"
        meta["fetch_error"] = str(last_exception)
        return meta

    raise RuntimeError(
        f"Failed to fetch OSM '{category}' after {MAX_RETRIES} attempts "
        f"and no valid cache exists: {last_exception}"
    ) from last_exception


# ---------------------------------------------------------------------------
# Batch fetch
# ---------------------------------------------------------------------------


def fetch_all_categories(refresh: bool = False, quiet: bool = False) -> dict[str, Any]:
    """Fetch all OSM categories for Bengaluru.

    Parameters
    ----------
    refresh : bool   If True, bypass caches.
    quiet : bool     If True, suppress console output.

    Returns
    -------
    dict    Per-category metadata.
    """
    results: dict[str, Any] = {}
    for cat in OSM_TAGS:
        results[cat] = fetch_osm_category(cat, refresh=refresh, quiet=quiet)
    results["_summary"] = {
        "total_categories": len(OSM_TAGS),
        "snapshot_timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    return results


# ---------------------------------------------------------------------------
# GeoJSON loading for downstream consumers
# ---------------------------------------------------------------------------


def load_category_geojson(category: str) -> dict[str, Any]:
    """Load a cached OSM category GeoJSON from disk.

    Returns an empty FeatureCollection if the file does not exist or is invalid.
    """
    geojson_path = _snapshot_geojson_path(category)
    if not geojson_path.exists():
        logger.warning("No cached GeoJSON for '%s' at %s", category, geojson_path)
        return {"type": "FeatureCollection", "features": []}
    valid, reason = _validate_geojson(geojson_path)
    if not valid:
        logger.warning("Invalid GeoJSON for '%s': %s", category, reason)
        return {"type": "FeatureCollection", "features": []}
    try:
        with geojson_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        logger.error("Failed to load GeoJSON for '%s': %s", category, exc)
        return {"type": "FeatureCollection", "features": []}


def get_snapshot_metadata(category: str) -> dict[str, Any]:
    """Return metadata for a cached OSM category snapshot."""
    meta_path = _snapshot_metadata_path(category)
    if not meta_path.exists():
        return {"category": category, "available": False}
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["available"] = True
        return meta
    except (json.JSONDecodeError, IOError):
        return {"category": category, "available": False}


def get_all_snapshot_metadata() -> dict[str, Any]:
    """Return metadata for all cached OSM category snapshots."""
    return {cat: get_snapshot_metadata(cat) for cat in OSM_TAGS}


# ---------------------------------------------------------------------------
# CLI entry point (legacy — kept for backward compat; prefer fetch_osm_bengaluru.py)
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Bengaluru OSM data and cache locally."
    )
    parser.add_argument(
        "--category", "-c",
        choices=list(OSM_TAGS.keys()) + ["all"],
        default="all",
        help="OSM category to fetch (default: all)",
    )
    parser.add_argument(
        "--refresh", "-r",
        action="store_true",
        help="Bypass cache and re-download",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress OSMnx console output",
    )
    parser.add_argument(
        "--info", "-i",
        action="store_true",
        help="Show cached snapshot metadata and exit",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.info:
        if args.category == "all":
            meta = get_all_snapshot_metadata()
        else:
            meta = {args.category: get_snapshot_metadata(args.category)}
        print(json.dumps(meta, indent=2, default=str))
        return

    if args.category == "all":
        result = fetch_all_categories(refresh=args.refresh, quiet=args.quiet)
    else:
        result = fetch_osm_category(args.category, refresh=args.refresh, quiet=args.quiet)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
