import React from 'react';
import { Factory, Trash2, Car, Construction, AlertTriangle } from 'lucide-react';

interface SourceIconProps {
  sourceType: string;
  size?: number;
}

export default function SourceIcon({ sourceType, size = 14 }: SourceIconProps) {
  const normType = sourceType.toLowerCase();
  
  if (normType.includes('heavy ind') || normType.includes('industrial') || normType.includes('emission')) {
    return <Factory size={size} className="text-brand-orange" />;
  }
  if (normType.includes('waste') || normType.includes('combustion') || normType.includes('burning')) {
    return <Trash2 size={size} className="text-brand-red" />;
  }
  if (normType.includes('traffic') || normType.includes('vehicular') || normType.includes('car')) {
    return <Car size={size} className="text-brand-blue" />;
  }
  if (normType.includes('construction') || normType.includes('dust')) {
    return <Construction size={size} className="text-brand-orange" />;
  }
  
  return <AlertTriangle size={size} className="text-brand-orange" />;
}
