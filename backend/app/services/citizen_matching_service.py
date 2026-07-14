"""Citizen Mode neighbourhood matching engine.

Loads pre-built locality_feature_vectors.json once, then scores localities
against a CitizenProfile with a transparent weighted sum.

Architecture (offline cache + fast online refinements):
  - Rent / parks / noise / construction / metro / hospital / school scores
    come from the offline feature vectors (no CSV or hex re-aggregation).
  - AQI: optional live overlay via estimate_fused_pm25 + precomputed
    catchment_hex_ids (falls back to offline snapshot on failure).
  - Commute (hybrid):
      1) Haversine × BENGALURU_EFFECTIVE_SPEED_KMH pre-filter + score all
         localities (cheap).
      2) Take a shortlist larger than top_n (ROUTES_SHORTLIST_SIZE).
      3) Refine those with compute_commute_burden() (Google Routes) when the
         API key is configured; drop any that exceed maxCommuteMinutes on
         real travel time; re-score and re-rank.
      4) If Routes is unavailable, keep the proxy times honestly
         (commute still returned — it is an estimate).

Weight design (documented for review — same style as ACTIONABILITY_* in
enforcement_priority_service.py):

  BASE_WEIGHTS — default mix when the user lists no priorities:
    rent_fit   0.30  — must fit budget; primary constraint for renters
    aqi        0.25  — core product differentiator (air quality)
    commute    0.25  — hard lifestyle constraint alongside rent
    parks      0.05  — livability default
    hospitals  0.05
    schools    0.05
    noise      0.05  — lower = better (inverted at scoring time)
    metro      0.00  — off by default; boost when user prioritises metro

  PRIORITY_BOOST — added then weights re-normalised to sum to 1.0:
    low_aqi / schools / hospitals / parks / low_noise / metro

  Health conditions (respiratory / elderly / young_children) each add
  +0.05 to aqi before renormalisation.
"""

from __future__ import annotations

import json
import logging
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.config import get_project_root
from backend.app.schemas.citizen import (
    CitizenProfile,
    NeighbourhoodFeatureVector,
    NeighbourhoodMatch,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring configuration
# ---------------------------------------------------------------------------

BASE_WEIGHTS: dict[str, float] = {
    "rent_fit": 0.30,
    "aqi": 0.25,
    "commute": 0.25,
    "parks": 0.05,
    "hospitals": 0.05,
    "schools": 0.05,
    "noise": 0.05,
    "metro": 0.00,
}

PRIORITY_BOOST: dict[str, tuple[str, float]] = {
    "low_aqi": ("aqi", 0.20),
    "schools": ("schools", 0.15),
    "hospitals": ("hospitals", 0.15),
    "parks": ("parks", 0.15),
    "low_noise": ("noise", 0.15),
    "metro": ("metro", 0.15),
}

HEALTH_AQI_BOOST: float = 0.05

# Effective citywide drive speed for the commute *proxy* (Bengaluru peak-ish).
BENGALURU_EFFECTIVE_SPEED_KMH: float = 18.0

# Soft slack on the proxy pre-filter so borderline localities still reach
# the Google Routes shortlist (proxy can overestimate or underestimate).
PROXY_COMMUTE_SLACK: float = 1.25

RENT_OVER_BUDGET_ZERO_RATIO: float = 1.50
AQI_SCORE_ZERO_AT: float = 200.0

DEFAULT_TOP_N: int = 12
# How many proxy-survivors to refine with Google Routes before cutting to top_n.
ROUTES_SHORTLIST_SIZE: int = 20

_EARTH_RADIUS_KM = 6371.0
FEATURE_VECTORS_RELATIVE = "pipeline/reference/locality_feature_vectors.json"


# ---------------------------------------------------------------------------
# Feature-vector loading
# ---------------------------------------------------------------------------

_VECTORS_CACHE: list[dict[str, Any]] | None = None
_VECTORS_MTIME: float | None = None


def _feature_vectors_path() -> Path:
    return get_project_root() / FEATURE_VECTORS_RELATIVE


def load_locality_feature_vectors(*, force_reload: bool = False) -> list[dict[str, Any]]:
    global _VECTORS_CACHE, _VECTORS_MTIME

    path = _feature_vectors_path()
    if not path.exists():
        logger.error("Feature vectors not found at %s", path)
        return []

    mtime = path.stat().st_mtime
    if (
        not force_reload
        and _VECTORS_CACHE is not None
        and _VECTORS_MTIME is not None
        and mtime == _VECTORS_MTIME
    ):
        return _VECTORS_CACHE

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    vectors = payload.get("localities", payload if isinstance(payload, list) else [])
    _VECTORS_CACHE = vectors
    _VECTORS_MTIME = mtime
    logger.info("Loaded %d locality feature vectors from %s", len(vectors), path)
    return vectors


def clear_feature_vectors_cache() -> None:
    global _VECTORS_CACHE, _VECTORS_MTIME
    _VECTORS_CACHE = None
    _VECTORS_MTIME = None


# ---------------------------------------------------------------------------
# Geometry + commute proxy
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * asin(sqrt(a))


def estimate_commute_minutes(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    speed_kmh: float = BENGALURU_EFFECTIVE_SPEED_KMH,
) -> float:
    """Haversine distance / effective speed → one-way minutes (rounded)."""
    if speed_kmh <= 0:
        return float("inf")
    dist_km = _haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)
    return round((dist_km / speed_kmh) * 60.0, 1)


def _routes_commute_minutes(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> dict[str, Any]:
    """Call compute_commute_burden; return {available, minutes, source}.

    Does not invent a duration when the provider is down — available=False.
    """
    try:
        from backend.app.services.commute_service import compute_commute_burden

        result = compute_commute_burden(
            origin_lat=origin_lat,
            origin_lng=origin_lon,
            workplace_lat=dest_lat,
            workplace_lng=dest_lon,
            travel_mode="DRIVE",
        )
    except Exception as exc:
        logger.warning("compute_commute_burden failed: %s", exc)
        return {"available": False, "minutes": None, "source": "error", "error": str(exc)}

    if not result.get("commute_available"):
        return {
            "available": False,
            "minutes": None,
            "source": result.get("source_status", "unavailable"),
            "error": result.get("error"),
        }

    # Prefer workplace route duration when present.
    for route in result.get("routes") or []:
        if (
            route.get("destination_type") == "workplace"
            and route.get("success")
            and route.get("duration_seconds") is not None
        ):
            minutes = float(route["duration_seconds"]) / 60.0
            return {
                "available": True,
                "minutes": round(minutes, 1),
                "source": "google_routes",
            }

    # Fallback: any successful route
    for route in result.get("routes") or []:
        if route.get("success") and route.get("duration_seconds") is not None:
            minutes = float(route["duration_seconds"]) / 60.0
            return {
                "available": True,
                "minutes": round(minutes, 1),
                "source": "google_routes",
            }

    return {
        "available": False,
        "minutes": None,
        "source": "unavailable",
        "error": "No successful route duration in commute result",
    }


# ---------------------------------------------------------------------------
# Live AQI overlay
# ---------------------------------------------------------------------------

def _live_aqi_by_locality(
    localities: list[dict[str, Any]],
) -> dict[str, tuple[float | None, bool]]:
    """Re-fuse PM2.5 and average over each locality's catchment_hex_ids.

    Returns name -> (aqi, aqi_is_estimated). On any failure, returns {}.
    """
    try:
        from backend.app.services.attribution_service import _load_hexagon_features
        from backend.app.services.fusion_estimation_service import estimate_fused_pm25

        hex_df = _load_hexagon_features()
        if hex_df is None or hex_df.empty:
            return {}

        fused = estimate_fused_pm25(hex_df)
        cell_to_idx = {
            str(cell): i for i, cell in enumerate(hex_df["h3_cell"].astype(str).tolist())
        }
        citywide = float(np.nanmean(fused)) if np.isfinite(fused).any() else None

        out: dict[str, tuple[float | None, bool]] = {}
        for loc in localities:
            name = loc["name"]
            env = loc.get("environment") or {}
            hex_ids = env.get("catchment_hex_ids") or []
            if not hex_ids:
                # No catchment metadata — keep offline values (caller handles).
                continue
            vals = []
            for hid in hex_ids:
                idx = cell_to_idx.get(str(hid))
                if idx is None:
                    continue
                v = fused[idx]
                if np.isfinite(v):
                    vals.append(float(v))
            if vals:
                out[name] = (round(float(np.mean(vals)), 1), False)
            else:
                out[name] = (
                    None if citywide is None else round(citywide, 1),
                    True,
                )
        return out
    except Exception as exc:
        logger.warning("Live AQI overlay failed; using offline snapshot: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Office location resolution
# ---------------------------------------------------------------------------

def resolve_office_coordinates(
    office_location: str,
    localities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve free-text office location to lat/lon.

    Resolution order:
      1. Exact match against registry locality name
      2. Substring match against registry locality names
      3. location_service.resolve_location (Google Geocoding when configured)
    """
    query = (office_location or "").strip()
    if not query:
        return {
            "success": False,
            "error": "officeLocation is empty.",
            "resolution_method": None,
        }

    if localities is None:
        localities = load_locality_feature_vectors()

    q_lower = query.lower()

    for loc in localities:
        if loc["name"].lower() == q_lower:
            return {
                "success": True,
                "latitude": float(loc["centroid_lat"]),
                "longitude": float(loc["centroid_lon"]),
                "label": loc["name"],
                "resolution_method": "locality_registry_exact",
            }

    substring_hits = [
        loc for loc in localities
        if loc["name"].lower() in q_lower or q_lower in loc["name"].lower()
    ]
    if substring_hits:
        best = max(substring_hits, key=lambda loc: len(loc["name"]))
        return {
            "success": True,
            "latitude": float(best["centroid_lat"]),
            "longitude": float(best["centroid_lon"]),
            "label": best["name"],
            "resolution_method": "locality_registry_substring",
        }

    try:
        from backend.app.services.location_service import resolve_location

        geo_query = query
        if "bengaluru" not in q_lower and "bangalore" not in q_lower:
            geo_query = f"{query}, Bengaluru"

        result = resolve_location(query=geo_query)
        if result.get("success"):
            return {
                "success": True,
                "latitude": float(result["latitude"]),
                "longitude": float(result["longitude"]),
                "label": result.get("label") or query,
                "resolution_method": "geocoding",
            }
        return {
            "success": False,
            "error": result.get("error")
            or "Could not resolve officeLocation to coordinates.",
            "resolution_method": "geocoding_failed",
            "source_status": result.get("source_status"),
        }
    except Exception as exc:  # pragma: no cover
        logger.exception("Office geocoding failed")
        return {
            "success": False,
            "error": f"Office location resolution failed: {exc}",
            "resolution_method": "geocoding_error",
        }


# ---------------------------------------------------------------------------
# BHK mapping + rent lookup
# ---------------------------------------------------------------------------

def family_size_to_bhk_bucket(family_size: int) -> str:
    n = max(1, int(family_size))
    if n <= 1:
        return "1"
    if n == 2:
        return "2"
    if n <= 4:
        return "3"
    if n <= 6:
        return "4"
    return "5+"


def _rent_for_locality(loc: dict[str, Any], bhk_bucket: str) -> tuple[float | None, bool]:
    rent_block = loc.get("rent") or {}
    by_bhk = rent_block.get("by_bhk") or {}
    entry = by_bhk.get(bhk_bucket) or by_bhk.get("2")
    if not entry or entry.get("median_rent") is None:
        overall = rent_block.get("overall_median_rent")
        if overall is None:
            return None, True
        return float(overall), True
    return float(entry["median_rent"]), bool(entry.get("is_estimated", True))


# ---------------------------------------------------------------------------
# Component scores (each in [0, 1], higher = better)
# ---------------------------------------------------------------------------

def _score_rent_fit(median_rent: float, budget: float) -> float:
    if budget <= 0 or median_rent is None:
        return 0.0
    ratio = median_rent / budget
    if ratio <= 1.0:
        return float(min(1.0, 0.85 + 0.15 * ratio))
    if ratio >= RENT_OVER_BUDGET_ZERO_RATIO:
        return 0.0
    return float(1.0 - (ratio - 1.0) / (RENT_OVER_BUDGET_ZERO_RATIO - 1.0))


def _score_aqi(aqi: float | None) -> float:
    if aqi is None:
        return 0.5
    return float(max(0.0, min(1.0, 1.0 - (float(aqi) / AQI_SCORE_ZERO_AT))))


def _score_commute(minutes: float, max_minutes: float) -> float:
    if max_minutes <= 0:
        return 0.0
    if minutes <= max_minutes * 0.5:
        return 1.0
    if minutes <= max_minutes:
        t = (minutes - max_minutes * 0.5) / (max_minutes * 0.5)
        return float(1.0 - 0.4 * t)
    return 0.0


def _score_0_100_field(value: float | None, *, invert: bool = False) -> float:
    if value is None:
        return 0.5
    s = max(0.0, min(100.0, float(value))) / 100.0
    return 1.0 - s if invert else s


def _score_metro(metro_km: float | None, available: bool) -> float:
    if not available or metro_km is None:
        return 0.0
    return float(max(0.0, min(1.0, 1.0 - (float(metro_km) / 3.0))))


def build_weights(profile: CitizenProfile) -> dict[str, float]:
    weights = dict(BASE_WEIGHTS)
    for priority in profile.priorities or []:
        boost = PRIORITY_BOOST.get(priority)
        if boost:
            key, amount = boost
            weights[key] = weights.get(key, 0.0) + amount

    sensitive = [
        c for c in (profile.healthConditions or [])
        if c in ("respiratory", "elderly", "young_children")
    ]
    if sensitive:
        weights["aqi"] = weights.get("aqi", 0.0) + HEALTH_AQI_BOOST * len(sensitive)

    total = sum(weights.values())
    if total <= 0:
        return dict(BASE_WEIGHTS)
    return {k: v / total for k, v in weights.items()}


# ---------------------------------------------------------------------------
# Reasons
# ---------------------------------------------------------------------------

def _format_inr(amount: float) -> str:
    n = int(round(amount))
    return f"₹{n:,}"


def generate_reasons(
    *,
    profile: CitizenProfile,
    name: str,
    median_rent: float,
    rent_is_estimated: bool,
    aqi: float | None,
    commute_minutes: float,
    commute_source: str,
    env: dict[str, Any],
    component_scores: dict[str, float],
    weights: dict[str, float],
) -> list[str]:
    reasons: list[str] = []
    budget = profile.rentBudget

    if median_rent <= budget:
        suffix = " (estimated)" if rent_is_estimated else ""
        reasons.append(
            f"Rent fits your {_format_inr(budget)} budget "
            f"(median {_format_inr(median_rent)}{suffix})"
        )
    else:
        pct_over = int(round((median_rent / budget - 1.0) * 100))
        reasons.append(
            f"{pct_over}% above your {_format_inr(budget)} budget "
            f"(median {_format_inr(median_rent)})"
        )

    if aqi is not None:
        if aqi <= 50:
            reasons.append(f"Good air quality here (PM2.5 ≈ {aqi:.0f} µg/m³)")
        elif aqi <= 90:
            reasons.append(f"Moderate air quality (PM2.5 ≈ {aqi:.0f} µg/m³)")
        else:
            reasons.append(f"Elevated pollution (PM2.5 ≈ {aqi:.0f} µg/m³)")

        attr = env.get("source_attribution") or {}
        industrial = attr.get("industrial")
        if industrial is not None and industrial < 0.15 and aqi <= 90:
            reasons.append("Low industrial pollution share in this area")

    commute_label = (
        f"~{commute_minutes:.0f} min drive"
        if commute_source == "google_routes"
        else f"~{commute_minutes:.0f} min (estimated)"
    )
    if commute_minutes <= profile.maxCommuteMinutes * 0.6:
        reasons.append(
            f"Short commute to office ({commute_label}, "
            f"within your {profile.maxCommuteMinutes} min limit)"
        )
    elif commute_minutes <= profile.maxCommuteMinutes:
        reasons.append(
            f"Commute {commute_label} (within your "
            f"{profile.maxCommuteMinutes} min limit)"
        )

    if env.get("metro_data_available") and env.get("metro_distance_km") is not None:
        station = env.get("nearest_metro_station")
        dist = env["metro_distance_km"]
        if dist <= 1.0:
            label = f"{station} ({dist:.1f} km)" if station else f"{dist:.1f} km"
            if "metro" in (profile.priorities or []) or dist <= 0.8:
                reasons.append(f"Near metro station — {label}")

    if "parks" in (profile.priorities or []) and component_scores.get("parks", 0) >= 0.55:
        reasons.append(f"Strong park / green cover score ({env.get('park_score', 0):.0f}/100)")
    if "schools" in (profile.priorities or []) and component_scores.get("schools", 0) >= 0.55:
        reasons.append(f"Good school-access score ({env.get('school_score', 0):.0f}/100)")
    if "hospitals" in (profile.priorities or []) and component_scores.get("hospitals", 0) >= 0.55:
        reasons.append(f"Good hospital-access score ({env.get('hospital_score', 0):.0f}/100)")
    if "low_noise" in (profile.priorities or []) and component_scores.get("noise", 0) >= 0.55:
        reasons.append(
            f"Relatively quiet roads (noise score {env.get('noise_score', 0):.0f}/100, lower is better)"
        )
    if "metro" in (profile.priorities or []) and not env.get("metro_data_available"):
        if not any("metro" in r.lower() for r in reasons):
            reasons.append("Metro distance unavailable (no transit layer in current data)")

    construction = env.get("construction_activity_score") or 0
    if construction >= 60:
        reasons.append(f"Elevated construction activity nearby (score {construction:.0f}/100)")

    deduped: list[str] = []
    for r in reasons:
        if r not in deduped:
            deduped.append(r)
    if len(deduped) < 2:
        deduped.append(f"Matched against your profile for {name}")
    return deduped[:4]


# ---------------------------------------------------------------------------
# Candidate building helpers
# ---------------------------------------------------------------------------

def _build_candidate(
    *,
    loc: dict[str, Any],
    profile: CitizenProfile,
    weights: dict[str, float],
    bhk_bucket: str,
    commute_min: float,
    commute_source: str,
    aqi: float | None,
    aqi_is_estimated: bool,
) -> dict[str, Any] | None:
    env = dict(loc.get("environment") or {})
    median_rent, rent_is_estimated = _rent_for_locality(loc, bhk_bucket)
    if median_rent is None:
        return None

    component_scores = {
        "rent_fit": _score_rent_fit(median_rent, profile.rentBudget),
        "aqi": _score_aqi(aqi),
        "commute": _score_commute(commute_min, profile.maxCommuteMinutes),
        "parks": _score_0_100_field(env.get("park_score")),
        "hospitals": _score_0_100_field(env.get("hospital_score")),
        "schools": _score_0_100_field(env.get("school_score")),
        "noise": _score_0_100_field(env.get("noise_score"), invert=True),
        "metro": _score_metro(
            env.get("metro_distance_km"),
            bool(env.get("metro_data_available")),
        ),
    }
    total = sum(weights.get(k, 0.0) * component_scores.get(k, 0.0) for k in weights)
    match_pct = round(total * 100.0, 1)

    reasons = generate_reasons(
        profile=profile,
        name=loc["name"],
        median_rent=median_rent,
        rent_is_estimated=rent_is_estimated,
        aqi=aqi,
        commute_minutes=commute_min,
        commute_source=commute_source,
        env=env,
        component_scores=component_scores,
        weights=weights,
    )

    feature = NeighbourhoodFeatureVector(
        aqi=float(aqi) if aqi is not None else 0.0,
        aqiIsEstimated=aqi_is_estimated,
        avgRentForBudgetBHK=float(median_rent),
        rentIsEstimated=rent_is_estimated,
        commuteMinutesToOffice=float(commute_min),
        hospitalScore=float(env.get("hospital_score") or 0.0),
        schoolScore=float(env.get("school_score") or 0.0),
        parkScore=float(env.get("park_score") or 0.0),
        metroDistanceKm=env.get("metro_distance_km"),
        noiseScore=float(env.get("noise_score") or 0.0),
        constructionActivityScore=float(env.get("construction_activity_score") or 0.0),
    )

    return {
        "name": loc["name"],
        "loc": loc,
        "match_pct": match_pct,
        "reasons": reasons,
        "feature": feature,
        "component_scores": component_scores,
        "commute_source": commute_source,
        "centroid_lat": float(loc["centroid_lat"]),
        "centroid_lon": float(loc["centroid_lon"]),
        "aqi": aqi,
        "aqi_is_estimated": aqi_is_estimated,
        "median_rent": median_rent,
        "rent_is_estimated": rent_is_estimated,
    }


# ---------------------------------------------------------------------------
# Main matching entry point
# ---------------------------------------------------------------------------

def match_neighbourhoods(
    profile: CitizenProfile,
    *,
    top_n: int = DEFAULT_TOP_N,
    localities: list[dict[str, Any]] | None = None,
    use_live_aqi: bool = True,
    use_routes_refine: bool = True,
) -> list[NeighbourhoodMatch]:
    """Score localities against the profile; return top-N NeighbourhoodMatch list.

    Empty list when no locality survives the commute filter.
    Raises OfficeLocationUnresolvedError when the office cannot be resolved.
    """
    if localities is None:
        localities = load_locality_feature_vectors()
    if not localities:
        logger.warning("No locality feature vectors available for matching")
        return []

    office = resolve_office_coordinates(profile.officeLocation, localities)
    if not office.get("success"):
        logger.warning(
            "Office location unresolved for %r: %s",
            profile.officeLocation,
            office.get("error"),
        )
        raise OfficeLocationUnresolvedError(
            office.get("error") or "Could not resolve officeLocation"
        )

    office_lat = float(office["latitude"])
    office_lon = float(office["longitude"])
    weights = build_weights(profile)
    bhk_bucket = family_size_to_bhk_bucket(profile.familySize)

    # --- Live AQI overlay (optional, best-effort) ---
    live_aqi: dict[str, tuple[float | None, bool]] = {}
    if use_live_aqi:
        live_aqi = _live_aqi_by_locality(localities)

    proxy_limit = profile.maxCommuteMinutes * PROXY_COMMUTE_SLACK
    proxy_candidates: list[dict[str, Any]] = []

    for loc in localities:
        env = loc.get("environment") or {}
        median_rent, _ = _rent_for_locality(loc, bhk_bucket)
        if median_rent is None:
            continue

        proxy_min = estimate_commute_minutes(
            loc["centroid_lat"], loc["centroid_lon"], office_lat, office_lon
        )
        # Soft pre-filter: allow slack so Routes can still rescue borderline cases
        if proxy_min > proxy_limit:
            continue

        if loc["name"] in live_aqi:
            aqi, aqi_est = live_aqi[loc["name"]]
        else:
            aqi = env.get("aqi")
            aqi_est = bool(env.get("aqi_is_estimated", True))

        cand = _build_candidate(
            loc=loc,
            profile=profile,
            weights=weights,
            bhk_bucket=bhk_bucket,
            commute_min=proxy_min,
            commute_source="proxy",
            aqi=aqi,
            aqi_is_estimated=aqi_est,
        )
        if cand is not None:
            proxy_candidates.append(cand)

    # Sort by proxy score
    proxy_candidates.sort(key=lambda c: (-c["match_pct"], c["name"]))

    if not proxy_candidates:
        return []

    # --- Hybrid Routes refine on shortlist ---
    shortlist = proxy_candidates[: max(ROUTES_SHORTLIST_SIZE, top_n)]
    refined: list[dict[str, Any]] = []
    any_routes_success = False

    if use_routes_refine:
        for cand in shortlist:
            routes = _routes_commute_minutes(
                cand["centroid_lat"],
                cand["centroid_lon"],
                office_lat,
                office_lon,
            )
            if routes.get("available") and routes.get("minutes") is not None:
                any_routes_success = True
                real_min = float(routes["minutes"])
                if real_min > profile.maxCommuteMinutes:
                    continue  # hard filter on real travel time — do not fall back
                rebuilt = _build_candidate(
                    loc=cand["loc"],
                    profile=profile,
                    weights=weights,
                    bhk_bucket=bhk_bucket,
                    commute_min=real_min,
                    commute_source="google_routes",
                    aqi=cand["aqi"],
                    aqi_is_estimated=cand["aqi_is_estimated"],
                )
                if rebuilt is not None:
                    refined.append(rebuilt)
            else:
                # Routes unavailable for this pair — keep proxy if within hard limit
                if cand["feature"].commuteMinutesToOffice <= profile.maxCommuteMinutes:
                    refined.append(cand)
    else:
        refined = [
            c for c in shortlist
            if c["feature"].commuteMinutesToOffice <= profile.maxCommuteMinutes
        ]

    # Only fall back to the full proxy list when Routes was completely
    # unavailable for every shortlist candidate (not when it successfully
    # filtered everyone as over the commute limit).
    if not refined and not any_routes_success:
        refined = [
            c for c in proxy_candidates
            if c["feature"].commuteMinutesToOffice <= profile.maxCommuteMinutes
        ]

    refined.sort(key=lambda c: (-c["match_pct"], c["name"]))
    top = refined[: max(1, top_n)] if refined else []

    matches: list[NeighbourhoodMatch] = []
    for rank, cand in enumerate(top, start=1):
        matches.append(
            NeighbourhoodMatch(
                rank=rank,
                name=cand["name"],
                matchScorePercent=cand["match_pct"],
                reasons=cand["reasons"],
                featureVector=cand["feature"],
            )
        )
    return matches


class OfficeLocationUnresolvedError(Exception):
    """Raised when the office free-text location cannot be resolved to coordinates."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
