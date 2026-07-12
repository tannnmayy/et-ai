// Central re-export point for feature-based API services
export { apiClient } from './axiosClient';

export { useStations, usePriorities, useFireDetections } from '../services/geospatialService';
export { useDashboardData } from '../services/analyticsService';
export { useCopilotHistory, useSendMessage } from '../services/copilotService';
