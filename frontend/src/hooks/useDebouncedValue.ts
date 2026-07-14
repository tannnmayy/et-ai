import { useEffect, useState } from 'react';

/**
 * Returns `value` after it has been stable for `delayMs` milliseconds.
 * Useful for search boxes and other high-frequency UI inputs.
 */
export function useDebouncedValue<T>(value: T, delayMs: number = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}
