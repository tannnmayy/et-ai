import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';

export function useDashboardData() {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const { data } = await apiClient.get<any>('/analytics/dashboard');
      return data;
    },
  });
}
