"""
LLM operations.
"""

from copy import deepcopy
from datetime import datetime, timezone
from time import time
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from jamaibase import protocol as p
from owl.db.gen_table import KnowledgeTable
from owl.llm import model_info, model_names, predict, predict_stream
from owl.utils.exceptions import ContextOverflowError, OwlException, ResourceNotFoundError


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    owl_db_dir: str = "db"


router = APIRouter()
config = Config()


@router.on_event("startup")
async def startup():
    # Router lifespan is broken as of fastapi==0.109.0 and starlette==0.35.1
    # https://github.com/tiangolo/fastapi/discussions/9664
    logger.info(f"LLM router config: {config}")


@router.get(
    "/v1/models",
    summary="List the info of models available.",
    description="List the info of models available with the specified name and capabilities.",
)
async def get_model_info(
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
        return await model_info(
            model=model,
            capabilities=capabilities,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
    except ResourceNotFoundError:
        return p.ModelInfoResponse(data=[])
    except Exception:
        logger.exception(f"Failed to list model info.")
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
        return await model_names(
            prefer=prefer,
            capabilities=capabilities,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
    except ResourceNotFoundError:
        return []
    except Exception:
        logger.exception(f"Failed to list model names.")
        raise


async def _preprocess_completion(
    request: Request,
    body: p.ChatRequest,
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
    cohere_api_key: str = "",
    groq_api_key: str = "",
    together_api_key: str = "",
    jina_api_key: str = "",
    voyage_api_key: str = "",
):
    request_dict = body.model_dump(mode="json", exclude_none=True)
    request_dict.pop("rag_params", None)
    request_dict.pop("messages")

    try:
        if body.id.startswith("test"):
            logger.info(f"{body.id} - Generating chat completions.")
        else:
            logger.info(f"{body.id} - Generating chat completions: {body}")
        # assert body.messages[-1].role in (p.ChatRole.USER, "user")

        # --- RAG --- #
        if body.rag_params is None:
            references = None
        else:
            search_query = body.rag_params.search_query

            # Reformulate query if not provided
            if search_query == "":
                rewriter_model = body.model
                rewriter_request_dict = deepcopy(request_dict)
                rewriter_request_dict["temperature"] = 0.01
                rewriter_request_dict["top_p"] = 0.01
                rewriter_request_dict["max_tokens"] = 256

                rewriter_messages = deepcopy(body.messages)
                rewriter_messages[0] = p.ChatEntry.system("You are a concise assistant.")
                query_ori = rewriter_messages[-1].content

                # Search query rewriter
                now = datetime.now(timezone.utc)
                rewriter_messages[-1] = p.ChatEntry.user(
                    (
                        f"QUESTION: `{query_ori}`\n\n"
                        f"Current datetime: {now.isoformat()}\n"
                        "You need to retrieve documents that are relevant to the user by using a search engine. "
                        "Use the information provided to generate one good Google search query sentence in English. "
                        "Do not include any search modifiers or symbols. "
                        "Make sure all relevant keywords are in the sentence. "
                        "Convert any ranges into comma-separated list of items. "
                        "Any date or time in the query should be in numeric format, "
                        f'for example last year is "{now.year - 1}", last 2 years is "{now.year - 1}, {now.year}". '
                        "Reply with only the query. Do not include reasoning, explanations, or notes."
                    )
                )
                completion = await predict(
                    request=request,
                    messages=rewriter_messages,
                    openai_api_key=openai_api_key,
                    anthropic_api_key=anthropic_api_key,
                    gemini_api_key=gemini_api_key,
                    cohere_api_key=cohere_api_key,
                    groq_api_key=groq_api_key,
                    together_api_key=together_api_key,
                    jina_api_key=jina_api_key,
                    voyage_api_key=voyage_api_key,
                    **rewriter_request_dict,
                )
                search_query = completion.text.strip()
                if search_query.startswith('"') and search_query.endswith('"'):
                    search_query = search_query[1:-1]
                logger.info(
                    "{id} - Reformulating user query from `{query_ori}` -> `{query_new}` using {model}",
                    id=body.id,
                    query_ori=query_ori,
                    query_new=search_query,
                    model=rewriter_model,
                )

            # Query
            body.rag_params.search_query = search_query
            logger.info(
                "{id} - Querying DB for `{query}` with params {params}",
                id=body.id,
                query=search_query,
                params=body.rag_params,
            )
            lance_path = (
                f"{config.owl_db_dir}/{request.state.org_id}/{request.state.project_id}/knowledge"
            )
            sqlite_path = f"sqlite:///{lance_path}.db"
            table = KnowledgeTable(sqlite_path, lance_path)
            with table.create_session() as session:
                rows = table.hybrid_search(
                    session,
                    table_id=body.rag_params.table_id,
                    reranking_model=body.rag_params.reranking_model,
                    query=search_query,
                    limit=body.rag_params.k,
                    remove_state_cols=True,
                    openai_api_key=openai_api_key,
                    anthropic_api_key=anthropic_api_key,
                    gemini_api_key=gemini_api_key,
                    cohere_api_key=cohere_api_key,
                    groq_api_key=groq_api_key,
                    together_api_key=together_api_key,
                    jina_api_key=jina_api_key,
                    voyage_api_key=voyage_api_key,
                )
            chunks = [
                p.Chunk(
                    text=row["Text"],
                    title=row["Title"],
                    document_id=row["File ID"],
                    chunk_id=row["ID"],
                )
                for row in rows
            ]
            if body.id.startswith("test"):
                logger.debug(f"{body.id} - Received {len(rows)} from vector query")
            else:
                logger.debug(
                    "{id} - Received response from hybrid query:\n{response}",
                    id=body.id,
                    response=rows,
                )
            references = p.References(chunks=chunks, search_query=search_query)

            # Generate
            # https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain/chains/retrieval_qa/prompt.py
            new_prompt = f"""UP-TO-DATE CONTEXT:\n\n"""
            for chunk in chunks:
                new_prompt += f"""
# Document: {chunk.title}
## Document ID: {chunk.chunk_id}

{chunk.text}

"""
            #             new_prompt += f"""
            # QUESTION:\n{body.messages[-1].content}

            # Answer the question with citation of relevant documents in the form of `\cite{{Document ID}}`.
            # """  # noqa: W605
            new_prompt += f"""
QUESTION:\n{body.messages[-1].content.strip()}

Answer the question.
"""  # noqa: W605
            if not body.id.startswith("test"):
                logger.debug(
                    "{id} - Constructed new user prompt: {prompt}",
                    id=body.id,
                    prompt=new_prompt,
                )
            body.messages[-1] = p.ChatEntry.user(content=new_prompt)

    except Exception:
        logger.exception(f"{body.id} - Failed to preprocess chat completions.")
        raise

    return body, request_dict, references


@router.post("/v1/chat/completions")
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
        body, request_dict, references = await _preprocess_completion(
            request=request,
            body=body,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
        if body.stream:

            async def _generate():
                completion = ""
                content_length = 0
                try:
                    i = 0
                    async for chunk in predict_stream(
                        request=request,
                        messages=body.messages,
                        openai_api_key=openai_api_key,
                        anthropic_api_key=anthropic_api_key,
                        gemini_api_key=gemini_api_key,
                        cohere_api_key=cohere_api_key,
                        groq_api_key=groq_api_key,
                        together_api_key=together_api_key,
                        jina_api_key=jina_api_key,
                        voyage_api_key=voyage_api_key,
                        **request_dict,
                    ):
                        if i == 0 and references is not None:
                            sse = f"data: {references.model_dump_json()}\n\n"
                            content_length += len(sse.encode("utf-8"))
                            yield sse
                        completion += chunk.text
                        sse = f"data: {chunk.model_dump_json()}\n\n"
                        content_length += len(sse.encode("utf-8"))
                        yield sse
                        i += 1
                except ContextOverflowError:
                    logger.warning(f"{body.id} - Chat is too long, returning references only.")
                    if references is not None:
                        references.finish_reason = "context_overflow"
                        sse = f"data: {references.model_dump_json()}\n\n"
                        content_length += len(sse.encode("utf-8"))
                        yield sse
                sse = "data: [DONE]\n\n"
                content_length += len(sse.encode("utf-8"))
                yield sse
                logger.info(f"{body.id} - Streamed completion: {completion}")
                request.state.billing_manager.create_egress_events(content_length / (1024**3))

            response = StreamingResponse(
                content=_generate(),
                status_code=200,
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no"},
            )

        else:
            try:
                response = await predict(
                    request=request,
                    messages=body.messages,
                    openai_api_key=openai_api_key,
                    anthropic_api_key=anthropic_api_key,
                    gemini_api_key=gemini_api_key,
                    cohere_api_key=cohere_api_key,
                    groq_api_key=groq_api_key,
                    together_api_key=together_api_key,
                    jina_api_key=jina_api_key,
                    voyage_api_key=voyage_api_key,
                    **request_dict,
                )
                response.references = references
            except ContextOverflowError:
                logger.warning(
                    f"{request.state.id} - Chat is too long, returning references only."
                )
                response = p.ChatCompletionChunk(
                    id=request.state.id,
                    object="chat.completion",
                    created=int(time()),
                    model=body.model,
                    usage=p.CompletionUsage(),
                    choices=[],
                    references=references,
                )
            else:
                logger.info(f"{request.state.id} - Generated completion: {response.text}")
    except OwlException:
        raise
    except Exception:
        logger.exception(f"{request.state.id} - Chat completion error.")
        raise
    return response
