from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from time import time
from typing import AsyncGenerator

import litellm
import openai
import tiktoken
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from litellm import Router
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from jamaibase.protocol import (
    DEFAULT_CHAT_MODEL,
    ChatCompletionChoiceDelta,
    ChatCompletionChunk,
    ChatEntry,
    ChatRole,
    Chunk,
    CompletionUsage,
    ModelInfo,
    ModelInfoResponse,
    ModelListConfig,
    RAGParams,
    References,
)
from owl.config import get_model_json
from owl.db.gen_table import KnowledgeTable
from owl.utils import filter_external_api_key, mask_string
from owl.utils.exceptions import ContextOverflowError, ResourceNotFoundError


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    owl_db_dir: str = "db"


CONFIG = Config()
litellm.drop_params = True
litellm.set_verbose = False


@lru_cache(maxsize=1)
def _get_llm_router(model_json: str):
    models = ModelListConfig.model_validate_json(model_json).llm_models
    # refer to https://docs.litellm.ai/docs/routing for more details
    # current fixed strategy to 'simple-shuffle' (no need extra redis, or setting of RPM/TPM)
    return Router(
        model_list=[
            {
                "model_name": m.id,
                "litellm_params": {
                    "model": m.litellm_id if m.litellm_id != "" else m.id,
                    "api_key": "null",
                    "api_base": None if m.api_base == "" else m.api_base,
                },
            }
            for m in models
        ],
        routing_strategy="simple-shuffle",
    )


def message_len(messages: list[ChatEntry]) -> int:
    try:
        openai_tokenizer = tiktoken.encoding_for_model("gpt-4")
    except KeyError:
        openai_tokenizer = tiktoken.get_encoding("cl100k_base")
    total_len = 0
    for message in messages:
        mlen = 5  # ChatML = 4, role = 1
        if message.content:
            mlen += len(openai_tokenizer.encode(message.content))
        if message.name:
            mlen += len(openai_tokenizer.encode(message.name))
        # if message.function_call:
        #     mlen += len(openai_tokenizer.encode(message.function_call.name))
        #     mlen += len(openai_tokenizer.encode(message.function_call.arguments))
        total_len += mlen
    return total_len


class LLMEngine:
    def __init__(
        self,
        openai_api_key: str = "",
        anthropic_api_key: str = "",
        gemini_api_key: str = "",
        cohere_api_key: str = "",
        groq_api_key: str = "",
        together_api_key: str = "",
        jina_api_key: str = "",
        voyage_api_key: str = "",
    ) -> None:
        self.openai_api_key = openai_api_key
        self.anthropic_api_key = anthropic_api_key
        self.gemini_api_key = gemini_api_key
        self.cohere_api_key = cohere_api_key
        self.groq_api_key = groq_api_key
        self.together_api_key = together_api_key
        self.jina_api_key = jina_api_key
        self.voyage_api_key = voyage_api_key

    @property
    def router(self):
        return _get_llm_router(get_model_json())

    @staticmethod
    def _prepare_messages(messages: list[ChatEntry | dict]):
        messages = [ChatEntry.model_validate(m) for m in messages]
        if messages[0].role in (ChatRole.SYSTEM.value, ChatRole.SYSTEM):
            if messages[1].role in (ChatRole.ASSISTANT.value, ChatRole.ASSISTANT):
                messages.insert(1, ChatEntry.user(content="."))
        elif messages[0].role in (ChatRole.ASSISTANT.value, ChatRole.ASSISTANT):
            messages.insert(0, ChatEntry.user(content="."))
        return messages

    @staticmethod
    def _log_completion(
        request: Request,
        model: str,
        messages: list[ChatEntry],
        **hyperparams,
    ):
        body = dict(
            model=model,
            messages=[{"role": m.role, "content": mask_string(m.content)} for m in messages],
            **hyperparams,
        )
        logger.info(f"{request.state.id} - Generating chat completions: {body}")

    def model_info(
        self,
        model: str = "",
        capabilities: list[str] | None = None,
    ) -> ModelInfoResponse:
        all_models = ModelListConfig.model_validate_json(get_model_json())
        # Chat models
        models = [m for m in all_models.llm_models if m.owned_by == "ellm"]
        if self.openai_api_key != "":
            models += [m for m in all_models.llm_models if m.owned_by == "openai"]
        if self.anthropic_api_key != "":
            models += [m for m in all_models.llm_models if m.owned_by == "anthropic"]
        if self.together_api_key != "":
            models += [m for m in all_models.llm_models if m.owned_by == "together_ai"]
        # Embedding models
        models += [m for m in all_models.embed_models if m.owned_by == "ellm"]
        if self.openai_api_key != "":
            models += [m for m in all_models.embed_models if m.owned_by == "openai"]
        if self.cohere_api_key != "":
            models += [m for m in all_models.embed_models if m.owned_by == "cohere"]
        # Reranking models
        models += [m for m in all_models.rerank_models if m.owned_by == "ellm"]
        if self.cohere_api_key != "":
            models += [m for m in all_models.rerank_models if m.owned_by == "cohere"]
        # Get unique models
        unique_models = {m.id: m for m in models}
        models = list(unique_models.values())
        # Filter by name
        if model != "":
            models = [m for m in models if m.id == model]
        # Filter by capability
        if capabilities is not None:
            for capability in capabilities:
                models = [m for m in models if capability in m.capabilities]
        if len(models) == 0:
            raise ResourceNotFoundError(
                f"No suitable model found with capabilities: {capabilities}"
            )
        response = ModelInfoResponse(
            data=[ModelInfo.model_validate(m.model_dump()) for m in models]
        )
        return response

    def model_names(
        self,
        prefer: str = "",
        capabilities: list[str] | None = None,
    ) -> list[str]:
        models = self.model_info(
            model="",
            capabilities=capabilities,
        )
        names = [m.id for m in models.data]
        if prefer in names:
            names.remove(prefer)
            names.insert(0, prefer)
        return names

    async def generate_stream(
        self,
        request: Request,
        model: str,
        messages: list[ChatEntry | dict],
        **hyperparams,
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        messages = self._prepare_messages(messages)
        self._log_completion(request, model, messages, **hyperparams)
        try:
            hyperparams.pop("stream", False)
            input_len = message_len(messages)
            messages = [m.model_dump(mode="json", exclude_none=True) for m in messages]

            output_len = 0

            if len(model) == 0:
                models = self.model_names(
                    prefer=DEFAULT_CHAT_MODEL,
                    capabilities=["chat"],
                )
                model = models[0]
            api_key = filter_external_api_key(
                model,
                openai_api_key=self.openai_api_key,
                anthropic_api_key=self.anthropic_api_key,
                gemini_api_key=self.gemini_api_key,
                cohere_api_key=self.cohere_api_key,
                groq_api_key=self.groq_api_key,
                together_api_key=self.together_api_key,
                jina_api_key=self.jina_api_key,
                voyage_api_key=self.voyage_api_key,
            )
            response = await self.router.acompletion(
                model=model,
                messages=messages,
                api_key=api_key,
                stream=True,
                **hyperparams,
            )
            output_text = ""
            async for chunk in response:
                chunk_message = chunk.choices[0].delta
                if not chunk_message.content:
                    continue
                output_len += 1
                yield ChatCompletionChunk(
                    id=request.state.id,
                    object="chat.completion.chunk",
                    created=int(time()),
                    model=model,
                    usage=CompletionUsage(
                        prompt_tokens=input_len,
                        completion_tokens=output_len,
                        total_tokens=input_len + output_len,
                    ),
                    choices=[
                        ChatCompletionChoiceDelta(
                            message=ChatEntry.assistant(choice.delta.content),
                            index=choice.index,
                            finish_reason=choice.get(
                                "finish_reason", chunk.get("finish_reason", None)
                            ),
                        )
                        for choice in chunk.choices
                    ],
                )
                output_text += chunk.choices[0].delta.content
            logger.info(f"{request.state.id} - Streamed completion: <{mask_string(output_text)}>")
            request.state.billing_manager.create_llm_events(
                model=model,
                input_tokens=input_len,
                output_tokens=output_len,
            )
        except Exception as exc:
            yield ChatCompletionChunk(
                id=request.state.id,
                object="chat.completion.chunk",
                created=int(time()),
                model=model,
                usage=None,
                choices=[
                    ChatCompletionChoiceDelta(
                        message=ChatEntry.assistant(f"[ERROR] {exc}"),
                        index=0,
                        finish_reason="error",
                    )
                ],
            )

    async def generate(
        self,
        request: Request,
        model: str,
        messages: list[ChatEntry | dict],
        **hyperparams,
    ) -> ChatCompletionChunk:
        messages = self._prepare_messages(messages)
        self._log_completion(request, model, messages, **hyperparams)
        hyperparams.pop("stream", False)
        messages = [m.model_dump(mode="json", exclude_none=True) for m in messages]
        try:
            if len(model) == 0:
                models = self.model_names(
                    prefer=DEFAULT_CHAT_MODEL,
                    capabilities=["chat"],
                )
                model = models[0]
            api_key = filter_external_api_key(
                model,
                openai_api_key=self.openai_api_key,
                anthropic_api_key=self.anthropic_api_key,
                gemini_api_key=self.gemini_api_key,
                cohere_api_key=self.cohere_api_key,
                groq_api_key=self.groq_api_key,
                together_api_key=self.together_api_key,
                jina_api_key=self.jina_api_key,
                voyage_api_key=self.voyage_api_key,
            )
            response = await self.router.acompletion(
                model=model,
                messages=messages,
                api_key=api_key,
                stream=False,
                **hyperparams,
            )
            usage = response.usage.model_dump()
            completion = ChatCompletionChunk(
                id=request.state.id,
                object="chat.completion",
                created=response.created,
                model=model,
                usage=usage,
                choices=[choice.model_dump() for choice in response.choices],
            )
            input_len = usage.get("prompt_tokens", 0)
            output_len = usage.get("completion_tokens", 0)
            if input_len == 0 or output_len == 0:
                logger.warning(f"LiteLLM '{model}' completion usage: {usage}")
            logger.info(
                f"{request.state.id} - Generated completion: <{mask_string(completion.text)}>"
            )
            request.state.billing_manager.create_llm_events(
                model=model,
                input_tokens=input_len,
                output_tokens=output_len,
            )
            return completion

        except litellm.exceptions.ContextWindowExceededError:
            logger.info(f"{request.state.id} - Context overflow for model: {model}")
            raise ContextOverflowError(f"Context overflow for model: {model}")

        except openai.BadRequestError as e:
            err_mssg = e.message
            err_code = e.code if e.code else None

            logger.warning(f"{request.state.id} - LiteLLM error: {err_mssg}")
            if e.status_code == 400:
                raise RequestValidationError(
                    errors=[
                        {
                            "msg": err_mssg,
                            "model": model,
                            "code": err_code,
                        }
                    ]
                )
            else:
                raise RuntimeError(
                    f"LLM server error: model={model}  code={err_code}  error={err_mssg}"
                )

    async def retrieve_references(
        self,
        request: Request,
        model: str,
        messages: list[ChatEntry | dict],
        rag_params: RAGParams | dict | None,
        **hyperparams,
    ) -> tuple[list[ChatEntry], References | None]:
        if rag_params is None:
            return messages, None

        messages = self._prepare_messages(messages)
        rag_params = RAGParams.model_validate(rag_params)
        search_query = rag_params.search_query
        # Reformulate query if not provided
        if search_query == "":
            hyperparams.update(temperature=0.01, top_p=0.01, max_tokens=512)
            rewriter_messages = deepcopy(messages)
            rewriter_messages[0] = ChatEntry.system("You are a concise assistant.")
            query_ori = rewriter_messages[-1].content

            # Search query rewriter
            now = datetime.now(timezone.utc)
            rewriter_messages[-1] = ChatEntry.user(
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
            completion = await self.generate(
                request=request,
                model=model,
                messages=rewriter_messages,
                **hyperparams,
            )
            search_query = completion.text.strip()
            if search_query.startswith('"') and search_query.endswith('"'):
                search_query = search_query[1:-1]
            logger.info(
                f"{request.state.id} - Rewritten query: `{query_ori}` -> `{search_query}` using {model}"
            )

        # Query
        rag_params.search_query = search_query
        logger.info(f"{request.state.id} - Querying table: {rag_params}")
        lance_path = (
            f"{CONFIG.owl_db_dir}/{request.state.org_id}/{request.state.project_id}/knowledge"
        )
        sqlite_path = f"sqlite:///{lance_path}.db"
        table = KnowledgeTable(sqlite_path, lance_path)
        with table.create_session() as session:
            rows = table.hybrid_search(
                session,
                table_id=rag_params.table_id,
                reranking_model=rag_params.reranking_model,
                query=search_query,
                limit=rag_params.k,
                remove_state_cols=True,
                openai_api_key=self.openai_api_key,
                anthropic_api_key=self.anthropic_api_key,
                gemini_api_key=self.gemini_api_key,
                cohere_api_key=self.cohere_api_key,
                groq_api_key=self.groq_api_key,
                together_api_key=self.together_api_key,
                jina_api_key=self.jina_api_key,
                voyage_api_key=self.voyage_api_key,
            )
        if len(rows) > 1:
            logger.info(
                (
                    f"{request.state.id} - Retrieved {len(rows):,d} rows from hybrid search: "
                    f"[{self._mask_retrieved_row(rows[0])}, ..., {self._mask_retrieved_row(rows[-1])}]"
                )
            )
        elif len(rows) == 1:
            logger.info(
                (
                    f"{request.state.id} - Retrieved 1 row from hybrid search: "
                    f"[{self._mask_retrieved_row(rows[0])}]"
                )
            )
        else:
            logger.warning(
                f"{request.state.id} - Failed to retrieve any rows from hybrid search !"
            )
        chunks = [
            Chunk(
                text="" if row["Text"] is None else row["Text"],
                title="" if row["Title"] is None else row["Title"],
                document_id="" if row["File ID"] is None else row["File ID"],
                chunk_id=row["ID"],
            )
            for row in rows
        ]
        references = References(chunks=chunks, search_query=search_query)

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
QUESTION:\n{messages[-1].content.strip()}

Answer the question.
"""  # noqa: W605
        logger.debug(
            "{id} - Constructed new user prompt: {prompt}",
            id=request.state.id,
            prompt=new_prompt,
        )
        messages[-1] = ChatEntry.user(content=new_prompt)
        return messages, references

    @staticmethod
    def _mask_retrieved_row(row: dict[str, str | None]):
        return {
            "ID": row["ID"],
            "File ID": row["File ID"],
            "Title": mask_string(row["Title"]),
            "Text": mask_string(row["Text"]),
        }

    async def rag_stream(
        self,
        request: Request,
        model: str,
        messages: list[ChatEntry | dict],
        rag_params: RAGParams | None = None,
        **hyperparams,
    ) -> AsyncGenerator[References | ChatCompletionChunk, None]:
        messages, references = await self.retrieve_references(
            request=request,
            model=model,
            messages=messages,
            rag_params=rag_params,
            **hyperparams,
        )
        if references is not None:
            yield references
        async for chunk in self.generate_stream(
            request=request,
            model=model,
            messages=messages,
            **hyperparams,
        ):
            yield chunk

    async def rag(
        self,
        request: Request,
        model: str,
        messages: list[ChatEntry | dict],
        rag_params: RAGParams | dict | None = None,
        **hyperparams,
    ) -> ChatCompletionChunk:
        messages, references = await self.retrieve_references(
            request=request,
            model=model,
            messages=messages,
            rag_params=rag_params,
            **hyperparams,
        )
        try:
            response = await self.generate(
                request=request,
                model=model,
                messages=messages,
                **hyperparams,
            )
            response.references = references
        except ContextOverflowError:
            logger.warning(f"{request.state.id} - Chat is too long, returning references only.")
            response = ChatCompletionChunk(
                id=request.state.id,
                object="chat.completion",
                created=int(time()),
                model=model,
                usage=None,
                choices=[],
                references=references,
            )
        return response
