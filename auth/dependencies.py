from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import decode_access_token
from database.connection import get_db
from database.models import User


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:

    token = credentials.credentials

    try:
        user_id = decode_access_token(token)
        user_uuid = UUID(user_id)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token.",
        )

    user = await db.scalar(
        select(User).where(User.id == user_uuid)
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User no longer exists.",
        )

    return user