import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * Citizens tab entry — immediately opens Citizen Mode.
 * Kept as a route alias so old /neighbourhoods links still work.
 */
export default function NeighbourhoodsPage() {
  const navigate = useNavigate();
  useEffect(() => {
    navigate('/citizen', { replace: true });
  }, [navigate]);

  return (
    <div className="w-full h-full bg-black flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-brand-blue border-t-transparent rounded-full animate-spin" />
    </div>
  );
}
