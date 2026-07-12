import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CitizenModePage from './pages/CitizenModePage';

// Initialize React Query Client for state management and caching
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
      <BrowserRouter>
        <Routes>
          {/* Main Citizen Mode Dashboard Route */}
          <Route path="/citizen" element={<CitizenModePage />} />

          {/* Standard fallbacks / redirects */}
          <Route path="/" element={<Navigate to="/citizen" replace />} />
          <Route path="*" element={<Navigate to="/citizen" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
