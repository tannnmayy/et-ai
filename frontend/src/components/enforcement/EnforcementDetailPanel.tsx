import React, { Suspense, lazy, useMemo, useState } from 'react';
import {
  ShieldAlert,
  Shield,
  ShieldCheck,
  X,
  Car,
  FileText,
  Clock,
  Database,
  Gauge,
  SlidersHorizontal,
} from 'lucide-react';
import type { PriorityHex } from '../../types';
import SourceIcon from '../SourceIcon';
import {
  actionTierLabel,
  actionTierStyles,
  buildRecommendations,
  confidenceLevelColor,
  formatHexIdSubtitle,
  formatLocationName,
  rankDelta,
  simulateConstructionCounterfactual,
} from '../../services/enforcementUtils';

// Recharts is heavy — only load when the detail panel is open (this file is
// already lazy-loaded from EnforcementPage).
const AttributionChart = lazy(() => import('./AttributionChart'));

interface Props {
  hex: PriorityHex;
  onClose: () => void;
  dispatched: boolean;
  onDispatch: () => void;
}

export default function EnforcementDetailPanel({
  hex,
  onClose,
  dispatched,
  onDispatch,
}: Props) {
  const [copied, setCopied] = useState(false);
  /** 100 = baseline construction intensity */
  const [constructionPct, setConstructionPct] = useState(100);
  const tierStyle = actionTierStyles(hex.actionTier);
  const recs = buildRecommendations(hex);
  const location = formatLocationName(hex);

  const counterfactual = useMemo(
    () => simulateConstructionCounterfactual(hex, constructionPct / 100),
    [hex, constructionPct],
  );
  const confPct = hex.attributionConfidence ?? hex.confidence;

  const copyReport = async () => {
    const lines = [
      `ENFORCEMENT BRIEF — ${location}`,
      `H3: ${hex.id}`,
      `Score: ${hex.score10}/10 | Tier: ${actionTierLabel(hex.actionTier)}`,
      `PM2.5: ${hex.pm25} µg/m³ | Exposure: ${hex.exposure}`,
      `Primary source: ${hex.primarySource}`,
      `Attribution: T ${(hex.sourceAttribution.traffic * 100).toFixed(0)}% | I ${(hex.sourceAttribution.industrial * 100).toFixed(0)}% | C ${(hex.sourceAttribution.construction * 100).toFixed(0)}% | B ${(hex.sourceAttribution.burning * 100).toFixed(0)}%`,
      hex.isMajorRoadCorridor ? 'FLAG: Major traffic corridor' : '',
      hex.isPeakHour
        ? `Peak hour active (×${hex.trafficTimeMultiplier ?? '—'}, hour ${hex.trafficHourLocal ?? '—'})`
        : '',
      '',
      'RECOMMENDATIONS:',
      ...recs.flatMap((r) => [`- ${r.title}`, ...r.actions.map((a) => `  • ${a}`)]),
      '',
      hex.explanation?.text ? `Guidance: ${hex.explanation.text}` : '',
    ].filter(Boolean);
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard may be denied */
    }
  };

  return (
    <div
      className="p-4 sm:p-5 ui-glass ui-glass-strong z-20 relative max-h-full overflow-y-auto border-0 md:border-t md:border-white/10"
      role="region"
      aria-label="Enforcement detail panel"
    >
      <div className="max-w-xl mx-auto flex flex-col gap-4">
        {/* Header */}
        <div className="flex justify-between items-start border-b border-apple-border/50 pb-3">
          <div className="flex gap-3 items-start min-w-0">
            <div
              className={`h-11 w-11 rounded-xl border flex items-center justify-center shrink-0 ${tierStyle.bg}`}
            >
              <ShieldAlert size={20} className={hex.actionTier === 'IMMEDIATE' ? 'animate-pulse' : ''} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-bold text-white tracking-tight truncate">
                  {location}
                </h3>
                <span
                  className={`text-[9px] font-bold px-2 py-0.5 rounded-full border select-none ${tierStyle.bg}`}
                >
                  {actionTierLabel(hex.actionTier)}
                </span>
              </div>
              <p
                className="text-[10px] text-apple-secondary font-mono mt-0.5 truncate"
                title={formatHexIdSubtitle(hex)}
              >
                Score {hex.score10}/10 · Rank #{String(hex.rank).padStart(2, '0')}
                {hex.riskAdjustedScore10 != null && (
                  <> · Risk-adj {hex.riskAdjustedScore10}/10</>
                )}
              </p>
              <p className="text-[9px] font-mono text-apple-secondary/50 mt-0.5 truncate" title={hex.id}>
                H3 {hex.id.slice(0, 8)}…{hex.id.slice(-4)}
              </p>
              {hex.isPeakHour && (
                <p className="text-[10px] text-brand-blue mt-1 flex items-center gap-1">
                  <Clock size={11} />
                  {hex.trafficHourLocal != null && hex.trafficHourLocal >= 17
                    ? 'Evening'
                    : hex.trafficHourLocal != null && hex.trafficHourLocal < 12
                      ? 'Morning'
                      : ''}{' '}
                  Peak ×{hex.trafficTimeMultiplier ?? 1.4}
                  {hex.trafficHourLocal != null ? ` (${hex.trafficHourLocal}:00 IST)` : ''}
                </p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-apple-card hover:bg-apple-border/20 border border-apple-border flex items-center justify-center text-apple-secondary hover:text-white transition-colors"
            aria-label="Close detail panel"
          >
            <X size={14} />
          </button>
        </div>

        {/* Metrics row */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <span className="text-[9px] font-mono uppercase tracking-widest text-apple-secondary">
              PM2.5
            </span>
            <div className="flex items-end gap-1 mt-1">
              <span className="font-mono text-xl font-bold text-brand-red leading-none">
                {hex.pm25 || '—'}
              </span>
              <span className="text-[9px] text-apple-secondary pb-0.5">µg/m³</span>
            </div>
          </div>
          <div>
            <span className="text-[9px] font-mono uppercase tracking-widest text-apple-secondary">
              Primary Source
            </span>
            <div className="text-xs font-semibold text-white flex items-center gap-1.5 mt-1">
              <SourceIcon sourceType={hex.primarySource} size={16} />
              {hex.primarySource}
            </div>
          </div>
          <div>
            <span className="text-[9px] font-mono uppercase tracking-widest text-apple-secondary">
              Exposure
            </span>
            <div className="text-xs font-semibold text-white mt-1">{hex.exposure}</div>
          </div>
        </div>

        {/* Corridor badge — visible whenever product flag or major-road flag is set */}
        {(hex.isTrafficCorridor || hex.isMajorRoadCorridor) && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-brand-blue/10 border border-brand-blue/25 text-brand-blue text-[11px] font-semibold">
            <Car size={14} />
            Major Traffic Corridor
            {hex.trafficCorridorScore != null && (
              <span className="ml-auto font-mono text-[10px] opacity-80">
                score {(hex.trafficCorridorScore * 100).toFixed(0)}%
              </span>
            )}
          </div>
        )}

        {/* Rank comparison under risk adjustment */}
        {hex.baseRank != null && (
          <div
            className={`rounded-2xl border p-3.5 ${
              rankDelta(hex) != null && Math.abs(rankDelta(hex)!) >= 2
                ? 'bg-brand-blue/10 border-brand-blue/35 shadow-lg shadow-brand-blue/10'
                : 'bg-white/[0.04] border-white/12'
            }`}
          >
            <div className="text-[10px] font-mono uppercase tracking-wider text-brand-blue mb-2 font-bold">
              Rank impact · risk adjustment
            </div>
            <div className="flex items-center justify-center gap-2 text-center">
              <div>
                <div className="text-[9px] font-mono uppercase text-apple-secondary">Base rank</div>
                <div className="text-2xl font-mono font-bold text-white">
                  #{String(hex.baseRank).padStart(2, '0')}
                </div>
              </div>
              <div className="text-xl text-apple-secondary px-1">→</div>
              <div>
                <div className="text-[9px] font-mono uppercase text-brand-blue">Risk-adj rank</div>
                <div className="text-2xl font-mono font-bold text-brand-blue">
                  #{String(hex.rank).padStart(2, '0')}
                </div>
              </div>
              {rankDelta(hex) != null && rankDelta(hex) !== 0 && (
                <span
                  className={`ml-1 text-xs font-bold px-2 py-1 rounded-full border ${
                    (rankDelta(hex) ?? 0) > 0
                      ? 'bg-brand-green/15 border-brand-green/30 text-brand-green'
                      : 'bg-brand-red/15 border-brand-red/30 text-brand-red'
                  }`}
                >
                  {(rankDelta(hex) ?? 0) > 0 ? '↑' : '↓'}
                  {Math.abs(rankDelta(hex) ?? 0)}
                </span>
              )}
            </div>
            <p className="text-[11px] text-apple-secondary mt-2.5 leading-snug text-center">
              {confPct != null && confPct < 55
                ? `Moved due to ${confPct < 30 ? 'very low' : 'low'} attribution confidence (${confPct}%).`
                : confPct != null && confPct >= 80
                  ? `Held or rose with high confidence (${confPct}%).`
                  : `Confidence ${confPct ?? '—'}% · factor ×${(hex.riskConfidenceFactor ?? 0).toFixed(2) || '—'}.`}
            </p>
            <div className="mt-2 flex justify-center gap-4 text-[11px] font-mono">
              <span className="text-apple-secondary">
                Base <span className="text-white font-bold">{hex.score10.toFixed(1)}</span>/10
              </span>
              <span className="text-brand-blue">
                Risk-adj{' '}
                <span className="font-bold">
                  {(hex.riskAdjustedScore10 ?? hex.score10).toFixed(1)}
                </span>
                /10
              </span>
            </div>
          </div>
        )}

        {/* Attribution confidence — highlighted card */}
        <div
          className="rounded-2xl border px-4 py-3.5"
          style={{
            borderColor: `${confidenceLevelColor(hex.attributionConfidenceLevel, confPct)}55`,
            background: `${confidenceLevelColor(hex.attributionConfidenceLevel, confPct)}12`,
            boxShadow: `0 0 24px ${confidenceLevelColor(hex.attributionConfidenceLevel, confPct)}18`,
          }}
        >
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-white/80">
              <Gauge size={13} style={{ color: confidenceLevelColor(hex.attributionConfidenceLevel, confPct) }} />
              Attribution confidence
            </div>
            <span
              className="text-[10px] font-bold px-2 py-0.5 rounded-full border"
              style={{
                color: confidenceLevelColor(hex.attributionConfidenceLevel, confPct),
                borderColor: `${confidenceLevelColor(hex.attributionConfidenceLevel, confPct)}55`,
                background: `${confidenceLevelColor(hex.attributionConfidenceLevel, confPct)}18`,
              }}
            >
              {hex.attributionConfidenceLevel || '—'}
            </span>
          </div>
          <div className="flex items-end gap-2">
            <span
              className="text-3xl font-mono font-bold leading-none"
              style={{ color: confidenceLevelColor(hex.attributionConfidenceLevel, confPct) }}
            >
              {confPct != null ? confPct : '—'}
              <span className="text-lg">%</span>
            </span>
            {hex.riskConfidenceFactor != null && (
              <span className="text-[10px] font-mono text-apple-secondary pb-0.5">
                ranking factor ×{hex.riskConfidenceFactor.toFixed(2)}
              </span>
            )}
          </div>
          {hex.confidenceExplanation && (
            <p className="text-[12px] text-white/85 mt-2 leading-snug font-medium">
              {hex.confidenceExplanation}
            </p>
          )}
          {hex.nearestStationDistanceM != null && (
            <p className="text-[10px] font-mono text-white/45 mt-1.5">
              Nearest station · {(hex.nearestStationDistanceM / 1000).toFixed(1)} km
            </p>
          )}
        </div>

        {/* Bounded what-if: construction intensity */}
        <div className="rounded-2xl bg-gradient-to-br from-brand-orange/10 to-brand-blue/5 border border-brand-orange/30 p-4 space-y-3 shadow-lg shadow-brand-orange/5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-brand-orange font-bold">
              <SlidersHorizontal size={13} />
              What-if analysis
            </div>
            <span className="text-[9px] font-mono text-apple-secondary bg-black/30 px-2 py-0.5 rounded-full border border-white/10">
              Local only
            </span>
          </div>
          <p className="text-[11px] text-apple-secondary leading-snug">
            Scale construction activity on this hex. Fused PM2.5 held constant — not a full
            emissions model.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {[
              { label: '−50% construction', pct: 50 },
              { label: 'Baseline', pct: 100 },
              { label: '+100% construction', pct: 200 },
            ].map((p) => (
              <button
                key={p.pct}
                type="button"
                onClick={() => {
                  setConstructionPct(p.pct);
                  void import('../../services/persistenceService').then(({ logAuditEvent }) => {
                    void logAuditEvent('whatif_construction_preset', {
                      hexId: hex.id,
                      constructionPct: p.pct,
                      location: location,
                    });
                  });
                }}
                className={`px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider border transition-colors ${
                  constructionPct === p.pct
                    ? 'bg-brand-orange/20 border-brand-orange text-brand-orange'
                    : 'bg-black/25 border-white/10 text-apple-secondary hover:text-white'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={0}
              max={200}
              step={10}
              value={constructionPct}
              onChange={(e) => setConstructionPct(Number(e.target.value))}
              className="flex-1 accent-brand-orange"
              aria-label="Construction activity scale percent"
            />
            <span className="font-mono text-sm font-bold text-white w-12 text-right">
              {constructionPct}%
            </span>
          </div>
          <div className="rounded-xl bg-black/40 border border-white/10 px-3 py-3 text-center">
            <div className="text-[9px] font-mono uppercase tracking-wider text-apple-secondary mb-1">
              Priority score · before → after
            </div>
            <div className="flex items-center justify-center gap-3">
              <span className="font-mono text-2xl font-bold text-white/70">
                {hex.score10.toFixed(1)}
              </span>
              <span className="text-apple-secondary text-lg">→</span>
              <span
                className={`font-mono text-2xl font-bold ${
                  counterfactual.score10 < hex.score10
                    ? 'text-brand-green'
                    : counterfactual.score10 > hex.score10
                      ? 'text-brand-orange'
                      : 'text-white'
                }`}
              >
                {counterfactual.score10.toFixed(1)}
              </span>
            </div>
            <p className="text-[10px] text-apple-secondary mt-2">
              Construction share → {(counterfactual.sourceAttribution.construction * 100).toFixed(0)}%
              · Mag {counterfactual.magnitude}
            </p>
          </div>
          <p className="text-[10px] text-apple-secondary/90 leading-snug border-t border-white/8 pt-2">
            This is a <strong className="text-white/80">local simulation only</strong>. City-wide
            re-ranking is not applied.
          </p>
          <details className="text-[10px] text-apple-secondary/80">
            <summary className="cursor-pointer text-white/60 hover:text-white">Assumptions</summary>
            <ul className="mt-1 list-disc pl-4 space-y-0.5">
              {counterfactual.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </details>
        </div>

        {/* Attribution chart — full 4-source mix always shown */}
        <div className="bg-apple-card/60 border border-apple-border rounded-xl p-4">
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-apple-secondary">
              Source Attribution
            </span>
            <span className="text-[9px] font-mono text-apple-secondary/70">
              T {(hex.sourceAttribution.traffic * 100).toFixed(0)}% · C{' '}
              {(hex.sourceAttribution.construction * 100).toFixed(0)}% · I{' '}
              {(hex.sourceAttribution.industrial * 100).toFixed(0)}% · B{' '}
              {(hex.sourceAttribution.burning * 100).toFixed(0)}%
            </span>
          </div>
          <Suspense
            fallback={
              <div className="h-40 flex items-center justify-center text-xs text-apple-secondary">
                Loading chart…
              </div>
            }
          >
            <AttributionChart
              hex={hex}
              highlightTraffic={Boolean(hex.isTrafficCorridor || hex.isMajorRoadCorridor)}
            />
          </Suspense>
        </div>

        {/* Recommendations */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Shield size={14} className="text-brand-blue" />
            <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-brand-blue">
              Enforcement Recommendations
            </span>
          </div>
          {recs.map((rec) => (
            <div
              key={rec.title}
              className="bg-apple-card/60 border border-apple-border rounded-xl p-3 space-y-2"
            >
              <div className="flex items-center justify-between gap-2">
                <h4 className="text-xs font-bold text-white">{rec.title}</h4>
                <span
                  className={`text-[8px] font-bold px-1.5 py-0.5 rounded border ${actionTierStyles(rec.urgency).bg}`}
                >
                  {actionTierLabel(rec.urgency)}
                </span>
              </div>
              <ul className="space-y-1">
                {rec.actions.map((a) => (
                  <li key={a} className="text-[11px] text-apple-secondary leading-relaxed flex gap-1.5">
                    <span className="text-brand-blue shrink-0">•</span>
                    {a}
                  </li>
                ))}
              </ul>
              <p className="text-[10px] text-apple-secondary/80 italic">{rec.estimatedImpact}</p>
            </div>
          ))}
          {hex.explanation?.text && (
            <div className="bg-apple-card/40 border border-brand-blue/15 rounded-xl p-3">
              <p className="text-[10px] text-apple-secondary leading-relaxed">
                {hex.explanation.text}
              </p>
              {hex.explanation.generated_by === 'llm' && (
                <span className="text-[8px] font-mono text-brand-blue/60 mt-1 inline-block">AI guidance</span>
              )}
            </div>
          )}
        </div>

        {/* Evidence metadata */}
        <div className="bg-black/30 border border-apple-border/60 rounded-xl p-3 space-y-1.5">
          <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-apple-secondary">
            <Database size={12} /> Evidence & metadata
          </div>
          <p className="text-[10px] text-apple-secondary leading-relaxed">
            Sources: CPCB/KSPCB stations · OSM land-use & roads · Sentinel-5P NO₂ (attribution path) ·
            FIRMS when available. Corridor:{' '}
            {hex.trafficCorridorApplied ? 'applied' : 'not applied / unavailable'}. TOD multiplier:{' '}
            {hex.trafficTimeMultiplier ?? '—'}
            {hex.isPeakHour ? ' (peak)' : ''}.
          </p>
          <p className="text-[9px] font-mono text-apple-secondary/70 truncate">Cell {hex.id}</p>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2 justify-end">
          <button
            type="button"
            onClick={copyReport}
            className="px-4 py-2.5 rounded-full text-[10px] font-bold uppercase tracking-wider border border-apple-border bg-apple-card text-white hover:bg-apple-border/30 flex items-center gap-1.5"
          >
            <FileText size={12} />
            {copied ? 'Copied' : 'Copy Brief'}
          </button>
          <button
            type="button"
            onClick={onDispatch}
            disabled={dispatched}
            className={`px-5 py-2.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-colors flex items-center gap-1.5 shadow-md ${
              dispatched
                ? 'bg-brand-green/20 text-brand-green border border-brand-green/30 cursor-not-allowed'
                : 'bg-brand-blue hover:bg-blue-600 text-white'
            }`}
          >
            {dispatched ? (
              <>
                <ShieldCheck size={12} /> Dispatched
              </>
            ) : (
              <>
                <ShieldAlert size={12} /> Dispatch Unit
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
