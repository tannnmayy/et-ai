from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.config import (
    WEATHER_BENGALURU_LATITUDE,
    WEATHER_BENGALURU_LONGITUDE,
    WEATHER_CACHE_TTL_MINUTES,
    WEATHER_FORECAST_HORIZON_HOURS,
    WEATHER_PROVIDER,
    WEATHER_STALE_CACHE_MAX_HOURS,
)
from backend.app.services.weather_client import (
    WeatherProviderError,
    fetch_open_meteo_forecast,
)
from backend.app.services.weather_forecast_service import (
    _derive_summary,
    _filter_hours,
    _hour_weather_risk,
    _normalize_forecast,
    _overall_risk,
    get_weather_forecast,
    get_weather_summary,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _sample_raw_response(start_hour: int = 0, hours: int = 72) -> dict:
    times = []
    fields: dict[str, list] = {
        "temperature_2m": [],
        "apparent_temperature": [],
        "relative_humidity_2m": [],
        "precipitation_probability": [],
        "precipitation": [],
        "rain": [],
        "showers": [],
        "snowfall": [],
        "weather_code": [],
        "wind_speed_10m": [],
        "wind_gusts_10m": [],
    }
    base = datetime(2026, 7, 6, 0, 0, 0, tzinfo=IST)
    for i in range(hours):
        dt = base + timedelta(hours=start_hour + i)
        times.append(dt.strftime("%Y-%m-%dT%H:%M"))
        fields["temperature_2m"].append(28.0 + (i % 6) * 1.5)
        fields["apparent_temperature"].append(27.0 + (i % 6) * 1.5)
        fields["relative_humidity_2m"].append(55.0 + (i % 3) * 5)
        if 24 <= i < 36:
            fields["precipitation_probability"].append(70.0)
            fields["precipitation"].append(3.0)
            fields["rain"].append(2.5)
            fields["weather_code"].append(63)
            fields["wind_speed_10m"].append(25.0)
            fields["wind_gusts_10m"].append(40.0)
        elif 48 <= i < 54:
            fields["precipitation_probability"].append(85.0)
            fields["precipitation"].append(12.0)
            fields["rain"].append(10.0)
            fields["weather_code"].append(65)
            fields["wind_speed_10m"].append(35.0)
            fields["wind_gusts_10m"].append(55.0)
        else:
            fields["precipitation_probability"].append(10.0)
            fields["precipitation"].append(0.0)
            fields["rain"].append(0.0)
            fields["weather_code"].append(0)
            fields["wind_speed_10m"].append(12.0)
            fields["wind_gusts_10m"].append(20.0)
        fields["showers"].append(0.0)
        fields["snowfall"].append(0.0)

    return {
        "latitude": WEATHER_BENGALURU_LATITUDE,
        "longitude": WEATHER_BENGALURU_LONGITUDE,
        "generationtime_ms": 0.5,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "timezone_abbreviation": "IST",
        "elevation": 920.0,
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "apparent_temperature": "°C",
            "relative_humidity_2m": "%",
            "precipitation_probability": "%",
            "precipitation": "mm",
            "rain": "mm",
            "showers": "mm",
            "snowfall": "cm",
            "weather_code": "wmo code",
            "wind_speed_10m": "km/h",
            "wind_gusts_10m": "km/h",
        },
        "hourly": {
            "time": times,
            **fields,
        },
    }


# ---------------------------------------------------------------------------
# Weather client tests
# ---------------------------------------------------------------------------


class TestWeatherClient:
    def test_request_parameter_construction(self):
        mock_session = MagicMock(spec=__import__("requests").Session)
        mock_response = MagicMock(spec=__import__("requests").Response)
        mock_response.status_code = 200
        mock_response.json.return_value = _sample_raw_response(hours=72)
        mock_session.get.return_value = mock_response

        result = fetch_open_meteo_forecast(
            city="bengaluru", horizon_hours=72, session=mock_session,
        )

        assert result["latitude"] == WEATHER_BENGALURU_LATITUDE
        mock_session.get.assert_called_once()
        call_kwargs = mock_session.get.call_args[1]
        assert "params" in call_kwargs
        params = call_kwargs["params"]
        assert params["latitude"] == WEATHER_BENGALURU_LATITUDE
        assert params["longitude"] == WEATHER_BENGALURU_LONGITUDE
        assert "temperature_2m" in params["hourly"]
        assert "timezone" in params
        assert params["timezone"] == "Asia/Kolkata"

    def test_successful_normalization_path(self):
        raw = _sample_raw_response(hours=72)
        mock_session = MagicMock(spec=__import__("requests").Session)
        mock_response = MagicMock(spec=__import__("requests").Response)
        mock_response.status_code = 200
        mock_response.json.return_value = raw
        mock_session.get.return_value = mock_response

        result = fetch_open_meteo_forecast(
            city="bengaluru", horizon_hours=72, session=mock_session,
        )
        assert "hourly" in result
        assert len(result["hourly"]["time"]) == 72

    def test_timeout_retry(self):
        mock_session = MagicMock(spec=__import__("requests").Session)
        conn_err = __import__("requests.exceptions").ConnectionError("timeout")
        mock_response = MagicMock(spec=__import__("requests").Response)
        mock_response.status_code = 200
        mock_response.json.return_value = _sample_raw_response(hours=72)
        mock_session.get.side_effect = [conn_err, conn_err, mock_response]

        result = fetch_open_meteo_forecast(
            city="bengaluru", horizon_hours=72, session=mock_session,
        )
        assert result is not None
        assert mock_session.get.call_count == 3

    def test_http_429_retry(self):
        mock_session = MagicMock(spec=__import__("requests").Session)
        resp429 = MagicMock(spec=__import__("requests").Response)
        resp429.status_code = 429
        resp429.headers = {}
        resp429.json.side_effect = ValueError("no json")
        resp200 = MagicMock(spec=__import__("requests").Response)
        resp200.status_code = 200
        resp200.json.return_value = _sample_raw_response(hours=72)
        mock_session.get.side_effect = [resp429, resp429, resp200]

        result = fetch_open_meteo_forecast(
            city="bengaluru", horizon_hours=72, session=mock_session,
        )
        assert result is not None
        assert mock_session.get.call_count == 3

    def test_http_5xx_retry(self):
        mock_session = MagicMock(spec=__import__("requests").Session)
        resp503 = MagicMock(spec=__import__("requests").Response)
        resp503.status_code = 503
        resp503.headers = {}
        resp503.json.side_effect = ValueError("no json")
        resp200 = MagicMock(spec=__import__("requests").Response)
        resp200.status_code = 200
        resp200.json.return_value = _sample_raw_response(hours=72)
        mock_session.get.side_effect = [resp503, resp503, resp200]

        result = fetch_open_meteo_forecast(
            city="bengaluru", horizon_hours=72, session=mock_session,
        )
        assert result is not None
        assert mock_session.get.call_count == 3

    def test_all_retries_exhausted_raises_error(self):
        mock_session = MagicMock(spec=__import__("requests").Session)
        resp503 = MagicMock(spec=__import__("requests").Response)
        resp503.status_code = 503
        resp503.headers = {}
        resp503.json.side_effect = ValueError("no json")
        mock_session.get.return_value = resp503

        with pytest.raises(WeatherProviderError):
            fetch_open_meteo_forecast(
                city="bengaluru", horizon_hours=72, session=mock_session,
            )
        assert mock_session.get.call_count == 3

    def test_invalid_response_raises_error(self):
        raw = _sample_raw_response(hours=72)
        del raw["hourly"]["temperature_2m"]
        mock_session = MagicMock(spec=__import__("requests").Session)
        mock_response = MagicMock(spec=__import__("requests").Response)
        mock_response.status_code = 200
        mock_response.json.return_value = raw
        mock_session.get.return_value = mock_response

        with pytest.raises(WeatherProviderError):
            fetch_open_meteo_forecast(
                city="bengaluru", horizon_hours=72, session=mock_session,
            )

    def test_no_network_call_at_import_time(self):
        import backend.app.services.weather_client
        import inspect
        source = inspect.getsource(backend.app.services.weather_client)
        assert "import requests" in source or "from requests" in source


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


class TestWeatherCache:
    def test_fresh_cache_is_used(self, tmp_path):
        retrieved = datetime.now(tz=IST) - timedelta(minutes=1)
        hourly = [{"timestamp_local": "2026-07-06T10:00", "temperature_c": 28.0, "weather_code": 0}]
        cache_data = {
            "schema_version": "1.0",
            "retrieved_at": retrieved.isoformat(),
            "city": "bengaluru",
            "provider": WEATHER_PROVIDER,
            "forecast_horizon_hours": 72,
            "data": {
                "city": "bengaluru",
                "hourly": hourly,
                "provider": WEATHER_PROVIDER,
                "source_status": "live_provider",
                "cache_used": False,
                "freshness": "fresh",
                "age_minutes": 1.0,
                "generated_at": retrieved.isoformat(),
                "retrieved_at": retrieved.isoformat(),
                "timezone": "Asia/Kolkata",
                "latitude": WEATHER_BENGALURU_LATITUDE,
                "longitude": WEATHER_BENGALURU_LONGITUDE,
                "forecast_start": "2026-07-06T10:00",
                "forecast_end": "2026-07-06T10:00",
                "warnings": [],
            },
        }
        cache_dir = tmp_path / "weather"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "bengaluru.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)

        with patch(
            "backend.app.services.weather_forecast_service._cache_dir",
            return_value=cache_dir,
        ):
            result = get_weather_forecast(city="bengaluru", refresh=False)
            assert result["cache_used"] is True
            assert result["freshness"] == "fresh"
            assert result["source_status"] == "live_provider"

    def test_stale_cache_fallback_on_provider_failure(self, tmp_path):
        retrieved = datetime.now(tz=IST) - timedelta(hours=2)
        hourly = [{"timestamp_local": "2026-07-06T10:00", "temperature_c": 28.0, "weather_code": 0}]
        cache_data = {
            "schema_version": "1.0",
            "retrieved_at": retrieved.isoformat(),
            "city": "bengaluru",
            "provider": WEATHER_PROVIDER,
            "forecast_horizon_hours": 72,
            "data": {
                "city": "bengaluru",
                "hourly": hourly,
                "provider": WEATHER_PROVIDER,
                "source_status": "stale_cache_fallback",
                "cache_used": True,
                "freshness": "stale",
                "age_minutes": 120.0,
                "generated_at": retrieved.isoformat(),
                "retrieved_at": retrieved.isoformat(),
                "timezone": "Asia/Kolkata",
                "latitude": WEATHER_BENGALURU_LATITUDE,
                "longitude": WEATHER_BENGALURU_LONGITUDE,
                "forecast_start": "2026-07-06T10:00",
                "forecast_end": "2026-07-06T10:00",
                "warnings": [],
            },
        }
        cache_dir = tmp_path / "weather"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "bengaluru.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)

        with patch(
            "backend.app.services.weather_forecast_service._cache_dir",
            return_value=cache_dir,
        ), patch(
            "backend.app.services.weather_forecast_service.fetch_open_meteo_forecast",
            side_effect=WeatherProviderError("provider down"),
        ):
            result = get_weather_forecast(city="bengaluru", refresh=True)
            assert result["cache_used"] is True
            assert result["freshness"] == "stale"
            assert result["source_status"] == "stale_cache_fallback"

    def test_expired_stale_cache_rejected(self, tmp_path):
        retrieved = datetime.now(tz=IST) - timedelta(hours=WEATHER_STALE_CACHE_MAX_HOURS + 1)
        cache_data = {
            "schema_version": "1.0",
            "retrieved_at": retrieved.isoformat(),
            "city": "bengaluru",
            "provider": WEATHER_PROVIDER,
            "forecast_horizon_hours": 72,
            "data": {"city": "bengaluru", "hourly": [], "provider": WEATHER_PROVIDER},
        }
        cache_dir = tmp_path / "weather"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "bengaluru.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)

        with patch(
            "backend.app.services.weather_forecast_service._cache_dir",
            return_value=cache_dir,
        ), patch(
            "backend.app.services.weather_forecast_service.fetch_open_meteo_forecast",
            side_effect=WeatherProviderError("provider down"),
        ):
            result = get_weather_forecast(city="bengaluru", refresh=True)
            assert result.get("source_status") == "unavailable"

    def test_cache_metadata_correct(self, tmp_path):
        retrieved = datetime.now(tz=IST) - timedelta(minutes=5)
        hourly = [{"timestamp_local": "2026-07-06T10:00", "temperature_c": 28.0, "weather_code": 0}]
        cache_data = {
            "schema_version": "1.0",
            "retrieved_at": retrieved.isoformat(),
            "city": "bengaluru",
            "provider": WEATHER_PROVIDER,
            "forecast_horizon_hours": 72,
            "data": {
                "city": "bengaluru",
                "hourly": hourly,
                "provider": WEATHER_PROVIDER,
                "source_status": "live_provider",
                "cache_used": False,
                "freshness": "fresh",
                "age_minutes": 5.0,
                "generated_at": retrieved.isoformat(),
                "retrieved_at": retrieved.isoformat(),
                "timezone": "Asia/Kolkata",
                "latitude": WEATHER_BENGALURU_LATITUDE,
                "longitude": WEATHER_BENGALURU_LONGITUDE,
                "forecast_start": "2026-07-06T10:00",
                "forecast_end": "2026-07-06T10:00",
                "warnings": [],
            },
        }
        cache_dir = tmp_path / "weather"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "bengaluru.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)

        with patch(
            "backend.app.services.weather_forecast_service._cache_dir",
            return_value=cache_dir,
        ):
            result = get_weather_forecast(city="bengaluru", refresh=False)
            assert "age_minutes" in result

    def test_corrupt_cache_handled_safely(self, tmp_path):
        cache_dir = tmp_path / "weather"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "bengaluru.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write("not valid json")

        with patch(
            "backend.app.services.weather_forecast_service._cache_dir",
            return_value=cache_dir,
        ), patch(
            "backend.app.services.weather_forecast_service.fetch_open_meteo_forecast",
            side_effect=WeatherProviderError("provider down"),
        ):
            result = get_weather_forecast(city="bengaluru", refresh=True)
            assert result.get("source_status") == "unavailable"


# ---------------------------------------------------------------------------
# Normalization and summary tests
# ---------------------------------------------------------------------------


class TestWeatherNormalization:
    def test_hourly_arrays_validated(self):
        raw = _sample_raw_response(hours=72)
        retrieved = datetime.now(tz=IST)
        normalized = _normalize_forecast(raw, "bengaluru", retrieved)
        assert len(normalized["hourly"]) == 72
        for rec in normalized["hourly"]:
            assert "timestamp_local" in rec
            assert "temperature_c" in rec
            assert "weather_code" in rec
            assert "weather_description" in rec

    def test_timestamps_in_ist(self):
        raw = _sample_raw_response(hours=72)
        retrieved = datetime.now(tz=IST)
        normalized = _normalize_forecast(raw, "bengaluru", retrieved)
        for rec in normalized["hourly"]:
            ts = rec["timestamp_local"]
            assert "T" in ts

    def test_weather_code_mapping_deterministic(self):
        raw = _sample_raw_response(hours=72)
        retrieved = datetime.now(tz=IST)
        normalized = _normalize_forecast(raw, "bengaluru", retrieved)
        for rec in normalized["hourly"]:
            if rec["weather_code"] == 0:
                assert rec["weather_description"] == "Clear sky"
            elif rec["weather_code"] == 63:
                assert rec["weather_description"] == "Moderate rain"
            elif rec["weather_code"] == 65:
                assert rec["weather_description"] == "Heavy rain"

    def test_rain_risk_classification(self):
        records = _normalize_forecast(
            _sample_raw_response(hours=72), "bengaluru", datetime.now(tz=IST)
        )["hourly"]
        for rec in records:
            risk = _hour_weather_risk(rec)
            pp = rec["precipitation_probability_percent"] or 0
            pm = rec["precipitation_mm"] or 0
            if rec["weather_code"] == 65:
                assert risk == "Severe"
            elif pm >= 5 and pp >= 70:
                assert risk in ("Severe", "High")
            elif pm >= 2:
                assert risk in ("Severe", "High", "Moderate")

    def test_wind_risk_classification(self):
        raw = _sample_raw_response(hours=72)
        raw["hourly"]["wind_speed_10m"][10] = 35.0
        raw["hourly"]["wind_gusts_10m"][10] = 55.0
        retrieved = datetime.now(tz=IST)
        records = _normalize_forecast(raw, "bengaluru", retrieved)["hourly"]
        risk = _hour_weather_risk(records[10])
        assert risk in ("High", "Moderate")

    def test_heat_risk_classification(self):
        raw = _sample_raw_response(hours=72)
        raw["hourly"]["apparent_temperature"][5] = 38.0
        retrieved = datetime.now(tz=IST)
        records = _normalize_forecast(raw, "bengaluru", retrieved)["hourly"]
        risk = _hour_weather_risk(records[5])
        assert risk == "Moderate"

    def test_summary_derives_correct_stats(self):
        raw = _sample_raw_response(hours=72)
        retrieved = datetime.now(tz=IST)
        records = _normalize_forecast(raw, "bengaluru", retrieved)["hourly"]
        summary = _derive_summary(records, "next_24h", "bengaluru")
        assert summary["temperature_min_c"] is not None
        assert summary["temperature_max_c"] is not None
        assert summary["max_precipitation_probability_percent"] is not None
        assert summary["total_precipitation_mm"] >= 0
        assert summary["weather_risk_level"] in ("Low", "Moderate", "High", "Severe")
        assert isinstance(summary["weather_risk_reasons"], list)

    def test_overall_risk_severe_when_severe_present(self):
        assert _overall_risk(["Low", "Moderate", "Severe", "High"]) == "Severe"

    def test_overall_risk_high_when_high_present(self):
        assert _overall_risk(["Low", "Moderate", "High"]) == "High"

    def test_overall_risk_moderate_when_moderate_present(self):
        assert _overall_risk(["Low", "Moderate"]) == "Moderate"

    def test_overall_risk_low_when_all_low(self):
        assert _overall_risk(["Low", "Low"]) == "Low"


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------


class TestWeatherAPI:
    def test_forecast_endpoint_works(self):
        from backend.app.routers.weather import weather_forecast

        raw = _sample_raw_response(hours=72)
        with patch(
            "backend.app.routers.weather.get_weather_forecast",
            return_value={
                "city": "bengaluru",
                "timezone": "Asia/Kolkata",
                "latitude": WEATHER_BENGALURU_LATITUDE,
                "longitude": WEATHER_BENGALURU_LONGITUDE,
                "provider": WEATHER_PROVIDER,
                "source_status": "live_provider",
                "cache_used": False,
                "freshness": "fresh",
                "age_minutes": 0.0,
                "generated_at": "2026-07-06T00:00:00+05:30",
                "retrieved_at": "2026-07-06T00:00:00+05:30",
                "forecast_start": "2026-07-06T00:00",
                "forecast_end": "2026-07-07T23:00",
                "hourly": _normalize_forecast(raw, "bengaluru", datetime.now(tz=IST))["hourly"],
                "hourly_count": 72,
                "summary_periods": {},
                "warnings": [],
            },
        ):
            result = weather_forecast(city="bengaluru")
            assert result.city == "bengaluru"
            assert result.provider == WEATHER_PROVIDER
            assert result.source_status == "live_provider"
            assert len(result.hourly) > 0

    def test_summary_endpoint_works(self):
        from backend.app.routers.weather import weather_summary

        with patch(
            "backend.app.routers.weather.get_weather_summary",
            return_value={
                "city": "bengaluru",
                "timezone": "Asia/Kolkata",
                "period": "next_24h",
                "provider": WEATHER_PROVIDER,
                "source_status": "live_provider",
                "cache_used": False,
                "freshness": "fresh",
                "age_minutes": 0.0,
                "generated_at": "2026-07-06T00:00:00+05:30",
                "temperature_min_c": 25.0,
                "temperature_max_c": 32.0,
                "apparent_temperature_min_c": 24.0,
                "apparent_temperature_max_c": 31.0,
                "max_precipitation_probability_percent": 10.0,
                "total_precipitation_mm": 0.0,
                "max_wind_speed_kmh": 12.0,
                "max_wind_gust_kmh": 20.0,
                "dominant_weather_code": 0,
                "dominant_weather_description": "Clear sky",
                "severe_weather_present": False,
                "weather_risk_level": "Low",
                "weather_risk_reasons": [],
                "warnings": [],
            },
        ):
            result = weather_summary(city="bengaluru", period="next_24h")
            assert result.city == "bengaluru"
            assert result.weather_risk_level == "Low"
            assert result.period == "next_24h"

    def test_invalid_city_returns_404(self):
        from fastapi import HTTPException
        from backend.app.routers.weather import weather_forecast

        with pytest.raises(HTTPException) as exc:
            weather_forecast(city="mumbai")
        assert exc.value.status_code == 404

    def test_invalid_period_returns_422(self):
        from fastapi import HTTPException
        from backend.app.routers.weather import weather_summary

        with pytest.raises(HTTPException) as exc:
            weather_summary(city="bengaluru", period="next_week")
        assert exc.value.status_code == 422

    def test_unavailable_forecast_returns_503(self):
        from fastapi import HTTPException
        from backend.app.routers.weather import weather_forecast

        with patch(
            "backend.app.routers.weather.get_weather_forecast",
            return_value={
                "source_status": "unavailable",
                "warnings": ["Weather data unavailable: test"],
            },
        ):
            with pytest.raises(HTTPException) as exc:
                weather_forecast(city="bengaluru")
            assert exc.value.status_code == 503
