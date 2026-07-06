from __future__ import annotations

import logging
import time
from typing import Any

import requests

from backend.app.config import (
    OPEN_METEO_HOURLY_FIELDS,
    WEATHER_BENGALURU_LATITUDE,
    WEATHER_BENGALURU_LONGITUDE,
    WEATHER_HTTP_TIMEOUT_SECONDS,
    WEATHER_HTTP_USER_AGENT,
    WEATHER_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.open-meteo.com/v1/forecast"

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class WeatherProviderError(Exception):
    """Raised when the weather provider cannot be reached or returns an error."""


def _get_coordinates(city: str) -> tuple[float, float]:
    if city.lower().strip() == "bengaluru":
        return WEATHER_BENGALURU_LATITUDE, WEATHER_BENGALURU_LONGITUDE
    raise ValueError(f"Unsupported city for weather: {city}")


def fetch_open_meteo_forecast(
    city: str = "bengaluru",
    horizon_hours: int = 72,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch raw hourly forecast from Open-Meteo.

    Returns the parsed JSON response dict.
    Raises WeatherProviderError on failure.
    """
    lat, lon = _get_coordinates(city)
    forecast_days = max(1, (horizon_hours + 23) // 24)

    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(OPEN_METEO_HOURLY_FIELDS),
        "timezone": "Asia/Kolkata",
        "forecast_days": forecast_days,
    }

    headers = {"User-Agent": WEATHER_HTTP_USER_AGENT}
    close_session = False
    if session is None:
        session = requests.Session()
        close_session = True

    last_error: Exception | None = None
    for attempt in range(1, WEATHER_MAX_RETRIES + 1):
        try:
            resp = session.get(
                BASE_URL,
                params=params,
                headers=headers,
                timeout=WEATHER_HTTP_TIMEOUT_SECONDS,
            )
            if resp.status_code == 200:
                data = resp.json()
                _validate_raw_response(data, forecast_days)
                return data
            if resp.status_code in RETRYABLE_STATUSES:
                retry_after = _parse_retry_after(resp)
                if attempt < WEATHER_MAX_RETRIES:
                    wait = retry_after if retry_after else 1.0 * attempt
                    logger.warning(
                        "Open-Meteo HTTP %d (attempt %d/%d), retrying in %.1fs",
                        resp.status_code, attempt, WEATHER_MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    continue
                raise WeatherProviderError(
                    f"Open-Meteo returned HTTP {resp.status_code} after "
                    f"{WEATHER_MAX_RETRIES} attempts."
                )
            raise WeatherProviderError(
                f"Open-Meteo returned non-retryable HTTP {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
            if attempt < WEATHER_MAX_RETRIES:
                wait = 1.0 * attempt
                logger.warning(
                    "Open-Meteo connection error (attempt %d/%d): %s, retrying in %.1fs",
                    attempt, WEATHER_MAX_RETRIES, e, wait,
                )
                time.sleep(wait)
            else:
                raise WeatherProviderError(
                    f"Open-Meteo unreachable after {WEATHER_MAX_RETRIES} attempts: {e}"
                ) from e
    if close_session:
        session.close()
    if last_error:
        raise WeatherProviderError(
            f"Open-Meteo request failed after {WEATHER_MAX_RETRIES} attempts: {last_error}"
        ) from last_error
    raise WeatherProviderError(
        f"Open-Meteo request failed after {WEATHER_MAX_RETRIES} attempts (unknown cause)."
    )


def _parse_retry_after(resp: requests.Response) -> float | None:
    val = resp.headers.get("Retry-After")
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _validate_raw_response(data: dict[str, Any], expected_days: int) -> None:
    if "hourly" not in data:
        raise WeatherProviderError("Open-Meteo response missing 'hourly' key.")
    hourly = data["hourly"]
    if "time" not in hourly:
        raise WeatherProviderError("Open-Meteo hourly data missing 'time' array.")
    times = hourly["time"]
    expected_hours = expected_days * 24
    if len(times) < expected_hours - 1:
        raise WeatherProviderError(
            f"Open-Meteo returned {len(times)} timestamps, expected ~{expected_hours}."
        )
    for field in OPEN_METEO_HOURLY_FIELDS:
        if field not in hourly:
            raise WeatherProviderError(
                f"Open-Meteo hourly data missing field '{field}'."
            )
        if not isinstance(hourly[field], list):
            raise WeatherProviderError(
                f"Open-Meteo field '{field}' is not a list."
            )
        if len(hourly[field]) != len(times):
            raise WeatherProviderError(
                f"Open-Meteo field '{field}' length {len(hourly[field])} "
                f"does not match time array length {len(times)}."
            )
