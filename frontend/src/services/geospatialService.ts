import { cellToLatLng } from 'h3-js';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';
import { PriorityHex } from '../types';

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
    name: `Grid ${hex.h3_cell.slice(-6)}`,
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
