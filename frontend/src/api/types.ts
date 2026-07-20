export interface ScannerRow {
  rank: number;
  symbol_id: number;
  ticker: string;
  name: string;
  sector: string;
  price: number;
  day_change_pct: number | null;
  volume: number | null;
  rel_volume: number | null;
  atr_pct: number | null;
  rsi: number | null;
  trend: string;
  swing_score: number;
  momentum_pts: number;
  volatility_pts: number;
  volume_pts: number;
  breakout_pts: number;
  options_pts: number;
  catalyst_pts: number;
  setup_label: string;
  reasons: string[];
  entry: number | null;
  entry_high: number | null;
  stop: number | null;
  target: number | null;
  risk_pct: number | null;
  reward_pct: number | null;
  rr_ratio: number | null;
  support: number | null;
  resistance: number | null;
  unusual_options: boolean;
  updated_at: string | null;
}

export interface ScannerResponse {
  total: number;
  rows: ScannerRow[];
  generated_at: string | null;
}

export interface Candle {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
}

export interface SymbolDetail {
  ticker: string;
  name: string;
  sector: string;
  market_cap: number | null;
  float_shares: number | null;
  row: ScannerRow | null;
  catalysts: { kind: string; headline: string; sentiment: number | null; event_date: string | null }[];
}

export interface AIAnalysis {
  ticker: string;
  why_moving: string;
  bull_case: string;
  bear_case: string;
  technical: string;
  trade_plan: string;
  risk_factors: string;
  generated_at: string;
  provider: string;
  cached: boolean;
}

export interface AlertRule {
  id: number;
  rule_type: string;
  params: Record<string, unknown>;
  enabled: boolean;
}

export interface AlertEvent {
  id: number;
  ticker: string;
  rule_type: string;
  message: string;
  triggered_at: string;
  seen: boolean;
}

export interface WatchlistItem {
  id: number;
  ticker: string;
  name: string;
  entry_price: number | null;
  shares: number | null;
  notes: string;
  price: number | null;
  day_change_pct: number | null;
  pl_amount: number | null;
  pl_pct: number | null;
  swing_score: number | null;
  added_at: string;
}

export interface BacktestParams {
  min_swing_score: number;
  min_rel_volume: number;
  price_above_ema: number | null;
  rsi_min: number | null;
  rsi_max: number | null;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_hold_days: number;
  lookback_days: number;
}

export interface BacktestTrade {
  ticker: string;
  entry_date: string;
  entry_price: number;
  exit_date: string | null;
  exit_price: number | null;
  return_pct: number | null;
  exit_reason: string;
}

export interface BacktestResults {
  total_trades: number;
  wins?: number;
  losses?: number;
  win_rate_pct?: number;
  avg_return_pct?: number;
  median_return_pct?: number;
  best_trade_pct?: number;
  worst_trade_pct?: number;
  max_drawdown_pct?: number;
  sharpe_ratio?: number | null;
  avg_hold_days?: number;
  total_return_pct?: number;
  exit_breakdown?: Record<string, number>;
  equity_curve?: { date: string; equity: number }[];
  message?: string;
}

export interface Backtest {
  id: number;
  name: string;
  status: string;
  error: string;
  params: BacktestParams;
  results: BacktestResults | null;
  created_at: string;
  trades: BacktestTrade[];
}

export interface ApiKeyStatus {
  provider: string;
  configured: boolean;
  hint: string;
}

export interface User {
  id: number;
  email: string;
  created_at: string;
}

export type WsEvent =
  | { type: "scanner"; payload: { count: number; top: ScannerRow[] } }
  | { type: "alert"; payload: { ticker: string; rule_type: string; message: string; user_id: number; triggered_at: string } }
  | { type: "backtest_done"; payload: { id: number; name: string; user_id: number } };
