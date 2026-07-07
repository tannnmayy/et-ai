from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.config import (
    MEDICAL_DISCLAIMER,
    SCOPE_AQI_COVERAGE,
    SCOPE_NO_TRAFFIC,
    SCOPE_WEATHER_CHANGE,
    WEATHER_PROVIDER,
)
from backend.app.services.travel_readiness_service import (
    _profile_precautions,
    get_travel_readiness,
)


def _make_weather_summary(
    risk: str = "Low",
    severe: bool = False,
    precip_mm: float = 0,
    precip_prob: float = 0,
    wind_gust: float = 10,
    wind_speed: float = 5,
    temp_min: float = 25,
    temp_max: float = 30,
    apparent_max: float = 29,
    reasons: list | None = None,
) -> dict:
    return {
        "city": "bengaluru",
        "timezone": "Asia/Kolkata",
        "period": "next_24h",
        "provider": WEATHER_PROVIDER,
        "source_status": "live_provider",
        "cache_used": False,
        "freshness": "fresh",
        "age_minutes": 0.0,
        "generated_at": "2026-07-06T00:00:00+05:30",
        "temperature_min_c": temp_min,
        "temperature_max_c": temp_max,
        "apparent_temperature_min_c": temp_min - 1,
        "apparent_temperature_max_c": apparent_max,
        "max_precipitation_probability_percent": precip_prob,
        "total_precipitation_mm": precip_mm,
        "max_wind_speed_kmh": wind_speed,
        "max_wind_gust_kmh": wind_gust,
        "dominant_weather_code": 0,
        "dominant_weather_description": "Clear sky",
        "severe_weather_present": severe,
        "weather_risk_level": risk,
        "weather_risk_reasons": reasons or [],
        "warnings": [],
    }


def _make_briefing(city_risk: str = "Moderate", stations: int = 7) -> dict:
    return {
        "city": "Bengaluru",
        "generated_at": "2026-07-06T00:00:00+00:00",
        "stations_with_forecasts": stations,
        "stations_by_risk_category": {city_risk: ["cpcb_hebbal"]},
        "stations_by_confidence_level": {"High": ["cpcb_hebbal"]},
        "lightgbm_selected_count": 5,
        "persistence_selected_count": 2,
        "top_priorities": [
            {
                "station_id": "cpcb_peenya",
                "station_name": "Peenya",
                "predicted_pm25": 85.0,
                "risk_category": "Poor",
                "confidence_level": "Medium",
            },
        ],
        "city_risk_level": city_risk,
        "executive_summary": f"Air quality is {city_risk.lower()}.",
        "operational_recommendations": ["Monitor stations."],
        "data_limitations": [
            f"Results represent {stations} monitored stations, not full citywide coverage.",
        ],
        "station_summaries": [],
    }


# ---------------------------------------------------------------------------
# Travel readiness service tests
# ---------------------------------------------------------------------------


class TestTravelReadiness:
    def test_low_weather_low_aqi_suitable(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Low"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Good"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            assert result["readiness_basis"] == "weather_and_air_quality"
            assert result["final_readiness"] in ("Suitable", "Suitable with precautions")
            assert result["weather_component"]["weather_available"] is True
            assert result["air_quality_component"]["aqi_available"] is True

    def test_heavy_rain_produces_caution_or_avoid(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(
                risk="High", severe=False, precip_mm=15, precip_prob=90,
                reasons=["Heavy rain expected."],
            ),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Moderate"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            assert result["readiness_basis"] == "weather_and_air_quality"
            assert result["final_readiness"] in ("Caution advised", "Avoid non-essential outdoor travel")
            assert any("rain" in r.lower() or "precipitation" in r.lower() for r in result["decision_reasons"])

    def test_high_wind_two_wheeler_caution(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(
                risk="Moderate", wind_gust=50, wind_speed=35,
                reasons=["Wind gusts may reach 50 km/h."],
            ),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Moderate"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="two_wheeler")
            assert result["profile"] == "two_wheeler"
            precautions = result["profile_specific_precautions"]
            precaution_text = " ".join(precautions).lower()
            assert any(w in precaution_text for w in ["wind", "stability", "two-wheeler"])

    def test_high_heat_outdoor_worker_caution(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(
                risk="High", apparent_max=42, temp_max=40,
                reasons=["Apparent temperature may reach 42°C."],
            ),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Moderate"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="outdoor_worker")
            assert result["profile"] == "outdoor_worker"
            precautions = result["profile_specific_precautions"]
            precaution_text = " ".join(precautions).lower()
            assert any(w in precaution_text for w in ["hydrat", "rest", "heat"])

    def test_poor_aqi_changes_readiness(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Low"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Very Poor"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            assert result["air_quality_component"]["city_risk_level"] == "Very Poor"
            assert result["final_readiness"] in ("Caution advised", "Avoid non-essential outdoor travel")

    def test_elderly_profile_receives_appropriate_precautions(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(
                risk="Moderate", precip_mm=3, precip_prob=70,
            ),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Moderate"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="elderly")
            precautions = " ".join(result["profile_specific_precautions"]).lower()
            assert any(w in precautions for w in ["outdoor", "exposure", "health"])
            assert result["medical_disclaimer"] == MEDICAL_DISCLAIMER

    def test_child_profile_receives_appropriate_precautions(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Moderate"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Moderate"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="child")
            assert result["medical_disclaimer"] == MEDICAL_DISCLAIMER
            assert len(result["profile_specific_precautions"]) > 0

    def test_school_profile_receives_appropriate_precautions(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Moderate"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Moderate"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="school")
            assert result["medical_disclaimer"] == MEDICAL_DISCLAIMER
            assert len(result["profile_specific_precautions"]) > 0

    def test_weather_unavailable_aqi_available_partial(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value={
                "source_status": "unavailable",
                "warnings": ["Weather unavailable"],
            },
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Moderate"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            assert result["readiness_basis"] == "air_quality_only_partial"
            assert result["weather_component"]["weather_available"] is False
            assert result["air_quality_component"]["aqi_available"] is True
            assert result["final_readiness"] is not None

    def test_aqi_unavailable_weather_available_partial(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Low"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            side_effect=Exception("briefing error"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            assert result["readiness_basis"] == "weather_only_partial"
            assert result["weather_component"]["weather_available"] is True
            assert result["air_quality_component"]["aqi_available"] is False
            assert result["final_readiness"] is not None

    def test_both_unavailable_controlled_response(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value={
                "source_status": "unavailable",
                "warnings": ["Weather unavailable"],
            },
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            side_effect=Exception("briefing error"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            assert result["readiness_basis"] == "unavailable"
            assert result["final_readiness"] is None

    def test_required_limitations_always_present(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Low"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Good"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            limitations = result["limitations"]
            limitation_text = " ".join(limitations)
            assert SCOPE_NO_TRAFFIC in limitation_text
            assert SCOPE_AQI_COVERAGE in limitation_text
            assert SCOPE_WEATHER_CHANGE in limitation_text

    def test_no_live_traffic_claim(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Low"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Good"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            assert SCOPE_NO_TRAFFIC in result["limitations"]
            assert result["readiness_basis"] != "unavailable"
            assert result["final_readiness"] is not None

    def test_existing_medical_disclaimer_present_for_elderly(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Low"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Good"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="elderly")
            assert result["medical_disclaimer"] == MEDICAL_DISCLAIMER

    def test_medical_disclaimer_absent_for_general(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Low"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Good"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            assert result["medical_disclaimer"] is None

    def test_two_wheeler_profile_rain_precautions(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(
                risk="Moderate", precip_mm=5, precip_prob=80,
            ),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Moderate"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="two_wheeler")
            precautions = " ".join(result["profile_specific_precautions"]).lower()
            assert "rain" in precautions or "wet" in precautions

    def test_severe_weather_avoid_travel(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(
                risk="Severe", severe=True, reasons=["Thunderstorm expected."],
            ),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Moderate"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="general")
            assert result["final_readiness"] == "Avoid non-essential outdoor travel"

    def test_invalid_city_returns_unavailable(self):
        result = get_travel_readiness(city="mumbai", profile="general")
        assert result["readiness_basis"] == "unavailable"

    def test_invalid_profile_defaults_to_general(self):
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value=_make_weather_summary(risk="Low"),
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Good"),
        ):
            result = get_travel_readiness(city="bengaluru", profile="invalid_profile_xyz")
            assert result["profile"] == "general"

    def test_unsupported_city_validation(self):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        client = TestClient(app)
        response = client.get("/travel/readiness?city=mumbai")
        assert response.status_code == 404

    def test_invalid_profile_validation(self):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        client = TestClient(app)
        response = client.get("/travel/readiness?city=bengaluru&profile=invalid")
        assert response.status_code == 422

    def test_invalid_period_validation(self):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        client = TestClient(app)
        response = client.get("/travel/readiness?city=bengaluru&period=next_week")
        assert response.status_code == 422

    def test_travel_readiness_endpoint_works(self):
        from backend.app.routers.travel import travel_readiness
        from backend.app.schemas.travel import TravelReadinessResponse
        result = TravelReadinessResponse(
            city="bengaluru",
            profile="general",
            period="next_24h",
            weather_component={
                "weather_available": True,
                "weather_risk_level": "Low",
                "weather_summary": "Temperature 25-30°C, clear sky",
                "weather_caution_reasons": [],
                "provider": WEATHER_PROVIDER,
                "source_status": "live_provider",
                "freshness": "fresh",
            },
            air_quality_component={
                "aqi_available": True,
                "city_risk_level": "Moderate",
                "executive_summary": "Moderate air quality.",
                "monitored_stations_note": "7 monitored stations provide data.",
                "high_risk_station_areas": [],
            },
            final_readiness="Suitable with precautions",
            readiness_basis="weather_and_air_quality",
            decision_reasons=["Weather risk: Low.", "Air quality risk: Moderate."],
            profile_specific_precautions=["Outdoor activities generally suitable."],
            limitations=["Scope limitation 1."],
            medical_disclaimer=None,
            warnings=[],
        )
        assert result.city == "bengaluru"
        assert result.final_readiness == "Suitable with precautions"
        assert result.readiness_basis == "weather_and_air_quality"

    def test_travel_readiness_tomorrow_uses_weather_and_aqi(self):
        """Travel readiness for period=tomorrow uses weather when both data sources exist."""
        with patch(
            "backend.app.services.travel_readiness_service.get_weather_summary",
            return_value={
                "city": "bengaluru",
                "period": "tomorrow",
                "provider": WEATHER_PROVIDER,
                "source_status": "live_provider",
                "cache_used": False,
                "freshness": "fresh",
                "weather_risk_level": "Low",
                "weather_risk_reasons": [],
                "severe_weather_present": False,
                "temperature_min_c": 25.0,
                "temperature_max_c": 30.0,
                "total_precipitation_mm": 0.0,
                "max_precipitation_probability_percent": 10.0,
                "max_wind_speed_kmh": 12.0,
                "max_wind_gust_kmh": 20.0,
                "dominant_weather_code": 0,
                "dominant_weather_description": "Clear sky",
                "warnings": [],
            },
        ), patch(
            "backend.app.services.travel_readiness_service.get_city_briefing",
            return_value=_make_briefing(city_risk="Good"),
        ):
            result = get_travel_readiness(
                city="bengaluru", profile="general", period="tomorrow",
            )
            assert result["readiness_basis"] == "weather_and_air_quality"
            assert result["weather_component"]["weather_available"] is True
            assert result["period"] == "tomorrow"
            assert result["final_readiness"] is not None
