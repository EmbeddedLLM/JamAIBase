import re
from asyncio import sleep
from io import BytesIO
from os.path import join, splitext
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Annotated, Any

from celery.result import AsyncResult
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    Path,
    Query,
    Request,
    Response,
)
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from pydantic import Field

from owl.configs import CACHE
from owl.db.gen_executor import MultiRowGenExecutor
from owl.db.gen_table import (
    ActionTable,
    ChatTable,
    ColumnMetadata,
    KnowledgeTable,
    TableMetadata,
)
from owl.docparse import GeneralDocLoader
from owl.tasks.gen_table import import_gen_table
from owl.types import (
    ActionTableSchemaCreate,
    ChatTableSchemaCreate,
    ChatThreadsResponse,
    ColumnDropRequest,
    ColumnRenameRequest,
    ColumnReorderRequest,
    CSVDelimiter,
    DuplicateTableQuery,
    ExportTableDataQuery,
    FileEmbedFormData,
    GenConfigUpdateRequest,
    GetTableRowQuery,
    GetTableThreadsQuery,
    KnowledgeTableSchemaCreate,
    ListTableQuery,
    ListTableRowQuery,
    MultiRowAddRequest,
    MultiRowAddRequestWithLimit,
    MultiRowDeleteRequest,
    MultiRowRegenRequest,
    MultiRowUpdateRequestWithLimit,
    OkResponse,
    OrganizationRead,
    Page,
    ProjectRead,
    RenameTableQuery,
    SearchRequest,
    TableDataImportFormData,
    TableImportFormData,
    TableImportProgress,
    TableMetaResponse,
    TableSchemaCreate,
    TableType,
    URLEmbedFormData,
    UserAuth,
)
from owl.url_loader import load_url_content
from owl.utils.auth import auth_user_project, has_permissions
from owl.utils.billing import BillingManager
from owl.utils.exceptions import (
    BadInputError,
    ServerBusyError,
    UnsupportedMediaTypeError,
    handle_exception,
)
from owl.utils.io import EMBED_WHITE_LIST_MIME, guess_mime, s3_temporary_file, s3_upload
from owl.utils.lm import LMEngine
from owl.utils.mcp import MCP_TOOL_TAG

router = APIRouter()


TABLE_CLS: dict[TableType, ActionTable | KnowledgeTable | ChatTable] = {
    TableType.ACTION: ActionTable,
    TableType.KNOWLEDGE: KnowledgeTable,
    TableType.CHAT: ChatTable,
}


async def _create_table(
    *,
    request: Request,
    user: UserAuth,
    project: ProjectRead,
    org: OrganizationRead,
    table_type: TableType,
    schema: TableSchemaCreate,
) -> TableMetaResponse:
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    kwargs = dict(
        project_id=project.id,
        table_metadata=TableMetadata(
            table_id=schema.id,
            created_by=user.id,
        ),
        column_metadata_list=[
            ColumnMetadata(
                table_id=schema.id,
                column_id=col.id,
                dtype=col.dtype.to_column_type(),
                vlen=col.vlen,
                gen_config=col.gen_config,
            )
            for col in schema.cols
        ],
    )
    if table_type == TableType.KNOWLEDGE:
        table = await KnowledgeTable.create_table(embedding_model=schema.embedding_model, **kwargs)
    else:
        table = await TABLE_CLS[table_type].create_table(**kwargs)
    return table.v1_meta_response


@router.post(
    "/v2/gen_tables/action",
    summary="Create an action table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def create_action_table(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: ActionTableSchemaCreate,
) -> TableMetaResponse:
    user, project, org = auth_info
    return await _create_table(
        request=request,
        user=user,
        project=project,
        org=org,
        table_type=TableType.ACTION,
        schema=body,
    )


@router.post(
    "/v2/gen_tables/knowledge",
    summary="Create a knowledge table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def create_knowledge_table(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: KnowledgeTableSchemaCreate,
) -> TableMetaResponse:
    user, project, org = auth_info
    return await _create_table(
        request=request,
        user=user,
        project=project,
        org=org,
        table_type=TableType.KNOWLEDGE,
        schema=body,
    )


@router.post(
    "/v2/gen_tables/chat",
    summary="Create a chat table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def create_chat_table(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: ChatTableSchemaCreate,
) -> TableMetaResponse:
    user, project, org = auth_info
    return await _create_table(
        request=request,
        user=user,
        project=project,
        org=org,
        table_type=TableType.CHAT,
        schema=body,
    )


@router.post(
    "/v2/gen_tables/{table_type}/duplicate",
    summary="Duplicate a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def duplicate_table(
    *,
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[DuplicateTableQuery, Query()],
) -> TableMetaResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    table = await TABLE_CLS[table_type].open_table(
        project_id=project.id, table_id=params.table_id_src
    )
    table = await table.duplicate_table(
        project_id=project.id,
        table_id_src=params.table_id_src,
        table_id_dst=params.table_id_dst,
        include_data=params.include_data,
        create_as_child=params.create_as_child,
        created_by=user.id,
    )
    return table.v1_meta_response


@router.get(
    "/v2/gen_tables/{table_type}",
    summary="Get a specific table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def get_table(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: Annotated[str, Query(description="Name of the table to fetch.")],
) -> TableMetaResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=table_id)
    return table.v1_meta_response


class _ListTableQuery(ListTableQuery):
    created_by: Annotated[
        str | None,
        Field(
            min_length=1,
            description="Return tables created by this user. Defaults to None (return all tables).",
        ),
    ] = None


@router.get(
    "/v2/gen_tables/{table_type}/list",
    summary="List tables of a specific type.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def list_tables(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[_ListTableQuery, Query()],
) -> Page[TableMetaResponse]:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    metas = await TABLE_CLS[table_type].list_tables(
        project_id=project.id,
        limit=params.limit,
        offset=params.offset,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        created_by=getattr(params, "created_by", None),
        parent_id=params.parent_id,
        search_query=params.search_query,
        count_rows=params.count_rows,
    )
    return metas


@router.post(
    "/v2/gen_tables/{table_type}/rename",
    summary="Rename a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def rename_table(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[RenameTableQuery, Query()],
) -> TableMetaResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(
        project_id=project.id, table_id=params.table_id_src
    )
    table = await table.rename_table(params.table_id_dst)
    return table.v1_meta_response


@router.delete(
    "/v2/gen_tables/{table_type}",
    summary="Delete a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def delete_table(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: Annotated[str, Query(description="Name of the table to be deleted.")],
) -> OkResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=table_id)
    await table.drop_table()
    return OkResponse()


@router.post(
    "/v2/gen_tables/{table_type}/columns/add",
    summary="Add columns to a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def add_columns(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: TableSchemaCreate,
) -> TableMetaResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=body.id)
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    for col in body.cols:
        table = await table.add_column(
            ColumnMetadata(
                table_id=body.id,
                column_id=col.id,
                dtype=col.dtype.to_column_type(),
                vlen=col.vlen,
                gen_config=col.gen_config,
            )
        )
    return table.v1_meta_response


@router.post(
    "/v2/gen_tables/{table_type}/columns/rename",
    summary="Rename columns in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def rename_columns(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: ColumnRenameRequest,
) -> TableMetaResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=body.table_id)
    table = await table.rename_columns(body.column_map)
    return table.v1_meta_response


@router.patch(
    "/v2/gen_tables/{table_type}/gen_config",
    summary="Update generation configuration for table columns.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def update_gen_config(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    updates: GenConfigUpdateRequest,
) -> TableMetaResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(
        project_id=project.id, table_id=updates.table_id
    )
    table = await table.update_gen_config(update_mapping=updates.column_map)
    return table.v1_meta_response


@router.post(
    "/v2/gen_tables/{table_type}/columns/reorder",
    summary="Reorder columns in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def reorder_columns(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: ColumnReorderRequest,
) -> TableMetaResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=body.table_id)
    table = await table.reorder_columns(body.column_names)
    return table.v1_meta_response


@router.post(
    "/v2/gen_tables/{table_type}/columns/drop",
    summary="Drop columns from a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def drop_columns(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: ColumnDropRequest,
) -> TableMetaResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=body.table_id)
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    table = await table.drop_columns(body.column_names)
    return table.v1_meta_response


@router.post(
    "/v2/gen_tables/{table_type}/rows/add",
    summary="Add rows to a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def add_rows(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: MultiRowAddRequestWithLimit,
):
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=body.table_id)
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    # Validate data
    [table.validate_row_data(d) for d in body.data]
    executor = MultiRowGenExecutor(
        request=request,
        table=table,
        organization=org,
        project=project,
        body=body,
    )
    if body.stream:
        return StreamingResponse(
            content=await executor.generate(),
            status_code=200,
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )
    else:
        return await executor.generate()


@router.get(
    "/v2/gen_tables/{table_type}/rows/list",
    summary="List rows in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def list_rows(
    *,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[ListTableRowQuery, Query()],
) -> Page[dict[str, Any]]:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=params.table_id)
    rows = await table.list_rows(
        limit=params.limit,
        offset=params.offset,
        order_by=[params.order_by],
        order_ascending=params.order_ascending,
        columns=params.columns,
        where=params.where,
        search_query=params.search_query,
        search_columns=params.search_columns,
        remove_state_cols=False,
    )
    return Page[dict[str, Any]](
        items=table.postprocess_rows(
            rows.items,
            float_decimals=params.float_decimals,
            vec_decimals=params.vec_decimals,
        ),
        offset=params.offset,
        limit=params.limit,
        total=rows.total,
    )


@router.get(
    "/v2/gen_tables/{table_type}/rows",
    summary="Get a specific row from a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def get_row(
    *,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[GetTableRowQuery, Query()],
) -> dict[str, Any]:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=params.table_id)
    row = await table.get_row(
        row_id=params.row_id,
        columns=params.columns,
        remove_state_cols=False,
    )
    row = table.postprocess_rows(
        [row],
        float_decimals=params.float_decimals,
        vec_decimals=params.vec_decimals,
    )[0]
    return row


@router.get(
    "/v2/gen_tables/{table_type}/threads",
    summary="Get all multi-turn / conversation threads from a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def get_conversation_threads(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[GetTableThreadsQuery, Query()],
) -> ChatThreadsResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table_id = params.table_id
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=table_id)
    if params.column_ids:
        for column_id in params.column_ids:
            table.check_multiturn_column(column_id)
        cols = params.column_ids
    else:
        cols = [c.column_id for c in table.column_metadata if c.is_chat_column]
    return ChatThreadsResponse(
        threads={
            c: await table.get_conversation_thread(
                column_id=c,
                row_id=params.row_id,
                include_row=params.include_row,
            )
            for c in cols
        },
        table_id=table_id,
    )


@router.post(
    "/v2/gen_tables/{table_type}/hybrid_search",
    summary="Perform hybrid search on a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def hybrid_search(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: SearchRequest,
) -> list[dict[str, Any]]:
    # TODO: Maybe this should return `Page` instead of `list`
    def split_query_to_or_terms(query):
        # Regular expression to match either quoted phrases or words
        pattern = r'("[^"]*"|\S+)'
        parts = re.findall(pattern, query)
        return " OR ".join(parts)

    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=body.table_id)
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    lm = LMEngine(
        organization=org,
        project=project,
        request=request,
    )
    # Do a split and OR join for fts query
    fts_query = split_query_to_or_terms(body.query)

    # As of 2025-04-17, this endpoint does not perform query rewrite
    rows = await table.hybrid_search(
        fts_query=fts_query,
        vs_query=body.query,
        embedding_fn=lm.embed_query_as_vector,
        vector_column_names=None,
        limit=body.limit,
        offset=0,
        remove_state_cols=False,
    )
    # Rerank
    if len(rows) > 0 and body.reranking_model is not None:
        order = (
            await lm.rerank_documents(
                model=body.reranking_model,
                query=body.query,
                documents=table.rows_to_documents(rows),
            )
        ).results
        rows = [rows[i.index] for i in order]
    rows = rows[: body.limit]
    rows = table.postprocess_rows(
        rows,
        float_decimals=body.float_decimals,
        vec_decimals=body.vec_decimals,
    )
    return rows


@router.post(
    "/v2/gen_tables/{table_type}/rows/regen",
    summary="Regenerate rows in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def regen_rows(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: MultiRowRegenRequest,
):
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=body.table_id)
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    executor = MultiRowGenExecutor(
        request=request,
        table=table,
        organization=org,
        project=project,
        body=body,
    )
    if body.stream:
        return StreamingResponse(
            content=await executor.generate(),
            status_code=200,
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )
    else:
        return await executor.generate()


@router.patch(
    "/v2/gen_tables/{table_type}/rows",
    summary="Update rows in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def update_rows(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: MultiRowUpdateRequestWithLimit,
) -> OkResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=body.table_id)
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    # Validate data
    {row_id: table.validate_row_data(d) for row_id, d in body.data.items()}
    await table.update_rows(body.data)
    return OkResponse()


@router.post(
    "/v2/gen_tables/{table_type}/rows/delete",
    summary="Delete rows from a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
    tags=[MCP_TOOL_TAG, "organization.MEMBER", "project.MEMBER"],
)
@handle_exception
async def delete_rows(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: MultiRowDeleteRequest,
) -> OkResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=body.table_id)
    await table.delete_rows(row_ids=body.row_ids, where=body.where)
    return OkResponse()


@router.options(
    "/v2/gen_tables/knowledge/embed_file",
    summary="Get CORS preflight options for file embedding endpoint",
    description="Permissions: None, publicly accessible.",
)
@handle_exception
async def embed_file_options():
    headers = {
        "Allow": "POST, OPTIONS",
        "Accept": ", ".join(EMBED_WHITE_LIST_MIME),
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    return Response(content=None, headers=headers)


@router.options(
    "/v2/gen_tables/knowledge/embed_url",
    summary="Get CORS preflight options for URL embedding endpoint",
    description="Permissions: None, publicly accessible.",
)
@handle_exception
async def embed_url_options():
    headers = {
        "Allow": "POST, OPTIONS",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    return Response(content=None, headers=headers)


@router.post(
    "/v2/gen_tables/knowledge/embed_file",
    summary="Embed a file into a knowledge table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def embed_file(
    *,
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    data: Annotated[FileEmbedFormData, Form()],
) -> OkResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    # Validate the Content-Type of the uploaded file
    file_name = data.file.filename or data.file_name
    mime = guess_mime(file_name)
    if mime == "application/octet-stream":
        mime = data.file.content_type
    if mime not in EMBED_WHITE_LIST_MIME:
        raise UnsupportedMediaTypeError(
            f'File type "{mime}" is unsupported. Accepted types are: {", ".join(EMBED_WHITE_LIST_MIME)}'
        )
    table = await KnowledgeTable.open_table(
        project_id=project.id,
        table_id=data.table_id,
    )
    # Check quota
    request_id: str = request.state.id
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    # --- Store original file into S3 --- #
    file_content = await data.file.read()
    file_uri = await s3_upload(
        project.organization.id,
        project.id,
        file_content,
        content_type=mime,
        filename=file_name,
    )
    # --- Add into Knowledge Table --- #
    logger.info(f'{request_id} - Parsing file "{file_name}".')
    doc_parser = GeneralDocLoader(request_id=request_id)
    try:
        chunks = await doc_parser.load_document_chunks(
            file_name, file_content, data.chunk_size, data.chunk_overlap
        )
    except BadInputError as e:
        logger.warning(f'Failed to parse file "{file_uri}" due to error: {repr(e)}')
        raise
    except Exception as e:
        logger.warning(f'Failed to parse file "{file_uri}" due to error: {repr(e)}')
        raise BadInputError(
            (
                f'Sorry we encountered an issue while processing your file "{file_name}". '
                "Please ensure the file is not corrupted and is in a supported format."
            )
        ) from e
    logger.info(f'{request_id} - Embedding file "{file_name}" with {len(chunks):,d} chunks.')

    # --- Extract title --- #
    lm = LMEngine(
        organization=org,
        project=project,
        request=request,
    )
    ext = splitext(file_name)[1].lower()
    if ext in [".pdf", ".pptx", ".xlsx"]:
        first_page_chunks = [d.text for d in chunks if d.page == 1]
        # If the first page content is too short, use the first 8 chunks instead
        if len(first_page_chunks) < 3:
            first_page_chunks = [d.text for d in chunks[:8]]
        excerpt = "".join(first_page_chunks)[:50000]
    else:
        excerpt = "".join(d.text for d in chunks[:8])[:50000]
    logger.debug(f"{request_id} - Performing title extraction.")
    title = await lm.generate_title(excerpt=excerpt, model="")

    # --- Embed --- #
    title_embed = text_embeds = None
    for col in table.column_metadata:
        if col.column_id.lower() == "title embed":
            title_embed = await lm.embed_documents(
                model=col.gen_config.embedding_model,
                texts=[title],
                encoding_format="float",
            )
            title_embed = title_embed.data[0].embedding
        elif col.column_id.lower() == "text embed":
            text_embeds = await lm.embed_documents(
                model=col.gen_config.embedding_model,
                texts=[chunk.text for chunk in chunks],
                encoding_format="float",
            )
            text_embeds = [data.embedding for data in text_embeds.data]

    if title_embed is None or text_embeds is None or len(text_embeds) == 0:
        raise BadInputError(
            "Sorry we encountered an issue during embedding. If this issue persists, please contact support."
        )
    # --- Store into Knowledge Table --- #
    row_add_data = [
        {
            "Title": title,
            "Title Embed": title_embed,
            "Text": chunk.text,
            "Text Embed": text_embed,
            "File ID": file_uri,
            "Page": chunk.page,
        }
        for chunk, text_embed in zip(chunks, text_embeds, strict=True)
    ]
    await table.add_rows(row_add_data)
    return OkResponse()


@router.post(
    "/v2/gen_tables/knowledge/embed_url",
    summary="Embed a URL into a knowledge table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def embed_url(
    *,
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    data: Annotated[URLEmbedFormData, Form()],
) -> OkResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    # --- Fetch URL content --- #
    logger.info(f'Fetching content from URL "{data.url}".')
    try:
        file_content_str, file_name = await load_url_content(data.url)
        file_content = file_content_str.encode("utf-8")
    except ValueError as e:
        raise BadInputError(f"Invalid URL: {e}")
    except Exception as e:
        logger.warning(f'Failed to fetch URL "{data.url}" due to error: {repr(e)}')
        raise BadInputError(f"Failed to fetch URL content: {str(e)}")

    table = await KnowledgeTable.open_table(
        project_id=project.id,
        table_id=data.table_id,
    )
    # Check quota
    request_id: str = request.state.id
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()

    # --- Add into Knowledge Table --- #
    logger.info(f'{request_id} - Parsing content from "{data.url}".')
    doc_parser = GeneralDocLoader(request_id=request_id)
    try:
        chunks = await doc_parser.load_document_chunks(
            file_name, file_content, data.chunk_size, data.chunk_overlap
        )
    except BadInputError as e:
        logger.warning(f'Failed to parse content from "{data.url}" due to error: {repr(e)}')
        raise
    except Exception as e:
        logger.warning(f'Failed to parse content from "{data.url}" due to error: {repr(e)}')
        raise BadInputError(
            f'Sorry we encountered an issue while processing content from "{data.url}". '
            "Please ensure the URL is valid and contains parseable content."
        ) from e

    logger.info(f'{request_id} - Embedding content from "{data.url}" with {len(chunks):,d} chunks.')

    # --- Extract title --- #
    lm = LMEngine(
        organization=org,
        project=project,
        request=request,
    )
    first_page_chunks = [d.text for d in chunks[:8]]
    excerpt = "".join(first_page_chunks)[:50000]
    logger.debug(f"{request_id} - Performing title extraction.")
    title = await lm.generate_title(excerpt=excerpt, model="")

    # --- Embed --- #
    title_embed = text_embeds = None
    for col in table.column_metadata:
        if col.column_id.lower() == "title embed":
            title_embed = await lm.embed_documents(
                model=col.gen_config.embedding_model,
                texts=[title],
                encoding_format="float",
            )
            title_embed = title_embed.data[0].embedding
        elif col.column_id.lower() == "text embed":
            text_embeds = await lm.embed_documents(
                model=col.gen_config.embedding_model,
                texts=[chunk.text for chunk in chunks],
                encoding_format="float",
            )
            text_embeds = [data.embedding for data in text_embeds.data]

    if title_embed is None or text_embeds is None or len(text_embeds) == 0:
        raise BadInputError(
            "Sorry we encountered an issue during embedding. If this issue persists, please contact support."
        )
    # --- Store into Knowledge Table --- #
    row_add_data = [
        {
            "Title": title,
            "Title Embed": title_embed,
            "Text": chunk.text,
            "Text Embed": text_embed,
            "File ID": data.url,
            "Page": chunk.page,
        }
        for chunk, text_embed in zip(chunks, text_embeds, strict=True)
    ]
    await table.add_rows(row_add_data)
    return OkResponse()


@router.post(
    "/v2/gen_tables/{table_type}/import_data",
    summary="Import data into a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def import_table_data(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    data: Annotated[TableDataImportFormData, Form()],
):
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=data.table_id)
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    # Import data
    rows = await table.read_csv(
        input_path=BytesIO(await data.file.read()),
        column_id_mapping=None,
        delimiter=data.delimiter,
        ignore_info_columns=True,  # Ignore "ID" and "Updated at" columns
    )
    return await add_rows(
        request=request,
        auth_info=auth_info,
        table_type=table_type,
        body=MultiRowAddRequest(table_id=data.table_id, data=rows, stream=data.stream),
    )


@router.get(
    "/v2/gen_tables/{table_type}/export_data",
    summary="Export data from a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def export_table_data(
    request: Request,
    bg_tasks: BackgroundTasks,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[ExportTableDataQuery, Query()],
) -> FileResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=params.table_id)
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    # Temporary file
    ext = ".csv" if params.delimiter == CSVDelimiter.COMMA else ".tsv"
    tmp_dir = TemporaryDirectory()
    filename = f"{params.table_id}{ext}"
    filepath = join(tmp_dir.name, filename)
    # Keep a reference to the directory and only delete upon completion
    bg_tasks.add_task(tmp_dir.cleanup)
    # Export
    await table.export_data(
        output_path=filepath,
        columns=params.columns,
        where="",
        limit=None,
        offset=0,
        delimiter=params.delimiter,
    )
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.post(
    "/v2/gen_tables/{table_type}/import",
    summary="Import a table including its metadata.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def import_table(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    data: Annotated[TableImportFormData, Form()],
) -> TableMetaResponse | OkResponse:
    user, project, org = auth_info
    if not data.migrate:
        has_permissions(
            user,
            ["organization.MEMBER", "project.MEMBER"],
            organization_id=org.id,
            project_id=project.id,
        )
        # Check quota
        billing: BillingManager = request.state.billing
        billing.has_db_storage_quota()
        billing.has_egress_quota()
    # Import
    async with s3_temporary_file(await data.file.read(), "application/vnd.apache.parquet") as uri:
        result: AsyncResult = import_gen_table.delay(
            source=uri,
            project_id=project.id,
            table_type=table_type,
            table_id_dst=data.table_id_dst,
            reupload_files=data.reupload or not data.migrate,
            progress_key=data.progress_key,
            verbose=data.migrate,
        )
        # Poll progress
        initial_wait: float = 0.5
        max_wait: float = 30 * 60  # 30 minutes
        t0 = perf_counter()
        i = 1
        while (not result.ready()) and ((perf_counter() - t0) < max_wait):
            await sleep(min(initial_wait * i, 5.0))
            if not data.blocking:
                prog = await CACHE.get_progress(data.progress_key, TableImportProgress)
                if prog.load_data.progress == 100:
                    return OkResponse(progress_key=data.progress_key)
            i += 1
        if (perf_counter() - t0) >= max_wait:
            raise ServerBusyError(
                "Table import took too long to complete. Please try again later."
            )
        return TableMetaResponse.model_validate_json(result.get(propagate=True))


@router.get(
    "/v2/gen_tables/{table_type}/export",
    summary="Export a table including its metadata.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def export_table(
    request: Request,
    bg_tasks: BackgroundTasks,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: Annotated[str, Query(description="Table name.")],
) -> FileResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_db_storage_quota()
    billing.has_egress_quota()
    table = await TABLE_CLS[table_type].open_table(project_id=project.id, table_id=table_id)
    # Temporary file
    tmp_dir = TemporaryDirectory()
    filename = f"{table_id}.parquet"
    filepath = join(tmp_dir.name, filename)
    # Keep a reference to the directory and only delete upon completion
    bg_tasks.add_task(tmp_dir.cleanup)
    # Export
    await table.export_table(filepath)
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream",
    )
