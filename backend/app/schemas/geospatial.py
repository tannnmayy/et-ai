from __future__ import annotations

from pydantic import BaseModel, Field


class RoadContext(BaseModel):
    total_road_length_m_within_radius: float | None = Field(
        None, description="Total mapped road length (m) within station context radius"
    )
    major_road_length_m_within_radius: float | None = Field(
        None, description="Major road length (m) within station context radius"
    )
    road_density_m_per_sq_km: float | None = Field(
        None, description="Road density (m per sq km) within buffer"
    )
    intersection_count_within_radius: int | None = Field(
        None, description="Intersection count within radius (not yet implemented)"
    )
    nearest_major_road_distance_m: float | None = Field(
        None, description="Distance (m) to nearest mapped major road"
    )
    road_feature_coverage_status: str = Field(
        description="Coverage status: 'complete' or reason for absence"
    )


class LanduseContext(BaseModel):
    industrial_landuse_fraction: float | None = Field(
        None, description="Fraction of mapped land use that is industrial"
    )
    commercial_landuse_fraction: float | None = Field(
        None, description="Fraction of mapped land use that is commercial"
    )
    residential_landuse_fraction: float | None = Field(
        None, description="Fraction of mapped land use that is residential"
    )
    green_space_fraction: float | None = Field(
        None, description="Fraction of mapped area that is green space"
    )
    landuse_feature_coverage_status: str = Field(
        description="Coverage status: 'complete' or reason for absence"
    )


class InvestigationContext(BaseModel):
    construction_feature_count_within_radius: int | None = Field(
        None, description="Count of OSM construction-tagged features within investigation radius"
    )
    mapped_industrial_or_facility_count_within_radius: int | None = Field(
        None, description="Count of OSM industrial/facility features within investigation radius"
    )
    nearest_mapped_industrial_or_facility_distance_m: float | None = Field(
        None, description="Distance (m) to nearest mapped industrial or facility feature"
    )
    investigation_context_coverage_status: str = Field(
        description="Coverage status: 'complete' or reason for absence"
    )


class GeospatialProvenance(BaseModel):
    osm_snapshot_timestamp: str | None = Field(
        None, description="Timestamp of the OSM data snapshot used"
    )
    feature_builder_version: str = Field(
        description="Version of the feature builder that generated this context"
    )
    h3_resolution: int = Field(description="H3 resolution used for spatial indexing")
    h3_cell: str | None = Field(None, description="H3 cell ID for the station location")


class StationGeospatialContext(BaseModel):
    station_id: str = Field(description="Station identifier matching the forecast registry")
    city: str = Field(description="City name")
    latitude: float = Field(description="Station latitude")
    longitude: float = Field(description="Station longitude")
    h3_cell: str | None = Field(None, description="H3 cell ID for spatial indexing")
    context_radius_meters: float = Field(description="Radius used for station context extraction")
    build_status: str | None = Field(None, description="Build status: 'full', 'partial', or 'unknown'")

    road_context: RoadContext = Field(description="Road and mobility proxy features")
    landuse_context: LanduseContext = Field(description="Land-use fraction features")
    investigation_context: InvestigationContext = Field(
        description="Investigation context features (construction, industrial)"
    )

    provenance: GeospatialProvenance = Field(description="Data provenance metadata")
    data_completeness_score: float = Field(
        ge=0.0, le=1.0, description="Overall data completeness score (0.0 to 1.0)"
    )
    limitations: list[str] = Field(description="Limitations and disclaimers")


class CityCoverageSummary(BaseModel):
    city: str = Field(description="City name")
    total_stations: int = Field(description="Number of stations with geospatial context")
    stations_with_coverage: int = Field(
        description="Number of stations with at least some feature coverage"
    )
    stations_with_complete_coverage: int = Field(
        description="Number of stations with complete feature coverage"
    )
    osm_snapshot_timestamp: str | None = Field(
        None, description="Timestamp of the OSM data snapshot"
    )
    feature_builder_version: str = Field(
        description="Version of the feature builder"
    )
    h3_resolution: int = Field(description="H3 resolution")
    build_status: str | None = Field(None, description="Build status: 'full', 'partial', or 'unknown'")
    disclaimers: list[str] = Field(description="Applicable disclaimers")
