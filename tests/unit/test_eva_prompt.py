# Testes da montagem de prompts da EVA (com/sem RAG, com/sem perfil).

from datetime import datetime

from app.schemas.profile import AddressProfile, BabyProfile, NutrizProfile
from app.schemas.rag import ChunkSearchResult
from app.services.eva_prompt import (
    EVA_SYSTEM_PROMPT,
    MAX_CHUNK_WORDS,
    build_messages_for_llm,
    build_messages_for_llm_with_rag,
)


class FakeMessage:
    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


def _chunk(content: str = "Lave as maos antes da ordenha.", score: float = 0.8) -> ChunkSearchResult:
    return ChunkSearchResult(
        content=content, source="ordenha_leite_humano", score=score, metadata_json=None
    )


def _profile(with_baby: bool = True, with_address: bool = True) -> NutrizProfile:
    baby = None
    if with_baby:
        baby = BabyProfile(
            id_user_baby="b1",
            name="Joao",
            birth_date=datetime(2026, 3, 1),
            age_in_days=120,
            age_description="4 meses - leite maduro, fase ideal de doacao",
        )
    address = None
    if with_address:
        address = AddressProfile(
            zipcode="04101000", city="Sao Paulo", state="SP", neighborhood="Vila Mariana"
        )
    return NutrizProfile(id_user="u1", name="Usuaria Teste", baby=baby, address=address)


def test_persona_presente_no_system_prompt():
    messages = build_messages_for_llm([], "ola")
    system = messages[0]["content"]
    assert messages[0]["role"] == "system"
    assert "SAMU 192" in system
    assert "NÃO prescreva medicamentos" in system
    assert "equipe Lactare" in system
    assert "mamãe" in system  # instrucao de NAO usar o termo


def test_historico_e_pergunta_na_ordem_correta():
    history = [FakeMessage("user", "primeira"), FakeMessage("assistant", "resposta")]
    messages = build_messages_for_llm(history, "segunda")
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[-1]["content"] == "segunda"


def test_com_chunks_prompt_contem_contexto_e_instrucao_de_uso_exclusivo():
    messages = build_messages_for_llm_with_rag([], "como ordenhar?", [_chunk()])
    system = messages[0]["content"]
    assert "CONTEXTO DOS PROTOCOLOS" in system
    assert "Use APENAS estas informacoes" in system
    assert "Lave as maos antes da ordenha." in system
    assert "relevancia: 0.80" in system


def test_sem_chunks_prompt_instrui_conhecimento_geral():
    messages = build_messages_for_llm_with_rag([], "posso doar?", [])
    system = messages[0]["content"]
    assert "Nao foi encontrada informacao especifica" in system
    assert "conhecimento geral confiavel" in system
    assert "MS, OMS, SBP, Fiocruz" in system
    assert "CONTEXTO DOS PROTOCOLOS" not in system


def test_com_perfil_completo_contexto_formatado():
    messages = build_messages_for_llm_with_rag([], "oi", [], profile=_profile())
    system = messages[0]["content"]
    assert "PERFIL DA NUTRIZ" in system
    assert "Usuaria Teste" in system
    assert "4 meses" in system
    assert "Vila Mariana" in system


def test_sem_perfil_nao_ha_secao_de_perfil():
    messages = build_messages_for_llm_with_rag([], "oi", [], profile=None)
    assert "PERFIL DA NUTRIZ" not in messages[0]["content"]


def test_perfil_degradado_sem_bebe_e_endereco():
    messages = build_messages_for_llm_with_rag(
        [], "oi", [], profile=_profile(with_baby=False, with_address=False)
    )
    system = messages[0]["content"]
    assert "Bebe: nao cadastrado" in system
    assert "Localizacao: nao cadastrada" in system


def test_chunk_longo_e_truncado_no_prompt():
    palavras = " ".join(f"palavra{i}" for i in range(MAX_CHUNK_WORDS + 100))
    messages = build_messages_for_llm_with_rag([], "oi", [_chunk(content=palavras)])
    system = messages[0]["content"]
    assert f"palavra{MAX_CHUNK_WORDS - 1}" in system
    assert f"palavra{MAX_CHUNK_WORDS}" not in system
    assert "[...]" in system
