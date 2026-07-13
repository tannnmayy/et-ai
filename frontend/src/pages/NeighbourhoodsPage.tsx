import React, { useState } from 'react';
import { useDashboardData } from '../api/client';
import { Neighbourhood } from '../types';
import { Search, Plus, X, BarChart3, Shield, Info, Building2, HelpCircle, AlertTriangle } from 'lucide-react';

export default function NeighbourhoodsPage() {
  const { data: dashboard, isError, isLoading } = useDashboardData();
  const [activeView, setActiveView] = useState<'analytics' | 'coming-soon'>('analytics');
  const [compareList, setCompareList] = useState<Neighbourhood[]>([]);
  const [searchInput, setSearchInput] = useState('');

  const handleAddLocation = () => {
    if (compareList.length >= 3) {
      alert('Maximum 3 neighbourhoods can be compared at once in multi-screen layout.');
      return;
    }
    alert('Enter a candidate location and workplace in Citizen Mode to run a real comparison. Demo neighbourhood data is not shown here.');
  };

  const handleRemoveLocation = (id: string) => {
    setCompareList(prev => prev.filter(n => n.id !== id));
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchInput.trim()) return;
    alert('Neighbourhood comparison needs a workplace and candidate locations. Use Citizen Mode to submit those real inputs.');
    setSearchInput('');
  };

  if (isLoading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-brand-blue border-t-transparent rounded-full animate-spin" />
          <span className="text-xs font-mono uppercase tracking-widest text-apple-secondary">Loading dashboard data...</span>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4 max-w-md text-center px-6">
          <div className="w-12 h-12 rounded-full bg-brand-red/10 border border-brand-red/20 flex items-center justify-center text-brand-red">
            <AlertTriangle size={24} />
          </div>
          <h2 className="text-lg font-bold text-white">Dashboard Unavailable</h2>
          <p className="text-sm text-apple-secondary leading-relaxed">
            Unable to load neighbourhood analytics from the API.
            No substitute or demonstration neighbourhood data is shown.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full bg-black overflow-y-auto px-6 py-8 md:px-8 space-y-12">
      {/* Top Selector: Analytics vs Coming Soon */}
      <div className="flex justify-center select-none">
        <div className="flex bg-apple-card border border-apple-border rounded-full p-1 shadow-lg">
          <button
            type="button"
            onClick={() => setActiveView('analytics')}
            className={`px-4 py-2 rounded-full text-xs font-bold uppercase tracking-wider transition-all duration-200 ${
              activeView === 'analytics'
                ? 'bg-brand-blue text-white shadow-md'
                : 'text-apple-secondary hover:text-white'
            }`}
          >
            Analytics Dashboard
          </button>
          <button
            type="button"
            onClick={() => setActiveView('coming-soon')}
            className={`px-4 py-2 rounded-full text-xs font-bold uppercase tracking-wider transition-all duration-200 ${
              activeView === 'coming-soon'
                ? 'bg-brand-blue text-white shadow-md'
                : 'text-apple-secondary hover:text-white'
            }`}
          >
            Coming Soon Preview
          </button>
        </div>
      </div>

      {activeView === 'analytics' ? (
        <>
          {/* Header & Search */}
          <div className="max-w-2xl mx-auto text-center space-y-4 pt-4">
            <h1 className="text-3xl font-bold text-white tracking-tight leading-snug">
              Neighbourhood Analytics
            </h1>
            <p className="text-sm text-apple-secondary max-w-md mx-auto">
              Compare environmental suitability metrics across urban sectors.
            </p>

            <form onSubmit={handleSearchSubmit} className="relative max-w-lg mx-auto group">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-apple-secondary group-focus-within:text-brand-blue transition-colors">
                <Search size={16} />
              </div>
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="w-full bg-apple-card border border-apple-border rounded-full py-3.5 pl-12 pr-12 text-sm text-white focus:outline-none focus:border-brand-blue/60 focus:ring-1 focus:ring-brand-blue/30 transition-all placeholder:text-apple-secondary/50 shadow-lg"
                placeholder="Add an address to compare..."
              />
              <div className="absolute inset-y-0 right-0 pr-2 flex items-center">
                <button
                  type="submit"
                  className="bg-brand-blue text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-blue-600 transition-colors shadow-md"
                >
                  <Plus size={16} />
                </button>
              </div>
            </form>
          </div>

          {/* Sector Rankings */}
          <section className="space-y-6">
            <h2 className="text-base font-bold text-white uppercase tracking-widest font-mono">
              Sector Rankings
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {/* Critical Targets */}
              <div className="space-y-4">
                <h3 className="text-[10px] font-bold uppercase tracking-wider text-brand-red font-mono">
                  Top 3 - Critical Targets
                </h3>
                <div className="flex flex-col gap-3">
                  {dashboard?.criticalTargets?.map((item: any) => (
                    <div
                      key={item.rank}
                      className="bg-apple-card border border-apple-border/50 p-4 rounded-xl flex items-center justify-between"
                    >
                      <div className="flex items-center gap-4">
                        <span className="font-mono text-xs font-bold text-apple-secondary">{item.rank}</span>
                        <div>
                          <div className="text-xs font-bold text-white">{item.name}</div>
                          <div className="text-[9px] font-mono uppercase tracking-wider text-brand-red font-bold mt-0.5">
                            {item.issue}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-brand-red shadow-[0_0_4px_#ff453a]" />
                        <span className="font-mono text-sm font-bold text-white">{item.score}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Prime Suitability */}
              <div className="space-y-4">
                <h3 className="text-[10px] font-bold uppercase tracking-wider text-brand-blue font-mono">
                  Top 3 - Prime Suitability
                </h3>
                <div className="flex flex-col gap-3">
                  {dashboard?.primeSuitability?.map((item: any) => (
                    <div
                      key={item.rank}
                      className="bg-apple-card border border-apple-border/50 p-4 rounded-xl flex items-center justify-between"
                    >
                      <div className="flex items-center gap-4">
                        <span className="font-mono text-xs font-bold text-apple-secondary">{item.rank}</span>
                        <div>
                          <div className="text-xs font-bold text-white">{item.name}</div>
                          <div className="text-[9px] font-mono uppercase tracking-wider text-brand-blue font-bold mt-0.5">
                            {item.issue}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-brand-blue shadow-[0_0_4px_#0A84FF]" />
                        <span className="font-mono text-sm font-bold text-white">{item.score}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* Comparison Grid */}
          <section className="space-y-6">
            <h2 className="text-base font-bold text-white uppercase tracking-widest font-mono">
              Neighbourhood Comparison
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {compareList.map((item) => (
                <div
                  key={item.id}
                  className="bg-apple-card border border-apple-border rounded-2xl p-6 flex flex-col justify-between hover:border-brand-blue/30 transition-all duration-300 relative shadow-2xl"
                >
                  {/* Card Header info */}
                  <div className="flex justify-between items-start mb-6">
                    <div>
                      <span className="text-[9px] font-mono uppercase tracking-widest text-apple-secondary font-bold">
                        {item.sectorCode}
                      </span>
                      <h3 className="text-md font-bold text-white mt-0.5 tracking-tight">{item.name}</h3>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRemoveLocation(item.id)}
                      className="text-apple-secondary hover:text-brand-red transition-colors"
                    >
                      <X size={15} />
                    </button>
                  </div>

                  {/* Rating ring gauge details */}
                  <div className="flex justify-center items-center mb-8 relative">
                    <svg className="w-28 h-28 transform -rotate-90" viewBox="0 0 100 100">
                      <circle cx="50" cy="50" fill="none" r="44" stroke="#2C2C2E" strokeWidth="6" />
                      <circle
                        cx="50"
                        cy="50"
                        fill="none"
                        r="44"
                        stroke={item.suitability > 75 ? '#0A84FF' : '#FF9F0A'}
                        strokeWidth="6"
                        strokeDasharray="276.4"
                        strokeDashoffset={276.4 - (276.4 * item.suitability) / 100}
                        strokeLinecap="round"
                        className="transition-all duration-1000"
                      />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className="text-2xl font-bold font-mono text-white leading-none">
                        {item.suitability}
                      </span>
                      <span className="text-[8px] font-mono uppercase text-apple-secondary tracking-widest mt-1">
                        SUITABILITY
                      </span>
                    </div>
                  </div>

                  {/* Component Breakdown vertical bar chart */}
                  <div className="mt-auto space-y-4 border-t border-apple-border/50 pt-4">
                    <div className="text-[9px] font-mono uppercase tracking-widest text-apple-secondary font-bold">
                      Component Breakdown
                    </div>

                    <div className="flex items-end justify-between h-28 gap-1.5 px-1.5 w-full">
                      {Object.entries(item.componentBreakdown).map(([key, val]) => (
                        <div key={key} className="flex flex-col items-center gap-1.5 group/bar flex-1">
                          {/* Tooltip bar popup */}
                          <div className="text-[9px] font-mono text-white opacity-0 group-hover/bar:opacity-100 transition-opacity absolute -mt-5 bg-apple-modal border border-apple-border px-1.5 py-0.5 rounded shadow-xl pointer-events-none">
                            {val}
                          </div>

                          <div className="w-full max-w-[10px] bg-[#1C1C1E] h-20 rounded-t-sm overflow-hidden flex items-end">
                            <div
                              className="w-full bg-brand-blue rounded-t-sm"
                              style={{
                                height: `${val}%`,
                                backgroundColor: item.suitability > 75 ? '#0A84FF' : '#FF9F0A',
                              }}
                            />
                          </div>
                          <span className="text-[8px] font-mono uppercase tracking-wide text-apple-secondary select-none">
                            {key.substring(0, 3)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}

              {/* Empty Location Slot Add Trigger */}
              {compareList.length < 3 && (
                <div
                  onClick={handleAddLocation}
                  className="bg-apple-card/30 border border-dashed border-apple-border rounded-2xl p-6 flex flex-col items-center justify-center hover:border-brand-blue/40 hover:bg-apple-card/60 transition-all duration-300 cursor-pointer group min-h-[350px]"
                >
                  <div className="w-12 h-12 rounded-full bg-apple-card border border-apple-border flex items-center justify-center text-apple-secondary group-hover:bg-brand-blue group-hover:text-white transition-colors shadow-md">
                    <Plus size={18} />
                  </div>
                  <h3 className="text-sm font-bold text-apple-secondary group-hover:text-white transition-colors mt-4">
                    Add Location
                  </h3>
                  <p className="text-[11px] text-apple-secondary/60 text-center mt-2 max-w-[180px] leading-relaxed">
                    Select a third neighborhood to run a side-by-side analysis.
                  </p>
                </div>
              )}
            </div>
          </section>
        </>
      ) : (
        /* Coming Soon Screen representation from Stitch screen 1 */
        <div className="flex-1 flex flex-col items-center justify-center text-center py-20 relative">
          {/* Decorative ambient blurred backing rings */}
          <div className="absolute inset-0 pointer-events-none overflow-hidden">
            <div className="absolute top-1/4 left-1/3 w-96 h-96 bg-brand-blue/5 rounded-full blur-[100px] animate-pulse" />
            <div className="absolute bottom-1/4 right-1/3 w-80 h-80 bg-brand-orange/5 rounded-full blur-[100px]" />
          </div>

          <div className="relative z-10 flex flex-col items-center max-w-md mx-auto space-y-6">
            {/* Big City Icon circle */}
            <div className="w-20 h-20 rounded-full bg-apple-card border border-apple-border flex items-center justify-center text-brand-blue shadow-2xl">
              <Building2 size={36} />
            </div>

            {/* Title details */}
            <div className="space-y-3">
              <h1 className="text-2xl font-bold text-white tracking-tight leading-snug">
                Neighbourhoods — Coming Soon
              </h1>
              <p className="text-xs text-apple-secondary leading-relaxed max-w-sm mx-auto">
                We are currently deploying localized environmental sensors. Hyper-local air quality resolution will be available shortly.
              </p>
            </div>

            {/* Calibration Status Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-apple-card/60 border border-apple-border select-none">
              <span className="w-2 h-2 rounded-full bg-brand-orange animate-pulse shadow-[0_0_6px_#FF9F0A]" />
              <span className="text-[9px] font-mono font-bold uppercase tracking-widest text-apple-secondary">
                Calibration in progress
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
