import type { CityGridAttributionResponse, EnforcementPriorityResponse, SingleHexagonResponse } from "./types";

// In development Vite forwards /api to FastAPI.  A deployed app can override
// this with VITE_API_BASE_URL without changing any component code.
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

const FETCH_TIMEOUT_MS = 30_000; // 30 s — surfaces as an error instead of infinite skeleton

async function apiGet<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { signal: controller.signal });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Request timed out after 30 s — the server may be busy or unreachable.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export function getCityGridAttribution(city: string = "bengaluru") {
  // Fusion is intentionally requested only for a selected cell. Computing it
  // for the full grid is expensive and the grid response does not expose it.
  return apiGet<CityGridAttributionResponse>(`/attribution/city/${city}?include_fusion=false&max_hexagons=80`);
}

export function getEnforcementPriority(city: string = "bengaluru", topK: number = 5) {
  return apiGet<EnforcementPriorityResponse>(`/enforcement/priority/${city}?top_k=${topK}`);
}

export function getHexagonAttribution(h3Cell: string, city: string = "bengaluru") {
  return apiGet<SingleHexagonResponse>(`/attribution/hexagon/${h3Cell}?city=${city}&include_fusion=true`);
}

export const getStations = () => apiGet<any>("/stations?city=bengaluru");
export const getForecasts = () => apiGet<any>("/forecast/real/multistation");
export const getCityBriefing = () => apiGet<any>("/intelligence/city-briefing");
export const getInspectionPriorities = () => apiGet<any>("/intelligence/inspection-priorities?top_k=5");
export const getAirQualityMap = () => apiGet<{ city: string; cells: Array<{ h3_cell: string; pm25: number; risk_label: string; message: string; nearest_station: string }> }>("/enforcement/map/bengaluru?max_cells=900");
export const getTravelReadiness = (profile: string) => apiGet<any>(`/travel/readiness?city=bengaluru&profile=${encodeURIComponent(profile)}&period=tomorrow`);
export const getWeatherSummary = () => apiGet<any>("/weather/summary?city=bengaluru&period=tomorrow");
export const askCopilot = (body: { query: string; station_id?: string; profile?: string }) =>
  apiPost<any>("/copilot/query", { city: "bengaluru", language: "en", top_k: 5, profile: "general", ...body });
export const compareNeighbourhoods = (body: unknown) => apiPost<any>("/neighbourhoods/compare", body);
