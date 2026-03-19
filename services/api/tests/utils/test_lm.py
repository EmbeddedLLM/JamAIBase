from types import SimpleNamespace

from owl.types import CloudProvider, ModelProvider, OnPremProvider
from owl.utils.lm import DeploymentContext, DeploymentRouter


def _make_router(*, owned_by: str = "openai") -> DeploymentRouter:
    router = DeploymentRouter.__new__(DeploymentRouter)
    router.config = SimpleNamespace(owned_by=owned_by)
    return router


def _make_ellm_context(*, is_reasoning_model: bool = True) -> DeploymentContext:
    return DeploymentContext(
        deployment=SimpleNamespace(provider=CloudProvider.ELLM),
        api_key="dummy",
        routing_id="Qwen/Qwen3.5-35B-A3B",
        inference_provider=CloudProvider.ELLM,
        is_reasoning_model=is_reasoning_model,
    )


def _make_vllm_context(*, is_reasoning_model: bool = True) -> DeploymentContext:
    return DeploymentContext(
        deployment=SimpleNamespace(provider=OnPremProvider.VLLM),
        api_key="dummy",
        routing_id="Qwen/Qwen3.5-35B-A3B",
        inference_provider=OnPremProvider.VLLM,
        is_reasoning_model=is_reasoning_model,
    )


def test_inference_provider_should_prefer_vllm_cloud_over_owned_by() -> None:
    router = _make_router()

    assert (
        router._inference_provider(CloudProvider.VLLM_CLOUD, "openai") == CloudProvider.VLLM_CLOUD
    )


def test_inference_provider_should_prefer_ellm_over_owned_by() -> None:
    router = _make_router()

    assert router._inference_provider(CloudProvider.ELLM, "openai") == CloudProvider.ELLM


def test_inference_provider_should_use_owned_by_for_azure_openai() -> None:
    router = _make_router()

    assert router._inference_provider(CloudProvider.AZURE, "openai") == ModelProvider.OPENAI


def test_ellm_default_disables_reasoning() -> None:
    router = _make_router()
    ctx = _make_ellm_context()
    hyperparams: dict[str, object] = {}

    router._prepare_hyperparams(ctx, hyperparams)

    assert hyperparams["reasoning_effort"] == "disable"
    assert hyperparams["allowed_openai_params"] == ["reasoning_effort"]


def test_ellm_explicitly_disable_reasoning() -> None:
    router = _make_router()
    ctx = _make_ellm_context()
    hyperparams: dict[str, object] = {"reasoning_effort": "disable"}

    router._prepare_hyperparams(ctx, hyperparams)

    assert hyperparams["reasoning_effort"] == "disable"
    assert hyperparams["allowed_openai_params"] == ["reasoning_effort"]


def test_vllm_default_does_not_disable_thinking() -> None:
    router = _make_router()
    ctx = _make_vllm_context()
    hyperparams: dict[str, object] = {}

    router._prepare_hyperparams(ctx, hyperparams)

    assert "extra_body" not in hyperparams


def test_vllm_explicitly_disable_thinking() -> None:
    router = _make_router()
    ctx = _make_vllm_context()
    hyperparams: dict[str, object] = {"reasoning_effort": "disable"}

    router._prepare_hyperparams(ctx, hyperparams)

    assert hyperparams["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}

    hyperparams = {"reasoning_effort": "none"}

    router._prepare_hyperparams(ctx, hyperparams)

    assert hyperparams["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
