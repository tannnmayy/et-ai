from __future__ import annotations

from backend.app.config import (
    ADVISORY_PROFILES,
    MEDICAL_DISCLAIMER,
    PM25_RISK_THRESHOLDS,
    SUPPORTED_LANGUAGES,
)
from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
    get_station_snapshot,
)
from backend.app.services.confidence_service import get_forecast_confidence

import logging

logger = logging.getLogger(__name__)


def _risk_category(pm25: float) -> str:
    for name, threshold in PM25_RISK_THRESHOLDS.items():
        if pm25 <= threshold:
            return name
    return "Severe"


_ADVISORY_EN: dict[str, dict[str, str | list[str]]] = {
    "Good": {
        "headline": "Air quality is satisfactory.",
        "recommendations": [
            "Normal outdoor activities are generally appropriate.",
            "Enjoy fresh air and outdoor exercise.",
        ],
        "caution_note": "No special precautions needed for most people.",
    },
    "Satisfactory": {
        "headline": "Air quality is acceptable.",
        "recommendations": [
            "Normal outdoor activities are generally appropriate.",
            "Sensitive individuals may experience mild discomfort.",
        ],
        "caution_note": "Sensitive individuals should monitor for symptoms.",
    },
    "Moderate": {
        "headline": "Moderate air quality.",
        "recommendations": [
            "Sensitive groups may reduce prolonged strenuous outdoor activity.",
            "Consider shorter outdoor exercise sessions.",
        ],
        "caution_note": "Children, elderly, and people with respiratory conditions should be cautious.",
    },
    "Poor": {
        "headline": "Unhealthy air quality.",
        "recommendations": [
            "Children, elderly people, and people with respiratory or cardiac conditions should reduce prolonged outdoor exertion.",
            "Schools should consider moving intense outdoor activity indoors.",
            "General public should limit prolonged outdoor exercise.",
        ],
        "caution_note": "Avoid prolonged outdoor exertion, especially for sensitive groups.",
    },
    "Very Poor": {
        "headline": "Very poor air quality.",
        "recommendations": [
            "Avoid prolonged outdoor exertion for everyone.",
            "Sensitive groups should remain indoors where possible.",
            "Outdoor workers should use exposure-reduction measures and take breaks.",
            "Schools should shift outdoor sports indoors.",
        ],
        "caution_note": "Stay indoors with windows closed where possible.",
    },
    "Severe": {
        "headline": "Severe air quality emergency.",
        "recommendations": [
            "Avoid all outdoor exertion.",
            "Sensitive groups should remain indoors with air purification if available.",
            "Outdoor workers should minimize exposure and use protective measures.",
            "Schools should cancel outdoor activities entirely.",
        ],
        "caution_note": "Emergency-level air quality. Minimize all outdoor exposure.",
    },
}

_PROFILE_MODIFIERS: dict[str, dict[str, list[str]]] = {
    "child": {
        "additional": [
            "Children should avoid outdoor play during poor or worse conditions.",
            "Schools should reschedule outdoor sports to indoor facilities.",
        ],
    },
    "elderly": {
        "additional": [
            "Older adults should remain indoors during moderate or worse conditions.",
            "Monitor for respiratory symptoms and seek medical attention if needed.",
        ],
    },
    "respiratory": {
        "additional": [
            "People with asthma or respiratory conditions should keep rescue medication accessible.",
            "Reduce outdoor exposure, especially during peak pollution hours.",
        ],
    },
    "outdoor_worker": {
        "additional": [
            "Use exposure-reduction measures: take breaks in clean-air areas.",
            "Consider wearing a well-fitted mask during poor or worse conditions.",
            "Schedule heavy exertion during lower-pollution periods if possible.",
        ],
    },
    "school": {
        "additional": [
            "Schools should move intense outdoor physical activities indoors during poor or worse conditions.",
            "Monitor student symptoms and provide clean-air break areas.",
        ],
    },
}

_TRANSLATIONS: dict[str, dict[str, str]] = {}


def _get_advisory(profile: str, risk_category: str) -> dict:
    base = _ADVISORY_EN.get(risk_category, _ADVISORY_EN["Good"])
    modifiers = _PROFILE_MODIFIERS.get(profile, {}).get("additional", [])
    recommendations = list(base["recommendations"]) + modifiers
    return {
        "headline": base["headline"],
        "recommendations": recommendations,
        "caution_note": base["caution_note"],
    }


def get_citizen_advisory(
    station_id: str,
    profile: str = "general",
    language: str = "en",
    city: str = "bengaluru",
) -> dict:
    """Generate a deterministic citizen health advisory for a station."""
    try:
        snapshot = get_station_snapshot(station_id, city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError):
        raise

    predicted_pm25 = snapshot["predicted_pm25"]
    risk_category = snapshot["risk_category"]
    conf_data = get_forecast_confidence(station_id, city=city)
    confidence_level = conf_data["confidence_level"]

    advisory = _get_advisory(profile, risk_category)

    translation_fallback = False
    language_served = "en"
    if language in _TRANSLATIONS and risk_category in _TRANSLATIONS[language]:
        language_served = language
    elif language != "en":
        translation_fallback = True

    confidence_note = ""
    if confidence_level in ("Low", "Unavailable"):
        confidence_note = f" Note: forecast confidence is {confidence_level}."

    data_quality_note = ""
    quality_class = snapshot.get("quality_classification", "Unknown")
    if "Usable" in quality_class:
        data_quality_note = f"Station data quality: {quality_class}."

    return {
        "station_id": station_id,
        "station_name": snapshot["station_name"],
        "city": snapshot["city"],
        "profile": profile,
        "language_requested": language,
        "language_served": language_served,
        "translation_fallback": translation_fallback,
        "forecast_risk_category": risk_category,
        "predicted_pm25": predicted_pm25,
        "confidence_level": confidence_level,
        "headline": advisory["headline"] + confidence_note,
        "recommendations": advisory["recommendations"],
        "caution_note": advisory["caution_note"],
        "data_quality_note": data_quality_note,
        "medical_disclaimer": MEDICAL_DISCLAIMER,
    }
