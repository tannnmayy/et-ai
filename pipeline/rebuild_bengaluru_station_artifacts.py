from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from ml.common import DATASET_REAL_MULTISTATION, get_paths

logger = logging.getLogger(__name__)


def _stage(msg: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  STAGE: {msg}")
    print(f"{'=' * 70}")


def rebuild_all(project_root: Path, station_ids: list[str] | None = None, dry_run: bool = False) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "stages": {},
        "station_ids": station_ids or [],
        "success": True,
    }

    # Stage 1: Registry validation
    _stage("Validating station registry")
    from pipeline.station_registry import get_registry_stations, refresh_registry

    refresh_registry()
    all_stations = get_registry_stations()
    if not all_stations:
        print("ERROR: No active stations in registry.")
        summary["success"] = False
        return summary

    if station_ids:
        active_ids = {s.station_id for s in all_stations}
        unknown = [sid for sid in station_ids if sid not in active_ids]
        if unknown:
            print(f"ERROR: Unknown station IDs: {unknown}")
            summary["success"] = False
            return summary
        stations_to_process = [s for s in all_stations if s.station_id in station_ids]
    else:
        stations_to_process = all_stations

    print(f"Active stations: {[s.station_id for s in stations_to_process]}")
    summary["station_ids"] = [s.station_id for s in stations_to_process]

    if dry_run:
        summary["dry_run"] = True
        print("[DRY RUN] No operations performed.")
        return summary

    # Stage 2: Ingestion
    _stage(f"Ingesting CPCB CSV data for {len(stations_to_process)} station(s)")
    from pipeline.ingest_cpcb_csv import ingest_all_stations

    ingestion_results = ingest_all_stations(project_root=project_root)
    ingested = list(ingestion_results.keys())
    print(f"Ingested: {ingested}")
    summary["stages"]["ingestion"] = {"stations": ingested}

    # Stage 3: Merge + multistation features
    _stage("Merging multi-station hourly data and building features")
    from pipeline.merge_multistation import merge_multistation

    try:
        features = merge_multistation(project_root=project_root)
        summary["stages"]["feature_build"] = {"feature_rows": len(features)}
        print(f"Built {len(features)} feature rows")
    except Exception as e:
        print(f"ERROR during feature build: {e}")
        summary["stages"]["feature_build"] = {"error": str(e)}
        summary["success"] = False
        return summary

    # Stage 4: Persistence baseline
    _stage("Training persistence baseline")
    from ml.train_persistence_baseline import train_persistence_baseline

    try:
        persistence_metrics = train_persistence_baseline(project_root=project_root, dataset=DATASET_REAL_MULTISTATION)
        summary["stages"]["persistence_baseline"] = {
            "validation_rmse": persistence_metrics.get("validation_rmse"),
        }
        print(f"Persistence baseline RMSE: {persistence_metrics.get('validation_rmse')}")
    except Exception as e:
        print(f"ERROR training persistence baseline: {e}")
        summary["stages"]["persistence_baseline"] = {"error": str(e)}
        summary["success"] = False
        return summary

    # Stage 5: LightGBM training
    _stage("Training LightGBM model")
    from ml.train_lightgbm import train_lightgbm

    try:
        train_lightgbm(project_root=project_root, dataset=DATASET_REAL_MULTISTATION)
        summary["stages"]["lightgbm"] = {"trained": True}
        print("LightGBM training complete")
    except Exception as e:
        print(f"ERROR training LightGBM: {e}")
        summary["stages"]["lightgbm"] = {"error": str(e)}
        summary["success"] = False
        return summary

    # Stage 6: Geospatial context
    _stage("Building OSM geospatial context")
    from pipeline.build_geospatial_context import build_geospatial_context

    try:
        geo_result = build_geospatial_context(allow_partial_osm=False)
        summary["stages"]["geospatial"] = {
            "build_status": geo_result.get("build_status"),
            "stations_processed": geo_result.get("stations_processed", 0),
        }
        print(f"Geospatial build status: {geo_result.get('build_status')}")
    except RuntimeError as e:
        if "Required OSM layers" in str(e):
            print(f"OSM layers not ready. Run fetch_osm_bengaluru first. Error: {e}")
            summary["stages"]["geospatial"] = {"error": "OSM layers not ready; run fetch_osm_bengaluru"}
            summary["success"] = False
            return summary
        print(f"ERROR building geospatial context: {e}")
        summary["stages"]["geospatial"] = {"error": str(e)}
    except Exception as e:
        print(f"ERROR building geospatial context: {e}")
        summary["stages"]["geospatial"] = {"error": str(e)}

    # Validate forecast artifacts exist
    _stage("Validating forecast artifacts")
    paths = get_paths(project_root, dataset=DATASET_REAL_MULTISTATION)
    artifact_checks = {
        "features": paths.processed_features.exists(),
        "persistence": paths.persistence_artifact.exists(),
        "lightgbm": paths.lightgbm_model.exists(),
        "feature_columns": paths.feature_columns.exists(),
        "evaluation": paths.evaluation_metrics.exists(),
    }
    all_valid = all(artifact_checks.values())
    summary["stages"]["artifact_validation"] = artifact_checks
    if all_valid:
        print("All forecast artifacts validated.")
    else:
        missing = [k for k, v in artifact_checks.items() if not v]
        print(f"WARNING: Missing artifacts: {missing}")
        summary["success"] = False

    print(f"\n{'=' * 70}")
    print(f"  REBUILD {'SUCCEEDED' if summary['success'] else 'FAILED'}")
    print(f"{'=' * 70}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild all pipeline artifacts for active Bengaluru stations.")
    parser.add_argument("--dry-run", action="store_true", help="Validate registry without running pipeline stages.")
    parser.add_argument("--stations", default="all", help="Comma-separated station IDs, or 'all'.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from backend.app.config import get_project_root

    project_root = get_project_root()
    station_ids = None
    if args.stations and args.stations.lower() != "all":
        station_ids = [s.strip() for s in args.stations.split(",")]

    print(f"Project root: {project_root}")
    print(f"Stations: {'all' if station_ids is None else station_ids}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'FULL BUILD'}")

    rebuild_all(project_root, station_ids=station_ids, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
