import React, { useState } from 'react';
import { usePriorities } from '../api/client';
import { PriorityHex } from '../types';
import MapContainer from '../components/MapContainer';
import SourceIcon from '../components/SourceIcon';
import { AlertCircle, ShieldAlert, X, ChevronRight, Compass, Plus, Minus, Navigation, Info, ShieldCheck } from 'lucide-react';

export default function EnforcementPage() {
  const { data: priorities = [], isError, isLoading } = usePriorities();
  const [selectedHex, setSelectedHex] = useState<PriorityHex | null>(null);
  const [dispatchedUnits, setDispatchedUnits] = useState<Record<string, boolean>>({});

  const activeHex = selectedHex || priorities[0] || null;

  if (isLoading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-brand-blue border-t-transparent rounded-full animate-spin" />
          <span className="text-xs font-mono uppercase tracking-widest text-apple-secondary">Loading enforcement data...</span>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4 max-w-md text-center px-6">
          <div className="w-12 h-12 rounded-full bg-brand-red/10 border border-brand-red/20 flex items-center justify-center text-brand-red">
            <AlertCircle size={24} />
          </div>
          <h2 className="text-lg font-bold text-white">Data Unavailable</h2>
          <p className="text-sm text-apple-secondary leading-relaxed">
            Unable to load enforcement priorities from the API.
            Please check that the backend is running and try again.
          </p>
        </div>
      </div>
    );
  }

  const handleDispatch = (hexId: string) => {
    setDispatchedUnits(prev => ({ ...prev, [hexId]: true }));
    setTimeout(() => {
      alert(`Dispatch ordered for Hexagon ${hexId}. Dispatch Code: ENF-992`);
    }, 150);
  };

  const getActionabilityStyle = (act: string) => {
    switch (act) {
      case 'IMMEDIATE':
        return {
          bg: 'bg-brand-red/10 border-brand-red/20 text-brand-red',
          dot: 'bg-brand-red shadow-[0_0_4px_#ff453a]',
          text: 'IMMEDIATE',
        };
      case 'HIGH':
        return {
          bg: 'bg-brand-orange/10 border-brand-orange/20 text-brand-orange',
          dot: 'bg-brand-orange shadow-[0_0_4px_#FF9F0A]',
          text: 'HIGH',
        };
      default:
        return {
          bg: 'bg-brand-blue/10 border-brand-blue/20 text-brand-blue',
          dot: 'bg-brand-blue shadow-[0_0_4px_#0A84FF]',
          text: 'MONITOR',
        };
    }
  };

  return (
    <div className="w-full h-full flex flex-col md:flex-row bg-black overflow-hidden">
      {/* Left Column: Data Table (55%) */}
      <section className="w-full md:w-[55%] h-full flex flex-col bg-black p-6 border-r border-apple-border">
        {/* Page Header */}
        <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white tracking-tight leading-snug">
              Enforcement Priorities
            </h2>
            <p className="text-xs text-apple-secondary font-sans mt-0.5">
              Real-time localized intervention targets based on compound risk scores.
            </p>
          </div>
          <div className="relative group cursor-pointer rounded-full px-4 py-2 bg-apple-card hover:bg-apple-modal border border-apple-border transition-colors flex items-center gap-2 select-none">
            <span className="text-[10px] font-bold uppercase tracking-widest text-apple-secondary">Show:</span>
            <span className="text-[10px] font-bold uppercase tracking-widest text-white">Top 10</span>
          </div>
        </div>

        {/* Priorities Table Structure */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Table Headers */}
          <div className="grid grid-cols-[50px_1fr_120px_90px_100px_110px] gap-4 px-4 py-3 border-b border-apple-border mb-2">
            <div className="text-[10px] font-mono font-bold text-apple-secondary uppercase text-right">RANK</div>
            <div className="text-[10px] font-sans font-bold text-apple-secondary uppercase pl-2">HEXAGON</div>
            <div className="text-[10px] font-mono font-bold text-apple-secondary uppercase text-right">SCORE</div>
            <div className="text-[10px] font-sans font-bold text-apple-secondary uppercase text-right">EXPOSURE</div>
            <div className="text-[10px] font-mono font-bold text-apple-secondary uppercase text-right">MAGNITUDE</div>
            <div className="text-[10px] font-sans font-bold text-apple-secondary uppercase text-right">ACTION</div>
          </div>

          {/* Scrollable Rows */}
          <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
            {priorities.map((item, idx) => {
              const rankStr = String(idx + 1).padStart(2, '0');
              const isSelected = activeHex?.id === item.id;
              const actionStyle = getActionabilityStyle(item.actionability);

              return (
                <div
                  key={item.id}
                  onClick={() => setSelectedHex(item)}
                  className={`group grid grid-cols-[50px_1fr_120px_90px_100px_110px] gap-4 items-center rounded-xl cursor-pointer transition-all duration-200 py-3 relative overflow-hidden ${
                    isSelected
                      ? 'bg-apple-card border border-brand-blue/30 shadow-lg'
                      : 'bg-apple-card/40 hover:bg-apple-card border border-transparent'
                  }`}
                >
                  {/* Active selected state line indicator */}
                  {isSelected && (
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-brand-blue" />
                  )}

                  {/* Rank */}
                  <div className="font-mono text-xs font-bold text-apple-secondary text-right pr-2">
                    {rankStr}
                  </div>

                  {/* Hexagon & Name */}
                  <div className="flex items-center gap-3 pl-2 min-w-0">
                    <div
                      className="w-2.5 h-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: item.priorityScore > 95 ? '#ff453a' : '#FF9F0A' }}
                    />
                    <div className="min-w-0">
                      <div className="font-mono text-xs font-bold text-white truncate">
                        {item.id}
                      </div>
                      <div className="text-[10px] font-sans text-apple-secondary truncate mt-0.5">
                        {item.name}
                      </div>
                    </div>
                  </div>

                  {/* Priority Score */}
                  <div className="font-mono text-sm font-bold text-white text-right">
                    {item.priorityScore}
                    <div className="text-[9px] font-mono font-normal mt-0.5" style={{ color: item.changeVal >= 0 ? '#ff453a' : '#34C759' }}>
                      {item.changeVal >= 0 ? `+${item.changeVal}` : item.changeVal} vs prev
                    </div>
                  </div>

                  {/* Exposure */}
                  <div className="font-sans text-xs font-bold text-apple-secondary text-right select-none">
                    {item.exposure}
                  </div>

                  {/* Magnitude */}
                  <div className="font-mono text-xs text-white text-right">
                    +{item.magnitude}%
                    <div className="text-[9px] font-mono text-apple-secondary mt-0.5 select-none">
                      {item.confidence}% conf
                    </div>
                  </div>

                  {/* Actionability Status Pill */}
                  <div className="flex justify-end items-center pr-3">
                    <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[9px] font-bold select-none ${actionStyle.bg}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${actionStyle.dot}`} />
                      {actionStyle.text}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Right Column: Digital Map + Detail Bottom Sheet (45%) */}
      <section className="w-full md:w-[45%] h-full relative bg-apple-bg flex flex-col justify-between">
        {/* Background Map Placeholder */}
        <div className="flex-1 w-full h-full relative">
          <MapContainer
            selectedHex={activeHex}
            onSelectHex={(hex) => setSelectedHex(hex)}
            allHexes={priorities}
            viewMode="enforcement"
          />

          {/* Simulated Tactical Overlay Panels */}
          <div className="absolute top-20 right-4 flex flex-col gap-2 z-10">
            <button className="w-9 h-9 rounded-full bg-apple-modal/90 backdrop-blur-md border border-apple-border flex items-center justify-center text-white hover:bg-apple-card transition-colors shadow-lg">
              <Plus size={16} />
            </button>
            <button className="w-9 h-9 rounded-full bg-apple-modal/90 backdrop-blur-md border border-apple-border flex items-center justify-center text-white hover:bg-apple-card transition-colors shadow-lg">
              <Minus size={16} />
            </button>
            <button className="w-9 h-9 rounded-full bg-apple-modal/90 backdrop-blur-md border border-apple-border flex items-center justify-center text-white hover:bg-apple-card transition-colors shadow-lg mt-3">
              <Navigation size={15} />
            </button>
          </div>
        </div>

        {/* Enforcement Active Hex Details Bottom Sheet */}
        {activeHex && (
          <div className="p-4 sm:p-6 bg-apple-modal/95 border-t border-apple-border backdrop-blur-xl z-20 shadow-2xl relative">
            <div className="max-w-xl mx-auto flex flex-col gap-5">
              {/* Top Row Header info */}
              <div className="flex justify-between items-start border-b border-apple-border/50 pb-4">
                <div className="flex gap-3.5 items-center">
                  <div className="h-11 w-11 rounded-xl bg-brand-red/10 border border-brand-red/20 flex items-center justify-center text-brand-red shrink-0">
                    <ShieldAlert size={20} className="animate-pulse" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-mono text-sm font-bold text-white tracking-tight">
                        {activeHex.id}
                      </h3>
                      <span className="bg-brand-red text-white font-mono text-[9px] font-bold px-2 py-0.5 rounded-full select-none">
                        PRIORITY 1
                      </span>
                    </div>
                    <p className="text-xs text-apple-secondary font-sans leading-relaxed mt-0.5">
                      {activeHex.name} Industrial Sector
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedHex(null)}
                  className="w-8 h-8 rounded-full bg-apple-card hover:bg-apple-border/20 border border-apple-border flex items-center justify-center text-apple-secondary hover:text-white transition-colors"
                >
                  <X size={14} />
                </button>
              </div>

              {/* Specs Metric Row */}
              <div className="grid grid-cols-3 gap-6">
                {/* Metric 1 */}
                <div className="flex flex-col gap-0.5">
                  <span className="text-[9px] font-mono uppercase tracking-widest text-apple-secondary">
                    PM2.5 CONCENTRATION
                  </span>
                  <div className="flex items-end gap-1.5 mt-1">
                    <span className="font-mono text-xl font-bold text-brand-red leading-none select-none">
                      {activeHex.pm25}
                    </span>
                    <span className="font-mono text-[9px] text-apple-secondary pb-0.5">
                      µg/m³
                    </span>
                  </div>
                </div>

                {/* Metric 2 */}
                <div className="flex flex-col gap-0.5">
                  <span className="text-[9px] font-mono uppercase tracking-widest text-apple-secondary">
                    PRIMARY SOURCE
                  </span>
                  <div className="text-xs font-semibold text-white flex items-center gap-1.5 mt-1">
                    <SourceIcon sourceType={activeHex.primarySource} size={16} />
                    {activeHex.primarySource}
                  </div>
                </div>

                {/* Action dispatch button */}
                <div className="flex items-center justify-end">
                  <button
                    type="button"
                    onClick={() => handleDispatch(activeHex.id)}
                    disabled={dispatchedUnits[activeHex.id]}
                    className={`px-5 py-2.5 rounded-full text-[10px] font-bold uppercase tracking-wider transition-colors duration-200 flex items-center gap-1.5 shadow-md ${
                      dispatchedUnits[activeHex.id]
                        ? 'bg-brand-green/20 text-brand-green border border-brand-green/30 cursor-not-allowed'
                        : 'bg-brand-blue hover:bg-blue-600 text-white'
                    }`}
                  >
                    {dispatchedUnits[activeHex.id] ? (
                      <>
                        <ShieldCheck size={12} /> DISPATCHED
                      </>
                    ) : (
                      <>
                        <ShieldAlert size={12} /> DISPATCH UNIT
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
