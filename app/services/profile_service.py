# Servico de consulta consolidada do perfil da nutriz.
# Faz join entre as tabelas espelhadas do backend Go (user, user_baby, address).
# Tabelas sao READ-ONLY no python - nunca escreve, apenas le.

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Address, User, UserBaby
from app.schemas.profile import AddressProfile, BabyProfile, NutrizProfile


logger = logging.getLogger(__name__)

# Papeis de staff Lactare: usam painel administrativo, nunca o chat da EVA.
# O gate de UI no front nao basta - um token valido permitiria conectar
# direto no WebSocket, entao o bloqueio precisa existir no backend.
STAFF_USER_TYPES = frozenset({"adm", "nurse"})


async def get_user_type(db: AsyncSession, id_user: str) -> str | None:
    result = await db.execute(
        select(User.type).where(User.id_user == id_user)
    )
    return result.scalar_one_or_none()


def _describe_baby_age(age_in_days: int) -> str:
    if age_in_days < 7:
        return f"recem-nascido ({age_in_days} dias) - fase de colostro"
    if age_in_days < 15:
        return f"{age_in_days} dias - fase de leite de transicao"
    if age_in_days < 180:
        meses = age_in_days // 30
        return f"{meses} meses - leite maduro, fase ideal de doacao"
    if age_in_days < 365:
        meses = age_in_days // 30
        return f"{meses} meses - leite maduro, atencao aos criterios de doacao"
    anos = age_in_days // 365
    return f"{anos} ano(s) - amamentacao prolongada"


async def get_nutriz_profile(
    db: AsyncSession,
    id_user: str,
) -> NutrizProfile | None:
    user_result = await db.execute(
        select(User).where(User.id_user == id_user)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        logger.warning(f"Perfil nao encontrado para id_user={id_user}")
        return None

    baby_result = await db.execute(
        select(UserBaby)
        .where(
            and_(
                UserBaby.id_user == id_user,
                UserBaby.removed_at.is_(None),
            )
        )
        .order_by(UserBaby.birth_date.desc())
        .limit(1)
    )
    baby_row = baby_result.scalar_one_or_none()

    baby_profile: BabyProfile | None = None
    if baby_row is not None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age_in_days = (now - baby_row.birth_date).days
        baby_profile = BabyProfile(
            id_user_baby=baby_row.id_user_baby,
            name=baby_row.name,
            birth_date=baby_row.birth_date,
            age_in_days=age_in_days,
            age_description=_describe_baby_age(age_in_days),
        )

    address_result = await db.execute(
        select(Address)
        .where(
            and_(
                Address.id_user == id_user,
                Address.id_donation_point.is_(None),
                Address.removed_at.is_(None),
            )
        )
        .limit(1)
    )
    address_row = address_result.scalar_one_or_none()

    address_profile: AddressProfile | None = None
    if address_row is not None:
        address_profile = AddressProfile(
            zipcode=address_row.zipcode,
            city=address_row.city,
            state=address_row.state,
            neighborhood=address_row.neighborhood,
        )

    return NutrizProfile(
        id_user=user.id_user,
        name=user.name,
        baby=baby_profile,
        address=address_profile,
    )
