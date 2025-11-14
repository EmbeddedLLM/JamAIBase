from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger
from sqlmodel import delete, func, select

from owl.configs import CACHE, ENV_CONFIG
from owl.db import TEMPLATE_ORG_ID, AsyncSession, async_session, yield_async_session
from owl.db.gen_table import GenerativeTableCore
from owl.db.models import (
    BASE_PLAN_ID,
    Deployment,
    ModelConfig,
    Organization,
    OrgMember,
    PricePlan,
    Project,
    ProjectMember,
    User,
)
from owl.types import (
    ListQuery,
    ListQueryByOrg,
    ModelConfigRead,
    OkResponse,
    OrganizationCreate,
    OrganizationRead,
    OrganizationReadDecrypt,
    OrganizationUpdate,
    OrgMemberRead,
    OrgModelCatalogueQuery,
    Page,
    PricePlanCreate,
    Role,
    UsageResponse,
    UserAuth,
)
from owl.utils import mask_dict
from owl.utils.auth import auth_user_service_key, has_permissions
from owl.utils.billing import CLICKHOUSE_CLIENT, STRIPE_CLIENT, BillingManager
from owl.utils.billing_metrics import BillingMetrics
from owl.utils.crypt import decrypt, encrypt_random, generate_key
from owl.utils.dates import now
from owl.utils.exceptions import (
    BadInputError,
    BaseTierCountError,
    ForbiddenError,
    NoTierError,
    ResourceExistsError,
    ResourceNotFoundError,
    UnexpectedError,
    UpgradeTierError,
    handle_exception,
)
from owl.utils.mcp import MCP_TOOL_TAG
from owl.utils.metrics import Telemetry

router = APIRouter()
telemetry = Telemetry()

billing_metrics = BillingMetrics(clickhouse_client=CLICKHOUSE_CLIENT)


def _encrypt_dict(value: dict[str, str]) -> dict[str, str]:
    return {k: encrypt_random(v, ENV_CONFIG.encryption_key_plain) for k, v in value.items()}


def _decrypt_dict(value: dict[str, str]) -> dict[str, str]:
    return {k: decrypt(v, ENV_CONFIG.encryption_key_plain) for k, v in value.items()}


@router.post(
    "/v2/organizations",
    summary="Create an organization.",
    description="Permissions: None.",
)
@handle_exception
async def create_organization(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    body: OrganizationCreate,
    organization_id: str = "",
) -> OrganizationReadDecrypt:
    # There must always be a free plan
    async with async_session() as session:
        base_plan = await session.get(PricePlan, BASE_PLAN_ID)
        if base_plan is None:
            session.add(
                PricePlan(
                    id=BASE_PLAN_ID,
                    **PricePlanCreate.free().model_dump(mode="json", exclude={"id"}),
                )
            )
            await session.commit()
        # This is mainly for migration and not exposed as REST API
        if organization_id:
            if await session.get(Organization, organization_id) is not None:
                raise ResourceExistsError(f'Organization "{organization_id}" already exists.')
        else:
            # There must always be a system admin org
            if await session.get(Organization, "0") is None:
                organization_id = "0"
            else:
                organization_id = generate_key(24, "org_")
        num_base_tier_orgs = len(await Organization.list_base_tier_orgs(session, user.id))
        if organization_id != "0" and ENV_CONFIG.is_cloud:
            # A user can only have one free organization
            if num_base_tier_orgs > 1:
                raise BaseTierCountError
    # Create Stripe customer
    if STRIPE_CLIENT is None:
        stripe_id = None
    else:
        customer = await STRIPE_CLIENT.customers.create_async(
            dict(
                name=f"{user.name} | {body.name}",
                email=user.email,
                metadata=dict(organization_id=organization_id),
            )
        )
        logger.bind(user_id=user.id, org_id=organization_id).info(
            f"Stripe customer created: {customer}"
        )
        stripe_id = customer.id
    async with async_session() as session:
        org = Organization(
            **body.model_dump(exclude={"external_keys"}),
            id=organization_id,
            created_by=user.id,
            owner=user.id,
            stripe_id=stripe_id,
            external_keys=_encrypt_dict(body.external_keys),
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)
        logger.bind(user_id=user.id, org_id=org.id).success(
            f'{user.name} ({user.email}) created an organization "{org.name}".'
        )
        logger.bind(user_id=user.id, org_id=org.id).info(
            f"{request.state.id} - Created organization: {org}"
        )
        # Add user as admin
        org_member = OrgMember(user_id=user.id, organization_id=org.id, role=Role.ADMIN)
        session.add(org_member)
        await session.commit()
        await session.refresh(org_member)
        logger.bind(user_id=user.id, org_id=org.id).success(
            f'{user.name} ({user.email}) joined organization "{org.name}" as as admin.'
        )
        logger.info(f"{request.state.id} - Created organization member: {org_member}")
        # Create template org
        if await session.get(Organization, TEMPLATE_ORG_ID) is None:
            session.add(
                Organization(
                    id=TEMPLATE_ORG_ID,
                    name="Template",
                    created_by=user.id,
                    owner=user.id,
                )
            )
            await session.commit()
            logger.bind(user_id=user.id, org_id=org.id).success(
                f"{user.name} ({user.email}) created template organization."
            )
            session.add(
                OrgMember(user_id=user.id, organization_id=TEMPLATE_ORG_ID, role=Role.ADMIN)
            )
            await session.commit()
            logger.bind(user_id=user.id, org_id=org.id).success(
                f"{user.name} ({user.email}) joined template organization as as admin."
            )
    # Subscribe to base plan if the user has no base tier org
    if ENV_CONFIG.is_cloud and num_base_tier_orgs == 0:
        from owl.routers.organizations.cloud import subscribe_plan

        async with async_session() as session:
            user = UserAuth.model_validate(
                await session.get(User, user.id, populate_existing=True)
            )
        await subscribe_plan(user, org.id, BASE_PLAN_ID)
        async with async_session() as session:
            org = await session.get(Organization, org.id, populate_existing=True)
    return org


@router.get(
    "/v2/organizations/list",
    summary="List organizations.",
    description="Permissions: `system`.",
    tags=[MCP_TOOL_TAG, "system"],
)
@handle_exception
async def list_organizations(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListQuery, Query()],
) -> Page[OrganizationRead]:
    has_permissions(user, ["system"])
    return await Organization.list_(
        session=session,
        return_type=OrganizationRead,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        after=params.after,
    )


@router.get(
    "/v2/organizations",
    summary="Get an organization.",
    description="Permissions: `system` OR `organization`. Only `organization.ADMIN` can view API keys.",
    tags=[MCP_TOOL_TAG, "system", "organization"],
)
@handle_exception
async def get_organization(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    organization_id: Annotated[str, Query(min_length=1, description="Organization ID.")],
) -> OrganizationRead:
    has_permissions(user, ["system", "organization"], organization_id=organization_id)
    org = await session.get(Organization, organization_id)
    if org is None:
        raise ResourceNotFoundError(f'Organization "{organization_id}" is not found.')
    org = OrganizationReadDecrypt.model_validate(org)
    # Whether we need to mask external API keys
    if not has_permissions(
        user, ["organization.ADMIN"], organization_id=org.id, raise_error=False
    ):
        org.external_keys = mask_dict(org.external_keys)
    # Update billing data if needed
    request.state.billing = BillingManager(
        organization=org,
        project_id="",
        user_id=user.id,
        request=request,
        models=None,
    )
    return org


@router.patch(
    "/v2/organizations",
    summary="Update an organization.",
    description="Permissions: `organization.ADMIN`.",
)
@handle_exception
async def update_organization(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    organization_id: Annotated[str, Query(min_length=1, description="Organization ID.")],
    body: OrganizationUpdate,
) -> OrganizationRead:
    has_permissions(user, ["organization.ADMIN"], organization_id=organization_id)
    org = await session.get(Organization, organization_id)
    if org is None:
        raise ResourceNotFoundError(f'Organization "{organization_id}" is not found.')
    # Perform update
    updates = body.model_dump(exclude=["id"], exclude_unset=True)
    for key, value in updates.items():
        if key == "external_keys":
            value = _encrypt_dict(value)
        setattr(org, key, value)
    org.updated_at = now()
    session.add(org)
    await session.commit()
    await session.refresh(org)
    logger.bind(user_id=user.id, org_id=org.id).success(
        (
            f"{user.name} ({user.email}) updated the attributes "
            f'{list(updates.keys())} of organization "{org.name}".'
        )
    )
    org = OrganizationReadDecrypt.model_validate(org)
    if not has_permissions(
        user, ["organization.ADMIN"], organization_id=org.id, raise_error=False
    ):
        org.external_keys = mask_dict(org.external_keys)
    # Clear cache
    await CACHE.clear_organization_async(organization_id)
    return org


@router.delete(
    "/v2/organizations",
    summary="Delete an organization.",
    description=(
        "Permissions: Only the owner can delete an organization. "
        'WARNING: Deleting system organization "0" will also delete ALL data.'
    ),
)
@handle_exception
async def delete_organization(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    organization_id: Annotated[str, Query(min_length=1, description="Organization ID.")],
) -> OkResponse:
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise ResourceNotFoundError(f'Organization "{organization_id}" is not found.')
    # TODO: Create an endpoint to transfer ownership
    if organization.owner != user.id:
        raise ForbiddenError("Only the owner can delete an organization.")
    logger.info(f'{request.state.id} - Deleting organization: "{organization_id}"')
    # Delete Generative Tables
    await session.refresh(organization, ["projects"])
    for project in organization.projects:
        await GenerativeTableCore.drop_schemas(project_id=project.id)
    # Delete related resources
    await session.exec(delete(Organization).where(Organization.id == organization_id))
    await session.exec(delete(Project).where(Project.organization_id == organization_id))
    if ENV_CONFIG.is_cloud:
        from owl.db.models.cloud import VerificationCode

        await session.exec(
            delete(VerificationCode).where(VerificationCode.organization_id == organization_id)
        )
    if organization_id == "0":
        await session.exec(delete(Deployment))
        await session.exec(delete(ModelConfig))
        await session.exec(delete(Organization).where(Organization.id == TEMPLATE_ORG_ID))
    # Delete Stripe customer
    if STRIPE_CLIENT is not None and organization.stripe_id is not None:
        customer = await STRIPE_CLIENT.customers.delete_async(organization.stripe_id)
        logger.info(
            f'Stripe customer "{customer.id}" deleted for organization "{organization_id}".'
        )
    await session.commit()
    if organization_id == "0":
        logger.bind(user_id=user.id, org_id=organization_id).success(
            f"{user.name} ({user.email}) deleted all templates, models and deployments."
        )
    logger.bind(user_id=user.id, org_id=organization_id).success(
        f'{user.name} ({user.email}) deleted organization "{organization.name}".'
    )
    logger.info(f"{request.state.id} - Deleted organization: {organization_id}")
    # Clear cache
    await CACHE.clear_organization_async(organization_id)
    return OkResponse()


@router.post(
    "/v2/organizations/members",
    summary="Join an organization.",
    description=(
        "Permissions: `organization.ADMIN`. "
        "Permissions are only needed if adding another user or invite code is not provided."
    ),
)
@handle_exception
async def join_organization(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    user_id: Annotated[str, Query(min_length=1, description="ID of the user joining the org.")],
    invite_code: Annotated[
        str | None,
        Query(min_length=1, description="(Optional) Invite code for validation."),
    ] = None,
    organization_id: Annotated[
        str | None,
        Query(
            min_length=1,
            description="(Optional) Organization ID. Ignored if invite code is provided.",
        ),
    ] = None,
    role: Annotated[
        Role | None,
        Query(min_length=1, description="(Optional) Role. Ignored if invite code is provided."),
    ] = None,
) -> OrgMemberRead:
    joining_user = await session.get(User, user_id)
    if joining_user is None:
        raise ResourceNotFoundError(f'User "{user_id}" is not found.')
    if invite_code is None:
        if organization_id is None or role is None:
            raise BadInputError("Missing organization ID or role.")
        invite = None
    else:
        if ENV_CONFIG.is_oss:
            raise BadInputError("Invite code is not supported in OSS.")
        else:
            from owl.db.models.cloud import VerificationCode

            # Fetch code
            invite = await session.get(VerificationCode, invite_code)
            if (
                invite is None
                or invite.organization_id is None
                or invite.purpose not in ("organization_invite", None)
                or now() > invite.expiry
                or invite.revoked_at is not None
                or invite.used_at is not None
                or invite.user_email != joining_user.preferred_email
            ):
                raise ResourceNotFoundError(f'Invite code "{invite_code}" is invalid.')
            organization_id = invite.organization_id
            role = invite.role
    # RBAC
    if user.id != user_id or invite_code is None:
        has_permissions(user, ["organization.ADMIN"], organization_id=organization_id)
    # Check for existing membership
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise ResourceNotFoundError(f'Organization "{organization_id}" is not found.')
    if await session.get(OrgMember, (user_id, organization_id)) is not None:
        raise ResourceExistsError("You are already in the organization.")
    # Enforce member count limit (cloud only)
    if ENV_CONFIG.is_cloud and organization.id not in ["0", TEMPLATE_ORG_ID]:
        if (plan := organization.price_plan) is None:
            raise NoTierError
        else:
            if plan.max_users is not None:
                member_count = (
                    await session.exec(
                        select(func.count(OrgMember.user_id)).where(
                            OrgMember.organization_id == organization_id
                        )
                    )
                ).one()
                if member_count >= plan.max_users:
                    raise UpgradeTierError(
                        (
                            f"Your subscribed plan only supports {plan.max_users:,d} members. "
                            "Consider upgrading your plan or remove existing member before adding more."
                        )
                    )
    # Add member
    org_member = OrgMember(user_id=user_id, organization_id=organization_id, role=role)
    session.add(org_member)
    await session.commit()
    await session.refresh(org_member)
    # Consume invite code
    if invite is not None:
        invite.used_at = now()
        session.add(invite)
        await session.commit()
    logger.bind(user_id=joining_user.id, org_id=organization.id).success(
        (
            f"{joining_user.preferred_name} ({joining_user.preferred_email}) joined "
            f'organization "{organization.name}" as "{role.name}".'
        )
    )
    return org_member


@router.get(
    "/v2/organizations/members/list",
    summary="List organization members.",
    description="Permissions: `system` OR `organization`.",
)
@handle_exception
async def list_organization_members(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListQueryByOrg[Literal["id", "created_at", "updated_at"]], Query()],
) -> Page[OrgMemberRead]:
    has_permissions(user, ["system", "organization"], organization_id=params.organization_id)
    return await OrgMember.list_(
        session=session,
        return_type=OrgMemberRead,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        filters=dict(organization_id=params.organization_id),
        after=params.after,
    )


@router.get(
    "/v2/organizations/members",
    summary="Get an organization member.",
    description="Permissions: `system` OR `organization`.",
)
@handle_exception
async def get_organization_member(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    user_id: Annotated[str, Query(min_length=1, description="User ID.")],
    organization_id: Annotated[str, Query(min_length=1, description="Organization ID.")],
) -> OrgMemberRead:
    has_permissions(user, ["system", "organization"], organization_id=organization_id)
    member_id = (user_id, organization_id)
    member = await session.get(OrgMember, member_id)
    if member is None:
        raise ResourceNotFoundError(f'Organization member "{member_id}" is not found.')
    return member


@router.patch(
    "/v2/organizations/members/role",
    summary="Update a organization member's role.",
    description="Permissions: `organization.ADMIN`.",
)
@handle_exception
async def update_member_role(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    user_id: Annotated[str, Query(min_length=1, description="User ID.")],
    organization_id: Annotated[str, Query(min_length=1, description="Organization ID.")],
    role: Annotated[Role, Query(description="New role.")],
) -> OrgMemberRead:
    # Check permissions
    has_permissions(user, ["organization.ADMIN"], organization_id=organization_id)
    # Fetch the member
    member = await session.get(OrgMember, (user_id, organization_id))
    if member is None:
        raise ResourceNotFoundError(
            f'User "{user_id}" is not a member of organization "{organization_id}".'
        )
    # Update
    member.role = role
    await session.commit()
    return member


@router.delete(
    "/v2/organizations/members",
    summary="Leave an organization.",
    description=(
        "Permissions: `organization.ADMIN`. "
        "Permissions are only needed if deleting another user's membership."
    ),
)
@handle_exception
async def leave_organization(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    user_id: Annotated[str, Query(min_length=1, description="User ID.")],
    organization_id: Annotated[str, Query(min_length=1, description="Organization ID.")],
) -> OkResponse:
    if user.id != user_id:
        has_permissions(user, ["organization.ADMIN"], organization_id=organization_id)
    leaving_user = await session.get(User, user_id)
    if leaving_user is None:
        raise ResourceNotFoundError(f'User "{user_id}" is not found.')
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise ResourceNotFoundError(f'Organization "{organization_id}" is not found.')
    if user_id == organization.created_by:
        raise ForbiddenError("Owner cannot leave the organization.")
    org_member = await session.get(OrgMember, (user_id, organization_id))
    if org_member is None:
        raise ResourceNotFoundError(
            f"Organization membership {(user_id, organization_id)} is not found."
        )
    await session.delete(org_member)
    await session.commit()
    # If the user has no remaining membership with the org, remove them from all projects
    num_memberships = (
        await session.exec(
            select(func.count(OrgMember.user_id)).where(
                OrgMember.user_id == user_id,
                OrgMember.organization_id == organization_id,
            )
        )
    ).one()
    if num_memberships == 0:
        projects = (
            await session.exec(select(Project).where(Project.organization_id == organization_id))
        ).all()
        for p in projects:
            try:
                await session.exec(
                    delete(ProjectMember).where(
                        ProjectMember.user_id == user_id,
                        ProjectMember.project_id == p.id,
                    )
                )
                await session.commit()
            except Exception as e:
                logger.warning(
                    f'Failed to remove "{user_id}" from project "{p.id}" due to {repr(e)}'
                )
    logger.bind(user_id=leaving_user.id, org_id=organization.id).success(
        (
            f"{leaving_user.preferred_name} ({leaving_user.preferred_email}) left "
            f'organization "{organization.name}".'
        )
    )
    return OkResponse()


@router.get(
    "/v2/organizations/models/catalogue",
    summary="List models AVAILABLE to an organization.",
    description="Permissions: `system` OR `organization`.",
)
@handle_exception
async def organization_model_catalogue(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[OrgModelCatalogueQuery, Query()],
) -> Page[ModelConfigRead]:
    has_permissions(user, ["system", "organization"], organization_id=params.organization_id)
    return await ModelConfig.list_(
        session=session,
        return_type=ModelConfigRead,
        organization_id=params.organization_id,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        after=params.after,
        capabilities=params.capabilities,
        exclude_inactive=True,
    )


@router.get("/v2/organizations/meters/query")
async def get_organization_metrics(
    user: Annotated[UserAuth, Depends(auth_user_service_key)],
    metric_id: Annotated[
        Literal["llm", "embedding", "reranking", "spent", "bandwidth", "storage"],
        Query(alias="metricId", description="Type of usage data to query."),
    ],
    from_: Annotated[
        datetime,
        Query(alias="from", description="Start datetime for the usage data query."),
    ],
    window_size: Annotated[
        str | None,
        Query(
            min_length=1,
            alias="windowSize",
            description="The aggregation window size (e.g., '1d' for daily, '1w' for weekly).",
        ),
    ],
    org_id: Annotated[
        str,
        Query(
            min_length=1,
            alias="orgId",
            description="Organization ID to filter the usage data.",
        ),
    ],
    proj_ids: Annotated[
        list[str] | None,
        Query(
            min_length=1,
            alias="projIds",
            description="List of project IDs to filter the usage data. If not provided, data for all projects is returned.",
        ),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(
            description="End datetime for the usage data query. If not provided, data up to the current datetime is returned."
        ),
    ] = None,
    group_by: Annotated[
        list[str] | None,
        Query(
            min_length=1,
            alias="groupBy",
            description="List of fields to group the usage data by. If not provided, no grouping is applied.",
        ),
    ] = None,
    data_source: Annotated[
        Literal["clickhouse", "victoriametrics"],
        Query(description="Data source to query. Defaults to 'clickhouse'.", alias="dataSource"),
    ] = "clickhouse",
) -> UsageResponse:
    has_permissions(user, ["organization.MEMBER"], organization_id=org_id)
    try:
        # always add org_id to group_by
        if to is None:
            to = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
        # set to default []
        if group_by is None:
            group_by = []

        if data_source == "clickhouse":
            metrics_client = billing_metrics
        elif data_source == "victoriametrics":
            metrics_client = telemetry

        if metric_id == "llm":
            results = await metrics_client.query_llm_usage(
                [org_id],
                proj_ids,
                from_,
                to,
                group_by,
                window_size,
            )
        elif metric_id == "embedding":
            results = await metrics_client.query_embedding_usage(
                [org_id],
                proj_ids,
                from_,
                to,
                group_by,
                window_size,
            )
        elif metric_id == "reranking":
            results = await metrics_client.query_reranking_usage(
                [org_id],
                proj_ids,
                from_,
                to,
                group_by,
                window_size,
            )
        elif metric_id == "spent":
            results = await metrics_client.query_billing(
                [org_id], proj_ids, from_, to, group_by, window_size
            )
        elif metric_id == "bandwidth":
            results = await metrics_client.query_bandwidth(
                [org_id], proj_ids, from_, to, group_by, window_size
            )
        elif metric_id == "storage":
            results = await metrics_client.query_storage(
                [org_id], proj_ids, from_, to, group_by, window_size
            )
        return results
    except Exception as e:
        err = f"Failed to fetch Metrics Data events: {e}"
        logger.error(err)
        raise UnexpectedError(err) from e
