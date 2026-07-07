from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.app.config import (
    CITY_RISK_POOR_MIN_POOR_STATIONS,
    CITY_RISK_SEVERE_IF_ANY_SEVERE,
    CITY_RISK_SEVERE_MIN_VERY_POOR_STATIONS,
    CITY_RISK_VERY_POOR_MIN_POOR_OR_WORSE_STATIONS,
    SEVERE_WEATHER_CODES,
    SUPPORTED_CITIES,
    WEATHER_BENGALURU_LATITUDE,
    WEATHER_BENGALURU_LONGITUDE,
    WEATHER_CACHE_DIRECTORY,
    WEATHER_CACHE_TTL_MINUTES,
    WEATHER_CITY_DEFAULT,
    WEATHER_CODE_DESCRIPTIONS,
    WEATHER_FORECAST_HORIZON_HOURS,
    WEATHER_HEAT_CAUTION_C,
    WEATHER_HEAT_HIGH_RISK_C,
    WEATHER_MAX_RETRIES,
    WEATHER_PRECIP_AMOUNT_CAUTION_MM,
    WEATHER_PRECIP_AMOUNT_HIGH_RISK_MM,
    WEATHER_PRECIP_PROB_CAUTION,
    WEATHER_PROVIDER,
    WEATHER_STALE_CACHE_MAX_HOURS,
    WEATHER_SUMMARY_PERIODS,
    WEATHER_WIND_GUST_CAUTION_KMH,
    WEATHER_WIND_SPEED_CAUTION_KMH,
)
from backend.app.services.weather_client import (
    WeatherProviderError,
    fetch_open_meteo_forecast,
)

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

CACHE_SCHEMA_VERSION = "1.1"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / WEATHER_CACHE_DIRECTORY


def _cache_path(city: str) -> Path:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{city.lower().strip()}.json"


def _read_cache(city: str) -> dict[str, Any] | None:
    path = _cache_path(city)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read weather cache for %s: %s", city, e)
        return None


def _write_cache(city: str, data: dict[str, Any]) -> None:
    path = _cache_path(city)
    try:
        fd, tmp_path_str = tempfile.mkstemp(
            suffix=".json", prefix="weather_cache_", dir=str(path.parent)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path_str, str(path))
    except OSError as e:
        logger.warning("Failed to write weather cache for %s: %s", city, e)


def _build_cache_entry(
    city: str, normalized: dict[str, Any], requested_horizon_hours: int = 0
) -> dict[str, Any]:
    now = datetime.now(tz=IST)
    hourly = normalized.get("hourly", [])
    actual_hours = len(hourly) if requested_horizon_hours <= 0 else max(len(hourly), requested_horizon_hours)
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "retrieved_at": now.isoformat(),
        "city": city,
        "provider": WEATHER_PROVIDER,
        "forecast_horizon_hours": actual_hours,
        "data": normalized,
    }


def _cache_is_fresh(entry: dict[str, Any]) -> bool:
    retrieved_str = entry.get("retrieved_at", "")
    if not retrieved_str:
        return False
    try:
        retrieved = datetime.fromisoformat(retrieved_str)
    except (ValueError, TypeError):
        return False
    age = datetime.now(tz=IST) - retrieved
    return age.total_seconds() < WEATHER_CACHE_TTL_MINUTES * 60


def _cache_is_usable_stale(entry: dict[str, Any]) -> bool:
    retrieved_str = entry.get("retrieved_at", "")
    if not retrieved_str:
        return False
    try:
        retrieved = datetime.fromisoformat(retrieved_str)
    except (ValueError, TypeError):
        return False
    age = datetime.now(tz=IST) - retrieved
    return age.total_seconds() < WEATHER_STALE_CACHE_MAX_HOURS * 3600


def _cache_coverage_hours(entry: dict[str, Any]) -> int:
    """Return how many hours of forecast the cached entry actually covers."""
    data = entry.get("data", {})
    hourly = data.get("hourly", [])
    if not hourly:
        return 0
    if len(hourly) >= 2:
        first_ts = hourly[0].get("timestamp_local", "")
        last_ts = hourly[-1].get("timestamp_local", "")
        if first_ts and last_ts:
            try:
                fdt = datetime.fromisoformat(first_ts)
                ldt = datetime.fromisoformat(last_ts)
                if fdt.tzinfo is None:
                    fdt = fdt.replace(tzinfo=IST)
                if ldt.tzinfo is None:
                    ldt = ldt.replace(tzinfo=IST)
                span = (ldt - fdt).total_seconds() / 3600 + 1
                return max(len(hourly), int(span))
            except (ValueError, TypeError):
                pass
    return len(hourly)


def _cache_is_sufficient(entry: dict[str, Any], needed_hours: int) -> bool:
    """Check whether cached forecast covers at least needed_hours of data."""
    coverage = _cache_coverage_hours(entry)
    return coverage >= needed_hours


def _age_minutes(entry: dict[str, Any]) -> float:
    retrieved_str = entry.get("retrieved_at", "")
    if not retrieved_str:
        return 0.0
    try:
        retrieved = datetime.fromisoformat(retrieved_str)
        age = datetime.now(tz=IST) - retrieved
        return age.total_seconds() / 60.0
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize_hourly(
    raw: dict[str, Any],
    retrieved_at: datetime,
) -> list[dict[str, Any]]:
    hourly = raw["hourly"]
    times = hourly["time"]
    records: list[dict[str, Any]] = []
    for i, ts in enumerate(times):
        wc = hourly["weather_code"][i]
        records.append({
            "timestamp_local": ts,
            "temperature_c": _safe_float(hourly["temperature_2m"][i]),
            "apparent_temperature_c": _safe_float(hourly["apparent_temperature"][i]),
            "relative_humidity_percent": _safe_float(hourly["relative_humidity_2m"][i]),
            "precipitation_probability_percent": _safe_float(hourly["precipitation_probability"][i]),
            "precipitation_mm": _safe_float(hourly["precipitation"][i]),
            "rain_mm": _safe_float(hourly["rain"][i]),
            "showers_mm": _safe_float(hourly["showers"][i]),
            "snowfall_cm": _safe_float(hourly["snowfall"][i]),
            "weather_code": wc,
            "weather_description": WEATHER_CODE_DESCRIPTIONS.get(wc, "Unknown"),
            "wind_speed_kmh": _safe_float(hourly["wind_speed_10m"][i]),
            "wind_gust_kmh": _safe_float(hourly["wind_gusts_10m"][i]),
        })
    return records


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        v = float(val)
        return v
    except (ValueError, TypeError):
        return None


def _normalize_forecast(
    raw: dict[str, Any],
    city: str,
    retrieved_at: datetime,
) -> dict[str, Any]:
    hourly = raw["hourly"]
    times = hourly["time"]
    records = _normalize_hourly(raw, retrieved_at)

    generated_at = raw.get("generationtime_ms")
    if generated_at is not None:
        generated_dt = retrieved_at - timedelta(milliseconds=float(generated_at))
        generated_iso = generated_dt.isoformat()
    else:
        generated_iso = retrieved_at.isoformat()

    return {
        "city": city,
        "timezone": raw.get("timezone", "Asia/Kolkata"),
        "latitude": raw.get("latitude", WEATHER_BENGALURU_LATITUDE),
        "longitude": raw.get("longitude", WEATHER_BENGALURU_LONGITUDE),
        "generated_at": generated_iso,
        "retrieved_at": retrieved_at.isoformat(),
        "forecast_start": times[0] if times else None,
        "forecast_end": times[-1] if times else None,
        "provider": WEATHER_PROVIDER,
        "source_status": "live_provider",
        "cache_used": False,
        "freshness": "fresh",
        "age_minutes": 0.0,
        "hourly": records,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Weather risk classification (per-hour)
# ---------------------------------------------------------------------------


def _hour_weather_risk(rec: dict[str, Any]) -> str:
    wc = rec.get("weather_code")
    if wc is not None and wc in SEVERE_WEATHER_CODES:
        return "Severe"
    precip_mm = rec.get("precipitation_mm") or 0
    apparent_temp = rec.get("apparent_temperature_c")
    wind_gust = rec.get("wind_gust_kmh") or 0
    precip_prob = rec.get("precipitation_probability_percent") or 0

    if precip_mm >= WEATHER_PRECIP_AMOUNT_HIGH_RISK_MM:
        return "High"
    if apparent_temp is not None and apparent_temp >= WEATHER_HEAT_HIGH_RISK_C:
        return "High"
    if wind_gust >= WEATHER_WIND_GUST_CAUTION_KMH * 1.5:
        return "High"
    if precip_prob >= 70 and precip_mm >= 5:
        return "High"

    if precip_prob >= WEATHER_PRECIP_PROB_CAUTION:
        return "Moderate"
    if precip_mm >= WEATHER_PRECIP_AMOUNT_CAUTION_MM:
        return "Moderate"
    wind_speed = rec.get("wind_speed_kmh") or 0
    if wind_speed >= WEATHER_WIND_SPEED_CAUTION_KMH:
        return "Moderate"
    if wind_gust >= WEATHER_WIND_GUST_CAUTION_KMH:
        return "Moderate"
    if apparent_temp is not None and apparent_temp >= WEATHER_HEAT_CAUTION_C:
        return "Moderate"

    return "Low"


def _get_risk_reasons(rec: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    wc = rec.get("weather_code")
    if wc is not None and wc in SEVERE_WEATHER_CODES:
        reasons.append(WEATHER_CODE_DESCRIPTIONS.get(wc, "Severe weather"))

    precip_mm = rec.get("precipitation_mm") or 0
    precip_prob = rec.get("precipitation_probability_percent") or 0
    wind_speed = rec.get("wind_speed_kmh") or 0
    wind_gust = rec.get("wind_gust_kmh") or 0
    apparent_temp = rec.get("apparent_temperature_c")

    if precip_prob >= WEATHER_PRECIP_PROB_CAUTION:
        reasons.append(f"Rain probability reaches {precip_prob:.0f}%.")
    if precip_mm >= WEATHER_PRECIP_AMOUNT_HIGH_RISK_MM:
        reasons.append(f"Forecast precipitation totals {precip_mm:.1f} mm.")
    elif precip_mm >= WEATHER_PRECIP_AMOUNT_CAUTION_MM:
        reasons.append(f"Precipitation of {precip_mm:.1f} mm.")
    if wind_speed >= WEATHER_WIND_SPEED_CAUTION_KMH:
        reasons.append(f"Wind speed may reach {wind_speed:.0f} km/h.")
    if wind_gust >= WEATHER_WIND_GUST_CAUTION_KMH:
        reasons.append(f"Wind gusts may reach {wind_gust:.0f} km/h.")
    if apparent_temp is not None and apparent_temp >= WEATHER_HEAT_HIGH_RISK_C:
        reasons.append(f"Apparent temperature may reach {apparent_temp:.0f}°C.")
    elif apparent_temp is not None and apparent_temp >= WEATHER_HEAT_CAUTION_C:
        reasons.append(f"Apparent temperature reaches {apparent_temp:.0f}°C.")

    return reasons


# ---------------------------------------------------------------------------
# Summary derivation
# ---------------------------------------------------------------------------


def _filter_hours(
    records: list[dict[str, Any]], period: str,
) -> list[dict[str, Any]]:
    now = datetime.now(tz=IST)
    if period == "next_24h":
        cutoff = now + timedelta(hours=24)
        return [r for r in records if _ts_in_range(r, now, cutoff)]
    if period == "tomorrow":
        tomorrow_start = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        tomorrow_end = tomorrow_start + timedelta(days=1)
        return [r for r in records if _ts_in_range(r, tomorrow_start, tomorrow_end)]
    return records


def _ts_in_range(
    rec: dict[str, Any], start: datetime, end: datetime,
) -> bool:
    ts = rec.get("timestamp_local", "")
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return start <= dt < end
    except (ValueError, TypeError):
        return False


def _derive_summary(
    records: list[dict[str, Any]], period: str, city: str,
) -> dict[str, Any]:
    temps = [r["temperature_c"] for r in records if r["temperature_c"] is not None]
    apparent_temps = [
        r["apparent_temperature_c"] for r in records if r["apparent_temperature_c"] is not None
    ]
    precip_probs = [
        r["precipitation_probability_percent"]
        for r in records if r["precipitation_probability_percent"] is not None
    ]
    total_precip = sum(r["precipitation_mm"] or 0 for r in records)
    wind_speeds = [r["wind_speed_kmh"] for r in records if r["wind_speed_kmh"] is not None]
    wind_gusts = [r["wind_gust_kmh"] for r in records if r["wind_gust_kmh"] is not None]

    risk_levels = [_hour_weather_risk(r) for r in records]
    overall_risk = _overall_risk(risk_levels)

    severe = any(
        r.get("weather_code") is not None and r["weather_code"] in SEVERE_WEATHER_CODES
        for r in records
    )

    max_risk_records = [r for r in records if _hour_weather_risk(r) == overall_risk]
    all_reasons: list[str] = []
    for r in max_risk_records[:5]:
        all_reasons.extend(_get_risk_reasons(r))
    unique_reasons = list(dict.fromkeys(all_reasons))

    dominant_code = _dominant_weather_code(records)

    return {
        "city": city,
        "timezone": "Asia/Kolkata",
        "period": period,
        "provider": WEATHER_PROVIDER,
        "temperature_min_c": min(temps) if temps else None,
        "temperature_max_c": max(temps) if temps else None,
        "apparent_temperature_min_c": min(apparent_temps) if apparent_temps else None,
        "apparent_temperature_max_c": max(apparent_temps) if apparent_temps else None,
        "max_precipitation_probability_percent": max(precip_probs) if precip_probs else None,
        "total_precipitation_mm": total_precip,
        "max_wind_speed_kmh": max(wind_speeds) if wind_speeds else None,
        "max_wind_gust_kmh": max(wind_gusts) if wind_gusts else None,
        "dominant_weather_code": dominant_code,
        "dominant_weather_description": WEATHER_CODE_DESCRIPTIONS.get(dominant_code) if dominant_code is not None else "Unknown",
        "severe_weather_present": severe,
        "weather_risk_level": overall_risk,
        "weather_risk_reasons": unique_reasons,
        "warnings": [],
    }


def _overall_risk(risk_levels: list[str]) -> str:
    if "Severe" in risk_levels:
        return "Severe"
    if "High" in risk_levels:
        return "High"
    if "Moderate" in risk_levels:
        return "Moderate"
    return "Low"


def _dominant_weather_code(records: list[dict[str, Any]]) -> int | None:
    counts: dict[int, int] = {}
    for r in records:
        wc = r.get("weather_code")
        if wc is not None:
            counts[wc] = counts.get(wc, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class WeatherDataError(Exception):
    """Raised when normalized weather data is invalid."""


def get_weather_forecast(
    city: str = WEATHER_CITY_DEFAULT,
    horizon_hours: int = WEATHER_FORECAST_HORIZON_HOURS,
    refresh: bool = False,
) -> dict[str, Any]:
    """Get normalized weather forecast.

    Uses cache if available and fresh. Falls back to stale cache
    if provider is unavailable. Returns a controlled error dict
    if no data is available.
    """
    city_key = city.lower().strip()
    if city_key not in SUPPORTED_CITIES:
        return _unavailable_response(city, "Unsupported city for weather.")

    if horizon_hours < 1:
        horizon_hours = 1
    if horizon_hours > WEATHER_FORECAST_HORIZON_HOURS:
        horizon_hours = WEATHER_FORECAST_HORIZON_HOURS

    if not refresh:
        entry = _read_cache(city_key)
        if entry and _cache_is_fresh(entry) and _cache_is_sufficient(entry, horizon_hours):
            data = entry["data"]
            data["source_status"] = "live_provider"
            data["cache_used"] = True
            data["freshness"] = "fresh"
            data["age_minutes"] = _age_minutes(entry)
            return dict(data)

    retrieved_at = datetime.now(tz=IST)
    try:
        raw = fetch_open_meteo_forecast(city=city_key, horizon_hours=horizon_hours)
        normalized = _normalize_forecast(raw, city_key, retrieved_at)
        cache_entry = _build_cache_entry(city_key, normalized, horizon_hours)
        _write_cache(city_key, cache_entry)
        return dict(normalized)
    except WeatherProviderError as e:
        logger.warning("Weather provider unavailable: %s", e)
        entry = _read_cache(city_key)
        if entry and _cache_is_usable_stale(entry) and _cache_is_sufficient(entry, horizon_hours):
            data = entry["data"]
            data["source_status"] = "stale_cache_fallback"
            data["cache_used"] = True
            data["freshness"] = "stale"
            data["age_minutes"] = _age_minutes(entry)
            warning = (
                f"Live weather provider unavailable. "
                f"Showing cached data from {_age_minutes(entry):.0f} minutes ago."
            )
            data.setdefault("warnings", []).append(warning)
            return dict(data)
        return _unavailable_response(
            city, f"Weather forecast unavailable: {e}"
        )


def get_weather_summary(
    city: str = WEATHER_CITY_DEFAULT,
    period: str = "next_24h",
    refresh: bool = False,
) -> dict[str, Any]:
    """Get deterministic weather summary for a period.

    Returns a dict matching WeatherSummaryResponse fields, or an
    unavailable response on failure.
    """
    forecast = get_weather_forecast(city=city, refresh=refresh)
    if forecast.get("source_status") == "unavailable":
        return forecast

    hourly = forecast.get("hourly", [])
    if not hourly:
        return _unavailable_response(city, "No hourly data available for summary.")

    filtered = _filter_hours(hourly, period)
    if not filtered:
        return _unavailable_response(
            city, f"No forecast data available for period '{period}'."
        )

    summary = _derive_summary(filtered, period, city)
    summary["source_status"] = forecast.get("source_status", "live_provider")
    summary["cache_used"] = forecast.get("cache_used", False)
    summary["freshness"] = forecast.get("freshness", "fresh")
    summary["age_minutes"] = forecast.get("age_minutes")
    summary["generated_at"] = forecast.get("generated_at", "")
    warnings = list(forecast.get("warnings", []))
    if summary.get("warnings"):
        warnings.extend(summary["warnings"])
    summary["warnings"] = warnings
    return summary


def _unavailable_response(city: str, reason: str) -> dict[str, Any]:
    return {
        "city": city,
        "timezone": "Asia/Kolkata",
        "latitude": WEATHER_BENGALURU_LATITUDE,
        "longitude": WEATHER_BENGALURU_LONGITUDE,
        "provider": WEATHER_PROVIDER,
        "source_status": "unavailable",
        "cache_used": False,
        "freshness": "unavailable",
        "age_minutes": None,
        "generated_at": "",
        "retrieved_at": "",
        "forecast_start": None,
        "forecast_end": None,
        "hourly": [],
        "hourly_count": 0,
        "summary_periods": {},
        "warnings": [reason],
    }
