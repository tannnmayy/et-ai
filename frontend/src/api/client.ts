import type { CityGridAttributionResponse, EnforcementPriorityResponse, SingleHexagonResponse } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

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

export function getCityGridAttribution(city: string = "bengaluru") {
  return apiGet<CityGridAttributionResponse>(`/attribution/city/${city}?include_fusion=true`);
}

export function getEnforcementPriority(city: string = "bengaluru", topK: number = 5) {
  return apiGet<EnforcementPriorityResponse>(`/enforcement/priority/${city}?top_k=${topK}`);
}

export function getHexagonAttribution(h3Cell: string, city: string = "bengaluru") {
  return apiGet<SingleHexagonResponse>(`/attribution/hexagon/${h3Cell}?city=${city}&include_fusion=true`);
}
