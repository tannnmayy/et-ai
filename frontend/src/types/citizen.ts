export type HealthCondition = 'respiratory' | 'elderly' | 'young_children' | 'none';
export type CitizenPriority = 'metro' | 'schools' | 'hospitals' | 'parks' | 'low_aqi' | 'low_noise';

export interface CitizenProfile {
  rentBudget: number;
  familySize: number;
  healthConditions: HealthCondition[];
  officeLocation: string;
  maxCommuteMinutes: number;
  priorities: CitizenPriority[];
}

export interface NeighbourhoodFeatureVector {
  aqi: number;
  aqiIsEstimated: boolean;
  avgRentForBudgetBHK: number;
  rentIsEstimated: boolean;
  commuteMinutesToOffice: number;
  hospitalScore: number;
  schoolScore: number;
  parkScore: number;
  /** null when metro/transit layer is unavailable for a locality */
  metroDistanceKm: number | null;
  noiseScore: number;
  constructionActivityScore: number;
}

export interface NeighbourhoodMatch {
  rank: number;
  name: string;
  matchScorePercent: number;
  reasons: string[];
  featureVector: NeighbourhoodFeatureVector;
}
