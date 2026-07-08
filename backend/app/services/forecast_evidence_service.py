from __future__ import annotations

import logging

from backend.app.config import (
    DEFAULT_INSPECTION_FOCUS,
    HIGH_NO2_FOCUS,
    HIGH_PM10_FOCUS,
    PM25_IMPROVING_THRESHOLD,
    PM25_RISK_THRESHOLDS,
    PM25_WORSENING_THRESHOLD,
)
from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
    get_lightgbm_explanation_context,
    get_station_evaluation,
    get_station_quality,
    get_station_snapshot,
)

logger = logging.getLogger(__name__)

PERSISTENCE_EVIDENCE_TEMPLATE = (
    "Persistence was selected because it outperformed or matched the pooled LightGBM "
    "model on held-out chronological data for this station. The forecast is based on "
    "PM2.5 observed exactly 24 hours earlier. Persistence validation RMSE: {rmse:.1f} "
    "ug/m3 vs LightGBM RMSE: {lgbm_rmse:.1f} ug/m3."
)

LIGHTGBM_EVIDENCE_TEMPLATE = (
    "Pooled LightGBM was selected because it outperformed persistence on held-out "
    "chronological data for this station. LightGBM validation RMSE: {lgbm_rmse:.1f} "
    "ug/m3 vs Persistence RMSE: {rmse:.1f} ug/m3."
)


def _compute_expected_change(predicted_pm25: float, latest_observed: float | None) -> tuple[float | None, str]:
    if latest_observed is None:
        return None, "unavailable"
    change = predicted_pm25 - latest_observed
    if change >= PM25_WORSENING_THRESHOLD:
        return round(change, 2), "worsening"
    if change <= PM25_IMPROVING_THRESHOLD:
        return round(change, 2), "improving"
    return round(change, 2), "stable"


def _persistence_evidence(eval_data: dict) -> list[dict]:
    rmse = eval_data.get("persistence_rmse", 0)
    lgbm_rmse = eval_data.get("lightgbm_rmse")
    evidence_items = []
    evidence_items.append({
        "factor": "forecast_engine",
        "direction": "for",
        "weight": 0.5,
        "description": PERSISTENCE_EVIDENCE_TEMPLATE.format(
            rmse=rmse, lgbm_rmse=lgbm_rmse if lgbm_rmse else "N/A"
        ),
    })
    evidence_items.append({
        "factor": "exact_24h_reference",
        "direction": "for",
        "weight": 0.5,
        "description": (
            "The forecast equals the PM2.5 value observed exactly 24 hours before "
            "the forecast origin. This is a direct reference, not a model inference."
        ),
    })
    return evidence_items


def _lightgbm_evidence(eval_data: dict, context: dict | None) -> list[dict]:
    rmse = eval_data.get("persistence_rmse", 0)
    lgbm_rmse = eval_data.get("lightgbm_rmse", 0)
    evidence_items = []
    evidence_items.append({
        "factor": "forecast_engine",
        "direction": "for",
        "weight": 0.4,
        "description": LIGHTGBM_EVIDENCE_TEMPLATE.format(
            lgbm_rmse=lgbm_rmse, rmse=rmse
        ),
    })
    if context:
        lag_vals = context.get("lag_values", {})
        roll_vals = context.get("rolling_values", {})
        temporal = context.get("temporal_context", {})
        weather = context.get("pollutant_weather_context", {})

        pm25_24h = lag_vals.get("pm25_lag_24h")
        pm25_1h = lag_vals.get("pm25_lag_1h")
        if pm25_24h is not None and pm25_1h is not None:
            trend_desc = "elevated recent particulate levels" if pm25_1h > pm25_24h else "declining recent particulate levels"
            evidence_items.append({
                "factor": "recent_trend",
                "direction": "for" if pm25_1h > pm25_24h else "against",
                "weight": 0.2,
                "description": f"The available station pattern is consistent with {trend_desc}.",
            })

        roll_24h = roll_vals.get("pm25_roll_mean_24h")
        if roll_24h is not None:
            evidence_items.append({
                "factor": "rolling_average",
                "direction": "for",
                "weight": 0.15,
                "description": f"24-hour rolling average PM2.5 is {roll_24h:.1f} ug/m3.",
            })

        hour = temporal.get("hour")
        if hour is not None:
            evidence_items.append({
                "factor": "temporal_context",
                "direction": "for",
                "weight": 0.1,
                "description": f"Forecast origin hour is {int(hour)}:00 UTC.",
            })

        pm10 = weather.get("pm10_lag_1h")
        no2 = weather.get("no2_lag_1h")
        if pm10 is not None:
            evidence_items.append({
                "factor": "pm10_context",
                "direction": "for",
                "weight": 0.08,
                "description": f"Recent PM10 context is {pm10:.1f} ug/m3.",
            })
        if no2 is not None:
            evidence_items.append({
                "factor": "no2_context",
                "direction": "for",
                "weight": 0.07,
                "description": f"Recent NO2 context is {no2:.1f} ug/m3.",
            })

    return evidence_items


def _build_caveats(quality: dict, eval_data: dict) -> list[str]:
    caveats = []
    classification = quality.get("classification", "")
    if "Usable" in classification:
        caveats.append(
            f"Station data quality is classified as '{classification}'. "
            "Results should be interpreted cautiously."
        )
    rmse = eval_data.get("persistence_rmse", 0)
    if rmse > 25:
        caveats.append(
            f"Selected model RMSE ({rmse:.1f} ug/m3) indicates moderate-to-high prediction uncertainty."
        )
    test_rows = eval_data.get("test_rows", 0)
    if test_rows < 100:
        caveats.append(f"Only {test_rows} test rows available; evaluation may be limited.")
    return caveats


def _non_eligible_evidence_response(
    station_id: str, snapshot: dict, city: str
) -> dict:
    status = snapshot.get("pm25_forecast_coverage_status", "unknown")
    return {
        "station_id": station_id,
        "station_name": snapshot.get("station_name", station_id),
        "city": snapshot.get("city", city),
        "forecast_engine": "unavailable",
        "explanation_method": "unavailable",
        "prediction_origin": "",
        "forecast_for": "",
        "predicted_pm25": 0,
        "latest_observed_pm25": None,
        "latest_observed_at": None,
        "expected_change_pm25": None,
        "expected_change_direction": "unavailable",
        "risk_category": "Unknown",
        "model_validation_summary": "Station is not forecast-eligible.",
        "evidence_items": [],
        "caveats": [f"Station is not forecast-eligible: {status}."],
        "data_quality_classification": "Not eligible",
        "data_quality_note": status,
        "forecast_eligible": False,
        "pm25_forecast_coverage_status": status,
        "available_pollutants": snapshot.get("available_pollutants", []),
    }


def get_forecast_evidence(station_id: str, city: str = "bengaluru") -> dict:
    """Generate structured evidence for a station's forecast."""
    try:
        snapshot = get_station_snapshot(station_id, city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError):
        raise

    if not snapshot.get("forecast_eligible", True):
        return _non_eligible_evidence_response(station_id, snapshot, city)

    eval_data = get_station_evaluation(station_id)
    quality = get_station_quality(station_id)
    forecast_engine = snapshot["forecast_engine"]
    predicted_pm25 = snapshot["predicted_pm25"]
    latest_observed = snapshot.get("latest_observed_pm25")

    expected_change, change_direction = _compute_expected_change(predicted_pm25, latest_observed)

    if forecast_engine == "persistence":
        explanation_method = "exact_24h_reference"
        evidence_items = _persistence_evidence(eval_data)
    else:
        explanation_method = "model_context_fallback"
        context = get_lightgbm_explanation_context(station_id)
        evidence_items = _lightgbm_evidence(eval_data, context)

    validation_summary = (
        f"Selected engine: {forecast_engine}. "
        f"Test rows: {eval_data.get('test_rows', 0)}. "
        f"RMSE improvement: {eval_data.get('rmse_improvement_percent', 0):+.1f}%."
    )

    caveats = _build_caveats(quality, eval_data)

    return {
        "station_id": station_id,
        "station_name": snapshot["station_name"],
        "city": snapshot["city"],
        "forecast_engine": forecast_engine,
        "explanation_method": explanation_method,
        "prediction_origin": snapshot["prediction_origin"],
        "forecast_for": snapshot["forecast_for"],
        "predicted_pm25": predicted_pm25,
        "latest_observed_pm25": latest_observed,
        "latest_observed_at": snapshot.get("latest_observed_at"),
        "expected_change_pm25": expected_change,
        "expected_change_direction": change_direction,
        "risk_category": snapshot["risk_category"],
        "model_validation_summary": validation_summary,
        "evidence_items": evidence_items,
        "caveats": caveats,
        "data_quality_classification": quality["classification"],
        "data_quality_note": quality["recommendation"],
        "forecast_eligible": True,
        "pm25_forecast_coverage_status": None,
        "available_pollutants": [],
    }
