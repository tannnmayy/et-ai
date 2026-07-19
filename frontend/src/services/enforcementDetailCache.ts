/**
 * Short-lived session cache so Enforcement detail full-page opens instantly
 * without an extra API round-trip when expanding from the side panel.
 */
import type { PriorityHex } from '../types';

const KEY = 'aqi_enforcement_detail_hex';

export function cacheEnforcementDetailHex(hex: PriorityHex): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(hex));
  } catch {
    /* private mode / quota */
  }
}

export function readCachedEnforcementDetailHex(id: string): PriorityHex | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PriorityHex;
    if (parsed && String(parsed.id) === String(id)) return parsed;
  } catch {
    /* ignore */
  }
  return null;
}
