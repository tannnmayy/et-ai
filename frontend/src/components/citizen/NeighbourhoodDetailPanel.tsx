import React, { useState } from 'react';
import { ArrowLeft, Map, Shield, Landmark, Sparkles, Navigation, Heart, TreePine, AlertTriangle, Check, BookOpen, Volume2, ShieldAlert } from 'lucide-react';
import type { NeighbourhoodMatch, CitizenProfile } from '../../types/citizen';

interface NeighbourhoodDetailPanelProps {
  match: NeighbourhoodMatch;
  profile: CitizenProfile;
  onBack: () => void;
}

export default function NeighbourhoodDetailPanel({ match, profile, onBack }: NeighbourhoodDetailPanelProps) {
  const [isSaved, setIsSaved] = useState(false);
  const { name, matchScorePercent, reasons, featureVector } = match;

  // Helper to format currency
  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val);
  };

  // Score levels converter
  const getScoreLevel = (score: number) => {
    if (score >= 80) return { label: 'High', colorClass: 'bg-brand-green', textClass: 'text-brand-green' };
    if (score >= 50) return { label: 'Med', colorClass: 'bg-brand-orange', textClass: 'text-brand-orange' };
    return { label: 'Low', colorClass: 'bg-brand-red', textClass: 'text-brand-red' };
  };

  // Helper for progress bar color based on a range
  const getBarColorClass = (val: number, type: 'aqi' | 'distance' | 'score') => {
    if (type === 'aqi') {
      if (val <= 50) return 'bg-brand-green';
      if (val <= 100) return 'bg-brand-orange';
      return 'bg-brand-red';
    }
    if (type === 'distance') {
      if (val <= 0.5) return 'bg-brand-green';
      if (val <= 1.2) return 'bg-brand-orange';
      return 'bg-brand-red';
    }
    // General scores (0-100, where higher is better)
    if (val >= 85) return 'bg-brand-green';
    if (val >= 60) return 'bg-brand-orange';
    return 'bg-brand-red';
  };

  // Derive levels for Feature Vector items
  const aqiLevel = featureVector.aqi <= 50 ? 'Good' : featureVector.aqi <= 100 ? 'Mod' : 'Unhealthy';
  const aqiBarColor = featureVector.aqi <= 50 ? 'bg-brand-green' : featureVector.aqi <= 100 ? 'bg-brand-orange' : 'bg-brand-red';

  const commuteLevel = featureVector.commuteMinutesToOffice <= 25 ? 'Good' : featureVector.commuteMinutesToOffice <= 45 ? 'Med' : 'Poor';
  const commuteBarColor = featureVector.commuteMinutesToOffice <= 25 ? 'bg-brand-green' : featureVector.commuteMinutesToOffice <= 45 ? 'bg-brand-orange' : 'bg-brand-red';

  const rentAffordabilityLevel = featureVector.avgRentForBudgetBHK <= profile.rentBudget ? 'High' : 'Low';
  const rentAffordabilityBarColor = featureVector.avgRentForBudgetBHK <= profile.rentBudget ? 'bg-brand-green' : 'bg-brand-red';

  const hospitalLevel = getScoreLevel(featureVector.hospitalScore);
  const schoolLevel = getScoreLevel(featureVector.schoolScore);
  const greenSpaceLevel = getScoreLevel(featureVector.parkScore);

  // General descriptions for Indiranagar, Koramangala and Jayanagar to match the visual context
  const getNeighbourhoodDesc = (nName: string) => {
    if (nName.includes('Koramangala')) {
      return 'Premium startup and commercial hub. Abundant elite dining, leafy streets, high-quality public parks, and central metropolitan connectivity.';
    }
    if (nName.includes('Indiranagar')) {
      return 'High-density commercial and residential hub. Excellent transit connectivity, premium rent pricing, vibrant culture, and active civic infrastructure.';
    }
    if (nName.includes('Jayanagar')) {
      return 'Classic, heritage-rich residential sector. Outstanding canopy cover, peaceful secondary streets, excellent schools, and highly stable local community vibe.';
    }
    return 'Balanced urban residential sector. Configured for high-efficiency commute access and localized municipal services.';
  };

  return (
    <div id="neighbourhood-detail-panel" className="space-y-6">
      
      {/* Navigation Header */}
      <div className="flex items-center space-x-3">
        <button
          id="btn-back-to-results"
          onClick={onBack}
          className="w-11 h-11 flex items-center justify-center rounded-xl bg-apple-card hover:bg-apple-border border border-apple-border text-white transition-all duration-200 cursor-pointer"
          aria-label="Back to results list"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <span className="text-apple-secondary text-sm font-semibold tracking-wider uppercase">
          Back to Ranked Results
        </span>
      </div>

      {/* Hero Title Block */}
      <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-4">
        <div className="space-y-2 max-w-xl">
          <div className="flex items-center space-x-3">
            <span className="px-2.5 py-0.5 rounded bg-brand-blue/10 text-brand-blue font-mono font-bold text-base border border-brand-blue/25">
              {String(match.rank).padStart(2, '0')}
            </span>
            <h1 id="neighbourhood-detail-title" className="text-3xl font-bold text-white tracking-tight">
              {name}
            </h1>
          </div>
          <p className="text-apple-secondary text-sm leading-relaxed">
            {getNeighbourhoodDesc(name)}
          </p>
        </div>

        {/* Overall Match Score Card */}
        <div id="match-score-card" className="bg-apple-card border border-apple-border rounded-xl p-4 min-w-[150px] flex flex-col items-center justify-center text-center select-none">
          <span className="text-apple-secondary text-[10px] font-bold tracking-widest uppercase mb-1">
            Overall Match
          </span>
          <span className="text-brand-green font-mono font-bold text-3xl">
            {matchScorePercent}%
          </span>
        </div>
      </div>

      {/* Grid: Left Column (Spatial Map Placeholder) | Right Column (Primary Constraints) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Spatial Context (Map Placeholder) */}
        <div id="spatial-context-box" className="bg-apple-card border border-apple-border rounded-xl p-6 lg:col-span-7 flex flex-col">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-semibold tracking-wider text-apple-secondary uppercase select-none flex items-center space-x-1.5">
              <Map className="w-4 h-4 text-brand-blue" />
              <span>Spatial Context</span>
            </h3>
            <span className="text-[10px] font-bold text-brand-blue bg-brand-blue/10 border border-brand-blue/30 px-2.5 py-0.5 rounded-full select-none">
              OSM DATA
            </span>
          </div>

          {/* Styled Map Container Mock */}
          <div className="flex-1 min-h-[220px] bg-black/50 border border-apple-border/50 rounded-lg flex flex-col items-center justify-center relative overflow-hidden group select-none">
            {/* Background grids / lines simulating spatial vectors */}
            <div className="absolute inset-0 grid grid-cols-6 grid-rows-6 opacity-10 pointer-events-none">
              {Array.from({ length: 36 }).map((_, i) => (
                <div key={i} className="border border-white/60" />
              ))}
            </div>
            
            {/* Visual concentric circle rings */}
            <div className="absolute w-44 h-44 rounded-full border border-brand-blue/20 opacity-20 pointer-events-none animate-pulse" />
            <div className="absolute w-28 h-28 rounded-full border border-brand-blue/30 opacity-20 pointer-events-none" />

            {/* Map Pins / Elements */}
            <div className="absolute top-[35%] left-[45%] flex flex-col items-center">
              <div className="w-3.5 h-3.5 bg-brand-blue rounded-full border border-white flex items-center justify-center animate-bounce shadow">
                <div className="w-1.5 h-1.5 bg-white rounded-full" />
              </div>
              <span className="mt-1 text-[9px] bg-black/90 border border-apple-border/80 text-white font-mono px-1.5 py-0.5 rounded shadow">
                {name}
              </span>
            </div>

            <div className="absolute bottom-[25%] right-[30%] flex flex-col items-center opacity-60">
              <div className="w-2.5 h-2.5 bg-brand-red rounded-full border border-white" />
              <span className="text-[8px] text-apple-secondary font-mono mt-0.5">Office Destination</span>
            </div>

            <Map className="w-12 h-12 text-apple-border opacity-60 group-hover:scale-105 transition-transform duration-300" />
            
            <div className="absolute bottom-3 left-3 text-[10px] text-apple-secondary font-mono flex items-center space-x-1 bg-black/80 px-2 py-0.5 rounded border border-apple-border/50">
              <Navigation className="w-3.5 h-3.5 text-brand-blue" />
              <span>Transit Route Computed: <strong className="text-white">{featureVector.commuteMinutesToOffice}m</strong> commute</span>
            </div>
          </div>
        </div>

        {/* Primary Constraints (Rent, AQI, Traffic) */}
        <div id="primary-constraints-box" className="bg-apple-card border border-apple-border rounded-xl p-6 lg:col-span-5 space-y-5 flex flex-col justify-between">
          <h3 className="text-sm font-semibold tracking-wider text-apple-secondary uppercase select-none">
            Primary Constraints
          </h3>

          <div className="space-y-4 flex-1 justify-center flex flex-col">
            
            {/* Rent constraint item */}
            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <span className="text-apple-secondary flex items-center space-x-1">
                  <Landmark className="w-4 h-4 text-apple-secondary" />
                  <span>Rent (1BHK)</span>
                </span>
                <div className="flex items-center space-x-1.5">
                  <span className="font-mono font-semibold text-white">
                    {formatCurrency(featureVector.avgRentForBudgetBHK)}
                  </span>
                  {featureVector.rentIsEstimated ? (
                    <span className="text-[9px] px-1 bg-apple-border border border-apple-border rounded text-apple-secondary font-sans font-medium select-none">
                      ESTIMATED
                    </span>
                  ) : (
                    <span className="text-[9px] px-1 bg-brand-green/15 border border-brand-green/30 rounded text-brand-green font-sans font-semibold select-none">
                      REAL DATA
                    </span>
                  )}
                </div>
              </div>
              <div className="h-1.5 w-full bg-apple-border rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${rentAffordabilityBarColor}`}
                  style={{
                    width: `${Math.min(
                      100,
                      featureVector.avgRentForBudgetBHK > 0
                        ? (profile.rentBudget / featureVector.avgRentForBudgetBHK) * 100
                        : 0,
                    )}%`,
                  }}
                />
              </div>
            </div>

            {/* AQI constraint item */}
            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <span className="text-apple-secondary flex items-center space-x-1">
                  <Shield className="w-4 h-4 text-apple-secondary" />
                  <span>AQI (PM2.5)</span>
                </span>
                <div className="flex items-center space-x-1.5">
                  <span className="font-mono font-semibold text-white">
                    {featureVector.aqi}
                  </span>
                  {featureVector.aqiIsEstimated ? (
                    <span className="text-[9px] px-1 bg-apple-border border border-apple-border rounded text-apple-secondary font-sans font-medium select-none">
                      ESTIMATED
                    </span>
                  ) : (
                    <span className="text-[9px] px-1 bg-brand-green/15 border border-brand-green/30 rounded text-brand-green font-sans font-semibold select-none">
                      REAL DATA
                    </span>
                  )}
                </div>
              </div>
              <div className="h-1.5 w-full bg-apple-border rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${aqiBarColor}`}
                  style={{ width: `${Math.min(100, (featureVector.aqi / 200) * 100)}%` }}
                />
              </div>
            </div>

            {/* Traffic Index constraint item */}
            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <span className="text-apple-secondary flex items-center space-x-1">
                  <Navigation className="w-4 h-4 text-apple-secondary" />
                  <span>Traffic Index</span>
                </span>
                <div className="flex items-center space-x-1.5">
                  <span className="font-mono font-semibold text-white">
                    {featureVector.commuteMinutesToOffice > 45 ? 'Severe' : featureVector.commuteMinutesToOffice > 25 ? 'Moderate' : 'Light'}
                  </span>
                  <span className="text-[9px] px-1 bg-brand-green/15 border border-brand-green/30 rounded text-brand-green font-sans font-semibold select-none">
                    REAL DATA
                  </span>
                </div>
              </div>
              <div className="h-1.5 w-full bg-apple-border rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${commuteBarColor}`}
                  style={{ width: `${Math.min(100, (featureVector.commuteMinutesToOffice / 90) * 100)}%` }}
                />
              </div>
            </div>

          </div>
        </div>

      </div>

      {/* Feature Vector Section */}
      <div id="feature-vector-box" className="bg-apple-card border border-apple-border rounded-xl p-6 space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="text-sm font-semibold tracking-wider text-apple-secondary uppercase select-none">
            Feature Vector Analysis
          </h3>
          <span className="text-xs font-mono text-apple-secondary flex items-center space-x-1 select-none">
            <Sparkles className="w-3.5 h-3.5 text-brand-blue" />
            <span>Target Delta Computed</span>
          </span>
        </div>

        {/* Density Grid for horizontal progress bars */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-5 pt-2">
          
          {/* AQI bar row */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="text-white font-medium flex items-center space-x-2">
                <Shield className="w-4 h-4 text-apple-secondary" />
                <span>AQI</span>
              </span>
              <div className="flex items-center space-x-1.5">
                {featureVector.aqiIsEstimated && (
                  <span className="text-[9px] text-apple-secondary uppercase font-semibold tracking-wider scale-90">EST</span>
                )}
                <span className={`font-mono font-bold text-xs ${featureVector.aqi <= 50 ? 'text-brand-green' : featureVector.aqi <= 100 ? 'text-brand-orange' : 'text-brand-red'}`}>
                  {aqiLevel}
                </span>
              </div>
            </div>
            <div className="h-2 w-full bg-apple-border rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${aqiBarColor}`} style={{ width: `${Math.max(15, Math.min(100, 100 - (featureVector.aqi / 200) * 100))}%` }} />
            </div>
          </div>

          {/* Commute bar row */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="text-white font-medium flex items-center space-x-2">
                <Navigation className="w-4 h-4 text-apple-secondary" />
                <span>Commute</span>
              </span>
              <span className={`font-mono font-bold text-xs ${featureVector.commuteMinutesToOffice <= 25 ? 'text-brand-green' : featureVector.commuteMinutesToOffice <= 45 ? 'text-brand-orange' : 'text-brand-red'}`}>
                {commuteLevel}
              </span>
            </div>
            <div className="h-2 w-full bg-apple-border rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${commuteBarColor}`} style={{ width: `${Math.max(15, Math.min(100, 100 - (featureVector.commuteMinutesToOffice / 90) * 100))}%` }} />
            </div>
          </div>

          {/* Rent Affordability bar row */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="text-white font-medium flex items-center space-x-2">
                <Landmark className="w-4 h-4 text-apple-secondary" />
                <span>Rent Affordability</span>
              </span>
              <div className="flex items-center space-x-1.5">
                {featureVector.rentIsEstimated && (
                  <span className="text-[9px] text-apple-secondary uppercase font-semibold tracking-wider scale-90">EST</span>
                )}
                <span className={`font-mono font-bold text-xs ${rentAffordabilityLevel === 'High' ? 'text-brand-green' : 'text-brand-red'}`}>
                  {rentAffordabilityLevel}
                </span>
              </div>
            </div>
            <div className="h-2 w-full bg-apple-border rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${rentAffordabilityBarColor}`}
                style={{
                  width: `${Math.max(
                    15,
                    Math.min(
                      100,
                      featureVector.avgRentForBudgetBHK > 0
                        ? (profile.rentBudget / featureVector.avgRentForBudgetBHK) * 100
                        : 15,
                    ),
                  )}%`,
                }}
              />
            </div>
          </div>

          {/* Hospital Access row */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="text-white font-medium flex items-center space-x-2">
                <Heart className="w-4 h-4 text-apple-secondary" />
                <span>Hospital Access</span>
              </span>
              <span className={`font-mono font-bold text-xs ${hospitalLevel.textClass}`}>
                {hospitalLevel.label}
              </span>
            </div>
            <div className="h-2 w-full bg-apple-border rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${hospitalLevel.colorClass}`} style={{ width: `${featureVector.hospitalScore}%` }} />
            </div>
          </div>

          {/* School Access row */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="text-white font-medium flex items-center space-x-2">
                <BookOpen className="w-4 h-4 text-apple-secondary" />
                <span>School Access</span>
              </span>
              <span className={`font-mono font-bold text-xs ${schoolLevel.textClass}`}>
                {schoolLevel.label}
              </span>
            </div>
            <div className="h-2 w-full bg-apple-border rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${schoolLevel.colorClass}`} style={{ width: `${featureVector.schoolScore}%` }} />
            </div>
          </div>

          {/* Green Space row */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="text-white font-medium flex items-center space-x-2">
                <TreePine className="w-4 h-4 text-apple-secondary" />
                <span>Green Space</span>
              </span>
              <span className={`font-mono font-bold text-xs ${greenSpaceLevel.textClass}`}>
                {greenSpaceLevel.label}
              </span>
            </div>
            <div className="h-2 w-full bg-apple-border rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${greenSpaceLevel.colorClass}`} style={{ width: `${featureVector.parkScore}%` }} />
            </div>
          </div>

        </div>
      </div>

      {/* Footer provenance notice & Action Button */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 pt-2">
        <p className="text-[11px] text-apple-secondary italic flex items-center space-x-1.5 select-none">
          <ShieldAlert className="w-4 h-4 text-apple-secondary" />
          <span>ESTIMATED DATA Based on available models and user reports.</span>
        </p>

        <button
          id="btn-save-shortlist"
          onClick={() => setIsSaved(!isSaved)}
          className={`min-h-[44px] sm:min-w-[180px] flex items-center justify-center space-x-2 rounded-xl text-sm font-bold shadow-md cursor-pointer transition-all duration-300 ${
            isSaved
              ? 'bg-brand-green hover:bg-brand-green/90 active:bg-brand-green/85 text-white'
              : 'bg-brand-blue hover:bg-brand-blue/90 active:bg-brand-blue/85 text-white'
          }`}
        >
          {isSaved ? (
            <>
              <Check className="w-4 h-4 text-white" />
              <span>Saved to Shortlist!</span>
            </>
          ) : (
            <span>Save to Shortlist</span>
          )}
        </button>
      </div>

    </div>
  );
}
