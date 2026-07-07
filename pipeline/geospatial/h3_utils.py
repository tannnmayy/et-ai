from __future__ import annotations

from typing import Any

import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon


def lat_lon_to_h3(lat: float, lon: float, resolution: int = 9) -> str:
    """Convert a latitude/longitude pair to an H3 cell ID at the given resolution.

    Parameters
    ----------
    lat : float        Latitude in decimal degrees.
    lon : float        Longitude in decimal degrees.
    resolution : int   H3 resolution (default 9).

    Returns
    -------
    str    H3 cell index string.
    """
    return h3.latlng_to_cell(lat, lon, resolution)


def h3_cell_to_boundary(cell: str) -> list[tuple[float, float]]:
    """Return the geographic boundary of an H3 cell as a list of (lat, lon) tuples.

    Parameters
    ----------
    cell : str    H3 cell index.

    Returns
    -------
    list[tuple[float, float]]    Boundary vertices in (lat, lon).
    """
    return h3.cell_to_boundary(cell)


def h3_cell_to_polygon(cell: str) -> Polygon:
    """Return a Shapely Polygon for the H3 cell boundary.

    Parameters
    ----------
    cell : str    H3 cell index.

    Returns
    -------
    Polygon    Shapely polygon in (lon, lat) order (GeoJSON convention).
    """
    boundary = h3.cell_to_boundary(cell)
    if boundary:
        return Polygon([(lon, lat) for lat, lon in boundary])
    return Polygon()


def station_to_h3_cell(
    lat: float, lon: float, resolution: int = 9
) -> dict[str, Any]:
    """Map a station lat/lon to an H3 cell and return cell metadata.

    Parameters
    ----------
    lat, lon : float   Station coordinates.
    resolution : int   H3 resolution.

    Returns
    -------
    dict with keys: h3_cell, resolution, lat, lon
    """
    cell = lat_lon_to_h3(lat, lon, resolution)
    return {
        "h3_cell": cell,
        "resolution": resolution,
        "latitude": lat,
        "longitude": lon,
    }


def compute_station_h3_mapping(
    registry_df: pd.DataFrame,
    resolution: int = 9,
) -> pd.DataFrame:
    """Add H3 cell column to a station registry DataFrame.

    Parameters
    ----------
    registry_df : pd.DataFrame   Must have columns station_id, latitude, longitude.
    resolution : int              H3 resolution.

    Returns
    -------
    pd.DataFrame    Registry with added h3_cell and h3_resolution columns.
    """
    df = registry_df.copy()
    cells: list[str] = []
    for _, row in df.iterrows():
        lat = row["latitude"]
        lon = row["longitude"]
        if pd.notna(lat) and pd.notna(lon):
            cells.append(lat_lon_to_h3(float(lat), float(lon), resolution))
        else:
            cells.append(None)
    df["h3_cell"] = cells
    df["h3_resolution"] = resolution
    return df


def h3_resolution_name(resolution: int) -> str:
    """Return a human-readable description of an H3 resolution level."""
    descriptions = {
        8: "neighbourhood (~0.7 km² hexagons)",
        9: "neighbourhood (~0.1 km² hexagons)",
        10: "block (~0.015 km² hexagons)",
    }
    return descriptions.get(resolution, f"resolution {resolution}")


def get_h3_api_version() -> str:
    """Return the H3 library version for provenance metadata."""
    return h3.__version__
