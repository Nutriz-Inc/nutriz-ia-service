from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth import get_current_user_id
from app.services.consent_service import get_latest_consent_version, has_valid_consent
from app.services.profile_service import get_nutriz_profile


router = APIRouter(tags=["me"])


@router.get("/me")
async def read_me(user_id: str = Depends(get_current_user_id)) -> dict[str, str]:
    return {"user_id": user_id}


@router.get("/me/profile")
async def get_my_profile(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    profile = await get_nutriz_profile(db, user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado para o usuario autenticado",
        )

    has_consent = await has_valid_consent(db, user_id)
    consent_version = await get_latest_consent_version(db, user_id)

    return {
        "profile": profile.model_dump(),
        "consent": {
            "has_valid_consent": has_consent,
            "terms_version": consent_version,
        },
    }
