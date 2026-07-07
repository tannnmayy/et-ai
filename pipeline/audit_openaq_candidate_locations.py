from __future__ import annotations

import argparse
import json
import logging
import os
import re
from glob import glob
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import BENGALURU_BOUNDING_BOX, get_project_root

logger = logging.getLogger(__name__)

PROJECT_ROOT = get_project_root()
CANDIDATES_PATH = PROJECT_ROOT / "data" / "reference" / "bengaluru_station_candidates.csv"
LOCATIONS_CSV = PROJECT_ROOT / "data" / "reports" / "openaq_bengaluru_locations.csv"
RAW_OPENAQ_DIR = PROJECT_ROOT / "data" / "raw" / "openaq"
BBOX = BENGALURU_BOUNDING_BOX

EXCLUDED_FILES: set[str] = {"jigani_bengaluru_kspcb_15m.csv"}

# Generic stop-words filtered from token matching to avoid spurious overlaps
_STOP_WORDS: set[str] = {
    "station", "stations", "bengaluru", "bangalore", "karnataka", "india",
    "monitoring", "air", "quality", "environmental",
    "cpcb", "kspcb", "cp",
}

REPORT_COLUMNS = [
    "proposed_station_id",
    "raw_filename",
    "aliases_searched",
    "matched_location_id",
    "matched_location_name",
    "latitude",
    "longitude",
    "openaq_source_authority",
    "available_parameters",
    "openaq_pm25_observed",
    "confidence",
    "evidence_note",
]


# ---------------------------------------------------------------------------
# Cache loading: CSV (preferred), JSON cache, live API (only if explicitly allowed)
# ---------------------------------------------------------------------------


def _detect_provider_from_name(name: str) -> str:
    lower = name.lower()
    if "cpcb" in lower and "kspcb" not in lower:
        return "CPCB"
    if "kspcb" in lower:
        return "KSPCB"
    return ""


def _load_locations_from_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        lid = row.get("location_id")
        name = str(row.get("location_name", "")).strip()
        lat = _safe_float(row.get("latitude"))
        lng = _safe_float(row.get("longitude"))
        locality = row.get("locality")
        if lid is None or not name or lat is None or lng is None:
            continue
        provider = _detect_provider_from_name(name)
        records.append({
            "location_id": int(lid),
            "location_name": name,
            "latitude": lat,
            "longitude": lng,
            "locality": str(locality) if pd.notna(locality) else None,
            "source_provider": provider,
            "sensor_parameters": [],
            "cache_source": "csv",
        })
    return records


def _load_locations_from_json_cache(glob_pattern: str) -> list[dict[str, Any]]:
    files = sorted(glob(glob_pattern))
    if not files:
        return []
    records: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for path_str in files:
        try:
            payload = json.loads(Path(path_str).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Skipping unreadable JSON cache: %s", path_str)
            continue

        items = _extract_location_results(payload)
        if not items:
            continue

        for item in items:
            record = _normalize_json_location_record(item)
            if record is None:
                continue
            lid = record["location_id"]
            if lid in seen_ids:
                continue
            seen_ids.add(lid)
            records.append(record)
    return records


def _extract_location_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("results"), list):
        return payload["results"]
    meta = payload.get("meta")
    if isinstance(meta, dict):
        inner = meta.get("results")
        if isinstance(inner, list):
            return inner
    return []


def _normalize_json_location_record(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    lid = item.get("id")
    name = str(item.get("name") or "").strip()
    coords = item.get("coordinates") or {}
    lat = _safe_float(coords.get("latitude"))
    lng = _safe_float(coords.get("longitude"))
    if lid is None or not name or lat is None or lng is None:
        return None

    provider = item.get("provider") or {}
    provider_name = provider.get("name") if isinstance(provider, dict) else ""

    sensors_raw = item.get("sensors") or []
    sensor_params: list[str] = []
    for s in sensors_raw:
        if not isinstance(s, dict):
            continue
        param = s.get("parameter") or {}
        param_name = param.get("name") if isinstance(param, dict) else s.get("name", "")
        if param_name:
            sensor_params.append(str(param_name).lower().strip())

    return {
        "location_id": int(lid),
        "location_name": name,
        "latitude": lat,
        "longitude": lng,
        "locality": str(item.get("locality") or "") if item.get("locality") else None,
        "source_provider": str(provider_name) if provider_name else "",
        "sensor_parameters": list(set(sensor_params)),
        "cache_source": "json",
    }


def _load_locations_from_live_api() -> list[dict[str, Any]]:
    api_key = (os.getenv("OPENAQ_API_KEY") or "").strip()
    if not api_key:
        logger.warning("OPENAQ_API_KEY not configured; cannot query live API.")
        return []
    try:
        from pipeline.openaq_client import OpenAQClient, OpenAQConfig, utc_run_timestamp
        from pipeline.audit_openaq_bengaluru import BoundingBox

        config = OpenAQConfig(api_key=api_key)
        client = OpenAQClient(config)
        bbox = BoundingBox()
        locations = client.get_locations_for_bbox(
            bbox.openaq_bbox(), utc_run_timestamp(), refresh=True
        )
        records: list[dict[str, Any]] = []
        for loc in locations:
            sensor_params = []
            try:
                sensors = client.get_sensors_for_location(
                    loc.location_id, utc_run_timestamp(), refresh=True
                )
                sensor_params = list({s.parameter for s in sensors})
            except Exception:
                pass
            records.append({
                "location_id": loc.location_id,
                "location_name": loc.name,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "locality": loc.locality,
                "source_provider": "",
                "sensor_parameters": sensor_params,
                "cache_source": "live_api",
            })
        return records
    except Exception as exc:
        logger.warning("Live OpenAQ API lookup failed: %s", exc)
        return []


def load_cached_locations(allow_live_api: bool = False) -> list[dict[str, Any]]:
    records = _load_locations_from_csv(LOCATIONS_CSV)
    if records:
        logger.info("Loaded %d locations from CSV cache: %s", len(records), LOCATIONS_CSV)
        return records

    json_pattern = str(RAW_OPENAQ_DIR / "locations_*.json")
    records = _load_locations_from_json_cache(json_pattern)
    if records:
        logger.info("Loaded %d locations from JSON cache: %s", len(records), json_pattern)
        return records

    if allow_live_api:
        logger.info("No local cache found; attempting live OpenAQ API lookup.")
        records = _load_locations_from_live_api()
        if records:
            logger.info("Loaded %d locations from live OpenAQ API.", len(records))
            return records
        logger.warning("Live API returned no results.")
    else:
        logger.info(
            "No local cache found and --allow-live-api not set. "
            "All candidates will be reported as not_found."
        )

    return []


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------


def _normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[-_,]", " ", name)
    name = re.sub(r"\s+", " ", name)
    for token in ["bengaluru", "bangalore"]:
        name = name.replace(token, "")
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _build_aliases(row: dict[str, Any]) -> list[str]:
    aliases: set[str] = set()
    sid = str(row.get("proposed_station_id", "")).strip()
    raw_fn = str(row.get("raw_filename", "")).strip()
    display = str(row.get("display_name", "")).strip()

    if sid:
        stem = sid.replace("cpcb_", "", 1)
        aliases.add(stem.replace("_", " "))
        aliases.add(stem.replace("_", ""))
        parts = stem.split("_")
        if len(parts) > 1:
            aliases.add(" ".join(parts))

    if raw_fn:
        stem = Path(raw_fn).stem
        tokens = [t for t in stem.split("_") if t.lower() not in ("bengaluru", "cpcb", "kspcb", "15m")]
        if tokens:
            aliases.add(" ".join(tokens))
            aliases.add("".join(tokens))

    if display:
        aliases.add(display.lower().strip())

    return sorted(a for a in aliases if a)


def _preferred_authority(raw_filename: str) -> str | None:
    lower = raw_filename.lower()
    if "cpcb" in lower and "kspcb" not in lower:
        return "CPCB"
    if "kspcb" in lower:
        return "KSPCB"
    return None


def _tokenize_for_match(text: str) -> set[str]:
    tokens = set(re.sub(r"[^a-z0-9]", " ", text.lower()).split())
    return tokens - _STOP_WORDS


def _within_bbox(lat: float, lng: float) -> bool:
    return (
        BBOX["south"] <= lat <= BBOX["north"]
        and BBOX["west"] <= lng <= BBOX["east"]
    )


def _sensor_has_pm25(sensor_params: list[str]) -> str:
    for p in sensor_params:
        if p in ("pm25", "pm2.5", "pm2,5"):
            return "true"
    if not sensor_params:
        return "unknown"
    return "false"


def match_candidate(
    row: dict[str, Any],
    locations: list[dict[str, Any]],
) -> dict[str, Any]:
    sid = str(row.get("proposed_station_id", "")).strip()
    raw_fn = str(row.get("raw_filename", "")).strip()

    aliases = _build_aliases(row)
    preferred = _preferred_authority(raw_fn)
    alias_str = "; ".join(aliases)

    if raw_fn in EXCLUDED_FILES:
        return {
            "proposed_station_id": sid,
            "raw_filename": raw_fn,
            "aliases_searched": alias_str,
            "matched_location_id": None,
            "matched_location_name": "",
            "latitude": None,
            "longitude": None,
            "openaq_source_authority": "",
            "available_parameters": "",
            "openaq_pm25_observed": "unknown",
            "confidence": "not_found",
            "evidence_note": "Jigani is explicitly excluded from this audit.",
        }

    if not aliases:
        return {
            "proposed_station_id": sid,
            "raw_filename": raw_fn,
            "aliases_searched": "",
            "matched_location_id": None,
            "matched_location_name": "",
            "latitude": None,
            "longitude": None,
            "openaq_source_authority": "",
            "available_parameters": "",
            "openaq_pm25_observed": "unknown",
            "confidence": "not_found",
            "evidence_note": "No search aliases could be built from candidate row.",
        }

    candidates_tokens = set()
    for alias in aliases:
        candidates_tokens |= _tokenize_for_match(alias)
    if not candidates_tokens:
        return {
            "proposed_station_id": sid,
            "raw_filename": raw_fn,
            "aliases_searched": alias_str,
            "matched_location_id": None,
            "matched_location_name": "",
            "latitude": None,
            "longitude": None,
            "openaq_source_authority": "",
            "available_parameters": "",
            "openaq_pm25_observed": "unknown",
            "confidence": "not_found",
            "evidence_note": "No significant tokens for matching.",
        }

    scored: list[tuple[float, int, str, dict[str, Any]]] = []
    for loc in locations:
        loc_name = loc.get("location_name", "")
        raw_tokens = set(re.sub(r"[^a-z0-9]", " ", loc_name.lower()).split())
        loc_tokens = _tokenize_for_match(loc_name)
        if not loc_tokens:
            continue
        overlap = candidates_tokens & loc_tokens
        if not overlap:
            continue
        score = len(overlap) / max(len(loc_tokens), 1)
        provider = loc.get("source_provider", "")
        if preferred and preferred.lower() in provider.lower():
            score += 0.3
        # Tiebreaker: prefer locations with more raw tokens (more specific name)
        scored.append((score, -len(raw_tokens), loc_name, loc))

    if not scored:
        return {
            "proposed_station_id": sid,
            "raw_filename": raw_fn,
            "aliases_searched": alias_str,
            "matched_location_id": None,
            "matched_location_name": "",
            "latitude": None,
            "longitude": None,
            "openaq_source_authority": "",
            "available_parameters": "",
            "openaq_pm25_observed": "unknown",
            "confidence": "not_found",
            "evidence_note": "No OpenAQ location matched the search aliases.",
        }

    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    best_score, _, _, best_loc = scored[0]

    lat = best_loc.get("latitude")
    lng = best_loc.get("longitude")
    provider = best_loc.get("source_provider", "")
    sensor_params = best_loc.get("sensor_parameters", [])
    pm25 = _sensor_has_pm25(sensor_params)
    param_str = ", ".join(sorted(set(sensor_params))) if sensor_params else ""

    if not _within_bbox(lat, lng):
        return {
            "proposed_station_id": sid,
            "raw_filename": raw_fn,
            "aliases_searched": alias_str,
            "matched_location_id": best_loc["location_id"],
            "matched_location_name": best_loc["location_name"],
            "latitude": lat,
            "longitude": lng,
            "openaq_source_authority": provider,
            "available_parameters": param_str,
            "openaq_pm25_observed": pm25,
            "confidence": "ambiguous",
            "evidence_note": (
                f"Matched location_id={best_loc['location_id']} "
                f"({best_loc['location_name']}) but coordinates "
                f"({lat:.4f}, {lng:.4f}) are outside Bengaluru bounding box."
            ),
        }

    if best_score >= 0.5:
        return {
            "proposed_station_id": sid,
            "raw_filename": raw_fn,
            "aliases_searched": alias_str,
            "matched_location_id": best_loc["location_id"],
            "matched_location_name": best_loc["location_name"],
            "latitude": lat,
            "longitude": lng,
            "openaq_source_authority": provider,
            "available_parameters": param_str,
            "openaq_pm25_observed": pm25,
            "confidence": "verified_exact",
            "evidence_note": (
                f"Strong match with OpenAQ location_id={best_loc['location_id']} "
                f"('{best_loc['location_name']}'). "
                f"Coordinates ({lat:.4f}, {lng:.4f}) within Bengaluru bounds. "
                f"Source: {provider or 'unspecified'}. "
                f"PM2.5 observed: {pm25}."
            ),
        }

    return {
        "proposed_station_id": sid,
        "raw_filename": raw_fn,
        "aliases_searched": alias_str,
        "matched_location_id": best_loc["location_id"],
        "matched_location_name": best_loc["location_name"],
        "latitude": lat,
        "longitude": lng,
        "openaq_source_authority": provider,
        "available_parameters": param_str,
        "openaq_pm25_observed": pm25,
        "confidence": "ambiguous",
        "evidence_note": (
            f"Weak partial match with OpenAQ location_id={best_loc['location_id']} "
            f"('{best_loc['location_name']}'). "
            f"Token overlap score {best_score:.2f} below 0.5 threshold."
        ),
    }


# ---------------------------------------------------------------------------
# Reporting and CLI
# ---------------------------------------------------------------------------


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        import math
        if math.isnan(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def run_audit(dry_run: bool = True, allow_live_api: bool = False) -> list[dict[str, Any]]:
    if not CANDIDATES_PATH.exists():
        raise FileNotFoundError(f"Candidates file not found: {CANDIDATES_PATH}")

    df = pd.read_csv(CANDIDATES_PATH)
    locations = load_cached_locations(allow_live_api=allow_live_api)

    if not locations:
        logger.warning("No OpenAQ location data available (offline and no cache found).")

    location_count = len(locations)
    rows: list[dict[str, Any]] = []

    print()
    header = (
        f"{'ID':30s} {'Confidence':16s} {'Location ID':>12s} {'Lat':>10s} {'Lng':>10s} "
        f"{'Authority':12s} {'PM2.5':8s} Notes"
    )
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for _, cand in df.iterrows():
        raw_fn = str(cand.get("raw_filename", "")).strip()
        sid = str(cand.get("proposed_station_id", "")).strip()

        if raw_fn in EXCLUDED_FILES:
            continue

        result = match_candidate(cand.to_dict(), locations)
        rows.append(result)

        lat_s = f"{result['latitude']:.4f}" if result["latitude"] is not None else "N/A"
        lng_s = f"{result['longitude']:.4f}" if result["longitude"] is not None else "N/A"
        lid_s = str(result["matched_location_id"]) if result["matched_location_id"] is not None else "N/A"
        pm25_s = result["openaq_pm25_observed"]
        auth_s = (result["openaq_source_authority"] or "N/A")[:10]
        note = (result["evidence_note"][:55] + "...") if len(result["evidence_note"]) > 55 else result["evidence_note"]
        print(
            f"{sid:30s} {result['confidence']:16s} {lid_s:>12s} {lat_s:>10s} {lng_s:>10s} "
            f"{auth_s:12s} {pm25_s:8s} {note}"
        )

    print("=" * len(header))
    print()
    counts = {}
    for r in rows:
        counts[r["confidence"]] = counts.get(r["confidence"], 0) + 1
    print(f"Locations loaded: {location_count}")
    for conf in ("verified_exact", "ambiguous", "not_found"):
        print(f"  {conf}: {counts.get(conf, 0)}")
    print()

    if not dry_run:
        pass

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit pending candidate stations against cached OpenAQ location metadata."
    )
    parser.add_argument("--allow-live-api", action="store_true",
                        help="Permit a live OpenAQ API call if no local cache is available.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    run_audit(dry_run=True, allow_live_api=args.allow_live_api)


if __name__ == "__main__":
    main()
