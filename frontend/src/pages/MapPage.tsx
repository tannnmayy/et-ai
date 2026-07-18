import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCityExtremes, usePriorities, useStations } from '../api/client';
import { PriorityHex } from '../types';
import MapContainer from '../components/MapContainer';
import SourceIcon from '../components/SourceIcon';
import { formatLocationName } from '../services/enforcementUtils';
import type { ExtremesRankingMode } from '../services/geospatialService';
import { useMapCopilotContext } from '../context/MapCopilotContext';
import {
  Shield,
  AlertTriangle,
  ArrowRight,
  MapPin,
  ChevronDown,
  BarChart3,
  Bot,
  Sparkles,
  X,
  Info,
} from 'lucide-react';

/** Map view mode: cleanest-only, both, or most-polluted with selectable depth. */
type ExtremeMode = 'best' | 'both' | 'worst';

/** Visual layer: PM2.5 AQI vs attribution confidence reliability. */
type MapLayerMode = 'aqi' | 'confidence';

/** How many most-polluted hexes to show (client-side slice of fetched top-100). */
type PollutedDepth = 15 | 30 | 50 | 100;

const POLLUTED_OPTIONS: { value: PollutedDepth; label: string }[] = [
  { value: 15, label: 'Top 15' },
  { value: 30, label: 'Top 30' },
  { value: 50, label: 'Top 50' },
  { value: 100, label: 'Top 100' },
];

const CLEANEST_COUNT = 15;

export default function MapPage() {
  const navigate = useNavigate();
  const {
    setMapContext,
    mapActions,
    mapActionsUpdatedAt,
    clearMapActions,
    station_id: mapCtxStation,
    h3_cell: mapCtxH3,
    label: mapCtxLabel,
  } = useMapCopilotContext();
  /**
   * Dual mode for worst list:
   * - global: absolute highest fused PM (scientific)
   * - local_peaks: worst hexes per station catchment (operational)
   * Default global preserves legacy "Top N most polluted" behaviour.
   */
  const [rankingMode, setRankingMode] = useState<ExtremesRankingMode>('global');
  const {
    data: extremes,
    isError: extremesError,
    isLoading: extremesLoading,
    isFetching: extremesFetching,
  } = useCityExtremes(rankingMode);
  const { data: priorities = [] } = usePriorities();
  const {
    data: stations = [],
    isError: stationsError,
    isLoading: stationsLoading,
  } = useStations();
  const [selectedHex, setSelectedHex] = useState<PriorityHex | null>(null);
  const [dispatchedUnits, setDispatchedUnits] = useState<Record<string, boolean>>({});
  const [extremeMode, setExtremeMode] = useState<ExtremeMode>('both');
  /** Demo-friendly default: Top 30 most polluted when viewing polluted set */
  const [pollutedDepth, setPollutedDepth] = useState<PollutedDepth>(30);
  const [mapLayer, setMapLayer] = useState<MapLayerMode>('aqi');

  const cleanestPool = extremes?.best ?? [];
  const pollutedPool = extremes?.worst ?? [];
  const pollutedAvailable = pollutedPool.length;
  const cleanestShown = cleanestPool.slice(0, CLEANEST_COUNT);
  const pollutedShown = pollutedPool.slice(0, Math.min(pollutedDepth, pollutedAvailable));

  const baseHexes: PriorityHex[] =
    extremeMode === 'best'
      ? cleanestShown
      : extremeMode === 'worst'
        ? pollutedShown
        : [...cleanestShown, ...pollutedShown];

  // Merge priority hexes so Copilot-highlighted cells (often top enforcement) are on the map
  const allHexes = useMemo(() => {
    const byId = new Map<string, PriorityHex>();
    for (const h of baseHexes) byId.set(h.id, h);
    for (const p of priorities || []) {
      if (p?.id && !byId.has(p.id)) byId.set(p.id, p);
    }
    return Array.from(byId.values());
  }, [baseHexes, priorities]);

  /**
   * Full pool of real fused-PM hexes for nearby-station samples.
   * Includes cleanest + polluted extremes + priorities so each sensor can find ≥5 neighbours.
   */
  const samplePool = useMemo(() => {
    const byId = new Map<string, PriorityHex>();
    for (const h of cleanestPool) if (h?.id) byId.set(h.id, h);
    for (const h of pollutedPool) if (h?.id) byId.set(h.id, h);
    for (const p of priorities || []) if (p?.id) byId.set(p.id, p);
    return Array.from(byId.values());
  }, [cleanestPool, pollutedPool, priorities]);

  const highlightedHexIds = useMemo(
    () => mapActions?.highlight_h3_cells || [],
    [mapActions?.highlight_h3_cells],
  );

  const focusCenter = useMemo(() => {
    const f = mapActions?.focus_on;
    if (f?.lat != null && f?.lng != null) {
      return { lat: Number(f.lat), lng: Number(f.lng) };
    }
    const cell = f?.h3_cell || highlightedHexIds[0];
    if (cell) {
      const match = allHexes.find((h) => h.id === cell);
      if (match) return { lat: match.lat, lng: match.lng };
    }
    return null;
  }, [mapActions?.focus_on, highlightedHexIds, allHexes]);

  // When Copilot publishes new map_actions, select / focus the primary hex
  useEffect(() => {
    if (!mapActionsUpdatedAt || !mapActions) return;
    const focusId =
      mapActions.focus_on?.h3_cell || mapActions.highlight_h3_cells?.[0] || null;
    if (!focusId) return;
    const match =
      allHexes.find((h) => h.id === focusId) ||
      (priorities || []).find((h) => h.id === focusId);
    if (match) {
      setSelectedHex(match);
      setExtremeMode((m) => (m === 'best' ? 'both' : m));
    }
  }, [mapActionsUpdatedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  const compactLabels =
    extremeMode === 'worst'
      ? pollutedDepth > 15
      : extremeMode === 'both'
        ? pollutedDepth > 15
        : false;

  const activeHex = selectedHex || allHexes[0] || null;
  const hasMapCtx = Boolean(mapCtxStation || mapCtxH3);
  const hasCopilotHighlights = highlightedHexIds.length > 0;

  // Progressive paint: never full-black when we already have stations or any hexes.
  // Mode switches (Global ↔ Local Peaks) use keepPreviousData so extremes stays painted.
  const stationsReady = !stationsLoading && stations.length > 0;
  const extremesReady = Boolean(extremes?.best || extremes?.worst);
  const hasAnyHexes = allHexes.length > 0;
  // Only block the whole page on first cold load with nothing to show
  const stillBootstrapping =
    !hasAnyHexes &&
    !stationsReady &&
    (stationsLoading || extremesLoading) &&
    !extremesError &&
    !stationsError;

  // Mode switch / refetch: keep map painted; show a chip, never a black full-page wipe
  const rankingsLoading = Boolean(extremesFetching || (extremesLoading && !extremesReady));
  const modeSwitchPending = Boolean(
    extremesFetching && extremes && extremes.mode !== rankingMode,
  );

  /** Polluted hexes shown under Local Peaks mode get a distinct Peak badge on the map.
   *  MUST stay above any early return (Rules of Hooks). */
  const localPeakHexIds = useMemo(() => {
    if (rankingMode !== 'local_peaks') return [] as string[];
    if (extremeMode === 'best') return [] as string[];
    return pollutedShown.map((h) => h.id).filter(Boolean);
  }, [rankingMode, extremeMode, pollutedShown]);

  const activeIsLocalPeak = Boolean(
    activeHex && localPeakHexIds.includes(activeHex.id),
  );

  const topFive = (priorities || []).slice(0, 5);

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

  /** One-way Map → Copilot: stash hex (and optional nearest station) then open Copilot. */
  const handleAskCopilot = (hex: PriorityHex) => {
    setMapContext({
      h3_cell: hex.id,
      station_id: undefined,
      label: formatLocationName(hex) || hex.name || hex.id,
    });
    const qs = new URLSearchParams({
      h3_cell: hex.id,
      label: formatLocationName(hex) || hex.name || hex.id,
    });
    navigate(`/copilot?${qs.toString()}`);
  };

  if (stillBootstrapping) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-brand-blue border-t-transparent rounded-full animate-spin" />
          <span className="text-xs font-mono uppercase tracking-widest text-apple-secondary">
            Loading map data…
          </span>
          <span className="text-[10px] text-apple-secondary/70 max-w-xs text-center">
            Prefetched from Landing when available — first open after a short wait is much faster.
          </span>
        </div>
      </div>
    );
  }

  if (extremesError && stationsError && !hasAnyHexes && !stationsReady) {
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

  return (
    <div className="w-full h-full flex flex-col bg-black overflow-y-auto">
      {/* Upper Section: Map Area + Float Overlay */}
      <div className="flex-1 relative min-h-[520px] shrink-0">
        <MapContainer
          selectedHex={activeHex}
          onSelectHex={(hex) => setSelectedHex(hex)}
          allHexes={allHexes}
          viewMode={mapLayer}
          compactLabels={compactLabels}
          highlightedHexIds={highlightedHexIds}
          focusCenter={focusCenter}
          stations={stations}
          samplePool={samplePool}
          localPeakHexIds={localPeakHexIds}
        />

        {/* Left: layer toggle + optional rankings-loading chip */}
        <div className="absolute top-4 left-4 z-20 flex flex-col gap-2 items-start">
          <div className="flex ui-glass ui-glass-floating rounded-full p-1 shadow-xl">
            {(
              [
                { id: 'aqi' as const, label: 'AQI' },
                { id: 'confidence' as const, label: 'Confidence' },
              ] as const
            ).map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setMapLayer(opt.id)}
                className={`px-4 py-2 rounded-full text-[11px] font-bold tracking-wide transition-colors min-h-[40px] ${
                  mapLayer === opt.id
                    ? 'bg-brand-blue text-white shadow-md'
                    : 'text-apple-secondary hover:text-white'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {rankingsLoading && (
            <div className="ui-glass ui-glass-floating rounded-full px-3 py-1.5 border border-brand-blue/30 flex items-center gap-2 shadow-lg">
              <div className="w-3 h-3 border-2 border-brand-blue/40 border-t-brand-blue rounded-full animate-spin" />
              <span className="text-[10px] font-mono text-brand-blue uppercase tracking-wider">
                {modeSwitchPending
                  ? rankingMode === 'local_peaks'
                    ? 'Switching to Local peaks…'
                    : 'Switching to Global highest…'
                  : 'Loading hex rankings…'}
              </span>
            </div>
          )}
          {extremesError && !rankingsLoading && (
            <div className="ui-glass rounded-full px-3 py-1.5 border border-brand-orange/30 text-[10px] text-brand-orange max-w-[220px]">
              {rankingMode === 'local_peaks'
                ? 'Local peaks failed — try Global or retry'
                : 'Rankings unavailable — sensors only'}
            </div>
          )}
        </div>

        {/* Legend — bottom-left, compact, no glow dots */}
        <div className="absolute bottom-6 left-4 z-10 ui-glass ui-glass-floating p-3.5 rounded-2xl max-w-[210px]">
          <div className="text-[10px] font-mono uppercase text-apple-secondary tracking-widest mb-2.5">
            {mapLayer === 'confidence' ? 'Attribution confidence' : 'Legend'}
          </div>
          <div className="flex flex-col gap-1.5">
            {mapLayer === 'confidence' ? (
              <>
                {[
                  { c: '#34C759', r: '80–100', l: 'High' },
                  { c: '#0A84FF', r: '55–79', l: 'Medium' },
                  { c: '#FF9F0A', r: '30–54', l: 'Low' },
                  { c: '#ff453a', r: '18–29', l: 'Very Low' },
                ].map((row) => (
                  <div key={row.l} className="flex items-center justify-between text-xs font-semibold">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ background: row.c }} />
                      <span className="font-mono text-white text-[11px]">{row.r}</span>
                    </div>
                    <span className="text-apple-secondary text-[10px] font-medium">{row.l}</span>
                  </div>
                ))}
              </>
            ) : (
              <>
                {[
                  { c: '#34C759', r: '0–50', l: 'Good' },
                  { c: '#FFCC00', r: '51–100', l: 'Moderate' },
                  { c: '#FF9F0A', r: '101–250', l: 'Poor' },
                  { c: '#ff453a', r: '251+', l: 'Severe' },
                ].map((row) => (
                  <div key={row.l} className="flex items-center justify-between text-xs font-semibold">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ background: row.c }} />
                      <span className="font-mono text-white text-[11px]">{row.r}</span>
                    </div>
                    <span className="text-apple-secondary text-[10px] font-medium">{row.l}</span>
                  </div>
                ))}
              </>
            )}
          </div>
          <div className="mt-3 pt-2.5 border-t border-white/10 space-y-1.5">
            <div className="flex items-center gap-2 text-[10px] text-white/85">
              <span className="relative w-3.5 h-3.5 shrink-0">
                <span className="absolute inset-0 rotate-45 rounded-[2px] bg-[#FF9F0A]" />
                <span className="absolute inset-[3px] rotate-45 rounded-[1px] bg-[#0A84FF] border border-white/90" />
              </span>
              <span>Official sensor (diamond)</span>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-white/85">
              <span className="inline-flex items-center gap-1 rounded-md bg-black/60 border border-white/20 px-1 py-0.5 text-[8px] font-mono font-bold text-white">
                <span className="w-1.5 h-1.5 rotate-45 bg-[#FFCC00]" />
                42
              </span>
              <span>Nearby fused AQI</span>
            </div>
            {rankingMode === 'local_peaks' && (extremeMode === 'worst' || extremeMode === 'both') && (
              <div className="flex items-center gap-2 text-[10px] text-white/85">
                <span className="text-[8px] font-bold uppercase tracking-wider text-brand-blue border border-brand-blue/40 px-1 py-0.5 rounded">
                  Peak
                </span>
                <span>Station-catchment dirty hex</span>
              </div>
            )}
            <p className="text-[8px] text-apple-secondary/80 leading-snug">
              Nearby samples = real fused hexes within ~4.5 km of a station — not synthetic.
            </p>
            {extremes && (
              <p className="text-[8px] font-mono text-apple-secondary/50 leading-relaxed">
                {extremes.totalWithData} hexes with data · {extremes.totalInGrid} grid
              </p>
            )}
          </div>
        </div>

        {/* Right stack: controls (top) + optional detail (below) — no overlap */}
        <div className="absolute top-4 right-4 z-20 flex flex-col items-end gap-2 w-[min(100vw-2rem,288px)] max-h-[calc(100%-2rem)] pointer-events-none">
          {/* Unified map controls card */}
          <div className="pointer-events-auto w-full ui-glass ui-glass-floating rounded-2xl border border-white/10 shadow-xl overflow-hidden">
            <div className="px-3 pt-2.5 pb-1.5">
              <div className="text-[9px] font-mono uppercase tracking-wider text-apple-secondary">
                Hex view
              </div>
            </div>
            <div className="px-2 pb-2">
              <div className="flex rounded-xl overflow-hidden bg-black/45 border border-white/8">
                {(
                  [
                    { id: 'best' as const, label: 'Cleanest', active: 'bg-brand-green text-white' },
                    { id: 'both' as const, label: 'Both', active: 'bg-brand-blue text-white' },
                    { id: 'worst' as const, label: 'Polluted', active: 'bg-brand-red text-white' },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setExtremeMode(opt.id)}
                    className={`flex-1 px-2 py-2.5 text-[11px] font-bold transition-colors min-h-[40px] ${
                      extremeMode === opt.id
                        ? opt.active
                        : 'text-apple-secondary hover:text-white hover:bg-white/5'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {/* Dual ranking mode — only relevant when polluted hexes are shown */}
              {(extremeMode === 'worst' || extremeMode === 'both') && (
                <div className="mt-2.5 space-y-2">
                  <div className="text-[9px] font-mono uppercase tracking-wider text-apple-secondary px-0.5">
                    Polluted ranking
                  </div>
                  <div className="flex rounded-xl overflow-hidden bg-black/45 border border-white/8">
                    <button
                      type="button"
                      onClick={() => setRankingMode('global')}
                      title="Absolute highest fused PM2.5 among all covered hexes"
                      className={`flex-1 px-2 py-2 text-[10px] font-bold min-h-[38px] transition-colors leading-tight ${
                        rankingMode === 'global'
                          ? 'bg-brand-orange text-white'
                          : 'text-apple-secondary hover:text-white hover:bg-white/5'
                      }`}
                    >
                      Global highest
                    </button>
                    <button
                      type="button"
                      onClick={() => setRankingMode('local_peaks')}
                      title="Worst fused hexes near each official station, then merged"
                      className={`flex-1 px-2 py-2 text-[10px] font-bold min-h-[38px] transition-colors leading-tight ${
                        rankingMode === 'local_peaks'
                          ? 'bg-brand-blue text-white'
                          : 'text-apple-secondary hover:text-white hover:bg-white/5'
                      }`}
                    >
                      Local peaks
                    </button>
                  </div>
                  <select
                    value={pollutedDepth}
                    onChange={(e) => {
                      setPollutedDepth(Number(e.target.value) as PollutedDepth);
                      setExtremeMode((m) => (m === 'best' ? 'worst' : m));
                    }}
                    className="w-full bg-black/50 border border-white/10 rounded-xl text-[11px] font-semibold text-white px-2.5 py-2 outline-none"
                    aria-label="Polluted hex count"
                  >
                    {POLLUTED_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value} className="bg-apple-card">
                        {o.label} · {rankingMode === 'local_peaks' ? 'local peaks' : 'global'}
                      </option>
                    ))}
                  </select>

                  {/* Honesty banner for active ranking mode */}
                  <div
                    className={`rounded-xl border px-2.5 py-2 flex gap-2 ${
                      rankingMode === 'local_peaks'
                        ? 'bg-brand-blue/10 border-brand-blue/30'
                        : 'bg-brand-orange/10 border-brand-orange/30'
                    }`}
                  >
                    <Info
                      size={12}
                      className={`shrink-0 mt-0.5 ${
                        rankingMode === 'local_peaks' ? 'text-brand-blue' : 'text-brand-orange'
                      }`}
                    />
                    <div className="min-w-0 text-[9px] leading-relaxed text-white/80">
                      {rankingMode === 'local_peaks' ? (
                        <>
                          <strong className="text-brand-blue">Local peaks</strong>
                          {' — '}
                          worst hexes near each PM2.5 station (~5 km), merged. Shows dirty
                          pockets city-wide; not the same as global Top N.
                        </>
                      ) : (
                        <>
                          <strong className="text-brand-orange">Global highest</strong>
                          {' — '}
                          absolute fused PM among covered hexes. A high station can create a
                          large northern tie plateau (e.g. Hebbal).
                          {extremes?.tieCountAtMax != null &&
                            extremes.tieCountAtMax > pollutedDepth && (
                              <>
                                {' '}
                                <span className="text-white/60">
                                  ~{extremes.tieCountAtMax} hexes near max
                                  {extremes.maxFusedPm25 != null
                                    ? ` (${Math.round(extremes.maxFusedPm25)} µg/m³)`
                                    : ''}
                                  .
                                </span>
                              </>
                            )}
                        </>
                      )}
                      {extremesFetching && (
                        <span className="block text-brand-blue mt-1 animate-pulse">
                          Updating ranking…
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="text-[9px] font-mono text-apple-secondary px-1 pt-2">
                {extremeMode === 'best' && `${cleanestShown.length} cleanest hexes`}
                {extremeMode === 'both' &&
                  `${cleanestShown.length} clean + ${pollutedShown.length} polluted`}
                {extremeMode === 'worst' && `${pollutedShown.length} polluted hexes`}
                {stations.length > 0 && ` · ${stations.length} sensors`}
              </div>
              {extremes && (
                <div className="text-[8px] font-mono text-apple-secondary/70 px-1 pt-1 leading-snug">
                  Ranked among {extremes.totalWithData.toLocaleString()} fused hexes of{' '}
                  {extremes.totalInGrid.toLocaleString()} grid
                  {extremes.fusionRangeM != null &&
                    ` · ~${Math.round(extremes.fusionRangeM / 1000)} km range`}
                </div>
              )}
            </div>

            {/* Copilot / map context — inside same card to avoid extra floating boxes */}
            {(hasCopilotHighlights || hasMapCtx) && (
              <div className="border-t border-white/10 px-3 py-2.5 space-y-2">
                {hasCopilotHighlights && (
                  <div className="flex items-start gap-2 rounded-xl bg-fuchsia-500/10 border border-fuchsia-500/30 px-2.5 py-2">
                    <Sparkles size={13} className="text-fuchsia-400 shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-fuchsia-300">
                        Copilot highlights
                      </div>
                      <div className="text-[10px] text-white/75 font-mono truncate">
                        {highlightedHexIds.length} hex
                        {highlightedHexIds.length === 1 ? '' : 'es'}
                        {mapActions?.focus_on?.label
                          ? ` · ${mapActions.focus_on.label}`
                          : ''}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => clearMapActions()}
                      className="p-1 rounded-full hover:bg-white/10 text-apple-secondary hover:text-white shrink-0"
                      title="Clear Copilot highlights"
                    >
                      <X size={12} />
                    </button>
                  </div>
                )}
                {hasMapCtx && (
                  <div className="flex items-center gap-2 rounded-xl bg-brand-blue/10 border border-brand-blue/30 px-2.5 py-2">
                    <MapPin size={12} className="text-brand-blue shrink-0" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-brand-blue shrink-0">
                      Context
                    </span>
                    <span className="text-[10px] text-white/70 font-mono truncate">
                      {mapCtxLabel || mapCtxStation || String(mapCtxH3 || '').slice(0, 12)}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Detail panel — scrolls inside stack, does not cover controls */}
          {activeHex && (
          <div className="pointer-events-auto w-full flex-1 min-h-0 max-h-[min(58vh,520px)] ui-glass ui-glass-strong rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-white/10">
            {/* Header */}
            <div className="p-4 border-b border-white/10 flex flex-col gap-0.5 bg-black/25 shrink-0">
              <div className="flex items-start justify-between gap-2">
                <span className="text-[10px] font-mono uppercase text-apple-secondary tracking-widest flex items-center gap-1.5 min-w-0">
                  <MapPin size={10} className="text-brand-blue shrink-0" />
                  <span className="truncate">{formatLocationName(activeHex)}</span>
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedHex(null)}
                  className="p-1 rounded-full hover:bg-white/10 text-apple-secondary hover:text-white shrink-0"
                  title="Close detail"
                >
                  <X size={14} />
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                <h2 className="text-base font-bold text-white tracking-tight leading-snug">
                  Area detail
                </h2>
                {activeIsLocalPeak && (
                  <span className="text-[9px] font-bold uppercase tracking-wider text-brand-blue bg-brand-blue/15 border border-brand-blue/35 px-2 py-0.5 rounded-full">
                    Local peak
                  </span>
                )}
              </div>
              {activeIsLocalPeak && (
                <p className="text-[10px] text-apple-secondary leading-snug mt-1">
                  Dirty pocket near an official station catchment — Local Peaks ranking, not
                  global absolute #1.
                </p>
              )}
              <span
                className="text-[10px] text-apple-secondary font-mono truncate mt-0.5"
                title={activeHex.id}
              >
                {activeHex.id}
              </span>
            </div>

            {/* Readouts */}
            <div className="p-4 flex flex-col gap-4 flex-1 overflow-y-auto min-h-0">
              {/* Giant AQI */}
              <div className="flex items-end gap-3">
                <div className={`text-4xl font-bold font-mono select-none leading-none ${
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
                    const method = (activeHex.attributionMethod || 'wind_weighted').toUpperCase();
                    return total > 0 ? (
                      <span className="text-brand-blue flex items-center gap-1 bg-brand-blue/10 px-2 py-0.5 rounded-full font-bold">
                        {method}
                      </span>
                    ) : (
                      <span className="text-apple-secondary flex items-center gap-1 bg-apple-border/20 px-2 py-0.5 rounded-full font-bold">
                        UNAVAILABLE
                      </span>
                    );
                  })()}
                </div>

                {/* Attribution confidence — calm, no blue glow bloom */}
                {(activeHex.attributionConfidence != null || activeHex.confidence > 0) && (
                  <div className="mt-3 rounded-xl border border-white/12 bg-white/[0.04] px-3 py-2.5">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary font-bold">
                        Attribution confidence
                      </span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                          (activeHex.attributionConfidence ?? activeHex.confidence) >= 80
                            ? 'bg-brand-green/15 border-brand-green/30 text-brand-green'
                            : (activeHex.attributionConfidence ?? activeHex.confidence) >= 55
                              ? 'bg-brand-blue/15 border-brand-blue/30 text-brand-blue'
                              : (activeHex.attributionConfidence ?? activeHex.confidence) >= 30
                                ? 'bg-brand-orange/15 border-brand-orange/30 text-brand-orange'
                                : 'bg-brand-red/15 border-brand-red/30 text-brand-red'
                        }`}
                      >
                        {activeHex.attributionConfidenceLevel || '—'}
                      </span>
                    </div>
                    <div className="text-2xl font-mono font-bold text-white leading-none">
                      {activeHex.attributionConfidence ?? activeHex.confidence}
                      <span className="text-sm text-apple-secondary">%</span>
                    </div>
                    {activeHex.confidenceExplanation && (
                      <p className="text-[11px] text-white/75 mt-1.5 leading-snug">
                        {activeHex.confidenceExplanation}
                      </p>
                    )}
                    {activeHex.nearestStationDistanceM != null && (
                      <p className="text-[10px] font-mono text-white/40 mt-1">
                        Nearest station · {(activeHex.nearestStationDistanceM / 1000).toFixed(1)} km
                      </p>
                    )}
                  </div>
                )}


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

              {activeHex.attributionMethod && (
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[10px] font-mono text-apple-secondary">
                  Method ·{' '}
                  <span className="text-white/80">
                    {(activeHex.attributionMethod || '').replace(/_/g, ' ')}
                  </span>
                </div>
              )}
            </div>

            {/* Actions: Ask Copilot (Map → Copilot) + Dispatch */}
            <div className="p-3 border-t border-white/10 bg-black/30 space-y-2 shrink-0">
              <button
                type="button"
                onClick={() => handleAskCopilot(activeHex)}
                className="w-full min-h-[42px] py-2.5 rounded-full text-[11px] font-bold uppercase tracking-wider transition-colors duration-200 flex items-center justify-center gap-2 bg-indigo-600/90 hover:bg-indigo-500 text-white border border-indigo-400/25"
              >
                <Bot size={14} />
                Ask Copilot
              </button>
              <button
                type="button"
                onClick={() => handleDispatch(activeHex)}
                className="w-full min-h-[42px] py-2.5 rounded-full text-[11px] font-bold uppercase tracking-wider transition-colors duration-200 flex items-center justify-center gap-2 bg-brand-blue hover:bg-blue-600 text-white"
              >
                <Shield size={14} />
                {dispatchedUnits[activeHex.id] ? 'Open Dispatch' : 'Dispatch unit'}
              </button>
            </div>
          </div>
          )}
        </div>

        {/* Scroll hint — offset so it does not collide with map status chip */}
        <div className="absolute bottom-14 left-1/2 -translate-x-1/2 z-[5] flex flex-col items-center gap-1 pointer-events-none">
          <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-white/60 bg-black/45 backdrop-blur-md px-3 py-1 rounded-full border border-white/10">
            Scroll for hotspots
          </span>
          <ChevronDown size={14} className="text-white/45 animate-bounce" />
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
