import base64
from typing import Type

import numpy as np
import pytest

from jamaibase import JamAI, JamAIAsync
from jamaibase import types as t
from jamaibase.utils import run

CLIENT_CLS = [JamAI, JamAIAsync]


def _get_models() -> list[str]:
    models = JamAI().model_names(capabilities=["embed"])
    providers = sorted(set(m.split("/")[0] for m in models))
    selected = []
    for provider in providers:
        selected.append([m for m in models if m.startswith(provider)][0])
    return selected


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("model", _get_models())
@pytest.mark.parametrize(
    "inputs",
    ["What is a llama?", ["What is a llama?", "What is an alpaca?"]],
)
async def test_generate_embeddings(
    client_cls: Type[JamAI | JamAIAsync],
    model: str,
    inputs: list[str] | str,
):
    jamai = client_cls()
    kwargs = {
        "input": inputs,
        "model": model,
        "encoding_format": "float",
    }

    # Get float embeddings
    response = await run(jamai.generate_embeddings, t.EmbeddingRequest(**kwargs))
    assert isinstance(response, t.EmbeddingResponse)
    assert isinstance(response.data, list)
    assert all(isinstance(d, t.EmbeddingResponseData) for d in response.data)
    assert all(isinstance(d.embedding, list) for d in response.data)
    assert isinstance(response.model, str)
    assert isinstance(response.usage, t.CompletionUsage)
    if isinstance(inputs, str):
        assert len(response.data) == 1
    else:
        assert len(response.data) == len(inputs)
    embed_float = np.asarray(response.data[0].embedding, dtype=np.float32)

    # Get base64 embeddings
    kwargs["encoding_format"] = "base64"
    response = await run(jamai.generate_embeddings, t.EmbeddingRequest(**kwargs))
    assert isinstance(response, t.EmbeddingResponse)
    assert isinstance(response.data, list)
    assert all(isinstance(d, t.EmbeddingResponseData) for d in response.data)
    assert all(isinstance(d.embedding, str) for d in response.data)
    assert isinstance(response.model, str)
    assert isinstance(response.usage, t.CompletionUsage)
    if isinstance(inputs, str):
        assert len(response.data) == 1
    else:
        assert len(response.data) == len(inputs)
    embed_base64 = np.frombuffer(base64.b64decode(response.data[0].embedding), dtype=np.float32)
    assert len(embed_float) == len(embed_base64)
    assert np.allclose(embed_float, embed_base64, atol=0.01, rtol=0.05)


if __name__ == "__main__":
    _get_models()
