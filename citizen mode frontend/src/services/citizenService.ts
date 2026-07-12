import { apiClient } from './apiClient';
import { CitizenProfile, NeighbourhoodMatch } from '../types/citizen';

/**
 * MOCK_MATCHES is provided ONLY for local development or prototyping the UI.
 * This must NOT be used as a silent fallback inside the production API call.
 * Developers can manually import this mock data in components to work on UI.
 */
export const MOCK_MATCHES: NeighbourhoodMatch[] = [
  {
    rank: 1,
    name: "Koramangala Block 3",
    matchScorePercent: 94,
    reasons: [
      "Rent matches ₹45k budget",
      "Direct metro line access (Est. 2025)",
      "High canopy cover; 3 parks within 1km"
    ],
    featureVector: {
      aqi: 112,
      aqiIsEstimated: true,
      avgRentForBudgetBHK: 42000,
      rentIsEstimated: true,
      commuteMinutesToOffice: 32,
      hospitalScore: 85,
      schoolScore: 90,
      parkScore: 95,
      metroDistanceKm: 0.4,
      noiseScore: 35,
      constructionActivityScore: 20
    }
  },
  {
    rank: 2,
    name: "Indiranagar Stage 1",
    matchScorePercent: 88,
    reasons: [
      "Optimal commute to primary workspace",
      "High density of healthcare facilities",
      "Rent exceeds target by 12%"
    ],
    featureVector: {
      aqi: 85,
      aqiIsEstimated: false,
      avgRentForBudgetBHK: 51000,
      rentIsEstimated: true,
      commuteMinutesToOffice: 24,
      hospitalScore: 92,
      schoolScore: 88,
      parkScore: 60,
      metroDistanceKm: 0.8,
      noiseScore: 75,
      constructionActivityScore: 45
    }
  },
  {
    rank: 3,
    name: "Jayanagar 4th Block",
    matchScorePercent: 76,
    reasons: [
      "Exceptional green cover and parks",
      "Well within stated budget parameters",
      "Longer commute time projected"
    ],
    featureVector: {
      aqi: 62,
      aqiIsEstimated: false,
      avgRentForBudgetBHK: 38000,
      rentIsEstimated: true,
      commuteMinutesToOffice: 55,
      hospitalScore: 78,
      schoolScore: 85,
      parkScore: 90,
      metroDistanceKm: 1.5,
      noiseScore: 25,
      constructionActivityScore: 15
    }
  }
];

/**
 * Fetches ranked neighborhood matches for a given citizen profile from the backend.
 * Crucial constraint: This function does NOT silently catch errors and return MOCK_MATCHES.
 * Any errors will propagate so the calling component can display an accurate isError / loading state.
 */
export async function getNeighbourhoodMatches(profile: CitizenProfile): Promise<NeighbourhoodMatch[]> {
  const response = await apiClient.post<NeighbourhoodMatch[]>('/citizen/matches', profile);
  return response.data;
}
