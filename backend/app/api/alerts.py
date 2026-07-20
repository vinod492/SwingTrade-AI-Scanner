from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import AlertEvent, AlertRule, Symbol, User
from app.schemas.core import AlertEventOut, AlertRuleOut, AlertRuleUpdate

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/rules", response_model=list[AlertRuleOut])
async def list_rules(user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    rules = (await db.execute(
        select(AlertRule).where(AlertRule.user_id == user.id).order_by(AlertRule.id)
    )).scalars().all()
    return [AlertRuleOut(id=r.id, rule_type=r.rule_type, params=r.params or {},
                         enabled=r.enabled) for r in rules]


@router.patch("/rules/{rule_id}", response_model=AlertRuleOut)
async def update_rule(rule_id: int, body: AlertRuleUpdate,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    rule = await db.get(AlertRule, rule_id)
    if rule is None or rule.user_id != user.id:
        raise HTTPException(404, "Rule not found")
    if body.enabled is not None:
        rule.enabled = body.enabled
    if body.params is not None:
        rule.params = body.params
    await db.commit()
    return AlertRuleOut(id=rule.id, rule_type=rule.rule_type, params=rule.params or {},
                        enabled=rule.enabled)


@router.get("/events", response_model=list[AlertEventOut])
async def list_events(user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db),
                      unseen_only: bool = Query(False),
                      limit: int = Query(100, ge=1, le=500)):
    stmt = (select(AlertEvent, Symbol.ticker)
            .join(Symbol, Symbol.id == AlertEvent.symbol_id)
            .where(AlertEvent.user_id == user.id))
    if unseen_only:
        stmt = stmt.where(AlertEvent.seen == False)  # noqa: E712
    stmt = stmt.order_by(AlertEvent.triggered_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).all()
    return [AlertEventOut(id=e.id, ticker=ticker, rule_type=e.rule_type,
                          message=e.message, triggered_at=e.triggered_at, seen=e.seen)
            for e, ticker in rows]


@router.post("/events/{event_id}/seen", status_code=204)
async def mark_seen(event_id: int, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    event = await db.get(AlertEvent, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(404, "Event not found")
    event.seen = True
    await db.commit()


@router.post("/events/seen-all", status_code=204)
async def mark_all_seen(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    events = (await db.execute(
        select(AlertEvent).where(AlertEvent.user_id == user.id,
                                 AlertEvent.seen == False)  # noqa: E712
    )).scalars().all()
    for e in events:
        e.seen = True
    await db.commit()
