import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';

export type CopilotSuggestion = {
  id: string;
  category: string;
  question: string;
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
    id: 'traffic-peak',
    category: 'Weather + Pollution',
    question: 'What are the peak traffic hours affecting pollution in Bengaluru?',
  },
];

export function useSendMessage() {
  return useMutation({
    mutationFn: async (payload: string | { message: string; force_dynamic_planning?: boolean }) => {
      const message = typeof payload === 'string' ? payload : payload.message;
      const force_dynamic_planning = typeof payload === 'object' ? payload.force_dynamic_planning : false;
      const { data } = await apiClient.post('/copilot/query', {
        query: message,
        city: 'bengaluru',
        profile: 'general',
        language: 'en',
        force_dynamic_planning,
      });
      return data;
    },
  });
}

export async function fetchCopilotSuggestions(): Promise<CopilotSuggestion[]> {
  try {
    const { data } = await apiClient.get('/copilot/suggestions');
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
    await apiClient.post('/copilot/prefetch', { city: 'bengaluru', wait: false });
  } catch {
    // non-blocking
  }
}
