import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/MainLayout';
import MapPage from './pages/MapPage';
import EnforcementPage from './pages/EnforcementPage';
import CopilotPage from './pages/CopilotPage';
import NeighbourhoodsPage from './pages/NeighbourhoodsPage';
import CitizenModePage from './pages/CitizenModePage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            {/* City Admin routes */}
            <Route index element={<MapPage />} />
            <Route path="map" element={<Navigate to="/" replace />} />
            <Route path="enforcement" element={<EnforcementPage />} />
            <Route path="copilot" element={<CopilotPage />} />
            <Route path="neighbourhoods" element={<NeighbourhoodsPage />} />

            {/* Citizen Mode — toggled via TopNav City Admin / Citizen */}
            <Route path="citizen" element={<CitizenModePage />} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </QueryClientProvider>
  );
}
