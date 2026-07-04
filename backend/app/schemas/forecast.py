from __future__ import annotations

from pydantic import BaseModel, Field


class StationForecast(BaseModel):
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    prediction_origin: str
    forecast_for: str
    predicted_pm25: float = Field(ge=0)
    risk_category: str


class ForecastResponse(BaseModel):
    city: str
    data_mode: str
    forecast_engine: str
    generated_at: str
    forecasts: list[StationForecast]


class RealHebbalForecastResponse(BaseModel):
    city: str
    station_id: str
    station_name: str
    data_mode: str
    source: str
    forecast_engine: str
    prediction_origin: str
    forecast_for: str
    predicted_pm25: float = Field(ge=0)
    risk_category: str
    data_quality_classification: str
    data_quality_note: str


class MultiStationStationForecast(BaseModel):
    station_id: str
    station_name: str
    data_mode: str
    source: str
    forecast_engine: str
    prediction_origin: str
    forecast_for: str
    predicted_pm25: float = Field(ge=0)
    risk_category: str
    model_rmse_on_test: float | None = None


class MultiStationForecastResponse(BaseModel):
    city: str
    data_mode: str
    generated_at: str
    station_count: int
    model_selection_strategy: str
    forecasts: list[MultiStationStationForecast]


class StationStatusItem(BaseModel):
    station_id: str
    station_name: str
    data_available: bool
    hourly_available: bool
    features_available: bool
    model_available: bool
    quality_classification: str | None = None


class StationStatusResponse(BaseModel):
    city: str
    station_count: int
    stations: list[StationStatusItem]
