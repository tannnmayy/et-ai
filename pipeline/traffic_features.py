"""Static high-traffic corridor features from OSM major roads.

Computes per-hexagon:
  - traffic_corridor_score (0.0–1.0): normalized major-road length density
  - is_major_road_corridor (bool): whether the hex meaningfully overlaps
    motorway / trunk / primary / secondary roads

Used by pipeline/build_hexagon_features.py and by
pipeline.augment_hexagon_traffic_corridors for incremental updates of an
existing hexagon_features.parquet without a full OSM rebuild.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from shapely.geometry import Polygon, shape
from shapely.strtree import STRtree

from backend.app.config import GEOSPATIAL_METRIC_CRS

logger = logging.getLogger(__name__)

# OSM highway classes treated as high-traffic corridors (arterial / freeflow).
MAJOR_HIGHWAY_TAGS: frozenset[str] = frozenset({
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
})

# Major-road length density (m road / m² cell) that maps to traffic_corridor_score=1.0.
# Tuned for H3 res-9 (~0.1 km² cells): a few hundred metres of arterial road
# already indicates a meaningful corridor.
MAJOR_ROAD_DENSITY_SATURATION: float = 0.04

# Corridor flag when score is at or above this fraction of saturation.
CORRIDOR_FLAG_SCORE_THRESHOLD: float = 0.25


def normalize_highway_tag(raw: Any) -> str:
    """Normalize OSM highway property (str, list, or stringified list) to one tag."""
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        for item in raw:
            tag = str(item).strip().lower()
            if tag:
                return tag
        return ""
    text = str(raw).strip().lower()
    if not text or text in {"nan", "none", "null"}:
        return ""
    # Handle pyogrio/pandas stringified lists: "['primary']" or "[primary]"
    if text.startswith("["):
        text = text.strip("[]").replace("'", "").replace('"', "")
        parts = [p.strip() for p in text.split(",") if p.strip()]
        return parts[0] if parts else ""
    return text


def is_major_highway(raw: Any) -> bool:
    return normalize_highway_tag(raw) in MAJOR_HIGHWAY_TAGS


def _project_geometry(geom: Any) -> Any:
    try:
        import pyproj
        from shapely.ops import transform

        proj = pyproj.Transformer.from_crs("EPSG:4326", GEOSPATIAL_METRIC_CRS, always_xy=True)
        return transform(proj.transform, geom)
    except ImportError:
        return geom


def _geographic_area_sq_m(polygon: Polygon) -> float:
    try:
        import pyproj
        from shapely.ops import transform

        proj = pyproj.Transformer.from_crs("EPSG:4326", GEOSPATIAL_METRIC_CRS, always_xy=True)
        return float(transform(proj.transform, polygon).area)
    except ImportError:
        # Fallback: rough planar estimate (same style as build_hexagon_features)
        if polygon.is_empty:
            return 0.0
        coords = list(polygon.exterior.coords)
        if len(coords) < 3:
            return 0.0
        R = 6371000.0
        area = 0.0
        for i in range(len(coords) - 1):
            lon1, lat1 = coords[i]
            lon2, lat2 = coords[i + 1]
            area += np.radians(lon2 - lon1) * (
                2 + np.sin(np.radians(lat1)) + np.sin(np.radians(lat2))
            )
        return abs(area * R * R / 2.0)


def filter_major_road_geometries(
    road_geoms: list[Any],
    road_props: list[dict],
) -> tuple[list[Any], STRtree]:
    """Keep only major-highway geometries for corridor scoring."""
    major: list[Any] = []
    for geom, props in zip(road_geoms, road_props):
        if is_major_highway(props.get("highway")):
            major.append(geom)
    tree = STRtree(major) if major else STRtree([])
    logger.info(
        "Major-road corridor filter: %d / %d road features retained (tags=%s)",
        len(major),
        len(road_geoms),
        sorted(MAJOR_HIGHWAY_TAGS),
    )
    return major, tree


def major_road_length_m(
    hex_poly: Polygon,
    major_geoms: list[Any],
    major_tree: STRtree,
) -> float:
    """Clipped length (metres) of major roads intersecting a hexagon."""
    if not major_geoms:
        return 0.0
    total = 0.0
    candidates = major_tree.query(hex_poly)
    for idx in candidates:
        geom = major_geoms[idx]
        if hex_poly.intersects(geom):
            clipped = hex_poly.intersection(geom)
            if not clipped.is_empty:
                total += float(_project_geometry(clipped).length)
    return total


def score_from_major_length(major_length_m: float, cell_area_sq_m: float) -> tuple[float, bool]:
    """Map major-road length + cell area → (traffic_corridor_score, is_major_road_corridor)."""
    if cell_area_sq_m <= 0 or major_length_m <= 0:
        return 0.0, False
    density = major_length_m / cell_area_sq_m
    score = float(min(1.0, max(0.0, density / MAJOR_ROAD_DENSITY_SATURATION)))
    is_corridor = score >= CORRIDOR_FLAG_SCORE_THRESHOLD
    return round(score, 4), is_corridor


def compute_corridor_columns_for_hex_df(
    hex_df: pd.DataFrame,
    major_geoms: list[Any],
    major_tree: STRtree,
    polygon_col: str = "polygon",
) -> pd.DataFrame:
    """Add traffic_corridor_score and is_major_road_corridor columns to a copy of hex_df.

    Expects either a ``polygon`` column of Shapely polygons or will rebuild
    polygons from h3_cell if polygon_col is missing.
    """
    out = hex_df.copy()
    scores: list[float] = []
    flags: list[bool] = []
    major_lengths: list[float] = []

    has_poly = polygon_col in out.columns
    if not has_poly:
        import h3 as _h3
        from shapely.geometry import Polygon as ShapelyPolygon

        def _poly_for(cell: str) -> Polygon:
            boundary = _h3.cell_to_boundary(cell)
            return ShapelyPolygon([(lon, lat) for lat, lon in boundary])

    for idx, row in out.iterrows():
        if has_poly:
            hex_poly = row[polygon_col]
        else:
            hex_poly = _poly_for(str(row["h3_cell"]))
        area = _geographic_area_sq_m(hex_poly)
        length = major_road_length_m(hex_poly, major_geoms, major_tree)
        score, flag = score_from_major_length(length, area)
        scores.append(score)
        flags.append(flag)
        major_lengths.append(round(length, 2))
        if (len(scores) % 1000) == 0:
            logger.info("Corridor scoring: %d / %d hexagons", len(scores), len(out))

    out["traffic_corridor_score"] = scores
    out["is_major_road_corridor"] = flags
    # Intermediate diagnostic column is useful for pipeline QA; safe to keep.
    out["major_road_length_m"] = major_lengths
    n_flagged = int(sum(flags))
    logger.info(
        "Corridor scores complete: %d / %d hexagons flagged as major-road corridors "
        "(mean score=%.4f)",
        n_flagged,
        len(out),
        float(np.mean(scores)) if scores else 0.0,
    )
    return out


def load_major_roads_from_geojson_category() -> tuple[list[Any], STRtree]:
    """Load roads OSM snapshot and return major-road geoms + STRtree."""
    from pipeline.geospatial.osm_client import load_category_geojson

    geojson = load_category_geojson("roads")
    geoms: list[Any] = []
    props_list: list[dict] = []
    for feat in geojson.get("features", []):
        geom_data = feat.get("geometry")
        if geom_data is None:
            continue
        shp = shape(geom_data)
        if shp.is_empty:
            continue
        geoms.append(shp)
        props_list.append(feat.get("properties") or {})
    return filter_major_road_geometries(geoms, props_list)
