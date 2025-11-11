import base64
import hashlib
import io
import re
from asyncio import sleep
from contextlib import asynccontextmanager
from time import time
from typing import Any

import httpx
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse, StreamingResponse
from loguru import logger
from PIL import Image
from pydantic import BaseModel, Field
from pydub import AudioSegment

from owl.configs import CACHE, ENV_CONFIG
from owl.types import (
    AudioContent,
    ChatCompletionChoice,
    ChatCompletionChunkResponse,
    ChatCompletionDelta,
    ChatCompletionMessage,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatRequest,
    ChatRole,
    CompletionUsageDetails,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingResponseData,
    EmbeddingUsage,
    ImageContent,
    PromptUsageDetails,
    SanitisedNonEmptyStr,
    TextContent,
    UserAgent,
)
from owl.utils import uuid7_str
from owl.utils.exceptions import BadInputError, JamaiException
from owl.utils.handlers import exception_handler, make_request_log_str, path_not_found_handler
from owl.utils.logging import setup_logger_sinks, suppress_logging_handlers

# Setup logging
setup_logger_sinks(None)
suppress_logging_handlers(["uvicorn", "litellm", "pottery"], True)


class ChatCompletionRequest(ChatRequest):
    stream: bool = False  # Set default to False


class ModelSpec(BaseModel, validate_assignment=True):
    id: SanitisedNonEmptyStr = Field(description="Model ID")
    ttft_ms: int = Field(0, description="Time to first token (TTFT)")
    tpot_ms: int = Field(0, description="Time per output token (TPOT)")
    max_context_length: int = Field(int(1e12), description="Max context length")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info(f"Using configuration: {ENV_CONFIG}")
    yield
    logger.info("Shutting down...")

    # Close Redis connection
    logger.info("Closing Redis connection.")
    try:
        await CACHE.aclose()
    except Exception as e:
        logger.warning(f"Failed to close Redis connection: {repr(e)}")


app = FastAPI(title="Mock LLM", lifespan=lifespan)
app.add_exception_handler(JamaiException, exception_handler)  # Suppress starlette traceback
app.add_exception_handler(Exception, exception_handler)
app.add_exception_handler(404, path_not_found_handler)


def _describe_image(image_content: ImageContent) -> str:
    """
    Describe the image based on an `ImageContent` object.

    Args:
        image_content (ImageContent): The `ImageContent` object containing the image URL or base64 data.

    Returns:
        description (str): A brief description of the image.
    """
    # Get image data from URL or base64
    url = image_content.image_url.url

    if url.startswith("data:"):
        # Handle base64 encoded image
        mime_match = re.match(r"data:([^;]+);base64,", url)
        mime_type = mime_match.group(1) if mime_match else "image/unknown"
        base64_data = url.split(",", 1)[1]
        image_data = base64.b64decode(base64_data)
        img = Image.open(io.BytesIO(image_data))
    else:
        # Handle URL using httpx instead of requests
        with httpx.Client() as client:
            response = client.get(url)
            response.raise_for_status()
            mime_type = response.headers.get("Content-Type", "image/unknown")
            img = Image.open(io.BytesIO(response.content))

    # Convert to numpy array for calculations
    img_array = np.asarray(img)

    # Get dimensions (height, width, channels)
    if len(img_array.shape) == 2:  # Grayscale image
        height, width = img_array.shape
        channels = 1
        img_array = img_array.reshape((height, width, 1))
    else:
        height, width, channels = img_array.shape

    # Calculate mean and standard deviation
    mean_value = float(np.mean(img_array))
    std_value = float(np.std(img_array))

    return (
        f"There is an image with MIME type [{mime_type}], "
        f"shape [{(height, width, channels)}], mean [{mean_value:,.1f}] and std [{std_value:,.1f}]."
    )


def _describe_audio(audio_content: AudioContent) -> str:
    """
    Describe the audio based on an `AudioContent` object.

    Args:
        audio_content (AudioContent): The `AudioContent` object containing the base64 encoded audio data.

    Returns:
        description (str): A brief description of the audio.
    """
    # Format to MIME type mapping
    format_to_mime: dict[str, str] = {"mp3": "audio/mpeg", "wav": "audio/wav"}
    # Get audio data and format
    base64_data = audio_content.input_audio.data
    audio_format = audio_content.input_audio.format
    # Decode base64 data
    audio_data = base64.b64decode(base64_data)
    # Get MIME type
    mime_type = format_to_mime.get(audio_format, f"audio/{audio_format}")
    # Load audio using pydub
    audio_file = io.BytesIO(audio_data)

    if audio_format == "mp3":
        audio = AudioSegment.from_mp3(audio_file)
    elif audio_format == "wav":
        audio = AudioSegment.from_wav(audio_file)
    else:
        # This shouldn't happen due to the Literal type constraint, but just in case
        raise BadInputError(f'Unsupported audio format: "{audio_format}".')

    # Calculate duration in seconds
    duration_sec = len(audio) / 1000.0  # pydub uses milliseconds
    return (
        f"There is an audio with MIME type [{mime_type}], duration [{duration_sec:,.1f}] seconds."
    )


def _describe_text(text_content: str | TextContent) -> str:
    """
    Describe the text based on a `TextContent` object.

    Args:
        text_content (str | TextContent): A string or `TextContent` object containing the text.

    Returns:
        description (TextDescription): A `TextDescription` object with text metadata.
    """
    if isinstance(text_content, str):
        text = text_content
    else:
        text = text_content.text
    text = text.strip()
    num_tokens = 0 if text == "" else len(text.split(" "))
    return f"There is a text with [{num_tokens:,d}] tokens."


def _execute_python(code: str, context: dict[str, Any] | None = None) -> Any:
    """
    Execute a string containing Python code and return its return value.
    This version wraps the code in a function to properly capture return values.

    Args:
        code (str): The Python code to execute
        context (dict[str, Any] | None, optional):
            Dictionary of variables to make available in the execution context.
            Defaults to None.

    Returns:
        value (Any): The return value of the executed code.
    """
    if context is None:
        context = {}
    # Wrap the code in a function to capture return values
    wrapped_code = [
        "def __temp_function():",
        "\n".join("    " + f"{k} = {repr(v)}" for k, v in context.items()),
        "\n".join("    " + line for line in code.strip().split("\n")),
        "__return_value__ = __temp_function()",
    ]
    # Execute the wrapped code
    local_namespace = {}
    exec("\n".join(wrapped_code), globals(), local_namespace)
    return local_namespace.get("__return_value__")


def _parse_chat_model_id(model_id: str) -> ModelSpec:
    spec = ModelSpec(id=model_id)
    # Time to first token (TTFT)
    if match := re.search(r"-ttft-(\d+)", model_id):
        spec.ttft_ms = int(match.group(1))
    # Time per output token (TPOT)
    if match := re.search(r"-tpot-(\d+)", model_id):
        spec.tpot_ms = int(match.group(1))
    # Max context length
    if match := re.search(r"-context-(\d+)", model_id):
        spec.max_context_length = int(match.group(1))
    return spec


@app.post("/v1/chat/completions")
async def chat_completion(body: ChatCompletionRequest):
    logger.info(f"Chat completion request: {body}")
    model_spec = _parse_chat_model_id(body.model)
    num_input_tokens = len(" ".join(m.text_content for m in body.messages).split(" "))
    user_messages = [m for m in body.messages if m.role == ChatRole.USER]

    # Test context length error handling
    if num_input_tokens > model_spec.max_context_length:
        return ORJSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": (
                        f"This model's maximum context length is {model_spec.max_context_length} tokens. "
                        f"However, your messages resulted in {num_input_tokens} tokens. "
                        "Please reduce the length of the messages."
                    ),
                    "type": "invalid_request_error",
                    "param": "messages",
                    "code": "context_length_exceeded",
                }
            },
        )
    elif num_input_tokens + body.max_tokens > model_spec.max_context_length:
        return ORJSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": (
                        f"This model's maximum context length is {model_spec.max_context_length} tokens. "
                        f"However, you requested {num_input_tokens + body.max_tokens} tokens "
                        f"({num_input_tokens} in the messages, {body.max_tokens} in the completion). "
                        "Please reduce the length of the messages or completion."
                    ),
                    "type": "invalid_request_error",
                    "param": "messages",
                    "code": "context_length_exceeded",
                }
            },
        )

    if "lorem" in model_spec.id:
        completion_tokens = "Lorem ipsum dolor sit amet, consectetur adipiscing elit.".split(" ")
        num_completion_tokens = body.max_tokens
    elif "describe" in model_spec.id:
        descriptions = []
        if body.messages[0].role == ChatRole.SYSTEM:
            descriptions.append(f"System prompt: {_describe_text(body.messages[0].content)}")
        if len(user_messages) == 0:
            descriptions.append(_describe_text(""))
        for message in user_messages:
            if isinstance(message.content, str):
                descriptions.append(_describe_text(message.content))
            else:
                for c in message.content:
                    if isinstance(c, ImageContent):
                        descriptions.append(_describe_image(c))
                    elif isinstance(c, AudioContent):
                        descriptions.append(_describe_audio(c))
                    elif isinstance(c, TextContent):
                        descriptions.append(_describe_text(c))
                    else:
                        raise BadInputError(f'Unknown content type: "{type(c)}".')
        completion_tokens = "\n".join(descriptions).split(" ")
        num_completion_tokens = len(completion_tokens)
    elif "echo-request" in model_spec.id:
        completion_tokens = body.model_dump_json().split(" ")
        num_completion_tokens = len(completion_tokens)
    elif "echo-prompt" in model_spec.id:
        prompt_concat = " ".join(m.text_content for m in user_messages)
        if body.messages[0].role == ChatRole.SYSTEM:
            prompt_concat = f"{body.messages[0].text_content} {prompt_concat}"
        completion_tokens = prompt_concat.strip().split(" ")
        num_completion_tokens = len(completion_tokens)
    elif "python" in model_spec.id:
        if len(user_messages) == 0:
            result = None
        else:
            result = _execute_python(user_messages[-1].text_content)
        completion_tokens = [repr(result)]
        num_completion_tokens = len(completion_tokens)
    else:
        raise BadInputError(f'Unknown model: "{model_spec.id}"')

    if body.stream:

        async def stream_response():
            if model_spec.ttft_ms > 0:
                await sleep(model_spec.ttft_ms / 1000)
            # Role chunk
            for i in range(body.n):
                chunk = ChatCompletionChunkResponse(
                    id=body.id,
                    model=model_spec.id,
                    choices=[
                        ChatCompletionChoice(
                            index=i,
                            delta=ChatCompletionDelta(role="assistant", content="", refusal=None),
                            logprobs=None,
                            finish_reason=None,
                        )
                    ],
                    usage=None,
                    object="chat.completion.chunk",
                    created=int(time()),
                    system_fingerprint=None,
                    service_tier=None,
                )
                yield f"data: {chunk.model_dump_json(exclude_unset=True)}\n\n"
            # Content chunks
            for t in range(num_completion_tokens):
                # If this is the last token
                if t == num_completion_tokens - 1:
                    content = f"{completion_tokens[t % len(completion_tokens)]}"
                else:
                    content = f"{completion_tokens[t % len(completion_tokens)]} "
                for i in range(body.n):
                    if model_spec.tpot_ms > 0:
                        await sleep(model_spec.tpot_ms / 1000)
                    chunk = ChatCompletionChunkResponse(
                        id=body.id,
                        model=model_spec.id,
                        choices=[
                            ChatCompletionChoice(
                                index=i,
                                delta=ChatCompletionDelta(content=content),
                                logprobs=None,
                                finish_reason=None,
                            )
                        ],
                        usage=None,
                        object="chat.completion.chunk",
                        created=int(time()),
                        system_fingerprint=None,
                        service_tier=None,
                    )
                    yield f"data: {chunk.model_dump_json(exclude_unset=True)}\n\n"
            # Finish reason chunk
            for i in range(body.n):
                chunk = ChatCompletionChunkResponse(
                    id=body.id,
                    model=model_spec.id,
                    choices=[
                        ChatCompletionChoice(
                            index=i,
                            logprobs=None,
                            finish_reason="length"
                            if num_completion_tokens == body.max_tokens
                            else "stop",
                        )
                    ],
                    usage=None,
                    object="chat.completion.chunk",
                    created=int(time()),
                    system_fingerprint=None,
                    service_tier=None,
                )
                yield f"data: {chunk.model_dump_json(exclude_unset=True)}\n\n"
            # Usage chunk
            chunk = ChatCompletionChunkResponse(
                id=body.id,
                model=model_spec.id,
                choices=[],
                usage=ChatCompletionUsage(
                    prompt_tokens=num_input_tokens,
                    completion_tokens=num_completion_tokens,
                    total_tokens=num_input_tokens + num_completion_tokens,
                    prompt_tokens_details=PromptUsageDetails(cached_tokens=0, audio_tokens=0),
                    completion_tokens_details=CompletionUsageDetails(
                        audio_tokens=0,
                        reasoning_tokens=0,
                        accepted_prediction_tokens=0,
                        rejected_prediction_tokens=0,
                    ),
                ),
                object="chat.completion.chunk",
                created=int(time()),
                system_fingerprint=None,
                service_tier=None,
            )
            yield f"data: {chunk.model_dump_json(exclude_unset=True)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_response(), media_type="text/event-stream")

    # Non-stream
    if (model_spec.ttft_ms + model_spec.tpot_ms) > 0:
        await sleep((model_spec.ttft_ms + model_spec.tpot_ms * len(completion_tokens)) / 1000)
    response = ChatCompletionResponse(
        id=body.id,
        model=model_spec.id,
        choices=[
            ChatCompletionChoice(
                index=i,
                message=ChatCompletionMessage(
                    content=" ".join(
                        completion_tokens[t % len(completion_tokens)]
                        for t in range(num_completion_tokens)
                    )
                ),
                logprobs=None,
                finish_reason="length",
            )
            for i in range(body.n)
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=num_input_tokens,
            completion_tokens=num_completion_tokens,
            total_tokens=num_input_tokens + num_completion_tokens,
        ),
    )
    return response


def _parse_embedding_model_id(model_id: str, fallback_dim: int = 768) -> int:
    """
    Extract the embedding dimension from the model_id if present (e.g. '...-dim-768').
    Otherwise return fallback_dim.
    """
    if match := re.search(r"-dim-(\d+)", model_id):
        return int(match.group(1))
    return fallback_dim


@app.post("/v1/embeddings")
async def embeddings(body: EmbeddingRequest) -> EmbeddingResponse:
    """
    Mock embedding endpoint that deterministically generates embeddings by
    seeding NumPy with a hash derived from each input string.
    """
    # Validate inputs
    inputs: list[str]
    if isinstance(body.input, str):
        text = body.input.strip()
        if text == "":
            raise BadInputError("Input cannot be an empty string.")
        inputs = [text]
    else:
        inputs = []
        for i, s in enumerate(body.input):
            t = s.strip()
            if t == "":
                raise BadInputError(f"Input at index {i} cannot be an empty string.")
            inputs.append(t)

    # Determine embedding dimension
    dim: int
    if body.dimensions is not None:
        if body.dimensions <= 0:
            raise BadInputError("`dimensions` must be a positive integer.")
        dim = body.dimensions
    else:
        dim = _parse_embedding_model_id(body.model, fallback_dim=768)

    # Generate deterministic embeddings per input
    data: list[EmbeddingResponseData] = []
    prompt_token_count = 0

    for idx, text in enumerate(inputs):
        # Naive token counting by whitespace
        prompt_token_count += 0 if text == "" else len(text.split())
        # Deterministic seed from SHA-256
        sha = hashlib.blake2b(text.encode("utf-8")).hexdigest()
        seed = int(sha[:16], 16) % (2**32)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(size=dim, dtype=np.float32)
        if body.encoding_format == "float":
            emb_value: list[float] | str = vec.tolist()
        else:
            # base64 encoding of float32 bytes
            emb_value = base64.b64encode(vec.tobytes()).decode("ascii")
        data.append(EmbeddingResponseData(embedding=emb_value, index=idx))

    return EmbeddingResponse(
        data=data,
        model=body.model,
        usage=EmbeddingUsage(
            prompt_tokens=prompt_token_count,
            total_tokens=prompt_token_count,
        ),
    )


@app.get("/health", tags=["Health"])
async def health() -> ORJSONResponse:
    """Health check."""
    return ORJSONResponse(status_code=200, content={})


@app.middleware("http")
async def log_request(request: Request, call_next):
    """
    Args:
        request (Request): Starlette request object.
        call_next (Callable): A function that will receive the request,
            pass it to the path operation, and returns the response generated.

    Returns:
        response (Response): Response of the path operation.
    """
    # Set request state
    request_id = request.headers.get("x-request-id", uuid7_str())
    request.state.id = request_id
    request.state.user_agent = UserAgent.from_user_agent_string(
        request.headers.get("user-agent", "")
    )
    # Call request
    logger.info(make_request_log_str(request))
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    logger.info(make_request_log_str(request, response.status_code))
    return response


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting LLM test server on {ENV_CONFIG.host}:{ENV_CONFIG.port + 1}")
    uvicorn.run(
        "owl.entrypoints.llm:app",
        reload=False,
        host=ENV_CONFIG.host,
        port=ENV_CONFIG.port + 1,
        workers=2,
        limit_concurrency=100,
    )

"""
OpenAI Chat Completion SSE


{
"error": {
    "message": "This model's maximum context length is 16385 tokens. However, your messages resulted in 19901 tokens. Please reduce the length of the messages.",
    "type": "invalid_request_error",
    "param": "messages",
    "code": "context_length_exceeded"
    }
}

{
  "error": {
    "message": "This model's maximum context length is 16385 tokens. However, you requested 18242 tokens (16242 in the messages, 2000 in the completion). Please reduce the length of the messages or completion.",
    "type": "invalid_request_error",
    "param": "messages",
    "code": "context_length_exceeded"
  }
}

{
  "id": "chatcmpl-AtBWW4Kf8NoM4WDBaNSBLR8fD0fc6",
  "object": "chat.completion",
  "created": 1737715700,
  "model": "gpt-3.5-turbo-1106",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "\n\nS",
        "refusal": null
      },
      "logprobs": null,
      "finish_reason": "length"
    }
  ],
  "usage": {
    "prompt_tokens": 17,
    "completion_tokens": 2,
    "total_tokens": 19,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "audio_tokens": 0
    },
    "completion_tokens_details": {
      "reasoning_tokens": 0,
      "audio_tokens": 0,
      "accepted_prediction_tokens": 0,
      "rejected_prediction_tokens": 0
    }
  },
  "service_tier": "default",
  "system_fingerprint": "fp_2f141ce944"
}

data: {"id":"chatcmpl-AtBSi41j2M6DGdAzfHgpTKjKKqtMy","object":"chat.completion.chunk","created":1737715464,"model":"gpt-3.5-turbo-1106","service_tier":"default","system_fingerprint":"fp_7fe28551a8","choices":[{"index":0,"delta":{"role":"assistant","content":"","refusal":null},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-AtBSi41j2M6DGdAzfHgpTKjKKqtMy","object":"chat.completion.chunk","created":1737715464,"model":"gpt-3.5-turbo-1106","service_tier":"default","system_fingerprint":"fp_7fe28551a8","choices":[{"index":0,"delta":{"content":"S"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-AtBSi41j2M6DGdAzfHgpTKjKKqtMy","object":"chat.completion.chunk","created":1737715464,"model":"gpt-3.5-turbo-1106","service_tier":"default","system_fingerprint":"fp_7fe28551a8","choices":[{"index":0,"delta":{},"logprobs":null,"finish_reason":"length"}]}

data: {"id":"chatcmpl-AtBbXar0rpsdn69L9cIeeu88frXVd","object":"chat.completion.chunk","created":1737716011,"model":"gpt-3.5-turbo-1106","service_tier":"default","system_fingerprint":"fp_2f141ce944","choices":[],"usage":{"prompt_tokens":17,"completion_tokens":2,"total_tokens":19,"prompt_tokens_details":{"cached_tokens":0,"audio_tokens":0},"completion_tokens_details":{"reasoning_tokens":0,"audio_tokens":0,"accepted_prediction_tokens":0,"rejected_prediction_tokens":0}}}

data: [DONE]
"""
