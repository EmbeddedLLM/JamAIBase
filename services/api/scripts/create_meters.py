import openmeter
from azure.core.exceptions import ResourceExistsError
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
        "slug": "request_count_v2",
        "eventType": "request_count",
        "aggregation": "COUNT",
        "windowSize": "MINUTE",
        "description": "API request count.",
        "groupBy": {
            "method": "$.method",
            "path": "$.path",
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "user_id": "$.user_id",
            "agent": "$.agent",
            "agent_version": "$.agent_version",
            "architecture": "$.architecture",
            "system": "$.system",
            "system_version": "$.system_version",
            "language": "$.language",
            "language_version": "$.language_version",
        },
    },
    {
        "slug": "spent_v2",
        "eventType": "spent",
        "aggregation": "SUM",  # "SUM", "COUNT", "UNIQUE_COUNT", "AVG", "MIN", "MAX"
        "windowSize": "MINUTE",  # Aggregation window size: "MINUTE", "HOUR", "DAY" (Only MINUTE accepted for now)
        "description": "Spent amount in USD.",
        "groupBy": {
            "category": "$.category",
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "user_id": "$.user_id",
            "agent": "$.agent",
            "agent_version": "$.agent_version",
            "architecture": "$.architecture",
            "system": "$.system",
            "system_version": "$.system_version",
            "language": "$.language",
            "language_version": "$.language_version",
        },
        "valueProperty": "$.spent_usd",
    },
    {
        "slug": "llm_tokens_v2",
        "eventType": "llm_tokens",
        "aggregation": "SUM",
        "windowSize": "MINUTE",
        "description": "LLM token usage.",
        "groupBy": {
            "model": "$.model",
            "type": "$.type",  # "system", "input", "output"
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "user_id": "$.user_id",
            "agent": "$.agent",
            "agent_version": "$.agent_version",
            "architecture": "$.architecture",
            "system": "$.system",
            "system_version": "$.system_version",
            "language": "$.language",
            "language_version": "$.language_version",
        },
        "valueProperty": "$.tokens",
    },
    {
        "slug": "embedding_tokens_v2",
        "eventType": "embedding_tokens",
        "aggregation": "SUM",
        "windowSize": "MINUTE",
        "description": "Embedding token usage.",
        "groupBy": {
            "model": "$.model",
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "user_id": "$.user_id",
            "agent": "$.agent",
            "agent_version": "$.agent_version",
            "architecture": "$.architecture",
            "system": "$.system",
            "system_version": "$.system_version",
            "language": "$.language",
            "language_version": "$.language_version",
        },
        "valueProperty": "$.tokens",
    },
    {
        "slug": "reranker_searches_v2",
        "eventType": "reranker_searches",
        "aggregation": "SUM",
        "windowSize": "MINUTE",
        "description": "Reranker search usage.",
        "groupBy": {
            "model": "$.model",
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "user_id": "$.user_id",
            "agent": "$.agent",
            "agent_version": "$.agent_version",
            "architecture": "$.architecture",
            "system": "$.system",
            "system_version": "$.system_version",
            "language": "$.language",
            "language_version": "$.language_version",
        },
        "valueProperty": "$.searches",
    },
    {
        "slug": "bandwidth_v2",
        "eventType": "bandwidth",
        "aggregation": "SUM",
        "windowSize": "MINUTE",
        "description": "Egress usage in GB.",
        "groupBy": {
            "type": "$.type",  # "egress"
            "org_id": "$.org_id",
            "project_id": "$.project_id",
            "user_id": "$.user_id",
            "agent": "$.agent",
            "agent_version": "$.agent_version",
            "architecture": "$.architecture",
            "system": "$.system",
            "system_version": "$.system_version",
            "language": "$.language",
            "language_version": "$.language_version",
        },
        "valueProperty": "$.amount_gb",
    },
    {
        "slug": "storage_v2",
        "eventType": "storage",
        "aggregation": "MAX",
        "windowSize": "MINUTE",
        "description": "Storage usage in GB.",
        "groupBy": {
            "type": "$.type",  # "db" or "file"
            "org_id": "$.org_id",
            "agent": "$.agent",
            "agent_version": "$.agent_version",
            "architecture": "$.architecture",
            "system": "$.system",
            "system_version": "$.system_version",
            "language": "$.language",
            "language_version": "$.language_version",
        },
        "valueProperty": "$.amount_gb",
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
