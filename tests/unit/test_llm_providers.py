# Testes da factory do Strategy Pattern de providers LLM e do streaming
# de cada provider (clients HTTP mockados - nenhum teste usa rede).

import json
from types import SimpleNamespace

import httpx
import pytest

from app.config import settings
from app.llm.groq_provider import GroqProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.provider import get_llm_provider


@pytest.fixture(autouse=True)
def clear_provider_cache():
    # Factory e cacheada (lru_cache); limpar antes e depois para isolar testes
    get_llm_provider.cache_clear()
    yield
    get_llm_provider.cache_clear()


def test_factory_retorna_groq(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    provider = get_llm_provider()
    assert provider.get_provider_name() == "groq"
    assert provider.get_model_name() == settings.GROQ_MODEL


def test_factory_retorna_ollama(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    provider = get_llm_provider()
    assert provider.get_provider_name() == "ollama"
    assert provider.get_model_name() == settings.OLLAMA_MODEL


def test_factory_ignora_maiusculas(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "GROQ")
    provider = get_llm_provider()
    assert provider.get_provider_name() == "groq"


def test_provider_invalido_levanta_erro_claro(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    with pytest.raises(ValueError, match="LLM_PROVIDER desconhecido"):
        get_llm_provider()


def test_factory_reutiliza_instancia(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    assert get_llm_provider() is get_llm_provider()


def _groq_chunk(content: str | None) -> SimpleNamespace:
    delta = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


async def test_groq_stream_chat_emite_conteudo(monkeypatch: pytest.MonkeyPatch):
    provider = GroqProvider()

    async def fake_stream():
        for content in ["Ola", ", nutriz", None, "!"]:
            yield _groq_chunk(content)

    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_stream()

    monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)

    messages = [{"role": "user", "content": "oi"}]
    chunks = [c async for c in provider.stream_chat(messages)]

    # Chunks None (keep-alive do stream) sao filtrados
    assert chunks == ["Ola", ", nutriz", "!"]
    assert captured["model"] == settings.GROQ_MODEL
    assert captured["messages"] == messages
    assert captured["stream"] is True


async def _parametros_enviados(monkeypatch: pytest.MonkeyPatch, modelo: str) -> dict:
    monkeypatch.setattr(settings, "GROQ_MODEL", modelo)
    provider = GroqProvider()

    async def fake_stream():
        yield _groq_chunk("ok")

    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_stream()

    monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)
    [c async for c in provider.stream_chat([{"role": "user", "content": "oi"}])]
    return captured


async def test_groq_gpt_oss_pede_raciocinio_curto(monkeypatch: pytest.MonkeyPatch):
    captured = await _parametros_enviados(monkeypatch, "openai/gpt-oss-120b")

    assert captured["extra_body"] == {"reasoning_effort": settings.GROQ_REASONING_EFFORT}
    assert captured["max_tokens"] == settings.LLM_MAX_TOKENS
    assert captured["temperature"] == settings.LLM_TEMPERATURE


async def test_groq_qwen_responde_sem_raciocinio(monkeypatch: pytest.MonkeyPatch):
    captured = await _parametros_enviados(monkeypatch, "qwen/qwen3.8-27b")

    assert captured["extra_body"] == {"reasoning_effort": "none"}


async def test_groq_outro_modelo_nao_recebe_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
):
    captured = await _parametros_enviados(monkeypatch, "meta-llama/llama-4-scout")

    assert captured["extra_body"] is None


async def test_ollama_stream_chat_emite_conteudo_e_para_no_done(
    monkeypatch: pytest.MonkeyPatch,
):
    linhas = [
        json.dumps({"message": {"content": "Ola"}, "done": False}),
        "",
        json.dumps({"message": {"content": " nutriz"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(200, text="\n".join(linhas))

    provider = OllamaProvider()
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock"
    )

    chunks = [c async for c in provider.stream_chat([{"role": "user", "content": "oi"}])]
    assert chunks == ["Ola", " nutriz"]
