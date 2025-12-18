import pytest
from pydantic import ValidationError

from owl.types import (
    ChatCompletionChoice,
    ChatCompletionChunkResponse,
    ChatCompletionDelta,
    ChatCompletionMessage,
    ChatCompletionResponse,
    ChatCompletionUsage,
    MultiRowAddRequestWithLimit,
    MultiRowUpdateRequestWithLimit,
)

REQUEST_ID = "chatcmpl-AtBWW4Kf8NoM4WDBaNSBLR8fD0fc6"
MODEL = "gpt-3.5-turbo"
CONTENT = "Hello"
SERVICE_TIER = "default"
SYSTEM_FINGERPRINT = "fp_2f141ce944"


@pytest.mark.parametrize(
    "body",
    [
        # Role chunk
        ChatCompletionChunkResponse(
            id=REQUEST_ID,
            model=MODEL,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    delta=ChatCompletionDelta(role="assistant", content="", refusal=None),
                    logprobs=None,
                    finish_reason=None,
                )
            ],
        ),
        # Content chunks
        ChatCompletionChunkResponse(
            id=REQUEST_ID,
            model=MODEL,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    delta=ChatCompletionDelta(content=CONTENT),
                    logprobs=None,
                    finish_reason=None,
                )
            ],
        ),
        # Finish reason chunk
        ChatCompletionChunkResponse(
            id=REQUEST_ID,
            model=MODEL,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    logprobs=None,
                    finish_reason="length",
                )
            ],
        ),
        # Usage chunk
        ChatCompletionChunkResponse(
            id=REQUEST_ID,
            model=MODEL,
            choices=[],
            usage=ChatCompletionUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=10 + 5,
            ),
        ),
    ],
)
def test_chat_completion_chunk(body: ChatCompletionChunkResponse):
    if len(body.choices) > 0:
        if body.message is None:
            assert body.delta is None
            assert body.content == ""
        else:
            assert isinstance(body.message, ChatCompletionDelta)
            assert isinstance(body.delta, ChatCompletionDelta)
            assert isinstance(body.content, str)
    else:
        assert body.message is None
        assert body.delta is None
        assert body.content == ""
    assert body.finish_reason is None or isinstance(body.finish_reason, str)
    assert isinstance(body.prompt_tokens, int)
    assert isinstance(body.completion_tokens, int)
    assert isinstance(body.total_tokens, int)
    if body.usage is not None:
        assert body.prompt_tokens == body.usage.prompt_tokens
        assert body.completion_tokens == body.usage.completion_tokens
        assert body.total_tokens == body.usage.total_tokens
        assert body.total_tokens == body.prompt_tokens + body.completion_tokens


@pytest.mark.parametrize(
    "body",
    [
        # Non-stream
        ChatCompletionResponse(
            id=REQUEST_ID,
            model=MODEL,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionMessage(content=CONTENT),
                    logprobs=None,
                    finish_reason="length",
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=10 + 5,
            ),
        )
    ],
)
def test_chat_completion(body: ChatCompletionResponse):
    if len(body.choices) > 0:
        assert isinstance(body.message, ChatCompletionMessage)
        assert isinstance(body.content, str)
    else:
        assert body.message is None
        assert body.content is None
    assert body.finish_reason is None or isinstance(body.finish_reason, str)
    assert isinstance(body.prompt_tokens, int)
    assert isinstance(body.completion_tokens, int)
    assert isinstance(body.total_tokens, int)
    assert body.prompt_tokens == body.usage.prompt_tokens
    assert body.completion_tokens == body.usage.completion_tokens
    assert body.total_tokens == body.usage.total_tokens
    assert body.total_tokens == body.prompt_tokens + body.completion_tokens


def test_multirow_add():
    body = MultiRowAddRequestWithLimit(
        table_id="x",
        data=[{"col1": "s3://val1.mp3", "col2": "val2"}],
    )
    assert body.data == [{"col1": "s3://val1.mp3", "col2": "val2"}]
    # Max 100 rows
    with pytest.raises(ValidationError):
        MultiRowAddRequestWithLimit(
            table_id="x",
            data=[{"col1": "val1"} for _ in range(101)],
        )
    MultiRowAddRequestWithLimit(
        table_id="x",
        data=[{"col1": "val1"} for _ in range(100)],
    )
    # Min 1 row
    with pytest.raises(ValidationError):
        MultiRowAddRequestWithLimit(
            table_id="x",
            data=[],
        )
    body = MultiRowAddRequestWithLimit(
        table_id="x",
        data=[{"col1": "val1", "col2": "val2"}],
    )
    assert body.table_id == "x"
    assert body.data == [{"col1": "val1", "col2": "val2"}]


def test_multirow_update():
    body = MultiRowUpdateRequestWithLimit(
        table_id="x",
        data={"row1": {"col1": "s3://val1.mp3", "col2": "val2"}},
    )
    assert body.data == {"row1": {"col1": "s3://val1.mp3", "col2": "val2"}}
    # Max 100 rows
    with pytest.raises(ValidationError):
        MultiRowUpdateRequestWithLimit(
            table_id="x",
            data={str(i): {"col1": "val1"} for i in range(101)},
        )
    MultiRowUpdateRequestWithLimit(
        table_id="x",
        data={str(i): {"col1": "val1"} for i in range(100)},
    )
    # Min 1 row
    with pytest.raises(ValidationError):
        MultiRowUpdateRequestWithLimit(
            table_id="x",
            data={},
        )
    body = MultiRowUpdateRequestWithLimit(
        table_id="x",
        data={"row1": {"col1": "val1", "col2": "val2"}},
    )
    assert body.table_id == "x"
    assert body.data == {"row1": {"col1": "val1", "col2": "val2"}}
