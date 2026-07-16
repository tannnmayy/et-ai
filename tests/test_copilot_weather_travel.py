from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.agents.fallback_renderer import render_travel_readiness, render_weather_forecast, render_weather_summary
from backend.app.agents.orchestrator import _detect_intent, run_orchestrator
from backend.app.agents.state import Intent
from backend.app.config import MEDICAL_DISCLAIMER, SCOPE_AQI_COVERAGE, SCOPE_NO_TRAFFIC, SCOPE_WEATHER_CHANGE

@pytest.fixture(autouse=True)
def remove_llm_keys(monkeypatch):
    from backend.app.agents.llm_provider import LLMProvider
    monkeypatch.setattr(LLMProvider, "_configured_providers", lambda self: [])
    monkeypatch.setattr(LLMProvider, "is_available", property(lambda self: False))




# ---------------------------------------------------------------------------
# Intent detection tests
# ---------------------------------------------------------------------------


class TestWeatherTravelIntentDetection:
    def test_weather_query(self):
        assert _detect_intent("What will Bengaluru weather be like tomorrow?") == Intent.weather_forecast

    def test_rain_query(self):
        assert _detect_intent("Will it rain tomorrow?") == Intent.weather_forecast

    def test_travel_outdoor_query(self):
        assert _detect_intent("Is tomorrow good for outdoor travel?") == Intent.travel_readiness

    def test_elderly_travel_query(self):
        assert _detect_intent("Can an elderly person travel outside tomorrow?") == Intent.travel_readiness

    def test_bike_query(self):
        assert _detect_intent("Should I take my bike tomorrow morning?") == Intent.travel_readiness

    def test_travel_briefing_query(self):
        assert _detect_intent("Give me a weather and air quality travel briefing.") == Intent.travel_readiness

    def test_two_wheeler_query(self):
        assert _detect_intent("Should I ride a two-wheeler tomorrow morning?") == Intent.travel_readiness

    def test_temperature_query(self):
        assert _detect_intent("What is the temperature today?") == Intent.weather_forecast


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


class TestWeatherTravelOrchestrator:
    def test_orchestrator_routes_weather_correctly(self, monkeypatch):
        monkeypatch.delenv("AQI_SENTINEL_LLM_API_KEY", raising=False)
        with patch("backend.app.agents.travel_readiness_agent.tool_get_weather_summary") as mock_summary, \
             patch("backend.app.agents.travel_readiness_agent.tool_get_travel_readiness") as mock_travel:
            mock_summary.return_value = {
                "city": "bengaluru",
                "period": "next_24h",
                "weather_risk_level": "Low",
                "weather_risk_reasons": [],
                "source_status": "live_provider",
            }
            mock_travel.return_value = {
                "city": "bengaluru",
                "profile": "general",
                "period": "next_24h",
                "readiness_basis": "weather_and_air_quality",
                "final_readiness": "Suitable",
                "weather_component": {"weather_available": True, "weather_risk_level": "Low"},
                "air_quality_component": {"aqi_available": True, "city_risk_level": "Moderate"},
                "decision_reasons": [],
                "profile_specific_precautions": [],
                "limitations": [],
                "medical_disclaimer": None,
                "warnings": [],
            }
            result = run_orchestrator(query="What is the weather like tomorrow?")
            assert result["intent"] == "weather_forecast"
            assert result["selected_agent"] == "travel_readiness_agent"
            assert result["structured_data"] is not None
            assert result["audit_trail"]["detected_intent"] == "weather_forecast"

    def test_orchestrator_routes_travel_correctly(self, monkeypatch):
        monkeypatch.delenv("AQI_SENTINEL_LLM_API_KEY", raising=False)
        with patch("backend.app.agents.travel_readiness_agent.tool_get_weather_summary") as mock_summary, \
             patch("backend.app.agents.travel_readiness_agent.tool_get_travel_readiness") as mock_travel:
            mock_summary.return_value = {
                "city": "bengaluru",
                "period": "next_24h",
                "weather_risk_level": "Low",
                "weather_risk_reasons": [],
                "source_status": "live_provider",
            }
            mock_travel.return_value = {
                "city": "bengaluru",
                "profile": "general",
                "period": "next_24h",
                "readiness_basis": "weather_and_air_quality",
                "final_readiness": "Suitable",
                "weather_component": {"weather_available": True, "weather_risk_level": "Low"},
                "air_quality_component": {"aqi_available": True, "city_risk_level": "Moderate"},
                "decision_reasons": [],
                "profile_specific_precautions": [],
                "limitations": [],
                "medical_disclaimer": None,
                "warnings": [],
            }
            result = run_orchestrator(query="Is tomorrow good for outdoor travel?")
            assert result["intent"] == "travel_readiness"
            assert result["selected_agent"] == "travel_readiness_agent"
            assert result["structured_data"] is not None

    def test_audit_trail_records_weather_tools(self, monkeypatch):
        monkeypatch.delenv("AQI_SENTINEL_LLM_API_KEY", raising=False)
        with patch("backend.app.agents.travel_readiness_agent.tool_get_weather_summary") as mock_summary, \
             patch("backend.app.agents.travel_readiness_agent.tool_get_travel_readiness") as mock_travel:
            mock_summary.return_value = {
                "city": "bengaluru",
                "period": "next_24h",
                "weather_risk_level": "Low",
                "weather_risk_reasons": [],
                "source_status": "live_provider",
                "cache_used": False,
                "freshness": "fresh",
                "age_minutes": 0.0,
                "provider": "open_meteo",
                "generated_at": "2026-07-06T00:00:00+05:30",
            }
            mock_travel.return_value = {
                "city": "bengaluru",
                "profile": "general",
                "period": "next_24h",
                "readiness_basis": "weather_and_air_quality",
                "final_readiness": "Suitable",
                "weather_component": {"weather_available": True, "weather_risk_level": "Low"},
                "air_quality_component": {"aqi_available": True, "city_risk_level": "Moderate"},
                "decision_reasons": [],
                "profile_specific_precautions": [],
                "limitations": [],
                "medical_disclaimer": None,
                "warnings": [],
            }
            result = run_orchestrator(query="What is the weather like tomorrow?")
            audit = result["audit_trail"]
            tools = [t["tool"] for t in audit["tools_called"]]
            assert "tool_get_weather_summary" in tools
            assert "tool_get_travel_readiness" in tools

    def test_deterministic_fallback_works_no_llm_key(self, monkeypatch):
        monkeypatch.delenv("AQI_SENTINEL_LLM_API_KEY", raising=False)
        with patch("backend.app.agents.travel_readiness_agent.tool_get_weather_summary") as mock_summary, \
             patch("backend.app.agents.travel_readiness_agent.tool_get_travel_readiness") as mock_travel:
            mock_summary.return_value = {
                "city": "bengaluru",
                "period": "next_24h",
                "weather_risk_level": "Low",
                "weather_risk_reasons": [],
                "source_status": "live_provider",
                "cache_used": False,
                "freshness": "fresh",
                "age_minutes": 0.0,
                "provider": "open_meteo",
                "generated_at": "2026-07-06T00:00:00+05:30",
            }
            mock_travel.return_value = {
                "city": "bengaluru",
                "profile": "general",
                "period": "next_24h",
                "readiness_basis": "weather_and_air_quality",
                "final_readiness": "Suitable",
                "weather_component": {"weather_available": True, "weather_risk_level": "Low"},
                "air_quality_component": {"aqi_available": True, "city_risk_level": "Moderate"},
                "decision_reasons": [],
                "profile_specific_precautions": [],
                "limitations": ["Limitation 1."],
                "medical_disclaimer": None,
                "warnings": [],
            }
            result = run_orchestrator(query="Is tomorrow good for outdoor travel?")
            assert result["llm_mode"] == "deterministic"
            assert result["fallback_used"] is False
            assert result["answer"] is not None
            assert len(result["answer"]) > 0


# ---------------------------------------------------------------------------
# Fallback renderer tests
# ---------------------------------------------------------------------------


class TestWeatherTravelFallbackRenderer:
    def test_render_weather_forecast(self):
        data = {
            "city": "bengaluru",
            "provider": "open_meteo",
            "source_status": "live_provider",
            "freshness": "fresh",
            "hourly": [{"timestamp_local": "2026-07-06T10:00"}, {"timestamp_local": "2026-07-06T11:00"}],
        }
        rendered = render_weather_forecast(data)
        assert "bengaluru" in rendered.lower()
        assert "open_meteo" in rendered
        assert "live_provider" in rendered

    def test_render_weather_summary(self):
        data = {
            "city": "bengaluru",
            "period": "tomorrow",
            "weather_risk_level": "Moderate",
            "temperature_min_c": 25.0,
            "temperature_max_c": 32.0,
            "total_precipitation_mm": 5.0,
            "max_wind_speed_kmh": 20.0,
            "dominant_weather_description": "Partly cloudy",
            "weather_risk_reasons": ["Rain probability reaches 70%."],
            "severe_weather_present": False,
        }
        rendered = render_weather_summary(data)
        assert "Moderate" in rendered
        assert "25" in rendered
        assert "32" in rendered

    def test_render_travel_readiness_includes_scope(self):
        data = {
            "city": "bengaluru",
            "profile": "general",
            "period": "tomorrow",
            "final_readiness": "Suitable with precautions",
            "readiness_basis": "weather_and_air_quality",
            "weather_component": {
                "weather_available": True,
                "weather_risk_level": "Low",
                "weather_summary": "Clear conditions",
            },
            "air_quality_component": {
                "aqi_available": True,
                "city_risk_level": "Moderate",
            },
            "decision_reasons": ["Weather risk: Low.", "Air quality risk: Moderate."],
            "profile_specific_precautions": ["Carry water."],
            "limitations": [SCOPE_NO_TRAFFIC, SCOPE_AQI_COVERAGE, SCOPE_WEATHER_CHANGE],
            "medical_disclaimer": None,
            "warnings": [],
        }
        rendered = render_travel_readiness(data)
        assert SCOPE_NO_TRAFFIC in rendered
        assert SCOPE_AQI_COVERAGE in rendered
        assert SCOPE_WEATHER_CHANGE in rendered
        assert "live traffic" not in rendered.lower() or SCOPE_NO_TRAFFIC in rendered

    def test_render_travel_readiness_with_disclaimer(self):
        data = {
            "city": "bengaluru",
            "profile": "elderly",
            "period": "tomorrow",
            "final_readiness": "Caution advised",
            "readiness_basis": "weather_and_air_quality",
            "weather_component": {
                "weather_available": True,
                "weather_risk_level": "Moderate",
                "weather_summary": "Rain expected",
            },
            "air_quality_component": {
                "aqi_available": True,
                "city_risk_level": "Poor",
            },
            "decision_reasons": ["Weather risk: Moderate.", "Air quality risk: Poor."],
            "profile_specific_precautions": ["Avoid outdoor exposure."],
            "limitations": [SCOPE_NO_TRAFFIC],
            "medical_disclaimer": MEDICAL_DISCLAIMER,
            "warnings": [],
        }
        rendered = render_travel_readiness(data)
        assert MEDICAL_DISCLAIMER in rendered


# ---------------------------------------------------------------------------
# Regression: existing copilot endpoints unchanged
# ---------------------------------------------------------------------------


class TestCopilotRegression:
    def test_existing_copilot_endpoints_unchanged(self):
        from backend.app.routers.copilot import copilot_query
        assert callable(copilot_query)
        from backend.app.agents.orchestrator import run_orchestrator
        assert callable(run_orchestrator)
        from backend.app.agents.fallback_renderer import render_city_briefing
        assert callable(render_city_briefing)
        from backend.app.agents.fallback_renderer import render_citizen_advisory
        assert callable(render_citizen_advisory)
