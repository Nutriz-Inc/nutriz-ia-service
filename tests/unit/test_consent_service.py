# Testes do servico de validacao de consentimento LGPD.

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.consent_service import get_latest_consent_version, has_valid_consent


async def test_usuario_com_consent_valido(db_session: AsyncSession, seed_consent: str):
    assert await has_valid_consent(db_session, seed_consent) is True


async def test_usuario_sem_consent(db_session: AsyncSession, seed_user: str):
    assert await has_valid_consent(db_session, seed_user) is False


async def test_usuario_inexistente_nao_tem_consent(db_session: AsyncSession, test_engine):
    assert await has_valid_consent(db_session, "00000000-0000-0000-0000-000000000000") is False


async def test_versao_dos_termos_do_consent(db_session: AsyncSession, seed_consent: str):
    version = await get_latest_consent_version(db_session, seed_consent)
    assert version == "v1.0"


async def test_versao_none_sem_consent(db_session: AsyncSession, seed_user: str):
    version = await get_latest_consent_version(db_session, seed_user)
    assert version is None
