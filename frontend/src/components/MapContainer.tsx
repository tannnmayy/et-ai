import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { APIProvider, Map, AdvancedMarker, useMap } from '@vis.gl/react-google-maps';
import { Key, AlertTriangle } from 'lucide-react';
import { PriorityHex } from '../types';
import { actionTierStyles, formatLocationName } from '../services/enforcementUtils';

export type StationMarker = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  aqi: number;
  status: string;
};

export type NearbySample = {
  key: string;
  lat: number;
  lng: number;
  aqi: number;
  stationId: string;
  stationName: string;
  hexId?: string;
  name?: string;
};

interface MapContainerProps {
  selectedHex: PriorityHex | null;
  onSelectHex: (hex: PriorityHex) => void;
  allHexes: PriorityHex[];
  /** Map colouring: AQI (default) or enforcement tier. Confidence layer removed. */
  viewMode: 'aqi' | 'enforcement';
  /** Smaller map labels when showing many polluted hexes (30–100). */
  compactLabels?: boolean;
  /** H3 cell ids to emphasize from Copilot map_actions */
  highlightedHexIds?: string[];
  /** Optional lat/lng from Copilot focus_on */
  focusCenter?: { lat: number; lng: number } | null;
  /** Official CPCB/KSPCB stations */
  stations?: StationMarker[];
  /**
   * Larger pool of hexes with real fused PM2.5 used only to pick ≥5 nearby
   * samples around each station (not all drawn as hex labels).
   */
  samplePool?: PriorityHex[];
  /**
   * When Local Peaks ranking is active, these hex ids get a distinct "Peak" badge
   * (station-catchment dirty pockets — not global absolute ties).
   */
  localPeakHexIds?: string[];
}

const API_KEY = String(
  (import.meta as any).env?.VITE_GOOGLE_MAPS_API_KEY ||
    (import.meta as any).env?.VITE_GOOGLE_MAPS_PLATFORM_KEY ||
    '',
).trim();

const MAP_ID = String((import.meta as any).env?.VITE_GOOGLE_MAPS_MAP_ID || '').trim();

const isRealKey =
  Boolean(API_KEY) &&
  API_KEY !== 'YOUR_API_KEY' &&
  !API_KEY.includes('MY_GEMINI') &&
  API_KEY.length >= 20;

const darkMapStyles = [
  { elementType: 'geometry', stylers: [{ color: '#000000' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#000000' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#74747a' }] },
  { featureType: 'administrative', elementType: 'geometry', stylers: [{ color: '#1c1c1e' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#1c1c1e' }] },
  { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#48484a' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0c0c0e' }] },
];

const NEARBY_COUNT = 5;
/** Max search radius (km) for real hex samples around a station */
const NEARBY_MAX_KM = 4.5;

function MapStyleController({ enabled }: { enabled: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!map || !enabled) return;
    map.setOptions({
      styles: darkMapStyles,
      disableDefaultUI: true,
      zoomControl: true,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: false,
    });
  }, [map, enabled]);
  return null;
}

function MapFocusController({
  center,
}: {
  center: { lat: number; lng: number } | null | undefined;
}) {
  const map = useMap();
  useEffect(() => {
    if (!map || !center) return;
    if (
      typeof center.lat !== 'number' ||
      typeof center.lng !== 'number' ||
      Number.isNaN(center.lat) ||
      Number.isNaN(center.lng)
    ) {
      return;
    }
    map.panTo(center);
    const z = map.getZoom() ?? 12;
    if (z < 12) map.setZoom(13);
  }, [map, center?.lat, center?.lng]);
  return null;
}

function aqiColor(aqi: number): string {
  if (aqi <= 50) return '#34C759';
  if (aqi <= 100) return '#FFCC00';
  if (aqi <= 250) return '#FF9F0A';
  return '#ff453a';
}

function hexColor(hex: PriorityHex, viewMode: 'aqi' | 'enforcement'): string {
  if (viewMode === 'enforcement') {
    return actionTierStyles(hex.actionTier || 'MONITOR').mapColor;
  }
  return aqiColor(hex.pm25);
}

/** Approx km between two lat/lng points (equirectangular). */
function distKm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const dLat = (aLat - bLat) * 111;
  const dLng = (aLng - bLng) * 111 * Math.cos((aLat * Math.PI) / 180);
  return Math.sqrt(dLat * dLat + dLng * dLng);
}

/** Short station label for map (avoid clutter). */
export function shortStationLabel(name: string, id: string): string {
  const cleaned = name
    .replace(/CPCB|KSPCB/gi, '')
    .replace(/Bengaluru|Bangalore/gi, '')
    .replace(/[-_,]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned) return id.slice(0, 10);
  // Prefer first meaningful token(s)
  const parts = cleaned.split(' ').filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 14);
  if (parts[0].length + parts[1].length < 16) return `${parts[0]} ${parts[1]}`.slice(0, 16);
  return parts[0].slice(0, 14);
}

/**
 * Pick ≥5 nearest real fused-PM hexes around each station from the sample pool.
 * No synthetic AQI — only hexes with valid pm25.
 */
export function buildNearbySamples(
  stations: StationMarker[],
  pool: PriorityHex[],
  count: number = NEARBY_COUNT,
): NearbySample[] {
  if (!stations.length || !pool.length) return [];

  const valid = pool.filter(
    (h) =>
      h &&
      typeof h.lat === 'number' &&
      typeof h.lng === 'number' &&
      Number.isFinite(h.pm25) &&
      h.pm25 > 0,
  );

  const out: NearbySample[] = [];
  const usedHexKeys = new Set<string>();

  for (const s of stations) {
    const ranked = valid
      .map((h) => ({
        hex: h,
        d: distKm(s.lat, s.lng, h.lat, h.lng),
      }))
      .filter((x) => x.d <= NEARBY_MAX_KM && x.d > 0.05)
      .sort((a, b) => a.d - b.d);

    let added = 0;
    for (const { hex } of ranked) {
      // Prefer unique hexes globally; allow reuse if pool is sparse
      const uk = `${s.id}:${hex.id}`;
      if (usedHexKeys.has(hex.id) && added < count) {
        // skip if already used by another station unless we need fillers
        if (ranked.length > count * 2) continue;
      }
      usedHexKeys.add(hex.id);
      out.push({
        key: uk,
        lat: hex.lat,
        lng: hex.lng,
        aqi: Math.round(hex.pm25),
        stationId: s.id,
        stationName: s.name,
        hexId: hex.id,
        name: formatLocationName(hex) || hex.name,
      });
      added += 1;
      if (added >= count) break;
    }
  }
  return out;
}

/** Official station diamond — distinct from hex cards; AQI-tinted edge, no neon glow. */
function StationDiamondIcon({
  name,
  aqi,
  status,
  showLabel = true,
}: {
  name: string;
  aqi: number;
  status: string;
  showLabel?: boolean;
}) {
  const label = shortStationLabel(name, '');
  const edge = aqiColor(aqi);
  return (
    <div
      className="flex flex-col items-center pointer-events-auto select-none -translate-y-1"
      title={`Official sensor · ${name} · ${aqi} µg/m³ · ${status}`}
    >
      <div className="relative w-6 h-6 flex items-center justify-center">
        {/* Soft drop only — no bloom */}
        <div
          className="absolute inset-0 rotate-45 rounded-[3px]"
          style={{
            background: edge,
            boxShadow: '0 2px 6px rgba(0,0,0,0.55)',
          }}
        />
        <div
          className="absolute inset-[3px] rotate-45 rounded-[2px] bg-[#0A84FF]"
          style={{ border: '1.5px solid rgba(255,255,255,0.95)' }}
        />
        <div className="absolute inset-[7px] rotate-45 rounded-[1px] bg-white" />
      </div>
      {showLabel && (
        <div className="mt-1.5 flex flex-col items-center gap-0.5 max-w-[100px]">
          <span className="text-[7px] font-mono font-bold uppercase tracking-[0.12em] text-[#0A84FF] bg-black/90 border border-[#0A84FF]/45 px-1.5 py-0.5 rounded leading-none">
            Sensor
          </span>
          <span className="max-w-[100px] truncate text-[9px] font-bold tracking-wide text-white bg-black/90 border border-white/15 px-1.5 py-0.5 rounded-md leading-none">
            {label}
          </span>
          <span
            className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded leading-none border border-white/20 bg-black/85"
            style={{ color: edge }}
          >
            {Math.round(aqi)} µg
          </span>
        </div>
      )}
    </div>
  );
}

/** Small AQI chip for nearby real hex samples around a sensor */
function NearbyAqiChip({ aqi, title }: { aqi: number; title: string }) {
  const color = aqiColor(aqi);
  return (
    <div
      className="flex items-center gap-1 rounded-md bg-black/88 border px-1.5 py-0.5"
      style={{ borderColor: `${color}66` }}
      title={title}
    >
      <span
        className="w-1.5 h-1.5 rounded-sm rotate-45 shrink-0"
        style={{ background: color }}
      />
      <span className="text-[8px] font-mono font-bold text-white leading-none tabular-nums">
        {aqi}
      </span>
    </div>
  );
}

function MapContainer({
  selectedHex,
  onSelectHex,
  allHexes,
  viewMode,
  compactLabels = false,
  highlightedHexIds = [],
  focusCenter = null,
  stations = [],
  samplePool,
  localPeakHexIds = [],
}: MapContainerProps) {
  const [showRealMap, setShowRealMap] = useState(isRealKey);
  const [mapsError, setMapsError] = useState<string | null>(null);
  const highlightSet = useMemo(() => new Set(highlightedHexIds || []), [highlightedHexIds]);
  const peakSet = useMemo(() => new Set(localPeakHexIds || []), [localPeakHexIds]);

  const pool = useMemo(() => {
    if (samplePool && samplePool.length > 0) return samplePool;
    return allHexes;
  }, [samplePool, allHexes]);

  const nearbySamples = useMemo(
    () => buildNearbySamples(stations, pool, NEARBY_COUNT),
    [stations, pool],
  );

  useEffect(() => {
    if (!isRealKey && import.meta.env.DEV) {
      console.warn(
        '[MapContainer] No Google Maps API key in import.meta.env.VITE_GOOGLE_MAPS_API_KEY. ' +
          'Showing simulation grid. Fix frontend/.env or root GOOGLE_MAPS_BROWSER_API_KEY (UTF-8 no BOM), then restart Vite.',
      );
    }
  }, []);

  const bounds = useMemo(() => {
    const pts = [
      ...allHexes.map((h) => ({ lat: h.lat, lng: h.lng })),
      ...stations.map((s) => ({ lat: s.lat, lng: s.lng })),
    ].filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng));
    if (pts.length === 0) {
      return { minLat: 12.9, maxLat: 13.05, minLng: 77.5, maxLng: 77.7 };
    }
    return {
      minLat: Math.min(...pts.map((p) => p.lat)),
      maxLat: Math.max(...pts.map((p) => p.lat)),
      minLng: Math.min(...pts.map((p) => p.lng)),
      maxLng: Math.max(...pts.map((p) => p.lng)),
    };
  }, [allHexes, stations]);

  const { minLat, maxLat, minLng, maxLng } = bounds;
  const latRange = maxLat - minLat || 0.01;
  const lngRange = maxLng - minLng || 0.01;

  const project = useCallback(
    (lat: number, lng: number) => {
      const x = 120 + ((lng - minLng) / lngRange) * 560;
      const y = 500 - ((lat - minLat) / latRange) * 400;
      return { x, y };
    },
    [minLat, minLng, latRange, lngRange],
  );

  const getHexPoints = useCallback((cx: number, cy: number, r: number) => {
    const points = [];
    for (let i = 0; i < 6; i++) {
      const angle = (i * 60 * Math.PI) / 180;
      points.push(`${(cx + r * Math.cos(angle)).toFixed(1)},${(cy + r * Math.sin(angle)).toFixed(1)}`);
    }
    return points.join(' ');
  }, []);

  const mapCenter = useMemo(
    () => ({
      lat: (minLat + maxLat) / 2 || 12.9716,
      lng: (minLng + maxLng) / 2 || 77.5946,
    }),
    [minLat, maxLat, minLng, maxLng],
  );

  // Allow stations-only shell while hex rankings are still loading (Landing warm path)
  if ((!allHexes || allHexes.length === 0) && stations.length === 0) {
    return (
      <div className="w-full h-full bg-black flex items-center justify-center flex-col gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-brand-blue/30 border-t-brand-blue animate-spin" />
        <span className="text-[10px] font-mono uppercase tracking-widest text-apple-secondary animate-pulse">
          Synchronizing Sentinel Grids...
        </span>
      </div>
    );
  }

  const effectiveMapId = MAP_ID || 'DEMO_MAP_ID';

  return (
    <div className="relative w-full h-full min-h-[320px] bg-black flex flex-col overflow-hidden">
      {/* Status chip — bottom-left area of map canvas (avoids MapPage top controls) */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 pointer-events-auto">
        <div className="bg-apple-card/85 backdrop-blur-md rounded-full px-3 py-1.5 border border-apple-border flex items-center gap-2 shadow-lg">
          <div
            className={`w-1.5 h-1.5 rounded-full ${isRealKey && showRealMap ? 'bg-brand-green' : 'bg-brand-orange animate-pulse'}`}
          />
          <span className="text-[10px] font-mono uppercase text-apple-secondary">
            {isRealKey && showRealMap ? 'Live map' : 'Simulation grid'}
          </span>
          {stations.length > 0 && (
            <span className="text-[10px] font-mono text-white/70 border-l border-white/10 pl-2">
              {stations.length} sensors
              {nearbySamples.length > 0 ? ` · ${nearbySamples.length} nearby` : ''}
            </span>
          )}
          {isRealKey && (
            <button
              type="button"
              onClick={() => setShowRealMap((v) => !v)}
              className="text-[10px] text-brand-blue underline hover:text-blue-300 ml-1"
            >
              {showRealMap ? 'Sim' : 'Live'}
            </button>
          )}
          {!isRealKey && (
            <button
              type="button"
              onClick={() =>
                setMapsError(
                  'No VITE_GOOGLE_MAPS_API_KEY loaded. Check frontend/.env and restart Vite.',
                )
              }
              className="text-[10px] text-brand-blue underline hover:text-blue-300 ml-1 flex items-center gap-1"
            >
              <Key size={10} /> Details
            </button>
          )}
        </div>
      </div>

      {mapsError && (
        <div className="absolute top-16 left-4 right-4 z-20 max-w-md rounded-2xl bg-brand-orange/15 border border-brand-orange/30 px-4 py-3 text-[11px] text-brand-orange flex gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>{mapsError}</span>
        </div>
      )}

      {showRealMap && isRealKey ? (
        <APIProvider
          apiKey={API_KEY}
          version="weekly"
          onLoad={() => setMapsError(null)}
          onError={() => {
            console.error('[MapContainer] Google Maps load error');
            setMapsError(
              'Google Maps failed to load. Enable Maps JavaScript API + billing, and allow this origin on the browser key.',
            );
          }}
        >
          <div className="w-full h-full min-h-[320px]">
            <Map
              defaultCenter={mapCenter}
              defaultZoom={12}
              gestureHandling="cooperative"
              disableDefaultUI
              zoomControl
              mapId={effectiveMapId}
              style={{ width: '100%', height: '100%' }}
              colorScheme="DARK"
            >
              {!MAP_ID && <MapStyleController enabled />}
              <MapFocusController center={focusCenter} />

              {/* Nearby real hex AQI chips around sensors */}
              {nearbySamples.map((r) => (
                <AdvancedMarker key={r.key} position={{ lat: r.lat, lng: r.lng }} zIndex={10}>
                  <NearbyAqiChip
                    aqi={r.aqi}
                    title={`${r.name || r.hexId || 'Nearby hex'} · ${r.aqi} µg/m³ (near ${shortStationLabel(r.stationName, r.stationId)})`}
                  />
                </AdvancedMarker>
              ))}

              {/* Official CPCB/KSPCB diamonds */}
              {stations.map((s) => (
                <AdvancedMarker
                  key={`st-${s.id}`}
                  position={{ lat: s.lat, lng: s.lng }}
                  zIndex={40}
                >
                  <StationDiamondIcon name={s.name} aqi={s.aqi} status={s.status} />
                </AdvancedMarker>
              ))}

              {/* Hex labels — peak mode uses a compact station-catchment card */}
              {allHexes.map((hex) => {
                const color = hexColor(hex, viewMode);
                const label = formatLocationName(hex);
                const isSelected = selectedHex?.id === hex.id;
                const isCopilotHighlight = highlightSet.has(hex.id);
                const isLocalPeak = peakSet.has(hex.id);
                const borderColor = isCopilotHighlight
                  ? '#BF5AF2'
                  : isLocalPeak
                    ? '#0A84FF'
                    : color;
                const borderW = isCopilotHighlight ? 2.5 : isLocalPeak || isSelected ? 2 : 1.5;
                return (
                  <AdvancedMarker
                    key={hex.id}
                    position={{ lat: hex.lat, lng: hex.lng }}
                    onClick={() => onSelectHex(hex)}
                    zIndex={isSelected || isCopilotHighlight || isLocalPeak ? 30 : 5}
                  >
                    <div
                      className={`cursor-pointer rounded-lg bg-black/90 font-mono text-white transition-transform hover:scale-105 ${
                        compactLabels ? 'p-1.5 text-[8px] max-w-[92px]' : 'p-2 text-[10px]'
                      } ${isCopilotHighlight ? 'ring-1 ring-fuchsia-400/70' : ''} ${
                        isLocalPeak && !isCopilotHighlight ? 'ring-1 ring-brand-blue/35' : ''
                      }`}
                      style={{
                        borderStyle: 'solid',
                        borderWidth: borderW,
                        borderColor,
                        borderTopWidth: isLocalPeak && !isCopilotHighlight ? 3 : borderW,
                        borderTopColor: isLocalPeak && !isCopilotHighlight ? '#0A84FF' : borderColor,
                        boxShadow: isSelected
                          ? `0 0 0 1px ${color}66`
                          : isCopilotHighlight
                            ? '0 0 0 1px #BF5AF266'
                            : isLocalPeak
                              ? '0 2px 8px rgba(10,132,255,0.18)'
                              : '0 1px 4px rgba(0,0,0,0.35)',
                      }}
                      title={`${label} · ${hex.pm25} µg/m³${isLocalPeak ? ' · Local peak (station catchment)' : ''}${isCopilotHighlight ? ' · Copilot highlight' : ''}`}
                    >
                      {(isLocalPeak || isCopilotHighlight) && (
                        <span
                          className={`text-[7px] uppercase tracking-wider font-bold block mb-0.5 ${
                            isCopilotHighlight ? 'text-fuchsia-300' : 'text-brand-blue'
                          }`}
                        >
                          {isCopilotHighlight ? 'Copilot' : 'Local peak'}
                        </span>
                      )}
                      <span
                        className={`font-bold font-sans block truncate ${compactLabels ? 'max-w-[80px]' : ''}`}
                      >
                        {compactLabels && label.length > 12 ? `${label.slice(0, 11)}…` : label}
                      </span>
                      <div
                        className="text-right font-bold mt-0.5 tabular-nums"
                        style={{
                          color: isCopilotHighlight ? '#BF5AF2' : isLocalPeak ? '#0A84FF' : color,
                        }}
                      >
                        {viewMode === 'enforcement'
                          ? `${hex.score10?.toFixed?.(1) ?? '—'} · ${hex.pm25 || '—'} µg`
                          : `${hex.pm25} µg/m³`}
                      </div>
                    </div>
                  </AdvancedMarker>
                );
              })}
            </Map>
          </div>
        </APIProvider>
      ) : (
        <div className="relative w-full h-full overflow-hidden bg-[#050506]">
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#1c1c1e_1px,transparent_1px),linear-gradient(to_bottom,#1c1c1e_1px,transparent_1px)] bg-[size:40px_40px] opacity-30" />

          <svg
            className="absolute inset-0 w-full h-full pointer-events-none"
            viewBox="0 0 800 600"
            preserveAspectRatio="none"
          >
            {allHexes.map((hex) => {
              const { x, y } = project(hex.lat, hex.lng);
              const color = hexColor(hex, viewMode);
              const isSelected = selectedHex?.id === hex.id;
              const isCopilotHighlight = highlightSet.has(hex.id);
              const isLocalPeak = peakSet.has(hex.id);
              const label = formatLocationName(hex);
              const strokeColor = isCopilotHighlight
                ? '#BF5AF2'
                : isLocalPeak
                  ? '#0A84FF'
                  : color;
              const strokeW = isCopilotHighlight ? 2.5 : isLocalPeak || isSelected ? 2 : 1.2;
              const r = compactLabels ? 28 : 42;
              return (
                <g
                  key={hex.id}
                  className="cursor-pointer pointer-events-auto group/hex"
                  onClick={() => onSelectHex(hex)}
                >
                  {isCopilotHighlight && (
                    <polygon
                      points={getHexPoints(x, y, r + 6)}
                      fill="none"
                      stroke="#BF5AF2"
                      strokeWidth={1.5}
                      opacity={0.5}
                    />
                  )}
                  {isLocalPeak && !isCopilotHighlight && (
                    <polygon
                      points={getHexPoints(x, y, r + 4)}
                      fill="none"
                      stroke="#0A84FF"
                      strokeWidth={1}
                      opacity={0.4}
                      strokeDasharray="3 2"
                    />
                  )}
                  <polygon
                    points={getHexPoints(x, y, r)}
                    fill={
                      isCopilotHighlight
                        ? '#BF5AF228'
                        : isLocalPeak
                          ? '#0A84FF22'
                          : isSelected
                            ? `${color}35`
                            : `${color}18`
                    }
                    stroke={strokeColor}
                    strokeWidth={strokeW}
                    className="transition-all duration-200 hover:fill-white/10"
                  />
                  {isLocalPeak && (
                    <text
                      x={x}
                      y={y - (compactLabels ? 12 : 14)}
                      fill="#0A84FF"
                      fontSize="6"
                      fontFamily="Inter, sans-serif"
                      textAnchor="middle"
                      className="font-bold pointer-events-none select-none"
                    >
                      PEAK
                    </text>
                  )}
                  <text
                    x={x}
                    y={y - 2}
                    fill="#fff"
                    fontSize={compactLabels ? '7' : '9'}
                    fontFamily="Inter, sans-serif"
                    textAnchor="middle"
                    className="font-bold pointer-events-none select-none opacity-90"
                  >
                    {label.length > (compactLabels ? 10 : 14)
                      ? `${label.slice(0, compactLabels ? 9 : 12)}…`
                      : label}
                  </text>
                  <text
                    x={x}
                    y={y + 10}
                    fill={isCopilotHighlight ? '#BF5AF2' : isLocalPeak ? '#0A84FF' : color}
                    fontSize={compactLabels ? '6' : '8'}
                    fontFamily="monospace"
                    textAnchor="middle"
                    className="pointer-events-none select-none font-semibold"
                  >
                    {viewMode === 'enforcement'
                      ? `${hex.score10?.toFixed?.(1) ?? '—'} / ${hex.pm25 || '—'}µg`
                      : `${hex.pm25} µg/m³`}
                  </text>
                </g>
              );
            })}

            {/* Nearby real samples (sim) */}
            {nearbySamples.map((r) => {
              const { x, y } = project(r.lat, r.lng);
              const c = aqiColor(r.aqi);
              return (
                <g key={r.key}>
                  <rect
                    x={x - 3}
                    y={y - 3}
                    width={6}
                    height={6}
                    fill={c}
                    stroke="#fff"
                    strokeWidth={0.8}
                    transform={`rotate(45 ${x} ${y})`}
                    rx={0.5}
                    opacity={0.95}
                  />
                  <text
                    x={x + 7}
                    y={y + 3}
                    fill="#fff"
                    fontSize="7"
                    fontFamily="monospace"
                    className="font-bold"
                  >
                    {r.aqi}
                  </text>
                </g>
              );
            })}

            {/* Station diamonds (sim) */}
            {stations.map((s) => {
              const { x, y } = project(s.lat, s.lng);
              const label = shortStationLabel(s.name, s.id);
              const edge = aqiColor(s.aqi);
              return (
                <g key={`st-${s.id}`}>
                  <rect
                    x={x - 7}
                    y={y - 7}
                    width={14}
                    height={14}
                    fill={edge}
                    transform={`rotate(45 ${x} ${y})`}
                    rx={1.5}
                    opacity={0.95}
                  />
                  <rect
                    x={x - 5}
                    y={y - 5}
                    width={10}
                    height={10}
                    fill="#0A84FF"
                    stroke="#fff"
                    strokeWidth={1.2}
                    transform={`rotate(45 ${x} ${y})`}
                    rx={1}
                  />
                  <rect
                    x={x - 2}
                    y={y - 2}
                    width={4}
                    height={4}
                    fill="#fff"
                    transform={`rotate(45 ${x} ${y})`}
                  />
                  <text
                    x={x}
                    y={y + 18}
                    fill="#8ECAFF"
                    fontSize="6"
                    fontFamily="monospace"
                    textAnchor="middle"
                    className="font-bold"
                  >
                    SENSOR
                  </text>
                  <text
                    x={x}
                    y={y + 28}
                    fill="#fff"
                    fontSize="8"
                    fontFamily="Inter, sans-serif"
                    textAnchor="middle"
                    className="font-bold"
                  >
                    {label}
                  </text>
                  <text
                    x={x}
                    y={y + 38}
                    fill={edge}
                    fontSize="7"
                    fontFamily="monospace"
                    textAnchor="middle"
                    className="font-bold"
                  >
                    {Math.round(s.aqi)} µg
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </div>
  );
}

export default memo(MapContainer);
