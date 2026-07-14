import React, { useState } from 'react';
import { Plus, Minus, MapPin } from 'lucide-react';
import type { CitizenProfile, HealthCondition, CitizenPriority } from '../../types/citizen';

interface ProfileBuilderFormProps {
  onSubmit: (profile: CitizenProfile) => void;
  isSubmitting?: boolean;
}

export default function ProfileBuilderForm({ onSubmit, isSubmitting = false }: ProfileBuilderFormProps) {
  // Rent budget: ₹15,000 to ₹80,000+
  const [rentBudget, setRentBudget] = useState<number>(45000);
  
  // Family size
  const [familySize, setFamilySize] = useState<number>(2);
  
  // Health conditions
  const [healthConditions, setHealthConditions] = useState<HealthCondition[]>(['none']);
  
  // Primary Destination (Office / School)
  const [officeLocation, setOfficeLocation] = useState<string>('Indiranagar');
  
  // Max commute minutes: 10m to 90m
  const [maxCommuteMinutes, setMaxCommuteMinutes] = useState<number>(45);
  
  // Priorities
  const [priorities, setPriorities] = useState<CitizenPriority[]>(['metro', 'low_aqi']);

  // Handle health chip selection
  const handleHealthClick = (condition: HealthCondition) => {
    if (condition === 'none') {
      setHealthConditions(['none']);
    } else {
      let updated: HealthCondition[] = healthConditions.filter((c) => c !== 'none');
      if (updated.includes(condition)) {
        updated = updated.filter((c) => c !== condition);
        if (updated.length === 0) {
          updated = ['none'];
        }
      } else {
        updated.push(condition);
      }
      setHealthConditions(updated);
    }
  };

  // Handle priority chip selection
  const handlePriorityClick = (priority: CitizenPriority) => {
    if (priorities.includes(priority)) {
      setPriorities(priorities.filter(p => p !== priority));
    } else {
      setPriorities([...priorities, priority]);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      rentBudget,
      familySize,
      healthConditions,
      officeLocation,
      maxCommuteMinutes,
      priorities
    });
  };

  // Helper to format currency
  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val);
  };

  return (
    <form id="profile-builder-form" onSubmit={handleSubmit} className="w-full space-y-6">
      
      {/* Rent budget card */}
      <div id="card-rent-budget" className="bg-apple-card border border-apple-border rounded-xl p-6 transition-all duration-200">
        <div className="flex justify-between items-center mb-4">
          <label htmlFor="rent-budget-slider" className="text-base font-medium text-white">
            Monthly Rent Budget
          </label>
          <span className="text-brand-blue font-mono font-bold text-xl select-none">
            {formatCurrency(rentBudget)}
          </span>
        </div>
        
        <input
          id="rent-budget-slider"
          type="range"
          min={15000}
          max={80000}
          step={1000}
          value={rentBudget}
          onChange={(e) => setRentBudget(Number(e.target.value))}
          className="w-full h-2 bg-apple-border rounded-lg appearance-none cursor-pointer accent-brand-blue"
          style={{ minHeight: '44px' }}
        />
        
        <div className="flex justify-between items-center text-xs text-apple-secondary font-mono mt-1 select-none">
          <span>₹15k</span>
          <span>₹80k+</span>
        </div>
      </div>

      {/* Family Size Card */}
      <div id="card-family-size" className="bg-apple-card border border-apple-border rounded-xl p-6 transition-all duration-200">
        <div className="flex justify-between items-center">
          <label className="text-base font-medium text-white">
            Family Size
          </label>
          
          <div className="flex items-center space-x-4 bg-black/40 border border-apple-border rounded-lg p-1">
            <button
              id="btn-family-decrement"
              type="button"
              onClick={() => setFamilySize(prev => Math.max(1, prev - 1))}
              className="w-11 h-11 flex items-center justify-center rounded-md bg-apple-card hover:bg-apple-border active:bg-apple-modal transition-colors text-white border border-apple-border"
              aria-label="Decrease family size"
            >
              <Minus className="w-5 h-5" />
            </button>
            <span id="text-family-size" className="w-12 text-center font-mono font-bold text-lg text-white select-none">
              {familySize}
            </span>
            <button
              id="btn-family-increment"
              type="button"
              onClick={() => setFamilySize(prev => Math.min(10, prev + 1))}
              className="w-11 h-11 flex items-center justify-center rounded-md bg-apple-card hover:bg-apple-border active:bg-apple-modal transition-colors text-white border border-apple-border"
              aria-label="Increase family size"
            >
              <Plus className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Health & Demographics Card */}
      <div id="card-health" className="bg-apple-card border border-apple-border rounded-xl p-6 transition-all duration-200">
        <h3 className="text-base font-medium text-white mb-3">
          Health & Demographics
        </h3>
        
        <div className="flex flex-wrap gap-3">
          {[
            { id: 'none', label: 'None' },
            { id: 'respiratory', label: 'Asthma / Respiratory' },
            { id: 'elderly', label: 'Elderly in household' },
            { id: 'young_children', label: 'Young children' }
          ].map((item) => {
            const isSelected = healthConditions.includes(item.id as HealthCondition);
            return (
              <button
                key={item.id}
                id={`chip-health-${item.id}`}
                type="button"
                onClick={() => handleHealthClick(item.id as HealthCondition)}
                className={`min-h-[44px] px-5 py-2 rounded-full text-sm font-medium border transition-all duration-200 ${
                  isSelected
                    ? 'bg-brand-blue/15 border-brand-blue text-brand-blue'
                    : 'bg-black/30 border-apple-border text-apple-secondary hover:border-apple-secondary hover:text-white'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Primary Destination Card */}
      <div id="card-destination" className="bg-apple-card border border-apple-border rounded-xl p-6 transition-all duration-200">
        <label htmlFor="input-destination" className="block text-base font-medium text-white mb-3">
          Primary Destination
        </label>
        
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-apple-secondary">
            <MapPin className="w-5 h-5" />
          </div>
          <input
            id="input-destination"
            type="text"
            required
            value={officeLocation}
            onChange={(e) => setOfficeLocation(e.target.value)}
            placeholder="Office or School Location"
            className="w-full min-h-[44px] pl-11 pr-4 py-2.5 bg-black/40 border border-apple-border rounded-lg text-white placeholder-apple-secondary focus:outline-none focus:border-brand-blue focus:ring-1 focus:ring-brand-blue transition-all"
          />
        </div>
      </div>

      {/* Max Commute Card */}
      <div id="card-commute" className="bg-apple-card border border-apple-border rounded-xl p-6 transition-all duration-200">
        <div className="flex justify-between items-center mb-4">
          <label htmlFor="commute-slider" className="text-base font-medium text-white">
            Max Commute
          </label>
          <span className="text-brand-blue font-mono font-bold text-xl select-none">
            {maxCommuteMinutes} mins
          </span>
        </div>
        
        <input
          id="commute-slider"
          type="range"
          min={10}
          max={90}
          step={5}
          value={maxCommuteMinutes}
          onChange={(e) => setMaxCommuteMinutes(Number(e.target.value))}
          className="w-full h-2 bg-apple-border rounded-lg appearance-none cursor-pointer accent-brand-blue"
          style={{ minHeight: '44px' }}
        />
        
        <div className="flex justify-between items-center text-xs text-apple-secondary font-mono mt-1 select-none">
          <span>10m</span>
          <span>90m</span>
        </div>
      </div>

      {/* Priorities Card */}
      <div id="card-priorities" className="bg-apple-card border border-apple-border rounded-xl p-6 transition-all duration-200">
        <h3 className="text-base font-medium text-white mb-3">
          What matters most to you?
        </h3>
        
        <div className="flex flex-wrap gap-3">
          {[
            { id: 'metro', label: 'Metro access' },
            { id: 'schools', label: 'Good schools nearby' },
            { id: 'hospitals', label: 'Hospital access' },
            { id: 'parks', label: 'Parks & green space' },
            { id: 'low_aqi', label: 'Low air pollution' },
            { id: 'low_noise', label: 'Low noise' }
          ].map((item) => {
            const isSelected = priorities.includes(item.id as CitizenPriority);
            return (
              <button
                key={item.id}
                id={`chip-priority-${item.id}`}
                type="button"
                onClick={() => handlePriorityClick(item.id as CitizenPriority)}
                className={`min-h-[44px] px-5 py-2 rounded-full text-sm font-medium border transition-all duration-200 ${
                  isSelected
                    ? 'bg-brand-blue/15 border-brand-blue text-brand-blue'
                    : 'bg-black/30 border-apple-border text-apple-secondary hover:border-apple-secondary hover:text-white'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Submit Button */}
      <button
        id="btn-find-neighbourhood"
        type="submit"
        disabled={isSubmitting}
        className="w-full h-[52px] flex items-center justify-center rounded-xl bg-brand-blue hover:bg-brand-blue/90 active:bg-brand-blue/85 disabled:bg-apple-border disabled:text-apple-secondary font-bold text-white shadow-lg shadow-brand-blue/10 cursor-pointer transition-all duration-200"
      >
        {isSubmitting ? 'Searching Optimal Matches...' : 'Find My Neighbourhood'}
      </button>

    </form>
  );
}
