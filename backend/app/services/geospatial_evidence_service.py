"""Geospatial evidence service.

Provides station-level spatial context derived from OSM and H3.
All data is read from pre-built artifacts; no OSM calls at request time.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

import backend.app.config as _config
from backend.app.schemas.geospatial import (
    CityCoverageSummary,
    InvestigationContext,
    LanduseContext,
    RoadContext,
    GeospatialProvenance,
    StationGeospatialContext,
)

logger = logging.getLogger(__name__)

OSM_COMPLETENESS_DISCLAIMER: str = (
    "OpenStreetMap data is community-maintained and may be incomplete, outdated, "
    "or inconsistently tagged. Mapped features are contextual evidence only and "
    "do not represent verified registered emission sources."
)

INVESTIGATION_DISCLAIMER: str = (
    "Spatial features are contextual evidence and investigation signals only. "
    "They do not prove that a specific industry, construction site, road, "
    "facility, or mapped object caused pollution at this station."
)


class GeospatialArtifactMissingError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Geospatial context artifacts are missing. Run: "
            "python -m pipeline.build_geospatial_context"
        )


class UnknownStationError(Exception):
    def __init__(self, station_id: str) -> None:
        super().__init__(f"Unknown station_id: {station_id}.")
        self.station_id = station_id


# Module-level tracking for artifact mtime to detect rebuilds
_parquet_path: Path | None = None
_metadata_path: Path | None = None
_parquet_mtime: float = 0.0
_metadata_mtime: float = 0.0
_cached_df: pd.DataFrame | None = None
_cached_meta: dict[str, Any] | None = None
_logged_paths: bool = False


def _get_parquet_path() -> Path:
    global _parquet_path
    if _parquet_path is None:
        _parquet_path = _config.get_project_root() / _config.GEOSPATIAL_PROCESSED_DIR / "station_geospatial_context.parquet"
    return _parquet_path


def _get_metadata_path() -> Path:
    global _metadata_path
    if _metadata_path is None:
        _metadata_path = _config.get_project_root() / _config.GEOSPATIAL_PROCESSED_DIR / "geospatial_build_metadata.json"
    return _metadata_path


def _load_context_dataframe() -> pd.DataFrame:
    """Load the geospatial context Parquet artifact, with mtime-based reload detection."""
    global _parquet_mtime, _cached_df, _logged_paths

    path = _get_parquet_path()
    if not path.exists():
        _cached_df = None
        raise GeospatialArtifactMissingError()

    current_mtime = path.stat().st_mtime
    if _cached_df is None or current_mtime > _parquet_mtime:
        _parquet_mtime = current_mtime
        _cached_df = pd.read_parquet(path)
        if not _logged_paths:
            logger.info(
                "Loaded geospatial parquet: %s (%d rows, stations=%s)",
                path, len(_cached_df), sorted(_cached_df["station_id"].tolist()),
            )
            _logged_paths = True

    return _cached_df


def _load_build_metadata() -> dict[str, Any]:
    """Load build metadata JSON, with mtime-based reload detection."""
    global _metadata_mtime, _cached_meta, _logged_paths

    path = _get_metadata_path()
    if not path.exists():
        _cached_meta = {}
        return {}

    current_mtime = path.stat().st_mtime
    if _cached_meta is None or current_mtime > _metadata_mtime:
        _metadata_mtime = current_mtime
        with path.open("r", encoding="utf-8") as f:
            _cached_meta = json.load(f)
        if not _logged_paths:
            logger.info(
                "Loaded geospatial metadata: %s (build_status=%s, stations_count=%s)",
                path, _cached_meta.get("build_status"), _cached_meta.get("stations_count"),
            )

    return _cached_meta


def get_station_geospatial_context(
    station_id: str,
    city: str = "bengaluru",
) -> dict[str, Any]:
    """Return the full geospatial context for a single station.

    Parameters
    ----------
    station_id : str    Station identifier.
    city : str          City name (default bengaluru).

    Returns
    -------
    dict    Geospatial context matching StationGeospatialContext schema.

    Raises
    ------
    GeospatialArtifactMissingError    If artifact has not been built.
    UnknownStationError    If station_id is not found.
    """
    df = _load_context_dataframe()
    matches = df[df["station_id"] == station_id]
    if matches.empty:
        raise UnknownStationError(station_id)

    row = matches.iloc[0]

    limitations_str = row.get("limitations", "")
    if pd.isna(limitations_str):
        limitations_list: list[str] = [OSM_COMPLETENESS_DISCLAIMER, INVESTIGATION_DISCLAIMER]
    else:
        limitations_list = limitations_str.split(" | ") if limitations_str else []

    # Ensure disclaimers are always present
    if OSM_COMPLETENESS_DISCLAIMER not in limitations_list:
        limitations_list.append(OSM_COMPLETENESS_DISCLAIMER)
    if INVESTIGATION_DISCLAIMER not in limitations_list:
        limitations_list.append(INVESTIGATION_DISCLAIMER)

    meta = _load_build_metadata()
    build_status = meta.get("build_status", "unknown")

    # Add partial-build limitation if applicable
    if build_status == "partial":
        partial_note = (
            "Partial build: one or more OSM layers were missing or empty. "
            "Spatial context features may be significantly reduced."
        )
        if partial_note not in limitations_list:
            limitations_list.append(partial_note)

    return {
        "station_id": station_id,
        "city": str(row.get("city", city)),
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "h3_cell": str(row.get("h3_cell")) if pd.notna(row.get("h3_cell")) else None,
        "context_radius_meters": float(row.get("context_radius_meters", 1000)),
        "build_status": build_status,
        "road_context": {
            "total_road_length_m_within_radius": _safe_float(row, "total_road_length_m_within_radius"),
            "major_road_length_m_within_radius": _safe_float(row, "major_road_length_m_within_radius"),
            "road_density_m_per_sq_km": _safe_float(row, "road_density_m_per_sq_km"),
            "intersection_count_within_radius": _safe_int(row, "intersection_count_within_radius"),
            "nearest_major_road_distance_m": _safe_float(row, "nearest_major_road_distance_m"),
            "road_feature_coverage_status": str(row.get("road_feature_coverage_status", "unavailable")),
        },
        "landuse_context": {
            "industrial_landuse_fraction": _safe_float(row, "industrial_landuse_fraction"),
            "commercial_landuse_fraction": _safe_float(row, "commercial_landuse_fraction"),
            "residential_landuse_fraction": _safe_float(row, "residential_landuse_fraction"),
            "green_space_fraction": _safe_float(row, "green_space_fraction"),
            "landuse_feature_coverage_status": str(row.get("landuse_feature_coverage_status", "unavailable")),
        },
        "investigation_context": {
            "construction_feature_count_within_radius": _safe_int(row, "construction_feature_count_within_radius"),
            "mapped_industrial_or_facility_count_within_radius": _safe_int(row, "mapped_industrial_or_facility_count_within_radius"),
            "nearest_mapped_industrial_or_facility_distance_m": _safe_float(row, "nearest_mapped_industrial_or_facility_distance_m"),
            "investigation_context_coverage_status": str(row.get("investigation_context_coverage_status", "unavailable")),
        },
        "provenance": {
            "osm_snapshot_timestamp": _safe_str(row, "osm_snapshot_timestamp"),
            "feature_builder_version": str(row.get("feature_builder_version", _config.GEOSPATIAL_FEATURE_BUILDER_VERSION)),
            "h3_resolution": _config.H3_RESOLUTION,
            "h3_cell": str(row.get("h3_cell")) if pd.notna(row.get("h3_cell")) else None,
        },
        "data_completeness_score": _safe_float(row, "data_completeness_score", 0.0),
        "limitations": limitations_list,
    }


def get_city_geospatial_coverage(city: str = "bengaluru") -> dict[str, Any]:
    """Return a summary of geospatial coverage for all stations in a city.

    Parameters
    ----------
    city : str    City name.

    Returns
    -------
    dict    Coverage summary matching CityCoverageSummary schema.
    """
    df = _load_context_dataframe()
    city_df = df[df["city"] == city].copy()

    meta = _load_build_metadata()

    total = len(city_df)
    with_coverage = sum(
        1
        for _, r in city_df.iterrows()
        if r.get("road_feature_coverage_status") == "complete"
        or r.get("landuse_feature_coverage_status") == "complete"
    )
    complete = sum(
        1
        for _, r in city_df.iterrows()
        if r.get("road_feature_coverage_status") == "complete"
        and r.get("landuse_feature_coverage_status") == "complete"
    )

    osm_ts = meta.get("osm_snapshot_timestamp")
    builder_version = meta.get("feature_builder_version", _config.GEOSPATIAL_FEATURE_BUILDER_VERSION)
    h3_res = meta.get("h3_resolution", _config.H3_RESOLUTION)

    build_status = meta.get("build_status", "unknown")

    return {
        "city": city,
        "total_stations": total,
        "stations_with_coverage": with_coverage,
        "stations_with_complete_coverage": complete,
        "osm_snapshot_timestamp": osm_ts,
        "feature_builder_version": builder_version,
        "h3_resolution": h3_res,
        "build_status": build_status,
        "disclaimers": [OSM_COMPLETENESS_DISCLAIMER, INVESTIGATION_DISCLAIMER],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_float(row: pd.Series, key: str, default: float | None = None) -> float | None:
    val = row.get(key)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(row: pd.Series, key: str, default: int | None = None) -> int | None:
    val = row.get(key)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_str(row: pd.Series, key: str, default: str | None = None) -> str | None:
    val = row.get(key)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return str(val)
