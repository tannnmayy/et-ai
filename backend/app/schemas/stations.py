from __future__ import annotations

from pydantic import BaseModel, Field


class StationInfo(BaseModel):
    station_id: str = Field(description="Unique station identifier")
    display_name: str = Field(description="Human-readable station name")
    city: str = Field(description="City name")
    latitude: float | None = Field(None, description="Station latitude")
    longitude: float | None = Field(None, description="Station longitude")
    source_authority: str = Field(description="Data source authority (CPCB, KSPCB, etc.)")
    forecast_available: bool = Field(description="Whether forecast artifacts exist for this station")
    geospatial_available: bool = Field(description="Whether geospatial context exists for this station")
    data_status: str = Field(description="Data status: active, pending_activation, or deferred")
    limitations: list[str] = Field(default_factory=list, description="Limitations for this station")


class StationListResponse(BaseModel):
    city: str = Field(description="City name")
    total_stations: int = Field(description="Total number of stations returned")
    stations: list[StationInfo] = Field(description="List of stations")
