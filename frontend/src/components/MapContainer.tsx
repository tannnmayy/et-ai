import React, { useState } from 'react';
import { APIProvider, Map, AdvancedMarker } from '@vis.gl/react-google-maps';
import { Shield, MapPin, Eye, Key, Layers, Compass, Wind } from 'lucide-react';
import { PriorityHex } from '../types';

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

// Custom dark styled map styles
const darkMapStyles = [
  { elementType: 'geometry', stylers: [{ color: '#000000' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#000000' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#74747a' }] },
  { featureType: 'administrative', elementType: 'geometry', stylers: [{ color: '#1c1c1e' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#1c1c1e' }] },
  { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#48484a' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0c0c0e' }] },
];

export default function MapContainer({
  selectedHex,
  onSelectHex,
  allHexes,
  viewMode,
}: MapContainerProps) {
  const [showRealMap, setShowRealMap] = useState(isRealKey);
  const [activeLayer, setActiveLayer] = useState<'h3' | 'heatmap' | 'sat'>('h3');

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

  // Set up projections for simulated SVG map based on coordinates of hexagons
  const lats = allHexes.map((h) => h.lat);
  const lngs = allHexes.map((h) => h.lng);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);

  const latRange = maxLat - minLat || 0.01;
  const lngRange = maxLng - minLng || 0.01;

  const project = (lat: number, lng: number) => {
    // Map coords into SVG viewbox: X from 120 to 680, Y from 100 to 500
    const x = 120 + ((lng - minLng) / lngRange) * 560;
    const y = 500 - ((lat - minLat) / latRange) * 400; // Invert Y coordinate
    return { x, y };
  };

  const getHexPoints = (cx: number, cy: number, r: number) => {
    const points = [];
    for (let i = 0; i < 6; i++) {
      const angle = (i * 60 * Math.PI) / 180;
      points.push(`${(cx + r * Math.cos(angle)).toFixed(1)},${(cy + r * Math.sin(angle)).toFixed(1)}`);
    }
    return points.join(' ');
  };

  return (
    <div className="relative w-full h-full bg-black flex flex-col overflow-hidden">
      {/* Top controls: simulation toggle vs real map */}
      <div className="absolute top-4 left-4 z-10 flex flex-wrap items-center gap-2">
        <div className="flex bg-apple-card/85 backdrop-blur-md rounded-full p-1 border border-apple-border shadow-lg animate-fade-in">
          <button
            type="button"
            onClick={() => setActiveLayer('h3')}
            className={`px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all ${
              activeLayer === 'h3' ? 'bg-brand-blue text-white' : 'text-apple-secondary hover:text-white'
            }`}
          >
            H3 Grid
          </button>
          <button
            type="button"
            onClick={() => setActiveLayer('heatmap')}
            className={`px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all ${
              activeLayer === 'heatmap' ? 'bg-brand-blue text-white' : 'text-apple-secondary hover:text-white'
            }`}
          >
            Plume Overlay
          </button>
          <button
            type="button"
            onClick={() => setActiveLayer('sat')}
            className={`px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all ${
              activeLayer === 'sat' ? 'bg-brand-blue text-white' : 'text-apple-secondary hover:text-white'
            }`}
          >
            Sensor Hotspots
          </button>
        </div>

        {/* API Key Status Toggle Pill */}
        <div className="bg-apple-card/85 backdrop-blur-md rounded-full px-3 py-1.5 border border-apple-border flex items-center gap-2 shadow-lg">
          <div className={`w-1.5 h-1.5 rounded-full ${isRealKey ? 'bg-brand-green' : 'bg-brand-orange animate-pulse'}`} />
          <span className="text-[10px] font-mono uppercase text-apple-secondary">
            {isRealKey ? 'Google Maps Live' : 'High-Fidelity Simulation'}
          </span>
          {!isRealKey && (
            <button
              onClick={() => setShowRealMap(!showRealMap)}
              className="text-[10px] text-brand-blue underline hover:text-blue-300 ml-1 flex items-center gap-1"
            >
              <Key size={10} /> Details
            </button>
          )}
        </div>
      </div>

      {/* Actual Map Render Selection */}
      {showRealMap && isRealKey ? (
        <APIProvider apiKey={API_KEY} version="weekly">
          <div className="w-full h-full">
            <Map
              defaultCenter={{ lat: (minLat + maxLat) / 2 || 12.9716, lng: (minLng + maxLng) / 2 || 77.5946 }}
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
                }
              } as any)}
            >
              {allHexes.map((hex) => {
                const color =
                  hex.priorityScore > 90
                    ? '#ff453a'
                    : hex.priorityScore > 70
                    ? '#FF9F0A'
                    : '#0A84FF';
                return (
                  <AdvancedMarker
                    key={hex.id}
                    position={{ lat: hex.lat, lng: hex.lng }}
                    onClick={() => onSelectHex(hex)}
                  >
                    <div
                      className="cursor-pointer p-2 rounded-lg bg-black/80 border text-[10px] font-mono text-white shadow-lg transition-transform hover:scale-105"
                      style={{ borderColor: color }}
                    >
                      <span className="font-bold">{hex.name}</span>
                      <div className="text-right font-bold mt-0.5" style={{ color }}>
                        {hex.pm25} µg/m³
                      </div>
                    </div>
                  </AdvancedMarker>
                );
              })}
            </Map>
          </div>
        </APIProvider>
      ) : (
        /* fall back to custom premium simulation map */
        <div className="relative w-full h-full overflow-hidden bg-gradient-to-br from-apple-bg via-[#0c0c0e] to-apple-bg">
          {/* Tactical map background grids */}
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#1c1c1e_1px,transparent_1px),linear-gradient(to_bottom,#1c1c1e_1px,transparent_1px)] bg-[size:40px_40px] opacity-40" />

          {/* Simulated H3 Grid representation */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 800 600" preserveAspectRatio="none">
            {/* Hexagon overlays for simulation */}
            {allHexes.map((hex) => {
              const { x, y } = project(hex.lat, hex.lng);
              const color =
                hex.priorityScore > 90
                  ? '#ff453a'
                  : hex.priorityScore > 70
                  ? '#FF9F0A'
                  : '#0A84FF';
              const isSelected = selectedHex?.id === hex.id;
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
                    fontFamily="monospace"
                    textAnchor="middle"
                    className="font-bold pointer-events-none select-none opacity-90"
                  >
                    {hex.name}
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
                    {hex.pm25} µg/m³
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Compass / wind flow vector animations in background */}
          <div className="absolute bottom-6 right-6 p-4 rounded-2xl bg-apple-card/80 border border-apple-border backdrop-blur-md text-right max-w-[180px]">
            <span className="text-[9px] font-mono uppercase text-apple-secondary block tracking-wider">
              Anemometer Vector
            </span>
            <div className="text-xs font-semibold mt-1 text-white flex items-center justify-end gap-1.5">
              <Compass size={12} className="text-brand-orange animate-spin" style={{ animationDuration: '8s' }} />
              12.4 km/h ESE
            </div>
            <div className="text-[9px] font-mono text-apple-secondary mt-1">
              Plume Center Dynamics
            </div>
          </div>

          {/* Informational warning if real map can't load */}
          {!isRealKey && showRealMap && (
            <div className="absolute inset-0 bg-black/90 flex items-center justify-center p-8 z-30">
              <div className="bg-apple-card p-6 rounded-2xl border border-apple-border max-w-md shadow-2xl">
                <div className="w-12 h-12 rounded-full bg-brand-orange/10 border border-brand-orange/30 text-brand-orange flex items-center justify-center mb-4">
                  <Key size={20} />
                </div>
                <h3 className="text-md font-bold text-white mb-2">Google Maps Key Needed</h3>
                <p className="text-xs text-apple-secondary leading-relaxed mb-4">
                  To load live interactive vector grids, register a Google Maps API Key and save it as an environment variable.
                </p>
                <div className="bg-black/40 p-3 rounded-lg border border-apple-border/50 text-[10px] font-mono text-apple-secondary leading-normal space-y-1 mb-4">
                  <div>1. Get key from Google Cloud Console</div>
                  <div>2. Go to Settings ⚙️ (top-right corner) → Secrets</div>
                  <div>3. Add <span className="text-brand-blue">GOOGLE_MAPS_PLATFORM_KEY</span></div>
                </div>
                <button
                  onClick={() => setShowRealMap(false)}
                  className="w-full py-2 bg-brand-blue hover:bg-blue-600 text-white font-bold text-xs rounded-lg transition-colors uppercase tracking-wider"
                >
                  Return to Simulated Vector Grid
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
