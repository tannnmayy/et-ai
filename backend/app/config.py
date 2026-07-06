from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    configured = os.getenv("AQI_SENTINEL_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[2]


def get_data_mode() -> str:
    return "local_demo_data"


SERVICE_NAME = "aqi-sentinel-api"

# ---------------------------------------------------------------------------
# City registry (multi-city ready, Bengaluru only initially)
# ---------------------------------------------------------------------------

SUPPORTED_CITIES: dict[str, dict[str, str]] = {
    "bengaluru": {
        "display_name": "Bengaluru",
        "artifact_dataset_key": "real_multistation_bengaluru",
    },
}

# ---------------------------------------------------------------------------
# PM2.5 risk thresholds (ug/m3) — Indian AQI scale
# ---------------------------------------------------------------------------

PM25_RISK_THRESHOLDS: dict[str, float] = {
    "Good": 30.0,
    "Satisfactory": 60.0,
    "Moderate": 90.0,
    "Poor": 120.0,
    "Very Poor": 250.0,
}

# ---------------------------------------------------------------------------
# PM2.5 change thresholds (ug/m3)
# ---------------------------------------------------------------------------

PM25_WORSENING_THRESHOLD: float = 10.0
PM25_IMPROVING_THRESHOLD: float = -10.0

# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

CONFIDENCE_FRESHNESS_PENALTIES: list[dict] = [
    {"min_age_hours": 12, "penalty": 35},
    {"min_age_hours": 3, "penalty": 20},
]

CONFIDENCE_COMPLETENESS_PENALTIES: list[dict] = [
    {"max_percent": 50, "penalty": 25},
    {"max_percent": 75, "penalty": 15},
]

CONFIDENCE_GAP_PENALTIES: list[dict] = [
    {"min_hours": 24, "penalty": 30},
    {"min_hours": 6, "penalty": 20},
]

CONFIDENCE_QUALITY_PENALTIES: dict[str, int] = {
    "Usable with caveats": 15,
    "Not suitable": 40,
}

CONFIDENCE_LEVELS: list[dict] = [
    {"min_score": 80, "level": "High"},
    {"min_score": 55, "level": "Medium"},
    {"min_score": 25, "level": "Low"},
    {"min_score": 0, "level": "Unavailable"},
]

CONFIDENCE_UNAVAILABLE_THRESHOLD: int = 25

# ---------------------------------------------------------------------------
# Inspection priority scoring
# ---------------------------------------------------------------------------

INSPECTION_SEVERITY_SCORES: dict[str, int] = {
    "Good": 0,
    "Satisfactory": 8,
    "Moderate": 18,
    "Poor": 30,
    "Very Poor": 40,
    "Severe": 45,
}

INSPECTION_WORSENING_RULES: list[dict] = [
    {"min_change": 40, "score": 20},
    {"min_change": 25, "score": 15},
    {"min_change": 10, "score": 8},
]

INSPECTION_ELEVATED_RULES: list[dict] = [
    {"min_pm25": 150, "score": 15},
    {"min_pm25": 100, "score": 10},
    {"min_pm25": 60, "score": 5},
]

INSPECTION_CONFIDENCE_ADJUSTMENTS: dict[str, int] = {
    "High": 10,
    "Medium": 5,
    "Low": -10,
    "Unavailable": -20,
}

INSPECTION_QUALITY_ADJUSTMENTS: dict[str, int] = {
    "Usable with caveats": -5,
    "Not suitable": -20,
}

INSPECTION_PRIORITY_LEVELS: list[dict] = [
    {"min_score": 70, "level": "Critical"},
    {"min_score": 50, "level": "High"},
    {"min_score": 30, "level": "Moderate"},
    {"min_score": 0, "level": "Watch"},
]

INVESTIGATION_DISCLAIMER: str = (
    "Suggested inspection focus is an investigation hypothesis based on forecast "
    "and station signals. It is not proof that a specific source caused the pollution."
)

# ---------------------------------------------------------------------------
# Station inspection context (generic, non-causal investigation prompts)
# ---------------------------------------------------------------------------

STATION_INSPECTION_FOCUS: dict[str, str] = {
    "cpcb_peenya": "Review industrial compliance checks, freight movement, and dust controls.",
    "cpcb_silkboard": "Review traffic congestion, idling, freight movement, and road-dust controls.",
}

DEFAULT_INSPECTION_FOCUS: str = "Review local particulate-source controls and verify station conditions."

HIGH_PM10_FOCUS: str = "Review road-dust controls, construction activity, and nearby particulate sources."
HIGH_NO2_FOCUS: str = "Review traffic congestion and combustion-source indicators."

# ---------------------------------------------------------------------------
# City risk thresholds
# ---------------------------------------------------------------------------

CITY_RISK_SEVERE_IF_ANY_SEVERE: bool = True
CITY_RISK_SEVERE_MIN_VERY_POOR_STATIONS: int = 2
CITY_RISK_VERY_POOR_MIN_POOR_OR_WORSE_STATIONS: int = 2
CITY_RISK_POOR_MIN_POOR_STATIONS: int = 1

# ---------------------------------------------------------------------------
# Advisory profiles and languages
# ---------------------------------------------------------------------------

ADVISORY_PROFILES: list[str] = [
    "general", "child", "elderly", "respiratory", "outdoor_worker", "school",
]

SUPPORTED_LANGUAGES: list[str] = ["en", "hi", "kn"]

MEDICAL_DISCLAIMER: str = "This is general air-quality guidance, not medical advice."
