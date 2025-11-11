import pytest

from jamaibase import JamAI
from jamaibase.types import (
    DeploymentRead,
    DeploymentUpdate,
    ModelConfigRead,
)
from owl.types import CloudProvider, DeploymentCreate, OkResponse, Page
from owl.utils.exceptions import (
    BadInputError,
    ForbiddenError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from owl.utils.test import (
    GPT_4O_MINI_CONFIG,
    GPT_4O_MINI_DEPLOYMENT,
    SMOL_LM2_CONFIG,
    create_deployment,
    create_model_config,
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


if __name__ == "__main__":
    test_create_model_config()
