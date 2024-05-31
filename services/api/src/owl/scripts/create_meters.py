import openmeter
from azure.core.exceptions import ResourceExistsError
from loguru import logger
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from jamaibase.utils.io import dump_yaml


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    openmeter_api_base: str = "https://openmeter.cloud"
    # openmeter_api_base: str = "http://localhost:8888"
    openmeter_api_key: SecretStr

    @property
    def openmeter_api_key_plain(self):
        return self.openmeter_api_key.get_secret_value()


config = Config()
meters = [
    {
        "slug": "spent",
        "eventType": "spent",
        "aggregation": "SUM",  # "SUM", "COUNT", "UNIQUE_COUNT", "AVG", "MIN", "MAX"
        "windowSize": "MINUTE",  # Aggregation window size: "MINUTE", "HOUR", "DAY" (Only MINUTE accepted for now)
        "description": "Spent amount in USD.",
        "groupBy": {
            "category": "$.category",
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "api_key": "$.api_key",
        },
        "valueProperty": "$.spent_usd",
    },
    {
        "slug": "llm_tokens",
        "eventType": "llm_tokens",
        "aggregation": "SUM",
        "windowSize": "MINUTE",
        "description": "LLM token usage.",
        "groupBy": {
            "model": "$.model",
            "type": "$.type",  # "system", "input", "output"
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "api_key": "$.api_key",
        },
        "valueProperty": "$.tokens",
    },
    {
        "slug": "bandwidth",
        "eventType": "bandwidth",
        "aggregation": "SUM",
        "windowSize": "MINUTE",
        "description": "Egress usage in GB.",
        "groupBy": {
            "type": "$.type",  # "egress"
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "api_key": "$.api_key",
        },
        "valueProperty": "$.amount_gb",
    },
    {
        "slug": "storage",
        "eventType": "storage",
        "aggregation": "MAX",
        "windowSize": "MINUTE",
        "description": "Storage usage in GB.",
        "groupBy": {
            "type": "$.type",  # "db" or "file"
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "api_key": "$.api_key",
        },
        "valueProperty": "$.amount_gb",
    },
    {
        "slug": "request_count",
        "eventType": "request_count",
        "aggregation": "COUNT",
        "windowSize": "MINUTE",
        "description": "API request count.",
        "groupBy": {
            "method": "$.method",
            "path": "$.path",
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "api_key": "$.api_key",
        },
    },
    {
        "slug": "request_latency",
        "eventType": "request_latency",
        "aggregation": "AVG",
        "windowSize": "MINUTE",
        "description": "Request latency in millisecond.",
        "groupBy": {
            "task": "$.task",
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "api_key": "$.api_key",
        },
        "valueProperty": "$.latency_ms",
    },
]

dump_yaml(
    {
        "ingest": {"kafka": {"broker": "kafka:29092"}},
        "aggregation": {"clickhouse": {"address": "clickhouse:9000"}},
        "sink": {"minCommitCount": 1, "namespaceRefetch": "1s"},
        "meters": meters,
        "portal": {"enabled": True, "tokenSecret": "this-isnt-secure"},
    },
    "config.yaml",
)

# Async client can be initialized by importing the `Client` from `openmeter.aio`
openmeter_client = openmeter.Client(
    endpoint=config.openmeter_api_base,
    headers={
        "Accept": "application/json",
        "Authorization": f"Bearer {config.openmeter_api_key_plain}",
    },
    retry_status=3,
    retry_total=5,
)
for meter in meters:
    try:
        openmeter_client.create_meter(meter)
    except ResourceExistsError:
        pass
