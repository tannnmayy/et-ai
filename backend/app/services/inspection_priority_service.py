from __future__ import annotations

from datetime import timezone

import pandas as pd

from backend.app.config import (
    DEFAULT_INSPECTION_FOCUS,
    HIGH_NO2_FOCUS,
    HIGH_PM10_FOCUS,
    INVESTIGATION_DISCLAIMER,
    INSPECTION_CONFIDENCE_ADJUSTMENTS,
    INSPECTION_ELEVATED_RULES,
    INSPECTION_PRIORITY_LEVELS,
    INSPECTION_QUALITY_ADJUSTMENTS,
    INSPECTION_SEVERITY_SCORES,
    INSPECTION_WORSENING_RULES,
    STATION_INSPECTION_FOCUS,
    PM25_IMPROVING_THRESHOLD,
    PM25_WORSENING_THRESHOLD,
)
from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
    _validate_city,
    get_station_recent_observations,
    get_station_snapshot,
    list_station_snapshots,
)
from backend.app.services.confidence_service import get_forecast_confidence

import logging

logger = logging.getLogger(__name__)


def _severity_score(risk_category: str) -> int:
    return INSPECTION_SEVERITY_SCORES.get(risk_category, 0)


def _worsening_score(expected_change: float | None) -> int:
    if expected_change is None:
        return 0
    for rule in INSPECTION_WORSENING_RULES:
        if expected_change >= rule["min_change"]:
            return rule["score"]
    return 0


def _elevated_pm25_score(recent_observations: list[dict]) -> int:
    pm25_values = [obs.get("pm25") for obs in recent_observations if obs.get("pm25") is not None]
    if not pm25_values:
        return 0
    mean_24h = sum(pm25_values[-24:]) / max(len(pm25_values[-24:]), 1)
    for rule in INSPECTION_ELEVATED_RULES:
        if mean_24h >= rule["min_pm25"]:
            return rule["score"]
    return 0


def _confidence_adjustment(confidence_level: str) -> int:
    return INSPECTION_CONFIDENCE_ADJUSTMENTS.get(confidence_level, 0)


def _quality_adjustment(quality_classification: str) -> int:
    return INSPECTION_QUALITY_ADJUSTMENTS.get(quality_classification, 0)


def _priority_level(score: int) -> str:
    for rule in INSPECTION_PRIORITY_LEVELS:
        if score >= rule["min_score"]:
            return rule["level"]
    return "Watch"


def _get_inspection_focus(station_id: str, recent_observations: list[dict]) -> str:
    if station_id in STATION_INSPECTION_FOCUS:
        return STATION_INSPECTION_FOCUS[station_id]

    pm10_values = [obs.get("pm10") for obs in recent_observations if obs.get("pm10") is not None]
    no2_values = [obs.get("no2") for obs in recent_observations if obs.get("no2") is not None]

    if pm10_values:
        recent_pm10_mean = sum(pm10_values[-6:]) / max(len(pm10_values[-6:]), 1)
        if recent_pm10_mean > 100:
            return HIGH_PM10_FOCUS

    if no2_values:
        recent_no2_mean = sum(no2_values[-6:]) / max(len(no2_values[-6:]), 1)
        if recent_no2_mean > 40:
            return HIGH_NO2_FOCUS

    return DEFAULT_INSPECTION_FOCUS


def _build_rationale(
    risk_category: str, expected_change: float | None, change_direction: str,
    confidence_level: str, quality_classification: str, predicted_pm25: float,
) -> str:
    parts = [f"Predicted PM2.5 is {predicted_pm25:.1f} ug/m3 ({risk_category})."]
    if change_direction == "worsening" and expected_change is not None:
        parts.append(f"Expected change is +{expected_change:.1f} ug/m3 (worsening).")
    elif change_direction == "improving" and expected_change is not None:
        parts.append(f"Expected change is {expected_change:.1f} ug/m3 (improving).")
    parts.append(f"Confidence: {confidence_level}. Quality: {quality_classification}.")
    return " ".join(parts)


def _build_caveats(confidence_level: str, quality_classification: str) -> list[str]:
    caveats = []
    if confidence_level in ("Low", "Unavailable"):
        caveats.append("Forecast confidence is limited; inspection results should be verified.")
    if "Usable" in quality_classification:
        caveats.append(f"Station data quality is '{quality_classification}'.")
    caveats.append(INVESTIGATION_DISCLAIMER)
    return caveats


def get_inspection_priorities(city: str = "bengaluru", top_k: int = 5) -> dict:
    """Rank stations for MPCB inspection by deterministic priority scoring."""
    _validate_city(city)
    snapshots = list_station_snapshots(city=city)

    ranked = []
    for snap in snapshots:
        sid = snap["station_id"]
        predicted_pm25 = snap["predicted_pm25"]
        risk_category = snap["risk_category"]
        forecast_engine = snap["forecast_engine"]
        quality_classification = snap["quality_classification"]

        conf_data = get_forecast_confidence(sid, city=city)
        confidence_level = conf_data["confidence_level"]

        observations = get_station_recent_observations(sid, lookback_hours=24)

        from backend.app.services.forecast_evidence_service import _compute_expected_change
        expected_change, change_direction = _compute_expected_change(
            predicted_pm25, snap.get("latest_observed_pm25")
        )

        severity = _severity_score(risk_category)
        worsening = _worsening_score(expected_change)
        elevated = _elevated_pm25_score(observations)
        conf_adj = _confidence_adjustment(confidence_level)
        qual_adj = _quality_adjustment(quality_classification)

        raw_score = severity + worsening + elevated + conf_adj + qual_adj
        priority_score = max(0, min(100, raw_score))
        priority_level = _priority_level(priority_score)

        scoring_breakdown = {
            "forecast_severity": severity,
            "worsening": worsening,
            "recent_elevated_pm25": elevated,
            "confidence_adjustment": conf_adj,
            "quality_adjustment": qual_adj,
            "raw_score": raw_score,
            "clamped_score": priority_score,
        }

        inspection_focus = _get_inspection_focus(sid, observations)
        rationale = _build_rationale(
            risk_category, expected_change, change_direction,
            confidence_level, quality_classification, predicted_pm25,
        )
        caveats = _build_caveats(confidence_level, quality_classification)

        ranked.append({
            "station_id": sid,
            "station_name": snap["station_name"],
            "city": snap["city"],
            "priority_score": priority_score,
            "priority_level": priority_level,
            "predicted_pm25": predicted_pm25,
            "risk_category": risk_category,
            "expected_change_pm25": expected_change,
            "forecast_engine": forecast_engine,
            "confidence_level": confidence_level,
            "data_quality_classification": quality_classification,
            "scoring_breakdown": scoring_breakdown,
            "recommended_inspection_focus": inspection_focus,
            "rationale": rationale,
            "caveats": caveats,
            "investigation_disclaimer": INVESTIGATION_DISCLAIMER,
        })

    ranked.sort(key=lambda x: (x["priority_score"], x["predicted_pm25"]), reverse=True)
    ranked.sort(key=lambda x: x["station_id"])

    for i, item in enumerate(ranked, start=1):
        item["rank"] = i

    ranked.sort(key=lambda x: (-x["priority_score"], -x["predicted_pm25"], x["station_id"]))
    for i, item in enumerate(ranked, start=1):
        item["rank"] = i

    return {
        "city": SUPPORTED_CITY_DISPLAY(city),
        "generated_at": pd.Timestamp.now(tz=timezone.utc).isoformat(),
        "total_stations": len(ranked),
        "top_k": min(top_k, len(ranked)),
        "ranked_stations": ranked[:top_k],
    }


def SUPPORTED_CITY_DISPLAY(city: str) -> str:
    from backend.app.config import SUPPORTED_CITIES
    return SUPPORTED_CITIES[city.lower().strip()]["display_name"]
