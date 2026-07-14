"""Build per-locality, per-BHK median rent cache from MagicBricks listings.

Aggregation rules (Document 11 / Citizen Mode rent plan):
  - Median rent (not mean) per canonical locality × BHK bucket.
  - BHK buckets: "0", "1", "2", "3", "4", "5+" (6 and above, including "> 10").
  - is_estimated=false only when listing count for that (locality, BHK) >= 5.
  - Below the threshold, fall back to citywide median for that BHK bucket and
    set is_estimated=true. If the citywide bucket is also empty, fall back to
    the locality's overall median (still is_estimated=true).

Output: pipeline/reference/locality_rent_cache.json

Run:
    python -m pipeline.build_locality_rent_cache
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.config import get_project_root
from pipeline.build_locality_registry import canonicalize_locality

logger = logging.getLogger(__name__)

MIN_BHK_COUNT_FOR_DIRECT = 5
BHK_BUCKETS = ("0", "1", "2", "3", "4", "5+")


def bhk_to_bucket(raw: Any) -> str | None:
    """Map a raw BHK value to a cache bucket key, or None if unusable."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip().lower()
    if not text or text in {"nan", "none", "null", "na", "n/a", "?"}:
        return None

    # "> 10", "10+", etc. fold into the open-ended top bucket.
    if text.startswith(">") or text.endswith("+"):
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits and int(digits) >= 5:
            return "5+"
        if digits:
            return digits if digits in BHK_BUCKETS else ("5+" if int(digits) >= 5 else None)

    try:
        # Handles "3", "3.0", "3 BHK"
        num_str = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in text).split()
        if not num_str:
            return None
        value = float(num_str[0])
    except (ValueError, IndexError):
        return None

    if value < 0:
        return None
    if value >= 5:
        return "5+"
    # 0 studio / 1-4 standard
    return str(int(value))


def _median_rent(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    clean = clean[clean > 0]
    if clean.empty:
        return None
    return float(np.median(clean.to_numpy()))


def build_locality_rent_cache(
    rentals_path: Path | None = None,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    root = get_project_root()
    if rentals_path is None:
        rentals_path = root / "rent_dataset_generator" / "output" / "rentals.csv"
    if registry_path is None:
        registry_path = root / "pipeline" / "reference" / "locality_registry.json"

    with registry_path.open("r", encoding="utf-8") as f:
        registry = json.load(f)
    registry_names = {entry["name"] for entry in registry}

    df = pd.read_csv(rentals_path)
    df = df.copy()
    df["canonical_locality"] = df["locality"].map(canonicalize_locality)
    df["bhk_bucket"] = df["bhk"].map(bhk_to_bucket)
    df["rent_num"] = pd.to_numeric(df["rent"], errors="coerce")

    usable = df[
        df["canonical_locality"].isin(registry_names)
        & df["bhk_bucket"].notna()
        & df["rent_num"].notna()
        & (df["rent_num"] > 0)
    ].copy()

    # Citywide fallbacks per BHK bucket
    citywide_by_bhk: dict[str, dict[str, Any]] = {}
    for bucket in BHK_BUCKETS:
        subset = usable[usable["bhk_bucket"] == bucket]["rent_num"]
        med = _median_rent(subset)
        citywide_by_bhk[bucket] = {
            "median_rent": None if med is None else int(round(med)),
            "count": int(len(subset)),
        }

    citywide_overall = _median_rent(usable["rent_num"])
    citywide_overall_rent = None if citywide_overall is None else int(round(citywide_overall))

    localities_out: dict[str, Any] = {}
    for name in sorted(registry_names):
        group = usable[usable["canonical_locality"] == name]
        overall_med = _median_rent(group["rent_num"])
        by_bhk: dict[str, Any] = {}

        for bucket in BHK_BUCKETS:
            bucket_rents = group[group["bhk_bucket"] == bucket]["rent_num"]
            count = int(len(bucket_rents))
            direct_med = _median_rent(bucket_rents)

            if count >= MIN_BHK_COUNT_FOR_DIRECT and direct_med is not None:
                by_bhk[bucket] = {
                    "median_rent": int(round(direct_med)),
                    "count": count,
                    "is_estimated": False,
                    "source": "locality_bhk_median",
                }
            else:
                # Prefer citywide same-BHK median; else locality overall median.
                fallback = citywide_by_bhk[bucket]["median_rent"]
                source = "citywide_bhk_median"
                if fallback is None:
                    fallback = None if overall_med is None else int(round(overall_med))
                    source = "locality_overall_median"
                if fallback is None:
                    fallback = citywide_overall_rent
                    source = "citywide_overall_median"

                by_bhk[bucket] = {
                    "median_rent": fallback,
                    "count": count,
                    "is_estimated": True,
                    "source": source,
                }

        localities_out[name] = {
            "by_bhk": by_bhk,
            "overall_median_rent": None if overall_med is None else int(round(overall_med)),
            "overall_count": int(len(group)),
        }

    return {
        "schema_version": 1,
        "min_count_for_direct_estimate": MIN_BHK_COUNT_FOR_DIRECT,
        "bhk_buckets": list(BHK_BUCKETS),
        "citywide": {
            "by_bhk": citywide_by_bhk,
            "overall_median_rent": citywide_overall_rent,
            "overall_count": int(len(usable)),
        },
        "localities": localities_out,
    }


def write_locality_rent_cache(
    output_path: Path | None = None,
    rentals_path: Path | None = None,
    registry_path: Path | None = None,
) -> Path:
    root = get_project_root()
    if output_path is None:
        output_path = root / "pipeline" / "reference" / "locality_rent_cache.json"

    cache = build_locality_rent_cache(rentals_path=rentals_path, registry_path=registry_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
        f.write("\n")
    logger.info("Wrote rent cache for %d localities to %s", len(cache["localities"]), output_path)
    return output_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = write_locality_rent_cache()
    print(f"Wrote locality rent cache -> {path}")


if __name__ == "__main__":
    main()
