from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from os.path import join
from time import time
from typing import AsyncGenerator

import litellm
import openai
from fastapi import Request
from litellm import Router
from litellm.router import RetryPolicy
from loguru import logger

from jamaibase.exceptions import (
    BadInputError,
    ContextOverflowError,
    ExternalAuthError,
    JamaiException,
    ResourceNotFoundError,
    ServerBusyError,
    UnexpectedError,
)
from owl.billing import BillingManager
from owl.configs.manager import ENV_CONFIG
from owl.db.gen_table import KnowledgeTable
from owl.models import CloudEmbedder, CloudReranker
from owl.protocol import (
    ChatCompletionChoiceDelta,
    ChatCompletionChoiceOutput,
    ChatCompletionChunk,
    ChatEntry,
    ChatRole,
    Chunk,
    CompletionUsage,
    ExternalKeys,
    LLMModelConfig,
    ModelInfo,
    ModelInfoResponse,
    ModelListConfig,
    RAGParams,
    References,
)
from owl.utils import mask_content, mask_string, select_external_api_key

litellm.drop_params = True
litellm.set_verbose = False
litellm.suppress_debug_info = True


@lru_cache(maxsize=64)
def _get_llm_router(model_json: str, external_api_keys: str):
    models = ModelListConfig.model_validate_json(model_json).llm_models
    ExternalApiKeys = ExternalKeys.model_validate_json(external_api_keys)
    # refer to https://docs.litellm.ai/docs/routing for more details
    return Router(
        model_list=[
            {
                "model_name": m.id,
                "litellm_params": {
                    "model": deployment.litellm_id if deployment.litellm_id.strip() else m.id,
                    "api_key": select_external_api_key(ExternalApiKeys, deployment.provider),
                    "api_base": deployment.api_base if deployment.api_base.strip() else None,
                },
            }
            for m in models
            for deployment in m.deployments
        ],
        routing_strategy="latency-based-routing",
        num_retries=3,
        retry_policy=RetryPolicy(
            TimeoutErrorRetries=3,
            RateLimitErrorRetries=3,
            ContentPolicyViolationErrorRetries=3,
            AuthenticationErrorRetries=0,
            BadRequestErrorRetries=0,
            ContextWindowExceededErrorRetries=0,
        ),
        retry_after=5.0,
        timeout=ENV_CONFIG.owl_llm_timeout_sec,
        allowed_fails=3,
        cooldown_time=5.5,
        debug_level="DEBUG",
        redis_host=ENV_CONFIG.owl_redis_host,
        redis_port=ENV_CONFIG.owl_redis_port,
    )


class LLMEngine:
    def __init__(
        self,
        *,
        request: Request,
    ) -> None:
        self.request = request
        self.id: str = request.state.id
        self.organization_id: str = request.state.org_id
        self.project_id: str = request.state.project_id
        self.org_models: ModelListConfig = request.state.org_models
        self.external_keys: ExternalKeys = request.state.external_keys
        self.is_browser: bool = request.state.user_agent.is_browser
        self._billing: BillingManager = request.state.billing

    @property
    def router(self):
        return _get_llm_router(
            model_json=self.request.state.all_models.model_dump_json(),
            external_api_keys=self.external_keys.model_dump_json(),
        )

    @staticmethod
    def _prepare_hyperparams(model: str, hyperparams: dict, **kwargs) -> dict:
        if isinstance(hyperparams.get("stop", None), list) and len(hyperparams["stop"]) == 0:
            hyperparams["stop"] = None
        hyperparams.update(kwargs)
        if model.startswith("anthropic"):
            hyperparams["extra_headers"] = {"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"}
        return hyperparams

    @staticmethod
    def _prepare_messages(messages: list[ChatEntry | dict]) -> list[ChatEntry]:
        messages: list[ChatEntry] = [ChatEntry.model_validate(m) for m in messages]
        if len(messages) == 0:
            raise ValueError("`messages` is an empty list.")
        elif len(messages) == 1:
            # [user]
            if messages[0].role in (ChatRole.USER.value, ChatRole.USER):
                pass
            # [system]
            elif messages[0].role in (ChatRole.SYSTEM.value, ChatRole.SYSTEM):
                messages.append(ChatEntry.user(content="."))
            # [assistant]
            else:
                messages = [ChatEntry.system(content="."), ChatEntry.user(content=".")] + messages
        else:
            # [user, ...]
            if messages[0].role in (ChatRole.USER.value, ChatRole.USER):
                pass
            # [system, ...]
            elif messages[0].role in (ChatRole.SYSTEM.value, ChatRole.SYSTEM):
                # [system, assistant, ...]
                if messages[1].role in (ChatRole.ASSISTANT.value, ChatRole.ASSISTANT):
                    messages.insert(1, ChatEntry.user(content="."))
            # [assistant, ...]
            else:
                messages = [ChatEntry.system(content="."), ChatEntry.user(content=".")] + messages
        return messages

    def _log_completion_masked(
        self,
        model: str,
        messages: list[ChatEntry],
        **hyperparams,
    ):
        body = dict(
            model=model,
            messages=[
                {"role": m["role"], "content": mask_content(m["content"])} for m in messages
            ],
            **hyperparams,
        )
        logger.info(f"{self.id} - Generating chat completions: {body}")

    def _log_exception(
        self,
        model: str,
        messages: list[ChatEntry],
        api_key: str = "",
        **hyperparams,
    ):
        body = dict(
            model=model,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            api_key=mask_string(api_key),
            **hyperparams,
        )
        logger.exception(f"{self.id} - Chat completion got unexpected error !!! {body}")

    def _map_and_log_exception(
        self,
        e: Exception,
        model: str,
        messages: list[ChatEntry],
        api_key: str = "",
        **hyperparams,
    ) -> Exception:
        request_id = hyperparams.get("id", None)
        err_mssg = getattr(e, "message", str(e))
        log_mssg = f"{request_id} - LiteLLM {e.__class__.__name__}: {err_mssg}"
        if isinstance(e, JamaiException):
            logger.info(log_mssg)
            return e
        elif isinstance(e, openai.BadRequestError):
            logger.info(log_mssg)
            return BadInputError(err_mssg)
        elif isinstance(e, openai.AuthenticationError):
            logger.info(log_mssg)
            return ExternalAuthError(err_mssg)
        elif isinstance(e, (openai.RateLimitError, openai.APITimeoutError)):
            logger.info(log_mssg)
            return ServerBusyError(err_mssg)
        elif isinstance(e, openai.OpenAIError):
            logger.warning(log_mssg)
            return UnexpectedError(err_mssg)
        else:
            self._log_exception(model, messages, api_key, **hyperparams)
            return UnexpectedError(err_mssg)

    def model_info(
        self,
        model: str = "",
        capabilities: list[str] | None = None,
    ) -> ModelInfoResponse:
        model_list: ModelListConfig = self.request.state.all_models
        models = model_list.models
        # Filter by name
        if model != "":
            models = [m for m in models if m.id == model]
        # Filter by capability
        if capabilities is not None:
            for capability in capabilities:
                models = [m for m in models if capability in m.capabilities]
        if len(models) == 0:
            raise ResourceNotFoundError(f"No model found with capabilities: {capabilities}")
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

    def get_model_name(self, model: str, capabilities: list[str] | None = None) -> str:
        capabilities = ["chat"] if capabilities is None else capabilities
        models = self.model_info(
            model="",
            capabilities=capabilities,
        )
        return [m.name for m in models.data if m.id == model][0]

    def validate_model_id(
        self,
        model: str = "",
        capabilities: list[str] | None = None,
    ) -> str:
        capabilities = ["chat"] if capabilities is None else capabilities
        if model == "":
            models: ModelListConfig = self.request.state.all_models
            model = models.get_default_model(capabilities)
            logger.info(f'{self.id} - Empty model changed to "{model}"')
        else:
            models = self.model_info(
                model="",
                capabilities=capabilities,
            )
            model_ids = [m.id for m in models.data]
            if model not in model_ids:
                err_mssg = (
                    f'Model "{model}" is not available among models with capabilities {capabilities}. '
                    f"Choose from: {model_ids}"
                )
                logger.info(f"{self.id} - {err_mssg}")
                # Return different error message depending if request came from browser
                if self.is_browser:
                    model_names = ", ".join(m.name for m in models.data)
                    err_mssg = (
                        f'Model "{model}" is not available among models with capabilities: {', '.join(capabilities)}. '
                        f'Choose from: {model_names}'
                    )
                raise ResourceNotFoundError(err_mssg)
        return model

    async def generate_stream(
        self,
        model: str,
        messages: list[ChatEntry | dict],
        capabilities: list[str] | None = None,
        **hyperparams,
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        api_key = ""
        usage = None
        try:
            model = model.strip()
            # check audio model type
            is_audio_gen_model = False
            if model != "":
                model_config: LLMModelConfig = self.request.state.all_models.get_llm_model_info(
                    model
                )
                if (
                    "audio" in model_config.capabilities
                    and model_config.deployments[0].provider == "openai"
                ):
                    is_audio_gen_model = True
            hyperparams = self._prepare_hyperparams(model, hyperparams, stream=True)
            messages = self._prepare_messages(messages)
            # omit system prompt for audio input with audio gen
            if is_audio_gen_model and messages[0].role in (ChatRole.SYSTEM.value, ChatRole.SYSTEM):
                messages = messages[1:]
            messages = [m.model_dump(mode="json", exclude_none=True) for m in messages]
            model = self.validate_model_id(
                model=model,
                capabilities=capabilities,
            )
            self._log_completion_masked(model, messages, **hyperparams)
            if is_audio_gen_model:
                response = await self.router.acompletion(
                    model=model,
                    modalities=["text", "audio"],
                    audio={"voice": "alloy", "format": "pcm16"},
                    messages=messages,
                    # Fixes discrepancy between stream and non-stream token usage
                    stream_options={"include_usage": True},
                    **hyperparams,
                )
            else:
                response = await self.router.acompletion(
                    model=model,
                    messages=messages,
                    # Fixes discrepancy between stream and non-stream token usage
                    stream_options={"include_usage": True},
                    **hyperparams,
                )
            output_text = ""
            usage = CompletionUsage()
            async for chunk in response:
                if hasattr(chunk, "usage"):
                    usage = CompletionUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )
                yield ChatCompletionChunk(
                    id=self.id,
                    object="chat.completion.chunk",
                    created=int(time()),
                    model=model,
                    usage=usage,
                    choices=[
                        ChatCompletionChoiceDelta(
                            message=ChatEntry.assistant(choice.delta.audio.get("transcript", ""))
                            if is_audio_gen_model and choice.delta.audio is not None
                            else ChatCompletionChoiceOutput.assistant(
                                choice.delta.content,
                                tool_calls=[
                                    tool_call.model_dump() for tool_call in choice.delta.tool_calls
                                ]
                                if isinstance(chunk.choices[0].delta.tool_calls, list)
                                else None,
                            ),
                            index=choice.index,
                            finish_reason=choice.get(
                                "finish_reason", chunk.get("finish_reason", None)
                            ),
                        )
                        for choice in chunk.choices
                    ],
                )
                if is_audio_gen_model and chunk.choices[0].delta.audio is not None:
                    output_text += chunk.choices[0].delta.audio.get("transcript", "")
                else:
                    content = chunk.choices[0].delta.content
                    output_text += content if content else ""
            logger.info(f"{self.id} - Streamed completion: <{mask_string(output_text)}>")

            self._billing.create_llm_events(
                model=model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
            )
        except Exception as e:
            self._map_and_log_exception(e, model, messages, api_key, **hyperparams)
            yield ChatCompletionChunk(
                id=self.id,
                object="chat.completion.chunk",
                created=int(time()),
                model=model,
                usage=usage,
                choices=[
                    ChatCompletionChoiceDelta(
                        message=ChatEntry.assistant(f"[ERROR] {e!r}"),
                        index=0,
                        finish_reason="error",
                    )
                ],
            )

    async def generate(
        self,
        model: str,
        messages: list[ChatEntry | dict],
        capabilities: list[str] | None = None,
        **hyperparams,
    ) -> ChatCompletionChunk:
        api_key = ""
        try:
            model = model.strip()
            # check audio model type
            is_audio_gen_model = False
            if model != "":
                model_config: LLMModelConfig = self.request.state.all_models.get_llm_model_info(
                    model
                )
                if (
                    "audio" in model_config.capabilities
                    and model_config.deployments[0].provider == "openai"
                ):
                    is_audio_gen_model = True
            hyperparams = self._prepare_hyperparams(model, hyperparams, stream=False)
            messages = self._prepare_messages(messages)
            # omit system prompt for audio input with audio gen
            if is_audio_gen_model and messages[0].role in (ChatRole.SYSTEM.value, ChatRole.SYSTEM):
                messages = messages[1:]
            messages = [m.model_dump(mode="json", exclude_none=True) for m in messages]
            model = self.validate_model_id(
                model=model,
                capabilities=capabilities,
            )
            self._log_completion_masked(model, messages, **hyperparams)
            if is_audio_gen_model:
                completion = await self.router.acompletion(
                    model=model,
                    modalities=["text", "audio"],
                    audio={"voice": "alloy", "format": "pcm16"},
                    messages=messages,
                    **hyperparams,
                )
            else:
                completion = await self.router.acompletion(
                    model=model,
                    messages=messages,
                    **hyperparams,
                )
            self._billing.create_llm_events(
                model=model,
                input_tokens=completion.usage.prompt_tokens,
                output_tokens=completion.usage.completion_tokens,
            )
            choices = []
            for choice in completion.choices:
                if is_audio_gen_model and choice.message.audio.transcript is not None:
                    choice.message.content = choice.message.audio.transcript
                choices.append(choice.model_dump())
            completion = ChatCompletionChunk(
                id=self.id,
                object="chat.completion",
                created=completion.created,
                model=model,
                usage=completion.usage.model_dump(),
                choices=choices,
            )
            logger.info(f"{self.id} - Generated completion: <{mask_string(completion.text)}>")
            return completion
        except Exception as e:
            raise self._map_and_log_exception(e, model, messages, api_key, **hyperparams) from e

    async def retrieve_references(
        self,
        model: str,
        messages: list[ChatEntry | dict],
        rag_params: RAGParams | dict | None,
        **hyperparams,
    ) -> tuple[list[ChatEntry], References | None]:
        if rag_params is None:
            return messages, None

        hyperparams = self._prepare_hyperparams(model, hyperparams)
        messages = self._prepare_messages(messages)
        has_file_input = True if isinstance(messages[-1].content, list) else False
        rag_params = RAGParams.model_validate(rag_params)
        search_query = rag_params.search_query
        # Reformulate query if not provided
        if search_query == "":
            hyperparams.update(temperature=0.01, top_p=0.01, max_tokens=512)
            rewriter_messages = deepcopy(messages)
            if rewriter_messages[0].role not in (ChatRole.SYSTEM.value, ChatRole.SYSTEM):
                logger.warning(f"{self.id} - `messages[0].role` is not `system` !!!")
                rewriter_messages.insert(0, ChatEntry.system("You are a concise assistant."))
            if has_file_input:
                query_ori = rewriter_messages[-1].content[0]["text"]
            else:
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
                model=model,
                messages=rewriter_messages,
                **hyperparams,
            )
            search_query = completion.text.strip()
            if search_query.startswith('"') and search_query.endswith('"'):
                search_query = search_query[1:-1]
            logger.info(
                (
                    f'{self.id} - Rewritten query using "{model}": '
                    f"<{mask_string(query_ori)}> -> <{mask_string(search_query)}>"
                )
            )

        # Query
        rag_params.search_query = search_query
        if rag_params.reranking_model is not None:
            reranker = CloudReranker(request=self.request)
        else:
            reranker = None
        embedder = CloudEmbedder(request=self.request)
        logger.info(f"{self.id} - Querying table: {rag_params}")
        lance_path = join(
            ENV_CONFIG.owl_db_dir, self.organization_id, self.project_id, "knowledge"
        )
        sqlite_path = f"sqlite:///{lance_path}.db"
        table = KnowledgeTable(sqlite_path, lance_path)
        with table.create_session() as session:
            rows = await table.hybrid_search(
                session=session,
                table_id=rag_params.table_id,
                embedder=embedder,
                reranker=reranker,
                reranking_model=rag_params.reranking_model,
                query=search_query,
                limit=rag_params.k,
                remove_state_cols=True,
                float_decimals=0,
                vec_decimals=0,
            )
        if len(rows) > 1:
            logger.info(
                (
                    f"{self.id} - Retrieved {len(rows):,d} rows from hybrid search: "
                    f"[{self._mask_retrieved_row(rows[0])}, ..., {self._mask_retrieved_row(rows[-1])}]"
                )
            )
        elif len(rows) == 1:
            logger.info(
                (
                    f"{self.id} - Retrieved 1 row from hybrid search: "
                    f"[{self._mask_retrieved_row(rows[0])}]"
                )
            )
        else:
            logger.warning(f"{self.id} - Failed to retrieve any rows from hybrid search !")
        chunks = [
            Chunk(
                text="" if row["Text"] is None else row["Text"],
                title="" if row["Title"] is None else row["Title"],
                page=row["Page"],
                document_id="" if row["File ID"] is None else row["File ID"],
                chunk_id=row["ID"],
            )
            for row in rows
        ]
        references = References(chunks=chunks, search_query=search_query)

        # Generate
        # https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain/chains/retrieval_qa/prompt.py
        new_prompt = """UP-TO-DATE CONTEXT:\n\n"""
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
QUESTION:\n{messages[-1].content[0]["text"].strip() if has_file_input else messages[-1].content.strip()}

Answer the question.
"""  # noqa: W605
        logger.debug(
            "{id} - Constructed new user prompt: {prompt}",
            id=self.id,
            prompt=new_prompt,
        )
        if has_file_input:
            new_content = [{"type": "text", "text": new_prompt}, messages[-1].content[1]]
        else:
            new_content = new_prompt
        messages[-1] = ChatEntry.user(content=new_content)
        return messages, references

    @staticmethod
    def _mask_retrieved_row(row: dict[str, str | None]):
        return {
            "ID": row["ID"],
            "File ID": row["File ID"],
            "Title": mask_string(row["Title"]),
            "Text": mask_string(row["Text"]),
            "Page": str(row["Page"]),
        }

    async def rag_stream(
        self,
        model: str,
        messages: list[ChatEntry | dict],
        rag_params: RAGParams | None = None,
        **hyperparams,
    ) -> AsyncGenerator[References | ChatCompletionChunk, None]:
        try:
            hyperparams = self._prepare_hyperparams(model, hyperparams)
            messages, references = await self.retrieve_references(
                model=model,
                messages=messages,
                rag_params=rag_params,
                **hyperparams,
            )
            if references is not None:
                yield references
            async for chunk in self.generate_stream(
                model=model,
                messages=messages,
                **hyperparams,
            ):
                yield chunk
        except Exception as e:
            self._log_exception(model, messages, **hyperparams)
            yield ChatCompletionChunk(
                id=self.id,
                object="chat.completion.chunk",
                created=int(time()),
                model=model,
                usage=None,
                choices=[
                    ChatCompletionChoiceDelta(
                        message=ChatEntry.assistant(f"[ERROR] {e!r}"),
                        index=0,
                        finish_reason="error",
                    )
                ],
            )

    async def rag(
        self,
        model: str,
        messages: list[ChatEntry | dict],
        capabilities: list[str] | None = None,
        rag_params: RAGParams | dict | None = None,
        **hyperparams,
    ) -> ChatCompletionChunk:
        hyperparams = self._prepare_hyperparams(model, hyperparams)
        messages, references = await self.retrieve_references(
            model=model,
            messages=messages,
            rag_params=rag_params,
            **hyperparams,
        )
        try:
            response = await self.generate(
                model=model,
                messages=messages,
                capabilities=capabilities,
                **hyperparams,
            )
            response.references = references
        except ContextOverflowError:
            logger.warning(f"{self.id} - Chat is too long, returning references only.")
            response = ChatCompletionChunk(
                id=self.id,
                object="chat.completion",
                created=int(time()),
                model=model,
                usage=None,
                choices=[],
                references=references,
            )
        return response
