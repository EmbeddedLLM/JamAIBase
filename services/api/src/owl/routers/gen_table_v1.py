from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, BeforeValidator, Field

from owl.routers import gen_table as v2
from owl.types import (
    TABLE_NAME_PATTERN,
    ActionTableSchemaCreate,
    ChatTableSchemaCreate,
    ChatThreadResponse,
    ColumnDropRequest,
    ColumnRenameRequest,
    ColumnReorderRequest,
    CSVDelimiter,
    GenConfigUpdateRequest,
    KnowledgeTableSchemaCreate,
    MultiRowAddRequestWithLimit,
    MultiRowDeleteRequest,
    MultiRowRegenRequest,
    MultiRowUpdateRequest,
    OkResponse,
    OrganizationRead,
    Page,
    ProjectRead,
    RowUpdateRequest,
    SanitisedNonEmptyStr,
    SearchRequest,
    TableMetaResponse,
    TableSchemaCreate,
    TableType,
    UserAuth,
    empty_string_to_none,
)
from owl.utils import uuid7_str
from owl.utils.auth import auth_user_project, has_permissions
from owl.utils.exceptions import handle_exception

router = APIRouter()


@router.post(
    "/v1/gen_tables/action",
    summary="Create an action table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def create_action_table(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: ActionTableSchemaCreate,
) -> TableMetaResponse:
    return await v2.create_action_table(request=request, auth_info=auth_info, body=body)


@router.post(
    "/v1/gen_tables/knowledge",
    summary="Create a knowledge table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
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
    has_permissions(
        user,
        ["organization.MEMBER", "project.MEMBER"],
        organization_id=org.id,
        project_id=project.id,
    )
    return await v2.create_knowledge_table(request=request, auth_info=auth_info, body=body)


@router.post(
    "/v1/gen_tables/chat",
    summary="Create a chat table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def create_chat_table(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: ChatTableSchemaCreate,
) -> TableMetaResponse:
    return await v2.create_chat_table(request=request, auth_info=auth_info, body=body)


@router.post(
    "/v1/gen_tables/{table_type}/duplicate/{table_id_src}",
    summary="Duplicate a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def duplicate_table(
    *,
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: TableType,
    table_id_src: str = Path(description="Name of the table to be duplicated."),
    table_id_dst: str | None = Query(
        None,
        pattern=TABLE_NAME_PATTERN,
        max_length=100,
        description=(
            "_Optional_. Name for the new table."
            "Defaults to None (automatically find the next available table name)."
        ),
    ),
    include_data: bool = Query(
        True,
        description="_Optional_. Whether to include data from the source table. Defaults to `True`.",
    ),
    create_as_child: bool = Query(
        False,
        description=(
            "_Optional_. Whether the new table is a child table. Defaults to `False`. "
            "If this is `True`, then `include_data` will be set to `True`."
        ),
    ),
) -> TableMetaResponse:
    return await v2.duplicate_table(
        request=request,
        auth_info=auth_info,
        table_type=table_type,
        params=v2.DuplicateTableQuery(
            table_id_src=table_id_src,
            table_id_dst=table_id_dst,
            include_data=include_data,
            create_as_child=create_as_child,
        ),
    )


@router.post(
    "/v1/gen_tables/{table_type}/duplicate/{table_id_src}/{table_id_dst}",
    deprecated=True,
    summary="Duplicate a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def duplicate_table_deprecated(
    *,
    request: Request,
    response: Response,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: TableType,
    table_id_src: str = Path(description="Source table name or ID."),
    table_id_dst: str = Path(
        pattern=TABLE_NAME_PATTERN,
        max_length=100,
        description="Destination table name or ID.",
    ),
    include_data: bool = Query(
        True,
        description="_Optional_. Whether to include the data from the source table in the duplicated table. Defaults to `True`.",
    ),
    deploy: bool = Query(
        False,
        description="_Optional_. Whether to deploy the duplicated table. Defaults to `False`.",
    ),
) -> TableMetaResponse:
    response.headers["Warning"] = (
        '299 - "This endpoint is deprecated and will be removed in v0.5. '
        "Use '/v1/gen_tables/{table_type}/duplicate/{table_id_src}' instead."
        '"'
    )
    return await v2.duplicate_table(
        request=request,
        auth_info=auth_info,
        table_type=table_type,
        params=v2.DuplicateTableQuery(
            table_id_src=table_id_src,
            table_id_dst=table_id_dst,
            include_data=include_data,
            create_as_child=deploy,
        ),
    )


@router.get(
    "/v1/gen_tables/{table_type}/{table_id}",
    summary="Get a specific table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def get_table(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(description="The ID of the table to fetch."),
) -> TableMetaResponse:
    return await v2.get_table(auth_info=auth_info, table_type=table_type, table_id=table_id)


class _ListTableQueryLegacy(BaseModel):
    offset: Annotated[
        int,
        Field(ge=0, description="Item offset for pagination. Defaults to 0."),
    ] = 0
    limit: Annotated[
        int,
        Field(
            gt=0,
            le=100,
            description="Number of tables to return (min 1, max 100). Defaults to 100.",
        ),
    ] = 100
    parent_id: Annotated[
        str | None,
        Field(
            min_length=1,
            description=(
                "Parent ID of tables to return. Defaults to None (return all tables). "
                "Additionally for Chat Table, you can list: "
                '(1) all chat agents by passing in "_agent_"; or '
                '(2) all chats by passing in "_chat_".'
            ),
        ),
    ] = None
    search_query: Annotated[
        str,
        Field(
            max_length=255,
            description='A string to search for within table IDs as a filter. Defaults to "" (no filter).',
        ),
    ] = ""
    order_by: Annotated[
        Literal["id", "updated_at"],
        Field(description='Sort tables by this attribute. Defaults to "updated_at".'),
    ] = "updated_at"
    order_descending: Annotated[
        bool,
        Field(
            description="Whether to sort by descending order. Defaults to True.",
        ),
    ] = True
    count_rows: Annotated[
        bool,
        Field(description="Whether to count the rows of the tables. Defaults to False."),
    ] = False


@router.get(
    "/v1/gen_tables/{table_type}",
    summary="List tables of a specific type.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def list_tables(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[_ListTableQueryLegacy, Query()],
) -> Page[TableMetaResponse]:
    kwargs = params.model_dump()
    order_ascending = not kwargs.pop("order_descending", True)
    return await v2.list_tables(
        auth_info=auth_info,
        table_type=table_type,
        params=v2.ListTableQuery(order_ascending=order_ascending, **kwargs),
    )


@router.post(
    "/v1/gen_tables/{table_type}/rename/{table_id_src}/{table_id_dst}",
    summary="Rename a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def rename_table(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id_src: Annotated[str, Path(description="Source table name.")],  # Don't validate
    table_id_dst: Annotated[
        str,
        Path(pattern=TABLE_NAME_PATTERN, max_length=100, description="New name for the table."),
    ],
) -> TableMetaResponse:
    return await v2.rename_table(
        auth_info=auth_info,
        table_type=table_type,
        params=v2.RenameTableQuery(table_id_src=table_id_src, table_id_dst=table_id_dst),
    )


@router.delete(
    "/v1/gen_tables/{table_type}/{table_id}",
    summary="Delete a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def delete_table(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: Annotated[str, Path(description="Name of the table to be deleted.")],
) -> OkResponse:
    return await v2.delete_table(auth_info=auth_info, table_type=table_type, table_id=table_id)


@router.post(
    "/v1/gen_tables/{table_type}/columns/add",
    summary="Add columns to a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
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
    return await v2.add_columns(
        request=request, auth_info=auth_info, table_type=table_type, body=body
    )


@router.post(
    "/v1/gen_tables/{table_type}/columns/rename",
    summary="Rename columns in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def rename_columns(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: ColumnRenameRequest,
) -> TableMetaResponse:
    return await v2.rename_columns(auth_info=auth_info, table_type=table_type, body=body)


@router.post(
    "/v1/gen_tables/{table_type}/gen_config/update",
    summary="Update generation configuration for table columns.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def update_gen_config(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    updates: GenConfigUpdateRequest,
) -> TableMetaResponse:
    return await v2.update_gen_config(auth_info=auth_info, table_type=table_type, updates=updates)


@router.post(
    "/v1/gen_tables/{table_type}/columns/reorder",
    summary="Reorder columns in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def reorder_columns(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: ColumnReorderRequest,
) -> TableMetaResponse:
    return await v2.reorder_columns(auth_info=auth_info, table_type=table_type, body=body)


@router.post(
    "/v1/gen_tables/{table_type}/columns/drop",
    summary="Drop columns from a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
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
    return await v2.drop_columns(
        request=request, auth_info=auth_info, table_type=table_type, body=body
    )


@router.post(
    "/v1/gen_tables/{table_type}/rows/add",
    summary="Add rows to a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
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
    return await v2.add_rows(
        request=request, auth_info=auth_info, table_type=table_type, body=body
    )


class _ListTableRowQueryLegacy(BaseModel):
    offset: Annotated[
        int,
        Field(ge=0, description="Item offset for pagination. Defaults to 0."),
    ] = 0
    limit: Annotated[
        int,
        Field(
            gt=0,
            le=100,
            description="Number of rows to return (min 1, max 100). Defaults to 100.",
        ),
    ] = 100
    order_descending: Annotated[
        bool,
        Field(
            description="Whether to sort by descending order. Defaults to True.",
        ),
    ] = True
    columns: Annotated[
        list[str] | None,
        Field(
            description="A list of column names to include in the response. Default is to return all columns.",
        ),
    ] = None
    search_query: Annotated[
        str,
        Field(
            max_length=10_000,
            description=(
                "A string to search for within row data as a filter. "
                'The string is interpreted as both POSIX regular expression and literal string. Defaults to "" (no filter). '
                "It will be combined other filters using `AND`."
            ),
        ),
    ] = ""
    float_decimals: Annotated[
        int,
        Field(
            ge=0,
            description="Number of decimals for float values. Defaults to 0 (no rounding).",
        ),
    ] = 0
    vec_decimals: Annotated[
        int,
        Field(
            description="Number of decimals for vectors. If its negative, exclude vector columns. Defaults to 0 (no rounding).",
        ),
    ] = 0


@router.get(
    "/v1/gen_tables/{table_type}/{table_id}/rows",
    summary="List rows in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def list_rows(
    *,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(description="Table ID or name."),
    params: Annotated[_ListTableRowQueryLegacy, Query()],
) -> Page[dict[str, Any]]:
    kwargs = params.model_dump()
    order_ascending = not kwargs.pop("order_descending", True)
    response = await v2.list_rows(
        auth_info=auth_info,
        table_type=table_type,
        params=v2.ListTableRowQuery(table_id=table_id, order_ascending=order_ascending, **kwargs),
    )
    # Reproduce V1 "value" bug for backwards compatibility
    if params.columns:
        for col in params.columns:
            for row in response.items:
                if col in row and isinstance(row[col], dict):
                    row[col] = row[col].get("value", row[col])
    return response


@router.get(
    "/v1/gen_tables/{table_type}/{table_id}/rows/{row_id}",
    summary="Get a specific row from a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def get_row(
    *,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(description="Table ID or name."),
    row_id: Annotated[str, Path(description="The ID of the specific row to fetch.")],
    columns: list[str] | None = Query(
        default=None,
        description="_Optional_. A list of column names to include in the response. Default is to return all columns.",
    ),
    float_decimals: int = Query(
        default=0,
        ge=0,
        description="_Optional_. Number of decimals for float values. Defaults to 0 (no rounding).",
    ),
    vec_decimals: int = Query(
        default=0,
        description="_Optional_. Number of decimals for vectors. If its negative, exclude vector columns. Defaults to 0 (no rounding).",
    ),
) -> dict[str, Any]:
    return await v2.get_row(
        auth_info=auth_info,
        table_type=table_type,
        params=v2.GetTableRowQuery(
            table_id=table_id,
            row_id=row_id,
            columns=columns,
            float_decimals=float_decimals,
            vec_decimals=vec_decimals,
        ),
    )


@router.get(
    "/v1/gen_tables/{table_type}/{table_id}/thread",
    summary="Get a conversation thread from a multi-turn LLM column.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def get_conversation_thread(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: Annotated[str, Path(description="Table ID or name.")],
    column_id: Annotated[str, Query(description="ID / name of the column to fetch.")],
    row_id: Annotated[
        str,
        Query(
            description='_Optional_. ID / name of the last row in the thread. Defaults to "" (export all rows).'
        ),
    ] = "",
    include: Annotated[
        bool,
        Query(
            description="_Optional_. Whether to include the row specified by `row_id`. Defaults to True."
        ),
    ] = True,
) -> ChatThreadResponse:
    response = await v2.get_conversation_threads(
        auth_info=auth_info,
        table_type=table_type,
        params=v2.GetTableThreadsQuery(
            table_id=table_id, column_ids=[column_id], row_id=row_id, include_row=include
        ),
    )
    return response.threads[column_id]


@router.post(
    "/v1/gen_tables/{table_type}/hybrid_search",
    summary="Perform hybrid search on a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
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
    return await v2.hybrid_search(
        request=request, auth_info=auth_info, table_type=table_type, body=body
    )


@router.post(
    "/v1/gen_tables/{table_type}/rows/regen",
    summary="Regenerate rows in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
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
    return await v2.regen_rows(
        request=request, auth_info=auth_info, table_type=table_type, body=body
    )


@router.post(
    "/v1/gen_tables/{table_type}/rows/update",
    summary="Update a row in a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def update_row(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: RowUpdateRequest,
) -> OkResponse:
    return await v2.update_rows(
        request=request,
        auth_info=auth_info,
        table_type=table_type,
        body=MultiRowUpdateRequest(table_id=body.table_id, data={body.row_id: body.data}),
    )


@router.post(
    "/v1/gen_tables/{table_type}/rows/delete",
    summary="Delete rows from a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def delete_rows(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: MultiRowDeleteRequest,
) -> OkResponse:
    return await v2.delete_rows(auth_info=auth_info, table_type=table_type, body=body)


@router.delete(
    "/v1/gen_tables/{table_type}/{table_id}/rows/{row_id}",
    summary="Delete a row from a table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def delete_row(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(description="Table ID or name."),
    row_id: str = Path(description="The ID of the specific row to delete."),
) -> OkResponse:
    return await v2.delete_rows(
        auth_info=auth_info,
        table_type=table_type,
        body=MultiRowDeleteRequest(table_id=table_id, row_ids=[row_id]),
    )


@router.options(
    "/v1/gen_tables/knowledge/embed_file",
    summary="Get CORS preflight options for file embedding endpoint",
    description="Permissions: None, publicly accessible.",
)
@router.options(
    "/v1/gen_tables/knowledge/upload_file",
    deprecated=True,
    summary="Get CORS preflight options for file embedding endpoint",
    description="Permissions: None, publicly accessible.",
)
@handle_exception
async def embed_file_options(request: Request, response: Response):
    if "upload_file" in request.url.path:
        response.headers["Warning"] = (
            '299 - "This endpoint is deprecated and will be removed in v0.5. '
            "Use '/v1/gen_tables/{table_type}/embed_file' instead."
            '"'
        )
    return await v2.embed_file_options()


class FileEmbedFormData(BaseModel):
    file: Annotated[UploadFile, File(description="The file.")]
    file_name: Annotated[str, Field(description="File name.", deprecated=True)] = ""
    table_id: Annotated[SanitisedNonEmptyStr, Field(description="Knowledge Table ID.")]
    # overwrite: Annotated[
    #     bool, Field(description="Whether to overwrite old file with the same name.")
    # ] = False,
    chunk_size: Annotated[
        int, Field(gt=0, description="Maximum chunk size (number of characters). Must be > 0.")
    ] = 2000
    chunk_overlap: Annotated[
        int, Field(ge=0, description="Overlap in characters between chunks. Must be >= 0.")
    ] = 200


@router.post(
    "/v1/gen_tables/knowledge/embed_file",
    summary="Embed a file into a knowledge table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@router.post(
    "/v1/gen_tables/knowledge/upload_file",
    deprecated=True,
    summary="Embed a file into a knowledge table.",
    description="Permissions: `organization.MEMBER` OR `project.MEMBER`.",
)
@handle_exception
async def embed_file(
    *,
    request: Request,
    response: Response,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    data: Annotated[FileEmbedFormData, Form()],
) -> OkResponse:
    if "upload_file" in request.url.path:
        response.headers["Warning"] = (
            '299 - "This endpoint is deprecated and will be removed in v0.5. '
            "Use '/v1/gen_tables/{table_type}/embed_file' instead."
            '"'
        )
    return await v2.embed_file(
        request=request,
        auth_info=auth_info,
        data=data,
    )


class TableDataImportFormData(BaseModel):
    file: Annotated[UploadFile, File(description="The CSV or TSV file.")]
    file_name: Annotated[str, Field(description="File name.", deprecated=True)] = ""
    table_id: Annotated[
        SanitisedNonEmptyStr,
        Field(description="ID or name of the table that the data should be imported into."),
    ]
    stream: Annotated[bool, Field(description="Whether or not to stream the LLM generation.")] = (
        True
    )
    # List of inputs is bugged as of 2024-07-14: https://github.com/tiangolo/fastapi/pull/9928/files
    # TODO: Maybe we can re-enable these since the bug is for direct `Form` declaration and not Form Model
    # column_names: Annotated[
    #     list[ColName] | None,
    #     Field(
    #         description="_Optional_. A list of columns names if the CSV does not have header row. Defaults to None (read from CSV).",
    #     ),
    # ] = None
    # columns: Annotated[
    #     list[ColName] | None,
    #     Field(
    #         description="_Optional_. A list of columns to be imported. Defaults to None (import all columns except 'ID' and 'Updated at').",
    #     ),
    # ] = None
    delimiter: Annotated[
        CSVDelimiter,
        Field(description='The delimiter, can be "," or "\\t". Defaults to ",".'),
    ] = CSVDelimiter.COMMA


@router.post(
    "/v1/gen_tables/{table_type}/import_data",
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
    return await v2.import_table_data(
        request=request, auth_info=auth_info, table_type=table_type, data=data
    )


@router.get(
    "/v1/gen_tables/{table_type}/{table_id}/export_data",
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
    table_id: Annotated[str, Path(description="ID or name of the table to be exported.")],
    delimiter: Annotated[
        CSVDelimiter,
        Query(description='The delimiter, can be "," or "\\t". Defaults to ",".'),
    ] = CSVDelimiter.COMMA,
    columns: Annotated[
        list[str] | None,
        Query(
            min_length=1,
            description="_Optional_. A list of columns to be exported. Defaults to None (export all columns).",
        ),
    ] = None,
) -> FileResponse:
    return await v2.export_table_data(
        request=request,
        bg_tasks=bg_tasks,
        auth_info=auth_info,
        table_type=table_type,
        params=v2.ExportTableDataQuery(table_id=table_id, delimiter=delimiter, columns=columns),
    )


class TableImportFormData(BaseModel):
    file: Annotated[UploadFile, File(description="The Parquet file.")]
    table_id_dst: Annotated[
        SanitisedNonEmptyStr | None,
        BeforeValidator(empty_string_to_none),
        Field(description="The ID or name of the new table."),
    ] = None
    blocking: Annotated[
        bool,
        Field(
            description=(
                "If True, waits until import finishes. "
                "If False, the task is submitted to a task queue and returns immediately."
            ),
        ),
    ] = True
    progress_key: Annotated[
        str,
        Field(
            default_factory=uuid7_str,
            description="The key to use to query progress. Defaults to a random string.",
        ),
    ]
    migrate: Annotated[bool, Field(description="Whether to import in migration mode.")] = False
    reupload: Annotated[
        bool,
        Field(description="Whether to reupload in migration mode (maybe removed without notice)."),
    ] = False


@router.post(
    "/v1/gen_tables/{table_type}/import",
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
) -> TableMetaResponse:
    return await v2.import_table(
        request=request,
        auth_info=auth_info,
        table_type=table_type,
        data=data,
    )


@router.get(
    "/v1/gen_tables/{table_type}/{table_id}/export",
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
    table_id: Annotated[str, Path(description="ID or name of the table to be exported.")],
) -> FileResponse:
    return await v2.export_table(
        request=request,
        bg_tasks=bg_tasks,
        auth_info=auth_info,
        table_type=table_type,
        table_id=table_id,
    )
