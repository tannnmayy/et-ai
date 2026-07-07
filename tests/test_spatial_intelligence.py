from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.services.spatial_intelligence_service import (
    get_location_intelligence,
    get_station_intelligence,
)


class TestStationIntelligence:
    def test_station_intelligence_includes_disclaimers(self) -> None:
        result = get_station_intelligence("cpcb_hebbal")
        assert "limitations" in result
        assert len(result["limitations"]) > 0

    def test_station_intelligence_has_evidence(self) -> None:
        result = get_station_intelligence("cpcb_hebbal")
        assert "station_id" in result
        assert result["station_id"] == "cpcb_hebbal"


class TestLocationIntelligence:
    def test_location_intelligence_direct_coordinates(self) -> None:
        result = get_location_intelligence(latitude=12.97, longitude=77.59)
        assert result["resolution_method"] == "direct_coordinates"
        assert len(result["nearby_stations"]) > 0
        assert result["station_evidence_proxy_note"] is not None

    def test_no_exact_aqi_prediction(self) -> None:
        result = get_location_intelligence(latitude=12.97, longitude=77.59)
        assert "predicted_pm25" not in result
        assert "risk_category" not in result
        text = str(result)
        assert "proximity-supported" in text or "proximity-supported" in result.get("station_evidence_proxy_note", "")

    def test_location_outside_bounds(self) -> None:
        result = get_location_intelligence(latitude=28.61, longitude=77.23)
        assert result["resolution_method"] == "failed"
        assert result["latitude"] is None

    def test_nearby_stations_for_bengaluru(self) -> None:
        result = get_location_intelligence(latitude=12.97, longitude=77.59)
        assert len(result["nearby_stations"]) > 0
        for s in result["nearby_stations"]:
            assert "station_id" in s
            assert "distance_km" in s
            assert s["distance_km"] > 0
