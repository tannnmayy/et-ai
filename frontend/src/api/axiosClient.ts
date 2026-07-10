import axios from 'axios';
import { cellToLatLng } from 'h3-js';
import {
  mockStations,
  mockPriorities,
  mockFireDetections,
  mockNo2Density,
  mockNeighbourhoods,
  addChatMessage,
} from './mockData';

// Create a custom Axios instance configured for FastAPI via Vite proxy /api
export const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

function mapRiskToStatus(risk: string): 'Good' | 'Moderate' | 'Poor' | 'Severe' {
  const r = risk.toLowerCase();
  if (r.includes('good') || r.includes('low')) return 'Good';
  if (r.includes('satisfactory') || r.includes('moderate')) return 'Moderate';
  if (r.includes('poor')) return 'Poor';
  return 'Severe';
}

function mapRealStation(item: any): any {
  return {
    id: item.station_id || item.id,
    name: item.station_name || item.display_name || item.name,
    lat: item.latitude || item.lat || 12.9716,
    lng: item.longitude || item.lng || 77.5946,
    aqi: Math.round(item.predicted_pm25 || item.aqi || 55),
    status: mapRiskToStatus(item.risk_category || item.status || 'Good'),
  };
}

function mapRealHex(hex: any, index: number): any {
  let lat = 12.9716;
  let lng = 77.5946;
  try {
    const coords = cellToLatLng(hex.h3_cell);
    lat = coords[0];
    lng = coords[1];
  } catch (e) {
    // Fallback if cell is invalid
  }

  // Find dominant source
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

  const sourceTypeMap: Record<string, string> = {
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
    pm25: Math.round(hex.fused_pm25 || 0),
    primarySource: maxSource.charAt(0).toUpperCase() + maxSource.slice(1),
    sourceType: sourceTypeMap[maxSource] || 'Heavy Ind.',
    lat,
    lng,
  };
}

// Request interceptor to dynamically execute real requests and fallback to mock if they fail
apiClient.interceptors.request.use(async (config) => {
  const url = config.url || '';

  // We bypass the interceptor if it's a real request that failed and we are retrying internally
  if ((config as any)._isFallback) {
    return config;
  }

  // Create a separate axios instance for actual backend queries so we don't trigger the interceptor recursively
  const realApi = axios.create({
    baseURL: '/api',
    headers: { 'Content-Type': 'application/json' },
  });

  try {
    if (url.includes('/geospatial/stations')) {
      // Try to fetch real stations from /forecast/real/multistation (contains current values)
      try {
        const res = await realApi.get('/forecast/real/multistation');
        if (res.data && res.data.forecasts && res.data.forecasts.length > 0) {
          const stations = res.data.forecasts.map(mapRealStation);
          return {
            ...config,
            adapter: () => Promise.resolve({ data: stations, status: 200, statusText: 'OK', headers: {}, config }),
          };
        }
      } catch (err) {
        // Fallback to /stations endpoint
        const res = await realApi.get('/stations?city=bengaluru');
        if (res.data && res.data.stations && res.data.stations.length > 0) {
          const stations = res.data.stations.map(mapRealStation);
          return {
            ...config,
            adapter: () => Promise.resolve({ data: stations, status: 200, statusText: 'OK', headers: {}, config }),
          };
        }
      }
    } else if (url.includes('/geospatial/ranked-priority')) {
      // Try to fetch real ranked priorities from /enforcement/priority/bengaluru
      const res = await realApi.get('/enforcement/priority/bengaluru?top_k=20');
      if (res.data && res.data.ranked_hexagons && res.data.ranked_hexagons.length > 0) {
        const priorities = res.data.ranked_hexagons.map((hex: any, idx: number) => mapRealHex(hex, idx));
        return {
          ...config,
          adapter: () => Promise.resolve({ data: priorities, status: 200, statusText: 'OK', headers: {}, config }),
        };
      }
    } else if (url.includes('/geospatial/fire-detections')) {
      const res = await realApi.get('/geospatial/fire-detections?city=bengaluru');
      if (res.data && res.data.hexagons) {
        const detections = res.data.hexagons.map((hex: any) => {
          let lat = 12.9716;
          let lng = 77.5946;
          try {
            const coords = cellToLatLng(hex.h3_cell);
            lat = coords[0];
            lng = coords[1];
          } catch (e) {}
          return {
            id: hex.h3_cell,
            lat,
            lng,
            frp: hex.total_frp_mw,
            confidence: hex.max_confidence || 'nominal',
            timestamp: hex.window_end_utc,
          };
        });
        return {
          ...config,
          adapter: () => Promise.resolve({ data: detections, status: 200, statusText: 'OK', headers: {}, config }),
        };
      }
    } else if (url.includes('/geospatial/no2-column-density')) {
      const res = await realApi.get('/geospatial/no2-column-density?city=bengaluru');
      if (res.data && res.data.hexagons) {
        const no2 = res.data.hexagons.map((hex: any) => {
          let lat = 12.9716;
          let lng = 77.5946;
          try {
            const coords = cellToLatLng(hex.h3_cell);
            lat = coords[0];
            lng = coords[1];
          } catch (e) {}
          return {
            id: hex.h3_cell,
            lat,
            lng,
            density: hex.no2_column_density_mean || 0,
          };
        });
        return {
          ...config,
          adapter: () => Promise.resolve({ data: no2, status: 200, statusText: 'OK', headers: {}, config }),
        };
      }
    } else if (url.includes('/analytics/dashboard')) {
      // Build dynamic dashboard from real priorities if possible
      try {
        const res = await realApi.get('/enforcement/priority/bengaluru?top_k=10');
        if (res.data && res.data.ranked_hexagons && res.data.ranked_hexagons.length > 0) {
          const priorities = res.data.ranked_hexagons.map((hex: any, idx: number) => mapRealHex(hex, idx));
          const critical = priorities.slice(0, 3).map((p: any, idx: number) => ({
            rank: `0${idx + 1}`,
            name: p.id,
            issue: `Elevated ${p.primarySource}`,
            score: p.priorityScore,
          }));
          const prime = [...priorities]
            .reverse()
            .slice(0, 3)
            .map((p: any, idx: number) => ({
              rank: `0${idx + 1}`,
              name: p.id,
              issue: `Low ${p.primarySource}`,
              score: 100 - p.priorityScore,
            }));
          return {
            ...config,
            adapter: () =>
              Promise.resolve({
                data: {
                  criticalTargets: critical,
                  primeSuitability: prime,
                  neighbourhoods: mockNeighbourhoods,
                },
                status: 200,
                statusText: 'OK',
                headers: {},
                config,
              }),
          };
        }
      } catch (err) {}
    } else if (url.includes('/copilot/chat')) {
      // Direct call to copilot agent query endpoint
      const body = JSON.parse(config.data || '{}');
      const res = await realApi.post('/copilot/query', {
        query: body.message,
        city: 'bengaluru',
        profile: 'general',
        language: 'en',
      });

      if (res.data) {
        const reply = res.data.response_text;
        const reasoningList: any[] = [];
        if (res.data.audit_trail && res.data.audit_trail.steps) {
          res.data.audit_trail.steps.forEach((step: any, idx: number) => {
            reasoningList.push({
              id: `r-${idx + 1}`,
              step: typeof step === 'string' ? step : step.name || step.action || JSON.stringify(step),
              completed: true,
            });
          });
        } else {
          reasoningList.push(
            { id: 'r-1', step: 'routing_intent', completed: true },
            { id: 'r-2', step: 'evaluating_context', completed: true }
          );
        }

        const updatedHistory = addChatMessage(body.message, reply, reasoningList);
        return {
          ...config,
          adapter: () =>
            Promise.resolve({ data: { history: updatedHistory }, status: 200, statusText: 'OK', headers: {}, config }),
        };
      }
    }
  } catch (error) {
    console.warn(`API Interceptor: Request to ${url} failed. Falling back to mock data.`, error);
  }

  // FALLBACK TO MOCK DATA INTERCEPTOR
  return Promise.resolve({
    ...config,
    adapter: () => {
      let data: any = null;

      if (url.includes('/geospatial/stations')) {
        data = mockStations;
      } else if (url.includes('/geospatial/ranked-priority')) {
        data = mockPriorities;
      } else if (url.includes('/geospatial/fire-detections')) {
        data = mockFireDetections;
      } else if (url.includes('/geospatial/no2-column-density')) {
        data = mockNo2Density;
      } else if (url.includes('/analytics/dashboard')) {
        data = {
          criticalTargets: [
            { rank: '01', name: 'Peenya Phase II', issue: 'High NO2', score: 24 },
            { rank: '02', name: 'Whitefield Sec 44', issue: 'High PM10', score: 31 },
            { rank: '03', name: 'Silk Board Jn', issue: 'Severe Noise', score: 38 },
          ],
          primeSuitability: [
            { rank: '01', name: 'Jayanagar 4th Block', issue: 'Low PM2.5', score: 88 },
            { rank: '02', name: 'HSR Sector 2', issue: 'High Greens', score: 85 },
            { rank: '03', name: 'Cubbon Park', issue: 'Optimal AQI', score: 82 },
          ],
          neighbourhoods: mockNeighbourhoods,
        };
      } else if (url.includes('/copilot/chat')) {
        const body = JSON.parse(config.data || '{}');
        const lower = body.message.toLowerCase();
        let reply = '';
        const reasoningList = [
          { id: 'r-1', step: 'parsing_query', completed: true },
          { id: 'r-2', step: 'retrieving_aqi_metrics', completed: true },
        ];

        if (lower.includes('dispatch') || lower.includes('issue') || lower.includes('enforce')) {
          reply = `Action initiated. An enforcement unit has been dispatched to Sector 44. Status updated to **ACTIVE DISPATCH**. Unit ID: \`EN-449\`. Expected Arrival: **12 minutes**.`;
          reasoningList.push({ id: 'r-3', step: 'triggering_dispatch_rpc', completed: true });
        } else if (lower.includes('peenya') || lower.includes('no2')) {
          reply = `Peenya Industrial Area shows chronic elevated NO₂ levels. The primary source remains industrial exhaust stacks from chemical processing plants in Block G. Winds are dispersing emissions towards residential areas to the South-West.`;
          reasoningList.push({ id: 'r-3', step: 'pulling_satellite_no2_overlay', completed: true });
        } else {
          reply = `Copilot is online. Received query: "${body.message}". I am continuously parsing sentinel sensor arrays. I detect elevated PM2.5 hotspots in adjacent sectors. How can I assist you with dispatches or analytics?`;
          reasoningList.push({ id: 'r-3', step: 'indexing_active_logs', completed: true });
        }

        const updatedHistory = addChatMessage(body.message, reply, reasoningList);
        data = { history: updatedHistory };
      }

      return Promise.resolve({
        data,
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      });
    },
  });
});
