import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Sequence

import httpx
from loguru import logger

from owl.client import VictoriaMetricsAsync
from owl.types import Host, Metric, Usage, UsageResponse

http_client = httpx.Client(timeout=5)


def filter_hostnames(
    metric_sequence: Sequence[Metric], host_name_sequence: Sequence[str]
) -> list[Metric]:
    return [metric for metric in metric_sequence if metric.hostname in host_name_sequence]


def group_metrics_by_hostname(
    metrics: list[Metric], hostnames: list[str] | None = None
) -> list[Host]:
    # If hostnames filter is provided, filter the metrics
    if hostnames:
        metrics = filter_hostnames(metrics, hostnames)

    # Group metrics by hostname
    hostname_dict = defaultdict(list)
    for metric in metrics:
        hostname_dict[metric.hostname].append(metric)

    # Create list of hosts
    hosts = [
        Host(name=hostname, metrics=metric_list) for hostname, metric_list in hostname_dict.items()
    ]

    return hosts


class Telemetry(VictoriaMetricsAsync):
    __QUERY_ENDPOINT = "/vm/prometheus/api/v1/query"
    __QUERY_RANGE_ENDPOINT = "/vm/prometheus/api/v1/query_range"

    # __METRIC_QUERY_TUPLE = (
    #     "label_set(sum(rate(container_cpu_usage_seconds_total{container!='',}[1m])) by (instance,job) / sum(machine_cpu_cores{}) by (instance,job) * 100, '__name__', 'cpu_util')",
    #     "label_set(sum(container_memory_working_set_bytes{container!='',}) by (instance,job) / sum(container_spec_memory_limit_bytes{container!='',}) by (instance,job) * 100,'__name__','memory_util')",
    #     "label_set(sum(rate(container_fs_reads_bytes_total{container!='',}[15s])) by (instance,job),'__name__','disk_read_bytes')",
    #     "label_set(sum(rate(container_fs_writes_bytes_total{container!='',}[15s])) by (instance,job),'__name__','disk_write_bytes')",
    #     "label_set(sum(rate(container_network_receive_bytes_total{container!='',}[15s])) by (instance,job),'__name__','network_receive_bytes')",
    #     "label_set(sum(rate(container_network_transmit_bytes_total{container!='',}[15s])) by (instance,job),'__name__','network_transmit_bytes')",
    #     "sort(topk(1, gpu_clock{clock_type='GPU_CLOCK_TYPE_SYSTEM',}))",
    #     "gpu_clock{clock_type='GPU_CLOCK_TYPE_MEMORY',}",
    #     "gpu_edge_temperature{}",
    #     "gpu_memory_temperature{}",
    #     "gpu_power_usage{}",
    #     "gpu_gfx_activity{}",
    #     "gpu_umc_activity{}",
    #     "gpu_free_vram{}",
    #     "used_memory{}",
    #     "DCGM_FI_DEV_SM_CLOCK{}",
    #     "DCGM_FI_DEV_MEM_CLOCK{}",
    #     "DCGM_FI_DEV_GPU_TEMP{}",
    #     "DCGM_FI_DEV_MEMORY_TEMP{}",
    #     "DCGM_FI_DEV_POWER_USAGE{}",
    #     "DCGM_FI_DEV_GPU_UTIL{}",
    #     "DCGM_FI_DEV_MEM_COPY_UTIL{}",
    #     "DCGM_FI_DEV_FB_FREE{}",
    #     "DCGM_FI_DEV_FB_USED{}",
    # )

    def _construct_metrics_query(self, queries: list[str]) -> str:
        """Construct a metrics retrieval query string.

        Args:
            queries (list[str]): A list of fields to query.

        Returns:
            str: The constructed query string.
        """
        return "union(" + ", ".join(f"{i}" for i in queries) + ")"

    def _construct_usage_query(
        self,
        range_func: str,
        aggregate_func: str,
        subject_id: str,
        query_filter: list[str],
        group_by: list[str],
        window_size: str,
    ) -> str:
        """Construct a usage retrieval query string.

        Args:
            range_func (str): The range function to use for the query, ex: max_over_time, increase_pure, etc..
            aggregate_func (str): The aggregate function to use for the query, ex: max, sum, etc..
            subject_id (str): The metric ID to query from, ex: owl_spent_total, owl_llm_token_usage_total, etc..
            group_by (list[str]): The group by fields for the query, ex: ["org_id", "proj_id"], etc..
            window_size (str): The window size to use for the query.

        Returns:
            str: The constructed query string.
        """
        return f"{aggregate_func}({range_func}({subject_id}{{{','.join(query_filter)}}}[{window_size}])) by ({', '.join(group_by)})"

    def _process_metrics(self, response: list[dict[str, Any]]) -> list[Metric]:
        """Process the metrics received from response.

        Args:
            response (list[dict[str, Any]]): JSON data from metrics provider.

        Returns:
            list[Metric]: A list of processed metrics.
        """
        metrics = []
        for metric in response:
            try:
                # Ensure "metric" key exists
                if "metric" not in metric or not isinstance(metric["metric"], dict):
                    raise KeyError('"metric" key is missing or not a dictionary')

                # Safely retrieve the "__name__" field
                metric_name = metric["metric"].get("__name__")
                if metric_name == "gpu_clock":
                    # Safely retrieve the "clock_type" field
                    clock_type = metric["metric"].get("clock_type")
                    if clock_type == "GPU_CLOCK_TYPE_MEMORY":
                        metric["metric"]["__name__"] = "gpu_memory_clock"

                # Process the metric
                metrics.append(Metric.from_response(metric))
            except (KeyError, TypeError) as e:
                # Log the error and skip the problematic metric
                logger.warning(
                    f"Skipping metric due to missing fields or invalid structure: {metric}. Error: {e}"
                )
                continue
        return metrics

    def _parse_duration(self, duration_str: str) -> timedelta:
        """Parse a duration string into a timedelta object.

        The duration string is expected to be in the format of a sequence of
        decimal numbers followed by a unit character. The unit characters
        supported are 'ms', 's', 'm', 'h', 'd', 'w', 'y', which represent
        milliseconds, seconds, minutes, hours, days, weeks, and years,
        respectively.

        Args:
            duration_str (str): The duration string to parse.

        Returns:
            timedelta: The parsed timedelta object.
        """
        pattern = r"(?P<value>\d+)(?P<unit>[smhdwy])"
        matches = re.findall(pattern, duration_str)

        delta = timedelta()
        unit_multipliers = {
            "ms": timedelta(milliseconds=1),
            "s": timedelta(seconds=1),
            "m": timedelta(minutes=1),
            "h": timedelta(hours=1),
            "d": timedelta(days=1),
            "w": timedelta(weeks=1),
            "y": timedelta(days=365),
        }

        for value, unit in matches:
            if unit == "ms":
                delta += int(value) * unit_multipliers[unit]
            else:
                delta += int(value) * unit_multipliers[unit]

        return delta

    async def query_metrics(
        self,
        queries: list[str] | None = None,
        hostnames: list[str] | None = None,
    ) -> list[Host]:
        """Retrieve the latest metrics from VictoriaMetrics.

        Args:
            queries (list[str] | None, optional): A list of fields to query. Defaults to None (which means self.__METRIC_QUERY_TUPLE will be used).
            hostnames (list[str] | None, optional): A list of hostnames to filter the results. If None, no filtering will be applied.

        Returns:
            list[Host]: A list of Host(s) each contains a name and list[Metric].
        """
        queries = queries or self.__METRIC_QUERY_TUPLE
        logger.info(self._construct_metrics_query(queries))
        params = {"query": self._construct_metrics_query(queries)}
        response = await self._fetch_victoria_metrics(self.__QUERY_ENDPOINT, params)
        response = response.json()["data"]["result"]

        if not response:
            return []

        metrics = self._process_metrics(response)
        return group_metrics_by_hostname(metrics, hostnames)

    def _process_usage(
        self,
        usage: list[dict[str, Any]],
        data_interval: timedelta,
        group_by: list[str],
    ) -> list[Usage]:
        """Process usage data into a list of Usage objects.

        Args:
            usage (list[dict[str, Any]]): The raw usage data from the query.
            data_interval (timedelta): The data interval to adjust the window range.
            group_by (list[str]): The group-by fields for the query.

        Returns:
            list[Usage]: a list of the usage metrics.
        """
        return [
            Usage.from_result(value, result["metric"], data_interval, group_by)
            for result in usage
            for value in result["values"]
        ]

    async def query_usage(
        self,
        range_func: str,
        aggregate_func: str,
        subject_id: str,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
        timeout_value: int = 5,
    ) -> UsageResponse:
        """
        Query VictoriaMetrics/Prometheus for usage metrics.

        Args:
            range_func (str): The range function to use for the query, e.g., max_over_time, increase_pure, etc.
            aggregate_func (str): The aggregate function to use for the query, e.g., max, sum, etc.
            subject_id (str): The metric ID to query from, e.g., owl_spent_total, owl_llm_token_usage_total, etc.
            filtered_by_org_id (list[str] | None): The organization IDs to filter by. None means no filtering.
            filtered_by_proj_id (list[str] | None): The project IDs to filter by. None means no filtering.
            from_ (datetime): The start time of the query.
            to (datetime | None): The end time of the query.
            group_by (list[str]): The group-by fields for the query, e.g., ["org_id", "proj_id"], etc.
            window_size (str): The window size to use for the query.
            timeout_value (int, optional): The timeout value in seconds. Defaults to 5.

        Returns:
            UsageResponse: A response containing windowSize and a list of the usage metrics.
        """
        # if "organization_id" in group_by:
        #     group_by.remove("organization_id")
        # if "project_id" in group_by:
        #     group_by.remove("project_id")
        #     group_by.append("proj_id")
        group_by = list(set(["org_id"] + group_by))
        query_filter = [
            "service.name=~'(owl|starling)'"
        ]  # always filter service by owl or starling
        if filtered_by_org_id:
            query_filter.append(f"org_id=~'{'|'.join(filtered_by_org_id)}'")
        if filtered_by_proj_id:
            query_filter.append(
                f"proj_id=~'{'|'.join(filtered_by_proj_id)}'"
            )  # Update to proj_id to align with Clickhouse Column

        # Convert datetime to Prometheus timestamp format
        data_interval = self._parse_duration(window_size)
        # Query VictoriaMetrics/Prometheus
        # In VictoriaMetrics/Prometheus max_over_time and increase are rollup functions,
        # which calculate the value over raw samples on the given lookbehind window d per each time series returned from the given series_selector.
        # Example: start time 2024-12-01 with step 1d means data is from 2024-11-30 to 2024-12-01.
        # Thus, the window_start is 2024-11-30 and window_end is 2024-12-01.
        # During the query, we add data_interval to start_time (so that the first datapoint is [2024-12-01, 2024-12-02]).
        # Otherwise, the first datetime will be [2024-11-30, 2024-12-01], which is not what we want.
        params = {
            "query": self._construct_usage_query(
                range_func, aggregate_func, subject_id, query_filter, group_by, window_size
            ),
            "start": (from_ + data_interval).timestamp(),
            "end": to.timestamp() if to else None,
            "step": window_size,
            "timeout": timeout_value,
        }
        response = await self._fetch_victoria_metrics(self.__QUERY_RANGE_ENDPOINT, params)
        response = response.json()["data"]["result"]

        return UsageResponse(
            windowSize=window_size,
            data=self._process_usage(response, data_interval, group_by),
            start=(from_ + data_interval).strftime("%Y-%m-%dT%H:%M:%SZ") if from_ else {},
            end=to.strftime("%Y-%m-%dT%H:%M:%SZ") if to else {},
        )

    async def query_llm_usage(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        return await self.query_usage(
            "increase_pure",
            "sum",
            "llm_token_usage",
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by,
            window_size,
        )

    async def query_image_usage(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        return await self.query_usage(
            "increase_pure",
            "sum",
            "image_token_usage",
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by,
            window_size,
        )

    async def query_embedding_usage(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        return await self.query_usage(
            "increase_pure",
            "sum",
            "embedding_token_usage",
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by,
            window_size,
        )

    async def query_reranking_usage(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        return await self.query_usage(
            "increase_pure",
            "sum",
            "reranker_search_usage",
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by,
            window_size,
        )

    async def query_billing(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        return await self.query_usage(
            "increase_pure",
            "sum",
            "spent",
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by,
            window_size,
        )

    def query_bandwidth(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        return self.query_usage(
            "increase_pure",
            "sum",
            "bandwidth_usage",
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by,
            window_size,
        )

    def query_storage(
        self,
        filtered_by_org_id: list[str] | None,
        filtered_by_proj_id: list[str] | None,
        from_: datetime,
        to: datetime | None,
        group_by: list[str],
        window_size: str,
    ) -> UsageResponse:
        return self.query_usage(
            "max_over_time",
            "max",
            "storage_usage",
            filtered_by_org_id,
            filtered_by_proj_id,
            from_,
            to,
            group_by,
            window_size,
        )
