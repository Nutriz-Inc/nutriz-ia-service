from fastapi import APIRouter

from app.config import settings

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
    }
