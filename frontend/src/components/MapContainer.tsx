import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { APIProvider, Map, AdvancedMarker, useMap } from '@vis.gl/react-google-maps';
import { Key, AlertTriangle } from 'lucide-react';
import { PriorityHex } from '../types';
import { actionTierStyles, formatLocationName } from '../services/enforcementUtils';

interface MapContainerProps {
  selectedHex: PriorityHex | null;
  onSelectHex: (hex: PriorityHex) => void;
  allHexes: PriorityHex[];
  viewMode: 'aqi' | 'enforcement';
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

/** Apply classic JSON styles when not using a Cloud Map ID. */
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

function hexColor(hex: PriorityHex, viewMode: 'aqi' | 'enforcement'): string {
  if (viewMode === 'enforcement') {
    return actionTierStyles(hex.actionTier || 'MONITOR').mapColor;
  }
  const pm = hex.pm25;
  if (pm <= 50) return '#34C759';
  if (pm <= 100) return '#FFCC00';
  if (pm <= 250) return '#FF9F0A';
  return '#ff453a';
}

function MapContainer({
  selectedHex,
  onSelectHex,
  allHexes,
  viewMode,
}: MapContainerProps) {
  const [showRealMap, setShowRealMap] = useState(isRealKey);
  const [activeLayer, setActiveLayer] = useState<'h3' | 'heatmap' | 'sat'>('h3');
  const [mapsError, setMapsError] = useState<string | null>(null);

  useEffect(() => {
    if (!isRealKey && import.meta.env.DEV) {
      console.warn(
        '[MapContainer] No Google Maps API key in import.meta.env.VITE_GOOGLE_MAPS_API_KEY. ' +
          'Showing simulation grid. Fix frontend/.env or root GOOGLE_MAPS_BROWSER_API_KEY (UTF-8 no BOM), then restart Vite.',
      );
    }
  }, []);

  const bounds = useMemo(() => {
    if (!allHexes || allHexes.length === 0) {
      return { minLat: 12.9, maxLat: 13.05, minLng: 77.5, maxLng: 77.7 };
    }
    const lats = allHexes.map((h) => h.lat);
    const lngs = allHexes.map((h) => h.lng);
    return {
      minLat: Math.min(...lats),
      maxLat: Math.max(...lats),
      minLng: Math.min(...lngs),
      maxLng: Math.max(...lngs),
    };
  }, [allHexes]);

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

  if (!allHexes || allHexes.length === 0) {
    return (
      <div className="w-full h-full bg-black flex items-center justify-center flex-col gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-brand-blue/30 border-t-brand-blue animate-spin" />
        <span className="text-[10px] font-mono uppercase tracking-widest text-apple-secondary animate-pulse">
          Synchronizing Sentinel Grids...
        </span>
      </div>
    );
  }

  // AdvancedMarker requires a mapId; DEMO_MAP_ID works for demos when Vector maps are allowed.
  const effectiveMapId = MAP_ID || 'DEMO_MAP_ID';

  return (
    <div className="relative w-full h-full min-h-[320px] bg-black flex flex-col overflow-hidden">
      <div className="absolute top-4 left-4 z-10 flex flex-wrap items-center gap-2">
        <div className="flex bg-apple-card/85 backdrop-blur-md rounded-full p-1 border border-apple-border shadow-lg animate-fade-in">
          {(['h3', 'heatmap', 'sat'] as const).map((layer) => (
            <button
              key={layer}
              type="button"
              onClick={() => setActiveLayer(layer)}
              className={`px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all ${
                activeLayer === layer
                  ? 'bg-brand-blue text-white'
                  : 'text-apple-secondary hover:text-white'
              }`}
            >
              {layer === 'h3' ? 'H3 Grid' : layer === 'heatmap' ? 'Plume Overlay' : 'Sensor Hotspots'}
            </button>
          ))}
        </div>

        <div className="bg-apple-card/85 backdrop-blur-md rounded-full px-3 py-1.5 border border-apple-border flex items-center gap-2 shadow-lg">
          <div
            className={`w-1.5 h-1.5 rounded-full ${isRealKey && showRealMap ? 'bg-brand-green' : 'bg-brand-orange animate-pulse'}`}
          />
          <span className="text-[10px] font-mono uppercase text-apple-secondary">
            {isRealKey && showRealMap ? 'Google Maps Live' : 'High-Fidelity Simulation'}
          </span>
          {isRealKey && (
            <button
              type="button"
              onClick={() => setShowRealMap((v) => !v)}
              className="text-[10px] text-brand-blue underline hover:text-blue-300 ml-1"
            >
              {showRealMap ? 'Sim' : 'Live map'}
            </button>
          )}
          {!isRealKey && (
            <button
              type="button"
              onClick={() =>
                setMapsError(
                  'No VITE_GOOGLE_MAPS_API_KEY loaded. Check frontend/.env and restart Vite (root .env must be UTF-8 without BOM).',
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
              {allHexes.map((hex) => {
                const color = hexColor(hex, viewMode);
                const label = formatLocationName(hex);
                const isSelected = selectedHex?.id === hex.id;
                return (
                  <AdvancedMarker
                    key={hex.id}
                    position={{ lat: hex.lat, lng: hex.lng }}
                    onClick={() => onSelectHex(hex)}
                  >
                    <div
                      className="cursor-pointer p-2 rounded-lg bg-black/80 border text-[10px] font-mono text-white shadow-lg transition-transform hover:scale-105"
                      style={{
                        borderColor: color,
                        boxShadow: isSelected ? `0 0 0 2px ${color}` : undefined,
                      }}
                    >
                      <span className="font-bold font-sans">{label}</span>
                      <div className="text-right font-bold mt-0.5" style={{ color }}>
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
        <div className="relative w-full h-full overflow-hidden bg-gradient-to-br from-apple-bg via-[#0c0c0e] to-apple-bg">
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#1c1c1e_1px,transparent_1px),linear-gradient(to_bottom,#1c1c1e_1px,transparent_1px)] bg-[size:40px_40px] opacity-40" />

          <svg
            className="absolute inset-0 w-full h-full pointer-events-none"
            viewBox="0 0 800 600"
            preserveAspectRatio="none"
          >
            {allHexes.map((hex) => {
              const { x, y } = project(hex.lat, hex.lng);
              const color = hexColor(hex, viewMode);
              const isSelected = selectedHex?.id === hex.id;
              const label = formatLocationName(hex);
              return (
                <g
                  key={hex.id}
                  className="cursor-pointer pointer-events-auto group/hex"
                  onClick={() => onSelectHex(hex)}
                >
                  <polygon
                    points={getHexPoints(x, y, 42)}
                    fill={isSelected ? `${color}40` : `${color}15`}
                    stroke={color}
                    strokeWidth={isSelected ? '2.5' : '1.2'}
                    className="transition-all duration-300 hover:fill-white/10"
                  />
                  <text
                    x={x}
                    y={y - 4}
                    fill="#fff"
                    fontSize="9"
                    fontFamily="Inter, sans-serif"
                    textAnchor="middle"
                    className="font-bold pointer-events-none select-none opacity-90"
                  >
                    {label.length > 14 ? `${label.slice(0, 12)}…` : label}
                  </text>
                  <text
                    x={x}
                    y={y + 8}
                    fill={color}
                    fontSize="8"
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
          </svg>

          <div className="absolute bottom-6 right-6 p-4 rounded-2xl bg-apple-card/80 border border-apple-border backdrop-blur-md text-right max-w-[200px]">
            <span className="text-[9px] font-mono uppercase text-apple-secondary block tracking-wider">
              {isRealKey ? 'Simulation mode' : 'No Maps API key'}
            </span>
            <span className="text-sm font-bold text-white font-mono">{allHexes.length}</span>
            <span className="text-[9px] text-apple-secondary block mt-1">grid targets</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default memo(MapContainer);
