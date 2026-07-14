"""Time-of-day traffic intensity multipliers for Bengaluru attribution.

Peak commuting windows amplify the traffic source weight so enforcement
ranking can distinguish rush-hour corridor risk from quiet night-time
road density. Purely multiplicative on the traffic intensity channel —
does not invent traffic volumes or live probe data.

Bengaluru local time (Asia/Kolkata) is used when hour is not provided.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BENGALURU_TZ = ZoneInfo("Asia/Kolkata")

# Multipliers (judgment calls, documented for review):
#   Morning peak 07:00–09:59 and evening peak 17:00–19:59 → 1.4
#   Daytime 10:00–16:59 → 1.1 (elevated activity, not peak)
#   Night / late evening / early morning → 0.7
PEAK_MULTIPLIER: float = 1.4
DAYTIME_MULTIPLIER: float = 1.1
OFFPEAK_MULTIPLIER: float = 0.7

MORNING_PEAK = range(7, 10)   # 7, 8, 9
EVENING_PEAK = range(17, 20)  # 17, 18, 19
DAYTIME = range(10, 17)       # 10 .. 16


def _resolve_hour(hour: int | None) -> int:
    if hour is None:
        return datetime.now(BENGALURU_TZ).hour
    try:
        h = int(hour)
    except (TypeError, ValueError):
        logger.warning("Invalid hour %r — using current Bengaluru hour", hour)
        return datetime.now(BENGALURU_TZ).hour
    return h % 24


def is_peak_hour(hour: int | None = None) -> bool:
    """True for Bengaluru morning/evening peak windows (local time)."""
    h = _resolve_hour(hour)
    return h in MORNING_PEAK or h in EVENING_PEAK


def get_traffic_time_multiplier(hour: int | None = None) -> float:
    """Return a traffic intensity multiplier for the given local hour.

    Parameters
    ----------
    hour:
        Optional hour in 0–23 (or any int, taken mod 24). When ``None``,
        uses the current hour in Asia/Kolkata.

    Returns
    -------
    float
        Multiplier applied to the traffic source intensity before
        attribution normalisation. Always > 0.
    """
    h = _resolve_hour(hour)
    if h in MORNING_PEAK or h in EVENING_PEAK:
        return PEAK_MULTIPLIER
    if h in DAYTIME:
        return DAYTIME_MULTIPLIER
    return OFFPEAK_MULTIPLIER


def traffic_time_metadata(hour: int | None = None) -> dict[str, Any]:
    """Bundle multiplier + peak flag + resolved hour for API responses."""
    h = _resolve_hour(hour)
    mult = get_traffic_time_multiplier(h)
    peak = is_peak_hour(h)
    return {
        "traffic_time_multiplier": mult,
        "is_peak_hour": peak,
        "traffic_hour_local": h,
        "traffic_timezone": "Asia/Kolkata",
    }
