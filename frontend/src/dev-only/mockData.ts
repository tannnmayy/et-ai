// ⚠️  DEV-ONLY: This file is quarantined from production code paths.
// It must NEVER be imported by apiClient.ts or any production service.
// Contains fake (and geographically wrong) data — e.g. "Okhla Phase II"
// is a Delhi location, not Bengaluru. Use only for local frontend-only
// prototyping with a stopped backend.
import { Station, PriorityHex, ChatMessage, Neighbourhood } from '../types';

export const mockStations: Station[] = [
  { id: 'st-1', name: 'Peenya Industrial Area', lat: 13.0285, lng: 77.5195, aqi: 185, status: 'Severe' },
  { id: 'st-2', name: 'Whitefield Sector 44', lat: 12.9698, lng: 77.7499, aqi: 142, status: 'Poor' },
  { id: 'st-3', name: 'Silk Board Junction', lat: 12.9176, lng: 77.6244, aqi: 128, status: 'Poor' },
  { id: 'st-4', name: 'Bellandur Lake Margin', lat: 12.9304, lng: 77.6784, aqi: 115, status: 'Poor' },
  { id: 'st-5', name: 'Electronic City Phase 1', lat: 12.8452, lng: 77.6762, aqi: 95, status: 'Moderate' },
  { id: 'st-6', name: 'Jayanagar 4th Block', lat: 12.9299, lng: 77.5824, aqi: 42, status: 'Good' },
  { id: 'st-7', name: 'Koramangala Sector 7A', lat: 12.9348, lng: 77.6189, aqi: 52, status: 'Moderate' },
];

export const mockPriorities: PriorityHex[] = [
  {
    id: '89283082b',
    name: 'Okhla Phase II',
    priorityScore: 98.4,
    changeVal: 2.4,
    exposure: 'High',
    magnitude: 42,
    confidence: 92,
    actionability: 'IMMEDIATE',
    pm25: 485,
    primarySource: 'Industrial Emission',
    sourceType: 'Heavy Ind.',
    sourceAttribution: { traffic: 0.25, industrial: 0.55, construction: 0.15, burning: 0.05 },
    lat: 12.9698,
    lng: 77.7499,
  },
  {
    id: '89283082a',
    name: 'Anand Vihar ISBT',
    priorityScore: 94.1,
    changeVal: -1.2,
    exposure: 'Critical',
    magnitude: 38,
    confidence: 89,
    actionability: 'HIGH',
    pm25: 412,
    primarySource: 'Vehicular Emissions',
    sourceType: 'Traffic Hub',
    sourceAttribution: { traffic: 0.60, industrial: 0.10, construction: 0.20, burning: 0.10 },
    lat: 12.9176,
    lng: 77.6244,
  },
  {
    id: '89283084c',
    name: 'Jahangirpuri Ind.',
    priorityScore: 91.8,
    changeVal: 0.5,
    exposure: 'High',
    magnitude: 29,
    confidence: 85,
    actionability: 'HIGH',
    pm25: 388,
    primarySource: 'Construction Dust',
    sourceType: 'Construction',
    sourceAttribution: { traffic: 0.15, industrial: 0.10, construction: 0.70, burning: 0.05 },
    lat: 13.0285,
    lng: 77.5195,
  },
  {
    id: '89283085f',
    name: 'Bawana Sector 3',
    priorityScore: 86.2,
    changeVal: 0,
    exposure: 'Medium',
    magnitude: 15,
    confidence: 76,
    actionability: 'MONITOR',
    pm25: 320,
    primarySource: 'Open Waste Combustion',
    sourceType: 'Waste Burning',
    sourceAttribution: { traffic: 0.05, industrial: 0.10, construction: 0.10, burning: 0.75 },
    lat: 12.9304,
    lng: 77.6784,
  },
];

export const mockFireDetections = [
  { id: 'fire-1', lat: 12.945, lng: 77.72, intensity: 'High', detectedAt: '15:12' },
  { id: 'fire-2', lat: 13.012, lng: 77.53, intensity: 'Moderate', detectedAt: '14:45' },
];

export const mockNo2Density = [
  { zone: 'Whitefield', density: 85.4, unit: '10^15 molec/cm²' },
  { zone: 'Peenya', density: 112.1, unit: '10^15 molec/cm²' },
  { zone: 'Silk Board', density: 98.6, unit: '10^15 molec/cm²' },
];

export const mockNeighbourhoods: Neighbourhood[] = [
  {
    id: 'n-1',
    sectorCode: 'Sector 7A',
    name: 'Koramangala',
    suitability: 82,
    componentBreakdown: { aqi: 75, greens: 90, noise: 60, transit: 85, safety: 78, health: 92, water: 65 },
    tags: ['Low PM2.5', 'Optimal Parks'],
  },
  {
    id: 'n-2',
    sectorCode: 'Sector 12B',
    name: 'Indiranagar',
    suitability: 65,
    componentBreakdown: { aqi: 45, greens: 80, noise: 50, transit: 70, safety: 65, health: 85, water: 55 },
    tags: ['Heavy Traffic', 'High Greens'],
  },
];

export const initialChatHistory: ChatMessage[] = [
  {
    id: 'msg-1',
    role: 'user',
    content: 'What are the primary pollution sources currently affecting the Whitefield zone? Are there any active violations?',
    timestamp: '14:02',
    sender: 'Operative K.',
  },
  {
    id: 'msg-2',
    role: 'assistant',
    content: `Analysis complete. The current elevated AQI (**142** - Unhealthy for Sensitive Groups) in the Whitefield sector is primarily driven by three factors:

* 🏭 **Industrial Emissions**: Sector 4 manufacturing plant showing anomalous PM2.5 output.
* 🚚 **Heavy Traffic Congestion**: Static corridor detected along Main Arterial Road due to construction.
* 🌬️ **Meteorological Stagnation**: Low wind speeds (1.2 m/s) preventing dispersion.

I have detected **2** potential regulatory violations in Sector **4**. Would you like me to draft an enforcement dispatch?`,
    timestamp: '14:03',
    sender: 'Copilot AI',
    reasoning: [
      { id: 'r-1', step: 'call: get_sensor_data{zone: "whitefield", type: "pm25"}', completed: true },
      { id: 'r-2', step: 'call: get_attribution{location: "whitefield_sector_4"}', completed: true },
      { id: 'r-3', step: 'call: get_enforcement_priority{violators: true}', completed: true },
      { id: 'r-4', step: 'synthesizing_response...', completed: true },
    ],
  },
];

// In-memory chat storage to persist across page navigations
export let copilotHistory: ChatMessage[] = [...initialChatHistory];

export function addChatMessage(userMessage: string, reply: string, reasoning: { id: string; step: string; completed: boolean }[]) {
  const userMsg: ChatMessage = {
    id: `msg-user-${Date.now()}`,
    role: 'user',
    content: userMessage,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    sender: 'Operative K.',
  };
  const botMsg: ChatMessage = {
    id: `msg-bot-${Date.now()}`,
    role: 'assistant',
    content: reply,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    sender: 'Copilot AI',
    reasoning,
  };
  copilotHistory = [...copilotHistory, userMsg, botMsg];
  return copilotHistory;
}
