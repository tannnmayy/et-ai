export interface SourceAttribution {
  traffic: number;
  industrial: number;
  construction: number;
  burning: number;
}

export interface WindUsed {
  direction_deg: number | null;
  speed_kmh: number | null;
  retrieved_at: string | null;
}

export interface SourceIntensities {
  traffic_raw: number;
  industrial_raw: number;
  construction_raw: number;
  burning_raw: number;
}

export interface HexagonAttribution {
  h3_cell: string;
  center_lat: number;
  center_lon: number;
  source_attribution: SourceAttribution;
  source_intensities: SourceIntensities;
  method: string;
  wind_used: WindUsed;
  source_hexagons_contributing: number;
  max_distance_m: number;
}

export interface HexagonFusion {
  fused_pm25: number | null;
  baseline_pm25: number | null;
  residual_correction: number | null;
  stations_contributing: number;
  nearest_station_id: string | null;
  nearest_station_distance_m: number | null;
  fusion_method: string;
}

export interface CityGridAttributionResponse {
  city: string;
  computed_at: string;
  hexagon_count: number;
  wind_used: WindUsed;
  hexagons: HexagonAttribution[];
  warnings: string[];
}

export interface ScoringBreakdown {
  exposure_weight: number;
  attributable_magnitude: number;
  actionability_weight: number;
}

export interface RankedHexagon {
  h3_cell: string;
  priority_score: number;
  rank: number;
  scoring_breakdown: ScoringBreakdown;
  fused_pm25: number | null;
  source_attribution: SourceAttribution;
  method: string;
}

export interface EnforcementPriorityResponse {
  city: string;
  computed_at: string;
  total_hexagons: number;
  top_k: number;
  ranked_hexagons: RankedHexagon[];
}

export interface SingleHexagonResponse extends HexagonAttribution {
  fused_pm25: number | null;
  baseline_pm25: number | null;
  residual_correction: number | null;
  stations_contributing: number;
  nearest_station_id: string | null;
  nearest_station_distance_m: number | null;
  fusion_method: string;
  computed_at: string;
  city: string;
}
