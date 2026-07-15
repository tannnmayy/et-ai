import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCityExtremes, usePriorities, useStations } from '../api/client';
import { PriorityHex } from '../types';
import MapContainer from '../components/MapContainer';
import SourceIcon from '../components/SourceIcon';
import { formatLocationName } from '../services/enforcementUtils';
import { Shield, AlertTriangle, ArrowRight, MapPin, ChevronDown, BarChart3 } from 'lucide-react';

/** Map view mode: cleanest-only, both, or most-polluted with selectable depth. */
type ExtremeMode = 'best' | 'both' | 'worst';

/** How many most-polluted hexes to show (client-side slice of fetched top-100). */
type PollutedDepth = 15 | 30 | 50 | 100;

const POLLUTED_OPTIONS: { value: PollutedDepth; label: string }[] = [
  { value: 15, label: 'Top 15 Most Polluted' },
  { value: 30, label: 'Top 30 Most Polluted' },
  { value: 50, label: 'Top 50 Most Polluted' },
  { value: 100, label: 'Show All Polluted (top 100)' },
];

const CLEANEST_COUNT = 15;

export default function MapPage() {
  const navigate = useNavigate();
  const { data: extremes, isError: extremesError, isLoading: extremesLoading } = useCityExtremes();
  const { data: priorities = [] } = usePriorities();
  const { isError: stationsError, isLoading: stationsLoading } = useStations();
  const [selectedHex, setSelectedHex] = useState<PriorityHex | null>(null);
  const [dispatchedUnits, setDispatchedUnits] = useState<Record<string, boolean>>({});
  const [extremeMode, setExtremeMode] = useState<ExtremeMode>('both');
  /** Demo-friendly default: Top 30 most polluted when viewing polluted set */
  const [pollutedDepth, setPollutedDepth] = useState<PollutedDepth>(30);

  if (extremesLoading || stationsLoading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-brand-blue border-t-transparent rounded-full animate-spin" />
          <span className="text-xs font-mono uppercase tracking-widest text-apple-secondary">Loading sensor data...</span>
        </div>
      </div>
    );
  }

  if (extremesError && stationsError) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4 max-w-md text-center px-6">
          <div className="w-12 h-12 rounded-full bg-brand-red/10 border border-brand-red/20 flex items-center justify-center text-brand-red">
            <AlertTriangle size={24} />
          </div>
          <h2 className="text-lg font-bold text-white">Data Unavailable</h2>
          <p className="text-sm text-apple-secondary leading-relaxed">
            Unable to load extremes data from the API.
            Please check that the backend is running and try again.
          </p>
        </div>
      </div>
    );
  }

  const cleanestPool = extremes?.best ?? [];
  const pollutedPool = extremes?.worst ?? [];
  const pollutedAvailable = pollutedPool.length;
  const cleanestShown = cleanestPool.slice(0, CLEANEST_COUNT);
  const pollutedShown = pollutedPool.slice(0, Math.min(pollutedDepth, pollutedAvailable));

  const allHexes: PriorityHex[] =
    extremeMode === 'best'
      ? cleanestShown
      : extremeMode === 'worst'
        ? pollutedShown
        : [...cleanestShown, ...pollutedShown];

  const compactLabels =
    extremeMode === 'worst'
      ? pollutedDepth > 15
      : extremeMode === 'both'
        ? pollutedDepth > 15
        : false;

  const activeHex = selectedHex || allHexes[0] || null;
  const pollutedLabel =
    POLLUTED_OPTIONS.find((o) => o.value === pollutedDepth)?.label ??
    `Top ${pollutedDepth} Most Polluted`;

  const handleDispatch = (hex: PriorityHex) => {
    setDispatchedUnits((prev) => ({ ...prev, [hex.id]: true }));
    const qs = new URLSearchParams({
      target: hex.name || hex.id,
      hex: hex.id,
      source: String(hex.sourceType || 'mixed'),
      score: String(hex.priorityScore ?? hex.pm25 ?? '—'),
      action: hex.explanation?.text || 'Inspect site for dust control compliance and document evidence.',
    });
    navigate(`/dispatch?${qs.toString()}`);
  };

  const topFive = (priorities || []).slice(0, 5);

  return (
    <div className="w-full h-full flex flex-col bg-black overflow-y-auto">
      {/* Upper Section: Map Area + Float Overlay */}
      <div className="flex-1 relative min-h-[520px] shrink-0">
        <MapContainer
          selectedHex={activeHex}
          onSelectHex={(hex) => setSelectedHex(hex)}
          allHexes={allHexes}
          viewMode="aqi"
          compactLabels={compactLabels}
        />

        {/* Legend Overlay (Floating at bottom-left) */}
        <div className="absolute bottom-6 left-6 z-10 bg-apple-card/90 border border-apple-border backdrop-blur-md p-4 rounded-2xl max-w-[220px] shadow-2xl">
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

          {/* Honesty note about data coverage */}
          {extremes && (
            <div className="mt-3 pt-3 border-t border-apple-border/40">
              <div className="text-[8px] font-mono uppercase tracking-wider text-apple-secondary/60 leading-relaxed">
                Ranked among {extremes.totalWithData} hexagons with live station coverage out of {extremes.totalInGrid} total
              </div>
            </div>
          )}
        </div>

        {/* Map layer control: cleanest / both / polluted depth dropdown */}
        <div className="absolute top-4 right-4 z-10 flex flex-col items-end gap-2 max-w-[min(100vw-2rem,280px)]">
          <div className="flex flex-wrap justify-end bg-apple-card/90 backdrop-blur-md rounded-full p-1 border border-apple-border shadow-lg">
            <button
              type="button"
              onClick={() => setExtremeMode('best')}
              className={`px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all min-h-[36px] ${
                extremeMode === 'best'
                  ? 'bg-brand-green text-white'
                  : 'text-apple-secondary hover:text-white'
              }`}
            >
              Top {CLEANEST_COUNT} Cleanest
            </button>
            <button
              type="button"
              onClick={() => setExtremeMode('both')}
              className={`px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all min-h-[36px] ${
                extremeMode === 'both'
                  ? 'bg-brand-blue text-white'
                  : 'text-apple-secondary hover:text-white'
              }`}
            >
              Both
            </button>
            <button
              type="button"
              onClick={() => setExtremeMode('worst')}
              className={`px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all min-h-[36px] ${
                extremeMode === 'worst'
                  ? 'bg-brand-red text-white'
                  : 'text-apple-secondary hover:text-white'
              }`}
            >
              Most Polluted
            </button>
          </div>

          {(extremeMode === 'worst' || extremeMode === 'both') && (
            <div className="flex flex-col items-end gap-1 w-full">
              <label className="flex items-center gap-2 rounded-full px-3 py-2 bg-apple-card/90 backdrop-blur-md border border-apple-border shadow-lg w-full max-w-[280px]">
                <span className="text-[9px] font-bold uppercase tracking-wider text-apple-secondary shrink-0">
                  Depth
                </span>
                <select
                  value={pollutedDepth}
                  onChange={(e) => {
                    setPollutedDepth(Number(e.target.value) as PollutedDepth);
                    setExtremeMode((m) => (m === 'best' ? 'worst' : m));
                  }}
                  className="flex-1 min-w-0 bg-transparent text-[11px] font-semibold text-white outline-none cursor-pointer"
                  aria-label="Number of most polluted hexes to show"
                >
                  {POLLUTED_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value} className="bg-apple-card text-white">
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="text-[9px] font-mono text-apple-secondary/80 bg-black/50 backdrop-blur-sm px-2.5 py-1 rounded-full border border-white/10">
                {extremeMode === 'both' ? (
                  <>
                    Showing {cleanestShown.length} cleanest + {pollutedShown.length} polluted
                    {pollutedDepth >= 100 || pollutedShown.length >= pollutedAvailable
                      ? pollutedAvailable >= 100
                        ? ' · polluted capped at 100'
                        : ''
                      : ` · of ${pollutedAvailable} loaded`}
                  </>
                ) : (
                  <>
                    Showing {pollutedShown.length}
                    {pollutedAvailable > pollutedShown.length
                      ? ` of ${pollutedAvailable} polluted hexes`
                      : ' polluted hexes'}
                    {pollutedDepth >= 100 ? ' (top 100 cap)' : ''}
                  </>
                )}
              </div>
              {extremeMode === 'worst' && (
                <div className="text-[9px] font-bold uppercase tracking-wider text-brand-red/90 px-1">
                  {pollutedLabel}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Floating Sidebar Detail Panel (Right side) */}
        {activeHex && (
          <div className="absolute right-6 top-24 bottom-6 w-80 bg-apple-modal/95 border border-apple-border backdrop-blur-xl rounded-2xl shadow-2xl flex flex-col overflow-hidden z-20">
            {/* Header */}
            <div className="p-5 border-b border-apple-border flex flex-col gap-1 bg-apple-card/30">
              <span className="text-[10px] font-mono uppercase text-apple-secondary tracking-widest flex items-center gap-1.5">
                <MapPin size={10} className="text-brand-blue" />
                {formatLocationName(activeHex)}
              </span>
              <h2 className="text-lg font-bold text-white tracking-tight leading-snug mt-1">
                Local Plume Analysis
              </h2>
              <span
                className="text-xs text-apple-secondary font-sans leading-none block"
                title={activeHex.id}
              >
                {formatLocationName(activeHex)}
              </span>
            </div>

            {/* Readouts */}
            <div className="p-5 flex flex-col gap-6 flex-1 overflow-y-auto">
              {/* Giant AQI Circle */}
              <div className="flex items-end gap-3.5">
                <div className={`text-5xl font-bold font-mono select-none leading-none ${
                  activeHex.pm25 <= 50 ? 'text-[#34C759]' : activeHex.pm25 <= 100 ? 'text-[#FFCC00]' : activeHex.pm25 <= 250 ? 'text-brand-orange' : 'text-brand-red'
                }`}>
                  {activeHex.pm25}
                </div>
                <div className="flex flex-col pb-0.5">
                  <span className={`text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 rounded-full border font-bold mb-1 w-fit ${
                    activeHex.pm25 <= 50 ? 'bg-[#34C759]/10 border-[#34C759]/30 text-[#34C759]' : activeHex.pm25 <= 100 ? 'bg-[#FFCC00]/10 border-[#FFCC00]/30 text-[#FFCC00]' : activeHex.pm25 <= 250 ? 'bg-brand-orange/10 border-brand-orange/30 text-brand-orange' : 'bg-brand-red/10 border-brand-red/30 text-brand-red'
                  }`}>
                    {activeHex.pm25 <= 50 ? 'Good' : activeHex.pm25 <= 100 ? 'Moderate' : activeHex.pm25 <= 250 ? 'Poor' : 'Severe'}
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
                  {activeHex.sourceAttribution && (() => {
                    const total = activeHex.sourceAttribution.traffic + activeHex.sourceAttribution.industrial + activeHex.sourceAttribution.construction + activeHex.sourceAttribution.burning;
                    return total > 0 ? (
                      <span className="text-brand-blue flex items-center gap-1 bg-brand-blue/10 px-2 py-0.5 rounded-full font-bold">
                        WIND_WEIGHTED
                      </span>
                    ) : (
                      <span className="text-apple-secondary flex items-center gap-1 bg-apple-border/20 px-2 py-0.5 rounded-full font-bold">
                        UNAVAILABLE
                      </span>
                    );
                  })()}
                </div>

                {(() => {
                  const attr = activeHex.sourceAttribution;
                  const total = attr ? (attr.traffic + attr.industrial + attr.construction + attr.burning) : 0;
                  if (!attr || total === 0) {
                    return (
                      <div className="w-full h-12 flex items-center justify-center text-[10px] font-mono text-apple-secondary bg-apple-border/10 rounded-lg">
                        <span className="flex items-center gap-1.5">
                          <AlertTriangle size={11} />
                          No attribution data
                        </span>
                      </div>
                    );
                  }

                  const pct = (v: number) => `${Math.round(v * 100)}%`;
                  const pctVal = (v: number) => Math.round(v * 100);
                  const segments = [
                    { key: 'construction', label: 'Const.', color: '#A2845E', value: pctVal(attr.construction) },
                    { key: 'traffic', label: 'Traffic', color: '#5AC8FA', value: pctVal(attr.traffic) },
                    { key: 'industrial', label: 'Industrial', color: '#FF9F0A', value: pctVal(attr.industrial) },
                    { key: 'burning', label: 'Waste Burn', color: '#FF453A', value: pctVal(attr.burning) },
                  ].filter(s => s.value > 0);

                  if (segments.length === 0) {
                    return (
                      <div className="w-full h-12 flex items-center justify-center text-[10px] font-mono text-apple-secondary bg-apple-border/10 rounded-lg">
                        <span className="flex items-center gap-1.5">
                          <AlertTriangle size={11} />
                          No attribution data
                        </span>
                      </div>
                    );
                  }

                  return (
                    <>
                      <div className="w-full h-3 flex rounded-full overflow-hidden mt-1.5 bg-apple-border/50">
                        {segments.map(s => (
                          <div
                            key={s.key}
                            className="transition-all duration-500"
                            style={{ backgroundColor: s.color, width: `${s.value}%` }}
                            title={`${s.label}: ${s.value}%`}
                          />
                        ))}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono text-apple-secondary mt-1.5">
                        {segments.map(s => (
                          <div key={s.key} className="flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: s.color }} />
                            {s.value}% {s.label}
                          </div>
                        ))}
                      </div>
                    </>
                  );
                })()}
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
            <div className="p-5 border-t border-apple-border bg-apple-card/20 space-y-2">
              <button
                type="button"
                onClick={() => handleDispatch(activeHex)}
                className="w-full min-h-[44px] py-3 rounded-full text-xs font-bold uppercase tracking-wider transition-colors duration-200 flex items-center justify-center gap-2 shadow-lg bg-brand-blue hover:bg-blue-600 text-white shadow-brand-blue/15"
              >
                <Shield size={14} />
                {dispatchedUnits[activeHex.id] ? 'Open Dispatch Sheet' : 'Dispatch Inspection Unit'}
              </button>
            </div>
          </div>
        )}

        {/* Scroll hint */}
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-1 pointer-events-none">
          <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-white/70 bg-black/50 backdrop-blur-md px-3 py-1 rounded-full border border-white/10">
            Scroll for hotspots
          </span>
          <ChevronDown size={16} className="text-white/60 animate-bounce" />
        </div>
      </div>

      {/* Lower Section: Top 5 Actionable Hotspots + Insights CTA */}
      <section className="bg-black border-t border-white/10 p-6 sm:p-8 pb-12">
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-4 mb-6">
          <div>
            <h2 className="text-md sm:text-lg font-bold text-white tracking-tight">
              Top 5 Actionable Hotspots
            </h2>
            <p className="text-xs text-apple-secondary font-sans mt-0.5">
              AI-ranked targets based on current emissions and wind dispersal.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => navigate('/enforcement')}
              className="min-h-[44px] text-xs font-semibold text-brand-blue hover:underline flex items-center gap-1 uppercase tracking-wider px-2"
            >
              View All Queue <ArrowRight size={12} />
            </button>
            <button
              type="button"
              onClick={() => navigate('/insights')}
              className="min-h-[44px] inline-flex items-center gap-2 px-5 rounded-full bg-brand-blue text-white text-xs font-bold uppercase tracking-wider shadow-lg shadow-brand-blue/20 hover:bg-brand-blue/90 transition-colors"
            >
              <BarChart3 size={14} />
              View City Insights
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4">
          {topFive.map((p, idx) => {
            const isDispatched = dispatchedUnits[p.id];
            return (
              <div
                key={p.id}
                onClick={() => setSelectedHex(p)}
                className={`relative glass-panel glass-card-hover border rounded-3xl p-5 flex flex-col justify-between overflow-hidden transition-all duration-300 cursor-pointer ${
                  activeHex?.id === p.id ? 'border-brand-blue/50 ring-1 ring-brand-blue/30 scale-[1.02]' : 'border-white/10'
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

                {/* Explanation snippet */}
                {p.explanation && (
                  <div className="mt-3 pt-3 border-t border-apple-border/30">
                    <p className="text-[9px] text-apple-secondary leading-relaxed line-clamp-2">
                      {p.explanation.text}
                    </p>
                    <div className="flex items-center gap-1 mt-1">
                      <Shield size={9} className="text-brand-blue/60" />
                      <span className="text-[8px] font-mono text-brand-blue/60 uppercase">
                        Guidance
                      </span>
                      {p.explanation.generated_by === 'llm' && (
                        <span className="text-[7px] font-mono text-brand-blue/40 ml-auto">AI</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
