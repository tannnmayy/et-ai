/**
 * Lightweight key-based i18n (no i18next dependency).
 * Keys are flat strings like "copilot.send". Missing keys fall back to English, then the key itself.
 */
import type { ApiLanguage } from './lang';
import { DEFAULT_LANGUAGE, normalizeLanguage } from './lang';
import en from './locales/en.json';
import hi from './locales/hi.json';
import kn from './locales/kn.json';

export type TranslateParams = Record<string, string | number>;

type Catalog = Record<string, string>;

const CATALOGS: Record<ApiLanguage, Catalog> = {
  en: en as Catalog,
  hi: hi as Catalog,
  kn: kn as Catalog,
};

function interpolate(template: string, params?: TranslateParams): string {
  if (!params) return template;
  let out = template;
  for (const [k, v] of Object.entries(params)) {
    out = out.replace(new RegExp(`\\{\\{${k}\\}\\}`, 'g'), String(v));
  }
  return out;
}

/** Translate a key for an explicit language (usable outside React). */
export function translate(
  key: string,
  language: ApiLanguage | string = DEFAULT_LANGUAGE,
  params?: TranslateParams,
): string {
  const lang = normalizeLanguage(language);
  const primary = CATALOGS[lang]?.[key];
  const fallback = CATALOGS.en?.[key];
  const raw = primary ?? fallback ?? key;
  return interpolate(raw, params);
}

/** Alias */
export const t = translate;

export function getCatalog(language: ApiLanguage | string): Catalog {
  return CATALOGS[normalizeLanguage(language)] || CATALOGS.en;
}
