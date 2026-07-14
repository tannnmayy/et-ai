"""Build the canonical locality registry from MagicBricks rental listings.

Reads rent_dataset_generator/output/rentals.csv, collapses raw locality strings
into a curated set of canonical names, keeps localities with >= 25 listings,
and writes median-centroid coordinates to pipeline/reference/locality_registry.json.

Run:
    python -m pipeline.build_locality_registry
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import get_project_root

logger = logging.getLogger(__name__)

MIN_LISTING_COUNT = 25

# ---------------------------------------------------------------------------
# Canonical name -> substring patterns (case-insensitive match against raw
# locality strings). Patterns are checked in definition order; the first
# match wins, so more-specific patterns should appear before broader ones
# that share tokens (e.g. "BTM Layout Stage 2" before "BTM").
#
# Covers at least the top ~50 raw locality strings by count, plus common
# variants that fold into the same neighbourhood. "Unknown" and clearly
# invalid values are NOT listed here — canonicalize_locality() returns None
# for those and such rows are dropped entirely.
# ---------------------------------------------------------------------------
LOCALITY_CANONICALIZATION: dict[str, list[str]] = {
    # East corridor
    "Whitefield": ["whitefield"],
    "Sarjapur Road": ["sarjapur road", "sarjapur rd"],
    "Sarjapur": ["sarjapur"],
    "Varthur": ["varthur"],
    "Marathahalli": ["marathahalli"],
    "Bellandur": ["bellandur"],
    "Electronic City": ["electronic city", "e-city", "ecity"],
    "Haralur": ["haralur"],
    "KR Puram": ["kr puram", "krishnarajapura", "k r puram"],
    "Panathur": ["panathur"],
    "Mahadevapura": ["mahadevapura"],
    "Hoodi": ["hoodi"],
    "Kadugodi": ["kadugodi"],
    "Kasavanahalli": ["kasavanahalli"],
    "Hosa Road": ["hosa road"],
    "Kundalahalli": ["kundalahalli"],
    "Kadubeesanahalli": ["kadubeesanahalli", "kadabesanahalli"],
    "Doddanekundi": ["doddanekundi"],
    "Brookefield": ["brookefield", "brookfield"],
    "EPIP Zone": ["epip"],
    "Yemalur": ["yemalur"],
    "Seegehalli": ["seegehalli"],
    "Choodasandra": ["choodasandra"],
    "Budigere Cross": ["budigere"],
    # North
    "Hebbal": ["hebbal"],
    "Thanisandra": ["thanisandra"],
    "Yelahanka": ["yelahanka"],
    "Devanahalli": ["devanahalli"],
    "Horamavu": ["horamavu"],
    "Hennur": ["hennur"],
    "Ramamurthy Nagar": ["ramamurthy nagar", "ramamurthynagar", "rm nagar"],
    "Sahakar Nagar": ["sahakar nagar", "sahakara nagar"],
    "RT Nagar": ["rt nagar", "r.t. nagar", "r t nagar"],
    "Manyata Tech Park": ["manyata"],
    "Jakkur": ["jakkur"],
    "Nagarbhavi": ["nagarbhavi"],  # west-ish but listed in top
    # Central / core
    "Koramangala": ["koramangala"],
    "HSR Layout": ["hsr layout", "hsr extension", "hsr"],
    "Indiranagar": ["indiranagar", "indirangar"],
    "Jayanagar": ["jayanagar", "jayanagara"],
    "JP Nagar": ["jp nagar", "j.p. nagar", "j p nagar"],
    "BTM Layout": ["btm layout", "btm"],
    "Domlur": ["domlur"],
    "Ulsoor": ["ulsoor", "halasuru"],
    "Richmond Town": ["richmond town", "richmond"],
    "Malleshwaram": ["malleshwaram", "malleswaram"],
    "Rajajinagar": ["rajajinagar", "rajaji nagar"],
    "Basavanagudi": ["basavanagudi"],
    "CV Raman Nagar": ["cv raman", "c.v. raman", "c v raman"],
    "Frazer Town": ["frazer town", "fraser town"],
    "Ejipura": ["ejipura"],
    "Kammanahalli": ["kammanahalli"],
    "Banaswadi": ["banaswadi"],
    "Vijayanagar": ["vijayanagar", "vijayanagara"],
    # South
    "Bannerghatta Road": ["bannerghatta road", "bannerghatta rd"],
    "Bommanahalli": ["bommanahalli"],
    "Hulimavu": ["hulimavu"],
    "Gottigere": ["gottigere"],
    "Begur": ["begur"],
    "Arekere": ["arekere"],
    "Singasandra": ["singasandra"],
    "Banashankari": ["banashankari", "banashankri"],
    "Kumaraswamy Layout": ["kumaraswamy"],
    "Jigani": ["jigani"],
    "Chandapura": ["chandapura"],
    "Neeladri Nagar": ["neeladri"],
    # West
    "Kengeri": ["kengeri"],
    "RR Nagar": ["rr nagar", "r.r. nagar", "rajarajeshwari", "rajarajeshwari nagar"],
    "Mysore Road": ["mysore road", "mysuru road"],
    "Tumkur Road": ["tumkur road", "tumakuru road"],
    "Kanakapura Road": ["kanakapura road", "kanakapura rd"],
    "Old Madras Road": ["old madras road", "omr bengaluru"],
}


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation noise."""
    t = str(text).strip().lower()
    t = re.sub(r"[\.,\-_'/]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# Precompute (canonical, normalized_pattern) pairs once. Longer patterns first
# so "sarjapur road" wins over "sarjapur" when both could match.
_PATTERN_PAIRS: list[tuple[str, str]] = []
for _canonical, _patterns in LOCALITY_CANONICALIZATION.items():
    for _p in _patterns:
        _PATTERN_PAIRS.append((_canonical, _normalize(_p)))
_PATTERN_PAIRS.sort(key=lambda pair: len(pair[1]), reverse=True)


_INVALID_EXACT = frozenset({
    "",
    "unknown",
    "na",
    "n/a",
    "none",
    "null",
    "nan",
    "other",
    "not available",
    "bengaluru",
    "bangalore",
    "bangalore urban",
    "karnataka",
    "india",
})


def canonicalize_locality(raw: Any) -> str | None:
    """Map a raw listing locality string to a canonical name, or None if invalid.

    Returns None for Unknown / empty / non-Bengaluru-area junk — callers must
    drop those rows rather than guessing.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    normalized = _normalize(raw)
    if not normalized or normalized in _INVALID_EXACT:
        return None

    for canonical, pattern in _PATTERN_PAIRS:
        if pattern in normalized:
            return canonical
    return None


def build_locality_registry(
    rentals_path: Path | None = None,
    min_listing_count: int = MIN_LISTING_COUNT,
) -> list[dict[str, Any]]:
    root = get_project_root()
    if rentals_path is None:
        rentals_path = root / "rent_dataset_generator" / "output" / "rentals.csv"

    df = pd.read_csv(rentals_path)
    if "locality" not in df.columns:
        raise ValueError(f"rentals.csv missing 'locality' column: {rentals_path}")

    df = df.copy()
    df["canonical_locality"] = df["locality"].map(canonicalize_locality)
    mapped = df[df["canonical_locality"].notna()].copy()
    logger.info(
        "Canonicalized %d / %d listings (%d dropped as unmapped/invalid)",
        len(mapped),
        len(df),
        len(df) - len(mapped),
    )

    registry: list[dict[str, Any]] = []
    for name, group in mapped.groupby("canonical_locality"):
        count = int(len(group))
        if count < min_listing_count:
            continue

        coords = group[["latitude", "longitude"]].dropna()
        if coords.empty:
            logger.warning("Skipping %s — no lat/lon among %d listings", name, count)
            continue

        registry.append({
            "name": str(name),
            "centroid_lat": round(float(coords["latitude"].median()), 6),
            "centroid_lon": round(float(coords["longitude"].median()), 6),
            "listing_count": count,
        })

    registry.sort(key=lambda r: (-r["listing_count"], r["name"]))
    logger.info("Registry: %d localities with >= %d listings", len(registry), min_listing_count)
    return registry


def write_locality_registry(
    output_path: Path | None = None,
    rentals_path: Path | None = None,
) -> Path:
    root = get_project_root()
    if output_path is None:
        output_path = root / "pipeline" / "reference" / "locality_registry.json"

    registry = build_locality_registry(rentals_path=rentals_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
        f.write("\n")
    logger.info("Wrote %d localities to %s", len(registry), output_path)
    return output_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = write_locality_registry()
    print(f"Wrote locality registry -> {path}")


if __name__ == "__main__":
    main()
