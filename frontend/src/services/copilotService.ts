import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';
import type { CopilotResponseMode } from '../types';

export type CopilotSuggestion = {
  id: string;
  category: string;
  question: string;
};

export type ConversationTurn = {
  role: 'user' | 'assistant';
  content: string;
};

/** Default suggestions used if the API is offline — keep in sync with backend list. */
export const FALLBACK_SUGGESTIONS: CopilotSuggestion[] = [
  {
    id: 'policy-dust',
    category: 'Policy',
    question: 'What does CPCB say about construction dust control?',
  },
  {
    id: 'policy-ncap',
    category: 'Policy',
    question: 'Give me a summary of NCAP guidelines for Bengaluru',
  },
  {
    id: 'enforce-priorities',
    category: 'Enforcement',
    question: 'Show me the top enforcement priorities in Bengaluru right now',
  },
  {
    id: 'enforce-area',
    category: 'Enforcement',
    question: 'Where should officers inspect for construction dust today?',
  },
  {
    id: 'aqi-why',
    category: 'General AQI',
    question: 'Why is air quality poor near Peenya right now?',
  },
  {
    id: 'whatif-construction',
    category: 'What-If',
    question: 'What if construction activity reduces by 50% near Peenya?',
  },
  {
    id: 'whatif-traffic',
    category: 'What-If',
    question: 'What if we reduce traffic emissions by 30% on major corridors?',
  },
  {
    id: 'traffic-peak',
    category: 'Weather + Pollution',
    question: 'What are the peak traffic hours affecting pollution in Bengaluru?',
  },
];

/** Generic refuse strings from old/new fallbacks — treat as soft failures in UI */
export function isGenericCopilotRefuse(text: string): boolean {
  const t = (text || '').toLowerCase();
  return (
    t.includes('could not answer that question specifically from the available') ||
    t.includes('could not produce an answer from available tools') ||
    t.includes("i couldn't complete the reasoning step") ||
    t.includes("i couldn't parse the planning decision") ||
    t.includes('try asking about enforcement priorities')
  );
}

export type CopilotSendPayload = {
  message: string;
  /** Map / Enforcement context — preferred location for the agent */
  station_id?: string;
  h3_cell?: string | null;
  /** Prior turns in this chat (max 6 sent) */
  conversation_history?: ConversationTurn[];
  session_id?: string;
};

export type CopilotModeLabel =
  | 'Tool Agent'
  | 'Heuristic Fallback'
  | 'Fast Path'
  | 'Cached';

/** Derive human-readable mode badge from API response. */
export function deriveCopilotMode(data: {
  response_mode?: string | null;
  selected_agent?: string;
  llm_mode?: string;
  fallback_used?: boolean;
  cache_hit?: boolean;
  warnings?: string[];
  audit_trail?: {
    response_mode?: string | null;
    cache_hit?: boolean;
    warnings?: string[];
    selected_agent?: string;
    whatif_used?: boolean;
    memory_turns_used?: number;
  };
  structured_data?: { path?: string };
}): {
  mode: CopilotResponseMode;
  label: CopilotModeLabel;
  fromCache: boolean;
  cacheKind: string | null;
  whatifUsed: boolean;
  memoryTurns: number;
} {
  const audit = data.audit_trail ?? {};
  const warnings = [...(data.warnings || []), ...(audit.warnings || [])];
  const fromCache =
    Boolean(data.cache_hit) ||
    Boolean(audit.cache_hit) ||
    warnings.includes('served_from_response_cache');
  const cacheKind = warnings.includes('served_from_semantic_cache')
    ? 'semantic'
    : fromCache
      ? 'exact'
      : null;

  let mode: CopilotResponseMode = data.response_mode || audit.response_mode || '';

  if (!mode) {
    const path = data.structured_data?.path || '';
    const agent = data.selected_agent || audit.selected_agent || '';
    if (path === 'heuristic_fallback' || (data.fallback_used && data.llm_mode === 'deterministic')) {
      mode = 'heuristic_fallback';
    } else if (agent === 'forecast_evidence_agent' && data.llm_mode === 'deterministic') {
      mode = 'fast_path';
    } else if (agent === 'grounded_tool_agent') {
      mode = 'tool_agent';
    } else {
      mode = agent || 'tool_agent';
    }
  }

  let label: CopilotModeLabel = 'Tool Agent';
  if (mode === 'heuristic_fallback') label = 'Heuristic Fallback';
  else if (mode === 'fast_path') label = 'Fast Path';
  else if (mode === 'tool_agent') label = 'Tool Agent';
  else if (fromCache) label = 'Cached';

  return {
    mode,
    label,
    fromCache,
    cacheKind,
    whatifUsed: Boolean(audit.whatif_used),
    memoryTurns: Number(audit.memory_turns_used || 0),
  };
}

export function formatCopilotError(err: unknown): {
  detail: string;
  timedOut: boolean;
  networkError: boolean;
  userMessage: string;
} {
  const e = err as {
    code?: string;
    message?: string;
    response?: { status?: number; data?: { detail?: unknown } };
  };
  const raw = e?.response?.data?.detail ?? e?.message ?? 'Request failed';
  const detail = Array.isArray(raw)
    ? raw.map((x: { msg?: string }) => x?.msg || JSON.stringify(x)).join('; ')
    : typeof raw === 'object' && raw !== null
      ? JSON.stringify(raw)
      : String(raw);

  const timedOut =
    e?.code === 'ECONNABORTED' || String(detail).toLowerCase().includes('timeout');
  const networkError =
    !e?.response &&
    (e?.code === 'ERR_NETWORK' ||
      String(detail).toLowerCase().includes('network') ||
      String(e?.message || '').toLowerCase().includes('network'));

  let userMessage: string;
  if (timedOut) {
    userMessage =
      'Timed out waiting for Copilot (90s). Try again or simplify the question.';
  } else if (networkError) {
    userMessage =
      'Network error — could not reach the API. Check that the backend is running and try again.';
  } else if (e?.response?.status && e.response.status >= 500) {
    userMessage = `Server error (${e.response.status}): ${detail}`;
  } else if (e?.response?.status === 422) {
    userMessage = `Invalid request: ${detail}`;
  } else {
    userMessage = detail;
  }

  return { detail, timedOut, networkError, userMessage };
}

export function useSendMessage() {
  return useMutation({
    mutationFn: async (payload: string | CopilotSendPayload) => {
      const message = typeof payload === 'string' ? payload : payload.message;
      const station_id = typeof payload === 'object' ? payload.station_id || '' : '';
      const h3_cell = typeof payload === 'object' ? payload.h3_cell || null : null;
      const conversation_history =
        typeof payload === 'object' ? payload.conversation_history || [] : [];
      const session_id = typeof payload === 'object' ? payload.session_id : undefined;

      const body: Record<string, unknown> = {
        query: message,
        city: 'bengaluru',
        profile: 'general',
        language: 'en',
      };
      if (station_id) body.station_id = station_id;
      if (h3_cell) body.h3_cell = h3_cell;
      if (conversation_history.length > 0) {
        body.conversation_history = conversation_history.slice(-6);
      }
      if (session_id) body.session_id = session_id;

      const { data } = await apiClient.post('/copilot/query', body, { timeout: 90_000 });
      return data;
    },
  });
}

export async function fetchCopilotSuggestions(): Promise<CopilotSuggestion[]> {
  try {
    const { data } = await apiClient.get('/copilot/suggestions', { timeout: 8_000 });
    if (Array.isArray(data?.suggestions) && data.suggestions.length > 0) {
      return data.suggestions as CopilotSuggestion[];
    }
  } catch {
    // offline / backend not ready
  }
  return FALLBACK_SUGGESTIONS;
}

/** Fire-and-forget: warm RAG + cache common answers when the Copilot tab opens. */
export async function prefetchCopilot(): Promise<void> {
  try {
    await apiClient.post(
      '/copilot/prefetch',
      { city: 'bengaluru', wait: false },
      { timeout: 10_000 },
    );
  } catch {
    // non-blocking
  }
}
