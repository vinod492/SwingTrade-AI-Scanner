import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import "./index.css";
import Layout from "./components/Layout";
import AlertsPage from "./pages/AlertsPage";
import BacktestPage from "./pages/BacktestPage";
import DashboardPage from "./pages/DashboardPage";
import ExplosiveRadarPage from "./pages/ExplosiveRadarPage";
import IdeaDetailPage from "./pages/IdeaDetailPage";
import IdeasPage from "./pages/IdeasPage";
import LoginPage from "./pages/LoginPage";
import ScannerPage from "./pages/ScannerPage";
import SettingsPage from "./pages/SettingsPage";
import WatchlistPage from "./pages/WatchlistPage";
import { AuthProvider } from "./state/auth";
import { LiveProvider } from "./state/live";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 10_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <LiveProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<ScannerPage />} />
                <Route path="ideas" element={<IdeasPage />} />
                <Route path="radar" element={<ExplosiveRadarPage />} />
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="idea/:ticker" element={<IdeaDetailPage />} />
                <Route path="alerts" element={<AlertsPage />} />
                <Route path="watchlist" element={<WatchlistPage />} />
                <Route path="backtest" element={<BacktestPage />} />
                <Route path="login" element={<LoginPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </LiveProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
