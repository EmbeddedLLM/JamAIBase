from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from owl.db import AsyncSession, yield_async_session
from owl.db.gen_executor import GenExecutor
from owl.db.models import ModelConfig
from owl.types import (
    EXAMPLE_CHAT_MODEL_IDS,
    ChatRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelCapability,
    ModelInfoListResponse,
    ModelInfoRead,
    OrganizationRead,
    ProjectRead,
    RerankingRequest,
    RerankingResponse,
    UserAuth,
)
from owl.utils.auth import auth_user_project
from owl.utils.billing import BillingManager
from owl.utils.exceptions import ResourceNotFoundError, handle_exception
from owl.utils.lm import LMEngine
from owl.utils.mcp import MCP_TOOL_TAG

router = APIRouter()


class _ListQuery(BaseModel):
    order_by: Literal["id", "name", "created_at", "updated_at"] = Field(
        "id",
        description='Sort by this attribute. Defaults to "id".',
    )
    order_ascending: bool = Field(
        True,
        description="Whether to sort in ascending order. Defaults to True.",
    )
    capabilities: list[ModelCapability] | None = Field(
        None,
        description=(
            "Filter the model info by model's capabilities. Defaults to None (no filter)."
        ),
        examples=[[ModelCapability.CHAT]],
    )


class ModelInfoListQuery(_ListQuery):
    model: str = Field(
        "",
        description="ID of the requested model.",
        examples=EXAMPLE_CHAT_MODEL_IDS,
    )


@router.get(
    "/v1/models",
    summary="List the info of models available.",
    description="List the info of models available with the specified name and capabilities.",
    tags=[MCP_TOOL_TAG, "project"],
)
@handle_exception
async def model_info(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ModelInfoListQuery, Query()],
) -> ModelInfoListResponse:
    _, _, org = auth_info
    try:
        models = (
            await ModelConfig.list_(
                session=session,
                return_type=ModelInfoRead,
                organization_id=org.id,
                order_by=params.order_by,
                order_ascending=params.order_ascending,
                capabilities=params.capabilities,
                exclude_inactive=True,
            )
        ).items
        # Filter by name
        if params.model != "":
            models = [m for m in models if m.id == params.model]
        return ModelInfoListResponse(data=models)
    except ResourceNotFoundError:
        return ModelInfoListResponse(data=[])


class ModelIdListQuery(_ListQuery):
    prefer: str = Field(
        "",
        description="ID of the preferred model.",
        examples=EXAMPLE_CHAT_MODEL_IDS,
    )


@router.get(
    "/v1/models/ids",
    summary="List the ID of models available.",
    description=(
        "List the ID of models available with the specified capabilities with an optional preferred model. "
        "If the preferred model is not available, then return the first available model."
    ),
)
@router.get(
    "/v1/model_names",
    deprecated=True,
    summary="List the ID of models available.",
    description="Deprecated, use `/v1/models/ids` instead. List the ID of models available.",
)
@handle_exception
async def model_ids(
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    session: Annotated[AsyncSession, Depends(yield_async_session)],
    params: Annotated[ModelIdListQuery, Query()],
) -> list[str]:
    models = await model_info(
        auth_info,
        session,
        ModelInfoListQuery(
            order_by=params.order_by,
            order_ascending=params.order_ascending,
            capabilities=params.capabilities,
            model="",
        ),
    )
    names = [m.id for m in models.data]
    if params.prefer in names:
        names.remove(params.prefer)
        names.insert(0, params.prefer)
    return names


async def _empty_async_generator():
    """Returns an empty asynchronous generator."""
    return
    # This line is never reached, but makes it an async generator
    yield


@router.post(
    "/v1/chat/completions",
    summary="Chat completion.",
    description="Given a list of messages comprising a conversation, returns a response from the model.",
)
@handle_exception
async def chat_completion(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: ChatRequest,
) -> Response:
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_llm_quota(body.model)
    billing.has_egress_quota()
    _, project, org = auth_info
    body.id = request.state.id
    llm = LMEngine(organization=org, project=project, request=request)
    body, references = await GenExecutor.setup_rag(
        project=project, lm=llm, body=body, request_id=body.id
    )
    if body.stream:
        agen = llm.chat_completion_stream(messages=body.messages, **body.hyperparams)
        try:
            chunk = await anext(agen)
        except StopAsyncIteration:
            return StreamingResponse(
                content=_empty_async_generator(),
                status_code=200,
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no"},
            )

        async def _generate():
            content_length = 1
            if references is not None:
                sse = f"data: {references.model_dump_json()}\n\n"
                content_length += len(sse.encode("utf-8"))
                yield sse
            nonlocal chunk
            yield f"data: {chunk.model_dump_json(exclude_unset=True)}\n\n"
            async for chunk in agen:
                sse = f"data: {chunk.model_dump_json(exclude_unset=True)}\n\n"
                content_length += len(sse.encode("utf-8"))
                yield sse
            sse = "data: [DONE]\n\n"
            content_length += len(sse.encode("utf-8"))
            yield sse
            # NOTE: We must create egress events here as SSE cannot be handled in the middleware
            billing.create_egress_events(content_length / (1024**3))

        response = StreamingResponse(
            content=_generate(),
            status_code=200,
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )
    else:
        response = await llm.chat_completion(messages=body.messages, **body.hyperparams)
        if references is not None:
            response.references = references
        return response
        # NOTE: Do not create egress events here as it is handled in the middleware
    return response


@router.post(
    "/v1/embeddings",
    summary="Embeds texts as vectors.",
    description=(
        "Get a vector representation of a given input that can be easily consumed by machine learning models and algorithms. "
        "Note that the vectors are NOT normalized."
    ),
)
@handle_exception
async def generate_embeddings(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: EmbeddingRequest,
) -> EmbeddingResponse:
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_embedding_quota(body.model)
    billing.has_egress_quota()
    _, project, org = auth_info
    embedder = LMEngine(organization=org, project=project, request=request)
    if isinstance(body.input, str):
        body.input = [body.input]
    kwargs = dict(
        model=body.model,
        texts=body.input,
        encoding_format=body.encoding_format,
    )
    if body.type == "document":
        embeddings = await embedder.embed_documents(**kwargs)
    else:
        embeddings = await embedder.embed_queries(**kwargs)
    return embeddings


@router.post(
    "/v1/rerank",
    summary="Ranks each text input to the query text.",
    description="Get the similarity score of each text input to query by giving a query and list of text inputs.",
)
@handle_exception
async def generate_rankings(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    body: RerankingRequest,
) -> RerankingResponse:
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_reranker_quota(body.model)
    billing.has_egress_quota()
    _, project, org = auth_info
    reranker = LMEngine(organization=org, project=project, request=request)
    return await reranker.rerank_documents(**body.model_dump())
