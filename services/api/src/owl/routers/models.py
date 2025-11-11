from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger
from sqlmodel import func, select

from owl.db import AsyncSession, yield_async_session
from owl.db.models import Deployment, ModelConfig
from owl.types import (
    CloudProvider,
    DeploymentCreate,
    DeploymentRead,
    DeploymentUpdate,
    ListQuery,
    ModelConfigCreate,
    ModelConfigRead,
    ModelConfigUpdate,
    OkResponse,
    Page,
    UserAuth,
)
from owl.utils.auth import auth_user_service_key, has_permissions
from owl.utils.dates import now
from owl.utils.exceptions import (
    BadInputError,
    ResourceExistsError,
    ResourceNotFoundError,
    handle_exception,
)

router = APIRouter()


@router.post(
    "/v2/models/configs",
    summary="Create a model config.",
    description="Permissions: `system.MEMBER`. Prerequisite for creating a deployment.",
)
@handle_exception
async def create_model_config(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    body: ModelConfigCreate,
) -> ModelConfigRead:
    has_permissions(user, ["system.MEMBER"])
    if (await session.get(ModelConfig, body.id)) is not None:
        raise ResourceExistsError(f'ModelConfig "{body.id}" already exists.')
    model = ModelConfig.model_validate(body)
    session.add(model)
    await session.commit()
    await session.refresh(model)
    logger.bind(user_id=user.id).success(
        f'{user.name} ({user.email}) created a model config for "{model.name}" ({model.id}).'
    )
    logger.bind(user_id=user.id).info(f"{request.state.id} - Created model config: {model}")
    return model


@router.get(
    "/v2/models/configs/list",
    summary="List system-wide model configs.",
    description="Permissions: `system`.",
)
@handle_exception
async def list_model_configs(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListQuery, Query()],
) -> Page[ModelConfigRead]:
    has_permissions(user, ["system"])
    return await ModelConfig.list_(
        session=session,
        return_type=ModelConfigRead,
        organization_id=None,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        after=params.after,
    )


@router.get(
    "/v2/models/configs",
    summary="Get a model config.",
    description="Permissions: `system`.",
)
@handle_exception
async def get_model_config(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    model_id: Annotated[str, Query(min_length=1, description="Deployment ID.")],
) -> ModelConfigRead:
    has_permissions(user, ["system"])
    return await ModelConfig.get(session, model_id, name="Model config")


@router.patch(
    "/v2/models/configs",
    summary="Update a model config.",
    description="Permissions: `system.MEMBER`.",
)
@handle_exception
async def update_model_config(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    model_id: Annotated[str, Query(min_length=1, description="Deployment ID.")],
    body: ModelConfigUpdate,
) -> ModelConfigRead:
    has_permissions(user, ["system.MEMBER"])
    model = await ModelConfig.get(session, model_id, name="Model config")
    updates = body.model_dump(exclude_unset=True)
    ModelConfigCreate.validate_updates(base=model, updates=updates)
    for key, value in updates.items():
        setattr(model, key, value)
    model.updated_at = now()
    session.add(model)
    await session.commit()
    await session.refresh(model)
    logger.bind(user_id=user.id).success(
        (
            f"{user.name} ({user.email}) updated the attributes "
            f'{list(updates.keys())} of the model config for "{model.name}" ({model.id}).'
        )
    )
    logger.bind(user_id=user.id).info(f"{request.state.id} - Updated model config: {model}")
    return model


@router.delete(
    "/v2/models/configs",
    summary="Delete a model config.",
    description="Permissions: `system.MEMBER`.",
)
@handle_exception
async def delete_model_config(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    model_id: Annotated[str, Query(min_length=1, description="Deployment ID.")],
) -> OkResponse:
    has_permissions(user, ["system.MEMBER"])
    model = await session.get(ModelConfig, model_id)
    if model is None:
        raise ResourceNotFoundError(f'ModelConfig "{model_id}" is not found.')
    # Check deployments
    num_deployments = (
        await session.exec(
            select(func.count(Deployment.id)).where(Deployment.model_id == model_id)
        )
    ).one()
    if num_deployments > 0:
        raise BadInputError(
            (
                f'Cannot delete model "{model_id}" because it still has {num_deployments:,d} deployments. '
                "Please delete the deployments first."
            )
        )
    await session.delete(model)
    await session.commit()
    return OkResponse()


@router.get(
    "/v2/models/deployments/providers/cloud",
    summary="List available cloud providers.",
    description="Permissions: `system`.",
)
@handle_exception
async def list_available_providers(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
) -> list[str]:
    has_permissions(user, ["system"])
    return list(CloudProvider)


@router.post(
    "/v2/models/deployments/cloud",
    summary="Create an external cloud deployment.",
    description=(
        "Permissions: `system.MEMBER`. "
        "Note that a model config must be created before creating a deployment. "
        "Request body format: "
        "`provider` must be a valid Provider enum. "
        "`routing_id` must be a string. "
        "`api_base` is an OPTIONAL string. "
    ),
)
@handle_exception
async def create_deployment(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    body: DeploymentCreate,
) -> DeploymentRead:
    logger.info(f"{request.state.id} - Creating deployment: {body}")
    has_permissions(user, ["system.MEMBER"])
    # Check if the associated model exists
    model = await session.get(ModelConfig, body.model_id)
    if model is None:
        raise ResourceNotFoundError(f'Model "{body.model_id}" does not exist.')
    deployment = Deployment.model_validate(body)
    session.add(deployment)
    await session.commit()
    await session.refresh(deployment)
    logger.bind(user_id=user.id).success(
        (
            f"{user.name} ({user.email}) created a cloud deployment "
            f'"{deployment.name}" ({deployment.id}) for model "{model.name}" with '
            f'provider "{deployment.provider}".'
        )
    )
    logger.info(f"{request.state.id} - Created cloud deployment: {deployment}")
    return deployment


@router.get(
    "/v2/models/deployments/list",
    summary="List deployments.",
    description="Permissions: `system`.",
)
@handle_exception
async def list_deployments(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListQuery, Query()],
) -> Page[DeploymentRead]:
    has_permissions(user, ["system"])
    return await Deployment.list_(
        session=session,
        return_type=DeploymentRead,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        after=params.after,
    )


@router.get(
    "/v2/models/deployments",
    summary="Get a deployment.",
    description="Permissions: `system`.",
)
@handle_exception
async def get_deployment(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    deployment_id: Annotated[str, Query(min_length=1, description="Deployment ID.")],
) -> DeploymentRead:
    has_permissions(user, ["system"])
    deployment = await session.get(Deployment, deployment_id)
    if deployment is None:
        raise ResourceNotFoundError(f'Deployment "{deployment_id}" is not found.')
    return deployment


@router.patch(
    "/v2/models/deployments",
    summary="Update a deployment.",
    description="Permissions: `system.MEMBER`.",
)
@handle_exception
async def update_deployment(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    deployment_id: Annotated[str, Query(min_length=1, description="Deployment ID.")],
    body: DeploymentUpdate,
) -> DeploymentRead:
    has_permissions(user, ["system.MEMBER"])
    deployment = await session.get(Deployment, deployment_id)
    if deployment is None:
        raise ResourceNotFoundError(f'Deployment "{deployment_id}" is not found.')
    logger.info(f"Current deployment: {deployment}")
    # Perform update
    updates = body.model_dump(exclude=["id"], exclude_unset=True)
    for key, value in updates.items():
        setattr(deployment, key, value)
    deployment.updated_at = now()
    session.add(deployment)
    await session.commit()
    await session.refresh(deployment)
    logger.bind(user_id=user.id).success(
        (
            f"{user.name} ({user.email}) updated the attributes "
            f'{list(updates.keys())} of a deployment "{deployment.name}" ({deployment.id}).'
        )
    )
    logger.info(f"{request.state.id} - Updated deployment: {deployment}")
    return deployment


@router.delete(
    "/v2/models/deployments",
    summary="Delete a deployment.",
    description="Permissions: `system.MEMBER`.",
)
@handle_exception
async def delete_deployment(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    deployment_id: Annotated[str, Query(min_length=1, description="Deployment ID.")],
) -> OkResponse:
    logger.info(f"{request.state.id} - Deleting deployment: {deployment_id}")
    has_permissions(user, ["system.MEMBER"])
    deployment = await session.get(Deployment, deployment_id)
    if deployment is None:
        raise ResourceNotFoundError(f'Deployment "{deployment_id}" is not found.')
    await session.delete(deployment)
    await session.commit()
    return OkResponse()
