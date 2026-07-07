from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.services.location_service import resolve_location


class TestResolveLocation:
    def test_blank_input_returns_error(self) -> None:
        result = resolve_location()
        assert result["success"] is False
        assert "provided" in result["error"]

    def test_direct_coordinates_work(self) -> None:
        result = resolve_location(latitude=12.97, longitude=77.59)
        assert result["success"] is True
        assert result["resolution_method"] == "direct_coordinates"
        assert result["latitude"] == 12.97
        assert result["longitude"] == 77.59

    def test_coordinates_outside_bengaluru_bounds(self) -> None:
        result = resolve_location(latitude=28.61, longitude=77.23)
        assert result["success"] is False
        assert result["source_status"] == "out_of_scope"

    def test_direct_coordinates_work_without_google_key(self) -> None:
        with patch("backend.app.services.location_service.GOOGLE_MAPS_SERVER_API_KEY", None):
            result = resolve_location(latitude=12.97, longitude=77.59)
            assert result["success"] is True
            assert result["resolution_method"] == "direct_coordinates"

    @patch("backend.app.services.location_service.GOOGLE_MAPS_SERVER_API_KEY", None)
    def test_free_text_fails_without_key(self) -> None:
        result = resolve_location(query="Jayanagar, Bengaluru")
        assert result["success"] is False
        assert "key is not configured" in result["error"]

    @patch("backend.app.services.location_service.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.location_service.geocode_address")
    def test_free_text_with_key(self, mock_geocode) -> None:
        mock_geocode.return_value = {
            "success": True,
            "provider_status": "OK",
            "source_status": "fresh",
            "data": {
                "label": "Jayanagar, Bengaluru, Karnataka, India",
                "latitude": 12.93,
                "longitude": 77.59,
                "formatted_address": "Jayanagar, Bengaluru, Karnataka, India",
                "place_id": "test",
            },
        }
        result = resolve_location(query="Jayanagar")
        assert result["success"] is True
        assert result["resolution_method"] == "geocoding"
        assert result["latitude"] == 12.93
