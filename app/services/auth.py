# TODO Leo: confirmar com o backend Go o formato do payload do JWT.
# Suposição atual: {"user_id": str, "phone": str, "exp": int}.
# Algoritmo: HS256.

from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, ValidationError

from app.config import settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=True)


class TokenPayload(BaseModel):
    user_id: UUID
    phone: str
    exp: int


def decode_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    try:
        return TokenPayload(**raw)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> UUID:
    payload = decode_token(token)
    return payload.user_id
