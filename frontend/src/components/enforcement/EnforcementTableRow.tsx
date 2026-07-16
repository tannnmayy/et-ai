import React, { memo } from 'react';
import type { PriorityHex } from '../../types';
import SourceIcon from '../SourceIcon';
import {
  actionTierStyles,
  formatHexIdSubtitle,
  formatLocationName,
  rankDelta,
} from '../../services/enforcementUtils';

interface Props {
  item: PriorityHex;
  isSelected: boolean;
  onSelect: (hex: PriorityHex) => void;
  /** When true, show base + risk-adjusted scores and rank-change badges */
  riskAdjusted?: boolean;
}

function RankChangeBadge({ delta }: { delta: number }) {
  if (delta === 0) return null;
  const up = delta > 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-[9px] font-bold px-1.5 py-0.5 rounded-full border ml-1 ${
        up
          ? 'bg-brand-green/15 border-brand-green/35 text-brand-green'
          : 'bg-brand-red/15 border-brand-red/35 text-brand-red'
      }`}
      title={
        up
          ? `Rose ${delta} places vs base ranking`
          : `Fell ${Math.abs(delta)} places vs base ranking`
      }
    >
      {up ? '↑' : '↓'}
      {Math.abs(delta)}
    </span>
  );
}

function EnforcementTableRow({ item, isSelected, onSelect, riskAdjusted = false }: Props) {
  const actionStyle = actionTierStyles(item.actionTier);
  const loc = formatLocationName(item);
  const delta = riskAdjusted ? rankDelta(item) : null;
  const significantMove = delta != null && Math.abs(delta) >= 2;
  const gridCols = riskAdjusted
    ? 'grid-cols-[52px_minmax(0,1.3fr)_68px_64px_72px_64px_72px_96px]'
    : 'grid-cols-[44px_minmax(0,1.4fr)_72px_88px_72px_80px_100px]';

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(item)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(item);
        }
      }}
      className={`group grid ${gridCols} gap-2 items-center rounded-2xl cursor-pointer transition-colors duration-150 py-2.5 px-2 relative overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-brand-blue active:scale-[0.99] ${
        isSelected
          ? 'ui-glass ui-glass-subtle border border-brand-blue/35 shadow-lg shadow-brand-blue/10'
          : significantMove
            ? 'bg-apple-card/50 hover:bg-apple-card/80 border border-brand-blue/15'
            : 'bg-apple-card/40 hover:bg-apple-card/70 border border-transparent hover:border-white/8'
      }`}
    >
      {isSelected && (
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-brand-blue" />
      )}

      <div className="font-mono text-xs font-bold text-apple-secondary text-right pr-1 flex flex-col items-end gap-0.5">
        <span className="text-white">{String(item.rank).padStart(2, '0')}</span>
        {riskAdjusted && delta != null && Math.abs(delta) > 0 && (
          <RankChangeBadge delta={delta} />
        )}
      </div>

      <div className="flex items-center gap-2 pl-1 min-w-0">
        <div
          className="w-2 h-2 shrink-0 rounded-full"
          style={{ backgroundColor: actionStyle.mapColor }}
        />
        <div className="min-w-0">
          <div
            className="text-xs font-bold text-white truncate"
            title={`${loc} · ${formatHexIdSubtitle(item)}`}
          >
            {loc}
          </div>
          {(item.isTrafficCorridor || item.isMajorRoadCorridor) && (
            <div className="text-[9px] text-brand-blue font-semibold truncate flex items-center gap-1">
              <span className="w-1 h-1 rounded-full bg-brand-blue shrink-0" />
              Major Traffic Corridor
            </div>
          )}
          {riskAdjusted && item.baseRank != null && item.baseRank !== item.rank && (
            <div className="text-[9px] text-apple-secondary font-mono truncate">
              was #{String(item.baseRank).padStart(2, '0')} base
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 min-w-0 text-[10px] font-semibold text-apple-secondary">
        <SourceIcon sourceType={item.primarySource} size={12} />
        <span className="truncate">{item.primarySource}</span>
      </div>

      {riskAdjusted ? (
        <>
          <div className="font-mono text-xs text-apple-secondary text-right">
            {item.score10.toFixed(1)}
            <div className="text-[8px] uppercase tracking-wider mt-0.5">base</div>
          </div>
          <div className="font-mono text-sm font-bold text-brand-blue text-right">
            {(item.riskAdjustedScore10 ?? item.score10).toFixed(1)}
            <div className="text-[8px] uppercase tracking-wider mt-0.5 text-brand-blue/70">
              risk-adj
            </div>
          </div>
        </>
      ) : (
        <div className="font-mono text-sm font-bold text-white text-right">
          {item.score10.toFixed(1)}
          <span className="text-[9px] text-apple-secondary font-normal">/10</span>
        </div>
      )}

      <div className="text-[11px] font-semibold text-apple-secondary text-right">
        {item.exposure}
      </div>

      <div className="font-mono text-xs text-white text-right">
        {item.magnitude}
        <div className="text-[9px] text-apple-secondary mt-0.5">intensity</div>
      </div>

      <div className="flex justify-end items-center pr-1">
        <div
          className={`flex items-center gap-1 px-2 py-1 rounded-full border text-[8px] font-bold select-none whitespace-nowrap ${actionStyle.bg}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${actionStyle.dot}`} />
          {actionStyle.text}
        </div>
      </div>
    </div>
  );
}

function propsEqual(prev: Props, next: Props): boolean {
  return (
    prev.isSelected === next.isSelected &&
    prev.riskAdjusted === next.riskAdjusted &&
    prev.item.id === next.item.id &&
    prev.item.rank === next.item.rank &&
    prev.item.baseRank === next.item.baseRank &&
    prev.item.score10 === next.item.score10 &&
    prev.item.riskAdjustedScore10 === next.item.riskAdjustedScore10 &&
    prev.item.actionTier === next.item.actionTier &&
    prev.item.primarySource === next.item.primarySource &&
    prev.item.exposure === next.item.exposure &&
    prev.item.magnitude === next.item.magnitude &&
    prev.item.isMajorRoadCorridor === next.item.isMajorRoadCorridor &&
    prev.item.isTrafficCorridor === next.item.isTrafficCorridor &&
    prev.onSelect === next.onSelect
  );
}

export default memo(EnforcementTableRow, propsEqual);
