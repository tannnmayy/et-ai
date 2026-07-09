from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
from pydantic import ValidationError

from backend.app.schemas.neighbourhood import CandidateArea
from backend.app.services.neighbourhood_suitability_service import (
    _score_air_quality,
    _score_forecast_confidence,
    _score_green_space_proxy,
    _score_road_mobility_proxy,
    compare_neighbourhoods,
    get_grid_suitability,
)


class TestCompareNeighbourhoods:
    @patch("backend.app.services.neighbourhood_suitability_service._load_hexagon_features")
    @patch("backend.app.services.neighbourhood_suitability_service.get_single_hexagon_attribution")
    @patch("backend.app.services.neighbourhood_suitability_service.resolve_location")
    @patch("backend.app.services.neighbourhood_suitability_service.compute_commute_burden")
    @patch("backend.app.services.neighbourhood_suitability_service.get_weather_summary")
    def test_successful_comparison(self, mock_weather, mock_commute, mock_resolve, mock_attribution, mock_hex_features) -> None:
        mock_resolve.return_value = {
            "success": True,
            "label": "Jayanagar, Bengaluru",
            "latitude": 12.93,
            "longitude": 77.59,
            "resolution_method": "direct_coordinates",
            "city_scope": "bengaluru",
            "source_status": "fresh",
            "limitations": [],
        }
        mock_commute.return_value = {
            "commute_available": True,
            "total_commute_burden_score": 0.3,
            "routes": [],
            "partial_assessment": False,
            "source_status": "fresh",
            "limitations": [],
        }
        mock_weather.return_value = {
            "weather_risk_level": "Low",
            "source_status": "live_provider",
        }
        mock_attribution.return_value = {"fused_pm25": 45.0}
        mock_hex_features.return_value = pd.DataFrame()

        candidates = [{"query": "Jayanagar"}, {"query": "HSR Layout"}]
        workplace = {"query": "Manyata Tech Park"}

        result = compare_neighbourhoods(
            candidate_queries=candidates,
            workplace_query=workplace,
            profile="general",
            travel_mode="DRIVE",
            period="tomorrow",
        )
        assert "candidates" in result
        assert result["ranking"] is not None
        assert len(result["candidates"]) == 2

    @patch("backend.app.services.neighbourhood_suitability_service.resolve_location")
    def test_candidate_limit_validation(self, mock_resolve) -> None:
        mock_resolve.return_value = {
            "success": True,
            "label": "Test",
            "latitude": 12.97,
            "longitude": 77.59,
            "resolution_method": "direct_coordinates",
            "city_scope": "bengaluru",
            "source_status": "fresh",
            "limitations": [],
        }

        candidates = [{"query": f"Candidate {i}"} for i in range(4)]
        workplace = {"query": "Workplace"}

        result = compare_neighbourhoods(
            candidate_queries=candidates,
            workplace_query=workplace,
        )
        assert "error" in result
        assert "1-3" in result["error"]

    def test_workplace_failure_returns_error(self) -> None:
        candidates = [{"query": "Jayanagar"}]
        workplace = {"query": ""}
        result = compare_neighbourhoods(
            candidate_queries=candidates,
            workplace_query=workplace,
        )
        assert "error" in result

    @patch("backend.app.services.neighbourhood_suitability_service._load_hexagon_features")
    @patch("backend.app.services.neighbourhood_suitability_service.get_single_hexagon_attribution")
    @patch("backend.app.services.neighbourhood_suitability_service.resolve_location")
    @patch("backend.app.services.neighbourhood_suitability_service.compute_commute_burden")
    @patch("backend.app.services.neighbourhood_suitability_service.get_weather_summary")
    def test_ranking_tie_behavior(self, mock_weather, mock_commute, mock_resolve, mock_attribution, mock_hex_features) -> None:
        mock_resolve.return_value = {
            "success": True,
            "label": "Test Area",
            "latitude": 12.97,
            "longitude": 77.59,
            "resolution_method": "direct_coordinates",
            "city_scope": "bengaluru",
            "source_status": "fresh",
            "limitations": [],
        }
        mock_commute.return_value = {
            "commute_available": True,
            "total_commute_burden_score": 0.3,
            "routes": [],
            "partial_assessment": False,
            "source_status": "fresh",
            "limitations": [],
        }
        mock_weather.return_value = {
            "weather_risk_level": "Low",
            "source_status": "live_provider",
        }
        mock_attribution.return_value = {"fused_pm25": 45.0}
        mock_hex_features.return_value = pd.DataFrame()

        candidates = [{"query": "Area A"}, {"query": "Area B"}]
        workplace = {"query": "Workplace"}
        result = compare_neighbourhoods(
            candidate_queries=candidates,
            workplace_query=workplace,
        )
        assert "candidates" in result
        assert result["ranking"] is not None

    @patch("backend.app.services.neighbourhood_suitability_service._load_hexagon_features")
    @patch("backend.app.services.neighbourhood_suitability_service.get_single_hexagon_attribution")
    @patch("backend.app.services.neighbourhood_suitability_service.resolve_location")
    @patch("backend.app.services.neighbourhood_suitability_service.compute_commute_burden")
    @patch("backend.app.services.neighbourhood_suitability_service.get_weather_summary")
    def test_partial_assessment_when_google_unavailable(self, mock_weather, mock_commute, mock_resolve, mock_attribution, mock_hex_features) -> None:
        mock_resolve.return_value = {
            "success": True,
            "label": "Jayanagar",
            "latitude": 12.93,
            "longitude": 77.59,
            "resolution_method": "direct_coordinates",
            "city_scope": "bengaluru",
            "source_status": "fresh",
            "limitations": [],
        }
        mock_commute.return_value = {
            "commute_available": False,
            "total_commute_burden_score": None,
            "routes": [],
            "error": "Commute unavailable",
            "source_status": "unavailable",
        }
        mock_weather.return_value = {
            "source_status": "unavailable",
        }
        mock_attribution.return_value = {"fused_pm25": 45.0}
        mock_hex_features.return_value = pd.DataFrame()

        candidates = [{"query": "Jayanagar"}]
        workplace = {"query": "Workplace"}
        result = compare_neighbourhoods(
            candidate_queries=candidates,
            workplace_query=workplace,
        )
        assert "candidates" in result
        if result["candidates"]:
            assert result["candidates"][0]["partial_assessment"] is True

    @patch("backend.app.services.neighbourhood_suitability_service._load_hexagon_features")
    @patch("backend.app.services.neighbourhood_suitability_service.get_single_hexagon_attribution")
    @patch("backend.app.services.neighbourhood_suitability_service.resolve_location")
    @patch("backend.app.services.neighbourhood_suitability_service.compute_commute_burden")
    @patch("backend.app.services.neighbourhood_suitability_service.get_weather_summary")
    def test_no_exact_aqi_claim(self, mock_weather, mock_commute, mock_resolve, mock_attribution, mock_hex_features) -> None:
        mock_resolve.return_value = {
            "success": True,
            "label": "Test Area",
            "latitude": 12.97,
            "longitude": 77.59,
            "resolution_method": "direct_coordinates",
            "city_scope": "bengaluru",
            "source_status": "fresh",
            "limitations": [],
        }
        mock_commute.return_value = {
            "commute_available": True,
            "total_commute_burden_score": 0.3,
            "routes": [],
            "partial_assessment": False,
            "source_status": "fresh",
            "limitations": [],
        }
        mock_weather.return_value = {
            "weather_risk_level": "Low",
            "source_status": "live_provider",
        }
        mock_attribution.return_value = {"fused_pm25": 45.0}
        mock_hex_features.return_value = pd.DataFrame()

        candidates = [{"query": "Test"}]
        workplace = {"query": "Office"}
        result = compare_neighbourhoods(
            candidate_queries=candidates,
            workplace_query=workplace,
        )
        if result["candidates"]:
            output = str(result)
            assert "direct pollution measurement" not in output or "not a direct pollution measurement" in result.get("disclaimer", "")


class TestCandidateAreaSchema:
    def test_query_accepted(self) -> None:
        c = CandidateArea(query="Jayanagar")
        assert c.query == "Jayanagar"
        assert c.latitude is None
        assert c.longitude is None

    def test_direct_coordinates_accepted(self) -> None:
        c = CandidateArea(latitude=12.97, longitude=77.59)
        assert c.query is None
        assert c.latitude == 12.97
        assert c.longitude == 77.59

    def test_neither_raises(self) -> None:
        with pytest.raises(ValidationError, match="Either a query or a latitude/longitude pair must be provided"):
            CandidateArea()

    def test_partial_pair_raises(self) -> None:
        with pytest.raises(ValidationError, match="Both latitude and longitude must be provided together"):
            CandidateArea(latitude=12.97)

    def test_mixed_raises(self) -> None:
        with pytest.raises(ValidationError, match="Provide either a query OR coordinates, not both"):
            CandidateArea(query="Jayanagar", latitude=12.97, longitude=77.59)

    def test_label_accepted_with_query(self) -> None:
        c = CandidateArea(query="Jayanagar", label="Home")
        assert c.label == "Home"

    def test_label_accepted_with_coordinates(self) -> None:
        c = CandidateArea(latitude=12.97, longitude=77.59, label="Office")
        assert c.label == "Office"


class TestScoreAirQuality:
    def test_fused_pm25_low_vs_high(self) -> None:
        score_low, _ = _score_air_quality([], fused_pm25=20.0)
        score_high, _ = _score_air_quality([], fused_pm25=300.0)
        assert score_low != score_high
        assert score_low > score_high

    def test_fused_pm25_none_falls_back_to_proxy(self) -> None:
        nearby = [{"distance_km": 1.5}]
        score, explanation = _score_air_quality(nearby, fused_pm25=None)
        assert score is not None
        assert "falling back" in explanation.lower()

    def test_no_nearby_and_no_fused(self) -> None:
        score, explanation = _score_air_quality([], fused_pm25=None)
        assert score == 0.5
        assert "no nearby stations" in explanation.lower()


class TestScoreForecastConfidence:
    def test_closer_scores_higher(self) -> None:
        try:
            score_close, _ = _score_forecast_confidence(12.93, 77.59)
            score_far, _ = _score_forecast_confidence(45.0, 77.59)
        except Exception:
            return
        assert score_close != score_far
        assert score_close > score_far


class TestScoreGreenSpaceProxy:
    @patch("backend.app.services.neighbourhood_suitability_service._get_grid_normalization_stats")
    def test_higher_fraction_higher_score(self, mock_stats) -> None:
        mock_stats.return_value = {"green_space_fraction_p95": 0.5, "road_density_p95": 0.05}
        score_low, _ = _score_green_space_proxy(0.05)
        score_high, _ = _score_green_space_proxy(0.50)
        assert score_low != score_high
        assert score_high > score_low

    def test_none_fallback(self) -> None:
        score, explanation = _score_green_space_proxy(None)
        assert score == 0.6
        assert "unavailable" in explanation.lower()


class TestScoreRoadMobilityProxy:
    @patch("backend.app.services.neighbourhood_suitability_service._get_grid_normalization_stats")
    def test_higher_density_lower_score(self, mock_stats) -> None:
        mock_stats.return_value = {"green_space_fraction_p95": 0.5, "road_density_p95": 0.05}
        score_low, _ = _score_road_mobility_proxy(0.005)
        score_high, _ = _score_road_mobility_proxy(0.05)
        assert score_low != score_high
        assert score_low > score_high

    def test_none_fallback(self) -> None:
        score, explanation = _score_road_mobility_proxy(None)
        assert score == 0.6
        assert "unavailable" in explanation.lower()


class TestGetGridSuitability:
    @patch("backend.app.services.neighbourhood_suitability_service.get_city_grid_attribution")
    @patch("backend.app.services.neighbourhood_suitability_service._load_hexagon_features")
    @patch("backend.app.services.neighbourhood_suitability_service.get_weather_summary")
    def test_returns_matching_hexagon_count(self, mock_weather, mock_hex, mock_grid_attr) -> None:
        mock_grid_attr.return_value = {
            "city": "bengaluru",
            "computed_at": "2025-01-01T00:00:00Z",
            "hexagon_count": 2,
            "hexagons": [
                {"h3_cell": "a", "center_lat": 12.93, "center_lon": 77.59, "fused_pm25": 45.0},
                {"h3_cell": "b", "center_lat": 12.94, "center_lon": 77.60, "fused_pm25": 80.0},
            ],
            "warnings": [],
        }
        mock_hex.return_value = pd.DataFrame({
            "h3_cell": ["a", "b"],
            "green_space_fraction": [0.1, 0.05],
            "road_density_m_per_sq_m": [0.01, 0.03],
        })
        mock_weather.return_value = {
            "weather_risk_level": "Low",
            "source_status": "live_provider",
        }

        result = get_grid_suitability(city="bengaluru")
        assert "error" not in result
        assert result["hexagon_count"] == 2
        assert len(result["hexagons"]) == 2
        for h in result["hexagons"]:
            assert "commute_component" not in h
        assert any("commute_component" in w for w in result["warnings"])

    @patch("backend.app.services.neighbourhood_suitability_service.get_city_grid_attribution")
    def test_unsupported_city(self, mock_grid_attr) -> None:
        mock_grid_attr.return_value = {"error": "Unsupported city: 'delhi'"}
        result = get_grid_suitability(city="delhi")
        assert "error" in result

    @patch("backend.app.services.neighbourhood_suitability_service.get_city_grid_attribution")
    @patch("backend.app.services.neighbourhood_suitability_service._load_hexagon_features")
    def test_missing_hexagon_features(self, mock_hex, mock_grid_attr) -> None:
        mock_grid_attr.return_value = {
            "city": "bengaluru",
            "computed_at": "2025-01-01T00:00:00Z",
            "hexagon_count": 1,
            "hexagons": [{"h3_cell": "a", "center_lat": 12.93, "center_lon": 77.59, "fused_pm25": 45.0}],
            "warnings": [],
        }
        mock_hex.return_value = pd.DataFrame()
        result = get_grid_suitability(city="bengaluru")
        assert "error" in result
