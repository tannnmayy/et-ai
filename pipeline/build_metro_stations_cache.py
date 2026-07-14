"""Fetch Bengaluru metro/subway stations from OpenStreetMap and write a
committed reference file for Citizen Mode.

Approach B (OSM): query the Bengaluru bounding box for subway-related station
tags via OSMnx, dedupe by name+proximity, write:

  pipeline/reference/bengaluru_metro_stations.json

Schema (per station):
  {
    "name": "Indiranagar",          # required — station display name
    "lat": 12.9783,                 # required
    "lon": 77.6389,                 # required
    "line": "Purple" | null,        # optional — Namma Metro line colour/name
    "osm_id": "node/123" | null,    # optional provenance
    "source": "osm"
  }

If you prefer to supply stations yourself, use the same schema (name/lat/lon
required; line optional). Drop the file at the path above and re-run
pipeline.build_locality_environment_cache.

Run:
    python -m pipeline.build_metro_stations_cache
    python -m pipeline.build_metro_stations_cache --refresh
"""

from __future__ import annotations

import argparse
import json
import logging
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

from backend.app.config import BENGALURU_BOUNDING_BOX, get_project_root

logger = logging.getLogger(__name__)

_EARTH_RADIUS_M = 6_371_000.0
# Collapse duplicate OSM nodes/entrances within this radius of the same name.
DEDUPE_RADIUS_M = 250.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return _EARTH_RADIUS_M * 2 * asin(sqrt(a))


def _infer_line(props: dict[str, Any], name: str) -> str | None:
    """Best-effort line colour/name from OSM tags or station name heuristics."""
    for key in ("line", "railway:line", "network", "operator", "colour", "color"):
        val = props.get(key)
        if val and isinstance(val, str) and val.strip():
            text = val.strip()
            low = text.lower()
            if "purple" in low:
                return "Purple"
            if "green" in low:
                return "Green"
            if "yellow" in low:
                return "Yellow"
            if "blue" in low:
                return "Blue"
            if "pink" in low:
                return "Pink"
            if "namma" in low or "bmrcl" in low:
                continue  # network name, not a line
            return text

    # Name heuristics for well-known corridors (fallback only).
    return None


def _extract_points_from_gdf(gdf) -> list[dict[str, Any]]:
    """Pull (name, lat, lon, props) rows from an OSMnx GeoDataFrame."""
    rows: list[dict[str, Any]] = []
    if gdf is None or gdf.empty:
        return rows

    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        # Use representative point for polygons / multipoints.
        try:
            pt = geom if geom.geom_type == "Point" else geom.representative_point()
            lon, lat = float(pt.x), float(pt.y)
        except Exception:
            continue

        name = None
        for key in ("name", "name:en", "ref", "uic_name"):
            val = row.get(key) if hasattr(row, "get") else None
            if val is None and key in row.index:
                val = row[key]
            if val is not None and str(val).strip() and str(val).lower() != "nan":
                name = str(val).strip()
                break
        if not name:
            continue

        # Skip bus-only / non-metro if tagged clearly.
        railway = str(row.get("railway") or "").lower() if "railway" in row.index else ""
        station = str(row.get("station") or "").lower() if "station" in row.index else ""
        subway = str(row.get("subway") or "").lower() if "subway" in row.index else ""
        public_transport = (
            str(row.get("public_transport") or "").lower()
            if "public_transport" in row.index
            else ""
        )

        looks_metro = (
            station == "subway"
            or subway in {"yes", "true", "1"}
            or "metro" in name.lower()
            or railway in {"station", "halt", "subway_entrance"}
        )
        # Prefer subway-tagged; still keep railway=station (Namma Metro often
        # tagged that way) but drop pure bus stops.
        highway = str(row.get("highway") or "").lower() if "highway" in row.index else ""
        amenity = str(row.get("amenity") or "").lower() if "amenity" in row.index else ""
        if amenity == "bus_station" or highway == "bus_stop":
            continue
        if public_transport == "stop_position" and station != "subway":
            continue
        if not looks_metro and station not in {"subway", "light_rail"}:
            # Keep railway=station as candidate; filter later by name/network
            if railway != "station":
                continue

        props = {c: row[c] for c in row.index if c != "geometry"}
        osm_id = None
        if isinstance(idx, tuple) and len(idx) >= 2:
            osm_id = f"{idx[0]}/{idx[1]}"
        elif idx is not None:
            osm_id = str(idx)

        rows.append({
            "name": name,
            "lat": lat,
            "lon": lon,
            "line": _infer_line(props, name),
            "osm_id": osm_id,
            "source": "osm",
            "_station_tag": station,
            "_railway_tag": railway,
            "_subway_tag": subway,
        })
    return rows


def fetch_metro_stations_from_osm() -> list[dict[str, Any]]:
    """Query OSM for subway/metro stations inside the Bengaluru bbox."""
    import osmnx as ox
    from shapely.geometry import box

    bbox = BENGALURU_BOUNDING_BOX
    polygon = box(bbox["west"], bbox["south"], bbox["east"], bbox["north"])
    ox.settings.log_console = False
    ox.settings.use_cache = True

    tag_queries = [
        {"station": "subway"},
        {"railway": "station", "station": "subway"},
        {"railway": "subway_entrance"},
        {"public_transport": "station", "subway": "yes"},
        # Broader: many Namma Metro stops are just railway=station
        {"railway": "station"},
    ]

    all_rows: list[dict[str, Any]] = []
    for tags in tag_queries:
        try:
            logger.info("OSMnx metro query tags=%s", tags)
            gdf = ox.features_from_polygon(polygon, tags)
            extracted = _extract_points_from_gdf(gdf)
            logger.info("  -> %d named points", len(extracted))
            all_rows.extend(extracted)
        except Exception as exc:
            logger.warning("OSM query failed for %s: %s", tags, exc)

    # Prefer subway-tagged rows when deduping.
    def _priority(r: dict[str, Any]) -> int:
        score = 0
        if r.get("_station_tag") == "subway":
            score += 3
        if r.get("_subway_tag") in {"yes", "true", "1"}:
            score += 2
        if "metro" in r["name"].lower():
            score += 1
        return score

    all_rows.sort(key=_priority, reverse=True)
    deduped: list[dict[str, Any]] = []
    for row in all_rows:
        name_key = row["name"].lower().strip()
        line_text = str(row.get("line") or "").lower()
        # Drop pure Indian Railways long-distance stations so "metro distance"
        # means Namma Metro / subway, not IR.
        if line_text in {"ir", "indian railways", "south western railway", "swr"}:
            continue
        if line_text.startswith("ir ") or line_text == "ir":
            continue
        if "railway station" in name_key and "metro" not in name_key:
            # Keep only if subway-tagged
            if row.get("_station_tag") != "subway" and row.get("_subway_tag") not in {
                "yes", "true", "1",
            }:
                continue

        is_dup = False
        for existing in deduped:
            same_name = existing["name"].lower().strip() == name_key
            near = _haversine_m(
                row["lat"], row["lon"], existing["lat"], existing["lon"]
            ) < DEDUPE_RADIUS_M
            if same_name or near:
                is_dup = True
                break
        if is_dup:
            continue

        deduped.append({
            "name": row["name"],
            "lat": round(float(row["lat"]), 6),
            "lon": round(float(row["lon"]), 6),
            "line": row.get("line"),
            "osm_id": row.get("osm_id"),
            "source": "osm",
        })

    deduped.sort(key=lambda s: s["name"].lower())
    logger.info("Deduped metro station set: %d", len(deduped))
    return deduped


def write_metro_stations(
    output_path: Path | None = None,
    refresh: bool = False,
) -> Path:
    root = get_project_root()
    if output_path is None:
        output_path = root / "pipeline" / "reference" / "bengaluru_metro_stations.json"

    if output_path.exists() and not refresh:
        logger.info("Metro stations file already exists at %s (use --refresh to rebuild)", output_path)
        return output_path

    stations = fetch_metro_stations_from_osm()
    payload = {
        "schema_version": 1,
        "city": "bengaluru",
        "source": "OpenStreetMap via OSMnx",
        "station_count": len(stations),
        "notes": [
            "Required fields per station: name, lat, lon.",
            "Optional: line (e.g. Purple/Green), osm_id, source.",
            "Used by build_locality_environment_cache for nearest-station distance.",
        ],
        "stations": stations,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    logger.info("Wrote %d metro stations to %s", len(stations), output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Bengaluru metro stations cache from OSM")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch even if file exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = write_metro_stations(refresh=args.refresh)
    print(f"Wrote metro stations -> {path}")


if __name__ == "__main__":
    main()
