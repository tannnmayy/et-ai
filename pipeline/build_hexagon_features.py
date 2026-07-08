from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon, shape
from shapely.strtree import STRtree

from backend.app.config import (
    BENGALURU_BOUNDING_BOX,
    GEOSPATIAL_METRIC_CRS,
    H3_RESOLUTION,
    get_project_root,
)
from pipeline.geospatial.osm_client import load_category_geojson

logger = logging.getLogger(__name__)

CATEGORIES = ["roads", "landuse", "green_spaces", "construction", "industrial_facility", "vulnerability"]

INDUSTRIAL_LANDUSE_VALS = {"industrial", "quarry", "landfill", "brownfield"}
COMMERCIAL_LANDUSE_VALS = {"commercial", "retail"}
RESIDENTIAL_LANDUSE_VALS = {"residential", "apartments"}

GREEN_LANDUSE_VALS = {"forest", "meadow", "grass", "recreation_ground", "village_green"}
GREEN_LEISURE_VALS = {"park", "garden", "nature_reserve", "golf_course", "playground", "pitch", "sports_centre"}
GREEN_NATURAL_VALS = {"wood", "scrub", "heath", "grassland", "tree", "tree_row"}


def _geographic_area_sq_m(polygon: Polygon | MultiPolygon) -> float:
    try:
        import pyproj
        from shapely.ops import transform

        proj = pyproj.Transformer.from_crs("EPSG:4326", GEOSPATIAL_METRIC_CRS, always_xy=True)
        projected = transform(proj.transform, polygon)
        return projected.area
    except ImportError:
        return _haversine_area_estimate(polygon)


def _haversine_area_estimate(polygon: Polygon | MultiPolygon) -> float:
    if polygon.is_empty:
        return 0.0
    if polygon.geom_type == "MultiPolygon":
        return sum(_haversine_area_estimate(p) for p in polygon.geoms)
    coords = list(polygon.exterior.coords)
    if len(coords) < 3:
        return 0.0
    R = 6371000
    area = 0.0
    for i in range(len(coords) - 1):
        lon1, lat1 = coords[i]
        lon2, lat2 = coords[i + 1]
        area += np.radians(lon2 - lon1) * (
            2 + np.sin(np.radians(lat1)) + np.sin(np.radians(lat2))
        )
    return abs(area * R * R / 2.0)


def _project_geometry(geom: Any) -> Any:
    try:
        import pyproj
        from shapely.ops import transform

        proj = pyproj.Transformer.from_crs("EPSG:4326", GEOSPATIAL_METRIC_CRS, always_xy=True)
        return transform(proj.transform, geom)
    except ImportError:
        return geom


def _get_hex_grid() -> pd.DataFrame:
    bbox = BENGALURU_BOUNDING_BOX
    north, south = bbox["north"], bbox["south"]
    east, west = bbox["east"], bbox["west"]
    res = H3_RESOLUTION

    cells = h3.polygon_to_cells(
        h3.LatLngPoly([(south, west), (south, east), (north, east), (north, west)]),
        res,
    )

    rows = []
    for cell in sorted(cells):
        center = h3.cell_to_latlng(cell)
        boundary = h3.cell_to_boundary(cell)
        polygon = Polygon([(lon, lat) for lat, lon in boundary])
        rows.append({
            "h3_cell": cell,
            "center_lat": center[0],
            "center_lon": center[1],
            "polygon": polygon,
        })

    df = pd.DataFrame(rows)
    logger.info("Generated %d H3 res-%d cells in Bengaluru bounding box", len(df), res)
    return df


def _load_geometries(category: str) -> tuple[list[Any], list[dict], STRtree]:
    geojson = load_category_geojson(category)
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
        props_list.append(feat.get("properties", {}))

    tree = STRtree(geoms) if geoms else STRtree([])
    logger.info("Loaded %d features for '%s'", len(geoms), category)
    return geoms, props_list, tree


def _road_length_for_hexagon(hex_poly: Polygon, road_geoms: list[Any], road_tree: STRtree) -> float:
    total = 0.0
    candidates = road_tree.query(hex_poly)
    for idx in candidates:
        geom = road_geoms[idx]
        if hex_poly.intersects(geom):
            clipped = hex_poly.intersection(geom)
            if not clipped.is_empty:
                total += _project_geometry(clipped).length
    return total


def _landuse_areas_for_hexagon(
    hex_poly: Polygon,
    landuse_geoms: list[Any],
    landuse_props: list[dict],
    landuse_tree: STRtree,
) -> dict[str, float]:
    result = {
        "industrial_area_sq_m": 0.0,
        "commercial_area_sq_m": 0.0,
        "residential_area_sq_m": 0.0,
        "green_space_area_sq_m": 0.0,
        "other_landuse_area_sq_m": 0.0,
    }

    candidates = landuse_tree.query(hex_poly)
    for idx in candidates:
        geom = landuse_geoms[idx]
        if not geom.intersects(hex_poly):
            continue
        intersection = hex_poly.intersection(geom)
        if intersection.is_empty:
            continue
        inter_area = _geographic_area_sq_m(intersection)

        props = landuse_props[idx]
        landuse_val = (props.get("landuse") or "").lower()
        leisure_val = (props.get("leisure") or "").lower()
        natural_val = (props.get("natural") or "").lower()

        if landuse_val in INDUSTRIAL_LANDUSE_VALS:
            result["industrial_area_sq_m"] += inter_area
        elif landuse_val in COMMERCIAL_LANDUSE_VALS:
            result["commercial_area_sq_m"] += inter_area
        elif landuse_val in RESIDENTIAL_LANDUSE_VALS:
            result["residential_area_sq_m"] += inter_area
        elif landuse_val in GREEN_LANDUSE_VALS or leisure_val in GREEN_LEISURE_VALS or natural_val in GREEN_NATURAL_VALS:
            result["green_space_area_sq_m"] += inter_area
        else:
            result["other_landuse_area_sq_m"] += inter_area

    return result


def _count_intersecting(hex_poly: Polygon, geoms: list[Any], tree: STRtree) -> int:
    count = 0
    candidates = tree.query(hex_poly)
    for idx in candidates:
        if geoms[idx].intersects(hex_poly):
            count += 1
    return count


def _green_area_for_hexagon(
    hex_poly: Polygon,
    green_geoms: list[Any],
    green_tree: STRtree,
) -> float:
    total = 0.0
    candidates = green_tree.query(hex_poly)
    for idx in candidates:
        geom = green_geoms[idx]
        if not geom.intersects(hex_poly):
            continue
        inter = hex_poly.intersection(geom)
        if not inter.is_empty:
            total += _geographic_area_sq_m(inter)
    return total


def build_hexagon_features(output_path: str | Path | None = None) -> pd.DataFrame:
    root = get_project_root()
    logger.info("Building hexagon features for Bengaluru...")

    hex_df = _get_hex_grid()
    logger.info("Hex grid generated: %d cells", len(hex_df))

    road_geoms, _, road_tree = _load_geometries("roads")
    landuse_geoms, landuse_props, landuse_tree = _load_geometries("landuse")
    construction_geoms, _, construction_tree = _load_geometries("construction")
    facility_geoms, _, facility_tree = _load_geometries("industrial_facility")
    green_geoms, _, green_tree = _load_geometries("green_spaces")
    vulnerability_geoms, _, vulnerability_tree = _load_geometries("vulnerability")

    cell_areas: list[float] = []
    road_lengths: list[float] = []
    industrial_areas: list[float] = []
    commercial_areas: list[float] = []
    residential_areas: list[float] = []
    green_areas: list[float] = []
    other_landuse_areas: list[float] = []
    construction_counts: list[int] = []
    facility_counts: list[int] = []
    vulnerability_counts: list[int] = []

    for idx, row in hex_df.iterrows():
        hex_poly = row["polygon"]
        area = _geographic_area_sq_m(hex_poly)
        cell_areas.append(area)

        road_lengths.append(_road_length_for_hexagon(hex_poly, road_geoms, road_tree))

        lf = _landuse_areas_for_hexagon(hex_poly, landuse_geoms, landuse_props, landuse_tree)
        industrial_areas.append(lf["industrial_area_sq_m"])
        commercial_areas.append(lf["commercial_area_sq_m"])
        residential_areas.append(lf["residential_area_sq_m"])
        green_areas.append(lf["green_space_area_sq_m"])
        other_landuse_areas.append(lf["other_landuse_area_sq_m"])

        green_areas[idx] += _green_area_for_hexagon(hex_poly, green_geoms, green_tree)

        construction_counts.append(_count_intersecting(hex_poly, construction_geoms, construction_tree))
        facility_counts.append(_count_intersecting(hex_poly, facility_geoms, facility_tree))
        vulnerability_counts.append(_count_intersecting(hex_poly, vulnerability_geoms, vulnerability_tree))

        if (idx + 1) % 500 == 0:
            logger.info("Processed %d / %d hexagons", idx + 1, len(hex_df))

    result_df = pd.DataFrame({
        "h3_cell": hex_df["h3_cell"],
        "center_lat": hex_df["center_lat"],
        "center_lon": hex_df["center_lon"],
        "cell_area_sq_m": cell_areas,
        "road_length_m": road_lengths,
        "industrial_area_sq_m": industrial_areas,
        "commercial_area_sq_m": commercial_areas,
        "residential_area_sq_m": residential_areas,
        "green_space_area_sq_m": green_areas,
        "other_landuse_area_sq_m": other_landuse_areas,
        "construction_feature_count": construction_counts,
        "industrial_facility_count": facility_counts,
        "vulnerability_feature_count": vulnerability_counts,
    })

    valid_areas = result_df["cell_area_sq_m"].replace(0, np.nan)
    result_df["road_density_m_per_sq_m"] = (result_df["road_length_m"] / valid_areas).fillna(0.0)
    area_sq_km = valid_areas / 1_000_000.0
    result_df["vulnerability_feature_density_per_sq_km"] = (result_df["vulnerability_feature_count"] / area_sq_km).fillna(0.0)

    for col in ["industrial_area_sq_m", "commercial_area_sq_m", "residential_area_sq_m",
                "green_space_area_sq_m", "other_landuse_area_sq_m"]:
        frac_col = col.replace("area_sq_m", "fraction")
        result_df[frac_col] = (result_df[col] / valid_areas).fillna(0.0).clip(0, 1)

    result_df = result_df.drop(columns=["cell_area_sq_m"])
    result_df = result_df.sort_values("h3_cell").reset_index(drop=True)

    if output_path is None:
        output_path = root / "data" / "processed" / "geospatial" / "hexagon_features.parquet"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_parquet(str(output_path), index=False)
    logger.info("Wrote %d hexagon features to %s", len(result_df), output_path)

    return result_df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_hexagon_features()
