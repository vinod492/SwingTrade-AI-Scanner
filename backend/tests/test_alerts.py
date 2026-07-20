"""Alert engine tests: rule triggering, cooldown dedup, prev-cycle transitions."""
from sqlalchemy import delete, select

from app.db.base import get_session_factory
from app.db.models import AlertEvent, AlertRule, Symbol, User
from app.db.seed import bootstrap
from app.services.alerts import evaluate_alerts
from app.services.security import hash_password


async def _setup_user_with_rules(rule_types: list[str]):
    import uuid

    await bootstrap()
    async with get_session_factory()() as s:
        await s.execute(delete(AlertEvent))
        await s.execute(delete(AlertRule))
        user = User(email=f"alerts-{uuid.uuid4().hex[:10]}@test.com",
                    password_hash=hash_password("x" * 12))
        s.add(user)
        await s.flush()
        for rt in rule_types:
            s.add(AlertRule(user_id=user.id, rule_type=rt, params={}, enabled=True))
        sym = (await s.execute(select(Symbol).where(Symbol.ticker == "NVDA"))).scalar_one()
        await s.commit()
        return user.id, sym.id


def row(symbol_id, **over):
    base = {"symbol_id": symbol_id, "ticker": "NVDA", "rank": 5, "swing_score": 85.0,
            "price": 100.0, "rel_volume": 1.0, "rsi": 55.0, "resistance": 110.0,
            "unusual_options": False}
    base.update(over)
    return base


class TestAlertEngine:
    async def test_relvol_fires_and_dedupes(self):
        _, sid = await _setup_user_with_rules(["relvol_3x"])
        async with get_session_factory()() as s:
            fired = await evaluate_alerts(s, [row(sid, rel_volume=3.5)], {}, set())
            assert fired == 1
            # same condition again inside cooldown → no re-fire
            fired = await evaluate_alerts(s, [row(sid, rel_volume=4.0)], {}, set())
            assert fired == 0

    async def test_relvol_below_threshold_silent(self):
        _, sid = await _setup_user_with_rules(["relvol_3x"])
        async with get_session_factory()() as s:
            assert await evaluate_alerts(s, [row(sid, rel_volume=2.9)], {}, set()) == 0

    async def test_top20_entry_only_on_transition(self):
        _, sid = await _setup_user_with_rules(["top20_entry"])
        async with get_session_factory()() as s:
            # already in top 20 last cycle → not "entering"
            assert await evaluate_alerts(s, [row(sid, rank=10)], {}, {"NVDA"}) == 0
            # newly entered → fires
            assert await evaluate_alerts(s, [row(sid, rank=10)], {}, set()) == 1

    async def test_rsi_cross_needs_prev_below_50(self):
        _, sid = await _setup_user_with_rules(["rsi_cross_50"])
        async with get_session_factory()() as s:
            prev = {"NVDA": row(sid, rsi=48.0)}
            assert await evaluate_alerts(s, [row(sid, rsi=52.0)], prev, set()) == 1

    async def test_rsi_no_cross_silent(self):
        _, sid = await _setup_user_with_rules(["rsi_cross_50"])
        async with get_session_factory()() as s:
            prev = {"NVDA": row(sid, rsi=55.0)}
            assert await evaluate_alerts(s, [row(sid, rsi=60.0)], prev, set()) == 0

    async def test_breakout_crossing_resistance(self):
        _, sid = await _setup_user_with_rules(["breakout"])
        async with get_session_factory()() as s:
            prev = {"NVDA": row(sid, price=108.0, resistance=110.0)}
            fired = await evaluate_alerts(
                s, [row(sid, price=111.0, resistance=110.0)], prev, set())
            assert fired == 1

    async def test_disabled_rule_never_fires(self):
        user_id, sid = await _setup_user_with_rules(["relvol_3x"])
        async with get_session_factory()() as s:
            rule = (await s.execute(select(AlertRule))).scalars().first()
            rule.enabled = False
            await s.commit()
            assert await evaluate_alerts(s, [row(sid, rel_volume=5.0)], {}, set()) == 0

    async def test_event_persisted_with_message(self):
        user_id, sid = await _setup_user_with_rules(["unusual_options"])
        async with get_session_factory()() as s:
            await evaluate_alerts(s, [row(sid, unusual_options=True)], {}, set())
            event = (await s.execute(select(AlertEvent))).scalars().one()
            assert event.user_id == user_id
            assert "unusual options" in event.message
