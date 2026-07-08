from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceAttribution(BaseModel):
    traffic: float = Field(ge=0.0, le=1.0, description="Fraction attributed to traffic sources")
    industrial: float = Field(ge=0.0, le=1.0, description="Fraction attributed to industrial sources")
    construction: float = Field(ge=0.0, le=1.0, description="Fraction attributed to construction activity")
    burning: float = Field(ge=0.0, le=1.0, description="Fraction attributed to biomass burning")


class WindUsed(BaseModel):
    direction_deg: float | None = Field(default=None, ge=0, le=360, description="Wind direction (meteorological convention) at computation time")
    speed_kmh: float | None = Field(default=None, ge=0, description="Wind speed at computation time")
    retrieved_at: str | None = Field(default=None, description="ISO timestamp of the wind reading used")


class SourceIntensities(BaseModel):
    traffic_raw: float = Field(description="Raw traffic intensity proxy (road density × NO2)")
    industrial_raw: float = Field(description="Raw industrial intensity proxy (landuse fraction × NO2)")
    construction_raw: float = Field(description="Raw construction intensity proxy")
    burning_raw: float = Field(description="Raw burning intensity proxy (FIRMS fire density)")


class HexagonAttribution(BaseModel):
    h3_cell: str = Field(description="H3 cell ID at resolution 9")
    center_lat: float = Field(description="Cell centroid latitude")
    center_lon: float = Field(description="Cell centroid longitude")
    source_attribution: SourceAttribution = Field(description="Normalized source-category breakdown")
    source_intensities: SourceIntensities = Field(description="Raw unnormalized source intensities")
    method: str = Field(description="'wind_weighted' or 'calm_fallback'")
    wind_used: WindUsed = Field(description="Wind conditions used for this computation")
    source_hexagons_contributing: int = Field(description="Number of source hexagons that contributed")
    max_distance_m: float = Field(description="Maximum distance from which source hexagons were considered")


class HexagonFusion(BaseModel):
    fused_pm25: float | None = Field(default=None, description="Final fused PM2.5 estimate (µg/m³)")
    baseline_pm25: float | None = Field(default=None, description="Baseline estimate from attribution-similarity weighting (µg/m³)")
    residual_correction: float | None = Field(default=None, description="IDW-interpolated residual correction (µg/m³)")
    stations_contributing: int = Field(description="Number of stations that contributed to the fusion")
    nearest_station_id: str | None = Field(default=None, description="Nearest station ID")
    nearest_station_distance_m: float | None = Field(default=None, description="Distance to nearest station (m)")
    fusion_method: str = Field(default="idw_attribution_baseline", description="Fusion method identifier")


class SingleHexagonResponse(BaseModel):
    h3_cell: str = Field(description="H3 cell ID at resolution 9")
    center_lat: float = Field(description="Cell centroid latitude")
    center_lon: float = Field(description="Cell centroid longitude")
    source_attribution: SourceAttribution = Field(description="Normalized source-category breakdown")
    source_intensities: SourceIntensities = Field(description="Raw unnormalized source intensities")
    method: str = Field(description="'wind_weighted' or 'calm_fallback'")
    wind_used: WindUsed = Field(description="Wind conditions used for this computation")
    source_hexagons_contributing: int = Field(description="Number of source hexagons that contributed")
    max_distance_m: float = Field(description="Maximum distance from which source hexagons were considered")
    fused_pm25: float | None = Field(default=None, description="Final fused PM2.5 estimate (µg/m³)")
    baseline_pm25: float | None = Field(default=None, description="Baseline estimate from attribution-similarity weighting (µg/m³)")
    residual_correction: float | None = Field(default=None, description="IDW-interpolated residual correction (µg/m³)")
    stations_contributing: int = Field(description="Number of stations that contributed to the fusion")
    nearest_station_id: str | None = Field(default=None, description="Nearest station ID")
    nearest_station_distance_m: float | None = Field(default=None, description="Distance to nearest station (m)")
    fusion_method: str = Field(default="idw_attribution_baseline", description="Fusion method identifier")
    computed_at: str = Field(description="ISO timestamp of computation")
    city: str = Field(default="bengaluru", description="City name")


class CityGridAttributionResponse(BaseModel):
    city: str = Field(description="City name")
    computed_at: str = Field(description="ISO timestamp of computation")
    hexagon_count: int = Field(description="Number of hexagons in response")
    wind_used: WindUsed = Field(description="Wind conditions used for this computation period")
    hexagons: list[HexagonAttribution] = Field(description="Per-hexagon attribution results")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")


class CityGridFusionResponse(BaseModel):
    city: str = Field(description="City name")
    computed_at: str = Field(description="ISO timestamp of computation")
    hexagon_count: int = Field(description="Number of hexagons in response")
    wind_used: WindUsed = Field(description="Wind conditions used for this computation period")
    station_readings_used: int = Field(description="Number of station readings that contributed to fusion")
    hexagons: list[HexagonFusion] = Field(description="Per-hexagon fusion results")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")
