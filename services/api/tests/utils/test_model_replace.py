from contextlib import ExitStack
from dataclasses import dataclass

import pytest

from jamaibase import JamAI
from jamaibase.types import (
    ColumnSchemaCreate,
    DeploymentCreate,
    ImageGenConfig,
    LLMGenConfig,
    ModelConfigCreate,
    OrganizationCreate,
    RAGParams,
)
from jamaibase.utils.background_loop import LOOP
from owl.configs import ENV_CONFIG
from owl.db.gen_table import GENTABLE_ENGINE
from owl.types import (
    CloudProvider,
    ModelCapability,
    ModelType,
    TableType,
)
from owl.utils import uuid7_str
from owl.utils.gen_table_model_replace import (
    GenTableModelReplacer,
    ModelReplaceStats,
)
from owl.utils.test import (
    ELLM_EMBEDDING_CONFIG,
    ELLM_EMBEDDING_DEPLOYMENT,
    GPT_41_NANO_CONFIG,
    GPT_41_NANO_DEPLOYMENT,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_table,
    create_user,
    setup_organizations,
)


@dataclass(slots=True)
class ReplacementModels:
    old_chat: str
    new_chat: str
    old_rerank: str
    new_rerank: str
    old_image: str
    new_image: str
    embed_model: str


@dataclass(slots=True)
class TableSetup:
    client: JamAI
    organization_id: str
    project_id: str
    action_table_id: str
    knowledge_table_id: str
    chat_table_id: str


@dataclass(slots=True)
class ModelReplaceSetup:
    superuser_id: str


@pytest.fixture
def setup() -> ModelReplaceSetup:
    with setup_organizations() as ctx:
        yield ModelReplaceSetup(superuser_id=ctx.superuser.id)


def _unique_model_id(prefix: str) -> str:
    return f"{prefix}-{uuid7_str()}"


def _create_llm_config(model_id: str) -> ModelConfigCreate:
    return GPT_41_NANO_CONFIG.model_copy(update={"id": model_id, "name": f"Test LLM {model_id}"})


def _create_llm_deployment(model_id: str) -> DeploymentCreate:
    return GPT_41_NANO_DEPLOYMENT.model_copy(
        update={
            "model_id": model_id,
            "name": f"Test LLM Deployment {model_id}",
            "routing_id": GPT_41_NANO_DEPLOYMENT.routing_id,
        }
    )


def _create_rerank_config(model_id: str) -> ModelConfigCreate:
    return RERANK_ENGLISH_v3_SMALL_CONFIG.model_copy(
        update={"id": model_id, "name": f"Test Rerank {model_id}"}
    )


def _create_rerank_deployment(model_id: str) -> DeploymentCreate:
    return RERANK_ENGLISH_v3_SMALL_DEPLOYMENT.model_copy(
        update={
            "model_id": model_id,
            "name": f"Test Rerank Deployment {model_id}",
            "routing_id": RERANK_ENGLISH_v3_SMALL_DEPLOYMENT.routing_id,
        }
    )


def _create_embed_config(model_id: str) -> ModelConfigCreate:
    return ELLM_EMBEDDING_CONFIG.model_copy(
        update={"id": model_id, "name": f"Test Embed {model_id}"}
    )


def _create_embed_deployment(model_id: str) -> DeploymentCreate:
    return ELLM_EMBEDDING_DEPLOYMENT.model_copy(
        update={
            "model_id": model_id,
            "name": f"Test Embed Deployment {model_id}",
            "routing_id": model_id,
        }
    )


def _create_image_config(model_id: str) -> ModelConfigCreate:
    return ModelConfigCreate(
        id=model_id,
        type=ModelType.IMAGE_GEN,
        name=f"Test Image {model_id}",
        capabilities=[ModelCapability.IMAGE_OUT, ModelCapability.IMAGE],
        context_length=8192,
        languages=["en"],
        owned_by="openai",
    )


def _create_image_deployment(model_id: str) -> DeploymentCreate:
    return DeploymentCreate(
        model_id=model_id,
        name=f"Test Image Deployment {model_id}",
        provider=CloudProvider.ELLM,
        routing_id=model_id,
        api_base=ENV_CONFIG.test_llm_api_base,
    )


def _create_replacement_models(
    stack: ExitStack,
    *,
    superuser_id: str,
    deploy_new_bad_chat: bool = True,
) -> ReplacementModels:
    old_chat = _unique_model_id("openai/old-chat")
    new_chat = _unique_model_id("openai/new-chat")
    old_rerank = _unique_model_id("cohere/old-rerank")
    new_rerank = _unique_model_id("cohere/new-rerank")
    old_image = _unique_model_id("openai/old-image")
    new_image = _unique_model_id("openai/new-image")
    embed_model = _unique_model_id("ellm/rag-embed")

    for model_config in (
        _create_llm_config(old_chat),
        _create_llm_config(new_chat),
        _create_rerank_config(old_rerank),
        _create_rerank_config(new_rerank),
        _create_image_config(old_image),
        _create_image_config(new_image),
        _create_embed_config(embed_model),
    ):
        stack.enter_context(create_model_config(model_config, user_id=superuser_id))

    for deployment in (
        _create_llm_deployment(old_chat),
        _create_rerank_deployment(old_rerank),
        _create_rerank_deployment(new_rerank),
        _create_image_deployment(old_image),
        _create_image_deployment(new_image),
        _create_embed_deployment(embed_model),
    ):
        stack.enter_context(create_deployment(deployment, user_id=superuser_id))
    if deploy_new_bad_chat:
        stack.enter_context(
            create_deployment(_create_llm_deployment(new_chat), user_id=superuser_id)
        )

    return ReplacementModels(
        old_chat=old_chat,
        new_chat=new_chat,
        old_rerank=old_rerank,
        new_rerank=new_rerank,
        old_image=old_image,
        new_image=new_image,
        embed_model=embed_model,
    )


def _mapping(models: ReplacementModels) -> dict[str, str]:
    return {
        models.old_chat: models.new_chat,
        models.old_rerank: models.new_rerank,
        models.old_image: models.new_image,
    }


def _create_tables(
    stack: ExitStack,
    *,
    organization_name: str,
    models: ReplacementModels,
) -> TableSetup:
    superuser = stack.enter_context(
        create_user({"email": f"model-replace-{uuid7_str()}@example.com", "name": "System Admin"})
    )
    organization = stack.enter_context(
        create_organization(OrganizationCreate(name=organization_name), user_id=superuser.id)
    )
    project = stack.enter_context(
        create_project(
            {"name": f"{organization_name} Project"},
            user_id=superuser.id,
            organization_id=organization.id,
        )
    )
    client = JamAI(user_id=superuser.id, project_id=project.id)
    knowledge_table = stack.enter_context(
        create_table(
            client,
            TableType.KNOWLEDGE,
            table_id=f"model_replace_kt_{uuid7_str()}",
            cols=[
                ColumnSchemaCreate(
                    id="knowledge_llm_out",
                    dtype="str",
                    gen_config=LLMGenConfig(model=models.old_chat, prompt="${Title}"),
                ),
            ],
            embedding_model=models.embed_model,
        )
    )
    action_table = stack.enter_context(
        create_table(
            client,
            TableType.ACTION,
            table_id=f"model_replace_at_{uuid7_str()}",
            cols=[
                ColumnSchemaCreate(id="input", dtype="str"),
                ColumnSchemaCreate(
                    id="llm_out",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model=models.old_chat,
                        prompt="${input}",
                        rag_params=RAGParams(
                            table_id=knowledge_table.id,
                            reranking_model=models.old_rerank,
                        ),
                    ),
                ),
                ColumnSchemaCreate(
                    id="image_out",
                    dtype="image",
                    gen_config=ImageGenConfig(
                        model=models.old_image,
                        prompt="Generate ${input}",
                        size="1024x1024",
                    ),
                ),
            ],
        )
    )
    chat_table = stack.enter_context(
        create_table(
            client,
            TableType.CHAT,
            table_id=f"model_replace_ct_{uuid7_str()}",
            cols=[],
            chat_cols=[
                ColumnSchemaCreate(id="User", dtype="str"),
                ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=LLMGenConfig(model=models.old_chat, prompt="${User}"),
                ),
            ],
        )
    )
    return TableSetup(
        client=client,
        organization_id=organization.id,
        project_id=project.id,
        action_table_id=action_table.id,
        knowledge_table_id=knowledge_table.id,
        chat_table_id=chat_table.id,
    )


def _run_replacer(
    *,
    mapping: dict[str, str],
    organization_ids: list[str] | None,
    progress_key: str | None = None,
) -> ModelReplaceStats:
    try:
        return LOOP.run(
            GenTableModelReplacer(
                mapping=mapping,
                organization_ids=organization_ids,
                progress_key=progress_key or f"test_gen_table_model_replace:{uuid7_str()}",
            ).run()
        )
    finally:
        LOOP.run(GENTABLE_ENGINE.close())


def _assert_action_models(
    setup: TableSetup,
    *,
    llm_model: str,
    rerank_model: str,
    image_model: str,
) -> None:
    table = setup.client.table.get_table(TableType.ACTION, setup.action_table_id)
    llm_config = table.cfg_map["llm_out"]
    image_config = table.cfg_map["image_out"]
    assert isinstance(llm_config, LLMGenConfig)
    assert llm_config.model == llm_model
    assert llm_config.rag_params is not None
    assert llm_config.rag_params.reranking_model == rerank_model
    assert isinstance(image_config, ImageGenConfig)
    assert image_config.model == image_model


def _assert_chat_model(setup: TableSetup, *, llm_model: str) -> None:
    table = setup.client.table.get_table(TableType.CHAT, setup.chat_table_id)
    llm_config = table.cfg_map["AI"]
    assert isinstance(llm_config, LLMGenConfig)
    assert llm_config.model == llm_model


def _assert_knowledge_model(setup: TableSetup, *, llm_model: str) -> None:
    table = setup.client.table.get_table(TableType.KNOWLEDGE, setup.knowledge_table_id)
    llm_config = table.cfg_map["knowledge_llm_out"]
    assert isinstance(llm_config, LLMGenConfig)
    assert llm_config.model == llm_model


def test_organization_filter_limits_scan_and_mutation_scope(setup: ModelReplaceSetup):
    with ExitStack() as stack:
        models = _create_replacement_models(stack, superuser_id=setup.superuser_id)
        included = _create_tables(stack, organization_name="Included Replace Org", models=models)
        excluded = _create_tables(stack, organization_name="Excluded Replace Org", models=models)

        result = _run_replacer(
            mapping=_mapping(models),
            organization_ids=[included.organization_id],
        )

        assert result.updated_columns == 5
        assert result.tables_updated == 3
        _assert_action_models(
            included,
            llm_model=models.new_chat,
            rerank_model=models.new_rerank,
            image_model=models.new_image,
        )
        _assert_knowledge_model(included, llm_model=models.new_chat)
        _assert_chat_model(included, llm_model=models.new_chat)
        _assert_action_models(
            excluded,
            llm_model=models.old_chat,
            rerank_model=models.old_rerank,
            image_model=models.old_image,
        )
        _assert_knowledge_model(excluded, llm_model=models.old_chat)
        _assert_chat_model(excluded, llm_model=models.old_chat)


def test_table_level_failure_skips_failed_table_and_continues(setup: ModelReplaceSetup):
    with ExitStack() as stack:
        good_models = _create_replacement_models(stack, superuser_id=setup.superuser_id)
        bad_models = _create_replacement_models(
            stack,
            superuser_id=setup.superuser_id,
            deploy_new_bad_chat=False,
        )
        good_setup = _create_tables(
            stack,
            organization_name="Good Replace Org",
            models=good_models,
        )
        bad_setup = _create_tables(
            stack,
            organization_name="Bad Replace Org",
            models=bad_models,
        )

        result = _run_replacer(
            mapping={
                good_models.old_chat: good_models.new_chat,
                bad_models.old_chat: bad_models.new_chat,
            },
            organization_ids=[good_setup.organization_id, bad_setup.organization_id],
        )

        assert result.updated_columns == 3
        assert result.tables_updated == 3
        assert result.tables_failed == 3
        assert result.failed_columns == 3
        _assert_action_models(
            good_setup,
            llm_model=good_models.new_chat,
            rerank_model=good_models.old_rerank,
            image_model=good_models.old_image,
        )
        _assert_knowledge_model(good_setup, llm_model=good_models.new_chat)
        _assert_chat_model(good_setup, llm_model=good_models.new_chat)
        _assert_action_models(
            bad_setup,
            llm_model=bad_models.old_chat,
            rerank_model=bad_models.old_rerank,
            image_model=bad_models.old_image,
        )
        _assert_knowledge_model(bad_setup, llm_model=bad_models.old_chat)
        _assert_chat_model(bad_setup, llm_model=bad_models.old_chat)
