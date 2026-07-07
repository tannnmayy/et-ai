from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import BENGALURU_BOUNDING_BOX, get_project_root

logger = logging.getLogger(__name__)

PROJECT_ROOT = get_project_root()
CANDIDATES_PATH = PROJECT_ROOT / "data" / "reference" / "bengaluru_station_candidates.csv"
REGISTRY_PATH = PROJECT_ROOT / "data" / "reference" / "bengaluru_station_registry.csv"
AUDIT_DIR = PROJECT_ROOT / "data" / "reports" / "station_coverage"
AUDIT_CSV = AUDIT_DIR / "bengaluru_station_onboarding_audit.csv"
REPORTS_DIR = PROJECT_ROOT / "data" / "reports" / "station_coverage"

BBOX = BENGALURU_BOUNDING_BOX

EXCLUDED_FILES = {"jigani_bengaluru_kspcb_15m.csv"}


def _load_candidates() -> pd.DataFrame:
    if not CANDIDATES_PATH.exists():
        raise FileNotFoundError(f"Candidates file not found: {CANDIDATES_PATH}")
    return pd.read_csv(CANDIDATES_PATH)


def _load_registry() -> list[dict[str, str]]:
    if not REGISTRY_PATH.exists():
        return []
    with REGISTRY_PATH.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_audit() -> dict[str, dict[str, Any]]:
    if not AUDIT_CSV.exists():
        return {}
    df = pd.read_csv(AUDIT_CSV)
    result: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        fid = str(row.get("raw_filename", ""))
        result[fid] = row.to_dict()
    return result


def _existing_station_ids(registry: list[dict[str, str]]) -> set[str]:
    return {r.get("station_id", "").strip() for r in registry if r.get("station_id")}


def check_activation_gates(row: dict[str, Any], audit: dict[str, Any], existing_ids: set[str]) -> tuple[bool, list[str]]:
    gates: list[str] = []
    raw_filename = str(row.get("raw_filename", "")).strip()
    sid = str(row.get("proposed_station_id", "")).strip()

    # Exclusion
    if raw_filename in EXCLUDED_FILES:
        return False, [f"File {raw_filename} is explicitly excluded (Jigani)"]

    # Raw filename present
    if not raw_filename:
        return False, ["raw_filename is empty"]

    # Station ID unique
    if sid in existing_ids:
        return False, [f"Station ID '{sid}' already exists in active registry"]

    # Metadata verification
    status = str(row.get("metadata_verification_status", "")).strip().lower()
    if status != "verified":
        return False, [f"metadata_verification_status is '{status}', need 'verified'"]

    # Source authority populated
    authority = str(row.get("source_authority", "")).strip()
    if not authority:
        return False, ["source_authority is empty"]

    # Coordinates valid and within bbox
    lat = _safe_float(row.get("latitude"))
    lng = _safe_float(row.get("longitude"))
    if lat is None or lng is None:
        return False, ["Missing or invalid coordinates"]
    if not (BBOX["south"] <= lat <= BBOX["north"]):
        gates.append(f"latitude {lat} outside bbox")
    if not (BBOX["west"] <= lng <= BBOX["east"]):
        gates.append(f"longitude {lng} outside bbox")

    # Audit passed
    audit_row = audit.get(raw_filename, {})
    audit_status = str(audit_row.get("eligibility_status", "")).strip()
    if audit_status and audit_status != "eligible":
        gates.append(f"onboarding audit status: {audit_status}")

    if gates:
        return False, gates
    return True, ["All gates passed"]


def build_activation_record(candidate: dict[str, Any]) -> dict[str, str]:
    lat = _safe_float(candidate.get("latitude"))
    lng = _safe_float(candidate.get("longitude"))
    sid = str(candidate.get("proposed_station_id", "")).strip()
    display = str(candidate.get("display_name", sid)).strip()
    authority = str(candidate.get("source_authority", "")).strip()
    raw = str(candidate.get("raw_filename", "")).strip()
    geo = str(candidate.get("geospatial_eligible", "True")).strip().lower() in ("true", "1", "yes")
    return {
        "station_id": sid,
        "display_name": display,
        "city": "bengaluru",
        "latitude": f"{lat:.6f}" if lat is not None else "",
        "longitude": f"{lng:.6f}" if lng is not None else "",
        "source": authority,
        "coordinate_source": "candidate_metadata",
        "coordinate_confidence": "Manual",
        "verification_note": f"Activated by pipeline.activate_bengaluru_stations on {datetime.now(timezone.utc).isoformat()}",
        "active": "True",
        "geospatial_eligible": str(geo),
        "raw_filename": raw,
    }


REGISTRY_CSV_COLUMNS = [
    "station_id", "display_name", "city", "latitude", "longitude",
    "source", "coordinate_source", "coordinate_confidence", "verification_note",
    "active", "geospatial_eligible", "raw_filename",
]


def write_registry(registry: list[dict[str, str]]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REGISTRY_CSV_COLUMNS)
        writer.writeheader()
        for row in registry:
            writer.writerow(row)


def run_activation(dry_run: bool = False) -> list[dict[str, Any]]:
    candidates = _load_candidates()
    audit = _load_audit()
    registry = _load_registry()
    existing_ids = _existing_station_ids(registry)

    results: list[dict[str, Any]] = []
    activated: list[dict[str, str]] = []

    for _, cand in candidates.iterrows():
        raw_filename = str(cand.get("raw_filename", "")).strip()
        sid = str(cand.get("proposed_station_id", "")).strip()
        passed, reasons = check_activation_gates(cand.to_dict(), audit, existing_ids)
        results.append({
            "raw_filename": raw_filename,
            "proposed_station_id": sid,
            "activation_possible": passed,
            "details": "; ".join(reasons),
        })
        if passed:
            record = build_activation_record(cand.to_dict())
            activated.append(record)
            existing_ids.add(sid)

    # Print summary
    print(f"\n{'File':50s} {'ID':30s} {'Status':10s} Details")
    print("-" * 120)
    for r in results:
        status = "ACTIVATE" if r["activation_possible"] else "BLOCKED"
        print(f"{r['raw_filename']:50s} {r['proposed_station_id']:30s} {status:10s} {r['details']}")

    if dry_run:
        print(f"\nDry run: {len([r for r in results if r['activation_possible']])} would activate, "
              f"{len([r for r in results if not r['activation_possible']])} blocked.")
        return results

    # Apply: append to registry
    if activated:
        registry.extend(activated)
        write_registry(registry)
        print(f"\nActivated {len(activated)} station(s): {[a['station_id'] for a in activated]}")
    else:
        print("\nNo stations to activate.")

    # Write activation report
    reports_dir = REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir / "station_activation_report.csv"
    md_path = reports_dir / "station_activation_report.md"

    pd.DataFrame(results).to_csv(csv_path, index=False)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Station Activation Report",
        "",
        f"**Generated:** {now}",
        f"**Activated:** {len(activated)}",
        f"**Blocked:** {len([r for r in results if not r['activation_possible']])}",
        "",
        "## Activated",
    ]
    for a in activated:
        lines.append(f"- `{a['station_id']}` ({a.get('display_name', '')})")
    lines.extend(["", "## Blocked"])
    for r in results:
        if not r["activation_possible"]:
            lines.append(f"- `{r['proposed_station_id']}` ({r['raw_filename']}): {r['details']}")
    lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote activation report: {csv_path}")
    print(f"Wrote activation report: {md_path}")
    return results


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Activate verified station candidates into the canonical registry.")
    parser.add_argument("--dry-run", action="store_true", help="Show activation plan without modifying the registry.")
    parser.add_argument("--apply", action="store_true", help="Apply activation, updating the registry CSV.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.apply and not args.dry_run:
        print("Specify --dry-run to preview or --apply to execute.")
        return

    run_activation(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
