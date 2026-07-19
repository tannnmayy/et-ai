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
    # Optional traffic enhancement metadata (defaults keep old clients happy)
    traffic_time_multiplier: float | None = Field(
        default=None,
        description="Time-of-day multiplier applied to traffic intensity (1.0 if disabled)",
    )
    is_peak_hour: bool | None = Field(
        default=None,
        description="Whether Bengaluru local hour is a peak commuting window",
    )
    traffic_hour_local: int | None = Field(
        default=None,
        description="Local hour (0–23, Asia/Kolkata) used for the traffic multiplier",
    )
    traffic_corridor_applied: bool | None = Field(
        default=None,
        description="True when major-road corridor scores were blended into traffic density",
    )


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
    traffic_time_multiplier: float | None = Field(
        default=None,
        description="Time-of-day multiplier applied to traffic intensity",
    )
    is_peak_hour: bool | None = Field(
        default=None,
        description="Whether Bengaluru local hour is a peak commuting window",
    )
    traffic_hour_local: int | None = Field(
        default=None,
        description="Local hour (0–23, Asia/Kolkata) used for the traffic multiplier",
    )
    traffic_corridor_applied: bool | None = Field(
        default=None,
        description="True when major-road corridor scores were blended into traffic density",
    )


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


class HexagonExtreme(BaseModel):
    h3_cell: str = Field(description="H3 cell ID at resolution 9")
    name: str | None = Field(default=None, description="Reverse-geocoded locality label when available")
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
    traffic_time_multiplier: float | None = Field(default=None)
    is_peak_hour: bool | None = Field(default=None)
    traffic_hour_local: int | None = Field(default=None)
    traffic_corridor_applied: bool | None = Field(default=None)


class CityExtremesResponse(BaseModel):
    city: str = Field(description="City name")
    computed_at: str = Field(description="ISO timestamp of computation")
    mode: str = Field(
        default="global_worst",
        description="Canonical mode: global_worst | global_best | local_peaks",
    )
    mode_description: str | None = Field(
        default=None,
        description="Human-readable explanation of the active ranking mode",
    )
    peak_k: int | None = Field(
        default=None,
        description="Per-station worst-hex count for local_peaks (always 10 on Map path)",
    )
    deprecation_warning: str | None = Field(
        default=None,
        description="Set when a legacy mode was soft-redirected (e.g. global → global_worst)",
    )
    best: list[HexagonExtreme] = Field(description="Top N cleanest hexagons (lowest fused PM2.5)")
    worst: list[HexagonExtreme] = Field(
        description="Top N most polluted hexagons under the active mode ranking",
    )
    total_hexagons_with_data: int = Field(description="Number of hexagons with a real fused PM2.5 estimate")
    total_hexagons_in_grid: int = Field(description="Total number of hexagons in the city grid")
    fusion_range_m: float | None = Field(
        default=None,
        description="Station fusion range in metres used for coverage",
    )
    max_fused_pm25: float | None = Field(
        default=None,
        description="Highest fused PM2.5 among covered hexes (global plateau max)",
    )
    tie_count_at_max: int | None = Field(
        default=None,
        description="How many covered hexes share ~max_fused_pm25 (global plateau size)",
    )
    max_station_id: str | None = Field(
        default=None,
        description="Station most associated with the global max plateau",
    )
    ranking_note: str | None = Field(
        default=None,
        description="Honesty note: uncovered hexes are unmeasured, not clean",
    )
