from contextlib import asynccontextmanager
from typing import Type

import pytest

from jamaibase import JamAI, JamAIAsync
from jamaibase.types import LLMModelConfig, ModelDeploymentConfig, ModelListConfig, OkResponse
from jamaibase.utils import run

CLIENT_CLS = [JamAI, JamAIAsync]
ORG_ID = "default"


@asynccontextmanager
async def _set_org_model_config(
    jamai: JamAI | JamAIAsync,
    org_id: str,
    config: ModelListConfig,
):
    old_config = await run(jamai.admin.organization.get_org_model_config, org_id)
    try:
        response = await run(jamai.admin.organization.set_org_model_config, org_id, config)
        assert isinstance(response, OkResponse)
        yield response
    finally:
        await run(jamai.admin.organization.set_org_model_config, org_id, old_config)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_get_set_org_model_config(
    client_cls: Type[JamAI | JamAIAsync],
):
    jamai = client_cls()
    # Get model config
    config = await run(jamai.admin.organization.get_org_model_config, ORG_ID)
    assert isinstance(config, ModelListConfig)
    assert isinstance(config.models, list)
    assert len(config.models) == 0
    assert isinstance(config.llm_models, list)
    assert isinstance(config.embed_models, list)
    assert isinstance(config.rerank_models, list)
    assert len(config.llm_models) == 0
    assert len(config.embed_models) == 0
    assert len(config.rerank_models) == 0
    llm_model_ids = [m.id for m in config.llm_models]
    assert "ellm/new_model" not in llm_model_ids
    model_ids = await run(jamai.model_names, capabilities=["chat"])
    assert "ellm/new_model" not in model_ids
    # Set
    new_config = config.model_copy(deep=True)
    new_config.llm_models.append(
        LLMModelConfig(
            id="ellm/new_model",
            name="ELLM New Model",
            deployments=[
                ModelDeploymentConfig(
                    provider="ellm",
                )
            ],
            context_length=8000,
            languages=["mul"],
            capabilities=["chat"],
            owned_by=ORG_ID,
        )
    )
    async with _set_org_model_config(jamai, ORG_ID, new_config) as response:
        assert isinstance(response, OkResponse)
        # Fetch again
        new_config = await run(jamai.admin.organization.get_org_model_config, ORG_ID)
        assert isinstance(new_config, ModelListConfig)
        assert len(new_config.llm_models) == 1
        assert len(new_config.embed_models) == 0
        assert len(new_config.rerank_models) == 0
        llm_model_ids = [m.id for m in new_config.llm_models]
        assert "ellm/new_model" in llm_model_ids
        # Fetch model list
        models = await run(jamai.model_names, capabilities=["chat"])
        assert isinstance(models, list)
        assert "ellm/new_model" in models
