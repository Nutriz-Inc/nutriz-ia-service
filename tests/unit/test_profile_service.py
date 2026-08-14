# Testes do servico de perfil consolidado (user + user_baby + address).

from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.profile_service import _describe_baby_age, get_nutriz_profile
from tests.conftest import SEED_USER_NAME


async def test_perfil_completo_com_bebe_e_endereco(
    db_session: AsyncSession, seed_baby_and_address: str
):
    profile = await get_nutriz_profile(db_session, seed_baby_and_address)
    assert profile is not None
    assert profile.name == SEED_USER_NAME
    assert profile.baby is not None
    assert profile.baby.name == "Joao"
    assert profile.baby.age_in_days in (119, 120, 121)
    assert "meses" in profile.baby.age_description
    assert profile.address is not None
    assert profile.address.neighborhood == "Vila Mariana"
    assert profile.address.city == "Sao Paulo"


async def test_usuario_sem_bebe_retorna_perfil_degradado(
    db_session: AsyncSession, seed_user: str
):
    profile = await get_nutriz_profile(db_session, seed_user)
    assert profile is not None
    assert profile.name == SEED_USER_NAME
    assert profile.baby is None
    assert profile.address is None


async def test_usuario_inexistente_retorna_none(db_session: AsyncSession, test_engine):
    profile = await get_nutriz_profile(db_session, "00000000-0000-0000-0000-000000000000")
    assert profile is None


def test_descricao_de_idade_do_bebe_por_faixa():
    assert "colostro" in _describe_baby_age(3)
    assert "transicao" in _describe_baby_age(10)
    assert "fase ideal de doacao" in _describe_baby_age(120)
    assert "atencao aos criterios" in _describe_baby_age(200)
    assert "amamentacao prolongada" in _describe_baby_age(400)


async def test_falha_na_leitura_do_perfil_degrada_sem_derrubar():
    # Qualquer erro ao ler o perfil (ex.: coluna inexistente no schema real do
    # Go, banco indisponivel) deve degradar para None + rollback da sessao, nunca
    # propagar e derrubar o chat. O rollback evita deixar a sessao em transacao
    # abortada, o que faria as queries seguintes do turno tambem falharem.
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = Exception("column address.updated_by does not exist")

    profile = await get_nutriz_profile(db, "f058115f-51cb-4eb6-b7b9-7e2397299641")

    assert profile is None
    db.rollback.assert_awaited_once()
