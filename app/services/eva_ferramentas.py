import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics import consultas
from app.services.analytics.periodo import PRESETS, Periodo, agora_utc, resolver_periodo

LINHAS_PARA_O_MODELO = 8
ITENS_POR_LISTA_NO_MODELO = LINHAS_PARA_O_MODELO

Preset = Literal[
    "hoje",
    "ontem",
    "ultimos_7_dias",
    "ultimos_30_dias",
    "mes_atual",
    "mes_anterior",
    "ultimos_3_meses",
    "ultimos_6_meses",
    "ano_atual",
    "tudo",
]
Etapa = Literal[
    "Exame de sangue",
    "Entregar kit de ordenha",
    "Coletar leite",
    "Análise de leite",
]
Tema = Literal[
    "visao_geral",
    "cadeia_fria",
    "logistica",
    "funil_doadora",
    "desempenho_motoristas",
    "desempenho_enfermagem",
    "regioes",
]
TipoDeRelatorio = Literal[
    "visao_geral",
    "cadeia_fria",
    "funil_doadora",
    "desempenho_motoristas",
    "desempenho_enfermagem",
    "regioes",
    "doadoras",
    "exames_vencendo",
    "rotas",
    "agendamentos",
]


class ArgumentosDePeriodo(BaseModel):
    periodo: Preset = "mes_atual"
    data_inicio: date | None = None
    data_fim: date | None = None

    def resolver(self) -> Periodo:
        return resolver_periodo(self.periodo, self.data_inicio, self.data_fim)


class ArgumentosDeIndicadores(ArgumentosDePeriodo):
    tema: Tema
    agrupar_regiao_por: Literal["cidade", "bairro"] = "cidade"


class ArgumentosDeFiltro(ArgumentosDePeriodo):
    etapa: Etapa | None = None
    situacao: str | None = Field(default=None, max_length=20)
    cidade: str | None = Field(default=None, max_length=80)
    bairro: str | None = Field(default=None, max_length=80)
    nome: str | None = Field(default=None, max_length=80)
    motorista: str | None = Field(default=None, max_length=80)
    enfermeira: str | None = Field(default=None, max_length=80)
    recorrente: bool | None = None
    exame: Literal["vencendo", "vencido"] | None = None
    somente_ativas: bool = True


class ArgumentosDeLista(ArgumentosDeFiltro):
    entidade: Literal["doadoras", "rotas", "agendamentos"]


class ArgumentosDeRelatorio(ArgumentosDeFiltro):
    tipo: TipoDeRelatorio


PROPRIEDADES_DE_PERIODO: dict[str, Any] = {
    "periodo": {
        "type": "string",
        "enum": list(PRESETS),
        "description": "Recorte de tempo. Padrao: mes_atual.",
    },
    "data_inicio": {
        "type": "string",
        "description": "Opcional, AAAA-MM-DD. Use so quando a pessoa citar datas exatas.",
    },
    "data_fim": {"type": "string", "description": "Opcional, AAAA-MM-DD."},
}

PROPRIEDADES_DE_FILTRO: dict[str, Any] = {
    **PROPRIEDADES_DE_PERIODO,
    "etapa": {"type": "string", "enum": list(consultas.ETAPAS)},
    "situacao": {
        "type": "string",
        "description": (
            "Rotas: pending, in_progress, done, error, canceled. "
            "Agendamentos: pending, done, failed."
        ),
    },
    "cidade": {"type": "string"},
    "bairro": {"type": "string"},
    "nome": {"type": "string", "description": "Parte do nome da doadora."},
    "motorista": {"type": "string"},
    "enfermeira": {"type": "string"},
    "recorrente": {"type": "boolean"},
    "exame": {
        "type": "string",
        "enum": ["vencendo", "vencido"],
        "description": "Validade do exame de sangue da doadora (vencendo = proximos 30 dias).",
    },
    "somente_ativas": {
        "type": "boolean",
        "description": "Doadoras: so com doacao ativa. Padrao true.",
    },
}

FERRAMENTAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "consultar_indicadores",
            "description": (
                "Indicadores agregados. visao_geral: litros, frascos, descarte, doadoras, "
                "satisfacao. cadeia_fria: regra das 6h e rotas em andamento. logistica: km "
                "por litro, paradas, imprevistos. funil_doadora: conversao por etapa e "
                "gargalo. regioes: litros por cidade ou bairro."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tema": {"type": "string", "enum": list(Tema.__args__)},
                    "agrupar_regiao_por": {"type": "string", "enum": ["cidade", "bairro"]},
                    **PROPRIEDADES_DE_PERIODO,
                },
                "required": ["tema"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_alertas",
            "description": (
                "Situacao de agora: todas as rotas em andamento (com tempo no limite "
                "de 6h), exames vencendo, doacoes paradas, agendamentos atrasados."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_registros",
            "description": (
                f"Lista doadoras, rotas ou agendamentos com filtros (ate {LINHAS_PARA_O_MODELO} "
                "linhas). Para lista completa ou para baixar, use gerar_relatorio."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entidade": {"type": "string", "enum": ["doadoras", "rotas", "agendamentos"]},
                    **PROPRIEDADES_DE_FILTRO,
                },
                "required": ["entidade"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gerar_relatorio",
            "description": (
                "Relatorio com botoes de baixar CSV e PDF no chat. Use para relatorio, "
                "planilha, exportar ou lista completa. Voce recebe so um resumo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": list(TipoDeRelatorio.__args__)},
                    **PROPRIEDADES_DE_FILTRO,
                },
                "required": ["tipo"],
            },
        },
    },
]

STATUS_POR_FERRAMENTA = {
    "consultar_indicadores": "Consultando os indicadores",
    "consultar_alertas": "Verificando os alertas da operação",
    "listar_registros": "Buscando os registros",
    "gerar_relatorio": "Montando o relatório",
}


@dataclass
class Relatorio:
    titulo: str
    periodo: str | None
    colunas: list[dict[str, str]]
    linhas: list[dict[str, Any]]
    resumo: list[dict[str, Any]] = field(default_factory=list)

    def como_frame(self) -> dict[str, Any]:
        return {
            "titulo": self.titulo,
            "periodo": self.periodo,
            "gerado_em": agora_utc().isoformat() + "Z",
            "colunas": self.colunas,
            "linhas": self.linhas,
            "resumo": self.resumo,
        }


@dataclass
class ResultadoDaFerramenta:
    conteudo: dict[str, Any]
    relatorio: Relatorio | None = None

    def para_o_modelo(self) -> str:
        return json.dumps(
            _compactar(self.conteudo), ensure_ascii=False, separators=(",", ":"), default=str
        )


def _compactar(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {
            chave: _compactar(item)
            for chave, item in valor.items()
            if item is not None and not chave.startswith("id_")
        }
    if isinstance(valor, list):
        itens = [_compactar(item) for item in valor[:ITENS_POR_LISTA_NO_MODELO]]
        if len(valor) > ITENS_POR_LISTA_NO_MODELO:
            itens.append({"mais_itens_nao_mostrados": len(valor) - ITENS_POR_LISTA_NO_MODELO})
        return itens
    return valor


def _colunas(*pares: tuple[str, str]) -> list[dict[str, str]]:
    return [{"chave": chave, "rotulo": rotulo} for chave, rotulo in pares]


def _resumo(dados: dict[str, Any], rotulos: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"rotulo": rotulo, "valor": dados.get(chave)}
        for chave, rotulo in rotulos.items()
        if dados.get(chave) is not None
    ]


async def _indicadores(db: AsyncSession, args: ArgumentosDeIndicadores) -> dict[str, Any]:
    periodo = args.resolver()
    if args.tema == "visao_geral":
        return await consultas.visao_geral(db, periodo)
    if args.tema == "cadeia_fria":
        return await consultas.cadeia_fria(db, periodo)
    if args.tema == "logistica":
        return await consultas.logistica(db, periodo)
    if args.tema == "funil_doadora":
        return await consultas.funil_doadora(db, periodo)
    if args.tema == "desempenho_motoristas":
        return await consultas.desempenho_motoristas(db, periodo)
    if args.tema == "desempenho_enfermagem":
        return await consultas.desempenho_enfermagem(db, periodo)
    return await consultas.regioes(db, periodo, args.agrupar_regiao_por)


async def _lista(
    db: AsyncSession, args: ArgumentosDeFiltro, entidade: str, limite: int
) -> dict[str, Any]:
    if entidade == "doadoras":
        return await consultas.listar_doadoras(
            db,
            etapa=args.etapa,
            somente_ativas=args.somente_ativas,
            recorrente=args.recorrente,
            cidade=args.cidade,
            bairro=args.bairro,
            exame=args.exame,
            nome=args.nome,
            limite=limite,
        )
    if entidade == "rotas":
        return await consultas.listar_rotas(
            db, args.resolver(), situacao=args.situacao, motorista=args.motorista, limite=limite
        )
    return await consultas.listar_agendamentos(
        db, args.resolver(), situacao=args.situacao, enfermeira=args.enfermeira, limite=limite
    )


def _cortar(dados: dict[str, Any], chave: str) -> dict[str, Any]:
    linhas = dados.get(chave, [])
    if len(linhas) <= LINHAS_PARA_O_MODELO:
        return dados
    return {
        **dados,
        chave: linhas[:LINHAS_PARA_O_MODELO],
        "aviso": f"Mostrando {LINHAS_PARA_O_MODELO} de {len(linhas)}. Ofereca gerar o relatorio completo.",
    }


COLUNAS_DE_DOADORAS = _colunas(
    ("doadora", "Doadora"),
    ("bairro", "Bairro"),
    ("cidade", "Cidade"),
    ("etapa_atual", "Etapa atual"),
    ("situacao_da_etapa", "Situação"),
    ("doacao_iniciada_em", "Início da doação"),
    ("litros_doados_nesta_doacao", "Litros"),
    ("exame_valido_ate", "Exame válido até"),
    ("telefone", "Telefone"),
)


def _totalizar(
    linhas: list[dict[str, Any]], campos: dict[str, str], contagem: str
) -> list[dict[str, Any]]:
    resumo: list[dict[str, Any]] = [{"rotulo": contagem, "valor": len(linhas)}]
    for chave, rotulo in campos.items():
        valores = [linha[chave] for linha in linhas if isinstance(linha.get(chave), (int, float))]
        if valores:
            resumo.append({"rotulo": rotulo, "valor": round(sum(valores), 1)})
    return resumo


async def _relatorio(db: AsyncSession, args: ArgumentosDeRelatorio) -> Relatorio:
    periodo = args.resolver()
    rotulo = periodo.rotulo

    if args.tipo in ("doadoras", "exames_vencendo"):
        exame = "vencendo" if args.tipo == "exames_vencendo" else args.exame
        dados = await consultas.listar_doadoras(
            db,
            etapa=args.etapa,
            somente_ativas=args.somente_ativas,
            recorrente=args.recorrente,
            cidade=args.cidade,
            bairro=args.bairro,
            exame=exame,
            nome=args.nome,
            limite=consultas.LIMITE_DE_LINHAS,
        )
        titulo = (
            "Doadoras com exame de sangue vencendo em 30 dias"
            if args.tipo == "exames_vencendo"
            else "Doadoras"
        )
        return Relatorio(
            titulo=titulo,
            periodo=None,
            colunas=COLUNAS_DE_DOADORAS,
            linhas=dados["doadoras"],
            resumo=[{"rotulo": "Doadoras listadas", "valor": dados["total_listado"]}],
        )

    if args.tipo == "rotas":
        dados = await _lista(db, args, "rotas", consultas.LIMITE_DE_LINHAS)
        return Relatorio(
            titulo="Rotas",
            periodo=rotulo,
            colunas=_colunas(
                ("data", "Data"), ("rota", "Rota"), ("motorista", "Motorista"),
                ("situacao", "Situação"), ("paradas", "Paradas"),
                ("paradas_com_imprevisto", "Imprevistos"), ("km", "Km"),
                ("duracao_horas", "Duração (h)"),
            ),
            linhas=dados["rotas"],
            resumo=[{"rotulo": "Rotas listadas", "valor": dados["total_listado"]}],
        )

    if args.tipo == "agendamentos":
        dados = await _lista(db, args, "agendamentos", consultas.LIMITE_DE_LINHAS)
        return Relatorio(
            titulo="Agendamentos",
            periodo=rotulo,
            colunas=_colunas(
                ("data", "Data"), ("etapa", "Etapa"), ("situacao", "Situação"),
                ("enfermeira", "Enfermagem"), ("doadora", "Doadora"), ("regiao", "Região"),
            ),
            linhas=dados["agendamentos"],
            resumo=[{"rotulo": "Agendamentos listados", "valor": dados["total_listado"]}],
        )

    if args.tipo == "desempenho_motoristas":
        dados = await consultas.desempenho_motoristas(db, periodo)
        return Relatorio(
            titulo="Desempenho dos motoristas",
            periodo=rotulo,
            colunas=_colunas(
                ("motorista", "Motorista"), ("rotas", "Rotas"),
                ("rotas_concluidas", "Concluídas"), ("km_rodados", "Km"),
                ("horas_em_rota", "Horas"), ("conformidade_6h_pct", "Dentro das 6h (%)"),
                ("paradas_com_imprevisto", "Imprevistos"),
            ),
            linhas=dados["motoristas"],
            resumo=_totalizar(
                dados["motoristas"],
                {"rotas": "Rotas", "km_rodados": "Km rodados", "paradas_com_imprevisto": "Imprevistos"},
                "Motoristas",
            ),
        )

    if args.tipo == "desempenho_enfermagem":
        dados = await consultas.desempenho_enfermagem(db, periodo)
        return Relatorio(
            titulo="Desempenho da enfermagem",
            periodo=rotulo,
            colunas=_colunas(
                ("enfermeira", "Enfermagem"), ("agendamentos", "Agendamentos"),
                ("concluidos", "Concluídos"), ("nao_realizados", "Não realizados"),
                ("pendentes", "Pendentes"), ("pendentes_com_data_ja_passada", "Atrasados"),
                ("taxa_de_conclusao_pct", "Conclusão (%)"),
            ),
            linhas=dados["enfermagem"],
            resumo=_totalizar(
                dados["enfermagem"],
                {"agendamentos": "Agendamentos", "concluidos": "Concluídos", "pendentes_com_data_ja_passada": "Atrasados"},
                "Profissionais",
            ),
        )

    if args.tipo == "regioes":
        dados = await consultas.regioes(db, periodo, "bairro" if args.bairro else "cidade")
        return Relatorio(
            titulo=f"Coleta por {dados['agrupado_por']}",
            periodo=rotulo,
            colunas=_colunas(
                ("regiao", "Região"), ("doadoras", "Doadoras"),
                ("doacoes", "Doações"), ("litros", "Litros"),
            ),
            linhas=dados["regioes"],
            resumo=_totalizar(
                dados["regioes"], {"doadoras": "Doadoras", "litros": "Litros"}, "Regiões"
            ),
        )

    if args.tipo == "funil_doadora":
        dados = await consultas.funil_doadora(db, periodo)
        return Relatorio(
            titulo="Funil da doadora",
            periodo=rotulo,
            colunas=_colunas(
                ("etapa", "Etapa"), ("doacoes_que_chegaram", "Chegaram"),
                ("doacoes_que_concluiram", "Concluíram"),
                ("conversao_da_etapa_pct", "Conversão (%)"),
                ("dias_medios_para_concluir", "Dias para concluir"),
                ("doacoes_ativas_nesta_etapa_agora", "Na etapa agora"),
            ),
            linhas=dados["etapas"],
            resumo=_resumo(
                dados,
                {"doacoes_iniciadas": "Doações iniciadas", "gargalo_por_tempo": "Etapa mais lenta"},
            ),
        )

    if args.tipo == "cadeia_fria":
        dados = await consultas.cadeia_fria(db, periodo)
        return Relatorio(
            titulo="Cadeia fria: rotas acima de 6 horas",
            periodo=rotulo,
            colunas=_colunas(
                ("data", "Data"), ("rota", "Rota"), ("motorista", "Motorista"), ("horas", "Horas"),
            ),
            linhas=dados["rotas_que_passaram_de_6h"],
            resumo=_resumo(
                dados,
                {
                    "rotas_no_periodo": "Rotas no período",
                    "conformidade_6h_pct": "Dentro das 6h (%)",
                    "duracao_media_horas": "Duração média (h)",
                    "rotas_acima_de_6h": "Acima de 6h",
                },
            ),
        )

    dados = await consultas.visao_geral(db, periodo)
    return Relatorio(
        titulo="Visão geral da operação",
        periodo=rotulo,
        colunas=_colunas(("mes", "Mês"), ("litros", "Litros coletados")),
        linhas=dados["litros_por_mes"],
        resumo=_resumo(
            dados,
            {
                "litros_coletados": "Litros coletados",
                "frascos": "Frascos",
                "taxa_de_descarte_pct": "Descarte (%)",
                "doacoes_no_periodo": "Doações",
                "doadoras_com_doacao_ativa_agora": "Doadoras ativas agora",
                "satisfacao_media_1_a_5": "Satisfação (1 a 5)",
            },
        ),
    )


def _ler_argumentos(argumentos: str | None) -> dict[str, Any]:
    if not argumentos:
        return {}
    dados = json.loads(argumentos)
    if not isinstance(dados, dict):
        raise ValueError("argumentos precisam ser um objeto")
    return {chave: valor for chave, valor in dados.items() if valor not in (None, "")}


async def executar(db: AsyncSession, nome: str, argumentos: str | None) -> ResultadoDaFerramenta:
    try:
        brutos = _ler_argumentos(argumentos)
        if nome == "consultar_indicadores":
            return ResultadoDaFerramenta(
                await _indicadores(db, ArgumentosDeIndicadores(**brutos))
            )
        if nome == "consultar_alertas":
            return ResultadoDaFerramenta(await consultas.alertas(db))
        if nome == "listar_registros":
            args = ArgumentosDeLista(**brutos)
            dados = await _lista(db, args, args.entidade, consultas.LIMITE_DE_LINHAS)
            return ResultadoDaFerramenta(_cortar(dados, args.entidade))
        if nome == "gerar_relatorio":
            relatorio = await _relatorio(db, ArgumentosDeRelatorio(**brutos))
            return ResultadoDaFerramenta(
                {
                    "relatorio_gerado": True,
                    "titulo": relatorio.titulo,
                    "periodo": relatorio.periodo,
                    "linhas": len(relatorio.linhas),
                    "resumo": relatorio.resumo,
                    "instrucao": (
                        "O relatorio ja esta na tela com os botoes de baixar. Diga isso em uma "
                        "frase. Cite no maximo 2 numeros e SOMENTE numeros que estao no resumo "
                        "acima; nenhum outro numero."
                    ),
                },
                relatorio,
            )
    except (ValidationError, ValueError, json.JSONDecodeError):
        return ResultadoDaFerramenta(
            {"erro": "argumentos invalidos para esta consulta; revise os campos e tente de novo"}
        )
    return ResultadoDaFerramenta({"erro": f"ferramenta desconhecida: {nome}"})
