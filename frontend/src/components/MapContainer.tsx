import React, { memo, useCallback, useMemo, useState } from 'react';
import { APIProvider, Map, AdvancedMarker } from '@vis.gl/react-google-maps';
import { Key } from 'lucide-react';
import { PriorityHex } from '../types';
import { actionTierStyles, formatLocationName } from '../services/enforcementUtils';

interface MapContainerProps {
  selectedHex: PriorityHex | null;
  onSelectHex: (hex: PriorityHex) => void;
  allHexes: PriorityHex[];
  viewMode: 'aqi' | 'enforcement';
}

const API_KEY =
  (import.meta as any).env?.VITE_GOOGLE_MAPS_API_KEY ||
  (import.meta as any).env?.VITE_GOOGLE_MAPS_PLATFORM_KEY ||
  '';

const isRealKey = Boolean(API_KEY) && API_KEY !== 'YOUR_API_KEY' && !API_KEY.includes('MY_GEMINI');

const darkMapStyles = [
  { elementType: 'geometry', stylers: [{ color: '#000000' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#000000' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#74747a' }] },
  { featureType: 'administrative', elementType: 'geometry', stylers: [{ color: '#1c1c1e' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#1c1c1e' }] },
  { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#48484a' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0c0c0e' }] },
];

function MapContainer({
  selectedHex,
  onSelectHex,
  allHexes,
  viewMode,
}: MapContainerProps) {
  const [showRealMap, setShowRealMap] = useState(isRealKey);
  const [activeLayer, setActiveLayer] = useState<'h3' | 'heatmap' | 'sat'>('h3');

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

  return (
    <div className="relative w-full h-full bg-black flex flex-col overflow-hidden">
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
            className={`w-1.5 h-1.5 rounded-full ${isRealKey ? 'bg-brand-green' : 'bg-brand-orange animate-pulse'}`}
          />
          <span className="text-[10px] font-mono uppercase text-apple-secondary">
            {isRealKey ? 'Google Maps Live' : 'High-Fidelity Simulation'}
          </span>
          {!isRealKey && (
            <button
              type="button"
              onClick={() => setShowRealMap(!showRealMap)}
              className="text-[10px] text-brand-blue underline hover:text-blue-300 ml-1 flex items-center gap-1"
            >
              <Key size={10} /> Details
            </button>
          )}
        </div>
      </div>

      {showRealMap && isRealKey ? (
        <APIProvider apiKey={API_KEY} version="weekly">
          <div className="w-full h-full">
            <Map
              defaultCenter={mapCenter}
              defaultZoom={12}
              mapId="DEMO_MAP_ID"
              gestureHandling="cooperative"
              internalUsageAttributionIds={['gmp_mcp_codeassist_v1_aistudio']}
              style={{ width: '100%', height: '100%' }}
              {...({
                options: {
                  styles: darkMapStyles,
                  disableDefaultUI: true,
                  zoomControl: true,
                },
              } as any)}
            >
              {allHexes.map((hex) => {
                const pm = hex.pm25;
                const color =
                  viewMode === 'aqi'
                    ? pm <= 50
                      ? '#34C759'
                      : pm <= 100
                        ? '#FFCC00'
                        : pm <= 250
                          ? '#FF9F0A'
                          : '#ff453a'
                    : actionTierStyles(hex.actionTier || 'MONITOR').mapColor;
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
              const pm = hex.pm25;
              const color =
                viewMode === 'aqi'
                  ? pm <= 50
                    ? '#34C759'
                    : pm <= 100
                      ? '#FFCC00'
                      : pm <= 250
                        ? '#FF9F0A'
                        : '#ff453a'
                  : actionTierStyles(hex.actionTier || 'MONITOR').mapColor;
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

          <div className="absolute bottom-6 right-6 p-4 rounded-2xl bg-apple-card/80 border border-apple-border backdrop-blur-md text-right max-w-[180px]">
            <span className="text-[9px] font-mono uppercase text-apple-secondary block tracking-wider">
              Grid targets
            </span>
            <span className="text-sm font-bold text-white font-mono">{allHexes.length}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function mapPropsEqual(prev: MapContainerProps, next: MapContainerProps): boolean {
  if (prev.viewMode !== next.viewMode) return false;
  if (prev.selectedHex?.id !== next.selectedHex?.id) return false;
  if (prev.onSelectHex !== next.onSelectHex) return false;
  if (prev.allHexes === next.allHexes) return true;
  if (prev.allHexes.length !== next.allHexes.length) return false;
  // Cheap id-sequence compare — avoids deep equality on every filter keystroke
  for (let i = 0; i < prev.allHexes.length; i++) {
    if (prev.allHexes[i].id !== next.allHexes[i].id) return false;
    if (prev.allHexes[i].score10 !== next.allHexes[i].score10) return false;
    if (prev.allHexes[i].actionTier !== next.allHexes[i].actionTier) return false;
  }
  return true;
}

export default memo(MapContainer, mapPropsEqual);
