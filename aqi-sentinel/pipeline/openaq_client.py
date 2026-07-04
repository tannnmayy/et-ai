from __future__ import annotations

import json
import logging
import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenAQConfigurationError(RuntimeError):
    """Raised when required OpenAQ configuration is missing or invalid."""


class OpenAQClientError(RuntimeError):
    """Raised for OpenAQ API errors that should stop the audit."""


class OpenAQAuthenticationError(OpenAQClientError):
    """Raised when the OpenAQ API key is rejected."""


@dataclass(frozen=True)
class OpenAQConfig:
    api_key: str
    base_url: str = "https://api.openaq.org/v3"
    timeout_seconds: float = 30.0
    max_retries: int = 4
    lookback_days: int = 365

    @classmethod
    def from_env(cls, load_dotenv_file: bool = True) -> "OpenAQConfig":
        if load_dotenv_file:
            load_dotenv()
        api_key = os.getenv("OPENAQ_API_KEY", "").strip()
        if not api_key:
            raise OpenAQConfigurationError("OPENAQ_API_KEY is missing. Create .env from .env.example and set the key locally.")
        return cls(
            api_key=api_key,
            base_url=os.getenv("OPENAQ_BASE_URL", cls.base_url).rstrip("/"),
            timeout_seconds=float(os.getenv("OPENAQ_TIMEOUT_SECONDS", cls.timeout_seconds)),
            max_retries=int(os.getenv("OPENAQ_MAX_RETRIES", cls.max_retries)),
            lookback_days=int(os.getenv("OPENAQ_LOOKBACK_DAYS", cls.lookback_days)),
        )


@dataclass(frozen=True)
class OpenAQLocation:
    location_id: int
    name: str
    latitude: float | None
    longitude: float | None
    locality: str | None
    country_code: str | None
    country_name: str | None
    is_active: bool | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class OpenAQSensor:
    sensor_id: int
    location_id: int
    parameter: str
    units: str | None
    raw_parameter_name: str
    raw: dict[str, Any]


class OpenAQClient:
    """Small OpenAQ v3 client with bounded retries, pagination, and raw-response caching."""

    def __init__(
        self,
        config: OpenAQConfig,
        raw_dir: Path | str = Path("data/raw/openaq"),
        session: requests.Session | None = None,
        sleep_func=time.sleep,
    ) -> None:
        self.config = config
        self.raw_dir = Path(raw_dir)
        self.session = session or requests.Session()
        self.sleep_func = sleep_func
        self.session.headers.update({"X-API-Key": config.api_key})

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None,
        resource_type: str,
        run_timestamp: str,
        refresh: bool = False,
        page_limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Fetch all pages for a v3 endpoint and return combined result records."""
        all_results: list[dict[str, Any]] = []
        page = 1
        while True:
            page_params = dict(params or {})
            page_params["limit"] = page_params.get("limit", page_limit)
            page_params["page"] = page
            cache_path = self._cache_path(resource_type, run_timestamp, page)
            payload = self._get_json(path, page_params, cache_path, refresh)
            results = payload.get("results")
            meta = payload.get("meta", {})
            if not isinstance(results, list):
                raise OpenAQClientError(f"OpenAQ response for {path} did not contain a list-valued results field.")
            all_results.extend(results)

            found = _safe_int(meta.get("found"))
            limit = _safe_int(meta.get("limit")) or page_limit
            current_page = _safe_int(meta.get("page")) or page
            if found is None:
                if len(results) < limit:
                    break
            elif current_page * limit >= found:
                break
            page += 1
        return all_results

    def get_locations_for_bbox(self, bbox: str, run_timestamp: str, refresh: bool = False) -> list[OpenAQLocation]:
        params = {"bbox": bbox, "limit": 1000, "page": 1, "order_by": "id", "sort_order": "asc"}
        records = self.paginate("/locations", params, "locations", run_timestamp, refresh)
        return [parse_location(record) for record in records]

    def get_sensors_for_location(self, location_id: int, run_timestamp: str, refresh: bool = False) -> list[OpenAQSensor]:
        records = self.paginate(
            f"/locations/{location_id}/sensors",
            {"limit": 1000, "page": 1},
            f"sensors_location_{location_id}",
            run_timestamp,
            refresh,
        )
        return [parse_sensor(record, location_id) for record in records]

    def get_hourly_measurements(
        self,
        sensor_id: int,
        datetime_from: str,
        datetime_to: str,
        run_timestamp: str,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        return self.paginate(
            f"/sensors/{sensor_id}/hours",
            {"datetime_from": datetime_from, "datetime_to": datetime_to, "limit": 1000, "page": 1},
            f"measurements_sensor_{sensor_id}",
            run_timestamp,
            refresh,
        )

    def _get_json(self, path: str, params: dict[str, Any], cache_path: Path, refresh: bool) -> dict[str, Any]:
        if cache_path.exists() and not refresh:
            logger.info("Using cached OpenAQ response %s", cache_path)
            return json.loads(cache_path.read_text(encoding="utf-8"))

        url = f"{self.config.base_url}{path if path.startswith('/') else '/' + path}"
        response = self._request(url, params)
        payload = response.json()
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    def _request(self, url: str, params: dict[str, Any]) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.config.timeout_seconds)
                if response.status_code in {401, 403}:
                    raise OpenAQAuthenticationError("OpenAQ authentication failed. Check OPENAQ_API_KEY in your local .env file.")
                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < self.config.max_retries:
                        self._sleep_before_retry(response, attempt)
                        continue
                    raise OpenAQClientError(f"OpenAQ request failed after retries with HTTP {response.status_code}: {response.text[:200]}")
                if 400 <= response.status_code < 500:
                    raise OpenAQClientError(f"OpenAQ request failed with HTTP {response.status_code}: {response.text[:200]}")
                response.raise_for_status()
                return response
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    self._sleep_before_retry(None, attempt)
                    continue
                raise OpenAQClientError(f"OpenAQ request failed after retries: {exc}") from exc
        raise OpenAQClientError(f"OpenAQ request failed: {last_error}")

    def _sleep_before_retry(self, response: requests.Response | None, attempt: int) -> None:
        retry_after = _retry_after_seconds(response.headers.get("Retry-After") if response is not None else None)
        delay = retry_after if retry_after is not None else min(60.0, (2**attempt) + random.uniform(0, 0.5))
        logger.warning("Retrying OpenAQ request after %.2f seconds.", delay)
        self.sleep_func(delay)

    def _cache_path(self, resource_type: str, run_timestamp: str, page: int) -> Path:
        safe_resource = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in resource_type)
        return self.raw_dir / f"{safe_resource}_{run_timestamp}_page_{page:03d}.json"


def utc_run_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def parse_location(record: dict[str, Any]) -> OpenAQLocation:
    coordinates = record.get("coordinates") or {}
    country = record.get("country") or {}
    location_id = record.get("id")
    if location_id is None:
        raise OpenAQClientError("OpenAQ location record is missing id.")
    return OpenAQLocation(
        location_id=int(location_id),
        name=str(record.get("name") or f"location_{location_id}"),
        latitude=_safe_float(coordinates.get("latitude")),
        longitude=_safe_float(coordinates.get("longitude")),
        locality=record.get("locality"),
        country_code=country.get("code") if isinstance(country, dict) else None,
        country_name=country.get("name") if isinstance(country, dict) else None,
        is_active=record.get("isActive") if isinstance(record.get("isActive"), bool) else record.get("active"),
        raw=record,
    )


def parse_sensor(record: dict[str, Any], location_id: int) -> OpenAQSensor:
    parameter = record.get("parameter") or {}
    sensor_id = record.get("id")
    if sensor_id is None:
        raise OpenAQClientError("OpenAQ sensor record is missing id.")
    raw_name = str(parameter.get("name") or parameter.get("displayName") or record.get("name") or "").strip()
    units = parameter.get("units") or record.get("units")
    normalized = normalize_parameter_name(raw_name)
    return OpenAQSensor(
        sensor_id=int(sensor_id),
        location_id=int(location_id),
        parameter=normalized,
        units=str(units) if units is not None else None,
        raw_parameter_name=raw_name,
        raw=record,
    )


def normalize_parameter_name(value: str | None) -> str:
    text = (value or "").lower().replace(" ", "").replace("_", "").replace(".", "")
    if text in {"pm25", "pm2,5"}:
        return "pm25"
    if text in {"pm10", "pm-10"}:
        return "pm10"
    if text in {"no2", "nitrogendioxide"}:
        return "no2"
    return text


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_time = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_time.tzinfo is None:
            retry_time = retry_time.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_time - datetime.now(timezone.utc)).total_seconds())
