from __future__ import annotations

import logging
from typing import Any

from backend.app.config import (
    MEDICAL_DISCLAIMER,
    SCOPE_AQI_COVERAGE,
    SCOPE_NO_TRAFFIC,
    SCOPE_WEATHER_CHANGE,
    SUPPORTED_CITIES,
    TRAVEL_PROFILES,
    TRAVEL_READINESS_MATRIX,
    WEATHER_CITY_DEFAULT,
)
from backend.app.services.city_briefing_service import get_city_briefing
from backend.app.services.weather_forecast_service import (
    get_weather_forecast,
    get_weather_summary,
)

logger = logging.getLogger(__name__)


def get_travel_readiness(
    city: str = WEATHER_CITY_DEFAULT,
    profile: str = "general",
    period: str = "next_24h",
    refresh_weather: bool = False,
) -> dict[str, Any]:
    """Deterministic travel-readiness assessment combining weather and AQI."""
    city_key = city.lower().strip()
    if city_key not in SUPPORTED_CITIES:
        return _unavailable_response(city, f"Unsupported city: {city}")

    if period not in ("next_24h", "tomorrow"):
        period = "next_24h"

    profile_key = profile.lower().strip()
    if profile_key not in TRAVEL_PROFILES:
        profile_key = "general"

    # 1. Fetch weather component
    weather_summary = get_weather_summary(
        city=city_key, period=period, refresh=refresh_weather,
    )
    weather_available = weather_summary.get("source_status") != "unavailable"

    # 2. Fetch AQI component
    aqi_available = False
    city_risk = "Unavailable"
    aqi_summary = ""
    monitored_note = ""
    high_risk_areas: list[str] = []
    try:
        briefing = get_city_briefing(city=city_key)
        city_risk = briefing.get("city_risk_level", "Unavailable")
        aqi_summary = briefing.get("executive_summary", "")
        monitored_note = f"{briefing.get('stations_with_forecasts', 0)} monitored stations provide data."
        limitations = briefing.get("data_limitations", [])
        for lim in limitations:
            if "monitored" in lim.lower():
                monitored_note = lim
                break
        aqi_available = city_risk != "Unavailable"
        top_priorities = briefing.get("top_priorities", [])
        for p in top_priorities[:3]:
            risk = p.get("risk_category", "")
            if risk in ("Poor", "Very Poor", "Severe"):
                high_risk_areas.append(
                    f"{p.get('station_name', p.get('station_id', 'Unknown'))} "
                    f"({risk}: {p.get('predicted_pm25', 'N/A')} µg/m³)"
                )
    except Exception as e:
        logger.warning("City briefing unavailable for travel: %s", e)
        aqi_available = False

    # 3. Determine readiness
    if weather_available and aqi_available:
        readiness_basis = "weather_and_air_quality"
        weather_risk = weather_summary.get("weather_risk_level", "Low")
        matrix_key = (weather_risk, city_risk)
        final_readiness = TRAVEL_READINESS_MATRIX.get(matrix_key, "Caution advised")
        decision_reasons = _build_decision_reasons(weather_summary, city_risk, aqi_summary)
    elif weather_available and not aqi_available:
        readiness_basis = "weather_only_partial"
        weather_risk = weather_summary.get("weather_risk_level", "Low")
        final_readiness = _weather_only_readiness(weather_risk)
        decision_reasons = _build_weather_only_reasons(weather_summary)
    elif not weather_available and aqi_available:
        readiness_basis = "air_quality_only_partial"
        final_readiness = _aqi_only_readiness(city_risk)
        decision_reasons = _build_aqi_only_reasons(city_risk, aqi_summary)
    else:
        return _unavailable_response(
            city, "Weather and air-quality data are both unavailable. "
            "Travel readiness cannot be assessed."
        )

    # 4. Profile-specific precautions
    precautions = _profile_precautions(profile_key, weather_summary, city_risk)

    # 5. Limitations
    limitations = [SCOPE_NO_TRAFFIC, SCOPE_AQI_COVERAGE, SCOPE_WEATHER_CHANGE]

    # 6. Medical disclaimer for sensitive profiles
    disclaimer = None
    if profile_key in ("elderly", "child", "school", "outdoor_worker"):
        disclaimer = MEDICAL_DISCLAIMER

    # 7. Weather component structure
    weather_component = {
        "weather_available": weather_available,
        "weather_risk_level": weather_summary.get("weather_risk_level") if weather_available else None,
        "weather_summary": _build_weather_summary_text(weather_summary) if weather_available else None,
        "weather_caution_reasons": weather_summary.get("weather_risk_reasons", []) if weather_available else [],
        "provider": weather_summary.get("provider"),
        "source_status": weather_summary.get("source_status"),
        "freshness": weather_summary.get("freshness"),
    }

    # 8. AQI component structure
    aqi_component = {
        "aqi_available": aqi_available,
        "city_risk_level": city_risk,
        "executive_summary": aqi_summary,
        "monitored_stations_note": monitored_note,
        "high_risk_station_areas": high_risk_areas,
    }

    return {
        "city": city_key,
        "profile": profile_key,
        "period": period,
        "weather_component": weather_component,
        "air_quality_component": aqi_component,
        "final_readiness": final_readiness,
        "readiness_basis": readiness_basis,
        "decision_reasons": decision_reasons,
        "profile_specific_precautions": precautions,
        "limitations": limitations,
        "medical_disclaimer": disclaimer,
        "warnings": weather_summary.get("warnings", []),
    }


def _build_weather_summary_text(summary: dict[str, Any]) -> str:
    parts: list[str] = []
    t_min = summary.get("temperature_min_c")
    t_max = summary.get("temperature_max_c")
    if t_min is not None and t_max is not None:
        parts.append(f"Temperature {t_min:.0f}–{t_max:.0f}°C")
    elif t_max is not None:
        parts.append(f"Temperature up to {t_max:.0f}°C")

    desc = summary.get("dominant_weather_description", "")
    if desc and desc != "Unknown":
        parts.append(desc.lower())

    wind = summary.get("max_wind_speed_kmh")
    if wind is not None and wind > 0:
        parts.append(f"wind {wind:.0f} km/h")

    precip = summary.get("total_precipitation_mm", 0)
    if precip > 0:
        parts.append(f"precipitation {precip:.1f} mm")

    return ", ".join(parts) if parts else "No significant weather."


def _build_decision_reasons(
    weather_summary: dict[str, Any], city_risk: str, aqi_summary: str,
) -> list[str]:
    reasons: list[str] = []
    weather_risk = weather_summary.get("weather_risk_level", "Low")
    reasons.append(f"Weather risk: {weather_risk}.")
    reasons.append(f"Air quality risk: {city_risk}.")
    if weather_summary.get("weather_risk_reasons"):
        reasons.extend(weather_summary["weather_risk_reasons"][:3])
    return reasons


def _build_weather_only_reasons(weather_summary: dict[str, Any]) -> list[str]:
    reasons: list[str] = ["Air quality data unavailable."]
    weather_risk = weather_summary.get("weather_risk_level", "Low")
    reasons.append(f"Weather risk: {weather_risk}.")
    if weather_summary.get("weather_risk_reasons"):
        reasons.extend(weather_summary["weather_risk_reasons"][:3])
    return reasons


def _build_aqi_only_reasons(city_risk: str, aqi_summary: str) -> list[str]:
    reasons: list[str] = ["Weather data unavailable."]
    reasons.append(f"Air quality risk: {city_risk}.")
    if aqi_summary:
        reasons.append(aqi_summary[:200])
    return reasons


def _weather_only_readiness(weather_risk: str) -> str:
    mapping = {
        "Low": "Suitable with precautions",
        "Moderate": "Caution advised",
        "High": "Caution advised",
        "Severe": "Avoid non-essential outdoor travel",
    }
    return mapping.get(weather_risk, "Caution advised")


def _aqi_only_readiness(city_risk: str) -> str:
    mapping = {
        "Good": "Suitable with precautions",
        "Satisfactory": "Suitable with precautions",
        "Moderate": "Caution advised",
        "Poor": "Caution advised",
        "Very Poor": "Avoid non-essential outdoor travel",
        "Severe": "Avoid non-essential outdoor travel",
    }
    return mapping.get(city_risk, "Caution advised")


def _profile_precautions(
    profile: str,
    weather_summary: dict[str, Any],
    city_risk: str,
) -> list[str]:
    precautions: list[str] = []
    weather_risk = weather_summary.get("weather_risk_level", "Low")
    severe = weather_summary.get("severe_weather_present", False)
    hot = _is_hot(weather_summary)
    rainy = _is_rainy(weather_summary)
    windy = _is_windy(weather_summary)

    aqi_elevated = city_risk in ("Moderate", "Poor", "Very Poor", "Severe")

    if profile == "general":
        if rainy:
            precautions.append("Carry rain protection.")
        if hot:
            precautions.append("Stay hydrated and avoid midday heat.")
        if windy:
            precautions.append("Caution in high wind areas.")
        if aqi_elevated:
            precautions.append("Reduce prolonged exertion if air quality is poor.")
        if weather_risk in ("Low", "Moderate") and not aqi_elevated:
            precautions.append("Outdoor activities generally suitable.")
    elif profile == "elderly":
        if hot or weather_risk in ("High", "Severe"):
            precautions.append("Avoid outdoor exposure during peak heat or severe weather.")
        if rainy or severe:
            precautions.append("Avoid outdoor travel during wet or severe conditions.")
        if aqi_elevated:
            precautions.append("Reduce outdoor exposure due to elevated AQI.")
        precautions.append("Monitor health symptoms and stay indoors if conditions are concerning.")
    elif profile == "child":
        if hot or weather_risk in ("High", "Severe"):
            precautions.append("Limit outdoor play during severe weather or extreme heat.")
        if rainy or severe:
            precautions.append("Avoid outdoor travel during wet or severe conditions.")
        if aqi_elevated:
            precautions.append("Reduce outdoor playtime due to air quality concerns.")
        precautions.append("Ensure children are supervised and appropriately dressed.")
    elif profile == "outdoor_worker":
        if hot:
            precautions.append("Plan hydration and rest breaks in shaded areas.")
        if weather_risk in ("High", "Severe"):
            precautions.append("Consider rescheduling strenuous outdoor tasks.")
        if windy:
            precautions.append("Secure loose materials and exercise caution at height.")
        if aqi_elevated:
            precautions.append("Use exposure-reduction measures per AQI guidance.")
        precautions.append("Take regular breaks in clean-air areas.")
    elif profile == "school":
        if hot or weather_risk in ("High", "Severe"):
            precautions.append("Keep students indoors during extreme weather.")
        if rainy:
            precautions.append("Plan indoor activities if rain is expected.")
        if aqi_elevated:
            precautions.append("Reduce extended outdoor physical activity.")
        precautions.append("Monitor student health and provide indoor alternatives.")
    elif profile == "two_wheeler":
        if rainy:
            precautions.append("Rain expected; consider alternative transport or wet-gear preparation.")
        if windy or severe:
            precautions.append("High winds pose stability risks for two-wheelers; use caution.")
        if weather_risk in ("High", "Severe"):
            precautions.append("Avoid riding during severe weather conditions.")
        if aqi_elevated:
            precautions.append("Elevated AQI may affect visibility and breathing; use mask.")
        precautions.append("Road conditions may be slippery; reduce speed and increase following distance.")
    return precautions


def _is_hot(summary: dict[str, Any]) -> bool:
    t = summary.get("apparent_temperature_max_c")
    return t is not None and t >= 35


def _is_rainy(summary: dict[str, Any]) -> bool:
    precip = summary.get("total_precipitation_mm", 0)
    prob = summary.get("max_precipitation_probability_percent") or 0
    return precip > 1 or prob >= 50


def _is_windy(summary: dict[str, Any]) -> bool:
    gust = summary.get("max_wind_gust_kmh") or 0
    speed = summary.get("max_wind_speed_kmh") or 0
    return gust >= 30 or speed >= 20


def _unavailable_response(city: str, reason: str) -> dict[str, Any]:
    return {
        "city": city,
        "profile": "general",
        "period": "next_24h",
        "weather_component": {
            "weather_available": False,
            "weather_risk_level": None,
            "weather_summary": None,
            "weather_caution_reasons": [],
            "provider": None,
            "source_status": None,
            "freshness": None,
        },
        "air_quality_component": {
            "aqi_available": False,
            "city_risk_level": None,
            "executive_summary": None,
            "monitored_stations_note": None,
            "high_risk_station_areas": [],
        },
        "final_readiness": None,
        "readiness_basis": "unavailable",
        "decision_reasons": [reason],
        "profile_specific_precautions": [],
        "limitations": [SCOPE_NO_TRAFFIC, SCOPE_AQI_COVERAGE, SCOPE_WEATHER_CHANGE],
        "medical_disclaimer": None,
        "warnings": [reason],
    }
