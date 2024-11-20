import pathlib
from datetime import datetime
from io import BytesIO
from os.path import join
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Annotated, Literal, Mapping

import pyarrow as pa
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
from loguru import logger
from pyarrow.parquet import read_table as read_parquet_table
from pyarrow.parquet import write_table as write_parquet_table
from sqlalchemy import func
from sqlmodel import Session, select

from jamaibase.exceptions import (
    BadInputError,
    ForbiddenError,
    ResourceExistsError,
    ResourceNotFoundError,
    UpgradeTierError,
    make_validation_error,
)
from jamaibase.utils.io import json_dumps, json_loads, read_json
from owl.configs.manager import CONFIG, ENV_CONFIG
from owl.db import MAIN_ENGINE, UserSQLModel, cached_text, create_sql_tables
from owl.db.gen_table import GenerativeTable
from owl.protocol import (
    AdminOrderBy,
    ModelListConfig,
    Name,
    OkResponse,
    Page,
    TableMeta,
    TableMetaResponse,
    TableType,
    TemplateMeta,
)
from owl.utils import datetime_now_iso
from owl.utils.auth import WRITE_METHODS, AuthReturn, auth_user
from owl.utils.crypt import generate_key
from owl.utils.exceptions import handle_exception

if ENV_CONFIG.is_oss:
    from owl.db.oss_admin import (
        Organization,
        OrganizationRead,
        Project,
        ProjectCreate,
        ProjectRead,
        ProjectUpdate,
    )
else:
    from owl.db.cloud_admin import (
        Organization,
        OrganizationRead,
        Project,
        ProjectCreate,
        ProjectRead,
        ProjectUpdate,
    )


CURR_DIR = pathlib.Path(__file__).resolve().parent
TEMPLATE_DIR = CURR_DIR.parent / "templates"
router = APIRouter()


@router.on_event("startup")
async def startup():
    create_sql_tables(UserSQLModel, MAIN_ENGINE)


def _get_session():
    with Session(MAIN_ENGINE) as session:
        yield session


def _check_access(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    auth_info: AuthReturn,
    org_or_id: str | Organization,
) -> Organization:
    if isinstance(org_or_id, str):
        if ENV_CONFIG.is_oss:
            # OSS only has one default organization
            org_or_id = ENV_CONFIG.default_org_id
        organization = session.get(Organization, org_or_id)
        if organization is None:
            raise ResourceNotFoundError(f'Organization "{org_or_id}" is not found.')
    else:
        organization = org_or_id
    if ENV_CONFIG.is_oss:
        return organization

    user, org = auth_info
    if user is not None:
        user_roles = {m.organization_id: m.role for m in user.member_of}
        user_role = user_roles.get(organization.id, None)
        if user_role is None:
            raise ForbiddenError(f'You do not have access to organization "{organization.id}".')
        if user_role == "guest" and request.method in WRITE_METHODS:
            raise ForbiddenError(
                f'You do not have write access to organization "{organization.id}".'
            )
    if org is not None and org.id != organization.id:
        raise ForbiddenError(f'You do not have access to organization "{organization.id}".')
    # Non-activated orgs can only perform GET requests
    if (not organization.active) and (request.method != "GET"):
        raise UpgradeTierError(f'Your organization "{organization.id}" is not activated.')
    return organization


def _get_organization_from_path(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    auth_info: Annotated[AuthReturn, Depends(auth_user)],
    organization_id: Annotated[str, Path(min_length=1, description='Organization ID "org_xxx".')],
) -> Organization:
    return _check_access(
        session=session, request=request, auth_info=auth_info, org_or_id=organization_id
    )


def _get_organization_from_query(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    auth_info: Annotated[AuthReturn, Depends(auth_user)],
    organization_id: Annotated[str, Query(min_length=1, description='Organization ID "org_xxx".')],
) -> Organization:
    return _check_access(
        session=session, request=request, auth_info=auth_info, org_or_id=organization_id
    )


def _get_project_from_path(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    auth_info: Annotated[AuthReturn, Depends(auth_user)],
    project_id: Annotated[str, Path(min_length=1, description='Project ID "proj_xxx".')],
) -> Project:
    proj = session.get(Project, project_id)
    if proj is None:
        raise ResourceNotFoundError(f'Project "{project_id}" is not found.')
    _check_access(
        session=session, request=request, auth_info=auth_info, org_or_id=proj.organization
    )
    return proj


@router.get("/v1/models/{organization_id}")
@handle_exception
def get_org_model_config(
    organization: Annotated[Organization, Depends(_get_organization_from_path)],
) -> ModelListConfig:
    # Get only org models
    return ModelListConfig.model_validate(organization.models)


@router.patch("/v1/models/{organization_id}")
@handle_exception
def set_org_model_config(
    *,
    session: Annotated[Session, Depends(_get_session)],
    organization: Annotated[Organization, Depends(_get_organization_from_path)],
    body: ModelListConfig,
) -> OkResponse:
    # Validate
    _ = body + CONFIG.get_model_config()
    for m in body.models:
        m.owned_by = "custom"
    organization.models = body.model_dump(mode="json")
    organization.updated_at = datetime_now_iso()
    session.add(organization)
    session.commit()
    return OkResponse()


@router.post("/v1/projects")
@handle_exception
def create_project(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    auth_info: Annotated[AuthReturn, Depends(auth_user)],
    body: ProjectCreate,
) -> ProjectRead:
    if ENV_CONFIG.is_oss:
        body.organization_id = ENV_CONFIG.default_org_id
    _check_access(
        session=session, request=request, auth_info=auth_info, org_or_id=body.organization_id
    )
    same_name_count = session.exec(
        select(
            func.count(Project.id).filter(
                Project.organization_id == body.organization_id, Project.name == body.name
            )
        )
    ).one()
    if same_name_count > 0:
        raise ResourceExistsError("Project with the same name exists.")
    project_id = generate_key(24, "proj_")
    while session.get(Project, project_id) is not None:
        project_id = generate_key(24, "proj_")
    proj = Project(
        id=project_id,
        name=body.name,
        organization_id=body.organization_id,
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    logger.info(f"{request.state.id} - Project created: {proj}")
    return ProjectRead(
        **proj.model_dump(),
        organization=OrganizationRead(
            **proj.organization.model_dump(),
            members=proj.organization.members,
        ).decrypt(ENV_CONFIG.owl_encryption_key_plain),
    )


@router.patch("/v1/projects")
@handle_exception
def update_project(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    auth_info: Annotated[AuthReturn, Depends(auth_user)],
    body: ProjectUpdate,
) -> ProjectRead:
    proj = session.get(Project, body.id)
    if proj is None:
        raise ResourceNotFoundError(f'Project "{body.id}" is not found.')
    _check_access(
        session=session, request=request, auth_info=auth_info, org_or_id=proj.organization
    )
    for key, value in body.model_dump(exclude=["id"], exclude_none=True).items():
        if key == "name":
            same_name_count = session.exec(
                select(
                    func.count(Project.id).filter(
                        Project.organization_id == proj.organization_id,
                        Project.name == body.name,
                    )
                )
            ).one()
            if same_name_count > 0:
                raise ResourceExistsError("Project with the same name exists.")
        setattr(proj, key, value)
    proj.updated_at = datetime_now_iso()
    session.add(proj)
    session.commit()
    session.refresh(proj)
    logger.info(f"{request.state.id} - Project updated: {proj}")
    return ProjectRead(
        **proj.model_dump(),
        organization=OrganizationRead(
            **proj.organization.model_dump(),
            members=proj.organization.members,
        ).decrypt(ENV_CONFIG.owl_encryption_key_plain),
    )


@router.patch("/v1/projects/{project_id}")
@handle_exception
def set_project_updated_at(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    project: Annotated[Project, Depends(_get_project_from_path)],
    updated_at: Annotated[
        str | None, Query(min_length=1, description="Project update datetime (ISO 8601 UTC).")
    ] = None,
) -> OkResponse:
    if updated_at is None:
        updated_at = datetime_now_iso()
    else:
        try:
            tz = str(datetime.fromisoformat(updated_at).tzinfo)
        except Exception as e:
            raise BadInputError("`updated_at` must be a ISO 8601 UTC datetime string.") from e
        if tz != "UTC":
            raise BadInputError(f'`updated_at` must be UTC, but received "{tz}".')
    project.updated_at = updated_at
    session.add(project)
    session.commit()
    logger.info(f"{request.state.id} - Project updated_at set to: {updated_at}")
    return OkResponse()


@router.get("/v1/projects")
@handle_exception
def list_projects(
    *,
    session: Annotated[Session, Depends(_get_session)],
    organization: Annotated[Organization, Depends(_get_organization_from_query)],
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
    organization_id = organization.id
    org = session.get(Organization, organization_id)
    if org is None:
        raise ResourceNotFoundError(f'Organization "{organization_id}" is not found.')
    search_query = search_query.strip()
    selection = select(Project).where(Project.organization_id == organization_id)
    count = func.count(Project.id).filter(Project.organization_id == organization_id)
    if search_query:
        selection = selection.where(Project.name.ilike(f"%{search_query}%"))
        count = count.filter(Project.name.ilike(f"%{search_query}%"))
    order_by = f"LOWER({order_by})"
    selection = selection.order_by(
        cached_text(f"{order_by} DESC" if order_descending else f"{order_by} ASC")
    )
    projects = session.exec(selection.offset(offset).limit(limit)).all()
    total = session.exec(select(count)).one()
    return Page[ProjectRead](
        items=projects,
        offset=offset,
        limit=limit,
        total=total,
    )


@router.get("/v1/projects/{project_id}")
@handle_exception
def get_project(
    project: Annotated[Project, Depends(_get_project_from_path)],
) -> ProjectRead:
    proj = ProjectRead(
        **project.model_dump(),
        organization=OrganizationRead(
            **project.organization.model_dump(),
            members=project.organization.members,
        ).decrypt(ENV_CONFIG.owl_encryption_key_plain),
    )
    return proj


@router.delete("/v1/projects/{project_id}")
@handle_exception
def delete_project(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    project: Annotated[Project, Depends(_get_project_from_path)],
) -> OkResponse:
    project_id = project.id
    session.delete(project)
    session.commit()
    logger.info(f"{request.state.id} - Project deleted: {project_id}")
    return OkResponse()


def _package_project_tables(project: Project) -> list[tuple[str, TableMetaResponse, bytes]]:
    data = []
    table_types = [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]
    for table_type in table_types:
        table = GenerativeTable.from_ids(project.organization_id, project.id, table_type)
        with table.create_session() as session:
            # Lance tables could be on S3 so we use list_meta instead of listdir
            batch_size, offset, total = 200, 0, 1
            while offset < total:
                metas, total = table.list_meta(
                    session,
                    offset=offset,
                    limit=batch_size,
                    remove_state_cols=True,
                    parent_id=None,
                )
                offset += batch_size
                for meta in metas:
                    with BytesIO() as f:
                        table.dump_parquet(session=session, table_id=meta.id, dest=f)
                        data.append((table_type.value, meta, f.getvalue()))
    return data


def _export_project(
    *,
    request: Request,
    bg_tasks: BackgroundTasks,
    project: Project,
    output_file_ext: str,
    compression: Literal["NONE", "ZSTD", "LZ4", "SNAPPY"] = "ZSTD",
    extra_metas: Mapping[str, str] | None = None,
) -> FileResponse:
    t0 = perf_counter()
    # Check quota
    request.state.billing.check_egress_quota()
    # Check extra metadata
    extra_metas = extra_metas or {}
    for k, v in extra_metas.items():
        if not isinstance(v, str):
            raise BadInputError(f'Invalid extra metadata: value of key "{k}" is not a string.')
    # Dump all tables as parquet files
    data = _package_project_tables(project)
    if len(data) == 0:
        metas = []
        pa_table = pa.Table.from_pydict({"table_type": pa.array([]), "data": pa.array([])})
    else:
        metas = []
        for table_type, meta, _ in data:
            metas.append({"table_type": table_type, "table_meta": meta.model_dump(mode="json")})
        data = list(zip(*data, strict=True))
        pa_table = pa.Table.from_pydict(
            {"table_type": pa.array(data[0]), "data": pa.array(data[2])}
        )
    pa_meta = pa_table.schema.metadata or {}
    pa_table = pa_table.replace_schema_metadata(
        {
            "project_meta": project.model_dump_json(),
            "table_metas": json_dumps(metas),
            **extra_metas,
            **pa_meta,
        }
    )
    tmp_dir = TemporaryDirectory()
    filename = f"{project.id}{output_file_ext}"
    filepath = join(tmp_dir.name, filename)
    # Keep a reference to the directory and only delete upon completion
    bg_tasks.add_task(tmp_dir.cleanup)
    write_parquet_table(pa_table, where=filepath, compression=compression)
    logger.info(
        f'{request.state.id} - Project "{project.id}" exported in {perf_counter() - t0:,.2f} s.'
    )
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.get("/v1/projects/{project_id}/export")
@handle_exception
def export_project(
    *,
    request: Request,
    bg_tasks: BackgroundTasks,
    project: Annotated[Project, Depends(_get_project_from_path)],
    compression: Annotated[
        Literal["NONE", "ZSTD", "LZ4", "SNAPPY"],
        Query(description="Parquet compression codec."),
    ] = "ZSTD",
) -> FileResponse:
    return _export_project(
        request=request,
        bg_tasks=bg_tasks,
        project=project,
        output_file_ext=".parquet",
        compression=compression,
    )


@router.get("/v1/projects/{project_id}/export/template")
@handle_exception
def export_project_as_template(
    *,
    request: Request,
    bg_tasks: BackgroundTasks,
    project: Annotated[Project, Depends(_get_project_from_path)],
    name: Annotated[Name, Query(description="Template name.")],
    tags: Annotated[list[str], Query(description="Template tags.")],
    description: Annotated[str, Query(description="Template description.")],
    compression: Annotated[
        Literal["NONE", "ZSTD", "LZ4", "SNAPPY"],
        Query(description="Parquet compression codec."),
    ] = "ZSTD",
) -> FileResponse:
    template_meta = TemplateMeta(name=name, description=description, tags=tags)
    return _export_project(
        request=request,
        bg_tasks=bg_tasks,
        project=project,
        output_file_ext=".template.parquet",
        compression=compression,
        extra_metas={"template_meta": template_meta.model_dump_json()},
    )


@router.post("/v1/projects/import/{organization_id}")
@handle_exception
async def import_project(
    *,
    session: Annotated[Session, Depends(_get_session)],
    request: Request,
    organization: Annotated[Organization, Depends(_get_organization_from_path)],
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
    t0 = perf_counter()
    organization_id = organization.id
    if project_id_dst == "":
        proj = None
    else:
        proj = session.get(Project, project_id_dst)
        if proj is None:
            raise ResourceNotFoundError(f'Project "{project_id_dst}" is not found.')
        if proj.organization_id != organization_id:
            raise ForbiddenError(
                f'You do not have access to organization "{proj.organization_id}".'
            )
    try:
        with BytesIO(await file.read()) as source:
            # Read metadata
            pa_table = read_parquet_table(source, columns=[], use_threads=False, memory_map=True)
            metadata = pa_table.schema.metadata
            if proj is None:
                # Create the project
                project_meta = metadata.get(b"template_meta", None)
                if project_meta is None:
                    project_meta = metadata.get(b"project_meta", None)
                if project_meta is None:
                    raise BadInputError("Missing template or table metadata in the Parquet file.")
                try:
                    project_meta = json_loads(project_meta)
                except Exception as e:
                    raise BadInputError(
                        "Invalid template or table metadata in the Parquet file."
                    ) from e
                proj = Project(name=project_meta["name"], organization_id=organization_id)
                session.add(proj)
                session.commit()
                session.refresh(proj)
                project_id_dst = proj.id
            else:
                # Check if all the table IDs have no conflict
                try:
                    type_metas = json_loads(metadata[b"table_metas"])
                except KeyError as e:
                    raise BadInputError("Missing table metadata in the Parquet file.") from e
                except Exception as e:
                    raise BadInputError("Invalid table metadata in the Parquet file.") from e
                for type_meta in type_metas:
                    table = GenerativeTable.from_ids(
                        organization_id, project_id_dst, type_meta["table_type"]
                    )
                    with table.create_session() as gt_sess:
                        table_id = type_meta["table_meta"]["id"]
                        meta = gt_sess.get(TableMeta, table_id)
                        if meta is not None:
                            raise ResourceExistsError(f'Table "{table_id}" already exists.')
            logger.info(
                f'{request.state.id} - Project "{proj.id}" metadata imported in {perf_counter() - t0:,.2f} s.'
            )
            # Create the tables
            pa_table = read_parquet_table(source, columns=None, use_threads=False, memory_map=True)
            for row in pa_table.to_pylist():
                table_type = row["table_type"]
                with BytesIO(row["data"]) as pq_source:
                    table = GenerativeTable.from_ids(organization_id, project_id_dst, table_type)
                    with table.create_session() as gt_sess:
                        await table.import_parquet(
                            session=gt_sess,
                            source=pq_source,
                            table_id_dst=None,
                        )
        logger.info(
            f'{request.state.id} - Project "{proj.id}" imported in {perf_counter() - t0:,.2f} s.'
        )
    except pa.ArrowInvalid as e:
        raise make_validation_error(
            e,
            loc=("body", "file"),
        ) from e
    return ProjectRead(
        **proj.model_dump(),
        organization=OrganizationRead(
            **proj.organization.model_dump(),
            members=proj.organization.members,
        ).decrypt(ENV_CONFIG.owl_encryption_key_plain),
    )


@router.post("/v1/projects/import/{organization_id}/templates/{template_id}")
@handle_exception
async def import_project_from_template(
    *,
    session: Annotated[Session, Depends(_get_session)],
    organization: Annotated[Organization, Depends(_get_organization_from_path)],
    template_id: Annotated[str, Path(description="ID of the template to import from.")],
    project_id_dst: Annotated[
        str,
        Query(
            description=(
                "_Optional_. ID of the project to import tables into. "
                "Defaults to creating new project."
            ),
        ),
    ] = "",
) -> ProjectRead:
    template_dir = TEMPLATE_DIR / template_id
    if not template_dir.is_dir():
        raise ResourceNotFoundError(f'Template "{template_id}" is not found.')
    organization_id = organization.id
    if project_id_dst == "":
        proj = None
    else:
        proj = session.get(Project, project_id_dst)
        if proj is None:
            raise ResourceNotFoundError(f'Project "{project_id_dst}" is not found.')
        if proj.organization_id != organization_id:
            raise ForbiddenError(
                f'You do not have access to organization "{proj.organization_id}".'
            )
    if proj is None:
        # Create the project
        template_meta = read_json(template_dir / "template_meta.json")
        proj = Project(name=template_meta["name"], organization_id=organization_id)
        session.add(proj)
        session.commit()
        session.refresh(proj)
        project_id_dst = proj.id
    else:
        # Check if all the table IDs have no conflict
        for table_type in [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]:
            table_dir = template_dir / table_type
            if not table_dir.is_dir():
                continue
            table = GenerativeTable.from_ids(organization_id, project_id_dst, table_type)
            for pq_source in table_dir.iterdir():
                if not pq_source.is_file():
                    continue
                pa_table = read_parquet_table(
                    pq_source, columns=[], use_threads=False, memory_map=True
                )
                try:
                    pq_meta = TableMeta.model_validate_json(
                        pa_table.schema.metadata[b"gen_table_meta"]
                    )
                except KeyError as e:
                    raise BadInputError("Missing table metadata in the Parquet file.") from e
                except Exception as e:
                    raise BadInputError("Invalid table metadata in the Parquet file.") from e
                with table.create_session() as gt_sess:
                    meta = gt_sess.get(TableMeta, pq_meta.id)
                    if meta is not None:
                        raise ResourceExistsError(f'Table "{pq_meta.id}" already exists.')
    # Create the tables
    for table_type in [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]:
        table_dir = template_dir / table_type
        if not table_dir.is_dir():
            continue
        for pq_source in table_dir.iterdir():
            if not pq_source.is_file():
                continue
            table = GenerativeTable.from_ids(organization_id, project_id_dst, table_type)
            with table.create_session() as gt_sess:
                await table.import_parquet(
                    session=gt_sess,
                    source=pq_source,
                    table_id_dst=None,
                )
    return ProjectRead(
        **proj.model_dump(),
        organization=OrganizationRead(
            **proj.organization.model_dump(),
            members=proj.organization.members,
        ).decrypt(ENV_CONFIG.owl_encryption_key_plain),
    )
