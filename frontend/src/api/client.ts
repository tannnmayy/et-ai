// Central re-export point for feature-based API services
export { apiClient } from './axiosClient';
export {
  mockStations,
  mockPriorities,
  mockFireDetections,
  mockNo2Density,
  mockNeighbourhoods,
  initialChatHistory,
  copilotHistory,
} from './mockData';

export { useStations, usePriorities, useFireDetections } from '../services/geospatialService';
export { useDashboardData } from '../services/analyticsService';
export { useCopilotHistory, useSendMessage } from '../services/copilotService';
