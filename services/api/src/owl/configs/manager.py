import os
from decimal import Decimal
from enum import Enum
from functools import cached_property, lru_cache
from os.path import abspath
from pathlib import Path
from typing import Annotated, Any

import redis
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError
from redis.retry import Retry

from owl.protocol import (
    EXAMPLE_CHAT_MODEL,
    EXAMPLE_EMBEDDING_MODEL,
    EXAMPLE_RERANKING_MODEL,
    ModelListConfig,
)

CURR_DIR = Path(__file__).resolve().parent


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", cli_parse_args=False
    )
    # API configs
    owl_is_prod: bool = False
    owl_cache_purge: bool = False
    owl_db_dir: str = "db"
    owl_file_dir: str = "file://file"
    owl_log_dir: str = "logs"
    owl_file_proxy_url: str = "localhost:6969"
    owl_host: str = "0.0.0.0"
    owl_port: int = 6969
    owl_workers: int = 1
    owl_max_concurrency: int = 300
    default_org_id: str = "default"
    default_project_id: str = "default"
    owl_redis_host: str = "dragonfly"
    owl_redis_port: int = 6379
    owl_internal_org_id: str = "org_82d01c923f25d5939b9d4188"
    # Configs
    owl_file_upload_max_bytes: int = 20 * 1024 * 1024  # 20MB in bytes
    owl_compute_storage_period_min: float = 1
    owl_models_config: str = "models.json"
    owl_pricing_config: str = "cloud_pricing.json"
    # Starling configs
    s3_endpoint: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = ""
    s3_backup_bucket_name: str = ""
    # Generative Table configs
    owl_table_lock_timeout_sec: int = 15
    owl_reindex_period_sec: int = 60
    owl_immediate_reindex_max_rows: int = 2000
    owl_optimize_period_sec: int = 60
    owl_remove_version_older_than_mins: float = 5.0
    owl_concurrent_rows_batch_size: int = 3
    owl_concurrent_cols_batch_size: int = 5
    owl_max_write_batch_size: int = 1000
    # Loader configs
    docio_url: str = "http://docio:6979/api/docio"
    unstructuredio_url: str = "http://unstructuredio:6989"
    # PDF Loader configs
    owl_fast_pdf_parsing: bool = True
    # LLM configs
    owl_llm_timeout_sec: Annotated[int, Field(gt=0, le=60 * 60)] = 60
    owl_embed_timeout_sec: Annotated[int, Field(gt=0, le=60 * 60)] = 60
    cohere_api_base: str = "https://api.cohere.ai/v1"
    jina_api_base: str = "https://api.jina.ai/v1"
    voyage_api_base: str = "https://api.voyageai.com/v1"
    clip_api_base: str = "http://localhost:51010"
    # Auth Keys
    owl_session_secret: SecretStr = "oh yeah"
    owl_github_client_id: str = ""
    owl_github_client_secret: SecretStr = ""
    owl_encryption_key: SecretStr = ""
    service_key: SecretStr = ""
    service_key_alt: SecretStr = ""
    # Keys
    unstructuredio_api_key: SecretStr = "ellm"
    stripe_api_key: SecretStr = ""
    openmeter_api_key: SecretStr = ""
    custom_api_key: SecretStr = ""
    openai_api_key: SecretStr = ""
    anthropic_api_key: SecretStr = ""
    gemini_api_key: SecretStr = ""
    cohere_api_key: SecretStr = ""
    groq_api_key: SecretStr = ""
    together_api_key: SecretStr = ""
    jina_api_key: SecretStr = ""
    voyage_api_key: SecretStr = ""
    hyperbolic_api_key: SecretStr = ""
    cerebras_api_key: SecretStr = ""
    sambanova_api_key: SecretStr = ""

    @model_validator(mode="after")
    def make_paths_absolute(self):
        self.owl_db_dir = abspath(self.owl_db_dir)
        self.owl_log_dir = abspath(self.owl_log_dir)
        self.owl_models_config: str = str(CURR_DIR / self.owl_models_config)
        self.owl_pricing_config: str = str(CURR_DIR / self.owl_pricing_config)
        return self

    @model_validator(mode="after")
    def check_alternate_service_key(self):
        if self.service_key_alt.get_secret_value().strip() == "":
            self.service_key_alt = self.service_key
        return self

    @cached_property
    def is_oss(self):
        if self.service_key.get_secret_value() == "":
            return True
        return not (CURR_DIR.parent / "routers" / "cloud_admin.py").is_file()

    @property
    def s3_secret_access_key_plain(self):
        return self.s3_secret_access_key.get_secret_value()

    @property
    def owl_encryption_key_plain(self):
        return self.owl_encryption_key.get_secret_value()

    @property
    def owl_session_secret_plain(self):
        return self.owl_session_secret.get_secret_value()

    @property
    def owl_github_client_secret_plain(self):
        return self.owl_github_client_secret.get_secret_value()

    @property
    def service_key_plain(self):
        return self.service_key.get_secret_value()

    @property
    def service_key_alt_plain(self):
        return self.service_key_alt.get_secret_value()

    @property
    def unstructuredio_api_key_plain(self):
        return self.unstructuredio_api_key.get_secret_value()

    @property
    def stripe_api_key_plain(self):
        return self.stripe_api_key.get_secret_value()

    @property
    def openmeter_api_key_plain(self):
        return self.openmeter_api_key.get_secret_value()

    @property
    def custom_api_key_plain(self):
        return self.custom_api_key.get_secret_value()

    @property
    def openai_api_key_plain(self):
        return self.openai_api_key.get_secret_value()

    @property
    def anthropic_api_key_plain(self):
        return self.anthropic_api_key.get_secret_value()

    @property
    def gemini_api_key_plain(self):
        return self.gemini_api_key.get_secret_value()

    @property
    def cohere_api_key_plain(self):
        return self.cohere_api_key.get_secret_value()

    @property
    def groq_api_key_plain(self):
        return self.groq_api_key.get_secret_value()

    @property
    def together_api_key_plain(self):
        return self.together_api_key.get_secret_value()

    @property
    def jina_api_key_plain(self):
        return self.jina_api_key.get_secret_value()

    @property
    def voyage_api_key_plain(self):
        return self.voyage_api_key.get_secret_value()

    @property
    def hyperbolic_api_key_plain(self):
        return self.hyperbolic_api_key.get_secret_value()

    @property
    def cerebras_api_key_plain(self):
        return self.cerebras_api_key.get_secret_value()

    @property
    def sambanova_api_key_plain(self):
        return self.sambanova_api_key.get_secret_value()


MODEL_CONFIG_KEY = "<owl> models"
PRICES_KEY = "<owl> prices"
INTERNAL_ORG_ID_KEY = "<owl> internal_org_id"
ENV_CONFIG = EnvConfig()
# Create db dir
try:
    os.makedirs(ENV_CONFIG.owl_db_dir, exist_ok=False)
except OSError:
    pass


class PlanName(str, Enum):
    DEFAULT = "default"
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    DEMO = "_demo"
    PARTNER = "_partner"
    DEBUG = "_debug"

    def __str__(self) -> str:
        return self.value


_product2column = dict(
    credit=("credit",),
    credit_grant=("credit_grant",),
    llm_tokens=("llm_tokens_quota_mtok", "llm_tokens_usage_mtok"),
    embedding_tokens=(
        "embedding_tokens_quota_mtok",
        "embedding_tokens_usage_mtok",
    ),
    reranker_searches=("reranker_quota_ksearch", "reranker_usage_ksearch"),
    db_storage=("db_quota_gib", "db_usage_gib"),
    file_storage=("file_quota_gib", "file_usage_gib"),
    egress=("egress_quota_gib", "egress_usage_gib"),
)


class ProductType(str, Enum):
    CREDIT = "credit"
    CREDIT_GRANT = "credit_grant"
    LLM_TOKENS = "llm_tokens"
    EMBEDDING_TOKENS = "embedding_tokens"
    RERANKER_SEARCHES = "reranker_searches"
    DB_STORAGE = "db_storage"
    FILE_STORAGE = "file_storage"
    EGRESS = "egress"

    def __str__(self) -> str:
        return self.value

    @property
    def quota_column(self) -> str:
        return _product2column[self.value][0]

    @property
    def usage_column(self) -> str:
        return _product2column[self.value][-1]

    @classmethod
    def exclude_credits(cls) -> list["ProductType"]:
        return [p for p in cls if not p.value.startswith("credit")]


class Tier(BaseModel):
    """
    https://docs.stripe.com/api/prices/object#price_object-tiers
    """

    unit_amount_decimal: Decimal = Field(
        description="Per unit price for units relevant to the tier.",
    )
    up_to: float | None = Field(
        description=(
            "Up to and including to this quantity will be contained in the tier. "
            "None means infinite quantity."
        ),
    )


class Product(BaseModel):
    name: str = Field(
        min_length=1,
        description="Plan name.",
    )
    included: Tier = Tier(unit_amount_decimal=0, up_to=0)
    tiers: list[Tier]
    unit: str = Field(
        description="Unit of measurement.",
    )


class Plan(BaseModel):
    name: str
    stripe_price_id_live: str
    stripe_price_id_test: str
    flat_amount_decimal: Decimal = Field(
        description="Base price for the entire tier.",
    )
    credit_grant: float = Field(
        description="Credit amount included in USD.",
    )
    max_users: int = Field(
        description="Maximum number of users per organization.",
    )
    products: dict[ProductType, Product] = Field(
        description="Mapping of price name to tier list where each element represents a pricing tier.",
    )

    @computed_field
    @property
    def stripe_price_id(self) -> str:
        return (
            self.stripe_price_id_live
            if ENV_CONFIG.stripe_api_key_plain.startswith("sk_live")
            else self.stripe_price_id_test
        )


class Price(BaseModel):
    object: str = Field(
        default="prices.plans",
        description="Type of API response object.",
        examples=["prices.plans"],
    )
    plans: dict[PlanName, Plan] = Field(
        description="Mapping of price plan name to price plan.",
    )


class _ModelPrice(BaseModel):
    id: str = Field(
        description=(
            'Unique identifier in the form of "{provider}/{model_id}". '
            "Users will specify this to select a model."
        ),
        examples=[EXAMPLE_CHAT_MODEL, EXAMPLE_EMBEDDING_MODEL, EXAMPLE_RERANKING_MODEL],
    )
    name: str = Field(
        description="Name of the model.",
        examples=["OpenAI GPT-4o Mini"],
    )


class LLMModelPrice(_ModelPrice):
    input_cost_per_mtoken: float = Field(
        description="Cost in USD per million (mega) input / prompt token.",
    )
    output_cost_per_mtoken: float = Field(
        description="Cost in USD per million (mega) output / completion token.",
    )


class EmbeddingModelPrice(_ModelPrice):
    cost_per_mtoken: float = Field(
        description="Cost in USD per million embedding tokens.",
    )


class RerankingModelPrice(_ModelPrice):
    cost_per_ksearch: float = Field(description="Cost in USD for a thousand searches.")


class ModelPrice(BaseModel):
    object: str = Field(
        default="prices.models",
        description="Type of API response object.",
        examples=["prices.models"],
    )
    llm_models: list[LLMModelPrice] = []
    embed_models: list[EmbeddingModelPrice] = []
    rerank_models: list[RerankingModelPrice] = []


class Config:
    def __init__(self):
        self.use_redis = ENV_CONFIG.owl_workers > 1
        if self.use_redis:
            logger.debug("Using Redis as cache.")
            self._redis = redis.Redis(
                host=ENV_CONFIG.owl_redis_host,
                port=ENV_CONFIG.owl_redis_port,
                db=0,
                # https://redis.io/kb/doc/22wxq63j93/how-to-manage-client-reconnections-in-case-of-errors-with-redis-py
                retry=Retry(ExponentialBackoff(cap=10, base=1), 25),
                retry_on_error=[ConnectionError, TimeoutError, ConnectionResetError],
                health_check_interval=1,
            )
        else:
            logger.debug("Using in-memory dict as cache.")
        self._data = {}

    def get(self, key: str) -> Any:
        return self[key]

    def set(self, key: str, value: str) -> None:
        self[key] = value

    def purge(self):
        if self.use_redis:
            for key in self._redis.scan_iter("<owl>*"):
                self._redis.delete(key)
        else:
            self._data = {}

    def __setitem__(self, key: str, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"`value` must be a str, received: {type(value)}")
        if not (isinstance(key, str) and key.startswith("<owl>")):
            raise ValueError(f'`key` must be a str that starts with "<owl>", received: {key}')
        if self.use_redis:
            self._redis.set(key, value)
        else:
            self._data[key] = value

    def __getitem__(self, key: str) -> str | None:
        if self.use_redis:
            item = self._redis.get(key)
            return None if item is None else item.decode("utf-8")
        else:
            try:
                return self._data[key]
            except KeyError:
                return None

    def __delitem__(self, key) -> None:
        if self.use_redis:
            self._redis.delete(key)
        else:
            if key in self._data:
                del self._data[key]

    def __contains__(self, key) -> bool:
        if self.use_redis:
            self._redis.exists(key)
        else:
            return key in self._data

    def __repr__(self) -> str:
        if self.use_redis:
            _data = {key.decode("utf-8"): self[key] for key in self._redis.scan_iter("<owl>*")}
        else:
            _data = self._data
        return repr(_data)

    def get_internal_organization_id(self) -> str:
        org_id = self[INTERNAL_ORG_ID_KEY]
        if org_id is None:
            org_id = ENV_CONFIG.owl_internal_org_id
            self[INTERNAL_ORG_ID_KEY] = org_id
        return org_id

    def set_internal_organization_id(self, organization_id: str) -> None:
        self[INTERNAL_ORG_ID_KEY] = organization_id
        logger.info(f"Internal organization ID set to: {organization_id}")

    @property
    def internal_organization_id(self) -> str:
        return self.get_internal_organization_id()

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_model_config_from_json(json: str) -> ModelListConfig:
        models = ModelListConfig.model_validate_json(json)
        return models

    def _load_model_config_from_file(self) -> ModelListConfig:
        # Validate JSON file
        with open(ENV_CONFIG.owl_models_config, "r") as f:
            models = self._load_model_config_from_json(f.read())
        return models

    def get_model_json(self) -> str:
        model_json = self[MODEL_CONFIG_KEY]
        if model_json is None:
            model_json = self._load_model_config_from_file().model_dump_json()
            self[MODEL_CONFIG_KEY] = model_json
            logger.warning(f"Model config set to: {model_json}")
        return model_json

    def get_model_config(self) -> ModelListConfig:
        model_json = self[MODEL_CONFIG_KEY]
        if model_json is None:
            model_json = self.get_model_json()
        return self._load_model_config_from_json(model_json)

    def set_model_config(self, body: ModelListConfig) -> None:
        self[MODEL_CONFIG_KEY] = body.model_dump_json()
        logger.info(f"Model config set to: {body}")
        try:
            with open(ENV_CONFIG.owl_models_config, "w") as f:
                f.write(body.model_dump_json(exclude_defaults=True))
        except Exception as e:
            logger.warning(f"Failed to update `{ENV_CONFIG.owl_models_config}`: {e}")

    def get_model_pricing(self) -> ModelPrice:
        return ModelPrice.model_validate(self.get_model_config().model_dump(exclude={"object"}))

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_pricing_from_json(json: str) -> Price:
        pricing = Price.model_validate_json(json)
        return pricing

    def _load_pricing_from_file(self) -> Price:
        # Validate JSON file
        with open(ENV_CONFIG.owl_pricing_config, "r") as f:
            pricing = self._load_pricing_from_json(f.read())
        return pricing

    def get_pricing(self) -> Price:
        pricing_json = self[PRICES_KEY]
        if pricing_json is None:
            pricing = self._load_pricing_from_file()
            self[PRICES_KEY] = pricing.model_dump_json()
            logger.warning(f"Pricing set to: {pricing}")
            return pricing
        return self._load_pricing_from_json(pricing_json)

    def set_pricing(self, body: Price) -> None:
        self[PRICES_KEY] = body.model_dump_json()
        logger.info(f"Pricing set to: {body}")
        try:
            with open(ENV_CONFIG.owl_pricing_config, "w") as f:
                f.write(body.model_dump_json(exclude_defaults=True))
        except Exception as e:
            logger.warning(f"Failed to update `{ENV_CONFIG.owl_pricing_config}`: {e}")


CONFIG = Config()
