"""Backtester unit tests on crafted price paths with known outcomes."""
import numpy as np
import pandas as pd
import pytest

from app.services.backtest import aggregate_metrics, simulate_symbol

ALWAYS_ENTER = {"min_swing_score": 0, "stop_loss_pct": 8, "take_profit_pct": 15,
                "max_hold_days": 20}


def frame(opens, highs, lows, closes, volume=1e6):
    n = len(closes)
    idx = pd.bdate_range("2025-01-01", periods=n, tz="UTC")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": [volume] * n}, index=idx)


def flat_then_path(days_flat, path):
    """`days_flat` boring days (warmup for indicators), then explicit
    (open, high, low, close) tuples."""
    opens = [100.0] * days_flat + [p[0] for p in path]
    highs = [101.0] * days_flat + [p[1] for p in path]
    lows = [99.0] * days_flat + [p[2] for p in path]
    closes = [100.0] * days_flat + [p[3] for p in path]
    return frame(opens, highs, lows, closes)


class TestSimulateSymbol:
    def test_target_exit(self):
        # Signal fires every day (score threshold 0); entry next open at 100,
        # then a day that tags +15% (115) without hitting -8% (92).
        df = flat_then_path(70, [(100, 101, 99, 100), (100, 120, 99, 118)])
        trades = simulate_symbol("TEST", df, ALWAYS_ENTER)
        assert trades, "expected at least one trade"
        # signals fire throughout the flat warmup, so earlier trades exit on
        # time — the final trade's window covers the surge bar
        t = trades[-1]
        assert t["exit_reason"] == "target"
        assert t["exit_price"] == pytest.approx(t["entry_price"] * 1.15)
        assert t["return_pct"] == pytest.approx(15.0, abs=0.01)

    def test_stop_checked_before_target_same_bar(self):
        # A single bar spans both -8% and +15%: conservative rule takes the stop.
        df = flat_then_path(70, [(100, 101, 99, 100), (100, 130, 85, 90)])
        trades = simulate_symbol("TEST", df, ALWAYS_ENTER)
        assert trades[-1]["exit_reason"] == "stop"
        assert trades[-1]["return_pct"] == pytest.approx(-8.0, abs=0.01)

    def test_time_exit_after_max_hold(self):
        path = [(100, 101, 99, 100)] * 25  # never hits stop or target
        df = flat_then_path(70, path)
        trades = simulate_symbol("TEST", df, {**ALWAYS_ENTER, "max_hold_days": 5})
        assert trades[0]["exit_reason"] == "time"
        assert trades[0]["hold_days"] == 5

    def test_no_signal_no_trades(self):
        df = flat_then_path(70, [(100, 101, 99, 100)] * 10)
        trades = simulate_symbol("TEST", df, {**ALWAYS_ENTER, "min_swing_score": 101})
        assert trades == []

    def test_no_overlapping_positions(self):
        df = flat_then_path(70, [(100, 101, 99, 100)] * 30)
        trades = simulate_symbol("TEST", df, {**ALWAYS_ENTER, "max_hold_days": 10})
        for prev, nxt in zip(trades, trades[1:]):
            assert nxt["entry_date"] > prev["exit_date"]


class TestAggregateMetrics:
    def _trade(self, ret, day, reason="target"):
        ts = pd.Timestamp(f"2025-02-{day:02d}", tz="UTC").to_pydatetime()
        return {"ticker": "T", "entry_date": ts, "exit_date": ts,
                "entry_price": 100.0, "exit_price": 100 + ret,
                "return_pct": ret, "exit_reason": reason, "hold_days": 5}

    def test_known_metrics(self):
        trades = [self._trade(10, 1), self._trade(-5, 2, "stop"),
                  self._trade(20, 3), self._trade(-10, 4, "stop")]
        m = aggregate_metrics(trades)
        assert m["total_trades"] == 4
        assert m["win_rate_pct"] == 50.0
        assert m["avg_return_pct"] == pytest.approx(3.75)
        assert m["best_trade_pct"] == 20.0
        assert m["worst_trade_pct"] == -10.0
        # equity: 1.10, 1.045, 1.254, 1.1286 → max dd is the final -10% leg
        assert m["max_drawdown_pct"] == pytest.approx(-10.0, abs=0.01)
        assert m["total_return_pct"] == pytest.approx(12.86, abs=0.01)
        assert m["exit_breakdown"] == {"target": 2, "stop": 2, "time": 0}
        assert len(m["equity_curve"]) == 4

    def test_empty_trades(self):
        m = aggregate_metrics([])
        assert m["total_trades"] == 0

    def test_sharpe_none_for_single_trade(self):
        m = aggregate_metrics([self._trade(5, 1)])
        assert m["sharpe_ratio"] is None
