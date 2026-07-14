import React, { Suspense, lazy } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/MainLayout';
import MapPage from './pages/MapPage';

// Route-level code splitting: keep Map eager (default landing), lazy the rest.
const EnforcementPage = lazy(() => import('./pages/EnforcementPage'));
const CopilotPage = lazy(() => import('./pages/CopilotPage'));
const NeighbourhoodsPage = lazy(() => import('./pages/NeighbourhoodsPage'));
const CitizenModePage = lazy(() => import('./pages/CitizenModePage'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: false,
      staleTime: 30_000,
      gcTime: 5 * 60_000,
    },
  },
});

function RouteFallback() {
  return (
    <div className="w-full h-full flex items-center justify-center bg-black">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-brand-blue/30 border-t-brand-blue animate-spin" />
        <span className="text-[10px] font-mono uppercase tracking-widest text-apple-secondary">
          Loading section…
        </span>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<MapPage />} />
            <Route path="map" element={<Navigate to="/" replace />} />
            <Route
              path="enforcement"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <EnforcementPage />
                </Suspense>
              }
            />
            <Route
              path="copilot"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <CopilotPage />
                </Suspense>
              }
            />
            <Route
              path="neighbourhoods"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <NeighbourhoodsPage />
                </Suspense>
              }
            />
            <Route
              path="citizen"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <CitizenModePage />
                </Suspense>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </QueryClientProvider>
  );
}
