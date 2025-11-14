from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from loguru import logger
from pydantic import BaseModel, Field

from owl.db import TEMPLATE_ORG_ID, AsyncSession, yield_async_session
from owl.db.gen_table import (
    ActionTable,
    ChatTable,
    KnowledgeTable,
)
from owl.db.models import Organization, Project
from owl.types import (
    GetTableRowQuery,
    ListQuery,
    ListTableQuery,
    ListTableRowQuery,
    Page,
    ProjectRead,
    SanitisedNonEmptyStr,
    TableMetaResponse,
    TableType,
)
from owl.utils.exceptions import (
    ResourceNotFoundError,
    handle_exception,
)

router = APIRouter()


class ListTemplateQuery(ListQuery):
    search_query: Annotated[
        str,
        Field(
            max_length=255,
            description='_Optional_. A string to search for within project names as a filter. Defaults to "" (no filter).',
        ),
    ] = ""


@router.get(
    "/v2/templates/list",
    summary="List templates.",
    description="Permissions: None, publicly accessible.",
)
@handle_exception
async def list_templates(
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ListTemplateQuery, Query()],
) -> Page[ProjectRead]:
    # Ensure the organization exists
    if (await session.get(Organization, TEMPLATE_ORG_ID)) is None:
        logger.warning(f'Template organization "{TEMPLATE_ORG_ID}" does not exist.')
        return Page[ProjectRead](
            items=[],
            offset=params.offset,
            limit=params.limit,
            total=0,
        )
    # List
    return await Project.list_(
        session=session,
        return_type=ProjectRead,
        offset=params.offset,
        limit=params.limit,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        search_query=params.search_query,
        search_columns=params.search_columns,
        filters=dict(organization_id=TEMPLATE_ORG_ID),
        after=params.after,
    )


@router.get(
    "/v2/templates",
    summary="Get a specific template.",
    description="Permissions: None, publicly accessible.",
)
@handle_exception
async def get_template(
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    template_id: Annotated[str, Query(min_length=1, description="Template ID.")],
) -> ProjectRead:
    # Fetch the template
    template = await session.get(Project, template_id)
    if template is None:
        raise ResourceNotFoundError(f'Template "{template_id}" is not found.')
    return template


TABLE_CLS: dict[TableType, ActionTable | KnowledgeTable | ChatTable] = {
    TableType.ACTION: ActionTable,
    TableType.KNOWLEDGE: KnowledgeTable,
    TableType.CHAT: ChatTable,
}


class _ListTableQuery(ListTableQuery):
    template_id: Annotated[str, Field(min_length=1, description="Template ID.")]


@router.get(
    "/v2/templates/gen_tables/{table_type}/list",
    summary="List tables in a template.",
    description="Permissions: None, publicly accessible.",
)
@handle_exception
async def list_tables(
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[_ListTableQuery, Query()],
) -> Page[TableMetaResponse]:
    metas = await TABLE_CLS[table_type].list_tables(
        project_id=params.template_id,
        limit=params.limit,
        offset=params.offset,
        parent_id=params.parent_id,
        search_query=params.search_query,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        count_rows=params.count_rows,
    )
    return metas


class GetTableQuery(BaseModel):
    template_id: Annotated[str, Field(min_length=1, description="Template ID.")]
    table_id: Annotated[SanitisedNonEmptyStr, Field(description="The ID of the table to fetch.")]


@router.get(
    "/v2/templates/gen_tables/{table_type}",
    summary="Get a specific table from a template.",
    description="Permissions: None, publicly accessible.",
)
@handle_exception
async def get_table(
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[GetTableQuery, Query()],
) -> TableMetaResponse:
    table = await TABLE_CLS[table_type].open_table(
        project_id=params.template_id, table_id=params.table_id
    )
    return table.v1_meta_response


class _ListTableRowQuery(ListTableRowQuery):
    template_id: Annotated[str, Field(min_length=1, description="Template ID.")]


@router.get(
    "/v2/templates/gen_tables/{table_type}/rows/list",
    summary="List rows in a template table.",
    description="Permissions: None, publicly accessible.",
)
@handle_exception
async def list_table_rows(
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[_ListTableRowQuery, Query()],
) -> Page[dict[str, Any]]:
    table = await TABLE_CLS[table_type].open_table(
        project_id=params.template_id, table_id=params.table_id
    )
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


class _GetTableRowQuery(GetTableRowQuery):
    template_id: Annotated[str, Field(min_length=1, description="Template ID.")]


@router.get(
    "/v2/templates/gen_tables/{table_type}/rows",
    summary="Get a specific row from a template table.",
    description="Permissions: None, publicly accessible.",
)
@handle_exception
async def get_table_row(
    table_type: Annotated[TableType, Path(description="Table type.")],
    params: Annotated[_GetTableRowQuery, Query()],
) -> dict[str, Any]:
    table = await TABLE_CLS[table_type].open_table(
        project_id=params.template_id, table_id=params.table_id
    )
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
