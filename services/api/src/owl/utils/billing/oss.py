import asyncio
from collections import defaultdict
from time import perf_counter
from typing import Any, DefaultDict

import clickhouse_connect
from cloudevents.conversion import to_dict
from cloudevents.http import CloudEvent
from fastapi import Request
from loguru import logger
from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, _Gauge
from tenacity import retry, stop_after_attempt, wait_exponential

from owl.configs import CACHE, ENV_CONFIG
from owl.db.gen_table import GenerativeTableCore
from owl.types import (
    DBStorageUsageData,
    EgressUsageData,
    EmbedUsageData,
    FileStorageUsageData,
    LlmUsageData,
    ModelConfigRead,
    OrganizationRead,
    ProductType,
    RerankUsageData,
    UsageData,
    UserAgent,
)
from owl.utils.exceptions import ResourceNotFoundError, handle_exception


class OpenTelemetryClient:
    def __init__(self) -> None:
        # resource = Resource.create(
        #     {
        #         "service.name": "owl-service",
        #         "service.instance.id": uuid7_str(),
        #     }
        # )
        # reader = PeriodicExportingMetricReader(
        #     OTLPMetricExporter(endpoint=endpoint), export_interval_millis=math.inf
        # )
        # self.provider = MeterProvider(resource=resource, metric_readers=[reader])
        # metrics.set_meter_provider(self.provider)
        self.meter = metrics.get_meter(__name__)
        self.counters: DefaultDict[str, Counter] = defaultdict(
            lambda: self.meter.create_counter(name="default")
        )
        self.histograms: DefaultDict[str, Histogram] = defaultdict(
            lambda: self.meter.create_histogram(name="default")
        )
        self.gauges: DefaultDict[str, _Gauge] = defaultdict(
            lambda: self.meter.create_gauge(name="default")
        )

    def get_counter(self, name) -> Counter:
        if name not in self.counters:
            self.counters[name] = self.meter.create_counter(name=name)
        return self.counters[name]

    def get_histogram(self, name) -> Histogram:
        if name not in self.histograms:
            self.histograms[name] = self.meter.create_histogram(name=name)
        return self.histograms[name]

    def get_gauge(self, name) -> _Gauge:
        if name not in self.gauges:
            self.gauges[name] = self.meter.create_gauge(name=name)
        return self.gauges[name]

    def get_meter(self):
        return self.meter

    def force_flush(self):
        # self.provider.force_flush()
        metrics.get_meter_provider().force_flush()


class ClickHouseAsyncClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        database: str,
        port: int,
    ) -> None:
        self.client = asyncio.run(
            clickhouse_connect.get_async_client(
                host=host,
                username=username,
                password=password,
                database=database,
                port=port,
            )
        )

    def _log_debug(self, message: str):
        logger.debug(f"{self.__class__.__name__}: {message}")

    def _log_info(self, message: str):
        logger.info(f"{self.__class__.__name__}: {message}")

    def _log_error(self, message: str):
        logger.error(f"{self.__class__.__name__}: {message}")

    async def query(self, sql: str):
        try:
            result = await self.client.query(sql)
            return result
        except Exception as e:
            self._log_error(f"Failed to execute query: {sql}. Error: {e}")
            raise

    async def insert_llm_usage(self, usages: list[LlmUsageData]):
        try:
            usages_list = [usage.as_list() for usage in usages]
            result = await self.client.insert(
                table="llm_usage",
                data=usages_list,
                column_names=[
                    "id",
                    "org_id",
                    "proj_id",
                    "user_id",
                    "timestamp",
                    "cost",
                    "model",
                    "input_token",
                    "output_token",
                    "input_cost",
                    "output_cost",
                ],
                settings={
                    "async_insert": 1,
                    "wait_for_async_insert": 1,
                    "async_insert_busy_timeout_ms": 1000,
                    "async_insert_use_adaptive_busy_timeout": 1,
                },
            )
            return result
        except Exception as e:
            self._log_error(f"Failed to insert data into table: llm_usage. Error: {e}")
            raise

    async def insert_embed_usage(self, usages: list[EmbedUsageData]):
        try:
            usages_list = [usage.as_list() for usage in usages]
            result = await self.client.insert(
                table="embed_usage",
                data=usages_list,
                column_names=[
                    "id",
                    "org_id",
                    "proj_id",
                    "user_id",
                    "timestamp",
                    "cost",
                    "model",
                    "num_token",
                ],
                settings={
                    "async_insert": 1,
                    "wait_for_async_insert": 1,
                    "async_insert_busy_timeout_ms": 1000,
                    "async_insert_use_adaptive_busy_timeout": 1,
                },
            )
            return result
        except Exception as e:
            self._log_error(f"Failed to insert data into table: embed_usage. Error: {e}")
            raise

    async def insert_rerank_usage(self, usages: list[RerankUsageData]):
        try:
            usages_list = [usage.as_list() for usage in usages]
            result = await self.client.insert(
                table="rerank_usage",
                data=usages_list,
                column_names=[
                    "id",
                    "org_id",
                    "proj_id",
                    "user_id",
                    "timestamp",
                    "cost",
                    "model",
                    "num_search",
                ],
                settings={
                    "async_insert": 1,
                    "wait_for_async_insert": 1,
                    "async_insert_busy_timeout_ms": 1000,
                    "async_insert_use_adaptive_busy_timeout": 1,
                },
            )
            return result
        except Exception as e:
            self._log_error(f"Failed to insert data into table: rerank_usage. Error: {e}")
            raise

    async def insert_egress_usage(self, usages: list[EgressUsageData]):
        try:
            usages_list = [usage.as_list() for usage in usages]
            result = await self.client.insert(
                table="egress_usage",
                data=usages_list,
                column_names=[
                    "id",
                    "org_id",
                    "proj_id",
                    "user_id",
                    "timestamp",
                    "cost",
                    "amount_gib",
                ],
                settings={
                    "async_insert": 1,
                    "wait_for_async_insert": 1,
                    "async_insert_busy_timeout_ms": 1000,
                    "async_insert_use_adaptive_busy_timeout": 1,
                },
            )
            return result
        except Exception as e:
            self._log_error(f"Failed to insert data into table: egress_usage. Error: {e}")
            raise

    async def insert_file_storage_usage(self, usages: list[FileStorageUsageData]):
        try:
            usages_list = [usage.as_list() for usage in usages]
            result = await self.client.insert(
                table="file_storage_usage",
                data=usages_list,
                column_names=[
                    "id",
                    "org_id",
                    "proj_id",
                    "user_id",
                    "timestamp",
                    "cost",
                    "amount_gib",
                    "snapshot_gib",
                ],
                settings={
                    "async_insert": 1,
                    "wait_for_async_insert": 1,
                    "async_insert_busy_timeout_ms": 1000,
                    "async_insert_use_adaptive_busy_timeout": 1,
                },
            )
            return result
        except Exception as e:
            self._log_error(f"Failed to insert data into table: file_storage_usage. Error: {e}")
            raise

    async def insert_db_storage_usage(self, usages: list[DBStorageUsageData]):
        try:
            usages_list = [usage.as_list() for usage in usages]
            result = await self.client.insert(
                table="db_storage_usage",
                data=usages_list,
                column_names=[
                    "id",
                    "org_id",
                    "proj_id",
                    "user_id",
                    "timestamp",
                    "cost",
                    "amount_gib",
                    "snapshot_gib",
                ],
                settings={
                    "async_insert": 1,
                    "wait_for_async_insert": 1,
                    "async_insert_busy_timeout_ms": 1000,
                    "async_insert_use_adaptive_busy_timeout": 1,
                },
            )
            return result
        except Exception as e:
            self._log_error(f"Failed to insert data into table: db_storage_usage. Error: {e}")
            raise

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def insert_usage(self, usage: UsageData):
        llm_result = await self.insert_llm_usage(usage.llm_usage)
        embed_result = await self.insert_embed_usage(usage.embed_usage)
        rerank_result = await self.insert_rerank_usage(usage.rerank_usage)
        egress_result = await self.insert_egress_usage(usage.egress_usage)
        file_storage_result = await self.insert_file_storage_usage(usage.file_storage_usage)
        db_storage_result = await self.insert_db_storage_usage(usage.db_storage_usage)
        return (
            llm_result,
            embed_result,
            rerank_result,
            egress_result,
            file_storage_result,
            db_storage_result,
        )

    async def bulk_insert_usage(self, usages: list[UsageData]):
        all_usages = sum(usages, start=UsageData())
        results = await self.insert_usage(all_usages)
        return results

    async def flush_buffer(self):
        buffer_key = ENV_CONFIG.clickhouse_buffer_key
        buffer_count_key = buffer_key + "_count"
        temp_key = buffer_key + "_temp"
        lock_key = buffer_key + ":lock"

        async with CACHE.alock(lock_key, blocking=False, expire=5) as lock_acquired:
            if lock_acquired:
                self._log_debug("Acquired lock to flush buffer.")
            else:
                self._log_debug("Could not acquire lock to flush buffer.")
                return

            # Exit if buffer key not found
            if not await CACHE.exists(buffer_key):
                self._log_debug("Buffer key not found, skipping insert operation.")
                return

            # Move data from buffer to temp key
            # TODO: Maybe use async redis
            with CACHE._redis.pipeline() as pipe:
                pipe.multi()
                pipe.rename(buffer_key, temp_key)
                temp_count = pipe.get(buffer_count_key)
                pipe.delete(buffer_count_key)
                pipe.execute()

            buffer_data = CACHE._redis.lrange(temp_key, 0, -1)
            if buffer_data:
                _t = perf_counter()
                usages = [UsageData.model_validate_json(data) for data in buffer_data]
                try:
                    await self.bulk_insert_usage(usages)
                    # Delete temp key on success
                    del CACHE[temp_key]
                    self._log_info(
                        (
                            f"{sum([usage.total_usage_events for usage in usages]):,d} buffered usage data inserted to DB, "
                            f"time taken: {perf_counter() - _t:,.3} seconds"
                        )
                    )
                except Exception as e:
                    self._log_error(f"Failed to insert data. Error: {e}")
                    # Move data back to buffer on failure
                    # Append data back to buffer on failure
                    with CACHE._redis.pipeline() as pipe:
                        pipe.multi()
                        for data in buffer_data:
                            pipe.rpush(buffer_key, data)
                        pipe.incrby(buffer_count_key, int(temp_count or 0))
                        pipe.execute()
                    # Delete temp key after appending data back to buffer
                    del CACHE[temp_key]


# OPENTELEMETRY_CLIENT = OpenTelemetryClient(
#     endpoint=f"http://{ENV_CONFIG.opentelemetry_host}:{ENV_CONFIG.opentelemetry_port}"
# )
OPENTELEMETRY_CLIENT = OpenTelemetryClient()
CLICKHOUSE_CLIENT = ClickHouseAsyncClient(
    host=ENV_CONFIG.clickhouse_host,
    username=ENV_CONFIG.clickhouse_user,
    password=ENV_CONFIG.clickhouse_password.get_secret_value(),
    database=ENV_CONFIG.clickhouse_db,
    port=ENV_CONFIG.clickhouse_port,
)
STRIPE_CLIENT = None


def _log_exception(e: Exception, *_, **__):
    logger.exception(f"Billing event processing encountered an error: {repr(e)}")


class BillingManager:
    def __init__(
        self,
        *,
        organization: OrganizationRead,
        project_id: str = "",
        user_id: str = "",
        request: Request | None = None,
        models: list[ModelConfigRead] | None = None,
    ) -> None:
        if not isinstance(organization, OrganizationRead):
            raise TypeError(
                f"`organization` must be an instance of `OrganizationRead`, received: {type(organization)}"
            )
        self.org = organization
        self.project_id = project_id
        self.user_id = user_id
        self.request = request
        self.id: str = request.state.id if request else "<no-id>"
        if models and not all(isinstance(m, ModelConfigRead) for m in models):
            raise TypeError(
                f"`models` must be a list of `ModelConfigRead` instances, received: {models}"
            )
        self.models = models
        self.model_map = {m.id: m for m in models} if models else {}
        if request is None:
            self._user_agent = UserAgent(is_browser=False, agent="")
        else:
            self._user_agent: UserAgent = request.state.user_agent
        self._price_plan = None
        self._events = []
        self._deltas: dict[ProductType, float] = defaultdict(float)
        self._values: dict[ProductType, float] = defaultdict(float)
        self._llm_usage_events: list[LlmUsageData] = []
        self._embed_usage_events: list[EmbedUsageData] = []
        self._rerank_usage_events: list[RerankUsageData] = []
        self._egress_usage_events: list[EgressUsageData] = []
        self._file_storage_usage_events: list[FileStorageUsageData] = []
        self._db_storage_usage_events: list[DBStorageUsageData] = []
        self._cost = 0.0

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def total_balance(self) -> float:
        return self.org.credit + self.org.credit_grant

    def _log_info(self, message: str):
        logger.info(f"{self.id} - {self.__class__.__name__}: {message}")

    def _log_warning(self, message: str):
        logger.warning(f"{self.id} - {self.__class__.__name__}: {message}")

    def _model(self, model_id: str) -> ModelConfigRead:
        model = self.model_map.get(model_id, None)
        if model is None:
            raise ResourceNotFoundError(
                f'Model "{self._model_id_or_name(model_id)}" is not found.'
            )
        return model

    def _check_project_id(self):
        if self.project_id.strip() == "":
            raise ValueError("Project ID must be provided.")

    def _cloud_event(
        self,
        attributes: dict[str, Any],
        data: dict[str, Any],
    ) -> CloudEvent:
        if (
            len(data.get("proj_id", "dummy")) == 0
        ):  # Update to proj_id to align with Clickhouse Column
            raise ValueError('"proj_id" if provided must not be empty.')
        # check if request_count
        extra_labels = (
            self._user_agent.model_dump() if attributes.get("type", "") == "request_count" else {}
        )
        return CloudEvent(
            attributes={
                **attributes,
                "source": "owl",
                "subject": self.org.id,
            },
            data={
                **data,
                "org_id": self.org.id,
                "user_id": self.user_id,
                **extra_labels,
            },
        )

    # --- Generative Table Usage --- #

    def has_gen_table_quota(self, table: GenerativeTableCore) -> bool:
        return True

    # --- LLM Usage --- #

    def has_llm_quota(self, model_id: str) -> bool:
        return True

    def create_llm_events(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        *,
        create_usage: bool = True,
    ) -> None:
        input_tokens = int(input_tokens)
        output_tokens = int(output_tokens)
        if input_tokens <= 0 and output_tokens <= 0:
            return
        self._check_project_id()
        # Analytics: Token usage
        self._events += [
            self._cloud_event(
                {"type": ProductType.LLM_TOKENS},
                {
                    "model": model_id,
                    "tokens": v,
                    "type": t,
                    "proj_id": self.project_id,  # Update to proj_id to align with Clickhouse Column
                },
            )
            for t, v in [("input", input_tokens), ("output", output_tokens)]
        ]
        if create_usage:
            self._llm_usage_events.append(
                LlmUsageData(
                    org_id=self.org.id,
                    proj_id=self.project_id,
                    user_id=self.user_id,
                    model=model_id,
                    input_token=input_tokens,
                    output_token=output_tokens,
                    input_cost=0.0,
                    output_cost=0.0,
                    cost=0.0,
                )
            )

    # --- Embedding Usage --- #

    def has_embedding_quota(self, model_id: str) -> bool:
        return True

    def create_embedding_events(
        self,
        model_id: str,
        token_usage: int,
        *,
        create_usage: bool = True,
    ) -> None:
        token_usage = int(token_usage)
        if token_usage <= 0:
            return
        self._check_project_id()
        # Analytics: Token usage
        self._events += [
            self._cloud_event(
                {"type": ProductType.EMBEDDING_TOKENS},
                {
                    "model": model_id,
                    "tokens": token_usage,
                    "proj_id": self.project_id,  # Update to proj_id to align with Clickhouse Column
                },
            )
        ]
        if create_usage:
            self._embed_usage_events.append(
                EmbedUsageData(
                    org_id=self.org.id,
                    proj_id=self.project_id,
                    user_id=self.user_id,
                    model=model_id,
                    token=token_usage,
                    cost=0.0,
                )
            )

    # --- Reranker Usage --- #

    def has_reranker_quota(self, model_id: str) -> bool:
        return True

    def create_reranker_events(
        self,
        model_id: str,
        num_searches: int,
        *,
        create_usage: bool = True,
    ) -> None:
        num_searches = int(num_searches)
        if num_searches <= 0:
            return
        self._check_project_id()
        # Analytics: Rerank usage
        self._events += [
            self._cloud_event(
                {"type": ProductType.RERANKER_SEARCHES},
                {
                    "model": model_id,
                    "searches": num_searches,
                    "proj_id": self.project_id,  # Update to proj_id to align with Clickhouse Column
                },
            )
        ]
        if create_usage:
            self._rerank_usage_events.append(
                RerankUsageData(
                    org_id=self.org.id,
                    proj_id=self.project_id,
                    user_id=self.user_id,
                    model=model_id,
                    number_of_search=num_searches,
                    cost=0.0,
                )
            )

    # --- Egress Usage --- #

    def has_egress_quota(self) -> bool:
        return True

    def create_egress_events(self, amount_gib: float, *, create_usage: bool = True) -> None:
        if amount_gib <= 0 or not self.project_id:
            return
        # Analytics: Egress usage
        self._events += [
            self._cloud_event(
                {"type": "bandwidth"},
                {
                    "amount_gib": amount_gib,
                    "type": ProductType.EGRESS,
                    "proj_id": self.project_id,  # Update to proj_id to align with Clickhouse Column
                },
            )
        ]
        if create_usage:
            self._egress_usage_events.append(
                EgressUsageData(
                    org_id=self.org.id,
                    proj_id=self.project_id,
                    user_id=self.user_id,
                    amount_gib=amount_gib,
                    cost=0.0,
                )
            )

    # --- DB Storage Usage --- #

    def has_db_storage_quota(self) -> bool:
        return True

    def create_db_storage_events(self, db_usage_gib: float, *, create_usage: bool = True) -> None:
        if db_usage_gib <= 0:
            return
        # Analytics: DB storage usage
        self._events += [
            self._cloud_event({"type": "storage"}, {"amount_gib": db_usage_gib, "type": "db"}),
        ]
        if create_usage:
            self._db_storage_usage_events.append(
                DBStorageUsageData(
                    org_id=self.org.id,
                    proj_id=self.project_id
                    or "not_applicable",  # possible the request is not associated with a project
                    user_id=self.user_id,
                    amount_gib=0.0,
                    cost=0.0,
                    snapshot_gib=db_usage_gib,
                )
            )

    # --- File Storage Usage --- #

    def has_file_storage_quota(self) -> bool:
        return True

    def create_file_storage_events(
        self, file_usage_gib: float, *, create_usage: bool = True
    ) -> None:
        if file_usage_gib <= 0:
            return
        # Analytics: DB storage usage
        self._events += [
            self._cloud_event({"type": "storage"}, {"amount_gib": file_usage_gib, "type": "file"}),
        ]
        if create_usage:
            self._file_storage_usage_events.append(
                FileStorageUsageData(
                    org_id=self.org.id,
                    proj_id=self.project_id
                    or "not_applicable",  # possible the request is not associated with a project
                    user_id=self.user_id,
                    amount_gib=0.0,
                    cost=0.0,
                    snapshot_gib=file_usage_gib,
                )
            )

    # --- Process all events --- #

    @handle_exception(handler=_log_exception)
    async def process_all(self) -> None:
        """
        Process all events. In general, only call this as a BACKGROUND TASK after the response is sent.
        """

        # Push usage to redis for queue if buffer less than 10000
        usage_data = UsageData(
            llm_usage=self._llm_usage_events,
            embed_usage=self._embed_usage_events,
            rerank_usage=self._rerank_usage_events,
            egress_usage=self._egress_usage_events,
            file_storage_usage=self._file_storage_usage_events,
            db_storage_usage=self._db_storage_usage_events,
        )
        usage_count = (await CACHE.get_usage_buffer_count()) + usage_data.total_usage_events
        if usage_count >= ENV_CONFIG.clickhouse_max_buffer_queue_size:
            await CLICKHOUSE_CLIENT.flush_buffer()
            # We could use asyncio TaskGroup here if there are other async tasks downstream
            # For now there isn't any, so we just simply await it
            await CLICKHOUSE_CLIENT.insert_usage(usage_data)
        elif usage_data.total_usage_events > 0:
            await CACHE.add_usage_to_buffer(usage_data)

        # API request count
        req_scope = getattr(self.request, "scope", {})
        req_method: str = getattr(self.request, "method", "")
        if req_scope.get("route", None) and req_method and self.project_id:
            # https://stackoverflow.com/a/72239186
            path = req_scope.get("root_path", "") + req_scope["route"].path
            self._events += [
                self._cloud_event(
                    {"type": "request_count"},
                    {
                        "method": req_method,
                        "path": path,
                        "proj_id": self.project_id,  # Update to proj_id to align with Clickhouse Column
                    },
                )
            ]
        # Send OpenTelemetry events
        if len(self._events) > 0:
            t0 = perf_counter()
            for event in self._events:
                attributes = to_dict(event)
                event_type = attributes["type"]
                if event_type == "request_count":
                    counter = OPENTELEMETRY_CLIENT.get_counter(name="request_count")
                    counter.add(1, attributes["data"])
                elif event_type == ProductType.LLM_TOKENS:
                    counter = OPENTELEMETRY_CLIENT.get_counter(name="llm_token_usage")
                    counter.add(
                        attributes["data"]["tokens"],
                        {k: v for k, v in attributes["data"].items() if k != "tokens"},
                    )
                elif event_type == ProductType.EMBEDDING_TOKENS:
                    counter = OPENTELEMETRY_CLIENT.get_counter(name="embedding_token_usage")
                    counter.add(
                        attributes["data"]["tokens"],
                        {k: v for k, v in attributes["data"].items() if k != "tokens"},
                    )
                elif event_type == ProductType.RERANKER_SEARCHES:
                    counter = OPENTELEMETRY_CLIENT.get_counter(name="reranker_search_usage")
                    counter.add(
                        attributes["data"]["searches"],
                        {k: v for k, v in attributes["data"].items() if k != "searches"},
                    )
                elif event_type == "bandwidth":
                    counter = OPENTELEMETRY_CLIENT.get_counter(name="bandwidth_usage")
                    counter.add(
                        attributes["data"]["amount_gib"],
                        {k: v for k, v in attributes["data"].items() if k != "amount_gib"},
                    )
                elif event_type == "storage":
                    gauge = OPENTELEMETRY_CLIENT.get_gauge(name="storage_usage")
                    gauge.set(
                        attributes["data"]["amount_gib"],
                        {k: v for k, v in attributes["data"].items() if k != "amount_gib"},
                    )
                elif event_type == "spent":
                    counter = OPENTELEMETRY_CLIENT.get_counter(name="spent")
                    counter.add(
                        attributes["data"]["spent_usd"],
                        {k: v for k, v in attributes["data"].items() if k != "spent_usd"},
                    )
            self._log_info(
                (
                    f"OpenTelemetry events ingestion: "
                    f"t={(perf_counter() - t0) * 1e3:,.2f} ms   "
                    f"num_events={len(self._events):,d}   "
                    f"event_types={set(str(e.get_attributes()['type']) for e in self._events)}"
                )
            )
            # Force flush
            # OPENTELEMETRY_CLIENT.force_flush()
            # Clear events
            self._events = []
