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
    model_config = {"protected_namespaces": ()}
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
    # Uncertainty (from held-out test RMSE; approximate Gaussian band)
    selected_model: str | None = Field(
        default=None,
        description="Model selected for serving at eval time (lightgbm|persistence)",
    )
    interval_low_pm25: float | None = Field(
        default=None, description="Approx. lower bound: max(0, pred − 1·RMSE)"
    )
    interval_high_pm25: float | None = Field(
        default=None, description="Approx. upper bound: pred + 1·RMSE"
    )
    interval_method: str | None = Field(
        default=None,
        description="e.g. test_rmse_gaussian_z1 (~68% if residuals ~N(0,RMSE²))",
    )
    prediction_uncertainty_level: str | None = Field(
        default=None, description="High|Medium|Low model-error uncertainty from RMSE"
    )
    prediction_uncertainty_reason: str | None = None


class MultiStationForecastResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    city: str
    data_mode: str
    generated_at: str
    station_count: int
    model_selection_strategy: str
    forecasts: list[MultiStationStationForecast]


class StationStatusItem(BaseModel):
    model_config = {"protected_namespaces": ()}
    station_id: str
    station_name: str
    data_available: bool
    hourly_available: bool
    features_available: bool
    model_available: bool
    quality_classification: str | None = None
    forecast_eligible: bool = True
    pm25_forecast_coverage_status: str | None = None
    available_pollutants: list[str] = []


class StationStatusResponse(BaseModel):
    city: str
    station_count: int
    stations: list[StationStatusItem]
