from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import BENGALURU_BOUNDING_BOX, get_project_root

logger = logging.getLogger(__name__)

PROJECT_ROOT = get_project_root()
CANDIDATES_PATH = PROJECT_ROOT / "data" / "reference" / "bengaluru_station_candidates.csv"
REPORTS_DIR = PROJECT_ROOT / "data" / "reports" / "station_coverage"

BBOX = BENGALURU_BOUNDING_BOX

VERIFICATION_REPORT_COLUMNS = [
    "proposed_station_id",
    "raw_filename",
    "decision",
    "latitude_considered",
    "longitude_considered",
    "source_authority",
    "source_url",
    "evidence_note",
    "rejection_reason",
]

EXCLUDED_FILES = {"jigani_bengaluru_kspcb_15m.csv"}

# ---------------------------------------------------------------------------
# Source handler framework
# ---------------------------------------------------------------------------


class SourceResult:
    result: str  # "found", "not_found", "ambiguous", "out_of_scope"
    latitude: float | None
    longitude: float | None
    display_name: str | None
    source_authority: str | None
    source_url: str | None
    evidence_note: str | None
    rejection_reason: str | None

    def __init__(
        self,
        result: str = "not_found",
        latitude: float | None = None,
        longitude: float | None = None,
        display_name: str | None = None,
        source_authority: str | None = None,
        source_url: str | None = None,
        evidence_note: str | None = None,
        rejection_reason: str | None = None,
    ):
        self.result = result
        self.latitude = latitude
        self.longitude = longitude
        self.display_name = display_name
        self.source_authority = source_authority
        self.source_url = source_url
        self.evidence_note = evidence_note
        self.rejection_reason = rejection_reason


class BaseSourceHandler(ABC):
    label: str

    @abstractmethod
    def lookup(self, station_id: str, raw_filename: str) -> SourceResult:
        ...


class CPCBSourceHandler(BaseSourceHandler):
    label = "CPCB/CAAQMS"

    def lookup(self, station_id: str, raw_filename: str) -> SourceResult:
        url = "https://airquality.cpcb.gov.in"
        return SourceResult(
            result="not_found",
            source_authority="CPCB",
            source_url=url,
            evidence_note="CPCB web portal does not expose a machine-readable station registry API. "
            "Manual verification via https://airquality.cpcb.gov.in is required.",
        )


class KSPCBSourceHandler(BaseSourceHandler):
    label = "KSPCB"

    def lookup(self, station_id: str, raw_filename: str) -> SourceResult:
        url = "https://kspcb.karnataka.gov.in"
        return SourceResult(
            result="not_found",
            source_authority="KSPCB",
            source_url=url,
            evidence_note="KSPCB web portal does not expose a machine-readable station registry API. "
            "Manual verification via https://kspcb.karnataka.gov.in is required.",
        )


class OpenAQSourceHandler(BaseSourceHandler):
    label = "OpenAQ"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENAQ_API_KEY", "").strip()

    def lookup(self, station_id: str, raw_filename: str) -> SourceResult:
        if not self.api_key:
            return SourceResult(
                result="not_found",
                source_authority="OpenAQ",
                source_url="https://docs.openaq.org/docs/api-authentication",
                evidence_note="OpenAQ API key not configured. Set OPENAQ_API_KEY environment variable.",
            )
        parts = station_id.replace("cpcb_", "", 1).split("_")
        search_name = " ".join(parts).title()
        url = f"https://api.openaq.org/v3/locations?name={search_name}&limit=5"
        return SourceResult(
            result="not_found",
            source_authority="OpenAQ",
            source_url=url,
            evidence_note=f"OpenAQ lookup for '{search_name}' requires manual confirmation. "
            "Set OPENAQ_API_KEY and retry for automated search.",
        )


class GoogleMapsSourceHandler(BaseSourceHandler):
    label = "Google Maps"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_SERVER_API_KEY", "").strip()

    def lookup(self, station_id: str, raw_filename: str) -> SourceResult:
        if not self.api_key:
            return SourceResult(
                result="not_found",
                source_authority="Google Maps",
                source_url="https://console.cloud.google.com/apis/credentials",
                evidence_note="Google Maps API key not configured. "
                "Set GOOGLE_MAPS_SERVER_API_KEY environment variable.",
            )
        parts = station_id.replace("cpcb_", "", 1).split("_")
        display_name = " ".join(parts).title()
        query = f"{display_name} Bengaluru air quality monitoring station"
        try:
            from backend.app.services.google_maps_client import geocode_address
            result = geocode_address(query)
        except Exception as exc:
            return SourceResult(
                result="not_found",
                source_authority="Google Maps",
                source_url="",
                evidence_note=f"Google Maps lookup failed: {exc}",
            )
        if not result.get("success") or not result.get("data"):
            return SourceResult(
                result="not_found",
                source_authority="Google Maps",
                source_url="",
                evidence_note=f"Google Maps returned no results for '{query}'.",
            )
        data = result["data"]
        lat = data.get("latitude")
        lng = data.get("longitude")
        formatted = data.get("formatted_address", "")
        if lat is None or lng is None:
            return SourceResult(
                result="not_found",
                source_authority="Google Maps",
                source_url="",
                evidence_note="Google Maps returned coordinates but location is ambiguous.",
            )
        if not (BBOX["south"] <= lat <= BBOX["north"] and BBOX["west"] <= lng <= BBOX["east"]):
            return SourceResult(
                result="out_of_scope",
                latitude=lat,
                longitude=lng,
                source_authority="Google Maps",
                source_url="",
                evidence_note=f"Coordinates ({lat}, {lng}) outside Bengaluru bounding box.",
                rejection_reason="Coordinates outside Bengaluru bounding box",
            )
        # Check if result looks like a specific station or a broad locality
        lower = formatted.lower()
        if any(kw in lower for kw in ("air quality", "monitoring station", "cpcb", "kspcb", "pollution")):
            return SourceResult(
                result="found",
                latitude=lat,
                longitude=lng,
                display_name=display_name,
                source_authority="Google Maps",
                source_url="",
                evidence_note=f"Google Maps geocoded '{query}' to ({lat}, {lng}) — {formatted}",
            )
        return SourceResult(
            result="ambiguous",
            latitude=lat,
            longitude=lng,
            source_authority="Google Maps",
            source_url="",
            evidence_note=f"Google Maps result '{formatted}' is a broad locality, not a verified station.",
            rejection_reason="Broad locality result, not a verified monitoring station",
        )


def _build_source_handlers() -> list[BaseSourceHandler]:
    return [
        CPCBSourceHandler(),
        KSPCBSourceHandler(),
        OpenAQSourceHandler(),
        GoogleMapsSourceHandler(),
    ]


# ---------------------------------------------------------------------------
# Verification logic
# ---------------------------------------------------------------------------


def _check_bounding_box(lat: float, lng: float) -> str | None:
    if not (BBOX["south"] <= lat <= BBOX["north"]):
        return f"Latitude {lat} outside Bengaluru bounds ({BBOX['south']} to {BBOX['north']})"
    if not (BBOX["west"] <= lng <= BBOX["east"]):
        return f"Longitude {lng} outside Bengaluru bounds ({BBOX['west']} to {BBOX['east']})"
    return None


ConfidenceDecision = str  # "verified_exact" | "ambiguous" | "not_found" | "out_of_scope"


def verify_candidate(
    row: dict[str, Any],
    source_handlers: list[BaseSourceHandler] | None = None,
) -> tuple[ConfidenceDecision, dict[str, Any]]:
    sid = str(row.get("proposed_station_id", "")).strip()
    raw_filename = str(row.get("raw_filename", "")).strip()

    if raw_filename in EXCLUDED_FILES:
        return "out_of_scope", {
            "latitude_considered": None,
            "longitude_considered": None,
            "source_authority": "",
            "source_url": "",
            "evidence_note": "Explicitly excluded file (Jigani).",
            "rejection_reason": "Excluded file",
        }

    if source_handlers is None:
        source_handlers = _build_source_handlers()

    for handler in source_handlers:
        sr = handler.lookup(sid, raw_filename)
        if sr.result == "found":
            bbox_error = _check_bounding_box(sr.latitude, sr.longitude) if sr.latitude is not None and sr.longitude is not None else None
            if bbox_error:
                return "out_of_scope", {
                    "latitude_considered": sr.latitude,
                    "longitude_considered": sr.longitude,
                    "source_authority": sr.source_authority,
                    "source_url": sr.source_url or "",
                    "evidence_note": sr.evidence_note or "",
                    "rejection_reason": bbox_error,
                }
            return "verified_exact", {
                "latitude_considered": sr.latitude,
                "longitude_considered": sr.longitude,
                "source_authority": sr.source_authority,
                "source_url": sr.source_url or "",
                "evidence_note": sr.evidence_note or "",
                "rejection_reason": "",
            }
        if sr.result == "ambiguous":
            return "ambiguous", {
                "latitude_considered": sr.latitude,
                "longitude_considered": sr.longitude,
                "source_authority": sr.source_authority,
                "source_url": sr.source_url or "",
                "evidence_note": sr.evidence_note or "",
                "rejection_reason": sr.rejection_reason or "Ambiguous result",
            }
        if sr.result == "out_of_scope":
            return "out_of_scope", {
                "latitude_considered": sr.latitude,
                "longitude_considered": sr.longitude,
                "source_authority": sr.source_authority,
                "source_url": sr.source_url or "",
                "evidence_note": sr.evidence_note or "",
                "rejection_reason": sr.rejection_reason or "Out of scope",
            }

    return "not_found", {
        "latitude_considered": None,
        "longitude_considered": None,
        "source_authority": "",
        "source_url": "",
        "evidence_note": "No authoritative source returned a verified result.",
        "rejection_reason": "Not found in any authoritative source",
    }


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------


def _write_verification_report(records: list[dict[str, Any]]) -> None:
    reports_dir = REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir / "bengaluru_station_metadata_verification.csv"
    md_path = reports_dir / "bengaluru_station_metadata_verification.md"

    pd.DataFrame(records, columns=VERIFICATION_REPORT_COLUMNS).to_csv(csv_path, index=False)
    logger.info("Wrote CSV verification report: %s", csv_path)

    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Bengaluru Station Metadata Verification Report",
        "",
        f"**Generated:** {now}",
        f"**Candidates inspected:** {len(records)}",
        "",
        "## Results",
        "",
    ]
    decisions = [r["decision"] for r in records]
    lines.append(f"- **verified_exact:** {decisions.count('verified_exact')}")
    lines.append(f"- **ambiguous:** {decisions.count('ambiguous')}")
    lines.append(f"- **not_found:** {decisions.count('not_found')}")
    lines.append(f"- **out_of_scope:** {decisions.count('out_of_scope')}")
    lines.append("")
    lines.append("| ID | File | Decision | Lat | Lng | Authority | Rejection |")
    lines.append("|----|------|----------|-----|-----|-----------|-----------|")
    for r in records:
        lat_str = f"{r['latitude_considered']:.6f}" if r["latitude_considered"] is not None else ""
        lng_str = f"{r['longitude_considered']:.6f}" if r["longitude_considered"] is not None else ""
        rej = (r["rejection_reason"] or "").replace("|", "/")
        lines.append(
            f"| {r['proposed_station_id']} | {r['raw_filename']} | {r['decision']} "
            f"| {lat_str} | {lng_str} | {r['source_authority']} | {rej} |"
        )
    lines.append("")
    lines.append("## Detailed Evidence")
    lines.append("")
    for r in records:
        if r["evidence_note"]:
            lines.append(f"- **{r['proposed_station_id']}:** {r['evidence_note']}")
    lines.append("")
    lines.append("*Verification performed by pipeline.verify_bengaluru_station_metadata*")
    lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote Markdown verification report: %s", md_path)


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------


def run_verification(dry_run: bool = False) -> list[dict[str, Any]]:
    if not CANDIDATES_PATH.exists():
        raise FileNotFoundError(f"Candidates file not found: {CANDIDATES_PATH}")

    df = pd.read_csv(CANDIDATES_PATH)
    handlers = _build_source_handlers()
    records: list[dict[str, Any]] = []
    updated_rows: list[dict[str, Any]] = []

    print(f"\n{'ID':30s} {'Decision':16s} {'Authority':20s} {'Notes'}")
    print("-" * 100)

    for idx, row in df.iterrows():
        raw = str(row.get("raw_filename", "")).strip()
        sid = str(row.get("proposed_station_id", "")).strip()

        if raw in EXCLUDED_FILES:
            continue

        decision, info = verify_candidate(row.to_dict(), handlers)

        note = info["evidence_note"][:55] + "..." if len(info.get("evidence_note", "")) > 55 else info.get("evidence_note", "")
        auth = info.get("source_authority", "") or ""
        print(f"{sid:30s} {decision:16s} {auth:20s} {note}")

        records.append({
            "proposed_station_id": sid,
            "raw_filename": raw,
            "decision": decision,
            "latitude_considered": info.get("latitude_considered"),
            "longitude_considered": info.get("longitude_considered"),
            "source_authority": auth,
            "source_url": info.get("source_url", ""),
            "evidence_note": info.get("evidence_note", ""),
            "rejection_reason": info.get("rejection_reason", ""),
        })

        if decision == "verified_exact":
            updated_rows.append({
                "raw_filename": raw,
                "proposed_station_id": sid,
                "display_name": info.get("display_name", ""),
                "city": str(row.get("city", "bengaluru")),
                "latitude": str(info["latitude_considered"]),
                "longitude": str(info["longitude_considered"]),
                "source_authority": auth,
                "metadata_verification_status": "verified",
                "geospatial_eligible": str(row.get("geospatial_eligible", "True")),
                "onboarding_status": str(row.get("onboarding_status", "pending")),
                "notes": info.get("evidence_note", ""),
                "metadata_source_url": info.get("source_url", ""),
            })
        elif decision == "ambiguous":
            updated_rows.append({
                "raw_filename": raw,
                "proposed_station_id": sid,
                "display_name": str(row.get("display_name", "")),
                "city": str(row.get("city", "bengaluru")),
                "latitude": str(info.get("latitude_considered", "") or ""),
                "longitude": str(info.get("longitude_considered", "") or ""),
                "source_authority": auth,
                "metadata_verification_status": "pending_verification",
                "geospatial_eligible": str(row.get("geospatial_eligible", "True")),
                "onboarding_status": str(row.get("onboarding_status", "pending")),
                "notes": info.get("evidence_note", ""),
                "metadata_source_url": info.get("source_url", ""),
            })
        else:
            updated_rows.append({
                "raw_filename": raw,
                "proposed_station_id": sid,
                "display_name": str(row.get("display_name", "")),
                "city": str(row.get("city", "bengaluru")),
                "latitude": str(row.get("latitude", "")),
                "longitude": str(row.get("longitude", "")),
                "source_authority": auth,
                "metadata_verification_status": "pending_verification",
                "geospatial_eligible": str(row.get("geospatial_eligible", "True")),
                "onboarding_status": str(row.get("onboarding_status", "pending")),
                "notes": info.get("evidence_note", ""),
                "metadata_source_url": info.get("source_url", ""),
            })

    print()
    print(f"verified_exact: {sum(1 for r in records if r['decision'] == 'verified_exact')}")
    print(f"ambiguous:      {sum(1 for r in records if r['decision'] == 'ambiguous')}")
    print(f"not_found:      {sum(1 for r in records if r['decision'] == 'not_found')}")
    print(f"out_of_scope:   {sum(1 for r in records if r['decision'] == 'out_of_scope')}")

    # Write reports (both dry-run and apply)
    _write_verification_report(records)

    if dry_run:
        print("\n[Dry run] No changes written to candidates file.")
        return records

    # Apply: write updated candidates CSV
    updated_df = pd.DataFrame(updated_rows)
    updated_df.to_csv(CANDIDATES_PATH, index=False)
    logger.info("Updated candidates file: %s", CANDIDATES_PATH)
    print(f"\n[Apply] Updated {len(updated_rows)} row(s) in candidates CSV.")
    print(f"  - {sum(1 for r in records if r['decision'] == 'verified_exact')} set to verified_exact")
    print(f"  - {sum(1 for r in records if r['decision'] in ('ambiguous', 'not_found', 'out_of_scope'))} left as pending_verification")

    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify candidate station metadata from authoritative sources."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview verification without modifying the candidates file.")
    parser.add_argument("--apply", action="store_true", help="Apply updates to candidates CSV for verified_exact results.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.apply and not args.dry_run:
        print("Specify --dry-run to preview or --apply to execute.")
        return

    run_verification(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
