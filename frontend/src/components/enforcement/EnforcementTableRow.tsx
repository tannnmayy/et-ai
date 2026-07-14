import React, { memo } from 'react';
import type { PriorityHex } from '../../types';
import SourceIcon from '../SourceIcon';
import {
  actionTierStyles,
  formatLocationName,
} from '../../services/enforcementUtils';

interface Props {
  item: PriorityHex;
  isSelected: boolean;
  onSelect: (hex: PriorityHex) => void;
}

function EnforcementTableRow({ item, isSelected, onSelect }: Props) {
  const actionStyle = actionTierStyles(item.actionTier);
  const loc = formatLocationName(item);

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
      className={`group grid grid-cols-[44px_minmax(0,1.4fr)_72px_88px_72px_80px_100px] gap-2 items-center rounded-xl cursor-pointer transition-all duration-200 py-2.5 px-1 relative overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-brand-blue ${
        isSelected
          ? 'bg-apple-card border border-brand-blue/30 shadow-lg'
          : 'bg-apple-card/40 hover:bg-apple-card border border-transparent'
      }`}
    >
      {isSelected && (
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-brand-blue" />
      )}

      <div className="font-mono text-xs font-bold text-apple-secondary text-right pr-1">
        {String(item.rank).padStart(2, '0')}
      </div>

      <div className="flex items-center gap-2 pl-1 min-w-0">
        <div
          className="w-2 h-2 shrink-0 rounded-full"
          style={{ backgroundColor: actionStyle.mapColor }}
        />
        <div className="min-w-0">
          <div className="text-xs font-bold text-white truncate" title={item.name}>
            {loc}
          </div>
          {item.isMajorRoadCorridor && (
            <div className="text-[9px] text-brand-blue truncate">Corridor</div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 min-w-0 text-[10px] font-semibold text-apple-secondary">
        <SourceIcon sourceType={item.primarySource} size={12} />
        <span className="truncate">{item.primarySource}</span>
      </div>

      <div className="font-mono text-sm font-bold text-white text-right">
        {item.score10.toFixed(1)}
        <span className="text-[9px] text-apple-secondary font-normal">/10</span>
      </div>

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
    prev.item.id === next.item.id &&
    prev.item.rank === next.item.rank &&
    prev.item.score10 === next.item.score10 &&
    prev.item.actionTier === next.item.actionTier &&
    prev.item.primarySource === next.item.primarySource &&
    prev.item.exposure === next.item.exposure &&
    prev.item.magnitude === next.item.magnitude &&
    prev.item.isMajorRoadCorridor === next.item.isMajorRoadCorridor &&
    prev.onSelect === next.onSelect
  );
}

export default memo(EnforcementTableRow, propsEqual);
