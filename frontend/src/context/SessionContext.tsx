import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

export type AppLanguage = 'EN' | 'HI' | 'KN';
export type UserRole = 'enforcement' | 'citizen' | 'guest';

export interface UserSession {
  name: string;
  phone: string;
  email?: string;
  role: UserRole;
  language: AppLanguage;
  acceptedTerms: boolean;
  enteredAt: string;
}

interface SessionContextValue {
  session: UserSession | null;
  language: AppLanguage;
  setLanguage: (lang: AppLanguage) => void;
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
    const parsed = JSON.parse(raw) as UserSession;
    if (!parsed?.name || !parsed?.role || !parsed?.acceptedTerms) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<UserSession | null>(() => loadSession());
  const [language, setLanguageState] = useState<AppLanguage>(
    () => loadSession()?.language ?? 'EN',
  );

  useEffect(() => {
    if (session) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    }
  }, [session]);

  const setLanguage = useCallback((lang: AppLanguage) => {
    setLanguageState(lang);
    setSession((prev) => (prev ? { ...prev, language: lang } : prev));
  }, []);

  const enterApp = useCallback((payload: Omit<UserSession, 'enteredAt'>) => {
    const next: UserSession = {
      ...payload,
      enteredAt: new Date().toISOString(),
    };
    setSession(next);
    setLanguageState(next.language);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }, []);

  const clearSession = useCallback(() => {
    setSession(null);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      language,
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
