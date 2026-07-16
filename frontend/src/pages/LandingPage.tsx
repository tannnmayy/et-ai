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
import { warmAppFromLanding } from '../services/prefetchService';

type RoleOption = {
  id: UserRole;
  title: string;
  description: string;
  badge?: string;
  highlight?: boolean;
  icon: React.ElementType;
};

const FEATURES = [
  {
    title: 'Source Attribution',
    body: 'Pinpoint whether pollution comes from construction, traffic, industry, or burning using satellite, sensor, and geospatial data.',
    icon: Crosshair,
    accent: 'text-brand-blue',
    ring: 'border-brand-blue/25 bg-brand-blue/10',
  },
  {
    title: 'Hyperlocal Forecasting',
    body: '24-hour AQI predictions at street level so authorities can act before pollution spikes.',
    icon: LineChart,
    accent: 'text-brand-green',
    ring: 'border-brand-green/25 bg-brand-green/10',
  },
  {
    title: 'Enforcement Intelligence',
    body: 'Prioritized, evidence-backed recommendations with clear actions for pollution control boards and municipal teams.',
    icon: Shield,
    accent: 'text-brand-orange',
    ring: 'border-brand-orange/25 bg-brand-orange/10',
  },
  {
    title: 'Citizen Guidance',
    body: 'Personalized neighborhood recommendations based on AQI, rent, commute, schools, hospitals, and parks.',
    icon: Home,
    accent: 'text-violet-400',
    ring: 'border-violet-400/25 bg-violet-400/10',
  },
] as const;

const DATA_SOURCES = [
  {
    title: 'CPCB & KSPCB Sensors',
    body: 'Ground-truth air quality readings',
    icon: Radio,
  },
  {
    title: 'Sentinel-5P & FIRMS Satellite',
    body: 'NO₂ levels and active fire/burning detection',
    icon: Flame,
  },
  {
    title: 'OpenStreetMap + H3 Grid',
    body: 'Road density, land use, construction sites, and vulnerability hotspots',
    icon: MapIcon,
  },
  {
    title: 'Open-Meteo Weather',
    body: 'Wind patterns that move pollution across the city',
    icon: CloudSun,
  },
  {
    title: 'MagicBricks Rental Data',
    body: 'Real housing costs for citizen recommendations',
    icon: Building,
  },
] as const;

const ROLES: RoleOption[] = [
  {
    id: 'enforcement',
    title: 'Enforcement Authority',
    description: 'For pollution control boards, municipal corporations, and police',
    icon: Shield,
  },
  {
    id: 'citizen',
    title: 'Citizen',
    description: 'Find better places to live based on air quality and livability',
    icon: Users,
  },
  {
    id: 'guest',
    title: 'Guest / Judge Mode',
    description: 'Quick demo access for judges and evaluators',
    badge: 'Recommended for hackathon',
    highlight: true,
    icon: Gavel,
  },
];

const TERMS_TEXT = `AQI Sentinel is an urban air-quality intelligence prototype for research, civic demonstration, and operational decision support in Bengaluru.

By continuing you acknowledge that:
• Air-quality estimates and forecasts are derived from public sensors, satellite products, weather, and geospatial layers. Coverage is incomplete and may lag real-world conditions.
• Source attribution and enforcement rankings are investigation aids — not legal findings of liability against any site, vehicle, or individual.
• Citizen neighbourhood scores use available AQI, rent estimates, commute, and amenity data; some fields may be modelled or incomplete and are labelled accordingly.
• Contact details you enter (name, phone, optional email) stay in your browser for this session only and are not sold to third parties.
• You will use the platform responsibly and will not treat outputs as medical advice or substitute for official CPCB / KSPCB notifications.`;

function LanguagePill({
  language,
  setLanguage,
}: {
  language: AppLanguage;
  setLanguage: (l: AppLanguage) => void;
}) {
  const items: { id: AppLanguage; label: string }[] = [
    { id: 'EN', label: 'English' },
    { id: 'KN', label: 'ಕನ್ನಡ' },
    { id: 'HI', label: 'हिंदी' },
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

  // Warm Map + Enforcement API caches and start Google Maps JS while user reads landing.
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
      setError('Please select how you want to enter.');
      return;
    }
    if (name.trim().length < 2) {
      setError('Please enter your full name.');
      return;
    }
    if (phone.trim().length < 8) {
      setError('Please enter a valid phone number.');
      return;
    }
    if (!accepted) {
      setError('Please accept the terms to continue.');
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

    // Ensure caches are warm before / while entering the app
    void warmAppFromLanding(queryClient);

    // Short deliberate pause so the transition feels intentional
    window.setTimeout(() => {
      navigate(defaultPathForRole(selectedRole), { replace: true });
      setSubmitting(false);
    }, 280);
  };

  const resume = () => {
    if (session) {
      navigate(defaultPathForRole(session.role), { replace: true });
    }
  };

  return (
    <div className="min-h-screen w-full bg-black text-white font-sans overflow-x-hidden">
      {/* Sticky header — solid black, no ambient color wash */}
      <header className="sticky top-0 z-50 border-b border-white/10 bg-black/90 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-2xl bg-white/[0.06] border border-white/15 flex items-center justify-center text-white shrink-0">
              <Satellite size={18} />
            </div>
            <div className="min-w-0">
              <div className="text-base sm:text-lg font-bold tracking-tight truncate">AQI Sentinel</div>
              <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-apple-secondary hidden sm:block">
                Urban air intelligence
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
                Resume session
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
            Bengaluru · Live intelligence prototype
          </div>
          <h1 className="text-5xl sm:text-6xl md:text-7xl font-bold tracking-tight text-white mb-5">
            AQI Sentinel
          </h1>
          <p className="text-lg sm:text-xl md:text-2xl font-medium text-white/90 max-w-3xl mx-auto leading-snug mb-5">
            AI-Powered Urban Air Quality Intelligence for Smarter Cities
          </p>
          <p className="text-sm sm:text-base text-apple-secondary max-w-2xl mx-auto leading-relaxed">
            Real-time source attribution • Hyperlocal forecasting • Evidence-based enforcement •
            Personalized citizen guidance
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <a
              href="#enter"
              className="min-h-[48px] inline-flex items-center gap-2 px-6 rounded-full bg-brand-blue hover:bg-brand-blue/90 text-white text-sm font-bold shadow-xl shadow-brand-blue/25 transition-all"
            >
              <Sparkles size={16} />
              Enter the platform
            </a>
            <a
              href="#features"
              className="min-h-[48px] inline-flex items-center gap-2 px-6 rounded-full glass-panel text-sm font-semibold text-white/90 hover:bg-white/10 transition-all"
            >
              Explore capabilities
            </a>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="mb-20">
          <div className="flex items-end justify-between gap-4 mb-8 animate-fade-up">
            <div>
              <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">What We Do</h2>
              <p className="text-sm text-apple-secondary mt-2 max-w-xl">
                Four pillars that connect satellite evidence, city sensors, and operational action.
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
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">Data We Use</h2>
            <p className="text-sm text-apple-secondary mt-2 max-w-2xl">
              Transparency first — every recommendation is grounded in public sensors, satellites,
              geospatial layers, weather, and open housing signals.
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
                    Secure lightweight entry
                  </div>
                  <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">Choose your role</h2>
                  <p className="text-sm text-apple-secondary mt-2 max-w-lg">
                    Tell us who you are so we open the right workspace. Judges: use Guest mode for
                    the fastest full-product tour.
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
                    Full name *
                  </span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Your name"
                    className="min-h-[48px] rounded-2xl bg-black/40 border border-white/10 px-4 text-sm text-white placeholder:text-apple-secondary/50 focus:outline-none focus:border-brand-blue/60 focus:ring-2 focus:ring-brand-blue/20 transition-all"
                    autoComplete="name"
                  />
                </label>
                <label className="flex flex-col gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-apple-secondary">
                    Phone number *
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
                    Email <span className="normal-case tracking-normal font-normal">(optional)</span>
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
                    I accept the Terms of Use for AQI Sentinel demonstration access.
                  </span>
                </label>
                <button
                  type="button"
                  onClick={() => setShowTerms((v) => !v)}
                  className="w-full flex items-center justify-between px-4 py-3 border-t border-white/10 text-xs font-semibold text-apple-secondary hover:text-white transition-colors min-h-[44px]"
                >
                  <span>View short terms</span>
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
                    Entering AQI Sentinel…
                  </>
                ) : (
                  <>
                    Accept Terms & Continue
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
