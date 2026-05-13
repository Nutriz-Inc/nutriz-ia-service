# Validação do JWT emitido pelo backend Go.
# Formato do payload: {id_user: str, exp: int} + claims registrados.
# Algoritmo: HS256.

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, ValidationError

from app.config import settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=True)


class TokenPayload(BaseModel):
    id_user: str
    exp: int


def decode_token(token: str) -> TokenPayload:
    try:
        raw = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            leeway=30,
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


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    payload = decode_token(token)
    return payload.id_user
