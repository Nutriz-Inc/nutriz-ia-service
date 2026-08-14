# Benchmark de latencia percebida no chat da EVA via WebSocket.
# Mede, por turno: tempo ate o 1o chunk (latencia percebida) e tempo total.
# Uso: python -m scripts.bench_ws [--turns N] [--url ws://localhost:8000/ws/chat]
#
# Requer servidor rodando e usuario seed com consent no banco.
# Os logs [latency] do servidor complementam com a quebra por fase.

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timedelta, timezone

import jwt
import websockets

from app.config import settings


PERGUNTAS = [
    "Como faco para armazenar o leite ordenhado em casa?",
    "Quais sao os requisitos para ser doadora de leite?",
    "Posso doar leite se estiver tomando remedio para pressao?",
    "Qual a validade do leite congelado?",
    "Como e feita a coleta do leite na minha casa?",
]

SEED_USER_ID = "f058115f-51cb-4eb6-b7b9-7e2397299641"


def make_token() -> str:
    exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    return jwt.encode(
        {"id_user": SEED_USER_ID, "exp": exp},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


async def run_bench(url: str, turns: int) -> None:
    token = make_token()
    first_token_times: list[float] = []
    total_times: list[float] = []

    async with websockets.connect(f"{url}?token={token}") as ws:
        # Primeira mensagem do servidor e o evento de conversa criada
        conv_event = json.loads(await ws.recv())
        print(f"Conversa: {conv_event.get('conversation_id')}")

        for i in range(turns):
            pergunta = PERGUNTAS[i % len(PERGUNTAS)]
            sent_at = time.perf_counter()
            await ws.send(json.dumps({"message": pergunta}))

            first_chunk_at: float | None = None
            while True:
                event = json.loads(await ws.recv())
                if event["type"] == "chunk" and first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                elif event["type"] == "done":
                    done_at = time.perf_counter()
                    break
                elif event["type"] == "error":
                    raise RuntimeError(f"Erro do servidor: {event}")

            ttft = (first_chunk_at - sent_at) * 1000 if first_chunk_at else 0.0
            total = (done_at - sent_at) * 1000
            first_token_times.append(ttft)
            total_times.append(total)
            print(
                f"Turno {i + 1}: primeiro_chunk={ttft:.0f}ms | total={total:.0f}ms"
                f" | pergunta='{pergunta[:40]}...'"
            )

    print("\n=== RESUMO ===")
    print(f"Turnos: {turns}")
    print(
        f"Primeiro chunk (percebido): media={statistics.mean(first_token_times):.0f}ms"
        f" | mediana={statistics.median(first_token_times):.0f}ms"
        f" | max={max(first_token_times):.0f}ms"
    )
    print(
        f"Total do turno: media={statistics.mean(total_times):.0f}ms"
        f" | mediana={statistics.median(total_times):.0f}ms"
        f" | max={max(total_times):.0f}ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark do chat da EVA")
    parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--url", default="ws://localhost:8000/ws/chat")
    args = parser.parse_args()
    asyncio.run(run_bench(args.url, args.turns))


if __name__ == "__main__":
    main()
