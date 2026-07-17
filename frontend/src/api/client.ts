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
  ENFORCEMENT_DEFAULT_TOP_K,
  ENFORCEMENT_MAX_TOP_K,
  fetchEnforcementPriorities,
  fetchCityExtremes,
  fetchStations,
} from '../services/geospatialService';
export type { ExtremesRankingMode, CityExtremesResult } from '../services/geospatialService';
export { useDashboardData } from '../services/analyticsService';
export { useSendMessage } from '../services/copilotService';
export { useCityInsights, fetchCityInsights } from '../services/insightsService';
export type { CityInsightsPack } from '../services/insightsService';
export {
  loadDispatchHistory,
  recordDispatch,
  logAuditEvent,
  mirrorSession,
} from '../services/persistenceService';
export type { DispatchRecord, DispatchStatus } from '../services/persistenceService';
export { warmAppFromLanding, prefetchMapAndEnforcementData } from '../services/prefetchService';
