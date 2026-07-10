import React, { useState } from 'react';
import { usePriorities, useStations } from '../api/client';
import { PriorityHex } from '../types';
import MapContainer from '../components/MapContainer';
import SourceIcon from '../components/SourceIcon';
import { Shield, AlertTriangle, Compass, Wind, ArrowRight, ChevronDown, CheckCircle, MapPin } from 'lucide-react';

export default function MapPage() {
  const { data: priorities = [], isLoading: loadingPriorities } = usePriorities();
  const { data: stations = [] } = useStations();
  const [selectedHex, setSelectedHex] = useState<PriorityHex | null>(null);
  const [dispatchedUnits, setDispatchedUnits] = useState<Record<string, boolean>>({});

  // Default to first hex (Okhla / Whitefield) for rendering side panels
  const activeHex = selectedHex || priorities[0] || null;

  const handleDispatch = (hexId: string) => {
    setDispatchedUnits(prev => ({ ...prev, [hexId]: true }));
    setTimeout(() => {
      alert(`Enforcement Unit Dispatched to Hexagon ${hexId}. Unit ID: EN-449`);
    }, 200);
  };

  return (
    <div className="w-full h-full flex flex-col bg-black">
      {/* Upper Section: Map Area + Float Overlay */}
      <div className="flex-1 relative min-h-[450px]">
        <MapContainer
          selectedHex={activeHex}
          onSelectHex={(hex) => setSelectedHex(hex)}
          allHexes={priorities}
          viewMode="aqi"
        />

        {/* Legend Overlay (Floating at bottom-left) */}
        <div className="absolute bottom-6 left-6 z-10 bg-apple-card/90 border border-apple-border backdrop-blur-md p-4 rounded-2xl max-w-[200px] shadow-2xl">
          <div className="text-[10px] font-mono uppercase text-apple-secondary tracking-widest mb-3">
            PM2.5 Levels (µg/m³)
          </div>
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs font-semibold">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#34C759] shadow-[0_0_6px_#34C759]" />
                <span className="font-mono text-white">0 - 50</span>
              </div>
              <span className="text-apple-secondary text-[10px] font-medium">Good</span>
            </div>
            <div className="flex items-center justify-between text-xs font-semibold">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#FFCC00] shadow-[0_0_6px_#FFCC00]" />
                <span className="font-mono text-white">51 - 100</span>
              </div>
              <span className="text-apple-secondary text-[10px] font-medium">Moderate</span>
            </div>
            <div className="flex items-center justify-between text-xs font-semibold">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-brand-orange shadow-[0_0_6px_#FF9F0A]" />
                <span className="font-mono text-white">101 - 250</span>
              </div>
              <span className="text-apple-secondary text-[10px] font-medium">Poor</span>
            </div>
            <div className="flex items-center justify-between text-xs font-semibold">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-brand-red shadow-[0_0_6px_#ff453a]" />
                <span className="font-mono text-white">251+</span>
              </div>
              <span className="text-apple-secondary text-[10px] font-medium">Severe</span>
            </div>
          </div>
        </div>

        {/* Floating Sidebar Detail Panel (Right side) */}
        {activeHex && (
          <div className="absolute right-6 top-6 bottom-6 w-80 bg-apple-modal/95 border border-apple-border backdrop-blur-xl rounded-2xl shadow-2xl flex flex-col overflow-hidden z-20">
            {/* Header */}
            <div className="p-5 border-b border-apple-border flex flex-col gap-1 bg-apple-card/30">
              <span className="text-[10px] font-mono uppercase text-apple-secondary tracking-widest flex items-center gap-1.5">
                <MapPin size={10} className="text-brand-blue" />
                Sector Grid: {activeHex.id}
              </span>
              <h2 className="text-lg font-bold text-white tracking-tight leading-snug mt-1">
                Local Plume Analysis
              </h2>
              <span className="text-xs text-apple-secondary font-sans leading-none block">
                {activeHex.name}
              </span>
            </div>

            {/* Readouts */}
            <div className="p-5 flex flex-col gap-6 flex-1 overflow-y-auto">
              {/* Giant AQI Circle */}
              <div className="flex items-end gap-3.5">
                <div className="text-5xl font-bold font-mono text-brand-orange select-none leading-none">
                  {activeHex.pm25}
                </div>
                <div className="flex flex-col pb-0.5">
                  <span className="text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 rounded-full bg-brand-orange/10 border border-brand-orange/30 text-brand-orange font-bold mb-1 w-fit">
                    {activeHex.pm25 > 250 ? 'Severe' : 'Poor'}
                  </span>
                  <span className="text-[10px] font-mono text-apple-secondary leading-none">
                    PM2.5 (µg/m³)
                  </span>
                </div>
              </div>

              <div className="h-px bg-apple-border/50" />

              {/* Source attribution bar */}
              <div className="flex flex-col gap-2">
                <div className="flex justify-between items-center text-[10px] font-mono uppercase text-apple-secondary">
                  <span>Source Attribution</span>
                  <span className="text-brand-blue flex items-center gap-1 bg-brand-blue/10 px-2 py-0.5 rounded-full font-bold">
                    WIND_WEIGHTED
                  </span>
                </div>

                {/* Multicolored bar */}
                <div className="w-full h-3 flex rounded-full overflow-hidden mt-1.5 bg-apple-border/50">
                  <div className="bg-[#A2845E] w-[45%]" title="Construction: 45%" />
                  <div className="bg-[#5AC8FA] w-[30%]" title="Traffic: 30%" />
                  <div className="bg-brand-orange w-[15%]" title="Industrial: 15%" />
                  <div className="bg-brand-red w-[10%]" title="Waste Burn: 10%" />
                </div>

                <div className="flex flex-wrap justify-between text-[10px] font-mono text-apple-secondary mt-1.5 gap-y-1">
                  <div className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#A2845E]" />
                    45% Const.
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#5AC8FA]" />
                    30% Traffic
                  </div>
                </div>
              </div>

              {/* Signature Wind compass gauge */}
              <div className="bg-apple-card border border-apple-border rounded-xl p-4 flex justify-between items-center">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[10px] font-mono uppercase text-apple-secondary block">
                    Local Wind Vector
                  </span>
                  <div className="text-xs font-semibold text-white mt-1">
                    Blowing towards East
                  </div>
                  <span className="text-[9px] font-mono text-apple-secondary mt-1">
                    Sensor array Alpha-2
                  </span>
                </div>

                {/* Wind Compass SVG */}
                <div className="relative w-16 h-16 flex items-center justify-center">
                  <svg className="absolute inset-0 w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" fill="none" r="44" stroke="#2C2C2E" strokeDasharray="3 3" strokeWidth="2" />
                    <circle cx="50" cy="50" fill="none" r="44" stroke="#FF9F0A" strokeWidth="3" strokeDasharray="120 280" strokeLinecap="round" />
                    {/* Compass needle pointing East */}
                    <polygon fill="#FF9F0A" points="50,14 46,36 54,36" transform="rotate(90, 50, 50)" />
                  </svg>
                  <div className="z-10 flex flex-col items-center">
                    <span className="text-[13px] font-mono font-bold text-white leading-none">12</span>
                    <span className="text-[8px] text-apple-secondary leading-none uppercase mt-0.5">km/h</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Action dispatch button */}
            <div className="p-5 border-t border-apple-border bg-apple-card/20">
              <button
                type="button"
                onClick={() => handleDispatch(activeHex.id)}
                disabled={dispatchedUnits[activeHex.id]}
                className={`w-full py-3 rounded-full text-xs font-bold uppercase tracking-wider transition-colors duration-200 flex items-center justify-center gap-2 shadow-lg ${
                  dispatchedUnits[activeHex.id]
                    ? 'bg-brand-green/20 text-brand-green border border-brand-green/30 cursor-not-allowed'
                    : 'bg-brand-blue hover:bg-blue-600 text-white shadow-brand-blue/15'
                }`}
              >
                <Shield size={14} />
                {dispatchedUnits[activeHex.id] ? 'Dispatch Complete' : 'Dispatch Inspection Unit'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Lower Section: Bottom Bento Grid Queue */}
      <section className="bg-black border-t border-apple-border p-6 sm:p-8">
        <div className="flex justify-between items-end mb-6">
          <div>
            <h2 className="text-md sm:text-lg font-bold text-white tracking-tight">
              Top Enforcement Priorities
            </h2>
            <p className="text-xs text-apple-secondary font-sans mt-0.5">
              AI-ranked targets based on current emissions and wind dispersal.
            </p>
          </div>
          <button className="text-xs font-semibold text-brand-blue hover:underline flex items-center gap-1 uppercase tracking-wider">
            View All Queue <ArrowRight size={12} />
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4">
          {priorities.map((p, idx) => {
            const isDispatched = dispatchedUnits[p.id];
            return (
              <div
                key={p.id}
                onClick={() => setSelectedHex(p)}
                className={`relative bg-apple-card border rounded-2xl p-5 flex flex-col justify-between overflow-hidden transition-all duration-300 cursor-pointer hover:bg-apple-modal/50 ${
                  activeHex?.id === p.id ? 'border-brand-blue/50 ring-1 ring-brand-blue/30 scale-[1.02]' : 'border-apple-border'
                }`}
              >
                {/* Visual indicator bar at top based on severity */}
                <div
                  className="absolute top-0 left-0 w-full h-1"
                  style={{ backgroundColor: p.priorityScore > 95 ? '#ff453a' : '#FF9F0A' }}
                />

                <div className="flex justify-between items-start mb-4 mt-1">
                  <span className="text-xs font-mono font-bold text-apple-secondary">#{String(idx + 1).padStart(2, '0')}</span>
                  <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-apple-modal border border-apple-border text-[9px] font-mono font-bold uppercase text-apple-secondary select-none">
                    <SourceIcon sourceType={p.sourceType} size={14} />
                    {p.sourceType}
                  </div>
                </div>

                <div className="flex flex-col gap-0.5">
                  <div className="text-xl font-bold font-mono text-white leading-none mb-1">
                    {p.pm25}
                    <span className="text-[10px] font-mono text-apple-secondary font-normal ml-1">µg/m³</span>
                  </div>
                  <div className="text-xs font-bold text-white truncate">{p.name}</div>
                </div>

                {/* Score bar */}
                <div className="mt-4">
                  <div className="w-full h-1 bg-apple-border/50 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-blue rounded-full"
                      style={{ width: `${(p.priorityScore / 100) * 100}%` }}
                    />
                  </div>
                  <div className="flex justify-between items-center text-[9px] font-mono text-apple-secondary mt-1.5">
                    <span>SCORE: {p.priorityScore}</span>
                    {isDispatched && <span className="text-brand-green uppercase font-bold">DISPATCHED</span>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
