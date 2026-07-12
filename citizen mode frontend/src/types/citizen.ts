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
  rentIsEstimated: boolean;   // true if sourced from an index, not a live listing
  commuteMinutesToOffice: number;
  hospitalScore: number;      // 0-100
  schoolScore: number;        // 0-100
  parkScore: number;          // 0-100
  metroDistanceKm: number;
  noiseScore: number;
  constructionActivityScore: number;
}

export interface NeighbourhoodMatch {
  rank: number;
  name: string;
  matchScorePercent: number;
  reasons: string[];          // human-readable explanation bullets
  featureVector: NeighbourhoodFeatureVector;
}
