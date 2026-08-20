# Servico de contexto de doacao da nutriz para a EVA (modo logado).
#
# Le as tabelas espelhadas do backend Go (donation, donation_step, address,
# donation_point). READ-ONLY - nunca escreve.
#
# ============================================================================
# LIMITE INVIOLAVEL - DADO SENSIVEL DE SAUDE
# ============================================================================
# O contexto montado aqui vai para o prompt da Groq (terceiro) e fica gravado
# no llm_audit, que e append-only e imutavel. Por isso NENHUM dado de saude
# pode passar por aqui:
#   - donation_step.description e donation_step_timeline.description sao texto
#     livre escrito por adm ("sorologia reagente", "inapta por ..."): as colunas
#     nao sao nem mapeadas no ORM, entao nao ha como vazarem por descuido.
#   - donation.user_feedback e a tabela job (texto livre) tambem ficam de fora.
#   - a etapa "Exame de sangue" com status failed/warn revela por inferencia o
#     resultado da sorologia; esse status e MASCARADO (ver _status_label).
# Sai daqui apenas: identificador, nome de etapa, status tratado, datas e local.
# ============================================================================

import logging
from decimal import Decimal
from typing import Awaitable, Callable, TypeVar

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Address, Donation, DonationPoint, DonationStep
from app.schemas.donation import (
    ActiveDonation,
    CollectionPlace,
    DonationContext,
    DonationHistory,
)


logger = logging.getLogger(__name__)

T = TypeVar("T")

# Ordem canonica das etapas (enum enum_donation_steps do Go). A etapa atual e a
# primeira desta ordem que ainda nao esta concluida - mesmo criterio que a tela
# de acompanhamento do app usa, para a EVA nunca divergir do que a nutriz ve.
STEP_ORDER: tuple[str, ...] = (
    "Exame de sangue",
    "Entregar kit de ordenha",
    "Coletar leite",
    "Análise de leite",
)

STATUS_DONE = "done"

_STATUS_LABELS: dict[str, str] = {
    "pending": "pendente",
    "review": "em analise",
    "done": "concluida",
    "warn": "com pendencia",
    "failed": "nao aprovada",
}

# Etapa cujo status revela desfecho de exame: os status negativos viram um
# rotulo neutro antes de sair do servico.
_CLINICAL_STEP = "Exame de sangue"
_MASKED_STATUSES = frozenset({"warn", "failed"})
_MASKED_LABEL = "aguardando retorno da equipe Lactare"


def _status_label(step_name: str, status: str | None) -> str | None:
    if status is None:
        return None
    if step_name == _CLINICAL_STEP and status in _MASKED_STATUSES:
        return _MASKED_LABEL
    return _STATUS_LABELS.get(status, "em andamento")


def _next_step_name(current_step_name: str | None) -> str | None:
    if current_step_name is None or current_step_name not in STEP_ORDER:
        return None
    index = STEP_ORDER.index(current_step_name)
    if index + 1 >= len(STEP_ORDER):
        return None
    return STEP_ORDER[index + 1]


async def _safe(
    db: AsyncSession,
    loader: Callable[[AsyncSession, str], Awaitable[T | None]],
    id_user: str,
    bloco: str,
) -> T | None:
    # Cada bloco de dado e independente: uma falha aqui degrada SO esse bloco,
    # nunca derruba o WebSocket. O rollback e obrigatorio - sem ele a sessao
    # fica em transacao abortada e as queries seguintes do mesmo turno (o outro
    # bloco, o historico de mensagens, o RAG, a persistencia) falhariam junto.
    try:
        return await loader(db, id_user)
    except Exception:
        logger.exception(
            f"Falha ao ler {bloco} de doacao para id_user={id_user}; "
            "seguindo sem esse bloco de contexto"
        )
        await db.rollback()
        return None


def _donations_of_user(id_user: str) -> Select:
    # ATENCAO: a tabela donation NAO tem id_user - o dono e created_by (mesma
    # regra do backend Go). removed_at trata o soft delete.
    return select(Donation).where(
        and_(Donation.created_by == id_user, Donation.removed_at.is_(None))
    )


async def _load_current_donation(
    db: AsyncSession, id_user: str
) -> ActiveDonation | None:
    # Prefere a doacao ativa (o Go permite no maximo uma); sem ativa, cai na
    # mais recente, para responder "qual foi o ponto de coleta da minha ultima
    # doacao" mesmo com o processo ja encerrado.
    result = await db.execute(
        _donations_of_user(id_user)
        .order_by(Donation.is_active.desc(), Donation.created_at.desc())
        .limit(1)
    )
    donation = result.scalar_one_or_none()
    if donation is None:
        return None

    steps_result = await db.execute(
        select(DonationStep)
        .where(DonationStep.id_donation == donation.id_donation)
        .order_by(DonationStep.created_at)
    )
    steps = list(steps_result.scalars().all())
    steps_by_name = {step.name: step for step in steps}

    current_step: DonationStep | None = None
    current_step_name: str | None = None
    for name in STEP_ORDER:
        step = steps_by_name.get(name)
        if step is None or step.status != STATUS_DONE:
            current_step_name = name
            current_step = step
            break

    place = await _load_place(db, current_step, steps)

    return ActiveDonation(
        id_donation=donation.id_donation,
        is_active=donation.is_active,
        created_at=donation.created_at,
        current_step_name=current_step_name,
        current_step_status_label=_status_label(
            current_step_name or "", current_step.status if current_step else None
        ),
        current_step_set_date=current_step.set_date if current_step else None,
        next_step_name=_next_step_name(current_step_name),
        place=place,
    )


async def _load_place(
    db: AsyncSession,
    current_step: DonationStep | None,
    steps: list[DonationStep],
) -> CollectionPlace | None:
    # Local da etapa atual; se ela ainda nao tem endereco definido, usa o da
    # ultima etapa que teve (e onde a nutriz esteve por ultimo).
    id_address = current_step.id_address if current_step else None
    if id_address is None:
        for step in reversed(steps):
            if step.id_address is not None:
                id_address = step.id_address
                break
    if id_address is None:
        return None

    result = await db.execute(
        select(
            Address.neighborhood,
            Address.city,
            Address.state,
            DonationPoint.name,
        )
        .select_from(Address)
        .outerjoin(
            DonationPoint,
            DonationPoint.id_donation_point == Address.id_donation_point,
        )
        .where(Address.id_address == id_address)
    )
    row = result.first()
    if row is None:
        return None

    return CollectionPlace(
        donation_point_name=row.name,
        neighborhood=row.neighborhood,
        city=row.city,
        state=row.state,
    )


async def _load_history(db: AsyncSession, id_user: str) -> DonationHistory:
    # Agregado em uma unica query. O total vem da soma de
    # donation.quantity_donated, e nao de user.milk_donated: essa coluna so e
    # escrita pelo seed do Go, nenhum handler a mantem atualizada.
    result = await db.execute(
        select(
            func.count(Donation.id_donation),
            func.count(Donation.id_donation).filter(Donation.is_active.is_(False)),
            func.sum(Donation.quantity_donated),
            func.max(Donation.created_at),
        ).where(and_(Donation.created_by == id_user, Donation.removed_at.is_(None)))
    )
    total, concluded, volume, last_at = result.one()

    return DonationHistory(
        total_donations=total or 0,
        concluded_donations=concluded or 0,
        total_volume_ml=Decimal(volume) if volume is not None else None,
        last_donation_at=last_at,
    )


async def get_donation_context(db: AsyncSession, id_user: str) -> DonationContext:
    # Buscado UMA vez por sessao de chat (junto do perfil), nunca por mensagem.
    # Sempre retorna um DonationContext: os blocos que falharem vem como None e
    # simplesmente nao entram no prompt.
    donation = await _safe(db, _load_current_donation, id_user, "doacao atual")
    history = await _safe(db, _load_history, id_user, "historico")
    return DonationContext(donation=donation, history=history)
