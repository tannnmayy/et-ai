// Central re-export point for feature-based API services
export { apiClient } from './axiosClient';

export { useStations, usePriorities, useFireDetections, useAttributionGrid } from '../services/geospatialService';
export { useDashboardData } from '../services/analyticsService';
export { useSendMessage } from '../services/copilotService';
