# Testes da montagem de prompts da EVA (com/sem RAG, com/sem perfil, com/sem
# contexto de doacao).

from datetime import datetime
from decimal import Decimal

from app.schemas.donation import (
    ActiveDonation,
    CollectionPlace,
    DonationContext,
    DonationHistory,
)
from app.schemas.profile import AddressProfile, BabyProfile, NutrizProfile
from app.schemas.rag import ChunkSearchResult
from app.services.eva_prompt import (
    EVA_SYSTEM_PROMPT,
    MAX_CHUNK_WORDS,
    build_messages_for_llm,
    build_messages_for_llm_with_rag,
    build_messages_for_public_llm,
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


def test_com_action_label_prompt_instrui_resposta_curta():
    messages = build_messages_for_llm_with_rag(
        [], "como me cadastrar?", [], action_label="Criar conta"
    )
    system = messages[0]["content"]
    assert "INTENCAO DE NAVEGACAO DETECTADA" in system
    assert '"Criar conta"' in system
    assert "NO MAXIMO 1 ou 2 frases" in system


def test_sem_action_label_prompt_nao_tem_instrucao_de_botao():
    messages = build_messages_for_llm_with_rag([], "como ordenhar?", [])
    assert "INTENCAO DE NAVEGACAO DETECTADA" not in messages[0]["content"]


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


def test_nome_do_bebe_entra_no_contexto():
    # Bug de producao: bebe cadastrado COM nome chegava a EVA so com a idade.
    messages = build_messages_for_llm_with_rag([], "oi", [], profile=_profile())
    system = messages[0]["content"]
    assert "Bebe: Joao, 4 meses" in system


def test_bebe_sem_nome_usa_so_a_idade():
    baby = BabyProfile(
        id_user_baby="b1",
        name=None,
        birth_date=datetime(2026, 3, 1),
        age_in_days=120,
        age_description="4 meses - leite maduro, fase ideal de doacao",
    )
    profile = NutrizProfile(
        id_user="u1", name="Usuaria Teste", baby=baby, address=None
    )
    messages = build_messages_for_llm_with_rag([], "oi", [], profile=profile)
    system = messages[0]["content"]
    assert "Bebe: 4 meses" in system
    assert "Joao" not in system


def test_chunk_longo_e_truncado_no_prompt():
    palavras = " ".join(f"palavra{i}" for i in range(MAX_CHUNK_WORDS + 100))
    messages = build_messages_for_llm_with_rag([], "oi", [_chunk(content=palavras)])
    system = messages[0]["content"]
    assert f"palavra{MAX_CHUNK_WORDS - 1}" in system
    assert f"palavra{MAX_CHUNK_WORDS}" not in system
    assert "[...]" in system


# ---------------------------------------------------------------------------
# Contexto de doacao (modo logado)
# ---------------------------------------------------------------------------

def _donation_context(
    with_donation: bool = True,
    with_history: bool = True,
    is_active: bool = True,
    current_step_name: str | None = "Coletar leite",
    status_label: str | None = "pendente",
    with_place: bool = True,
    total_donations: int = 2,
    volume: str | None = "1250.00",
) -> DonationContext:
    donation = None
    if with_donation:
        place = None
        if with_place:
            place = CollectionPlace(
                donation_point_name="Banco de Leite Teste",
                neighborhood="Vila Clementino",
                city="Sao Paulo",
                state="SP",
            )
        donation = ActiveDonation(
            id_donation="don_2veL1FPpuXxUaZcFaEC57BfpcKE",
            is_active=is_active,
            created_at=datetime(2026, 8, 9),
            current_step_name=current_step_name,
            current_step_status_label=status_label,
            current_step_set_date=datetime(2026, 8, 24) if current_step_name else None,
            next_step_name="Análise de leite" if current_step_name == "Coletar leite" else None,
            place=place,
        )
    history = None
    if with_history:
        history = DonationHistory(
            total_donations=total_donations,
            concluded_donations=1 if total_donations else 0,
            total_volume_ml=Decimal(volume) if volume else None,
            last_donation_at=datetime(2026, 8, 9) if total_donations else None,
        )
    return DonationContext(donation=donation, history=history)


def test_com_doacao_prompt_traz_etapa_data_proxima_e_local():
    messages = build_messages_for_llm_with_rag(
        [], "em que etapa esta minha doacao?", [], donations=_donation_context()
    )
    system = messages[0]["content"]
    assert "DOACOES DA NUTRIZ" in system
    assert "Doacao em andamento" in system
    assert 'etapa atual "Coletar leite" (pendente)' in system
    assert "prevista para 24/08/2026" in system
    assert 'proxima etapa "Análise de leite"' in system
    assert "local: Banco de Leite Teste, Vila Clementino, Sao Paulo/SP" in system


def test_historico_com_volume_e_totais_no_prompt():
    messages = build_messages_for_llm_with_rag(
        [], "quanto ja doei?", [], donations=_donation_context()
    )
    system = messages[0]["content"]
    assert "2 doacoes no total" in system
    assert "1 concluidas" in system
    # Volume sem zeros a direita: menos token e menos ruido na resposta.
    assert "1250 ml doados" in system
    assert "1250.00" not in system


def test_volume_fracionado_mantem_a_casa_decimal():
    messages = build_messages_for_llm_with_rag(
        [], "quanto ja doei?", [], donations=_donation_context(volume="980.50")
    )
    assert "980.5 ml doados" in messages[0]["content"]


def test_sem_doacoes_registradas_o_prompt_diz_isso_explicitamente():
    # Nutriz sem doacao: nao pode faltar contexto (a EVA inventaria), nem dar erro.
    messages = build_messages_for_llm_with_rag(
        [], "quantas doacoes eu fiz?", [],
        donations=_donation_context(with_donation=False, total_donations=0, volume=None),
    )
    system = messages[0]["content"]
    assert "nenhuma doacao registrada ate agora" in system
    assert "Doacao em andamento" not in system


def test_sem_contexto_de_doacao_nao_ha_secao():
    assert "DOACOES DA NUTRIZ" not in build_messages_for_llm_with_rag(
        [], "oi", [], donations=None
    )[0]["content"]


def test_falha_total_na_busca_nao_gera_secao_vazia():
    # Ambos os blocos falharam: a secao inteira some do prompt em vez de entrar
    # vazia (uma secao vazia convidaria a EVA a preencher com invencao).
    vazio = DonationContext(donation=None, history=None)
    assert "DOACOES DA NUTRIZ" not in build_messages_for_llm_with_rag(
        [], "oi", [], donations=vazio
    )[0]["content"]


def test_falha_em_um_bloco_mantem_o_outro_no_prompt():
    messages = build_messages_for_llm_with_rag(
        [], "oi", [], donations=_donation_context(with_donation=False)
    )
    system = messages[0]["content"]
    assert "DOACOES DA NUTRIZ" in system
    assert "2 doacoes no total" in system
    assert "Doacao em andamento" not in system


def test_doacao_encerrada_e_rotulada_como_ultima():
    messages = build_messages_for_llm_with_rag(
        [], "qual foi o ponto de coleta?", [],
        donations=_donation_context(is_active=False, current_step_name=None),
    )
    system = messages[0]["content"]
    assert "Ultima doacao (encerrada)" in system
    assert "todas as etapas concluidas" in system


def test_instrucoes_de_uso_proibem_inventar_e_lembram_do_limite_clinico():
    system = build_messages_for_llm_with_rag(
        [], "oi", [], donations=_donation_context()
    )[0]["content"]
    assert "INSTRUCOES DE USO DAS DOACOES" in system
    assert "NUNCA estime, deduza ou invente" in system
    assert "nao tem acesso a exames" in system


def test_persona_avisa_que_nao_acessa_exames():
    # Vale mesmo sem contexto de doacao: a recusa nao pode depender do bloco.
    system = build_messages_for_llm([], "quais meus resultados de exame?")[0]["content"]
    assert "NÃO tem acesso a exames" in system
    assert "sorologias" in system


def test_modo_publico_avisa_que_nao_tem_acesso_a_doacoes():
    system = build_messages_for_public_llm([], "em que etapa esta minha doacao?", [])[0][
        "content"
    ]
    assert "nao tem acesso a cadastro, doacoes" in system
    assert "DOACOES DA NUTRIZ" not in system
