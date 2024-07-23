"""
LLM operations.
"""

import base64
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from owl import protocol as p
from owl.llm import LLMEngine
from owl.models import CloudEmbedder
from owl.utils.exceptions import OwlException, ResourceNotFoundError

router = APIRouter()


@router.get(
    "/v1/models",
    summary="List the info of models available.",
    description="List the info of models available with the specified name and capabilities.",
)
async def get_model_info(
    request: Request,
    model: Annotated[
        str,
        Query(
            description="ID of the requested model.",
            examples=[p.DEFAULT_CHAT_MODEL],
        ),
    ] = "",
    capabilities: Annotated[
        list[p.ModelCapability] | None,
        Query(
            description=(
                "Filter the model info by model's capabilities. "
                "Leave it blank to disable filter."
            ),
            examples=[[p.ModelCapability.chat]],
        ),
    ] = None,
    openai_api_key: Annotated[str, Header(description="OpenAI API key.")] = "",
    anthropic_api_key: Annotated[str, Header(description="Anthropic API key.")] = "",
    gemini_api_key: Annotated[str, Header(description="Google Gemini API key.")] = "",
    cohere_api_key: Annotated[str, Header(description="Cohere API key.")] = "",
    groq_api_key: Annotated[str, Header(description="Groq API key.")] = "",
    together_api_key: Annotated[str, Header(description="Together AI API key.")] = "",
    jina_api_key: Annotated[str, Header(description="Jina API key.")] = "",
    voyage_api_key: Annotated[str, Header(description="Voyage API key.")] = "",
) -> p.ModelInfoResponse:
    logger.info(f"Listing model info with capabilities: {capabilities}")
    try:
        if capabilities is not None:
            capabilities = [c.value for c in capabilities]
        llm = LLMEngine(
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
        return llm.model_info(
            model=model,
            capabilities=capabilities,
        )
    except ResourceNotFoundError:
        return p.ModelInfoResponse(data=[])
    except Exception:
        logger.exception(
            (
                f"{request.state.id} - [{request.state.org_id}/{request.state.project_id}] "
                f"Failed to list model info: model={model}  capabilities={capabilities}"
            )
        )
        raise


@router.get(
    "/v1/model_names",
    summary="List the ID of models available.",
    description=(
        "List the ID of models available with the specified capabilities with an optional preferred model. "
        "If the preferred model is not available, then return the first available model."
    ),
)
async def get_model_names(
    request: Request,
    prefer: Annotated[
        str,
        Query(
            description="ID of the preferred model.",
            examples=[p.DEFAULT_CHAT_MODEL],
        ),
    ] = "",
    capabilities: Annotated[
        list[p.ModelCapability] | None,
        Query(
            description=(
                "Filter the model info by model's capabilities. "
                "Leave it blank to disable filter."
            ),
            examples=[[p.ModelCapability.chat]],
        ),
    ] = None,
    openai_api_key: Annotated[str, Header(description="OpenAI API key.")] = "",
    anthropic_api_key: Annotated[str, Header(description="Anthropic API key.")] = "",
    gemini_api_key: Annotated[str, Header(description="Google Gemini API key.")] = "",
    cohere_api_key: Annotated[str, Header(description="Cohere API key.")] = "",
    groq_api_key: Annotated[str, Header(description="Groq API key.")] = "",
    together_api_key: Annotated[str, Header(description="Together AI API key.")] = "",
    jina_api_key: Annotated[str, Header(description="Jina API key.")] = "",
    voyage_api_key: Annotated[str, Header(description="Voyage API key.")] = "",
) -> list[str]:
    try:
        if capabilities is not None:
            capabilities = [c.value for c in capabilities]
        llm = LLMEngine(
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
        return llm.model_names(
            prefer=prefer,
            capabilities=capabilities,
        )
    except ResourceNotFoundError:
        return []
    except Exception:
        logger.exception(
            (
                f"{request.state.id} - [{request.state.org_id}/{request.state.project_id}] "
                f"Failed to list model names: prefer={prefer}  capabilities={capabilities}"
            )
        )
        raise


@router.post(
    "/v1/chat/completions",
    description="Given a list of messages comprising a conversation, the model will return a response.",
)
async def generate_completions(
    request: Request,
    body: p.ChatRequest,
    openai_api_key: Annotated[str, Header(description="OpenAI API key.")] = "",
    anthropic_api_key: Annotated[str, Header(description="Anthropic API key.")] = "",
    gemini_api_key: Annotated[str, Header(description="Google Gemini API key.")] = "",
    cohere_api_key: Annotated[str, Header(description="Cohere API key.")] = "",
    groq_api_key: Annotated[str, Header(description="Groq API key.")] = "",
    together_api_key: Annotated[str, Header(description="Together AI API key.")] = "",
    jina_api_key: Annotated[str, Header(description="Jina API key.")] = "",
    voyage_api_key: Annotated[str, Header(description="Voyage API key.")] = "",
):
    try:
        # Check quota
        request.state.billing_manager.check_llm_quota(body.model)
        request.state.billing_manager.check_egress_quota()
        # Run LLM
        llm = LLMEngine(
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
        hyperparams = body.model_dump(exclude_none=True)
        if body.stream:

            async def _generate():
                content_length = 0
                async for chunk in llm.rag_stream(request=request, **hyperparams):
                    sse = f"data: {chunk.model_dump_json()}\n\n"
                    content_length += len(sse.encode("utf-8"))
                    yield sse
                sse = "data: [DONE]\n\n"
                content_length += len(sse.encode("utf-8"))
                yield sse
                request.state.billing_manager.create_egress_events(content_length / (1024**3))

            response = StreamingResponse(
                content=_generate(),
                status_code=200,
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no"},
            )

        else:
            response = await llm.rag(request=request, **hyperparams)
            request.state.billing_manager.create_egress_events(
                len(response.model_dump_json().encode("utf-8")) / (1024**3)
            )
        return response
    except OwlException:
        raise
    except Exception:
        logger.exception(
            (
                f"{request.state.id} - [{request.state.org_id}/{request.state.project_id}] "
                f"Failed to generate chat completion: body={body}"
            )
        )
        raise


@router.post(
    "/v1/embeddings",
    description=(
        "Get a vector representation of a given input that can be "
        "easily consumed by machine learning models and algorithms. "
        "Note that the vectors are NOT normalized."
    ),
)
async def generate_embeddings(
    request: Request,
    body: p.EmbeddingRequest,
    openai_api_key: Annotated[str, Header(description="OpenAI API key.")] = "",
    anthropic_api_key: Annotated[str, Header(description="Anthropic API key.")] = "",
    gemini_api_key: Annotated[str, Header(description="Google Gemini API key.")] = "",
    cohere_api_key: Annotated[str, Header(description="Cohere API key.")] = "",
    groq_api_key: Annotated[str, Header(description="Groq API key.")] = "",
    together_api_key: Annotated[str, Header(description="Together AI API key.")] = "",
    jina_api_key: Annotated[str, Header(description="Jina API key.")] = "",
    voyage_api_key: Annotated[str, Header(description="Voyage API key.")] = "",
) -> p.EmbeddingResponse:
    try:
        embedder = CloudEmbedder(
            embedder_name=body.model,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
        if isinstance(body.input, str):
            body.input = [body.input]
        if body.type == "document":
            embeddings = embedder.embed_documents(texts=body.input)
        else:
            embeddings = embedder.embed_queries(texts=body.input)
        if body.encoding_format == "base64":
            embeddings.data = [
                p.EmbeddingResponseData(
                    embedding=base64.b64encode(np.asarray(e.embedding, dtype=np.float32)), index=i
                )
                for i, e in enumerate(embeddings.data)
            ]
        return embeddings
    except OwlException:
        raise
    except Exception:
        logger.exception(
            (
                f"{request.state.id} - [{request.state.org_id}/{request.state.project_id}] "
                f"Failed to generate embedding: body={body}"
            )
        )
        raise
