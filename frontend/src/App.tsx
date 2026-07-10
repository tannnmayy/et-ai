import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AppHeader from "./components/AppHeader";
import HomePage from "./pages/HomePage";
import EnforcementPage from "./pages/EnforcementPage";
import CopilotPage from "./pages/CopilotPage";
import NeighbourhoodsPage from "./pages/NeighbourhoodsPage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppHeader />
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/enforcement" element={<EnforcementPage />} />
          <Route path="/copilot" element={<CopilotPage />} />
          <Route path="/neighbourhoods" element={<NeighbourhoodsPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
