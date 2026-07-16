"""Post-hoc grounding check: numbers in the answer must appear in tool results."""

from __future__ import annotations

import json
import re
from typing import Any


def _flatten_numbers(obj: Any, out: set[str], floats: list[float]) -> None:
    if obj is None:
        return
    if isinstance(obj, bool):
        return
    if isinstance(obj, int):
        out.add(str(obj))
        out.add(f"{obj:.1f}")
        floats.append(float(obj))
        return
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return
        floats.append(float(obj))
        out.add(str(int(obj)) if abs(obj - int(obj)) < 1e-6 else f"{obj:.1f}")
        out.add(f"{obj:.0f}")
        out.add(f"{obj:.1f}")
        out.add(f"{obj:.2f}")
        # Fraction → percent forms (0.587 → 59, 58.7, 59%)
        if 0 < abs(obj) <= 1.0001:
            pct = obj * 100.0
            floats.append(pct)
            out.add(str(int(round(pct))))
            out.add(f"{pct:.0f}")
            out.add(f"{pct:.1f}")
            # Nearby rounded percents (58.7 → 58, 59, 60)
            for delta in (-2, -1, 0, 1, 2):
                out.add(str(int(round(pct)) + delta))
        # Already a percent-like value 1–100
        if 1 < abs(obj) <= 100:
            for delta in (-2, -1, 0, 1, 2):
                out.add(str(int(round(obj)) + delta))
        return
    if isinstance(obj, str):
        for m in re.findall(r"\d+(?:\.\d+)?", obj):
            out.add(m)
            if "." in m:
                out.add(m.split(".")[0])
            try:
                floats.append(float(m))
            except ValueError:
                pass
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out, floats)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            _flatten_numbers(v, out, floats)


def extract_answer_numbers(text: str) -> list[str]:
    """Extract numeric tokens that look like claims (skip years 20xx)."""
    if not text:
        return []
    found: list[str] = []
    for m in re.finditer(r"\b(\d{1,4}(?:\.\d+)?)\b", text):
        tok = m.group(1)
        if re.fullmatch(r"20\d{2}", tok):
            continue
        found.append(tok)
    return found


def _number_matches_tools(claim: float, tool_floats: list[float], allowed_str: set[str]) -> bool:
    """Exact string, absolute tolerance, or percent-style rounding band."""
    c_str = str(int(claim)) if abs(claim - int(claim)) < 1e-9 else f"{claim:.1f}"
    if c_str in allowed_str or str(claim) in allowed_str:
        return True
    if f"{claim:.0f}" in allowed_str or f"{claim:.1f}" in allowed_str:
        return True

    for t in tool_floats:
        # Tight absolute for small values (PM2.5 style)
        if abs(t - claim) <= 0.15:
            return True
        # Relative / rounding for larger magnitudes
        # e.g. tool 58.7, answer "approximately 60"
        tol = max(1.5, abs(t) * 0.05)  # 5% or ±1.5
        if abs(t - claim) <= tol:
            return True
        # Fraction tool vs percent answer (0.587 vs 59)
        if 0 < abs(t) <= 1.0001:
            pct = t * 100.0
            if abs(pct - claim) <= max(2.0, pct * 0.05):
                return True
        # Percent tool vs fraction answer (rare)
        if 1 < abs(t) <= 100 and 0 < abs(claim) <= 1.0001:
            if abs(t - claim * 100.0) <= max(2.0, t * 0.05):
                return True
    return False


def check_answer_grounding(
    answer: str,
    tool_results: dict[str, Any],
    *,
    max_unverified: int = 2,
) -> dict[str, Any]:
    """Return grounding status for audit + retry decisions.

    Numbers in the answer should match tool data via:
    - exact string forms
    - absolute ±0.15 (sensor-scale)
    - percentage rounding band (±1.5 or 5%, and ±2 on displayed %)
    Small discourse integers 1–10 are allowed without a tool match.
    """
    allowed: set[str] = set()
    tool_floats: list[float] = []
    _flatten_numbers(tool_results, allowed, tool_floats)
    try:
        blob = json.dumps(tool_results, default=str)
        for m in re.findall(r"\d+(?:\.\d+)?", blob):
            allowed.add(m)
            if "." in m:
                allowed.add(m.split(".")[0])
            try:
                tool_floats.append(float(m))
            except ValueError:
                pass
    except Exception:
        pass

    claims = extract_answer_numbers(answer)
    if not claims:
        return {
            "passed": True,
            "reason": "no_numeric_claims",
            "claims": [],
            "unverified": [],
            "verified": [],
        }

    if not allowed and not tool_floats and claims:
        return {
            "passed": False,
            "reason": "numbers_without_tool_data",
            "claims": claims,
            "unverified": claims,
            "verified": [],
        }

    verified: list[str] = []
    unverified: list[str] = []
    for c in claims:
        ok = False
        try:
            cf = float(c)
            ok = _number_matches_tools(cf, tool_floats, allowed)
            # Discourse ranks / counts
            if not ok and cf <= 10 and "." not in c:
                ok = True
        except ValueError:
            ok = c in allowed
        (verified if ok else unverified).append(c)

    passed = len(unverified) <= max_unverified
    return {
        "passed": passed,
        "reason": "ok" if passed else "invented_numbers",
        "claims": claims,
        "unverified": unverified,
        "verified": verified,
        "allowed_sample": sorted(list(allowed))[:40],
    }


def deterministic_summary_from_tools(query: str, tool_results: dict[str, Any]) -> str:
    """Build a grounded prose answer from tool results when LLM invents numbers."""
    parts: list[str] = []
    enf = tool_results.get("get_enforcement_priority") or tool_results.get(
        "tool_get_enforcement_priority"
    )
    if isinstance(enf, dict) and enf.get("ranked_hexagons"):
        top = enf["ranked_hexagons"][:5]
        lines = []
        for i, h in enumerate(top, 1):
            name = h.get("location_name") or h.get("name") or h.get("h3_cell")
            score = h.get("priority_score")
            sa = h.get("source_attribution") or {}
            dom = max(sa, key=sa.get) if sa else "mixed"
            pm = h.get("fused_pm25")
            lines.append(
                f"{i}. {name}: priority {score}, dominant {dom}"
                + (f", PM2.5 ≈ {pm} µg/m³" if pm is not None else "")
            )
        parts.append("Top enforcement targets (hex-level):\n" + "\n".join(lines))

    for key, val in tool_results.items():
        if not isinstance(val, dict) or val.get("_tool_error"):
            continue
        if "predicted_pm25" in val or "forecast_engine" in val:
            pm = val.get("predicted_pm25")
            risk = val.get("risk_category", "Unavailable")
            sid = val.get("station_id") or val.get("station_name") or "station"
            parts.append(
                f"Forecast for {sid}: next-period PM2.5 ≈ {pm} µg/m³ ({risk})."
            )
            break

    for key, val in tool_results.items():
        if not isinstance(val, dict):
            continue
        sa = val.get("source_attribution") or (val.get("attribution") or {}).get(
            "source_attribution"
        )
        if isinstance(sa, dict) and sa:
            bits = ", ".join(
                f"{k} {float(v) * 100:.0f}%" for k, v in sa.items() if v is not None
            )
            fused = val.get("fused_pm25")
            parts.append(
                f"Source mix: {bits}."
                + (f" Fused PM2.5 ≈ {fused} µg/m³." if fused is not None else "")
            )
            break

    pol = tool_results.get("search_policy_guidance") or tool_results.get(
        "tool_search_policy_guidance"
    )
    if isinstance(pol, dict) and pol.get("results"):
        r0 = pol["results"][0]
        title = r0.get("title") or "Policy source"
        snip = (r0.get("snippet") or r0.get("excerpt") or "")[:280]
        parts.append(f"Policy guidance ({title}): {snip}")

    whatif = tool_results.get("run_whatif_scenario") or tool_results.get(
        "tool_run_whatif_scenario"
    )
    if isinstance(whatif, dict) and not whatif.get("_tool_error"):
        if whatif.get("summary_text"):
            parts.append(str(whatif["summary_text"]))
        else:
            pm = whatif.get("pm25") or {}
            if pm.get("baseline_pm25") is not None:
                parts.append(
                    f"What-if simulation: PM2.5 {pm.get('baseline_pm25')} → "
                    f"{pm.get('simulated_pm25')} µg/m³ "
                    f"(range {pm.get('uncertainty_low_pm25')}–{pm.get('uncertainty_high_pm25')}). "
                    f"{whatif.get('disclaimer') or 'Simulation only.'}"
                )

    brief = tool_results.get("get_city_briefing") or tool_results.get("tool_get_city_briefing")
    if isinstance(brief, dict) and brief.get("headline"):
        parts.append(str(brief["headline"]))

    loc = tool_results.get("resolve_location") or tool_results.get("tool_resolve_location")
    if isinstance(loc, dict) and (
        loc.get("resolved_name") or loc.get("display_name") or loc.get("label")
    ):
        name = (
            loc.get("resolved_name")
            or loc.get("display_name")
            or loc.get("locality")
            or loc.get("label")
        )
        parts.insert(0, f"Resolved location: {name}.")

    if not parts:
        return (
            "I looked up the available air-quality tools for your question but could not "
            "assemble a fully grounded numeric answer. Try naming a Bengaluru locality "
            "(e.g. Peenya, Whitefield) or ask for enforcement priorities, a city briefing, "
            "or CPCB construction-dust guidance."
        )
    parts.append(
        "Numbers above come only from live AQI Sentinel tools. "
        "Attribution and rankings are investigation aids, not legal determinations."
    )
    return " ".join(parts) if len(parts) == 1 else "\n\n".join(parts)
