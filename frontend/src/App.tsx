import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AppHeader from "./components/AppHeader";
import HomePage from "./pages/HomePage";
import EnforcementPage from "./pages/EnforcementPage";
import ComingSoonPage from "./pages/ComingSoonPage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppHeader />
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/enforcement" element={<EnforcementPage />} />
          <Route path="/copilot" element={<ComingSoonPage title="Copilot" />} />
          <Route path="/neighbourhoods" element={<ComingSoonPage title="Neighbourhoods" />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
