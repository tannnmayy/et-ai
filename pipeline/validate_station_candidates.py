from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import BENGALURU_BOUNDING_BOX

REQUIRED_COLUMNS = [
    "raw_filename", "proposed_station_id", "display_name", "city",
    "latitude", "longitude", "source_authority",
    "metadata_verification_status", "geospatial_eligible",
    "onboarding_status", "notes",
]

OPTIONAL_COLUMNS = [
    "metadata_source_url",
]

CANDIDATES_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "bengaluru_station_candidates.csv"
BBOX = BENGALURU_BOUNDING_BOX


class ValidationError(Exception):
    pass


def validate_candidates(dry_run: bool = False) -> list[dict[str, Any]]:
    if not CANDIDATES_PATH.exists():
        raise ValidationError(f"Candidates file not found: {CANDIDATES_PATH}")

    df = pd.read_csv(CANDIDATES_PATH)
    errors: list[dict[str, Any]] = []

    # Required columns
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValidationError(f"Missing required columns: {missing_cols}")

    # Add optional columns with defaults if absent
    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    for idx, row in df.iterrows():
        sid = str(row.get("proposed_station_id", f"row_{idx}"))

        # Duplicate station IDs
        ids = df["proposed_station_id"].dropna().astype(str).str.strip()
        dup_ids = ids[ids.duplicated(keep=False)]
        for dup_id in dup_ids.unique():
            dup_rows = df[ids == dup_id].index.tolist()
            errors.append({
                "row": dup_rows[0], "station_id": dup_id,
                "field": "proposed_station_id",
                "error": f"Duplicate station ID found in rows {dup_rows}",
            })

        # Missing coordinates
        lat = row.get("latitude")
        lng = row.get("longitude")
        lat_valid = _is_valid_float(lat)
        lng_valid = _is_valid_float(lng)
        if not lat_valid or not lng_valid:
            errors.append({
                "row": idx, "station_id": sid,
                "field": "latitude/longitude",
                "error": f"Missing or invalid coordinates (lat={lat}, lng={lng})",
            })
            continue

        lat_val = float(lat)
        lng_val = float(lng)

        # Outside bounding box
        if not (BBOX["south"] <= lat_val <= BBOX["north"]):
            errors.append({
                "row": idx, "station_id": sid,
                "field": "latitude",
                "error": f"Latitude {lat_val} outside Bengaluru bounds ({BBOX['south']} to {BBOX['north']})",
            })
        if not (BBOX["west"] <= lng_val <= BBOX["east"]):
            errors.append({
                "row": idx, "station_id": sid,
                "field": "longitude",
                "error": f"Longitude {lng_val} outside Bengaluru bounds ({BBOX['west']} to {BBOX['east']})",
            })

        # Duplicate coordinates
        for jdx, other in df.iterrows():
            if idx >= jdx:
                continue
            other_lat = _safe_float(other.get("latitude"))
            other_lng = _safe_float(other.get("longitude"))
            if other_lat is not None and other_lng is not None and other_lat == lat_val and other_lng == lng_val:
                notes = str(row.get("notes", ""))
                if "duplicate coords" not in notes.lower():
                    errors.append({
                        "row": idx, "station_id": sid,
                        "field": "coordinates",
                        "error": f"Duplicate coordinates ({lat_val}, {lng_val}) row {jdx} without justification in notes",
                    })

        # Verification status
        status = str(row.get("metadata_verification_status", "")).strip().lower()
        if status != "verified":
            errors.append({
                "row": idx, "station_id": sid,
                "field": "metadata_verification_status",
                "error": f"Status is '{status}', must be 'verified'",
            })

        # Geospatial eligible
        geo = str(row.get("geospatial_eligible", "")).strip().lower()
        if geo not in ("true", "1", "yes"):
            errors.append({
                "row": idx, "station_id": sid,
                "field": "geospatial_eligible",
                "error": f"geospatial_eligible must be True, got '{geo}'",
            })

    return errors


def _is_valid_float(val: Any) -> bool:
    if val is None:
        return False
    try:
        f = float(val)
        import math
        if math.isnan(f):
            return False
        return True
    except (ValueError, TypeError):
        return False


def _safe_float(val: Any) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate station candidate metadata.")
    parser.add_argument("--dry-run", action="store_true", help="Print validation results without side effects.")
    args = parser.parse_args()

    errors = validate_candidates(dry_run=args.dry_run)
    if errors:
        print(f"\n{len(errors)} validation error(s) found:\n")
        for e in errors:
            print(f"  Row {e['row']} ({e['station_id']}): [{e['field']}] {e['error']}")
        if not args.dry_run:
            sys.exit(1)
    else:
        print("\nAll candidates pass validation.")


if __name__ == "__main__":
    main()
