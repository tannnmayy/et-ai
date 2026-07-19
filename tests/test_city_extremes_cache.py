"""Short TTL cache for get_city_extremes (Landing warm → Map open)."""

from __future__ import annotations

from unittest.mock import patch

from backend.app.services import attribution_service as attr


def test_extremes_cache_roundtrip_without_full_compute():
    attr._EXTREMES_CACHE.clear()
    key = ("bengaluru", 30, "global_worst", 0, None)
    payload = {
        "city": "bengaluru",
        "best": [{"h3_cell": "a", "attribution_confidence_score": 99}],
        "worst": [{"h3_cell": "b"}],
        "mode": "global_worst",
    }
    attr._extremes_cache_set(key, payload)
    hit = attr._extremes_cache_get(key)
    assert hit is not None
    assert hit["city"] == "bengaluru"
    assert hit["best"][0]["h3_cell"] == "a"


def test_extremes_cache_expires():
    attr._EXTREMES_CACHE.clear()
    key = ("bengaluru", 30, "global_worst", 0, None)
    attr._extremes_cache_set(key, {"city": "bengaluru", "best": [], "worst": []})
    ts, payload = attr._EXTREMES_CACHE[key]
    attr._EXTREMES_CACHE[key] = (ts - attr._EXTREMES_CACHE_TTL_S - 5, payload)
    assert attr._extremes_cache_get(key) is None


def test_get_city_extremes_returns_cache_hit_flag():
    attr._EXTREMES_CACHE.clear()
    fake = {
        "city": "bengaluru",
        "mode": "global_worst",
        "best": [{"h3_cell": "c", "attribution_confidence_score": 40}],
        "worst": [{"h3_cell": "d", "risk_confidence_factor": 0.5}],
        "total_hexagons_with_data": 1,
        "total_hexagons_in_grid": 1,
        "cache_hit": False,
    }
    # Cache key must match get_city_extremes: (city, n_eff, ranking_engine, peak_k_eff, hour)
    key = ("bengaluru", 30, "global_worst", 0, None)
    attr._extremes_cache_set(key, fake)

    with patch.object(attr, "_load_hexagon_features") as mock_load:
        out = attr.get_city_extremes(
            city="bengaluru", n=30, mode="global_worst", peak_k=10
        )
        mock_load.assert_not_called()
    assert out.get("cache_hit") is True
    assert out.get("mode") == "global_worst"
    # Confidence stripped on cache hit path
    assert "attribution_confidence_score" not in (out.get("best") or [{}])[0]
    assert "risk_confidence_factor" not in (out.get("worst") or [{}])[0]
