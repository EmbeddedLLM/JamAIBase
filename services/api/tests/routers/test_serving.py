import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import sleep
from typing import Generator

import numpy as np
import pytest
from flaky import flaky

from jamaibase import JamAI, JamAIAsync
from jamaibase.types import (
    ChatCompletionChoice,
    ChatCompletionChunkResponse,
    ChatCompletionMessage,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatEntry,
    ChatRequest,
    DeploymentCreate,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingUsage,
    ModelInfoListResponse,
    OkResponse,
    OrganizationCreate,
    RAGParams,
    References,
    RerankingRequest,
    StripePaymentInfo,
    TextContent,
)
from jamaibase.utils.exceptions import BadInputError, ForbiddenError, ResourceNotFoundError
from owl.configs import ENV_CONFIG
from owl.types import (
    CloudProvider,
    ModelCapability,
    ModelType,
    Role,
    TableType,
)
from owl.utils import uuid7_str
from owl.utils.test import (
    DS_PARAMS,
    ELLM_EMBEDDING_DEPLOYMENT,
    GPT_41_NANO_CONFIG,
    GPT_41_NANO_DEPLOYMENT,
    STREAM_PARAMS,
    TEXT_EMBEDDING_3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    add_table_rows,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_table,
    create_user,
)

METER_RETRY = 50
METER_RETRY_DELAY = 1
# Together AI sometimes take a long time
CHAT_TIMEOUT = 30
RERANK_TIMEOUT = 60
EMBED_TIMEOUT = 30


@dataclass(slots=True)
class ServingContext:
    superuser_id: str
    user_id: str
    superorg_id: str
    org_id: str
    project_ids: list[str]
    chat_model_id: str
    short_chat_model_id: str
    embedding_model_id: str
    rerank_model_id: str
    chat_deployment_id: str
    embedding_deployment_id: str
    rerank_deployment_id: str
    llm_input_costs: float
    llm_output_costs: float
    embed_costs: float
    rerank_costs: float
    chat_request: ChatRequest
    chat_request_text_array: ChatRequest
    chat_request_short: ChatRequest
    embedding_request: EmbeddingRequest
    reranking_request: RerankingRequest


def _metrics_match_llm_token_counts(metrics_data, serving_info):
    count_true = 0
    for entry in metrics_data.get("data", []):
        if entry["groupBy"].get("model", "") == serving_info["model"]:
            if (
                entry["groupBy"]["type"] == "input"
                and entry["value"] == serving_info["prompt_tokens"]
            ):
                count_true += 1
            if (
                entry["groupBy"]["type"] == "output"
                and entry["value"] == serving_info["completion_tokens"]
            ):
                count_true += 1
    return count_true == 2


def _metrics_match_llm_spent(metrics_data, serving_info):
    count_true = 0
    for entry in metrics_data["data"]:
        if (
            entry["groupBy"].get("model", "") == serving_info["model"]
            and entry["groupBy"].get("category", "") == "llm_tokens"
        ):
            if (
                entry["groupBy"]["type"] == "input"
                and round(entry["value"], 8) == serving_info["prompt_costs"]
            ):
                count_true += 1
            if (
                entry["groupBy"]["type"] == "output"
                and round(entry["value"], 8) == serving_info["completion_costs"]
            ):
                count_true += 1
    return count_true == 2


def _metrics_match_embed_token_counts(metrics_data, serving_info):
    count_true = 0
    for entry in metrics_data["data"]:
        if entry["groupBy"].get("model", "") == serving_info["model"]:
            if entry["value"] == serving_info["tokens"]:
                count_true += 1
    return count_true == 1


def _metrics_match_embed_spent(metrics_data, serving_info):
    count_true = 0
    for entry in metrics_data["data"]:
        if (
            entry["groupBy"].get("model", "") == serving_info["model"]
            and entry["groupBy"].get("category", "") == "embedding_tokens"
        ):
            if round(entry["value"], 8) == serving_info["costs"]:
                count_true += 1
    return count_true == 1


def _metrics_match_rerank_search_counts(metrics_data, serving_info):
    count_true = 0
    for entry in metrics_data["data"]:
        if entry["groupBy"].get("model", "") == serving_info["model"]:
            if entry["value"] == serving_info["documents"]:
                count_true += 1
    return count_true == 1


def _metrics_match_rerank_spent(metrics_data, serving_info):
    count_true = 0
    for entry in metrics_data["data"]:
        if (
            entry["groupBy"].get("model", "") == serving_info["model"]
            and entry["groupBy"].get("category", "") == "reranker_searches"
        ):
            if round(entry["value"], 8) == serving_info["costs"]:
                count_true += 1
    return count_true == 1


@pytest.fixture(scope="module")
def setup():
    """
    Fixture to set up the necessary organization, models, deployments, and projects for serving tests.
    """
    with (
        # Create superuser
        create_user() as superuser,
        # Create user
        create_user({"email": "testuser@example.com", "name": "Test User"}) as user,
        # Create organization
        create_organization(body=OrganizationCreate(name="TSP"), user_id=superuser.id) as superorg,
        create_organization(body=OrganizationCreate(name="Org"), user_id=user.id) as org,
        # Create project
        create_project(dict(name="P0"), user_id=superuser.id, organization_id=superorg.id) as p0,
        create_project(dict(name="P1"), user_id=superuser.id, organization_id=superorg.id) as p1,
        create_project(dict(name="P2"), user_id=user.id, organization_id=org.id) as p2,
    ):
        assert superuser.id == "0"
        assert superorg.id == "0"
        projects = [p0, p1, p2]
        client = JamAI(user_id=superuser.id)
        # Join organization and project
        client.organizations.join_organization(
            user_id=user.id, organization_id=superorg.id, role=Role.ADMIN
        )
        client.projects.join_project(user_id=user.id, project_id=p0.id, role=Role.ADMIN)
        client.projects.join_project(user_id=user.id, project_id=p1.id, role=Role.ADMIN)
        # Create models
        with (
            create_model_config(GPT_41_NANO_CONFIG) as llm_config,
            create_model_config(
                dict(
                    # Max context length = 5
                    id=f"ellm/lorem-context-5/{uuid7_str()}",
                    type=ModelType.LLM,
                    name="Short-Context Chat Model",
                    capabilities=[ModelCapability.CHAT],
                    context_length=5,
                    languages=["en"],
                    owned_by="ellm",
                )
            ) as short_llm_config,
            create_model_config(TEXT_EMBEDDING_3_SMALL_CONFIG) as embed_config,
            create_model_config(RERANK_ENGLISH_v3_SMALL_CONFIG) as rerank_config,
        ):
            # Create deployments
            with (
                create_deployment(GPT_41_NANO_DEPLOYMENT) as chat_deployment,
                create_deployment(
                    DeploymentCreate(
                        model_id=short_llm_config.id,
                        name="Short chat Deployment",
                        provider="custom",
                        routing_id=short_llm_config.id,
                        api_base=ENV_CONFIG.test_llm_api_base,
                    )
                ),
                create_deployment(
                    ELLM_EMBEDDING_DEPLOYMENT.model_copy(update=dict(model_id=embed_config.id))
                ) as embedding_deployment,
                create_deployment(RERANK_ENGLISH_v3_SMALL_DEPLOYMENT) as rerank_deployment,
            ):
                # Yield the setup data for use in tests
                yield ServingContext(
                    superuser_id=superuser.id,
                    user_id=user.id,
                    superorg_id=superorg.id,
                    org_id=org.id,
                    project_ids=[project.id for project in projects],
                    chat_model_id=llm_config.id,
                    short_chat_model_id=short_llm_config.id,
                    embedding_model_id=embed_config.id,
                    rerank_model_id=rerank_config.id,
                    chat_deployment_id=chat_deployment.id,
                    embedding_deployment_id=embedding_deployment.id,
                    rerank_deployment_id=rerank_deployment.id,
                    llm_input_costs=llm_config.llm_input_cost_per_mtoken,
                    llm_output_costs=llm_config.llm_output_cost_per_mtoken,
                    embed_costs=embed_config.embedding_cost_per_mtoken,
                    rerank_costs=rerank_config.reranking_cost_per_ksearch,
                    chat_request=ChatRequest(
                        model=llm_config.id,
                        # Test malformed input
                        messages=[ChatEntry.system(content=""), ChatEntry.user(content="Hi")],
                        max_tokens=3,
                        stream=False,
                    ),
                    # TODO: Test image and audio input
                    chat_request_text_array=ChatRequest(
                        model=llm_config.id,
                        messages=[
                            ChatEntry.user(
                                content=[
                                    TextContent(text="Hi "),
                                    TextContent(text="there"),
                                ]
                            )
                        ],
                        max_tokens=3,
                        stream=False,
                    ),
                    chat_request_short=ChatRequest(
                        model=short_llm_config.id,
                        messages=[{"role": "user", "content": "Hi there how is your day going?"}],
                        max_tokens=4,
                        stream=False,
                    ),
                    embedding_request=EmbeddingRequest(
                        model=embed_config.id,
                        input="This is a test input.",
                        # encoding_format="base64",
                    ),
                    reranking_request=RerankingRequest(
                        model=rerank_config.id,
                        query="What is the capital of France?",
                        documents=["London", "Berlin", "Paris"],
                    ),
                )


@pytest.mark.cloud
def test_model_prices(setup: ServingContext):
    del setup
    client = JamAI()
    prices = client.prices.list_model_prices()
    assert len(prices.llm_models) == 2
    assert len(prices.embed_models) == 1
    assert len(prices.rerank_models) == 1


def test_model_info(setup: ServingContext):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    chat_model_id = setup.chat_model_id

    response = client.model_info()
    assert isinstance(response, ModelInfoListResponse)
    assert len(response.data) == 4

    response = client.model_info(model=chat_model_id)
    assert len(response.data) == 1
    assert response.data[0].id == chat_model_id
    assert response.data[0].capabilities == ["chat", "image", "tool"]

    response = client.model_info(capabilities=["chat"])
    assert len(response.data) > 1
    assert all("chat" in m.capabilities for m in response.data)

    response = client.model_info(model="non-existent-model")
    assert len(response.data) == 0  # Ensure no data is returned for a non-existent model


def test_model_ids(setup: ServingContext):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    embedding_model_id = setup.embedding_model_id

    response = client.model_ids()
    assert isinstance(response, list)
    assert len(response) == 4

    response = client.model_ids(prefer=embedding_model_id)
    assert isinstance(response, list)
    assert len(response) == 4
    assert embedding_model_id == response[0]


@pytest.mark.cloud
def test_chat_completion_without_credit(setup: ServingContext):
    # Only Cloud enforces quota and credits
    super_client = JamAI(user_id=setup.superuser_id)
    # Set zero credit
    response = super_client.organizations.set_credit_grant(setup.org_id, amount=0)
    assert isinstance(response, OkResponse)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[2])
    with pytest.raises(ForbiddenError, match="Insufficient .+ credits"):
        client.generate_chat_completions(setup.chat_request)


def _test_chat_completion_stream(
    setup: ServingContext, request: ChatRequest
) -> list[ChatCompletionChunkResponse | References]:
    request.stream = True
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    _responses = client.generate_chat_completions(request)
    responses: list[ChatCompletionChunkResponse | References] = [item for item in _responses]
    assert len(responses) > 0
    assert all(isinstance(r, (ChatCompletionChunkResponse, References)) for r in responses)
    _chat_chunks = [r for r in responses if isinstance(r, ChatCompletionChunkResponse)]
    assert all(isinstance(r.content, str) for r in _chat_chunks)
    assert len("".join(r.content for r in _chat_chunks)) > 1
    response = responses[-1]
    assert isinstance(response.usage, ChatCompletionUsage)
    assert isinstance(response.usage.prompt_tokens, int)
    assert isinstance(response.usage.completion_tokens, int)
    assert isinstance(response.usage.total_tokens, int)
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.total_tokens == response.prompt_tokens + response.completion_tokens
    return responses


def _compile_and_check_responses(
    response: (Generator[ChatCompletionChunkResponse, None, None] | ChatCompletionResponse),
    stream: bool,
):
    if stream:
        responses: list[ChatCompletionChunkResponse] = [item for item in response]
        for r in responses:
            assert isinstance(r, ChatCompletionChunkResponse)
            assert r.object == "chat.completion.chunk"
            assert r.usage is None or isinstance(r.usage, ChatCompletionUsage)
        content = "".join(getattr(r.choices[0].delta, "content", "") or "" for r in responses)
        reasoning_content = "".join(
            getattr(r.choices[0].delta, "reasoning_content", "") or "" for r in responses
        )
        usage = responses[-1].usage
        assert isinstance(usage, ChatCompletionUsage)

        choice = responses[0].choices[0]
        assert isinstance(choice, ChatCompletionChoice)

        message = ChatCompletionMessage(content=content)
        assert isinstance(message, ChatCompletionMessage)

        if reasoning_content:
            message.reasoning_content = reasoning_content
            assert isinstance(message.reasoning_content, str)
            assert len(message.reasoning_content) > 0

        choice.delta = None
        choice.message = message

        response = ChatCompletionResponse(
            id=responses[0].id,
            object="chat.completion",
            created=responses[0].created,
            model=responses[0].model,
            choices=[choice],
            usage=usage,
            service_tier=responses[0].service_tier,
            system_fingerprint=responses[0].system_fingerprint,
        )

    assert isinstance(response, ChatCompletionResponse)
    assert isinstance(response.id, str)
    assert response.object == "chat.completion"
    assert isinstance(response.created, int)
    assert isinstance(response.model, str)
    assert isinstance(response.choices[0], ChatCompletionChoice)
    assert isinstance(response.choices[0].message, ChatCompletionMessage)
    assert isinstance(response.choices[0].message.content, str)
    assert len(response.choices[0].message.content) > 1
    assert isinstance(response.usage, ChatCompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.usage.total_tokens == response.prompt_tokens + response.completion_tokens

    return response


@pytest.mark.cloud
def test_serving_credit(setup: ServingContext):
    setup = deepcopy(setup)
    super_client = JamAI(user_id=setup.superuser_id, project_id=setup.project_ids[0])
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[2])
    # Assert credit grant is consumed first
    response = super_client.organizations.set_credit_grant(setup.org_id, amount=0.01)
    assert isinstance(response, OkResponse)
    client.generate_chat_completions(setup.chat_request, timeout=CHAT_TIMEOUT)
    sleep(1.0)
    org = client.organizations.get_organization(setup.org_id)
    assert org.credit == 0
    assert org.credit_grant < 0.01
    # Set credit to zero
    super_client.organizations.set_credit_grant(setup.org_id, amount=0)
    # Chat completion
    for stream in [True, False]:
        setup.chat_request.stream = stream
        with pytest.raises(ForbiddenError, match="Insufficient quota or credits"):
            client.generate_chat_completions(setup.chat_request, timeout=CHAT_TIMEOUT)
    # Embedding
    with pytest.raises(ForbiddenError, match="Insufficient quota or credits"):
        client.generate_embeddings(setup.embedding_request, timeout=EMBED_TIMEOUT)
    # Reranking
    with pytest.raises(ForbiddenError, match="Insufficient quota or credits"):
        client.rerank(setup.reranking_request, timeout=RERANK_TIMEOUT)
    # Assert credit is consumed if there is no credit grant
    response = client.organizations.purchase_credits(setup.org_id, amount=1)
    assert isinstance(response, StripePaymentInfo)
    super_client.organizations.set_credit_grant(setup.org_id, amount=0)
    client.generate_chat_completions(setup.chat_request, timeout=CHAT_TIMEOUT)
    sleep(1.0)
    org = client.organizations.get_organization(setup.org_id)
    assert org.credit < 1
    assert org.credit_grant == 0


def _test_chat_completion(
    client: JamAI,
    request: ChatRequest,
    stream: bool,
    timeout: int = 60,
):
    request.stream = stream
    response = client.generate_chat_completions(request, timeout=timeout)
    return _compile_and_check_responses(response, stream)


def _test_chat_completion_no_stream(
    setup: ServingContext, request: ChatRequest
) -> ChatCompletionResponse:
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    response = client.generate_chat_completions(request)
    assert isinstance(response, ChatCompletionResponse)
    assert isinstance(response.content, str)
    assert len(response.content) > 1
    assert isinstance(response.usage, ChatCompletionUsage)
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.usage.total_tokens == response.prompt_tokens + response.completion_tokens
    return response


def test_chat_completion_auto_model(setup: ServingContext):
    setup = deepcopy(setup)
    setup.chat_request = ChatRequest(
        **setup.chat_request.model_dump(
            exclude={"model"}, exclude_unset=True, exclude_defaults=True
        )
    )
    _test_chat_completion_no_stream(setup, setup.chat_request)


@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_chat_completion(setup: ServingContext, stream: bool):
    setup = deepcopy(setup)
    if stream:
        _test_chat_completion_stream(setup, setup.chat_request)
    else:
        _test_chat_completion_no_stream(setup, setup.chat_request)


@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_chat_completion_text_array(setup: ServingContext, stream: bool):
    setup = deepcopy(setup)
    if stream:
        _test_chat_completion_stream(setup, setup.chat_request_text_array)
    else:
        _test_chat_completion_no_stream(setup, setup.chat_request_text_array)


@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_chat_completion_rag(setup: ServingContext, stream: bool):
    """
    Chat completion with RAG.
    - RAG on empty table: stream and non-stream
    - RAG on non-empty table: stream and non-stream

    Args:
        setup (ServingContext): Setup.
        stream (bool): Stream (SSE) or not.
    """
    setup = deepcopy(setup)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    with create_table(client, TableType.KNOWLEDGE, cols=[]) as kt:
        setup.chat_request.rag_params = RAGParams(
            reranking_model=None,
            table_id=kt.id,
            search_query="",
            k=2,
        )
        ### --- RAG on empty table --- ###
        if stream:
            responses = _test_chat_completion_stream(setup, setup.chat_request)
            assert isinstance(responses[0], References)
        else:
            response = _test_chat_completion_no_stream(setup, setup.chat_request)
            assert isinstance(response.references, References)
        ### --- Add data into Knowledge Table --- ###
        data = [dict(Title="Pet", Text="My pet's name is Latte.")]
        response = add_table_rows(client, TableType.KNOWLEDGE, kt.id, data, stream=False)
        assert len(response.rows) == len(data)
        if stream:
            responses = _test_chat_completion_stream(setup, setup.chat_request)
            assert isinstance(responses[0], References)
        else:
            response = _test_chat_completion_no_stream(setup, setup.chat_request)
            assert isinstance(response.references, References)


@pytest.mark.parametrize("stream", **STREAM_PARAMS)
async def test_chat_completion_error_cases(setup: ServingContext, stream: bool):
    """
    Test chat completion error cases.
    - Sync and async
    - Exceed context length
    - Model not found

    Args:
        setup (ServingContext): Setup.
        stream (bool): Stream (SSE) or not.
    """
    setup = deepcopy(setup)
    model_id = setup.chat_request_short.model
    setup.chat_request_short.stream = stream
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    aclient = JamAIAsync(user_id=setup.user_id, project_id=setup.project_ids[0])
    # Prompt too long, max tokens too large
    with pytest.raises(BadInputError, match="maximum context length"):
        client.generate_chat_completions(setup.chat_request_short)
    with pytest.raises(BadInputError, match="maximum context length"):
        await aclient.generate_chat_completions(setup.chat_request_short)
    # Max tokens is too large
    setup.chat_request_short.messages[0].content = "Hi there"
    with pytest.raises(BadInputError, match="maximum context length"):
        client.generate_chat_completions(setup.chat_request_short)
    with pytest.raises(BadInputError, match="maximum context length"):
        await aclient.generate_chat_completions(setup.chat_request_short)
    # Unknown model
    setup.chat_request_short.model = "unknown"
    with pytest.raises(ResourceNotFoundError, match="Model .+ is not found"):
        client.generate_chat_completions(setup.chat_request_short)
    with pytest.raises(ResourceNotFoundError, match="Model .+ is not found"):
        await aclient.generate_chat_completions(setup.chat_request_short)
    # OK
    setup.chat_request_short.model = model_id
    setup.chat_request_short.max_tokens = 1
    if stream:
        responses = list(client.generate_chat_completions(setup.chat_request_short))
        assert len(responses) > 0
        assert all(isinstance(r, ChatCompletionChunkResponse) for r in responses)
        assert all(isinstance(r.content, str) for r in responses)
        assert len("".join(r.content for r in responses)) > 1
        response = responses[-1]
    else:
        response = client.generate_chat_completions(setup.chat_request_short)
    assert isinstance(response.usage, ChatCompletionUsage)
    assert isinstance(response.usage.prompt_tokens, int)
    assert isinstance(response.usage.completion_tokens, int)
    assert isinstance(response.usage.total_tokens, int)
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert response.total_tokens == response.prompt_tokens + response.completion_tokens


@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_get_llm_usage_metrics(setup: ServingContext, stream: bool, data_source: str):
    setup = deepcopy(setup)
    setup.chat_request.stream = stream
    start_dt = datetime.now(tz=timezone.utc)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    if stream:
        responses = list(client.generate_chat_completions(setup.chat_request))
        response = responses[-1]
    else:
        response = client.generate_chat_completions(setup.chat_request)
    serving_info = {
        "model": setup.chat_model_id,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
    }
    response_match = False
    for _ in range(METER_RETRY):
        response = client.meters.get_usage_metrics(
            type="llm",
            from_=start_dt,
            to=start_dt + timedelta(minutes=2),
            window_size="10s",
            proj_ids=[setup.project_ids[0]],
            group_by=["type", "model"],
            data_source=data_source,
        )
        if _metrics_match_llm_token_counts(response.model_dump(), serving_info):
            response_match = True
            break
        sleep(METER_RETRY_DELAY)
    assert response_match

    response = client.organizations.get_organization_metrics(
        metric_id="llm",
        from_=start_dt,
        to=start_dt + timedelta(minutes=2),
        window_size="10s",
        org_id=setup.superorg_id,
        proj_ids=[setup.project_ids[0]],
        group_by=["type", "model"],
        data_source=data_source,
    )
    assert _metrics_match_llm_token_counts(response.model_dump(), serving_info)


@pytest.mark.cloud
@flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_get_llm_billing_metrics(setup: ServingContext, stream: bool, data_source: str):
    setup = deepcopy(setup)
    start_dt = datetime.now(tz=timezone.utc)
    setup.chat_request.stream = stream
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    if stream:
        responses = list(client.generate_chat_completions(setup.chat_request))
        response = responses[-1]
    else:
        response = client.generate_chat_completions(setup.chat_request)
    serving_info = {
        "model": setup.chat_model_id,
        "prompt_costs": round(response.prompt_tokens * 1e-6 * setup.llm_input_costs, 8),
        "completion_costs": round(response.completion_tokens * 1e-6 * setup.llm_output_costs, 8),
    }
    response_match = False
    for _ in range(METER_RETRY):
        response = client.meters.get_billing_metrics(
            from_=start_dt,
            to=start_dt + timedelta(minutes=2),
            window_size="10s",
            proj_ids=[setup.project_ids[0]],
            group_by=["type", "model", "category"],
            data_source=data_source,
        )
        if _metrics_match_llm_spent(response.model_dump(), serving_info):
            response_match = True
            break
        sleep(METER_RETRY_DELAY)
    assert response_match

    response = client.organizations.get_organization_metrics(
        metric_id="spent",
        from_=start_dt,
        to=start_dt + timedelta(minutes=2),
        window_size="10s",
        org_id=setup.superorg_id,
        proj_ids=[setup.project_ids[0]],
        group_by=["type", "model", "category"],
        data_source=data_source,
    )
    assert _metrics_match_llm_spent(response.model_dump(), serving_info)


def _test_chat_reasoning_cloud(
    setup: ServingContext,
    provider: CloudProvider,
    routing_id: str,
    stream: bool,
    max_tokens: int,
    timeout: int = 60,
    prompt: str = "How many R is in Red?",
    reasoning_effort: str | None = None,
    thinking_budget: int | None = None,
):
    model_id = setup.chat_model_id
    super_client = JamAI(user_id=setup.superuser_id)
    super_client.models.update_deployment(
        setup.chat_deployment_id,
        dict(provider=provider, routing_id=routing_id),
    )
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    chat_request = ChatRequest(
        model=model_id,
        messages=[ChatEntry.user(content=prompt)],
        max_tokens=max_tokens,
        stream=stream,
        reasoning_effort=reasoning_effort,
        thinking_budget=thinking_budget,
        temperature=0,
        top_p=0.6,
    )

    response = _test_chat_completion(client, chat_request, stream, timeout)
    assert response.model == model_id
    return response


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_chat_reasoning_openai(setup: ServingContext, stream: bool):
    kwargs = dict(
        setup=setup,
        provider=CloudProvider.OPENAI,
        stream=stream,
        max_tokens=1000,
    )
    # Test default params
    response = _test_chat_reasoning_cloud(
        routing_id="gpt-5-mini",
        **kwargs,
    )
    assert len(response.content) > 0
    # Test disabling reasoning
    response = _test_chat_reasoning_cloud(
        routing_id="gpt-5-mini",
        reasoning_effort="disable",
        **kwargs,
    )
    assert len(response.content) > 0
    assert response.reasoning_tokens < 300
    # Test reasoning effort
    med_response = _test_chat_reasoning_cloud(
        routing_id="gpt-5-mini",
        thinking_budget=512,
        **kwargs,
    )
    assert len(med_response.content) > 0
    assert med_response.usage.reasoning_tokens > 0


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_chat_reasoning_anthropic(setup: ServingContext, stream: bool):
    kwargs = dict(
        setup=setup,
        provider=CloudProvider.ANTHROPIC,
        routing_id="claude-sonnet-4-0",
        stream=stream,
        max_tokens=2200,
    )
    # Test default params
    response = _test_chat_reasoning_cloud(**kwargs)
    assert len(response.content) > 0
    kwargs["routing_id"] = "claude-3-7-sonnet-latest"
    response = _test_chat_reasoning_cloud(**kwargs)
    assert len(response.content) > 0
    # Test disabling reasoning
    response = _test_chat_reasoning_cloud(
        reasoning_effort="disable",
        **kwargs,
    )
    # Test reasoning effort
    kwargs["max_tokens"] = 5000
    med_response = _test_chat_reasoning_cloud(
        reasoning_effort="medium",
        **kwargs,
    )
    assert len(med_response.content) > 0
    assert med_response.usage.reasoning_tokens > 0


# @flaky(max_runs=3, min_passes=1)
# @pytest.mark.parametrize("stream", **STREAM_PARAMS)
# def test_chat_reasoning_gemini(setup: ServingContext, stream: bool):
#     kwargs = dict(
#         setup=setup,
#         provider=CloudProvider.GEMINI,
#         stream=stream,
#         max_tokens=1024,
#     )
#     # Test default params
#     response = _test_chat_reasoning_cloud(
#         routing_id="gemini-2.5-flash-lite",
#         **kwargs,
#     )
#     assert len(response.content) > 0
#     # Test disabling reasoning
#     response = _test_chat_reasoning_cloud(
#         reasoning_effort="disable",
#         routing_id="gemini-2.5-pro",
#         **kwargs,
#     )
#     assert len(response.content) > 0
#     # Test reasoning effort
#     high_response = _test_chat_reasoning_cloud(
#         thinking_budget=512,
#         routing_id="gemini-2.5-flash",
#         **kwargs,
#     )
#     assert len(high_response.content) > 0
#     assert high_response.reasoning_tokens > 0


@flaky(max_runs=5, min_passes=1)
def test_generate_embeddings_auto_model(setup: ServingContext):
    setup = deepcopy(setup)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    setup.embedding_request.model = ""
    response = client.generate_embeddings(setup.embedding_request, timeout=EMBED_TIMEOUT)
    assert len(response.data) > 0
    embedding = response.data[0].embedding
    assert isinstance(embedding, list)
    assert len(embedding) > 1
    assert all(isinstance(x, float) for x in embedding)


@flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize(
    "texts",
    ["What is a llama?", ["What is a llama?", "What is an alpaca?"]],
    ids=["str", "list[str]"],
)
def test_generate_embeddings(setup: ServingContext, texts: str | list[str]):
    setup = deepcopy(setup)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    setup.embedding_request.input = texts
    # Float embeddings
    response = client.generate_embeddings(setup.embedding_request, timeout=EMBED_TIMEOUT)
    assert isinstance(response, EmbeddingResponse)
    assert isinstance(response.model, str)
    assert isinstance(response.usage, EmbeddingUsage)
    assert isinstance(response.data, list)
    if isinstance(texts, str):
        assert len(response.data) == 1
    else:
        assert len(response.data) == len(texts)
    for d in response.data:
        assert isinstance(d.embedding, list)
        assert len(d.embedding) > 1
        assert all(isinstance(x, float) for x in d.embedding)
    embed_float = np.asarray(response.data[0].embedding, dtype=np.float32)

    # Base64 embeddings
    setup.embedding_request.encoding_format = "base64"
    response = client.generate_embeddings(setup.embedding_request, timeout=EMBED_TIMEOUT)
    assert isinstance(response, EmbeddingResponse)
    assert isinstance(response.model, str)
    assert isinstance(response.usage, EmbeddingUsage)
    assert isinstance(response.data, list)
    if isinstance(texts, str):
        assert len(response.data) == 1
    else:
        assert len(response.data) == len(texts)
    for d in response.data:
        assert isinstance(d.embedding, str)
        assert len(d.embedding) > 1
    embed_base64 = np.frombuffer(base64.b64decode(response.data[0].embedding), dtype=np.float32)
    assert len(embed_float) == len(embed_base64)
    assert np.allclose(embed_float, embed_base64, atol=0.01, rtol=0.05)


@flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_get_embed_usage_metrics(setup: ServingContext, data_source: str):
    start_dt = datetime.now(tz=timezone.utc)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    response = client.generate_embeddings(setup.embedding_request, timeout=EMBED_TIMEOUT)
    serving_info = {
        "model": setup.embedding_model_id,
        "tokens": response.usage.total_tokens,
    }
    response_match = False
    for _ in range(METER_RETRY):
        response = client.meters.get_usage_metrics(
            type="embedding",
            from_=start_dt,
            to=start_dt + timedelta(minutes=2),
            window_size="10s",
            group_by=["model"],
            data_source=data_source,
        )
        if _metrics_match_embed_token_counts(response.model_dump(), serving_info):
            response_match = True
            break
        sleep(METER_RETRY_DELAY)

    assert response_match

    response = client.organizations.get_organization_metrics(
        metric_id="embedding",
        from_=start_dt,
        to=start_dt + timedelta(minutes=2),
        window_size="10s",
        org_id=setup.superorg_id,
        group_by=["model"],
        data_source=data_source,
    )

    assert _metrics_match_embed_token_counts(response.model_dump(), serving_info)


#     response = client.projects.get_usage_metrics(
#         type="embedding",
#         from_=start_dt,
#         to=start_dt + timedelta(minutes=2),
#         window_size="10s",
#         proj_id=setup.project_ids[0],
#         group_by=["model"],
#     )
#     assert _metrics_match_embed_token_counts(response.json(), serving_info)

#     response = client.projects.get_usage_metrics(
#         type="embedding",
#         from_=start_dt,
#         to=start_dt + timedelta(minutes=2),
#         window_size="10s",
#         proj_id=setup.project_ids[1],
#         group_by=["model"],
#     )
#     assert not _metrics_match_embed_token_counts(response.json(), serving_info)


@pytest.mark.cloud
@flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_get_embed_billing_metrics(setup: ServingContext, data_source: str):
    start_dt = datetime.now(tz=timezone.utc)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    response = client.generate_embeddings(setup.embedding_request, timeout=EMBED_TIMEOUT)
    serving_info = {
        "model": setup.embedding_model_id,
        "costs": round(response.usage.total_tokens * 1e-6 * setup.embed_costs, 8),
    }
    response_match = False
    for _ in range(METER_RETRY):
        response = client.meters.get_billing_metrics(
            from_=start_dt,
            to=start_dt + timedelta(minutes=2),
            window_size="10s",
            group_by=["model", "category"],
            data_source=data_source,
        )
        if _metrics_match_embed_spent(response.model_dump(), serving_info):
            response_match = True
            break
        sleep(METER_RETRY_DELAY)

    assert response_match

    response = client.organizations.get_organization_metrics(
        metric_id="spent",
        from_=start_dt,
        to=start_dt + timedelta(minutes=2),
        window_size="10s",
        org_id=setup.superorg_id,
        group_by=["model", "category"],
        data_source=data_source,
    )
    assert _metrics_match_embed_spent(response.model_dump(), serving_info)


#     response = client.projects.get_billing_metrics(
#         from_=start_dt,
#         to=start_dt + timedelta(minutes=2),
#         window_size="10s",
#         proj_id=setup.project_ids[0],
#         group_by=["model", "category"],
#     )
#     assert _metrics_match_embed_spent(response.json(), serving_info)

#     response = client.projects.get_billing_metrics(
#         from_=start_dt,
#         to=start_dt + timedelta(minutes=2),
#         window_size="10s",
#         proj_id=setup.project_ids[1],
#         group_by=["model", "category"],
#     )
#     assert not _metrics_match_embed_spent(response.json(), serving_info)


@flaky(max_runs=5, min_passes=1)
def test_rerank_auto_model(setup: ServingContext):
    setup = deepcopy(setup)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    setup.reranking_request.model = ""
    response = client.rerank(setup.reranking_request, timeout=RERANK_TIMEOUT)
    assert response.results[0].index == 2, f"Reranking results are unsorted: {response.results}"
    relevance_scores = [x.relevance_score for x in response.results]
    assert len(relevance_scores) == 3
    assert relevance_scores[0] > relevance_scores[1]


@flaky(max_runs=5, min_passes=1)
def test_rerank(setup: ServingContext):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    response = client.rerank(setup.reranking_request, timeout=RERANK_TIMEOUT)
    assert response.results[0].index == 2, f"Reranking results are unsorted: {response.results}"
    relevance_scores = [x.relevance_score for x in response.results]
    assert len(relevance_scores) == 3
    assert relevance_scores[0] > relevance_scores[1]


@flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_get_rerank_usage_metrics(setup: ServingContext, data_source: str):
    start_dt = datetime.now(tz=timezone.utc)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    response = client.rerank(setup.reranking_request, timeout=RERANK_TIMEOUT)
    serving_info = {
        "model": setup.rerank_model_id,
        "documents": len(response.results),
    }
    response_match = False
    for _ in range(METER_RETRY):
        response = client.meters.get_usage_metrics(
            type="reranking",
            from_=start_dt,
            to=start_dt + timedelta(minutes=2),
            window_size="10s",
            group_by=["model"],
            data_source=data_source,
        )
        if _metrics_match_rerank_search_counts(response.model_dump(), serving_info):
            response_match = True
            break
        sleep(METER_RETRY_DELAY)

    assert response_match

    response = client.organizations.get_organization_metrics(
        metric_id="reranking",
        from_=start_dt,
        to=start_dt + timedelta(minutes=2),
        window_size="10s",
        org_id=setup.superorg_id,
        group_by=["model"],
        data_source=data_source,
    )

    assert _metrics_match_rerank_search_counts(response.model_dump(), serving_info)


#     response = client.projects.get_usage_metrics(
#         type="reranking",
#         from_=start_dt,
#         to=start_dt + timedelta(minutes=2),
#         window_size="10s",
#         proj_id=setup.project_ids[0],
#         group_by=["model"],
#     )
#     assert _metrics_match_rerank_search_counts(response.json(), serving_info)

#     response = client.projects.get_usage_metrics(
#         type="reranking",
#         from_=start_dt,
#         to=start_dt + timedelta(minutes=2),
#         window_size="10s",
#         proj_id=setup.project_ids[1],
#         group_by=["model"],
#     )
#     assert not _metrics_match_rerank_search_counts(response.json(), serving_info)


@pytest.mark.cloud
@flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize("data_source", **DS_PARAMS)
def test_get_rerank_billing_metrics(setup: ServingContext, data_source: str):
    start_dt = datetime.now(tz=timezone.utc)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
    response = client.rerank(setup.reranking_request, timeout=RERANK_TIMEOUT)
    serving_info = {
        "model": setup.rerank_model_id,
        "costs": round(len(response.results) * 1e-3 * setup.rerank_costs, 8),
    }
    response_match = False
    for _ in range(METER_RETRY):
        response = client.meters.get_billing_metrics(
            from_=start_dt,
            to=start_dt + timedelta(minutes=2),
            window_size="10s",
            group_by=["model", "category"],
            data_source=data_source,
        )
        if _metrics_match_rerank_spent(response.model_dump(), serving_info):
            response_match = True
            break
        sleep(METER_RETRY_DELAY)

    assert response_match

    response = client.organizations.get_organization_metrics(
        metric_id="spent",
        from_=start_dt,
        to=start_dt + timedelta(minutes=2),
        window_size="10s",
        org_id=setup.superorg_id,
        group_by=["model", "category"],
        data_source=data_source,
    )
    assert _metrics_match_rerank_spent(response.model_dump(), serving_info)


#     response = client.projects.get_billing_metrics(
#         from_=start_dt,
#         to=start_dt + timedelta(minutes=2),
#         window_size="10s",
#         proj_id=setup.project_ids[0],
#         group_by=["model", "category"],
#     )
#     assert _metrics_match_rerank_spent(response.json(), serving_info)

#     response = client.projects.get_billing_metrics(
#         from_=start_dt,
#         to=start_dt + timedelta(minutes=2),
#         window_size="10s",
#         proj_id=setup.project_ids[1],
#         group_by=["model", "category"],
#     )
#     assert not _metrics_match_rerank_spent(response.json(), serving_info)


# @flaky(max_runs=5, min_passes=1)
# def test_chat_arbitrary_provider(setup: ServingContext):
#     setup = deepcopy(setup)
#     client = JamAI(user_id=setup.superuser_id)
#     model_id = uuid7_str("llm-model/")
#     with create_model_config(
#         {
#             "id": model_id,
#             "type": "llm",
#             "name": "Chat Model",
#             "capabilities": ["chat"],
#             "context_length": 1024,
#             "languages": ["en"],
#         }
#     ):
#         with create_deployment(
#             DeploymentCreate(
#                 model_id=model_id,
#                 name="Chat Deployment",
#                 provider="abc",
#                 routing_id="openai/gpt-4o-mini",
#                 api_base="",
#             )
#         ):
#             client.organizations.update_organization(
#                 OrganizationUpdate(
#                     id=setup.org_id,
#                     external_keys=dict(abc=ENV_CONFIG.openai_api_key_plain),
#                 )
#             )
#             client = JamAI(user_id=setup.user_id, project_id=setup.project_ids[0])
#             setup.chat_request.model = model_id
#             response = client.generate_chat_completions(setup.chat_request, timeout=CHAT_TIMEOUT)
#             assert response.model == model_id
#             assert isinstance(response.content, str)
#             assert len(response.content) > 1
