from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline import cpcb_csv_adapter
from pipeline.cpcb_csv_adapter import CPCBStationConfig
from backend.app.config import get_project_root

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Eligibility thresholds (named constants with explanations)
# ---------------------------------------------------------------------------

# Minimum number of raw rows to consider a station viable.
# At 15-minute cadence, 96 rows/day × 30 days = 2880.
MIN_RAW_ROW_COUNT: int = 500

# Minimum fraction of PM2.5 non-null values in the raw cleaned 15-min data.
# Below this threshold the station has insufficient PM2.5 data for forecasting.
MIN_PM25_NONNULL_FRACTION: float = 0.10

# Minimum fraction of timestamps that parse successfully.
# If >50% of timestamps are invalid the station likely has a structural data issue.
MIN_TIMESTAMP_PARSE_FRACTION: float = 0.50

# Maximum allowable fraction of duplicate timestamps.
# High duplication suggests a data quality issue that requires investigation.
MAX_DUPLICATE_TIMESTAMP_FRACTION: float = 0.05

# ---------------------------------------------------------------------------
# Scope: only these 6 candidate CSVs
# ---------------------------------------------------------------------------

IN_SCOPE_CANDIDATES: list[str] = [
    "btm_layout_bengaluru_cpcb_15m.csv",
    "bwssb_kadabesanahalli_bengaluru_cpcb_15m.csv",
    "city_railway_station_bengaluru_kspcb_15m.csv",
    "kasturi_nagar_bengaluru_kspcb_15m.csv",
    "rvce_mailasandra_bengaluru_kspcb_15m.csv",
    "sanegurava_halli_bengaluru_kspcb_15m.csv",
]

PROJECT_ROOT = get_project_root()
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "cpcb"
REPORTS_DIR = PROJECT_ROOT / "data" / "reports" / "station_coverage"


def _detect_authority(filename: str) -> str:
    lower = filename.lower()
    if "cpcb" in lower and "kspcb" in lower:
        return "CPCB/KSPCB"
    if "cpcb" in lower:
        return "CPCB"
    if "kspcb" in lower:
        return "KSPCB"
    return "Unknown"


def _propose_station_id(filename: str) -> str:
    stem = Path(filename).stem
    parts = stem.split("_")
    name_parts = [p for p in parts if p not in ("bengaluru", "cpcb", "kspcb", "15m")]
    return "cpcb_" + "_".join(name_parts)


def _detect_timestamp_column(headers: list[str]) -> str | None:
    lower_headers = [h.lower().strip() for h in headers]
    for i, h in enumerate(lower_headers):
        if h in ("timestamp", "date", "datetime", "from date", "date & time"):
            return headers[i]
    return None


def _estimate_cadence(cleaned: pd.DataFrame, stats: cpcb_csv_adapter.CPCBQualityStats) -> str:
    if cleaned.empty:
        return "unknown"
    timestamps = pd.to_datetime(cleaned["timestamp_utc"], utc=True).sort_values()
    if len(timestamps) < 2:
        return "unknown"
    diffs = timestamps.diff().dropna().dt.total_seconds()
    median_gap = float(diffs.median())
    if 840 <= median_gap <= 960:
        return "15-minute"
    if 3540 <= median_gap <= 3660:
        return "hourly"
    return f"irregular (~{median_gap:.0f}s median gap)"


def _calculate_pm25_fraction(cleaned: pd.DataFrame) -> float:
    if "pm25" not in cleaned.columns or cleaned.empty:
        return 0.0
    non_null = cleaned["pm25"].notna().sum()
    return non_null / len(cleaned) if len(cleaned) > 0 else 0.0


def _assess_eligibility(
    raw_row_count: int,
    pm25_fraction: float,
    timestamp_parse_fraction: float,
    duplicate_fraction: float,
) -> tuple[str, str]:
    failures: list[str] = []
    if raw_row_count < MIN_RAW_ROW_COUNT:
        failures.append(f"raw rows ({raw_row_count}) < {MIN_RAW_ROW_COUNT}")
    if pm25_fraction < MIN_PM25_NONNULL_FRACTION:
        failures.append(f"PM2.5 non-null fraction ({pm25_fraction:.1%}) < {MIN_PM25_NONNULL_FRACTION:.0%}")
    if timestamp_parse_fraction < MIN_TIMESTAMP_PARSE_FRACTION:
        failures.append(f"timestamp parse fraction ({timestamp_parse_fraction:.1%}) < {MIN_TIMESTAMP_PARSE_FRACTION:.0%}")
    if duplicate_fraction > MAX_DUPLICATE_TIMESTAMP_FRACTION:
        failures.append(f"duplicate fraction ({duplicate_fraction:.1%}) > {MAX_DUPLICATE_TIMESTAMP_FRACTION:.0%}")
    if failures:
        return "ineligible", "; ".join(failures)
    return "eligible", "Passes all minimum thresholds"


def audit_single_candidate(filename: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "raw_filename": filename,
        "proposed_station_id": "",
        "detected_station_name": "",
        "source_authority": "",
        "row_count": 0,
        "detected_timestamp_column": "",
        "timestamp_parse_success_count": 0,
        "timestamp_parse_failure_count": 0,
        "earliest_timestamp_utc": "",
        "latest_timestamp_utc": "",
        "duplicate_timestamp_count": 0,
        "pm25_column_detected": False,
        "pm25_non_null_fraction": 0.0,
        "estimated_sampling_cadence": "",
        "malformed_row_count": 0,
        "eligibility_status": "",
        "exclusion_reason": "",
    }
    try:
        row["proposed_station_id"] = _propose_station_id(filename)
        row["source_authority"] = _detect_authority(filename)
        filepath = RAW_DIR / filename
        if not filepath.exists():
            row["eligibility_status"] = "error"
            row["exclusion_reason"] = f"File not found: {filepath}"
            return row
        station_cfg = CPCBStationConfig(
            station_id=row["proposed_station_id"],
            station_name=filename,
            source=row["source_authority"],
        )
        raw_frame = cpcb_csv_adapter.read_raw_csv(str(filepath))
        row["row_count"] = len(raw_frame)
        cleaned, stats = cpcb_csv_adapter.clean_cpcb_frame(raw_frame, station_cfg, raw_path=str(filepath))
        row["detected_station_name"] = stats.raw_headers[0] if stats.raw_headers else ""
        row["detected_timestamp_column"] = _detect_timestamp_column(stats.raw_headers) or ""
        total_timestamps = stats.raw_row_count
        row["timestamp_parse_failure_count"] = stats.invalid_timestamp_count
        row["timestamp_parse_success_count"] = total_timestamps - stats.invalid_timestamp_count
        row["earliest_timestamp_utc"] = stats.earliest_timestamp_utc or ""
        row["latest_timestamp_utc"] = stats.latest_timestamp_utc or ""
        row["duplicate_timestamp_count"] = stats.duplicate_timestamp_count
        row["pm25_column_detected"] = "pm25" in cleaned.columns
        row["pm25_non_null_fraction"] = round(_calculate_pm25_fraction(cleaned), 4)
        row["estimated_sampling_cadence"] = _estimate_cadence(cleaned, stats)
        pm25_frac = row["pm25_non_null_fraction"]
        ts_parse_frac = (row["timestamp_parse_success_count"] / total_timestamps) if total_timestamps > 0 else 0.0
        dup_frac = (row["duplicate_timestamp_count"] / total_timestamps) if total_timestamps > 0 else 0.0
        row["eligibility_status"], row["exclusion_reason"] = _assess_eligibility(
            row["row_count"], pm25_frac, ts_parse_frac, dup_frac,
        )
    except Exception as e:
        row["eligibility_status"] = "error"
        row["exclusion_reason"] = str(e)
        logger.warning("Audit failed for %s: %s", filename, e)
    return row


def run_audit() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filename in IN_SCOPE_CANDIDATES:
        row = audit_single_candidate(filename)
        rows.append(row)
    return rows


def _print_audit_table(rows: list[dict[str, Any]]) -> None:
    print()
    print("=" * 120)
    print(f"{'Raw Filename':45s} {'ID':30s} {'Rows':>6s} {'PM2.5%':>7s} {'Status':12s} {'Notes'}")
    print("-" * 120)
    for r in rows:
        pm25 = f"{r['pm25_non_null_fraction']:.0%}" if r['pm25_non_null_fraction'] else "N/A"
        status = r["eligibility_status"]
        notes = r["exclusion_reason"] if r["exclusion_reason"] else ""
        print(f"{r['raw_filename']:45s} {r['proposed_station_id']:30s} {r['row_count']:>6d} {pm25:>7s} {status:12s} {notes}")
    print("=" * 120)


REPORT_COLUMNS = [
    "raw_filename", "proposed_station_id", "detected_station_name",
    "source_authority", "row_count", "detected_timestamp_column",
    "timestamp_parse_success_count", "timestamp_parse_failure_count",
    "earliest_timestamp_utc", "latest_timestamp_utc",
    "duplicate_timestamp_count", "pm25_column_detected",
    "pm25_non_null_fraction", "estimated_sampling_cadence",
    "eligibility_status", "exclusion_reason",
]


def _write_csv_report(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=REPORT_COLUMNS).to_csv(path, index=False)


def _write_md_report(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Bengaluru Station Onboarding Audit",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Candidates inspected:** {len(rows)}",
        "",
        "## Eligibility Thresholds",
        "",
        f"- Minimum raw rows: {MIN_RAW_ROW_COUNT}",
        f"- Minimum PM2.5 non-null fraction: {MIN_PM25_NONNULL_FRACTION:.0%}",
        f"- Minimum timestamp parse fraction: {MIN_TIMESTAMP_PARSE_FRACTION:.0%}",
        f"- Maximum duplicate timestamp fraction: {MAX_DUPLICATE_TIMESTAMP_FRACTION:.0%}",
        "",
        "## Results",
        "",
        "| File | ID | Rows | PM2.5% | Status | Notes |",
        "|------|----|------|--------|--------|-------|",
    ]
    for r in rows:
        pm25 = f"{r['pm25_non_null_fraction']:.0%}" if r['pm25_non_null_fraction'] else "N/A"
        status = r["eligibility_status"]
        notes = r["exclusion_reason"].replace("|", "/") if r["exclusion_reason"] else ""
        lines.append(f"| {r['raw_filename']} | {r['proposed_station_id']} | {r['row_count']} | {pm25} | {status} | {notes} |")
    lines.extend([
        "",
        "## Summary",
        "",
        f"- Eligible: {sum(1 for r in rows if r['eligibility_status'] == 'eligible')}",
        f"- Ineligible: {sum(1 for r in rows if r['eligibility_status'] == 'ineligible')}",
        f"- Errors: {sum(1 for r in rows if r['eligibility_status'] == 'error')}",
        "",
        "## Excluded Candidates (Not in Scope)",
        "",
        "- **jigani_bengaluru_kspcb_15m.csv**: Deferred pending a future Greater Bengaluru geographic-scope decision.",
        "",
        "*Audit performed by pipeline.audit_bengaluru_station_coverage*",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit candidate CPCB/KSPCB CSVs for onboarding eligibility.")
    parser.add_argument("--dry-run", action="store_true", help="Print audit table and exit without writing files.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger.info("Starting Bengaluru station coverage audit...")
    logger.info("Scanning %d candidate files in %s", len(IN_SCOPE_CANDIDATES), RAW_DIR)

    rows = run_audit()
    _print_audit_table(rows)

    if args.dry_run:
        print("\nDry run complete. No files written.")
        return

    reports_dir = REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir / "bengaluru_station_onboarding_audit.csv"
    md_path = reports_dir / "bengaluru_station_onboarding_audit.md"
    _write_csv_report(rows, csv_path)
    _write_md_report(rows, md_path)
    logger.info("Wrote CSV report: %s", csv_path)
    logger.info("Wrote Markdown report: %s", md_path)

    eligible = sum(1 for r in rows if r["eligibility_status"] == "eligible")
    ineligible = sum(1 for r in rows if r["eligibility_status"] == "ineligible")
    errors = sum(1 for r in rows if r["eligibility_status"] == "error")
    logger.info("Audit complete: %d eligible, %d ineligible, %d errors", eligible, ineligible, errors)


if __name__ == "__main__":
    main()
