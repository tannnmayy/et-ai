/**
 * AQI Sentinel Types
 */

export interface Station {
  id: string;
  name: string;
  lat: number;
  lng: number;
  aqi: number;
  status: 'Good' | 'Moderate' | 'Poor' | 'Severe';
}

export type SourceKey = 'traffic' | 'industrial' | 'construction' | 'burning';
export type ExposureLevel = 'Low' | 'Medium' | 'High' | 'Critical';
export type ActionTier = 'IMMEDIATE' | 'HIGH' | 'MONITOR' | 'ROUTINE';

export interface PriorityHex {
  id: string;
  name: string;
  /** Display score 0–10 (derived from backend 0–1 priority_score) */
  score10: number;
  /** Backend 0–1 priority score (kept for sorting fidelity) */
  priorityScore: number;
  rank: number;
  changeVal: number;
  exposure: ExposureLevel;
  /** Attributable magnitude 0–100 */
  magnitude: number;
  confidence: number;
  /** @deprecated use actionTier */
  actionability: ActionTier;
  actionTier: ActionTier;
  pm25: number;
  primarySource: string;
  primarySourceKey: SourceKey | 'mixed';
  sourceType: 'Heavy Ind.' | 'Construction' | 'Traffic Hub' | 'Waste Burning' | 'Mixed';
  sourceAttribution: {
    traffic: number;
    industrial: number;
    construction: number;
    burning: number;
  };
  explanation?: { text: string; generated_by: string };
  lat: number;
  lng: number;
  // Optional traffic enhancements from backend
  trafficCorridorScore?: number;
  isMajorRoadCorridor?: boolean;
  /** Product flag: corridor_score > 0.4 or major-road corridor */
  isTrafficCorridor?: boolean;
  trafficTimeMultiplier?: number;
  isPeakHour?: boolean;
  trafficHourLocal?: number | null;
  trafficCorridorApplied?: boolean;
  scoringBreakdown?: {
    exposure_weight: number;
    attributable_magnitude: number;
    actionability_weight: number;
  };
}

/** One step in the Copilot operational / deep-reasoning trace */
export interface ReasoningStep {
  id: string;
  step: string;
  completed: boolean;
  type?: string;
  meta?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sender: string;
  reasoning?: ReasoningStep[];
  /** Optional badges: KB used, LLM key fallback, etc. */
  meta?: {
    knowledgeBaseUsed?: boolean;
    knowledgeBackend?: string | null;
    llmProvider?: string | null;
    geminiKeyIndex?: number | null;
    fallbackUsed?: boolean;
    llmMode?: string;
  };
  attachments?: { name: string; type: string }[];
}

export interface Neighbourhood {
  id: string;
  sectorCode: string;
  name: string;
  suitability: number;
  componentBreakdown: {
    aqi: number;
    greens: number;
    noise: number;
    transit: number;
    safety: number;
    health: number;
    water: number;
  };
  tags: string[];
}
