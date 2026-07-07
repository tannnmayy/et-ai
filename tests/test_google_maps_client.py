from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

import httpx
import pytest

from backend.app.services.google_maps_client import (
    GoogleMapsOutOfScopeError,
    GoogleMapsProviderError,
    GoogleMapsUnavailableError,
    GoogleMapsValidationError,
    compute_routes,
    geocode_address,
    resolve_place,
)


class TestGeocodeAddress:
    def test_empty_query_raises_validation_error(self) -> None:
        with pytest.raises(GoogleMapsValidationError, match="must not be empty"):
            geocode_address("")
        with pytest.raises(GoogleMapsValidationError, match="must not be empty"):
            geocode_address("   ")

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_successful_geocode(self, mock_client_class) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Bengaluru, Karnataka, India",
                    "geometry": {
                        "location": {"lat": 12.9716, "lng": 77.5946}
                    },
                    "place_id": "ChIJbU60yXAWrjsR4E9-UejD3_g",
                }
            ],
        }
        mock_client.get.return_value = mock_response

        result = geocode_address("Bengaluru")
        assert result["success"] is True
        assert result["data"]["latitude"] == 12.9716
        assert result["data"]["longitude"] == 77.5946
        assert result["data"]["label"] == "Bengaluru, Karnataka, India"

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_no_results(self, mock_client_class) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ZERO_RESULTS", "results": []}
        mock_client.get.return_value = mock_response

        result = geocode_address("asdfghjkl")
        assert result["success"] is False
        assert "No geocoding results found" in result["error"]

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", None)
    def test_missing_key_raises_unavailable(self) -> None:
        with pytest.raises(GoogleMapsUnavailableError, match="API key is not configured"):
            geocode_address("Bengaluru")

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_out_of_scope_coordinates(self, mock_client_class) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Somewhere far",
                    "geometry": {
                        "location": {"lat": 28.6139, "lng": 77.2090}
                    },
                    "place_id": "test",
                }
            ],
        }
        mock_client.get.return_value = mock_response

        result = geocode_address("Delhi")
        assert result["success"] is False
        assert result["source_status"] == "out_of_scope"

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_timeout_retry_then_unavailable(self, mock_client_class) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout", request=MagicMock())

        with pytest.raises(GoogleMapsUnavailableError, match="unavailable after"):
            geocode_address("Bengaluru")

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_http_error_raises_provider_error(self, mock_client_class) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_client.get.return_value = mock_response
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403 Forbidden", request=MagicMock(), response=mock_response
        )

        with pytest.raises(GoogleMapsProviderError, match="HTTP error"):
            geocode_address("Bengaluru")

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    def test_no_key_leaked_in_logs_or_errors(self) -> None:
        assert "test_key" not in str(geocode_address.__doc__)


class TestComputeRoutes:
    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_successful_route(self, mock_client_class) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "routes": [
                {
                    "duration": "900s",
                    "staticDuration": "850s",
                    "distanceMeters": 10000,
                    "routeLabels": ["DEFAULT_ROUTE"],
                }
            ],
        }
        mock_client.post.return_value = mock_response

        result = compute_routes(12.97, 77.59, 13.02, 77.58, "DRIVE")
        assert result["success"] is True
        assert result["data"]["distance_meters"] == 10000
        assert result["data"]["duration_seconds"] == 900
        assert result["data"]["duration_in_traffic_seconds"] is None
        assert result["data"]["travel_mode"] == "DRIVE"

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_no_routes_found(self, mock_client_class) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {"routes": []}
        mock_client.post.return_value = mock_response

        result = compute_routes(12.97, 77.59, 13.02, 77.58, "DRIVE")
        assert result["success"] is False
        assert "No routes returned" in result["error"]

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_timeout_retry_then_unavailable(self, mock_client_class) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("timeout", request=MagicMock())

        with pytest.raises(GoogleMapsUnavailableError, match="unavailable after"):
            compute_routes(12.97, 77.59, 13.02, 77.58, "DRIVE")

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", None)
    def test_missing_key_raises_unavailable(self) -> None:
        with pytest.raises(GoogleMapsUnavailableError, match="API key is not configured"):
            compute_routes(12.97, 77.59, 13.02, 77.58, "DRIVE")

    def test_out_of_scope_coordinates(self) -> None:
        with pytest.raises(GoogleMapsOutOfScopeError, match="outside Bengaluru bounds"):
            compute_routes(28.61, 77.23, 12.97, 77.59, "DRIVE")

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_v2_request_shape(self, mock_client_class) -> None:
        """Assert exact URL, method, headers, and body shape."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "routes": [
                {
                    "duration": "600s",
                    "distanceMeters": 5000,
                }
            ],
        }
        mock_client.post.return_value = mock_response

        compute_routes(12.97, 77.59, 13.02, 77.58, "DRIVE")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        url = call_args[0][0]
        kwargs = call_args[1]

        assert url == "https://routes.googleapis.com/directions/v2:computeRoutes"
        assert kwargs["headers"]["X-Goog-Api-Key"] == "test_key"
        assert "routes.duration,routes.distanceMeters" in kwargs["headers"]["X-Goog-FieldMask"]
        assert kwargs["json"]["travelMode"] == "DRIVE"
        assert kwargs["json"]["routingPreference"] == "TRAFFIC_AWARE"
        assert kwargs["json"]["origin"]["location"]["latLng"]["latitude"] == 12.97
        assert kwargs["json"]["origin"]["location"]["latLng"]["longitude"] == 77.59
        assert kwargs["json"]["destination"]["location"]["latLng"]["latitude"] == 13.02
        assert kwargs["json"]["destination"]["location"]["latLng"]["longitude"] == 77.58

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_v2_two_wheeler_maps_to_drive(self, mock_client_class) -> None:
        """TWO_WHEELER uses DRIVE mode in Routes API v2."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "routes": [
                {
                    "duration": "300s",
                    "distanceMeters": 2000,
                }
            ],
        }
        mock_client.post.return_value = mock_response

        result = compute_routes(12.97, 77.59, 13.02, 77.58, "TWO_WHEELER")
        assert result["success"] is True
        assert "two-wheeler" in result["data"]["limitations"][-1].lower()

        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["travelMode"] == "DRIVE"

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_v2_permission_denied_error(self, mock_client_class) -> None:
        """Google v2 permission-denied error is parsed and raised as GoogleMapsProviderError."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 403
        error_body = {
            "error": {
                "code": 403,
                "message": "API key not authorized. Enable Routes API in Google Cloud Console.",
                "status": "PERMISSION_DENIED",
            }
        }
        mock_response.json.return_value = error_body
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403 Forbidden", request=MagicMock(), response=mock_response
        )
        mock_client.post.return_value = mock_response

        with pytest.raises(GoogleMapsProviderError) as exc_info:
            compute_routes(12.97, 77.59, 13.02, 77.58, "DRIVE")

        assert "PERMISSION_DENIED" in str(exc_info.value)
        assert exc_info.value.status_code == 403

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_v2_missing_duration_or_distance(self, mock_client_class) -> None:
        """Routes v2 response missing duration or distanceMeters returns error."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "routes": [{"routeLabels": ["DEFAULT_ROUTE"]}]
        }
        mock_client.post.return_value = mock_response

        result = compute_routes(12.97, 77.59, 13.02, 77.58, "DRIVE")
        assert result["success"] is False
        assert "missing duration or distance" in result["error"]

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_v2_walk_mode(self, mock_client_class) -> None:
        """WALK mode sends WALK in the v2 body."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "routes": [{"duration": "1200s", "distanceMeters": 1000}]
        }
        mock_client.post.return_value = mock_response

        compute_routes(12.97, 77.59, 13.02, 77.58, "WALK")
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["travelMode"] == "WALK"


class TestParseDuration:
    def test_standard_duration(self) -> None:
        from backend.app.services.google_maps_client import _parse_duration_string
        assert _parse_duration_string("900s") == 900

    def test_zero_duration(self) -> None:
        from backend.app.services.google_maps_client import _parse_duration_string
        assert _parse_duration_string("0s") == 0

    def test_large_duration(self) -> None:
        from backend.app.services.google_maps_client import _parse_duration_string
        assert _parse_duration_string("3600s") == 3600

    def test_missing_suffix(self) -> None:
        from backend.app.services.google_maps_client import _parse_duration_string
        assert _parse_duration_string("900") is None

    def test_non_numeric(self) -> None:
        from backend.app.services.google_maps_client import _parse_duration_string
        assert _parse_duration_string("abc") is None
        assert _parse_duration_string("") is None

    def test_non_string(self) -> None:
        from backend.app.services.google_maps_client import _parse_duration_string
        assert _parse_duration_string(None) is None  # type: ignore[arg-type]
        assert _parse_duration_string(900) is None  # type: ignore[arg-type]


class TestRoutesV2ErrorParsing:
    def test_parse_standard_error(self) -> None:
        from backend.app.services.google_maps_client import _parse_routes_v2_error
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": {
                "code": 403,
                "message": "Routes API is not enabled.",
                "status": "PERMISSION_DENIED",
            }
        }
        error_msg = _parse_routes_v2_error(mock_response)
        assert "PERMISSION_DENIED" in error_msg
        assert "(403)" in error_msg

    def test_parse_unparseable_body(self) -> None:
        from backend.app.services.google_maps_client import _parse_routes_v2_error
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("not json")
        mock_response.status_code = 500
        error_msg = _parse_routes_v2_error(mock_response)
        assert "500" in error_msg


class TestResolvePlace:
    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_PLACES_ENABLED", False)
    def test_places_disabled_by_default(self) -> None:
        with pytest.raises(GoogleMapsUnavailableError, match="disabled"):
            resolve_place("Some place")

    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_PLACES_ENABLED", True)
    @patch("backend.app.services.google_maps_client.GOOGLE_MAPS_SERVER_API_KEY", "test_key")
    @patch("backend.app.services.google_maps_client.httpx.Client")
    def test_places_success(self, mock_client_class) -> None:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "OK",
            "candidates": [
                {
                    "name": "Test Place",
                    "formatted_address": "Test Address, Bengaluru",
                    "geometry": {"location": {"lat": 12.97, "lng": 77.59}},
                    "place_id": "test_place_id",
                }
            ],
        }
        mock_client.get.return_value = mock_response

        result = resolve_place("Test Place")
        assert result["success"] is True
        assert result["data"]["label"] == "Test Place"
