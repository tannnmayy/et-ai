/**
 * Warm Map + Enforcement data (and Google Maps JS) while the user is still
 * on the landing page so the first app screen feels instant.
 *
 * Phase 1 (immediate): stations + extremes global + enforcement top-K + maps preconnect/script
 * Phase 2 (idle / delayed): local_peaks extremes + lazy route chunks
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

/** Prevent stampede from Landing mount + Continue + StrictMode double-mount */
let warmPhase1Started = false;
let warmPhase2Started = false;
let phase1Promise: Promise<void> | null = null;

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

/**
 * Phase 1 — Map-critical (default ranking mode is global).
 * Stations + global extremes + enforcement top-15.
 */
export async function prefetchMapCriticalData(queryClient: QueryClient): Promise<void> {
  await Promise.allSettled([
    queryClient.prefetchQuery({
      queryKey: ['stations'],
      queryFn: fetchStations,
      staleTime: 60_000,
    }),
    queryClient.prefetchQuery({
      queryKey: ['city-extremes', CITY_EXTREMES_FETCH_N, 'global'],
      queryFn: () => fetchCityExtremes(CITY_EXTREMES_FETCH_N, 'global'),
      staleTime: 90_000,
    }),
    queryClient.prefetchQuery({
      queryKey: enforcementPrioritiesQueryKey(ENFORCEMENT_DEFAULT_TOP_K, null),
      queryFn: () => fetchEnforcementPriorities(ENFORCEMENT_DEFAULT_TOP_K, null),
      staleTime: 60_000,
    }),
  ]);
}

/**
 * Phase 2 — secondary: Local Peaks extremes (Map dual-mode) after critical path.
 */
export async function prefetchMapSecondaryData(queryClient: QueryClient): Promise<void> {
  await Promise.allSettled([
    queryClient.prefetchQuery({
      queryKey: ['city-extremes', CITY_EXTREMES_FETCH_N, 'local_peaks'],
      queryFn: () => fetchCityExtremes(CITY_EXTREMES_FETCH_N, 'local_peaks'),
      staleTime: 90_000,
    }),
  ]);
}

/** Full data warm (both phases) — used when explicitly re-warming on Continue. */
export async function prefetchMapAndEnforcementData(queryClient: QueryClient) {
  await prefetchMapCriticalData(queryClient);
  await prefetchMapSecondaryData(queryClient);
}

/** Prefetch lazy route chunks so tab switches don't wait on network for JS. */
export function preloadAppRouteChunks() {
  void import('../pages/EnforcementPage');
  void import('../pages/InsightsPage');
  void import('../pages/CopilotPage');
  void import('../pages/CitizenModePage');
  void import('../pages/DispatchPage');
}

/**
 * Full landing-page warm-up: maps network + prioritized data + route chunks.
 * Safe to call multiple times (idempotent).
 *
 * Phase 1 runs immediately so Map is warm while the user fills the form.
 * Phase 2 (local_peaks + extra chunks) is deferred so it does not compete
 * with the critical extremes request.
 */
export function warmAppFromLanding(queryClient: QueryClient) {
  preconnectGoogleMaps();

  // Phase 1: immediate (stations + global extremes + enforcement + Maps JS)
  if (!warmPhase1Started) {
    warmPhase1Started = true;
    const runPhase1 = () => {
      preloadGoogleMapsScript();
      phase1Promise = prefetchMapCriticalData(queryClient).then(() => undefined);
      void phase1Promise;
    };
    // Next macrotask so Landing first paint is not blocked
    if (typeof window !== 'undefined') {
      window.setTimeout(runPhase1, 0);
    } else {
      runPhase1();
    }
  } else if (phase1Promise) {
    // Already in flight / done — no-op; Continue can still re-trigger secondary
    void phase1Promise;
  }

  // Phase 2: idle or after short delay
  if (!warmPhase2Started) {
    warmPhase2Started = true;
    const runPhase2 = () => {
      preloadAppRouteChunks();
      void prefetchMapSecondaryData(queryClient);
    };
    if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      (window as any).requestIdleCallback(runPhase2, { timeout: 2500 });
    } else if (typeof window !== 'undefined') {
      window.setTimeout(runPhase2, 2000);
    } else {
      runPhase2();
    }
  }
}

/**
 * Re-warm on Continue / Resume: ensure phase-1 is running and kick secondary.
 * Does not wait — Map will use RQ cache as soon as ready.
 */
export function ensureMapWarm(queryClient: QueryClient) {
  preconnectGoogleMaps();
  preloadGoogleMapsScript();
  if (!warmPhase1Started) {
    warmAppFromLanding(queryClient);
    return;
  }
  // Force another phase-1 prefetch (cheap if RQ already has data)
  void prefetchMapCriticalData(queryClient);
  if (!warmPhase2Started) {
    warmPhase2Started = true;
    void prefetchMapSecondaryData(queryClient);
    preloadAppRouteChunks();
  }
}
