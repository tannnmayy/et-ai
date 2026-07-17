import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  DEFAULT_LANGUAGE,
  normalizeLanguage,
  type ApiLanguage,
} from '../i18n/lang';

/** Canonical session language codes (API-aligned lowercase). */
export type AppLanguage = ApiLanguage;

export type UserRole = 'enforcement' | 'citizen' | 'guest';

export interface UserSession {
  name: string;
  phone: string;
  email?: string;
  role: UserRole;
  /** Always en | hi | kn */
  language: AppLanguage;
  acceptedTerms: boolean;
  enteredAt: string;
}

interface SessionContextValue {
  session: UserSession | null;
  /** Current language (en | hi | kn), default en */
  language: AppLanguage;
  /** Same as language — explicit name for API clients */
  apiLanguage: AppLanguage;
  setLanguage: (lang: AppLanguage | string) => void;
  isAuthenticated: boolean;
  enterApp: (payload: Omit<UserSession, 'enteredAt'>) => void;
  clearSession: () => void;
  defaultPathForRole: (role: UserRole) => string;
  roleLabel: (role: UserRole) => string;
}

const STORAGE_KEY = 'aqi_sentinel_session_v1';

const SessionContext = createContext<SessionContextValue | null>(null);

export function defaultPathForRole(role: UserRole): string {
  if (role === 'citizen') return '/citizen';
  if (role === 'enforcement') return '/enforcement';
  return '/'; // guest / judge → Map
}

export function roleLabel(role: UserRole): string {
  if (role === 'enforcement') return 'Enforcement Authority';
  if (role === 'citizen') return 'Citizen';
  return 'Guest / Judge';
}

function loadSession(): UserSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as UserSession & { language?: string };
    if (!parsed?.name || !parsed?.role || !parsed?.acceptedTerms) return null;
    // Migrate legacy EN/HI/KN → en/hi/kn
    return {
      ...parsed,
      language: normalizeLanguage(parsed.language),
    };
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<UserSession | null>(() => loadSession());
  const [language, setLanguageState] = useState<AppLanguage>(
    () => normalizeLanguage(loadSession()?.language ?? DEFAULT_LANGUAGE),
  );

  useEffect(() => {
    if (session) {
      const normalized = { ...session, language: normalizeLanguage(session.language) };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    }
  }, [session]);

  const setLanguage = useCallback((lang: AppLanguage | string) => {
    const next = normalizeLanguage(lang);
    setLanguageState(next);
    setSession((prev) => (prev ? { ...prev, language: next } : prev));
  }, []);

  const enterApp = useCallback((payload: Omit<UserSession, 'enteredAt'>) => {
    const next: UserSession = {
      ...payload,
      language: normalizeLanguage(payload.language),
      enteredAt: new Date().toISOString(),
    };
    setSession(next);
    setLanguageState(next.language);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    // Best-effort SQLite mirror — never blocks login
    void import('../services/persistenceService').then(({ mirrorSession, logAuditEvent }) => {
      void mirrorSession(next);
      void logAuditEvent('session_enter', { role: next.role, language: next.language }, next.name);
    });
  }, []);

  const clearSession = useCallback(() => {
    setSession(null);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      language,
      apiLanguage: language,
      setLanguage,
      isAuthenticated: Boolean(session?.acceptedTerms),
      enterApp,
      clearSession,
      defaultPathForRole,
      roleLabel,
    }),
    [session, language, setLanguage, enterApp, clearSession],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error('useSession must be used within SessionProvider');
  }
  return ctx;
}
