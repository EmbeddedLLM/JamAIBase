from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger
from sqlmodel import select

from owl.configs import ENV_CONFIG
from owl.db import AsyncSession, yield_async_session
from owl.db.models import Project, Secret
from owl.types import (
    ListQueryByOrg,
    OkResponse,
    Page,
    SecretCreate,
    SecretRead,
    SecretUpdate,
    UserAuth,
)
from owl.utils.auth import auth_user_service_key, has_permissions
from owl.utils.crypt import encrypt_random
from owl.utils.exceptions import (
    BadInputError,
    ResourceExistsError,
    ResourceNotFoundError,
    handle_exception,
)
from owl.utils.mcp import MCP_TOOL_TAG

router = APIRouter()


@router.post(
    "/v2/secrets",
    summary="Create an organization secret.",
    description="Permissions: `organization.ADMIN`.",
    tags=[MCP_TOOL_TAG, "organization.ADMIN"],
)
@handle_exception
async def create_secret(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    organization_id: Annotated[str, Query(description="Organization ID.")],
    body: SecretCreate,
) -> SecretRead:
    """Create a new secret.

    Secrets are scoped to the specified organization.
    Only organization admins can create secrets. Secret names are normalized to uppercase.

    Args:
        request (Request): The FastAPI request object.
        user (UserAuth): Authenticated user information.
        session (AsyncSession): Database session.
        organization_id (str): Organization ID.
        body (SecretCreate): Secret creation data.

    Returns:
        secret (SecretRead): Created secret details.

    Raises:
        BadInputError: If secret name is empty.
        ResourceExistsError: If secret with the same name already exists.
    """
    has_permissions(user, ["organization.ADMIN"], organization_id=organization_id)

    # Convert name to uppercase and validate
    normalized_name = body.name.upper()
    if not normalized_name:
        raise BadInputError("Secret name cannot be empty")

    # Check for existing secret with composite key (organization_id, name)
    if (await session.get(Secret, (organization_id, normalized_name))) is not None:
        raise ResourceExistsError(f'Secret "{normalized_name}" already exists.')

    # Remove duplicates from allowed_projects
    if body.allowed_projects is not None and len(body.allowed_projects) > 0:
        body.allowed_projects = list(set(body.allowed_projects))

    # Verify allowed_projects exist in the organization
    if body.allowed_projects is not None and len(body.allowed_projects) > 0:
        statement = select(Project.id).where(
            Project.organization_id == organization_id,
            Project.id.in_(body.allowed_projects),
        )
        existing_projects = (await session.exec(statement)).all()
        if len(existing_projects) != len(body.allowed_projects):
            non_exist_projects = set(body.allowed_projects) - set(existing_projects)
            raise ResourceNotFoundError(f"Projects not found: {', '.join(non_exist_projects)}")

    # Create new secret
    secret = Secret(
        organization_id=organization_id,
        name=normalized_name,
        value=encrypt_random(body.value, ENV_CONFIG.encryption_key_plain),
        allowed_projects=body.allowed_projects,  # None: all projects; []: no projects
    )
    session.add(secret)
    await session.commit()
    await session.refresh(secret)

    logger.bind(user_id=user.id).success(
        f'{user.name} ({user.email}) created secret "{secret.name}". ({request.state.id})'
    )
    return secret.to_read()


@router.get(
    "/v2/secrets/list",
    summary="List organization secrets.",
    description="Permissions: `organization.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER"],
)
@handle_exception
async def list_secrets(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListQueryByOrg, Query()],
) -> Page[SecretRead]:
    """List secrets with pagination and filtering.

    Secrets are filtered based on the specified organization_id.
    All users (both ADMIN and MEMBER roles) see only secrets scoped to their organization.
    Secret values are masked in the response.

    Args:
        user (UserAuth): Authenticated user information.
        session (AsyncSession): Database session.
        params (ListQueryByOrg): Query parameters for pagination and filtering.

    Returns:
        secrets (Page[SecretRead]): Paginated list of secrets with masked values.
    """
    # Both ADMIN and MEMBER roles can list secrets
    organization_id = params.organization_id

    has_permissions(user, ["organization.MEMBER"], organization_id=organization_id)

    results = await Secret.list_(
        session=session,
        return_type=Secret,  # Get Secret objects
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        filters=dict(organization_id=organization_id),
        after=params.after,
    )

    # Convert Secret objects to SecretRead objects with masked values
    secret_reads = [secret.to_read_masked() for secret in results.items]

    return Page[SecretRead](
        items=secret_reads,
        total=results.total,
        offset=results.offset,
        limit=results.limit,
        end_cursor=results.end_cursor,
    )


@router.get(
    "/v2/secrets",
    summary="Get an organization secret.",
    description="Permissions: `organization.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER"],
)
@handle_exception
async def get_secret(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    organization_id: Annotated[str, Query(description="Organization ID.")],
    name: Annotated[str, Query(min_length=1, description="Secret name (case-insensitive).")],
) -> SecretRead:
    """Get a secret by name.

    All organization members (both ADMIN and MEMBER roles) can read secrets.
    Users can only access secrets scoped to their organization. The secret value
    is masked (***) when retrieved. Secret names are normalized to uppercase.

    Args:
        user (UserAuth): Authenticated user information.
        session (AsyncSession): Database session.
        organization_id (str): Organization ID.
        name (str): Name of the secret (case-insensitive).

    Returns:
        secret (SecretRead): Secret details (with masked value).

    Raises:
        ResourceNotFoundError: If secret is not found.
    """
    # Both ADMIN and MEMBER roles can get secrets
    has_permissions(user, ["organization.MEMBER"], organization_id=organization_id)

    # Normalize to uppercase
    normalized_name = name.upper()
    # Use composite key (organization_id, name)
    secret = await session.get(Secret, (organization_id, normalized_name))
    if secret is None:
        raise ResourceNotFoundError(f'Secret "{normalized_name}" is not found.')
    return secret.to_read_masked()


@router.patch(
    "/v2/secrets",
    summary="Update an organization secret.",
    description="Permissions: `organization.ADMIN`.",
    tags=[MCP_TOOL_TAG, "organization.ADMIN"],
)
@handle_exception
async def update_secret(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    organization_id: Annotated[str, Query(description="Organization ID.")],
    name: Annotated[str, Query(min_length=1, description="Secret name (case-insensitive).")],
    body: SecretUpdate,
) -> SecretRead:
    """Update a secret's value and access settings.

    Only organization admins can update secrets. Users can only update secrets
    scoped to their organization(s). The updated value is returned unmasked.
    Secret names are normalized to uppercase.

    Args:
        request (Request): The FastAPI request object.
        user (UserAuth): Authenticated user information.
        session (AsyncSession): Database session.
        organization_id (str): Organization ID.
        name (str): Name of the secret (case-insensitive).
        body (SecretUpdate): Secret update data.

    Returns:
        secret (SecretRead): Updated secret details (with unmasked value).

    Raises:
        ResourceNotFoundError: If secret is not found.
    """
    # Check permissions
    has_permissions(user, ["organization.ADMIN"], organization_id=organization_id)

    # Normalize to uppercase
    normalized_name = name.upper()

    # Check if secret exists and user has access
    secret = await session.get(Secret, (organization_id, normalized_name))
    if secret is None:
        raise ResourceNotFoundError(f'Secret "{normalized_name}" is not found.')

    if body.value is not None:
        body.value = encrypt_random(body.value, ENV_CONFIG.encryption_key_plain)

    # Remove duplicates from allowed_projects
    if body.allowed_projects is not None and len(body.allowed_projects) > 0:
        body.allowed_projects = list(set(body.allowed_projects))

    # Verify allowed_projects exist in the organization
    if body.allowed_projects is not None and len(body.allowed_projects) > 0:
        statement = select(Project.id).where(
            Project.organization_id == organization_id,
            Project.id.in_(body.allowed_projects),
        )
        existing_projects = (await session.exec(statement)).all()
        if len(existing_projects) != len(body.allowed_projects):
            non_exist_projects = set(body.allowed_projects) - set(existing_projects)
            raise ResourceNotFoundError(f"Projects not found: {', '.join(non_exist_projects)}")
    secret, updates = await Secret.update(
        session, (organization_id, normalized_name), body, name="Secret"
    )

    logger.bind(user_id=user.id).success(
        f"{user.name} ({user.email}) updated the attributes "
        f'{list(updates.keys())} of secret "{secret.name}". ({request.state.id})'
    )
    return secret.to_read()


@router.delete(
    "/v2/secrets",
    summary="Delete an organization secret.",
    description="Permissions: `organization.ADMIN`.",
    tags=[MCP_TOOL_TAG, "organization.ADMIN"],
)
@handle_exception
async def delete_secret(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    organization_id: Annotated[str, Query(description="Organization ID.")],
    name: Annotated[str, Query(min_length=1, description="Secret name (case-insensitive).")],
) -> OkResponse:
    """Delete a secret.

    Only organization admins can delete secrets. Users can only delete secrets
    scoped to their organization(s). Secret names are normalized to uppercase.

    Args:
        user (UserAuth): Authenticated user information.
        session (AsyncSession): Database session.
        organization_id (str): Organization ID.
        name (str): Name of the secret (case-insensitive).

    Returns:
        response (OkResponse): Success confirmation.

    Raises:
        ResourceNotFoundError: If secret is not found.
    """
    # Check permissions
    has_permissions(user, ["organization.ADMIN"], organization_id=organization_id)

    # Normalize to uppercase
    normalized_name = name.upper()
    secret = await session.get(Secret, (organization_id, normalized_name))
    if secret is None:
        raise ResourceNotFoundError(f'Secret "{normalized_name}" is not found.')

    await session.delete(secret)
    await session.commit()

    logger.bind(user_id=user.id).success(
        f'{user.name} ({user.email}) deleted secret "{secret.name}".'
    )
    return OkResponse()
