"""Unit tests for the Citizen Mode matching engine.

Uses synthetic locality vectors so scoring logic is tested independently of
the offline build artifacts.
"""

from __future__ import annotations

import pytest

from backend.app.schemas.citizen import CitizenProfile
from backend.app.services.citizen_matching_service import (
    OfficeLocationUnresolvedError,
    build_weights,
    estimate_commute_minutes,
    family_size_to_bhk_bucket,
    match_neighbourhoods,
    _score_aqi,
    _score_rent_fit,
)


def _synthetic_locality(
    name: str,
    lat: float,
    lon: float,
    *,
    aqi: float = 60.0,
    rent_2bhk: float = 40000.0,
    rent_3bhk: float = 55000.0,
    park: float = 50.0,
    hospital: float = 50.0,
    school: float = 50.0,
    noise: float = 40.0,
    construction: float = 20.0,
) -> dict:
    def _bhk(rent: float) -> dict:
        return {
            "median_rent": rent,
            "count": 20,
            "is_estimated": False,
            "source": "locality_bhk_median",
        }

    return {
        "name": name,
        "centroid_lat": lat,
        "centroid_lon": lon,
        "listing_count": 50,
        "rent": {
            "by_bhk": {
                "0": _bhk(rent_2bhk * 0.5),
                "1": _bhk(rent_2bhk * 0.7),
                "2": _bhk(rent_2bhk),
                "3": _bhk(rent_3bhk),
                "4": _bhk(rent_3bhk * 1.3),
                "5+": _bhk(rent_3bhk * 1.6),
            },
            "overall_median_rent": rent_2bhk,
            "overall_count": 50,
        },
        "environment": {
            "aqi": aqi,
            "aqi_is_estimated": False,
            "source_attribution": {
                "traffic": 0.4,
                "industrial": 0.1,
                "construction": 0.3,
                "burning": 0.2,
            },
            "park_score": park,
            "hospital_score": hospital,
            "school_score": school,
            "noise_score": noise,
            "construction_activity_score": construction,
            "metro_distance_km": None,
            "metro_data_available": False,
            "catchment_hex_count": 12,
        },
    }


# Cluster of localities around Indiranagar / Koramangala / Whitefield-ish coords
SYNTHETIC_LOCALITIES = [
    _synthetic_locality("Alpha Clean", 12.978, 77.640, aqi=40.0, rent_2bhk=35000, park=80, school=40),
    _synthetic_locality("Beta Schools", 12.975, 77.645, aqi=70.0, rent_2bhk=38000, park=30, school=95),
    _synthetic_locality("Gamma Dirty", 12.980, 77.650, aqi=150.0, rent_2bhk=30000, park=20, school=40),
    _synthetic_locality("Delta Far", 13.050, 77.750, aqi=50.0, rent_2bhk=32000, park=60, school=50),
    _synthetic_locality("Epsilon Pricey", 12.976, 77.642, aqi=55.0, rent_2bhk=90000, park=70, school=70),
]


def _base_profile(**overrides) -> CitizenProfile:
    data = {
        "rentBudget": 45000,
        "familySize": 2,
        "healthConditions": ["none"],
        "officeLocation": "Alpha Clean",  # resolves via registry exact match
        "maxCommuteMinutes": 45,
        "priorities": [],
    }
    data.update(overrides)
    return CitizenProfile(**data)


class TestHelpers:
    def test_family_size_to_bhk_bucket(self) -> None:
        assert family_size_to_bhk_bucket(1) == "1"
        assert family_size_to_bhk_bucket(2) == "2"
        assert family_size_to_bhk_bucket(4) == "3"
        assert family_size_to_bhk_bucket(8) == "5+"

    def test_rent_fit_under_and_over_budget(self) -> None:
        assert _score_rent_fit(40000, 45000) > 0.85
        assert _score_rent_fit(45000, 45000) == pytest.approx(1.0)
        assert _score_rent_fit(67500, 45000) == pytest.approx(0.0)  # 1.5×
        assert 0.0 < _score_rent_fit(50000, 45000) < 1.0

    def test_aqi_score_decreases_with_pollution(self) -> None:
        assert _score_aqi(0) == 1.0
        assert _score_aqi(100) == pytest.approx(0.5)
        assert _score_aqi(200) == 0.0
        assert _score_aqi(40) > _score_aqi(120)

    def test_commute_minutes_scales_with_distance(self) -> None:
        near = estimate_commute_minutes(12.97, 77.64, 12.98, 77.65)
        far = estimate_commute_minutes(12.97, 77.64, 13.10, 77.80)
        assert near < far
        assert near > 0

    def test_priority_weights_boost_aqi(self) -> None:
        base = build_weights(_base_profile(priorities=[]))
        boosted = build_weights(_base_profile(priorities=["low_aqi"]))
        assert boosted["aqi"] > base["aqi"]
        assert pytest.approx(sum(boosted.values()), abs=1e-6) == 1.0

    def test_health_conditions_boost_aqi(self) -> None:
        base = build_weights(_base_profile(healthConditions=["none"]))
        health = build_weights(
            _base_profile(healthConditions=["respiratory", "elderly"])
        )
        assert health["aqi"] > base["aqi"]


class TestMatchNeighbourhoods:
    def test_returns_ranked_matches_with_frontend_fields(self) -> None:
        profile = _base_profile()
        matches = match_neighbourhoods(
            profile,
            localities=SYNTHETIC_LOCALITIES,
            use_live_aqi=False,
            use_routes_refine=False,
        )

        assert len(matches) >= 1
        m = matches[0]
        assert m.rank == 1
        assert m.matchScorePercent > 0
        assert 2 <= len(m.reasons) <= 4
        fv = m.featureVector
        assert fv.aqi > 0
        assert fv.avgRentForBudgetBHK > 0
        assert fv.commuteMinutesToOffice >= 0

        # Ranks are sequential
        for i, match in enumerate(matches, start=1):
            assert match.rank == i

        # Scores non-increasing
        scores = [m.matchScorePercent for m in matches]
        assert scores == sorted(scores, reverse=True)

    def test_priority_low_aqi_changes_ranking(self) -> None:
        """Gamma Dirty has terrible AQI; Alpha Clean is clean.

        With low_aqi priority, Alpha should rank above Gamma more strongly,
        and the clean locality should outrank the dirty cheap one.
        """
        kwargs = dict(localities=SYNTHETIC_LOCALITIES, use_live_aqi=False, use_routes_refine=False)
        base_matches = match_neighbourhoods(_base_profile(priorities=[]), **kwargs)
        aqi_matches = match_neighbourhoods(_base_profile(priorities=["low_aqi"]), **kwargs)

        def rank_of(matches, name: str) -> int:
            for m in matches:
                if m.name == name:
                    return m.rank
            return 999

        assert rank_of(aqi_matches, "Alpha Clean") <= rank_of(base_matches, "Alpha Clean")
        assert rank_of(aqi_matches, "Gamma Dirty") >= rank_of(base_matches, "Gamma Dirty")
        assert rank_of(aqi_matches, "Alpha Clean") < rank_of(aqi_matches, "Gamma Dirty")

    def test_priority_schools_changes_ranking(self) -> None:
        kwargs = dict(localities=SYNTHETIC_LOCALITIES, use_live_aqi=False, use_routes_refine=False)
        base_matches = match_neighbourhoods(_base_profile(priorities=[]), **kwargs)
        school_matches = match_neighbourhoods(_base_profile(priorities=["schools"]), **kwargs)

        def rank_of(matches, name: str) -> int:
            for m in matches:
                if m.name == name:
                    return m.rank
            return 999

        assert rank_of(school_matches, "Beta Schools") <= rank_of(base_matches, "Beta Schools")

    def test_impossible_commute_returns_empty(self) -> None:
        profile = _base_profile(maxCommuteMinutes=5, officeLocation="Alpha Clean")
        far_only = [loc for loc in SYNTHETIC_LOCALITIES if loc["name"] == "Delta Far"]
        office_pin = _synthetic_locality("Alpha Clean", 12.978, 77.640)
        matches = match_neighbourhoods(
            profile,
            localities=[office_pin] + far_only,
            use_live_aqi=False,
            use_routes_refine=False,
        )
        names = {m.name for m in matches}
        assert "Delta Far" not in names

    def test_impossible_budget_and_commute_can_return_empty(self) -> None:
        """When every locality exceeds maxCommuteMinutes, return []."""
        from unittest.mock import patch

        candidates_far = [
            _synthetic_locality("Far A", 13.20, 77.80),
            _synthetic_locality("Far B", 13.21, 77.81),
        ]
        with patch(
            "backend.app.services.citizen_matching_service.resolve_office_coordinates",
            return_value={
                "success": True,
                "latitude": 12.50,
                "longitude": 77.50,
                "label": "Remote Office",
                "resolution_method": "mock",
            },
        ):
            empty = match_neighbourhoods(
                _base_profile(maxCommuteMinutes=5, officeLocation="Somewhere"),
                localities=candidates_far,
                use_live_aqi=False,
                use_routes_refine=False,
            )
        assert empty == []

    def test_hybrid_routes_refine_filters_over_limit(self) -> None:
        """Google Routes can exclude a proxy-passing locality that is actually too far."""
        from unittest.mock import patch

        near = _synthetic_locality("Near Place", 12.978, 77.640, aqi=50.0)
        # Same coords so proxy is 0 min; Routes will claim 90 min → filtered out.
        profile = _base_profile(officeLocation="Near Place", maxCommuteMinutes=45)

        def fake_routes(origin_lat, origin_lon, dest_lat, dest_lon):
            return {
                "available": True,
                "minutes": 90.0,
                "source": "google_routes",
            }

        with patch(
            "backend.app.services.citizen_matching_service._routes_commute_minutes",
            side_effect=fake_routes,
        ):
            matches = match_neighbourhoods(
                profile,
                localities=[near],
                use_live_aqi=False,
                use_routes_refine=True,
            )
        assert matches == []

    def test_hybrid_routes_refine_uses_real_minutes(self) -> None:
        from unittest.mock import patch

        near = _synthetic_locality("Near Place", 12.978, 77.640, aqi=50.0)
        profile = _base_profile(officeLocation="Near Place", maxCommuteMinutes=45)

        with patch(
            "backend.app.services.citizen_matching_service._routes_commute_minutes",
            return_value={"available": True, "minutes": 22.0, "source": "google_routes"},
        ):
            matches = match_neighbourhoods(
                profile,
                localities=[near],
                use_live_aqi=False,
                use_routes_refine=True,
            )
        assert len(matches) == 1
        assert matches[0].featureVector.commuteMinutesToOffice == 22.0
        assert any("drive" in r.lower() or "22" in r for r in matches[0].reasons)

    def test_unresolved_office_raises(self) -> None:
        profile = _base_profile(officeLocation="zzzz_not_a_real_place_xyzzy")
        with pytest.raises(OfficeLocationUnresolvedError):
            from unittest.mock import patch

            with patch(
                "backend.app.services.location_service.resolve_location",
                return_value={"success": False, "error": "not found"},
            ):
                match_neighbourhoods(
                    profile,
                    localities=SYNTHETIC_LOCALITIES,
                    use_live_aqi=False,
                    use_routes_refine=False,
                )
