import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'motion/react';
import { 
  User, 
  ListOrdered, 
  BarChart3, 
  Settings, 
  HelpCircle, 
  Bell, 
  Database, 
  RefreshCw, 
  FileCode, 
  AlertOctagon, 
  Compass
} from 'lucide-react';
import { CitizenProfile, NeighbourhoodMatch } from '../types/citizen';
import { getNeighbourhoodMatches, MOCK_MATCHES } from '../services/citizenService';
import ProfileBuilderForm from '../components/citizen/ProfileBuilderForm';
import RankedResultsList from '../components/citizen/RankedResultsList';
import NeighbourhoodDetailPanel from '../components/citizen/NeighbourhoodDetailPanel';

type ActiveView = 'profile' | 'results' | 'detail';

export default function CitizenModePage() {
  const [activeView, setActiveView] = useState<ActiveView>('profile');
  const [profile, setProfile] = useState<CitizenProfile | null>(null);
  const [selectedNeighbourhood, setSelectedNeighbourhood] = useState<NeighbourhoodMatch | null>(null);
  
  // Developer Override: explicitly toggle to mock data to view the results/details screens in sandbox preview
  const [useLocalMockData, setUseLocalMockData] = useState<boolean>(false);

  // TanStack Query for neighborhood matches
  const { data: matches, isLoading, isError, error, refetch } = useQuery<NeighbourhoodMatch[]>({
    queryKey: ['neighbourhoodMatches', profile],
    queryFn: () => {
      if (!profile) return Promise.resolve([]);
      return getNeighbourhoodMatches(profile);
    },
    enabled: !!profile && !useLocalMockData,
    retry: false, // Don't retry endlessly in development
  });

  // Decide what data to render
  const activeMatches = useLocalMockData ? MOCK_MATCHES : (matches || []);

  // Form Submission
  const handleProfileSubmit = (submittedProfile: CitizenProfile) => {
    setProfile(submittedProfile);
    
    if (useLocalMockData) {
      // Bypassing real API and going straight to results
      setActiveView('results');
    } else {
      // Trigger query and transition to results after load
      setActiveView('results');
    }
  };

  // Neighborhood Selection
  const handleSelectNeighbourhood = (match: NeighbourhoodMatch) => {
    setSelectedNeighbourhood(match);
    setActiveView('detail');
  };

  // Back to Results
  const handleBackToResults = () => {
    setActiveView('results');
  };

  // Back to Profile
  const handleBackToProfile = () => {
    setActiveView('profile');
  };

  // Explicit Toggle to Mock Data
  const enableDeveloperMockMode = () => {
    setUseLocalMockData(true);
    if (!profile) {
      // Populate a standard default profile to make results cohesive
      setProfile({
        rentBudget: 45000,
        familySize: 2,
        healthConditions: ['none'],
        officeLocation: 'Indiranagar',
        maxCommuteMinutes: 45,
        priorities: ['metro', 'low_aqi']
      });
    }
    setActiveView('results');
  };

  // Reset all state
  const handleReset = () => {
    setProfile(null);
    setSelectedNeighbourhood(null);
    setUseLocalMockData(false);
    setActiveView('profile');
  };

  return (
    <div id="citizen-mode-page" className="min-h-screen bg-apple-bg flex text-[#e0e2ed]">
      
      {/* SIDEBAR */}
      <aside id="sidebar" className="w-[260px] border-r border-apple-border bg-black flex flex-col justify-between shrink-0 hidden md:flex">
        <div className="p-6 space-y-8">
          
          {/* Logo / Title */}
          <div className="flex items-center space-x-3 select-none">
            <div className="w-9 h-9 rounded-lg bg-brand-blue flex items-center justify-center text-white">
              <Compass className="w-5 h-5 animate-spin-slow" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white tracking-wide uppercase">Citizen Sentinel</h2>
              <p className="text-[10px] text-apple-secondary font-semibold uppercase tracking-wider">Bengaluru Sector</p>
            </div>
          </div>

          {/* Nav Links */}
          <nav id="sidebar-navigation" className="space-y-1.5">
            <button
              id="sidebar-nav-profile"
              onClick={() => setActiveView('profile')}
              className={`w-full min-h-[44px] px-4 py-2.5 rounded-lg flex items-center space-x-3 text-sm font-semibold transition-all duration-200 cursor-pointer ${
                activeView === 'profile'
                  ? 'bg-brand-blue/15 text-brand-blue border border-brand-blue/20'
                  : 'text-apple-secondary hover:text-white hover:bg-apple-card'
              }`}
            >
              <User className="w-4 h-4 shrink-0" />
              <span>Profile Builder</span>
            </button>

            <button
              id="sidebar-nav-results"
              disabled={!profile && activeMatches.length === 0}
              onClick={() => setActiveView('results')}
              className={`w-full min-h-[44px] px-4 py-2.5 rounded-lg flex items-center space-x-3 text-sm font-semibold transition-all duration-200 cursor-pointer ${
                activeView === 'results'
                  ? 'bg-brand-blue/15 text-brand-blue border border-brand-blue/20'
                  : 'text-apple-secondary hover:text-white hover:bg-apple-card disabled:opacity-40 disabled:cursor-not-allowed'
              }`}
            >
              <ListOrdered className="w-4 h-4 shrink-0" />
              <span>Ranked Results</span>
            </button>

            <button
              id="sidebar-nav-details"
              disabled={!selectedNeighbourhood}
              onClick={() => setActiveView('detail')}
              className={`w-full min-h-[44px] px-4 py-2.5 rounded-lg flex items-center space-x-3 text-sm font-semibold transition-all duration-200 cursor-pointer ${
                activeView === 'detail'
                  ? 'bg-brand-blue/15 text-brand-blue border border-brand-blue/20'
                  : 'text-apple-secondary hover:text-white hover:bg-apple-card disabled:opacity-40 disabled:cursor-not-allowed'
              }`}
            >
              <BarChart3 className="w-4 h-4 shrink-0" />
              <span>Match Details</span>
            </button>
          </nav>
        </div>

        {/* Sidebar Footer options */}
        <div className="p-6 border-t border-apple-border/50 space-y-4">
          <div className="flex items-center justify-between text-xs text-apple-secondary">
            <span>Server Mode:</span>
            {useLocalMockData ? (
              <span className="text-brand-orange font-semibold font-mono flex items-center space-x-1">
                <Database className="w-3.5 h-3.5" />
                <span>LOCAL_MOCK</span>
              </span>
            ) : (
              <span className="text-brand-green font-semibold font-mono flex items-center space-x-1">
                <RefreshCw className="w-3.5 h-3.5" />
                <span>API_LIVE</span>
              </span>
            )}
          </div>
          
          <div className="space-y-1">
            <button className="w-full text-left text-xs text-apple-secondary hover:text-white flex items-center space-x-2 py-1 select-none">
              <Settings className="w-4 h-4" />
              <span>System Settings</span>
            </button>
            <button className="w-full text-left text-xs text-apple-secondary hover:text-white flex items-center space-x-2 py-1 select-none">
              <HelpCircle className="w-4 h-4" />
              <span>Support & Docs</span>
            </button>
          </div>
        </div>

      </aside>

      {/* MAIN CONTAINER */}
      <main id="main-content" className="flex-1 flex flex-col min-w-0 bg-apple-bg">
        
        {/* Navigation / Header */}
        <header id="header-bar" className="h-16 border-b border-apple-border px-6 flex justify-between items-center select-none bg-black/40">
          <div className="flex items-center space-x-3">
            {/* Mobile Sidebar Toggle alternative title */}
            <h1 className="text-lg font-bold text-white tracking-tight md:text-xl">Citizen Mode</h1>
          </div>

          {/* Action Icons */}
          <div className="flex items-center space-x-4">
            {/* Developer Banner */}
            {useLocalMockData && (
              <div className="hidden lg:flex items-center space-x-2 bg-brand-orange/15 border border-brand-orange/30 px-3 py-1 rounded-full text-xs text-brand-orange font-semibold">
                <Database className="w-3.5 h-3.5" />
                <span>Sandbox Developer Mode Enabled</span>
              </div>
            )}

            <button
              id="btn-header-notifications"
              className="w-11 h-11 flex items-center justify-center rounded-xl bg-apple-card hover:bg-apple-border text-white border border-apple-border relative active:scale-95 transition-all duration-200 cursor-pointer animate-none"
              aria-label="View notifications"
            >
              <Bell className="w-5 h-5" />
              <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-brand-red" />
            </button>
            
            <button
              id="btn-header-settings"
              className="w-11 h-11 flex items-center justify-center rounded-xl bg-apple-card hover:bg-apple-border text-white border border-apple-border active:scale-95 transition-all duration-200 cursor-pointer"
              aria-label="Open settings"
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* VIEW SCROLLER */}
        <div className="flex-1 overflow-y-auto p-6 max-w-5xl w-full mx-auto space-y-6">
          
          <AnimatePresence mode="wait">
            
            {/* State 1: LOADING */}
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
                  <p className="text-apple-secondary text-sm">Evaluating live air quality levels, rental budgets, and transit route grids...</p>
                </div>
              </motion.div>
            )}

            {/* State 2: ERROR */}
            {isError && !isLoading && !useLocalMockData && (
              <motion.div
                key="error"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="space-y-6 max-w-2xl mx-auto"
              >
                <div id="api-error-card" className="p-6 bg-brand-red/10 border border-brand-red/30 rounded-2xl flex items-start space-x-4">
                  <div className="w-12 h-12 rounded-full bg-brand-red/20 flex items-center justify-center text-brand-red shrink-0">
                    <AlertOctagon className="w-6 h-6" />
                  </div>
                  <div className="space-y-2 flex-1">
                    <h3 className="text-lg font-bold text-white">Backend Connection Interrupted</h3>
                    <p className="text-apple-secondary text-sm leading-relaxed">
                      We tried querying the database at <code className="bg-black/50 px-1 py-0.5 rounded font-mono text-brand-red">/api/citizen/matches</code>, 
                      but the real endpoint doesn't exist yet (which is completely normal in the preview environment!).
                    </p>
                    <p className="text-xs text-brand-red/90 font-mono font-medium leading-relaxed">
                      Details: {error instanceof Error ? error.message : 'API 404 Endpoint Not Found'}
                    </p>
                  </div>
                </div>

                {/* Developer onboarding option */}
                <div id="dev-override-card" className="p-6 bg-apple-card border border-apple-border rounded-2xl space-y-4">
                  <div className="flex items-center space-x-2.5 text-brand-orange">
                    <FileCode className="w-5 h-5" />
                    <h4 className="font-semibold text-white">Developer Sandbox Override</h4>
                  </div>
                  <p className="text-apple-secondary text-xs leading-relaxed">
                    According to security constraints, the API function correctly propagation error states without silently falling back. 
                    However, you can explicitly override using this sandbox trigger to populate the UI with <code className="text-white font-mono bg-black px-1 rounded">MOCK_MATCHES</code> for evaluation.
                  </p>
                  <div className="flex flex-wrap gap-3 pt-2">
                    <button
                      id="btn-dev-use-mock"
                      onClick={enableDeveloperMockMode}
                      className="min-h-[44px] px-5 py-2 bg-brand-orange hover:bg-brand-orange/95 active:bg-brand-orange/90 text-black font-bold rounded-xl transition-all text-xs flex items-center space-x-2"
                    >
                      <Database className="w-4 h-4" />
                      <span>Use Sandbox Mock Dataset</span>
                    </button>
                    <button
                      id="btn-retry-api"
                      onClick={() => refetch()}
                      className="min-h-[44px] px-5 py-2 bg-apple-card hover:bg-apple-border border border-apple-border active:bg-apple-modal text-white font-bold rounded-xl transition-all text-xs flex items-center space-x-2"
                    >
                      <RefreshCw className="w-4 h-4" />
                      <span>Retry Live API Call</span>
                    </button>
                    <button
                      onClick={handleBackToProfile}
                      className="min-h-[44px] px-4 py-2 text-apple-secondary hover:text-white text-xs font-semibold"
                    >
                      Back to Profile
                    </button>
                  </div>
                </div>
              </motion.div>
            )}

            {/* State 3: GENERAL SCREENS (PROFILE / RESULTS / DETAIL) */}
            {!isLoading && (!isError || useLocalMockData) && (
              <div className="space-y-6">
                
                {/* Profile Builder Screen */}
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
                        Configure your parameters for optimal environmental and civic matchmaking.
                      </p>
                    </div>

                    <div className="max-w-2xl">
                      <ProfileBuilderForm 
                        onSubmit={handleProfileSubmit} 
                        isSubmitting={isLoading} 
                      />
                    </div>
                  </motion.div>
                )}

                {/* Ranked Results Screen */}
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
                      profile={profile || {
                        rentBudget: 45000,
                        familySize: 2,
                        healthConditions: ['none'],
                        officeLocation: 'Indiranagar',
                        maxCommuteMinutes: 45,
                        priorities: ['metro', 'low_aqi']
                      }}
                      onSelectNeighbourhood={handleSelectNeighbourhood}
                      onBackToProfile={handleBackToProfile}
                    />
                  </motion.div>
                )}

                {/* Neighbourhood Detail Screen */}
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
                      profile={profile || {
                        rentBudget: 45000,
                        familySize: 2,
                        healthConditions: ['none'],
                        officeLocation: 'Indiranagar',
                        maxCommuteMinutes: 45,
                        priorities: ['metro', 'low_aqi']
                      }}
                      onBack={handleBackToResults}
                    />
                  </motion.div>
                )}

              </div>
            )}

          </AnimatePresence>

        </div>

      </main>

    </div>
  );
}
