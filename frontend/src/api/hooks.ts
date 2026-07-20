import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type {
  AIAnalysis,
  AlertEvent,
  AlertRule,
  Backtest,
  BacktestParams,
  Candle,
  ScannerResponse,
  SymbolDetail,
  User,
  WatchlistItem,
} from "./types";

export interface ScannerFilters {
  min_score?: number | "";
  sector?: string;
  min_rel_volume?: number | "";
  trend?: string;
  q?: string;
  sort?: string;
  order?: "asc" | "desc";
  limit?: number;
}

export const useScanner = (filters: ScannerFilters) =>
  useQuery({
    queryKey: ["scanner", filters],
    queryFn: () => api<ScannerResponse>("/scanner", { params: { ...filters } }),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  });

export const useSectors = () =>
  useQuery({ queryKey: ["sectors"], queryFn: () => api<string[]>("/scanner/sectors"), staleTime: 300_000 });

export const useIdeas = (minScore = 0) =>
  useQuery({
    queryKey: ["ideas", minScore],
    queryFn: () => api<ScannerResponse["rows"]>("/ideas", { params: { min_score: minScore } }),
    refetchInterval: 30_000,
  });

export const useSymbol = (ticker: string) =>
  useQuery({
    queryKey: ["symbol", ticker],
    queryFn: () => api<SymbolDetail>(`/symbols/${ticker}`),
    refetchInterval: 30_000,
  });

export const useCandles = (ticker: string) =>
  useQuery({
    queryKey: ["candles", ticker],
    queryFn: () => api<Candle[]>(`/symbols/${ticker}/candles`, { params: { limit: 300 } }),
  });

export const useAnalyze = (ticker: string) =>
  useMutation({
    mutationFn: (force: boolean) =>
      api<AIAnalysis>(`/ai/analyze/${ticker}`, { method: "POST", params: { force } }),
  });

export const useMe = (enabled: boolean) =>
  useQuery({ queryKey: ["me"], queryFn: () => api<User>("/auth/me"), enabled, retry: false });

// ── alerts ─────────────────────────────────────────────────────────────────
export const useAlertRules = () =>
  useQuery({ queryKey: ["alert-rules"], queryFn: () => api<AlertRule[]>("/alerts/rules") });

export const useAlertEvents = () =>
  useQuery({
    queryKey: ["alert-events"],
    queryFn: () => api<AlertEvent[]>("/alerts/events"),
    refetchInterval: 30_000,
  });

export function useToggleRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api<AlertRule>(`/alerts/rules/${id}`, { method: "PATCH", body: { enabled } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-rules"] }),
  });
}

export function useMarkAllSeen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/alerts/events/seen-all", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-events"] }),
  });
}

// ── watchlist ──────────────────────────────────────────────────────────────
export const useWatchlist = () =>
  useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api<WatchlistItem[]>("/watchlist"),
    refetchInterval: 30_000,
  });

export function useWatchlistMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["watchlist"] });
  return {
    add: useMutation({
      mutationFn: (body: { ticker: string; entry_price?: number; shares?: number; notes?: string }) =>
        api<WatchlistItem>("/watchlist", { method: "POST", body }),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/watchlist/${id}`, { method: "DELETE" }),
      onSuccess: invalidate,
    }),
  };
}

// ── backtests ──────────────────────────────────────────────────────────────
export const useBacktests = () =>
  useQuery({ queryKey: ["backtests"], queryFn: () => api<Backtest[]>("/backtests") });

export const useBacktest = (id: number | null) =>
  useQuery({
    queryKey: ["backtest", id],
    queryFn: () => api<Backtest>(`/backtests/${id}`),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data?.status === "done" ||
                                 query.state.data?.status === "error" ? false : 2_000),
  });

export function useCreateBacktest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; params: Partial<BacktestParams> }) =>
      api<Backtest>("/backtests", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtests"] }),
  });
}
