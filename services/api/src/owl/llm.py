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

from jamaibase.protocol import (
    DEFAULT_CHAT_MODEL,
    ChatCompletionChoiceDelta,
    ChatCompletionChunk,
    ChatEntry,
    ChatRole,
    ModelInfo,
    ModelInfoResponse,
    ModelListConfig,
)
from owl.config import get_model_json
from owl.utils import get_api_key
from owl.utils.exceptions import ContextOverflowError, ResourceNotFoundError

litellm.drop_params = True


async def model_info(
    model: str = "",
    capabilities: list[str] | None = None,
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
    cohere_api_key: str = "",
    groq_api_key: str = "",
    together_api_key: str = "",
    jina_api_key: str = "",
    voyage_api_key: str = "",
) -> ModelInfoResponse:
    all_models = ModelListConfig.model_validate_json(get_model_json())
    # Chat models
    models = [m for m in all_models.llm_models if m.owned_by == "ellm"]
    if openai_api_key != "":
        models += [m for m in all_models.llm_models if m.owned_by == "openai"]
    if anthropic_api_key != "":
        models += [m for m in all_models.llm_models if m.owned_by == "anthropic"]
    if together_api_key != "":
        models += [m for m in all_models.llm_models if m.owned_by == "together_ai"]
    # Embedding models
    models += [m for m in all_models.embed_models if m.owned_by == "ellm"]
    if openai_api_key != "":
        models += [m for m in all_models.embed_models if m.owned_by == "openai"]
    if cohere_api_key != "":
        models += [m for m in all_models.embed_models if m.owned_by == "cohere"]
    # Reranking models
    models += [m for m in all_models.rerank_models if m.owned_by == "ellm"]
    if cohere_api_key != "":
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
        raise ResourceNotFoundError(f"No suitable model found with capabilities: {capabilities}")
    response = ModelInfoResponse(data=[ModelInfo.model_validate(m.model_dump()) for m in models])
    return response


async def model_names(
    prefer: str = "",
    capabilities: list[str] | None = None,
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
    cohere_api_key: str = "",
    groq_api_key: str = "",
    together_api_key: str = "",
    jina_api_key: str = "",
    voyage_api_key: str = "",
) -> list[str]:
    models = await model_info(
        model="",
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
    model_names = [m.id for m in models.data]
    if prefer in model_names:
        model_names.remove(prefer)
        model_names.insert(0, prefer)
    return model_names


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


# Cached function
def get_llm_router():
    return _get_llm_router(get_model_json())


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


def _check_messages(messages: list[ChatEntry]):
    if messages[0].role in (ChatRole.SYSTEM.value, ChatRole.SYSTEM):
        if messages[1].role in (ChatRole.ASSISTANT.value, ChatRole.ASSISTANT):
            messages.insert(1, ChatEntry.user(content="."))
    elif messages[0].role in (ChatRole.ASSISTANT.value, ChatRole.ASSISTANT):
        messages.insert(0, ChatEntry.user(content="."))
    return messages


async def predict_stream(
    request: Request,
    model: str,
    messages: list[ChatEntry],
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
    cohere_api_key: str = "",
    groq_api_key: str = "",
    together_api_key: str = "",
    jina_api_key: str = "",
    voyage_api_key: str = "",
    **hyperparams,
) -> AsyncGenerator[ChatCompletionChunk, None]:
    hyperparams.pop("stream", False)
    input_len = message_len(messages)
    messages = _check_messages(messages)
    messages = [m.model_dump(mode="json", exclude_none=True) for m in messages]

    output_len = 0
    try:
        if len(model) == 0:
            models = await model_names(
                prefer=DEFAULT_CHAT_MODEL,
                capabilities=["chat"],
                openai_api_key=openai_api_key,
                anthropic_api_key=anthropic_api_key,
                gemini_api_key=gemini_api_key,
                cohere_api_key=cohere_api_key,
                groq_api_key=groq_api_key,
                together_api_key=together_api_key,
                jina_api_key=jina_api_key,
                voyage_api_key=voyage_api_key,
            )
            model = models[0]
        api_key = get_api_key(
            model,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
        _log_messages = [{"role": m["role"], "content_len": len(m["content"])} for m in messages]
        logger.info(
            f"LiteLLM stream request: {dict(model=model, messages=_log_messages, **hyperparams)}"
        )
        response = await get_llm_router().acompletion(
            model=model,
            messages=messages,
            api_key=api_key,
            stream=True,
            **hyperparams,
        )

        async for chunk in response:
            chunk_message = chunk["choices"][0]["delta"]
            if "content" in chunk_message:
                output_len += 1
            yield ChatCompletionChunk(
                id=request.state.id,
                object="chat.completion.chunk",
                created=int(time()),
                model=model,
                usage=None,
                choices=[
                    ChatCompletionChoiceDelta(
                        message=ChatEntry.assistant(
                            choice["delta"].get("content", "")
                            if choice["delta"].get("content", "") is not None
                            else ""
                        ),
                        index=choice["index"],
                        finish_reason=choice.get(
                            "finish_reason", chunk.get("finish_reason", None)
                        ),
                    )
                    for choice in chunk["choices"]
                ],
            )
        request.state.billing_manager.create_llm_events(
            model=model,
            input_tokens=input_len,
            output_tokens=output_len,
        )
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


async def predict(
    request: Request,
    model: str,
    messages: list[ChatEntry],
    openai_api_key: str = "",
    anthropic_api_key: str = "",
    gemini_api_key: str = "",
    cohere_api_key: str = "",
    groq_api_key: str = "",
    together_api_key: str = "",
    jina_api_key: str = "",
    voyage_api_key: str = "",
    **hyperparams,
) -> ChatCompletionChunk:
    hyperparams.pop("stream", False)
    messages = _check_messages(messages)
    messages = [m.model_dump(mode="json", exclude_none=True) for m in messages]
    try:
        if len(model) == 0:
            models = await model_names(
                prefer=DEFAULT_CHAT_MODEL,
                capabilities=["chat"],
                openai_api_key=openai_api_key,
                anthropic_api_key=anthropic_api_key,
                gemini_api_key=gemini_api_key,
                cohere_api_key=cohere_api_key,
                groq_api_key=groq_api_key,
                together_api_key=together_api_key,
                jina_api_key=jina_api_key,
                voyage_api_key=voyage_api_key,
            )
            model = models[0]
        api_key = get_api_key(
            model,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
        _log_messages = [{"role": m["role"], "content_len": len(m["content"])} for m in messages]
        logger.info(f"LiteLLM request: {dict(model=model, messages=_log_messages, **hyperparams)}")
        response = await get_llm_router().acompletion(
            model=model,
            messages=messages,
            api_key=api_key,
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
        logger.warning(f"LiteLLM {model} completion usage: {usage}")
        input_len = usage.get("prompt_tokens")
        output_len = usage.get("completion_tokens")
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
