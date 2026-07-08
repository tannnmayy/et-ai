from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.common import DATASET_REAL_HEBBAL, DATASET_REAL_MULTISTATION, get_paths
from pipeline.cpcb_csv_adapter import CPCBQualityStats, CPCBStationConfig, load_and_clean_cpcb_csv
from pipeline.station_registry import BENGALURU_STATIONS, station_id_to_cpcb_config, station_output_dir
from pipeline.storage import ensure_parent, write_parquet

logger = logging.getLogger(__name__)

HOURLY_COLUMNS = [
    "timestamp_utc",
    "station_id",
    "station_name",
    "latitude",
    "longitude",
    "pm25",
    "pm10",
    "no2",
    "temperature_c",
    "relative_humidity",
    "wind_speed_mps",
    "wind_direction_deg",
    "rainfall_mm",
    "observations_per_hour",
    "pm25_observations_per_hour",
    "pm10_observations_per_hour",
    "no2_observations_per_hour",
    "weather_observations_per_hour",
    "source",
]

WEATHER_COLUMNS = ["temperature_c", "relative_humidity", "wind_speed_mps", "wind_direction_deg", "rainfall_mm"]

CLASSIFICATION_THRESHOLDS = {
    "recommended": {"covered_days": 180, "pm25_completeness": 70.0, "longest_run_days": 30},
    "usable": {"covered_days": 90, "pm25_completeness": 50.0, "longest_run_days": 7},
}


def aggregate_to_hourly(
    cleaned_15min: pd.DataFrame,
    min_pm25_observations_per_hour: int = 2,
) -> tuple[pd.DataFrame, int]:
    frame = cleaned_15min.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    frame["timestamp_hour_utc"] = frame["timestamp_utc"].dt.floor("h")

    grouped = frame.groupby(["station_id", "timestamp_hour_utc"], as_index=False)
    hourly = grouped.agg(
        station_name=("station_name", "first"),
        latitude=("latitude", "first"),
        longitude=("longitude", "first"),
        source=("source", "first"),
        observations_per_hour=("timestamp_utc", "count"),
        pm25_observations_per_hour=("pm25", lambda s: int(s.notna().sum())),
        pm10_observations_per_hour=("pm10", lambda s: int(s.notna().sum())),
        no2_observations_per_hour=("no2", lambda s: int(s.notna().sum())),
        weather_observations_per_hour=(
            "temperature_c",
            lambda s: int(frame.loc[s.index, WEATHER_COLUMNS].notna().any(axis=1).sum()),
        ),
        pm25=("pm25", "median"),
        pm10=("pm10", "median"),
        no2=("no2", "median"),
        temperature_c=("temperature_c", "mean"),
        relative_humidity=("relative_humidity", "mean"),
        wind_speed_mps=("wind_speed_mps", "mean"),
        wind_direction_deg=("wind_direction_deg", "mean"),
        rainfall_mm=("rainfall_mm", "sum"),
    )
    hourly = hourly.rename(columns={"timestamp_hour_utc": "timestamp_utc"})
    excluded = int((hourly["pm25_observations_per_hour"] < min_pm25_observations_per_hour).sum())
    hourly.loc[hourly["pm25_observations_per_hour"] < min_pm25_observations_per_hour, "pm25"] = pd.NA
    hourly = hourly.sort_values(["station_id", "timestamp_utc"]).drop_duplicates(["station_id", "timestamp_utc"]).reset_index(drop=True)
    return hourly[HOURLY_COLUMNS], excluded


def _missingness_percent(series: pd.Series) -> float:
    if series.empty:
        return 100.0
    return round(float(series.isna().mean() * 100), 2)


def _longest_continuous_run(timestamps: pd.Series, gap_hours: int = 1) -> int:
    if timestamps.empty:
        return 0
    ordered = pd.to_datetime(timestamps, utc=True).sort_values().drop_duplicates()
    if ordered.empty:
        return 0
    longest = 1
    current = 1
    previous = ordered.iloc[0]
    for current_ts in ordered.iloc[1:]:
        delta_hours = (current_ts - previous) / pd.Timedelta(hours=1)
        if delta_hours == gap_hours:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
        previous = current_ts
    return longest


def _gaps_longer_than(timestamps: pd.Series, hours: int) -> int:
    ordered = pd.to_datetime(timestamps, utc=True).sort_values().drop_duplicates()
    if len(ordered) < 2:
        return 0
    diffs = ordered.diff().dropna() / pd.Timedelta(hours=1)
    return int((diffs > hours).sum())


def _expected_15min_intervals(earliest: pd.Timestamp, latest: pd.Timestamp) -> int:
    if pd.isna(earliest) or pd.isna(latest) or earliest >= latest:
        return 0
    return int(((latest - earliest) / pd.Timedelta(minutes=15)) + 1)


def classify_dataset(
    hourly: pd.DataFrame,
    pm25_completeness: float,
    longest_run_hours: int,
) -> tuple[str, str]:
    covered_days = 0
    if not hourly.empty:
        covered_days = int((hourly["timestamp_utc"].max() - hourly["timestamp_utc"].min()).days) + 1
    longest_run_days = longest_run_hours / 24.0

    if (
        covered_days >= CLASSIFICATION_THRESHOLDS["recommended"]["covered_days"]
        and pm25_completeness >= CLASSIFICATION_THRESHOLDS["recommended"]["pm25_completeness"]
        and longest_run_days >= CLASSIFICATION_THRESHOLDS["recommended"]["longest_run_days"]
    ):
        return (
            "Recommended for real-data training",
            "Coverage, PM2.5 completeness, and continuity meet the recommended thresholds for 24-hour PM2.5 training.",
        )
    if (
        covered_days >= CLASSIFICATION_THRESHOLDS["usable"]["covered_days"]
        and pm25_completeness >= CLASSIFICATION_THRESHOLDS["usable"]["pm25_completeness"]
        and longest_run_days >= CLASSIFICATION_THRESHOLDS["usable"]["longest_run_days"]
    ):
        return (
            "Usable with caveats",
            "The station has enough PM2.5 history for pipeline validation, but gaps or missing auxiliary sensors should be interpreted cautiously.",
        )
    return (
        "Not suitable",
        "Coverage, PM2.5 completeness, or continuity fall below the minimum thresholds for reliable 24-hour PM2.5 training.",
    )


def build_quality_metrics(
    cleaned_15min: pd.DataFrame,
    hourly: pd.DataFrame,
    adapter_stats: CPCBQualityStats,
    station: CPCBStationConfig,
    min_pm25_observations_per_hour: int,
    hours_excluded_for_pm25: int,
) -> dict[str, Any]:
    pm25_hourly = hourly["pm25"]
    pm25_completeness = round(float(pm25_hourly.notna().mean() * 100), 2) if not hourly.empty else 0.0
    pm25_timestamps = hourly.loc[pm25_hourly.notna(), "timestamp_utc"]
    longest_run_hours = _longest_continuous_run(pm25_timestamps)
    classification, recommendation = classify_dataset(hourly, pm25_completeness, longest_run_hours)

    earliest = pd.to_datetime(cleaned_15min["timestamp_utc"], utc=True).min() if not cleaned_15min.empty else pd.NaT
    latest = pd.to_datetime(cleaned_15min["timestamp_utc"], utc=True).max() if not cleaned_15min.empty else pd.NaT

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_source_file": adapter_stats.raw_path,
        "station_id": station.station_id,
        "station_name": station.station_name,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "source": station.source,
        "raw_headers": adapter_stats.raw_headers,
        "raw_row_count": adapter_stats.raw_row_count,
        "cleaned_15min_row_count": adapter_stats.cleaned_15min_row_count,
        "hourly_row_count": int(len(hourly)),
        "earliest_timestamp_utc": adapter_stats.earliest_timestamp_utc,
        "latest_timestamp_utc": adapter_stats.latest_timestamp_utc,
        "timestamp_interpretation": adapter_stats.timestamp_interpretation,
        "source_timezone_assumption": adapter_stats.source_timezone_assumption,
        "utc_conversion_note": adapter_stats.utc_conversion_note,
        "invalid_timestamp_count": adapter_stats.invalid_timestamp_count,
        "duplicate_timestamp_count": adapter_stats.duplicate_timestamp_count,
        "numeric_conversion_failures": adapter_stats.numeric_conversion_failures,
        "negative_value_rejections": adapter_stats.negative_value_rejections,
        "plausibility_flag_counts": adapter_stats.plausibility_flag_counts,
        "expected_15min_intervals": _expected_15min_intervals(earliest, latest),
        "observed_15min_intervals": adapter_stats.cleaned_15min_row_count,
        "missingness_15min_percent": {
            "pm25": _missingness_percent(cleaned_15min["pm25"]),
            "pm10": _missingness_percent(cleaned_15min["pm10"]),
            "no2": _missingness_percent(cleaned_15min["no2"]),
            "temperature_c": _missingness_percent(cleaned_15min["temperature_c"]),
            "relative_humidity": _missingness_percent(cleaned_15min["relative_humidity"]),
            "wind_speed_mps": _missingness_percent(cleaned_15min["wind_speed_mps"]),
            "rainfall_mm": _missingness_percent(cleaned_15min["rainfall_mm"]),
        },
        "missingness_hourly_percent": {
            "pm25": _missingness_percent(hourly["pm25"]),
            "pm10": _missingness_percent(hourly["pm10"]),
            "no2": _missingness_percent(hourly["no2"]),
            "temperature_c": _missingness_percent(hourly["temperature_c"]),
            "relative_humidity": _missingness_percent(hourly["relative_humidity"]),
            "wind_speed_mps": _missingness_percent(hourly["wind_speed_mps"]),
            "rainfall_mm": _missingness_percent(hourly["rainfall_mm"]),
        },
        "hours_excluded_for_insufficient_pm25": hours_excluded_for_pm25,
        "min_pm25_observations_per_hour": min_pm25_observations_per_hour,
        "longest_continuous_pm25_run_hours": longest_run_hours,
        "pm25_gaps_longer_than_24h": _gaps_longer_than(pm25_timestamps, 24),
        "rainfall_treatment": adapter_stats.rainfall_treatment,
        "dataset_suitability_classification": classification,
        "recommendation": recommendation,
        "limitation": "One station validates the real-data pipeline; it does not yet prove citywide generalization.",
    }


def write_quality_reports(metrics: dict[str, Any], csv_path: Path, md_path: Path) -> None:
    ensure_parent(csv_path)
    flat = metrics.copy()
    for key in [
        "raw_headers",
        "numeric_conversion_failures",
        "negative_value_rejections",
        "plausibility_flag_counts",
        "missingness_15min_percent",
        "missingness_hourly_percent",
    ]:
        flat[key] = json.dumps(flat.get(key, {}), ensure_ascii=False)
    pd.DataFrame([flat]).to_csv(csv_path, index=False)

    lines = [
        "# Hebbal CPCB/KSPCB Data Quality Report",
        "",
        f"Generated at (UTC): {metrics['generated_at_utc']}",
        "",
        "## Source",
        f"- Raw file: `{metrics['raw_source_file']}`",
        f"- Station: `{metrics['station_name']}` (`{metrics['station_id']}`)",
        f"- Source label: {metrics['source']}",
        "",
        "## Raw CSV Inspection",
        f"- Detected headers: `{', '.join(metrics['raw_headers'])}`",
        f"- Raw row count: {metrics['raw_row_count']}",
        f"- Cleaned 15-minute rows: {metrics['cleaned_15min_row_count']}",
        f"- Hourly rows: {metrics['hourly_row_count']}",
        f"- Earliest UTC timestamp: {metrics['earliest_timestamp_utc']}",
        f"- Latest UTC timestamp: {metrics['latest_timestamp_utc']}",
        "",
        "## Timestamp Handling",
        f"- Interpretation: {metrics['timestamp_interpretation']}",
        f"- Source timezone assumption: {metrics['source_timezone_assumption']}",
        f"- UTC conversion: {metrics['utc_conversion_note']}",
        f"- Invalid timestamps: {metrics['invalid_timestamp_count']}",
        "",
        "## Cleaning Summary",
        f"- Duplicate timestamps resolved: {metrics['duplicate_timestamp_count']}",
        f"- Numeric conversion failures: `{json.dumps(metrics['numeric_conversion_failures'])}`",
        f"- Negative-value rejections: `{json.dumps(metrics['negative_value_rejections'])}`",
        f"- Plausibility flags: `{json.dumps(metrics['plausibility_flag_counts'])}`",
        f"- Expected 15-minute intervals: {metrics['expected_15min_intervals']}",
        f"- Observed 15-minute intervals: {metrics['observed_15min_intervals']}",
        "",
        "## Missingness",
        "### 15-minute",
        *[f"- {key}: {value}%" for key, value in metrics["missingness_15min_percent"].items()],
        "",
        "### Hourly",
        *[f"- {key}: {value}%" for key, value in metrics["missingness_hourly_percent"].items()],
        "",
        "## Hourly PM2.5 Controls",
        f"- Minimum PM2.5 observations per hour: {metrics['min_pm25_observations_per_hour']}",
        f"- Hours excluded for insufficient PM2.5: {metrics['hours_excluded_for_insufficient_pm25']}",
        f"- Longest continuous hourly PM2.5 run (hours): {metrics['longest_continuous_pm25_run_hours']}",
        f"- PM2.5 gaps longer than 24 hours: {metrics['pm25_gaps_longer_than_24h']}",
        "",
        "## Rainfall",
        metrics["rainfall_treatment"],
        "",
        "## Suitability",
        f"- Classification: **{metrics['dataset_suitability_classification']}**",
        f"- Recommendation: {metrics['recommendation']}",
        f"- Limitation: {metrics['limitation']}",
    ]
    ensure_parent(md_path)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ingest_cpcb_csv(
    input_path: Path,
    station: CPCBStationConfig,
    output_15min: Path,
    output_hourly: Path,
    report_csv: Path,
    report_md: Path,
    quality_summary: Path,
    min_pm25_observations_per_hour: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    cleaned, adapter_stats = load_and_clean_cpcb_csv(input_path, station)
    write_parquet(cleaned, output_15min)
    hourly, excluded = aggregate_to_hourly(cleaned, min_pm25_observations_per_hour=min_pm25_observations_per_hour)
    write_parquet(hourly, output_hourly)

    metrics = build_quality_metrics(
        cleaned,
        hourly,
        adapter_stats,
        station,
        min_pm25_observations_per_hour,
        excluded,
    )
    write_quality_reports(metrics, report_csv, report_md)
    ensure_parent(quality_summary)
    quality_summary.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logger.info("Wrote cleaned 15-minute data to %s", output_15min)
    logger.info("Wrote hourly data to %s", output_hourly)
    logger.info("Dataset classification: %s", metrics["dataset_suitability_classification"])
    return cleaned, hourly, metrics


def ingest_all_stations(
    project_root: Path | None = None,
    min_pm25_observations_per_hour: int = 2,
) -> dict[str, dict[str, Any]]:
    from ml.common import get_project_root

    root = Path(project_root or get_project_root()).resolve()
    results: dict[str, dict[str, Any]] = {}
    for station_config in BENGALURU_STATIONS:
        raw_path = root / "data" / "raw" / "cpcb" / station_config.source_file
        if not raw_path.exists():
            logger.warning("Skipping %s: raw file not found at %s", station_config.station_id, raw_path)
            continue
        out_dir = station_output_dir(root, station_config.station_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        cpcb_config = station_id_to_cpcb_config(station_config)
        cleaned, hourly, metrics = ingest_cpcb_csv(
            input_path=raw_path,
            station=cpcb_config,
            output_15min=out_dir / f"{station_config.station_id}_15min_clean.parquet",
            output_hourly=out_dir / f"{station_config.station_id}_hourly.parquet",
            report_csv=out_dir / f"{station_config.station_id}_quality.csv",
            report_md=out_dir / f"{station_config.station_id}_quality.md",
            quality_summary=out_dir / f"{station_config.station_id}_quality_summary.json",
            min_pm25_observations_per_hour=min_pm25_observations_per_hour,
        )
        results[station_config.station_id] = metrics
        logger.info(
            "Ingested %s: %d hourly rows, classification=%s",
            station_config.station_id,
            metrics["hourly_row_count"],
            metrics["dataset_suitability_classification"],
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest a CPCB/KSPCB 15-minute CSV into canonical real-data outputs.")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--station-id", default="cpcb_hebbal")
    parser.add_argument("--station-name", default="Hebbal, Bengaluru - KSPCB")
    parser.add_argument("--source-timezone", default="Asia/Kolkata")
    parser.add_argument("--latitude", type=float, default=None)
    parser.add_argument("--longitude", type=float, default=None)
    parser.add_argument("--min-pm25-observations-per-hour", type=int, default=2)
    parser.add_argument("--multi-station", action="store_true", help="Ingest all registered Bengaluru stations")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    if args.multi_station:
        ingest_all_stations(min_pm25_observations_per_hour=args.min_pm25_observations_per_hour)
        return
    if args.input is None:
        raise SystemExit("Error: --input is required when --multi-station is not set.")
    paths = get_paths(dataset=DATASET_REAL_HEBBAL)
    station = CPCBStationConfig(
        station_id=args.station_id,
        station_name=args.station_name,
        latitude=args.latitude,
        longitude=args.longitude,
        source_timezone=args.source_timezone,
    )
    ingest_cpcb_csv(
        input_path=args.input,
        station=station,
        output_15min=paths.cleaned_15min,
        output_hourly=paths.processed_hourly,
        report_csv=paths.quality_report_csv,
        report_md=paths.quality_report_md,
        quality_summary=paths.data_quality_summary,
        min_pm25_observations_per_hour=args.min_pm25_observations_per_hour,
    )


if __name__ == "__main__":
    main()
