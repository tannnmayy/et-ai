/**
 * Dual-write persistence: SQLite API + localStorage fallback.
 * Never throws — operational flows keep working offline.
 */
import { apiClient } from '../api/axiosClient';

export type DispatchStatus = 'open' | 'in_progress' | 'resolved';

export interface DispatchRecord {
  id: string;
  unitId: string;
  target: string;
  hexId: string;
  source: string;
  score: string;
  action: string;
  notes: string;
  officer: string;
  operator: string;
  status: DispatchStatus;
  issuedAt: string;
  signedOperator: boolean;
  signedLead: boolean;
  createdAt?: string;
  updatedAt?: string;
}

const HISTORY_KEY = 'aqi_sentinel_dispatch_history_v1';
const MAX_HISTORY = 50;

// ---------------------------------------------------------------------------
// localStorage helpers (always available)
// ---------------------------------------------------------------------------

export function loadLocalHistory(): DispatchRecord[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as DispatchRecord[];
    if (!Array.isArray(parsed)) return [];
    // Normalize legacy records missing in_progress
    return parsed.map((r) => ({
      ...r,
      status: (r.status === 'resolved' || r.status === 'in_progress' ? r.status : 'open') as DispatchStatus,
    }));
  } catch {
    return [];
  }
}

export function saveLocalHistory(items: DispatchRecord[]): void {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, MAX_HISTORY)));
  } catch {
    /* quota / private mode */
  }
}

export function upsertLocalDispatch(record: DispatchRecord): DispatchRecord[] {
  const prev = loadLocalHistory().filter((r) => r.id !== record.id);
  const next = [record, ...prev].slice(0, MAX_HISTORY);
  saveLocalHistory(next);
  return next;
}

// ---------------------------------------------------------------------------
// SQLite API (best-effort)
// ---------------------------------------------------------------------------

export async function fetchDispatchesFromApi(
  limit: number = 50,
): Promise<{ ok: boolean; dispatches: DispatchRecord[] }> {
  try {
    const { data } = await apiClient.get('/persistence/dispatches', {
      params: { limit },
      timeout: 4000,
    });
    const list = (data?.dispatches || []) as DispatchRecord[];
    return { ok: true, dispatches: list };
  } catch {
    return { ok: false, dispatches: [] };
  }
}

export async function saveDispatchToApi(
  record: DispatchRecord,
): Promise<{ ok: boolean; dispatch: DispatchRecord | null }> {
  try {
    const { data } = await apiClient.post('/persistence/dispatches', record, {
      timeout: 5000,
    });
    if (data?.ok && data.dispatch) {
      return { ok: true, dispatch: data.dispatch as DispatchRecord };
    }
    return { ok: false, dispatch: null };
  } catch {
    return { ok: false, dispatch: null };
  }
}

export async function updateDispatchStatusApi(
  id: string,
  status: DispatchStatus,
): Promise<boolean> {
  try {
    const { data } = await apiClient.patch(
      `/persistence/dispatches/${encodeURIComponent(id)}/status`,
      { status },
      { timeout: 4000 },
    );
    return Boolean(data?.ok);
  } catch {
    return false;
  }
}

/**
 * Load history: prefer SQLite, merge with localStorage so offline records
 * are not lost. Dedupes by id, sorts by issuedAt desc.
 */
export async function loadDispatchHistory(): Promise<{
  items: DispatchRecord[];
  source: 'sqlite' | 'local' | 'merged';
}> {
  const local = loadLocalHistory();
  const remote = await fetchDispatchesFromApi(50);

  if (!remote.ok || remote.dispatches.length === 0) {
    return { items: local, source: 'local' };
  }

  if (local.length === 0) {
    // Keep local mirror warm for offline
    saveLocalHistory(remote.dispatches);
    return { items: remote.dispatches, source: 'sqlite' };
  }

  const map = new Map<string, DispatchRecord>();
  for (const r of remote.dispatches) map.set(r.id, r);
  for (const r of local) {
    if (!map.has(r.id)) map.set(r.id, r);
  }
  const items = Array.from(map.values()).sort(
    (a, b) => new Date(b.issuedAt).getTime() - new Date(a.issuedAt).getTime(),
  );
  saveLocalHistory(items);
  return { items, source: 'merged' };
}

/**
 * Dual-write: always localStorage; attempt SQLite.
 */
export async function recordDispatch(record: DispatchRecord): Promise<{
  items: DispatchRecord[];
  persistedRemote: boolean;
}> {
  const items = upsertLocalDispatch(record);
  const remote = await saveDispatchToApi(record);
  if (remote.ok && remote.dispatch) {
    // Prefer server copy (may have createdAt/updatedAt)
    const merged = upsertLocalDispatch(remote.dispatch);
    return { items: merged, persistedRemote: true };
  }
  return { items, persistedRemote: false };
}

// ---------------------------------------------------------------------------
// Audit + session
// ---------------------------------------------------------------------------

export async function logAuditEvent(
  actionType: string,
  context: Record<string, unknown> = {},
  actor?: string,
): Promise<void> {
  try {
    await apiClient.post(
      '/persistence/audit',
      { actionType, context, actor: actor || null },
      { timeout: 3000 },
    );
  } catch {
    /* silent */
  }
}

export async function mirrorSession(session: {
  name: string;
  phone: string;
  email?: string;
  role: string;
  language: string;
  acceptedTerms: boolean;
  enteredAt: string;
}): Promise<void> {
  try {
    await apiClient.post(
      '/persistence/session',
      {
        sessionKey: 'local',
        name: session.name,
        phone: session.phone,
        email: session.email || null,
        role: session.role,
        language: session.language,
        acceptedTerms: session.acceptedTerms,
        enteredAt: session.enteredAt,
      },
      { timeout: 3000 },
    );
  } catch {
    /* silent */
  }
}
