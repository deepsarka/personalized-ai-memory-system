
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()


JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = max(
    5,
    int(
        os.getenv(
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            "60",
        )
    ),
)


def _load_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")

    if not secret:
        raise RuntimeError(
            "JWT_SECRET must be configured."
        )

    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError(
            "JWT_SECRET must contain at least 32 bytes."
        )

    return secret


JWT_SECRET = _load_jwt_secret()


def hash_password(
    password: str,
) -> str:
    return password_hash.hash(password)


def verify_password(
    password: str,
    hashed_password: str,
) -> bool:
    try:
        return password_hash.verify(
            password,
            hashed_password,
        )
    except Exception:
        return False


def create_access_token(
    user_id: str,
) -> str:
    now = datetime.now(timezone.utc)

    expires_at = (
        now
        + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
        "jti": secrets.token_urlsafe(16),
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(
    token: str,
) -> str:
    payload = jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        options={
            "require": [
                "sub",
                "exp",
            ],
        },
    )

    user_id = payload.get("sub")

    if not isinstance(user_id, str) or not user_id:
        raise ValueError(
            "Token does not contain a valid user identity."
        )

    return user_id

