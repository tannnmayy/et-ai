"""Human-readable locality labels for H3 hex centers (Bengaluru).

Priority:
  1. Pre-supplied name (if not a raw Grid/hex id label)
  2. Nearest locality centroid from locality_registry.json
  3. Nearest monitoring station name
  4. Soft sector label from lat/lng (never primary raw H3 id)
"""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.config import get_project_root

logger = logging.getLogger(__name__)


def _is_raw_grid_label(name: str | None) -> bool:
    if not name:
        return True
    n = name.strip()
    if not n:
        return True
    low = n.lower()
    if low.startswith("grid ") or low.startswith("sector "):
        return True
    # bare h3-like token
    if len(n) >= 10 and all(c in "0123456789abcdef" for c in n.lower()):
        return True
    return False


@lru_cache(maxsize=1)
def _locality_centroids() -> list[tuple[str, float, float]]:
    path = get_project_root() / "pipeline" / "reference" / "locality_registry.json"
    if not path.exists():
        logger.warning("locality_registry.json missing at %s", path)
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load locality registry: %s", exc)
        return []
    out: list[tuple[str, float, float]] = []
    for r in rows:
        name = (r.get("name") or "").strip()
        lat = r.get("centroid_lat")
        lon = r.get("centroid_lon")
        if name and lat is not None and lon is not None:
            out.append((name, float(lat), float(lon)))
    return out


@lru_cache(maxsize=1)
def _station_points() -> list[tuple[str, float, float]]:
    try:
        from pipeline.station_registry import get_registry_stations

        out: list[tuple[str, float, float]] = []
        for s in get_registry_stations():
            name = getattr(s, "display_name", None) or getattr(s, "station_name", None) or getattr(s, "name", None)
            lat = getattr(s, "latitude", None)
            lon = getattr(s, "longitude", None)
            if name and lat is not None and lon is not None:
                out.append((str(name), float(lat), float(lon)))
        return out
    except Exception as exc:
        logger.debug("Station points unavailable for naming: %s", exc)
        return []


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def _nearest(
    lat: float,
    lon: float,
    points: list[tuple[str, float, float]],
    max_km: float,
) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for name, plat, plon in points:
        d = _haversine_km(lat, lon, plat, plon)
        if d > max_km:
            continue
        if best is None or d < best[1]:
            best = (name, d)
    return best


def resolve_location_name(
    lat: float,
    lon: float,
    *,
    h3_cell: str | None = None,
    preferred: str | None = None,
) -> str:
    """Return a human-readable locality label for a map/enforcement hex."""
    if preferred and not _is_raw_grid_label(preferred):
        # Prefer first segment of reverse-geocode style labels
        return preferred.split(",")[0].strip()

    near = _nearest(lat, lon, _locality_centroids(), max_km=4.5)
    if near:
        name, dist = near
        if dist <= 1.8:
            return name
        return f"Near {name}"

    station = _nearest(lat, lon, _station_points(), max_km=3.5)
    if station:
        name, dist = station
        if dist <= 1.2:
            return name
        return f"Near {name}"

    # Soft geographic sector — never expose raw H3 as the primary label
    ns = "N" if lat >= 12.97 else "S"
    ew = "E" if lon >= 77.60 else "W"
    return f"Bengaluru {ns}{ew}"


def attach_location_names(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mutate/return ranked hex dicts with reliable ``name`` / ``location_name``."""
    for row in ranked:
        lat = row.get("center_lat")
        lon = row.get("center_lon")
        if lat is None or lon is None:
            # try nested
            continue
        name = resolve_location_name(
            float(lat),
            float(lon),
            h3_cell=row.get("h3_cell"),
            preferred=row.get("name") or row.get("location_name"),
        )
        row["name"] = name
        row["location_name"] = name
    return ranked
