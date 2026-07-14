"""Aggregate environmental + infrastructure features per canonical locality.

For each locality in locality_registry.json, finds H3 hexagons within a
CATCHMENT_RADIUS_M (~1.75 km) of the locality centroid and aggregates:

  - fused_pm25  (estimate_fused_pm25 — build-time snapshot used as offline
    fallback; online matching can overlay a live fuse) -> aqi
  - source_attribution  (wind-weighted attribution averaged over catchment)
  - green_space_fraction -> parkScore (0-100)
  - hospital / school POI counts from vulnerability.geojson (split by amenity)
  - road_density_m_per_sq_m -> noiseScore (0-100)
  - construction_feature_count -> constructionActivityScore (0-100)
  - nearest Namma Metro / subway station distance from bengaluru_metro_stations.json

Hospital vs school split:
  OSM vulnerability features are loaded from data/raw/geospatial/osm/vulnerability.geojson
  and classified by amenity/healthcare tags into hospital-like vs school-like
  POIs. Counts within the catchment radius are scaled to 0–100 independently.
  (hexagon_features.parquet still has a combined vulnerability column; we do
  not rely on it here so citizen scores work without rebuilding that parquet.)

Metro:
  pipeline/reference/bengaluru_metro_stations.json (built via OSM). If the
  file is missing or empty, metro_distance_km=null and metro_data_available=false.

Run:
    python -m pipeline.build_locality_environment_cache
"""

from __future__ import annotations

import json
import logging
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.config import HEXAGON_FEATURES_PATH, OSM_CACHE_DIR, get_project_root
from backend.app.services.attribution_service import (
    _build_firms_lookup,
    _build_no2_lookup,
    _get_current_wind,
    compute_attribution_for_hexagon,
)
from backend.app.services.fusion_estimation_service import estimate_fused_pm25

logger = logging.getLogger(__name__)

# Catchment radius around each locality centroid (~1.5–2 km band).
CATCHMENT_RADIUS_M = 1750.0
_EARTH_RADIUS_M = 6_371_000.0

# ---------------------------------------------------------------------------
# Score scaling (design choices — documented for review)
#
# parkScore: green_space_fraction is already 0–1 (fraction of hex area).
#   Score = min(100, fraction / GREEN_SPACE_SATURATION * 100).
#   GREEN_SPACE_SATURATION=0.25 means 25% green cover scores a perfect 100.
#
# noiseScore: road_density / ROAD_DENSITY_SATURATION * 100, clipped 0–100.
#
# constructionActivityScore: mean construction_feature_count / CONSTRUCTION_SATURATION.
#
# hospitalScore / schoolScore: POI *counts* inside the catchment (not density
#   from the combined hexagon column). HOSPITAL_COUNT_SATURATION / SCHOOL_COUNT_
#   SATURATION are the counts that map to 100. A catchment with 8+ hospitals
#   or 12+ schools is "well served" for citizen matching purposes.
# ---------------------------------------------------------------------------
GREEN_SPACE_SATURATION = 0.25
ROAD_DENSITY_SATURATION = 0.08
CONSTRUCTION_SATURATION = 5.0
# Higher saturations so dense central neighbourhoods still differentiate
# (Indiranagar has 100+ clinic/hospital POIs in a 1.75 km catchment).
HOSPITAL_COUNT_SATURATION = 40.0
SCHOOL_COUNT_SATURATION = 30.0

# Pharmacy is intentionally excluded — it is extremely dense in OSM and would
# saturate hospitalScore everywhere without discriminating real healthcare access.
HOSPITAL_AMENITIES = frozenset({
    "hospital", "clinic", "doctors", "nursing_home",
})
SCHOOL_AMENITIES = frozenset({
    "school", "kindergarten", "college", "university",
})


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return _EARTH_RADIUS_M * 2 * asin(sqrt(a))


def _haversine_m_vectorized(
    lat1: float, lon1: float, lats: np.ndarray, lons: np.ndarray
) -> np.ndarray:
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lats_r, lons_r = np.radians(lats), np.radians(lons)
    dlat = lats_r - lat1_r
    dlon = lons_r - lon1_r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_r) * np.cos(lats_r) * np.sin(dlon / 2.0) ** 2
    return 2 * _EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _scale_0_100(value: float, saturation: float) -> float:
    if saturation <= 0:
        return 0.0
    return float(round(min(100.0, max(0.0, (value / saturation) * 100.0)), 1))


def _load_hex_df() -> pd.DataFrame:
    root = get_project_root()
    path = root / HEXAGON_FEATURES_PATH
    if not path.exists():
        raise FileNotFoundError(f"Hexagon features not found: {path}")
    return pd.read_parquet(str(path))


def _catchment_mask(
    hex_df: pd.DataFrame, lat: float, lon: float, radius_m: float = CATCHMENT_RADIUS_M
) -> np.ndarray:
    dists = _haversine_m_vectorized(
        lat, lon,
        hex_df["center_lat"].to_numpy(dtype=float),
        hex_df["center_lon"].to_numpy(dtype=float),
    )
    return dists <= radius_m


def _feature_centroid(geom: dict[str, Any] | None) -> tuple[float, float] | None:
    """Return (lat, lon) for a GeoJSON geometry (point or polygon centroid)."""
    if not geom:
        return None
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None
    try:
        if gtype == "Point":
            lon, lat = coords[0], coords[1]
            return float(lat), float(lon)
        if gtype == "MultiPoint":
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            return float(np.mean(lats)), float(np.mean(lons))
        if gtype == "Polygon":
            ring = coords[0]
            lons = [c[0] for c in ring]
            lats = [c[1] for c in ring]
            return float(np.mean(lats)), float(np.mean(lons))
        if gtype == "MultiPolygon":
            ring = coords[0][0]
            lons = [c[0] for c in ring]
            lats = [c[1] for c in ring]
            return float(np.mean(lats)), float(np.mean(lons))
        if gtype == "LineString":
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            return float(np.mean(lats)), float(np.mean(lons))
    except (TypeError, IndexError, ValueError):
        return None
    return None


def _load_poi_points() -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Load hospital-like and school-like POI coordinates from vulnerability.geojson.

    Returns (hospital_points, school_points) as lists of (lat, lon).
    """
    root = get_project_root()
    path = root / OSM_CACHE_DIR / "vulnerability.geojson"
    hospitals: list[tuple[float, float]] = []
    schools: list[tuple[float, float]] = []
    if not path.exists():
        logger.warning(
            "vulnerability.geojson not found at %s — hospital/school scores will be 0. "
            "Run: python -c \"from pipeline.geospatial.osm_client import fetch_osm_category; "
            "fetch_osm_category('vulnerability', refresh=True)\"",
            path,
        )
        return hospitals, schools

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        amenity = str(props.get("amenity") or "").lower().strip()
        healthcare = str(props.get("healthcare") or "").lower().strip()

        is_hospital = amenity in HOSPITAL_AMENITIES or healthcare in {
            "hospital", "clinic", "doctor", "doctors",
        }
        is_school = amenity in SCHOOL_AMENITIES

        # social_facility / nursing_home already in HOSPITAL_AMENITIES via amenity
        if not is_hospital and not is_school:
            continue

        centroid = _feature_centroid(feat.get("geometry"))
        if centroid is None:
            continue
        lat, lon = centroid
        if is_hospital:
            hospitals.append((lat, lon))
        if is_school:
            schools.append((lat, lon))

    logger.info(
        "Loaded vulnerability POIs: %d hospital-like, %d school-like",
        len(hospitals),
        len(schools),
    )
    return hospitals, schools


def _count_pois_in_radius(
    points: list[tuple[float, float]],
    lat: float,
    lon: float,
    radius_m: float = CATCHMENT_RADIUS_M,
) -> int:
    if not points:
        return 0
    arr = np.asarray(points, dtype=float)
    dists = _haversine_m_vectorized(lat, lon, arr[:, 0], arr[:, 1])
    return int(np.sum(dists <= radius_m))


def _load_metro_stations() -> list[dict[str, Any]]:
    root = get_project_root()
    path = root / "pipeline" / "reference" / "bengaluru_metro_stations.json"
    if not path.exists():
        logger.warning("Metro stations file missing at %s", path)
        return []
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, list):
        stations = payload
    else:
        stations = payload.get("stations") or []
    valid = [
        s for s in stations
        if s.get("lat") is not None and s.get("lon") is not None and s.get("name")
    ]
    logger.info("Loaded %d metro stations", len(valid))
    return valid


def _nearest_metro(
    lat: float, lon: float, stations: list[dict[str, Any]]
) -> tuple[float | None, str | None]:
    if not stations:
        return None, None
    best_d = float("inf")
    best_name: str | None = None
    for s in stations:
        d = _haversine_m(lat, lon, float(s["lat"]), float(s["lon"]))
        if d < best_d:
            best_d = d
            best_name = str(s["name"])
    if best_name is None:
        return None, None
    return round(best_d / 1000.0, 3), best_name  # km


def build_locality_environment_cache(
    registry_path: Path | None = None,
) -> dict[str, Any]:
    root = get_project_root()
    if registry_path is None:
        registry_path = root / "pipeline" / "reference" / "locality_registry.json"

    with registry_path.open("r", encoding="utf-8") as f:
        registry = json.load(f)

    hex_df = _load_hex_df()
    if hex_df.empty:
        raise RuntimeError("Hexagon features DataFrame is empty")

    hospital_pts, school_pts = _load_poi_points()
    metro_stations = _load_metro_stations()
    metro_available = len(metro_stations) > 0

    # Build-time fused PM2.5 snapshot (station IDW; NaN outside station range).
    fused = estimate_fused_pm25(hex_df)
    hex_df = hex_df.copy()
    hex_df["_fused_pm25"] = fused
    citywide_aqi = float(np.nanmean(fused)) if np.isfinite(fused).any() else None

    wind_data = _get_current_wind("bengaluru")
    firms_lookup = _build_firms_lookup("bengaluru")
    no2_lookup = _build_no2_lookup("bengaluru")

    needed_cells: set[str] = set()
    locality_masks: dict[str, np.ndarray] = {}
    for entry in registry:
        mask = _catchment_mask(hex_df, entry["centroid_lat"], entry["centroid_lon"])
        locality_masks[entry["name"]] = mask
        for cell in hex_df.loc[mask, "h3_cell"].tolist():
            needed_cells.add(cell)

    logger.info(
        "Computing attribution for %d unique catchment hexes across %d localities",
        len(needed_cells),
        len(registry),
    )

    attribution_by_cell: dict[str, dict[str, float]] = {}
    for cell in needed_cells:
        attr = compute_attribution_for_hexagon(
            cell, hex_df, wind_data, firms_lookup=firms_lookup, no2_lookup=no2_lookup
        )
        src = attr.get("source_attribution") or {}
        attribution_by_cell[cell] = {
            "traffic": float(src.get("traffic") or 0.0),
            "industrial": float(src.get("industrial") or 0.0),
            "construction": float(src.get("construction") or 0.0),
            "burning": float(src.get("burning") or 0.0),
        }

    localities_out: dict[str, Any] = {}
    for entry in registry:
        name = entry["name"]
        clat = float(entry["centroid_lat"])
        clon = float(entry["centroid_lon"])
        mask = locality_masks[name]
        catchment = hex_df.loc[mask]

        hospital_count = _count_pois_in_radius(hospital_pts, clat, clon)
        school_count = _count_pois_in_radius(school_pts, clat, clon)
        hospital_score = _scale_0_100(float(hospital_count), HOSPITAL_COUNT_SATURATION)
        school_score = _scale_0_100(float(school_count), SCHOOL_COUNT_SATURATION)

        metro_km, metro_name = _nearest_metro(clat, clon, metro_stations)

        if catchment.empty:
            aqi = citywide_aqi
            aqi_estimated = True
            hex_count = 0
            catchment_hex_ids: list[str] = []
            source_attr = {
                "traffic": None,
                "industrial": None,
                "construction": None,
                "burning": None,
            }
            park = 0.0
            noise = 0.0
            construction_score = 0.0
        else:
            hex_count = int(len(catchment))
            catchment_hex_ids = catchment["h3_cell"].astype(str).tolist()
            fused_vals = catchment["_fused_pm25"].to_numpy(dtype=float)
            finite = fused_vals[np.isfinite(fused_vals)]
            if len(finite) > 0:
                aqi = float(np.mean(finite))
                aqi_estimated = False
            else:
                aqi = citywide_aqi
                aqi_estimated = True

            attr_rows = [
                attribution_by_cell[c]
                for c in catchment_hex_ids
                if c in attribution_by_cell
            ]
            if attr_rows:
                source_attr = {
                    key: round(float(np.mean([r[key] for r in attr_rows])), 4)
                    for key in ("traffic", "industrial", "construction", "burning")
                }
            else:
                source_attr = {
                    "traffic": None,
                    "industrial": None,
                    "construction": None,
                    "burning": None,
                }

            green = float(catchment["green_space_fraction"].fillna(0.0).mean())
            park = _scale_0_100(green, GREEN_SPACE_SATURATION)

            road_density = float(catchment["road_density_m_per_sq_m"].fillna(0.0).mean())
            noise = _scale_0_100(road_density, ROAD_DENSITY_SATURATION)

            construction_count = float(
                catchment["construction_feature_count"].fillna(0.0).mean()
            )
            construction_score = _scale_0_100(construction_count, CONSTRUCTION_SATURATION)

        localities_out[name] = {
            "aqi": None if aqi is None else round(float(aqi), 1),
            "aqi_is_estimated": aqi_estimated,
            "source_attribution": source_attr,
            "park_score": park,
            "hospital_score": hospital_score,
            "school_score": school_score,
            "hospital_poi_count": hospital_count,
            "school_poi_count": school_count,
            "noise_score": noise,
            "construction_activity_score": construction_score,
            "metro_distance_km": metro_km if metro_available else None,
            "metro_data_available": metro_available and metro_km is not None,
            "nearest_metro_station": metro_name if metro_available else None,
            "catchment_hex_count": hex_count,
            # Stored so online matching can re-fuse AQI live without re-finding hexes.
            "catchment_hex_ids": catchment_hex_ids,
            "catchment_radius_m": CATCHMENT_RADIUS_M,
        }

    limitations = [
        "aqi in this file is a build-time fused PM2.5 (µg/m³) snapshot; "
        "online matching may overlay a live fuse using catchment_hex_ids.",
    ]
    if not hospital_pts and not school_pts:
        limitations.append(
            "vulnerability.geojson missing or empty — hospital/school scores are 0."
        )
    if not metro_available:
        limitations.append(
            "metro stations file missing — metro_distance_km is null. "
            "Run: python -m pipeline.build_metro_stations_cache --refresh"
        )

    return {
        "schema_version": 2,
        "catchment_radius_m": CATCHMENT_RADIUS_M,
        "scaling": {
            "green_space_saturation": GREEN_SPACE_SATURATION,
            "road_density_saturation": ROAD_DENSITY_SATURATION,
            "construction_saturation": CONSTRUCTION_SATURATION,
            "hospital_count_saturation": HOSPITAL_COUNT_SATURATION,
            "school_count_saturation": SCHOOL_COUNT_SATURATION,
        },
        "known_limitations": limitations,
        "citywide_aqi_fallback": None if citywide_aqi is None else round(citywide_aqi, 1),
        "poi_totals": {
            "hospital_like": len(hospital_pts),
            "school_like": len(school_pts),
            "metro_stations": len(metro_stations),
        },
        "localities": localities_out,
    }


def write_locality_environment_cache(
    output_path: Path | None = None,
    registry_path: Path | None = None,
) -> Path:
    root = get_project_root()
    if output_path is None:
        output_path = root / "pipeline" / "reference" / "locality_environment_cache.json"

    cache = build_locality_environment_cache(registry_path=registry_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
        f.write("\n")
    logger.info(
        "Wrote environment cache for %d localities to %s",
        len(cache["localities"]),
        output_path,
    )
    return output_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = write_locality_environment_cache()
    print(f"Wrote locality environment cache -> {path}")


if __name__ == "__main__":
    main()
