import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';

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
