import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, Compass, ArrowRight, Info } from 'lucide-react';

/**
 * Admin-facing Neighbourhoods landing.
 * Live personalised matching lives in Citizen Mode (#/citizen) —
 * this page deep-links there instead of inventing demo neighbourhood cards.
 */
export default function NeighbourhoodsPage() {
  const navigate = useNavigate();

  return (
    <div className="w-full h-full bg-black overflow-y-auto px-6 py-10 md:px-10">
      <div className="max-w-2xl mx-auto space-y-8">
        <div className="flex flex-col items-center text-center space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-brand-blue/10 border border-brand-blue/25 flex items-center justify-center text-brand-blue">
            <Building2 size={28} />
          </div>
          <div className="space-y-2">
            <h1 className="text-3xl font-bold text-white tracking-tight">
              Neighbourhood Matching
            </h1>
            <p className="text-sm text-apple-secondary leading-relaxed max-w-md mx-auto">
              Personalised neighbourhood recommendations (rent, AQI, commute, schools,
              hospitals, parks) run in <strong className="text-white">Citizen Mode</strong>.
              No fabricated comparison cards are shown here.
            </p>
          </div>
        </div>

        <div className="bg-apple-card border border-apple-border rounded-2xl p-6 space-y-5">
          <div className="flex items-start gap-3">
            <Compass className="w-5 h-5 text-brand-blue shrink-0 mt-0.5" />
            <div className="space-y-1 text-left">
              <h2 className="text-base font-semibold text-white">Citizen Mode</h2>
              <p className="text-xs text-apple-secondary leading-relaxed">
                Build a profile (budget, family, health, workplace, priorities), then get a
                ranked list from the live matching API with honesty flags for estimated
                AQI and rent.
              </p>
            </div>
          </div>

          <button
            type="button"
            id="btn-open-citizen-mode"
            onClick={() => navigate('/citizen')}
            className="w-full min-h-[48px] flex items-center justify-center gap-2 rounded-xl bg-brand-blue hover:bg-brand-blue/90 active:bg-brand-blue/85 text-white font-bold text-sm shadow-lg shadow-brand-blue/10 transition-all"
          >
            <span>Open Citizen Mode</span>
            <ArrowRight size={16} />
          </button>
        </div>

        <div className="flex items-start gap-2.5 text-[11px] text-apple-secondary leading-relaxed px-1">
          <Info className="w-4 h-4 shrink-0 mt-0.5 text-apple-secondary" />
          <p>
            You can also switch via the <strong className="text-white">Citizen</strong> pill
            in the top navigation. City Admin tools (Map, Enforcement, Copilot) stay on this
            side of the app.
          </p>
        </div>
      </div>
    </div>
  );
}
