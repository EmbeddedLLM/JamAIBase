from enum import StrEnum
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Path,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse

from owl.db import AsyncSession, yield_async_session
from owl.routers.projects import oss as v2
from owl.types import (
    OkResponse,
    Page,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    UserAuth,
)
from owl.utils.auth import auth_user
from owl.utils.exceptions import handle_exception

router = APIRouter()


@router.post("/v1/projects")
@handle_exception
async def create_project(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    body: ProjectCreate,
    project_id: str = "",
) -> ProjectRead:
    return await v2.create_project(request, user, session, body, project_id=project_id)


class AdminOrderBy(StrEnum):
    ID = "id"
    NAME = "name"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@router.get("/v1/projects")
@handle_exception
async def list_projects(
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    organization_id: Annotated[str, Query(min_length=1, description='Organization ID "org_xxx".')],
    search_query: Annotated[
        str,
        Query(
            max_length=10_000,
            description='_Optional_. A string to search for within project names as a filter. Defaults to "" (no filter).',
        ),
    ] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(gt=0, le=100)] = 100,
    order_by: Annotated[
        AdminOrderBy,
        Query(
            min_length=1,
            description='_Optional_. Sort projects by this attribute. Defaults to "updated_at".',
        ),
    ] = AdminOrderBy.UPDATED_AT,
    order_descending: Annotated[
        bool,
        Query(description="_Optional_. Whether to sort by descending order. Defaults to True."),
    ] = True,
) -> Page[ProjectRead]:
    params = v2.ListProjectQuery(
        offset=offset,
        limit=limit,
        order_by=order_by,
        order_ascending=not order_descending,
        organization_id=organization_id,
        search_query=search_query,
    )
    return await v2.list_projects(user, session, params)


@router.get("/v1/projects/{project_id}")
@handle_exception
async def get_project(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    project_id: Annotated[str, Path(min_length=1, description='Project ID "proj_xxx".')],
) -> ProjectRead:
    return await v2.get_project(request, user, session, project_id)


@router.patch("/v1/projects")
@handle_exception
async def update_project(
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    project_id: Annotated[str, Query(min_length=1, description="Project ID.")],
    body: ProjectUpdate,
) -> ProjectRead:
    return await v2.update_project(user, session, project_id, body)


@router.delete("/v1/projects/{project_id}")
@handle_exception
async def delete_project(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    project_id: Annotated[str, Path(min_length=1, description='Project ID "proj_xxx".')],
) -> OkResponse:
    return await v2.delete_project(request, user, session, project_id)


@router.get("/v1/projects/{project_id}/export")
@handle_exception
async def export_project(
    request: Request,
    bg_tasks: BackgroundTasks,
    user: Annotated[UserAuth, Depends(auth_user)],
    project_id: Annotated[str, Path(min_length=1, description='Project ID "proj_xxx".')],
) -> FileResponse:
    return await v2.export_project(request, bg_tasks, user, project_id)


@router.post("/v1/projects/import/{organization_id}")
@handle_exception
async def import_project(
    request: Request,
    user: Annotated[UserAuth, Depends(auth_user)],
    organization_id: Annotated[str, Path(min_length=1, description='Organization ID "org_xxx".')],
    file: Annotated[UploadFile, File(description="Project or Template Parquet file.")],
    project_id_dst: Annotated[
        str,
        Form(
            description=(
                "_Optional_. ID of the project to import tables into. "
                "Defaults to creating new project."
            ),
        ),
    ] = "",
) -> ProjectRead:
    data = v2.ProjectImportFormData(
        file=file,
        project_id=project_id_dst,
        organization_id=organization_id,
    )
    return await v2.import_project(request, user, data)
