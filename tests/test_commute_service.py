from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.services.commute_service import compute_commute_burden
from backend.app.services.google_maps_client import GoogleMapsUnavailableError


class TestComputeCommuteBurden:
    @patch("backend.app.services.commute_service.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.commute_service.compute_routes")
    def test_successful_commute(self, mock_routes) -> None:
        mock_routes.return_value = {
            "success": True,
            "data": {
                "distance_meters": 10000,
                "duration_seconds": 900,
                "duration_in_traffic_seconds": None,
                "travel_mode": "DRIVE",
                "provider_status": "OK",
                "source_status": "fresh",
                "obtained_at": "2026-01-01T00:00:00+00:00",
                "limitations": ["No traffic data"],
            },
        }
        result = compute_commute_burden(
            origin_lat=12.97, origin_lng=77.59,
            workplace_lat=13.02, workplace_lng=77.58,
            travel_mode="DRIVE",
        )
        assert result["commute_available"] is True
        assert result["total_commute_burden_score"] is not None
        assert len(result["routes"]) == 1

    @patch("backend.app.services.commute_service.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.commute_service.compute_routes")
    def test_commute_with_schools(self, mock_routes) -> None:
        mock_routes.return_value = {
            "success": True,
            "data": {
                "distance_meters": 5000,
                "duration_seconds": 600,
                "duration_in_traffic_seconds": None,
                "travel_mode": "DRIVE",
                "provider_status": "OK",
                "source_status": "fresh",
                "obtained_at": "2026-01-01T00:00:00+00:00",
                "limitations": [],
            },
        }
        schools = [
            {"latitude": 12.95, "longitude": 77.60, "label": "School A"},
            {"latitude": 12.98, "longitude": 77.62, "label": "School B"},
        ]
        result = compute_commute_burden(
            origin_lat=12.97, origin_lng=77.59,
            workplace_lat=13.02, workplace_lng=77.58,
            travel_mode="DRIVE",
            school_locations=schools,
        )
        assert result["commute_available"] is True
        assert len(result["routes"]) == 3  # workplace + 2 schools

    @patch("backend.app.services.commute_service.GOOGLE_MAPS_SERVER_API_KEY", None)
    def test_no_key_returns_unavailable(self) -> None:
        result = compute_commute_burden(
            origin_lat=12.97, origin_lng=77.59,
            workplace_lat=13.02, workplace_lng=77.58,
        )
        assert result["commute_available"] is False
        assert result["total_commute_burden_score"] is None

    @patch("backend.app.services.commute_service.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.commute_service.compute_routes")
    def test_partial_route_failure(self, mock_routes) -> None:
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "success": True,
                    "data": {
                        "distance_meters": 10000,
                        "duration_seconds": 900,
                        "duration_in_traffic_seconds": None,
                        "travel_mode": "DRIVE",
                        "provider_status": "OK",
                        "source_status": "fresh",
                        "obtained_at": "2026-01-01T00:00:00+00:00",
                        "limitations": [],
                    },
                }
            return {
                "success": False,
                "error": "No route found.",
                "data": {},
            }
        mock_routes.side_effect = side_effect

        schools = [{"latitude": 12.95, "longitude": 77.60, "label": "School A"}]
        result = compute_commute_burden(
            origin_lat=12.97, origin_lng=77.59,
            workplace_lat=13.02, workplace_lng=77.58,
            school_locations=schools,
        )
        assert result["commute_available"] is True
        assert result["partial_assessment"] is True

    @patch("backend.app.services.commute_service.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.commute_service.compute_routes")
    def test_no_fabricated_commute_values(self, mock_routes) -> None:
        mock_routes.side_effect = GoogleMapsUnavailableError("API unavailable")
        result = compute_commute_burden(
            origin_lat=12.97, origin_lng=77.59,
            workplace_lat=13.02, workplace_lng=77.58,
        )
        assert result["commute_available"] is False
        assert result["total_commute_burden_score"] is None
