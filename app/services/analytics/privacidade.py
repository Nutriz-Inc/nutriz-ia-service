import re

ETAPA_DO_EXAME = "Exame de sangue"
SITUACOES_QUE_REVELAM_EXAME = {"warn", "failed"}

SITUACAO_DA_ETAPA = {
    "pending": "pendente",
    "review": "em análise",
    "done": "concluída",
    "warn": "atenção",
    "failed": "reprovada",
}

SITUACAO_DA_ROTA = {
    "pending": "agendada",
    "in_progress": "em andamento",
    "done": "concluída",
    "error": "com erro",
    "canceled": "cancelada",
}

SITUACAO_DA_PARADA = {
    "pending": "não visitada",
    "in_progress": "em andamento",
    "done": "chegada registrada",
    "error": "imprevisto",
}

SITUACAO_DO_AGENDAMENTO = {
    "pending": "pendente",
    "done": "concluído",
    "failed": "não realizado",
}


def _digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def mascarar_cpf(cpf: str | None) -> str | None:
    digitos = _digitos(cpf)
    if len(digitos) != 11:
        return None
    return f"***.{digitos[3:6]}.***-**"


def mascarar_telefone(telefone: str | None) -> str | None:
    digitos = _digitos(telefone)
    if len(digitos) < 8:
        return None
    return f"(**) *****-{digitos[-4:]}"


def situacao_da_etapa(nome: str | None, status: str | None) -> str:
    if nome == ETAPA_DO_EXAME and status in SITUACOES_QUE_REVELAM_EXAME:
        return "aguardando retorno da equipe"
    return SITUACAO_DA_ETAPA.get(status or "", f"situação não reconhecida ({status})")


def traduzir(tabela: dict[str, str], valor: str | None) -> str:
    return tabela.get(valor or "", f"situação não reconhecida ({valor})")
