import re
from io import BytesIO
from os import listdir, makedirs
from os.path import isdir, join, splitext
from shutil import copy2, copytree
from tempfile import TemporaryDirectory
from typing import Annotated, Any

import numpy as np
import pandas as pd
import tiktoken
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
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger

from jamaibase.exceptions import (
    ResourceNotFoundError,
    TableSchemaFixedError,
    UnsupportedMediaTypeError,
    make_validation_error,
)
from jamaibase.utils.io import csv_to_df, json_loads
from owl.configs.manager import ENV_CONFIG
from owl.db.gen_executor import MultiRowsGenExecutor
from owl.db.gen_table import GenerativeTable
from owl.llm import LLMEngine
from owl.loaders import load_file
from owl.models import CloudEmbedder, CloudReranker
from owl.protocol import (
    GEN_CONFIG_VAR_PATTERN,
    TABLE_NAME_PATTERN,
    ActionTableSchemaCreate,
    AddActionColumnSchema,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    ChatEntry,
    ChatTableSchemaCreate,
    ChatThread,
    CodeGenConfig,
    ColName,
    ColumnDropRequest,
    ColumnDtype,
    ColumnRenameRequest,
    ColumnReorderRequest,
    CSVDelimiter,
    EmbedGenConfig,
    GenConfig,
    GenConfigUpdateRequest,
    GenTableOrderBy,
    KnowledgeTableSchemaCreate,
    LLMGenConfig,
    OkResponse,
    Page,
    RowAddRequest,
    RowAddRequestWithLimit,
    RowDeleteRequest,
    RowRegenRequest,
    RowUpdateRequest,
    SearchRequest,
    TableMetaResponse,
    TableSchema,
    TableSchemaCreate,
    TableType,
)
from owl.utils import uuid7_str
from owl.utils.auth import ProjectRead, auth_user_project
from owl.utils.exceptions import handle_exception
from owl.utils.io import EMBED_WHITE_LIST_MIME, upload_file_to_s3

router = APIRouter()


def _validate_gen_config(
    llm: LLMEngine,
    gen_config: GenConfig | None,
    table_type: TableType,
    column_id: str,
    image_column_ids: list[str],
    audio_column_ids: list[str],
) -> GenConfig | None:
    if gen_config is None:
        return gen_config
    if isinstance(gen_config, LLMGenConfig):
        # Set multi-turn for Chat Table
        if table_type == TableType.CHAT and column_id.lower() == "ai":
            gen_config.multi_turn = True
        # Assign a LLM model if not specified
        try:
            capabilities = ["chat"]
            for message in (gen_config.system_prompt, gen_config.prompt):
                for col_id in re.findall(GEN_CONFIG_VAR_PATTERN, message):
                    if col_id in image_column_ids:
                        capabilities = ["image"]
                    if col_id in audio_column_ids:
                        capabilities = ["audio"]
                        break
            gen_config.model = llm.validate_model_id(
                model=gen_config.model,
                capabilities=capabilities,
            )
        except ValueError as e:
            raise ResourceNotFoundError("There is no chat model available.") from e
        except ResourceNotFoundError as e:
            raise ResourceNotFoundError(
                f'Column {column_id} used a chat model "{gen_config.model}" that is not available.'
            ) from e
        # Check Knowledge Table existence
        if gen_config.rag_params is None:
            return gen_config
        ref_table_id = gen_config.rag_params.table_id
        kt_table_dir = join(
            ENV_CONFIG.owl_db_dir,
            llm.organization_id,
            llm.project_id,
            TableType.KNOWLEDGE,
            f"{ref_table_id}.lance",
        )
        if not (isdir(kt_table_dir) and len(listdir(kt_table_dir)) > 0):
            raise ResourceNotFoundError(
                f"Column {column_id} referred to a Knowledge Table '{ref_table_id}' that does not exist."
            )
        # Validate Reranking Model
        reranking_model = gen_config.rag_params.reranking_model
        if reranking_model is None:
            return gen_config
        try:
            gen_config.rag_params.reranking_model = llm.validate_model_id(
                model=reranking_model,
                capabilities=["rerank"],
            )
        except ValueError as e:
            raise ResourceNotFoundError("There is no reranking model available.") from e
        except ResourceNotFoundError as e:
            raise ResourceNotFoundError(
                f'Column {column_id} used a reranking model "{reranking_model}" that is not available.'
            ) from e
    elif isinstance(gen_config, CodeGenConfig):
        pass
    elif isinstance(gen_config, EmbedGenConfig):
        pass
    return gen_config


def _create_table(
    request: Request,
    organization_id: str,
    project_id: str,
    table_type: TableType,
    schema: TableSchemaCreate,
) -> TableMetaResponse:
    # Validate
    llm = LLMEngine(request=request)
    image_column_ids = [
        col.id
        for col in schema.cols
        if col.dtype == ColumnDtype.IMAGE and not col.id.endswith("_")
    ]
    audio_column_ids = [
        col.id
        for col in schema.cols
        if col.dtype == ColumnDtype.AUDIO and not col.id.endswith("_")
    ]
    for col in schema.cols:
        col.gen_config = _validate_gen_config(
            llm=llm,
            gen_config=col.gen_config,
            table_type=table_type,
            column_id=col.id,
            image_column_ids=image_column_ids,
            audio_column_ids=audio_column_ids,
        )
    if table_type == TableType.KNOWLEDGE:
        try:
            embedding_model = schema.embedding_model
            schema.embedding_model = llm.validate_model_id(
                model=embedding_model,
                capabilities=["embed"],
            )
        except ValueError as e:
            raise ResourceNotFoundError("There is no embedding model available.") from e
        except ResourceNotFoundError as e:
            raise ResourceNotFoundError(
                f'Column used a embedding model "{embedding_model}" that is not available.'
            ) from e
    table = GenerativeTable.from_ids(organization_id, project_id, table_type)
    # Create
    with table.create_session() as session:
        _, meta = (
            table.create_table(session, schema, request.state.all_models)
            if table_type == TableType.KNOWLEDGE
            else table.create_table(session, schema)
        )
    meta = TableMetaResponse(**meta.model_dump(), num_rows=0)
    return meta


@router.post("/v1/gen_tables/action")
@handle_exception
def create_action_table(
    request: Request,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    body: ActionTableSchemaCreate,
) -> TableMetaResponse:
    return _create_table(request, project.organization.id, project.id, TableType.ACTION, body)


@router.post("/v1/gen_tables/knowledge")
@handle_exception
def create_knowledge_table(
    request: Request,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    body: KnowledgeTableSchemaCreate,
) -> TableMetaResponse:
    return _create_table(request, project.organization.id, project.id, TableType.KNOWLEDGE, body)


@router.post("/v1/gen_tables/chat")
@handle_exception
def create_chat_table(
    request: Request,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    body: ChatTableSchemaCreate,
) -> TableMetaResponse:
    return _create_table(request, project.organization.id, project.id, TableType.CHAT, body)


def _duplicate_table(
    organization_id: str,
    project_id: str,
    table_type: TableType,
    table_id_src: str,
    table_id_dst: str,
    include_data: bool,
    create_as_child: bool,
) -> TableMetaResponse:
    # Duplicate
    table = GenerativeTable.from_ids(organization_id, project_id, table_type)
    with table.create_session() as session:
        meta = table.duplicate_table(
            session,
            table_id_src,
            table_id_dst,
            include_data,
            create_as_child=create_as_child,
        )
    meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(meta.id))
    return meta


@router.post("/v1/gen_tables/{table_type}/duplicate/{table_id_src}")
@handle_exception
def duplicate_table(
    *,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: TableType,
    table_id_src: str = Path(pattern=TABLE_NAME_PATTERN, description="Source table name or ID."),
    table_id_dst: str | None = Query(
        default=None, pattern=TABLE_NAME_PATTERN, description="Destination table name or ID."
    ),
    include_data: bool = Query(
        default=True,
        description="_Optional_. Whether to include the data from the source table in the duplicated table. Defaults to `True`.",
    ),
    create_as_child: bool = Query(
        default=False,
        description=(
            "_Optional_. Whether the new table is a child table. Defaults to `False`. "
            "If this is True, then `include_data` will be set to True."
        ),
    ),
) -> TableMetaResponse:
    if create_as_child:
        include_data = True
    if not table_id_dst:
        table_id_dst = f"{table_id_src}_{uuid7_str()}"
    return _duplicate_table(
        organization_id=project.organization.id,
        project_id=project.id,
        table_type=table_type,
        table_id_src=table_id_src,
        table_id_dst=table_id_dst,
        include_data=include_data,
        create_as_child=create_as_child,
    )


@router.post("/v1/gen_tables/{table_type}/duplicate/{table_id_src}/{table_id_dst}")
@handle_exception
def duplicate_table_deprecated(
    *,
    response: Response,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: TableType,
    table_id_src: str = Path(pattern=TABLE_NAME_PATTERN, description="Source table name or ID."),
    table_id_dst: str = Path(
        pattern=TABLE_NAME_PATTERN, description="Destination table name or ID."
    ),
    include_data: bool = Query(
        default=True,
        description="_Optional_. Whether to include the data from the source table in the duplicated table. Defaults to `True`.",
    ),
    deploy: bool = Query(
        default=False,
        description="_Optional_. Whether to deploy the duplicated table. Defaults to `False`.",
    ),
) -> TableMetaResponse:
    response.headers["Warning"] = (
        '299 - "This endpoint is deprecated and will be removed in v0.4. '
        "Use '/v1/gen_tables/{table_type}/duplicate/{table_id_src}' instead."
        '"'
    )
    return _duplicate_table(
        organization_id=project.organization.id,
        project_id=project.id,
        table_type=table_type,
        table_id_src=table_id_src,
        table_id_dst=table_id_dst,
        include_data=include_data,
        create_as_child=deploy,
    )


@router.post("/v1/gen_tables/{table_type}/rename/{table_id_src}/{table_id_dst}")
@handle_exception
def rename_table(
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id_src: Annotated[str, Path(description="Source table name or ID.")],  # Don't validate
    table_id_dst: Annotated[
        str,
        Path(
            pattern=TABLE_NAME_PATTERN,
            description="Destination table name or ID.",
        ),
    ],
) -> TableMetaResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        meta = table.rename_table(session, table_id_src, table_id_dst)
    meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(table_id_dst))
    return meta


@router.delete("/v1/gen_tables/{table_type}/{table_id}")
@handle_exception
def delete_table(
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: Annotated[str, Path(description="The ID of the table to delete.")],  # Don't validate
) -> OkResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        table.delete_table(session, table_id)
        return OkResponse()


@router.get("/v1/gen_tables/{table_type}")
@handle_exception
def list_tables(
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="_Optional_. Item offset for pagination. Defaults to 0.",
        ),
    ] = 0,
    limit: Annotated[
        int,
        Query(
            gt=0,
            le=100,
            description="_Optional_. Number of tables to return (min 1, max 100). Defaults to 100.",
        ),
    ] = 100,
    parent_id: Annotated[
        str | None,
        Query(
            description=(
                "_Optional_. Parent ID of tables to return. Defaults to None (return all tables). "
                "Additionally for Chat Table, you can list: "
                '(1) all chat agents by passing in "_agent_"; or '
                '(2) all chats by passing in "_chat_".'
            ),
        ),
    ] = None,
    search_query: Annotated[
        str,
        Query(
            max_length=100,
            description='_Optional_. A string to search for within table IDs as a filter. Defaults to "" (no filter).',
        ),
    ] = "",
    order_by: Annotated[
        GenTableOrderBy,
        Query(
            min_length=1,
            description='_Optional_. Sort tables by this attribute. Defaults to "updated_at".',
        ),
    ] = GenTableOrderBy.UPDATED_AT,
    order_descending: Annotated[
        bool,
        Query(description="_Optional_. Whether to sort by descending order. Defaults to True."),
    ] = True,
    count_rows: Annotated[
        bool,
        Query(
            description="_Optional_. Whether to count the rows of the tables. Defaults to False."
        ),
    ] = False,
) -> Page[TableMetaResponse]:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        metas, total = table.list_meta(
            session,
            offset=offset,
            limit=limit,
            remove_state_cols=True,
            parent_id=parent_id,
            search_query=search_query,
            order_by=order_by,
            order_descending=order_descending,
            count_rows=count_rows,
        )
        return Page[TableMetaResponse](
            items=metas,
            offset=offset,
            limit=limit,
            total=total,
        )


@router.get("/v1/gen_tables/{table_type}/{table_id}")
@handle_exception
def get_table(
    request: Request,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(pattern=TABLE_NAME_PATTERN, description="The ID of the table to fetch."),
) -> TableMetaResponse:
    organization_id = project.organization.id
    project_id = project.id
    try:
        table = GenerativeTable.from_ids(organization_id, project_id, table_type)
        with table.create_session() as session:
            meta = table.open_meta(session, table_id, remove_state_cols=True)
        meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(meta.id))
        return meta
    except ResourceNotFoundError:
        lance_path = join(
            ENV_CONFIG.owl_db_dir,
            organization_id,
            project_id,
            table_type,
            f"{table_id}.lance",
        )
        if isdir(lance_path):
            logger.exception(
                f"{request.state.id} - Table cannot be opened but the directory exists !!!"
            )
            dst_dir = join(
                ENV_CONFIG.owl_db_dir,
                "problematic",
                organization_id,
                project_id,
                table_type,
            )
            makedirs(dst_dir, exist_ok=True)
            _uuid = uuid7_str()
            copytree(lance_path, join(dst_dir, f"{table_id}_{_uuid}.lance"))
            copy2(
                join(
                    ENV_CONFIG.owl_db_dir,
                    organization_id,
                    project_id,
                    f"{table_type}.db",
                ),
                join(
                    ENV_CONFIG.owl_db_dir,
                    "problematic",
                    organization_id,
                    project_id,
                    f"{table_type}_{_uuid}.db",
                ),
            )
        raise


@router.post("/v1/gen_tables/{table_type}/gen_config/update")
@handle_exception
def update_gen_config(
    request: Request,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    updates: GenConfigUpdateRequest,
) -> TableMetaResponse:
    # Validate
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        meta = table.open_meta(session, updates.table_id)
        llm = LLMEngine(request=request)
        image_column_ids = [
            col["id"]
            for col in meta.cols
            if col["dtype"] == ColumnDtype.IMAGE and not col["id"].endswith("_")
        ]
        audio_column_ids = [
            col["id"]
            for col in meta.cols
            if col["dtype"] == ColumnDtype.AUDIO and not col["id"].endswith("_")
        ]

        if table_type == TableType.KNOWLEDGE:
            # Knowledge Table "Title Embed" and "Text Embed" columns must always have gen config
            for c in ["Title Embed", "Text Embed"]:
                if c in updates.column_map and updates.column_map[c] is None:
                    updates.column_map.pop(c)
        elif table_type == TableType.CHAT:
            # Chat Table AI column must always have gen config
            if "AI" in updates.column_map and updates.column_map["AI"] is None:
                updates.column_map.pop("AI")

        updates.column_map = {
            col_id: _validate_gen_config(
                llm=llm,
                gen_config=gen_config,
                table_type=table_type,
                column_id=col_id,
                image_column_ids=image_column_ids,
                audio_column_ids=audio_column_ids,
            )
            for col_id, gen_config in updates.column_map.items()
        }
        # Update
        meta = table.update_gen_config(session, updates)
    meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(meta.id))
    return meta


def _add_columns(
    request: Request,
    organization_id: str,
    project_id: str,
    table_type: TableType,
    schema: TableSchemaCreate,
) -> TableMetaResponse:
    # Validate
    table = GenerativeTable.from_ids(organization_id, project_id, table_type)
    with table.create_session() as session:
        meta = table.open_meta(session, schema.id)
        llm = LLMEngine(request=request)
        cols = TableSchema(
            id=meta.id, cols=[c.model_dump() for c in meta.cols_schema + schema.cols]
        ).cols
        image_column_ids = [
            col.id for col in cols if col.dtype == ColumnDtype.IMAGE and not col.id.endswith("_")
        ]
        audio_column_ids = [
            col.id for col in cols if col.dtype == ColumnDtype.AUDIO and not col.id.endswith("_")
        ]
        schema.cols = [col for col in cols if col.id in set(c.id for c in schema.cols)]
        for col in schema.cols:
            col.gen_config = _validate_gen_config(
                llm=llm,
                gen_config=col.gen_config,
                table_type=table_type,
                column_id=col.id,
                image_column_ids=image_column_ids,
                audio_column_ids=audio_column_ids,
            )
        # Create
        _, meta = table.add_columns(session, schema)
    meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(meta.id))
    return meta


@router.post("/v1/gen_tables/action/columns/add")
@handle_exception
def add_action_columns(
    request: Request,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    body: AddActionColumnSchema,
) -> TableMetaResponse:
    return _add_columns(request, project.organization.id, project.id, TableType.ACTION, body)


@router.post("/v1/gen_tables/knowledge/columns/add")
@handle_exception
def add_knowledge_columns(
    request: Request,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    body: AddKnowledgeColumnSchema,
) -> TableMetaResponse:
    return _add_columns(request, project.organization.id, project.id, TableType.KNOWLEDGE, body)


@router.post("/v1/gen_tables/chat/columns/add")
@handle_exception
def add_chat_columns(
    request: Request,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    body: AddChatColumnSchema,
) -> TableMetaResponse:
    return _add_columns(request, project.organization.id, project.id, TableType.CHAT, body)


def _create_indexes(
    project: ProjectRead,
    table_type: TableType,
    table_id: str,
) -> TableMetaResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        table.create_indexes(session, table_id)


@router.post("/v1/gen_tables/{table_type}/columns/drop")
@handle_exception
def drop_columns(
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: ColumnDropRequest,
) -> TableMetaResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        _, meta = table.drop_columns(session, body.table_id, body.column_names)
    meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(meta.id))
    bg_tasks.add_task(_create_indexes, project, table_type, body.table_id)
    return meta


@router.post("/v1/gen_tables/{table_type}/columns/rename")
@handle_exception
def rename_columns(
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: ColumnRenameRequest,
) -> TableMetaResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        meta = table.rename_columns(session, body.table_id, body.column_map)
    meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(meta.id))
    return meta


@router.post("/v1/gen_tables/{table_type}/columns/reorder")
@handle_exception
def reorder_columns(
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: ColumnReorderRequest,
) -> TableMetaResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        meta = table.reorder_columns(session, body.table_id, body.column_names)
    meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(meta.id))
    return meta


@router.get("/v1/gen_tables/{table_type}/{table_id}/rows")
@handle_exception
def list_rows(
    *,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(pattern=TABLE_NAME_PATTERN, description="Table ID or name."),
    offset: int = Query(
        default=0,
        ge=0,
        description="_Optional_. Item offset for pagination. Defaults to 0.",
    ),
    limit: int = Query(
        default=100,
        gt=0,
        le=100,
        description="_Optional_. Number of rows to return (min 1, max 100). Defaults to 100.",
    ),
    search_query: str = Query(
        default="",
        max_length=10_000,
        description='_Optional_. A string to search for within the rows as a filter. Defaults to "" (no filter).',
    ),
    columns: list[ColName] | None = Query(
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
    order_descending: Annotated[
        bool,
        Query(description="_Optional_. Whether to sort by descending order. Defaults to True."),
    ] = True,
) -> Page[dict[ColName, Any]]:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    if search_query == "":
        rows, total = table.list_rows(
            table_id=table_id,
            offset=offset,
            limit=limit,
            columns=columns,
            convert_null=True,
            remove_state_cols=True,
            json_safe=True,
            include_original=True,
            float_decimals=float_decimals,
            vec_decimals=vec_decimals,
            order_descending=order_descending,
        )
    else:
        with table.create_session() as session:
            rows = table.regex_search(
                session=session,
                table_id=table_id,
                query=search_query,
                columns=columns,
                convert_null=True,
                remove_state_cols=True,
                json_safe=True,
                include_original=True,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
                order_descending=order_descending,
            )
            total = len(rows)
            rows = rows[offset : offset + limit]
    return Page[dict[ColName, Any]](items=rows, offset=offset, limit=limit, total=total)


@router.get("/v1/gen_tables/{table_type}/{table_id}/rows/{row_id}")
@handle_exception
def get_row(
    *,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(pattern=TABLE_NAME_PATTERN, description="Table ID or name."),
    row_id: Annotated[str, Path(description="The ID of the specific row to fetch.")],
    columns: list[ColName] | None = Query(
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
) -> dict[ColName, Any]:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    row = table.get_row(
        table_id,
        row_id,
        columns=columns,
        convert_null=True,
        remove_state_cols=True,
        json_safe=True,
        include_original=True,
        float_decimals=float_decimals,
        vec_decimals=vec_decimals,
    )
    return row


@router.post("/v1/gen_tables/{table_type}/rows/add")
@handle_exception
async def add_rows(
    request: Request,
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: RowAddRequestWithLimit,
):
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    # Check quota
    request.state.billing.check_gen_table_llm_quota(table, body.table_id)
    # Checks
    with table.create_session() as session:
        meta = table.open_meta(session, body.table_id)
    has_chat_cols = (
        sum(
            col["gen_config"] is not None and col["gen_config"].get("multi_turn", False)
            for col in meta.cols
        )
        > 0
    )
    # Maybe re-index
    if body.reindex or (
        body.reindex is None
        and table.count_rows(body.table_id) <= ENV_CONFIG.owl_immediate_reindex_max_rows
    ):
        bg_tasks.add_task(_create_indexes, project, table_type, body.table_id)
    executor = MultiRowsGenExecutor(
        table=table,
        meta=meta,
        request=request,
        body=body,
        rows_batch_size=(1 if has_chat_cols else ENV_CONFIG.owl_concurrent_rows_batch_size),
        cols_batch_size=ENV_CONFIG.owl_concurrent_cols_batch_size,
        max_write_batch_size=(1 if has_chat_cols else ENV_CONFIG.owl_max_write_batch_size),
    )
    if body.stream:
        return StreamingResponse(
            content=await executor.gen_rows(),
            status_code=200,
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )
    else:
        return await executor.gen_rows()


@router.post("/v1/gen_tables/{table_type}/rows/regen")
@handle_exception
async def regen_rows(
    request: Request,
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: RowRegenRequest,
):
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    # Check quota
    request.state.billing.check_gen_table_llm_quota(table, body.table_id)
    # Checks
    with table.create_session() as session:
        meta = table.open_meta(session, body.table_id)
    if body.output_column_id is not None:
        output_column_ids = [col["id"] for col in meta.cols if col["gen_config"] is not None]
        if len(output_column_ids) > 0 and body.output_column_id not in output_column_ids:
            raise ResourceNotFoundError(
                (
                    f'`output_column_id` "{body.output_column_id}" is not found. '
                    f"Available output columns: {output_column_ids}"
                )
            )
    has_chat_cols = (
        sum(
            col["gen_config"] is not None and col["gen_config"].get("multi_turn", False)
            for col in meta.cols
        )
        > 0
    )
    # Maybe re-index
    if body.reindex or (
        body.reindex is None
        and table.count_rows(body.table_id) <= ENV_CONFIG.owl_immediate_reindex_max_rows
    ):
        bg_tasks.add_task(_create_indexes, project, table_type, body.table_id)
    executor = MultiRowsGenExecutor(
        table=table,
        meta=meta,
        request=request,
        body=body,
        rows_batch_size=(1 if has_chat_cols else ENV_CONFIG.owl_concurrent_rows_batch_size),
        cols_batch_size=ENV_CONFIG.owl_concurrent_cols_batch_size,
        max_write_batch_size=(1 if has_chat_cols else ENV_CONFIG.owl_max_write_batch_size),
    )
    if body.stream:
        return StreamingResponse(
            content=await executor.gen_rows(),
            status_code=200,
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )
    else:
        return await executor.gen_rows()


@router.post("/v1/gen_tables/{table_type}/rows/update")
@handle_exception
def update_row(
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: RowUpdateRequest,
) -> OkResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    # Check column type
    if table_type == TableType.KNOWLEDGE:
        col_names = set(n.lower() for n in body.data.keys())
        if "text embed" in col_names or "title embed" in col_names:
            raise TableSchemaFixedError("Cannot update 'Text Embed' or 'Title Embed'.")
    # Update
    with table.create_session() as session:
        table.update_rows(
            session,
            body.table_id,
            where=f"`ID` = '{body.row_id}'",
            values=body.data,
        )
    if body.reindex or (
        body.reindex is None
        and table.count_rows(body.table_id) <= ENV_CONFIG.owl_immediate_reindex_max_rows
    ):
        bg_tasks.add_task(_create_indexes, project, table_type, body.table_id)
    return OkResponse()


@router.post("/v1/gen_tables/{table_type}/rows/delete")
@handle_exception
def delete_rows(
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: RowDeleteRequest,
) -> OkResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        table.delete_rows(session, body.table_id, body.row_ids, body.where)
    if body.reindex or (
        body.reindex is None
        and table.count_rows(body.table_id) <= ENV_CONFIG.owl_immediate_reindex_max_rows
    ):
        bg_tasks.add_task(_create_indexes, project, table_type, body.table_id)
    return OkResponse()


@router.delete("/v1/gen_tables/{table_type}/{table_id}/rows/{row_id}")
@handle_exception
def delete_row(
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(pattern=TABLE_NAME_PATTERN, description="Table ID or name."),
    row_id: str = Path(description="The ID of the specific row to delete."),
    reindex: Annotated[bool, Query(description="Whether to reindex immediately.")] = True,
) -> OkResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        table.delete_row(session, table_id, row_id)
    if reindex:
        bg_tasks.add_task(_create_indexes, project, table_type, table_id)
    return OkResponse()


@router.get("/v1/gen_tables/{table_type}/{table_id}/thread")
@handle_exception
def get_conversation_thread(
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: Annotated[str, Path(pattern=TABLE_NAME_PATTERN, description="Table ID or name.")],
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
) -> ChatThread:
    # Fetch
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    return table.get_conversation_thread(
        table_id=table_id,
        column_id=column_id,
        row_id=row_id,
        include=include,
    )


@router.post("/v1/gen_tables/{table_type}/hybrid_search")
@handle_exception
async def hybrid_search(
    request: Request,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    body: SearchRequest,
) -> list[dict[ColName, Any]]:
    # Search
    embedder = CloudEmbedder(request=request)
    if body.reranking_model is not None:
        reranker = CloudReranker(request=request)
    else:
        reranker = None
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        rows = await table.hybrid_search(
            session,
            body.table_id,
            query=body.query,
            where=body.where,
            limit=body.limit,
            metric=body.metric,
            nprobes=body.nprobes,
            refine_factor=body.refine_factor,
            embedder=embedder,
            reranker=reranker,
            reranking_model=body.reranking_model,
            vec_decimals=body.vec_decimals,
            convert_null=True,
            remove_state_cols=True,
            json_safe=True,
            include_original=True,
        )
    return rows


def list_files():
    pass


def _truncate_text(text: str, max_context_length: int, encoding_name: str = "cl100k_base") -> str:
    """Truncates the text to fit within the max_context_length."""

    encoding = tiktoken.get_encoding(encoding_name)
    encoded_text = encoding.encode(text)

    if len(encoded_text) <= max_context_length:
        return text

    truncated_encoded = encoded_text[:max_context_length]
    truncated_text = encoding.decode(truncated_encoded)
    return truncated_text


async def _embed(
    embedder_name: str, embedder: CloudEmbedder, texts: list[str], embed_dtype: str
) -> np.ndarray:
    if len(texts) == 0:
        raise make_validation_error(
            ValueError("There is no text or content to embed."), loc=("body", "file")
        )
    embeddings = await embedder.embed_documents(embedder_name, texts=texts)
    embeddings = np.asarray([d.embedding for d in embeddings.data], dtype=embed_dtype)
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings


async def _embed_file(
    request: Request,
    bg_tasks: BackgroundTasks,
    project: ProjectRead,
    table_id: str,
    file_name: str,
    file_content: bytes,
    file_uri: str,
    chunk_size: int,
    chunk_overlap: int,
) -> OkResponse:
    request_id = request.state.id
    logger.info(f'{request_id} - Parsing file "{file_name}".')
    chunks = await load_file(file_name, file_content, chunk_size, chunk_overlap)
    logger.info(f'{request_id} - Embedding file "{file_name}" with {len(chunks):,d} chunks.')

    # --- Extract title --- #
    excerpt = "".join(d.text for d in chunks[:8])[:50000]
    llm = LLMEngine(request=request)
    model = llm.validate_model_id(
        model="",
        capabilities=["chat"],
    )
    logger.debug(f"{request_id} - Performing title extraction using: {model}")
    try:
        response = await llm.generate(
            id=request_id,
            model=model,
            messages=[
                ChatEntry.system("You are an concise assistant."),
                ChatEntry.user(
                    (
                        f"CONTEXT:\n{excerpt}\n\n"
                        "From the excerpt, extract the document title or guess a possible title. "
                        "Provide the title without explanation."
                    )
                ),
            ],
            max_tokens=200,
            temperature=0.01,
            top_p=0.01,
            stream=False,
        )
        title = response.text.strip()
        if title.startswith('"') and title.endswith('"'):
            title = title[1:-1]
    except Exception:
        logger.exception(f"{request_id} - Title extraction errored for excerpt: \n{excerpt}\n")
        title = ""

    # --- Add into Knowledge Table --- #
    organization_id = project.organization.id
    project_id = project.id
    table = GenerativeTable.from_ids(organization_id, project_id, TableType.KNOWLEDGE)
    # Check quota
    request.state.billing.check_gen_table_llm_quota(table, table_id)
    with table.create_session() as session:
        meta = table.open_meta(session, table_id)
        title_embed = None
        text_embeds = []
        for col in meta.cols:
            if col["vlen"] == 0:
                continue
            gen_config = EmbedGenConfig.model_validate(col["gen_config"])
            request.state.billing.check_embedding_quota(model_id=gen_config.embedding_model)
            embedder = CloudEmbedder(request=request)
            if col["id"] == "Title Embed":
                title_embed = await _embed(
                    gen_config.embedding_model, embedder, [title], col["dtype"]
                )
                title_embed = title_embed[0]
            elif col["id"] == "Text Embed":
                # Truncate based on embedder context length
                embedder_context_length = (
                    (llm.model_info(gen_config.embedding_model)).data[0].context_length
                )
                texts = [_truncate_text(chunk.text, embedder_context_length) for chunk in chunks]

                text_embeds = await _embed(
                    gen_config.embedding_model,
                    embedder,
                    texts,
                    col["dtype"],
                )
            else:
                continue
        if title_embed is None or len(text_embeds) == 0:
            raise RuntimeError(
                "Sorry we encountered an issue during embedding. Please try again later."
            )
        row_add_data = [
            {
                "Text": chunk.text,
                "Text Embed": text_embed,
                "Title": title,
                "Title Embed": title_embed,
                "File ID": file_uri,
                "Page": chunk.page,
            }
            for chunk, text_embed in zip(chunks, text_embeds, strict=True)
        ]
        logger.info(
            f'{request_id} - Writing file "{file_name}" with {len(chunks):,d} chunks to DB.'
        )
        await add_rows(
            request=request,
            bg_tasks=bg_tasks,
            project=project,
            table_type=TableType.KNOWLEDGE,
            body=RowAddRequest.model_construct(table_id=table_id, data=row_add_data, stream=False),
        )
        bg_tasks.add_task(_create_indexes, project, "knowledge", table_id)
    return OkResponse()


@router.options("/v1/gen_tables/knowledge/embed_file")
@router.options("/v1/gen_tables/knowledge/upload_file", deprecated=True)
@handle_exception
async def embed_file_options(request: Request, response: Response):
    headers = {
        "Allow": "POST, OPTIONS",
        "Accept": ", ".join(EMBED_WHITE_LIST_MIME),
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    if "upload_file" in request.url.path:
        response.headers["Warning"] = (
            '299 - "This endpoint is deprecated and will be removed in v0.4. '
            "Use '/v1/gen_tables/{table_type}/embed_file' instead."
            '"'
        )
    return Response(content=None, headers=headers)


@router.post("/v1/gen_tables/knowledge/embed_file")
@router.post("/v1/gen_tables/knowledge/upload_file", deprecated=True)
@handle_exception
async def embed_file(
    *,
    request: Request,
    response: Response,
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    file: Annotated[UploadFile, File(description="The file.")],
    file_name: Annotated[str, Form(description="File name.", deprecated=True)] = "",
    table_id: Annotated[str, Form(pattern=TABLE_NAME_PATTERN, description="Knowledge Table ID.")],
    # overwrite: Annotated[
    #     bool, Form(description="Whether to overwrite old file with the same name.")
    # ] = False,
    chunk_size: Annotated[
        int, Form(description="Maximum chunk size (number of characters). Must be > 0.", gt=0)
    ] = 1000,
    chunk_overlap: Annotated[
        int, Form(description="Overlap in characters between chunks. Must be >= 0.", ge=0)
    ] = 200,
    # stream: Annotated[
    #     bool, Form(description="Whether or not to stream the LLM generation.")
    # ] = True,
) -> OkResponse:
    if "upload_file" in request.url.path:
        response.headers["Warning"] = (
            '299 - "This endpoint is deprecated and will be removed in v0.4. '
            "Use '/v1/gen_tables/{table_type}/embed_file' instead."
            '"'
        )
    # Validate the Content-Type of the uploaded file
    file_name = file.filename or file_name
    if splitext(file_name)[1].lower() == ".jsonl":
        file_content_type = "application/jsonl"
    elif splitext(file_name)[1].lower() == ".md":
        file_content_type = "text/markdown"
    elif splitext(file_name)[1].lower() == ".tsv":
        file_content_type = "text/tab-separated-values"
    else:
        file_content_type = file.content_type
    if file_content_type not in EMBED_WHITE_LIST_MIME:
        raise UnsupportedMediaTypeError(
            f"File type '{file_content_type}' is unsupported. Accepted types are: {', '.join(EMBED_WHITE_LIST_MIME)}"
        )
    # --- Add into File Table --- #
    content = await file.read()
    uri = await upload_file_to_s3(
        project.organization.id,
        project.id,
        content,
        file_content_type,
        file_name,
    )
    # if overwrite:
    #     file_table.delete_file(file_name=file_name)
    # --- Add into Knowledge Table --- #
    return await _embed_file(
        request=request,
        bg_tasks=bg_tasks,
        project=project,
        table_id=table_id,
        file_name=file_name,
        file_content=content,
        file_uri=uri,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


@router.post("/v1/gen_tables/{table_type}/import_data")
@handle_exception
async def import_table_data(
    request: Request,
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    file: Annotated[UploadFile, File(description="The CSV or TSV file.")],
    table_id: Annotated[
        str,
        Form(
            pattern=TABLE_NAME_PATTERN,
            description="ID or name of the table that the data should be imported into.",
        ),
    ],
    stream: Annotated[
        bool, Form(description="Whether or not to stream the LLM generation.")
    ] = True,
    # List of inputs is bugged as of 2024-07-14: https://github.com/tiangolo/fastapi/pull/9928/files
    # column_names: Annotated[
    #     list[ColName] | None,
    #     Form(
    #         description="_Optional_. A list of columns names if the CSV does not have header row. Defaults to None (read from CSV).",
    #     ),
    # ] = None,
    # columns: Annotated[
    #     list[ColName] | None,
    #     Form(
    #         description="_Optional_. A list of columns to be imported. Defaults to None (import all columns except 'ID' and 'Updated at').",
    #     ),
    # ] = None,
    delimiter: Annotated[
        CSVDelimiter,
        Form(description='The delimiter, can be "," or "\\t". Defaults to ",".'),
    ] = CSVDelimiter.COMMA,
):
    # Get column info
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with table.create_session() as session:
        meta = table.open_meta(session, table_id, remove_state_cols=True)
        cols = {
            c.id.lower(): c for c in meta.cols_schema if c.id.lower() not in ("id", "updated at")
        }
        cols_dtype = {
            c.id: c.dtype
            for c in meta.cols_schema
            if c.id.lower() not in ("id", "updated at") and c.vlen == 0
        }
    # --- Read file as DataFrame --- #
    content = await file.read()
    try:
        df = csv_to_df(content.decode("utf-8"), sep=delimiter.value)
        # Do not import "ID" and "Updated at"
        keep_cols = [c for c in df.columns.tolist() if c.lower() in cols]
        df = df.filter(items=keep_cols, axis="columns")
    except ValueError as e:
        raise make_validation_error(e, loc=("body", "file")) from e
    # if isinstance(columns, list) and len(columns) > 0:
    #     df = df[columns]
    if len(df) == 0:
        raise make_validation_error(
            ValueError("The file provided is empty."), loc=("body", "file")
        )
    # Convert vector data
    for col_id in df.columns.tolist():
        if cols[col_id.lower()].vlen > 0:
            df[col_id] = df[col_id].apply(json_loads)
    # Cast data to follow column dtype
    for col_id, dtype in cols_dtype.items():
        if col_id not in df.columns:
            continue
        try:
            if dtype == "str":
                df[col_id] = df[col_id].apply(lambda x: str(x) if not pd.isna(x) else x)
            else:
                if dtype in [ColumnDtype.IMAGE, ColumnDtype.AUDIO]:
                    dtype = "str"
                df[col_id] = df[col_id].astype(dtype, errors="raise")
        except ValueError as e:
            raise make_validation_error(e, loc=("body", "file")) from e
    # Convert DF to list of dicts
    row_add_data = df.to_dict(orient="records")
    return await add_rows(
        request=request,
        bg_tasks=bg_tasks,
        project=project,
        table_type=table_type,
        body=RowAddRequest(table_id=table_id, data=row_add_data, stream=stream),
    )


@router.get("/v1/gen_tables/{table_type}/{table_id}/export_data")
@handle_exception
def export_table_data(
    *,
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: Annotated[
        str,
        Path(pattern=TABLE_NAME_PATTERN, description="ID or name of the table to be exported."),
    ],
    delimiter: Annotated[
        CSVDelimiter,
        Query(description='The delimiter, can be "," or "\\t". Defaults to ",".'),
    ] = CSVDelimiter.COMMA,
    columns: Annotated[
        list[ColName] | None,
        Query(
            min_length=1,
            description="_Optional_. A list of columns to be exported. Defaults to None (export all columns).",
        ),
    ] = None,
) -> FileResponse:
    # Export data
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    ext = ".csv" if delimiter == CSVDelimiter.COMMA else ".tsv"
    tmp_dir = TemporaryDirectory()
    filename = f"{table_id}{ext}"
    filepath = join(tmp_dir.name, filename)
    # Keep a reference to the directory and only delete upon completion
    bg_tasks.add_task(tmp_dir.cleanup)
    table.export_csv(
        table_id=table_id,
        columns=columns,
        file_path=filepath,
        delimiter=delimiter,
    )
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.post("/v1/gen_tables/{table_type}/import")
@handle_exception
async def import_table(
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    file: Annotated[UploadFile, File(description="The parquet file.")],
    table_id_dst: Annotated[
        str | None,
        Form(pattern=TABLE_NAME_PATTERN, description="The ID or name of the new table."),
    ] = None,
) -> TableMetaResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    with BytesIO(await file.read()) as source:
        with table.create_session() as session:
            _, meta = await table.import_parquet(
                session=session,
                source=source,
                table_id_dst=table_id_dst,
            )
    meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(meta.id))
    return meta


@router.get("/v1/gen_tables/{table_type}/{table_id}/export")
@handle_exception
def export_table(
    *,
    bg_tasks: BackgroundTasks,
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: Annotated[
        str,
        Path(pattern=TABLE_NAME_PATTERN, description="ID or name of the table to be exported."),
    ],
) -> FileResponse:
    table = GenerativeTable.from_ids(project.organization.id, project.id, table_type)
    tmp_dir = TemporaryDirectory()
    filename = f"{table_id}.parquet"
    filepath = join(tmp_dir.name, filename)
    # Keep a reference to the directory and only delete upon completion
    bg_tasks.add_task(tmp_dir.cleanup)
    with table.create_session() as session:
        table.dump_parquet(
            session=session,
            table_id=table_id,
            dest=filepath,
        )
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream",
    )
