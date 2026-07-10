import React from 'react';
import { Satellite, User, Globe } from 'lucide-react';

interface TopNavProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  language: 'EN' | 'HI' | 'KN';
  setLanguage: (lang: 'EN' | 'HI' | 'KN') => void;
  role: 'admin' | 'citizen';
  setRole: (role: 'admin' | 'citizen') => void;
}

export default function TopNav({
  activeTab,
  setActiveTab,
  language,
  setLanguage,
  role,
  setRole,
}: TopNavProps) {
  return (
    <nav className="fixed top-0 left-0 w-full h-16 bg-apple-card/90 backdrop-blur-md border-b border-apple-border z-50 flex items-center justify-between px-6 sm:px-8">
      {/* Logo Section */}
      <div className="flex items-center gap-3 cursor-pointer" onClick={() => setActiveTab('map')}>
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-brand-blue/10 border border-brand-blue/30 text-brand-blue animate-pulse">
          <Satellite size={18} />
        </div>
        <span className="text-xl font-bold tracking-tight text-white font-sans">
          AQI Sentinel
        </span>
      </div>

      {/* Navigation Items */}
      <div className="hidden md:flex items-center gap-8 h-full">
        {['map', 'enforcement', 'copilot', 'neighbourhoods'].map((tab) => {
          const isActive = activeTab === tab || (tab === 'neighbourhoods' && activeTab === 'coming-soon');
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`h-full px-2 flex items-center relative text-xs font-semibold tracking-wider uppercase transition-colors duration-200 ${
                isActive
                  ? 'text-brand-blue font-bold'
                  : 'text-apple-secondary hover:text-white'
              }`}
            >
              {tab === 'neighbourhoods' ? 'Neighbourhoods' : tab}
              {isActive && (
                <div className="absolute bottom-0 left-0 w-full h-0.5 bg-brand-blue rounded-t" />
              )}
            </button>
          );
        })}
      </div>

      {/* Control Actions / Settings */}
      <div className="flex items-center gap-4 sm:gap-6">
        {/* Role Selector Toggle */}
        <div className="hidden sm:flex items-center bg-apple-card border border-apple-border rounded-full p-0.5">
          <button
            onClick={() => setRole('admin')}
            className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-full transition-all duration-200 ${
              role === 'admin'
                ? 'bg-apple-modal text-white border border-apple-border/50 shadow-sm'
                : 'text-apple-secondary hover:text-white'
            }`}
          >
            City Admin
          </button>
          <button
            onClick={() => setRole('citizen')}
            className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-full transition-all duration-200 ${
              role === 'citizen'
                ? 'bg-apple-modal text-white border border-apple-border/50 shadow-sm'
                : 'text-apple-secondary hover:text-white'
            }`}
          >
            Citizen
          </button>
        </div>

        {/* Languages Selection Panel */}
        <div className="flex items-center gap-1.5 text-[11px] font-medium bg-apple-card/60 px-3 py-1.5 rounded-full border border-apple-border text-apple-secondary select-none">
          <button
            onClick={() => setLanguage('EN')}
            className={`cursor-pointer hover:text-white transition-colors uppercase ${
              language === 'EN' ? 'text-brand-blue font-bold' : ''
            }`}
          >
            EN
          </button>
          <span>·</span>
          <button
            onClick={() => setLanguage('HI')}
            className={`cursor-pointer hover:text-white transition-colors ${
              language === 'HI' ? 'text-brand-blue font-bold' : ''
            }`}
          >
            हिंदी
          </button>
          <span>·</span>
          <button
            onClick={() => setLanguage('KN')}
            className={`cursor-pointer hover:text-white transition-colors ${
              language === 'KN' ? 'text-brand-blue font-bold' : ''
            }`}
          >
            ಕನ್ನಡ
          </button>
        </div>

        {/* Profile Button */}
        <button className="w-8 h-8 rounded-full bg-apple-modal border border-apple-border flex items-center justify-center text-apple-secondary hover:text-white transition-colors shadow-sm">
          <User size={15} />
        </button>
      </div>
    </nav>
  );
}
