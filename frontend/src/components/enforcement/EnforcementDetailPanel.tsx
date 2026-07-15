import React, { Suspense, lazy, useState } from 'react';
import {
  ShieldAlert,
  Shield,
  ShieldCheck,
  X,
  Car,
  FileText,
  Clock,
  Database,
} from 'lucide-react';
import type { PriorityHex } from '../../types';
import SourceIcon from '../SourceIcon';
import {
  actionTierLabel,
  actionTierStyles,
  buildRecommendations,
  formatHexIdSubtitle,
  formatLocationName,
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
  const tierStyle = actionTierStyles(hex.actionTier);
  const recs = buildRecommendations(hex);
  const location = formatLocationName(hex);

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
      className="p-4 sm:p-5 bg-apple-modal/95 border-t border-apple-border backdrop-blur-xl z-20 shadow-2xl relative max-h-[55%] overflow-y-auto"
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
