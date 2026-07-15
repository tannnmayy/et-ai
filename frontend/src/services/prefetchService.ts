/**
 * Warm Map + Enforcement data (and Google Maps JS) while the user is still
 * on the landing page so the first app screen feels instant.
 */
import type { QueryClient } from '@tanstack/react-query';
import {
  CITY_EXTREMES_FETCH_N,
  ENFORCEMENT_DEFAULT_TOP_K,
  enforcementPrioritiesQueryKey,
  fetchCityExtremes,
  fetchEnforcementPriorities,
  fetchStations,
} from './geospatialService';

const MAPS_KEY = String(
  (import.meta as any).env?.VITE_GOOGLE_MAPS_API_KEY ||
    (import.meta as any).env?.VITE_GOOGLE_MAPS_PLATFORM_KEY ||
    '',
).trim();

function ensurePreconnect(href: string) {
  if (typeof document === 'undefined') return;
  if (document.querySelector(`link[data-prefetch-origin="${href}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'preconnect';
  link.href = href;
  link.crossOrigin = 'anonymous';
  link.setAttribute('data-prefetch-origin', href);
  document.head.appendChild(link);
}

/** DNS + TLS warm for Google Maps hosts (safe, no double script load). */
export function preconnectGoogleMaps() {
  ensurePreconnect('https://maps.googleapis.com');
  ensurePreconnect('https://maps.gstatic.com');
}

/**
 * Optionally start loading the Maps JS API early.
 * @vis.gl/react-google-maps will reuse `window.google` if already present.
 */
export function preloadGoogleMapsScript() {
  if (typeof window === 'undefined' || !MAPS_KEY || MAPS_KEY.length < 20) return;
  const w = window as any;
  if (w.google?.maps || w.__AQI_MAPS_PRELOAD__) return;
  w.__AQI_MAPS_PRELOAD__ = true;

  preconnectGoogleMaps();

  const existing = document.querySelector('script[data-aqi-maps-preload]');
  if (existing) return;

  const script = document.createElement('script');
  script.src =
    `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(MAPS_KEY)}` +
    '&v=weekly&libraries=marker&loading=async';
  script.async = true;
  script.defer = true;
  script.dataset.aqiMapsPreload = '1';
  document.head.appendChild(script);
}

/** Prefetch React Query caches used by Map + Enforcement. */
export async function prefetchMapAndEnforcementData(queryClient: QueryClient) {
  await Promise.allSettled([
    queryClient.prefetchQuery({
      queryKey: ['city-extremes', CITY_EXTREMES_FETCH_N],
      queryFn: () => fetchCityExtremes(CITY_EXTREMES_FETCH_N),
      staleTime: 60_000,
    }),
    queryClient.prefetchQuery({
      queryKey: ['stations'],
      queryFn: fetchStations,
      staleTime: 30_000,
    }),
    queryClient.prefetchQuery({
      queryKey: enforcementPrioritiesQueryKey(ENFORCEMENT_DEFAULT_TOP_K, null),
      queryFn: () => fetchEnforcementPriorities(ENFORCEMENT_DEFAULT_TOP_K, null),
      staleTime: 60_000,
    }),
  ]);
}

/** Prefetch lazy route chunks so tab switches don't wait on network for JS. */
export function preloadAppRouteChunks() {
  void import('../pages/EnforcementPage');
  void import('../pages/InsightsPage');
  void import('../pages/CopilotPage');
}

/**
 * Full landing-page warm-up: maps network + data + route chunks.
 * Safe to call multiple times (idempotent where possible).
 */
export function warmAppFromLanding(queryClient: QueryClient) {
  preconnectGoogleMaps();

  const run = () => {
    preloadGoogleMapsScript();
    preloadAppRouteChunks();
    void prefetchMapAndEnforcementData(queryClient);
  };

  if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
    (window as any).requestIdleCallback(run, { timeout: 1200 });
  } else {
    window.setTimeout(run, 200);
  }
}
