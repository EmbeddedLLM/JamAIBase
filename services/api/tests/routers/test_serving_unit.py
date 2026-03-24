from types import SimpleNamespace

import pytest

from owl.routers.serving import chat_completion


class _BillingSpy:
    def __init__(self) -> None:
        self.events: list[str] = []

    def has_egress_quota(self) -> None:
        self.events.append("egress")

    def has_model_preflight_access(self, model_id: str) -> None:
        self.events.append(f"preflight:{model_id}")


@pytest.mark.asyncio
async def test_chat_completion_should_check_preflight_access_before_setup_rag(
    monkeypatch,
) -> None:
    billing = _BillingSpy()
    request = SimpleNamespace(state=SimpleNamespace(billing=billing, id="req_1"))
    auth_info = (None, SimpleNamespace(id="project_1"), SimpleNamespace(id="org_1"))
    body = SimpleNamespace(
        model="openai/gpt-4.1-nano",
        rag_params=SimpleNamespace(),
        stream=False,
        messages=[],
        hyperparams={},
        id="",
    )

    async def _setup_rag(*, project, lm, body, request_id):
        billing.events.append("setup_rag")
        return body, None

    class _LMEngine:
        def __init__(self, organization, project, request) -> None:
            pass

        async def chat_completion(self, *, messages, **hyperparams):
            billing.events.append("chat_completion")
            return SimpleNamespace(references=None)

    monkeypatch.setattr("owl.routers.serving.GenExecutor.setup_rag", _setup_rag)
    monkeypatch.setattr("owl.routers.serving.LMEngine", _LMEngine)

    await chat_completion(request, auth_info, body)

    assert billing.events == [
        "egress",
        "preflight:openai/gpt-4.1-nano",
        "setup_rag",
        "chat_completion",
    ]


@pytest.mark.asyncio
async def test_chat_completion_should_check_preflight_access_without_rag(
    monkeypatch,
) -> None:
    billing = _BillingSpy()
    request = SimpleNamespace(state=SimpleNamespace(billing=billing, id="req_1"))
    auth_info = (None, SimpleNamespace(id="project_1"), SimpleNamespace(id="org_1"))
    body = SimpleNamespace(
        model="openai/gpt-4.1-nano",
        rag_params=None,
        stream=False,
        messages=[],
        hyperparams={},
        id="",
    )

    async def _setup_rag(*, project, lm, body, request_id):
        billing.events.append("setup_rag")
        return body, None

    class _LMEngine:
        def __init__(self, organization, project, request) -> None:
            pass

        async def chat_completion(self, *, messages, **hyperparams):
            billing.events.append("chat_completion")
            return SimpleNamespace(references=None)

    monkeypatch.setattr("owl.routers.serving.GenExecutor.setup_rag", _setup_rag)
    monkeypatch.setattr("owl.routers.serving.LMEngine", _LMEngine)

    await chat_completion(request, auth_info, body)

    assert billing.events == [
        "egress",
        "preflight:openai/gpt-4.1-nano",
        "setup_rag",
        "chat_completion",
    ]


@pytest.mark.asyncio
async def test_generate_embeddings_should_check_preflight_access(monkeypatch) -> None:
    from owl.routers.serving import generate_embeddings

    billing = _BillingSpy()
    request = SimpleNamespace(state=SimpleNamespace(billing=billing, id="req_1"))
    auth_info = (None, SimpleNamespace(id="project_1"), SimpleNamespace(id="org_1"))
    body = SimpleNamespace(
        model="openai/text-embedding-3-small",
        input="hello",
        encoding_format="float",
        type="document",
    )

    class _LMEngine:
        def __init__(self, organization, project, request) -> None:
            pass

        async def embed_documents(self, **kwargs):
            billing.events.append("embed_documents")
            return SimpleNamespace()

    monkeypatch.setattr("owl.routers.serving.LMEngine", _LMEngine)

    await generate_embeddings(request, auth_info, body)

    assert billing.events == [
        "egress",
        "preflight:openai/text-embedding-3-small",
        "embed_documents",
    ]


@pytest.mark.asyncio
async def test_generate_rankings_should_check_preflight_access(monkeypatch) -> None:
    from owl.routers.serving import generate_rankings

    billing = _BillingSpy()
    request = SimpleNamespace(state=SimpleNamespace(billing=billing, id="req_1"))
    auth_info = (None, SimpleNamespace(id="project_1"), SimpleNamespace(id="org_1"))

    class _Body:
        model = "cohere/rerank-english-v3.0"

        def model_dump(self):
            return dict(model=self.model, query="q", documents=["a", "b"])

    class _LMEngine:
        def __init__(self, organization, project, request) -> None:
            pass

        async def rerank_documents(self, **kwargs):
            billing.events.append("rerank_documents")
            return SimpleNamespace()

    monkeypatch.setattr("owl.routers.serving.LMEngine", _LMEngine)

    await generate_rankings(request, auth_info, _Body())

    assert billing.events == [
        "egress",
        "preflight:cohere/rerank-english-v3.0",
        "rerank_documents",
    ]
