import json
from datetime import datetime, timezone

from app.services import eva_ferramentas
from app.services.eva_ferramentas import (
    COLUNAS_DE_DOADORAS,
    FERRAMENTAS,
    ITENS_POR_LISTA_NO_MODELO,
    ResultadoDaFerramenta,
)
from app.services.role_context_service import contexto_do_adm


def test_resultado_para_o_modelo_corta_listas_e_tira_ids():
    resultado = ResultadoDaFerramenta(
        {"id_rota": "abc", "itens": [{"id_route": str(i), "n": i} for i in range(20)]}
    )

    dados = json.loads(resultado.para_o_modelo())

    assert "id_rota" not in dados
    assert len(dados["itens"]) == ITENS_POR_LISTA_NO_MODELO + 1
    assert dados["itens"][-1] == {"mais_itens_nao_mostrados": 20 - ITENS_POR_LISTA_NO_MODELO}
    assert "id_route" not in dados["itens"][0]


def test_relatorio_de_doadoras_nao_tem_coluna_sensivel():
    chaves = {coluna["chave"] for coluna in COLUNAS_DE_DOADORAS}

    assert "email" not in chaves
    assert "cpf" not in chaves
    assert not any("senha" in chave or "password" in chave for chave in chaves)


def test_ferramentas_tem_nomes_unicos_e_status():
    nomes = [ferramenta["function"]["name"] for ferramenta in FERRAMENTAS]

    assert len(nomes) == len(set(nomes))
    assert set(nomes) == set(eva_ferramentas.STATUS_POR_FERRAMENTA)


async def test_ferramenta_desconhecida_devolve_erro():
    resultado = await eva_ferramentas.executar(None, "apagar_tudo", "{}")

    assert "erro" in resultado.conteudo


async def test_argumentos_que_nao_sao_objeto_devolvem_erro():
    resultado = await eva_ferramentas.executar(None, "consultar_indicadores", "[1, 2]")

    assert "erro" in resultado.conteudo


def test_contexto_do_adm_traz_data_e_hora_de_brasilia():
    bloco = contexto_do_adm(datetime(2026, 9, 26, 15, 30, tzinfo=timezone.utc))[0]

    assert "sabado, 26 set 2026, 12h30" in bloco
