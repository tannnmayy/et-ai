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

export interface PriorityHex {
  id: string;
  name: string;
  priorityScore: number;
  changeVal: number;
  exposure: 'Low' | 'Medium' | 'High' | 'Critical';
  magnitude: number;
  confidence: number;
  actionability: 'IMMEDIATE' | 'HIGH' | 'MONITOR';
  pm25: number;
  primarySource: string;
  sourceType: 'Heavy Ind.' | 'Construction' | 'Traffic Hub' | 'Waste Burning';
  sourceAttribution: { traffic: number; industrial: number; construction: number; burning: number };
  lat: number;
  lng: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sender: string;
  reasoning?: {
    id: string;
    step: string;
    completed: boolean;
  }[];
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
