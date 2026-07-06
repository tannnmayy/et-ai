from __future__ import annotations

from pydantic import BaseModel, Field


class WeatherComponent(BaseModel):
    weather_available: bool
    weather_risk_level: str | None = None
    weather_summary: str | None = None
    weather_caution_reasons: list[str] = Field(default_factory=list)
    provider: str | None = None
    source_status: str | None = None
    freshness: str | None = None


class AirQualityComponent(BaseModel):
    aqi_available: bool
    city_risk_level: str | None = None
    executive_summary: str | None = None
    monitored_stations_note: str | None = None
    high_risk_station_areas: list[str] = Field(default_factory=list)


class TravelReadinessResponse(BaseModel):
    city: str
    profile: str
    period: str
    weather_component: WeatherComponent
    air_quality_component: AirQualityComponent
    final_readiness: str | None = Field(description="Suitable, Suitable with precautions, Caution advised, Avoid non-essential outdoor travel, or None if unavailable")
    readiness_basis: str = Field(description="weather_and_air_quality, weather_only_partial, air_quality_only_partial, or unavailable")
    decision_reasons: list[str] = Field(default_factory=list)
    profile_specific_precautions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    medical_disclaimer: str | None = None
    warnings: list[str] = Field(default_factory=list)
