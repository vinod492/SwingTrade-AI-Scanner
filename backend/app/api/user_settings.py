from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import User, UserApiKey
from app.schemas.core import ApiKeyIn, ApiKeyStatus
from app.services.security import encrypt_secret

router = APIRouter(prefix="/settings", tags=["settings"])

SUPPORTED_PROVIDERS = {"polygon", "alpaca", "openai"}


def _hint(key: str) -> str:
    return f"{key[:4]}…{key[-3:]}" if len(key) > 10 else "•••"


@router.get("/api-keys", response_model=list[ApiKeyStatus])
async def list_api_keys(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    saved = {k.provider: k for k in (await db.execute(
        select(UserApiKey).where(UserApiKey.user_id == user.id)
    )).scalars()}
    return [ApiKeyStatus(provider=p, configured=p in saved)
            for p in sorted(SUPPORTED_PROVIDERS)]


@router.put("/api-keys", response_model=ApiKeyStatus)
async def save_api_key(body: ApiKeyIn, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if body.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"provider must be one of {sorted(SUPPORTED_PROVIDERS)}")
    if not body.key.strip():
        raise HTTPException(400, "key must not be empty")
    existing = (await db.execute(
        select(UserApiKey).where(UserApiKey.user_id == user.id,
                                 UserApiKey.provider == body.provider)
    )).scalar_one_or_none()
    if existing is None:
        existing = UserApiKey(user_id=user.id, provider=body.provider,
                              encrypted_key="", encrypted_secret="")
        db.add(existing)
    existing.encrypted_key = encrypt_secret(body.key.strip())
    existing.encrypted_secret = encrypt_secret(body.secret.strip()) if body.secret else ""
    await db.commit()
    return ApiKeyStatus(provider=body.provider, configured=True, hint=_hint(body.key))


@router.delete("/api-keys/{provider}", status_code=204)
async def delete_api_key(provider: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(
        select(UserApiKey).where(UserApiKey.user_id == user.id,
                                 UserApiKey.provider == provider)
    )).scalar_one_or_none()
    if existing is None:
        raise HTTPException(404, "No key saved for that provider")
    await db.delete(existing)
    await db.commit()
