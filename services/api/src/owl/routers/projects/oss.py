import base64
from io import BytesIO
from os.path import join
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel import delete, func, select

from owl.configs import ENV_CONFIG
from owl.db import AsyncSession, async_session, cached_text, yield_async_session
from owl.db.gen_table import (
    ActionTable,
    ChatTable,
    ColumnMetadata,
    KnowledgeTable,
    TableMetadata,
)
from owl.db.models import (
    Organization,
    Project,
    ProjectMember,
    User,
)
from owl.types import (
    ListQueryByOrg,
    ListQueryByProject,
    OkResponse,
    OrganizationRead,
    Page,
    ProjectCreate,
    ProjectMemberRead,
    ProjectRead,
    ProjectUpdate,
    Role,
    TableMetaResponse,
    TableType,
    UserAuth,
)
from owl.utils.auth import auth_user, has_permissions
from owl.utils.billing import BillingManager
from owl.utils.dates import now
from owl.utils.exceptions import (
    BadInputError,
    ForbiddenError,
    ResourceExistsError,
    ResourceNotFoundError,
    UnexpectedError,
    handle_exception,
)
from owl.utils.io import json_dumps, json_loads, open_uri_async, s3_upload
from owl.utils.mcp import MCP_TOOL_TAG

router = APIRouter()


async def _count_project_name(
    session: AsyncSession,
    organization_id: str,
    name: str,
) -> int:
    return (
        await session.exec(
            select(
                func.count(Project.id).filter(
                    Project.organization_id == organization_id, Project.name == name
                )
            )
        )
    ).one()


@router.post(
    "/v2/projects",
    summary="Create a new project under an organization.",
    description="Permissions: `organization.ADMIN`.",
    tags=[MCP_TOOL_TAG, "organization.ADMIN"],
)
@handle_exception
async def create_project(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    body: ProjectCreate,
    project_id: str = "",
) -> ProjectRead:
    has_permissions(user, ["organization.ADMIN"], organization_id=body.organization_id)
    # Check for duplicate project ID
    if project_id and await session.get(Project, project_id) is not None:
        raise ResourceExistsError(f'Project "{project_id}" already exists.')
    # Ensure the organization exists
    organization = await session.get(Organization, body.organization_id)
    if organization is None:
        raise ResourceNotFoundError(f'Organization "{body.organization_id}" is not found.')
    # Try assigning a unique name
    name_count = await _count_project_name(session, body.organization_id, body.name)
    if name_count > 0:
        idx = name_count
        while (
            await _count_project_name(session, body.organization_id, f"{body.name} ({idx})")
        ) > 0:
            idx += 1
        body.name = f"{body.name} ({idx})"

    # Create project
    project = Project(
        **body.model_dump(),
        created_by=user.id,
        owner=user.id,
    )
    if project_id:
        project.id = project_id
    else:
        project_id = project.id
    session.add(project)
    await session.commit()
    await session.refresh(project)
    logger.bind(user_id=user.id, org_id=organization.id, proj_id=project_id).info(
        f"{request.state.id} - Created project: {project}"
    )
    logger.bind(user_id=user.id, org_id=organization.id, proj_id=project_id).success(
        f'{user.name} ({user.email}) created a project "{project.name}"'
    )
    # Create membership
    project_member = ProjectMember(
        user_id=user.id,
        project_id=project_id,
        role=Role.ADMIN,
    )
    session.add(project_member)
    await session.commit()
    await session.refresh(project_member)
    logger.bind(user_id=user.id, org_id=organization.id, proj_id=project_id).info(
        f"{request.state.id} - Created project member: {project_member}"
    )
    logger.bind(user_id=user.id, org_id=organization.id, proj_id=project_id).success(
        f'{user.name} ({user.email}) joined project "{project.name}" as as admin.'
    )
    # Create Generative Table schemas
    for table_type in TableType:
        schema_id = f"{project_id}_{table_type}"
        await session.exec(cached_text(f'CREATE SCHEMA IF NOT EXISTS "{schema_id}"'))
        await session.exec(cached_text(TableMetadata.sql_create(schema_id)))
        await session.exec(cached_text(ColumnMetadata.sql_create(schema_id)))
    return project


class ListProjectQuery(ListQueryByOrg):
    search_query: Annotated[
        str,
        Field(
            max_length=255,
            description=(
                "_Optional_. A string to search for within project names as a filter. "
                'Defaults to "" (no filter).'
            ),
        ),
    ] = ""
    list_chat_agents: Annotated[
        bool, Field(description="_Optional_. List chat agents. Defaults to False.")
    ] = False


@router.get(
    "/v2/projects/list",
    summary="List all projects within an organization.",
    description="Permissions: `system` OR `organization`.",
    tags=[MCP_TOOL_TAG, "system", "organization"],
)
@handle_exception
async def list_projects(
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListProjectQuery, Query()],
) -> Page[ProjectRead]:
    org_id = params.organization_id
    has_permissions(user, ["system", "organization"], organization_id=org_id)
    # Ensure the organization exists
    org_role = next((r.role for r in user.org_memberships if r.organization_id == org_id), None)
    if org_role is None:
        raise ResourceNotFoundError(f'Organization "{org_id}" is not found.')
    # List
    response = await Project.list_(
        session=session,
        return_type=ProjectRead,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        filters=dict(organization_id=org_id),
        after=params.after,
        filter_by_user=user.id if org_role == Role.GUEST else "",
    )
    if params.list_chat_agents:
        for p in response.items:
            metas = await ChatTable.list_tables(
                project_id=p.id,
                limit=None,
                offset=0,
                order_by="id",
                order_ascending=True,
                parent_id="_agent_",
            )
            p.chat_agents = metas.items
    return response


@router.get(
    "/v2/projects",
    summary="Get a project.",
    description="Permissions: `system` OR `organization`.",
    tags=[MCP_TOOL_TAG, "system", "organization"],
)
@handle_exception
async def get_project(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    project_id: Annotated[str, Query(min_length=1, description="Project ID.")],
) -> ProjectRead:
    # Fetch the project
    project = await session.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    has_permissions(user, ["system", "organization"], organization_id=project.organization_id)
    # Update billing data if needed
    request.state.billing = BillingManager(
        organization=OrganizationRead.model_validate(project.organization),
        project_id="",  # Skip egress charge
        user_id=user.id,
        request=request,
        models=None,
    )
    return project


@router.patch(
    "/v2/projects",
    summary="Update a project.",
    description="Permissions: `organization.ADMIN` OR `project.ADMIN`.",
)
@handle_exception
async def update_project(
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    project_id: Annotated[str, Query(min_length=1, description="Project ID.")],
    body: ProjectUpdate,
) -> ProjectRead:
    # Fetch
    project = await session.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    # Check permissions
    has_permissions(
        user,
        ["organization.ADMIN", "project.ADMIN"],
        organization_id=project.organization_id,
        project_id=project_id,
    )
    # Update
    updates = body.model_dump(exclude={"id"}, exclude_unset=True)
    for key, value in updates.items():
        setattr(project, key, value)
    project.updated_at = now()
    session.add(project)
    await session.commit()
    await session.refresh(project)
    logger.bind(user_id=user.id, proj_id=project.id).success(
        (
            f"{user.name} ({user.email}) updated the attributes "
            f'{list(updates.keys())} of project "{project.name}".'
        )
    )
    return project


@router.delete(
    "/v2/projects",
    summary="Delete a project.",
    description="Permissions: `organization.ADMIN`, OR None for the project owner.",
)
@handle_exception
async def delete_project(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    project_id: Annotated[str, Query(min_length=1, description="Project ID.")],
) -> OkResponse:
    # Fetch
    project = await session.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    # Check permissions
    has_permissions(user, ["organization.ADMIN"], organization_id=project.organization_id)
    # Delete Generative Tables
    for table_type in TableType:
        schema_id = f"{project_id}_{table_type}"
        await session.exec(cached_text(f'DROP SCHEMA IF EXISTS "{schema_id}" CASCADE'))
    # Delete related resources
    await session.exec(delete(ProjectMember).where(ProjectMember.project_id == project_id))
    if ENV_CONFIG.is_cloud:
        from owl.db.models.cloud import ProjectKey, VerificationCode

        await session.exec(
            delete(VerificationCode).where(VerificationCode.project_id == project_id)
        )
        await session.exec(delete(ProjectKey).where(ProjectKey.project_id == project_id))
    await session.delete(project)
    await session.commit()
    logger.bind(user_id=user.id, org_id=project.id).success(
        f'{user.name} ({user.email}) deleted project "{project.name}".'
    )
    logger.info(f"{request.state.id} - Deleted project: {project.id}")
    return OkResponse()


@router.post(
    "/v2/projects/members",
    summary="Join a project.",
    description=(
        "Permissions: `organization.ADMIN` OR `project.ADMIN`. "
        "Permissions are only needed if adding another user or invite code is not provided."
    ),
)
@handle_exception
async def join_project(
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    user_id: Annotated[
        str, Query(min_length=1, description="ID of the user joining the project.")
    ],
    invite_code: Annotated[
        str | None,
        Query(min_length=1, description="(Optional) Invite code for validation."),
    ] = None,
    project_id: Annotated[
        str | None,
        Query(
            min_length=1,
            description="(Optional) Project ID. Ignored if invite code is provided.",
        ),
    ] = None,
    role: Annotated[
        Role | None,
        Query(
            min_length=1,
            description="(Optional) Project role. Ignored if invite code is provided.",
        ),
    ] = None,
) -> ProjectMemberRead:
    joining_user = await session.get(User, user_id)
    if joining_user is None:
        raise ResourceNotFoundError(f'User "{user_id}" is not found.')
    if invite_code is None:
        if project_id is None or role is None:
            raise BadInputError("Missing project ID or role.")
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
                or invite.project_id is None
                or invite.purpose not in ("project_invite", None)
                or now() > invite.expiry
                or invite.revoked_at is not None
                or invite.used_at is not None
                or invite.user_email != joining_user.preferred_email
            ):
                raise ResourceNotFoundError(f'Invite code "{invite_code}" is invalid.')
            project_id = invite.project_id
            role = invite.role
    # Fetch
    project = await session.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    if project.organization_id not in [r.organization_id for r in joining_user.org_memberships]:
        raise ForbiddenError("You are not a member of this project's organization.")
    if await session.get(ProjectMember, (user_id, project_id)) is not None:
        raise ResourceExistsError("You are already in the project.")
    # RBAC
    if user.id != user_id or invite_code is None:
        has_permissions(
            user,
            ["organization.ADMIN", "project.ADMIN"],
            organization_id=project.organization_id,
            project_id=project_id,
        )
    project_member = ProjectMember(user_id=user_id, project_id=project_id, role=role)
    session.add(project_member)
    await session.commit()
    await session.refresh(project_member)
    # Consume invite code
    if invite is not None:
        invite.used_at = now()
        session.add(invite)
        await session.commit()
    logger.bind(user_id=joining_user.id, proj_id=project.id).success(
        (
            f"{joining_user.preferred_name} ({joining_user.preferred_email}) joined "
            f'project "{project.name}" as "{role.name}".'
        )
    )
    return project_member


@router.get(
    "/v2/projects/members/list",
    summary="List project members.",
    description="Permissions: `system` OR `organization` OR `project`.",
)
@handle_exception
async def list_project_members(
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListQueryByProject[Literal["id", "created_at", "updated_at"]], Query()],
) -> Page[ProjectMemberRead]:
    project_id = params.project_id
    # Fetch the project
    project = await session.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    has_permissions(
        user,
        ["system", "organization", "project"],
        organization_id=project.organization_id,
        project_id=project_id,
    )
    return await ProjectMember.list_(
        session=session,
        return_type=ProjectMemberRead,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        filters=dict(project_id=project_id),
        after=params.after,
    )


@router.get(
    "/v2/projects/members",
    summary="Get a project member.",
    description="Permissions: `system` OR `organization` OR `project`.",
)
@handle_exception
async def get_project_member(
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    user_id: Annotated[str, Query(min_length=1, description="User ID.")],
    project_id: Annotated[str, Query(min_length=1, description="Project ID.")],
) -> ProjectMemberRead:
    # Fetch the project
    project = await session.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    has_permissions(
        user,
        ["system", "organization", "project"],
        organization_id=project.organization_id,
        project_id=project_id,
    )
    member = await session.get(ProjectMember, (user_id, project_id))
    if member is None:
        raise ResourceNotFoundError(f'User "{user_id}" is not a member of project "{project_id}".')
    return member


@router.patch(
    "/v2/projects/members/role",
    summary="Update a project member's role.",
    description="Permissions: `organization.ADMIN` OR `project.ADMIN`.",
)
@handle_exception
async def update_member_role(
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    user_id: Annotated[str, Query(min_length=1, description="User ID.")],
    project_id: Annotated[str, Query(min_length=1, description="Project ID.")],
    role: Annotated[Role, Query(description="New role.")],
) -> ProjectMemberRead:
    # Fetch the project
    project = await session.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    # Check permissions
    has_permissions(
        user,
        ["organization.ADMIN", "project.ADMIN"],
        organization_id=project.organization_id,
        project_id=project.id,
    )
    # Fetch the member
    member = await session.get(ProjectMember, (user_id, project_id))
    if member is None:
        raise ResourceNotFoundError(f'User "{user_id}" is not a member of project "{project_id}".')
    # Update
    member.role = role
    await session.commit()
    return member


@router.delete(
    "/v2/projects/members",
    summary="Leave a project.",
    description=(
        "Permissions: `organization.ADMIN` OR `project.ADMIN`. "
        "Permissions are only needed if deleting other user's membership."
    ),
)
@handle_exception
async def leave_project(
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    user_id: Annotated[str, Query(min_length=1, description="User ID.")],
    project_id: Annotated[str, Query(min_length=1, description="Project ID.")],
) -> OkResponse:
    leaving_user = await session.get(User, user_id)
    if leaving_user is None:
        raise ResourceNotFoundError(f'User "{user_id}" is not found.')
    project = await session.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    if user.id != user_id:
        has_permissions(
            user,
            ["organization.ADMIN", "project.ADMIN"],
            organization_id=project.organization_id,
            project_id=project_id,
        )
    project_member = await session.get(ProjectMember, (user_id, project_id))
    if project_member is None:
        raise ResourceNotFoundError(f'User "{user_id}" is not a member of project "{project_id}".')
    await session.delete(project_member)
    await session.commit()
    logger.bind(user_id=leaving_user.id, proj_id=project.id).success(
        (
            f"{leaving_user.preferred_name} ({leaving_user.preferred_email}) left "
            f'project "{project.name}".'
        )
    )
    return OkResponse()


TABLE_CLS: dict[TableType, ActionTable | KnowledgeTable | ChatTable] = {
    TableType.ACTION: ActionTable,
    TableType.KNOWLEDGE: KnowledgeTable,
    TableType.CHAT: ChatTable,
}


async def _export_project_as_pa_table(
    request: Request,
    user: UserAuth,
    project: Project,
) -> pa.Table:
    organization = OrganizationRead.model_validate(project.organization)
    # Check quota
    billing = BillingManager(
        organization=organization,
        project_id=project.id,
        user_id=user.id,
        request=request,
        models=None,
    )
    billing.has_egress_quota()
    # Dump all tables as parquet files
    data = []
    table_types = [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]
    for table_type in table_types:
        metas = (
            await TABLE_CLS[table_type].list_tables(
                project_id=project.id,
                limit=None,
                offset=0,
                parent_id=None,
                count_rows=False,
            )
        ).items
        for meta in metas:
            table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=meta.id)
            with BytesIO() as f:
                await table.export_table(f)
                data.append((table_type, meta, f.getvalue()))
    if len(data) == 0:
        raise BadInputError(f'Project "{project.id}" is empty with no tables.')
    # Download project pictures
    project_meta = project.model_dump()
    for pic_type in ["profile_picture", "cover_picture"]:
        uri: str | None = project_meta.get(f"{pic_type}_url", None)
        if uri is None:
            continue
        async with open_uri_async(uri) as (f, mime):
            project_meta[pic_type] = (
                f"data:{mime};base64,{base64.b64encode(await f.read()).decode('utf-8')}"
            )
    # Bundle everything into a single PyArrow Table
    table_metas = [
        {"table_type": table_type, "table_meta": meta.model_dump(mode="json")}
        for table_type, meta, _ in data
    ]
    data = list(zip(*data, strict=True))
    pa_table = pa.table(
        {"table_type": pa.array(data[0], pa.utf8()), "data": pa.array(data[2], pa.binary())},
        metadata={
            "project_meta": json_dumps(project_meta),
            "table_metas": json_dumps(table_metas),
        },
    )
    return pa_table


@router.get("/v2/projects/export")
@handle_exception
async def export_project(
    request: Request,
    bg_tasks: BackgroundTasks,
    user: Annotated[UserAuth, Depends(auth_user)],
    project_id: Annotated[str, Query(min_length=1, description="Project ID.")],
) -> FileResponse:
    # Fetch the project
    async with async_session() as session:
        project = await session.get(Project, project_id)
    if project is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    pa_table = await _export_project_as_pa_table(
        request=request,
        user=user,
        project=project,
    )
    # Temporary file
    tmp_dir = TemporaryDirectory()
    filename = f"{project.id}.parquet"
    filepath = join(tmp_dir.name, filename)
    # Keep a reference to the directory and only delete upon completion
    bg_tasks.add_task(tmp_dir.cleanup)
    pq.write_table(pa_table, filepath, compression="ZSTD")
    logger.bind(user_id=user.id).success(
        f'{user.name} ({user.email}) exported project "{project.name}" ({project.id}).'
    )
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream",
    )


async def _import_project_from_pa_table(
    request: Request,
    user: UserAuth,
    *,
    organization_id: str,
    project_id: str,
    pa_table: pa.Table,
    keep_original_ids: bool = False,
    check_quota: bool = True,
    raise_error: bool = True,
    verbose: bool = False,
) -> ProjectRead:
    has_permissions(user, ["system", "organization"], organization_id=organization_id)
    async with async_session() as session:
        if project_id:
            # Fetch the project
            project = await session.get(Project, project_id)
            if project is None:
                raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
            organization = project.organization
        else:
            if not organization_id:
                raise BadInputError("Organization ID is required when project ID is not provided.")
            project = None
            # Fetch the organization
            organization = await session.get(Organization, organization_id)
            if organization is None:
                raise ResourceNotFoundError(f'Organization "{organization_id}" is not found.')
        organization = OrganizationRead.model_validate(organization)
    # Check quota
    if check_quota:
        billing = BillingManager(
            organization=organization,
            project_id="",  # Not needed to check storage quotas
            user_id=user.id,
            request=request,
            models=None,
        )
        billing.has_db_storage_quota()
        billing.has_file_storage_quota()
    # Create the project if needed
    if project is None:
        try:
            project_meta = json_loads(pa_table.schema.metadata[b"project_meta"])
        except KeyError as e:
            raise BadInputError("Missing project metadata in the Parquet file.") from e
        except Exception as e:
            raise BadInputError("Invalid project metadata in the Parquet file.") from e
        body = {k: v for k, v in project_meta.items() if k not in ["id", "organization_id"]}
        body["organization_id"] = organization_id
        async with async_session() as session:
            project = await create_project(
                request=request,
                user=user,
                session=session,
                body=ProjectCreate.model_validate(body),
                project_id=project_meta.get("id", "") if keep_original_ids else "",
            )
            # Upload and update project picture URL
            project = await session.get(Project, project.id)
            if project is None:
                raise UnexpectedError(f'Project "{project.id}" is not found.')
            for pic_type in ["profile_picture", "cover_picture"]:
                data: str | None = project_meta.get(pic_type, None)
                uri_ori: str | None = project_meta.get(f"{pic_type}_url", None)
                if data is None or uri_ori is None:
                    uri = None
                else:
                    # f"data:{mime};base64,{base64.b64encode(await f.read()).decode('utf-8')}"
                    mime_type, b64 = data.replace("data:", "", 1).split(";base64,")
                    uri = await s3_upload(
                        organization.id,
                        project.id,
                        base64.b64decode(b64.encode("utf-8")),
                        content_type=mime_type,
                        filename=uri_ori.split("/")[-1],
                    )
                setattr(project, f"{pic_type}_url", uri)
            await session.commit()
            await session.refresh(project)
    if verbose:
        logger.info(
            f'Importing project "{project.name}" ({project.id}): Project metadata imported.'
        )

    # Import Knowledge Tables first
    async def _import_table(_data: bytes, _type: str):
        with BytesIO(_data) as source:
            await TABLE_CLS[_type].import_table(
                project_id=project.id,
                source=source,
                table_id_dst=None,
                reupload_files=not keep_original_ids,
                verbose=verbose,
            )

    table_metas = json_loads(pa_table.schema.metadata[b"table_metas"])
    rows = pa_table.to_pylist()
    i = 1
    for row, meta in zip(rows, table_metas, strict=True):
        if row["table_type"] != TableType.KNOWLEDGE:
            continue
        meta = TableMetaResponse.model_validate(meta["table_meta"])
        if verbose:
            logger.info(
                (
                    f'Importing project "{project.name}" ({project.id}): '
                    f'Importing table "{meta.id}" ({i} of {len(rows)}) ...'
                )
            )
        try:
            await _import_table(row["data"], row["table_type"])
        except ResourceExistsError as e:
            logger.info(f'Importing project "{project.name}" ({project.id}): {e}')
            if raise_error:
                raise
        except Exception as e:
            logger.exception(
                f'Importing project "{project.name}" ({project.id}): Failed to import table "{meta.id}": {e}'
            )
            if raise_error:
                raise
        i += 1
    # Import the rest
    for row, meta in zip(rows, table_metas, strict=True):
        if row["table_type"] == TableType.KNOWLEDGE:
            continue
        meta = TableMetaResponse.model_validate(meta["table_meta"])
        if verbose:
            logger.info(
                (
                    f'Importing project "{project.name}" ({project.id}): '
                    f'Importing table "{meta.id}" ({i} of {len(rows)}) ...'
                )
            )
        try:
            await _import_table(row["data"], row["table_type"])
        except ResourceExistsError as e:
            logger.info(f'Importing project "{project.name}" ({project.id}): {e}')
            if raise_error:
                raise
        except Exception as e:
            logger.exception(
                f'Importing project "{project.name}" ({project.id}): Failed to import table "{meta.id}": {e}'
            )
            if raise_error:
                raise
        i += 1
    return project


class ProjectImportFormData(BaseModel):
    file: Annotated[UploadFile, File(description="The project or template Parquet file.")]
    project_id: Annotated[
        str,
        Field(
            description='If given, import tables into this project. Defaults to "" (create new project).'
        ),
    ] = ""
    organization_id: Annotated[
        str,
        Field(
            description="Organization ID of the new project. Only required if creating a new project."
        ),
    ] = ""


@router.post("/v2/projects/import/parquet")
@handle_exception
async def import_project(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    data: Annotated[ProjectImportFormData, Form()],
) -> ProjectRead:
    # Load Parquet file
    try:
        with BytesIO(await data.file.read()) as source:
            # TODO: Perhaps check the metadata with `columns=[]` first and avoid parsing the whole file
            pa_table: pa.Table = pq.read_table(
                source, columns=None, use_threads=False, memory_map=True
            )
    except Exception as e:
        raise BadInputError("Failed to parse Parquet file.") from e
    return await _import_project_from_pa_table(
        request,
        user,
        organization_id=data.organization_id,
        project_id=data.project_id,
        pa_table=pa_table,
    )


@router.post("/v2/projects/import/parquet/migration")
@handle_exception
async def import_project_migration(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    data: Annotated[ProjectImportFormData, Form()],
) -> ProjectRead:
    # Load Parquet file
    try:
        with BytesIO(await data.file.read()) as source:
            pa_table: pa.Table = pq.read_table(
                source, columns=None, use_threads=False, memory_map=True
            )
    except Exception as e:
        raise BadInputError("Failed to parse Parquet file.") from e
    try:
        return await _import_project_from_pa_table(
            request,
            user,
            organization_id=data.organization_id,
            project_id=data.project_id,
            pa_table=pa_table,
            keep_original_ids=True,
            check_quota=False,
            raise_error=False,
            verbose=True,
        )
    except Exception as e:
        logger.exception(e)
        raise


class TemplateImportQuery(BaseModel):
    template_id: Annotated[str, Field(description="Template ID.")]
    project_id: Annotated[
        str,
        Field(
            description='If given, import tables into this project. Defaults to "" (create new project).'
        ),
    ] = ""
    organization_id: Annotated[
        str,
        Field(
            description="Organization ID of the new project. Only required if creating a new project."
        ),
    ] = ""


@router.post("/v2/projects/import/template")
@handle_exception
async def import_template(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    params: Annotated[TemplateImportQuery, Query()],
) -> ProjectRead:
    # Fetch the project
    async with async_session() as session:
        template = await session.get(Project, params.template_id)
    if template is None:
        raise ResourceNotFoundError(f'Template "{params.template_id}" is not found.')
    # Export template
    pa_table = await _export_project_as_pa_table(
        request=request,
        user=user,
        project=template,
    )
    # Import
    return await _import_project_from_pa_table(
        request,
        user,
        organization_id=params.organization_id,
        project_id=params.project_id,
        pa_table=pa_table,
    )
