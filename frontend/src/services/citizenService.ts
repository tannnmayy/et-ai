import { apiClient } from '../api/axiosClient';
import type { CitizenProfile, NeighbourhoodMatch } from '../types/citizen';

/**
 * MOCK_MATCHES is ONLY for local UI sandboxing.
 * Never used as a silent fallback when the live API fails.
 */
export const MOCK_MATCHES: NeighbourhoodMatch[] = [
  {
    rank: 1,
    name: 'Koramangala Block 3',
    matchScorePercent: 94,
    reasons: [
      'Rent matches ₹45k budget',
      'Direct metro line access (Est. 2025)',
      'High canopy cover; 3 parks within 1km',
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
      constructionActivityScore: 20,
    },
  },
  {
    rank: 2,
    name: 'Indiranagar Stage 1',
    matchScorePercent: 88,
    reasons: [
      'Optimal commute to primary workspace',
      'High density of healthcare facilities',
      'Rent exceeds target by 12%',
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
      constructionActivityScore: 45,
    },
  },
  {
    rank: 3,
    name: 'Jayanagar 4th Block',
    matchScorePercent: 76,
    reasons: [
      'Exceptional green cover and parks',
      'Well within stated budget parameters',
      'Longer commute time projected',
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
      constructionActivityScore: 15,
    },
  },
];

/**
 * Normalize a single API match into the frontend NeighbourhoodMatch shape.
 * Guards against missing nested fields that would crash list/detail renderers.
 */
function normalizeMatch(raw: unknown, index: number): NeighbourhoodMatch | null {
  if (!raw || typeof raw !== 'object') return null;
  const m = raw as Record<string, unknown>;
  const fvRaw = (m.featureVector ?? m.feature_vector) as Record<string, unknown> | undefined;
  if (!fvRaw || typeof fvRaw !== 'object') return null;

  const num = (v: unknown, fallback = 0) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
  };

  const metroRaw = fvRaw.metroDistanceKm ?? fvRaw.metro_distance_km;
  const metroDistanceKm =
    metroRaw == null || metroRaw === ''
      ? null
      : Number.isFinite(Number(metroRaw))
        ? Number(metroRaw)
        : null;

  const reasons = Array.isArray(m.reasons)
    ? (m.reasons as unknown[]).map(String).filter(Boolean)
    : [];

  return {
    rank: num(m.rank, index + 1),
    name: String(m.name || `Area ${index + 1}`),
    matchScorePercent: Math.round(num(m.matchScorePercent ?? m.match_score_percent, 0)),
    reasons,
    featureVector: {
      aqi: num(fvRaw.aqi, 0),
      aqiIsEstimated: Boolean(fvRaw.aqiIsEstimated ?? fvRaw.aqi_is_estimated),
      avgRentForBudgetBHK: num(
        fvRaw.avgRentForBudgetBHK ?? fvRaw.avg_rent_for_budget_bhk,
        0,
      ),
      rentIsEstimated: Boolean(fvRaw.rentIsEstimated ?? fvRaw.rent_is_estimated),
      commuteMinutesToOffice: Math.round(
        num(fvRaw.commuteMinutesToOffice ?? fvRaw.commute_minutes_to_office, 0),
      ),
      hospitalScore: num(fvRaw.hospitalScore ?? fvRaw.hospital_score, 0),
      schoolScore: num(fvRaw.schoolScore ?? fvRaw.school_score, 0),
      parkScore: num(fvRaw.parkScore ?? fvRaw.park_score, 0),
      metroDistanceKm,
      noiseScore: num(fvRaw.noiseScore ?? fvRaw.noise_score, 0),
      constructionActivityScore: num(
        fvRaw.constructionActivityScore ?? fvRaw.construction_activity_score,
        0,
      ),
    },
  };
}

/**
 * Fetches ranked neighbourhood matches for a citizen profile.
 * Errors propagate so the UI can show an honest error state.
 */
export async function getNeighbourhoodMatches(
  profile: CitizenProfile,
): Promise<NeighbourhoodMatch[]> {
  const response = await apiClient.post<unknown>('/citizen/matches', profile);
  const data = response.data;

  // Backend returns a bare array; tolerate accidental envelope shapes.
  let list: unknown[] = [];
  if (Array.isArray(data)) {
    list = data;
  } else if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (Array.isArray(obj.matches)) list = obj.matches;
    else if (Array.isArray(obj.results)) list = obj.results;
    else if (Array.isArray(obj.data)) list = obj.data;
  }

  return list
    .map((item, i) => normalizeMatch(item, i))
    .filter((m): m is NeighbourhoodMatch => m != null);
}
