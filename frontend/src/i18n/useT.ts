import { useCallback } from 'react';
import { useSession } from '../context/SessionContext';
import { translate, type TranslateParams } from './translate';
import type { ApiLanguage } from './lang';

/**
 * Reactive translator bound to SessionContext.language.
 * UI re-renders when language changes.
 */
export function useT(): {
  t: (key: string, params?: TranslateParams) => string;
  language: ApiLanguage;
} {
  const { language } = useSession();
  const t = useCallback(
    (key: string, params?: TranslateParams) => translate(key, language, params),
    [language],
  );
  return { t, language };
}
