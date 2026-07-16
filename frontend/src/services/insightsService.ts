import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';

export interface RushHourSeriesPoint {
  hour: number;
  label: string;
  traffic: number;
  industrial: number;
  construction: number;
  burning: number;
  dominant: string;
  multiplier?: number | null;
}

export interface RushHourFlipInsight {
  available: boolean;
  reason?: string;
  headline?: string;
  finding?: string;
  method_note?: string;
  h3_cell?: string;
  location_name?: string;
  center_lat?: number;
  center_lon?: number;
  corridor_score?: number;
  series?: RushHourSeriesPoint[];
  traffic_am_pct?: number;
  traffic_night_pct?: number;
  flip_pp?: number;
  dominant_am?: string;
  dominant_night?: string;
}

export interface SensorGapRow {
  file: string;
  station_hint: string;
  rows: number;
  pm25_missing_pct: number;
  pm25_valid: number;
}

export interface SensorBlindSpotsInsight {
  available: boolean;
  reason?: string;
  headline?: string;
  finding?: string;
  method_note?: string;
  severe_gaps?: SensorGapRow[];
  station_files_scanned?: number;
}

export interface PredictabilityStation {
  station_id: string;
  display_name: string;
  winner: 'lightgbm' | 'persistence' | string;
  persistence_rmse?: number | null;
  lightgbm_rmse?: number | null;
  rmse_improvement_percent?: number | null;
  test_rows?: number | null;
  interpretation?: string;
}

export interface PredictabilityMapInsight {
  available: boolean;
  reason?: string;
  headline?: string;
  finding?: string;
  method_note?: string;
  stations?: PredictabilityStation[];
  lgbm_wins?: number;
  persistence_wins?: number;
  overall_rmse_improvement_percent?: number | null;
  overall_persistence_rmse?: number | null;
  overall_lightgbm_rmse?: number | null;
}

export interface EnforcementCurvePoint {
  k: number;
  exposure_share_pct: number;
  land_share_of_full_grid_pct: number;
  share_of_scored_hexes_pct: number;
}

export interface TargetedEnforcementInsight {
  available: boolean;
  reason?: string;
  headline?: string;
  finding?: string;
  method_note?: string;
  curve?: EnforcementCurvePoint[];
  n_grid_hexes?: number;
  n_scored_hexes?: number;
}

export interface RentLocality {
  name: string;
  aqi: number;
  median_rent: number;
  listings?: number;
  source_attribution?: Record<string, number> | null;
}

export interface RentVsAirInsight {
  available: boolean;
  reason?: string;
  headline?: string;
  finding?: string;
  method_note?: string;
  expensive_dirty?: RentLocality;
  affordable_clean?: RentLocality;
  city_median_aqi?: number;
  city_median_rent?: number;
  localities_compared?: number;
  rental_listings_dataset?: number | null;
}

export interface BeforeAfterInsight {
  available: boolean;
  reason?: string;
  headline?: string;
  finding?: string;
  method_note?: string;
  before?: {
    cpcb_kspcb_stations: number;
    automated_enforcement_link: boolean;
    actionable_protocol_share_national_pct: number;
  };
  after?: {
    h3_hexagons: number;
    enforcement_priority_decomposed: boolean;
    tod_traffic_multipliers: boolean;
    sentinel5p_no2: boolean;
    firms_burning: boolean;
  };
}

export interface CityInsightsPack {
  city: string;
  generated_at: string;
  cache_hit?: boolean;
  insights: {
    rush_hour_flip: RushHourFlipInsight;
    sensor_blind_spots: SensorBlindSpotsInsight;
    predictability_map: PredictabilityMapInsight;
    targeted_enforcement: TargetedEnforcementInsight;
    rent_vs_air: RentVsAirInsight;
    before_after: BeforeAfterInsight;
  };
}

export async function fetchCityInsights(
  city: string = 'bengaluru',
  refresh: boolean = false,
): Promise<CityInsightsPack> {
  const { data } = await apiClient.get<CityInsightsPack>(
    `/insights/city/${encodeURIComponent(city)}`,
    { params: refresh ? { refresh: true } : undefined },
  );
  return data;
}

export function useCityInsights(city: string = 'bengaluru') {
  return useQuery<CityInsightsPack>({
    queryKey: ['city-insights', city],
    queryFn: () => fetchCityInsights(city),
    staleTime: 90_000,
    gcTime: 10 * 60_000,
    retry: 1,
  });
}
