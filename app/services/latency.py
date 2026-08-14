# Instrumentacao de latencia por fase do pipeline do chat.
# Objetivo: medir onde o tempo e gasto (auth, perfil, rag, llm, persistencia)
# para orientar otimizacoes. Apenas logging - nao altera comportamento.

import logging
import time
from contextlib import contextmanager
from typing import Iterator


logger = logging.getLogger("latency")


class PhaseTimer:
    """Acumula duracao de fases nomeadas de um turno de chat e loga o resumo."""

    def __init__(self) -> None:
        self.phases_ms: dict[str, float] = {}

    @contextmanager
    def measure(self, phase: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            # Soma em vez de sobrescrever: fases repetidas no turno acumulam
            self.phases_ms[phase] = self.phases_ms.get(phase, 0.0) + elapsed_ms

    def record(self, phase: str, elapsed_ms: float) -> None:
        self.phases_ms[phase] = self.phases_ms.get(phase, 0.0) + elapsed_ms

    def log_summary(self, context: str) -> None:
        if not self.phases_ms:
            return
        parts = [f"{phase}={ms:.0f}ms" for phase, ms in self.phases_ms.items()]
        total = sum(self.phases_ms.values())
        logger.info(f"[latency] {context}: {' | '.join(parts)} | total={total:.0f}ms")
