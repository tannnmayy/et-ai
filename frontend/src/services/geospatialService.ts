import { cellToLatLng } from 'h3-js';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';
import { PriorityHex } from '../types';

// Bengaluru area lookup: bounding boxes for known localities
const BENGALURU_AREAS: { name: string; minLat: number; maxLat: number; minLng: number; maxLng: number }[] = [
  { name: 'Whitefield', minLat: 12.96, maxLat: 12.99, minLng: 77.70, maxLng: 77.78 },
  { name: 'Indiranagar', minLat: 12.96, maxLat: 12.99, minLng: 77.62, maxLng: 77.68 },
  { name: 'Koramangala', minLat: 12.92, maxLat: 12.94, minLng: 77.60, maxLng: 77.63 },
  { name: 'Jayanagar', minLat: 12.91, maxLat: 12.94, minLng: 77.56, maxLng: 77.60 },
  { name: 'Hebbal', minLat: 13.02, maxLat: 13.06, minLng: 77.58, maxLng: 77.62 },
  { name: 'Peenya', minLat: 13.00, maxLat: 13.05, minLng: 77.50, maxLng: 77.56 },
  { name: 'Yeshwanthpur', minLat: 12.99, maxLat: 13.03, minLng: 77.53, maxLng: 77.57 },
  { name: 'Malleshwaram', minLat: 12.99, maxLat: 13.01, minLng: 77.55, maxLng: 77.58 },
  { name: 'Rajajinagar', minLat: 12.97, maxLat: 13.00, minLng: 77.54, maxLng: 77.57 },
  { name: 'Basavanagudi', minLat: 12.93, maxLat: 12.96, minLng: 77.55, maxLng: 77.58 },
  { name: 'BTM Layout', minLat: 12.90, maxLat: 12.93, minLng: 77.59, maxLng: 77.62 },
  { name: 'HSR Layout', minLat: 12.90, maxLat: 12.93, minLng: 77.62, maxLng: 77.65 },
  { name: 'Electronic City', minLat: 12.82, maxLat: 12.86, minLng: 77.65, maxLng: 77.69 },
  { name: 'MG Road', minLat: 12.97, maxLat: 12.99, minLng: 77.59, maxLng: 77.62 },
  { name: 'Shivajinagar', minLat: 12.98, maxLat: 13.00, minLng: 77.58, maxLng: 77.60 },
  { name: 'Vijayanagar', minLat: 12.96, maxLat: 12.98, minLng: 77.52, maxLng: 77.55 },
  { name: 'Nagarbhavi', minLat: 12.94, maxLat: 12.97, minLng: 77.50, maxLng: 77.54 },
  { name: 'JP Nagar', minLat: 12.90, maxLat: 12.93, minLng: 77.56, maxLng: 77.59 },
  { name: 'Banashankari', minLat: 12.91, maxLat: 12.93, minLng: 77.54, maxLng: 77.56 },
  { name: 'Nagasandra', minLat: 13.04, maxLat: 13.08, minLng: 77.50, maxLng: 77.54 },
  { name: 'Yelahanka', minLat: 13.08, maxLat: 13.13, minLng: 77.57, maxLng: 77.62 },
  { name: 'Kengeri', minLat: 12.90, maxLat: 12.95, minLng: 77.46, maxLng: 77.50 },
  { name: 'Marathahalli', minLat: 12.94, maxLat: 12.97, minLng: 77.69, maxLng: 77.73 },
  { name: 'Bellandur', minLat: 12.91, maxLat: 12.94, minLng: 77.65, maxLng: 77.69 },
  { name: 'Sarjapur Road', minLat: 12.88, maxLat: 12.92, minLng: 77.67, maxLng: 77.72 },
  { name: 'CV Raman Nagar', minLat: 12.98, maxLat: 13.01, minLng: 77.65, maxLng: 77.68 },
];

function _lookupArea(lat: number, lng: number): string | null {
  for (const area of BENGALURU_AREAS) {
    if (lat >= area.minLat && lat <= area.maxLat && lng >= area.minLng && lng <= area.maxLng) {
      return area.name;
    }
  }
  return null;
}

function _resolveName(h3_cell: string, lat: number, lng: number): string {
  const area = _lookupArea(lat, lng);
  if (area) return area;
  return `Grid ${h3_cell.slice(-6)}`;
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

function mapRealHex(hex: any, index: number) {
  let lat: number;
  let lng: number;
  try {
    const coords = cellToLatLng(hex.h3_cell);
    lat = coords[0];
    lng = coords[1];
  } catch (e) {
    console.warn('Skipping hexagon with unparseable h3_cell:', hex.h3_cell);
    return null;
  }

  let maxSource = 'traffic';
  let maxVal = 0;
  if (hex.source_attribution) {
    for (const [key, value] of Object.entries(hex.source_attribution)) {
      if ((value as number) > maxVal) {
        maxVal = value as number;
        maxSource = key;
      }
    }
  }

  const sourceTypeMap: Record<string, 'Traffic Hub' | 'Heavy Ind.' | 'Construction' | 'Waste Burning'> = {
    traffic: 'Traffic Hub',
    industrial: 'Heavy Ind.',
    construction: 'Construction',
    burning: 'Waste Burning',
  };

  let exposure: 'Low' | 'Medium' | 'High' | 'Critical' = 'Medium';
  const expWeight = hex.scoring_breakdown?.exposure_weight ?? 0.5;
  if (expWeight < 0.3) exposure = 'Low';
  else if (expWeight < 0.6) exposure = 'Medium';
  else if (expWeight < 0.8) exposure = 'High';
  else exposure = 'Critical';

  let actionability: 'IMMEDIATE' | 'HIGH' | 'MONITOR' = 'MONITOR';
  const actWeight = hex.scoring_breakdown?.actionability_weight ?? 0.5;
  if (actWeight > 0.8) actionability = 'IMMEDIATE';
  else if (actWeight > 0.4) actionability = 'HIGH';

  return {
    id: hex.h3_cell,
    name: _resolveName(hex.h3_cell, lat, lng),
    priorityScore: Math.round(hex.priority_score * 100),
    changeVal: Number((Math.sin(index + 1) * 2.5).toFixed(1)),
    exposure,
    magnitude: Math.round((hex.scoring_breakdown?.attributable_magnitude || 0) * 100),
    confidence: 90,
    actionability,
    pm25: Math.round(hex.fused_pm25 || hex.predicted_pm25 || 0),
    primarySource: maxSource.charAt(0).toUpperCase() + maxSource.slice(1),
    sourceType: sourceTypeMap[maxSource] || ('Heavy Ind.' as const),
    sourceAttribution: {
      traffic: hex.source_attribution?.traffic ?? 0,
      industrial: hex.source_attribution?.industrial ?? 0,
      construction: hex.source_attribution?.construction ?? 0,
      burning: hex.source_attribution?.burning ?? 0,
    },
    explanation: hex.explanation,
    lat,
    lng,
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

  return {
    id: attr.h3_cell,
    name: _resolveName(attr.h3_cell, lat, lng),
    priorityScore: fusedPm25Num,
    changeVal: 0,
    exposure: 'Medium',
    magnitude: 0,
    confidence: 0,
    actionability: 'MONITOR',
    pm25: fusedPm25Num,
    primarySource: maxSource.charAt(0).toUpperCase() + maxSource.slice(1),
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

export function useStations() {
  return useQuery<{ id: string; name: string; lat: number; lng: number; aqi: number; status: 'Good' | 'Moderate' | 'Poor' | 'Severe' }[]>({
    queryKey: ['stations'],
    queryFn: async () => {
      const { data } = await apiClient.get('/stations?city=bengaluru');
      if (data && data.stations && data.stations.length > 0) {
        return data.stations.map(mapRealStation);
      }
      throw new Error('No stations returned from API');
    },
    refetchInterval: 10000,
  });
}

export function usePriorities() {
  return useQuery<PriorityHex[]>({
    queryKey: ['priorities'],
    queryFn: async () => {
      const { data } = await apiClient.get('/enforcement/priority/bengaluru?top_k=20');
      if (data && data.ranked_hexagons && data.ranked_hexagons.length > 0) {
        return data.ranked_hexagons.map((hex: any, idx: number) => mapRealHex(hex, idx)).filter((h: PriorityHex | null): h is PriorityHex => h !== null);
      }
      throw new Error('No ranked hexagons returned from API');
    },
  });
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
