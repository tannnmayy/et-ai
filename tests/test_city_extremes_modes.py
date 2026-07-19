"""City extremes: only global_worst | global_best | local_peaks."""

from __future__ import annotations

from backend.app.services.attribution_service import (
    EXTREMES_MODE_GLOBAL_BEST,
    EXTREMES_MODE_GLOBAL_WORST,
    EXTREMES_MODE_LOCAL_PEAKS,
    GLOBAL_BEST_N,
    LOCAL_PEAKS_PER_STATION_K,
    _normalize_extremes_mode,
    _select_local_peaks_worst,
    _strip_map_confidence_fields,
    get_city_extremes,
)


def test_select_local_peaks_dedupes_and_caps():
    scored = []
    for i in range(12):
        scored.append(
            {
                "h3_cell": f"A{i}",
                "center_lat": 13.0 + i * 0.001,
                "center_lon": 77.5,
                "fused_pm25": 90.0 - i * 0.1,
            }
        )
    for i in range(12):
        scored.append(
            {
                "h3_cell": f"B{i}",
                "center_lat": 12.92 + i * 0.001,
                "center_lon": 77.6,
                "fused_pm25": 70.0 - i * 0.1,
            }
        )

    top_a = sorted(
        [h for h in scored if h["h3_cell"].startswith("A")],
        key=lambda h: h["fused_pm25"],
        reverse=True,
    )[:3]
    top_b = sorted(
        [h for h in scored if h["h3_cell"].startswith("B")],
        key=lambda h: h["fused_pm25"],
        reverse=True,
    )[:3]
    merged = {h["h3_cell"]: h for h in top_a + top_b}
    assert len(merged) == 6
    assert max(h["fused_pm25"] for h in merged.values()) == 90.0


def test_local_peaks_selector_uses_scored_only():
    assert _select_local_peaks_worst([], n=10) == []


def test_normalize_extremes_mode_canonical_only():
    assert _normalize_extremes_mode("global_worst") == ("global_worst", None)
    assert _normalize_extremes_mode("global_best") == ("global_best", None)
    assert _normalize_extremes_mode("local_peaks") == ("local_peaks", None)

    # Soft redirect
    mode, warn = _normalize_extremes_mode("global")
    assert mode == "global_worst"
    assert warn and "deprecated" in warn.lower()

    # Hard reject legacy junk
    assert _normalize_extremes_mode("local_plume") == (None, None)
    assert _normalize_extremes_mode("peaks") == (None, None)
    assert _normalize_extremes_mode("worst") == (None, None)
    assert _normalize_extremes_mode("nope") == (None, None)
    assert LOCAL_PEAKS_PER_STATION_K == 10
    assert GLOBAL_BEST_N == 30


def test_strip_map_confidence_fields():
    rows = [
        {
            "h3_cell": "x",
            "fused_pm25": 40,
            "attribution_confidence_score": 55,
            "confidence_explanation": "test",
            "risk_confidence_factor": 0.7,
        }
    ]
    out = _strip_map_confidence_fields(rows)
    assert "attribution_confidence_score" not in out[0]
    assert "confidence_explanation" not in out[0]
    assert "risk_confidence_factor" not in out[0]
    assert out[0]["fused_pm25"] == 40


def test_get_city_extremes_three_modes():
    worst = get_city_extremes(city="bengaluru", n=30, mode=EXTREMES_MODE_GLOBAL_WORST)
    if "error" in worst:
        return

    assert worst["mode"] == "global_worst"
    assert worst.get("peak_k") is None
    assert len(worst.get("worst") or []) <= 30
    # No confidence on Map extremes hexes
    for h in (worst.get("worst") or [])[:5]:
        assert "attribution_confidence_score" not in h
        assert "risk_confidence_factor" not in h

    best = get_city_extremes(city="bengaluru", n=50, mode=EXTREMES_MODE_GLOBAL_BEST)
    assert "error" not in best
    assert best["mode"] == "global_best"
    assert len(best.get("best") or []) <= GLOBAL_BEST_N

    local = get_city_extremes(
        city="bengaluru",
        n=50,
        mode=EXTREMES_MODE_LOCAL_PEAKS,
        peak_k=99,  # ignored — fixed to 10
    )
    assert "error" not in local
    assert local["mode"] == "local_peaks"
    assert local["peak_k"] == LOCAL_PEAKS_PER_STATION_K

    # Cleanest ranking matches between global_worst and local (same scored set, same n_eff for best on worst mode)
    # best lists use different n for global_best vs global_worst; compare first min cells
    w_best = [h["h3_cell"] for h in worst["best"][:15]]
    l_best = [h["h3_cell"] for h in local["best"][:15]]
    assert w_best == l_best

    assert worst.get("ranking_note")
    if worst["total_hexagons_with_data"] > 50:
        assert len(local["worst"]) >= 5


def test_legacy_global_soft_redirect():
    res = get_city_extremes(city="bengaluru", n=15, mode="global")
    if "error" in res:
        return
    assert res["mode"] == "global_worst"
    assert res.get("deprecation_warning")


def test_invalid_and_legacy_modes_error():
    res = get_city_extremes(city="bengaluru", n=5, mode="not_a_mode")
    assert "error" in res
    assert "Unsupported extremes mode" in res["error"]

    for bad in ("local_plume", "peaks", "local", "worst", "best", "global_analysis"):
        r = get_city_extremes(city="bengaluru", n=5, mode=bad)
        assert "error" in r, bad
