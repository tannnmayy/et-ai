"""
Geospatial context builder for AQI Sentinel stations.

Builds one record per station with road, land-use, and investigation-context
features derived from cached OpenStreetMap data and H3 spatial indexing.

By default, fails if required OSM layers are missing or invalid.
Use --allow-partial-osm for explicit degraded builds.

Output:
  data/processed/geospatial/station_geospatial_context.parquet
  data/reports/geospatial/geospatial_coverage_report.csv
  data/reports/geospatial/geospatial_coverage_report.md
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from shapely import wkt
from shapely.geometry import Point, shape
from shapely.ops import unary_union

import backend.app.config as _config
from pipeline.geospatial.h3_utils import (
    compute_station_h3_mapping,
    get_h3_api_version,
)
from pipeline.geospatial.osm_client import (
    OSM_TAGS,
    _snapshot_geojson_path,
    _validate_geojson,
    get_all_snapshot_metadata,
    load_category_geojson,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OSM_COMPLETENESS_DISCLAIMER: str = (
    "OpenStreetMap data is community-maintained and may be incomplete, outdated, "
    "or inconsistently tagged. Mapped features are contextual evidence only and "
    "do not represent verified registered emission sources."
)

NON_CAUSALITY_DISCLAIMER: str = (
    "Spatial features are contextual evidence and investigation signals only. "
    "They do not prove that a specific industry, construction site, road, facility, "
    "or mapped object caused pollution at this station."
)

REQUIRED_OSM_LAYERS = list(OSM_TAGS.keys())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_registry() -> pd.DataFrame:
    registry_path = _config.get_project_root() / _config.STATION_REGISTRY_PATH
    if not registry_path.exists():
        raise FileNotFoundError(
            f"Station registry not found at {registry_path}. "
            "Ensure data/reference/bengaluru_station_registry.csv exists."
        )
    df = pd.read_csv(registry_path)
    required = {"station_id", "latitude", "longitude", "city"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Station registry missing columns: {missing}")
    return df


def _point_from_row(row: pd.Series) -> Point:
    return Point(float(row["longitude"]), float(row["latitude"]))


def _buffer_in_metric(point: Point, radius_m: float) -> Any:
    """Create a circular buffer in a metric CRS and project back to WGS84."""
    import pyproj
    from shapely.ops import transform

    project = pyproj.Transformer.from_crs(
        "EPSG:4326", _config.GEOSPATIAL_METRIC_CRS, always_xy=True
    ).transform
    project_back = pyproj.Transformer.from_crs(
        _config.GEOSPATIAL_METRIC_CRS, "EPSG:4326", always_xy=True
    ).transform

    point_metric = transform(project, point)
    buffer_metric = point_metric.buffer(radius_m)
    return transform(project_back, buffer_metric)


def _area_sq_km(polygon: Any) -> float:
    """Compute area in square kilometres using metric CRS."""
    import pyproj
    from shapely.ops import transform

    project = pyproj.Transformer.from_crs(
        "EPSG:4326", _config.GEOSPATIAL_METRIC_CRS, always_xy=True
    ).transform
    poly_metric = transform(project, polygon)
    return poly_metric.area / 1_000_000.0


def _distance_m(point_a: Point, point_b: Point) -> float | None:
    """Great-circle distance in metres between two WGS84 points."""
    try:
        return point_a.distance(point_b) * 111_320.0
    except Exception:
        return None


def _load_geojson_features(category: str) -> list[dict]:
    data = load_category_geojson(category)
    return data.get("features", [])


def _safe_get(feature: dict, key: str, default: Any = None) -> Any:
    return feature.get("properties", {}).get(key, default)


# ---------------------------------------------------------------------------
# OSM layer validation
# ---------------------------------------------------------------------------


def _check_osm_layers(allow_partial: bool = False) -> dict[str, Any]:
    """Validate that required OSM layers exist and have features.

    Returns a dict with per-layer status.
    Raises RuntimeError if required layers are missing and --allow-partial-osm
    is not set.
    """
    results: dict[str, Any] = {}
    all_ok = True
    missing: list[str] = []
    empty: list[str] = []

    for layer in REQUIRED_OSM_LAYERS:
        gjson_path = _snapshot_geojson_path(layer)
        valid, reason = _validate_geojson(gjson_path)
        results[layer] = {
            "exists": gjson_path.exists(),
            "valid": valid,
            "reason": reason,
        }
        if not gjson_path.exists():
            missing.append(layer)
            all_ok = False
        elif not valid:
            empty.append(layer)
            all_ok = False
        else:
            try:
                with gjson_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if len(data.get("features", [])) == 0:
                    empty.append(layer)
                    all_ok = False
                    results[layer]["reason"] = "zero_features"
                    results[layer]["valid"] = False
            except (json.JSONDecodeError, IOError):
                empty.append(layer)
                all_ok = False
                results[layer]["valid"] = False

    results["_all_ok"] = all_ok
    results["_missing"] = missing
    results["_empty"] = empty

    if not all_ok and not allow_partial:
        parts = []
        if missing:
            parts.append(f"missing layers: {missing}")
        if empty:
            parts.append(f"empty layers: {empty}")
        raise RuntimeError(
            f"Required OSM layers are not ready: {'; '.join(parts)}. "
            "Run 'python -m pipeline.geospatial.fetch_osm_bengaluru' first, "
            "or use --allow-partial-osm for a degraded build."
        )
    return results


# ---------------------------------------------------------------------------
# Road feature extraction
# ---------------------------------------------------------------------------


def normalize_osm_tag_values(value: Any) -> list[str]:
    """Normalize an OSM tag value (possibly a list, None, NaN, or string) to a list of clean strings.

    Returns a list of lowercased, stripped non-empty strings.
    """
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    if isinstance(value, str):
        cleaned = value.strip().lower()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set, frozenset)):
        result: list[str] = []
        for item in value:
            result.extend(normalize_osm_tag_values(item))
        return result
    return [str(value).strip().lower()]


def _compute_road_features(
    station_point: Point,
    context_radius_m: float,
    road_radius_m: float,
) -> dict[str, Any]:
    """Compute road/mobility feature values for a station context.

    Returns a dict with road features and coverage status.
    """
    from shapely.geometry import shape as shapely_shape

    road_features = _load_geojson_features("roads")
    buffer = _buffer_in_metric(station_point, context_radius_m)

    total_length_m = 0.0
    major_length_m = 0.0
    road_count = 0

    major_highway_types = {
        "motorway", "trunk", "primary", "secondary",
        "motorway_link", "trunk_link", "primary_link", "secondary_link",
    }

    for feat in road_features:
        try:
            geom = shapely_shape(feat.get("geometry", {}))
        except Exception:
            continue
        if not geom.intersects(buffer):
            continue

        highway_values = normalize_osm_tag_values(_safe_get(feat, "highway"))
        is_major = any(v in major_highway_types for v in highway_values)
        intersection = geom.intersection(buffer)
        road_count += 1

        if not intersection.is_empty and intersection.geom_type in ("LineString", "MultiLineString"):
            length = intersection.length * 111_320.0
            total_length_m += length
            if is_major:
                major_length_m += length

    buffer_area_sq_km = _area_sq_km(buffer)
    road_density = total_length_m / buffer_area_sq_km if buffer_area_sq_km > 0 else None

    nearest_major_m: float | None = None
    for feat in road_features:
        try:
            geom = shapely_shape(feat.get("geometry", {}))
        except Exception:
            continue
        highway_values = normalize_osm_tag_values(_safe_get(feat, "highway"))
        if not any(v in major_highway_types for v in highway_values):
            continue
        d = station_point.distance(geom) * 111_320.0
        if nearest_major_m is None or d < nearest_major_m:
            nearest_major_m = d

    coverage_status = "complete" if total_length_m > 0 else "no_mapped_roads"
    if road_count == 0:
        coverage_status = "no_mapped_roads"

    return {
        "total_road_length_m_within_radius": round(total_length_m, 2) if total_length_m > 0 else None,
        "major_road_length_m_within_radius": round(major_length_m, 2) if major_length_m > 0 else None,
        "road_density_m_per_sq_km": round(road_density, 2) if road_density is not None else None,
        "intersection_count_within_radius": None,
        "nearest_major_road_distance_m": round(nearest_major_m, 2) if nearest_major_m is not None else None,
        "road_feature_coverage_status": coverage_status,
    }


# ---------------------------------------------------------------------------
# Land-use feature extraction
# ---------------------------------------------------------------------------


def _compute_landuse_features(
    station_point: Point,
    context_radius_m: float,
) -> dict[str, Any]:
    """Compute land-use fraction features for a station context."""
    from shapely.geometry import shape as shapely_shape

    landuse_features = _load_geojson_features("landuse")
    buffer = _buffer_in_metric(station_point, context_radius_m)
    buffer_area_sq_km = _area_sq_km(buffer)

    if buffer_area_sq_km <= 0:
        return _empty_landuse("zero_buffer_area")

    industrial_area = 0.0
    commercial_area = 0.0
    residential_area = 0.0
    green_area = 0.0
    total_mapped_area = 0.0

    green_features = _load_geojson_features("green_spaces")

    for feat in landuse_features:
        try:
            geom = shapely_shape(feat.get("geometry", {}))
        except Exception:
            continue
        if not geom.intersects(buffer):
            continue

        landuse_values = normalize_osm_tag_values(_safe_get(feat, "landuse"))
        intersection = geom.intersection(buffer)
        if intersection.is_empty:
            continue

        area = _area_sq_km(intersection)
        total_mapped_area += area

        if any(v in ("industrial", "quarry", "landfill", "brownfield") for v in landuse_values):
            industrial_area += area
        if any(v in ("commercial", "retail") for v in landuse_values):
            commercial_area += area
        if any(v in ("residential", "apartments") for v in landuse_values):
            residential_area += area

    for feat in green_features:
        try:
            geom = shapely_shape(feat.get("geometry", {}))
        except Exception:
            continue
        if not geom.intersects(buffer):
            continue
        intersection = geom.intersection(buffer)
        if intersection.is_empty:
            continue
        area = _area_sq_km(intersection)
        green_area += area

    if total_mapped_area <= 0:
        return _empty_landuse("no_mapped_landuse")

    return {
        "industrial_landuse_fraction": round(industrial_area / total_mapped_area, 4),
        "commercial_landuse_fraction": round(commercial_area / total_mapped_area, 4),
        "residential_landuse_fraction": round(residential_area / total_mapped_area, 4),
        "green_space_fraction": round(green_area / total_mapped_area, 4),
        "landuse_feature_coverage_status": "complete",
    }


def _empty_landuse(reason: str) -> dict[str, Any]:
    return {
        "industrial_landuse_fraction": None,
        "commercial_landuse_fraction": None,
        "residential_landuse_fraction": None,
        "green_space_fraction": None,
        "landuse_feature_coverage_status": reason,
    }


# ---------------------------------------------------------------------------
# Investigation context features
# ---------------------------------------------------------------------------


def _compute_investigation_context(
    station_point: Point,
    context_radius_m: float,
) -> dict[str, Any]:
    """Compute investigation-context features (construction, industrial, facility)."""
    from shapely.geometry import shape as shapely_shape

    buffer = _buffer_in_metric(station_point, context_radius_m)

    construction_features = _load_geojson_features("construction")
    industrial_features = _load_geojson_features("industrial_facility")

    construction_count = 0
    industrial_count = 0
    nearest_industrial_m: float | None = None

    for feat in construction_features:
        try:
            geom = shapely_shape(feat.get("geometry", {}))
        except Exception:
            continue
        if geom.intersects(buffer):
            construction_count += 1

    for feat in industrial_features:
        try:
            geom = shapely_shape(feat.get("geometry", {}))
        except Exception:
            continue
        if geom.intersects(buffer):
            industrial_count += 1
            d = station_point.distance(geom) * 111_320.0
            if nearest_industrial_m is None or d < nearest_industrial_m:
                nearest_industrial_m = d

    coverage_status = "complete"
    if construction_count == 0 and industrial_count == 0:
        coverage_status = "no_features_found"
    if construction_count == 0:
        coverage_status = "no_construction_found"
    if industrial_count == 0:
        coverage_status = "no_industrial_found"
    if construction_count == 0 and industrial_count == 0:
        coverage_status = "no_mapped_investigation_features"

    return {
        "construction_feature_count_within_radius": construction_count,
        "mapped_industrial_or_facility_count_within_radius": industrial_count,
        "nearest_mapped_industrial_or_facility_distance_m": (
            round(nearest_industrial_m, 2) if nearest_industrial_m is not None else None
        ),
        "investigation_context_coverage_status": coverage_status,
    }


# ---------------------------------------------------------------------------
# Data completeness scoring
# ---------------------------------------------------------------------------


def _compute_completeness(
    road: dict[str, Any],
    landuse: dict[str, Any],
    investigation: dict[str, Any],
) -> float:
    """Compute a data completeness score from 0.0 to 1.0 based on which feature groups are available."""
    scores = {
        "road": 1.0 if road.get("road_feature_coverage_status") == "complete" else 0.0,
        "landuse": 1.0 if landuse.get("landuse_feature_coverage_status") == "complete" else 0.0,
        "investigation": 1.0 if investigation.get("investigation_context_coverage_status") == "complete" else 0.0,
    }
    return round(sum(scores.values()) / len(scores), 4)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_geospatial_context(allow_partial_osm: bool = False) -> dict[str, Any]:
    """Build the station geospatial context artifact.

    Parameters
    ----------
    allow_partial_osm : bool
        If True, proceed even if some OSM layers are missing/invalid.
        The artifact will be marked as partial.

    Returns
    -------
    dict    Build metadata summary.

    Raises
    ------
    RuntimeError    If OSM layers are incomplete and allow_partial_osm is False.
    """
    project_root = _config.get_project_root()
    processed_dir = _ensure_dir(project_root / _config.GEOSPATIAL_PROCESSED_DIR)
    reports_dir = _ensure_dir(project_root / _config.GEOSPATIAL_REPORTS_DIR)

    # Validate OSM layers
    layer_status = _check_osm_layers(allow_partial=allow_partial_osm)
    is_partial = not layer_status.get("_all_ok", True)

    # Load station registry
    registry = _load_registry()
    registry = compute_station_h3_mapping(registry)
    logger.info("Loaded %d stations from registry", len(registry))

    osm_meta = get_all_snapshot_metadata()
    osm_snapshot_ts = None
    for cat_meta in osm_meta.values():
        if cat_meta.get("snapshot_timestamp"):
            osm_snapshot_ts = cat_meta["snapshot_timestamp"]
            break

    records: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []

    for _, row in registry.iterrows():
        station_id = row["station_id"]
        lat = float(row["latitude"])
        lon = float(row["longitude"])
        h3_cell = row.get("h3_cell")
        city = row.get("city", "bengaluru")

        station_point = Point(lon, lat)

        # Road features
        road = _compute_road_features(
            station_point,
            context_radius_m=_config.STATION_CONTEXT_RADIUS_METERS,
            road_radius_m=_config.ROAD_CONTEXT_RADIUS_METERS,
        )

        # Land-use features
        landuse = _compute_landuse_features(
            station_point,
            context_radius_m=_config.STATION_CONTEXT_RADIUS_METERS,
        )

        # Investigation context
        investigation = _compute_investigation_context(
            station_point,
            context_radius_m=_config.GEOSPATIAL_INVESTIGATION_CONTEXT_RADIUS_METERS,
        )

        # Completeness
        completeness = _compute_completeness(road, landuse, investigation)

        # Collect limitations
        limitations = []
        if road.get("road_feature_coverage_status") != "complete":
            limitations.append(f"Road features: {road['road_feature_coverage_status']}")
        if landuse.get("landuse_feature_coverage_status") != "complete":
            limitations.append(f"Land-use features: {landuse['landuse_feature_coverage_status']}")
        if investigation.get("investigation_context_coverage_status") != "complete":
            limitations.append(
                f"Investigation context: {investigation['investigation_context_coverage_status']}"
            )
        limitations.append(OSM_COMPLETENESS_DISCLAIMER)
        limitations.append(NON_CAUSALITY_DISCLAIMER)

        record = {
            "station_id": station_id,
            "city": city,
            "latitude": lat,
            "longitude": lon,
            "h3_cell": h3_cell,
            "context_radius_meters": _config.STATION_CONTEXT_RADIUS_METERS,
            **road,
            **landuse,
            **investigation,
            "osm_snapshot_timestamp": osm_snapshot_ts,
            "feature_builder_version": _config.GEOSPATIAL_FEATURE_BUILDER_VERSION,
            "data_completeness_score": completeness,
            "limitations": " | ".join(limitations),
        }
        records.append(record)

        # Coverage row
        coverage_rows.append({
            "station_id": station_id,
            "road_coverage": road["road_feature_coverage_status"],
            "landuse_coverage": landuse["landuse_feature_coverage_status"],
            "investigation_coverage": investigation["investigation_context_coverage_status"],
            "completeness_score": completeness,
        })

    # Write Parquet
    df = pd.DataFrame(records)
    parquet_path = processed_dir / "station_geospatial_context.parquet"
    df.to_parquet(parquet_path, index=False)
    logger.info("Wrote geospatial context to %s (%d rows)", parquet_path, len(df))

    # Write coverage CSV
    cov_df = pd.DataFrame(coverage_rows)
    cov_csv_path = reports_dir / "geospatial_coverage_report.csv"
    cov_df.to_csv(cov_csv_path, index=False)
    logger.info("Wrote coverage CSV to %s", cov_csv_path)

    # Write coverage MD report
    md_path = reports_dir / "geospatial_coverage_report.md"
    _write_md_report(md_path, records, osm_meta, layer_status, is_partial)
    logger.info("Wrote coverage MD report to %s", md_path)

    # Write JSON metadata
    meta = {
        "artifact": "station_geospatial_context",
        "build_status": "partial" if is_partial else "full",
        "feature_builder_version": _config.GEOSPATIAL_FEATURE_BUILDER_VERSION,
        "h3_resolution": 9,
        "h3_library_version": get_h3_api_version(),
        "stations_count": len(records),
        "registry_station_count": len(records),
        "geospatial_station_count": len([r for r in records if r.get("road_feature_coverage_status") == "complete"]),
        "station_ids_included": sorted([r["station_id"] for r in records]),
        "osm_snapshot_timestamp": osm_snapshot_ts,
        "context_radius_meters": _config.STATION_CONTEXT_RADIUS_METERS,
        "road_context_radius_meters": _config.ROAD_CONTEXT_RADIUS_METERS,
        "investigation_context_radius_meters": _config.GEOSPATIAL_INVESTIGATION_CONTEXT_RADIUS_METERS,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "bounding_box": _config.BENGALURU_BOUNDING_BOX,
        "metric_crs": _config.GEOSPATIAL_METRIC_CRS,
        "layer_status": layer_status,
        "disclaimers": {
            "osm_completeness": OSM_COMPLETENESS_DISCLAIMER,
            "non_causality": NON_CAUSALITY_DISCLAIMER,
        },
    }

    # In partial mode, add build limitation to the metadata
    if is_partial:
        meta["build_limitation"] = (
            "Partial build: one or more OSM layers were missing or empty. "
            "Feature completeness and investigation-context coverage may be "
            "significantly reduced. Run 'python -m pipeline.geospatial.fetch_osm_bengaluru' "
            "to fetch all layers, then rebuild."
        )
        meta["disclaimers"]["partial_build"] = meta["build_limitation"]

    meta_path = processed_dir / "geospatial_build_metadata.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)
    logger.info("Wrote build metadata to %s", meta_path)

    return meta


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------


def _write_md_report(
    path: Path,
    records: list[dict],
    osm_meta: dict[str, Any],
    layer_status: dict[str, Any],
    is_partial: bool,
) -> None:
    lines: list[str] = [
        "# Geospatial Coverage Report",
        "",
        f"**Generated:** {datetime.now(tz=timezone.utc).isoformat()}",
        f"**Feature Builder Version:** {_config.GEOSPATIAL_FEATURE_BUILDER_VERSION}",
        f"**Build Status:** {'PARTIAL' if is_partial else 'FULL'}",
        "",
    ]

    if is_partial:
        lines.extend([
            "> **Warning:** This is a partial build. One or more OSM layers were missing or empty.",
            "> Spatial context features may be incomplete. Run `python -m pipeline.geospatial.fetch_osm_bengaluru` to fetch all layers.",
            "",
        ])

    lines.append("## OSM Layer Status")
    lines.append("")
    lines.append("| Layer | Exists | Valid | Features | Cache Status | Snapshot Timestamp |")
    lines.append("|-------|--------|-------|----------|-------------|--------------------|")

    for layer in ["roads", "landuse", "green_spaces", "construction", "industrial_facility"]:
        ls = layer_status.get(layer, {})
        exists = "Yes" if ls.get("exists") else "No"
        valid = "Yes" if ls.get("valid") else "No"
        reason = ls.get("reason", "")
        meta = osm_meta.get(layer, {})
        cache_status = meta.get("cache_status", "N/A")
        ts = meta.get("snapshot_timestamp", "N/A")
        # Extract feature count from reason
        feat_count = reason.split("(")[-1].replace(")", "") if "features" in reason else reason
        lines.append(f"| {layer} | {exists} | {valid} | {feat_count} | {cache_status} | {ts} |")

    lines.extend([
        "",
        "## Summary",
        "",
        f"- **Stations processed:** {len(records)}",
    ])

    for cat, meta in osm_meta.items():
        ts = meta.get("snapshot_timestamp", "N/A")
        status = meta.get("cache_status", "unknown")
        lines.append(f"- **OSM '{cat}' snapshot:** {ts} ({status})")

    lines.extend([
        "",
        "## Feature Definitions",
        "",
        "### Road / Mobility Proxies",
        "- `total_road_length_m_within_radius`: Sum length of all mapped roads within station context radius.",
        "- `major_road_length_m_within_radius`: Sum length of major roads (motorway/trunk/primary/secondary).",
        "- `road_density_m_per_sq_km`: Total road length divided by buffer area.",
        "- `nearest_major_road_distance_m`: Distance to nearest major road.",
        "- `road_feature_coverage_status`: 'complete' or reason for absence.",
        "",
        "### Land-Use Context",
        "- `industrial_landuse_fraction`: Fraction of mapped land-use area classified as industrial.",
        "- `commercial_landuse_fraction`: Fraction of mapped land-use area classified as commercial.",
        "- `residential_landuse_fraction`: Fraction of mapped land-use area classified as residential.",
        "- `green_space_fraction`: Fraction of mapped area classified as greenspace (parks, forests, etc.).",
        "- `landuse_feature_coverage_status`: 'complete' or reason for absence.",
        "",
        "### Investigation Context",
        "- `construction_feature_count_within_radius`: Count of OSM features with construction tags.",
        "- `mapped_industrial_or_facility_count_within_radius`: Count of industrial/facility mapped features.",
        "- `nearest_mapped_industrial_or_facility_distance_m`: Distance to nearest mapped industrial feature.",
        "- `investigation_context_coverage_status`: 'complete' or reason.",
        "",
        "## Per-Station Coverage",
        "",
        "| Station | Road | Land-use | Investigation | Completeness |",
        "|---------|------|----------|---------------|-------------|",
    ])

    for rec in records:
        sid = rec["station_id"]
        rc = rec.get("road_feature_coverage_status", "N/A")
        lc = rec.get("landuse_feature_coverage_status", "N/A")
        ic = rec.get("investigation_context_coverage_status", "N/A")
        cs = rec.get("data_completeness_score", 0)
        lines.append(f"| {sid} | {rc} | {lc} | {ic} | {cs} |")

    lines.extend([
        "",
        "## Null / Coverage Semantics",
        "",
        "- **No mapped object found:** Feature value is `None` and coverage status starts with `no_`.",
        "- **Data unavailable:** Coverage status indicates the category was not fetched or has no data.",
        "- **Feature calculation failed:** Status will describe the failure reason (e.g., `zero_buffer_area`).",
        "- **Incomplete OSM tagging:** Limitations field documents known gaps.",
        "",
        "## Disclaimers",
        "",
        f"- {OSM_COMPLETENESS_DISCLAIMER}",
        f"- {NON_CAUSALITY_DISCLAIMER}",
        "",
        "## Radii",
        "",
        f"- Station context radius: {_config.STATION_CONTEXT_RADIUS_METERS}m",
        f"- Road context radius: {_config.ROAD_CONTEXT_RADIUS_METERS}m",
        f"- Investigation context radius: {_config.GEOSPATIAL_INVESTIGATION_CONTEXT_RADIUS_METERS}m",
    ])

    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Build station geospatial context from cached OSM data."
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force rebuild even if output exists",
    )
    parser.add_argument(
        "--allow-partial-osm", "-p",
        action="store_true",
        help="Allow build even if some OSM layers are missing/empty (degraded mode)",
    )

    args = parser.parse_args()

    processed_dir = _config.get_project_root() / _config.GEOSPATIAL_PROCESSED_DIR
    parquet_path = processed_dir / "station_geospatial_context.parquet"
    if parquet_path.exists() and not args.force:
        # Check if the existing artifact is partial or full
        meta_path = processed_dir / "geospatial_build_metadata.json"
        build_status = "unknown"
        if meta_path.exists():
            try:
                with meta_path.open("r") as f:
                    meta = json.load(f)
                build_status = meta.get("build_status", "unknown")
            except (json.JSONDecodeError, IOError):
                pass

        logger.info(
            "Geospatial context already exists at %s (build_status=%s). "
            "Use --force to rebuild.",
            parquet_path, build_status,
        )
        return

    try:
        result = build_geospatial_context(allow_partial_osm=args.allow_partial_osm)
        print(json.dumps(result, indent=2, default=str))
    except RuntimeError as e:
        logger.error(str(e))
        print(json.dumps({"error": str(e), "build_status": "failed"}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
