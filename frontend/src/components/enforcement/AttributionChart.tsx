import React from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { PriorityHex } from '../../types';
import { SOURCE_KEYS, SOURCE_LABELS } from '../../services/enforcementUtils';

const COLORS: Record<string, string> = {
  construction: '#FF9F0A',
  traffic: '#0A84FF',
  industrial: '#ff453a',
  burning: '#af52de',
};

interface AttributionChartProps {
  hex: PriorityHex;
  /** When true, emphasize the traffic share (corridor hexes). */
  highlightTraffic?: boolean;
}

export default function AttributionChart({ hex, highlightTraffic = false }: AttributionChartProps) {
  // Always show all four sources (even 0%) so judges see the full mix.
  const data = SOURCE_KEYS.map((key) => ({
    key,
    name: SOURCE_LABELS[key],
    value: Math.round((hex.sourceAttribution[key] ?? 0) * 1000) / 10,
  }));

  const hasAny = data.some((d) => d.value > 0);
  if (!hasAny) {
    return (
      <div className="h-40 flex items-center justify-center text-xs text-apple-secondary">
        No source attribution available
      </div>
    );
  }

  // Pie only plots positive slices; legend/bar still show zeros.
  const pieData = data.filter((d) => d.value > 0);
  const trafficPct = data.find((d) => d.key === 'traffic')?.value ?? 0;

  return (
    <div className="w-full">
      {highlightTraffic && (
        <div className="mb-3 flex items-center justify-between gap-2 rounded-xl bg-brand-blue/10 border border-brand-blue/25 px-3 py-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-brand-blue">
            Traffic share on this corridor
          </span>
          <span className="font-mono text-sm font-bold text-brand-blue">{trafficPct}%</span>
        </div>
      )}

      <div className="h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={pieData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={42}
              outerRadius={68}
              paddingAngle={2}
              stroke="transparent"
            >
              {pieData.map((entry) => (
                <Cell
                  key={entry.key}
                  fill={COLORS[entry.key] || '#8E8E93'}
                  stroke={
                    highlightTraffic && entry.key === 'traffic' ? '#ffffff' : 'transparent'
                  }
                  strokeWidth={highlightTraffic && entry.key === 'traffic' ? 2 : 0}
                />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: '#1C1C1E',
                border: '1px solid #38383A',
                borderRadius: 8,
                fontSize: 11,
              }}
              formatter={(value) => [`${value ?? 0}%`, 'Share']}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Stacked bar — always full width 4-way mix (zeros take no space) */}
      <div className="mt-2 h-2.5 w-full rounded-full overflow-hidden flex bg-apple-border">
        {data.map((d) =>
          d.value > 0 ? (
            <div
              key={d.key}
              style={{
                width: `${d.value}%`,
                backgroundColor: COLORS[d.key],
                boxShadow:
                  highlightTraffic && d.key === 'traffic'
                    ? '0 0 0 1px rgba(255,255,255,0.5)'
                    : undefined,
              }}
              title={`${d.name}: ${d.value}%`}
            />
          ) : null,
        )}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        {data.map((d) => {
          const isTraffic = d.key === 'traffic';
          const emphasize = highlightTraffic && isTraffic;
          return (
            <div
              key={d.key}
              className={`flex items-center gap-2 text-[11px] rounded-lg px-2 py-1.5 ${
                emphasize ? 'bg-brand-blue/15 border border-brand-blue/30' : ''
              }`}
            >
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: COLORS[d.key] }}
              />
              <span className={emphasize ? 'text-brand-blue font-semibold' : 'text-apple-secondary'}>
                {d.name}
              </span>
              <span
                className={`ml-auto font-mono font-semibold ${
                  emphasize ? 'text-brand-blue' : 'text-white'
                }`}
              >
                {d.value}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
