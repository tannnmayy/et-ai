import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import {
  AlertOctagon,
  BarChart3,
  Database,
  FileCode,
  ListOrdered,
  RefreshCw,
  User,
} from 'lucide-react';
import type { CitizenProfile, NeighbourhoodMatch } from '../types/citizen';
import { getNeighbourhoodMatches, MOCK_MATCHES } from '../services/citizenService';
import ProfileBuilderForm from '../components/citizen/ProfileBuilderForm';
import RankedResultsList from '../components/citizen/RankedResultsList';
import NeighbourhoodDetailPanel from '../components/citizen/NeighbourhoodDetailPanel';

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
 * Citizen Mode experience embedded in the main SPA shell.
 * Shared TopNav owns the City Admin / Citizen toggle; this page owns
 * Profile → Ranked Results → Match Details.
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
        ? 'bg-brand-blue text-white shadow-lg shadow-brand-blue/10 font-bold'
        : 'text-apple-secondary hover:bg-apple-card hover:text-white border border-transparent'
    }`;

  return (
    <div id="citizen-mode-page" className="w-full h-full flex bg-black text-[#e0e2ed] overflow-hidden">
      <aside
        id="citizen-sidebar"
        className="hidden md:flex w-64 shrink-0 border-r border-apple-border bg-apple-bg flex-col p-4"
      >
        <div className="flex items-center gap-3 mb-8 p-3 bg-apple-card/30 rounded-xl border border-apple-border/20">
          <div className="w-10 h-10 rounded-xl bg-brand-blue/10 border border-brand-blue/20 flex items-center justify-center text-brand-blue">
            <User size={18} />
          </div>
          <div>
            <div className="text-[14px] font-bold text-white font-sans leading-tight">Citizen Mode</div>
            <div className="text-[10px] text-brand-blue uppercase tracking-wider font-mono font-medium mt-0.5">
              Neighbourhood Match
            </div>
          </div>
        </div>

        <nav className="flex flex-col gap-1.5 flex-1">
          <button
            type="button"
            id="sidebar-nav-profile"
            onClick={() => setActiveView('profile')}
            className={navButtonClass('profile')}
          >
            <User size={16} />
            <span>Profile Builder</span>
          </button>

          <button
            type="button"
            id="sidebar-nav-results"
            disabled={!profile && activeMatches.length === 0}
            onClick={() => setActiveView('results')}
            className={`${navButtonClass('results')} disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            <ListOrdered size={16} />
            <span>Ranked Results</span>
          </button>

          <button
            type="button"
            id="sidebar-nav-details"
            disabled={!selectedNeighbourhood}
            onClick={() => setActiveView('detail')}
            className={`${navButtonClass('detail')} disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            <BarChart3 size={16} />
            <span>Match Details</span>
          </button>
        </nav>

        <div className="p-3 border-t border-apple-border/50 text-[10px] font-mono text-apple-secondary flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span>DATA SOURCE</span>
            {useLocalMockData ? (
              <span className="text-brand-orange font-semibold flex items-center gap-1">
                <Database className="w-3 h-3" />
                MOCK
              </span>
            ) : (
              <span className="text-brand-green font-semibold flex items-center gap-1">
                <RefreshCw className="w-3 h-3" />
                LIVE API
              </span>
            )}
          </div>
          <div className="text-brand-green flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse" />
            CITIZEN MATCHING V1
          </div>
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <header className="h-12 shrink-0 border-b border-apple-border px-4 md:px-6 flex items-center justify-between bg-black/40">
          <h1 className="text-sm md:text-base font-bold text-white tracking-tight">
            Find Your Neighbourhood
          </h1>
          {useLocalMockData && (
            <div className="flex items-center space-x-2 bg-brand-orange/15 border border-brand-orange/30 px-3 py-1 rounded-full text-[10px] text-brand-orange font-semibold">
              <Database className="w-3.5 h-3.5" />
              <span>Sandbox Mock Mode</span>
            </div>
          )}
        </header>

        <div className="flex-1 overflow-y-auto p-4 md:p-6 max-w-5xl w-full mx-auto">
          <AnimatePresence mode="wait">
            {isLoading && !useLocalMockData && (
              <motion.div
                key="loading"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center justify-center min-h-[400px] text-center space-y-4"
              >
                <div className="w-12 h-12 rounded-full border-2 border-brand-blue/30 border-t-brand-blue animate-spin" />
                <div className="space-y-1">
                  <h3 className="text-lg font-semibold text-white">Computing Optimal Matches</h3>
                  <p className="text-apple-secondary text-sm">
                    Evaluating air quality, rental budgets, and commute routes...
                  </p>
                </div>
              </motion.div>
            )}

            {isError && !isLoading && !useLocalMockData && (
              <motion.div
                key="error"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="space-y-6 max-w-2xl mx-auto"
              >
                <div
                  id="api-error-card"
                  className="p-6 bg-brand-red/10 border border-brand-red/30 rounded-2xl flex items-start space-x-4"
                >
                  <div className="w-12 h-12 rounded-full bg-brand-red/20 flex items-center justify-center text-brand-red shrink-0">
                    <AlertOctagon className="w-6 h-6" />
                  </div>
                  <div className="space-y-2 flex-1">
                    <h3 className="text-lg font-bold text-white">Could not reach matching API</h3>
                    <p className="text-apple-secondary text-sm leading-relaxed">
                      Request to{' '}
                      <code className="bg-black/50 px-1 py-0.5 rounded font-mono text-brand-red">
                        POST /api/citizen/matches
                      </code>{' '}
                      failed. Ensure the FastAPI backend is running on port 8010.
                    </p>
                    <p className="text-xs text-brand-red/90 font-mono font-medium leading-relaxed">
                      {error instanceof Error ? error.message : 'Unknown API error'}
                    </p>
                  </div>
                </div>

                <div
                  id="dev-override-card"
                  className="p-6 bg-apple-card border border-apple-border rounded-2xl space-y-4"
                >
                  <div className="flex items-center space-x-2.5 text-brand-orange">
                    <FileCode className="w-5 h-5" />
                    <h4 className="font-semibold text-white">Developer Sandbox Override</h4>
                  </div>
                  <p className="text-apple-secondary text-xs leading-relaxed">
                    Errors are not silently replaced with mock data. You can explicitly load{' '}
                    <code className="text-white font-mono bg-black px-1 rounded">MOCK_MATCHES</code>{' '}
                    to review the UI, or retry the live endpoint.
                  </p>
                  <div className="flex flex-wrap gap-3 pt-2">
                    <button
                      id="btn-dev-use-mock"
                      type="button"
                      onClick={enableDeveloperMockMode}
                      className="min-h-[44px] px-5 py-2 bg-brand-orange hover:bg-brand-orange/95 text-black font-bold rounded-xl transition-all text-xs flex items-center space-x-2"
                    >
                      <Database className="w-4 h-4" />
                      <span>Use Sandbox Mock Dataset</span>
                    </button>
                    <button
                      id="btn-retry-api"
                      type="button"
                      onClick={() => refetch()}
                      className="min-h-[44px] px-5 py-2 bg-apple-card hover:bg-apple-border border border-apple-border text-white font-bold rounded-xl transition-all text-xs flex items-center space-x-2"
                    >
                      <RefreshCw className="w-4 h-4" />
                      <span>Retry Live API Call</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveView('profile')}
                      className="min-h-[44px] px-4 py-2 text-apple-secondary hover:text-white text-xs font-semibold"
                    >
                      Back to Profile
                    </button>
                  </div>
                </div>
              </motion.div>
            )}

            {!isLoading && (!isError || useLocalMockData) && (
              <div className="space-y-6">
                {activeView === 'profile' && (
                  <motion.div
                    key="profile-builder"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -12 }}
                    transition={{ duration: 0.25 }}
                    className="space-y-6"
                  >
                    <div className="space-y-2">
                      <h2 className="text-2xl font-bold text-white tracking-tight">Build Your Profile</h2>
                      <p className="text-apple-secondary text-sm">
                        Configure rent, commute, health, and priorities for neighbourhood matching.
                      </p>
                    </div>
                    <div className="max-w-2xl">
                      <ProfileBuilderForm onSubmit={handleProfileSubmit} isSubmitting={isLoading} />
                    </div>
                  </motion.div>
                )}

                {activeView === 'results' && (
                  <motion.div
                    key="results-list"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -12 }}
                    transition={{ duration: 0.25 }}
                  >
                    <RankedResultsList
                      matches={activeMatches}
                      profile={profile || DEFAULT_PROFILE}
                      onSelectNeighbourhood={handleSelectNeighbourhood}
                      onBackToProfile={() => setActiveView('profile')}
                    />
                  </motion.div>
                )}

                {activeView === 'detail' && selectedNeighbourhood && (
                  <motion.div
                    key="detail-panel"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -12 }}
                    transition={{ duration: 0.25 }}
                  >
                    <NeighbourhoodDetailPanel
                      match={selectedNeighbourhood}
                      profile={profile || DEFAULT_PROFILE}
                      onBack={() => setActiveView('results')}
                    />
                  </motion.div>
                )}
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
