import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/axiosClient';
import { Station, PriorityHex } from '../types';

export function useStations() {
  return useQuery<Station[]>({
    queryKey: ['stations'],
    queryFn: async () => {
      const { data } = await apiClient.get<Station[]>('/geospatial/stations');
      return data;
    },
    refetchInterval: 10000, // Auto-refresh sensors
  });
}

export function usePriorities() {
  return useQuery<PriorityHex[]>({
    queryKey: ['priorities'],
    queryFn: async () => {
      const { data } = await apiClient.get<PriorityHex[]>('/geospatial/ranked-priority');
      return data;
    },
  });
}

export function useFireDetections() {
  return useQuery({
    queryKey: ['fire-detections'],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/geospatial/fire-detections');
      return data;
    },
  });
}
