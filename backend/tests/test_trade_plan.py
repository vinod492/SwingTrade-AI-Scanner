import pytest

from app.services.trade_plan import build_trade_plan


class TestTradePlan:
    def test_orders_entry_stop_target(self):
        plan = build_trade_plan(price=100.0, atr=2.0, support=95.0, resistance=110.0)
        assert plan.stop < plan.entry < plan.target
        assert plan.entry_high > plan.entry

    def test_breakout_entry_uses_resistance_trigger(self):
        plan = build_trade_plan(price=100.0, atr=2.0, support=95.0, resistance=101.0)
        assert plan.entry == pytest.approx(101.0 * 1.001, abs=0.01)

    def test_atr_stop_when_no_structure(self):
        plan = build_trade_plan(price=100.0, atr=2.0, support=None, resistance=None)
        assert plan.entry == 100.0
        assert plan.stop == pytest.approx(97.0, abs=0.01)  # 1.5 x ATR

    def test_risk_capped_at_15_pct(self):
        plan = build_trade_plan(price=100.0, atr=20.0, support=40.0, resistance=None)
        assert plan.risk_pct <= 15.0 + 1e-6

    def test_reward_at_least_2x_risk(self):
        for atr in (0.5, 2.0, 5.0):
            plan = build_trade_plan(price=100.0, atr=atr, support=96.0, resistance=104.0)
            assert plan.rr_ratio >= 2.0 - 1e-6

    def test_rr_math_consistent(self):
        plan = build_trade_plan(price=50.0, atr=1.5, support=47.0, resistance=55.0)
        assert plan.risk_pct == pytest.approx((plan.entry - plan.stop) / plan.entry * 100, abs=0.05)
        assert plan.reward_pct == pytest.approx((plan.target - plan.entry) / plan.entry * 100, abs=0.05)
        assert plan.rr_ratio == pytest.approx(plan.reward_pct / plan.risk_pct, abs=0.05)

    def test_zero_price_returns_none(self):
        assert build_trade_plan(price=0.0, atr=1.0, support=None, resistance=None) is None

    def test_missing_atr_defaults_to_2pct(self):
        plan = build_trade_plan(price=100.0, atr=None, support=None, resistance=None)
        assert plan.stop == pytest.approx(97.0, abs=0.01)
