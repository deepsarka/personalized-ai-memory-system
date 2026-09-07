from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
)
from auth.service import (
    authenticate_user,
    build_auth_response,
    register_user,
)
from database.connection import get_db


router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
)


@router.post(
    "/register",
    response_model=AuthResponse,
)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await register_user(
            db=db,
            email=request.email,
            display_name=request.display_name,
            password=request.password,
        )

        return build_auth_response(user)

    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e),
        )


@router.post(
    "/login",
    response_model=AuthResponse,
)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(
        db=db,
        email=request.email,
        password=request.password,
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )
    print("backend login successful for user:", user.email  )

    return build_auth_response(user)