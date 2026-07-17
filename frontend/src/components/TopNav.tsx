import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Satellite, LogOut, LayoutDashboard } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../context/SessionContext';
import { LANGUAGE_SHORT, type ApiLanguage } from '../i18n/lang';
import { useT } from '../i18n/useT';

interface TopNavProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export default function TopNav({ activeTab, setActiveTab }: TopNavProps) {
  const navigate = useNavigate();
  const { session, language, setLanguage, clearSession } = useSession();
  const { t } = useT();
  const isCitizen = session?.role === 'citizen';
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const adminTabs = useMemo(
    () =>
      [
        { id: 'map', label: t('nav.map') },
        { id: 'enforcement', label: t('nav.enforcement') },
        { id: 'copilot', label: t('nav.copilot') },
        { id: 'citizens', label: t('nav.citizens') || t('nav.neighbourhoods') },
        { id: 'insights', label: t('nav.insights') },
      ] as const,
    [t],
  );

  const roleLabelText = (role: string) => {
    if (role === 'enforcement') return t('role.enforcement');
    if (role === 'citizen') return t('role.citizen');
    return t('role.guest');
  };

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const initials = (session?.name || 'G')
    .split(/\s+/)
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <nav className="fixed top-0 left-0 w-full h-16 bg-black/70 backdrop-blur-xl border-b border-white/10 z-50 flex items-center justify-between px-4 sm:px-8">
      <div
        className="flex items-center gap-3 cursor-pointer min-w-0"
        onClick={() => setActiveTab(isCitizen ? 'citizen' : 'map')}
        onKeyDown={(e) => {
          if (e.key === 'Enter') setActiveTab(isCitizen ? 'citizen' : 'map');
        }}
        role="button"
        tabIndex={0}
      >
        <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-brand-blue/15 border border-brand-blue/30 text-brand-blue shadow-[0_0_20px_rgba(10,132,255,0.2)]">
          <Satellite size={18} />
        </div>
        <div className="flex flex-col leading-tight min-w-0">
          <span className="text-lg sm:text-xl font-bold tracking-tight text-white font-sans truncate">
            {t('app.name')}
          </span>
          {isCitizen && (
            <span className="text-[9px] font-semibold uppercase tracking-wider text-brand-blue">
              {t('app.citizen_mode')}
            </span>
          )}
        </div>
      </div>

      <div className="hidden lg:flex items-center gap-6 h-full">
        {!isCitizen &&
          adminTabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`h-full px-2 flex items-center relative text-xs font-semibold tracking-wider uppercase transition-colors duration-200 min-h-[44px] ${
                  isActive
                    ? 'text-brand-blue font-bold'
                    : 'text-apple-secondary hover:text-white'
                }`}
              >
                {tab.label}
                {isActive && (
                  <div className="absolute bottom-0 left-0 w-full h-0.5 bg-brand-blue rounded-t shadow-[0_0_12px_rgba(10,132,255,0.6)]" />
                )}
              </button>
            );
          })}

        {isCitizen && (
          <div className="h-full px-2 flex items-center text-xs font-semibold tracking-wider uppercase text-brand-blue font-bold relative">
            {t('nav.neighbourhood_finder')}
            <div className="absolute bottom-0 left-0 w-full h-0.5 bg-brand-blue rounded-t" />
          </div>
        )}
      </div>

      <div className="flex items-center gap-3 sm:gap-5">
        <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-medium bg-white/5 px-3 py-1.5 rounded-full border border-white/10 text-apple-secondary select-none">
          {(['en', 'hi', 'kn'] as ApiLanguage[]).map((lang, i) => (
            <React.Fragment key={lang}>
              {i > 0 && <span className="text-white/20">·</span>}
              <button
                type="button"
                onClick={() => setLanguage(lang)}
                className={`cursor-pointer hover:text-white transition-colors min-h-[28px] px-0.5 ${
                  language === lang ? 'text-brand-blue font-bold' : ''
                } ${lang === 'en' ? 'uppercase' : ''}`}
              >
                {LANGUAGE_SHORT[lang]}
              </button>
            </React.Fragment>
          ))}
        </div>

        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 pl-1 pr-2 sm:pr-3 py-1 rounded-full bg-white/5 border border-white/10 hover:border-white/20 transition-colors min-h-[44px]"
            aria-label={t('common.profile_menu')}
          >
            <span className="w-8 h-8 rounded-full bg-brand-blue/20 border border-brand-blue/30 flex items-center justify-center text-[11px] font-bold font-mono text-brand-blue">
              {initials}
            </span>
            <span className="hidden md:flex flex-col items-start leading-tight pr-1">
              <span className="text-[11px] font-semibold text-white max-w-[100px] truncate">
                {session?.name || t('common.guest')}
              </span>
              <span className="text-[9px] font-mono uppercase tracking-wider text-apple-secondary">
                {session ? roleLabelText(session.role) : t('common.session')}
              </span>
            </span>
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-[calc(100%+8px)] w-56 rounded-2xl glass-panel-strong border border-white/15 shadow-2xl p-2 z-50 animate-fade-up">
              <div className="px-3 py-2 border-b border-white/10 mb-1">
                <div className="text-xs font-semibold text-white truncate">{session?.name}</div>
                <div className="text-[10px] text-apple-secondary font-mono">
                  {session ? roleLabelText(session.role) : '—'}
                </div>
              </div>
              <button
                type="button"
                className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs font-semibold text-apple-secondary hover:text-white hover:bg-white/5 transition-colors min-h-[44px]"
                onClick={() => {
                  setMenuOpen(false);
                  navigate('/welcome');
                }}
              >
                <LayoutDashboard size={14} />
                {t('common.change_role')}
              </button>
              <button
                type="button"
                className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs font-semibold text-brand-red/90 hover:bg-brand-red/10 transition-colors min-h-[44px]"
                onClick={() => {
                  setMenuOpen(false);
                  clearSession();
                  navigate('/welcome', { replace: true });
                }}
              >
                <LogOut size={14} />
                {t('common.sign_out')}
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
