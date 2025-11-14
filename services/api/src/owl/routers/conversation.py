from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from owl.db.gen_executor import MultiRowGenExecutor
from owl.db.gen_table import ChatTable
from owl.types import (
    AgentMetaResponse,
    ConversationCreateRequest,
    ConversationMetaResponse,
    ConversationThreadsResponse,
    GetConversationThreadsQuery,
    ListMessageQuery,
    ListQuery,
    LLMGenConfig,
    MessageAddRequest,
    MessagesRegenRequest,
    MessageUpdateRequest,
    MultiRowAddRequest,
    MultiRowRegenRequest,
    OkResponse,
    OrganizationRead,
    Page,
    ProjectRead,
    SanitisedStr,
    TableMetaResponse,
    UserAuth,
)
from owl.utils.auth import auth_user_project, has_permissions
from owl.utils.billing import BillingManager
from owl.utils.exceptions import ResourceNotFoundError, handle_exception
from owl.utils.lm import LMEngine
from owl.utils.mcp import MCP_TOOL_TAG

router = APIRouter()


def _table_meta_to_conv(metas: Page[TableMetaResponse]) -> Page[ConversationMetaResponse]:
    """Converts Page[TableMetaResponse] to Page[ConversationMetaResponse]."""
    return Page[ConversationMetaResponse](
        items=[ConversationMetaResponse.from_table_meta(m) for m in metas.items],
        limit=metas.limit,
        offset=metas.offset,
        total=metas.total,
    )


async def _generate_and_save_title(
    request: Request,
    project: ProjectRead,
    organization: OrganizationRead,
    conversation_id: str,
    table: ChatTable,
):
    first_multiturn_column_meta = next(
        (
            c
            for c in table.column_metadata
            if isinstance(c.gen_config, LLMGenConfig) and c.gen_config.multi_turn
        ),
        None,
    )
    if first_multiturn_column_meta is None:
        raise ResourceNotFoundError(
            f'Conversation "{conversation_id}" has no multi-turn LLM column configured.'
        )

    first_multiturn_column_id = first_multiturn_column_meta.column_id
    title_model_id = first_multiturn_column_meta.gen_config.model

    # Generate title after the first user message is saved and streamed
    rows_page = await table.list_rows(limit=1, order_ascending=True)
    first_user_content = rows_page.items[0].get("User", "")
    first_assistant_content = rows_page.items[0].get(first_multiturn_column_id, "")

    llm = LMEngine(organization=organization, project=project, request=request)
    generated_title = await llm.generate_chat_title(
        user_content=first_user_content,
        assistant_content=first_assistant_content,
        model=title_model_id,
    )
    await table.update_table_title(generated_title)


### --- Conversations CRUD --- ###


@router.post(
    "/v2/conversations",
    summary="Creates a new conversation and sends the first message. "
    "Title will be generated automatically if not provided.",
    description="Permissions: `project`.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def create_conversation(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: ConversationCreateRequest,
) -> StreamingResponse:
    user, project, org = auth_info
    has_permissions(user, ["project"], project_id=project.id)
    table_id = body.agent_id
    # Validate data early
    row_data = MultiRowAddRequest(table_id=table_id, data=[body.data], stream=True)
    table = await ChatTable.open_table(project_id=project.id, table_id=table_id)
    if table.table_metadata.parent_id is not None:
        raise ResourceNotFoundError(f'Agent "{table_id}" is not found.')

    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_db_storage_quota()
    billing.has_egress_quota()

    table = await table.duplicate_table(
        project_id=project.id,
        table_id_src=table_id,
        table_id_dst=None,
        include_data=False,
        create_as_child=True,
        created_by=user.id,
    )
    if body.title is not None:
        table = await table.update_table_title(body.title)
    conversation_id = table.table_metadata.table_id
    row_data.table_id = conversation_id
    executor = MultiRowGenExecutor(
        request=request,
        table=table,
        organization=org,
        project=project,
        body=row_data,
    )

    async def stream_generator():
        meta = ConversationMetaResponse.from_table_meta(table.v1_meta_response)
        yield f"event: metadata\ndata: {meta.model_dump_json()}\n\n"

        generator = await executor.generate()
        async for chunk in generator:
            if body.title is None and chunk == "data: [DONE]\n\n":
                try:
                    await _generate_and_save_title(
                        request=request,
                        project=project,
                        organization=org,
                        conversation_id=conversation_id,
                        table=table,
                    )
                except Exception as e:
                    logger.error(f"Error generating title: {repr(e)}")
                finally:
                    meta = ConversationMetaResponse.from_table_meta(table.v1_meta_response)
                    yield f"event: metadata\ndata: {meta.model_dump_json()}\n\n"
            yield chunk

    return StreamingResponse(
        content=stream_generator(),
        status_code=200,
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.get(
    "/v2/conversations/list",
    summary="Lists all conversations.",
    description="Permissions: `project`.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def list_conversations(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    params: Annotated[ListQuery, Query()],
) -> Page[ConversationMetaResponse]:
    user, project, _ = auth_info
    has_permissions(user, ["project"], project_id=project.id)

    metas = await ChatTable.list_tables(
        project_id=project.id,
        limit=params.limit,
        offset=params.offset,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        created_by=user.id,
        parent_id="_chat_",
        search_query=params.search_query,
        search_columns=["title"],
    )
    return _table_meta_to_conv(metas)


@router.get(
    "/v2/conversations/agents/list",
    summary="Lists all available agents.",
    description="Permissions: `project`.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def list_agents(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    params: Annotated[ListQuery, Query()],
) -> Page[ConversationMetaResponse]:
    user, project, _ = auth_info
    has_permissions(user, ["project"], project_id=project.id)

    metas = await ChatTable.list_tables(
        project_id=project.id,
        limit=params.limit,
        offset=params.offset,
        order_by=params.order_by,
        order_ascending=params.order_ascending,
        parent_id="_agent_",
        search_query=params.search_query,
        search_columns=["table_id"],
    )
    return _table_meta_to_conv(metas)


@router.get(
    "/v2/conversations",
    summary="Fetches a single conversation (table) metadata.",
    description="Permissions: `project`.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def get_conversation(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    conversation_id: Annotated[str, Query(description="The ID of the conversation to fetch.")],
) -> ConversationMetaResponse:
    """Fetches a single conversation metadata."""
    user, project, _ = auth_info
    has_permissions(user, ["project"], project_id=project.id)
    try:
        table = await ChatTable.open_table(
            project_id=project.id, table_id=conversation_id, created_by=user.id
        )
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Conversation "{conversation_id}" not found.') from e
    return ConversationMetaResponse.from_table_meta(table.v1_meta_response)


@router.get(
    "/v2/conversations/agents",
    summary="Fetches a single agent (table) metadata.",
    description="Permissions: `project`.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def get_agent(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    agent_id: Annotated[str, Query(description="The ID of the agent to fetch.")],
) -> AgentMetaResponse:
    """Fetches a single agent metadata."""
    user, project, _ = auth_info
    has_permissions(user, ["project"], project_id=project.id)
    try:
        table = await ChatTable.open_table(project_id=project.id, table_id=agent_id)
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Agent "{agent_id}" not found.') from e
    return AgentMetaResponse.from_table_meta(table.v1_meta_response)


@router.post(
    "/v2/conversations/title",
    summary="Generates a title for a conversation based on the first user message and assistant response. "
    "If the conversation already has a title, it will be overwritten.",
    description="Permissions: `project`.",
)
@handle_exception
async def generate_conversation_title(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    conversation_id: Annotated[
        str, Query(description="The ID of the conversation to generate a title for.")
    ],
) -> ConversationMetaResponse:
    user, project, org = auth_info
    has_permissions(user, ["project"], project_id=project.id)

    try:
        table = await ChatTable.open_table(
            project_id=project.id, table_id=conversation_id, created_by=user.id
        )
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Conversation "{conversation_id}" not found.') from e

    await _generate_and_save_title(
        request=request,
        project=project,
        organization=org,
        conversation_id=conversation_id,
        table=table,
    )
    return ConversationMetaResponse.from_table_meta(table.v1_meta_response)


@router.patch(
    "/v2/conversations/title",
    summary="Renames conversation title.",
    description="Permissions: `project`.",
)
@handle_exception
async def rename_conversation_title(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    conversation_id: Annotated[str, Query(description="The ID of the conversation to rename.")],
    title: Annotated[SanitisedStr, Query(description="The new title for the conversation.")],
) -> ConversationMetaResponse:
    user, project, _ = auth_info
    has_permissions(user, ["project"], project_id=project.id)

    try:
        table = await ChatTable.open_table(
            project_id=project.id, table_id=conversation_id, created_by=user.id
        )
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Conversation "{conversation_id}" not found.') from e

    table = await table.update_table_title(title)
    return ConversationMetaResponse.from_table_meta(table.v1_meta_response)


@router.delete(
    "/v2/conversations",
    summary="Deletes a conversation permanently.",
    description="Permissions: `project`.",
)
@handle_exception
async def delete_conversation(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    conversation_id: Annotated[str, Query(description="The ID of the conversation to delete.")],
) -> OkResponse:
    user, project, _ = auth_info
    has_permissions(user, ["project"], project_id=project.id)

    try:
        table = await ChatTable.open_table(
            project_id=project.id, table_id=conversation_id, created_by=user.id
        )
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Conversation "{conversation_id}" not found.') from e

    await table.drop_table()
    return OkResponse()


### --- Messages CRUD --- ###


@router.post(
    "/v2/conversations/messages",
    summary="Sends a message to a conversation and streams the response.",
    description="Permissions: `project`.",
)
@handle_exception
async def send_message(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: MessageAddRequest,
) -> StreamingResponse:
    user, project, org = auth_info
    has_permissions(user, ["project"], project_id=project.id)
    conversation_id = body.conversation_id
    # Validate data early
    row_data = MultiRowAddRequest(table_id=conversation_id, data=[body.data], stream=True)
    try:
        table = await ChatTable.open_table(
            project_id=project.id, table_id=conversation_id, created_by=user.id
        )
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Conversation "{conversation_id}" not found.') from e

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
        body=row_data,
    )

    return StreamingResponse(
        content=await executor.generate(),
        status_code=200,
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.get(
    "/v2/conversations/messages/list",
    summary="Lists messages in a conversation.",
    description="Permissions: `project`.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def list_messages(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    params: Annotated[ListMessageQuery, Query()],
) -> Page[dict[str, Any]]:
    user, project, _ = auth_info
    has_permissions(user, ["project"], project_id=project.id)

    try:
        table = await ChatTable.open_table(
            project_id=project.id, table_id=params.conversation_id, created_by=user.id
        )
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Conversation "{params.conversation_id}" not found.') from e

    return await table.list_rows(
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


@router.post(
    "/v2/conversations/messages/regen",
    summary="Regenerates a specific message in a conversation and streams back the response.",
    description="Permissions: `project`.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def regen_conversation_message(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: MessagesRegenRequest,
) -> StreamingResponse:
    user, project, org = auth_info
    has_permissions(user, ["project"], project_id=project.id)

    conversation_id = body.conversation_id
    try:
        table = await ChatTable.open_table(
            project_id=project.id, table_id=conversation_id, created_by=user.id
        )
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Conversation "{conversation_id}" not found.') from e

    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_gen_table_quota(table)
    billing.has_egress_quota()

    # Construct the full request for the executor
    regen_rows = await table.list_rows(
        where=f"\"ID\" >= '{body.row_id}'", columns=["ID"], order_by=["ID"], order_ascending=True
    )
    regen_row_ids = [str(r["ID"]) for r in regen_rows.items]

    executor = MultiRowGenExecutor(
        request=request,
        table=table,
        organization=org,
        project=project,
        body=MultiRowRegenRequest(
            table_id=table.table_metadata.table_id, row_ids=regen_row_ids, stream=True
        ),
    )

    return StreamingResponse(
        content=await executor.generate(),
        status_code=200,
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.patch(
    "/v2/conversations/messages",
    summary="Updates a specific message in a conversation.",
    description="Permissions: `project`.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def update_conversation_message(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: MessageUpdateRequest,
) -> OkResponse:
    user, project, _ = auth_info
    has_permissions(user, ["project"], project_id=project.id)

    try:
        table = await ChatTable.open_table(
            project_id=project.id, table_id=body.conversation_id, created_by=user.id
        )
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Conversation "{body.conversation_id}" not found.') from e

    # Check quota for DB write
    billing: BillingManager = request.state.billing
    billing.has_db_storage_quota()

    await table.update_rows({body.row_id: body.data})

    return OkResponse()


### --- Threads CRUD --- ###


@router.get(
    "/v2/conversations/threads",
    summary="Get all threads from a conversation or an agent.",
    description="Permissions: `project`.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def get_threads(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    params: Annotated[GetConversationThreadsQuery, Query()],
) -> ConversationThreadsResponse:
    user, project, _ = auth_info
    has_permissions(user, ["project"], project_id=project.id)
    table_id = params.conversation_id
    try:
        table = await ChatTable.open_table(project_id=project.id, table_id=table_id)
    except ResourceNotFoundError as e:
        raise ResourceNotFoundError(f'Conversation "{table_id}" not found.') from e
    if table.table_metadata.parent_id is None:
        pass
    elif table.table_metadata.created_by != user.id:
        raise ResourceNotFoundError(f'Conversation "{table_id}" not found.')
    if params.column_ids:
        for column_id in params.column_ids:
            table.check_multiturn_column(column_id)
        cols = params.column_ids
    else:
        cols = [c.column_id for c in table.column_metadata if c.is_chat_column]
    return ConversationThreadsResponse(
        threads={c: await table.get_conversation_thread(column_id=c) for c in cols},
        conversation_id=table_id,
    )
