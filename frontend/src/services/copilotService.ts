import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';
import { ChatMessage } from '../types';
import { copilotHistory } from '../api/mockData';

export function useCopilotHistory() {
  return useQuery<ChatMessage[]>({
    queryKey: ['copilot-history'],
    queryFn: async () => {
      // Prepared for backend integration:
      // In production, you would fetch from: await apiClient.get<ChatMessage[]>('/copilot/history')
      return Promise.resolve(copilotHistory);
    },
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (message: string) => {
      const { data } = await apiClient.post<any>('/copilot/chat', { message });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['copilot-history'] });
    },
  });
}
