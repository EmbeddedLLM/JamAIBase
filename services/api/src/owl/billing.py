from collections import defaultdict
from datetime import datetime, timedelta, timezone
from time import perf_counter

import stripe
from cloudevents.conversion import to_dict
from cloudevents.http import CloudEvent
from fastapi import Request
from loguru import logger
from openmeter.aio import Client as OpenMeterAsyncClient

from jamaibase import JamAIAsync
from jamaibase.exceptions import InsufficientCreditsError
from jamaibase.protocol import EventCreate, OrganizationRead
from owl.configs.manager import CONFIG, ENV_CONFIG, ProductType
from owl.db.gen_table import GenerativeTable
from owl.protocol import (
    EmbeddingModelConfig,
    LLMGenConfig,
    LLMModelConfig,
    RerankingModelConfig,
    UserAgent,
)
from owl.utils import uuid7_str

if ENV_CONFIG.stripe_api_key_plain.strip() == "":
    STRIPE_CLIENT = None
else:
    STRIPE_CLIENT = stripe.StripeClient(
        api_key=ENV_CONFIG.stripe_api_key_plain,
        http_client=stripe.RequestsClient(),
        max_network_retries=5,
    )
if ENV_CONFIG.openmeter_api_key_plain.strip() == "":
    OPENMETER_CLIENT = None
else:
    # Async client can be initialized by importing the `Client` from `openmeter.aio`
    OPENMETER_CLIENT = OpenMeterAsyncClient(
        endpoint="https://openmeter.cloud",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {ENV_CONFIG.openmeter_api_key_plain}",
        },
        retry_status=3,
        retry_total=5,
    )
CLIENT = JamAIAsync(token=ENV_CONFIG.service_key_plain)


class BillingManager:
    def __init__(
        self,
        *,
        organization: OrganizationRead | None = None,
        project_id: str = "",
        user_id: str = "",
        openmeter_client: OpenMeterAsyncClient = OPENMETER_CLIENT,
        client: JamAIAsync | None = CLIENT,
        request: Request | None = None,
    ) -> None:
        self.org = organization
        self.project_id = project_id
        self.user_id = user_id
        self.openmeter_client = openmeter_client
        self.client = client
        self.request = request
        if request is None:
            self.user_agent = UserAgent(is_browser=False, agent="")
        else:
            self.user_agent: UserAgent = request.state.user_agent
        self.is_oss = ENV_CONFIG.is_oss
        self._events = []
        self._deltas = defaultdict(float)
        self._values = defaultdict(float)
        self._cost = 0.0

    @property
    def total_balance(self) -> float:
        if self.is_oss or self.org is None:
            return 0.0
        return self.org.credit + self.org.credit_grant

    def _compute_cost(
        self,
        product_type: ProductType,
        remaining_quota: float,
        usage: float,
    ) -> float:
        if self.org is None:
            return 0.0
        prices = CONFIG.get_pricing()
        try:
            product = prices.plans[self.org.tier].products[product_type]
        except Exception as e:
            logger.warning(f"Failed to fetch product: {e}")
            return 0.0
        cost = 0.0
        remaining_usage = (usage - remaining_quota) if remaining_quota > 0 else usage
        for tier in product.tiers:
            if remaining_usage <= 0:
                break
            if tier.up_to is not None and remaining_usage > tier.up_to:
                tier_usage = tier.up_to
            else:
                tier_usage = remaining_usage
            cost += tier_usage * float(tier.unit_amount_decimal)
            remaining_usage -= tier_usage
        if cost > 0:
            self._cost += cost
            self._events += [
                CloudEvent(
                    attributes={
                        "type": "spent",
                        "source": "owl",
                        "subject": self.org.openmeter_id,
                    },
                    data={
                        "spent_usd": cost,
                        "category": product_type,
                        "org_id": self.org.id,
                        "project_id": self.project_id,
                        "user_id": self.user_id,
                        "agent": self.user_agent.agent,
                        "agent_version": self.user_agent.agent_version,
                        "architecture": self.user_agent.architecture,
                        "system": self.user_agent.system,
                        "system_version": self.user_agent.system_version,
                        "language": self.user_agent.language,
                        "language_version": self.user_agent.language_version,
                    },
                )
            ]
        return cost

    async def process_all(self) -> None:
        try:
            if self.is_oss or self.org is None:
                return
            # No billing events for admin API
            if self.request is not None and "api/admin" in self.request.url.path:
                return

            if self.request is not None and self.request.scope.get("route", None):
                # https://stackoverflow.com/a/72239186
                path = self.request.scope.get("root_path", "") + self.request.scope["route"].path
                self._events += [
                    CloudEvent(
                        attributes={
                            "type": "request_count",
                            "source": "owl",
                            "subject": self.org.openmeter_id,
                        },
                        data={
                            "method": self.request.method,
                            "path": path,
                            "org_id": self.org.id,
                            "project_id": self.project_id,
                            "user_id": self.user_id,
                            "agent": self.user_agent.agent,
                            "agent_version": self.user_agent.agent_version,
                            "architecture": self.user_agent.architecture,
                            "system": self.user_agent.system,
                            "system_version": self.user_agent.system_version,
                            "language": self.user_agent.language,
                            "language_version": self.user_agent.language_version,
                        },
                    ),
                ]

            # Process credits
            # Deduct from credit_grant first
            if self.org.credit_grant >= self._cost:
                credit_deduct = 0.0
                credit_grant_deduct = self._cost
            else:
                credit_deduct = self._cost - self.org.credit_grant
                credit_grant_deduct = self.org.credit_grant
            if credit_deduct > 0:
                self._deltas[ProductType.CREDIT] -= credit_deduct
            if credit_grant_deduct > 0:
                self._deltas[ProductType.CREDIT_GRANT] -= credit_grant_deduct
            # Update records
            if len(self._deltas) > 0 or len(self._values) > 0:
                await self.client.admin.backend.add_event(
                    EventCreate(
                        id=uuid7_str(),
                        organization_id=self.org.id,
                        deltas=self._deltas,
                        values=self._values,
                    )
                )
            # Send OpenMeter events
            if (
                self.openmeter_client is not None
                and self.org.openmeter_id is not None
                and len(self._events) > 0
            ):
                t0 = perf_counter()
                await self.openmeter_client.ingest_events([to_dict(e) for e in self._events])
                logger.info(
                    (
                        f"{self.request.state.id} - OpenMeter events ingestion: "
                        if self.request is not None
                        else "OpenMeter events ingestion: "
                    )
                    + (
                        f"t={(perf_counter() - t0) * 1e3:,.2f} ms   "
                        f"num_events={len(self._events):,d}"
                    )
                )
        except Exception as e:
            logger.exception(f"Failed to process billing events due to error: {e}")

    def _quota_ok(
        self,
        quota: float,
        usage: float,
        provider: str | None = None,
    ):
        # OSS has no billing
        if self.is_oss:
            return True
        # If there is credit left
        if self.total_balance > 0:
            return True
        # If user provides their own API key
        if self.org.external_keys.get(provider, "").strip():
            return True
        # If it's a ELLM model and there is quota left
        has_quota = (quota - usage) > 0
        if provider is None:
            return has_quota
        elif provider.startswith("ellm") and has_quota:
            return True
        return False

    # --- LLM Usage --- #

    def check_llm_quota(self, model_id: str) -> None:
        if self.is_oss or self.org is None:
            return
        provider = model_id.split("/")[0]
        if self._quota_ok(
            self.org.llm_tokens_quota_mtok, self.org.llm_tokens_usage_mtok, provider
        ):
            return
        # Return different error message depending if request came from browser
        if self.request is not None and self.user_agent.is_browser:
            model_id = self.request.state.all_models.get_llm_model_info(model_id).name
        raise InsufficientCreditsError(
            f"Insufficient LLM token quota or credits for model: {model_id}"
        )

    def check_gen_table_llm_quota(
        self,
        table: GenerativeTable,
        table_id: str,
    ) -> None:
        if self.is_oss or self.org is None:
            return
        with table.create_session() as session:
            meta = table.open_meta(session, table_id)
            for c in meta.cols_schema:
                if not isinstance(c.gen_config, LLMGenConfig):
                    continue
                self.check_llm_quota(c.gen_config.model)

    def create_llm_events(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        if self.is_oss or self.org is None:
            return
        if input_tokens < 1:
            logger.warning(f"Input token count should be > 0, received: {input_tokens}")
            input_tokens = 1
        if output_tokens < 1:
            logger.warning(f"Output token count should be > 0, received: {output_tokens}")
            output_tokens = 1
        self._events += [
            CloudEvent(
                attributes={
                    "type": ProductType.LLM_TOKENS,
                    "source": "owl",
                    "subject": self.org.openmeter_id,
                },
                data={
                    "model": model,
                    "tokens": v,
                    "type": t,
                    "org_id": self.org.id,
                    "project_id": self.project_id,
                    "user_id": self.user_id,
                    "agent": self.user_agent.agent,
                    "agent_version": self.user_agent.agent_version,
                    "architecture": self.user_agent.architecture,
                    "system": self.user_agent.system,
                    "system_version": self.user_agent.system_version,
                    "language": self.user_agent.language,
                    "language_version": self.user_agent.language_version,
                },
            )
            for t, v in [("input", input_tokens), ("output", output_tokens)]
        ]
        provider = model.split("/")[0]
        model_config: LLMModelConfig = self.request.state.all_models.get_llm_model_info(model)
        input_cost_per_mtoken = model_config.input_cost_per_mtoken
        output_cost_per_mtoken = model_config.output_cost_per_mtoken
        llm_credit_mtok = max(0.0, self.org.llm_tokens_quota_mtok - self.org.llm_tokens_usage_mtok)
        input_mtoken = input_tokens / 1e6
        output_mtoken = output_tokens / 1e6

        if provider.startswith("ellm"):
            self._deltas[ProductType.LLM_TOKENS] += input_mtoken + output_mtoken
        if provider.startswith("ellm") and llm_credit_mtok > 0:
            # Deduct input tokens first
            if llm_credit_mtok >= input_mtoken:
                input_mtoken = 0.0
                output_mtoken = max(0.0, output_mtoken - llm_credit_mtok)
            else:
                input_mtoken = max(0.0, input_mtoken - llm_credit_mtok)
            cost = input_cost_per_mtoken * input_mtoken + output_cost_per_mtoken * output_mtoken
        elif self.org.external_keys.get(provider, "").strip():
            cost = 0.0
        else:
            cost = input_cost_per_mtoken * input_mtoken + output_cost_per_mtoken * output_mtoken

        if cost > 0:
            self._cost += cost
            self._events += [
                CloudEvent(
                    attributes={
                        "type": "spent",
                        "source": "owl",
                        "subject": self.org.openmeter_id,
                    },
                    data={
                        "spent_usd": cost,
                        "category": ProductType.LLM_TOKENS,
                        "org_id": self.org.id,
                        "project_id": self.project_id,
                        "user_id": self.user_id,
                        "agent": self.user_agent.agent,
                        "agent_version": self.user_agent.agent_version,
                        "architecture": self.user_agent.architecture,
                        "system": self.user_agent.system,
                        "system_version": self.user_agent.system_version,
                        "language": self.user_agent.language,
                        "language_version": self.user_agent.language_version,
                    },
                )
            ]

    # --- Embedding Usage --- #

    def check_embedding_quota(self, model_id: str) -> None:
        if self.is_oss or self.org is None:
            return
        provider = model_id.split("/")[0]
        if self._quota_ok(
            self.org.embedding_tokens_quota_mtok, self.org.embedding_tokens_usage_mtok, provider
        ):
            return
        # Return different error message depending if request came from browser
        if self.request is not None and self.user_agent.is_browser:
            model_id = self.request.state.all_models.get_embed_model_info(model_id).name
        raise InsufficientCreditsError(
            f"Insufficient Embedding token quota or credits for model: {model_id}"
        )

    def create_embedding_events(
        self,
        model: str,
        token_usage: int,
    ) -> None:
        if self.is_oss or self.org is None:
            return
        if token_usage < 1:
            logger.warning(f"Token usage should be >= 1, received: {token_usage}")
            token_usage = 1
        # Create the CloudEvent for embedding token usage
        self._events += [
            CloudEvent(
                attributes={
                    "type": ProductType.EMBEDDING_TOKENS,
                    "source": "owl",
                    "subject": self.org.openmeter_id,
                },
                data={
                    "model": model,
                    "tokens": token_usage,
                    "org_id": self.org.id,
                    "project_id": self.project_id,
                    "user_id": self.user_id,
                    "agent": self.user_agent.agent,
                    "agent_version": self.user_agent.agent_version,
                    "architecture": self.user_agent.architecture,
                    "system": self.user_agent.system,
                    "system_version": self.user_agent.system_version,
                    "language": self.user_agent.language,
                    "language_version": self.user_agent.language_version,
                },
            )
        ]

        # Determine the provider from the model string
        provider = model.split("/")[0]
        # Get tokens in per mtoken unit
        model_config: EmbeddingModelConfig = self.request.state.all_models.get_embed_model_info(
            model
        )
        cost_per_mtoken = model_config.cost_per_mtoken
        embedding_credit_mtok = max(
            0.0, self.org.embedding_tokens_quota_mtok - self.org.embedding_tokens_usage_mtok
        )
        token_usage_mtok = token_usage / 1e6

        if provider.startswith("ellm"):
            self._deltas[ProductType.EMBEDDING_TOKENS] += token_usage_mtok

        if provider.startswith("ellm") and embedding_credit_mtok > 0:
            cost = max(0.0, token_usage_mtok - embedding_credit_mtok) * cost_per_mtoken
        elif self.org.external_keys.get(provider, "").strip():
            cost = 0.0
        else:
            cost = token_usage_mtok * cost_per_mtoken

        # If there is a cost, update the total cost and create a CloudEvent for the spending
        if cost > 0:
            self._cost += cost
            self._events += [
                CloudEvent(
                    attributes={
                        "type": "spent",
                        "source": "owl",
                        "subject": self.org.openmeter_id,
                    },
                    data={
                        "spent_usd": cost,
                        "category": ProductType.EMBEDDING_TOKENS,
                        "org_id": self.org.id,
                        "project_id": self.project_id,
                        "user_id": self.user_id,
                        "agent": self.user_agent.agent,
                        "agent_version": self.user_agent.agent_version,
                        "architecture": self.user_agent.architecture,
                        "system": self.user_agent.system,
                        "system_version": self.user_agent.system_version,
                        "language": self.user_agent.language,
                        "language_version": self.user_agent.language_version,
                    },
                )
            ]

    # --- Reranker Usage --- #

    def check_reranker_quota(self, model_id: str) -> None:
        if self.is_oss or self.org is None:
            return
        provider = model_id.split("/")[0]
        if self._quota_ok(
            self.org.reranker_quota_ksearch, self.org.reranker_usage_ksearch, provider
        ):
            return
        # Return different error message depending if request came from browser
        if self.request is not None and self.user_agent.is_browser:
            model_id = self.request.state.all_models.get_rerank_model_info(model_id).name
        raise InsufficientCreditsError(
            f"Insufficient Reranker search quota or credits for model: {model_id}"
        )

    def create_reranker_events(
        self,
        model: str,
        num_searches: int,
    ) -> None:
        if self.is_oss or self.org is None:
            return
        if num_searches < 1:
            logger.warning(f"Number of searches should be >= 1, received: {num_searches}")
            num_searches = 1

        # Create the CloudEvent for rerank search usage
        self._events += [
            CloudEvent(
                attributes={
                    "type": ProductType.RERANKER_SEARCHES,
                    "source": "owl",
                    "subject": self.org.openmeter_id,
                },
                data={
                    "model": model,
                    "searches": num_searches,
                    "org_id": self.org.id,
                    "project_id": self.project_id,
                    "user_id": self.user_id,
                    "agent": self.user_agent.agent,
                    "agent_version": self.user_agent.agent_version,
                    "architecture": self.user_agent.architecture,
                    "system": self.user_agent.system,
                    "system_version": self.user_agent.system_version,
                    "language": self.user_agent.language,
                    "language_version": self.user_agent.language_version,
                },
            )
        ]

        # Determine the provider from the model string
        provider = model.split("/")[0]

        # Get search cost per ksearch unit
        model_config: RerankingModelConfig = self.request.state.all_models.get_rerank_model_info(
            model
        )
        cost_per_ksearch = model_config.cost_per_ksearch

        remaining_rerank_ksearches = (
            self.org.reranker_quota_ksearch - self.org.reranker_usage_ksearch
        )
        num_ksearches = num_searches / 1e3

        if provider.startswith("ellm"):
            self._deltas[ProductType.RERANKER_SEARCHES] += num_ksearches

        if provider.startswith("ellm") and remaining_rerank_ksearches > 0:
            cost = max(0.0, num_ksearches - remaining_rerank_ksearches) * cost_per_ksearch
        elif self.org.external_keys.get(provider, "").strip():
            cost = 0.0
        else:
            cost = cost_per_ksearch * num_ksearches

        # If there is a cost, update the total cost and create a CloudEvent for the spending
        if cost > 0:
            self._cost += cost
            self._events += [
                CloudEvent(
                    attributes={
                        "type": "spent",
                        "source": "owl",
                        "subject": self.org.openmeter_id,
                    },
                    data={
                        "spent_usd": cost,
                        "category": ProductType.RERANKER_SEARCHES,
                        "org_id": self.org.id,
                        "project_id": self.project_id,
                        "user_id": self.user_id,
                        "agent": self.user_agent.agent,
                        "agent_version": self.user_agent.agent_version,
                        "architecture": self.user_agent.architecture,
                        "system": self.user_agent.system,
                        "system_version": self.user_agent.system_version,
                        "language": self.user_agent.language,
                        "language_version": self.user_agent.language_version,
                    },
                )
            ]

    # --- Egress Usage --- #

    def check_egress_quota(self) -> None:
        if self.is_oss or self.org is None:
            return
        if self._quota_ok(self.org.egress_quota_gib, self.org.egress_usage_gib):
            return
        raise InsufficientCreditsError("Insufficient egress quota or credits.")

    def create_egress_events(self, amount_gb: float) -> None:
        if self.is_oss or self.org is None:
            return
        if amount_gb <= 0:
            logger.warning(f"Egress amount should be > 0, received: {amount_gb}")
            return
        self._events += [
            CloudEvent(
                attributes={
                    "type": "bandwidth",
                    "source": "owl",
                    "subject": self.org.openmeter_id,
                },
                data={
                    "amount_gb": amount_gb,
                    "type": ProductType.EGRESS,
                    "org_id": self.org.id,
                    "project_id": self.project_id,
                    "user_id": self.user_id,
                    "agent": self.user_agent.agent,
                    "agent_version": self.user_agent.agent_version,
                    "architecture": self.user_agent.architecture,
                    "system": self.user_agent.system,
                    "system_version": self.user_agent.system_version,
                    "language": self.user_agent.language,
                    "language_version": self.user_agent.language_version,
                },
            )
        ]
        self._compute_cost(
            ProductType.EGRESS, self.org.egress_quota_gib - self.org.egress_usage_gib, amount_gb
        )
        self._deltas[ProductType.EGRESS] += amount_gb

    # --- Storage Usage --- #

    def check_db_storage_quota(self) -> None:
        if self.is_oss or self.org is None:
            return
        if self._quota_ok(self.org.db_quota_gib, self.org.db_usage_gib):
            return
        raise InsufficientCreditsError("Insufficient DB storage quota.")

    def check_file_storage_quota(self) -> None:
        if self.is_oss or self.org is None:
            return
        if self._quota_ok(self.org.file_quota_gib, self.org.file_usage_gib):
            return
        raise InsufficientCreditsError("Insufficient file storage quota.")

    def create_storage_events(self, db_usage_gib: float, file_usage_gib: float) -> None:
        if self.is_oss or self.org is None:
            return
        if db_usage_gib <= 0:
            logger.warning(f"DB storage usage should be > 0, received: {db_usage_gib}")
            return
        if file_usage_gib <= 0:
            logger.warning(f"File storage usage should be > 0, received: {file_usage_gib}")
            return
        # Wait for at least `min_wait` before recomputing
        now = datetime.now(timezone.utc)
        min_wait = timedelta(minutes=max(5.0, ENV_CONFIG.owl_compute_storage_period_min))
        # Wait because quota refresh might be called a few times
        quota_reset_at = datetime.fromisoformat(self.org.quota_reset_at)
        if (now - quota_reset_at) <= min_wait:
            return
        self._events += [
            CloudEvent(
                attributes={
                    "type": "storage",
                    "source": "owl",
                    "subject": self.org.openmeter_id,
                },
                data={
                    "amount_gb": db_usage_gib,
                    "type": "db",
                    "org_id": self.org.id,
                },
            ),
            CloudEvent(
                attributes={
                    "type": "storage",
                    "source": "owl",
                    "subject": self.org.openmeter_id,
                },
                data={
                    "amount_gb": file_usage_gib,
                    "type": "file",
                    "org_id": self.org.id,
                },
            ),
        ]
        self._values[ProductType.DB_STORAGE] = db_usage_gib
        self._values[ProductType.FILE_STORAGE] = file_usage_gib
