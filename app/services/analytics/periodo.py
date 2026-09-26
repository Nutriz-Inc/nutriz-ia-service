from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

FUSO_BRASILIA = timezone(timedelta(hours=-3), "BRT")

PRESETS = (
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
)

MESES = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)


def hoje_em_brasilia(agora: datetime | None = None) -> date:
    referencia = agora or datetime.now(timezone.utc)
    return referencia.astimezone(FUSO_BRASILIA).date()


def agora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def para_utc_ingenuo(dia: date) -> datetime:
    local = datetime.combine(dia, time.min, tzinfo=FUSO_BRASILIA)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def formatar_data(dia: date) -> str:
    return f"{dia.day:02d} {MESES[dia.month - 1]} {dia.year}"


@dataclass(frozen=True)
class Periodo:
    inicio: date | None
    fim: date | None
    rotulo: str

    @property
    def inicio_utc(self) -> datetime | None:
        return para_utc_ingenuo(self.inicio) if self.inicio else None

    @property
    def fim_utc(self) -> datetime | None:
        return para_utc_ingenuo(self.fim + timedelta(days=1)) if self.fim else None

    def descrever(self) -> dict[str, str | None]:
        return {
            "rotulo": self.rotulo,
            "inicio": self.inicio.isoformat() if self.inicio else None,
            "fim": self.fim.isoformat() if self.fim else None,
        }


def _primeiro_do_mes(dia: date) -> date:
    return dia.replace(day=1)


def _meses_atras(dia: date, meses: int) -> date:
    ano = dia.year + (dia.month - 1 - meses) // 12
    mes = (dia.month - 1 - meses) % 12 + 1
    return date(ano, mes, 1)


def _intervalo(inicio: date, fim: date) -> str:
    if inicio == fim:
        return formatar_data(inicio)
    return f"{formatar_data(inicio)} a {formatar_data(fim)}"


def resolver_periodo(
    preset: str | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    hoje: date | None = None,
) -> Periodo:
    dia = hoje or hoje_em_brasilia()

    if inicio or fim:
        inicio_real = inicio or date(2000, 1, 1)
        fim_real = fim or dia
        if fim_real < inicio_real:
            inicio_real, fim_real = fim_real, inicio_real
        return Periodo(inicio_real, fim_real, _intervalo(inicio_real, fim_real))

    escolha = preset or "mes_atual"

    if escolha == "hoje":
        return Periodo(dia, dia, f"hoje ({formatar_data(dia)})")
    if escolha == "ontem":
        ontem = dia - timedelta(days=1)
        return Periodo(ontem, ontem, f"ontem ({formatar_data(ontem)})")
    if escolha == "ultimos_7_dias":
        inicio_real = dia - timedelta(days=6)
        return Periodo(inicio_real, dia, f"últimos 7 dias ({_intervalo(inicio_real, dia)})")
    if escolha == "ultimos_30_dias":
        inicio_real = dia - timedelta(days=29)
        return Periodo(inicio_real, dia, f"últimos 30 dias ({_intervalo(inicio_real, dia)})")
    if escolha == "mes_anterior":
        fim_real = _primeiro_do_mes(dia) - timedelta(days=1)
        inicio_real = _primeiro_do_mes(fim_real)
        return Periodo(inicio_real, fim_real, f"mês anterior ({_intervalo(inicio_real, fim_real)})")
    if escolha == "ultimos_3_meses":
        inicio_real = _meses_atras(dia, 2)
        return Periodo(inicio_real, dia, f"últimos 3 meses ({_intervalo(inicio_real, dia)})")
    if escolha == "ultimos_6_meses":
        inicio_real = _meses_atras(dia, 5)
        return Periodo(inicio_real, dia, f"últimos 6 meses ({_intervalo(inicio_real, dia)})")
    if escolha == "ano_atual":
        inicio_real = date(dia.year, 1, 1)
        return Periodo(inicio_real, dia, f"ano de {dia.year} ({_intervalo(inicio_real, dia)})")
    if escolha == "tudo":
        return Periodo(None, None, "todo o histórico")

    inicio_real = _primeiro_do_mes(dia)
    return Periodo(inicio_real, dia, f"mês atual ({_intervalo(inicio_real, dia)})")
