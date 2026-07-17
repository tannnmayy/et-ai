import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  Satellite,
  Crosshair,
  LineChart,
  Shield,
  Home,
  Radio,
  Flame,
  Map as MapIcon,
  CloudSun,
  Building,
  Gavel,
  Users,
  ChevronDown,
  ChevronUp,
  Check,
  ArrowRight,
  Sparkles,
  Lock,
} from 'lucide-react';
import {
  useSession,
  type AppLanguage,
  type UserRole,
  defaultPathForRole,
} from '../context/SessionContext';
import { ensureMapWarm, warmAppFromLanding } from '../services/prefetchService';
import { useT } from '../i18n/useT';
import type { TranslateParams } from '../i18n/translate';

type RoleOption = {
  id: UserRole;
  title: string;
  description: string;
  badge?: string;
  highlight?: boolean;
  icon: React.ElementType;
};

type TFn = (key: string, params?: TranslateParams) => string;

function buildFeatures(t: TFn) {
  return [
    {
      title: t('landing.feature.attribution.title'),
      body: t('landing.feature.attribution.body'),
      icon: Crosshair,
      accent: 'text-brand-blue',
      ring: 'border-brand-blue/25 bg-brand-blue/10',
    },
    {
      title: t('landing.feature.forecast.title'),
      body: t('landing.feature.forecast.body'),
      icon: LineChart,
      accent: 'text-brand-green',
      ring: 'border-brand-green/25 bg-brand-green/10',
    },
    {
      title: t('landing.feature.enforcement.title'),
      body: t('landing.feature.enforcement.body'),
      icon: Shield,
      accent: 'text-brand-orange',
      ring: 'border-brand-orange/25 bg-brand-orange/10',
    },
    {
      title: t('landing.feature.citizen.title'),
      body: t('landing.feature.citizen.body'),
      icon: Home,
      accent: 'text-violet-400',
      ring: 'border-violet-400/25 bg-violet-400/10',
    },
  ] as const;
}

function buildDataSources(t: TFn) {
  return [
    { title: t('landing.data.cpcb.title'), body: t('landing.data.cpcb.body'), icon: Radio },
    { title: t('landing.data.satellite.title'), body: t('landing.data.satellite.body'), icon: Flame },
    { title: t('landing.data.osm.title'), body: t('landing.data.osm.body'), icon: MapIcon },
    { title: t('landing.data.weather.title'), body: t('landing.data.weather.body'), icon: CloudSun },
    { title: t('landing.data.rent.title'), body: t('landing.data.rent.body'), icon: Building },
  ] as const;
}

function buildRoles(t: TFn): RoleOption[] {
  return [
    {
      id: 'enforcement',
      title: t('landing.role.enforcement.title'),
      description: t('landing.role.enforcement.desc'),
      icon: Shield,
    },
    {
      id: 'citizen',
      title: t('landing.role.citizen.title'),
      description: t('landing.role.citizen.desc'),
      icon: Users,
    },
    {
      id: 'guest',
      title: t('landing.role.guest.title'),
      description: t('landing.role.guest.desc'),
      badge: t('landing.role.guest.badge'),
      highlight: true,
      icon: Gavel,
    },
  ];
}

const TERMS_TEXT = `AQI SENTINEL — TERMS OF USE (DEMONSTRATION ACCESS)

1. Purpose
AQI Sentinel is a research and operational decision-support prototype for Bengaluru urban air quality. It is intended for civic demonstration, training, and informed prioritisation — not as a substitute for statutory monitoring or court evidence.

2. Data sources & estimates
Outputs combine CPCB/KSPCB station readings, satellite products (e.g. Sentinel-5P, FIRMS), weather, OpenStreetMap/H3 geospatial layers, and open housing signals. Coverage is incomplete, may lag live conditions, and may include model-based interpolation. Forecasts and fused PM2.5 values are estimates with uncertainty.

3. Attribution & enforcement rankings
Source mixes (traffic, industrial, construction, burning) and enforcement priority scores are investigation signals. They do not identify a liable person or entity and must not be treated as legal findings, violation determinations, or grounds for prosecution without independent field verification by authorised officers.

4. Citizen recommendations
Neighbourhood matching uses AQI, rent estimates, commute proxies, and amenities. Some inputs are incomplete or modelled. Recommendations are guidance for personal planning only — not medical, financial, or legal advice.

5. Privacy
Name, phone, and optional email you enter are stored in this browser session (and optionally a local SQLite demo store if configured). They are not sold to third parties. Clear browser data or sign out to remove session details.

6. Responsible use
You will not present AQI Sentinel outputs as official CPCB/KSPCB notifications, medical advice, or final enforcement orders. Always verify with authorised agencies and current Gazette / board notifications.

By continuing you accept these terms.`;

function LanguagePill({
  language,
  setLanguage,
}: {
  language: AppLanguage;
  setLanguage: (l: AppLanguage) => void;
}) {
  const items: { id: AppLanguage; label: string }[] = [
    { id: 'en', label: 'English' },
    { id: 'kn', label: 'ಕನ್ನಡ' },
    { id: 'hi', label: 'हिंदी' },
  ];
  return (
    <div className="inline-flex items-center gap-0.5 p-1 rounded-full glass-panel">
      {items.map((item) => {
        const active = language === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => setLanguage(item.id)}
            className={`min-h-[36px] min-w-[72px] px-3 rounded-full text-[11px] font-semibold tracking-wide transition-all duration-200 ${
              active
                ? 'bg-brand-blue text-white shadow-lg shadow-brand-blue/25'
                : 'text-apple-secondary hover:text-white'
            }`}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

export default function LandingPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { enterApp, language, setLanguage, session, isAuthenticated } = useSession();
  const { t } = useT();
  const FEATURES = useMemo(() => buildFeatures(t), [t]);
  const DATA_SOURCES = useMemo(() => buildDataSources(t), [t]);
  const ROLES = useMemo(() => buildRoles(t), [t]);

  // Warm Map data + Google Maps JS as soon as Landing mounts (prioritized phases).
  useEffect(() => {
    warmAppFromLanding(queryClient);
  }, [queryClient]);

  const [selectedRole, setSelectedRole] = useState<UserRole | null>(
    session?.role ?? 'guest',
  );
  const [name, setName] = useState(session?.name ?? '');
  const [phone, setPhone] = useState(session?.phone ?? '');
  const [email, setEmail] = useState(session?.email ?? '');
  const [accepted, setAccepted] = useState(Boolean(session?.acceptedTerms));
  const [showTerms, setShowTerms] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = useMemo(() => {
    return Boolean(selectedRole && name.trim().length >= 2 && phone.trim().length >= 8 && accepted);
  }, [selectedRole, name, phone, accepted]);

  const handleContinue = () => {
    setError(null);
    if (!selectedRole) {
      setError(t('landing.error.role'));
      return;
    }
    if (name.trim().length < 2) {
      setError(t('landing.error.name'));
      return;
    }
    if (phone.trim().length < 8) {
      setError(t('landing.error.phone'));
      return;
    }
    if (!accepted) {
      setError(t('landing.error.terms'));
      return;
    }

    setSubmitting(true);
    enterApp({
      name: name.trim(),
      phone: phone.trim(),
      email: email.trim() || undefined,
      role: selectedRole,
      language,
      acceptedTerms: true,
    });

    // Kick / continue Map warm (in-flight prefetch or RQ cache) before navigate
    ensureMapWarm(queryClient);

    // Short deliberate pause so the transition feels intentional
    window.setTimeout(() => {
      navigate(defaultPathForRole(selectedRole), { replace: true });
      setSubmitting(false);
    }, 280);
  };

  const resume = () => {
    if (session) {
      ensureMapWarm(queryClient);
      navigate(defaultPathForRole(session.role), { replace: true });
    }
  };

  return (
    <div className="min-h-screen w-full bg-black text-white font-sans overflow-x-hidden relative">
      {/* Atmospheric Bengaluru map layer — soft, blurred, Apple-like depth */}
      <div
        className="pointer-events-none fixed inset-0 z-0"
        aria-hidden
        style={{
          backgroundImage: `url(${new URL('../assets/bengaluru-map-bg.png', import.meta.url).href})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center 30%',
          filter: 'blur(18px) saturate(0.55) brightness(0.35)',
          transform: 'scale(1.08)',
          opacity: 0.45,
        }}
      />
      <div
        className="pointer-events-none fixed inset-0 z-0 bg-gradient-to-b from-black/80 via-black/75 to-black"
        aria-hidden
      />
      {/* Sticky header — solid black, no ambient color wash */}
      <header className="sticky top-0 z-50 border-b border-white/10 bg-black/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-2xl bg-white/[0.06] border border-white/15 flex items-center justify-center text-white shrink-0">
              <Satellite size={18} />
            </div>
            <div className="min-w-0">
              <div className="text-base sm:text-lg font-bold tracking-tight truncate">{t('app.name')}</div>
              <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-apple-secondary hidden sm:block">
                {t('app.tagline')}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <LanguagePill language={language} setLanguage={setLanguage} />
            {isAuthenticated && (
              <button
                type="button"
                onClick={resume}
                className="hidden sm:inline-flex min-h-[44px] items-center gap-2 px-4 rounded-full bg-white/10 border border-white/15 text-xs font-semibold hover:bg-white/15 transition-colors"
              >
                {t('common.resume_session')}
                <ArrowRight size={14} />
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="relative z-10 max-w-6xl mx-auto px-5 sm:px-8 pb-24">
        {/* Hero */}
        <section className="pt-14 sm:pt-20 pb-16 sm:pb-20 text-center animate-fade-up">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full glass-panel text-[10px] font-mono uppercase tracking-[0.2em] text-apple-secondary mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse" />
            {t('landing.badge')}
          </div>
          <h1 className="text-5xl sm:text-6xl md:text-7xl font-bold tracking-tight text-white mb-5">
            {t('app.name')}
          </h1>
          <p className="text-lg sm:text-xl md:text-2xl font-medium text-white/90 max-w-3xl mx-auto leading-snug mb-5">
            {t('landing.hero_subtitle')}
          </p>
          <p className="text-sm sm:text-base text-apple-secondary max-w-2xl mx-auto leading-relaxed">
            {t('landing.hero_bullets')}
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <a
              href="#enter"
              className="min-h-[48px] inline-flex items-center gap-2 px-6 rounded-full bg-brand-blue hover:bg-brand-blue/90 text-white text-sm font-bold shadow-xl shadow-brand-blue/25 transition-all"
            >
              <Sparkles size={16} />
              {t('landing.enter')}
            </a>
            <a
              href="#features"
              className="min-h-[48px] inline-flex items-center gap-2 px-6 rounded-full glass-panel text-sm font-semibold text-white/90 hover:bg-white/10 transition-all"
            >
              {t('landing.explore')}
            </a>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="mb-20">
          <div className="flex items-end justify-between gap-4 mb-8 animate-fade-up">
            <div>
              <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">{t('landing.what_we_do')}</h2>
              <p className="text-sm text-apple-secondary mt-2 max-w-xl">
                {t('landing.what_we_do_sub')}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-5">
            {FEATURES.map((f, i) => {
              const Icon = f.icon;
              return (
                <article
                  key={f.title}
                  className={`glass-panel glass-card-hover rounded-3xl p-6 md:p-7 text-left animate-fade-up animate-fade-up-delay-${Math.min(i + 1, 4)}`}
                >
                  <div className={`w-12 h-12 rounded-2xl border flex items-center justify-center mb-5 ${f.ring} ${f.accent}`}>
                    <Icon size={22} />
                  </div>
                  <h3 className="text-lg font-bold text-white mb-2 tracking-tight">{f.title}</h3>
                  <p className="text-sm text-apple-secondary leading-relaxed">{f.body}</p>
                </article>
              );
            })}
          </div>
        </section>

        {/* Data transparency */}
        <section className="mb-20">
          <div className="mb-8 animate-fade-up">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">{t('landing.data_we_use')}</h2>
            <p className="text-sm text-apple-secondary mt-2 max-w-2xl">
              {t('landing.data_we_use_sub')}
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 md:gap-4">
            {DATA_SOURCES.map((d) => {
              const Icon = d.icon;
              return (
                <article
                  key={d.title}
                  className="glass-panel glass-card-hover rounded-3xl p-5 flex flex-col gap-3 min-h-[160px]"
                >
                  <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-brand-blue">
                    <Icon size={18} />
                  </div>
                  <h3 className="text-sm font-bold text-white leading-snug">{d.title}</h3>
                  <p className="text-xs text-apple-secondary leading-relaxed flex-1">{d.body}</p>
                </article>
              );
            })}
          </div>
        </section>

        {/* Role + auth */}
        <section id="enter" className="scroll-mt-24">
          <div className="glass-panel-strong rounded-[28px] p-6 sm:p-10 md:p-12 relative overflow-hidden">
            <div className="relative">
              <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
                <div>
                  <div className="inline-flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em] text-brand-blue mb-3">
                    <Lock size={12} />
                    {t('landing.secure_entry')}
                  </div>
                  <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">{t('landing.choose_role')}</h2>
                  <p className="text-sm text-apple-secondary mt-2 max-w-lg">
                    {t('landing.choose_role_sub')}
                  </p>
                </div>
                <LanguagePill language={language} setLanguage={setLanguage} />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
                {ROLES.map((role) => {
                  const Icon = role.icon;
                  const active = selectedRole === role.id;
                  return (
                    <button
                      key={role.id}
                      type="button"
                      onClick={() => setSelectedRole(role.id)}
                      className={`text-left rounded-3xl p-5 min-h-[168px] transition-all duration-300 border relative overflow-hidden group ${
                        role.highlight
                          ? active
                            ? 'bg-brand-blue/20 border-brand-blue shadow-[0_0_40px_rgba(10,132,255,0.25)] scale-[1.02]'
                            : 'bg-brand-blue/10 border-brand-blue/40 hover:border-brand-blue hover:shadow-[0_0_32px_rgba(10,132,255,0.2)]'
                          : active
                            ? 'bg-white/10 border-white/30 shadow-xl'
                            : 'bg-white/5 border-white/10 hover:border-white/25 hover:bg-white/[0.07]'
                      }`}
                    >
                      {role.badge && (
                        <span className="absolute top-3 right-3 text-[9px] font-bold uppercase tracking-wider px-2 py-1 rounded-full bg-brand-blue text-white shadow-lg">
                          {role.badge}
                        </span>
                      )}
                      <div
                        className={`w-11 h-11 rounded-2xl border flex items-center justify-center mb-4 ${
                          role.highlight
                            ? 'bg-brand-blue/20 border-brand-blue/40 text-brand-blue'
                            : 'bg-white/5 border-white/10 text-white'
                        }`}
                      >
                        <Icon size={20} />
                      </div>
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-base font-bold text-white pr-6">{role.title}</h3>
                        <span
                          className={`mt-0.5 w-5 h-5 rounded-full border flex items-center justify-center shrink-0 ${
                            active
                              ? 'bg-brand-blue border-brand-blue text-white'
                              : 'border-white/25 text-transparent'
                          }`}
                        >
                          <Check size={12} strokeWidth={3} />
                        </span>
                      </div>
                      <p className="text-xs text-apple-secondary leading-relaxed mt-2">
                        {role.description}
                      </p>
                    </button>
                  );
                })}
              </div>

              {/* Form */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
                <label className="flex flex-col gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-apple-secondary">
                    {t('landing.name')} *
                  </span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={t('landing.name')}
                    className="min-h-[48px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white placeholder:text-apple-secondary/50 focus:outline-none focus:border-brand-blue/60 focus:ring-2 focus:ring-brand-blue/20 transition-all"
                    autoComplete="name"
                  />
                </label>
                <label className="flex flex-col gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-apple-secondary">
                    {t('landing.phone')} *
                  </span>
                  <input
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+91 …"
                    className="min-h-[48px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white placeholder:text-apple-secondary/50 focus:outline-none focus:border-brand-blue/60 focus:ring-2 focus:ring-brand-blue/20 transition-all font-mono"
                    autoComplete="tel"
                    inputMode="tel"
                  />
                </label>
                <label className="flex flex-col gap-2 md:col-span-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-apple-secondary">
                    {t('landing.email')}
                  </span>
                  <input
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@organisation.gov.in"
                    className="min-h-[48px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white placeholder:text-apple-secondary/50 focus:outline-none focus:border-brand-blue/60 focus:ring-2 focus:ring-brand-blue/20 transition-all"
                    autoComplete="email"
                    type="email"
                  />
                </label>
              </div>

              {/* Terms */}
              <div className="rounded-2xl border border-white/10 bg-black/30 overflow-hidden mb-6">
                <label className="flex items-start gap-3 p-4 cursor-pointer min-h-[52px]">
                  <input
                    type="checkbox"
                    checked={accepted}
                    onChange={(e) => setAccepted(e.target.checked)}
                    className="mt-1 w-5 h-5 rounded border-white/20 bg-black/40 text-brand-blue focus:ring-brand-blue/40"
                  />
                  <span className="text-sm text-white/90 leading-relaxed pt-0.5">
                    {t('landing.accept_terms')}
                  </span>
                </label>
                <button
                  type="button"
                  onClick={() => setShowTerms((v) => !v)}
                  className="w-full flex items-center justify-between px-4 py-3 border-t border-white/10 text-xs font-semibold text-apple-secondary hover:text-white transition-colors min-h-[44px]"
                >
                  <span>{showTerms ? t('landing.hide_terms') : t('landing.show_terms')}</span>
                  {showTerms ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                {showTerms && (
                  <div className="px-4 pb-4 text-xs text-apple-secondary leading-relaxed whitespace-pre-line border-t border-white/5 pt-3 font-sans">
                    {TERMS_TEXT}
                  </div>
                )}
              </div>

              {error && (
                <div className="mb-4 text-sm text-brand-red bg-brand-red/10 border border-brand-red/20 rounded-2xl px-4 py-3">
                  {error}
                </div>
              )}

              <button
                type="button"
                disabled={!canSubmit || submitting}
                onClick={handleContinue}
                className="w-full min-h-[52px] rounded-2xl bg-brand-blue hover:bg-brand-blue/90 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold text-sm shadow-xl shadow-brand-blue/20 flex items-center justify-center gap-2 transition-all"
              >
                {submitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    {t('landing.entering')}
                  </>
                ) : (
                  <>
                    {t('landing.continue')}
                    <ArrowRight size={16} />
                  </>
                )}
              </button>

              <p className="mt-4 text-center text-[11px] text-apple-secondary/80">
                Session is stored only in this browser. You can switch roles anytime from the app header.
              </p>
            </div>
          </div>
        </section>

        <footer className="mt-16 pt-8 border-t border-white/10 flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px] text-apple-secondary font-mono">
          <span>AQI SENTINEL · BENGALURU</span>
          <span className="text-center">Sensors · Satellite · Geospatial · Weather · Housing</span>
          <span className="text-brand-green flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse" />
            DEMO READY
          </span>
        </footer>
      </main>
    </div>
  );
}
