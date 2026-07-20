import numpy as np
import pandas as pd
import pytest

from app.services.indicators import (
    atr,
    bollinger,
    compute_indicators,
    ema,
    latest_snapshot,
    macd,
    pivot_levels,
    rsi,
)


def simple_df(closes, volumes=None):
    idx = pd.bdate_range("2024-01-01", periods=len(closes), tz="UTC")
    closes = pd.Series(list(closes), dtype=float, index=idx)
    return pd.DataFrame(
        {
            "open": closes.shift(1).fillna(closes.iloc[0]),
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": pd.Series(volumes if volumes is not None else [1e6] * len(closes),
                                index=idx, dtype=float),
        },
        index=idx,
    )


class TestEma:
    def test_matches_manual_recursion(self):
        s = pd.Series([10.0, 11.0, 12.0, 13.0])
        result = ema(s, span=3)  # alpha = 0.5
        expected = 10.0
        for i, x in enumerate(s):
            expected = x * 0.5 + expected * 0.5 if i else 10.0
        assert result.iloc[-1] == pytest.approx(expected)

    def test_constant_series_is_identity(self):
        s = pd.Series([50.0] * 30)
        assert (ema(s, 20) == 50.0).all()


class TestRsi:
    def test_all_gains_is_100(self):
        s = pd.Series(np.arange(1, 40, dtype=float))
        assert rsi(s).iloc[-1] == pytest.approx(100.0)

    def test_all_losses_near_0(self):
        s = pd.Series(np.arange(100, 40, -1, dtype=float))
        assert rsi(s).iloc[-1] == pytest.approx(0.0, abs=1e-6)

    def test_alternating_is_midrange(self):
        s = pd.Series([100 + (1 if i % 2 else -1) for i in range(60)], dtype=float)
        assert 35 < rsi(s).iloc[-1] < 65


class TestMacd:
    def test_positive_in_uptrend(self):
        s = pd.Series(np.linspace(50, 150, 80))
        line, signal = macd(s)
        assert line.iloc[-1] > 0
        assert signal.iloc[-1] > 0

    def test_crossover_after_reversal(self):
        s = pd.Series(list(np.linspace(100, 60, 40)) + list(np.linspace(60, 110, 40)))
        line, signal = macd(s)
        assert line.iloc[-1] > signal.iloc[-1]


class TestBollinger:
    def test_bands_bracket_price_on_flat_series(self):
        s = pd.Series([100.0] * 30)
        upper, lower = bollinger(s)
        assert upper.iloc[-1] == pytest.approx(100.0)
        assert lower.iloc[-1] == pytest.approx(100.0)

    def test_band_width_is_4_std(self):
        rng = np.random.default_rng(1)
        s = pd.Series(100 + rng.normal(0, 5, 200))
        upper, lower = bollinger(s, period=20)
        std = s.rolling(20).std(ddof=0).iloc[-1]
        assert (upper.iloc[-1] - lower.iloc[-1]) == pytest.approx(4 * std)


class TestAtr:
    def test_constant_range_converges_to_range(self):
        n = 300
        idx = pd.bdate_range("2024-01-01", periods=n, tz="UTC")
        df = pd.DataFrame(
            {"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 1e6},
            index=idx,
        )
        assert atr(df).iloc[-1] == pytest.approx(4.0, rel=1e-3)


class TestStructure:
    def test_pivot_levels_bracket_price(self):
        rng = np.random.default_rng(7)
        closes = pd.Series(100 + np.cumsum(rng.normal(0, 1, 150)))
        df = simple_df(closes)
        support, resistance = pivot_levels(df)
        price = df["close"].iloc[-1]
        assert support < price
        assert resistance > price

    def test_rel_volume_and_new_high(self):
        closes = list(np.linspace(90, 100, 59)) + [110.0]  # breakout day
        volumes = [1e6] * 59 + [4e6]
        snap = latest_snapshot(simple_df(closes, volumes))
        assert snap["rel_volume"] == pytest.approx(4.0, rel=0.01)
        assert snap["new_high_20"] is True
        assert snap["recent_vol_spike"] is True

    def test_compute_indicators_columns_and_alignment(self):
        df = simple_df(np.linspace(50, 80, 250))
        ind = compute_indicators(df)
        assert len(ind) == len(df)
        for col in ("ema20", "ema50", "ema200", "rsi", "macd", "atr", "rel_volume"):
            assert col in ind.columns
        assert ind["ema200"].notna().iloc[-1]
