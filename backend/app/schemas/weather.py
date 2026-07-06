from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NormalizedHourlyRecord(BaseModel):
    timestamp_local: str = Field(description="Local time ISO format")
    temperature_c: float | None = Field(default=None, ge=-50, le=60)
    apparent_temperature_c: float | None = Field(default=None, ge=-50, le=60)
    relative_humidity_percent: float | None = Field(default=None, ge=0, le=100)
    precipitation_probability_percent: float | None = Field(default=None, ge=0, le=100)
    precipitation_mm: float | None = Field(default=None, ge=0)
    rain_mm: float | None = Field(default=None, ge=0)
    showers_mm: float | None = Field(default=None, ge=0)
    snowfall_cm: float | None = Field(default=None, ge=0)
    weather_code: int | None = Field(default=None, ge=0, le=99)
    weather_description: str = Field(default="Unknown")
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    wind_gust_kmh: float | None = Field(default=None, ge=0)


class NormalizedWeatherForecast(BaseModel):
    city: str
    timezone: str
    latitude: float
    longitude: float
    generated_at: str = Field(description="When the provider generated this data")
    retrieved_at: str = Field(description="When we retrieved this data")
    forecast_start: str | None = None
    forecast_end: str | None = None
    provider: str
    source_status: str = Field(description="live_provider or stale_cache_fallback")
    cache_used: bool
    freshness: str = Field(description="fresh or stale")
    age_minutes: float | None = None
    hourly: list[NormalizedHourlyRecord]
    warnings: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class WeatherSummaryResponse(BaseModel):
    city: str
    timezone: str
    period: str
    provider: str
    source_status: str
    cache_used: bool
    freshness: str
    age_minutes: float | None = None
    generated_at: str
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    apparent_temperature_min_c: float | None = None
    apparent_temperature_max_c: float | None = None
    max_precipitation_probability_percent: float | None = None
    total_precipitation_mm: float = 0
    max_wind_speed_kmh: float | None = None
    max_wind_gust_kmh: float | None = None
    dominant_weather_code: int | None = None
    dominant_weather_description: str = "Unknown"
    severe_weather_present: bool = False
    weather_risk_level: str = "Low"
    weather_risk_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WeatherForecastResponse(BaseModel):
    city: str
    timezone: str
    latitude: float
    longitude: float
    provider: str
    source_status: str
    cache_used: bool
    freshness: str
    age_minutes: float | None = None
    generated_at: str
    retrieved_at: str
    forecast_start: str | None = None
    forecast_end: str | None = None
    hourly: list[NormalizedHourlyRecord]
    hourly_count: int
    summary_periods: dict[str, Any] = Field(default_factory=dict, description="Pre-computed summaries for next_24h and tomorrow")
    warnings: list[str] = Field(default_factory=list)
