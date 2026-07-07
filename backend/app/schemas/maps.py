from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GeocodeRequest(BaseModel):
    q: str = Field(description="Free-text address or place query")


class GeocodeResult(BaseModel):
    label: str = Field(description="Normalized address label")
    latitude: float = Field(description="Latitude")
    longitude: float = Field(description="Longitude")
    formatted_address: str = Field(description="Full formatted address from provider")
    place_id: str | None = Field(None, description="Google Place ID if available")


class GeocodeResponse(BaseModel):
    success: bool
    data: GeocodeResult | None = None
    provider_status: str = Field(description="Provider status code")
    source_status: str = Field(description="fresh, stale, or unavailable")
    resolution_method: str = Field(description="geocoding or direct_coordinates")
    city_scope: str = Field(default="bengaluru")
    limitations: list[str] = Field(default_factory=list)


class RouteOrigin(BaseModel):
    latitude: float = Field(description="Origin latitude")
    longitude: float = Field(description="Origin longitude")
    label: str | None = Field(None, description="Optional origin label")


class RouteDestination(BaseModel):
    latitude: float = Field(description="Destination latitude")
    longitude: float = Field(description="Destination longitude")
    label: str | None = Field(None, description="Optional destination label")


class RouteRequest(BaseModel):
    origin: RouteOrigin = Field(description="Origin coordinates")
    destination: RouteDestination = Field(description="Destination coordinates")
    travel_mode: str = Field(default="DRIVE", description="DRIVE, TWO_WHEELER, TRANSIT, or WALK")


class RouteResult(BaseModel):
    distance_meters: float | None = Field(None, description="Route distance in meters")
    duration_seconds: float | None = Field(None, description="Route duration in seconds")
    duration_in_traffic_seconds: float | None = Field(None, description="Traffic-aware duration if available")
    travel_mode: str = Field(description="Travel mode used")
    provider_status: str = Field(description="Provider status code")
    source_status: str = Field(description="fresh, stale, or unavailable")
    obtained_at: str = Field(description="ISO timestamp when route was computed")
    limitations: list[str] = Field(default_factory=list)


class RouteResponse(BaseModel):
    success: bool
    data: RouteResult | None = None
    error: str | None = None
