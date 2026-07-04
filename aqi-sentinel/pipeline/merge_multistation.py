from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from ml.common import DATASET_REAL_MULTISTATION, get_paths
from pipeline.build_real_features import create_real_features, select_training_features
from pipeline.ingest_cpcb_csv import classify_dataset, _missingness_percent, _longest_continuous_run
from pipeline.station_registry import BENGALURU_STATIONS, all_station_ids, station_output_dir
from pipeline.storage import read_parquet, write_parquet

logger = logging.getLogger(__name__)


def load_all_station_hourly(project_root: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for config in BENGALURU_STATIONS:
        hourly_path = station_output_dir(project_root, config.station_id) / f"{config.station_id}_hourly.parquet"
        if not hourly_path.exists():
            logger.warning("No hourly data for %s at %s", config.station_id, hourly_path)
            continue
        frame = read_parquet(hourly_path)
        frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
        frames[config.station_id] = frame
    return frames


def validate_no_cross_station_mixing(frame: pd.DataFrame, station_ids: list[str]) -> None:
    if "station_id" not in frame.columns:
        raise ValueError("DataFrame missing station_id column — cross-station mixing cannot be verified.")
    null_station = frame["station_id"].isna().sum()
    if null_station:
        raise ValueError(f"Found {null_station} rows with null station_id.")
    unknown = set(frame["station_id"].unique()) - set(station_ids)
    if unknown:
        raise ValueError(f"Found unknown station_ids: {unknown}")


def apply_quality_gate(
    hourly_frames: dict[str, pd.DataFrame],
) -> tuple[list[str], list[str], dict[str, dict]]:
    accepted: list[str] = []
    excluded: list[str] = []
    quality_details: dict[str, dict] = {}
    for station_id, frame in hourly_frames.items():
        pm25_hourly = frame["pm25"]
        pm25_completeness = round(float(pm25_hourly.notna().mean() * 100), 2) if not frame.empty else 0.0
        pm25_timestamps = frame.loc[pm25_hourly.notna(), "timestamp_utc"]
        longest_run_hours = _longest_continuous_run(pm25_timestamps)
        classification, recommendation = classify_dataset(frame, pm25_completeness, longest_run_hours)
        details = {
            "hourly_row_count": int(len(frame)),
            "pm25_completeness_percent": pm25_completeness,
            "longest_continuous_pm25_run_hours": longest_run_hours,
            "classification": classification,
            "recommendation": recommendation,
        }
        quality_details[station_id] = details
        if classification.startswith("Not suitable"):
            excluded.append(station_id)
            logger.warning("Excluding %s: %s", station_id, classification)
        else:
            accepted.append(station_id)
            logger.info("Accepted %s: %s (PM2.5 completeness %.1f%%)", station_id, classification, pm25_completeness)
    return accepted, excluded, quality_details


def build_multistation_features(
    accepted_frames: dict[str, pd.DataFrame],
    completeness_threshold_percent: float = 60.0,
) -> tuple[pd.DataFrame, dict]:
    combined = pd.concat(list(accepted_frames.values()), ignore_index=True)
    combined = combined.sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)
    validate_no_cross_station_mixing(combined, list(accepted_frames.keys()))
    features, metadata = create_real_features(combined, completeness_threshold_percent=completeness_threshold_percent)
    return features, metadata


def write_per_station_features(
    features: pd.DataFrame,
    accepted_station_ids: list[str],
    project_root: Path,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for station_id in accepted_station_ids:
        station_features = features[features["station_id"] == station_id].copy()
        if station_features.empty:
            logger.warning("No features for accepted station %s", station_id)
            continue
        out_dir = station_output_dir(project_root, station_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{station_id}_features_24h.parquet"
        write_parquet(station_features, out_path)
        paths[station_id] = out_path
        logger.info("Wrote %d feature rows for %s to %s", len(station_features), station_id, out_path)
    return paths


def merge_multistation(
    project_root: Path | None = None,
    completeness_threshold_percent: float = 60.0,
    min_pm25_observations_per_hour: int = 2,
) -> pd.DataFrame:
    root = project_root or Path(__file__).resolve().parents[1]
    paths = get_paths(root, dataset=DATASET_REAL_MULTISTATION)

    hourly_frames = load_all_station_hourly(root)
    if not hourly_frames:
        raise FileNotFoundError("No per-station hourly Parquets found. Run python -m pipeline.ingest_cpcb_csv --multi-station first.")

    accepted_ids, excluded_ids, quality_details = apply_quality_gate(hourly_frames)
    if not accepted_ids:
        raise ValueError("No stations passed the quality gate. Check data quality reports.")

    accepted_frames = {sid: hourly_frames[sid] for sid in accepted_ids}
    features, metadata = build_multistation_features(accepted_frames, completeness_threshold_percent)

    per_station_paths = write_per_station_features(features, accepted_ids, root)

    unified_path = paths.processed_features
    write_parquet(features, unified_path)
    logger.info("Wrote unified multi-station features (%d rows) to %s", len(features), unified_path)

    paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
    with paths.feature_columns.open("w", encoding="utf-8") as f:
        json.dump(metadata["selected_features"], f, indent=2)
    if paths.feature_metadata:
        with paths.feature_metadata.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)
    logger.info("Wrote feature_columns.json and feature_metadata.json to %s", paths.artifacts_dir)

    manifest = {
        "accepted_station_ids": accepted_ids,
        "excluded_station_ids": excluded_ids,
        "quality_details": quality_details,
        "feature_metadata": metadata,
        "per_station_feature_paths": {sid: str(p) for sid, p in per_station_paths.items()},
        "unified_features_path": str(unified_path),
    }
    paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = paths.artifacts_dir / "station_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote station manifest to %s", manifest_path)

    return features


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge quality-gated multi-station hourly data into features.")
    parser.add_argument("--completeness-threshold-percent", type=float, default=60.0)
    parser.add_argument("--min-pm25-observations-per-hour", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    merge_multistation(
        completeness_threshold_percent=args.completeness_threshold_percent,
        min_pm25_observations_per_hour=args.min_pm25_observations_per_hour,
    )


if __name__ == "__main__":
    main()
