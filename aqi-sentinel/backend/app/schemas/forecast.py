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
