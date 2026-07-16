import React, { Suspense, lazy } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/MainLayout';
import MapPage from './pages/MapPage';
import LandingPage from './pages/LandingPage';
import { SessionProvider, useSession, defaultPathForRole } from './context/SessionContext';
import { MapCopilotProvider } from './context/MapCopilotContext';

const EnforcementPage = lazy(() => import('./pages/EnforcementPage'));
const CopilotPage = lazy(() => import('./pages/CopilotPage'));
const NeighbourhoodsPage = lazy(() => import('./pages/NeighbourhoodsPage'));
const CitizenModePage = lazy(() => import('./pages/CitizenModePage'));
const InsightsPage = lazy(() => import('./pages/InsightsPage'));
const DispatchPage = lazy(() => import('./pages/DispatchPage'));

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

/** Always allow the landing route (change-role / first entry). */
function WelcomeGate() {
  return <LandingPage />;
}

function RootRedirect() {
  const { isAuthenticated, session } = useSession();
  if (!isAuthenticated) {
    return <Navigate to="/welcome" replace />;
  }
  if (session) {
    return <Navigate to={defaultPathForRole(session.role)} replace />;
  }
  return <Navigate to="/welcome" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <MapCopilotProvider>
        <HashRouter>
          <Routes>
            <Route path="/welcome" element={<WelcomeGate />} />
            <Route path="/entry" element={<Navigate to="/welcome" replace />} />

            <Route path="/" element={<MainLayout />}>
              <Route
                index
                element={<MapPage />}
              />
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
                path="dispatch"
                element={
                  <Suspense fallback={<RouteFallback />}>
                    <DispatchPage />
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
                path="insights"
                element={
                  <Suspense fallback={<RouteFallback />}>
                    <InsightsPage />
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
              <Route path="*" element={<RootRedirect />} />
            </Route>
          </Routes>
        </HashRouter>
        </MapCopilotProvider>
      </SessionProvider>
    </QueryClientProvider>
  );
}
