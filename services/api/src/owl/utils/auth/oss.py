from secrets import compare_digest
from time import perf_counter
from typing import Annotated, AsyncGenerator

from fastapi import BackgroundTasks, Depends, Header, Request
from loguru import logger

from owl.configs import ENV_CONFIG
from owl.db import async_session
from owl.db.models.oss import ModelConfig, Project, User
from owl.types import (
    ModelConfigRead,
    OrganizationRead,
    ProjectRead,
    UserAuth,
)
from owl.utils.billing import BillingManager
from owl.utils.dates import now
from owl.utils.exceptions import AuthorizationError, ResourceNotFoundError

WRITE_METHODS = {"PUT", "PATCH", "POST", "DELETE", "PURGE"}
NO_USER_ID_MESSAGE = (
    'You didn\'t provide a user ID. You need to provide the user ID in an "X-USER-ID" header.'
)
NO_PROJECT_ID_MESSAGE = (
    "You didn't provide a project ID. "
    'You need to provide the project ID in an "X-PROJECT-ID" header.'
)
NO_TOKEN_MESSAGE = (
    "You didn't provide an authorization token. "
    'You need to provide your PAT in an "Authorization" header using Bearer auth (i.e. "Authorization: Bearer TOKEN").'
)
INVALID_TOKEN_MESSAGE = "You provided an invalid authorization token."


def is_service_key(token: str) -> bool:
    return compare_digest(token, ENV_CONFIG.service_key_plain) or compare_digest(
        token, ENV_CONFIG.service_key_alt_plain
    )


async def auth_service_key(
    bearer_token: Annotated[
        str, Header(alias="Authorization", description="Not needed for OSS.")
    ] = "",
) -> str:
    return bearer_token


async def _bearer_auth(
    user_id: Annotated[str, Header(alias="X-USER-ID", description="User ID.")] = "",
) -> tuple[UserAuth, None]:
    if user_id == "":
        user_id = "0"
    async with async_session() as session:
        user = await session.get(User, user_id)
    if user is None:
        raise AuthorizationError(f'User "{user_id}" is not found.')
    user = UserAuth.model_validate(user)
    return user, None


async def auth_user_service_key(
    request: Request,
    user_project: Annotated[tuple[UserAuth, None], Depends(_bearer_auth)],
) -> AsyncGenerator[UserAuth, None]:
    t0 = perf_counter()
    user = user_project[0]
    t1 = perf_counter()
    request.state.timing["Auth"] = t1 - t0
    yield user
    request.state.timing["Request"] = perf_counter() - t1


auth_user = auth_user_service_key


async def _set_project_updated_at(
    request: Request,
    project_id: str,
) -> None:
    if "gen_tables" in request.url.path and request.method in WRITE_METHODS:
        try:
            async with async_session() as session:
                project = await session.get(Project, project_id)
                if project is None:
                    raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
                project.updated_at = now()
                session.add(project)
                await session.commit()
        except Exception as e:
            logger.warning(
                f'{request.state.id} - Error setting project "{project_id}" last updated time: {e}'
            )


async def auth_user_project(
    request: Request,
    bg_tasks: BackgroundTasks,
    user_project: Annotated[tuple[UserAuth, None], Depends(_bearer_auth)],
    project_id: Annotated[
        str, Header(alias="X-PROJECT-ID", description="Project ID.")
    ] = "default",
) -> AsyncGenerator[tuple[UserAuth, ProjectRead, OrganizationRead], None]:
    t0 = perf_counter()
    user, project = user_project
    ### --- Fetch project --- ###
    async with async_session() as session:
        proj = await session.get(Project, project_id)
        if proj is None:
            raise AuthorizationError(f'Project "{project_id}" is not found.')
        project = ProjectRead.model_validate(proj)
        organization = OrganizationRead.model_validate(proj.organization)
        models = (
            await ModelConfig.list_(
                session=session,
                return_type=ModelConfigRead,
                organization_id=organization.id,
            )
        ).items
    ### --- Billing --- ###
    request.state.billing = BillingManager(
        organization=organization,
        project_id=project.id,
        user_id=user.id,
        request=request,
        models=models,
    )
    t1 = perf_counter()
    request.state.timing["Auth"] = t1 - t0
    yield user, project, organization
    request.state.timing["Request"] = perf_counter() - t1
    # This will run BEFORE any responses are sent

    # Background tasks will run AFTER streaming responses are sent
    bg_tasks.add_task(
        _set_project_updated_at,
        request=request,
        project_id=project_id,
    )


def has_permissions(
    user: UserAuth,
    requirements: list[str],
    *,
    organization_id: str | None = None,
    project_id: str | None = None,
    raise_error: bool = True,
) -> bool:
    del user
    del requirements
    del organization_id
    del project_id
    del raise_error
    return True
