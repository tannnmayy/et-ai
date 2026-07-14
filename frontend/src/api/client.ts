// Central re-export point for feature-based API services
export { apiClient } from './axiosClient';

export {
  useStations,
  usePriorities,
  useEnforcementPriorities,
  useFireDetections,
  useAttributionGrid,
  useCityExtremes,
  ENFORCEMENT_FETCH_TOP_K,
} from '../services/geospatialService';
export { useDashboardData } from '../services/analyticsService';
export { useSendMessage } from '../services/copilotService';
