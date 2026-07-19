import { cellToLatLng } from 'h3-js';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
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
  // Single-source label only if ≥ 80%; otherwise Mixed (reduces false "Construction")
  const isMixed = maxVal < 0.8;

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

  // Backend priority_score is a small 0–1 product. Linear ×10 made ranks look like 0.5/10.
  // Display: rank-aware 0–10 so #1 ≈ 9.5–10 and lower ranks still readable.
  const priority01 = Number(hex.priority_score ?? 0);
  const risk01 = Number(hex.risk_adjusted_score ?? priority01);
  const rankN = Number(hex.rank ?? index + 1);
  const rankBased = Math.max(1.5, Math.min(10, 10.5 - (rankN - 1) * 0.55));
  // Blend absolute signal (log-ish) so score is not only rank
  const absSignal = Math.min(10, Math.max(0, Math.log10(1 + priority01 * 200) * 5));
  const score10 = Math.round((rankBased * 0.65 + absSignal * 0.35) * 10) / 10;
  const riskAbs = Math.min(10, Math.max(0, Math.log10(1 + risk01 * 200) * 5));
  const riskAdjustedScore10 = Math.round((rankBased * 0.65 + riskAbs * 0.35) * 10) / 10;

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

  const attrConf =
    hex.attribution_confidence_score != null
      ? Number(hex.attribution_confidence_score)
      : Math.round((hex.scoring_breakdown?.actionability_weight ?? 0.5) * 100);

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
    riskAdjustedScore: risk01,
    riskAdjustedScore10,
    baseRank: hex.base_rank != null ? Number(hex.base_rank) : Number(hex.rank ?? index + 1),
    rank: Number(hex.rank ?? index + 1),
    changeVal,
    exposure,
    magnitude,
    confidence: attrConf,
    attributionConfidence: attrConf,
    attributionConfidenceLevel: hex.attribution_confidence_level ?? undefined,
    confidenceExplanation: hex.confidence_explanation ?? undefined,
    confidenceFlags: hex.confidence_flags ?? undefined,
    riskConfidenceFactor:
      hex.risk_confidence_factor != null
        ? Number(hex.risk_confidence_factor)
        : hex.scoring_breakdown?.risk_confidence_factor != null
          ? Number(hex.scoring_breakdown.risk_confidence_factor)
          : undefined,
    nearestStationDistanceM:
      hex.nearest_station_distance_m != null ? Number(hex.nearest_station_distance_m) : null,
    attributionMethod: hex.method ?? undefined,
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
          risk_confidence_factor: hex.scoring_breakdown.risk_confidence_factor,
          attribution_confidence_score: hex.scoring_breakdown.attribution_confidence_score,
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

  const fusion = fusionMap[attr.h3_cell] || {};
  const fusedPm25 = fusion?.fused_pm25 ?? attr.fused_pm25;
  const fusedPm25Num = fusedPm25 != null ? Math.round(fusedPm25) : 0;
  let attrConf =
    attr.attribution_confidence_score != null
      ? Number(attr.attribution_confidence_score)
      : fusion.attribution_confidence_score != null
        ? Number(fusion.attribution_confidence_score)
        : 0;
  // Display floor so map never shows broken 0% for valid source mixes
  if (attrConf > 0 && attrConf < 18) attrConf = 18;
  if (attrConf === 0 && (sa.traffic || sa.industrial || sa.construction || sa.burning)) {
    attrConf = 18;
  }

  const isMixedAttr = maxVal < 0.8;
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
    confidence: attrConf,
    attributionConfidence: attrConf,
    attributionConfidenceLevel:
      attr.attribution_confidence_level || fusion.attribution_confidence_level,
    confidenceExplanation: attr.confidence_explanation || fusion.confidence_explanation,
    confidenceFlags: attr.confidence_flags || fusion.confidence_flags,
    nearestStationDistanceM:
      attr.nearest_station_distance_m ?? fusion.nearest_station_distance_m ?? null,
    attributionMethod: attr.method,
    actionability: 'MONITOR',
    actionTier: 'MONITOR',
    pm25: fusedPm25Num,
    primarySource: isMixedAttr
      ? 'Mixed'
      : maxSource.charAt(0).toUpperCase() + maxSource.slice(1),
    primarySourceKey: isMixedAttr
      ? 'mixed'
      : (maxSource as PriorityHex['primarySourceKey']),
    sourceType: isMixedAttr
      ? 'Mixed'
      : sourceTypeMap[maxSource] || ('Heavy Ind.' as const),
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
  riskAdjusted: boolean = false,
  constructionScale: number | null = null,
) {
  return [
    'enforcement-priorities',
    'bengaluru',
    simulatedHour,
    topK,
    riskAdjusted,
    constructionScale,
  ] as const;
}

export async function fetchEnforcementPriorities(
  topK: number = ENFORCEMENT_DEFAULT_TOP_K,
  simulatedHour: number | null = null,
  riskAdjusted: boolean = false,
  constructionScale: number | null = null,
): Promise<PriorityHex[]> {
  const k = Math.min(ENFORCEMENT_MAX_TOP_K, Math.max(1, topK));
  const params = new URLSearchParams({ top_k: String(k) });
  if (simulatedHour != null) {
    params.set('simulated_hour', String(simulatedHour));
  }
  if (riskAdjusted) {
    params.set('risk_adjusted', 'true');
  }
  if (constructionScale != null && constructionScale !== 1) {
    params.set('construction_scale', String(constructionScale));
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
  riskAdjusted: boolean = false,
  constructionScale: number | null = null,
) {
  return useQuery<PriorityHex[]>({
    queryKey: enforcementPrioritiesQueryKey(
      topK,
      simulatedHour,
      riskAdjusted,
      constructionScale,
    ),
    queryFn: () =>
      fetchEnforcementPriorities(topK, simulatedHour, riskAdjusted, constructionScale),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
    placeholderData: (previousData) => previousData,
  });
}

/** Enforcement page — topK is request size (default 15). */
export function useEnforcementPriorities(
  simulatedHour: number | null = null,
  topK: number = ENFORCEMENT_DEFAULT_TOP_K,
  riskAdjusted: boolean = false,
  constructionScale: number | null = null,
) {
  return usePriorities(topK, simulatedHour, riskAdjusted, constructionScale);
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

/**
 * Fetch sizes per Map mode:
 * - global_worst: 50 (client slices 15|30|50)
 * - global_best: 30
 * - local_peaks: 100 merge headroom (peak_k=10 × sensors)
 */
export const CITY_EXTREMES_FETCH_N = 50;
export const CITY_EXTREMES_BEST_N = 30;
export const CITY_EXTREMES_LOCAL_PEAKS_N = 100;

/** Per-station worst-hex count for Local Peaks (matches backend). */
export const LOCAL_PEAKS_PER_STATION_K = 10;

/** Canonical Map extremes modes only (matches backend). */
export type ExtremesRankingMode = 'global_worst' | 'global_best' | 'local_peaks';

export interface CityExtremesResult {
  best: PriorityHex[];
  worst: PriorityHex[];
  totalWithData: number;
  totalInGrid: number;
  fetchedN: number;
  mode: ExtremesRankingMode;
  modeDescription?: string;
  peakK?: number | null;
  fusionRangeM?: number | null;
  maxFusedPm25?: number | null;
  tieCountAtMax?: number | null;
  maxStationId?: string | null;
  rankingNote?: string | null;
  deprecationWarning?: string | null;
}

const SOURCE_KEYS_SAFE = ['traffic', 'industrial', 'construction', 'burning'] as const;

/** Map extremes mapper — does not surface attribution confidence (Map path). */
function mapExtremeHex(h: any): PriorityHex | null {
  if (!h || !h.h3_cell) return null;
  let lat = Number(h.center_lat);
  let lng = Number(h.center_lon ?? h.center_lng);
  // Recover coordinates from H3 when API omits them (prevents blank map / marker crashes)
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    try {
      const [la, ln] = cellToLatLng(String(h.h3_cell));
      lat = la;
      lng = ln;
    } catch {
      return null;
    }
  }
  const pm = Math.round(Number(h.fused_pm25) || 0);
  const score10 = Math.min(10, Math.round(pm / 20));
  const sa = h.source_attribution || {};
  let maxSource = 'traffic';
  let maxVal = 0;
  for (const [key, value] of Object.entries(sa)) {
    if ((value as number) > maxVal) {
      maxVal = value as number;
      maxSource = key;
    }
  }
  const sourceTypeMap: Record<string, PriorityHex['sourceType']> = {
    traffic: 'Traffic Hub',
    industrial: 'Heavy Ind.',
    construction: 'Construction',
    burning: 'Waste Burning',
  };
  const sourceKey = (
    (SOURCE_KEYS_SAFE as readonly string[]).includes(maxSource) ? maxSource : 'traffic'
  ) as PriorityHex['primarySourceKey'];
  return {
    id: String(h.h3_cell),
    name: _resolveName(String(h.h3_cell), lat, lng, h.location_name || h.name),
    score10,
    priorityScore: score10 / 10,
    rank: 0,
    changeVal: 0,
    exposure: 'Medium',
    magnitude: 0,
    // Map path: confidence intentionally omitted (Enforcement still maps it).
    confidence: 0,
    nearestStationDistanceM: h.nearest_station_distance_m ?? null,
    attributionMethod: h.method,
    actionability: 'MONITOR',
    actionTier: 'MONITOR',
    pm25: pm,
    primarySource: sourceKey.charAt(0).toUpperCase() + sourceKey.slice(1),
    primarySourceKey: sourceKey,
    sourceType: sourceTypeMap[sourceKey] || 'Heavy Ind.',
    sourceAttribution: {
      traffic: Number(sa.traffic) || 0,
      industrial: Number(sa.industrial) || 0,
      construction: Number(sa.construction) || 0,
      burning: Number(sa.burning) || 0,
    },
    lat,
    lng,
  };
}

function fetchNForMode(mode: ExtremesRankingMode): number {
  if (mode === 'global_best') return CITY_EXTREMES_BEST_N;
  if (mode === 'local_peaks') return CITY_EXTREMES_LOCAL_PEAKS_N;
  return CITY_EXTREMES_FETCH_N; // global_worst max depth 50
}

export async function fetchCityExtremes(
  n: number = CITY_EXTREMES_FETCH_N,
  mode: ExtremesRankingMode = 'global_worst',
): Promise<CityExtremesResult> {
  const modeParam: ExtremesRankingMode =
    mode === 'global_best' || mode === 'local_peaks' ? mode : 'global_worst';
  const capped = Math.min(100, Math.max(1, n || fetchNForMode(modeParam)));
  const peakQs =
    modeParam === 'local_peaks' ? `&peak_k=${LOCAL_PEAKS_PER_STATION_K}` : '';
  const { data } = await apiClient.get(
    `/attribution/city/bengaluru/extremes?n=${capped}&mode=${modeParam}${peakQs}`,
  );
  if (!data || !Array.isArray(data.best) || !Array.isArray(data.worst)) {
    throw new Error('No extremes data returned from API');
  }
  const best = data.best
    .map(mapExtremeHex)
    .filter((h: PriorityHex | null): h is PriorityHex => h != null);
  const worst = data.worst
    .map(mapExtremeHex)
    .filter((h: PriorityHex | null): h is PriorityHex => h != null);
  const responseMode = String(data.mode || modeParam);
  const rankingMode: ExtremesRankingMode =
    responseMode === 'global_best' || responseMode === 'local_peaks'
      ? responseMode
      : 'global_worst';
  return {
    best,
    worst,
    totalWithData: Number(data.total_hexagons_with_data) || best.length + worst.length,
    totalInGrid: Number(data.total_hexagons_in_grid) || 0,
    fetchedN: capped,
    mode: rankingMode,
    modeDescription: data.mode_description ?? undefined,
    peakK: data.peak_k ?? null,
    fusionRangeM: data.fusion_range_m ?? null,
    maxFusedPm25: data.max_fused_pm25 ?? null,
    tieCountAtMax: data.tie_count_at_max ?? null,
    maxStationId: data.max_station_id ?? null,
    rankingNote: data.ranking_note ?? null,
    deprecationWarning: data.deprecation_warning ?? null,
  };
}

export function useCityExtremes(mode: ExtremesRankingMode = 'global_worst') {
  const fetchN = fetchNForMode(mode);
  return useQuery<CityExtremesResult>({
    // Separate cache per canonical mode + fetch size
    queryKey: ['city-extremes', fetchN, mode],
    queryFn: () => fetchCityExtremes(fetchN, mode),
    staleTime: 90_000,
    // Critical: switching modes must NOT blank the map.
    placeholderData: keepPreviousData,
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
