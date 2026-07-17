"""Hex-level attribution confidence / reliability scoring.

Honest, explainable confidence for source attribution and fused PM2.5.
Does NOT invent sensor readings — it only quantifies how much we should
trust the attribution mix given distance, wind regime, and data coverage.
"""

from __future__ import annotations

from typing import Any

# Distance bands (metres) → score penalty applied after base 100.
# Fusion station range is typically 5 km; beyond that fused PM is usually null.
_DISTANCE_PENALTIES: list[tuple[float, int, str]] = [
    (1000.0, 0, "within 1 km of a monitoring station"),
    (2500.0, 15, "1–2.5 km from nearest station"),
    (4000.0, 30, "2.5–4 km from nearest station"),
    (5000.0, 45, "4–5 km from nearest station (edge of fusion range)"),
]

_LEVELS = (
    (80, "High"),
    (55, "Medium"),
    (30, "Low"),
    (0, "Very Low"),
)


def _level_for(score: int) -> str:
    for threshold, label in _LEVELS:
        if score >= threshold:
            return label
    return "Very Low"


def compute_attribution_confidence(
    *,
    nearest_station_distance_m: float | None = None,
    stations_contributing: int = 0,
    method: str | None = None,
    wind_speed_kmh: float | None = None,
    source_hexagons_contributing: int | None = None,
    fusion_available: bool | None = None,
    fused_pm25: float | None = None,
) -> dict[str, Any]:
    """Return a 0–100 confidence score with human-readable explanation.

    Parameters map to fields already produced by attribution / fusion /
    enforcement pipelines so this can be attached without re-running physics.
    """
    score = 100
    flags: list[str] = []
    reasons: list[str] = []

    # --- Distance to nearest station (softer penalties — avoid mass 0% on the map) ---
    dist = nearest_station_distance_m
    if dist is None or (isinstance(dist, float) and dist != dist):  # NaN
        score -= 32
        flags.append("no_station_anchor")
        reasons.append("no monitoring station within fusion range — attribution is feature-proxy only")
        dist_note = "no station in range"
    else:
        dist = float(dist)
        applied = False
        for max_m, penalty, note in _DISTANCE_PENALTIES:
            if dist <= max_m:
                score -= penalty
                reasons.append(f"{note} ({dist / 1000:.1f} km)")
                dist_note = f"{dist / 1000:.1f} km from nearest station"
                if penalty >= 30:
                    flags.append("far_from_station")
                applied = True
                break
        if not applied:
            score -= 40
            flags.append("beyond_fusion_range")
            reasons.append(f"nearest station {dist / 1000:.1f} km (beyond typical fusion range)")
            dist_note = f"{dist / 1000:.1f} km from nearest station"

    # --- Wind / method ---
    method_norm = (method or "").lower()
    if method_norm == "calm_fallback":
        score -= 15
        flags.append("calm_fallback")
        reasons.append("calm / unusable wind → pure distance weighting (directional uncertainty)")
    elif method_norm == "unavailable":
        score -= 30
        flags.append("attribution_unavailable")
        reasons.append("attribution method unavailable")
    elif method_norm == "vectorised_feature_proxy":
        # Enforcement fast path — still usable but not full wind plume physics
        score -= 5
        flags.append("feature_proxy_attribution")
        reasons.append("feature-proxy attribution (not full wind-plume transfer)")
    elif wind_speed_kmh is not None and wind_speed_kmh <= 1.0:
        score -= 12
        flags.append("calm_wind")
        reasons.append(f"very low wind speed ({wind_speed_kmh:.1f} km/h)")
    elif wind_speed_kmh is not None:
        reasons.append(f"wind {wind_speed_kmh:.1f} km/h used for directional weighting")

    # --- Station contribution count (fusion) ---
    n_st = int(stations_contributing or 0)
    if n_st <= 0 and (fusion_available is False or fused_pm25 is None):
        score -= 12
        flags.append("fusion_unavailable")
        reasons.append("no fused PM2.5 anchor from stations (source mix still computed from local features)")
    elif n_st == 1:
        score -= 6
        flags.append("single_station_anchor")
        reasons.append("only one station contributes to fusion")
    elif n_st >= 2:
        reasons.append(f"{n_st} stations contribute to fusion")

    # --- Source context density ---
    if source_hexagons_contributing is not None:
        n_src = int(source_hexagons_contributing)
        if n_src <= 0:
            score -= 15
            flags.append("no_source_context")
            reasons.append("no source hexagons in search radius")
        elif n_src < 3:
            score -= 8
            flags.append("sparse_source_context")
            reasons.append(f"sparse source context ({n_src} hexes)")

    score = max(0, min(100, int(round(score))))
    # Floor: if we still have a usable attribution method, never show a broken 0%
    # (judges read 0% as "system failure" rather than "low station support").
    if method_norm not in ("unavailable", "") and score < 18:
        score = 18
        flags.append("confidence_floor_applied")
        reasons.append("minimum display floor for valid feature-based attribution")
    level = _level_for(score)

    # Compact narrative for UI
    primary = reasons[0] if reasons else "baseline reliability"
    explanation = f"{score}% — {level} confidence due to {primary}"
    if len(reasons) > 1:
        explanation += f"; also: {reasons[1]}"

    # Soft factor for risk-adjusted ranking (never zero — keep some signal)
    risk_factor = round(0.35 + 0.65 * (score / 100.0), 4)

    dist_out = None
    if nearest_station_distance_m is not None:
        try:
            dist_out = round(float(nearest_station_distance_m), 1)
        except (TypeError, ValueError):
            dist_out = None

    return {
        "attribution_confidence_score": score,
        "attribution_confidence_level": level,
        "attribution_confidence_pct": score,
        "confidence_flags": flags,
        "confidence_reasons": reasons,
        "confidence_explanation": explanation,
        "nearest_station_distance_m": dist_out,
        "risk_confidence_factor": risk_factor,
        "distance_note": dist_note,
    }


def attach_confidence_to_hex_payload(
    payload: dict[str, Any],
    *,
    wind_speed_kmh: float | None = None,
) -> dict[str, Any]:
    """Mutate/return payload with confidence fields from existing keys."""
    wind = payload.get("wind_used") or {}
    ws = wind_speed_kmh
    if ws is None:
        ws = wind.get("speed_kmh")
    conf = compute_attribution_confidence(
        nearest_station_distance_m=payload.get("nearest_station_distance_m"),
        stations_contributing=int(payload.get("stations_contributing") or 0),
        method=payload.get("method"),
        wind_speed_kmh=ws if ws is not None else None,
        source_hexagons_contributing=payload.get("source_hexagons_contributing"),
        fusion_available=payload.get("fusion_method") not in (None, "unavailable"),
        fused_pm25=payload.get("fused_pm25"),
    )
    payload.update(conf)
    return payload


def nearest_station_distances_m(
    lats: Any,
    lons: Any,
    station_lats: list[float],
    station_lons: list[float],
) -> tuple[Any, Any]:
    """Vectorised nearest-station distance (m) and station index for hex arrays."""
    import numpy as np

    lats_a = np.asarray(lats, dtype=float)
    lons_a = np.asarray(lons, dtype=float)
    if not station_lats:
        nan = np.full(lats_a.shape, np.nan)
        return nan, np.full(lats_a.shape, -1, dtype=int)

    s_lats = np.asarray(station_lats, dtype=float)
    s_lons = np.asarray(station_lons, dtype=float)
    # Broadcast haversine: (n_hex, n_st)
    r = 6_371_000.0
    dlat = np.radians(s_lats[None, :] - lats_a[:, None])
    dlon = np.radians(s_lons[None, :] - lons_a[:, None])
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(np.radians(lats_a))[:, None]
        * np.cos(np.radians(s_lats))[None, :]
        * np.sin(dlon / 2) ** 2
    )
    dist = r * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    idx = np.argmin(dist, axis=1)
    nearest = dist[np.arange(len(lats_a)), idx]
    return nearest, idx
