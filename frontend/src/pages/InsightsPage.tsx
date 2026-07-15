import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart3,
  Flame,
  MapPin,
  Shield,
  TrendingUp,
  Wind,
  ArrowRight,
  AlertTriangle,
  Activity,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from 'recharts';
import { useCityExtremes, useFireDetections, usePriorities, useStations } from '../api/client';

function GlassCard({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`glass-panel rounded-3xl border border-white/10 ${className}`}>{children}</div>
  );
}

export default function InsightsPage() {
  const navigate = useNavigate();
  const { data: extremes, isLoading: extremesLoading } = useCityExtremes();
  const { data: priorities = [], isLoading: prioLoading } = usePriorities();
  const { data: stations = [], isLoading: stationsLoading } = useStations();
  const { data: fires } = useFireDetections();

  const topHotspots = useMemo(() => (priorities || []).slice(0, 5), [priorities]);

  const sourceMix = useMemo(() => {
    const counts: Record<string, number> = {
      traffic: 0,
      industrial: 0,
      construction: 0,
      burning: 0,
      other: 0,
    };
    for (const p of priorities || []) {
      const key = String(p.primarySource || p.primarySourceKey || p.sourceType || 'other').toLowerCase();
      if (key.includes('traffic')) counts.traffic += 1;
      else if (key.includes('indust')) counts.industrial += 1;
      else if (key.includes('construct')) counts.construction += 1;
      else if (key.includes('burn')) counts.burning += 1;
      else counts.other += 1;
    }
    return Object.entries(counts)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value }));
  }, [priorities]);

  const peakHours = useMemo(
    () => [
      { hour: '07–09', label: 'Morning peak', intensity: 86, note: 'Commute corridors' },
      { hour: '12–14', label: 'Midday', intensity: 54, note: 'Mixed urban' },
      { hour: '17–21', label: 'Evening peak', intensity: 92, note: 'Traffic + residual dust' },
      { hour: '22–05', label: 'Night', intensity: 41, note: 'Stagnation risk' },
    ],
    [],
  );

  const loading = extremesLoading || prioLoading || stationsLoading;
  const fireCount = Array.isArray(fires) ? fires.length : (fires as any)?.detections?.length ?? 0;
  const stationCount = Array.isArray(stations) ? stations.length : 0;

  const COLORS = ['#0A84FF', '#FF9F0A', '#ff453a', '#34C759', '#8E8E93'];

  return (
    <div className="w-full h-full overflow-y-auto bg-black landing-mesh">
      <div className="max-w-6xl mx-auto px-5 md:px-8 py-8 md:py-10 space-y-8 pb-16">
        <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 animate-fade-up">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-brand-blue mb-2 flex items-center gap-2">
              <BarChart3 size={12} />
              City Insights
            </div>
            <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-white">
              Bengaluru air intelligence
            </h1>
            <p className="text-sm text-apple-secondary mt-2 max-w-xl leading-relaxed">
              Live snapshot of station coverage, enforcement hotspots, source mix, and
              peak-hour traffic pressure — grounded in platform data where available.
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate('/enforcement')}
            className="min-h-[44px] inline-flex items-center gap-2 px-5 rounded-full bg-brand-blue text-white text-sm font-bold shadow-lg shadow-brand-blue/20 hover:bg-brand-blue/90 transition-colors"
          >
            Open Enforcement
            <ArrowRight size={16} />
          </button>
        </header>

        {/* KPI row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          {[
            {
              label: 'Stations online',
              value: stationCount || '—',
              icon: Activity,
              hint: 'CPCB / KSPCB network',
            },
            {
              label: 'Hexes with fusion',
              value: extremes?.totalWithData ?? '—',
              icon: MapPin,
              hint: `of ${extremes?.totalInGrid ?? '—'} grid cells`,
            },
            {
              label: 'Priority targets',
              value: priorities?.length ?? 0,
              icon: Shield,
              hint: 'Enforcement ranking',
            },
            {
              label: 'FIRMS detections',
              value: fireCount,
              icon: Flame,
              hint: 'Recent fire signals',
            },
          ].map((kpi) => {
            const Icon = kpi.icon;
            return (
              <GlassCard key={kpi.label} className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary">
                    {kpi.label}
                  </span>
                  <Icon size={16} className="text-brand-blue" />
                </div>
                <div className="text-3xl font-bold font-mono text-white tracking-tight">
                  {loading && kpi.value === '—' ? '…' : kpi.value}
                </div>
                <div className="text-[11px] text-apple-secondary mt-1">{kpi.hint}</div>
              </GlassCard>
            );
          })}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 md:gap-5">
          {/* Top hotspots */}
          <GlassCard className="lg:col-span-3 p-6">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="text-lg font-bold text-white">Top 5 actionable hotspots</h2>
                <p className="text-xs text-apple-secondary mt-1">
                  From live enforcement priority ranking
                </p>
              </div>
              <TrendingUp size={18} className="text-brand-orange" />
            </div>

            {loading && topHotspots.length === 0 ? (
              <div className="py-12 text-center text-sm text-apple-secondary">Loading priorities…</div>
            ) : topHotspots.length === 0 ? (
              <div className="py-10 flex flex-col items-center gap-2 text-center">
                <AlertTriangle size={20} className="text-apple-secondary" />
                <p className="text-sm text-apple-secondary">No priority hexes available yet.</p>
              </div>
            ) : (
              <ul className="space-y-2.5">
                {topHotspots.map((h, idx: number) => {
                  const id = h.id || `hex-${idx}`;
                  const score = h.priorityScore ?? h.pm25 ?? '—';
                  const source = h.primarySource || h.primarySourceKey || h.sourceType || 'mixed';
                  const name = h.name || id;
                  return (
                    <li
                      key={id}
                      className="flex items-center gap-3 p-3 rounded-2xl bg-white/[0.03] border border-white/8 hover:border-brand-blue/30 transition-colors"
                    >
                      <span className="w-8 h-8 rounded-xl bg-brand-blue/15 border border-brand-blue/25 text-brand-blue font-mono text-xs font-bold flex items-center justify-center">
                        {idx + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-white truncate">{name}</div>
                        <div className="text-[10px] font-mono text-apple-secondary uppercase tracking-wider">
                          {String(source).replace(/_/g, ' ')}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-mono font-bold text-white">{typeof score === 'number' ? score.toFixed(1) : score}</div>
                        <div className="text-[9px] text-apple-secondary uppercase">score</div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </GlassCard>

          {/* Source mix chart */}
          <GlassCard className="lg:col-span-2 p-6">
            <h2 className="text-lg font-bold text-white mb-1">Dominant sources</h2>
            <p className="text-xs text-apple-secondary mb-4">
              Among ranked enforcement hexes
            </p>
            {sourceMix.length === 0 ? (
              <div className="h-48 flex items-center justify-center text-xs text-apple-secondary">
                Awaiting priority source mix
              </div>
            ) : (
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sourceMix} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#38383A" vertical={false} />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: '#8E8E93', fontSize: 10 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      allowDecimals={false}
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
                    <Bar dataKey="value" radius={[8, 8, 4, 4]}>
                      {sourceMix.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </GlassCard>
        </div>

        {/* Peak hours */}
        <GlassCard className="p-6">
          <div className="flex items-center gap-2 mb-5">
            <Wind size={18} className="text-sky-400" />
            <div>
              <h2 className="text-lg font-bold text-white">Peak traffic hours & pollution pressure</h2>
              <p className="text-xs text-apple-secondary mt-0.5">
                Operational guidance for corridor-weighted attribution (morning / evening peaks)
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {peakHours.map((p) => (
              <div
                key={p.hour}
                className="rounded-2xl bg-white/[0.04] border border-white/10 p-4"
              >
                <div className="text-[10px] font-mono uppercase tracking-wider text-apple-secondary mb-1">
                  {p.hour}
                </div>
                <div className="text-sm font-bold text-white mb-2">{p.label}</div>
                <div className="h-1.5 rounded-full bg-white/10 overflow-hidden mb-2">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-brand-blue to-brand-orange"
                    style={{ width: `${p.intensity}%` }}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-apple-secondary">{p.note}</span>
                  <span className="text-xs font-mono font-bold text-white">{p.intensity}</span>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Extremes strip */}
        {extremes && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <GlassCard className="p-5">
              <h3 className="text-sm font-bold text-brand-green mb-3">Cleanest monitored hexes</h3>
              <ul className="space-y-2">
                {(extremes.best || []).slice(0, 3).map((h: any, i: number) => (
                  <li key={i} className="text-xs text-apple-secondary flex justify-between gap-2">
                    <span className="text-white/90 truncate font-mono">
                      {h.h3_index || h.h3_cell || h.id}
                    </span>
                    <span className="font-mono text-brand-green">
                      {h.pm25 != null ? Number(h.pm25).toFixed(0) : '—'} µg/m³
                    </span>
                  </li>
                ))}
              </ul>
            </GlassCard>
            <GlassCard className="p-5">
              <h3 className="text-sm font-bold text-brand-red mb-3">Most polluted monitored hexes</h3>
              <ul className="space-y-2">
                {(extremes.worst || []).slice(0, 3).map((h: any, i: number) => (
                  <li key={i} className="text-xs text-apple-secondary flex justify-between gap-2">
                    <span className="text-white/90 truncate font-mono">
                      {h.h3_index || h.h3_cell || h.id}
                    </span>
                    <span className="font-mono text-brand-red">
                      {h.pm25 != null ? Number(h.pm25).toFixed(0) : '—'} µg/m³
                    </span>
                  </li>
                ))}
              </ul>
            </GlassCard>
          </div>
        )}
      </div>
    </div>
  );
}
