from datetime import timedelta
from types import SimpleNamespace

import pytest

from owl.configs import CACHE
from owl.types import CloudProvider, ModelCapability, ModelProvider, ModelType, OnPremProvider
from owl.utils.dates import now
from owl.utils.exceptions import InsufficientCreditsError, ModelOverloadError, RateLimitExceedError
from owl.utils.lm import DeploymentContext, DeploymentRouter


class _BillingSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bool]] = []

    def get_byok_key(self, provider: str) -> str:
        return ""

    def has_llm_quota(
        self,
        *,
        model_id: str,
        is_byok: bool = False,
    ) -> None:
        self.calls.append(("llm", model_id, is_byok))

    def has_image_gen_quota(
        self,
        *,
        model_id: str,
        is_byok: bool = False,
    ) -> None:
        self.calls.append(("image_gen", model_id, is_byok))

    def has_embedding_quota(
        self,
        *,
        model_id: str,
        is_byok: bool = False,
    ) -> None:
        self.calls.append(("embed", model_id, is_byok))

    def has_reranker_quota(
        self,
        *,
        model_id: str,
        is_byok: bool = False,
    ) -> None:
        self.calls.append(("rerank", model_id, is_byok))


class _BillingQuotaFallbackSpy(_BillingSpy):
    def __init__(self) -> None:
        super().__init__()
        self.byok_key = "ORG_KEY"

    def get_byok_key(self, provider: str) -> str:
        return self.byok_key

    def has_llm_quota(
        self,
        *,
        model_id: str,
        is_byok: bool = False,
    ) -> None:
        self.calls.append(("llm", model_id, is_byok))
        if not is_byok:
            raise InsufficientCreditsError("no credits")


def _make_router(
    *,
    owned_by: str = "openai",
    model_id: str = "openai/test-model",
    model_type: ModelType = ModelType.LLM,
    billing: _BillingSpy | None = None,
) -> DeploymentRouter:
    router = DeploymentRouter.__new__(DeploymentRouter)
    router.config = SimpleNamespace(owned_by=owned_by, id=model_id, type=model_type)
    router.request = SimpleNamespace(state=SimpleNamespace(billing=billing))
    return router


def _make_deployment(
    *,
    deployment_id: str,
    provider: str = "openai",
    weight: int = 1,
):
    return SimpleNamespace(
        id=deployment_id,
        provider=provider,
        routing_id="gpt-4.1-nano",
        weight=weight,
        cooldown_until=now(),
    )


def _make_router_for_deployment(
    *,
    billing: _BillingSpy | None = None,
    deployments: list[SimpleNamespace] | None = None,
) -> DeploymentRouter:
    router = _make_router(
        owned_by="ellm",
        model_id="ellm/gpt-4.1-nano",
        model_type=ModelType.LLM,
        billing=billing,
    )
    router.config = SimpleNamespace(
        id="ellm/gpt-4.1-nano",
        name="GPT 4.1 nano",
        type=ModelType.LLM,
        owned_by="ellm",
        capabilities=[ModelCapability.CHAT],
        deployments=deployments or [_make_deployment(deployment_id="dep_1")],
    )
    router.organization = SimpleNamespace(id="org_1", get_external_key=lambda provider: "")
    router.request = SimpleNamespace(state=SimpleNamespace(billing=billing, timing={}))
    router._model_display_id = router.config.id
    router.id = "router-1"
    router.cooldown = 30
    router.chosen_credential = None
    router._byok_key_cache = {}
    return router


async def _clear_byok_cooldown(*routers: DeploymentRouter) -> None:
    for router in routers:
        for deployment in router.config.deployments:
            await CACHE.delete(router._byok_cooldown_key(deployment.id))


async def _require_cache() -> None:
    try:
        await CACHE.exists("__pytest__:byok_cooldown")
    except Exception as exc:
        pytest.skip(f"Redis cache unavailable: {exc!r}")


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


def test_check_quota_should_use_actual_provider_for_llm() -> None:
    billing = _BillingSpy()
    router = _make_router(
        model_id="ellm/gpt-4.1-nano",
        model_type=ModelType.LLM,
        billing=billing,
    )

    router._check_quota(True)

    assert billing.calls == [("llm", "ellm/gpt-4.1-nano", True)]


def test_check_quota_should_dispatch_image_models_to_image_quota() -> None:
    billing = _BillingSpy()
    router = _make_router(
        model_id="ellm/gpt-image-1",
        model_type=ModelType.IMAGE_GEN,
        billing=billing,
    )

    router._check_quota(False)

    assert billing.calls == [("image_gen", "ellm/gpt-image-1", False)]


@pytest.mark.asyncio
async def test_resolve_credentials_should_fallback_to_system_when_byok_is_cooled_down() -> None:
    router = _make_router_for_deployment()

    def _get_byok_key(provider: str) -> str:
        assert provider == "openai"
        return "ORG_KEY"

    async def _get_system_key(provider: str) -> str:
        assert provider == "openai"
        return "SYSTEM_KEY"

    async def _is_byok_cooldown_active(deployment_id: str) -> bool:
        assert deployment_id == "dep_1"
        return True

    router._get_byok_key = _get_byok_key
    router._get_system_key = _get_system_key
    router._is_byok_cooldown_active = _is_byok_cooldown_active

    credentials = await router._resolve_credentials(SimpleNamespace(id="dep_1", provider="openai"))

    assert len(credentials) == 1
    assert credentials[0].api_key == "SYSTEM_KEY"
    assert credentials[0].provider == "openai"
    assert credentials[0].source == "system"
    assert credentials[0].is_byok is False


@pytest.mark.asyncio
async def test_byok_cooldown_should_be_scoped_by_org_and_deployment() -> None:
    router_a = _make_router_for_deployment()
    router_b = _make_router_for_deployment()
    router_b.organization = SimpleNamespace(id="org_2", get_external_key=lambda provider: "")

    await _require_cache()
    await _clear_byok_cooldown(router_a, router_b)
    try:
        await router_a._cooldown_byok_deployment("dep_1", timedelta(seconds=30))
        assert await router_a._is_byok_cooldown_active("dep_1") is True
        assert await router_b._is_byok_cooldown_active("dep_1") is False
    finally:
        await _clear_byok_cooldown(router_a, router_b)


@pytest.mark.asyncio
async def test_byok_rate_limit_cooldown_should_not_affect_other_org_on_same_deployment(
    monkeypatch,
) -> None:
    billing = _BillingSpy()
    billing.get_byok_key = lambda provider: "ORG_KEY"
    router_a = _make_router_for_deployment(billing=billing)
    router_b = _make_router_for_deployment(billing=billing)
    router_b.organization = SimpleNamespace(id="org_2", get_external_key=lambda provider: "")

    async def _get_system_key(provider: str) -> str:
        return ""

    monkeypatch.setattr("owl.utils.lm.litellm.supports_reasoning", lambda _: False)
    router_a._get_system_key = _get_system_key
    router_b._get_system_key = _get_system_key

    await _require_cache()
    await _clear_byok_cooldown(router_a, router_b)
    try:
        with pytest.raises(RateLimitExceedError):
            async with router_a._get_deployment():
                raise RateLimitExceedError(
                    "rate limited",
                    limit=10,
                    remaining=0,
                    reset_at=123,
                    retry_after=7,
                )

        assert await router_a._is_byok_cooldown_active("dep_1") is True
        assert await router_b._is_byok_cooldown_active("dep_1") is False
    finally:
        await _clear_byok_cooldown(router_a, router_b)


@pytest.mark.asyncio
async def test_byok_model_overload_cooldown_should_not_affect_other_org_on_same_deployment(
    monkeypatch,
) -> None:
    billing = _BillingSpy()
    billing.get_byok_key = lambda provider: "ORG_KEY"
    router_a = _make_router_for_deployment(billing=billing)
    router_b = _make_router_for_deployment(billing=billing)
    router_b.organization = SimpleNamespace(id="org_2", get_external_key=lambda provider: "")

    async def _get_system_key(provider: str) -> str:
        return ""

    monkeypatch.setattr("owl.utils.lm.litellm.supports_reasoning", lambda _: False)
    router_a._get_system_key = _get_system_key
    router_b._get_system_key = _get_system_key

    await _require_cache()
    await _clear_byok_cooldown(router_a, router_b)
    try:
        with pytest.raises(ModelOverloadError):
            async with router_a._get_deployment():
                raise ModelOverloadError("overloaded")

        assert await router_a._is_byok_cooldown_active("dep_1") is True
        assert await router_b._is_byok_cooldown_active("dep_1") is False
    finally:
        await _clear_byok_cooldown(router_a, router_b)


@pytest.mark.asyncio
async def test_get_deployment_should_cooldown_byok_path_for_model_overload(monkeypatch) -> None:
    billing = _BillingSpy()
    billing.get_byok_key = lambda provider: "ORG_KEY"
    router = _make_router_for_deployment(billing=billing)

    async def _is_byok_cooldown_active(deployment_id: str) -> bool:
        return False

    async def _get_system_key(provider: str) -> str:
        return ""

    byok_cooldowns: list[str] = []
    deployment_cooldowns: list[str] = []

    async def _cooldown_byok_deployment(deployment_id: str, cooldown_time: timedelta) -> None:
        byok_cooldowns.append(deployment_id)

    async def _cooldown_deployment(deployment, cooldown_time: timedelta) -> None:
        deployment_cooldowns.append(deployment.id)

    monkeypatch.setattr("owl.utils.lm.litellm.supports_reasoning", lambda _: False)
    router._is_byok_cooldown_active = _is_byok_cooldown_active
    router._get_system_key = _get_system_key
    router._cooldown_byok_deployment = _cooldown_byok_deployment
    router._cooldown_deployment = _cooldown_deployment

    with pytest.raises(ModelOverloadError):
        async with router._get_deployment():
            raise ModelOverloadError("overloaded")

    assert byok_cooldowns == ["dep_1"]
    assert deployment_cooldowns == []


@pytest.mark.asyncio
async def test_get_deployment_should_cooldown_system_deployment_for_rate_limit(
    monkeypatch,
) -> None:
    billing = _BillingSpy()
    router = _make_router_for_deployment(
        billing=billing,
        deployments=[
            _make_deployment(deployment_id="dep_1"),
            _make_deployment(deployment_id="dep_2"),
        ],
    )

    async def _is_byok_cooldown_active(deployment_id: str) -> bool:
        return False

    async def _get_system_key(provider: str) -> str:
        return "SYSTEM_KEY"

    byok_cooldowns: list[str] = []
    deployment_cooldowns: list[str] = []

    async def _cooldown_byok_deployment(deployment_id: str, cooldown_time: timedelta) -> None:
        byok_cooldowns.append(deployment_id)

    async def _cooldown_deployment(deployment, cooldown_time: timedelta) -> None:
        deployment_cooldowns.append(deployment.id)

    monkeypatch.setattr("owl.utils.lm.litellm.supports_reasoning", lambda _: False)
    monkeypatch.setattr("owl.utils.lm.random.choices", lambda seq, weights, k: [seq[0]])
    router._is_byok_cooldown_active = _is_byok_cooldown_active
    router._get_system_key = _get_system_key
    router._cooldown_byok_deployment = _cooldown_byok_deployment
    router._cooldown_deployment = _cooldown_deployment

    with pytest.raises(RateLimitExceedError):
        async with router._get_deployment():
            raise RateLimitExceedError(
                "rate limited",
                limit=10,
                remaining=0,
                reset_at=123,
                retry_after=7,
            )

    assert byok_cooldowns == []
    assert deployment_cooldowns == ["dep_1"]


@pytest.mark.asyncio
async def test_get_deployment_should_cooldown_system_deployment_for_model_overload(
    monkeypatch,
) -> None:
    billing = _BillingSpy()
    router = _make_router_for_deployment(
        billing=billing,
        deployments=[
            _make_deployment(deployment_id="dep_1"),
            _make_deployment(deployment_id="dep_2"),
        ],
    )

    async def _is_byok_cooldown_active(deployment_id: str) -> bool:
        return False

    async def _get_system_key(provider: str) -> str:
        return "SYSTEM_KEY"

    byok_cooldowns: list[str] = []
    deployment_cooldowns: list[str] = []

    async def _cooldown_byok_deployment(deployment_id: str, cooldown_time: timedelta) -> None:
        byok_cooldowns.append(deployment_id)

    async def _cooldown_deployment(deployment, cooldown_time: timedelta) -> None:
        deployment_cooldowns.append(deployment.id)

    monkeypatch.setattr("owl.utils.lm.litellm.supports_reasoning", lambda _: False)
    monkeypatch.setattr("owl.utils.lm.random.choices", lambda seq, weights, k: [seq[0]])
    router._is_byok_cooldown_active = _is_byok_cooldown_active
    router._get_system_key = _get_system_key
    router._cooldown_byok_deployment = _cooldown_byok_deployment
    router._cooldown_deployment = _cooldown_deployment

    with pytest.raises(ModelOverloadError):
        async with router._get_deployment():
            raise ModelOverloadError("overloaded")

    assert byok_cooldowns == []
    assert deployment_cooldowns == ["dep_1"]


@pytest.mark.asyncio
async def test_get_deployment_should_preserve_byok_transient_error_over_system_quota_failure(
    monkeypatch,
) -> None:
    billing = _BillingQuotaFallbackSpy()
    router = _make_router_for_deployment(billing=billing)
    byok_cooled_down = False

    async def _is_byok_cooldown_active(deployment_id: str) -> bool:
        return byok_cooled_down

    async def _get_system_key(provider: str) -> str:
        return "SYSTEM_KEY"

    async def _cooldown_byok_deployment(deployment_id: str, cooldown_time: timedelta) -> None:
        nonlocal byok_cooled_down
        byok_cooled_down = True

    monkeypatch.setattr("owl.utils.lm.litellm.supports_reasoning", lambda _: False)
    router._is_byok_cooldown_active = _is_byok_cooldown_active
    router._get_system_key = _get_system_key
    router._cooldown_byok_deployment = _cooldown_byok_deployment

    with pytest.raises(RateLimitExceedError):
        async with router._get_deployment():
            raise RateLimitExceedError(
                "rate limited",
                limit=10,
                remaining=0,
                reset_at=123,
                retry_after=7,
            )

    with pytest.raises(RateLimitExceedError):
        async with router._get_deployment():
            pytest.fail("quota check should fail before yielding")


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
