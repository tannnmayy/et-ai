/**
 * Full-page Enforcement detail — spacious view for judges / operators.
 * Route: #/enforcement/detail/:h3Cell
 *
 * Data resolution order (no unnecessary API if already warm):
 * 1. router location.state.hex
 * 2. sessionStorage cache (set on Expand from panel)
 * 3. React Query enforcement-priorities caches
 * 4. fetch top-100 priorities as fallback
 */
import React, { Suspense, lazy, useMemo, useCallback, useState } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Expand, ShieldAlert } from 'lucide-react';
import type { PriorityHex } from '../types';
import {
  ENFORCEMENT_MAX_TOP_K,
  enforcementPrioritiesQueryKey,
  fetchEnforcementPriorities,
} from '../services/geospatialService';
import { formatLocationName } from '../services/enforcementUtils';
import { readCachedEnforcementDetailHex } from '../services/enforcementDetailCache';

const EnforcementDetailPanel = lazy(
  () => import('../components/enforcement/EnforcementDetailPanel'),
);

function findHexInQueryCache(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string,
): PriorityHex | null {
  const matches = queryClient.getQueriesData<PriorityHex[]>({
    queryKey: ['enforcement-priorities'],
  });
  for (const [, data] of matches) {
    if (!Array.isArray(data)) continue;
    const hit = data.find((h) => h.id === id);
    if (hit) return hit;
  }
  return null;
}

export default function EnforcementDetailPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { h3Cell: h3Param } = useParams<{ h3Cell: string }>();
  const location = useLocation();
  const id = decodeURIComponent(h3Param || '').trim();

  const stateHex = (location.state as { hex?: PriorityHex } | null)?.hex;

  const cachedHex = useMemo(
    () => (id ? readCachedEnforcementDetailHex(id) : null),
    [id],
  );

  const rqHex = useMemo(
    () => (id ? findHexInQueryCache(queryClient, id) : null),
    [queryClient, id],
  );

  const needsFetch = Boolean(
    id &&
      !(stateHex?.id === id) &&
      !(cachedHex?.id === id) &&
      !(rqHex?.id === id),
  );

  // Fallback fetch ONLY when hex is not already in state / session / RQ cache
  const {
    data: fetched = [],
    isLoading,
    isError,
    isFetching,
  } = useQuery({
    queryKey: enforcementPrioritiesQueryKey(ENFORCEMENT_MAX_TOP_K, null, false, null),
    queryFn: () => fetchEnforcementPriorities(ENFORCEMENT_MAX_TOP_K, null, false, null),
    enabled: needsFetch,
    staleTime: 60_000,
  });

  const hex = useMemo(() => {
    if (stateHex?.id === id) return stateHex;
    if (cachedHex?.id === id) return cachedHex;
    if (rqHex?.id === id) return rqHex;
    return fetched.find((h) => h.id === id) || null;
  }, [stateHex, cachedHex, rqHex, fetched, id]);

  const [dispatched, setDispatched] = useState(false);

  const handleBack = useCallback(() => {
    navigate('/enforcement');
  }, [navigate]);

  const handleDispatch = useCallback(() => {
    if (!hex) return;
    setDispatched(true);
    const loc = formatLocationName(hex);
    const qs = new URLSearchParams({
      target: loc,
      hex: hex.id,
      source: String(hex.primarySource ?? hex.primarySourceKey ?? 'mixed'),
      score: String(hex.score10 ?? hex.priorityScore ?? '—'),
      action:
        hex.explanation?.text ||
        'Inspect site for dust control compliance and document evidence.',
    });
    navigate(`/dispatch?${qs.toString()}`);
  }, [hex, navigate]);

  if (!id) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center bg-black gap-3 p-6">
        <p className="text-sm text-apple-secondary">Missing location id.</p>
        <button
          type="button"
          onClick={handleBack}
          className="px-4 py-2 rounded-full bg-brand-blue text-white text-xs font-bold uppercase"
        >
          Back to Enforcement
        </button>
      </div>
    );
  }

  if (!hex && needsFetch && (isLoading || isFetching)) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center bg-black gap-4">
        <div className="w-8 h-8 border-2 border-brand-blue border-t-transparent rounded-full animate-spin" />
        <span className="text-xs font-mono uppercase tracking-widest text-apple-secondary">
          Loading location detail…
        </span>
      </div>
    );
  }

  if (!hex || isError) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center bg-black gap-4 p-6 text-center">
        <div className="w-12 h-12 rounded-full bg-brand-orange/10 border border-brand-orange/25 flex items-center justify-center text-brand-orange">
          <ShieldAlert size={22} />
        </div>
        <h1 className="text-lg font-bold text-white">Location not in current queue</h1>
        <p className="text-sm text-apple-secondary max-w-md leading-relaxed">
          Hex <span className="font-mono text-white/80">{id}</span> was not found in the
          loaded enforcement priorities. Return to the list and select a target, or raise Top-N.
        </p>
        <button
          type="button"
          onClick={handleBack}
          className="min-h-[44px] px-5 rounded-full bg-brand-blue text-white text-xs font-bold uppercase tracking-wider"
        >
          Back to Enforcement
        </button>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col bg-black overflow-hidden">
      {/* Sticky chrome */}
      <header className="shrink-0 border-b border-white/10 bg-black/80 backdrop-blur-xl px-4 sm:px-6 py-3 flex items-center gap-3 z-10">
        <button
          type="button"
          onClick={handleBack}
          className="min-h-[40px] px-3 rounded-full border border-white/15 bg-white/5 hover:bg-white/10 text-white text-xs font-bold uppercase tracking-wider inline-flex items-center gap-2"
        >
          <ArrowLeft size={14} />
          Enforcement
        </button>
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary flex items-center gap-1.5">
            <Expand size={11} className="text-brand-blue" />
            Full detail
          </div>
          <h1 className="text-base sm:text-lg font-bold text-white truncate">
            {formatLocationName(hex)}
          </h1>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto min-h-0">
        <Suspense
          fallback={
            <div className="p-10 text-center text-xs text-apple-secondary">Loading detail…</div>
          }
        >
          <EnforcementDetailPanel
            hex={hex}
            variant="page"
            onClose={handleBack}
            dispatched={dispatched}
            onDispatch={handleDispatch}
          />
        </Suspense>
      </div>
    </div>
  );
}
