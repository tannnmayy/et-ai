from __future__ import annotations

from datetime import timezone

import pandas as pd

from backend.app.config import (
    CONFIDENCE_COMPLETENESS_PENALTIES,
    CONFIDENCE_FRESHNESS_PENALTIES,
    CONFIDENCE_GAP_PENALTIES,
    CONFIDENCE_LEVELS,
    CONFIDENCE_QUALITY_PENALTIES,
    CONFIDENCE_UNAVAILABLE_THRESHOLD,
    get_project_root,
)
from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
    _validate_city,
    _validate_station,
    get_station_recent_observations,
    get_station_snapshot,
    _load_all_artifacts,
)
from pipeline.station_registry import get_station_by_id, station_output_dir

import logging

logger = logging.getLogger(__name__)


def _compute_latest_observation_age_hours(observations: list[dict]) -> float | None:
    if not observations:
        return None
    timestamps = []
    for obs in observations:
        ts_str = obs.get("timestamp")
        if ts_str is not None:
            try:
                ts = pd.Timestamp(ts_str)
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                timestamps.append(ts)
            except Exception:
                continue
    if not timestamps:
        return None
    latest = max(timestamps)
    now = pd.Timestamp.now(tz=timezone.utc)
    age_hours = (now - latest).total_seconds() / 3600
    return round(age_hours, 2)


def _compute_recent_completeness(observations: list[dict]) -> float | None:
    if not observations:
        return None
    pm25_values = [obs.get("pm25") for obs in observations if obs.get("pm25") is not None]
    total = len(observations)
    if total == 0:
        return None
    return round(len(pm25_values) / total * 100, 2)


def _compute_recent_gap_hours(observations: list[dict]) -> int | None:
    if not observations:
        return None
    pm25_obs = [(obs.get("timestamp"), obs.get("pm25")) for obs in observations]
    timestamps_with_values = []
    for ts_str, val in pm25_obs:
        if val is not None and ts_str is not None:
            try:
                ts = pd.Timestamp(ts_str)
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                timestamps_with_values.append(ts)
            except Exception:
                continue
    if len(timestamps_with_values) < 2:
        return 0
    timestamps_with_values.sort()
    max_gap = 0
    for i in range(1, len(timestamps_with_values)):
        gap = (timestamps_with_values[i] - timestamps_with_values[i - 1]).total_seconds() / 3600
        max_gap = max(max_gap, gap)
    return int(max_gap)


def get_forecast_confidence(station_id: str, city: str = "bengaluru") -> dict:
    """Compute forecast confidence for a station (data reliability only, no persistence penalty)."""
    try:
        snapshot = get_station_snapshot(station_id, city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError):
        raise

    quality = snapshot.get("quality_classification", "Unknown")
    score = 100
    reasons: list[str] = []
    blockers: list[str] = []

    observations = get_station_recent_observations(station_id, lookback_hours=72)

    age_hours = _compute_latest_observation_age_hours(observations)
    completeness = _compute_recent_completeness(observations)
    gap_hours = _compute_recent_gap_hours(observations)

    for rule in CONFIDENCE_FRESHNESS_PENALTIES:
        if age_hours is not None and age_hours > rule["min_age_hours"]:
            score -= rule["penalty"]
            reasons.append(f"Latest observation is {age_hours:.1f}h old (>{rule['min_age_hours']}h penalty)")
            break

    for rule in CONFIDENCE_COMPLETENESS_PENALTIES:
        if completeness is not None and completeness < rule["max_percent"]:
            score -= rule["penalty"]
            reasons.append(f"Recent PM2.5 completeness is {completeness:.1f}% (<{rule['max_percent']}% penalty)")
            break

    for rule in CONFIDENCE_GAP_PENALTIES:
        if gap_hours is not None and gap_hours > rule["min_hours"]:
            score -= rule["penalty"]
            reasons.append(f"Recent PM2.5 gap is {gap_hours}h (>{rule['min_hours']}h penalty)")
            break

    quality_penalty = CONFIDENCE_QUALITY_PENALTIES.get(quality, 0)
    if quality_penalty > 0:
        score -= quality_penalty
        reasons.append(f"Station quality classified as '{quality}' (-{quality_penalty} penalty)")

    score = max(0, min(100, score))

    if not reasons:
        reasons.append("Station data meets freshness, completeness, and quality thresholds.")

    confidence_level = "Unavailable"
    for level_rule in CONFIDENCE_LEVELS:
        if score >= level_rule["min_score"]:
            confidence_level = level_rule["level"]
            break

    if confidence_level == "Unavailable":
        blockers.append("Forecast data reliability is below the minimum threshold.")

    return {
        "station_id": station_id,
        "station_name": snapshot["station_name"],
        "city": snapshot["city"],
        "confidence_level": confidence_level,
        "confidence_score": score if confidence_level != "Unavailable" else None,
        "latest_observation_age_hours": age_hours,
        "recent_pm25_completeness_percent": completeness,
        "recent_gap_hours": gap_hours,
        "selected_engine": snapshot["forecast_engine"],
        "quality_classification": quality,
        "reasons": reasons,
        "blockers": blockers,
    }
