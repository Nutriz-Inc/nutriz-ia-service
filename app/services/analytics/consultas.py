from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics.periodo import (
    FUSO_BRASILIA,
    Periodo,
    agora_utc,
    resolver_periodo,
)
from app.services.analytics.privacidade import (
    SITUACAO_DA_ROTA,
    SITUACAO_DO_AGENDAMENTO,
    mascarar_cpf,
    mascarar_telefone,
    situacao_da_etapa,
    traduzir,
)

LIMITE_ROTA_HORAS = 6
AVISO_ROTA_HORAS = 5
DIAS_PARA_EXAME_VENCER = 30
DIAS_PARADA_NA_ETAPA = 7
LIMITE_DE_LINHAS = 200

ETAPAS = (
    "Exame de sangue",
    "Entregar kit de ordenha",
    "Coletar leite",
    "Análise de leite",
)

ETAPA_ATUAL = """
    LEFT JOIN LATERAL (
        SELECT ds.name::text AS nome, ds.status::text AS status,
               ds.set_date, ds.created_at
        FROM donation_step ds
        WHERE ds.id_donation = d.id_donation
        ORDER BY ds.created_at DESC
        LIMIT 1
    ) etapa ON true
"""

ENDERECO_DA_DOADORA = """
    LEFT JOIN LATERAL (
        SELECT a.city, a.neighborhood
        FROM address a
        WHERE a.id_user = u.id_user
          AND a.id_donation_point IS NULL
          AND a.removed_at IS NULL
        ORDER BY a.created_at DESC
        LIMIT 1
    ) endereco ON true
"""


def _numero(valor: Any, casas: int = 2) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        valor = float(valor)
    return round(float(valor), casas)


def _inteiro(valor: Any) -> int:
    return int(valor or 0)


def _percentual(parte: Any, total: Any) -> float | None:
    if not total:
        return None
    return round(float(parte or 0) * 100 / float(total), 1)


def _litros(ml: Any) -> float:
    return round(float(ml or 0) / 1000, 2)


def _data(valor: datetime | None) -> str | None:
    if valor is None:
        return None
    local = valor.replace(tzinfo=timezone.utc).astimezone(FUSO_BRASILIA)
    return local.isoformat(timespec="minutes")


def _limites(periodo: Periodo) -> dict[str, datetime | None]:
    return {"ini": periodo.inicio_utc, "fim": periodo.fim_utc}


FILTRO_DE_PERIODO = (
    "(CAST(:ini AS timestamp) IS NULL OR {coluna} >= CAST(:ini AS timestamp)) "
    "AND (CAST(:fim AS timestamp) IS NULL OR {coluna} < CAST(:fim AS timestamp))"
)


def _no_periodo(coluna: str) -> str:
    return FILTRO_DE_PERIODO.format(coluna=coluna)


async def _linhas(db: AsyncSession, sql: str, **params: Any) -> list[dict[str, Any]]:
    resultado = await db.execute(text(sql), params)
    return [dict(linha) for linha in resultado.mappings().all()]


async def _uma(db: AsyncSession, sql: str, **params: Any) -> dict[str, Any]:
    linhas = await _linhas(db, sql, **params)
    return linhas[0] if linhas else {}


def _limitar(limite: int | None) -> int:
    if not limite or limite < 1:
        return 50
    return min(limite, LIMITE_DE_LINHAS)


async def visao_geral(db: AsyncSession, periodo: Periodo) -> dict[str, Any]:
    limites = _limites(periodo)

    doacoes = await _uma(
        db,
        f"""
        SELECT COUNT(*) AS doacoes,
               COUNT(DISTINCT d.created_by) AS doadoras,
               COUNT(*) FILTER (WHERE d.is_recurrent) AS doacoes_recorrentes,
               AVG(d.score_feedback) FILTER (WHERE d.score_feedback IS NOT NULL) AS satisfacao,
               COUNT(d.score_feedback) AS avaliacoes
        FROM donation d
        WHERE d.removed_at IS NULL AND {_no_periodo("d.created_at")}
        """,
        **limites,
    )

    frascos = await _uma(
        db,
        f"""
        SELECT COUNT(*) AS frascos,
               COUNT(*) FILTER (WHERE b.discarded IS TRUE) AS descartados,
               COALESCE(SUM(b.quantity_donated_ml) FILTER (WHERE b.discarded IS NOT TRUE), 0) AS ml
        FROM bottle b
        JOIN donation d ON d.id_donation = b.id_donation AND d.removed_at IS NULL
        WHERE {_no_periodo("d.created_at")}
        """,
        **limites,
    )

    agora = await _uma(
        db,
        f"""
        SELECT
          (SELECT COUNT(DISTINCT d.created_by) FROM donation d
            WHERE d.removed_at IS NULL AND d.is_active) AS doadoras_ativas,
          (SELECT COUNT(*) FROM "user" u
            WHERE u.removed_at IS NULL AND u.type::text = 'common'
              AND {_no_periodo("u.created_at")}) AS novas_doadoras
        """,
        **limites,
    )

    por_mes = await _linhas(
        db,
        f"""
        SELECT TO_CHAR(d.created_at, 'YYYY-MM') AS mes,
               COALESCE(SUM(b.quantity_donated_ml), 0) AS ml
        FROM bottle b
        JOIN donation d ON d.id_donation = b.id_donation AND d.removed_at IS NULL
        WHERE b.discarded IS NOT TRUE AND {_no_periodo("d.created_at")}
        GROUP BY 1 ORDER BY 1
        """,
        **limites,
    )

    return {
        "periodo": periodo.descrever(),
        "litros_coletados": _litros(frascos.get("ml")),
        "frascos": _inteiro(frascos.get("frascos")),
        "frascos_descartados": _inteiro(frascos.get("descartados")),
        "taxa_de_descarte_pct": _percentual(frascos.get("descartados"), frascos.get("frascos")),
        "doacoes_no_periodo": _inteiro(doacoes.get("doacoes")),
        "doadoras_no_periodo": _inteiro(doacoes.get("doadoras")),
        "doacoes_recorrentes": _inteiro(doacoes.get("doacoes_recorrentes")),
        "novas_doadoras_cadastradas": _inteiro(agora.get("novas_doadoras")),
        "doadoras_com_doacao_ativa_agora": _inteiro(agora.get("doadoras_ativas")),
        "satisfacao_media_1_a_5": _numero(doacoes.get("satisfacao"), 1),
        "avaliacoes": _inteiro(doacoes.get("avaliacoes")),
        "litros_por_mes": [
            {"mes": linha["mes"], "litros": _litros(linha["ml"])} for linha in por_mes
        ],
    }


async def _rotas_em_andamento(db: AsyncSession) -> list[dict[str, Any]]:
    linhas = await _linhas(
        db,
        """
        SELECT r.id_route, r.name, r.city, r.neighborhood, r.date_start,
               u.name AS motorista,
               COUNT(p.id_route_donation_step) AS paradas,
               COUNT(p.id_route_donation_step) FILTER (WHERE p.status::text = 'done') AS feitas,
               COUNT(p.id_route_donation_step) FILTER (WHERE p.status::text = 'error') AS imprevistos
        FROM route r
        LEFT JOIN "user" u ON u.id_user = r.id_driver
        LEFT JOIN route_donation_step p
          ON p.id_route = r.id_route AND p.removed_at IS NULL
        WHERE r.removed_at IS NULL AND r.status::text = 'in_progress'
        GROUP BY r.id_route, u.name
        ORDER BY r.date_start NULLS LAST
        """,
    )
    agora = agora_utc()
    rotas = []
    for linha in linhas:
        inicio = linha["date_start"]
        decorrido = (agora - inicio).total_seconds() / 3600 if inicio else None
        rotas.append(
            {
                "id_rota": linha["id_route"],
                "rota": linha["name"],
                "motorista": linha["motorista"],
                "regiao": linha["neighborhood"] or linha["city"],
                "iniciada_em": _data(inicio),
                "horas_decorridas": _numero(decorrido, 1),
                "horas_restantes_ate_6h": _numero(
                    max(LIMITE_ROTA_HORAS - decorrido, 0), 1
                )
                if decorrido is not None
                else None,
                "passou_de_6h": bool(decorrido and decorrido >= LIMITE_ROTA_HORAS),
                "em_alerta": bool(
                    decorrido and AVISO_ROTA_HORAS <= decorrido < LIMITE_ROTA_HORAS
                ),
                "paradas": _inteiro(linha["paradas"]),
                "paradas_feitas": _inteiro(linha["feitas"]),
                "paradas_com_imprevisto": _inteiro(linha["imprevistos"]),
            }
        )
    return rotas


async def cadeia_fria(db: AsyncSession, periodo: Periodo) -> dict[str, Any]:
    limites = _limites(periodo)
    resumo = await _uma(
        db,
        f"""
        WITH rotas AS (
            SELECT r.status::text AS status,
                   EXTRACT(EPOCH FROM (r.date_end - r.date_start)) / 3600 AS horas,
                   r.estimated_time / 3.6e12 AS horas_estimadas
            FROM route r
            WHERE r.removed_at IS NULL AND {_no_periodo("r.date_set")}
        )
        SELECT COUNT(*) AS rotas,
               COUNT(*) FILTER (WHERE status = 'done') AS concluidas,
               COUNT(*) FILTER (WHERE status = 'error') AS com_erro,
               COUNT(*) FILTER (WHERE status = 'canceled') AS canceladas,
               COUNT(horas) AS medidas,
               COUNT(*) FILTER (WHERE horas IS NOT NULL AND horas <= :limite) AS dentro,
               COUNT(*) FILTER (WHERE horas > :limite) AS acima,
               AVG(horas) AS media,
               MAX(horas) AS maior,
               AVG(horas_estimadas) FILTER (WHERE horas IS NOT NULL) AS media_estimada
        FROM rotas
        """,
        limite=LIMITE_ROTA_HORAS,
        **limites,
    )

    acima = await _linhas(
        db,
        f"""
        SELECT r.name, u.name AS motorista, r.date_set,
               EXTRACT(EPOCH FROM (r.date_end - r.date_start)) / 3600 AS horas
        FROM route r
        LEFT JOIN "user" u ON u.id_user = r.id_driver
        WHERE r.removed_at IS NULL
          AND r.date_end IS NOT NULL AND r.date_start IS NOT NULL
          AND EXTRACT(EPOCH FROM (r.date_end - r.date_start)) / 3600 > :limite
          AND {_no_periodo("r.date_set")}
        ORDER BY horas DESC
        LIMIT 20
        """,
        limite=LIMITE_ROTA_HORAS,
        **limites,
    )

    return {
        "periodo": periodo.descrever(),
        "limite_horas": LIMITE_ROTA_HORAS,
        "rotas_no_periodo": _inteiro(resumo.get("rotas")),
        "rotas_concluidas": _inteiro(resumo.get("concluidas")),
        "rotas_com_erro": _inteiro(resumo.get("com_erro")),
        "rotas_canceladas": _inteiro(resumo.get("canceladas")),
        "rotas_com_duracao_medida": _inteiro(resumo.get("medidas")),
        "rotas_dentro_de_6h": _inteiro(resumo.get("dentro")),
        "rotas_acima_de_6h": _inteiro(resumo.get("acima")),
        "conformidade_6h_pct": _percentual(resumo.get("dentro"), resumo.get("medidas")),
        "duracao_media_horas": _numero(resumo.get("media"), 1),
        "duracao_estimada_media_horas": _numero(resumo.get("media_estimada"), 1),
        "maior_duracao_horas": _numero(resumo.get("maior"), 1),
        "rotas_que_passaram_de_6h": [
            {
                "rota": linha["name"],
                "motorista": linha["motorista"],
                "data": _data(linha["date_set"]),
                "horas": _numero(linha["horas"], 1),
            }
            for linha in acima
        ],
        "rotas_em_andamento_agora": await _rotas_em_andamento(db),
    }


async def logistica(db: AsyncSession, periodo: Periodo) -> dict[str, Any]:
    limites = _limites(periodo)
    rotas = await _uma(
        db,
        f"""
        SELECT COUNT(*) AS rotas,
               COALESCE(SUM(r.mileage), 0) AS km,
               AVG(r.mileage) AS km_medio
        FROM route r
        WHERE r.removed_at IS NULL AND r.status::text = 'done'
          AND {_no_periodo("r.date_set")}
        """,
        **limites,
    )

    paradas = await _uma(
        db,
        f"""
        SELECT COUNT(*) AS paradas,
               COUNT(*) FILTER (WHERE p.status::text = 'done') AS feitas,
               COUNT(*) FILTER (WHERE p.status::text = 'error') AS imprevistos,
               COUNT(DISTINCT p.id_route) AS rotas
        FROM route_donation_step p
        JOIN route r ON r.id_route = p.id_route AND r.removed_at IS NULL
        WHERE p.removed_at IS NULL AND {_no_periodo("r.date_set")}
        """,
        **limites,
    )

    coletado = await _uma(
        db,
        f"""
        SELECT COALESCE(SUM(b.quantity_donated_ml), 0) AS ml
        FROM bottle b
        WHERE b.discarded IS NOT TRUE
          AND b.id_donation IN (
            SELECT ds.id_donation
            FROM route_donation_step p
            JOIN route r ON r.id_route = p.id_route AND r.removed_at IS NULL
            JOIN donation_step ds ON ds.id_donation_step = p.id_donation_step
            WHERE p.removed_at IS NULL AND r.status::text = 'done'
              AND {_no_periodo("r.date_set")}
          )
        """,
        **limites,
    )

    litros = _litros(coletado.get("ml"))
    km = _numero(rotas.get("km"), 1) or 0
    rotas_concluidas = _inteiro(rotas.get("rotas"))

    return {
        "periodo": periodo.descrever(),
        "rotas_concluidas": rotas_concluidas,
        "km_rodados": km,
        "km_medio_por_rota": _numero(rotas.get("km_medio"), 1),
        "litros_coletados_nas_rotas": litros,
        "km_por_litro_coletado": round(km / litros, 2) if litros else None,
        "litros_por_rota": round(litros / rotas_concluidas, 2) if rotas_concluidas else None,
        "paradas": _inteiro(paradas.get("paradas")),
        "paradas_feitas": _inteiro(paradas.get("feitas")),
        "paradas_com_imprevisto": _inteiro(paradas.get("imprevistos")),
        "taxa_de_imprevisto_pct": _percentual(paradas.get("imprevistos"), paradas.get("paradas")),
        "paradas_por_rota": round(
            _inteiro(paradas.get("paradas")) / _inteiro(paradas.get("rotas")), 1
        )
        if _inteiro(paradas.get("rotas"))
        else None,
    }


async def funil_doadora(db: AsyncSession, periodo: Periodo) -> dict[str, Any]:
    limites = _limites(periodo)
    por_etapa = await _linhas(
        db,
        f"""
        SELECT ds.name::text AS etapa,
               COUNT(DISTINCT ds.id_donation) AS chegaram,
               COUNT(DISTINCT ds.id_donation) FILTER (WHERE ds.status::text = 'done') AS concluiram,
               AVG(EXTRACT(EPOCH FROM (ds.completed_at - ds.created_at)) / 86400)
                 FILTER (WHERE ds.completed_at >= ds.created_at) AS dias_medios
        FROM donation_step ds
        JOIN donation d ON d.id_donation = ds.id_donation AND d.removed_at IS NULL
        WHERE {_no_periodo("d.created_at")}
        GROUP BY ds.name
        """,
        **limites,
    )

    ativas = await _linhas(
        db,
        f"""
        SELECT etapa.nome AS etapa, COUNT(*) AS doacoes,
               COUNT(*) FILTER (WHERE etapa.set_date < :limite
                                AND etapa.status <> 'done') AS paradas
        FROM donation d
        {ETAPA_ATUAL}
        WHERE d.removed_at IS NULL AND d.is_active
        GROUP BY etapa.nome
        """,
        limite=agora_utc() - timedelta(days=DIAS_PARADA_NA_ETAPA),
    )

    iniciadas = await _uma(
        db,
        f"""
        SELECT COUNT(*) AS total FROM donation d
        WHERE d.removed_at IS NULL AND {_no_periodo("d.created_at")}
        """,
        **limites,
    )

    indice = {linha["etapa"]: linha for linha in por_etapa}
    atuais = {linha["etapa"]: linha for linha in ativas}
    total = _inteiro(iniciadas.get("total"))

    etapas = []
    for nome in ETAPAS:
        linha = indice.get(nome, {})
        atual = atuais.get(nome, {})
        etapas.append(
            {
                "etapa": nome,
                "doacoes_que_chegaram": _inteiro(linha.get("chegaram")),
                "doacoes_que_concluiram": _inteiro(linha.get("concluiram")),
                "conversao_da_etapa_pct": _percentual(linha.get("concluiram"), linha.get("chegaram")),
                "alcance_desde_o_inicio_pct": _percentual(linha.get("chegaram"), total),
                "dias_medios_para_concluir": _numero(linha.get("dias_medios"), 1),
                "doacoes_ativas_nesta_etapa_agora": _inteiro(atual.get("doacoes")),
                "paradas_ha_mais_de_7_dias": _inteiro(atual.get("paradas")),
            }
        )

    com_tempo = [e for e in etapas if e["dias_medios_para_concluir"] is not None]
    mais_lenta = max(com_tempo, key=lambda e: e["dias_medios_para_concluir"], default=None)
    mais_cheia = max(etapas, key=lambda e: e["doacoes_ativas_nesta_etapa_agora"])

    return {
        "periodo": periodo.descrever(),
        "doacoes_iniciadas": total,
        "etapas": etapas,
        "gargalo_por_tempo": mais_lenta["etapa"] if mais_lenta else None,
        "gargalo_por_fila": mais_cheia["etapa"]
        if mais_cheia["doacoes_ativas_nesta_etapa_agora"]
        else None,
    }


async def desempenho_motoristas(db: AsyncSession, periodo: Periodo) -> dict[str, Any]:
    limites = _limites(periodo)
    linhas = await _linhas(
        db,
        f"""
        WITH rotas AS (
            SELECT r.id_route, r.id_driver, r.status::text AS status, r.mileage,
                   EXTRACT(EPOCH FROM (r.date_end - r.date_start)) / 3600 AS horas
            FROM route r
            WHERE r.removed_at IS NULL AND {_no_periodo("r.date_set")}
        ),
        paradas AS (
            SELECT p.id_route,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE p.status::text = 'error') AS imprevistos
            FROM route_donation_step p
            WHERE p.removed_at IS NULL
            GROUP BY p.id_route
        )
        SELECT u.name AS motorista,
               COUNT(rt.id_route) AS rotas,
               COUNT(rt.id_route) FILTER (WHERE rt.status = 'done') AS concluidas,
               COUNT(rt.id_route) FILTER (WHERE rt.status = 'error') AS com_erro,
               COALESCE(SUM(rt.mileage), 0) AS km,
               COALESCE(SUM(rt.horas), 0) AS horas,
               COUNT(rt.horas) AS medidas,
               COUNT(rt.horas) FILTER (WHERE rt.horas <= :limite) AS dentro,
               COALESCE(SUM(pa.total), 0) AS paradas,
               COALESCE(SUM(pa.imprevistos), 0) AS imprevistos
        FROM "user" u
        LEFT JOIN rotas rt ON rt.id_driver = u.id_user
        LEFT JOIN paradas pa ON pa.id_route = rt.id_route
        WHERE u.removed_at IS NULL AND u.type::text = 'driver'
        GROUP BY u.id_user, u.name
        ORDER BY rotas DESC, u.name
        """,
        limite=LIMITE_ROTA_HORAS,
        **limites,
    )

    return {
        "periodo": periodo.descrever(),
        "motoristas": [
            {
                "motorista": linha["motorista"],
                "rotas": _inteiro(linha["rotas"]),
                "rotas_concluidas": _inteiro(linha["concluidas"]),
                "rotas_com_erro": _inteiro(linha["com_erro"]),
                "km_rodados": _numero(linha["km"], 1),
                "horas_em_rota": _numero(linha["horas"], 1),
                "conformidade_6h_pct": _percentual(linha["dentro"], linha["medidas"]),
                "paradas": _inteiro(linha["paradas"]),
                "paradas_com_imprevisto": _inteiro(linha["imprevistos"]),
                "taxa_de_imprevisto_pct": _percentual(linha["imprevistos"], linha["paradas"]),
            }
            for linha in linhas
        ],
    }


async def desempenho_enfermagem(db: AsyncSession, periodo: Periodo) -> dict[str, Any]:
    limites = _limites(periodo)
    linhas = await _linhas(
        db,
        f"""
        SELECT u.name AS enfermeira,
               COUNT(j.id_job) AS agendamentos,
               COUNT(j.id_job) FILTER (WHERE j.status::text = 'done') AS concluidos,
               COUNT(j.id_job) FILTER (WHERE j.status::text = 'failed') AS nao_realizados,
               COUNT(j.id_job) FILTER (WHERE j.status::text = 'pending') AS pendentes,
               COUNT(j.id_job) FILTER (WHERE j.status::text = 'pending' AND j.date_set < :agora) AS atrasados
        FROM "user" u
        LEFT JOIN job j ON j.id_user = u.id_user AND j.removed_at IS NULL
                       AND {_no_periodo("j.date_set")}
        WHERE u.removed_at IS NULL AND u.type::text = 'nurse'
        GROUP BY u.id_user, u.name
        ORDER BY agendamentos DESC, u.name
        """,
        agora=agora_utc(),
        **limites,
    )

    return {
        "periodo": periodo.descrever(),
        "enfermagem": [
            {
                "enfermeira": linha["enfermeira"],
                "agendamentos": _inteiro(linha["agendamentos"]),
                "concluidos": _inteiro(linha["concluidos"]),
                "nao_realizados": _inteiro(linha["nao_realizados"]),
                "pendentes": _inteiro(linha["pendentes"]),
                "pendentes_com_data_ja_passada": _inteiro(linha["atrasados"]),
                "taxa_de_conclusao_pct": _percentual(
                    linha["concluidos"],
                    _inteiro(linha["concluidos"]) + _inteiro(linha["nao_realizados"]),
                ),
            }
            for linha in linhas
        ],
    }


async def regioes(
    db: AsyncSession, periodo: Periodo, agrupar_por: str = "cidade"
) -> dict[str, Any]:
    coluna = "endereco.neighborhood" if agrupar_por == "bairro" else "endereco.city"
    linhas = await _linhas(
        db,
        f"""
        SELECT COALESCE({coluna}, 'sem endereço') AS regiao,
               COUNT(DISTINCT d.created_by) AS doadoras,
               COUNT(DISTINCT d.id_donation) AS doacoes,
               COALESCE(SUM(b.quantity_donated_ml) FILTER (WHERE b.discarded IS NOT TRUE), 0) AS ml
        FROM donation d
        JOIN "user" u ON u.id_user = d.created_by
        {ENDERECO_DA_DOADORA}
        LEFT JOIN bottle b ON b.id_donation = d.id_donation
        WHERE d.removed_at IS NULL AND {_no_periodo("d.created_at")}
        GROUP BY 1
        ORDER BY ml DESC, doadoras DESC
        LIMIT 30
        """,
        **_limites(periodo),
    )

    return {
        "periodo": periodo.descrever(),
        "agrupado_por": "bairro" if agrupar_por == "bairro" else "cidade",
        "regioes": [
            {
                "regiao": linha["regiao"],
                "doadoras": _inteiro(linha["doadoras"]),
                "doacoes": _inteiro(linha["doacoes"]),
                "litros": _litros(linha["ml"]),
            }
            for linha in linhas
        ],
    }


async def _exames(db: AsyncSession, vencidos: bool) -> list[dict[str, Any]]:
    agora = agora_utc()
    condicao = (
        "u.blood_exam_valid_until < :agora"
        if vencidos
        else "u.blood_exam_valid_until >= :agora AND u.blood_exam_valid_until < :limite"
    )
    linhas = await _linhas(
        db,
        f"""
        SELECT u.name, u.blood_exam_valid_until, endereco.city, endereco.neighborhood
        FROM "user" u
        {ENDERECO_DA_DOADORA}
        WHERE u.removed_at IS NULL AND u.type::text = 'common'
          AND u.blood_exam_valid_until IS NOT NULL
          AND {condicao}
          AND EXISTS (
            SELECT 1 FROM donation d
            WHERE d.created_by = u.id_user AND d.removed_at IS NULL
              AND (d.is_active OR d.is_recurrent)
          )
        ORDER BY u.blood_exam_valid_until
        LIMIT 50
        """,
        agora=agora,
        limite=agora + timedelta(days=DIAS_PARA_EXAME_VENCER),
    )
    return [
        {
            "doadora": linha["name"],
            "exame_valido_ate": _data(linha["blood_exam_valid_until"]),
            "regiao": linha["neighborhood"] or linha["city"],
        }
        for linha in linhas
    ]


async def alertas(db: AsyncSession) -> dict[str, Any]:
    agora = agora_utc()
    rotas = await _rotas_em_andamento(db)

    paradas_na_etapa = await _linhas(
        db,
        f"""
        SELECT u.name AS doadora, etapa.nome, etapa.status, etapa.set_date,
               endereco.city, endereco.neighborhood
        FROM donation d
        JOIN "user" u ON u.id_user = d.created_by
        {ETAPA_ATUAL}
        {ENDERECO_DA_DOADORA}
        WHERE d.removed_at IS NULL AND d.is_active
          AND etapa.status <> 'done'
          AND etapa.set_date < :limite
        ORDER BY etapa.set_date
        LIMIT 50
        """,
        limite=agora - timedelta(days=DIAS_PARADA_NA_ETAPA),
    )

    hoje = await _uma(
        db,
        """
        SELECT
          (SELECT COUNT(*) FROM job j WHERE j.removed_at IS NULL
             AND j.status::text = 'pending'
             AND j.date_set >= :ini AND j.date_set < :fim) AS agendamentos_pendentes_hoje,
          (SELECT COUNT(*) FROM job j WHERE j.removed_at IS NULL
             AND j.status::text = 'pending' AND j.date_set < :ini) AS agendamentos_atrasados,
          (SELECT COUNT(*) FROM route r WHERE r.removed_at IS NULL
             AND r.status::text = 'pending'
             AND r.date_set < :agora) AS rotas_nao_iniciadas_no_horario
        """,
        agora=agora,
        **_hoje(),
    )

    return {
        "gerado_em": _data(agora),
        "total_de_rotas_em_andamento_agora": len(rotas),
        "rotas_em_andamento_agora": rotas,
        "rotas_passando_de_6h": [r for r in rotas if r["passou_de_6h"]],
        "rotas_em_alerta_5h": [r for r in rotas if r["em_alerta"]],
        "exames_vencendo_em_30_dias": await _exames(db, vencidos=False),
        "exames_vencidos_com_doacao_ativa": await _exames(db, vencidos=True),
        "doacoes_paradas_ha_mais_de_7_dias": [
            {
                "doadora": linha["doadora"],
                "etapa": linha["nome"],
                "situacao": situacao_da_etapa(linha["nome"], linha["status"]),
                "prevista_para": _data(linha["set_date"]),
                "regiao": linha["neighborhood"] or linha["city"],
            }
            for linha in paradas_na_etapa
        ],
        "agendamentos_pendentes_hoje": _inteiro(hoje.get("agendamentos_pendentes_hoje")),
        "agendamentos_atrasados": _inteiro(hoje.get("agendamentos_atrasados")),
        "rotas_agendadas_que_nao_iniciaram": _inteiro(hoje.get("rotas_nao_iniciadas_no_horario")),
    }


def _hoje() -> dict[str, datetime | None]:
    return _limites(resolver_periodo("hoje"))


async def operacao_agora(db: AsyncSession) -> dict[str, Any]:
    dados = await alertas(db)
    rotas = await _rotas_em_andamento(db)
    agendadas_hoje = await _uma(
        db,
        """
        SELECT COUNT(*) FILTER (WHERE r.status::text = 'pending') AS agendadas,
               COUNT(*) FILTER (WHERE r.status::text = 'done') AS concluidas
        FROM route r
        WHERE r.removed_at IS NULL AND r.date_set >= :ini AND r.date_set < :fim
        """,
        **_hoje(),
    )
    return {
        "gerado_em": dados["gerado_em"],
        "rotas_em_andamento": rotas,
        "rotas_agendadas_hoje": _inteiro(agendadas_hoje.get("agendadas")),
        "rotas_concluidas_hoje": _inteiro(agendadas_hoje.get("concluidas")),
        "agendamentos_pendentes_hoje": dados["agendamentos_pendentes_hoje"],
        "agendamentos_atrasados": dados["agendamentos_atrasados"],
        "alertas": {
            "rotas_passando_de_6h": len(dados["rotas_passando_de_6h"]),
            "rotas_em_alerta_5h": len(dados["rotas_em_alerta_5h"]),
            "exames_vencendo_em_30_dias": len(dados["exames_vencendo_em_30_dias"]),
            "exames_vencidos_com_doacao_ativa": len(dados["exames_vencidos_com_doacao_ativa"]),
            "doacoes_paradas_ha_mais_de_7_dias": len(dados["doacoes_paradas_ha_mais_de_7_dias"]),
            "rotas_agendadas_que_nao_iniciaram": dados["rotas_agendadas_que_nao_iniciaram"],
        },
    }


async def listar_doadoras(
    db: AsyncSession,
    etapa: str | None = None,
    somente_ativas: bool = True,
    recorrente: bool | None = None,
    cidade: str | None = None,
    bairro: str | None = None,
    exame: str | None = None,
    nome: str | None = None,
    limite: int | None = None,
) -> dict[str, Any]:
    agora = agora_utc()
    condicoes = ["d.removed_at IS NULL", "u.removed_at IS NULL"]
    params: dict[str, Any] = {"limite": _limitar(limite), "agora": agora}

    if somente_ativas:
        condicoes.append("d.is_active")
    if etapa:
        condicoes.append("etapa.nome = :etapa")
        params["etapa"] = etapa
    if recorrente is not None:
        condicoes.append("d.is_recurrent = :recorrente")
        params["recorrente"] = recorrente
    if cidade:
        condicoes.append("endereco.city ILIKE :cidade")
        params["cidade"] = f"%{cidade}%"
    if bairro:
        condicoes.append("endereco.neighborhood ILIKE :bairro")
        params["bairro"] = f"%{bairro}%"
    if nome:
        condicoes.append("u.name ILIKE :nome")
        params["nome"] = f"%{nome}%"
    if exame == "vencendo":
        condicoes.append(
            "u.blood_exam_valid_until >= :agora AND u.blood_exam_valid_until < :vence"
        )
        params["vence"] = agora + timedelta(days=DIAS_PARA_EXAME_VENCER)
    elif exame == "vencido":
        condicoes.append("u.blood_exam_valid_until < :agora")

    linhas = await _linhas(
        db,
        f"""
        SELECT u.name, u.cpf, u.phone_number, u.blood_exam_valid_until,
               d.is_active, d.is_recurrent, d.created_at,
               etapa.nome AS etapa, etapa.status AS status, etapa.set_date,
               endereco.city, endereco.neighborhood,
               (SELECT COALESCE(SUM(b.quantity_donated_ml), 0) FROM bottle b
                 WHERE b.id_donation = d.id_donation AND b.discarded IS NOT TRUE) AS ml
        FROM donation d
        JOIN "user" u ON u.id_user = d.created_by
        {ETAPA_ATUAL}
        {ENDERECO_DA_DOADORA}
        WHERE {" AND ".join(condicoes)}
        ORDER BY d.created_at DESC
        LIMIT :limite
        """,
        **params,
    )

    return {
        "total_listado": len(linhas),
        "doadoras": [
            {
                "doadora": linha["name"],
                "cpf": mascarar_cpf(linha["cpf"]),
                "telefone": mascarar_telefone(linha["phone_number"]),
                "cidade": linha["city"],
                "bairro": linha["neighborhood"],
                "etapa_atual": linha["etapa"],
                "situacao_da_etapa": situacao_da_etapa(linha["etapa"], linha["status"]),
                "etapa_prevista_para": _data(linha["set_date"]),
                "doacao_ativa": bool(linha["is_active"]),
                "recorrente": bool(linha["is_recurrent"]),
                "doacao_iniciada_em": _data(linha["created_at"]),
                "litros_doados_nesta_doacao": _litros(linha["ml"]),
                "exame_valido_ate": _data(linha["blood_exam_valid_until"]),
            }
            for linha in linhas
        ],
    }


async def listar_rotas(
    db: AsyncSession,
    periodo: Periodo,
    situacao: str | None = None,
    motorista: str | None = None,
    limite: int | None = None,
) -> dict[str, Any]:
    condicoes = ["r.removed_at IS NULL", _no_periodo("r.date_set")]
    params: dict[str, Any] = {"limite": _limitar(limite), **_limites(periodo)}
    if situacao:
        condicoes.append("r.status::text = :situacao")
        params["situacao"] = situacao
    if motorista:
        condicoes.append("u.name ILIKE :motorista")
        params["motorista"] = f"%{motorista}%"

    linhas = await _linhas(
        db,
        f"""
        SELECT r.name, r.status::text AS status, r.date_set, r.date_start, r.date_end,
               r.mileage, r.city, r.neighborhood, u.name AS motorista,
               COUNT(p.id_route_donation_step) AS paradas,
               COUNT(p.id_route_donation_step) FILTER (WHERE p.status::text = 'done') AS feitas,
               COUNT(p.id_route_donation_step) FILTER (WHERE p.status::text = 'error') AS imprevistos
        FROM route r
        LEFT JOIN "user" u ON u.id_user = r.id_driver
        LEFT JOIN route_donation_step p ON p.id_route = r.id_route AND p.removed_at IS NULL
        WHERE {" AND ".join(condicoes)}
        GROUP BY r.id_route, u.name
        ORDER BY r.date_set DESC
        LIMIT :limite
        """,
        **params,
    )

    def _horas(linha: dict[str, Any]) -> float | None:
        if not linha["date_start"] or not linha["date_end"]:
            return None
        return _numero((linha["date_end"] - linha["date_start"]).total_seconds() / 3600, 1)

    return {
        "periodo": periodo.descrever(),
        "total_listado": len(linhas),
        "rotas": [
            {
                "rota": linha["name"],
                "motorista": linha["motorista"],
                "data": _data(linha["date_set"]),
                "situacao": traduzir(SITUACAO_DA_ROTA, linha["status"]),
                "regiao": linha["neighborhood"] or linha["city"],
                "paradas": _inteiro(linha["paradas"]),
                "paradas_feitas": _inteiro(linha["feitas"]),
                "paradas_com_imprevisto": _inteiro(linha["imprevistos"]),
                "km": _numero(linha["mileage"], 1),
                "duracao_horas": _horas(linha),
            }
            for linha in linhas
        ],
    }


async def listar_agendamentos(
    db: AsyncSession,
    periodo: Periodo,
    situacao: str | None = None,
    enfermeira: str | None = None,
    limite: int | None = None,
) -> dict[str, Any]:
    condicoes = ["j.removed_at IS NULL", _no_periodo("j.date_set")]
    params: dict[str, Any] = {"limite": _limitar(limite), **_limites(periodo)}
    if situacao:
        condicoes.append("j.status::text = :situacao")
        params["situacao"] = situacao
    if enfermeira:
        condicoes.append("enf.name ILIKE :enfermeira")
        params["enfermeira"] = f"%{enfermeira}%"

    linhas = await _linhas(
        db,
        f"""
        SELECT j.date_set, j.status::text AS status, ds.name::text AS etapa,
               enf.name AS enfermeira, doadora.name AS doadora,
               endereco.city, endereco.neighborhood
        FROM job j
        LEFT JOIN "user" enf ON enf.id_user = j.id_user
        LEFT JOIN donation_step ds ON ds.id_donation_step = j.id_step
        LEFT JOIN donation d ON d.id_donation = ds.id_donation
        LEFT JOIN "user" doadora ON doadora.id_user = d.created_by
        LEFT JOIN LATERAL (
            SELECT a.city, a.neighborhood FROM address a
            WHERE a.id_user = doadora.id_user AND a.id_donation_point IS NULL
              AND a.removed_at IS NULL
            ORDER BY a.created_at DESC LIMIT 1
        ) endereco ON true
        WHERE {" AND ".join(condicoes)}
        ORDER BY j.date_set DESC NULLS LAST
        LIMIT :limite
        """,
        **params,
    )

    return {
        "periodo": periodo.descrever(),
        "total_listado": len(linhas),
        "agendamentos": [
            {
                "data": _data(linha["date_set"]),
                "etapa": linha["etapa"],
                "situacao": traduzir(SITUACAO_DO_AGENDAMENTO, linha["status"]),
                "enfermeira": linha["enfermeira"],
                "doadora": linha["doadora"],
                "regiao": linha["neighborhood"] or linha["city"],
            }
            for linha in linhas
        ],
    }
