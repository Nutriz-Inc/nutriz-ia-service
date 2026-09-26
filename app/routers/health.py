from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    backend_configurado = (
        "local" if "localhost" in settings.BACKEND_API_URL else "configurado"
    )

    return {
        "status": "ok",
        "service": "nutriz-ia-service",
        "backend_api": backend_configurado,
        "llm_model": settings.GROQ_MODEL,
    }


@router.get("/health/banco")
async def health_banco(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "banco": "ok"}
