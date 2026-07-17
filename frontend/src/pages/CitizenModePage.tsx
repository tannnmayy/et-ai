import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import {
  AlertOctagon,
  Info,
  ListOrdered,
  RefreshCw,
  User,
  Home,
  Wind,
  IndianRupee,
  Train,
} from 'lucide-react';
import type { CitizenProfile, NeighbourhoodMatch } from '../types/citizen';
import { getNeighbourhoodMatches, MOCK_MATCHES } from '../services/citizenService';
import ProfileBuilderForm from '../components/citizen/ProfileBuilderForm';
import RankedResultsList from '../components/citizen/RankedResultsList';
import NeighbourhoodDetailPanel from '../components/citizen/NeighbourhoodDetailPanel';
import { Glass, MotionCard } from '../components/ui';

type ActiveView = 'profile' | 'results' | 'detail';

const DEFAULT_PROFILE: CitizenProfile = {
  rentBudget: 45000,
  familySize: 2,
  healthConditions: ['none'],
  officeLocation: 'Indiranagar',
  maxCommuteMinutes: 45,
  priorities: ['metro', 'low_aqi'],
};

/**
 * Citizen Mode — neighbourhood matching for residents and judges.
 */
export default function CitizenModePage() {
  const [activeView, setActiveView] = useState<ActiveView>('profile');
  const [profile, setProfile] = useState<CitizenProfile | null>(null);
  const [selectedNeighbourhood, setSelectedNeighbourhood] = useState<NeighbourhoodMatch | null>(null);
  const [useLocalMockData, setUseLocalMockData] = useState(false);

  const { data: matches, isLoading, isError, error, refetch } = useQuery<NeighbourhoodMatch[]>({
    queryKey: ['neighbourhoodMatches', profile],
    queryFn: () => {
      if (!profile) return Promise.resolve([]);
      return getNeighbourhoodMatches(profile);
    },
    enabled: !!profile && !useLocalMockData,
    retry: false,
  });

  const activeMatches = useLocalMockData ? MOCK_MATCHES : matches || [];

  const handleProfileSubmit = (submittedProfile: CitizenProfile) => {
    setProfile(submittedProfile);
    setSelectedNeighbourhood(null);
    setActiveView('results');
  };

  const handleSelectNeighbourhood = (match: NeighbourhoodMatch) => {
    setSelectedNeighbourhood(match);
    setActiveView('detail');
  };

  const enableDeveloperMockMode = () => {
    setUseLocalMockData(true);
    if (!profile) setProfile(DEFAULT_PROFILE);
    setActiveView('results');
  };

  const navButtonClass = (view: ActiveView) =>
    `w-full min-h-[44px] px-4 py-2.5 rounded-xl flex items-center space-x-3 text-xs font-semibold uppercase tracking-wider transition-all duration-200 cursor-pointer ${
      activeView === view
        ? 'bg-brand-blue text-white shadow-lg shadow-brand-blue/15 font-bold'
        : 'text-apple-secondary hover:bg-white/5 hover:text-white border border-transparent'
    }`;

  return (
    <div className="w-full h-full flex bg-black text-white overflow-hidden">
      <aside className="hidden md:flex w-64 shrink-0 border-r border-white/10 bg-black/90 backdrop-blur-xl flex-col p-4">
        <div className="flex items-center gap-3 mb-6 p-3 rounded-2xl ui-glass ui-glass-subtle">
          <div className="w-10 h-10 rounded-xl bg-brand-blue/15 border border-brand-blue/25 flex items-center justify-center text-brand-blue">
            <Home size={18} />
          </div>
          <div>
            <div className="text-[14px] font-bold text-white leading-tight">Citizens</div>
            <div className="text-[10px] text-brand-blue uppercase tracking-wider font-mono mt-0.5">
              Neighbourhood match
            </div>
          </div>
        </div>

        <nav className="flex flex-col gap-1.5 flex-1">
          <button type="button" onClick={() => setActiveView('profile')} className={navButtonClass('profile')}>
            <User size={15} />
            <span>Your profile</span>
          </button>
          <button
            type="button"
            onClick={() => profile && setActiveView('results')}
            disabled={!profile}
            className={`${navButtonClass('results')} disabled:opacity-40`}
          >
            <ListOrdered size={15} />
            <span>Ranked areas</span>
          </button>
          <button
            type="button"
            onClick={() => selectedNeighbourhood && setActiveView('detail')}
            disabled={!selectedNeighbourhood}
            className={`${navButtonClass('detail')} disabled:opacity-40`}
          >
            <Home size={15} />
            <span>Area detail</span>
          </button>
        </nav>

        <div className="mt-auto pt-4 border-t border-white/10">
          <p className="text-[10px] text-apple-secondary leading-relaxed px-1">
            Matches blend live AQI signals with rent, commute, and amenity data — guidance only, not
            medical or legal advice.
          </p>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* How it works — judge-friendly */}
        <div className="shrink-0 border-b border-white/10 bg-gradient-to-r from-brand-blue/10 via-black to-black px-5 py-4 md:px-8">
          <div className="max-w-5xl mx-auto">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-xl bg-brand-blue/15 border border-brand-blue/30 flex items-center justify-center shrink-0">
                <Info size={16} className="text-brand-blue" />
              </div>
              <div className="min-w-0">
                <h1 className="text-lg md:text-xl font-bold text-white tracking-tight">
                  Find a neighbourhood that fits your life
                </h1>
                <p className="text-xs md:text-sm text-apple-secondary mt-1 leading-relaxed max-w-3xl">
                  Tell us your budget, family, health needs, workplace, and priorities. We rank
                  Bengaluru areas using <strong className="text-white/90">AQI</strong> (breathability),{' '}
                  <strong className="text-white/90">rent</strong> (affordability),{' '}
                  <strong className="text-white/90">commute</strong> (time to work), and amenities
                  (metro, parks, schools, hospitals). Higher rank = better fit — not a guarantee of
                  air quality on any given day.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {[
                    { icon: Wind, label: 'AQI & pollution' },
                    { icon: IndianRupee, label: 'Rent band' },
                    { icon: Train, label: 'Commute & metro' },
                    { icon: Home, label: 'Amenities' },
                  ].map(({ icon: Icon, label }) => (
                    <span
                      key={label}
                      className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-apple-secondary"
                    >
                      <Icon size={11} className="text-brand-blue" />
                      {label}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
          <div className="max-w-5xl mx-auto">
            <AnimatePresence mode="wait">
              {activeView === 'profile' && (
                <motion.div
                  key="profile"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="space-y-4"
                >
                  <MotionCard glass="strong" interactive={false} className="p-5 md:p-7">
                    <h2 className="text-base font-bold text-white mb-1">Build your profile</h2>
                    <p className="text-xs text-apple-secondary mb-5">
                      Used only for this session to rank neighbourhoods. No medical diagnosis.
                    </p>
                    <ProfileBuilderForm onSubmit={handleProfileSubmit} />
                  </MotionCard>
                </motion.div>
              )}

              {activeView === 'results' && (
                <motion.div
                  key="results"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                >
                  {isLoading && (
                    <div className="flex flex-col items-center justify-center py-20 gap-3">
                      <div className="w-8 h-8 border-2 border-brand-blue border-t-transparent rounded-full animate-spin" />
                      <span className="text-xs font-mono text-apple-secondary uppercase tracking-wider">
                        Matching neighbourhoods…
                      </span>
                    </div>
                  )}
                  {isError && !useLocalMockData && (
                    <Glass className="p-6 border border-brand-red/25">
                      <div className="flex items-start gap-3">
                        <AlertOctagon className="text-brand-red shrink-0" size={20} />
                        <div>
                          <h3 className="text-sm font-bold text-white">Could not load matches</h3>
                          <p className="text-xs text-apple-secondary mt-1">
                            {(error as Error)?.message || 'API unavailable'}
                          </p>
                          <div className="flex flex-wrap gap-2 mt-4">
                            <button
                              type="button"
                              onClick={() => void refetch()}
                              className="min-h-[40px] px-4 rounded-full bg-brand-blue text-white text-xs font-bold inline-flex items-center gap-2"
                            >
                              <RefreshCw size={14} /> Retry
                            </button>
                            <button
                              type="button"
                              onClick={enableDeveloperMockMode}
                              className="min-h-[40px] px-4 rounded-full border border-white/15 text-xs font-semibold text-apple-secondary hover:text-white"
                            >
                              Use demo matches
                            </button>
                          </div>
                        </div>
                      </div>
                    </Glass>
                  )}
                  {!isLoading && (activeMatches.length > 0 || useLocalMockData) && (
                    <RankedResultsList
                      matches={activeMatches}
                      onSelect={handleSelectNeighbourhood}
                      selectedId={selectedNeighbourhood?.id}
                    />
                  )}
                </motion.div>
              )}

              {activeView === 'detail' && selectedNeighbourhood && profile && (
                <motion.div
                  key="detail"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                >
                  <NeighbourhoodDetailPanel
                    match={selectedNeighbourhood}
                    profile={profile}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}
