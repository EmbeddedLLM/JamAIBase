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

    response = await run(jamai.model_names, capabilities=["chat", "image"])
    assert isinstance(response, list)
    name_cat = ",".join(response)
    assert "gpt-4" in name_cat
    assert "embedding" not in name_cat
    assert "rerank" not in name_cat

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
        if provider == "ellm":
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
    assert all(r.references is None for r in responses)


# def pdf_s3files():
#     return [
#         ("tests/pdf/Swire_AR22_e_230406_sample.pdf", 5),
#         ("tests/pdf/sample_tables.pdf", 3),
#         ("tests/pdf/background-checks.pdf", 1),
#     ]


# @pytest.mark.parametrize("pdf_file,page_count", pdf_s3files())
# @pytest.mark.parametrize("fn_suffix", FN_SUFFIXES)
# async def test_load_file(fn_suffix, pdf_file, page_count):
#     client = JamAI(api_base=f"http://127.0.0.1:{PORT}/api")
#     fn = getattr(client, f"load_file{fn_suffix}")

#     response = await fn(pdf_file) if fn_suffix.endswith("async") else fn(pdf_file)
#     logger.debug(response)
#     assert isinstance(response[0], p.Document)
#     assert len(response) == page_count

#     # # overwrite target data
#     # dump_json(
#     #     [res.model_dump() for res in response],
#     #     f"tests/_loader_check/pdfloader__{pdf_file.split('/')[-1]}.json",
#     # )

#     with open(f"tests/_loader_check/pdfloader__{pdf_file.split('/')[-1]}.json", "r") as f:
#         target_data = json.load(f)

#     for idx, res in enumerate(response):
#         document = res.model_dump()
#         assert document["page_content"] == target_data[idx]["page_content"]
#         assert document["metadata"]["source"] == pdf_file.split("/")[-1]


# def pdf_s3files():
#     return [
#         ("s3:///amagpt/Swire_AR22_e_230406_sample.pdf", 5),
#         ("s3:///amagpt/sample_tables.pdf", 3),
#         ("s3:///amagpt/background-checks.pdf", 1),
#     ]


# @pytest.mark.parametrize("pdf_file,page_count", pdf_s3files())
# @pytest.mark.parametrize("fn_suffix", FN_SUFFIXES)
# async def test_load_s3file(fn_suffix, pdf_file, page_count):
#     client = JamAI(api_base=f"http://127.0.0.1:{PORT}/api")
#     fn = getattr(client, f"load_s3file{fn_suffix}")

#     request = p.File(uri=pdf_file, document_id="abc")
#     response = await fn(request) if fn_suffix.endswith("async") else fn(request)
#     logger.debug(response)
#     assert isinstance(response[0], p.Document)
#     assert len(response) == page_count

#     # # overwrite target data
#     # dump_json(
#     #     [res.model_dump() for res in response],
#     #     f"tests/_loader_check/pdfloader__{pdf_file.split('/')[-1]}.json",
#     # )

#     with open(f"tests/_loader_check/pdfloader__{pdf_file.split('/')[-1]}.json", "r") as f:
#         target_data = json.load(f)

#     for idx, res in enumerate(response):
#         document = res.model_dump()
#         assert document["page_content"] == target_data[idx]["page_content"]
#         assert document["metadata"]["source"] == target_data[idx]["metadata"]["source"]

#     # assert [res.model_dump() for res in response] == target_data


# @pytest.mark.parametrize("pdf_file,page_count", pdf_s3files())
# @pytest.mark.parametrize("fn_suffix", FN_SUFFIXES)
# async def test_split_documents(fn_suffix, pdf_file, page_count):
#     client = JamAI(api_base=f"http://127.0.0.1:{PORT}/api")
#     fn0 = getattr(client, f"load_s3file")

#     request0 = p.File(uri=pdf_file, document_id="abc")
#     response0 = fn0(request0)
#     assert isinstance(response0[0], p.Document)
#     assert len(response0) == page_count

#     fn = getattr(client, f"split_documents{fn_suffix}")

#     request = p.SplitChunksRequest(documents=response0)
#     response = await fn(request) if fn_suffix.endswith("async") else fn(request)
#     logger.debug(response)
#     assert isinstance(response[0], p.Document)

#     # # # overwrite target data
#     # dump_json(
#     #     [res.model_dump() for res in response],
#     #     f"tests/_loader_check/split_documents__{pdf_file.split('/')[-1]}.json",
#     # )

#     with open(f"tests/_loader_check/split_documents__{pdf_file.split('/')[-1]}.json", "r") as f:
#         target_data = json.load(f)

#     for idx, res in enumerate(response):
#         document = res.model_dump()
#         assert document["page_content"] == target_data[idx]["page_content"]
#         assert document["metadata"]["source"] == target_data[idx]["metadata"]["source"]

#     # assert [res.model_dump() for res in response] == target_data


if __name__ == "__main__":
    _get_models()
