import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  BarChart3,
  Building2,
  Clock,
  Info,
  MapPin,
  RefreshCw,
  Sparkles,
  AlertTriangle,
  Home,
  Layers,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useCityInsights } from '../api/client';
import type {
  AblationStudiesInsight,
  BeforeAfterInsight,
  FailureModesInsight,
  PredictabilityMapInsight,
  RentVsAirInsight,
  RushHourFlipInsight,
  SensorBlindSpotsInsight,
  TargetedEnforcementInsight,
} from '../services/insightsService';
import { SpringButton } from '../components/ui';

function GlassCard({
  children,
  className = '',
  hero = false,
}: {
  children: React.ReactNode;
  className?: string;
  hero?: boolean;
}) {
  return (
    <div
      className={`ui-glass rounded-3xl ${
        hero
          ? 'ui-glass-strong border-brand-blue/35 shadow-lg shadow-brand-blue/10'
          : 'ui-glass-subtle'
      } ${className}`}
    >
      {children}
    </div>
  );
}

function MethodNote({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <div className="mt-4 flex items-start gap-2 rounded-2xl bg-white/[0.03] border border-white/8 px-3.5 py-2.5">
      <Info size={13} className="text-apple-secondary shrink-0 mt-0.5" />
      <p className="text-[11px] leading-relaxed text-apple-secondary">
        <span className="font-semibold text-white/70">How we calculated this · </span>
        {text}
      </p>
    </div>
  );
}

function InsightBadge({ n, label }: { n: number; label: string }) {
  return (
    <div className="inline-flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em] text-brand-blue">
      <span className="w-5 h-5 rounded-lg bg-brand-blue/15 border border-brand-blue/30 flex items-center justify-center text-[10px] font-bold">
        {n}
      </span>
      {label}
    </div>
  );
}

function UnavailableCard({ title, reason }: { title: string; reason?: string }) {
  return (
    <GlassCard className="p-6">
      <div className="flex items-center gap-2 text-apple-secondary mb-2">
        <AlertTriangle size={16} />
        <h2 className="text-lg font-bold text-white/80">{title}</h2>
      </div>
      <p className="text-sm text-apple-secondary">
        {reason || 'This insight is temporarily unavailable.'}
      </p>
    </GlassCard>
  );
}

function formatInr(n: number) {
  return `₹${Math.round(n).toLocaleString('en-IN')}`;
}

function pct(n: number, digits = 0) {
  return `${n.toFixed(digits)}%`;
}

/* ─── Insight 1: Rush-Hour Personality Flip ─── */
function RushHourFlipCard({ data }: { data: RushHourFlipInsight }) {
  if (!data.available || !data.series?.length) {
    return <UnavailableCard title="The Rush-Hour Personality Flip" reason={data.reason} />;
  }

  const chartData = data.series.map((s) => ({
    label: s.label,
    Traffic: Math.round(s.traffic * 100),
    Industrial: Math.round(s.industrial * 100),
    Construction: Math.round(s.construction * 100),
    Burning: Math.round(s.burning * 100),
    dominant: s.dominant,
  }));

  return (
    <GlassCard hero className="p-6 md:p-8">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-5">
        <div className="max-w-2xl">
          <InsightBadge n={1} label="Hero insight · Time-of-day attribution" />
          <h2 className="text-2xl md:text-3xl font-bold text-white tracking-tight mt-3">
            {data.headline || 'The Rush-Hour Personality Flip'}
          </h2>
          <p className="text-sm md:text-base text-apple-secondary mt-3 leading-relaxed">
            {data.finding}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 lg:flex-col lg:items-end shrink-0">
          <StatPill
            label="8 AM traffic"
            value={pct(data.traffic_am_pct ?? 0)}
            accent="text-brand-blue"
          />
          <StatPill
            label="2 AM traffic"
            value={pct(data.traffic_night_pct ?? 0)}
            accent="text-brand-orange"
          />
          <StatPill
            label="Flip"
            value={`${(data.flip_pp ?? 0) > 0 ? '−' : ''}${Math.abs(data.flip_pp ?? 0).toFixed(0)} pp`}
            accent="text-brand-green"
          />
        </div>
      </div>

      <div className="h-64 md:h-72 rounded-2xl bg-black/30 border border-white/8 p-3 md:p-4">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
            <defs>
              <linearGradient id="gTraffic" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0A84FF" stopOpacity={0.45} />
                <stop offset="100%" stopColor="#0A84FF" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="gConstruct" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#BF5AF2" stopOpacity={0.4} />
                <stop offset="100%" stopColor="#BF5AF2" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#38383A" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: '#8E8E93', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              unit="%"
              domain={[0, 100]}
              tick={{ fill: '#8E8E93', fontSize: 10, fontFamily: 'JetBrains Mono' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: '#1C1C1E',
                border: '1px solid #38383A',
                borderRadius: 12,
                fontSize: 12,
              }}
              formatter={(v: number) => [`${v}%`, '']}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: '#8E8E93' }} />
            <Area
              type="monotone"
              dataKey="Traffic"
              stroke="#0A84FF"
              fill="url(#gTraffic)"
              strokeWidth={2.5}
            />
            <Area
              type="monotone"
              dataKey="Construction"
              stroke="#BF5AF2"
              fill="url(#gConstruct)"
              strokeWidth={2}
            />
            <Area
              type="monotone"
              dataKey="Industrial"
              stroke="#FF9F0A"
              fill="transparent"
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
            <Area
              type="monotone"
              dataKey="Burning"
              stroke="#ff453a"
              fill="transparent"
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2">
        {data.series.map((s) => (
          <div
            key={s.hour}
            className="rounded-2xl bg-white/[0.04] border border-white/10 px-3 py-2.5"
          >
            <div className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary">
              {s.label}
            </div>
            <div className="text-sm font-bold text-white mt-1 capitalize">
              {s.dominant}
            </div>
            <div className="text-[11px] font-mono text-brand-blue mt-0.5">
              {Math.round(s.traffic * 100)}% traffic
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-apple-secondary">
        <span className="inline-flex items-center gap-1.5">
          <MapPin size={12} className="text-brand-blue" />
          {data.location_name}
        </span>
        <span className="font-mono text-white/40">{data.h3_cell}</span>
        {data.corridor_score != null && (
          <span>Corridor score {data.corridor_score.toFixed(2)}</span>
        )}
      </div>
      <MethodNote text={data.method_note} />
    </GlassCard>
  );
}

function StatPill({
  label,
  value,
  accent = 'text-white',
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="rounded-2xl bg-white/[0.05] border border-white/10 px-4 py-2.5 min-w-[120px]">
      <div className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary">
        {label}
      </div>
      <div className={`text-xl font-bold font-mono tracking-tight mt-0.5 ${accent}`}>{value}</div>
    </div>
  );
}

/* ─── Insight 2: Sensor Blind Spots ─── */
function SensorBlindSpotsCard({ data }: { data: SensorBlindSpotsInsight }) {
  if (!data.available) {
    return <UnavailableCard title="Sensor Blind Spots" reason={data.reason} />;
  }
  const gaps = data.severe_gaps || [];

  return (
    <GlassCard className="p-6 md:p-7">
      <InsightBadge n={2} label="Trust layer · Official data integrity" />
      <h2 className="text-xl md:text-2xl font-bold text-white mt-3">
        {data.headline || 'Sensor Blind Spots'}
      </h2>
      <p className="text-sm text-apple-secondary mt-2.5 leading-relaxed max-w-3xl">
        {data.finding}
      </p>

      {gaps.length > 0 ? (
        <div className="mt-5 overflow-x-auto rounded-2xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="bg-white/[0.04] text-[10px] font-mono uppercase tracking-wider text-apple-secondary">
                <th className="px-4 py-3 font-medium">Station export</th>
                <th className="px-4 py-3 font-medium text-right">Rows</th>
                <th className="px-4 py-3 font-medium text-right">Valid PM2.5</th>
                <th className="px-4 py-3 font-medium text-right">Missing</th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((g) => (
                <tr key={g.file} className="border-t border-white/8 hover:bg-white/[0.02]">
                  <td className="px-4 py-3">
                    <div className="text-white font-medium truncate max-w-[220px]">
                      {g.station_hint}
                    </div>
                    <div className="text-[10px] font-mono text-apple-secondary truncate max-w-[220px]">
                      {g.file}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-white/80">
                    {g.rows.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-white/80">
                    {g.pm25_valid.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span
                      className={`font-mono font-bold ${
                        g.pm25_missing_pct >= 90
                          ? 'text-brand-red'
                          : g.pm25_missing_pct >= 70
                            ? 'text-brand-orange'
                            : 'text-white'
                      }`}
                    >
                      {pct(g.pm25_missing_pct, 1)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-5 rounded-2xl bg-white/[0.03] border border-white/10 p-4 text-sm text-apple-secondary">
          No severe (≥50% missing) PM2.5 gaps found in scanned station files.
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-3 text-[11px] text-apple-secondary">
        <span className="inline-flex items-center gap-1.5">
          <Activity size={12} className="text-brand-blue" />
          {data.station_files_scanned ?? 0} station files scanned
        </span>
        <span>{gaps.length} severe gaps surfaced</span>
      </div>
      <MethodNote text={data.method_note} />
    </GlassCard>
  );
}

function uncertaintyFromRmse(rmse: number | null | undefined): {
  level: 'Low' | 'Medium' | 'High';
  color: string;
  reason: string;
} {
  const r = Number(rmse ?? 99);
  if (r < 12) {
    return { level: 'Low', color: '#34C759', reason: `Test RMSE ${r.toFixed(1)} µg/m³ (<12)` };
  }
  if (r < 22) {
    return { level: 'Medium', color: '#FF9F0A', reason: `Test RMSE ${r.toFixed(1)} µg/m³ (12–22)` };
  }
  return { level: 'High', color: '#ff453a', reason: `Test RMSE ${r.toFixed(1)} µg/m³ (>22)` };
}

/* ─── Insight 3: Predictability Map ─── */
function PredictabilityMapCard({ data }: { data: PredictabilityMapInsight }) {
  if (!data.available || !data.stations?.length) {
    return <UnavailableCard title="The Predictability Map" reason={data.reason} />;
  }

  const chartData = data.stations.map((s) => ({
    name: s.display_name.replace(/CPCB |KSPCB /gi, '').slice(0, 18),
    improvement: Number(s.rmse_improvement_percent ?? 0),
    winner: s.winner,
  }));

  const withUncertainty = data.stations.map((s) => {
    const selectedRmse =
      s.winner === 'lightgbm'
        ? (s.lightgbm_rmse ?? s.persistence_rmse)
        : (s.persistence_rmse ?? s.lightgbm_rmse);
    return { ...s, selectedRmse, unc: uncertaintyFromRmse(selectedRmse) };
  });
  const highUnc = withUncertainty.filter((s) => s.unc.level === 'High');

  return (
    <GlassCard className="p-6 md:p-7 h-full">
      <InsightBadge n={3} label="Model behaviour · LightGBM vs persistence" />
      <h2 className="text-xl md:text-2xl font-bold text-white mt-3">
        {data.headline || 'The Predictability Map'}
      </h2>
      <p className="text-sm text-apple-secondary mt-2.5 leading-relaxed">{data.finding}</p>

      {highUnc.length > 0 && (
        <div className="mt-3 rounded-xl border border-brand-red/30 bg-brand-red/10 px-3.5 py-2.5">
          <div className="text-[10px] font-mono uppercase tracking-wider text-brand-red font-bold mb-1">
            High forecast uncertainty
          </div>
          <p className="text-[12px] text-white/85 leading-snug">
            {highUnc.map((s) => s.display_name.replace(/CPCB |KSPCB /gi, '')).join(' · ')} — point
            forecasts should be read with RMSE intervals, not as certain values.
          </p>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <StatPill
          label="LightGBM wins"
          value={String(data.lgbm_wins ?? 0)}
          accent="text-brand-blue"
        />
        <StatPill
          label="Persistence wins"
          value={String(data.persistence_wins ?? 0)}
          accent="text-brand-orange"
        />
        <StatPill
          label="Overall RMSE Δ"
          value={`${Number(data.overall_rmse_improvement_percent ?? 0).toFixed(1)}%`}
          accent="text-brand-green"
        />
      </div>

      <div className="h-52 mt-5 rounded-2xl bg-black/30 border border-white/8 p-3">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 28 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#38383A" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fill: '#8E8E93', fontSize: 9 }}
              axisLine={false}
              tickLine={false}
              interval={0}
              angle={-25}
              textAnchor="end"
              height={50}
            />
            <YAxis
              unit="%"
              tick={{ fill: '#8E8E93', fontSize: 10, fontFamily: 'JetBrains Mono' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: '#1C1C1E',
                border: '1px solid #38383A',
                borderRadius: 12,
                fontSize: 12,
              }}
              formatter={(v: number, _n, props: any) => [
                `${v.toFixed(1)}% RMSE improvement`,
                props?.payload?.winner === 'lightgbm' ? 'LightGBM' : 'Persistence',
              ]}
            />
            <Bar dataKey="improvement" radius={[8, 8, 4, 4]}>
              {chartData.map((row, i) => (
                <Cell
                  key={i}
                  fill={row.winner === 'lightgbm' ? '#0A84FF' : '#FF9F0A'}
                  fillOpacity={0.9}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
        {withUncertainty.map((s) => (
          <div
            key={s.station_id}
            className="rounded-2xl bg-white/[0.04] border border-white/10 px-3 py-2.5"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-white truncate">
                {s.display_name}
              </span>
              <span
                className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                  s.winner === 'lightgbm'
                    ? 'text-brand-blue border-brand-blue/30 bg-brand-blue/10'
                    : 'text-brand-orange border-brand-orange/30 bg-brand-orange/10'
                }`}
              >
                {s.winner}
              </span>
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span
                className="text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border"
                style={{
                  color: s.unc.color,
                  borderColor: `${s.unc.color}55`,
                  background: `${s.unc.color}18`,
                }}
                title={s.unc.reason}
              >
                Uncertainty · {s.unc.level}
              </span>
              {s.selectedRmse != null && (
                <span className="text-[10px] font-mono text-apple-secondary">
                  RMSE {Number(s.selectedRmse).toFixed(1)}
                </span>
              )}
            </div>
            {s.unc.level === 'High' && (
              <p className="text-[10px] text-brand-red/90 mt-1 leading-snug">{s.unc.reason}</p>
            )}
            <p className="text-[11px] text-apple-secondary mt-1 leading-snug">
              {s.interpretation}
            </p>
          </div>
        ))}
      </div>
      <MethodNote text={data.method_note} />
    </GlassCard>
  );
}

/* ─── Insight 4: Targeted Enforcement ─── */
function TargetedEnforcementCard({ data }: { data: TargetedEnforcementInsight }) {
  if (!data.available || !data.curve?.length) {
    return <UnavailableCard title="Targeted Enforcement" reason={data.reason} />;
  }

  const top10 = data.curve.find((c) => c.k === 10) || data.curve[0];
  const chartData = data.curve.map((c) => ({
    k: `Top ${c.k}`,
    exposure: c.exposure_share_pct,
    land: c.land_share_of_full_grid_pct,
  }));

  return (
    <GlassCard className="p-6 md:p-7 h-full">
      <InsightBadge n={4} label="Business impact · 80/20 argument" />
      <h2 className="text-xl md:text-2xl font-bold text-white mt-3">
        {data.headline || 'Targeted Enforcement vs Blanket Policy'}
      </h2>
      <p className="text-sm text-apple-secondary mt-2.5 leading-relaxed">{data.finding}</p>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="rounded-2xl bg-brand-blue/10 border border-brand-blue/25 p-4">
          <div className="text-[10px] font-mono uppercase tracking-wider text-brand-blue">
            Top 10 · exposure share
          </div>
          <div className="text-3xl font-bold font-mono text-white mt-1">
            {pct(top10.exposure_share_pct, 2)}
          </div>
          <div className="text-[11px] text-apple-secondary mt-1">
            of actionable pollution mass
          </div>
        </div>
        <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-4">
          <div className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary">
            Top 10 · land share
          </div>
          <div className="text-3xl font-bold font-mono text-brand-orange mt-1">
            {pct(top10.land_share_of_full_grid_pct, 2)}
          </div>
          <div className="text-[11px] text-apple-secondary mt-1">
            of {data.n_grid_hexes?.toLocaleString() ?? '—'} hex city grid
          </div>
        </div>
      </div>

      <div className="h-52 mt-5 rounded-2xl bg-black/30 border border-white/8 p-3">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#38383A" vertical={false} />
            <XAxis
              dataKey="k"
              tick={{ fill: '#8E8E93', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="left"
              unit="%"
              tick={{ fill: '#8E8E93', fontSize: 10, fontFamily: 'JetBrains Mono' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              unit="%"
              tick={{ fill: '#8E8E93', fontSize: 10, fontFamily: 'JetBrains Mono' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: '#1C1C1E',
                border: '1px solid #38383A',
                borderRadius: 12,
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar
              yAxisId="left"
              dataKey="exposure"
              name="Exposure share %"
              fill="#0A84FF"
              radius={[8, 8, 4, 4]}
              fillOpacity={0.85}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="land"
              name="Land share %"
              stroke="#FF9F0A"
              strokeWidth={2.5}
              dot={{ r: 4, fill: '#FF9F0A' }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 text-[11px] text-apple-secondary">
        Scored cells: {data.n_scored_hexes?.toLocaleString() ?? '—'} with fused PM2.5 + magnitude
      </div>
      <MethodNote text={data.method_note} />
    </GlassCard>
  );
}

/* ─── Insight 5: Rent vs Air ─── */
function RentVsAirCard({ data }: { data: RentVsAirInsight }) {
  if (!data.available || !data.expensive_dirty || !data.affordable_clean) {
    return <UnavailableCard title="Rent vs What You Actually Breathe" reason={data.reason} />;
  }

  const dirty = data.expensive_dirty;
  const clean = data.affordable_clean;

  return (
    <GlassCard className="p-6 md:p-7">
      <InsightBadge n={5} label="Citizen Mode bridge · Market vs lungs" />
      <h2 className="text-xl md:text-2xl font-bold text-white mt-3">
        {data.headline || 'Rent vs What You Actually Breathe'}
      </h2>
      <p className="text-sm text-apple-secondary mt-2.5 leading-relaxed max-w-3xl">
        {data.finding}
      </p>

      <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-2xl border border-brand-red/30 bg-brand-red/10 p-5">
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-brand-red">
            <Building2 size={12} />
            Premium · dirtier air
          </div>
          <div className="text-xl font-bold text-white mt-2">{dirty.name}</div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div>
              <div className="text-[10px] text-apple-secondary uppercase tracking-wider">
                Median rent
              </div>
              <div className="text-lg font-mono font-bold text-white">
                {formatInr(dirty.median_rent)}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-apple-secondary uppercase tracking-wider">
                Catchment AQI
              </div>
              <div className="text-lg font-mono font-bold text-brand-red">
                {Math.round(dirty.aqi)}
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-brand-green/30 bg-brand-green/10 p-5">
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-brand-green">
            <Home size={12} />
            Affordable · cleaner air
          </div>
          <div className="text-xl font-bold text-white mt-2">{clean.name}</div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div>
              <div className="text-[10px] text-apple-secondary uppercase tracking-wider">
                Median rent
              </div>
              <div className="text-lg font-mono font-bold text-white">
                {formatInr(clean.median_rent)}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-apple-secondary uppercase tracking-wider">
                Catchment AQI
              </div>
              <div className="text-lg font-mono font-bold text-brand-green">
                {Math.round(clean.aqi)}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-4 text-[11px] text-apple-secondary">
        <span>
          City median AQI{' '}
          <span className="font-mono text-white">{data.city_median_aqi ?? '—'}</span>
        </span>
        <span>
          City median rent{' '}
          <span className="font-mono text-white">
            {data.city_median_rent != null ? formatInr(data.city_median_rent) : '—'}
          </span>
        </span>
        <span>
          {data.localities_compared ?? 0} measured localities ·{' '}
          {(data.rental_listings_dataset ?? 0).toLocaleString()} rental listings
        </span>
      </div>
      <MethodNote text={data.method_note} />
    </GlassCard>
  );
}

function isFailureModeLive(liveExample: string): boolean {
  const t = liveExample.toLowerCase();
  if (t.includes('inactive')) return false;
  if (t.includes('none in registry') || /:\s*none\b/.test(t) || /^0\s+station/.test(t)) {
    return false;
  }
  if (t.includes('active')) return true;
  const m = t.match(/(\d+)\s+station/);
  if (m && Number(m[1]) > 0) return true;
  return false;
}

function FailureModesCard({ data }: { data?: FailureModesInsight }) {
  if (!data?.available || !data.modes?.length) {
    return data?.reason ? (
      <UnavailableCard title="Failure Mode Taxonomy" reason={data.reason} />
    ) : null;
  }
  const n = data.modes.length;
  const liveCount = data.modes.filter((m) => isFailureModeLive(m.live_example)).length;
  return (
    <GlassCard className="p-6 md:p-7">
      <InsightBadge n={7} label="Honesty layer · Known limitations" />
      <h2 className="text-xl md:text-2xl font-bold text-white mt-3">
        {data.headline || 'Formal Failure Mode Taxonomy'}
      </h2>
      <div className="mt-3 inline-flex flex-wrap items-center gap-2">
        <span className="text-sm font-bold text-white bg-white/8 border border-white/15 px-3 py-1.5 rounded-full">
          {n} known failure modes currently handled gracefully
        </span>
        {liveCount > 0 && (
          <span className="text-[11px] font-semibold text-brand-green bg-brand-green/10 border border-brand-green/30 px-2.5 py-1 rounded-full">
            {liveCount} with live signal right now
          </span>
        )}
      </div>
      <p className="text-sm text-apple-secondary mt-2.5 leading-relaxed max-w-3xl">
        {data.finding}
      </p>
      <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-3">
        {data.modes.map((m) => {
          const live = isFailureModeLive(m.live_example);
          return (
            <div
              key={m.id}
              className={`rounded-2xl border p-4 ${
                live
                  ? 'bg-brand-green/[0.06] border-brand-green/25'
                  : 'bg-white/[0.03] border-white/10'
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-bold text-white leading-snug pr-2">{m.name}</h3>
                <div className="flex items-center gap-1.5 shrink-0">
                  {live && (
                    <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider text-brand-green bg-brand-green/15 border border-brand-green/30 px-1.5 py-0.5 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse" />
                      Live
                    </span>
                  )}
                  {m.status_flag && (
                    <span className="text-[9px] font-mono text-brand-orange bg-brand-orange/10 border border-brand-orange/25 px-1.5 py-0.5 rounded-full">
                      {m.status_flag}
                    </span>
                  )}
                </div>
              </div>
              <div className="mt-3 space-y-2.5 text-[11px] leading-relaxed">
                <div>
                  <span className="text-[9px] font-mono uppercase tracking-wider text-apple-secondary">
                    Detection
                  </span>
                  <p className="text-white/80 mt-0.5">{m.detected_by}</p>
                </div>
                <div>
                  <span className="text-[9px] font-mono uppercase tracking-wider text-apple-secondary">
                    Graceful degradation
                  </span>
                  <p className="text-white/80 mt-0.5">{m.degradation}</p>
                </div>
                <div className="rounded-xl bg-black/30 border border-white/8 px-2.5 py-2">
                  <span className="text-[9px] font-mono uppercase tracking-wider text-brand-blue">
                    Real example
                  </span>
                  <p className="text-brand-blue font-medium mt-0.5">{m.live_example}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <MethodNote text={data.method_note} />
    </GlassCard>
  );
}

function AblationStudiesCard({ data }: { data?: AblationStudiesInsight }) {
  if (!data?.available) {
    return data?.reason ? (
      <UnavailableCard title="Ablation Studies" reason={data.reason} />
    ) : null;
  }
  const wind = data.wind_vs_distance;
  const fus = data.fusion_vs_no_fusion;
  return (
    <GlassCard className="p-6 md:p-7">
      <InsightBadge n={8} label="Evaluation rigor · Controlled ablations" />
      <h2 className="text-xl md:text-2xl font-bold text-white mt-3">
        {data.headline || 'Focused Ablation Studies'}
      </h2>
      <p className="text-sm text-apple-secondary mt-2.5 leading-relaxed max-w-3xl">
        {data.finding}
      </p>
      <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
        {wind && (
          <div className="rounded-2xl border border-brand-blue/30 bg-gradient-to-br from-brand-blue/10 to-white/[0.02] p-5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-brand-blue font-bold mb-2">
              Ablation 1 · Attribution physics
            </div>
            <h3 className="text-base font-bold text-white leading-snug">
              Wind-weighted vs pure distance
            </h3>
            <p className="mt-3 text-[15px] font-semibold text-white leading-snug">
              Dominant source flips on{' '}
              <span className="text-brand-blue">{wind.dominant_source_change_pct}%</span> of a{' '}
              {wind.sample_size}-hex corridor sample
              {wind.mean_abs_traffic_fraction_delta_pp > 0 && (
                <>
                  {' '}
                  (mean |Δ traffic|{' '}
                  <span className="text-brand-orange">
                    {wind.mean_abs_traffic_fraction_delta_pp} pp
                  </span>
                  )
                </>
              )}
              .
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <StatPill
                label="Dominant flips"
                value={`${wind.dominant_source_change_pct}%`}
                accent="text-brand-blue"
              />
              <StatPill
                label="|Δ traffic|"
                value={`${wind.mean_abs_traffic_fraction_delta_pp} pp`}
                accent="text-brand-orange"
              />
            </div>
            <p className="text-[11px] text-white/70 mt-3 leading-snug">{wind.interpretation}</p>
          </div>
        )}
        {fus && (
          <div className="rounded-2xl border border-brand-orange/30 bg-gradient-to-br from-brand-orange/10 to-white/[0.02] p-5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-brand-orange font-bold mb-2">
              Ablation 2 · Station fusion
            </div>
            <h3 className="text-base font-bold text-white leading-snug">
              Fusion vs no-fusion
            </h3>
            <p className="mt-3 text-[15px] font-semibold text-white leading-snug">
              While overall rank correlation stays high (
              <span className="text-brand-green">{fus.spearman_rank_correlation}</span>
              ), only{' '}
              <span className="text-brand-orange">{fus.top_k_overlap_pct}%</span> of the top-
              {fus.top_k} enforcement targets overlap — fusion meaningfully changes who gets
              prioritized.
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <StatPill
                label={`Top-${fus.top_k} overlap`}
                value={`${fus.top_k_overlap_pct}%`}
                accent="text-brand-orange"
              />
              <StatPill
                label="Spearman ρ"
                value={String(fus.spearman_rank_correlation)}
                accent="text-brand-green"
              />
            </div>
            <p className="text-[11px] text-apple-secondary mt-3 leading-snug">
              No-fusion fill = city median {fus.city_median_pm25_used} µg/m³ ·{' '}
              {fus.scored_hexes_with_fusion.toLocaleString()} fused hexes scored
            </p>
          </div>
        )}
      </div>
      <MethodNote text={data.method_note} />
    </GlassCard>
  );
}

function BeforeAfterCard({ data }: { data: BeforeAfterInsight }) {
  if (!data.available || !data.before || !data.after) {
    return <UnavailableCard title="Before AQI Sentinel / After" reason={data.reason} />;
  }

  return (
    <GlassCard className="p-6 md:p-7">
      <InsightBadge n={6} label="Problem statement · System delta" />
      <h2 className="text-xl md:text-2xl font-bold text-white mt-3">
        {data.headline || 'Before AQI Sentinel / After'}
      </h2>
      <p className="text-sm text-apple-secondary mt-2.5 leading-relaxed max-w-3xl">
        {data.finding}
      </p>

      <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-2xl bg-white/[0.03] border border-white/10 p-5">
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-apple-secondary mb-3">
            Before
          </div>
          <ul className="space-y-3">
            <li className="flex justify-between gap-3 text-sm">
              <span className="text-apple-secondary">CPCB / KSPCB stations</span>
              <span className="font-mono font-bold text-white">
                {data.before.cpcb_kspcb_stations}
              </span>
            </li>
            <li className="flex justify-between gap-3 text-sm">
              <span className="text-apple-secondary">Automated enforcement link</span>
              <span className="font-mono font-bold text-brand-red">None</span>
            </li>
            <li className="flex justify-between gap-3 text-sm">
              <span className="text-apple-secondary">Cities with actionable protocol (CAG)</span>
              <span className="font-mono font-bold text-brand-orange">
                {data.before.actionable_protocol_share_national_pct}%
              </span>
            </li>
          </ul>
        </div>

        <div className="rounded-2xl bg-brand-blue/10 border border-brand-blue/25 p-5">
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-brand-blue mb-3">
            After · AQI Sentinel
          </div>
          <ul className="space-y-3">
            <li className="flex justify-between gap-3 text-sm">
              <span className="text-apple-secondary">H3 hexagons live-scored</span>
              <span className="font-mono font-bold text-white">
                {data.after.h3_hexagons.toLocaleString()}
              </span>
            </li>
            <li className="flex justify-between gap-3 text-sm">
              <span className="text-apple-secondary">Decomposed priority</span>
              <span className="font-mono font-bold text-brand-green">
                {data.after.enforcement_priority_decomposed ? 'Yes' : 'No'}
              </span>
            </li>
            <li className="flex justify-between gap-3 text-sm">
              <span className="text-apple-secondary">Layers</span>
              <span className="font-mono font-bold text-white text-right">
                {[
                  data.after.tod_traffic_multipliers && 'TOD traffic',
                  data.after.sentinel5p_no2 && 'S5P NO₂',
                  data.after.firms_burning && 'FIRMS',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </li>
          </ul>
        </div>
      </div>
      <MethodNote text={data.method_note} />
    </GlassCard>
  );
}

/* ─── Page ─── */
export default function InsightsPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error, isFetching, refetch } = useCityInsights('bengaluru');

  const insights = data?.insights;
  const availableCount = useMemo(() => {
    if (!insights) return 0;
    return Object.values(insights).filter((i) => i && (i as { available?: boolean }).available).length;
  }, [insights]);

  return (
    <div className="w-full h-full overflow-y-auto bg-black landing-mesh">
      <div className="max-w-6xl mx-auto px-5 md:px-8 py-8 md:py-10 space-y-6 md:space-y-8 pb-16">
        <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 animate-fade-up">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-brand-blue mb-2 flex items-center gap-2">
              <BarChart3 size={12} />
              Defensible city intelligence
            </div>
            <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-white">
              Six findings from the live system
            </h1>
            <p className="text-sm text-apple-secondary mt-2 max-w-2xl leading-relaxed">
              Not generic dashboards — each card is a real computation from attribution,
              station CSVs, model evaluation, enforcement scores, and rental catchments.
              Built for judges who ask “where did that number come from?”
            </p>
            {data?.generated_at && (
              <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-apple-secondary">
                <span className="inline-flex items-center gap-1.5">
                  <Clock size={12} />
                  Generated {new Date(data.generated_at).toLocaleString()}
                </span>
                {data.cache_hit && (
                  <span className="text-white/40 font-mono">cache hit</span>
                )}
                <span className="inline-flex items-center gap-1.5 text-brand-green">
                  <Sparkles size={12} />
                  {availableCount} insights live
                </span>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <SpringButton
              variant="secondary"
              size="md"
              className="rounded-full"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw size={15} className={isFetching ? 'animate-spin' : ''} />
              Refresh
            </SpringButton>
            <SpringButton
              variant="primary"
              size="md"
              className="rounded-full"
              onClick={() => navigate('/enforcement')}
            >
              Open Enforcement
              <ArrowRight size={16} />
            </SpringButton>
          </div>
        </header>

        {isLoading && (
          <GlassCard className="p-10 text-center">
            <div className="inline-flex items-center gap-3 text-sm text-apple-secondary">
              <RefreshCw size={16} className="animate-spin text-brand-blue" />
              Computing data-grounded insights pack…
            </div>
            <p className="text-[11px] text-apple-secondary mt-2">
              Running attribution TOD series, station gap scan, evaluation metrics, and
              enforcement concentration math.
            </p>
          </GlassCard>
        )}

        {isError && (
          <GlassCard className="p-6 border-brand-red/30">
            <div className="flex items-start gap-3">
              <AlertTriangle className="text-brand-red shrink-0 mt-0.5" size={18} />
              <div>
                <h2 className="text-lg font-bold text-white">Could not load insights pack</h2>
                <p className="text-sm text-apple-secondary mt-1">
                  {(error as Error)?.message ||
                    'Ensure the API is running and GET /api/insights/city/bengaluru is reachable.'}
                </p>
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="mt-3 text-sm font-semibold text-brand-blue hover:underline"
                >
                  Try again
                </button>
              </div>
            </div>
          </GlassCard>
        )}

        {insights && (
          <>
            {/* 1 — Hero */}
            <RushHourFlipCard data={insights.rush_hour_flip} />

            {/* 2 — Trust */}
            <SensorBlindSpotsCard data={insights.sensor_blind_spots} />

            {/* 3 + 4 — Analytical pair */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5">
              <PredictabilityMapCard data={insights.predictability_map} />
              <TargetedEnforcementCard data={insights.targeted_enforcement} />
            </div>

            {/* 5 — Cross-feature */}
            <RentVsAirCard data={insights.rent_vs_air} />

            {/* 6 — Before / After */}
            <BeforeAfterCard data={insights.before_after} />

            {/* 7 — Failure modes (honesty) */}
            <FailureModesCard data={insights.failure_modes} />

            {/* 8 — Ablations */}
            <AblationStudiesCard data={insights.ablation_studies} />

            <footer className="pt-2 pb-4 flex flex-wrap items-center justify-between gap-3 text-[11px] text-apple-secondary">
              <span className="inline-flex items-center gap-1.5">
                <Layers size={12} className="text-brand-blue" />
                Same engines as Map, Enforcement, Citizen Mode, and multi-station forecast.
              </span>
              <button
                type="button"
                onClick={() => navigate('/map')}
                className="inline-flex items-center gap-1.5 text-brand-blue font-semibold hover:underline"
              >
                Explore the map
                <ArrowRight size={12} />
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
