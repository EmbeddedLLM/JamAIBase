from asyncio.coroutines import iscoroutine
from typing import AsyncGenerator, Generator, Type

import pytest
from flaky import flaky
from loguru import logger

from jamaibase import JamAI, JamAIAsync
from jamaibase import protocol as p

CLIENT_CLS = [JamAI, JamAIAsync]


async def run(fn, *args, **kwargs):
    ret = fn(*args, **kwargs)
    if iscoroutine(ret):
        return await ret
    return ret


async def run_gen_async(fn, *args, **kwargs):
    ret = fn(*args, **kwargs)
    if iscoroutine(ret):
        ret = await ret
    if isinstance(ret, AsyncGenerator):
        async for item in ret:
            yield item
    else:
        yield ret


def run_gen_sync(fn, *args, **kwargs):
    ret = fn(*args, **kwargs)
    if isinstance(ret, Generator):
        for item in ret:
            yield item
    else:
        yield ret


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_model_info(client_cls: Type[JamAI | JamAIAsync]):
    jamai = client_cls(project_id="", api_key="")
    response = await run(jamai.model_info)

    # Get all model info
    assert isinstance(response, p.ModelInfoResponse)
    assert len(response.data) > 0
    assert isinstance(response.data[0], p.ModelInfo)
    model = response.data[0]
    assert isinstance(model.id, str)
    assert isinstance(model.context_length, int)
    assert model.context_length > 0
    assert isinstance(model.languages, list)
    assert len(model.languages) > 0

    # Get specific model info
    response = await run(jamai.model_info, name=model.id)
    assert isinstance(response, p.ModelInfoResponse)
    assert len(response.data) == 1
    assert response.data[0].id == model.id

    # Filter based on capability
    response = await run(jamai.model_info, capabilities=["chat"])
    assert isinstance(response, p.ModelInfoResponse)
    for m in response.data:
        assert "chat" in m.capabilities
        assert "embed" not in m.capabilities
        assert "rerank" not in m.capabilities

    response = await run(jamai.model_info, capabilities=["chat", "image"])
    assert isinstance(response, p.ModelInfoResponse)
    for m in response.data:
        assert "chat" in m.capabilities
        assert "image" in m.capabilities
        assert "embed" not in m.capabilities
        assert "rerank" not in m.capabilities

    response = await run(jamai.model_info, capabilities=["embed"])
    assert isinstance(response, p.ModelInfoResponse)
    for m in response.data:
        assert "chat" not in m.capabilities
        assert "embed" in m.capabilities
        assert "rerank" not in m.capabilities

    response = await run(jamai.model_info, capabilities=["rerank"])
    assert isinstance(response, p.ModelInfoResponse)
    for m in response.data:
        assert "chat" not in m.capabilities
        assert "embed" not in m.capabilities
        assert "rerank" in m.capabilities


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_model_names(client_cls: Type[JamAI | JamAIAsync]):
    jamai = client_cls(project_id="", api_key="")
    response = await run(jamai.model_names)
    logger.info(f"response: {response}")
    logger.info(f"type(response): {type(response)}")

    # Get all model info
    assert isinstance(response, list)
    assert len(response) > 0
    assert all(isinstance(r, str) for r in response)
    model = response[0]

    # Get specific model info
    response = await run(jamai.model_names, prefer=model)
    assert isinstance(response, list)
    assert len(response) > 0
    assert response[0] == model

    # Preferred model can be non-existent
    response = await run(jamai.model_names, prefer="dummy")
    assert isinstance(response, list)
    assert len(response) > 0
    assert isinstance(response[0], str)

    # Filter based on capability
    response = await run(jamai.model_names, capabilities=["chat"])
    assert isinstance(response, list)
    name_cat = ",".join(response)
    assert "gpt-3.5-turbo" in name_cat
    assert "embedding" not in name_cat
    assert "rerank" not in name_cat

    # response = await run(jamai.model_names, capabilities=["chat", "image"])
    # assert isinstance(response, list)
    # name_cat = ",".join(response)
    # assert "gpt-4" in name_cat
    # assert "embedding" not in name_cat
    # assert "rerank" not in name_cat

    response = await run(jamai.model_names, capabilities=["embed"])
    assert isinstance(response, list)
    name_cat = ",".join(response)
    assert "gpt-3.5-turbo" not in name_cat
    assert "embedding" in name_cat
    assert "rerank" not in name_cat

    response = await run(jamai.model_names, capabilities=["rerank"])
    assert isinstance(response, list)
    name_cat = ",".join(response)
    assert "gpt-3.5-turbo" not in name_cat
    assert "embedding" not in name_cat
    assert "rerank" in name_cat


def _get_chat_request(model: str, **kwargs):
    request = p.ChatRequest(
        id="test",
        model=model,
        messages=[
            p.ChatEntry.system("You are a concise assistant."),
            p.ChatEntry.user(f"What is a llama?"),
        ],
        temperature=0.001,
        top_p=0.001,
        max_tokens=3,
        **kwargs,
    )
    return request


def _get_models() -> list[str]:
    models = JamAI(project_id="", api_key="").model_names(capabilities=["chat"])
    providers = list(set(m.split("/")[0] for m in models))
    selected = []
    for provider in providers:
        if provider.startswith("ellm"):
            continue
        selected.append([m for m in models if m.startswith(provider)][0])
    return selected


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", _get_models())
async def test_chat_completion(client_cls: Type[JamAI | JamAIAsync], model: str):
    jamai = client_cls(project_id="", api_key="")

    # Non-streaming
    request = _get_chat_request(model, stream=False)
    if isinstance(jamai, JamAIAsync):
        response = [r async for r in run_gen_async(jamai.generate_chat_completions, request)]
    else:
        response = [r for r in run_gen_sync(jamai.generate_chat_completions, request)]
    assert len(response) == 1
    response = response[0]
    assert isinstance(response, p.ChatCompletionChunk)
    assert isinstance(response.text, str)
    assert len(response.text) > 1
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.references is None

    # Streaming
    request.stream = True
    if isinstance(jamai, JamAIAsync):
        responses = [r async for r in run_gen_async(jamai.generate_chat_completions, request)]
    else:
        responses = [r for r in run_gen_sync(jamai.generate_chat_completions, request)]
    assert len(responses) > 0
    assert all(isinstance(r, p.ChatCompletionChunk) for r in responses)
    assert all(isinstance(r.text, str) for r in responses)
    assert len("".join(r.text for r in responses)) > 1
    assert all(r.references is None for r in responses)
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", _get_models())
async def test_chat_opener(client_cls: Type[JamAI | JamAIAsync], model: str):
    jamai = client_cls(project_id="", api_key="")

    # Non-streaming
    request = p.ChatRequest(
        id="test",
        model=model,
        messages=[
            p.ChatEntry.system("You are a concise assistant."),
            p.ChatEntry.assistant("Hi, I am Sam. How may I help you?"),
            p.ChatEntry.user("What is your first message?"),
        ],
        temperature=0.001,
        top_p=0.001,
        max_tokens=30,
        stream=False,
    )
    if isinstance(jamai, JamAIAsync):
        response = [r async for r in run_gen_async(jamai.generate_chat_completions, request)]
    else:
        response = [r for r in run_gen_sync(jamai.generate_chat_completions, request)]
    assert len(response) == 1
    response = response[0]
    assert isinstance(response, p.ChatCompletionChunk)
    assert isinstance(response.text, str)
    assert "Sam" in response.text
    assert len(response.text) > 1
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.references is None

    # Streaming
    request.stream = True
    if isinstance(jamai, JamAIAsync):
        responses = [r async for r in run_gen_async(jamai.generate_chat_completions, request)]
    else:
        responses = [r for r in run_gen_sync(jamai.generate_chat_completions, request)]
    assert len(responses) > 0
    assert all(isinstance(r, p.ChatCompletionChunk) for r in responses)
    assert all(isinstance(r.text, str) for r in responses)
    assert "Sam" in "".join(r.text for r in responses)
    assert all(r.references is None for r in responses)
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", _get_models())
async def test_chat_user_only(client_cls: Type[JamAI | JamAIAsync], model: str):
    jamai = client_cls(project_id="", api_key="")

    # Non-streaming
    request = p.ChatRequest(
        id="test",
        model=model,
        messages=[p.ChatEntry.user("Hi there")],
        temperature=0.001,
        top_p=0.001,
        max_tokens=30,
        stream=False,
    )
    if isinstance(jamai, JamAIAsync):
        response = [r async for r in run_gen_async(jamai.generate_chat_completions, request)]
    else:
        response = [r for r in run_gen_sync(jamai.generate_chat_completions, request)]
    assert len(response) == 1
    response = response[0]
    assert isinstance(response, p.ChatCompletionChunk)
    assert isinstance(response.text, str)
    assert len(response.text) > 1
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.references is None

    # Streaming
    request.stream = True
    if isinstance(jamai, JamAIAsync):
        responses = [r async for r in run_gen_async(jamai.generate_chat_completions, request)]
    else:
        responses = [r for r in run_gen_sync(jamai.generate_chat_completions, request)]
    assert len(responses) > 0
    assert all(isinstance(r, p.ChatCompletionChunk) for r in responses)
    assert all(isinstance(r.text, str) for r in responses)
    assert len("".join(r.text for r in responses)) > 1
    assert all(r.references is None for r in responses)
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", _get_models())
async def test_chat_system_only(client_cls: Type[JamAI | JamAIAsync], model: str):
    jamai = client_cls(project_id="", api_key="")

    # Non-streaming
    request = p.ChatRequest(
        id="test",
        model=model,
        messages=[p.ChatEntry.system("You are a concise assistant.")],
        temperature=0.001,
        top_p=0.001,
        max_tokens=30,
        stream=False,
    )
    if isinstance(jamai, JamAIAsync):
        response = [r async for r in run_gen_async(jamai.generate_chat_completions, request)]
    else:
        response = [r for r in run_gen_sync(jamai.generate_chat_completions, request)]
    assert len(response) == 1
    response = response[0]
    assert isinstance(response, p.ChatCompletionChunk)
    assert isinstance(response.text, str)
    assert len(response.text) > 1
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.references is None

    # Streaming
    request.stream = True
    if isinstance(jamai, JamAIAsync):
        responses = [r async for r in run_gen_async(jamai.generate_chat_completions, request)]
    else:
        responses = [r for r in run_gen_sync(jamai.generate_chat_completions, request)]
    assert len(responses) > 0
    assert all(isinstance(r, p.ChatCompletionChunk) for r in responses)
    assert all(isinstance(r.text, str) for r in responses)
    assert len("".join(r.text for r in responses)) > 1
    assert all(r.references is None for r in responses)
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", ["openai/gpt-3.5-turbo"])
async def test_long_chat_completion(client_cls: Type[JamAI | JamAIAsync], model: str):
    jamai = client_cls(project_id="", api_key="")

    # Streaming
    request = p.ChatRequest(
        id="test",
        model=model,
        messages=[
            p.ChatEntry.system("You are a concise assistant."),
            p.ChatEntry.user(" ".join(["What is a llama?"] * 5000)),
        ],
        temperature=0.001,
        top_p=0.001,
        max_tokens=50,
        stream=True,
    )
    if isinstance(jamai, JamAIAsync):
        responses = [r async for r in run_gen_async(jamai.generate_chat_completions, request)]
    else:
        responses = [r for r in run_gen_sync(jamai.generate_chat_completions, request)]
    assert len(responses) > 0
    assert all(isinstance(r, p.ChatCompletionChunk) for r in responses)
    assert responses[-1].finish_reason == "error"
    assert all(r.references is None for r in responses)


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_chat_opener(JamAI, model="anthropic/claude-3.5-sonnet"))
