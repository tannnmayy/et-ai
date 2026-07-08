from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from backend.app.config import SUPPORTED_CITIES, get_project_root, HEXAGON_FEATURES_PATH
from backend.app.services.attribution_service import get_city_grid_attribution

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Actionability weights per source category
#
# These are judgment calls documented for review:
#
#   industrial (1.0) — Permitted facilities with known locations; direct
#       inspection and enforcement action (e.g. consent orders, closure
#       notices) is possible. High actionability.
#
#   construction (1.0) — Sites require permits and are inspectable;
#       stop-work orders and dust-control mandates can be issued. High
#       actionability.
#
#   burning (1.0) — Illegal burning can be directly enforced against
#       when located. High actionability.
#
#   traffic (0.2) — Diffuse, area-wide source attributable to a fleet
#       of vehicles rather than a single inspectable entity. Low
#       actionability — enforcement relies on systemic measures
#       (e.g. vehicle emissions standards, fuel policy) rather than
#       site-level action.
# ---------------------------------------------------------------------------
ACTIONABILITY_INDUSTRIAL: float = 1.0
ACTIONABILITY_CONSTRUCTION: float = 1.0
ACTIONABILITY_BURNING: float = 1.0
ACTIONABILITY_TRAFFIC: float = 0.2

_ACTIONABILITY_MAP: dict[str, float] = {
    "industrial": ACTIONABILITY_INDUSTRIAL,
    "construction": ACTIONABILITY_CONSTRUCTION,
    "burning": ACTIONABILITY_BURNING,
    "traffic": ACTIONABILITY_TRAFFIC,
}

_ENFORCEABLE_CATEGORIES = ["industrial", "construction", "burning"]

# Number of vulnerability features (hospitals, schools, etc.) per hexagon
# that saturates the exposure weight to 1.0.
EXPOSURE_WEIGHT_SATURATION_COUNT: float = 3.0

# PM2.5 value (µg/m³) that saturates attributable magnitude to 1.0.
MAGNITUDE_SATURATION_PM25: float = 300.0


def _load_hexagon_features() -> pd.DataFrame:
    if "features" in getattr(_load_hexagon_features, "_cache", {}):
        return _load_hexagon_features._cache["features"]

    root = get_project_root()
    path = root / HEXAGON_FEATURES_PATH
    if not path.exists():
        logger.warning("Hexagon features not found at %s", path)
        df = pd.DataFrame()
    else:
        df = pd.read_parquet(str(path))
        logger.info("Loaded %d hexagon features", len(df))

    if not hasattr(_load_hexagon_features, "_cache"):
        _load_hexagon_features._cache = {}
    _load_hexagon_features._cache["features"] = df
    return df


def _compute_exposure_weight(hex_row: pd.Series | None) -> float:
    if hex_row is None:
        return 0.5

    vuln_count = float(hex_row.get("vulnerability_feature_count", 0))
    if pd.isna(vuln_count):
        vuln_count = 0.0

    # Residential density as a secondary proxy when vulnerability features are sparse
    residential_frac = float(hex_row.get("residential_fraction", 0))
    if pd.isna(residential_frac):
        residential_frac = 0.0

    vuln_exposure = min(1.0, vuln_count / EXPOSURE_WEIGHT_SATURATION_COUNT)
    res_exposure = min(1.0, residential_frac / 0.5)

    # Combine: vulnerability features dominate when present, residential fraction
    # provides a baseline everywhere
    return min(1.0, vuln_exposure * 0.7 + res_exposure * 0.3)


def _compute_attributable_magnitude(
    fused_pm25: float | None,
    source_attribution: dict[str, float],
) -> float:
    if fused_pm25 is None:
        return 0.0

    enforceable_frac = sum(
        source_attribution.get(cat, 0.0) for cat in _ENFORCEABLE_CATEGORIES
    )
    magnitude = fused_pm25 * enforceable_frac
    return min(1.0, magnitude / MAGNITUDE_SATURATION_PM25)


def _compute_actionability_weight(source_attribution: dict[str, float]) -> float:
    total = sum(source_attribution.get(cat, 0.0) for cat in _ACTIONABILITY_MAP)
    if total <= 0:
        return 0.0

    weighted = sum(
        source_attribution.get(cat, 0.0) * weight
        for cat, weight in _ACTIONABILITY_MAP.items()
    )
    return weighted / total


def compute_enforcement_priorities(
    city: str = "bengaluru",
    top_k: int = 10,
) -> dict[str, Any]:
    if city not in SUPPORTED_CITIES:
        return {"error": f"Unsupported city: '{city}'"}

    hex_df = _load_hexagon_features()
    grid_data = get_city_grid_attribution(city, include_fusion=True)

    if "error" in grid_data:
        return grid_data

    computed_at = datetime.now(tz=timezone.utc).isoformat()

    ranked: list[dict[str, Any]] = []
    for hex_result in grid_data.get("hexagons", []):
        h3 = hex_result["h3_cell"]

        hex_row = None
        if not hex_df.empty:
            match = hex_df[hex_df["h3_cell"] == h3]
            if not match.empty:
                hex_row = match.iloc[0]

        exposure_weight = _compute_exposure_weight(hex_row)
        attributable_magnitude = _compute_attributable_magnitude(
            hex_result.get("fused_pm25"),
            hex_result["source_attribution"],
        )
        actionability_weight = _compute_actionability_weight(
            hex_result["source_attribution"]
        )

        priority_score = exposure_weight * attributable_magnitude * actionability_weight

        ranked.append({
            "h3_cell": h3,
            "priority_score": round(priority_score, 4),
            "scoring_breakdown": {
                "exposure_weight": round(exposure_weight, 4),
                "attributable_magnitude": round(attributable_magnitude, 4),
                "actionability_weight": round(actionability_weight, 4),
            },
            "fused_pm25": hex_result.get("fused_pm25"),
            "source_attribution": hex_result["source_attribution"],
            "method": hex_result.get("method", "unavailable"),
        })

    ranked.sort(key=lambda x: (-x["priority_score"], x["h3_cell"]))
    for i, item in enumerate(ranked, start=1):
        item["rank"] = i

    return {
        "city": SUPPORTED_CITIES.get(city, {}).get("display_name", city.title()),
        "computed_at": computed_at,
        "total_hexagons": len(ranked),
        "top_k": min(top_k, len(ranked)),
        "ranked_hexagons": ranked[:top_k],
    }
