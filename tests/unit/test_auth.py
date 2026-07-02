# Testes do decode de JWT (emitido pelo backend Go, validado aqui).

from datetime import timedelta

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.auth import decode_token
from tests.conftest import SEED_USER_ID, make_token


def test_token_valido_retorna_payload():
    token = make_token()
    payload = decode_token(token)
    assert payload.id_user == SEED_USER_ID


def test_token_expirado_levanta_401():
    token = make_token(expires_in=timedelta(hours=-1))
    with pytest.raises(HTTPException) as exc:
        decode_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token expired"


def test_token_malformado_levanta_401():
    with pytest.raises(HTTPException) as exc:
        decode_token("nao-e-um-jwt")
    assert exc.value.status_code == 401


def test_token_com_assinatura_errada_levanta_401():
    token = make_token(secret="outro-segredo")
    with pytest.raises(HTTPException) as exc:
        decode_token(token)
    assert exc.value.status_code == 401


def test_token_sem_id_user_levanta_401():
    from datetime import datetime, timezone

    exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    token = pyjwt.encode({"exp": exp}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        decode_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token payload"


def test_token_dentro_do_leeway_de_30s_e_aceito():
    # Go configura clock skew de 30s; expirado ha 10s ainda deve passar
    token = make_token(expires_in=timedelta(seconds=-10))
    payload = decode_token(token)
    assert payload.id_user == SEED_USER_ID
