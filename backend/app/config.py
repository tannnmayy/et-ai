from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

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

# ---------------------------------------------------------------------------
# Knowledge base source guardrails
# ---------------------------------------------------------------------------

LEGAL_DISCLAIMER: str = (
    "Regulatory information is provided for general context and is not legal advice. "
    "Verify current requirements with the relevant authority and Gazette notifications."
)

WHO_NOT_INDIAN_AQI_NOTE: str = (
    "WHO guideline values are health-evidence context and do not replace "
    "India's CPCB AQI categories or Indian AQI thresholds."
)

SOURCE_NOT_CAUSAL_NOTE: str = (
    "Retrieved source context supports investigation hypotheses and does not "
    "prove that a specific source caused pollution at a specific station."
)

# ---------------------------------------------------------------------------
# Knowledge base / policy guidance
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE_DIR: str = "knowledge_base"
KNOWLEDGE_MANIFEST_PATH: str = "manifests/corpus_manifest.json"
KNOWLEDGE_CHUNKS_PATH: str = "processed/chunks.jsonl"
KNOWLEDGE_INDEX_DIR: str = "indexes"
KNOWLEDGE_RETRIEVAL_MODE: str = "lexical"
KNOWLEDGE_TOP_K_DEFAULT: int = 3
KNOWLEDGE_TOP_K_MAX: int = 10
KNOWLEDGE_MIN_RELEVANCE_SCORE: float = 0.05
KNOWLEDGE_ALLOW_DEMO_CITATIONS: bool = False
KNOWLEDGE_EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
KNOWLEDGE_CHUNK_SIZE: int = 800
KNOWLEDGE_CHUNK_OVERLAP: int = 120

# ---------------------------------------------------------------------------
# Weather provider configuration
# ---------------------------------------------------------------------------

WEATHER_PROVIDER: str = "open_meteo"
WEATHER_CITY_DEFAULT: str = "bengaluru"
WEATHER_BENGALURU_LATITUDE: float = 12.9716
WEATHER_BENGALURU_LONGITUDE: float = 77.5946
WEATHER_FORECAST_HORIZON_HOURS: int = 72
WEATHER_HTTP_TIMEOUT_SECONDS: int = 15
WEATHER_MAX_RETRIES: int = 3
WEATHER_CACHE_TTL_MINUTES: int = 30
WEATHER_STALE_CACHE_MAX_HOURS: int = 6
WEATHER_CACHE_DIRECTORY: str = "cache/weather"
WEATHER_HTTP_USER_AGENT: str = "AQISentinel/1.0"

# ---------------------------------------------------------------------------
# Open-Meteo hourly field names (provider-specific)
# ---------------------------------------------------------------------------

OPEN_METEO_HOURLY_FIELDS: list[str] = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "rain",
    "showers",
    "snowfall",
    "weather_code",
    "wind_speed_10m",
    "wind_gusts_10m",
    "winddirection_10m",
]

# ---------------------------------------------------------------------------
# Weather-risk thresholds
# ---------------------------------------------------------------------------

WEATHER_PRECIP_PROB_CAUTION: float = 60.0
WEATHER_PRECIP_AMOUNT_CAUTION_MM: float = 2.0
WEATHER_PRECIP_AMOUNT_HIGH_RISK_MM: float = 10.0
WEATHER_WIND_SPEED_CAUTION_KMH: float = 30.0
WEATHER_WIND_GUST_CAUTION_KMH: float = 45.0
WEATHER_HEAT_CAUTION_C: float = 35.0
WEATHER_HEAT_HIGH_RISK_C: float = 40.0

SEVERE_WEATHER_CODES: set[int] = {65, 67, 75, 82, 85, 86, 95, 96, 99}

WEATHER_CODE_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

# ---------------------------------------------------------------------------
# Weather risk levels
# ---------------------------------------------------------------------------

WEATHER_RISK_LEVELS: list[str] = [
    "Low", "Moderate", "High", "Severe",
]

# ---------------------------------------------------------------------------
# Travel-readiness profiles and profiles supported across the project
# ---------------------------------------------------------------------------

TRAVEL_PROFILES: list[str] = [
    "general", "child", "elderly", "outdoor_worker", "school", "two_wheeler",
]

# ---------------------------------------------------------------------------
# Scope / limitation strings (reusable, single source)
# ---------------------------------------------------------------------------

SCOPE_NO_TRAFFIC: str = (
    "This assessment does not include live traffic, route ETA, "
    "road closures, accidents, or public-transit disruptions."
)

SCOPE_AQI_COVERAGE: str = (
    "Air-quality assessment reflects available monitored-station forecasts "
    "and does not represent complete citywide coverage."
)

SCOPE_WEATHER_CHANGE: str = (
    "Weather forecasts may change; check again closer to departure."
)

# ---------------------------------------------------------------------------
# Travel-readiness decision matrix
#   Keys: (weather_risk, aqi_risk)
#   Values: readiness category
# ---------------------------------------------------------------------------

TRAVEL_READINESS_CATEGORIES: list[str] = [
    "Suitable",
    "Suitable with precautions",
    "Caution advised",
    "Avoid non-essential outdoor travel",
]

TRAVEL_READINESS_MATRIX: dict[tuple[str, str], str] = {
    ("Low", "Good"): "Suitable",
    ("Low", "Satisfactory"): "Suitable",
    ("Low", "Moderate"): "Suitable with precautions",
    ("Low", "Poor"): "Caution advised",
    ("Low", "Very Poor"): "Caution advised",
    ("Low", "Severe"): "Caution advised",
    ("Moderate", "Good"): "Suitable with precautions",
    ("Moderate", "Satisfactory"): "Suitable with precautions",
    ("Moderate", "Moderate"): "Caution advised",
    ("Moderate", "Poor"): "Caution advised",
    ("Moderate", "Very Poor"): "Avoid non-essential outdoor travel",
    ("Moderate", "Severe"): "Avoid non-essential outdoor travel",
    ("High", "Good"): "Caution advised",
    ("High", "Satisfactory"): "Caution advised",
    ("High", "Moderate"): "Caution advised",
    ("High", "Poor"): "Avoid non-essential outdoor travel",
    ("High", "Very Poor"): "Avoid non-essential outdoor travel",
    ("High", "Severe"): "Avoid non-essential outdoor travel",
    ("Severe", "Good"): "Avoid non-essential outdoor travel",
    ("Severe", "Satisfactory"): "Avoid non-essential outdoor travel",
    ("Severe", "Moderate"): "Avoid non-essential outdoor travel",
    ("Severe", "Poor"): "Avoid non-essential outdoor travel",
    ("Severe", "Very Poor"): "Avoid non-essential outdoor travel",
    ("Severe", "Severe"): "Avoid non-essential outdoor travel",
}

# ---------------------------------------------------------------------------
# Weather summary periods
# ---------------------------------------------------------------------------

WEATHER_SUMMARY_PERIODS: list[str] = ["next_24h", "tomorrow"]

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# FIRMS (NASA fire detection) — Milestone 7
# ---------------------------------------------------------------------------

FIRMS_CACHE_DIR: str = "data/raw/firms"
FIRMS_CACHE_TTL_MINUTES: int = 30
FIRMS_STALE_CACHE_MAX_HOURS: int = 24

# ---------------------------------------------------------------------------
# Sentinel-5P (TROPOMI NO2 column density) — Milestone 7
# ---------------------------------------------------------------------------

SENTINEL5P_CACHE_DIR: str = "data/raw/sentinel5p"
SENTINEL5P_CACHE_TTL_HOURS: int = 24
SENTINEL5P_STALE_CACHE_MAX_HOURS: int = 48

# ---------------------------------------------------------------------------
# Geospatial evidence configuration
# ---------------------------------------------------------------------------

GEOSPATIAL_ENABLED: bool = True
GEOSPATIAL_CITY_DEFAULT: str = "bengaluru"

# Bounding box for Bengaluru OSM queries (approx city limits)
BENGALURU_BOUNDING_BOX: dict[str, float] = {
    "north": 13.15,
    "south": 12.85,
    "east": 77.75,
    "west": 77.45,
}

# H3 resolution: resolution 9 → ~0.1 km² hexagons, ideal for neighbourhood-scale analysis
# Resolution  9 hexagon edge length ~174 m, area ~0.105 km²
# Resolution 10 hexagon edge length  ~66 m, area ~0.015 km²
H3_RESOLUTION: int = 9

# Default radii for station-context feature extraction
STATION_CONTEXT_RADIUS_METERS: float = 1000.0
ROAD_CONTEXT_RADIUS_METERS: float = 500.0

# OSM cache directory (project-relative)
OSM_CACHE_DIR: str = "data/raw/geospatial/osm"

# Geospatial output directories (project-relative)
GEOSPATIAL_RAW_DIR: str = "data/raw/geospatial"
GEOSPATIAL_PROCESSED_DIR: str = "data/processed/geospatial"
GEOSPATIAL_REPORTS_DIR: str = "data/reports/geospatial"

# OSM cache snapshot TTL
OSM_SNAPSHOT_TTL_DAYS: int = 30

# Feature builder version (semantic, bumped on meaningful changes)
GEOSPATIAL_FEATURE_BUILDER_VERSION: str = "1.0.0"

# Geospatial context radius for investigation (meters)
GEOSPATIAL_INVESTIGATION_CONTEXT_RADIUS_METERS: float = 1500.0

# CRS for metric area and distance calculations
GEOSPATIAL_METRIC_CRS: str = "EPSG:32643"  # UTM zone 43N (covers Bengaluru)

# Station registry path (project-relative)
STATION_REGISTRY_PATH: str = "data/reference/bengaluru_station_registry.csv"

# ---------------------------------------------------------------------------
# Attribution engine (Milestone 8)
# ---------------------------------------------------------------------------

# Maximum distance (meters) for source hexagons to contribute to attribution
ATTRIBUTION_SEARCH_RADIUS_METERS: float = 3000.0

# Wind speed threshold (km/h) below which directional weighting is skipped
ATTRIBUTION_CALM_WIND_SPEED_THRESHOLD_KMH: float = 1.0

# Maximum distance (meters) for stations to contribute IDW residual correction
FUSION_STATION_RANGE_METERS: float = 5000.0

# Path to precomputed per-hexagon feature parquet
HEXAGON_FEATURES_PATH: str = "data/processed/geospatial/hexagon_features.parquet"

# ---------------------------------------------------------------------------
# Google Maps configuration (Milestone 5B)
# ---------------------------------------------------------------------------

GOOGLE_MAPS_SERVER_API_KEY: str = os.getenv(
    "GOOGLE_MAPS_SERVER_API_KEY", ""
).strip()

GOOGLE_MAPS_BROWSER_API_KEY: str = os.getenv(
    "GOOGLE_MAPS_BROWSER_API_KEY", ""
).strip()

GOOGLE_MAPS_GEOCODING_ENABLED: bool = True
GOOGLE_MAPS_ROUTES_ENABLED: bool = True
GOOGLE_MAPS_PLACES_ENABLED: bool = False

GOOGLE_MAPS_TIMEOUT_SECONDS: float = 8.0
GOOGLE_MAPS_MAX_RETRIES: int = 2

GOOGLE_MAPS_BENGALURU_ONLY: bool = True

GOOGLE_MAPS_MAX_CANDIDATE_AREAS: int = 3

COMMUTE_MODE_DEFAULT: str = "DRIVE"
COMMUTE_MAX_DESTINATIONS: int = 3

# Supported travel modes for commute service
COMMUTE_SUPPORTED_MODES: list[str] = ["DRIVE", "TWO_WHEELER", "TRANSIT", "WALK"]

NEIGHBOURHOOD_SCORE_WEIGHTS: dict[str, float] = {
    "air_quality_component": 0.30,
    "forecast_confidence_component": 0.10,
    "green_space_proxy_component": 0.10,
    "road_mobility_proxy_component": 0.10,
    "commute_component": 0.20,
    "weather_disruption_component": 0.10,
    "data_coverage_component": 0.10,
}

NEIGHBOURHOOD_MIN_STATION_COVERAGE: float = 0.50  # 50% minimum station coverage

# Neighbourhood suitability disclaimer
NEIGHBOURHOOD_SUITABILITY_DISCLAIMER: str = (
    "Neighbourhood suitability decision-support estimate. "
    "This comparison uses nearby monitored-station evidence and mapped contextual proxies. "
    "It is not a direct pollution measurement at a home, school, or workplace address."
)
