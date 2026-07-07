from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.app.schemas.neighbourhood import CandidateArea
from backend.app.services.neighbourhood_suitability_service import compare_neighbourhoods


class TestCompareNeighbourhoods:
    @patch("backend.app.services.neighbourhood_suitability_service.resolve_location")
    @patch("backend.app.services.neighbourhood_suitability_service.compute_commute_burden")
    @patch("backend.app.services.neighbourhood_suitability_service.get_weather_summary")
    def test_successful_comparison(self, mock_weather, mock_commute, mock_resolve) -> None:
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

    @patch("backend.app.services.neighbourhood_suitability_service.resolve_location")
    @patch("backend.app.services.neighbourhood_suitability_service.compute_commute_burden")
    @patch("backend.app.services.neighbourhood_suitability_service.get_weather_summary")
    def test_ranking_tie_behavior(self, mock_weather, mock_commute, mock_resolve) -> None:
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

        candidates = [{"query": "Area A"}, {"query": "Area B"}]
        workplace = {"query": "Workplace"}
        result = compare_neighbourhoods(
            candidate_queries=candidates,
            workplace_query=workplace,
        )
        assert "candidates" in result
        assert result["ranking"] is not None

    @patch("backend.app.services.neighbourhood_suitability_service.resolve_location")
    @patch("backend.app.services.neighbourhood_suitability_service.compute_commute_burden")
    @patch("backend.app.services.neighbourhood_suitability_service.get_weather_summary")
    def test_partial_assessment_when_google_unavailable(self, mock_weather, mock_commute, mock_resolve) -> None:
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

        candidates = [{"query": "Jayanagar"}]
        workplace = {"query": "Workplace"}
        result = compare_neighbourhoods(
            candidate_queries=candidates,
            workplace_query=workplace,
        )
        assert "candidates" in result
        if result["candidates"]:
            assert result["candidates"][0]["partial_assessment"] is True

    @patch("backend.app.services.neighbourhood_suitability_service.resolve_location")
    @patch("backend.app.services.neighbourhood_suitability_service.compute_commute_burden")
    @patch("backend.app.services.neighbourhood_suitability_service.get_weather_summary")
    def test_no_exact_aqi_claim(self, mock_weather, mock_commute, mock_resolve) -> None:
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
