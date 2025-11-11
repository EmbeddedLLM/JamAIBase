from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pwdlib import PasswordHash
from sqlmodel import select

from owl.db import AsyncSession, yield_async_session
from owl.db.models import User
from owl.types import (
    PasswordChangeRequest,
    PasswordLoginRequest,
    UserAuth,
    UserCreate,
    UserReadObscured,
)
from owl.utils.auth import auth_user_service_key
from owl.utils.exceptions import (
    AuthorizationError,
    ForbiddenError,
    ResourceNotFoundError,
    handle_exception,
)

router = APIRouter()


@router.post("/v2/auth/register/password", summary="Register with email and password.")
@handle_exception
async def register_password(
    request: Request,
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    body: UserCreate,
) -> UserReadObscured:
    from owl.routers.users.oss import create_user

    return await create_user(request=request, token="", session=session, body=body)


@router.post("/v2/auth/login/password", summary="Login with email and password.")
@handle_exception
async def login_password(
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    body: PasswordLoginRequest,
) -> UserReadObscured:
    user = (await session.exec(select(User).where(User.email == body.email))).one_or_none()
    if user:
        password_hash, updated_hash = user.password_hash, None
        if password_hash is None:
            raise AuthorizationError("Invalid password.")
        hasher = PasswordHash.recommended()
        password_match, updated_hash = hasher.verify_and_update(body.password, user.password_hash)
        if password_match:
            if updated_hash is not None:
                user.password_hash = updated_hash
                session.add(user)
                await session.commit()
                await session.refresh(user)
        else:
            raise AuthorizationError("Invalid password.")
    else:
        raise AuthorizationError("User not found.")
    user = await User.get(session, user.id, populate_existing=True)
    return user


@router.patch("/v2/auth/login/password", summary="Change password.")
@handle_exception
async def change_password(
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    _user: Annotated[UserAuth, Depends(auth_user_service_key)],
    body: PasswordChangeRequest,
) -> UserReadObscured:
    if _user.email != body.email:
        raise ForbiddenError("You can only update your own account.")
    # Re-fetch user to set `password_hash`
    user = await User.get(session, _user.id)
    if user is None:
        raise ResourceNotFoundError(f'User "{_user.id}" is not found.')
    password_hash, updated_hash = user.password_hash, None
    hasher = PasswordHash.recommended()
    password_match = hasher.verify(body.password, password_hash)
    if password_match:
        updated_hash = hasher.hash(body.new_password)
        user.password_hash = updated_hash
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        raise AuthorizationError("Invalid existing password.")
    return user
