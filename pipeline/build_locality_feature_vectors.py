"""Merge registry + rent + environment caches into final locality feature vectors.

Also orchestrates the full offline build chain (registry → rent → environment
→ merge) when run as the main module.

Output: pipeline/reference/locality_feature_vectors.json

Run:
    python -m pipeline.build_locality_feature_vectors
    python -m pipeline.build_locality_feature_vectors --skip-rebuild   # merge only
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from backend.app.config import get_project_root

logger = logging.getLogger(__name__)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def merge_feature_vectors(
    registry_path: Path | None = None,
    rent_path: Path | None = None,
    env_path: Path | None = None,
) -> list[dict[str, Any]]:
    root = get_project_root()
    ref = root / "pipeline" / "reference"
    if registry_path is None:
        registry_path = ref / "locality_registry.json"
    if rent_path is None:
        rent_path = ref / "locality_rent_cache.json"
    if env_path is None:
        env_path = ref / "locality_environment_cache.json"

    registry = _load_json(registry_path)
    rent_cache = _load_json(rent_path)
    env_cache = _load_json(env_path)

    rent_localities = rent_cache.get("localities", {})
    env_localities = env_cache.get("localities", {})

    vectors: list[dict[str, Any]] = []
    for entry in registry:
        name = entry["name"]
        rent = rent_localities.get(name)
        env = env_localities.get(name)
        if rent is None or env is None:
            logger.warning("Skipping %s — missing rent or environment cache entry", name)
            continue

        vectors.append({
            "name": name,
            "centroid_lat": entry["centroid_lat"],
            "centroid_lon": entry["centroid_lon"],
            "listing_count": entry["listing_count"],
            "rent": {
                "by_bhk": rent["by_bhk"],
                "overall_median_rent": rent["overall_median_rent"],
                "overall_count": rent["overall_count"],
            },
            "environment": {
                "aqi": env["aqi"],
                "aqi_is_estimated": env["aqi_is_estimated"],
                "source_attribution": env["source_attribution"],
                "park_score": env["park_score"],
                "hospital_score": env["hospital_score"],
                "school_score": env["school_score"],
                "hospital_poi_count": env.get("hospital_poi_count"),
                "school_poi_count": env.get("school_poi_count"),
                "noise_score": env["noise_score"],
                "construction_activity_score": env["construction_activity_score"],
                "metro_distance_km": env["metro_distance_km"],
                "metro_data_available": env["metro_data_available"],
                "nearest_metro_station": env.get("nearest_metro_station"),
                "catchment_hex_count": env["catchment_hex_count"],
                "catchment_hex_ids": env.get("catchment_hex_ids") or [],
            },
        })

    vectors.sort(key=lambda v: v["name"])
    logger.info("Merged %d locality feature vectors", len(vectors))
    return vectors


def write_feature_vectors(
    output_path: Path | None = None,
    rebuild: bool = True,
) -> Path:
    root = get_project_root()
    ref = root / "pipeline" / "reference"
    if output_path is None:
        output_path = ref / "locality_feature_vectors.json"

    if rebuild:
        from pipeline.build_locality_registry import write_locality_registry
        from pipeline.build_locality_rent_cache import write_locality_rent_cache
        from pipeline.build_locality_environment_cache import write_locality_environment_cache
        from pipeline.build_metro_stations_cache import write_metro_stations

        logger.info("Step 0/5 — metro stations (skip if present)")
        try:
            write_metro_stations(refresh=False)
        except Exception as exc:
            logger.warning("Metro station build skipped/failed: %s", exc)

        logger.info("Step 1/5 — locality registry")
        write_locality_registry()
        logger.info("Step 2/5 — rent cache")
        write_locality_rent_cache()
        logger.info("Step 3/5 — environment cache")
        write_locality_environment_cache()

    logger.info("Step 4/5 — merge feature vectors")
    vectors = merge_feature_vectors()

    payload = {
        "schema_version": 2,
        "locality_count": len(vectors),
        "localities": vectors,
        "notes": [
            "Offline-built feature vectors for Citizen Mode matching.",
            "Online path scores over this list; may overlay live AQI fuse and "
            "Google Routes commute for the top shortlist (hybrid).",
            "catchment_hex_ids support live AQI re-aggregation without re-finding hexes.",
            "metro_distance_km is null when metro_data_available is false.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    logger.info("Wrote %d feature vectors to %s", len(vectors), output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build locality feature vectors for Citizen Mode")
    parser.add_argument(
        "--skip-rebuild",
        action="store_true",
        help="Only merge existing registry/rent/environment JSON files",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = write_feature_vectors(rebuild=not args.skip_rebuild)
    print(f"Wrote locality feature vectors -> {path}")


if __name__ == "__main__":
    main()
