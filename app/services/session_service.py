# Sessao anonima do modo publico.
# Emite e valida um session token curto (JWT com anon=true + session_id),
# sem id_user. Mesma secret/algoritmo do JWT do backend Go, mas o claim
# anon=true e obrigatorio para distinguir de um token de nutriz logada.

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pydantic import BaseModel, ValidationError

from app.config import settings


class AnonSessionToken(BaseModel):
    token: str
    session_id: str
    expires_in: int


class AnonSessionPayload(BaseModel):
    anon: bool
    session_id: str
    exp: int


def create_anonymous_session() -> AnonSessionToken:
    session_id = str(uuid.uuid4())
    ttl_seconds = settings.ANON_SESSION_TTL_MINUTES * 60
    exp = int((datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).timestamp())
    token = jwt.encode(
        {"anon": True, "session_id": session_id, "exp": exp},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return AnonSessionToken(token=token, session_id=session_id, expires_in=ttl_seconds)


def decode_anonymous_session(token: str) -> AnonSessionPayload | None:
    try:
        raw = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            leeway=30,
        )
    except jwt.InvalidTokenError:
        return None

    try:
        payload = AnonSessionPayload(**raw)
    except ValidationError:
        return None

    # Token de nutriz logada (sem anon=true) nao pode ser aceito aqui
    if payload.anon is not True:
        return None
    return payload


def hash_ip(ip: str) -> str:
    # IP nunca e persistido em claro (LGPD). Hash com a secret como sal para
    # nao permitir enumeracao por dicionario de IPs.
    salted = f"{ip}:{settings.JWT_SECRET}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()
