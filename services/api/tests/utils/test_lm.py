from types import SimpleNamespace

from owl.types import CloudProvider, ModelProvider
from owl.utils.lm import DeploymentRouter


def _make_router(*, owned_by: str = "openai") -> DeploymentRouter:
    router = DeploymentRouter.__new__(DeploymentRouter)
    router.config = SimpleNamespace(owned_by=owned_by)
    return router


def test_inference_provider_should_prefer_vllm_cloud_over_owned_by() -> None:
    router = _make_router()

    assert (
        router._inference_provider(CloudProvider.VLLM_CLOUD, "openai")
        == CloudProvider.VLLM_CLOUD
    )


def test_inference_provider_should_prefer_ellm_over_owned_by() -> None:
    router = _make_router()

    assert router._inference_provider(CloudProvider.ELLM, "openai") == CloudProvider.ELLM


def test_inference_provider_should_use_owned_by_for_azure_openai() -> None:
    router = _make_router()

    assert router._inference_provider(CloudProvider.AZURE, "openai") == ModelProvider.OPENAI
