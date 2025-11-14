from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger
from sqlmodel import delete, func, select

from owl.configs import ENV_CONFIG
from owl.db import AsyncSession, yield_async_session
from owl.db.models import (
    Organization,
    OrgMember,
    ProjectMember,
    User,
)
from owl.types import (
    ListQuery,
    OkResponse,
    Page,
    UserAuth,
    UserCreate,
    UserReadObscured,
    UserUpdate,
)
from owl.utils.auth import auth_service_key, auth_user_service_key, has_permissions
from owl.utils.dates import now
from owl.utils.exceptions import (
    ResourceExistsError,
    ResourceNotFoundError,
    handle_exception,
)

router = APIRouter()


async def _count_email(session: AsyncSession, email: str) -> int:
    return (await session.exec(select(func.count(User.id)).where(User.email == email))).one()


@router.post(
    "/v2/users",
    summary="Create a user.",
    description="Permissions: None.",
)
@handle_exception
async def create_user(
    request: Request,
    token: Annotated[str, Depends(auth_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    body: UserCreate,
) -> UserReadObscured:
    del token
    # Unless explicitly specified, create the first user with ID 0
    if (
        "id" not in body.model_dump(exclude_unset=True)
        and (await session.exec(select(func.count(User.id)))).one() == 0
    ):
        body.id = "0"
    # Check if user already exists
    if (await session.get(User, body.id)) is not None:
        raise ResourceExistsError(f'User "{body.id}" already exists.')
    if await _count_email(session, body.email) > 0:
        raise ResourceExistsError(f'User with email "{body.email}" already exists.')
    user = User.model_validate(body)
    # Auth0 handles email verification
    if ENV_CONFIG.auth0_api_key_plain:
        user.email_verified = True
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info(
        f"{request.state.id} - Created user: {user.model_dump(exclude={'password', 'password_hash'})}"
    )
    logger.bind(user_id=user.id).success(f"{user.name} ({user.email}) created their account.")
    user = await User.get(session, user.id, populate_existing=True)
    return user


@router.get(
    "/v2/users/list",
    summary="List users.",
    description="Permissions: `system.ADMIN`.",
)
@handle_exception
async def list_users(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListQuery, Query()],
) -> Page[UserReadObscured]:
    has_permissions(user, ["system.ADMIN"])
    return await User.list_(
        session=session,
        return_type=UserReadObscured,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        after=params.after,
    )


@router.get(
    "/v2/users",
    summary="Get current user or a specific user.",
    description=(
        "Permissions: `system.ADMIN`. "
        "Permissions are only needed if the queried user is not the current logged-in user."
    ),
)
@handle_exception
async def get_user(
    _user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    user_id: Annotated[
        str | None, Query(description="User ID. If not provided, the logged-in user is returned.")
    ] = None,
) -> UserReadObscured:
    if (not user_id) or (user_id == _user.id):
        return await User.get(session, _user.id, populate_existing=True)
    if _user.id != user_id:
        has_permissions(_user, ["system.ADMIN"])
    return await User.get(session, user_id)


@router.patch(
    "/v2/users",
    summary="Update the current logged-in user.",
    description="Permissions: None.",
)
@handle_exception
async def update_user(
    *,
    _user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    body: UserUpdate,
) -> UserReadObscured:
    user = await User.get(session, _user.id)
    if user is None:
        raise ResourceNotFoundError(f'User "{_user.id}" is not found.')
    # Perform update
    updates = body.model_dump(exclude={"id"}, exclude_unset=True)
    for key, value in updates.items():
        if key == "email" and body.email != user.email:
            if await _count_email(session, body.email) > 0:
                raise ResourceExistsError(f'User with email "{body.email}" already exists.')
            user.email_verified = False
        setattr(user, key, value)
    user.updated_at = now()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.bind(user_id=user.id).success(
        (
            f"{user.name} ({user.email}) updated the attributes "
            f"{list(updates.keys())} of their user account."
        )
    )
    return user


@router.delete(
    "/v2/users",
    summary="Delete a user.",
    description="Permissions: None.",
)
@handle_exception
async def delete_user(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
) -> OkResponse:
    user = await session.get(User, user.id)
    if user is None:
        raise ResourceNotFoundError(f'User "{user.id}" is not found.')
    org_ids = [m.organization_id for m in user.org_memberships]
    # Delete all related resources
    logger.info(f'{request.state.id} - Deleting user: "{user.id}"')
    await session.exec(delete(OrgMember).where(OrgMember.user_id == user.id))
    await session.exec(delete(ProjectMember).where(ProjectMember.user_id == user.id))
    if ENV_CONFIG.is_cloud:
        from owl.db.models.cloud import ProjectKey, VerificationCode

        await session.exec(delete(ProjectKey).where(ProjectKey.user_id == user.id))
        await session.exec(
            delete(VerificationCode).where(VerificationCode.user_email == user.email)
        )
    await session.delete(user)
    await session.commit()
    # Delete organizations if the user was the last member
    logger.info(f"{request.state.id} - Inspecting organizations: {org_ids}")
    for org_id in org_ids:
        member_count = (
            await session.exec(
                select(func.count(OrgMember.user_id)).where(OrgMember.organization_id == org_id)
            )
        ).one()
        if member_count > 0:
            continue
        try:
            await session.exec(delete(Organization).where(Organization.id == org_id))
            await session.commit()
            logger.info(f'{request.state.id} - Deleting empty organization "{org_id}"')
        except Exception as e:
            logger.warning(f'Failed to delete organization "{org_id}" due to {repr(e)}')
    logger.bind(user_id=user.id).success(f"{user.name} ({user.email}) deleted their account.")
    return OkResponse()
