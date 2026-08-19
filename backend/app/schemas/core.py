"""Pydantic request/response models for the public API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ── Auth ────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    email: str
    created_at: datetime


# ── Scanner / ideas ─────────────────────────────────────────────────────────
class ScannerRow(BaseModel):
    rank: int
    symbol_id: int
    ticker: str
    name: str
    sector: str
    price: float
    day_change_pct: float | None = None
    volume: float | None = None
    rel_volume: float | None = None
    atr_pct: float | None = None
    rsi: float | None = None
    trend: str
    swing_score: float
    momentum_pts: float
    volatility_pts: float
    volume_pts: float
    breakout_pts: float
    options_pts: float
    catalyst_pts: float
    setup_label: str
    reasons: list[str] = []
    entry: float | None = None
    entry_high: float | None = None
    stop: float | None = None
    target: float | None = None
    risk_pct: float | None = None
    reward_pct: float | None = None
    rr_ratio: float | None = None
    support: float | None = None
    resistance: float | None = None
    unusual_options: bool = False
    updated_at: str | datetime | None = None


class ScannerResponse(BaseModel):
    total: int
    rows: list[ScannerRow]
    generated_at: str | datetime | None = None


class CandleOut(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None


class SymbolDetail(BaseModel):
    ticker: str
    name: str
    sector: str
    market_cap: float | None
    float_shares: float | None
    row: ScannerRow | None = None
    catalysts: list[dict] = []


# ── Catalyst Radar (explosive-move potential) ───────────────────────────────
class ExplosiveRow(BaseModel):
    rank: int
    symbol_id: int
    ticker: str
    name: str
    sector: str
    explosive_score: float
    catalyst_pts: float
    squeeze_pts: float
    float_pts: float
    iv_pts: float
    volume_pts: float
    catalyst_kind: str
    catalyst_headline: str
    catalyst_date: str | None = None
    days_to_catalyst: int | None = None
    short_pct_float: float | None = None
    days_to_cover: float | None = None
    iv_rank: float | None = None
    float_shares: float | None = None
    rel_volume: float | None = None
    reasons: list[str] = []


class ExplosiveResponse(BaseModel):
    total: int
    rows: list[ExplosiveRow]


# ── AI ──────────────────────────────────────────────────────────────────────
class AIAnalysis(BaseModel):
    ticker: str
    why_moving: str
    bull_case: str
    bear_case: str
    technical: str
    trade_plan: str
    risk_factors: str
    generated_at: datetime
    provider: str
    cached: bool = False


# ── Alerts ──────────────────────────────────────────────────────────────────
class AlertRuleOut(BaseModel):
    id: int
    rule_type: str
    params: dict
    enabled: bool


class AlertRuleUpdate(BaseModel):
    enabled: bool | None = None
    params: dict | None = None


class AlertEventOut(BaseModel):
    id: int
    ticker: str
    rule_type: str
    message: str
    triggered_at: datetime
    seen: bool


# ── Watchlist ───────────────────────────────────────────────────────────────
class WatchlistItemIn(BaseModel):
    ticker: str
    entry_price: float | None = None
    shares: float | None = None
    notes: str = ""


class WatchlistItemUpdate(BaseModel):
    entry_price: float | None = None
    shares: float | None = None
    notes: str | None = None


class WatchlistItemOut(BaseModel):
    id: int
    ticker: str
    name: str
    entry_price: float | None
    shares: float | None
    notes: str
    price: float | None = None
    day_change_pct: float | None = None
    pl_amount: float | None = None
    pl_pct: float | None = None
    swing_score: float | None = None
    added_at: datetime


# ── Backtests ───────────────────────────────────────────────────────────────
class BacktestParams(BaseModel):
    min_swing_score: float = 80
    min_rel_volume: float = 0
    price_above_ema: int | None = None  # 20 | 50 | 200
    rsi_min: float | None = None
    rsi_max: float | None = None
    stop_loss_pct: float = 8.0
    take_profit_pct: float = 15.0
    max_hold_days: int = 20
    lookback_days: int = 365


class BacktestCreate(BaseModel):
    name: str = "My strategy"
    params: BacktestParams = BacktestParams()


class BacktestTradeOut(BaseModel):
    ticker: str
    entry_date: datetime
    entry_price: float
    exit_date: datetime | None
    exit_price: float | None
    return_pct: float | None
    exit_reason: str


class BacktestOut(BaseModel):
    id: int
    name: str
    status: str
    error: str = ""
    params: dict
    results: dict | None = None
    created_at: datetime
    trades: list[BacktestTradeOut] = []


# ── Settings ────────────────────────────────────────────────────────────────
class ApiKeyIn(BaseModel):
    provider: str  # polygon | alpaca | openai
    key: str
    secret: str = ""


class ApiKeyStatus(BaseModel):
    provider: str
    configured: bool
    hint: str = ""  # e.g. "gS3p…QrI"
