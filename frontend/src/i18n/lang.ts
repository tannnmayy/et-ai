/**
 * Canonical API language codes for AQI Sentinel.
 * Backend SUPPORTED_LANGUAGES = ["en", "hi", "kn"].
 */

export type ApiLanguage = 'en' | 'hi' | 'kn';

export const API_LANGUAGES: readonly ApiLanguage[] = ['en', 'hi', 'kn'] as const;

export const DEFAULT_LANGUAGE: ApiLanguage = 'en';

/** Display labels for language switchers */
export const LANGUAGE_LABELS: Record<ApiLanguage, string> = {
  en: 'English',
  hi: 'हिंदी',
  kn: 'ಕನ್ನಡ',
};

/** Short pill labels */
export const LANGUAGE_SHORT: Record<ApiLanguage, string> = {
  en: 'EN',
  hi: 'हिंदी',
  kn: 'ಕನ್ನಡ',
};

/**
 * Normalize any session / legacy / API value to a supported API code.
 * Accepts: en, EN, hi, HI, kn, KN, hindi, kannada, english, etc.
 */
export function normalizeLanguage(raw: unknown): ApiLanguage {
  if (raw == null) return DEFAULT_LANGUAGE;
  const s = String(raw).trim().toLowerCase();
  if (s === 'en' || s === 'english' || s === 'eng') return 'en';
  if (s === 'hi' || s === 'hindi' || s === 'hin') return 'hi';
  if (s === 'kn' || s === 'kannada' || s === 'kan') return 'kn';
  // Legacy uppercase already lowercased above (EN→en)
  if ((API_LANGUAGES as readonly string[]).includes(s)) {
    return s as ApiLanguage;
  }
  return DEFAULT_LANGUAGE;
}

/** Alias used by API clients */
export function toApiLang(raw: unknown): ApiLanguage {
  return normalizeLanguage(raw);
}

export function isApiLanguage(raw: unknown): raw is ApiLanguage {
  return (API_LANGUAGES as readonly string[]).includes(String(raw).trim().toLowerCase());
}
