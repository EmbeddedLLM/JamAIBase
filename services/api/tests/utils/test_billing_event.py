"""
Tests for the BillingManager's event creation and processing for all usage types.

This module verifies that different API endpoints and periodic tasks trigger the
correct billing events, leading to accurate updates in an organization's usage
and credit records in the database.

It covers:
- LLM, Embedding, and Reranker token/search usage and costs.
- Egress (bandwidth) usage for streaming responses.
- Database and File Storage usage calculated by the periodic Celery task.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from os.path import dirname, join, realpath
from time import sleep

import pytest
from loguru import logger

from jamaibase import JamAI
from jamaibase import types as t
from owl.types import (
    ChatEntry,
    ChatRequest,
    ColumnSchemaCreate,
    EmbeddingRequest,
    LLMGenConfig,
    OrganizationRead,
    PaymentState,
    PricePlan_,
    PriceTier,
    Product,
    Products,
    ProjectRead,
    RAGParams,
    RerankingRequest,
    TableType,
    UserRead,
)
from owl.utils.dates import now
from owl.utils.test import (
    ELLM_DESCRIBE_CONFIG,
    ELLM_DESCRIBE_DEPLOYMENT,
    ELLM_EMBEDDING_CONFIG,
    ELLM_EMBEDDING_DEPLOYMENT,
    GPT_41_NANO_CONFIG,
    GPT_41_NANO_DEPLOYMENT,
    STREAM_PARAMS,
    TEXT_EMBEDDING_3_SMALL_CONFIG,
    TEXT_EMBEDDING_3_SMALL_DEPLOYMENT,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    add_table_rows,
    create_deployment,
    create_model_config,
    create_project,
    create_table,
    get_file_map,
    setup_organizations,
)

USAGE_RETRY = 30
USAGE_RETRY_DELAY = 1.0
MODEL_PROVIDER_PARAMS = dict(argvalues=[True, False], ids=["ellm", "other"])

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)


@dataclass(slots=True)
class BillingContext:
    user: UserRead
    org: OrganizationRead
    project: ProjectRead
    ellm_chat_model_id: str
    chat_model_id: str
    ellm_embedding_model_id: str
    embedding_model_id: str
    ellm_rerank_model_id: str
    rerank_model_id: str


@pytest.fixture(scope="module")
def setup():
    """
    Sets up a test environment with an organization, project, and both internal (ELLM)
    and external models configured for billing tests.
    """
    with setup_organizations() as ctx:
        with create_project(user_id=ctx.user.id, organization_id=ctx.org.id) as project:
            # Create ELLM and External models for all types (Chat, Embed, Rerank)
            with (
                # --- Chat Models ---
                create_model_config(ELLM_DESCRIBE_CONFIG) as ellm_chat_model,
                create_model_config(GPT_41_NANO_CONFIG) as chat_model,
                # --- Embedding Models ---
                create_model_config(ELLM_EMBEDDING_CONFIG) as ellm_embed_model,
                create_model_config(TEXT_EMBEDDING_3_SMALL_CONFIG) as embed_model,
                # --- Reranking Models ---
                create_model_config(
                    dict(
                        id=f"ellm/{RERANK_ENGLISH_v3_SMALL_CONFIG.id}",
                        name=f"ELLM {RERANK_ENGLISH_v3_SMALL_CONFIG.name}",
                        owned_by="ellm",
                        **RERANK_ENGLISH_v3_SMALL_CONFIG.model_dump(
                            exclude={"id", "name", "owned_by"}
                        ),
                    )
                ) as ellm_rerank_model,
                create_model_config(RERANK_ENGLISH_v3_SMALL_CONFIG) as rerank_model,
                # --- Deployments ---
                create_deployment(ELLM_DESCRIBE_DEPLOYMENT),
                create_deployment(GPT_41_NANO_DEPLOYMENT),
                create_deployment(ELLM_EMBEDDING_DEPLOYMENT),
                create_deployment(TEXT_EMBEDDING_3_SMALL_DEPLOYMENT),
                create_deployment(
                    dict(
                        model_id=f"ellm/{RERANK_ENGLISH_v3_SMALL_DEPLOYMENT.model_id}",
                        name=f"ELLM {RERANK_ENGLISH_v3_SMALL_DEPLOYMENT.name}",
                        **RERANK_ENGLISH_v3_SMALL_DEPLOYMENT.model_dump(
                            exclude={"model_id", "name"}, mode="json"
                        ),
                    )
                ),
                create_deployment(RERANK_ENGLISH_v3_SMALL_DEPLOYMENT),
            ):
                yield BillingContext(
                    user=ctx.user,
                    org=ctx.org,
                    project=project,
                    ellm_chat_model_id=ellm_chat_model.id,
                    chat_model_id=chat_model.id,
                    ellm_embedding_model_id=ellm_embed_model.id,
                    embedding_model_id=embed_model.id,
                    ellm_rerank_model_id=ellm_rerank_model.id,
                    rerank_model_id=rerank_model.id,
                )


def _cmp(new_org: OrganizationRead, org: OrganizationRead, attr: str, op: str) -> bool:
    return getattr(getattr(new_org, attr), op)(getattr(org, attr))


@contextmanager
def _test_usage_event(
    client: JamAI,
    org_id: str,
    is_ellm: bool,
    usage_attr: str,
    quota_attr: str,
):
    """
    Helper function to test billing events for a specific usage type.

    Args:
        client: The JamAI client instance.
        org_id: The ID of the organization to test.
        is_ellm: Boolean indicating if an ELLM model is being tested.
        usage_attr: The attribute name for usage on the OrganizationRead object.
        quota_attr: The attribute name for quota on the OrganizationRead object.
    """
    org = client.organizations.get_organization(org_id)
    assert isinstance(org, t.OrganizationRead)
    yield
    for i in range(USAGE_RETRY):
        sleep(USAGE_RETRY_DELAY)
        logger.info(f"{usage_attr}: Attempt {i}")
        new_org = client.organizations.get_organization(org_id)
        checks = {
            "credit": _cmp(new_org, org, "credit", "__eq__"),
            "credit_grant": _cmp(new_org, org, "credit_grant", "__eq__" if is_ellm else "__lt__"),
            quota_attr: _cmp(new_org, org, quota_attr, "__eq__"),
            usage_attr: _cmp(new_org, org, usage_attr, "__gt__" if is_ellm else "__eq__"),
            "egress_quota_gib": _cmp(new_org, org, "egress_quota_gib", "__eq__"),
            "egress_usage_gib": _cmp(new_org, org, "egress_usage_gib", "__gt__"),
        }
        if all(checks.values()):
            break
    else:
        org = {k: getattr(org, k) for k in checks}
        new_org = {k: getattr(new_org, k) for k in checks}
        raise AssertionError(f"Usage failed to update: {checks=} {new_org=} {org=}")


@pytest.mark.cloud
@pytest.mark.parametrize("is_ellm", **MODEL_PROVIDER_PARAMS)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_create_llm_events(setup: BillingContext, is_ellm: bool, stream: bool):
    """Verifies that LLM usage events correctly update organization metrics."""
    client = JamAI(user_id=setup.user.id, project_id=setup.project.id)
    request = ChatRequest(
        model=setup.ellm_chat_model_id if is_ellm else setup.chat_model_id,
        messages=[ChatEntry.user(content="Tell me a very short joke.")],
        max_tokens=10,
        stream=stream,
    )

    with _test_usage_event(
        client=client,
        org_id=setup.org.id,
        is_ellm=is_ellm,
        usage_attr="llm_tokens_usage_mtok",
        quota_attr="llm_tokens_quota_mtok",
    ):
        if stream:
            list(client.generate_chat_completions(request))
        else:
            client.generate_chat_completions(request)


@pytest.mark.cloud
@pytest.mark.parametrize("is_ellm", **MODEL_PROVIDER_PARAMS)
def test_create_embedding_events(setup: BillingContext, is_ellm: bool):
    """Verifies that embedding usage events correctly update organization metrics."""
    client = JamAI(user_id=setup.user.id, project_id=setup.project.id)
    request = EmbeddingRequest(
        model=setup.ellm_embedding_model_id if is_ellm else setup.embedding_model_id,
        input="This is a test for embedding billing.",
    )

    with _test_usage_event(
        client=client,
        org_id=setup.org.id,
        is_ellm=is_ellm,
        usage_attr="embedding_tokens_usage_mtok",
        quota_attr="embedding_tokens_quota_mtok",
    ):
        client.generate_embeddings(request)


@pytest.mark.cloud
@pytest.mark.parametrize("is_ellm", **MODEL_PROVIDER_PARAMS)
def test_create_reranker_events(setup: BillingContext, is_ellm: bool):
    """Verifies that reranker usage events correctly update organization metrics."""
    client = JamAI(user_id=setup.user.id, project_id=setup.project.id)
    documents = [
        "Paris is the capital of France.",
        "The Eiffel Tower is in Paris.",
        "Berlin is the capital of Germany.",
    ]
    request = RerankingRequest(
        model=setup.ellm_rerank_model_id if is_ellm else setup.rerank_model_id,
        query="What is the capital of France?",
        documents=documents,
    )

    with _test_usage_event(
        client=client,
        org_id=setup.org.id,
        is_ellm=is_ellm,
        usage_attr="reranker_usage_ksearch",
        quota_attr="reranker_quota_ksearch",
    ):
        client.rerank(request)


def _retry(func):
    for i in range(USAGE_RETRY):
        sleep(USAGE_RETRY_DELAY)
        logger.info(f"{func.__name__}: Attempt {i}")
        try:
            return func()
        except Exception:
            if i == USAGE_RETRY - 1:
                raise


def _check_quotas(org: OrganizationRead, new_org: OrganizationRead):
    # Credits
    assert new_org.credit == org.credit
    # LLM
    assert new_org.llm_tokens_quota_mtok == org.llm_tokens_quota_mtok
    # Embed
    assert new_org.embedding_tokens_quota_mtok == org.embedding_tokens_quota_mtok
    # Rerank (no usage yet)
    assert new_org.reranker_quota_ksearch == org.reranker_quota_ksearch
    # Egress
    assert new_org.egress_quota_gib == org.egress_quota_gib
    # DB storage
    assert new_org.db_quota_gib == org.db_quota_gib
    # File storage
    assert new_org.file_quota_gib == org.file_quota_gib


@pytest.mark.cloud
@pytest.mark.timeout(180)
def test_gen_table_billing(setup: BillingContext):
    client = JamAI(user_id=setup.user.id, project_id=setup.project.id)
    org = client.organizations.get_organization(setup.org.id)
    with (
        create_table(
            client, TableType.KNOWLEDGE, embedding_model=setup.embedding_model_id, cols=[]
        ) as kt,
        create_table(
            client, TableType.KNOWLEDGE, embedding_model=setup.ellm_embedding_model_id, cols=[]
        ) as ellm_kt,
    ):
        ### --- Perform RAG --- ###
        system_prompt = "Be concise."
        gen_config_kwargs = dict(
            system_prompt=system_prompt,
            prompt="",
            max_tokens=20,
            temperature=0.001,
            top_p=0.001,
        )
        rag_kwargs = dict(search_query="", k=2)
        cols = [
            ColumnSchemaCreate(id="question", dtype="str"),
            ColumnSchemaCreate(id="image", dtype="image"),
            ColumnSchemaCreate(
                id="ellm",
                dtype="str",
                gen_config=LLMGenConfig(
                    model=setup.ellm_chat_model_id,
                    multi_turn=False,
                    rag_params=RAGParams(
                        reranking_model=setup.ellm_rerank_model_id,
                        table_id=ellm_kt.id,
                        **rag_kwargs,
                    ),
                    **gen_config_kwargs,
                ),
            ),
            ColumnSchemaCreate(
                id="non_ellm",
                dtype="str",
                gen_config=LLMGenConfig(
                    model=setup.chat_model_id,
                    multi_turn=False,
                    rag_params=RAGParams(
                        reranking_model=setup.rerank_model_id,
                        table_id=kt.id,
                        **rag_kwargs,
                    ),
                    **gen_config_kwargs,
                ),
            ),
        ]

        ### --- Embed file --- ###
        client.table.embed_file(file_path=FILES["weather.txt"], table_id=kt.id)
        client.table.embed_file(file_path=FILES["weather.txt"], table_id=ellm_kt.id)

        # Check the billing data
        def _check_embed():
            new_org = client.organizations.get_organization(setup.org.id)
            # fmt: off
            assert new_org.credit_grant < org.credit_grant, (
                f"{new_org.credit_grant=}, {org.credit_grant=}"
            )
            assert new_org.llm_tokens_usage_mtok > org.llm_tokens_usage_mtok, (
                f"{new_org.llm_tokens_usage_mtok=}, {org.llm_tokens_usage_mtok=}"
            )
            assert new_org.embedding_tokens_usage_mtok > org.embedding_tokens_usage_mtok, (
                f"{new_org.embedding_tokens_usage_mtok=}, {org.embedding_tokens_usage_mtok=}"
            )
            # No usage yet
            assert new_org.reranker_usage_ksearch == org.reranker_usage_ksearch, (
                f"{new_org.reranker_usage_ksearch=}, {org.reranker_usage_ksearch=}"
            )
            assert new_org.egress_usage_gib > org.egress_usage_gib, (
                f"{new_org.egress_usage_gib=}, {org.egress_usage_gib=}"
            )
            assert new_org.db_usage_gib > org.db_usage_gib, (
                f"{new_org.db_usage_gib=}, {org.db_usage_gib=}"
            )
            assert new_org.file_usage_gib > org.file_usage_gib, (
                f"{new_org.file_usage_gib=}, {org.file_usage_gib=}"
            )
            # fmt: on
            _check_quotas(org, new_org)
            return new_org

        org = _retry(_check_embed)

        ### --- RAG --- ###
        image_uri = client.file.upload_file(FILES["rabbit.jpeg"]).uri
        table_type = TableType.ACTION
        with create_table(client, table_type, cols=cols) as table:
            ### Stream
            data = [dict(question="What is it?", image=image_uri)]
            response = add_table_rows(client, table_type, table.id, data, stream=True)
            assert len(response.rows) == len(data)

            # Check the billing data
            def _check_rag_stream():
                new_org = client.organizations.get_organization(setup.org.id)
                # fmt: off
                assert new_org.credit_grant < org.credit_grant, (
                    f"{new_org.credit_grant=}, {org.credit_grant=}"
                )
                assert new_org.llm_tokens_usage_mtok > org.llm_tokens_usage_mtok, (
                    f"{new_org.llm_tokens_usage_mtok=}, {org.llm_tokens_usage_mtok=}"
                )
                assert new_org.embedding_tokens_usage_mtok > org.embedding_tokens_usage_mtok, (
                    f"{new_org.embedding_tokens_usage_mtok=}, {org.embedding_tokens_usage_mtok=}"
                )
                assert new_org.reranker_usage_ksearch > org.reranker_usage_ksearch, (
                    f"{new_org.reranker_usage_ksearch=}, {org.reranker_usage_ksearch=}"
                )
                assert new_org.egress_usage_gib > org.egress_usage_gib, (
                    f"{new_org.egress_usage_gib=}, {org.egress_usage_gib=}"
                )
                assert new_org.db_usage_gib > org.db_usage_gib, (
                    f"{new_org.db_usage_gib=}, {org.db_usage_gib=}"
                )
                assert new_org.file_usage_gib > org.file_usage_gib, (
                    f"{new_org.file_usage_gib=}, {org.file_usage_gib=}"
                )
                # fmt: on
                _check_quotas(org, new_org)
                return new_org

            org = _retry(_check_rag_stream)

            ### Non-stream
            data = [dict(question="What is it?", image=image_uri)]
            response = add_table_rows(client, table_type, table.id, data, stream=False)
            assert len(response.rows) == len(data)

            # Check the billing data
            def _check_rag_non_stream():
                new_org = client.organizations.get_organization(setup.org.id)
                # fmt: off
                assert new_org.credit_grant < org.credit_grant, (
                    f"{new_org.credit_grant=}, {org.credit_grant=}"
                )
                assert new_org.llm_tokens_usage_mtok > org.llm_tokens_usage_mtok, (
                    f"{new_org.llm_tokens_usage_mtok=}, {org.llm_tokens_usage_mtok=}"
                )
                assert new_org.embedding_tokens_usage_mtok > org.embedding_tokens_usage_mtok, (
                    f"{new_org.embedding_tokens_usage_mtok=}, {org.embedding_tokens_usage_mtok=}"
                )
                assert new_org.reranker_usage_ksearch > org.reranker_usage_ksearch, (
                    f"{new_org.reranker_usage_ksearch=}, {org.reranker_usage_ksearch=}"
                )
                assert new_org.egress_usage_gib > org.egress_usage_gib, (
                    f"{new_org.egress_usage_gib=}, {org.egress_usage_gib=}"
                )
                # No new page allocated
                assert new_org.db_usage_gib == org.db_usage_gib, (
                    f"{new_org.db_usage_gib=}, {org.db_usage_gib=}"
                )
                # No new file uploaded
                assert new_org.file_usage_gib == org.file_usage_gib, (
                    f"{new_org.file_usage_gib=}, {org.file_usage_gib=}"
                )
                # fmt: on
                _check_quotas(org, new_org)
                return new_org

            org = _retry(_check_rag_non_stream)

    ### --- Tables deleted --- ###
    # Check the billing data
    def _check_delete():
        new_org = client.organizations.get_organization(setup.org.id)
        # fmt: off
        assert new_org.credit_grant == org.credit_grant, (
            f"{new_org.credit_grant=}, {org.credit_grant=}"
        )
        assert new_org.llm_tokens_usage_mtok == org.llm_tokens_usage_mtok, (
            f"{new_org.llm_tokens_usage_mtok=}, {org.llm_tokens_usage_mtok=}"
        )
        assert new_org.embedding_tokens_usage_mtok == org.embedding_tokens_usage_mtok, (
            f"{new_org.embedding_tokens_usage_mtok=}, {org.embedding_tokens_usage_mtok=}"
        )
        assert new_org.reranker_usage_ksearch == org.reranker_usage_ksearch, (
            f"{new_org.reranker_usage_ksearch=}, {org.reranker_usage_ksearch=}"
        )
        assert new_org.egress_usage_gib > org.egress_usage_gib, (
            f"{new_org.egress_usage_gib=}, {org.egress_usage_gib=}"
        )
        assert new_org.db_usage_gib < org.db_usage_gib, (
            f"{new_org.db_usage_gib=}, {org.db_usage_gib=}"
        )
        assert new_org.file_usage_gib == org.file_usage_gib, (
            f"{new_org.file_usage_gib=}, {org.file_usage_gib=}"
        )
        # fmt: on
        _check_quotas(org, new_org)
        return new_org

    org = _retry(_check_delete)


@pytest.mark.cloud
def test_tiered_billing():
    from owl.utils.billing.cloud import BillingManager

    base_kwargs = dict(created_at=now(), updated_at=now())
    price_plan = PricePlan_(
        id="free",
        name="Free plan",
        stripe_price_id_live="stripe_price_id_live",
        stripe_price_id_test="stripe_price_id_test",
        flat_cost=0.0,
        credit_grant=0.0,
        max_users=2,  # For ease of testing
        products=Products(
            llm_tokens=Product(
                name="ELLM tokens",
                included=PriceTier(unit_cost=0.5, up_to=0.75),
                tiers=[],
                unit="Million Tokens",
            ),
            embedding_tokens=Product(
                name="Embedding tokens",
                included=PriceTier(unit_cost=0.5, up_to=0.75),
                tiers=[],
                unit="Million Tokens",
            ),
            reranker_searches=Product(
                name="Reranker searches",
                included=PriceTier(unit_cost=0.5, up_to=0.75),
                tiers=[],
                unit="Thousand Searches",
            ),
            db_storage=Product(
                name="Database storage",
                included=PriceTier(unit_cost=0.5, up_to=0.75),
                tiers=[],
                unit="GiB",
            ),
            file_storage=Product(
                name="File storage",
                included=PriceTier(unit_cost=0.5, up_to=0.75),
                tiers=[],
                unit="GiB",
            ),
            egress=Product(
                name="Egress bandwidth",
                included=PriceTier(unit_cost=0.5, up_to=0.5),
                tiers=[
                    PriceTier(unit_cost=1.0, up_to=1.0),
                    PriceTier(unit_cost=2.0, up_to=None),
                ],
                unit="GiB",
            ),
        ),
        is_private=False,
        stripe_price_id="stripe_price_id",
        **base_kwargs,
    )
    assert price_plan.products.egress.included.unit_cost == 0
    org = OrganizationRead(
        id="test_org",
        name="test_org",
        created_by="",
        owner="",
        stripe_id="stripe_id",
        external_keys={},
        price_plan_id=price_plan.id,
        payment_state=PaymentState.SUCCESS,
        last_subscription_payment_at=now(),
        quota_reset_at=now(),
        credit=0.0,
        credit_grant=0.0,
        llm_tokens_quota_mtok=price_plan.products.llm_tokens.included.up_to,
        llm_tokens_usage_mtok=0.0,
        embedding_tokens_quota_mtok=price_plan.products.embedding_tokens.included.up_to,
        embedding_tokens_usage_mtok=0.0,
        reranker_quota_ksearch=price_plan.products.reranker_searches.included.up_to,
        reranker_usage_ksearch=0.0,
        db_quota_gib=price_plan.products.db_storage.included.up_to,
        db_usage_gib=0.0,
        db_usage_updated_at=now(),
        file_quota_gib=price_plan.products.file_storage.included.up_to,
        file_usage_gib=0.0,
        file_usage_updated_at=now(),
        egress_quota_gib=price_plan.products.egress.included.up_to,
        egress_usage_gib=0.0,
        quotas={},
        active=True,
        price_plan=price_plan,
        **base_kwargs,
    )
    # Test single charge
    billing = BillingManager(
        organization=org.model_copy(),
        project_id="test_project",
        user_id="test_user",
    )
    usage = 2.0
    billing.create_egress_events(usage)
    billing.org.egress_usage_gib += usage
    assert round(billing.cost, 2) == 2.0
    # Test multiple charge
    billing = BillingManager(
        organization=org.model_copy(),
        project_id="test_project",
        user_id="test_user",
    )
    usage = 0.4
    billing.create_egress_events(usage)
    billing.org.egress_usage_gib += usage
    assert billing.cost == 0.0
    usage = 0.2  # 0.1 * 0.0 + 0.1 * 1.0
    billing.create_egress_events(usage)
    billing.org.egress_usage_gib += usage
    assert round(billing.cost, 2) == 0.1
    usage = 1.2  # 0.9 * 1.0 + 0.3 * 2.0
    billing.create_egress_events(usage)
    billing.org.egress_usage_gib += usage
    assert round(billing.cost, 2) == 1.6
