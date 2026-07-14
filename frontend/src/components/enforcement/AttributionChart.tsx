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
}

export default function AttributionChart({ hex }: AttributionChartProps) {
  const data = SOURCE_KEYS.map((key) => ({
    key,
    name: SOURCE_LABELS[key],
    value: Math.round((hex.sourceAttribution[key] ?? 0) * 1000) / 10,
  })).filter((d) => d.value > 0);

  if (data.length === 0) {
    return (
      <div className="h-40 flex items-center justify-center text-xs text-apple-secondary">
        No source attribution available
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={42}
              outerRadius={68}
              paddingAngle={2}
              stroke="transparent"
            >
              {data.map((entry) => (
                <Cell key={entry.key} fill={COLORS[entry.key] || '#8E8E93'} />
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

      {/* Stacked bar alternative / legend */}
      <div className="mt-2 h-2.5 w-full rounded-full overflow-hidden flex bg-apple-border">
        {data.map((d) => (
          <div
            key={d.key}
            style={{ width: `${d.value}%`, backgroundColor: COLORS[d.key] }}
            title={`${d.name}: ${d.value}%`}
          />
        ))}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {data.map((d) => (
          <div key={d.key} className="flex items-center gap-2 text-[11px]">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: COLORS[d.key] }}
            />
            <span className="text-apple-secondary">{d.name}</span>
            <span className="ml-auto font-mono text-white font-semibold">{d.value}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
