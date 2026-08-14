# Rate limiting do modo publico, in-memory e async-safe.
#
# Duas politicas independentes:
# - por IP: janela deslizante de 1h (limite de mensagens/hora)
# - por sessao: contador acumulado no tempo de vida da sessao anonima
#
# Escolha por store in-memory (dict + asyncio.Lock) em vez de slowapi: slowapi
# e desenhado para rotas HTTP (decorator + Request), nao para o loop de um
# WebSocket, onde cada mensagem — nao cada conexao — precisa ser contada. Para o
# MVP (container unico) isto basta. Multi-instancia exigiria um store
# compartilhado (Redis); ver docs/modo-publico.md.

import asyncio
import time

from app.config import settings


class RateLimiter:
    def __init__(self) -> None:
        self._ip_hits: dict[str, list[float]] = {}
        self._session_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def check_and_increment(
        self, ip_hash: str, session_id: str
    ) -> tuple[bool, str | None]:
        # Retorna (permitido, motivo). motivo preenchido apenas quando barrado.
        now = time.monotonic()
        window = 3600.0
        async with self._lock:
            hits = [t for t in self._ip_hits.get(ip_hash, []) if now - t < window]
            if len(hits) >= settings.ANON_RATE_LIMIT_PER_IP_HOUR:
                self._ip_hits[ip_hash] = hits
                return False, "ip_hour"

            session_count = self._session_counts.get(session_id, 0)
            if session_count >= settings.ANON_RATE_LIMIT_PER_SESSION:
                return False, "session"

            hits.append(now)
            self._ip_hits[ip_hash] = hits
            self._session_counts[session_id] = session_count + 1
            return True, None

    def reset(self) -> None:
        self._ip_hits.clear()
        self._session_counts.clear()


rate_limiter = RateLimiter()
