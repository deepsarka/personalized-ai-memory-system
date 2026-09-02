
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from database.models import User


async def register_user(
    db: AsyncSession,
    email: str,
    display_name: str,
    password: str,
) -> User:
    normalized_email = email.strip().lower()

    user = User(
        email=normalized_email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        role="user",
    )

    db.add(user)

    try:
        await db.commit()

    except IntegrityError as exc:
        await db.rollback()

        # The database-level UNIQUE constraint on users.email
        # prevents concurrent duplicate registrations.
        raise ValueError(
            "Email is already registered."
        ) from exc

    await db.refresh(user)

    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    normalized_email = email.strip().lower()

    user = await db.scalar(
        select(User).where(
            User.email == normalized_email
        )
    )

    if user is None:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    return user


def build_auth_response(user: User) -> dict:
    token = create_access_token(str(user.id))

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
    }

