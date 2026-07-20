from datetime import datetime, timedelta, timezone

import pytest

from app.providers.base import CatalystInfo, OptionsInfo
from app.services.scoring import classify_trend, score_symbol

NOW = datetime(2026, 7, 17, 15, 0, tzinfo=timezone.utc)


def perfect_indicators(price=110.0):
    """Indicator dict that satisfies every price/volume criterion."""
    return {
        "ema20": price * 0.95, "ema50": price * 0.90, "ema200": price * 0.80,
        "rsi": 60.0, "macd": 2.0, "macd_signal": 1.0,
        "atr": 3.0, "atr_avg": 2.0, "atr_pct": 2.7,
        "avg_volume": 1e6, "rel_volume": 2.5, "range_expansion": 1.5,
        "recent_vol_spike": True, "new_high_20": True,
        "support": price * 0.92, "resistance": price * 1.01,
    }


def bullish_options():
    return OptionsInfo(ticker="X", call_volume=3e6, avg_call_volume=1e6,
                       put_call_ratio=0.5, oi_change_pct=5.0, iv=0.5,
                       iv_change=0.05, unusual=True)


def bullish_catalysts():
    return [
        CatalystInfo(ticker="X", kind="earnings", event_date=NOW + timedelta(days=5)),
        CatalystInfo(ticker="X", kind="upgrade", sentiment=0.7),
        CatalystInfo(ticker="X", kind="news", sentiment=0.8),
    ]


class TestScoreWeights:
    def test_perfect_setup_scores_100(self):
        bd = score_symbol(perfect_indicators(), price=110.0,
                          options=bullish_options(), catalysts=bullish_catalysts(),
                          now=NOW)
        assert bd.momentum == 20
        assert bd.volatility == 20
        assert bd.volume == 15
        assert bd.breakout == 20
        assert bd.options == 15
        assert bd.catalyst == 10
        assert bd.total == 100

    def test_empty_setup_scores_0(self):
        ind = {
            "ema20": 120.0, "ema50": 130.0, "ema200": 140.0, "rsi": 25.0,
            "macd": -1.0, "macd_signal": 0.5, "atr": 1.0, "atr_avg": 2.0,
            "rel_volume": 0.5, "range_expansion": 0.8, "recent_vol_spike": False,
            "new_high_20": False, "support": 90.0, "resistance": 150.0,
        }
        bd = score_symbol(ind, price=100.0, options=None, catalysts=None, now=NOW)
        assert bd.total == 0

    def test_volume_points_scale_linearly(self):
        ind = perfect_indicators()
        ind["recent_vol_spike"] = False
        ind["rel_volume"] = 1.5  # halfway between 1x and 2x
        bd = score_symbol(ind, price=110.0, now=NOW)
        assert bd.volume == pytest.approx(5.0)

    def test_rsi_outside_power_zone_loses_5(self):
        ind = perfect_indicators()
        ind["rsi"] = 80.0
        bd = score_symbol(ind, price=110.0, now=NOW)
        assert bd.momentum == 15

    def test_earnings_outside_window_not_counted(self):
        cats = [CatalystInfo(ticker="X", kind="earnings",
                             event_date=NOW + timedelta(days=45))]
        bd = score_symbol(perfect_indicators(), price=110.0, catalysts=cats, now=NOW)
        assert bd.catalyst == 0

    def test_catalyst_capped_at_10(self):
        cats = bullish_catalysts() * 3
        bd = score_symbol(perfect_indicators(), price=110.0, catalysts=cats, now=NOW)
        assert bd.catalyst == 10


class TestTrendAndSetup:
    def test_strong_uptrend(self):
        assert classify_trend(110, 105, 100, 90) == "Strong Uptrend"

    def test_downtrend(self):
        assert classify_trend(80, 85, 90, 100) == "Downtrend"

    def test_sideways(self):
        assert classify_trend(100, 101, 99, 100) == "Sideways"

    def test_breakout_setup_label(self):
        bd = score_symbol(perfect_indicators(), price=110.0, now=NOW)
        assert bd.setup_label == "Bullish continuation breakout"
