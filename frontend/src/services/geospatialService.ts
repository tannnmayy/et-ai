import { cellToLatLng } from 'h3-js';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';
import { PriorityHex } from '../types';
import { BENGALURU_LOCALITIES } from '../data/bengaluruLocalities';

/** Haversine distance in km */
function _distKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const toR = (d: number) => (d * Math.PI) / 180;
  const dLat = toR(lat2 - lat1);
  const dLng = toR(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toR(lat1)) * Math.cos(toR(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

function _isRawLabel(name: string | null | undefined): boolean {
  if (!name) return true;
  const n = name.trim();
  if (!n) return true;
  const low = n.toLowerCase();
  if (low.startsWith('grid ') || low.startsWith('sector ')) return true;
  if (n.length >= 10 && /^[0-9a-f]+$/i.test(n)) return true;
  return false;
}

/** Prefer API/locality name; never use raw H3 / "Grid xxxx" as primary label. */
function _resolveName(h3_cell: string, lat: number, lng: number, preferred?: string | null): string {
  if (preferred && !_isRawLabel(preferred)) {
    return preferred.split(',')[0]?.trim() || preferred;
  }

  let best: { name: string; d: number } | null = null;
  for (const loc of BENGALURU_LOCALITIES) {
    const d = _distKm(lat, lng, loc.lat, loc.lng);
    if (d > 4.5) continue;
    if (!best || d < best.d) best = { name: loc.name, d };
  }
  if (best) {
    return best.d <= 1.8 ? best.name : `Near ${best.name}`;
  }

  const ns = lat >= 12.97 ? 'N' : 'S';
  const ew = lng >= 77.6 ? 'E' : 'W';
  return `Bengaluru ${ns}${ew}`;
}

function mapRealStation(item: any): { id: string; name: string; lat: number; lng: number; aqi: number; status: 'Good' | 'Moderate' | 'Poor' | 'Severe' } {
  const r = item.risk_category || '';
  const status = r.includes('good') || r.includes('low') ? 'Good'
    : r.includes('satisfactory') || r.includes('moderate') ? 'Moderate'
    : r.includes('poor') ? 'Poor' : 'Severe';

  return {
    id: item.station_id || item.id,
    name: item.station_name || item.display_name || item.name,
    lat: item.latitude || item.lat || 12.9716,
    lng: item.longitude || item.lng || 77.5946,
    aqi: Math.round(item.predicted_pm25 || item.aqi || 0),
    status,
  };
}

function mapRealHex(hex: any, index: number): PriorityHex | null {
  let lat: number;
  let lng: number;
  try {
    if (hex.center_lat != null && hex.center_lon != null) {
      lat = Number(hex.center_lat);
      lng = Number(hex.center_lon);
    } else {
      const coords = cellToLatLng(hex.h3_cell);
      lat = coords[0];
      lng = coords[1];
    }
  } catch (e) {
    console.warn('Skipping hexagon with unparseable h3_cell:', hex.h3_cell);
    return null;
  }

  const sa = hex.source_attribution || {};
  const sourceAttribution = {
    traffic: sa.traffic ?? 0,
    industrial: sa.industrial ?? 0,
    construction: sa.construction ?? 0,
    burning: sa.burning ?? 0,
  };

  let maxSource = 'traffic';
  let maxVal = 0;
  for (const [key, value] of Object.entries(sourceAttribution)) {
    if ((value as number) > maxVal) {
      maxVal = value as number;
      maxSource = key;
    }
  }
  const secondVals = Object.values(sourceAttribution).sort((a, b) => b - a);
  const isMixed = maxVal < 0.4 || (secondVals[0] - (secondVals[1] ?? 0) < 0.08);

  const sourceTypeMap: Record<string, PriorityHex['sourceType']> = {
    traffic: 'Traffic Hub',
    industrial: 'Heavy Ind.',
    construction: 'Construction',
    burning: 'Waste Burning',
  };

  let exposure: PriorityHex['exposure'] = 'Medium';
  const expWeight = hex.scoring_breakdown?.exposure_weight ?? 0.5;
  if (expWeight < 0.3) exposure = 'Low';
  else if (expWeight < 0.6) exposure = 'Medium';
  else if (expWeight < 0.8) exposure = 'High';
  else exposure = 'Critical';

  // Backend priority_score is 0–1; display as 0–10 for officer-friendly scale
  const priority01 = Number(hex.priority_score ?? 0);
  const score10 = Math.round(Math.min(1, Math.max(0, priority01)) * 100) / 10;

  // Action tier from score + exposure (not just actionability weight)
  let actionTier: PriorityHex['actionTier'] = 'ROUTINE';
  const highExp = exposure === 'High' || exposure === 'Critical';
  if (score10 >= 9 && highExp) actionTier = 'IMMEDIATE';
  else if (score10 >= 9 || score10 >= 7) actionTier = 'HIGH';
  else if (score10 >= 5) actionTier = 'MONITOR';
  else actionTier = 'ROUTINE';

  const magnitude = Math.round((hex.scoring_breakdown?.attributable_magnitude || 0) * 100);
  // Magnitude already encodes attributable pollution intensity — use as "vs baseline" proxy
  // rather than synthetic sin-based change values.
  const changeVal = Number(((hex.scoring_breakdown?.attributable_magnitude || 0) * 5).toFixed(1));

  return {
    id: hex.h3_cell,
    name: _resolveName(
      hex.h3_cell,
      lat,
      lng,
      hex.location_name || hex.name,
    ),
    score10,
    priorityScore: priority01,
    rank: Number(hex.rank ?? index + 1),
    changeVal,
    exposure,
    magnitude,
    confidence: Math.round((hex.scoring_breakdown?.actionability_weight ?? 0.5) * 100),
    actionability: actionTier,
    actionTier,
    pm25: Math.round(hex.fused_pm25 || hex.predicted_pm25 || 0),
    primarySource: isMixed ? 'Mixed' : maxSource.charAt(0).toUpperCase() + maxSource.slice(1),
    primarySourceKey: isMixed ? 'mixed' : (maxSource as PriorityHex['primarySourceKey']),
    sourceType: isMixed ? 'Mixed' : sourceTypeMap[maxSource] || 'Heavy Ind.',
    sourceAttribution,
    explanation: hex.explanation,
    lat,
    lng,
    trafficCorridorScore: hex.traffic_corridor_score ?? undefined,
    isMajorRoadCorridor: hex.is_major_road_corridor ?? undefined,
    isTrafficCorridor: Boolean(
      hex.is_traffic_corridor ??
        hex.is_major_road_corridor ??
        ((hex.traffic_corridor_score ?? 0) > 0.4),
    ),
    trafficTimeMultiplier: hex.traffic_time_multiplier ?? undefined,
    isPeakHour: hex.is_peak_hour ?? undefined,
    trafficHourLocal: hex.traffic_hour_local ?? null,
    trafficCorridorApplied: hex.traffic_corridor_applied ?? undefined,
    scoringBreakdown: hex.scoring_breakdown
      ? {
          exposure_weight: hex.scoring_breakdown.exposure_weight,
          attributable_magnitude: hex.scoring_breakdown.attributable_magnitude,
          actionability_weight: hex.scoring_breakdown.actionability_weight,
        }
      : undefined,
  };
}

function mapAttributionHex(attr: any, fusionMap: Record<string, any>): PriorityHex | null {
  let lat = attr.center_lat;
  let lng = attr.center_lon;
  if (lat == null || lng == null) {
    try {
      const coords = cellToLatLng(attr.h3_cell);
      lat = coords[0];
      lng = coords[1];
    } catch (e) {
      console.warn('Skipping attribution hex with unparseable h3_cell:', attr.h3_cell);
      return null;
    }
  }

  const sa = attr.source_attribution || {};
  let maxSource = 'traffic';
  let maxVal = 0;
  for (const [key, value] of Object.entries(sa)) {
    if ((value as number) > maxVal) {
      maxVal = value as number;
      maxSource = key;
    }
  }

  const sourceTypeMap: Record<string, 'Traffic Hub' | 'Heavy Ind.' | 'Construction' | 'Waste Burning'> = {
    traffic: 'Traffic Hub',
    industrial: 'Heavy Ind.',
    construction: 'Construction',
    burning: 'Waste Burning',
  };

  const fusion = fusionMap[attr.h3_cell];
  const fusedPm25 = fusion?.fused_pm25;
  const fusedPm25Num = fusedPm25 != null ? Math.round(fusedPm25) : 0;

  const score10 = Math.min(10, Math.round(fusedPm25Num / 20));
  return {
    id: attr.h3_cell,
    name: _resolveName(attr.h3_cell, lat, lng, attr.location_name || attr.name),
    score10,
    priorityScore: score10 / 10,
    rank: 0,
    changeVal: 0,
    exposure: 'Medium',
    magnitude: 0,
    confidence: 0,
    actionability: 'MONITOR',
    actionTier: 'MONITOR',
    pm25: fusedPm25Num,
    primarySource: maxSource.charAt(0).toUpperCase() + maxSource.slice(1),
    primarySourceKey: maxSource as PriorityHex['primarySourceKey'],
    sourceType: sourceTypeMap[maxSource] || ('Heavy Ind.' as const),
    sourceAttribution: {
      traffic: sa.traffic ?? 0,
      industrial: sa.industrial ?? 0,
      construction: sa.construction ?? 0,
      burning: sa.burning ?? 0,
    },
    lat,
    lng,
  };
}

export async function fetchStations() {
  const { data } = await apiClient.get('/stations?city=bengaluru');
  if (data && data.stations && data.stations.length > 0) {
    return data.stations.map(mapRealStation);
  }
  throw new Error('No stations returned from API');
}

export function useStations() {
  return useQuery<{ id: string; name: string; lat: number; lng: number; aqi: number; status: 'Good' | 'Moderate' | 'Poor' | 'Severe' }[]>({
    queryKey: ['stations'],
    queryFn: fetchStations,
    refetchInterval: 10000,
    staleTime: 30_000,
  });
}

/**
 * Enforcement priority list.
 *
 * Default fetch is top 15 for fast first paint. Larger Top-N values trigger a
 * new request (cached by React Query). Landing page prefetches the default.
 */
export const ENFORCEMENT_DEFAULT_TOP_K = 15;
/** @deprecated use ENFORCEMENT_DEFAULT_TOP_K — kept for older imports */
export const ENFORCEMENT_FETCH_TOP_K = ENFORCEMENT_DEFAULT_TOP_K;
export const ENFORCEMENT_MAX_TOP_K = 100;

export function enforcementPrioritiesQueryKey(
  topK: number = ENFORCEMENT_DEFAULT_TOP_K,
  simulatedHour: number | null = null,
) {
  return ['enforcement-priorities', 'bengaluru', simulatedHour, topK] as const;
}

export async function fetchEnforcementPriorities(
  topK: number = ENFORCEMENT_DEFAULT_TOP_K,
  simulatedHour: number | null = null,
): Promise<PriorityHex[]> {
  const k = Math.min(ENFORCEMENT_MAX_TOP_K, Math.max(1, topK));
  const params = new URLSearchParams({ top_k: String(k) });
  if (simulatedHour != null) {
    params.set('simulated_hour', String(simulatedHour));
  }
  const { data } = await apiClient.get(
    `/enforcement/priority/bengaluru?${params.toString()}`,
  );
  if (data && data.ranked_hexagons && data.ranked_hexagons.length > 0) {
    return data.ranked_hexagons
      .map((hex: any, idx: number) => {
        const mapped = mapRealHex(
          {
            ...hex,
            traffic_time_multiplier:
              hex.traffic_time_multiplier ?? data.traffic_time_multiplier,
            is_peak_hour: hex.is_peak_hour ?? data.is_peak_hour,
            traffic_hour_local: hex.traffic_hour_local ?? data.traffic_hour_local,
            traffic_corridor_applied:
              hex.traffic_corridor_applied ?? data.traffic_corridor_applied,
          },
          idx,
        );
        return mapped;
      })
      .filter((h: PriorityHex | null): h is PriorityHex => h !== null);
  }
  throw new Error('No ranked hexagons returned from API');
}

export function usePriorities(
  topK: number = ENFORCEMENT_DEFAULT_TOP_K,
  simulatedHour: number | null = null,
) {
  return useQuery<PriorityHex[]>({
    queryKey: enforcementPrioritiesQueryKey(topK, simulatedHour),
    queryFn: () => fetchEnforcementPriorities(topK, simulatedHour),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    placeholderData: (previousData) => previousData,
  });
}

/** Enforcement page — topK is request size (default 15). */
export function useEnforcementPriorities(
  simulatedHour: number | null = null,
  topK: number = ENFORCEMENT_DEFAULT_TOP_K,
) {
  return usePriorities(topK, simulatedHour);
}

export function useAttributionGrid() {
  return useQuery<PriorityHex[]>({
    queryKey: ['attribution-grid'],
    queryFn: async () => {
      const [attrRes, fusionRes] = await Promise.all([
        apiClient.get('/attribution/city/bengaluru'),
        apiClient.get('/attribution/city/bengaluru/fusion'),
      ]);
      const hexagons: any[] = attrRes.data?.hexagons ?? [];
      const fusionList: any[] = fusionRes.data?.hexagons ?? [];
      const fusionMap: Record<string, any> = {};
      for (const f of fusionList) {
        fusionMap[f.h3_cell] = f;
      }
      return hexagons.map((h: any) => mapAttributionHex(h, fusionMap)).filter((h): h is PriorityHex => h !== null);
    },
    staleTime: 60_000,
  });
}

/** Max worst/best hexes fetched once for map filters (client-side slice). */
export const CITY_EXTREMES_FETCH_N = 100;

export async function fetchCityExtremes(n: number = CITY_EXTREMES_FETCH_N) {
  const capped = Math.min(100, Math.max(1, n));
  const { data } = await apiClient.get(
    `/attribution/city/bengaluru/extremes?n=${capped}`,
  );
  if (!data || !data.best || !data.worst) {
    throw new Error('No extremes data returned from API');
  }
  const mapExtreme = (h: any): PriorityHex => {
    const pm = Math.round(h.fused_pm25 || 0);
    const score10 = Math.min(10, Math.round(pm / 20));
    return {
      id: h.h3_cell,
      name: _resolveName(h.h3_cell, h.center_lat, h.center_lon, h.location_name || h.name),
      score10,
      priorityScore: score10 / 10,
      rank: 0,
      changeVal: 0,
      exposure: 'Medium',
      magnitude: 0,
      confidence: 0,
      actionability: 'MONITOR',
      actionTier: 'MONITOR',
      pm25: pm,
      primarySource: '',
      primarySourceKey: 'traffic',
      sourceType: 'Heavy Ind.',
      sourceAttribution: {
        traffic: h.source_attribution?.traffic ?? 0,
        industrial: h.source_attribution?.industrial ?? 0,
        construction: h.source_attribution?.construction ?? 0,
        burning: h.source_attribution?.burning ?? 0,
      },
      lat: h.center_lat,
      lng: h.center_lon,
    };
  };
  const best = data.best.map(mapExtreme);
  const worst = data.worst.map(mapExtreme);
  return {
    best,
    worst,
    totalWithData: data.total_hexagons_with_data,
    totalInGrid: data.total_hexagons_in_grid,
    fetchedN: capped,
  };
}

export function useCityExtremes() {
  return useQuery<{
    best: PriorityHex[];
    worst: PriorityHex[];
    totalWithData: number;
    totalInGrid: number;
    fetchedN: number;
  }>({
    // Include N so we don't reuse an older top-15 cache from earlier builds
    queryKey: ['city-extremes', CITY_EXTREMES_FETCH_N],
    queryFn: () => fetchCityExtremes(CITY_EXTREMES_FETCH_N),
    staleTime: 60_000,
  });
}

export function useFireDetections() {
  return useQuery({
    queryKey: ['fire-detections'],
    queryFn: async () => {
      const { data } = await apiClient.get('/geospatial/fire-detections?city=bengaluru');
      if (data && data.hexagons) {
        return data.hexagons.reduce((acc: any[], hex: any) => {
          let lat: number;
          let lng: number;
          try {
            const coords = cellToLatLng(hex.h3_cell);
            lat = coords[0];
            lng = coords[1];
          } catch (e) {
            console.warn('Skipping fire detection with unparseable h3_cell:', hex.h3_cell);
            return acc;
          }
          acc.push({
            id: hex.h3_cell,
            lat,
            lng,
            frp: hex.total_frp_mw,
            confidence: hex.max_confidence || 'nominal',
            timestamp: hex.window_end_utc,
          });
          return acc;
        }, []);
      }
      throw new Error('No fire detections returned from API');
    },
  });
}
