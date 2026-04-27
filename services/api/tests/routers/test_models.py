import pytest

from jamaibase import JamAI
from jamaibase.types import (
    ColumnSchemaCreate,
    DeploymentRead,
    DeploymentUpdate,
    GenTableModelReplaceProgressKeys,
    GenTableModelReplaceRequest,
    LLMGenConfig,
    ModelConfigRead,
    OrganizationCreate,
)
from owl.configs import ENV_CONFIG
from owl.types import CloudProvider, DeploymentCreate, OkResponse, Page, TableType
from owl.utils import uuid7_str
from owl.utils.exceptions import (
    BadInputError,
    ForbiddenError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from owl.utils.test import (
    ELLM_EMBEDDING_CONFIG,
    ELLM_EMBEDDING_DEPLOYMENT,
    GPT_4O_MINI_CONFIG,
    GPT_4O_MINI_DEPLOYMENT,
    SMOL_LM2_CONFIG,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_table,
    create_user,
    setup_organizations,
)


def test_create_model_config():
    with setup_organizations():
        with create_model_config(SMOL_LM2_CONFIG) as model:
            assert isinstance(model, ModelConfigRead)
            assert model.id == SMOL_LM2_CONFIG.id
            assert model.type == SMOL_LM2_CONFIG.type
            assert model.name == SMOL_LM2_CONFIG.name
            assert model.context_length == SMOL_LM2_CONFIG.context_length
            assert model.capabilities == SMOL_LM2_CONFIG.capabilities


def test_create_existing_model_config():
    with setup_organizations():
        with create_model_config(SMOL_LM2_CONFIG) as model:
            assert model.id == SMOL_LM2_CONFIG.id
            with pytest.raises(ResourceExistsError):
                with create_model_config(SMOL_LM2_CONFIG):
                    pass


def test_list_system_model_configs():
    with setup_organizations() as ctx:
        with create_model_config(SMOL_LM2_CONFIG):
            # OK
            models = JamAI(user_id=ctx.superuser.id).models.list_model_configs()
            assert isinstance(models, Page)
            assert len(models.items) == 1
            assert models.total == 1


@pytest.mark.cloud
def test_list_system_model_configs_permission():
    with setup_organizations() as ctx:
        with create_model_config(SMOL_LM2_CONFIG):
            # No permission
            with pytest.raises(ForbiddenError):
                JamAI(user_id=ctx.user.id).models.list_model_configs()


def test_get_model_config():
    with setup_organizations() as ctx:
        with create_model_config(SMOL_LM2_CONFIG) as model:
            client = JamAI(user_id=ctx.superuser.id)
            # Fetch
            response = client.models.get_model_config(model.id)
            assert isinstance(response, ModelConfigRead)
            assert response.model_dump() == model.model_dump()


def test_get_nonexistent_model_config():
    with setup_organizations() as ctx:
        client = JamAI(user_id=ctx.superuser.id)
        with pytest.raises(ResourceNotFoundError):
            client.models.get_model_config("nonexistent-model")


def test_update_model_config():
    """
    Test updating a model config.
    - Update name
    - Update ID and ensure foreign keys of deployments are updated
    - `owned_by` and `id` must match for ELLM models
    """
    with setup_organizations() as ctx:
        with (
            create_model_config(GPT_4O_MINI_CONFIG) as model,
            create_deployment(GPT_4O_MINI_DEPLOYMENT) as deployment,
        ):
            assert isinstance(model, ModelConfigRead)
            client = JamAI(user_id=ctx.superuser.id)
            # Update name
            new_name = "NEW MODEL"
            model = client.models.update_model_config(model.id, dict(name=new_name))
            assert isinstance(model, ModelConfigRead)
            assert model.id == model.id
            assert model.name == new_name
            # Update meta
            meta = dict(icon="openai")
            model = client.models.update_model_config(model.id, dict(meta=meta))
            assert isinstance(model, ModelConfigRead)
            assert model.id == model.id
            assert model.meta == meta
            # `owned_by` and `id` must match for ELLM models
            new_owned_by = "ellm"
            new_id = "ellm/biglm2:135m"
            with pytest.raises(BadInputError, match="ELLM models must have `owned_by"):
                client.models.update_model_config(model.id, dict(owned_by=new_owned_by))
            with pytest.raises(BadInputError, match="ELLM models must have `owned_by"):
                client.models.update_model_config(model.id, dict(id=new_id))
            # Update ID and `owned_by`
            model = client.models.update_model_config(
                model.id, dict(id=new_id, owned_by=new_owned_by)
            )
            assert isinstance(model, ModelConfigRead)
            assert model.id == new_id
            assert model.name == new_name
            assert model.meta == meta
            assert model.owned_by == new_owned_by
            # Fetch again
            model = client.models.get_model_config(model.id)
            assert isinstance(model, ModelConfigRead)
            assert model.id == new_id
            assert model.name == new_name
            assert model.meta == meta
            assert model.owned_by == new_owned_by
            # Fetch deployment to ensure foreign key is updated
            response = client.models.get_deployment(deployment.id)
            assert isinstance(response, DeploymentRead)
            assert response.model.id == new_id


def test_delete_model_config():
    with setup_organizations() as ctx:
        with create_model_config(SMOL_LM2_CONFIG) as model:
            client = JamAI(user_id=ctx.superuser.id)
            response = client.models.delete_model_config(model.id)
            assert isinstance(response, OkResponse)
            with pytest.raises(ResourceNotFoundError):
                client.models.get_model_config(model.id)


def test_create_cloud_deployment():
    with setup_organizations() as ctx:
        with (
            create_model_config(GPT_4O_MINI_CONFIG) as model,
            create_deployment(GPT_4O_MINI_DEPLOYMENT) as deployment,
        ):
            assert deployment.model_id == model.id
            assert deployment.name == GPT_4O_MINI_DEPLOYMENT.name
            assert deployment.provider == CloudProvider.OPENAI
            assert deployment.routing_id == GPT_4O_MINI_DEPLOYMENT.routing_id

            model = JamAI(user_id=ctx.superuser.id).models.get_model_config(model.id)
            assert isinstance(model, ModelConfigRead)


def test_get_deployment():
    with setup_organizations() as ctx:
        with (
            create_model_config(GPT_4O_MINI_CONFIG) as model,
            create_deployment(
                DeploymentCreate(
                    model_id=model.id,
                    name="Test Deployment",
                    provider=CloudProvider.OPENAI,
                    routing_id="openai/gpt-4o-mini",
                )
            ) as deployment,
        ):
            client = JamAI(user_id=ctx.superuser.id)
            # Fetch
            response = client.models.get_deployment(deployment.id)
            assert isinstance(response, DeploymentRead)
            assert response.model_dump() == deployment.model_dump()


def test_update_deployment():
    with setup_organizations() as ctx:
        with (
            create_model_config(GPT_4O_MINI_CONFIG),
            create_deployment(GPT_4O_MINI_DEPLOYMENT) as deployment,
        ):
            assert deployment.name == GPT_4O_MINI_DEPLOYMENT.name
            client = JamAI(user_id=ctx.superuser.id)
            # Update
            new_name = "NEW DEPLOYMENT"
            deployment = client.models.update_deployment(
                deployment.id, DeploymentUpdate(name=new_name)
            )
            assert isinstance(deployment, DeploymentRead)
            assert deployment.name == new_name
            # Fetch again
            deployment = client.models.get_deployment(deployment.id)
            assert isinstance(deployment, DeploymentRead)
            assert deployment.name == new_name


def _unique_llm_config(prefix: str):
    return SMOL_LM2_CONFIG.model_copy(
        update={
            "id": f"ellm/{prefix}-{uuid7_str()}",
            "name": f"Replace Test {prefix}",
        }
    )


def _unique_llm_deployment(model_id: str) -> DeploymentCreate:
    return DeploymentCreate(
        model_id=model_id,
        name=f"Replace Test Deployment {model_id}",
        provider=CloudProvider.ELLM,
        routing_id=model_id,
        api_base=ENV_CONFIG.test_llm_api_base,
    )


def _unique_embedding_config(prefix: str):
    model_id = f"ellm/{prefix}-{uuid7_str()}"
    return ELLM_EMBEDDING_CONFIG.model_copy(
        update={
            "id": model_id,
            "name": f"Replace Test {prefix}",
        }
    )


def _unique_embedding_deployment(model_id: str) -> DeploymentCreate:
    return ELLM_EMBEDDING_DEPLOYMENT.model_copy(
        update={
            "model_id": model_id,
            "name": f"Replace Test Deployment {model_id}",
            "routing_id": model_id,
        }
    )


def test_replace_model_ids_endpoint_updates_action_knowledge_and_chat_tables():
    with setup_organizations() as ctx:
        old_model_config = _unique_llm_config("replace-old")
        new_model_config = _unique_llm_config("replace-new")
        embedding_config = _unique_embedding_config("replace-embed")
        with (
            create_model_config(old_model_config, user_id=ctx.superuser.id) as old_model,
            create_model_config(new_model_config, user_id=ctx.superuser.id) as new_model,
            create_model_config(embedding_config, user_id=ctx.superuser.id) as embedding_model,
            create_deployment(
                _unique_llm_deployment(old_model.id),
                user_id=ctx.superuser.id,
            ),
            create_deployment(
                _unique_llm_deployment(new_model.id),
                user_id=ctx.superuser.id,
            ),
            create_deployment(
                _unique_embedding_deployment(embedding_model.id),
                user_id=ctx.superuser.id,
            ),
            create_user(
                {"email": f"replace-e2e-{uuid7_str()}@example.com", "name": "Replace User"}
            ) as table_user,
            create_organization(
                OrganizationCreate(name=f"Replace E2E Org {uuid7_str()}"),
                user_id=table_user.id,
            ) as organization,
            create_project(
                {"name": "Replace E2E Project"},
                user_id=table_user.id,
                organization_id=organization.id,
            ) as project,
        ):
            table_client = JamAI(user_id=table_user.id, project_id=project.id)
            knowledge_table = create_table(
                table_client,
                TableType.KNOWLEDGE,
                table_id=f"replace_kt_{uuid7_str()}",
                cols=[
                    ColumnSchemaCreate(
                        id="knowledge_llm_out",
                        dtype="str",
                        gen_config=LLMGenConfig(model=old_model.id, prompt="${Title}"),
                    ),
                ],
                embedding_model=embedding_model.id,
            )
            action_table = create_table(
                table_client,
                TableType.ACTION,
                table_id=f"replace_at_{uuid7_str()}",
                cols=[
                    ColumnSchemaCreate(id="input", dtype="str"),
                    ColumnSchemaCreate(
                        id="action_llm_out",
                        dtype="str",
                        gen_config=LLMGenConfig(model=old_model.id, prompt="${input}"),
                    ),
                ],
            )
            chat_table = create_table(
                table_client,
                TableType.CHAT,
                table_id=f"replace_ct_{uuid7_str()}",
                cols=[],
                chat_cols=[
                    ColumnSchemaCreate(id="User", dtype="str"),
                    ColumnSchemaCreate(
                        id="AI",
                        dtype="str",
                        gen_config=LLMGenConfig(model=old_model.id, prompt="${User}"),
                    ),
                ],
            )
            with knowledge_table as knowledge, action_table as action, chat_table as chat:
                client = JamAI(user_id=ctx.superuser.id)
                response = client.models.replace_model_ids(
                    GenTableModelReplaceRequest(
                        mapping={old_model.id: new_model.id},
                        organization_ids=[organization.id],
                    )
                )

                assert isinstance(response, OkResponse)
                assert response.progress_key.startswith("gen_table_model_replace:")
                progress = client.tasks.poll_progress(response.progress_key, max_wait=30)
                assert progress is not None
                assert progress["state"] == "COMPLETED"
                assert progress["data"]["request"] == {
                    "mapping": {old_model.id: new_model.id},
                    "organization_ids": [organization.id],
                    "requested_by": ctx.superuser.id,
                }
                progress_keys = client.models.list_model_replace_progress_keys()
                assert isinstance(progress_keys, GenTableModelReplaceProgressKeys)
                assert response.progress_key in progress_keys.items

                action_config = table_client.table.get_table(TableType.ACTION, action.id).cfg_map[
                    "action_llm_out"
                ]
                knowledge_config = table_client.table.get_table(
                    TableType.KNOWLEDGE, knowledge.id
                ).cfg_map["knowledge_llm_out"]
                chat_config = table_client.table.get_table(TableType.CHAT, chat.id).cfg_map["AI"]
                assert isinstance(action_config, LLMGenConfig)
                assert isinstance(knowledge_config, LLMGenConfig)
                assert isinstance(chat_config, LLMGenConfig)
                assert action_config.model == new_model.id
                assert knowledge_config.model == new_model.id
                assert chat_config.model == new_model.id


def test_replace_model_ids_endpoint_rejects_missing_source_model_config():
    with setup_organizations() as ctx:
        with create_model_config(
            _unique_llm_config("missing-source-target"),
            user_id=ctx.superuser.id,
        ) as target_model:
            body = GenTableModelReplaceRequest(
                mapping={"missing-old": target_model.id},
            )

            with pytest.raises(ResourceNotFoundError, match="missing-old"):
                JamAI(user_id=ctx.superuser.id).models.replace_model_ids(body)


def test_replace_model_ids_endpoint_rejects_missing_replacement_model_config():
    with setup_organizations() as ctx:
        with create_model_config(
            _unique_llm_config("missing-target-source"),
            user_id=ctx.superuser.id,
        ) as source_model:
            body = GenTableModelReplaceRequest(
                mapping={source_model.id: "missing-new"},
            )

            with pytest.raises(ResourceNotFoundError, match="missing-new"):
                JamAI(user_id=ctx.superuser.id).models.replace_model_ids(body)


def test_replace_model_ids_endpoint_rejects_missing_organization():
    with setup_organizations() as ctx:
        with (
            create_model_config(
                _unique_llm_config("missing-org-source"),
                user_id=ctx.superuser.id,
            ) as source_model,
            create_model_config(
                _unique_llm_config("missing-org-target"),
                user_id=ctx.superuser.id,
            ) as target_model,
        ):
            body = GenTableModelReplaceRequest(
                mapping={source_model.id: target_model.id},
                organization_ids=["missing-org"],
            )

            with pytest.raises(ResourceNotFoundError, match='Organization "missing-org"'):
                JamAI(user_id=ctx.superuser.id).models.replace_model_ids(body)


def test_replace_model_ids_endpoint_rejects_embedding_models():
    with setup_organizations() as ctx:
        embedding_config = ELLM_EMBEDDING_CONFIG.model_copy(
            update={
                "id": f"ellm/embed-replace-{uuid7_str()}",
                "name": "Embedding Replace Test Model",
            }
        )
        with (
            create_model_config(
                _unique_llm_config("embedding-source"),
                user_id=ctx.superuser.id,
            ) as source_model,
            create_model_config(embedding_config, user_id=ctx.superuser.id) as embedding_model,
        ):
            body = GenTableModelReplaceRequest(
                mapping={source_model.id: embedding_model.id},
            )

            with pytest.raises(BadInputError, match="Replacing embedding model is not supported"):
                JamAI(user_id=ctx.superuser.id).models.replace_model_ids(body)


if __name__ == "__main__":
    test_create_model_config()
