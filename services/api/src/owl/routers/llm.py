"""
LLM operations.
"""

import base64
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from jamaibase.exceptions import ResourceNotFoundError
from owl.llm import LLMEngine
from owl.models import CloudEmbedder
from owl.protocol import (
    EXAMPLE_CHAT_MODEL,
    ChatRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingResponseData,
    ModelCapability,
    ModelInfoResponse,
)
from owl.utils.auth import auth_user_project
from owl.utils.exceptions import handle_exception

router = APIRouter(dependencies=[Depends(auth_user_project)])


@router.get(
    "/v1/models",
    summary="List the info of models available.",
    description="List the info of models available with the specified name and capabilities.",
)
@handle_exception
async def get_model_info(
    request: Request,
    model: Annotated[
        str,
        Query(
            description="ID of the requested model.",
            examples=[EXAMPLE_CHAT_MODEL],
        ),
    ] = "",
    capabilities: Annotated[
        list[ModelCapability] | None,
        Query(
            description=(
                "Filter the model info by model's capabilities. "
                "Leave it blank to disable filter."
            ),
            examples=[[ModelCapability.CHAT]],
        ),
    ] = None,
) -> ModelInfoResponse:
    try:
        if capabilities is not None:
            capabilities = [c.value for c in capabilities]
        return LLMEngine(request=request).model_info(
            model=model,
            capabilities=capabilities,
        )
    except ResourceNotFoundError:
        return ModelInfoResponse(data=[])


@router.get(
    "/v1/model_names",
    summary="List the ID of models available.",
    description=(
        "List the ID of models available with the specified capabilities with an optional preferred model. "
        "If the preferred model is not available, then return the first available model."
    ),
)
@handle_exception
async def get_model_names(
    request: Request,
    prefer: Annotated[
        str,
        Query(
            description="ID of the preferred model.",
            examples=[EXAMPLE_CHAT_MODEL],
        ),
    ] = "",
    capabilities: Annotated[
        list[ModelCapability] | None,
        Query(
            description=(
                "Filter the model info by model's capabilities. "
                "Leave it blank to disable filter."
            ),
            examples=[[ModelCapability.CHAT]],
        ),
    ] = None,
) -> list[str]:
    try:
        if capabilities is not None:
            capabilities = [c.value for c in capabilities]
        return LLMEngine(request=request).model_names(
            prefer=prefer,
            capabilities=capabilities,
        )
    except ResourceNotFoundError:
        return []


@router.post(
    "/v1/chat/completions",
    description="Given a list of messages comprising a conversation, the model will return a response.",
)
@handle_exception
async def generate_completions(request: Request, body: ChatRequest):
    # Check quota
    request.state.billing.check_llm_quota(body.model)
    request.state.billing.check_egress_quota()
    # Run LLM
    llm = LLMEngine(request=request)
    # object key could cause issue to some LLM provider, ex: Anthropic
    body.id = request.state.id
    hyperparams = body.model_dump(exclude_none=True, exclude={"object"})
    if body.stream:

        async def _generate():
            content_length = 0
            async for chunk in llm.rag_stream(**hyperparams):
                sse = f"data: {chunk.model_dump_json()}\n\n"
                content_length += len(sse.encode("utf-8"))
                yield sse
            sse = "data: [DONE]\n\n"
            content_length += len(sse.encode("utf-8"))
            yield sse
            request.state.billing.create_egress_events(content_length / (1024**3))

        response = StreamingResponse(
            content=_generate(),
            status_code=200,
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    else:
        response = await llm.rag(**hyperparams)
        request.state.billing.create_egress_events(
            len(response.model_dump_json().encode("utf-8")) / (1024**3)
        )
    return response


@router.post(
    "/v1/embeddings",
    description=(
        "Get a vector representation of a given input that can be "
        "easily consumed by machine learning models and algorithms. "
        "Note that the vectors are NOT normalized."
    ),
)
@handle_exception
async def generate_embeddings(request: Request, body: EmbeddingRequest) -> EmbeddingResponse:
    embedder = CloudEmbedder(request=request)
    if isinstance(body.input, str):
        body.input = [body.input]
    if body.type == "document":
        embeddings = await embedder.embed_documents(embedder_name=body.model, texts=body.input)
    else:
        embeddings = await embedder.embed_queries(embedder_name=body.model, texts=body.input)
    if body.encoding_format == "base64":
        embeddings.data = [
            EmbeddingResponseData(
                embedding=base64.b64encode(np.asarray(e.embedding, dtype=np.float32)), index=i
            )
            for i, e in enumerate(embeddings.data)
        ]
    return embeddings
