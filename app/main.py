import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat_ws, conversations, health, me, session
from app.services.embeddings import embeddings_service


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Pre-aquece o modelo de embeddings no startup para eliminar o cold start
    # de varios segundos que a primeira mensagem pagava (baseline: ~5.4s).
    start = time.perf_counter()
    await asyncio.to_thread(embeddings_service.encode, "warmup")
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(f"Modelo de embeddings pre-aquecido em {elapsed_ms:.0f}ms")
    yield


app = FastAPI(title="Nutriz IA Service", version="0.1.0", lifespan=lifespan)

# Front Vite (5173) consome o POST /session/anonymous via fetch: precisa de CORS.
# WebSocket nao passa por preflight CORS, mas mantemos a lista alinhada.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(me.router)
app.include_router(session.router)
app.include_router(chat_ws.router)
app.include_router(conversations.router)
