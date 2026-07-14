import React from 'react';
import { Satellite, User } from 'lucide-react';
import type { AppRole } from './MainLayout';

interface TopNavProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  language: 'EN' | 'HI' | 'KN';
  setLanguage: (lang: 'EN' | 'HI' | 'KN') => void;
  role: AppRole;
  setRole: (role: AppRole) => void;
}

const ADMIN_TABS = ['map', 'enforcement', 'copilot', 'neighbourhoods'] as const;

export default function TopNav({
  activeTab,
  setActiveTab,
  language,
  setLanguage,
  role,
  setRole,
}: TopNavProps) {
  const isCitizen = role === 'citizen';

  return (
    <nav className="fixed top-0 left-0 w-full h-16 bg-apple-card/90 backdrop-blur-md border-b border-apple-border z-50 flex items-center justify-between px-6 sm:px-8">
      <div
        className="flex items-center gap-3 cursor-pointer"
        onClick={() => setActiveTab(isCitizen ? 'citizen' : 'map')}
      >
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-brand-blue/10 border border-brand-blue/30 text-brand-blue animate-pulse">
          <Satellite size={18} />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-xl font-bold tracking-tight text-white font-sans">
            AQI Sentinel
          </span>
          {isCitizen && (
            <span className="text-[9px] font-semibold uppercase tracking-wider text-brand-blue">
              Citizen Mode
            </span>
          )}
        </div>
      </div>

      <div className="hidden md:flex items-center gap-8 h-full">
        {!isCitizen &&
          ADMIN_TABS.map((tab) => {
            const isActive =
              activeTab === tab || (tab === 'neighbourhoods' && activeTab === 'coming-soon');
            return (
              <button
                key={tab}
                type="button"
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

        {isCitizen && (
          <div className="h-full px-2 flex items-center text-xs font-semibold tracking-wider uppercase text-brand-blue font-bold relative">
            Neighbourhood Finder
            <div className="absolute bottom-0 left-0 w-full h-0.5 bg-brand-blue rounded-t" />
          </div>
        )}
      </div>

      <div className="flex items-center gap-4 sm:gap-6">
        <div className="flex items-center bg-apple-card border border-apple-border rounded-full p-0.5">
          <button
            type="button"
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
            type="button"
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

        <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-medium bg-apple-card/60 px-3 py-1.5 rounded-full border border-apple-border text-apple-secondary select-none">
          <button
            type="button"
            onClick={() => setLanguage('EN')}
            className={`cursor-pointer hover:text-white transition-colors uppercase ${
              language === 'EN' ? 'text-brand-blue font-bold' : ''
            }`}
          >
            EN
          </button>
          <span>·</span>
          <button
            type="button"
            onClick={() => setLanguage('HI')}
            className={`cursor-pointer hover:text-white transition-colors ${
              language === 'HI' ? 'text-brand-blue font-bold' : ''
            }`}
          >
            हिंदी
          </button>
          <span>·</span>
          <button
            type="button"
            onClick={() => setLanguage('KN')}
            className={`cursor-pointer hover:text-white transition-colors ${
              language === 'KN' ? 'text-brand-blue font-bold' : ''
            }`}
          >
            ಕನ್ನಡ
          </button>
        </div>

        <button
          type="button"
          className="w-8 h-8 rounded-full bg-apple-modal border border-apple-border flex items-center justify-center text-apple-secondary hover:text-white transition-colors shadow-sm"
          aria-label="Profile"
        >
          <User size={15} />
        </button>
      </div>
    </nav>
  );
}
