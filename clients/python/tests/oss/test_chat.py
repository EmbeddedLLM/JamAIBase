from typing import Type

import pytest
from flaky import flaky
from loguru import logger

from jamaibase import JamAI, JamAIAsync
from jamaibase import protocol as p
from jamaibase.utils import run

CLIENT_CLS = [JamAI, JamAIAsync]


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_model_info(
    client_cls: Type[JamAI | JamAIAsync],
):
    jamai = client_cls()

    # Get all model info
    response = await run(jamai.model_info)
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
async def test_model_names(
    client_cls: Type[JamAI | JamAIAsync],
):
    jamai = client_cls()
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
    assert "gpt-4o-mini" in name_cat
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
    assert "gpt-4o-mini" not in name_cat
    assert "embedding" in name_cat
    assert "rerank" not in name_cat

    response = await run(jamai.model_names, capabilities=["rerank"])
    assert isinstance(response, list)
    name_cat = ",".join(response)
    assert "gpt-4o-mini" not in name_cat
    assert "embedding" not in name_cat
    assert "rerank" in name_cat


def _get_chat_request(model: str, **kwargs):
    request = p.ChatRequest(
        id="test",
        model=model,
        messages=[
            p.ChatEntry.system("You are a concise assistant."),
            p.ChatEntry.user("What is a llama?"),
        ],
        temperature=0.001,
        top_p=0.001,
        max_tokens=3,
        **kwargs,
    )
    return request


def _get_models(
    capabilities: list[str] = None, return_all: bool = False, exclude_audio: bool = True
) -> list[str]:
    if capabilities is None:
        capabilities = ["chat"]
    models = JamAI().model_names(capabilities=capabilities)
    audio_models = JamAI().model_names(capabilities=["audio"])
    if return_all:
        if exclude_audio:
            return list(set(models) - set(audio_models))
        return models
    if exclude_audio:
        return list(set(models) - set(audio_models))
    providers = sorted(set(m.split("/")[0] for m in models))
    selected = []
    for provider in providers:
        selected.append([m for m in models if m.startswith(provider)][0])
    return selected


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", _get_models(return_all=True))
async def test_chat_completion(
    client_cls: Type[JamAI | JamAIAsync],
    model: str,
):
    jamai = client_cls()

    # Non-streaming
    request = _get_chat_request(model, stream=False)
    response = await run(jamai.generate_chat_completions, request)
    assert isinstance(response, p.ChatCompletionChunk)
    assert isinstance(response.text, str)
    assert len(response.text) > 1
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.usage.total_tokens == response.prompt_tokens + response.completion_tokens
    assert response.references is None

    # Streaming
    request.stream = True
    responses = await run(jamai.generate_chat_completions, request)
    assert len(responses) > 0
    assert all(isinstance(r, p.ChatCompletionChunk) for r in responses)
    assert all(isinstance(r.text, str) for r in responses)
    assert len("".join(r.text for r in responses)) > 1
    assert all(r.references is None for r in responses)
    response = responses[-1]
    assert all(isinstance(r.usage, p.CompletionUsage) for r in responses)
    assert all(isinstance(r.prompt_tokens, int) for r in responses)
    assert all(isinstance(r.completion_tokens, int) for r in responses)
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.usage.total_tokens == response.prompt_tokens + response.completion_tokens


TOOLS = {
    "get_weather": p.Tool(
        type="function",
        function=p.Function(
            name="get_weather",
            description="Get the current weather for a location",
            parameters=p.FunctionParameters(
                type="object",
                properties={
                    "location": p.FunctionParameter(
                        type="string", description="The city and state, e.g. San Francisco, CA"
                    )
                },
                required=["location"],
                additionalProperties=False,
            ),
        ),
    ),
    "calculator": p.Tool(
        type="function",
        function=p.Function(
            name="calculator",
            description="Perform a basic arithmetic operation",
            parameters=p.FunctionParameters(
                type="object",
                properties={
                    "operation": p.FunctionParameter(
                        type="string",
                        description="The arithmetic operation to perform",
                        enum=["add", "subtract", "multiply", "divide"],
                    ),
                    "first_number": p.FunctionParameter(
                        type="number",
                        description="The first number",
                    ),
                    "second_number": p.FunctionParameter(
                        type="number",
                        description="The second number",
                    ),
                },
                required=["operation", "first_number", "second_number"],
                additionalProperties=False,
            ),
        ),
    ),
}

TOOL_PROMPTS = [
    {
        "tool_choice": "get_weather",
        "prompt": "What's the weather like in Paris?",
        "response": ['{"location":'],
    },
    {
        "tool_choice": "calculator",
        "prompt": "Divide 5 by 2.",
        "response": ['"operation":"divide"', "first_number"],
    },
]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", _get_models(capabilities=["tool"], return_all=True))
@pytest.mark.parametrize("tool_prompt", TOOL_PROMPTS)
@pytest.mark.parametrize("set_multi_tools", [False, True])
async def test_chat_completion_with_tools(
    client_cls: Type[JamAI | JamAIAsync], model: str, tool_prompt: dict, set_multi_tools: bool
):
    jamai = client_cls()

    tool_choice = p.ToolChoice(
        type="function",
        function=p.ToolChoiceFunction(
            name=tool_prompt["tool_choice"],
        ),
    )

    # Create a chat request with a tool
    request = p.ChatRequestWithTools(
        id="test",
        model=model,
        messages=[
            p.ChatEntry.system("You are a concise assistant."),
            p.ChatEntry.user(tool_prompt["prompt"]),
        ],
        tools=[v for _, v in TOOLS.items()]
        if set_multi_tools
        else [TOOLS[tool_prompt["tool_choice"]]],
        tool_choice="auto" if model.startswith("openai/") else tool_choice,
        temperature=0.001,
        top_p=0.001,
        max_tokens=50,
        stream=False,
    )

    # Non-streaming
    response = await run(jamai.generate_chat_completions, request)
    assert isinstance(response, p.ChatCompletionChunk)
    assert isinstance(response.text, str)
    assert len(response.text) == 0
    tool_calls = response.message.tool_calls
    assert isinstance(tool_calls, list)
    assert len(tool_calls) == 1
    assert tool_calls[0].function.name == tool_prompt["tool_choice"]
    for argument in tool_prompt["response"]:
        assert argument in tool_calls[0].function.arguments.replace(" ", "")
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.references is None

    # Streaming
    request.stream = True
    responses = await run(jamai.generate_chat_completions, request)
    assert len(responses) > 0
    assert all(isinstance(r, p.ChatCompletionChunk) for r in responses)
    assert all(isinstance(r.text, str) for r in responses)
    assert len("".join(r.text for r in responses)) == 0
    assert all(r.references is None for r in responses)
    response = responses[-1]
    assert all(isinstance(r.usage, p.CompletionUsage) for r in responses)
    assert all(isinstance(r.prompt_tokens, int) for r in responses)
    assert all(isinstance(r.completion_tokens, int) for r in responses)
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.usage.total_tokens == response.prompt_tokens + response.completion_tokens
    arguments_result = ""
    for response in responses:
        tool_calls = response.message.tool_calls
        assert isinstance(tool_calls, list) or tool_calls is None
        if isinstance(tool_calls, list):
            assert len(tool_calls) == 1
            arguments_result += tool_calls[0].function.arguments
            assert (
                tool_calls[0].function.name == tool_prompt["tool_choice"]
                or tool_calls[0].function.name is None
            )
    for argument in tool_prompt["response"]:
        assert argument in arguments_result.replace(" ", "")


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", _get_models())
async def test_chat_opener(
    client_cls: Type[JamAI | JamAIAsync],
    model: str,
):
    jamai = client_cls()

    # Non-streaming
    request = p.ChatRequest(
        id="test",
        model=model,
        messages=[
            p.ChatEntry.system("You are a concise assistant."),
            p.ChatEntry.assistant("Sam has 7 apples."),
            p.ChatEntry.user("How many apples does Sam have?"),
        ],
        temperature=0.001,
        top_p=0.001,
        max_tokens=30,
        stream=False,
    )
    response = await run(jamai.generate_chat_completions, request)
    assert isinstance(response, p.ChatCompletionChunk)
    assert isinstance(response.text, str)
    assert "7" in response.text or "seven" in response.text.lower()
    assert len(response.text) > 1
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.references is None

    # Streaming
    request.stream = True
    responses = await run(jamai.generate_chat_completions, request)
    assert len(responses) > 0
    assert all(isinstance(r, p.ChatCompletionChunk) for r in responses)
    assert all(isinstance(r.text, str) for r in responses)
    assert "7" in response.text or "seven" in response.text.lower()
    assert all(r.references is None for r in responses)
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", _get_models())
async def test_chat_user_only(
    client_cls: Type[JamAI | JamAIAsync],
    model: str,
):
    jamai = client_cls()

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
    response = await run(jamai.generate_chat_completions, request)
    assert isinstance(response, p.ChatCompletionChunk)
    assert isinstance(response.text, str)
    assert len(response.text) > 1
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.references is None

    # Streaming
    request.stream = True
    responses = await run(jamai.generate_chat_completions, request)
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
async def test_chat_system_only(
    client_cls: Type[JamAI | JamAIAsync],
    model: str,
):
    jamai = client_cls()

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
    response = await run(jamai.generate_chat_completions, request)
    assert isinstance(response, p.ChatCompletionChunk)
    assert isinstance(response.text, str)
    assert len(response.text) > 1
    assert isinstance(response.usage, p.CompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.references is None

    # Streaming
    request.stream = True
    responses = await run(jamai.generate_chat_completions, request)
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
@pytest.mark.parametrize("model", ["openai/gpt-4o-mini"])
async def test_long_chat_completion(
    client_cls: Type[JamAI | JamAIAsync],
    model: str,
):
    jamai = client_cls()

    # Streaming
    request = p.ChatRequest(
        id="test",
        model=model,
        messages=[
            p.ChatEntry.system("You are a concise assistant."),
            p.ChatEntry.user(" ".join(["What is a llama?"] * 50000)),
        ],
        temperature=0.001,
        top_p=0.001,
        max_tokens=50,
        stream=True,
    )
    responses = await run(jamai.generate_chat_completions, request)
    assert len(responses) == 1
    assert all(isinstance(r, p.ChatCompletionChunk) for r in responses)
    completion = responses[0]
    assert completion.finish_reason == "error"
    assert "ContextWindowExceededError" in completion.text
    assert all(r.references is None for r in responses)


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_chat_completion(JamAI, model="openai/gpt-4o-mini"))
    asyncio.run(test_chat_completion(JamAIAsync, model="openai/gpt-4o-mini"))
