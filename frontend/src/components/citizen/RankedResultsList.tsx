import React from 'react';
import { AlertTriangle, Train, Home, Heart, Compass, ArrowLeft, Info, MapPin } from 'lucide-react';
import type { NeighbourhoodMatch, CitizenProfile } from '../../types/citizen';

interface RankedResultsListProps {
  matches: NeighbourhoodMatch[];
  profile: CitizenProfile;
  onSelectNeighbourhood: (match: NeighbourhoodMatch) => void;
  onBackToProfile: () => void;
}

export default function RankedResultsList({
  matches,
  profile,
  onSelectNeighbourhood,
  onBackToProfile
}: RankedResultsListProps) {

  // Helper to format currency
  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val);
  };

  // Helper to get AQI text and styling
  const getAQIStyle = (aqi: number | null | undefined) => {
    const v = Number(aqi);
    if (!Number.isFinite(v) || v <= 50) {
      return {
        text: 'Good',
        bgColor: 'bg-brand-green/10',
        textColor: 'text-brand-green',
        borderColor: 'border-brand-green/30',
      };
    }
    if (v <= 100) {
      return {
        text: 'Moderate',
        bgColor: 'bg-brand-orange/10',
        textColor: 'text-brand-orange',
        borderColor: 'border-brand-orange/30',
      };
    }
    return {
      text: 'Unhealthy',
      bgColor: 'bg-brand-red/10',
      textColor: 'text-brand-red',
      borderColor: 'border-brand-red/30',
    };
  };

  // Handle empty match states or very few results
  if (!matches || matches.length === 0) {
    return (
      <div id="empty-matches-state" className="flex flex-col items-center justify-center p-8 bg-apple-card border border-apple-border rounded-2xl text-center space-y-6">
        <div className="w-16 h-16 rounded-full bg-brand-orange/10 flex items-center justify-center text-brand-orange">
          <AlertTriangle className="w-8 h-8" />
        </div>
        <div className="space-y-2 max-w-md">
          <h3 className="text-xl font-semibold text-white">No Matching Neighbourhoods Found</h3>
          <p className="text-apple-secondary text-sm leading-relaxed">
            We couldn't find any locations that meet your current requirements. 
            Try relaxing your rent budget or allowing a slightly longer commute time to see optimal matches.
          </p>
        </div>
        <button
          id="btn-relax-filters"
          onClick={onBackToProfile}
          className="min-h-[44px] px-6 py-2.5 bg-brand-blue hover:bg-brand-blue/95 active:bg-brand-blue/90 text-white font-medium rounded-xl transition-all"
        >
          Relax My Filters & Re-try
        </button>
      </div>
    );
  }

  return (
    <div id="ranked-results-list" className="space-y-6">
      
      {/* Header section with back button and general metadata */}
      <div className="flex justify-between items-center pb-2">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Ranked Results</h2>
          <p className="text-apple-secondary text-sm mt-1">
            Top algorithmic matches for your profile in {profile.officeLocation || 'Bengaluru'}.
          </p>
        </div>
        
        {/* Estimates indicator */}
        <div className="flex items-center space-x-1 px-3 py-1 bg-apple-border/40 border border-apple-border rounded-lg text-[10px] font-semibold tracking-wider text-apple-secondary select-none">
          <Info className="w-3.5 h-3.5 text-apple-secondary" />
          <span>ESTIMATES INCLUDED</span>
        </div>
      </div>

      {/* Profile summary banner */}
      <div className="bg-apple-card/60 border border-apple-border rounded-xl p-4 flex flex-wrap gap-4 items-center justify-between text-xs text-apple-secondary">
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          <span>Budget: <strong className="text-white font-mono">{formatCurrency(profile.rentBudget)}</strong></span>
          <span>Commute Limit: <strong className="text-white font-mono">{profile.maxCommuteMinutes} mins</strong></span>
          <span>Family: <strong className="text-white font-mono">{profile.familySize} persons</strong></span>
        </div>
        <button
          id="btn-edit-profile-top"
          onClick={onBackToProfile}
          className="flex items-center space-x-1.5 text-brand-blue hover:text-brand-blue/80 active:text-brand-blue/70 font-semibold min-h-[44px] px-3 rounded-lg hover:bg-apple-border/30 transition-all cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Edit Profile</span>
        </button>
      </div>

      {/* Main ranked cards list */}
      <div className="space-y-4">
        {matches.map((match, idx) => {
          const fv = match.featureVector;
          if (!fv) return null;
          const aqiStyle = getAQIStyle(fv.aqi);
          const isOverBudget = Number(fv.avgRentForBudgetBHK) > profile.rentBudget;
          const isOverCommute = Number(fv.commuteMinutesToOffice) > profile.maxCommuteMinutes;
          const reasons = Array.isArray(match.reasons) ? match.reasons : [];

          return (
            <div
              key={`${match.name}-${match.rank}-${idx}`}
              id={`ranked-match-${idx + 1}`}
              onClick={() => onSelectNeighbourhood(match)}
              className="group ui-glass ui-glass-subtle hover:border-brand-blue/40 rounded-2xl p-6 cursor-pointer transition-colors duration-200 relative overflow-hidden active:scale-[0.99] select-none"
            >
              
              {/* Header inside card: Rank and Match Score */}
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-center space-x-3">
                  <span className="text-brand-blue font-mono font-bold text-2xl">
                    #{String(idx + 1).padStart(2, '0')}
                  </span>
                  <h3 className="text-lg font-bold text-white group-hover:text-brand-blue transition-colors duration-200">
                    {match.name}
                  </h3>
                </div>
                
                <div className="text-right">
                  <span className="text-brand-green font-mono font-bold text-xl block">
                    {match.matchScorePercent}%
                  </span>
                  <span className="text-[10px] font-semibold text-apple-secondary tracking-wider block">
                    MATCH
                  </span>
                </div>
              </div>

              {/* Reasons list (reasons bullet items with border accent) */}
              <ul className="space-y-2.5 mb-5 pl-1">
                {reasons.map((reason, rIdx) => {
                  // If it's a warning reason (rent exceeds, commute longer, etc.)
                  const lower = reason.toLowerCase();
                  const isRentWarning =
                    lower.includes('exceeds') || (isOverBudget && lower.includes('budget'));
                  const isCommuteWarning =
                    lower.includes('longer') || (isOverCommute && lower.includes('commute'));
                  const isWarning = isRentWarning || isCommuteWarning;

                  return (
                    <li
                      key={rIdx}
                      className={`flex items-start text-xs leading-relaxed py-0.5 px-2 border-l-2 ${
                        isWarning
                          ? 'border-brand-orange text-brand-orange/90 bg-brand-orange/5'
                          : 'border-brand-blue text-apple-secondary bg-brand-blue/5'
                      } rounded-r`}
                    >
                      {isWarning ? (
                        <AlertTriangle className="w-3.5 h-3.5 mr-2 mt-0.5 text-brand-orange shrink-0" />
                      ) : (
                        <span className="w-1.5 h-1.5 rounded-full bg-brand-blue/80 mr-2.5 mt-2 shrink-0" />
                      )}
                      <span>{reason}</span>
                    </li>
                  );
                })}
              </ul>

              {/* Grid of stats at bottom of the card */}
              <div className="grid grid-cols-3 gap-2 pt-4 border-t border-apple-border/50 text-xs">
                
                {/* AQI Score */}
                <div className="flex flex-col space-y-1">
                  <span className="text-[10px] font-semibold tracking-wider text-apple-secondary select-none">
                    AQI (PM2.5)
                  </span>
                  <div className="flex items-center space-x-2">
                    <span className={`px-2 py-0.5 rounded font-mono font-bold ${aqiStyle.textColor} ${aqiStyle.bgColor} border ${aqiStyle.borderColor}`}>
                      {fv.aqi}
                    </span>
                    {fv.aqiIsEstimated && (
                      <span className="text-[9px] px-1 bg-apple-border border border-apple-border rounded text-apple-secondary select-none font-sans font-medium">
                        EST
                      </span>
                    )}
                  </div>
                </div>

                {/* Avg Rent */}
                <div className="flex flex-col space-y-1">
                  <span className="text-[10px] font-semibold tracking-wider text-apple-secondary select-none">
                    AVG RENT
                  </span>
                  <div className="flex items-center space-x-1">
                    <span className="text-white font-mono font-bold">
                      {formatCurrency(fv.avgRentForBudgetBHK)}
                    </span>
                    {fv.rentIsEstimated && (
                      <span className="text-[9px] px-1 bg-apple-border border border-apple-border rounded text-apple-secondary select-none font-sans font-medium">
                        EST
                      </span>
                    )}
                  </div>
                </div>

                {/* Commute */}
                <div className="flex flex-col space-y-1 text-right">
                  <span className="text-[10px] font-semibold tracking-wider text-apple-secondary select-none">
                    COMMUTE TIME
                  </span>
                  <span className="text-white font-mono font-bold">
                    {fv.commuteMinutesToOffice}m
                  </span>
                </div>

              </div>

            </div>
          );
        })}
      </div>

      {/* Suggestion block to encourage tuning filters */}
      <div className="p-4 bg-apple-card border border-apple-border rounded-xl text-xs text-apple-secondary flex items-start space-x-3">
        <Info className="w-5 h-5 text-brand-blue shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold text-white mb-1">Environmental & Spatial Intelligence</p>
          <p className="leading-relaxed">
            Our civic database computes match percentages based on a real-time blend of Air Quality Index (AQI), 
            average listing rents, commute profiles, and municipal spatial proximity indexes.
          </p>
        </div>
      </div>

    </div>
  );
}
