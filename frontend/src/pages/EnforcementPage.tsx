import React, {
  Suspense,
  lazy,
  useCallback,
  useMemo,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { useEnforcementPriorities } from '../api/client';
import type { ActionTier, ExposureLevel, PriorityHex, SourceKey } from '../types';
import MapContainer from '../components/MapContainer';
import EnforcementTableRow from '../components/enforcement/EnforcementTableRow';
import {
  AlertCircle,
  Info,
  Search,
  ArrowUpDown,
  Clock,
} from 'lucide-react';
import {
  actionTierLabel,
  actionTierStyles,
  formatLocationName,
  sortHexes,
  type SortKey,
} from '../services/enforcementUtils';
import { useDebouncedValue } from '../hooks/useDebouncedValue';

// Lazy: Recharts lives behind the detail panel — keep it out of the first paint.
const EnforcementDetailPanel = lazy(
  () => import('../components/enforcement/EnforcementDetailPanel'),
);

const TOP_OPTIONS = [
  { label: 'Top 15', value: 15 },
  { label: 'Top 20', value: 20 },
  { label: 'Top 50', value: 50 },
  { label: 'All (100)', value: 100 },
] as const;

const SIM_OPTIONS: { label: string; hour: number | null }[] = [
  { label: 'Current time', hour: null },
  { label: 'Morning peak (8 AM)', hour: 8 },
  { label: 'Evening peak (6 PM)', hour: 18 },
  { label: 'Night (2 AM)', hour: 2 },
];

const SOURCE_FILTERS: { key: SourceKey | 'mixed'; label: string }[] = [
  { key: 'construction', label: 'Construction' },
  { key: 'traffic', label: 'Traffic' },
  { key: 'industrial', label: 'Industrial' },
  { key: 'burning', label: 'Burning' },
  { key: 'mixed', label: 'Mixed' },
];

const TIER_FILTERS: ActionTier[] = ['IMMEDIATE', 'HIGH', 'MONITOR', 'ROUTINE'];
const EXPOSURE_FILTERS: ExposureLevel[] = ['Low', 'Medium', 'High', 'Critical'];

export default function EnforcementPage() {
  const navigate = useNavigate();
  // Default top 15 for fast first paint (prefetched on landing). Larger Top-N hits the API.
  const [topK, setTopK] = useState(15);
  // Immediate UI value for Simulate; debounced before it hits React Query
  const [simHourUi, setSimHourUi] = useState<number | null>(null);
  const simulatedHour = useDebouncedValue(simHourUi, 250);

  const [selectedHex, setSelectedHex] = useState<PriorityHex | null>(null);
  const [dispatchedUnits, setDispatchedUnits] = useState<Record<string, boolean>>({});

  const [search, setSearch] = useState('');
  const debouncedSearch = useDebouncedValue(search, 300);
  const [sourceFilter, setSourceFilter] = useState<Set<string>>(new Set());
  const [tierFilter, setTierFilter] = useState<Set<ActionTier>>(new Set());
  const [exposureFilter, setExposureFilter] = useState<Set<ExposureLevel>>(new Set());
  /** When true, only show major traffic corridor hexes */
  const [trafficCorridorOnly, setTrafficCorridorOnly] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('rank');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const {
    data: allPriorities = [],
    isError,
    isLoading,
    isFetching,
    isPlaceholderData,
  } = useEnforcementPriorities(simulatedHour, topK);

  // Server already returns topK rows; keep slice as safety
  const priorities = useMemo(
    () => allPriorities.slice(0, topK),
    [allPriorities, topK],
  );

  const filtered = useMemo(() => {
    let list = priorities;
    const q = debouncedSearch.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (h) =>
          formatLocationName(h).toLowerCase().includes(q) ||
          h.id.toLowerCase().includes(q) ||
          h.primarySource.toLowerCase().includes(q),
      );
    }
    if (sourceFilter.size > 0) {
      list = list.filter((h) => sourceFilter.has(h.primarySourceKey));
    }
    if (tierFilter.size > 0) {
      list = list.filter((h) => tierFilter.has(h.actionTier));
    }
    if (exposureFilter.size > 0) {
      list = list.filter((h) => exposureFilter.has(h.exposure));
    }
    if (trafficCorridorOnly) {
      list = list.filter((h) => h.isTrafficCorridor || h.isMajorRoadCorridor);
    }
    return sortHexes(list, sortKey, sortDir);
  }, [
    priorities,
    debouncedSearch,
    sourceFilter,
    tierFilter,
    exposureFilter,
    trafficCorridorOnly,
    sortKey,
    sortDir,
  ]);

  // Stable map hex list — avoid recreating array identity when empty filter fallback
  const mapHexes = useMemo(
    () => (filtered.length > 0 ? filtered : priorities),
    [filtered, priorities],
  );

  const activeHex = useMemo(() => {
    if (selectedHex) {
      const stillVisible = filtered.find((h) => h.id === selectedHex.id);
      if (stillVisible) return stillVisible;
      // Keep selection even if filtered out (detail stays open)
      return selectedHex;
    }
    return filtered[0] || null;
  }, [selectedHex, filtered]);

  const handleSelectHex = useCallback((hex: PriorityHex) => {
    setSelectedHex(hex);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedHex(null);
  }, []);

  const toggleSet = useCallback(<T,>(set: Set<T>, value: T, updater: (s: Set<T>) => void) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    updater(next);
  }, []);

  const handleSort = useCallback(
    (key: SortKey) => {
      if (sortKey === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortKey(key);
        setSortDir(key === 'name' || key === 'source' ? 'asc' : 'desc');
      }
    },
    [sortKey],
  );

  const handleDispatch = useCallback(
    (hexId: string) => {
      setDispatchedUnits((prev) => ({ ...prev, [hexId]: true }));
      const hex = allPriorities.find((h) => h.id === hexId);
      const loc = hex ? formatLocationName(hex) : hexId;
      const qs = new URLSearchParams({
        target: loc,
        hex: hexId,
        source: String(hex?.primarySource ?? hex?.primarySourceKey ?? 'mixed'),
        score: String(hex?.priorityScore ?? hex?.score10 ?? '—'),
        action:
          hex?.explanation?.text ||
          'Inspect site for dust control compliance and document evidence.',
      });
      navigate(`/dispatch?${qs.toString()}`);
    },
    [allPriorities, navigate],
  );

  const handleDispatchActive = useCallback(() => {
    if (activeHex) handleDispatch(activeHex.id);
  }, [activeHex, handleDispatch]);

  if (isLoading && allPriorities.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-brand-blue border-t-transparent rounded-full animate-spin" />
          <span className="text-xs font-mono uppercase tracking-widest text-apple-secondary">
            Loading enforcement intelligence...
          </span>
        </div>
      </div>
    );
  }

  if (isError && allPriorities.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4 max-w-md text-center px-6">
          <div className="w-12 h-12 rounded-full bg-brand-red/10 border border-brand-red/20 flex items-center justify-center text-brand-red">
            <AlertCircle size={24} />
          </div>
          <h2 className="text-lg font-bold text-white">Data Unavailable</h2>
          <p className="text-sm text-apple-secondary leading-relaxed">
            Unable to load enforcement priorities from the API. Check that the backend is
            running on port 8010.
          </p>
        </div>
      </div>
    );
  }

  const SortBtn = ({ k, children }: { k: SortKey; children: React.ReactNode }) => (
    <button
      type="button"
      onClick={() => handleSort(k)}
      className="inline-flex items-center gap-1 hover:text-white transition-colors"
      aria-label={`Sort by ${k}`}
    >
      {children}
      <ArrowUpDown size={10} className={sortKey === k ? 'text-brand-blue' : 'opacity-40'} />
    </button>
  );

  return (
    <div className="w-full h-full flex flex-col md:flex-row bg-black overflow-hidden">
      <section className="w-full md:w-[55%] h-full flex flex-col bg-black p-4 sm:p-6 border-r border-apple-border min-h-0">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-4 shrink-0">
          <div>
            <h2 className="text-2xl font-bold text-white tracking-tight leading-snug">
              Enforcement Intelligence
            </h2>
            <p className="text-xs text-apple-secondary font-sans mt-0.5">
              Evidence-backed intervention targets — exposure × magnitude × actionability.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 rounded-full px-3 py-2 bg-apple-card border border-apple-border text-[10px] font-bold uppercase tracking-wider">
              <Clock size={12} className="text-brand-blue" />
              <span className="text-apple-secondary">Simulate</span>
              <select
                value={simHourUi ?? ''}
                onChange={(e) =>
                  setSimHourUi(e.target.value === '' ? null : Number(e.target.value))
                }
                className="bg-transparent text-white outline-none cursor-pointer max-w-[140px]"
                aria-label="Simulate time of day for traffic weighting"
              >
                {SIM_OPTIONS.map((o) => (
                  <option key={o.label} value={o.hour ?? ''} className="bg-apple-card text-white">
                    {o.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex items-center gap-2 rounded-full px-3 py-2 bg-apple-card border border-apple-border text-[10px] font-bold uppercase tracking-wider">
              <span className="text-apple-secondary">Show</span>
              <select
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="bg-transparent text-white outline-none cursor-pointer"
                aria-label="Number of priority hexagons to display"
              >
                {TOP_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value} className="bg-apple-card">
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="mb-3 px-3 py-2.5 rounded-xl bg-apple-card/40 border border-apple-border/60 text-[10px] text-apple-secondary leading-relaxed shrink-0">
          <div className="flex items-start gap-2">
            <Info size={12} className="text-brand-blue shrink-0 mt-0.5" />
            <div>
              <strong className="text-white">Score (0–10)</strong> = exposure × attributable
              magnitude × actionability. Top-N is client-side (instant). Time simulation is
              cached per hour.
              {(isFetching || isPlaceholderData) && (
                <span className="ml-2 text-brand-blue animate-pulse">
                  {isPlaceholderData ? 'Loading simulation…' : 'Refreshing…'}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-2 mb-3 shrink-0">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-apple-secondary"
            />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search location…"
              className="w-full min-h-[40px] pl-9 pr-3 py-2 rounded-xl bg-apple-card border border-apple-border text-sm text-white placeholder:text-apple-secondary focus:outline-none focus:border-brand-blue"
              aria-label="Search locations"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {SOURCE_FILTERS.map((s) => {
              const on = sourceFilter.has(s.key);
              return (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => toggleSet(sourceFilter, s.key, setSourceFilter)}
                  className={`px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider border transition-colors ${
                    on
                      ? 'bg-brand-blue/15 border-brand-blue text-brand-blue'
                      : 'bg-apple-card border-apple-border text-apple-secondary hover:text-white'
                  }`}
                >
                  {s.label}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setTrafficCorridorOnly((v) => !v)}
              className={`px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider border transition-colors ${
                trafficCorridorOnly
                  ? 'bg-brand-blue text-white border-brand-blue shadow-sm shadow-brand-blue/20'
                  : 'bg-apple-card border-apple-border text-apple-secondary hover:text-white'
              }`}
              title="Show only major traffic corridor hexes"
            >
              Traffic Corridors
            </button>
            <span className="w-px h-5 bg-apple-border self-center mx-0.5" />
            {TIER_FILTERS.map((t) => {
              const on = tierFilter.has(t);
              const st = actionTierStyles(t);
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => toggleSet(tierFilter, t, setTierFilter)}
                  className={`px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider border transition-colors ${
                    on ? st.bg : 'bg-apple-card border-apple-border text-apple-secondary hover:text-white'
                  }`}
                >
                  {actionTierLabel(t)}
                </button>
              );
            })}
            <span className="w-px h-5 bg-apple-border self-center mx-0.5" />
            {EXPOSURE_FILTERS.map((e) => {
              const on = exposureFilter.has(e);
              return (
                <button
                  key={e}
                  type="button"
                  onClick={() => toggleSet(exposureFilter, e, setExposureFilter)}
                  className={`px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider border transition-colors ${
                    on
                      ? 'bg-white/10 border-white/30 text-white'
                      : 'bg-apple-card border-apple-border text-apple-secondary hover:text-white'
                  }`}
                >
                  {e}
                </button>
              );
            })}
          </div>
          <p className="text-[10px] font-mono text-apple-secondary">
            Showing {filtered.length} of {priorities.length} displayed
            {allPriorities.length > priorities.length
              ? ` (${allPriorities.length} cached)`
              : ''}
            {simulatedHour != null ? ` · simulated hour ${simulatedHour}:00 IST` : ''}
          </p>
        </div>

        <div className="flex-1 flex flex-col overflow-hidden min-h-0">
          <div className="grid grid-cols-[44px_minmax(0,1.4fr)_72px_88px_72px_80px_100px] gap-2 px-3 py-2 border-b border-apple-border mb-1.5 shrink-0">
            <div className="text-[10px] font-mono font-bold text-apple-secondary uppercase text-right">
              <SortBtn k="rank">#</SortBtn>
            </div>
            <div className="text-[10px] font-sans font-bold text-apple-secondary uppercase pl-1">
              <SortBtn k="name">Location</SortBtn>
            </div>
            <div className="text-[10px] font-sans font-bold text-apple-secondary uppercase">
              <SortBtn k="source">Source</SortBtn>
            </div>
            <div className="text-[10px] font-mono font-bold text-apple-secondary uppercase text-right">
              <SortBtn k="score">Score</SortBtn>
            </div>
            <div className="text-[10px] font-sans font-bold text-apple-secondary uppercase text-right">
              <SortBtn k="exposure">Exp.</SortBtn>
            </div>
            <div className="text-[10px] font-mono font-bold text-apple-secondary uppercase text-right">
              <SortBtn k="magnitude">Mag.</SortBtn>
            </div>
            <div className="text-[10px] font-sans font-bold text-apple-secondary uppercase text-right pr-1">
              Action
            </div>
          </div>

          <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
            {filtered.length === 0 && (
              <div className="py-12 text-center text-sm text-apple-secondary">
                No targets match the current filters.
              </div>
            )}
            {filtered.map((item) => (
              <EnforcementTableRow
                key={item.id}
                item={item}
                isSelected={activeHex?.id === item.id}
                onSelect={handleSelectHex}
              />
            ))}
          </div>
        </div>
      </section>

      <section className="w-full md:w-[45%] h-full relative bg-apple-bg flex flex-col justify-between min-h-0">
        <div className="flex-1 w-full min-h-0 relative">
          <MapContainer
            selectedHex={activeHex}
            onSelectHex={handleSelectHex}
            allHexes={mapHexes}
            viewMode="enforcement"
          />
        </div>

        {activeHex && (
          <Suspense
            fallback={
              <div className="p-6 border-t border-apple-border bg-apple-modal/95 text-xs text-apple-secondary text-center">
                Loading detail panel…
              </div>
            }
          >
            <EnforcementDetailPanel
              hex={activeHex}
              onClose={handleCloseDetail}
              dispatched={!!dispatchedUnits[activeHex.id]}
              onDispatch={handleDispatchActive}
            />
          </Suspense>
        )}
      </section>
    </div>
  );
}
