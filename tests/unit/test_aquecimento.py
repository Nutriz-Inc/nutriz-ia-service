import pytest

from app.llm.provider import get_llm_provider
from app.services import aquecimento


@pytest.fixture(autouse=True)
def limpar_provider():
    get_llm_provider.cache_clear()
    yield
    get_llm_provider.cache_clear()


async def test_falha_no_aquecimento_nao_derruba_o_startup(monkeypatch: pytest.MonkeyPatch):
    async def banco_fora():
        raise ConnectionError("sem banco")

    async def llm_fora(self):
        raise TimeoutError("sem llm")

    monkeypatch.setattr(aquecimento, "_aquecer_banco", banco_fora)
    monkeypatch.setattr(type(get_llm_provider()), "aquecer", llm_fora)

    await aquecimento.aquecer_dependencias()


async def test_aquecimento_chama_banco_e_llm(monkeypatch: pytest.MonkeyPatch):
    chamados: list[str] = []

    async def banco():
        chamados.append("banco")

    async def llm(self):
        chamados.append("llm")

    monkeypatch.setattr(aquecimento, "_aquecer_banco", banco)
    monkeypatch.setattr(type(get_llm_provider()), "aquecer", llm)

    await aquecimento.aquecer_dependencias()

    assert sorted(chamados) == ["banco", "llm"]
