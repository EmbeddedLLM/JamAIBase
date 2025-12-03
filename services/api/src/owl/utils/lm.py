import asyncio
import itertools
import random
from base64 import b64encode
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
from textwrap import dedent
from time import perf_counter, time
from typing import Any, AsyncGenerator

import httpx
import litellm
import numpy as np
import openai
from fastapi import Request
from litellm import acompletion, aembedding, arerank
from litellm.llms.base_llm.chat.transformation import BaseLLMException
from litellm.types.rerank import RerankResponse
from litellm.types.utils import (
    Choices,
    Delta,
    Message,
    ModelResponse,
    ModelResponseStream,
    StreamingChoices,
    Usage,
)
from litellm.types.utils import (
    EmbeddingResponse as LiteLLMEmbeddingResponse,
)
from loguru import logger
from natsort import natsorted
from openai import AsyncOpenAI
from openai.types.responses import (
    Response,
    ResponseCodeInterpreterToolCall,
    ResponseCompletedEvent,
    ResponseFunctionWebSearch,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseReasoningItem,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseTextDeltaEvent,
)
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from jamaibase.types.common import SanitisedStr
from owl.configs import CACHE, ENV_CONFIG
from owl.db import SCHEMA, async_session, cached_text
from owl.db.models import Deployment, ModelConfig
from owl.types import (
    AudioContent,
    ChatCompletionChunkResponse,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatEntry,
    ChatRole,
    CloudProvider,
    CodeInterpreterTool,
    CompletionUsageDetails,
    Deployment_,
    EmbeddingResponse,
    EmbeddingResponseData,
    EmbeddingUsage,
    ImageContent,
    ModelCapability,
    ModelConfig_,
    ModelConfigRead,
    ModelProvider,
    ModelType,
    OnPremProvider,
    OrganizationRead,
    Project_,
    PromptUsageDetails,
    RAGParams,
    References,
    RerankingResponse,
    RerankingUsage,
    TextContent,
    ToolUsageDetails,
    WebSearchTool,
)
from owl.utils import mask_content, mask_string
from owl.utils.billing import BillingManager
from owl.utils.dates import now
from owl.utils.exceptions import (
    BadInputError,
    ExternalAuthError,
    JamaiException,
    ModelCapabilityError,
    ModelOverloadError,
    RateLimitExceedError,
    ResourceNotFoundError,
    UnavailableError,
    UnexpectedError,
)

litellm.drop_params = True
litellm.set_verbose = False
litellm.suppress_debug_info = True

WEB_SEARCH_TOOL = WebSearchTool()
CODE_INTERPRETER_TOOL = CodeInterpreterTool()
OPENAI_HOSTED_TOOLS = (WEB_SEARCH_TOOL.type, CODE_INTERPRETER_TOOL.type)


class _Logger:
    @staticmethod
    def log(
        log_level: int,
        message: str,
        **kwargs,
    ):
        logger.bind(**kwargs).log(log_level, message)


@dataclass(slots=True)
class DeploymentContext:
    deployment: Deployment
    api_key: str
    routing_id: str
    inference_provider: str
    is_reasoning_model: bool
    use_openai_responses: bool = False


class DeploymentRouter:
    def __init__(
        self,
        *,
        request: Request,
        config: ModelConfigRead,
        organization: OrganizationRead,
        cooldown: float = 0.0,  # No cooldown by default
        is_browser: bool = False,
    ) -> None:
        self.request = request
        self.id: str = request.state.id
        if not isinstance(config, ModelConfigRead):
            raise TypeError(f"Expected ModelConfigRead, got {type(config)}.")
        self.config = config
        if not isinstance(organization, OrganizationRead):
            raise TypeError(f"Expected OrganizationRead, got {type(organization)}.")
        self.organization = organization
        self.cooldown = cooldown
        self.is_browser = is_browser
        self.retry_policy = dict(
            retry=retry_if_exception_type((RateLimitExceedError, ModelOverloadError)),
            wait=wait_exponential_jitter(initial=0.5, exp_base=1.2, max=5, jitter=0.5),
            stop=stop_after_attempt(3),
            reraise=True,
            before_sleep=before_sleep_log(_Logger(), "WARNING"),
        )
        self._model_display_id = self.config.name if is_browser else self.config.id

    @staticmethod
    def batch(seq, n):
        if n < 1:
            raise ValueError("`n` must be > 0")
        for i in range(0, len(seq), n):
            yield seq[i : i + n]

    def _inference_provider(self, provider: str) -> str:
        if provider == CloudProvider.ELLM:
            return CloudProvider.ELLM
        if provider in ModelProvider:
            return ModelProvider(provider)
        if provider in OnPremProvider:
            return OnPremProvider(provider)
        owned_by = self.config.owned_by or ""
        return next((p for p in ModelProvider if owned_by.lower() == p.value.lower()), "")

    def _litellm_model_id(self, deployment: Deployment_):
        """
        Chat and embedding:
        - Known cloud providers: provider/model
        - Unknown cloud providers and on-prem: openai/model

        Reranking:
        - Known cloud providers and on-prem: provider/model
        - Unknown cloud providers: cohere/model
        """
        provider = deployment.provider
        routing_id = self.config.id if deployment.routing_id == "" else deployment.routing_id
        if provider in CloudProvider and provider not in (
            CloudProvider.INFINITY_CLOUD,
            CloudProvider.ELLM,
        ):
            # Standard cloud providers
            prefix = "hosted_vllm" if provider == CloudProvider.VLLM_CLOUD else provider
            return routing_id if routing_id.startswith(f"{prefix}/") else f"{prefix}/{routing_id}"
        if self.config.type != ModelType.RERANK:
            # Non-standard providers including ELLM
            prefix = "openai"
        else:
            # Reranking
            if provider in (
                CloudProvider.INFINITY_CLOUD,
                CloudProvider.ELLM,
            ):
                prefix = "infinity"
            elif provider in OnPremProvider:
                prefix = provider.split("_")[0]  # infinity_cpu -> infinity
            else:
                prefix = "cohere"
        return f"{prefix}/{routing_id}"

    def _log_completion_masked(
        self,
        messages: list[dict],
        **hyperparams,
    ):
        body = dict(
            model=self.config.id,
            messages=[mask_content(m) for m in messages],
            **hyperparams,
        )
        logger.info(f"{self.id} - Generating chat completions: {body}")

    def _map_and_log_exception(
        self,
        e: Exception,
        deployment: Deployment_,
        api_key: str,
        *,
        messages: list[dict] | None = None,
        **hyperparams,
    ) -> Exception:
        messages = [mask_content(m) for m in messages] if messages else None
        err_mssg = getattr(e, "message", str(e))
        if isinstance(e, JamaiException):
            return e
        elif isinstance(e, openai.BadRequestError):
            logger.info(
                (
                    f'{self.id} - LLM request to model "{self.config.id}" failed due to bad request. '
                    f"Hyperparameters: {hyperparams}  Messages: {messages}"
                )
            )
            return BadInputError(err_mssg)
        elif isinstance(e, openai.AuthenticationError):
            return ExternalAuthError(f"Invalid API key: {mask_string(api_key)}")

        logger.warning(
            (
                f'{self.id} - LLM request to model "{self.config.id}" failed. '
                f"Exception: {e.__class__}: {err_mssg}\n"
                f"Deployment: {deployment}"
            )
        )
        if isinstance(e, openai.RateLimitError):
            _header = e.response.headers
            limit = int(_header.get("X-RateLimit-Limit", 0))
            remaining = int(_header.get("X-RateLimit-Remaining", 0))
            reset_at = int(_header.get("X-RateLimit-Reset", time() + 30))
            mapped_e = RateLimitExceedError(
                err_mssg,
                limit=limit,
                remaining=remaining,
                reset_at=reset_at,
                used=int(_header.get("X-RateLimit-Used", limit - remaining)),
                retry_after=int(_header.get("Retry-After", int(reset_at - time()) + 1)),
                meta=None,
            )
        elif isinstance(
            e,
            (
                openai.APITimeoutError,
                openai.APIError,
                httpx.HTTPStatusError,
                httpx.TimeoutException,  # ReadTimeout, ConnectTimeout, etc
            ),
        ):
            mapped_e = ModelOverloadError(
                f'Model provider for "{self._model_display_id}" is overloaded. Please try again later.'
            )
        elif isinstance(e, (BaseLLMException, openai.OpenAIError)):
            mapped_e = BadInputError(err_mssg)
        else:
            body = dict(
                model=self.config.id,
                api_key=mask_string(api_key),
                messages=messages,
                **hyperparams,
            )
            logger.exception(
                f"{self.id} - {self.__class__.__name__} -  Unexpected error !!! {body}"
            )
            mapped_e = UnexpectedError(err_mssg)
        logger.warning(
            f"{self.id} - LLM request failed. Mapped exception: {mapped_e.__class__}: {str(mapped_e)}"
        )
        return mapped_e

    async def _cooldown_deployment(self, deployment: Deployment_, cooldown_time: timedelta):
        if cooldown_time.total_seconds() <= 0:
            logger.warning(
                f"{self.id} - Cooldown time is zero or negative for deployment {deployment.id}. Skipping cooldown."
            )
            return
        cooldown_until = now() + cooldown_time
        logger.warning(
            (
                f'{self.id} - Cooling down deployment "{deployment.id}" '
                f"until {cooldown_until} ({cooldown_time.total_seconds()} seconds)."
            )
        )
        try:
            async with async_session() as session:
                await session.exec(
                    cached_text(
                        f'UPDATE {SCHEMA}."Deployment" SET cooldown_until = :cooldown_until WHERE id = :deployment_id;'
                    ),
                    params={
                        "cooldown_until": cooldown_until,
                        "deployment_id": deployment.id,
                    },
                )
                await session.commit()
        except Exception as exc:
            logger.warning(f"{self.id} - Failed to cooldown deployment: {repr(exc)}")

    @asynccontextmanager
    async def _get_deployment(
        self,
        **hyperparams,
    ) -> AsyncGenerator[DeploymentContext, None]:
        name = self.config.name
        # Get deployment
        if len(self.config.deployments) == 0:
            logger.warning(
                f"{self.id} - No deployments attached to model config. Fetching from database."
            )
            async with async_session() as session:
                deployments = (
                    await Deployment.list_(
                        session=session,
                        return_type=Deployment_,
                        filters=dict(model_id=self.config.id),
                    )
                ).items
            if len(deployments) == 0:
                raise UnavailableError(f'No deployments found for model "{name}".')
        else:
            deployments = self.config.deployments
        deployments = [d for d in deployments if d.cooldown_until <= now()]
        if len(deployments) == 0:
            raise UnavailableError(f'All deployments are on cooldown for model "{name}".')
        deployment = random.choices(deployments, weights=[d.weight for d in deployments], k=1)[0]
        # Get API key
        provider = deployment.provider.lower()
        api_key = ""
        if self.organization.id == "0" or (
            ENV_CONFIG.enable_byok and provider not in OnPremProvider
        ):
            # Use Organization keys
            api_key = self.organization.get_external_key(provider)
        if (not api_key) and self.organization.id != "0":
            # Use TSP keys
            async with async_session() as session:
                tsp_org = await CACHE.get_organization_async("0", session)
                api_key = "" if tsp_org is None else tsp_org.get_external_key(provider)
        if not api_key:
            # Use System keys
            api_key = ENV_CONFIG.get_api_key(provider)
        if not api_key:
            api_key = "DUMMY_KEY"
        # Get model routing ID
        routing_id = self._litellm_model_id(deployment)
        # Check if its a reasoning model
        can_reason = ModelCapability.REASONING in self.config.capabilities
        is_reasoning_model = can_reason or litellm.supports_reasoning(routing_id)
        if is_reasoning_model and not can_reason:
            logger.warning(
                f'Model "{self.config.id}" by provider "{provider}" seems to support reasoning, but it is not labelled as such.'
            )
        try:
            logger.info(
                f'Request started for model "{self.config.id}" ({provider=}, {routing_id=}, {self.id}).'
            )
            t0 = perf_counter()
            self.request.state.model_start_time = t0
            yield DeploymentContext(
                deployment=deployment,
                api_key=api_key,
                routing_id=routing_id,
                inference_provider=self._inference_provider(provider),
                is_reasoning_model=is_reasoning_model,
            )
            self.request.state.timing["external_call"] = perf_counter() - t0
            logger.info(
                f'Request completed for model "{self.config.id}" ({provider=}, {routing_id=}, {self.id}).'
            )
        except Exception as e:
            mapped_e = self._map_and_log_exception(e, deployment, api_key, **hyperparams)
            if isinstance(mapped_e, (ModelOverloadError, RateLimitExceedError)):
                # Cooldown deployment
                if len(deployments) > 1:
                    cooldown_time = timedelta(
                        seconds=getattr(mapped_e, "retry_after", self.cooldown)
                    )
                    await self._cooldown_deployment(deployment, cooldown_time)
            raise mapped_e from e

    ### --- Chat Completion --- ###

    async def _prepare_chat(
        self,
        *,
        messages: list[ChatEntry],
        hyperparams,
        **kwargs,
    ) -> tuple[list[dict[str, Any]], dict]:
        # Prepare messages
        if len(messages) == 0:
            raise ValueError("`messages` is an empty list.")
        elif len(messages) == 1:
            # [user]
            if messages[0].role == ChatRole.USER:
                pass
            # [system]
            elif messages[0].role == ChatRole.SYSTEM:
                messages.append(ChatEntry.user(content="."))
            # [assistant]
            else:
                messages = [
                    ChatEntry.system(content="."),
                    ChatEntry.user(content="."),
                ] + messages
        else:
            # [user, ...]
            if messages[0].role == ChatRole.USER:
                pass
            # [system, ...]
            elif messages[0].role == ChatRole.SYSTEM:
                # [system, assistant, ...]
                if messages[1].role == ChatRole.ASSISTANT:
                    messages.insert(1, ChatEntry.user(content="."))
            # [assistant, ...]
            else:
                messages = [
                    ChatEntry.system(content="."),
                    ChatEntry.user(content="."),
                ] + messages
        if messages[0].role == ChatRole.SYSTEM and messages[0].content == "":
            messages[0].content = "."
        messages = [m.model_dump(mode="json", exclude_none=True) for m in messages]
        # Prepare hyperparams
        if isinstance(hyperparams.get("stop", None), list) and len(hyperparams["stop"]) == 0:
            hyperparams["stop"] = None
        hyperparams.update(kwargs)
        # if self.config.id.startswith("anthropic"):
        #     hyperparams["extra_headers"] = {"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"}
        # Log
        # self._log_completion_masked(messages, **hyperparams)
        return messages, hyperparams

    def _prepare_hyperparams(
        self,
        ctx: DeploymentContext,
        hyperparams: dict[str, Any],
    ):
        # Handle max_tokens
        max_tokens = hyperparams.pop("max_tokens", None)
        max_completion_tokens = hyperparams.pop("max_completion_tokens", None)
        hyperparams["max_tokens"] = max_completion_tokens or max_tokens
        tools: list[dict] = hyperparams.pop("tools", None) or []
        # OpenAI specific
        if ctx.inference_provider == CloudProvider.OPENAI:
            if ctx.is_reasoning_model or any(
                t.get("type", "") in OPENAI_HOSTED_TOOLS for t in tools
            ):
                ctx.use_openai_responses = True
                if ctx.is_reasoning_model:
                    hyperparams.pop("temperature", None)
                    hyperparams.pop("top_p", None)
                hyperparams["max_output_tokens"] = hyperparams.pop("max_tokens", None)
                hyperparams.pop("id", None)
                hyperparams.pop("n", None)
                hyperparams.pop("presence_penalty", None)
                hyperparams.pop("frequency_penalty", None)
                hyperparams.pop("logit_bias", None)
                hyperparams.pop("stop", None)
            else:
                hyperparams["max_completion_tokens"] = hyperparams.pop("max_tokens", None)
        elif ctx.inference_provider == CloudProvider.ELLM:
            pass
        else:
            tools = [t for t in tools if t.get("type", "") not in OPENAI_HOSTED_TOOLS]

        # Anthropic specific
        if ctx.inference_provider == CloudProvider.ANTHROPIC:
            # Sonnet 4.5 cannot specify both `temperature` and `top_p`
            if "sonnet-4-5" in ctx.routing_id:
                t = hyperparams.get("temperature", None)
                p = hyperparams.get("top_p", None)
                if t is not None and p is not None:
                    hyperparams.pop("top_p", None)  # Prioritise temperature

        if tools:
            hyperparams["tools"] = tools

        # Handle reasoning params
        reasoning_effort: str | None = hyperparams.pop("reasoning_effort", None)
        thinking_budget: int | None = hyperparams.pop("thinking_budget", None)
        reasoning_summary: str = hyperparams.pop("reasoning_summary", "auto")
        if thinking_budget is not None:
            thinking_budget = max(thinking_budget, 0)
        # Non-reasoning model does not require further processing
        if not ctx.is_reasoning_model:
            return
        # Disable reasoning if requested
        if (
            reasoning_effort in ("disable", "minimal", "none")
            or thinking_budget == 0
            or (reasoning_effort is None and thinking_budget is None)
        ):
            if ctx.inference_provider == CloudProvider.ELLM:
                hyperparams["reasoning_effort"] = "disable"
                return
            elif ctx.inference_provider == CloudProvider.GEMINI:
                # 3-Pro cannot disable thinking
                if "3-pro" in ctx.routing_id:
                    hyperparams["reasoning_effort"] = "low"
                # 2.5 Pro cannot disable thinking
                elif "2.5-pro" in ctx.routing_id:
                    hyperparams["thinking"] = {"type": "enabled", "budget_tokens": 128}
                else:
                    hyperparams["reasoning_effort"] = "disable"
                return
            elif ctx.inference_provider == CloudProvider.ANTHROPIC:
                hyperparams["thinking"] = {"type": "disabled"}
                return
            elif ctx.inference_provider == CloudProvider.OPENAI:
                if "gpt-5.1" in ctx.routing_id:
                    # gpt-5.1: Supported values are: 'none', 'low', 'medium', and 'high'.
                    hyperparams["reasoning"] = {
                        "effort": "none",
                        "summary": reasoning_summary,
                    }
                    return
                elif "gpt-5" in ctx.routing_id:
                    hyperparams["reasoning"] = {
                        "effort": "minimal",
                        "summary": reasoning_summary,
                    }
                    return
                elif "o1" in ctx.routing_id or "o3" in ctx.routing_id or "o4" in ctx.routing_id:
                    hyperparams["reasoning"] = {
                        "effort": "low",
                        "summary": reasoning_summary,
                    }
                    return
                else:
                    hyperparams["reasoning"] = {
                        "effort": "low",
                        "summary": reasoning_summary,
                    }
                    return
            elif ctx.inference_provider == OnPremProvider.VLLM:
                hyperparams["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
                return
            logger.warning(
                (
                    f'Disabling reasoning is not supported for model "{self.config.id}" '
                    f'by provider "{ctx.inference_provider}". '
                    f"(owned_by={self.config.owned_by}, deployment.provider={ctx.deployment.provider})"
                )
            )
            return
        # Configure reasoning effort
        if reasoning_effort not in ("disable", "minimal") or thinking_budget:
            if reasoning_effort not in ("low", "medium", "high"):
                if thinking_budget <= 1024:
                    reasoning_effort = "low"
                elif thinking_budget <= 4096:
                    reasoning_effort = "medium"
                else:
                    reasoning_effort = "high"
            if ctx.inference_provider == CloudProvider.ELLM:
                hyperparams["reasoning_effort"] = reasoning_effort
                return
            elif ctx.inference_provider in [CloudProvider.GEMINI, CloudProvider.ANTHROPIC]:
                # Gemini 3-Pro recommends reasoning_effort
                # https://ai.google.dev/gemini-api/docs/openai
                if "3-pro" in ctx.routing_id:
                    hyperparams["reasoning_effort"] = (
                        "high" if reasoning_effort == "high" else "low"
                    )
                    return
                if not thinking_budget:
                    if reasoning_effort == "low":
                        thinking_budget = 1024
                    elif reasoning_effort == "medium":
                        thinking_budget = 4096
                    else:
                        thinking_budget = 8192
                if ctx.inference_provider == CloudProvider.ANTHROPIC:
                    hyperparams["temperature"] = 1
                    hyperparams["top_p"] = min(max(0.95, hyperparams.pop("top_p", 1.0)), 1.0)
                    thinking_budget = max(thinking_budget, 1024)
                hyperparams["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                }
            elif ctx.inference_provider == CloudProvider.OPENAI:
                hyperparams["reasoning"] = {
                    "effort": reasoning_effort,
                    "summary": reasoning_summary,
                }
            else:
                logger.warning(
                    (
                        f'Thinking budget is not supported for model "{self.config.id}" '
                        f'by provider "{ctx.inference_provider}". '
                        f"(owned_by={self.config.owned_by}, deployment.provider={ctx.deployment.provider})"
                    )
                )

    def _stream_delta(self, delta: Delta, finish_reason: Any | None = None) -> ModelResponseStream:
        return ModelResponseStream(
            id=self.id,
            model=self.config.id,
            choices=[StreamingChoices(index=0, delta=delta, finish_reason=finish_reason)],
        )

    def _prepare_responses_messages(self, messages: list[dict]) -> list[dict]:
        for m in messages:
            content: str | list[dict[str, str]] = m["content"]
            if not isinstance(content, list):
                continue
            for c in content:
                if c.get("type", None) == "text":
                    c["type"] = "input_text"
                elif c.get("type", None) == "image_url":
                    c["type"] = "input_image"
                    c["image_url"] = c["image_url"]["url"]
                elif c.get("type", None) == "input_audio":
                    pass
                else:
                    pass

    async def _openai_responses_stream(
        self,
        ctx: DeploymentContext,
        messages: list[dict],
        **hyperparams,
    ) -> AsyncGenerator[ModelResponseStream, None]:
        self._prepare_responses_messages(messages)
        openai_client = AsyncOpenAI(api_key=ctx.api_key)
        response_stream = await openai_client.responses.create(
            model=ctx.routing_id.split("openai/")[-1],
            input=messages,
            stream=True,
            **hyperparams,
        )
        usage_stats = {"web_search_calls": 0, "code_interpreter_calls": 0}
        final_usage = None
        async for chunk in response_stream:
            if isinstance(chunk, ResponseReasoningSummaryTextDeltaEvent):
                yield self._stream_delta(Delta(role="assistant", reasoning_content=chunk.delta))
            elif isinstance(chunk, ResponseOutputItemDoneEvent):
                if isinstance(chunk.item, ResponseFunctionWebSearch):
                    usage_stats["web_search_calls"] += 1
                    if (
                        chunk.item.action
                        and hasattr(chunk.item.action, "query")
                        and chunk.item.action.query
                    ):
                        yield self._stream_delta(Delta(role="assistant", reasoning_content="\n\n"))
                        yield self._stream_delta(
                            Delta(
                                role="assistant",
                                reasoning_content=f'Searched the web for "{chunk.item.action.query}".',
                            )
                        )
                        yield self._stream_delta(Delta(role="assistant", reasoning_content="\n\n"))
                elif isinstance(chunk.item, ResponseCodeInterpreterToolCall):
                    usage_stats["code_interpreter_calls"] += 1
                    code_snippet = chunk.item.code
                    yield self._stream_delta(Delta(role="assistant", reasoning_content="\n\n"))
                    yield self._stream_delta(
                        Delta(
                            role="assistant",
                            reasoning_content=f"Ran Python code:\n\n```python\n{code_snippet}\n```",
                        )
                    )
                    yield self._stream_delta(Delta(role="assistant", reasoning_content="\n\n"))
            elif isinstance(chunk, ResponseTextDeltaEvent):
                yield self._stream_delta(Delta(role="assistant", content=chunk.delta))
            elif isinstance(chunk, ResponseCompletedEvent):
                if chunk.response.usage:
                    final_usage = chunk.response.usage

        if final_usage:
            usage = ChatCompletionUsage(
                prompt_tokens=final_usage.input_tokens,
                completion_tokens=final_usage.output_tokens,
                total_tokens=final_usage.total_tokens,
                prompt_tokens_details=PromptUsageDetails(
                    cached_tokens=final_usage.input_tokens_details.cached_tokens
                    if final_usage.input_tokens_details
                    else 0
                ),
                completion_tokens_details=CompletionUsageDetails(
                    reasoning_tokens=final_usage.output_tokens_details.reasoning_tokens
                    if final_usage.output_tokens_details
                    else 0
                ),
                tool_usage_details=ToolUsageDetails(**usage_stats),
            )
        else:
            # Fallback if usage is not in the final chunk for some reason
            usage = ChatCompletionUsage(tool_usage_details=ToolUsageDetails(**usage_stats))

        final_chunk = self._stream_delta(delta=Delta(), finish_reason="stop")
        final_chunk.usage = Usage(**usage.model_dump())
        yield final_chunk

    async def _openai_responses(
        self,
        ctx: DeploymentContext,
        messages: list[dict],
        **hyperparams,
    ) -> ModelResponse:
        self._prepare_responses_messages(messages)
        openai_client = AsyncOpenAI(api_key=ctx.api_key)
        response: Response = await openai_client.responses.create(
            model=ctx.routing_id.split("openai/")[-1],
            input=messages,
            stream=False,
            **hyperparams,
        )
        reasoning_parts = []
        result_parts = []
        usage_stats = {"web_search_calls": 0, "code_interpreter_calls": 0}
        for item in response.output:
            if isinstance(item, ResponseReasoningItem):
                if item.summary:
                    summary_text = "\n".join(
                        part.text for part in item.summary if hasattr(part, "text")
                    )
                    if summary_text:
                        reasoning_parts.append(summary_text)
            elif isinstance(item, ResponseFunctionWebSearch) and item.status == "completed":
                usage_stats["web_search_calls"] += 1
                if item.action and hasattr(item.action, "query") and item.action.query:
                    reasoning_parts.append(f'\n\nSearched the web for "{item.action.query}".\n\n')
            elif isinstance(item, ResponseCodeInterpreterToolCall) and item.status == "completed":
                usage_stats["code_interpreter_calls"] += 1
                code_snippet = item.code
                reasoning_parts.append(
                    f"\n\nRan Python code:\n\n```python\n{code_snippet}\n```\n\n"
                )
            elif isinstance(item, ResponseOutputMessage) and item.status == "completed":
                text_content = item.content[0].text if item.content else ""
                result_parts.append(text_content)

        reasoning_result = "\n\n".join(part for part in reasoning_parts if part)
        final_result = "\n\n".join(part for part in result_parts if part)

        if response.usage:
            usage = ChatCompletionUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
                prompt_tokens_details=PromptUsageDetails(
                    cached_tokens=response.usage.input_tokens_details.cached_tokens
                    if response.usage.input_tokens_details
                    else 0
                ),
                completion_tokens_details=CompletionUsageDetails(
                    reasoning_tokens=response.usage.output_tokens_details.reasoning_tokens
                    if response.usage.output_tokens_details
                    else 0
                ),
                tool_usage_details=ToolUsageDetails(**usage_stats),
            )
        else:
            usage = ChatCompletionUsage(tool_usage_details=ToolUsageDetails(**usage_stats))

        return ModelResponse(
            id=self.id,
            model=self.config.id,
            choices=[
                Choices(
                    index=0,
                    message=Message(
                        role="assistant",
                        content=final_result,
                        reasoning_content=reasoning_result.strip(),
                    ),
                    finish_reason="stop",
                )
            ],
            usage=Usage(**usage.model_dump()),
            created=int(time()),
        )

    async def _completion_stream(
        self,
        messages: list[dict],
        **hyperparams,
    ) -> AsyncGenerator[ModelResponseStream, None]:
        async for attempt in AsyncRetrying(**self.retry_policy):
            with attempt:
                async with self._get_deployment(messages=messages, **hyperparams) as ctx:
                    self._prepare_hyperparams(ctx, hyperparams)
                    # logger.warning(f"{hyperparams=}")
                    if ctx.use_openai_responses:
                        async for chunk in self._openai_responses_stream(
                            ctx, messages, **hyperparams
                        ):
                            yield chunk
                    else:
                        response: AsyncGenerator[ModelResponseStream, None] = await acompletion(
                            timeout=self.config.timeout,
                            api_key=ctx.api_key,
                            base_url=ctx.deployment.api_base,
                            model=ctx.routing_id,
                            messages=messages,
                            stream=True,
                            stream_options={"include_usage": True},
                            **hyperparams,
                        )
                        if response is None:
                            raise ModelOverloadError(
                                f'Model provider for "{self._model_display_id}" is overloaded. Please try again later.'
                            )
                        # TODO: Investigate why litellm yields role chunks at the end of the stream
                        # i = 0
                        async for chunk in response:
                            chunk.model = self.config.id
                            yield chunk
                            # i += 1

    async def _completion(
        self,
        messages: list[dict],
        **hyperparams,
    ) -> ModelResponse:
        async for attempt in AsyncRetrying(**self.retry_policy):
            with attempt:
                async with self._get_deployment(messages=messages, **hyperparams) as ctx:
                    self._prepare_hyperparams(ctx, hyperparams)
                    if ctx.use_openai_responses:
                        return await self._openai_responses(ctx, messages, **hyperparams)
                    response = await acompletion(
                        timeout=self.config.timeout,
                        api_key=ctx.api_key,
                        base_url=ctx.deployment.api_base,
                        model=ctx.routing_id,
                        messages=messages,
                        stream=False,
                        **hyperparams,
                    )
                    if response is None:
                        raise ModelOverloadError(
                            f'Model provider for "{self._model_display_id}" is overloaded. Please try again later.'
                        )
                    response.model = self.config.id
                    return response

    async def chat_completion(
        self,
        *,
        messages: list[ChatEntry],
        stream: bool,
        **hyperparams,
    ) -> ModelResponse | AsyncGenerator[ModelResponse, None]:
        if not (isinstance(messages, list) and all(isinstance(m, ChatEntry) for m in messages)):
            # We raise TypeError here since this is a programming error
            raise TypeError("`messages` must be a list of `ChatEntry`.")
        hyperparams.pop("stream_options", None)
        messages, hyperparams = await self._prepare_chat(
            messages=messages,
            hyperparams=hyperparams,
        )
        if stream:
            return self._completion_stream(messages, **hyperparams)
        else:
            return await self._completion(messages, **hyperparams)

    ### --- Embedding --- ###

    async def embedding(
        self,
        *,
        texts: list[str],
        is_query: bool = True,
        encoding_format: str | None = None,
        **hyperparams,
    ) -> EmbeddingResponse:
        async for attempt in AsyncRetrying(**self.retry_policy):
            with attempt:
                async with self._get_deployment(
                    texts=texts, encoding_format=encoding_format, **hyperparams
                ) as ctx:
                    # Get output dimensions
                    dimensions = (
                        hyperparams.get("dimensions", None) or self.config.embedding_dimensions
                    )
                    # Maybe transform texts
                    if self.config.embedding_transform_query is not None:
                        texts = [self.config.embedding_transform_query + text for text in texts]
                    # Set batch size and hyperparams
                    batch_size = 2048
                    if ctx.deployment.provider == CloudProvider.COHERE:
                        if is_query:
                            hyperparams["input_type"] = "search_query"
                        else:
                            hyperparams["input_type"] = "search_document"
                        batch_size = 96  # limit on cohere server
                    elif ctx.deployment.provider == CloudProvider.JINA_AI:
                        batch_size = 128  # don't know limit, but too large will timeout
                    elif ctx.deployment.provider == CloudProvider.VOYAGE:
                        batch_size = 128  # limit on voyage server
                    elif ctx.deployment.provider == CloudProvider.OPENAI:
                        batch_size = 256  # limited by token per min (10,000,000)

                    # self._billing.has_embedding_quota(model_id=self.embedder_config["id"])
                    # Call
                    responses: list[LiteLLMEmbeddingResponse] = await asyncio.gather(
                        *[
                            aembedding(
                                timeout=self.config.timeout,
                                api_key=ctx.api_key,
                                api_base=ctx.deployment.api_base,
                                model=ctx.routing_id,
                                input=txt,
                                dimensions=dimensions,
                                encoding_format=encoding_format,
                                **hyperparams,
                            )
                            for txt in self.batch(texts, batch_size)
                        ]
                    )
                    # Compile from batches
                    vectors = [
                        e["embedding"] for e in itertools.chain(*[r.data for r in responses])
                    ]
                    usage = EmbeddingUsage(
                        prompt_tokens=sum(getattr(r.usage, "prompt_tokens", 1) for r in responses),
                        total_tokens=sum(getattr(r.usage, "total_tokens", 1) for r in responses),
                    )
                    # Might need to encode into base64
                    if encoding_format == "base64" and isinstance(vectors[0], list):
                        logger.warning(
                            "`encoding_format` is `base64` but vectors are not base64 encoded."
                        )
                        vectors = [
                            b64encode(np.asarray(v, dtype=np.float32).tobytes()).decode("ascii")
                            for v in vectors
                        ]
                    embeddings = EmbeddingResponse(
                        data=[
                            EmbeddingResponseData(embedding=v, index=i)
                            for i, v in enumerate(vectors)
                        ],
                        model=self.config.id,
                        usage=usage,
                    )
                    return embeddings

    ### --- Reranking --- ###

    async def reranking(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        **hyperparams,
    ) -> RerankingResponse:
        if len(documents) == 0:
            raise ValueError("There are no documents to rerank.")
        async for attempt in AsyncRetrying(**self.retry_policy):
            with attempt:
                async with self._get_deployment(
                    query=query, documents=documents, **hyperparams
                ) as ctx:
                    batch_size = 100
                    # self._billing.has_embedding_quota(model_id=self.embedder_config["id"])
                    # Call
                    batches = list(self.batch(documents, batch_size))
                    responses: list[RerankResponse] = await asyncio.gather(
                        *[
                            arerank(
                                timeout=self.config.timeout,
                                api_key=ctx.api_key,
                                api_base=ctx.deployment.api_base,
                                model=ctx.routing_id,
                                query=query,
                                documents=docs,
                                top_n=top_n,
                                return_documents=False,
                                **hyperparams,
                            )
                            for docs in batches
                        ]
                    )
                    responses = [r.model_dump(exclude_unset=True) for r in responses]
                    # Compile results from batches
                    results = [
                        {
                            "index": res["index"]
                            if i == 0
                            else res["index"] + i * len(batches[i - 1]),
                            "relevance_score": res["relevance_score"],
                        }
                        for i, response in enumerate(responses)
                        for res in response["results"]
                    ]
                    results = sorted(results, key=lambda x: x["relevance_score"], reverse=True)
                    # Compile usage from batches
                    metas = [r.get("meta", {}) for r in responses]
                    billed_units = [m.get("billed_units", {}) for m in metas]
                    tokens = [m.get("tokens", {}) for m in metas]
                    billed_units = {
                        k: sum(d.get(k, 0) or 0 for d in billed_units)
                        for k in set().union(*billed_units)
                    }
                    tokens = {
                        k: sum(d.get(k, 0) or 0 for d in tokens) for k in set().union(*tokens)
                    }
                    usage = deepcopy(tokens)
                    usage["documents"] = len(documents)
                    # Generate final response
                    try:
                        response = responses[0]
                    except IndexError:
                        logger.error(
                            f"No responses from reranking!!! {batches=}  {documents=}  {batch_size=}"
                        )
                        raise
                    response["results"] = results
                    response["usage"] = usage
                    response["meta"]["model"] = self.config.id
                    if len(billed_units) > 0:
                        response["meta"]["billed_units"] = billed_units
                    if len(tokens) > 0:
                        response["meta"]["tokens"] = tokens
                    return RerankingResponse.model_validate(response)


class LMEngine:
    def __init__(
        self,
        *,
        organization: OrganizationRead,
        project: Project_,
        request: Request,
    ) -> None:
        self.organization = organization
        self.project = project
        self.request = request
        self.id: str = request.state.id
        self.is_browser: bool = request.state.user_agent.is_browser
        self.billing: BillingManager | None = getattr(request.state, "billing", None)
        self._models: list[ModelConfigRead] | None = getattr(self.billing, "models", None)
        self._chat_usage = ChatCompletionUsage()
        self._embed_usage = EmbeddingUsage()
        self._rerank_usage = RerankingUsage(documents=0)

    async def _get_models(self, capabilities: list[str] | None = None) -> list[ModelConfigRead]:
        if self._models is None:
            logger.warning(
                f"{self.id} - No models found in BillingManager. Fetching from database."
            )
            async with async_session() as session:
                models = (
                    await ModelConfig.list_(
                        session=session,
                        return_type=ModelConfigRead,
                        organization_id=self.organization.id,
                        capabilities=capabilities,
                        exclude_inactive=True,
                    )
                ).items
            self._models = models
        else:
            models = [m for m in self._models if m.is_active]
            # Filter by capability
            if capabilities is not None:
                for capability in capabilities:
                    models = [m for m in models if capability in m.capabilities]
        if len(models) == 0:
            raise ResourceNotFoundError(
                f"No model found with capabilities: {list(map(str, capabilities))}."
            )
        return models

    async def _get_model(self, model: str) -> ModelConfigRead:
        model = model.strip()
        model_configs = await self._get_models()
        model_config = next((m for m in model_configs if m.id == model), None)
        if model_config is None:
            raise ResourceNotFoundError(f'Model "{model}" is not found.')
        return model_config

    @staticmethod
    def pick_best_model(
        model_configs: list[ModelConfig_],
        capabilities: list[ModelCapability],
    ) -> ModelConfig_:
        def _sort_key_with_priority(m: ModelConfig_) -> tuple[int, int, str]:
            return (
                int(not m.id.startswith("ellm")),
                int(ModelCapability.AUDIO in m.capabilities),  # De-prioritise audio models
                len(m.capabilities_set - set(capabilities)),
                -m.priority,
                m.name,
            )

        model_configs = natsorted(model_configs, key=_sort_key_with_priority)
        return model_configs[0]

    ### --- Chat Completion --- ###

    @staticmethod
    def _check_messages_type(messages: list[ChatEntry]):
        if not (isinstance(messages, list) and all(isinstance(m, ChatEntry) for m in messages)):
            # We raise TypeError here since this is a programming error
            raise TypeError("`messages` must be a list of `ChatEntry`.")

    async def _get_default_model(
        self,
        model: str,
        capabilities: list[ModelCapability],
    ) -> ModelConfigRead:
        capabilities_set = set(capabilities)
        # If model is empty string, we try to get a suitable model
        if model == "":
            # Error will be raised if no suitable model is found
            model_configs = await self._get_models(capabilities)
            model_config = self.pick_best_model(model_configs, capabilities)
        else:
            model_config = await self._get_model(model)
            if len(lack := (capabilities_set - model_config.capabilities_set)) > 0:
                raise ModelCapabilityError(
                    f'Model "{model_config.name if self.is_browser else model}" lack these capabilities: {", ".join(lack)}'
                )
        return model_config

    @asynccontextmanager
    async def _setup_chat(
        self,
        model: str,
        messages: list[ChatEntry],
    ):
        # Validate model capability
        self._check_messages_type(messages)
        capabilities = [str(ModelCapability.CHAT)]
        if any(m.has_image for m in messages):
            capabilities.append(str(ModelCapability.IMAGE))
        if any(m.has_audio for m in messages):
            capabilities.append(str(ModelCapability.AUDIO))
        # If model is empty string, we try to get a suitable model
        model_config = await self._get_default_model(model, capabilities)
        model = model_config.id
        # Setup rate limiting
        # rpm_limiter = CascadeRateLimiter(
        #     org_hpm=ENV_CONFIG.llm_requests_per_minute,
        #     proj_hpm=ENV_CONFIG.llm_requests_per_minute,
        #     organization_id=self.organization.id,
        #     project_id=self.project.id,
        #     key=f"{model}:rpm",
        #     name="RPM",
        # )
        # tpm_limiter = CascadeRateLimiter(
        #     org_hpm=ENV_CONFIG.llm_tokens_per_minute,
        #     proj_hpm=ENV_CONFIG.llm_tokens_per_minute,
        #     organization_id=self.organization.id,
        #     project_id=self.project.id,
        #     key=f"{model}:tpm",
        #     name="TPM",
        # )
        # # Test rate limits
        # await asyncio.gather(rpm_limiter.test(), tpm_limiter.test(max_tokens))
        router = DeploymentRouter(
            request=self.request,
            config=model_config,
            organization=self.organization,
            is_browser=self.is_browser,
        )
        try:
            yield router
        finally:
            # # Consume rate limits
            # await asyncio.gather(rpm_limiter.hit(), tpm_limiter.hit(self._chat_usage.total_tokens))
            if self.billing is not None:
                try:
                    self.billing.create_llm_events(
                        model_id=model,
                        input_tokens=self._chat_usage.prompt_tokens,
                        output_tokens=self._chat_usage.completion_tokens,
                    )
                except Exception as e:
                    logger.warning(f"Failed to create LLM events due to error: {repr(e)}")

    async def chat_completion_stream(
        self,
        *,
        model: str,
        messages: list[ChatEntry],
        **hyperparams,
    ) -> AsyncGenerator[ChatCompletionChunkResponse, None]:
        """
        Generate streaming chat completions.

        Args:
            model (str): Model ID. Can be empty in which case we try to get a suitable model based on message content.
            messages (list[ChatEntry]): List of messages.
            **hyperparams (Any): Keyword arguments.

        Yields:
            chunk (ChatCompletionChunkResponse): A chat chunk.
        """
        hyperparams.pop("stream", None)
        async with self._setup_chat(model, messages) as router:
            completion: AsyncGenerator[ModelResponse, None] = await router.chat_completion(
                messages=messages,
                stream=True,
                **hyperparams,
            )
            async for chunk in completion:
                if hasattr(chunk, "usage"):
                    self._chat_usage = ChatCompletionUsage.model_validate(chunk.usage.model_dump())
                yield ChatCompletionChunkResponse(
                    **chunk.model_dump(exclude_unset=True, exclude_none=True)
                )

    async def chat_completion(
        self,
        *,
        model: str,
        messages: list[ChatEntry],
        **hyperparams,
    ) -> ChatCompletionResponse:
        """
        Generate chat completions.

        Args:
            model (str): Model ID. Can be empty in which case we try to get a suitable model based on message content.
            messages (list[ChatEntry]): List of messages.
            **hyperparams (Any): Keyword arguments.

        Returns:
            response (ChatCompletionResponse): The chat response.
        """
        hyperparams.pop("stream", None)
        async with self._setup_chat(model, messages) as router:
            completion: ModelResponse = await router.chat_completion(
                messages=messages,
                stream=False,
                **hyperparams,
            )
            completion = ChatCompletionResponse.model_validate(
                completion.model_dump(exclude_unset=True, exclude_none=True)
            )
            self._chat_usage = completion.usage
            return completion

    async def generate_title(
        self,
        *,
        excerpt: str,
        model: str = "",
        **hyperparams,
    ) -> str:
        system_prompt = dedent("""\
                You are a professional document analyst. Your primary goal is to extract the most accurate and complete title from the document's first page.

                Analyze the page using the following prioritized steps:

                1.  **PRIORITY 1: EXTRACT VERBATIM TITLE:**
                    - First, attempt to identify and extract the main, verbatim title. This is typically the most prominent text block (e.g., largest font, bold, centered)
                    at the top of the page, common in academic papers, reports, or articles. This is the preferred method.
                    - Prominent text block may not always represent the title, so read the entire page to understand the context. Append the suitable subtitle if it exists.
                    - Append the purpose of the document based on the page content.

                2.  **PRIORITY 2: ASSEMBLE FROM COMPONENTS:**
                    If no single, clear verbatim title exists (common in forms or structured plans),
                    then construct a title by extracting and combining these components:
                    - Primary Entity: The main company/organization.
                    - Document Type: The official name of the document (e.g., Insurance Plan, Agreement).
                    - Key Identifiers:  Extract ALL unique codes and levels. This includes a master identifier (like a Policy or Group Number)
                    AND specific sub-identifier (like a Plan Name, Plan Level, Tier, Date and/or Year).

                3.  **UNIVERSAL RULE: INCLUDE IDENTIFIERS:**
                    Regardless of whether the title is extracted verbatim (Priority 1) or assembled (Priority 2),
                    append both the master identifier and the specific plan level if both are present.
                    Append the date or year if it is part of the title or relevant to the document's context.

                4.  **OUTPUT:** Output only the final, single-line title. (Max 20 words).
            """)
        prompt = dedent(f"""\
                Analyze the Page content below and output the most representative title based on your core instructions.
                - DO NOT THINK, OUTPUT ONLY THE FINAL TITLE

                **Page Context:**
                {excerpt}
            """)
        # Override hyperparams
        hyperparams.update(
            temperature=0.01,
            top_p=0.01,
            max_tokens=500,
            stream=False,
            reasoning_effort="minimal",
        )
        try:
            completion = (
                await self.chat_completion(
                    model=model,
                    messages=[ChatEntry.system(system_prompt), ChatEntry.user(prompt)],
                    **hyperparams,
                )
            ).content
            title = completion.strip().strip('"')
        except Exception as e:
            logger.warning(
                f"{hyperparams.get('id', '')} - Title extraction failed for excerpt: \n{excerpt}\n, error: {e}"
            )
            title = ""
        if not title:
            title = "Document"
        return title

    async def generate_chat_title(
        self,
        *,
        user_content: str,
        assistant_content: str,
        model: str = "",
        **hyperparams,
    ) -> SanitisedStr:
        system_prompt = "Generate a concise, descriptive title for a chat message."
        prompt = dedent(f"""\
            <user>
            {user_content}
            </user>

            <assistant>
            {assistant_content}
            </assistant>

            Do not think. Generate a short, concise title of no more than 5 words for the conversation.
            """)
        # Override hyperparams
        hyperparams.update(
            temperature=0.01,
            top_p=0.01,
            max_tokens=500,
            stream=False,
            reasoning_effort="minimal",
        )
        default_title = "New Chat"
        try:
            completion = (
                await self.chat_completion(
                    model=model,
                    messages=[ChatEntry.system(system_prompt), ChatEntry.user(prompt)],
                    **hyperparams,
                )
            ).content
            title = completion.strip().strip('"')
            if not title:
                title = default_title
        except Exception as e:
            logger.warning(
                f"{hyperparams.get('id', '')} - Title generation failed for the chat message: {user_content}, error: {e}"
            )
            title = default_title

        # Replace non-printable characters with space
        return " ".join("".join(c if c.isprintable() else " " for c in title).split())

    def _rewrite_prompts_for_fts_query(self, input_prompt: str) -> str:
        system_prompt = dedent("""\
        You are an advanced search query generation system. Your purpose is to translate user questions and conversational context into precise query components optimized for an information retrieval system using both keyword-based Full-Text Search (FTS) with pgroonga.

        Your primary tasks are:
        1.  **Analyze Intent:** Deeply understand the user's information need expressed in their query and any relevant conversation history (if provided).
        2.  **Extract Key Information:** Identify critical keywords, named entities (people, places, organizations, dates, etc.), specific technical terms, and core concepts.
        3.  **Disambiguate:** Resolve ambiguities based on context.
        4.  **Generate Direct Query Output:** Produce a direct answer containing the distinct query strings:
            *Optimized for keyword precision and recall in pgroonga. Focus on essential nouns, verbs, entities, and specific identifiers. Should be concise.

        Focus on generating queries that, when used together in their respective search engines, will yield the most relevant results. Accuracy, relevance, and appropriate optimization for each search type are paramount.
        """)
        prompt = dedent(f"""\
        "user_query": "{input_prompt}",
        "current_datetime": "{now().isoformat()}"

        Instructions:
        Analyze the user_query, considering the current_datetime for temporal references. Generate a direct query string containing the rewritten query optimized for pgroonga FTS, keeping in mind that **stemming is active (at least for English)**. Follow these steps precisely:

        1.  **Identify Core Concepts:** Extract the most important terms representing the subject, action/intent, and key context from the user_query. Include essential nouns, verbs, entities, codes, and specific identifiers. Since stemming is active, focus on the root concepts.
        2.  **Handle Phrases:** Identify multi-word terms crucial to the meaning (e.g., "machine learning", "API key", "user acceptance testing"). Enclose these exact phrases in double quotes (`"`). Stemming does not preserve word order, making phrase matching critical.
        3.  **Use Synonyms/Alternatives (OR - Strategically):**
            *   Use `OR` *only* for genuinely distinct synonyms or alternative concepts that **will likely not stem to the same root** (e.g., `bug OR defect`, `UI OR "user interface"`).
            *   **Do NOT** use `OR` for simple word variations handled by stemming (e.g., do not write `database OR databases`, `configure OR configuration`, `run OR running` - the stemmer handles these).
            *   Use OR sparingly, focusing on high-value alternatives to improve recall for distinct concepts.
        4.  **Convert Dates:** Use the `current_datetime` to resolve relative temporal references (e.g., "last year", "yesterday") into absolute numeric formats (YYYY or YYYY-MM-DD). For ranges like "last 2 years", list the specific years space-separated (e.g., based on 2025-04-16, "last 2 years" -> `2023 2024`).
        5.  **Combine Terms:** Join individual keywords (prefer base/stemmed forms where natural), quoted phrases, and `OR` groups primarily with spaces (implying an AND relationship between distinct concepts).
        6.  **Filter Noise but Preserve Meaning:** Remove generic filler words (like "the", "a", "is", "how to") UNLESS they are part of an essential quoted phrase. Prioritize terms likely to appear verbatim (or their stems) in relevant documents, but do not discard terms crucial for understanding the query's specific intent (e.g., keep words like "compare", "impact", "migrate" if central).
        7.  **Conciseness and Completeness:** Aim for a query that is concise yet captures the full essential meaning of the original user query, leveraging the stemmer's capabilities.
        8.  **Multi-Word Terms:** Use double quotes for terms composed of multiple words that should be treated as a single unit. Example: United Kingdom -> "United Kingdom"

        **Examples:**

        *   **User Query:** What's the meaning of USG?
            **FTS Query:** USG meaning OR definition

        *   **User Query:** In 2024 how many database outage happened?
            **FTS Query:** database outage OR failure 2024 count

        *   **User Query:** How can I configure the connection pool for the main transaction database?
            **FTS Query:** configure OR setup "connection pool" "main transaction database"

        *   **User Query:** Any issues reported for the payment gateway integration last month? (Given Datetime: 2025-04-16)
            **FTS Query:** issue OR problem OR error "payment gateway integration" 2025-03

        *   **User Query:** Compare performance impact of Redis vs Memcached deployment in production last year. (Given Datetime: 2025-04-16)
            **FTS Query:** compare performance impact Redis Memcached deployment production 2024

        *   **User Query:** What's the weather in Japan 3 months ago? (Given Datetime: 2025-04-16)
            **FTS Query:** weather Japan 2025-01

        *   **User Query:** チカワは何年に生まれますか？
            **FTS Query:** チカワ 生まれる OR 誕生

        Reply ONLY with the generated FTS query string. Do not think. Do not include explanations, reasoning, markdown formatting, no need to use quotes to encapsulate the entire results, or any text outside the final FTS Query in the original query language.

        Now generate the query:
        """)
        return system_prompt, prompt

    def _rewrite_prompts_for_vs_query(self, input_prompt: str) -> str:
        system_prompt = dedent("""\
        You are an advanced search query generation system. Your purpose is to translate user questions and conversational context into precise query components optimized for an information retrieval system using semantic Vector Search (VS).

        Your primary tasks are:
        1.  **Analyze Intent:** Deeply understand the user's information need expressed in their query and any relevant conversation history (if provided).
        2.  **Extract Key Information:** Identify critical keywords, named entities (people, places, organizations, dates, etc.), specific technical terms, and core concepts.
        3.  **Disambiguate:** Resolve ambiguities based on context.
        4.  **Generate Direct Query Output:** Produce a direct answer containing the distinct query strings:
            *Optimized for capturing semantic meaning and nuance for vector embedding similarity search. Should be a well-formed natural language sentence or question reflecting the user's core intent.

        Focus on generating queries that, when used together in their respective search engines, will yield the most relevant results. Accuracy, relevance, and appropriate optimization for each search type are paramount.
        """)
        prompt = dedent(f"""\
        "user_query": "{input_prompt}",
        "current_datetime": "{now().isoformat()}"

        Instructions:
        Analyze the user_query, considering the current_datetime for temporal references. Generate a direct query string containing vector query for vector search.

        1.  **vector_query**:
            *   Create a natural language sentence or question that captures the core semantic meaning and intent of the user_query.
            *   This query should be suitable for generating an embedding for vector similarity search.
            *   Retain natural language phrasing for concepts, including relative time expressions (e.g., "last year", "next quarter") if they better represent the user's intent semantically.
            *   Example style: How to fix database connection timeout errors when configuring pgroonga, especially issues seen recently?

        Reply ONLY with the generated VS query. Do not think. Do not include explanations, reasoning, markdown formatting, or any text outside the final VS Query.

        Now generate the query:
        """)
        return system_prompt, prompt

    @staticmethod
    def _extract_text_prompt(
        messages: list[ChatEntry],
    ) -> tuple[list[ChatEntry], str, list[ImageContent | AudioContent] | None]:
        # Make a deep copy to avoid side effects
        messages = deepcopy(messages)
        # The message list should end with user message
        if messages[-1].role == ChatRole.USER:
            pass
        elif messages[-2].role == ChatRole.USER:
            messages = messages[:-1]
        else:
            raise BadInputError("The message list should end with user or assistant message.")
        content = messages[-1].content
        if isinstance(content, str):
            prompt = content
            multimodal_contents = None
        else:
            prompt = messages[-1].text_content
            multimodal_contents = [c for c in content if not isinstance(c, TextContent)]
        return messages, prompt, multimodal_contents

    async def _generate_search_query(
        self,
        *,
        model: str,
        messages: list[ChatEntry],
        type: str,
        **hyperparams,
    ) -> str:
        messages, prompt, multimodal_contents = self._extract_text_prompt(messages)
        # Retrieved system and user prompt, updated as of 2025-04-17
        if type == "fts":
            system_prompt, new_prompt = self._rewrite_prompts_for_fts_query(prompt)
        elif type == "vs":
            system_prompt, new_prompt = self._rewrite_prompts_for_vs_query(prompt)
        else:
            raise BadInputError(
                f"Rewrite prompt only works for type: FTS or VS. Invalid type: {type}"
            )

        if messages[0].role == ChatRole.SYSTEM:
            # Suggest to just override system prompt, 2025-04-17
            messages[0].content = system_prompt
        else:
            messages.insert(0, ChatEntry.system(system_prompt))
        # Override hyperparams
        hyperparams.update(
            temperature=0.01,
            top_p=0.01,
            max_tokens=1000,
            stream=False,
            reasoning_effort="minimal",
        )
        if multimodal_contents is not None:
            new_prompt = multimodal_contents + [TextContent(text=new_prompt)]
        messages[-1] = ChatEntry.user(new_prompt)
        completion = (
            await self.chat_completion(
                model=model,
                messages=messages,
                **hyperparams,
            )
        ).content
        if completion is None:
            new_prompt = prompt
        else:
            new_prompt = completion.strip()
            if new_prompt.startswith('"') and new_prompt.endswith('"'):
                new_prompt = new_prompt[1:-1]
        return new_prompt

    async def generate_search_query(
        self,
        *,
        model: str,
        messages: list[ChatEntry],
        rag_params: RAGParams,
        **hyperparams,
    ) -> tuple[str, str]:
        """
        Generate search query for RAG.

        Args:
            model (str): Model ID. Can be empty in which case we try to get a suitable model based on message content.
            messages (list[ChatEntry]): List of messages.
            rag_params (RAGParams): RAG parameters.
            **hyperparams (Any): Keyword arguments.

        Raises:
            TypeError: If `rag_params` is not an instance of `RAGParams`.
            BadInputError: If the message list does not end with user or assistant message.

        Returns:
            fts_query (str): The fts search query.
            vs_query (str): The vs search query.
        """
        self._check_messages_type(messages)
        if not isinstance(rag_params, RAGParams):
            raise TypeError("`rag_params` must be an instance of `RAGParams`.")
        # Generate missing queries in parallel
        queries = {
            "fts": rag_params.search_query.strip(),
            "vs": rag_params.search_query.strip(),
        }
        to_generate = [q_type for q_type, query in queries.items() if not query]
        if to_generate:
            generated = await asyncio.gather(
                *[
                    self._generate_search_query(
                        model=model,
                        messages=messages,
                        type=q_type,
                        **hyperparams,
                    )
                    for q_type in to_generate
                ]
            )
            # Update the queries dict with generated values
            for q_type, generated_query in zip(to_generate, generated, strict=True):
                queries[q_type] = generated_query
        return queries["fts"], queries["vs"]

    async def make_rag_prompt(
        self,
        *,
        messages: list[ChatEntry],
        references: References,
        inline_citations: bool = False,
    ) -> str | list[TextContent | ImageContent | AudioContent]:
        _, prompt, multimodal_contents = self._extract_text_prompt(messages)
        documents = "\n\n".join(
            dedent(f"""\
            <document>

            <title> {chunk.title} </title>
            <id> {i} </id>
            <page-number> {chunk.page} </page-number>
            <content>
            {"\n".join(f"## {k}: {v}" for k, v in chunk.context.items())}

            ## Text:\n{chunk.text}

            </content>

            </document>
            """)
            for i, chunk in enumerate(references.chunks)
        )
        context_prompt = f"<up-to-date-context>\n\n{documents}\n\n</up-to-date-context>\n\n"
        if inline_citations:
            prompt += (
                "\n"
                "When any sentence in your answer is supported by or refers to one or more documents inside <up-to-date-context>, "
                "append inline citations using Pandoc-style `[@<id>]` for each supporting document at the end of that sentence, "
                "immediately before the sentence-ending punctuation. "
                "Use the exact <id> from each <document> and never invent IDs. "
                "Arrange the citations from most to least relevant. "
                "If multiple documents support the sentence, include multiple citations delimited by semicolons `[@<id-1>; @<id-2>]`. "
                "Always separate the text and citations with one space, ie `<text> [@<id>]`. "
                "Do not cite for general knowledge, your own reasoning, or content not found in the provided documents. "
                "\n"
                "For example:"
                "\n"
                '- "London is the capital of England."\n'
                '- "The merger was completed in Q3 [@4]."\n'
                '- "Revenue was $8.2 million [@7; @1]."\n'
            )
        if multimodal_contents is None:
            multimodal_contents = []
        prompt = (
            [TextContent(text=context_prompt)] + multimodal_contents + [TextContent(text=prompt)]
        )
        return prompt

    ### --- Embedding --- ###

    @asynccontextmanager
    async def _setup_embedding(self, model: str):
        # Validate model capability
        capabilities = [str(ModelCapability.EMBED)]
        model_config = await self._get_default_model(model, capabilities)
        model = model_config.id
        # Setup rate limiting
        # rpm_limiter = CascadeRateLimiter(
        #     org_hpm=ENV_CONFIG.embed_requests_per_minute,
        #     proj_hpm=ENV_CONFIG.embed_requests_per_minute,
        #     organization_id=self.organization.id,
        #     project_id=self.project.id,
        #     key=f"{model}:rpm",
        #     name="RPM",
        # )
        # tpm_limiter = CascadeRateLimiter(
        #     org_hpm=ENV_CONFIG.embed_tokens_per_minute,
        #     proj_hpm=ENV_CONFIG.embed_tokens_per_minute,
        #     organization_id=self.organization.id,
        #     project_id=self.project.id,
        #     key=f"{model}:tpm",
        #     name="TPM",
        # )
        # # Test rate limits
        # await asyncio.gather(rpm_limiter.test(), tpm_limiter.test())
        router = DeploymentRouter(
            request=self.request,
            config=model_config,
            organization=self.organization,
            is_browser=self.is_browser,
        )
        try:
            yield router
        finally:
            # # Consume rate limits
            # await asyncio.gather(
            #     rpm_limiter.hit(), tpm_limiter.hit(self._embed_usage.total_tokens)
            # )
            if self.billing is not None:
                try:
                    self.billing.create_embedding_events(
                        model_id=model,
                        token_usage=self._embed_usage.total_tokens,
                    )
                except Exception as e:
                    logger.warning(f"Failed to create embedding events due to error: {repr(e)}")

    async def embed_documents(
        self,
        *,
        model: str,
        texts: list[str],
        encoding_format: str | None = None,
        **hyperparams,
    ) -> EmbeddingResponse:
        """
        Embed documents.

        Args:
            model (str): Model ID. Can be empty in which case we try to get a suitable model.
            texts (list[str]): List of strings to embed as documents.
            encoding_format (str | None, optional): Vector encoding format. Defaults to None.

        Returns:
            response (EmbeddingResponse): The embedding response.
        """
        if len(texts) == 0:
            raise BadInputError("There is no text or content to embed.")
        # TODO: Do we need to truncate based on context length?
        # encoding = tiktoken.get_encoding(encoding_name)
        # encoded_text = encoding.encode(text)
        # if len(encoded_text) <= max_context_length:
        #     return text
        # truncated_encoded = encoded_text[:max_context_length]
        # truncated_text = encoding.decode(truncated_encoded)
        async with self._setup_embedding(model) as router:
            embeddings = await router.embedding(
                texts=texts,
                is_query=False,
                encoding_format=encoding_format,
                **hyperparams,
            )
            self._embed_usage = embeddings.usage
            return embeddings

    async def embed_queries(
        self,
        model: str,
        texts: list[str],
        encoding_format: str | None = None,
        **hyperparams,
    ) -> EmbeddingResponse:
        """
        Embed documents.

        Args:
            model (str): Model ID. Can be empty in which case we try to get a suitable model.
            texts (list[str]): List of strings to embed as queries.
            encoding_format (str | None, optional): Vector encoding format. Defaults to None.

        Returns:
            response (EmbeddingResponse): The embedding response.
        """
        # TODO: Do we need to truncate based on context length?
        async with self._setup_embedding(model) as router:
            embeddings = await router.embedding(
                texts=texts,
                is_query=True,
                encoding_format=encoding_format,
                **hyperparams,
            )
            self._embed_usage = embeddings.usage
            return embeddings

    async def embed_query_as_vector(
        self,
        model: str,
        text: str,
        **hyperparams,
    ) -> list[float]:
        """
        Embed documents.

        Args:
            model (str): Model ID. Can be empty in which case we try to get a suitable model.
            text (str): A string to embed as query.

        Returns:
            vector (list[float]): The embedding vector.
        """
        response = await self.embed_queries(
            model=model,
            texts=[text],
            encoding_format="float",
            **hyperparams,
        )
        return response.data[0].embedding

    ### --- Reranking --- ###

    @asynccontextmanager
    async def _setup_reranking(self, model: str):
        # Validate model capability
        capabilities = [str(ModelCapability.RERANK)]
        model_config = await self._get_default_model(model, capabilities)
        model = model_config.id
        # Setup rate limiting
        # rpm_limiter = CascadeRateLimiter(
        #     org_hpm=ENV_CONFIG.rerank_requests_per_minute,
        #     proj_hpm=ENV_CONFIG.rerank_requests_per_minute,
        #     organization_id=self.organization.id,
        #     project_id=self.project.id,
        #     key=f"{model}:rpm",
        #     name="RPM",
        # )
        # spm_limiter = CascadeRateLimiter(
        #     org_hpm=ENV_CONFIG.rerank_searches_per_minute,
        #     proj_hpm=ENV_CONFIG.rerank_searches_per_minute,
        #     organization_id=self.organization.id,
        #     project_id=self.project.id,
        #     key=f"{model}:spm",
        #     name="SPM",
        # )
        # # Test rate limits
        # await asyncio.gather(rpm_limiter.test(), spm_limiter.test())
        router = DeploymentRouter(
            request=self.request,
            config=model_config,
            organization=self.organization,
            is_browser=self.is_browser,
        )
        try:
            yield router
        finally:
            # # Consume rate limits
            # await asyncio.gather(rpm_limiter.hit(), spm_limiter.hit(self._rerank_usage.documents))
            if self.billing is not None:
                try:
                    self.billing.create_reranker_events(
                        model_id=model,
                        num_searches=self._rerank_usage.documents,
                    )
                except Exception as e:
                    logger.warning(f"Failed to create reranker events due to error: {repr(e)}")

    async def rerank_documents(
        self,
        *,
        model: str,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        **hyperparams,
    ) -> RerankingResponse:
        """
        Rerank documents.

        Args:
            model (str): Model ID. Can be empty in which case we try to get a suitable model.
            query (str): Query string.
            documents (list[str]): List of strings to rerank.
            top_n (int | None, optional): Only return `top_n` results. Defaults to None.

        Returns:
            response (RerankingResponse): The rerank response.
        """
        if len(query.strip()) == 0:
            raise BadInputError("Query cannot be empty.")
        if len(documents) == 0:
            raise BadInputError("There are no documents to rerank.")
        async with self._setup_reranking(model) as router:
            rerankings = await router.reranking(
                query=query,
                documents=documents,
                top_n=top_n,
                **hyperparams,
            )
            self._rerank_usage = rerankings.usage
            return rerankings
