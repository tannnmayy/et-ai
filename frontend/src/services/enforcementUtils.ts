/**
 * Pure helpers for Enforcement Intelligence UI.
 * Score tiers, primary source labels, and source-specific recommendations.
 */

import type { ActionTier, PriorityHex, SourceKey } from '../types';

// Re-export for consumers
export type { ActionTier };

export const SOURCE_KEYS: SourceKey[] = ['traffic', 'industrial', 'construction', 'burning'];

export const SOURCE_LABELS: Record<SourceKey, string> = {
  traffic: 'Traffic',
  industrial: 'Industrial',
  construction: 'Construction',
  burning: 'Burning',
};

/** Map 0–1 priority_score → 0–10 display score (1 decimal). */
export function toScore10(priorityScore01: number): number {
  return Math.round(Math.min(1, Math.max(0, priorityScore01)) * 100) / 10;
}

/**
 * Bounded what-if: scale construction share, renormalize, recompute priority
 * using the same E×M×A×L ingredients available on the hex (client-side preview).
 * Does not re-run fusion or city-wide ranking — scoped to the selected hex.
 */
export function simulateConstructionCounterfactual(
  hex: PriorityHex,
  constructionScale: number,
): {
  scale: number;
  sourceAttribution: PriorityHex['sourceAttribution'];
  priorityScore: number;
  score10: number;
  riskAdjustedScore: number;
  riskAdjustedScore10: number;
  magnitude: number;
  actionabilityWeight: number;
  assumptions: string[];
} {
  const scale = Math.min(2, Math.max(0, constructionScale));
  const sa = hex.sourceAttribution;
  const c = sa.construction * scale;
  const t = sa.traffic;
  const i = sa.industrial;
  const b = sa.burning;
  const total = t + i + c + b || 1;
  const sourceAttribution = {
    traffic: t / total,
    industrial: i / total,
    construction: c / total,
    burning: b / total,
  };

  const E = hex.scoringBreakdown?.exposure_weight ?? 0.5;
  const corridor = hex.trafficCorridorScore ?? 0;
  const TRAFFIC_ACT = 0.28 + 0.17 * corridor;
  const A =
    sourceAttribution.traffic * TRAFFIC_ACT +
    sourceAttribution.industrial * 1 +
    sourceAttribution.construction * 1 +
    sourceAttribution.burning * 1;
  const magFrac = Math.min(
    1.5,
    sourceAttribution.industrial +
      sourceAttribution.construction +
      sourceAttribution.burning +
      sourceAttribution.traffic * corridor * 0.75,
  );
  const M = Math.min(1, Math.max(0, ((hex.pm25 || 0) * magFrac) / 300));
  const L = 1 + 0.4 * corridor * sourceAttribution.traffic;
  const priorityScore = E * M * A * L;
  const confFactor =
    hex.riskConfidenceFactor ??
    (hex.attributionConfidence != null
      ? 0.35 + 0.65 * (hex.attributionConfidence / 100)
      : 0.85);
  const riskAdjustedScore = priorityScore * confFactor;

  return {
    scale,
    sourceAttribution,
    priorityScore,
    score10: toScore10(priorityScore),
    riskAdjustedScore,
    riskAdjustedScore10: toScore10(riskAdjustedScore),
    magnitude: Math.round(M * 100),
    actionabilityWeight: A,
    assumptions: [
      'Fused PM2.5 held constant (no re-fusion).',
      'Only construction intensity scaled; other channels re-normalized.',
      'Uses same E×M×A×corridor-lift formula as enforcement ranking.',
      'City-wide ranks are not recomputed in this panel preview.',
    ],
  };
}

/**
 * Action tier rules (score is 0–10 scale):
 *  ≥9 + High/Critical exposure → IMMEDIATE
 *  7–8.9 → HIGH PRIORITY
 *  5–6.9 → MONITOR
 *  else → ROUTINE
 */
export function deriveActionTier(
  score10: number,
  exposure: PriorityHex['exposure'],
): ActionTier {
  const highExposure = exposure === 'High' || exposure === 'Critical';
  if (score10 >= 9 && highExposure) return 'IMMEDIATE';
  if (score10 >= 9) return 'HIGH';
  if (score10 >= 7) return 'HIGH';
  if (score10 >= 5) return 'MONITOR';
  return 'ROUTINE';
}

export function actionTierLabel(tier: ActionTier): string {
  switch (tier) {
    case 'IMMEDIATE':
      return 'IMMEDIATE';
    case 'HIGH':
      return 'HIGH PRIORITY';
    case 'MONITOR':
      return 'MONITOR';
    case 'ROUTINE':
      return 'ROUTINE';
  }
}

export function actionTierStyles(tier: ActionTier): {
  bg: string;
  dot: string;
  text: string;
  mapColor: string;
} {
  switch (tier) {
    case 'IMMEDIATE':
      return {
        bg: 'bg-brand-red/10 border-brand-red/20 text-brand-red',
        dot: 'bg-brand-red shadow-[0_0_4px_#ff453a]',
        text: 'IMMEDIATE',
        mapColor: '#ff453a',
      };
    case 'HIGH':
      return {
        bg: 'bg-brand-orange/10 border-brand-orange/20 text-brand-orange',
        dot: 'bg-brand-orange shadow-[0_0_4px_#FF9F0A]',
        text: 'HIGH PRIORITY',
        mapColor: '#FF9F0A',
      };
    case 'MONITOR':
      return {
        bg: 'bg-yellow-500/10 border-yellow-500/25 text-yellow-400',
        dot: 'bg-yellow-400 shadow-[0_0_4px_#eab308]',
        text: 'MONITOR',
        mapColor: '#eab308',
      };
    case 'ROUTINE':
    default:
      return {
        bg: 'bg-apple-border/40 border-apple-border text-apple-secondary',
        dot: 'bg-apple-secondary',
        text: 'ROUTINE',
        mapColor: '#8E8E93',
      };
  }
}

export function dominantSource(
  attr: PriorityHex['sourceAttribution'],
): { key: SourceKey; label: string; share: number; isMixed: boolean } {
  const entries = SOURCE_KEYS.map((k) => ({ key: k, val: attr[k] ?? 0 }));
  entries.sort((a, b) => b.val - a.val);
  const top = entries[0];
  const second = entries[1];
  const isMixed = top.val < 0.4 || (second && top.val - second.val < 0.08);
  if (isMixed) {
    return { key: top.key, label: 'Mixed', share: top.val, isMixed: true };
  }
  return {
    key: top.key,
    label: SOURCE_LABELS[top.key],
    share: top.val,
    isMixed: false,
  };
}

export interface EnforcementRecommendation {
  title: string;
  urgency: ActionTier;
  actions: string[];
  estimatedImpact: string;
}

export function buildRecommendations(hex: PriorityHex): EnforcementRecommendation[] {
  const { key, isMixed } = dominantSource(hex.sourceAttribution);
  const tier = hex.actionTier;
  const recs: EnforcementRecommendation[] = [];

  if (key === 'construction' || isMixed) {
    recs.push({
      title: 'Construction dust control',
      urgency: tier === 'IMMEDIATE' || key === 'construction' ? tier : 'HIGH',
      actions: [
        'Inspect site for active C&D activity and valid permits',
        'Mandate water sprinkling / dust screens during working hours',
        'Issue stop-work notice if dust controls are absent',
        'Photograph and log site GPS + contractor details',
      ],
      estimatedImpact: 'Can cut local dust peaks 20–40% within 24–48h when enforced',
    });
  }

  if (key === 'traffic' || (isMixed && hex.sourceAttribution.traffic > 0.25)) {
    const corridorNote = hex.isMajorRoadCorridor
      ? 'Focus on major arterial corridor segments (motorway/trunk/primary).'
      : 'Prioritise congested approaches and signalised junctions.';
    recs.push({
      title: hex.isMajorRoadCorridor ? 'Corridor traffic enforcement' : 'Traffic emission checks',
      urgency: key === 'traffic' ? tier : 'MONITOR',
      actions: [
        corridorNote,
        'Deploy idling checks for diesel fleets during peak windows',
        'Coordinate with traffic police on congestion choke points',
        'Spot-check PUC / overloaded commercial vehicles',
      ],
      estimatedImpact: hex.isPeakHour
        ? `Peak-hour traffic weight ×${hex.trafficTimeMultiplier ?? 1.4} — intercept during rush for maximum visibility`
        : 'Steady-state traffic control; peak hours yield higher impact',
    });
  }

  if (key === 'industrial' || (isMixed && hex.sourceAttribution.industrial > 0.25)) {
    recs.push({
      title: 'Industrial source inspection',
      urgency: key === 'industrial' ? tier : 'HIGH',
      actions: [
        'Verify consent to operate and stack monitoring logs',
        'Check visible emissions and bag-filter / scrubber status',
        'Sample fugitive emissions from open storage if present',
        'Escalate to KSPCB if non-compliant',
      ],
      estimatedImpact: 'Direct compliance action on permitted facilities',
    });
  }

  if (key === 'burning' || (isMixed && hex.sourceAttribution.burning > 0.2)) {
    recs.push({
      title: 'Open burning response',
      urgency: key === 'burning' ? 'IMMEDIATE' : 'HIGH',
      actions: [
        'Locate active fire / smoulder sites (FIRMS + ground patrol)',
        'Extinguish illegal waste/biomass burning immediately',
        'Identify responsible party; issue notice under relevant rules',
        'Schedule follow-up within 24 hours',
      ],
      estimatedImpact: 'Immediate local PM reduction when fire is extinguished',
    });
  }

  if (recs.length === 0) {
    recs.push({
      title: 'General monitoring',
      urgency: 'ROUTINE',
      actions: [
        'Continue ambient monitoring and reassess after next peak window',
        'Log community complaints for this sector',
      ],
      estimatedImpact: 'Baseline surveillance',
    });
  }

  return recs;
}

export function formatLocationName(hex: PriorityHex): string {
  const raw = (hex.name || '').trim();
  const looksRaw =
    !raw ||
    raw === hex.id ||
    raw.toLowerCase().startsWith('grid ') ||
    raw.toLowerCase().startsWith('sector ') ||
    (raw.length >= 10 && /^[0-9a-f]+$/i.test(raw));

  if (!looksRaw) {
    // Prefer short locality (first segment of reverse-geocode label)
    const short = raw.split(',')[0]?.trim();
    return short || raw;
  }

  // Backend should always send a locality; last-resort soft label (never bare H3)
  const ns = hex.lat >= 12.97 ? 'N' : 'S';
  const ew = hex.lng >= 77.6 ? 'E' : 'W';
  return `Bengaluru ${ns}${ew}`;
}

/** H3 id for tooltips / debug only — never the primary table label. */
export function formatHexIdSubtitle(hex: PriorityHex): string {
  return hex.id;
}

export type SortKey = 'rank' | 'score' | 'magnitude' | 'exposure' | 'name' | 'source';

export function sortHexes(
  items: PriorityHex[],
  key: SortKey,
  dir: 'asc' | 'desc',
): PriorityHex[] {
  const mult = dir === 'asc' ? 1 : -1;
  const exposureOrder = { Low: 0, Medium: 1, High: 2, Critical: 3 };
  return [...items].sort((a, b) => {
    let cmp = 0;
    switch (key) {
      case 'rank':
        cmp = a.rank - b.rank;
        break;
      case 'score':
        cmp = a.score10 - b.score10;
        break;
      case 'magnitude':
        cmp = a.magnitude - b.magnitude;
        break;
      case 'exposure':
        cmp = exposureOrder[a.exposure] - exposureOrder[b.exposure];
        break;
      case 'name':
        cmp = formatLocationName(a).localeCompare(formatLocationName(b));
        break;
      case 'source':
        cmp = a.primarySource.localeCompare(b.primarySource);
        break;
    }
    return cmp * mult;
  });
}
