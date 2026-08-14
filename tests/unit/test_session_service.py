# Testes do servico de sessao anonima do modo publico.

import jwt as pyjwt

from app.config import settings
from app.services import session_service


def test_cria_token_anonimo_valido():
    session = session_service.create_anonymous_session()
    raw = pyjwt.decode(
        session.token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
    assert raw["anon"] is True
    assert raw["session_id"] == session.session_id
    assert "id_user" not in raw
    assert session.expires_in == settings.ANON_SESSION_TTL_MINUTES * 60


def test_decode_aceita_token_anonimo():
    session = session_service.create_anonymous_session()
    payload = session_service.decode_anonymous_session(session.token)
    assert payload is not None
    assert payload.session_id == session.session_id


def test_decode_rejeita_token_de_nutriz_logada():
    # Token com id_user e sem anon=true nao pode ser aceito no modo publico
    token = pyjwt.encode(
        {"id_user": "abc", "exp": 9999999999},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert session_service.decode_anonymous_session(token) is None


def test_decode_rejeita_token_expirado():
    token = pyjwt.encode(
        {"anon": True, "session_id": "x", "exp": 1},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert session_service.decode_anonymous_session(token) is None


def test_decode_rejeita_assinatura_errada():
    token = pyjwt.encode(
        {"anon": True, "session_id": "x", "exp": 9999999999},
        "secret-errado",
        algorithm=settings.JWT_ALGORITHM,
    )
    assert session_service.decode_anonymous_session(token) is None


def test_hash_ip_nao_expoe_ip_em_claro():
    h = session_service.hash_ip("203.0.113.7")
    assert "203.0.113.7" not in h
    assert len(h) == 64
    # Deterministico: mesmo IP, mesmo hash
    assert h == session_service.hash_ip("203.0.113.7")
