from datetime import datetime, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel


class Metric(BaseModel):
    name: str
    device_type: str
    value: float
    timestamp: int
    hostname: str
    device_model: str
    device_id: str

    SYSTEM_METRIC_NAMES: ClassVar[dict[str, str]] = {
        "cpu_util": "cpu_util",
        "memory_util": "memory_util",
        "disk_read_bytes": "disk_read_bytes",
        "disk_write_bytes": "disk_write_bytes",
        "network_receive_bytes": "network_receive_bytes",
        "network_transmit_bytes": "network_transmit_bytes",
    }

    AMD_METRIC_NAMES: ClassVar[dict[str, str]] = {
        "gpu_clock": "device_clock",
        "gpu_memory_clock": "device_memory_clock",
        "gpu_edge_temperature": "device_temp",
        "gpu_memory_temperature": "device_memory_temp",
        "gpu_power_usage": "device_power_usage",
        "gpu_gfx_activity": "device_util",
        "gpu_umc_activity": "device_memory_utils",
        "gpu_free_vram": "device_free_memory",
        "gpu_used_vram": "device_used_memory",
    }

    NVIDIA_METRIC_NAMES: ClassVar[dict[str, str]] = {
        "DCGM_FI_DEV_SM_CLOCK": "device_clock",
        "DCGM_FI_DEV_MEM_CLOCK": "device_memory_clock",
        "DCGM_FI_DEV_GPU_TEMP": "device_temp",
        "DCGM_FI_DEV_MEMORY_TEMP": "device_memory_temp",
        "DCGM_FI_DEV_POWER_USAGE": "device_power_usage",
        "DCGM_FI_DEV_GPU_UTIL": "device_util",
        "DCGM_FI_DEV_MEM_COPY_UTIL": "device_memory_utils",
        "DCGM_FI_DEV_FB_FREE": "device_free_memory",
        "DCGM_FI_DEV_FB_USED": "device_used_memory",
    }

    SYSTEM_LABELS: ClassVar[dict[str, str]] = {
        "metric_name": "__name__",
        "hostname": "instance",
        "device_model": "N/A",
        "device_id": "N/A",
    }

    AMD_LABELS: ClassVar[dict[str, str]] = {
        "metric_name": "__name__",
        "hostname": "hostname",
        "device_model": "card_series",
        "device_id": "gpu_id",
    }

    NVIDIA_LABELS: ClassVar[dict[str, str]] = {
        "metric_name": "__name__",
        "hostname": "Hostname",
        "device_model": "modelName",
        "device_id": "gpu",
    }

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> "Metric":
        """Create a Metric instance from a response dictionary.

        This method extracts relevant information from the response dictionary obtained from response
        and uses it to create and return a Metric object. It determines the Device type and selects the appropriate
        labels and metric names for processing.

        Args:
            response (dict[str, Any]): A dictionary containing the metric data from response.

        Returns:
            Metric: A Metric object populated with the data from the response.

        Raises:
            ValueError: If the Device type is not recognized as either 'system', 'amd' or 'nvidia'.
        """
        device_type = response["metric"]["job"].split("-")[0]
        if device_type.lower() not in ["amd", "nvidia", "system"]:
            raise ValueError(
                f"Expected device_type to be within [nvidia, amd, system] but instead got {device_type}"
            )

        if device_type == "nvidia":
            device_labels = cls.NVIDIA_LABELS
            metric_names = cls.NVIDIA_METRIC_NAMES
        elif device_type == "amd":
            device_labels = cls.AMD_LABELS
            metric_names = cls.AMD_METRIC_NAMES
        elif device_type == "system":
            device_labels = cls.SYSTEM_LABELS
            metric_names = cls.SYSTEM_METRIC_NAMES

        return cls(
            name=metric_names[response["metric"][device_labels["metric_name"]]],
            device_type=device_type,
            value=float(response["value"][1]),
            timestamp=response["value"][0],
            hostname=response["metric"][device_labels["hostname"]],
            device_model=response["metric"].get(device_labels["device_model"], "N/A"),
            device_id=response["metric"].get(device_labels["device_id"], "N/A"),
        )


class Host(BaseModel):
    name: str
    metrics: list[Metric]


class Usage(BaseModel):
    value: float
    window_start: str
    window_end: str
    subject: str
    groupBy: dict[str, str]

    @classmethod
    def from_result(
        cls,
        value: list[Any],
        metrics: dict[str, Any],
        data_interval: timedelta,
        group_by: list[str],
    ) -> "Usage":
        """Create a Usage instance from a result entry.

        Args:
            value (list[Any]): A list containing the timestamp and value.
            metrics (dict[str, Any]): A dictionary containing metric labels.
            data_interval (timedelta): The data interval to adjust the window range.
            group_by (list[str]): The group-by fields for the query.

        Returns:
            Usage: A Usage object populated with the data from the result entry.
        """
        return cls(
            value=float(value[1]),
            window_start=(datetime.fromtimestamp(value[0]) - data_interval).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            window_end=datetime.fromtimestamp(value[0]).strftime("%Y-%m-%dT%H:%M:%SZ"),
            subject=metrics["org_id"],
            groupBy={
                key: metrics[key] for key in group_by if key != "org_id" and key in metrics.keys()
            },
        )


class UsageResponse(BaseModel):
    windowSize: str
    data: list[Usage]
    start: str
    end: str
