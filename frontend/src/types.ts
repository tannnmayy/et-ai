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
  /** Risk-adjusted score = base × confidence factor */
  riskAdjustedScore?: number;
  /** Display 0–10 from risk-adjusted score */
  riskAdjustedScore10?: number;
  /** Rank under unadjusted base priority */
  baseRank?: number;
  rank: number;
  changeVal: number;
  exposure: ExposureLevel;
  /** Attributable magnitude 0–100 */
  magnitude: number;
  /** @deprecated actionability weight 0–100 — prefer attributionConfidence */
  confidence: number;
  /** 0–100 attribution reliability */
  attributionConfidence?: number;
  attributionConfidenceLevel?: string;
  confidenceExplanation?: string;
  confidenceFlags?: string[];
  riskConfidenceFactor?: number;
  nearestStationDistanceM?: number | null;
  attributionMethod?: string;
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
    risk_confidence_factor?: number;
    attribution_confidence_score?: number;
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

/** Phase 2 Copilot response mode badges */
export type CopilotResponseMode =
  | 'tool_agent'
  | 'heuristic_fallback'
  | 'fast_path'
  | 'cached'
  | string;

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sender: string;
  reasoning?: ReasoningStep[];
  /** Optional badges: KB used, mode, cache, LLM provider, etc. */
  meta?: {
    knowledgeBaseUsed?: boolean;
    knowledgeBackend?: string | null;
    llmProvider?: string | null;
    geminiKeyIndex?: number | null;
    fallbackUsed?: boolean;
    llmMode?: string;
    responseMode?: CopilotResponseMode | null;
    cacheHit?: boolean;
    cacheKind?: string | null;
    isGenericRefuse?: boolean;
    isLimitedResponse?: boolean;
    whatifUsed?: boolean;
    memoryTurns?: number;
    mapActionsApplied?: boolean;
    mapActionCount?: number;
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
