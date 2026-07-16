"""What-If / counterfactual scenario simulation for AQI Sentinel Copilot.

Uses existing source attribution + fused PM2.5 (and optionally enforcement
rankings) to estimate how pollution shares and PM2.5 would change under
hypothetical source reductions or increases.

IMPORTANT
---------
Results are **simulations**, not forecasts or legal determinations.
They use a linear source-contribution model with explicit uncertainty bounds.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SOURCE_KEYS = ("traffic", "industrial", "construction", "burning")

SIMULATION_DISCLAIMER = (
    "This is a what-if simulation based on current source-attribution shares "
    "and a linear contribution model. It is not a validated atmospheric forecast, "
    "not legal proof of impact, and carries substantial uncertainty."
)

# Relative uncertainty band around simulated ΔPM2.5 (fraction of |delta|)
_UNCERTAINTY_FRAC = 0.30
# Floor for total share after renormalization
_EPS = 1e-9


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _normalize_shares(raw: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(raw.get(k, 0.0))) for k in SOURCE_KEYS)
    if total <= _EPS:
        return {k: 0.25 for k in SOURCE_KEYS}
    return {k: max(0.0, float(raw.get(k, 0.0))) / total for k in SOURCE_KEYS}


def _parse_scale(
    *,
    scale: float | None,
    reduction_percent: float | None,
    increase_percent: float | None,
) -> float:
    """Convert scale / reduction% / increase% into a multiplicative factor.

    scale=0.5 → 50% of baseline activity
    reduction_percent=50 → scale 0.5
    increase_percent=30 → scale 1.3
    """
    if scale is not None:
        return _clamp(float(scale), 0.0, 2.0)
    if reduction_percent is not None:
        return _clamp(1.0 - float(reduction_percent) / 100.0, 0.0, 2.0)
    if increase_percent is not None:
        return _clamp(1.0 + float(increase_percent) / 100.0, 0.0, 2.0)
    return 1.0


def _apply_source_scales(
    baseline: dict[str, float],
    scales: dict[str, float],
) -> dict[str, float]:
    raw = {
        k: float(baseline.get(k, 0.0)) * float(scales.get(k, 1.0))
        for k in SOURCE_KEYS
    }
    return _normalize_shares(raw)


def _estimate_pm25_delta(
    baseline_pm25: float | None,
    baseline_attr: dict[str, float],
    scales: dict[str, float],
) -> dict[str, Any]:
    """Linear source-contribution model.

    Assuming PM2.5 ≈ sum_i (share_i * PM2.5) under current shares,
    reducing source s activity by factor f (scale) removes approximately
    share_s * (1 - f) of total PM2.5 (local linearization).

    multi-source: retained_fraction = 1 - sum_s share_s * (1 - scale_s)
    """
    if baseline_pm25 is None or baseline_pm25 <= 0:
        return {
            "baseline_pm25": baseline_pm25,
            "simulated_pm25": None,
            "delta_pm25": None,
            "delta_percent": None,
            "retained_fraction": None,
            "uncertainty_low_pm25": None,
            "uncertainty_high_pm25": None,
            "model": "unavailable_no_baseline_pm25",
        }

    removed = 0.0
    for k in SOURCE_KEYS:
        share = float(baseline_attr.get(k, 0.0))
        sc = float(scales.get(k, 1.0))
        removed += share * (1.0 - sc)
    # Clamp: cannot remove more than 100% or go negative absurdly
    retained = _clamp(1.0 - removed, 0.05, 2.0)
    sim = float(baseline_pm25) * retained
    delta = sim - float(baseline_pm25)
    delta_pct = (delta / float(baseline_pm25)) * 100.0
    band = abs(delta) * _UNCERTAINTY_FRAC
    return {
        "baseline_pm25": round(float(baseline_pm25), 2),
        "simulated_pm25": round(sim, 2),
        "delta_pm25": round(delta, 2),
        "delta_percent": round(delta_pct, 1),
        "retained_fraction": round(retained, 4),
        "uncertainty_low_pm25": round(max(0.0, sim - band), 2),
        "uncertainty_high_pm25": round(sim + band, 2),
        "model": "linear_source_contribution_v1",
        "uncertainty_band_fraction": _UNCERTAINTY_FRAC,
    }


def _resolve_location_inputs(
    *,
    city: str,
    h3_cell: str | None,
    station_id: str | None,
    lat: float | None,
    lon: float | None,
) -> dict[str, Any]:
    """Resolve to an h3_cell + baseline attribution payload."""
    import h3 as _h3

    from backend.app.services.attribution_service import get_single_hexagon_attribution

    cell = (h3_cell or "").strip() or None
    sid = (station_id or "").strip() or None

    if not cell and sid:
        try:
            from pipeline.station_registry import get_station_by_id

            st = get_station_by_id(sid)
            if st and st.latitude is not None and st.longitude is not None:
                cell = _h3.latlng_to_cell(float(st.latitude), float(st.longitude), 9)
        except Exception as exc:
            logger.debug("station→h3 failed for %s: %s", sid, exc)

    if not cell and lat is not None and lon is not None:
        cell = _h3.latlng_to_cell(float(lat), float(lon), 9)

    if not cell:
        # City-level: use top enforcement hex as representative scenario anchor
        try:
            from backend.app.services.enforcement_priority_service import (
                compute_enforcement_priorities,
            )

            enf = compute_enforcement_priorities(city=city, top_k=1)
            ranked = enf.get("ranked_hexagons") or []
            if ranked:
                cell = ranked[0].get("h3_cell") or ranked[0].get("id")
                anchor_name = ranked[0].get("location_name") or cell
                attr = get_single_hexagon_attribution(str(cell), city=city)
                return {
                    "h3_cell": str(cell),
                    "location_label": f"top-priority hex ({anchor_name})",
                    "scope": "city_anchor_top_priority",
                    "attribution": attr,
                    "enforcement_seed": ranked[0],
                }
        except Exception as exc:
            logger.warning("City anchor for what-if failed: %s", exc)
        return {"error": "Could not resolve a location for the scenario. Provide h3_cell, station_id, or lat/lon."}

    attr = get_single_hexagon_attribution(str(cell), city=city)
    if attr.get("error"):
        return {"error": attr["error"], "h3_cell": cell}

    label = sid or str(cell)
    try:
        # Prefer reverse locality if present later; keep cell id short
        label = sid or f"H3 {str(cell)[:12]}…"
    except Exception:
        pass

    return {
        "h3_cell": str(cell),
        "location_label": label,
        "scope": "hexagon",
        "attribution": attr,
        "station_id": sid,
    }


def run_whatif_scenario(
    *,
    city: str = "bengaluru",
    h3_cell: str | None = None,
    station_id: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    # Per-source scales (1.0 = no change). Prefer these when agent can set them.
    traffic_scale: float | None = None,
    industrial_scale: float | None = None,
    construction_scale: float | None = None,
    burning_scale: float | None = None,
    # Or percent reductions (0–100) / increases
    traffic_reduction_percent: float | None = None,
    industrial_reduction_percent: float | None = None,
    construction_reduction_percent: float | None = None,
    burning_reduction_percent: float | None = None,
    traffic_increase_percent: float | None = None,
    industrial_increase_percent: float | None = None,
    construction_increase_percent: float | None = None,
    burning_increase_percent: float | None = None,
    # Natural-language scenario fragment (optional parse assist)
    scenario_text: str | None = None,
    include_enforcement_delta: bool = True,
) -> dict[str, Any]:
    """Run a counterfactual pollution scenario for one area (or city anchor)."""
    city = (city or "bengaluru").lower().strip()

    # Optional NL parse if scales not provided
    if scenario_text and all(
        x is None
        for x in (
            traffic_scale,
            industrial_scale,
            construction_scale,
            burning_scale,
            traffic_reduction_percent,
            industrial_reduction_percent,
            construction_reduction_percent,
            burning_reduction_percent,
        )
    ):
        parsed = parse_scenario_text(scenario_text)
        traffic_reduction_percent = traffic_reduction_percent or parsed.get("traffic_reduction_percent")
        industrial_reduction_percent = industrial_reduction_percent or parsed.get(
            "industrial_reduction_percent"
        )
        construction_reduction_percent = construction_reduction_percent or parsed.get(
            "construction_reduction_percent"
        )
        burning_reduction_percent = burning_reduction_percent or parsed.get("burning_reduction_percent")
        traffic_increase_percent = traffic_increase_percent or parsed.get("traffic_increase_percent")
        # scales from parse
        for k in SOURCE_KEYS:
            sk = f"{k}_scale"
            if parsed.get(sk) is not None:
                if k == "traffic" and traffic_scale is None:
                    traffic_scale = parsed[sk]
                elif k == "industrial" and industrial_scale is None:
                    industrial_scale = parsed[sk]
                elif k == "construction" and construction_scale is None:
                    construction_scale = parsed[sk]
                elif k == "burning" and burning_scale is None:
                    burning_scale = parsed[sk]

    scales = {
        "traffic": _parse_scale(
            scale=traffic_scale,
            reduction_percent=traffic_reduction_percent,
            increase_percent=traffic_increase_percent,
        ),
        "industrial": _parse_scale(
            scale=industrial_scale,
            reduction_percent=industrial_reduction_percent,
            increase_percent=industrial_increase_percent,
        ),
        "construction": _parse_scale(
            scale=construction_scale,
            reduction_percent=construction_reduction_percent,
            increase_percent=construction_increase_percent,
        ),
        "burning": _parse_scale(
            scale=burning_scale,
            reduction_percent=burning_reduction_percent,
            increase_percent=burning_increase_percent,
        ),
    }

    if all(abs(v - 1.0) < 1e-9 for v in scales.values()):
        return {
            "_tool_error": (
                "No source change specified. Set e.g. construction_reduction_percent=50 "
                "or traffic_scale=0.7 for a what-if scenario."
            ),
            "_error_type": "ParameterError",
            "disclaimer": SIMULATION_DISCLAIMER,
        }

    resolved = _resolve_location_inputs(
        city=city,
        h3_cell=h3_cell,
        station_id=station_id,
        lat=lat,
        lon=lon,
    )
    if resolved.get("error"):
        return {
            "_tool_error": resolved["error"],
            "_error_type": "LocationError",
            "disclaimer": SIMULATION_DISCLAIMER,
        }

    attr_payload = resolved.get("attribution") or {}
    baseline_attr = _normalize_shares(attr_payload.get("source_attribution") or {})
    baseline_pm25 = attr_payload.get("fused_pm25")
    if baseline_pm25 is None:
        baseline_pm25 = attr_payload.get("baseline_pm25")
    pm_source = "fusion" if baseline_pm25 is not None else None

    # Fallback: station forecast / latest evidence PM2.5
    if baseline_pm25 is None:
        sid_for_pm = resolved.get("station_id") or station_id or attr_payload.get(
            "nearest_station_id"
        )
        if sid_for_pm:
            try:
                from backend.app.services.forecast_evidence_service import get_forecast_evidence

                ev = get_forecast_evidence(str(sid_for_pm), city)
                if isinstance(ev, dict) and ev.get("predicted_pm25") is not None:
                    baseline_pm25 = float(ev["predicted_pm25"])
                    pm_source = "station_forecast"
            except Exception as exc:
                logger.debug("what-if station PM fallback failed: %s", exc)

    sim_attr = _apply_source_scales(baseline_attr, scales)
    pm = _estimate_pm25_delta(baseline_pm25, baseline_attr, scales)
    if pm_source:
        pm["baseline_pm25_source"] = pm_source

    # Human-readable intervention list
    interventions: list[str] = []
    for k in SOURCE_KEYS:
        sc = scales[k]
        if abs(sc - 1.0) < 1e-6:
            continue
        if sc < 1.0:
            interventions.append(f"{k}: reduce activity to {sc * 100:.0f}% of baseline (−{(1 - sc) * 100:.0f}%)")
        else:
            interventions.append(f"{k}: increase activity to {sc * 100:.0f}% of baseline (+{(sc - 1) * 100:.0f}%)")

    # Dominant source shift
    base_dom = max(baseline_attr, key=baseline_attr.get)
    sim_dom = max(sim_attr, key=sim_attr.get)

    result: dict[str, Any] = {
        "is_simulation": True,
        "disclaimer": SIMULATION_DISCLAIMER,
        "city": city,
        "h3_cell": resolved.get("h3_cell"),
        "station_id": resolved.get("station_id") or station_id,
        "location_label": resolved.get("location_label"),
        "scope": resolved.get("scope"),
        "interventions": interventions,
        "source_scales_applied": {k: round(v, 4) for k, v in scales.items()},
        "baseline_source_attribution": {k: round(v, 4) for k, v in baseline_attr.items()},
        "simulated_source_attribution": {k: round(v, 4) for k, v in sim_attr.items()},
        "baseline_dominant_source": base_dom,
        "simulated_dominant_source": sim_dom,
        "pm25": pm,
        "attribution_confidence_score": attr_payload.get("attribution_confidence_score"),
        "attribution_confidence_level": attr_payload.get("attribution_confidence_level"),
        "computed_at": datetime.now(tz=timezone.utc).isoformat(),
        "limitations": [
            "Linear source-contribution model; real atmospheric response is non-linear.",
            "Background / regional transport not fully separated from local sources.",
            "Enforcement intensity is not a direct multiplier on emissions inventory.",
            f"Uncertainty band ±{_UNCERTAINTY_FRAC * 100:.0f}% of estimated ΔPM2.5 (illustrative).",
            "Source attribution is investigation signal, not legal proof of a polluter.",
        ],
    }

    # Optional: city enforcement ranking under construction (or multi) scale
    if include_enforcement_delta and abs(scales["construction"] - 1.0) > 1e-6:
        try:
            from backend.app.services.enforcement_priority_service import (
                compute_enforcement_priorities,
            )

            base_enf = compute_enforcement_priorities(city=city, top_k=5)
            sim_enf = compute_enforcement_priorities(
                city=city,
                top_k=5,
                construction_scale=scales["construction"],
            )
            result["enforcement_ranking_baseline_top"] = [
                {
                    "rank": h.get("rank"),
                    "location_name": h.get("location_name"),
                    "h3_cell": h.get("h3_cell"),
                    "priority_score": h.get("priority_score"),
                    "primary_source": h.get("primary_source") or h.get("primary_source_key"),
                }
                for h in (base_enf.get("ranked_hexagons") or [])[:5]
            ]
            result["enforcement_ranking_simulated_top"] = [
                {
                    "rank": h.get("rank"),
                    "location_name": h.get("location_name"),
                    "h3_cell": h.get("h3_cell"),
                    "priority_score": h.get("priority_score"),
                    "primary_source": h.get("primary_source") or h.get("primary_source_key"),
                }
                for h in (sim_enf.get("ranked_hexagons") or [])[:5]
            ]
            result["enforcement_note"] = (
                "City-wide enforcement re-rank uses construction channel scale only "
                f"(construction_scale={scales['construction']}). Other source scales affect local PM estimate only."
            )
        except Exception as exc:
            logger.debug("Enforcement what-if ranking skipped: %s", exc)
            result["enforcement_note"] = f"Enforcement re-rank unavailable: {exc}"

    # Narrative summary for deterministic / grounding-friendly consumers
    result["summary_text"] = _build_summary_text(result)
    return result


def _build_summary_text(result: dict[str, Any]) -> str:
    loc = result.get("location_label") or result.get("h3_cell") or "the selected area"
    pm = result.get("pm25") or {}
    ints = result.get("interventions") or []
    lines = [
        f"What-if simulation for {loc} (NOT a forecast).",
        "Interventions: " + ("; ".join(ints) if ints else "none"),
    ]
    if pm.get("baseline_pm25") is not None and pm.get("simulated_pm25") is not None:
        lines.append(
            f"Estimated PM2.5: {pm['baseline_pm25']} → {pm['simulated_pm25']} µg/m³ "
            f"(Δ {pm.get('delta_pm25')} µg/m³, {pm.get('delta_percent')}%). "
            f"Illustrative range {pm.get('uncertainty_low_pm25')}–{pm.get('uncertainty_high_pm25')} µg/m³."
        )
    base = result.get("baseline_source_attribution") or {}
    sim = result.get("simulated_source_attribution") or {}
    if base and sim:
        bits = []
        for k in SOURCE_KEYS:
            bits.append(f"{k} {base.get(k, 0) * 100:.0f}%→{sim.get(k, 0) * 100:.0f}%")
        lines.append("Source mix: " + ", ".join(bits) + ".")
    lines.append(SIMULATION_DISCLAIMER)
    return " ".join(lines)


def parse_scenario_text(text: str) -> dict[str, Any]:
    """Best-effort extraction of source + % from free text."""
    q = (text or "").lower()
    out: dict[str, Any] = {}

    # Map keywords → source
    source_patterns = [
        (r"construction|dust|building|site work", "construction"),
        (r"traffic|vehicles?|corridor|road|congestion", "traffic"),
        (r"industrial|industry|factory|factories|emission", "industrial"),
        (r"burning|waste fire|biomass|open burn", "burning"),
    ]
    # "reduce by 50%" / "50% reduction" / "drop by 30%" / "increase by 20%"
    pct_m = re.search(
        r"(?:reduc(?:e|es|ed|ing|tion)|drop(?:s|ped)?|cut(?:s|ting)?|decreas(?:e|es|ed|ing))"
        r"[^\d%]{0,40}?(\d{1,3})\s*%"
        r"|"
        r"(\d{1,3})\s*%\s*(?:reduc|drop|cut|less|lower|decreas)",
        q,
    )
    inc_m = re.search(
        r"(?:increas(?:e|es|ed|ing)|rais(?:e|es|ed|ing)|more enforcement on)"
        r"[^\d%]{0,40}?(\d{1,3})\s*%"
        r"|"
        r"(\d{1,3})\s*%\s*(?:increas|more|higher)",
        q,
    )
    pct = None
    if pct_m:
        pct = float(pct_m.group(1) or pct_m.group(2))
    inc_pct = None
    if inc_m and not pct_m:
        inc_pct = float(inc_m.group(1) or inc_m.group(2))

    # Default enforcement language → traffic focus if no source
    sources_hit: list[str] = []
    for pat, src in source_patterns:
        if re.search(pat, q):
            sources_hit.append(src)
    if not sources_hit and re.search(r"enforce|inspect|officer", q):
        sources_hit = ["traffic", "construction"]

    if pct is not None and sources_hit:
        for src in sources_hit:
            out[f"{src}_reduction_percent"] = min(100.0, max(0.0, pct))
    elif inc_pct is not None and sources_hit:
        for src in sources_hit:
            out[f"{src}_increase_percent"] = min(100.0, max(0.0, inc_pct))
    elif pct is not None and not sources_hit:
        # Ambiguous — assume construction (common demo case)
        out["construction_reduction_percent"] = min(100.0, max(0.0, pct))

    # "half" / "50 percent less construction"
    if re.search(r"\bhalf\b|50\s*%", q) and "construction" in q and "construction_reduction_percent" not in out:
        out["construction_reduction_percent"] = 50.0

    return out
