import os
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import redis
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from owl.protocol import (
    EmbeddingModelConfig,
    LLMModelConfig,
    ModelListConfig,
    RerankingModelConfig,
)

CURR_DIR = Path(__file__).resolve().parent


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", cli_parse_args=True
    )
    # API configs
    owl_cache_purge: bool = False
    owl_db_dir: str = "db"
    owl_log_dir: str = "logs"
    owl_port: int = 7770
    owl_host: str = "0.0.0.0"
    owl_workers: int = 2
    owl_service: str = ""
    default_project: str = "default"
    default_org: str = "default"
    owl_redis_host: str = "dragonfly"
    # Configs
    owl_compute_storage_period_min: float = 1
    owl_models_config: str = str(CURR_DIR / "models.json")
    owl_pricing_config: str = str(CURR_DIR / "cloud_pricing.json")
    owl_llm_pricing_config: str = str(CURR_DIR / "cloud_pricing_llm.json")
    # Generative Table configs
    owl_reindex_period_sec: int = 60
    owl_immediate_reindex_max_rows: int = 2000
    owl_optimize_period_sec: int = 60
    owl_remove_version_older_than_mins: float = 5.0
    owl_concurrent_rows_batch_size: int = 3
    owl_concurrent_cols_batch_size: int = 5
    # Loader configs
    docio_url: str = "http://docio:6979/api/docio"
    unstructuredio_url: str = "http://unstructuredio:6989"
    # LLM configs
    cohere_api_base: str = "https://api.cohere.ai/v1"
    jina_api_base: str = "https://api.jina.ai/v1"
    voyage_api_base: str = "https://api.voyageai.com/v1"
    clip_api_base: str = "http://localhost:51010"
    # Keys
    owl_encryption_key: SecretStr = ""
    service_key: SecretStr = ""
    unstructuredio_api_key: SecretStr = "ellm"
    stripe_api_key: SecretStr = ""
    openmeter_api_key: SecretStr = ""
    openai_api_key: SecretStr = ""
    anthropic_api_key: SecretStr = ""
    gemini_api_key: SecretStr = ""
    cohere_api_key: SecretStr = ""
    groq_api_key: SecretStr = ""
    together_api_key: SecretStr = ""
    jina_api_key: SecretStr = ""
    voyage_api_key: SecretStr = ""

    @property
    def owl_encryption_key_plain(self):
        return self.owl_encryption_key.get_secret_value()

    @property
    def service_key_plain(self):
        return self.service_key.get_secret_value()

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


ENV_CONFIG = EnvConfig()

MODEL_CONFIG_KEY = "<owl> models"
PRICES_KEY = "<owl> prices"
LLM_PRICES_KEY = "<owl> llm_prices"
LOGS = {
    "stderr": {
        "level": "INFO",
        "serialize": False,
        "backtrace": False,
        "diagnose": True,
        "enqueue": True,
        "catch": True,
    },
    f"{ENV_CONFIG.owl_log_dir}/owl.log": {
        "level": "INFO",
        "serialize": False,
        "backtrace": False,
        "diagnose": True,
        "enqueue": True,
        "catch": True,
        "rotation": "50 MB",
        "delay": False,
        "watch": False,
    },
}
# Create db dir
try:
    os.makedirs(ENV_CONFIG.owl_db_dir, exist_ok=False)
except OSError:
    pass


class PlanName(str, Enum):
    default = "default"
    free = "free"
    pro = "pro"
    team = "team"


class ProductType(str, Enum):
    credit = "credit"
    credit_grant = "credit_grant"
    llm_tokens = "llm_tokens"
    db_storage = "db_storage"
    file_storage = "file_storage"
    egress = "egress"


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
    name: str
    included: Tier = Tier(unit_amount_decimal=0, up_to=0)
    tiers: list[Tier]
    unit: str = Field(
        description="Unit of measurement.",
    )


class Plan(BaseModel):
    stripe_price_id_live: str
    stripe_price_id_test: str
    flat_amount_decimal: Decimal = Field(
        description="Base price for the entire tier.",
    )
    credit_grant: float = Field(
        description="Credit amount included in USD.",
    )
    max_users: int = Field(
        description=(
            "Maximum number of users per organization. "
            "Amount of quota will be scaled by the number of users."
        ),
    )
    products: dict[str, Product] = Field(
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
    plans: dict[PlanName, Plan] = Field(
        description="Mapping of price plan name to price plan.",
    )


class LLMPricing(BaseModel):
    products: dict[ProductType, Product] = Field(
        description="Mapping of price name to tier list where each element represents a pricing tier.",
    )


class Config:
    def __init__(self):
        self.use_redis = ENV_CONFIG.owl_workers > 1
        if self.use_redis:
            logger.info("Using Redis as cache.")
            self._redis = redis.Redis(host=ENV_CONFIG.owl_redis_host, port=6379, db=0)
        else:
            logger.info("Using in-memory dict as cache.")
        self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

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

    def __getitem__(self, key: str) -> str:
        if self.use_redis:
            item = self._redis.get(key)
            if item is None:
                raise KeyError(key)
            return item.decode("utf-8")
        else:
            return self._data[key]

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
            key in self._data

    def __repr__(self) -> str:
        if self.use_redis:
            _data = {key.decode("utf-8"): self[key] for key in self._redis.scan_iter("<owl>*")}
        else:
            _data = self._data
        return repr(_data)

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_model_config() -> ModelListConfig:
        # Validate JSON file
        with open(ENV_CONFIG.owl_models_config, "r") as f:
            models = ModelListConfig.model_validate_json(f.read())
        return models

    def get_model_json(self) -> str:
        models = self.get(MODEL_CONFIG_KEY)
        if models is None:
            models = self._load_model_config().model_dump_json()
            self[MODEL_CONFIG_KEY] = models
            logger.warning(f"Model config set to: {models}")
        return models

    def get_model_config(self) -> ModelListConfig:
        model_json = self[MODEL_CONFIG_KEY]
        if model_json is None:
            model_json = self.get_model_json()
        return ModelListConfig.model_validate_json(model_json)

    def set_model_config(self, body: ModelListConfig) -> None:
        config_json = body.model_dump_json()
        self[MODEL_CONFIG_KEY] = config_json
        logger.info(f"Model config set to: {body}")
        try:
            with open(ENV_CONFIG.owl_models_config, "w") as f:
                f.write(config_json)
        except Exception as e:
            logger.warning(f"Failed to update `{ENV_CONFIG.owl_models_config}`: {e}")

    def get_model_info(
        self,
        model_type: str,
        model_id: str,
    ) -> LLMModelConfig | EmbeddingModelConfig | RerankingModelConfig:
        models = getattr(self.get_model_config(), model_type)
        infos = [m for m in models if m.id == model_id]
        if len(infos) == 0:
            raise ValueError(
                f"Invalid model ID: {model_id}. Available models: {[m.id for m in models]}"
            )
        return infos[0]

    def get_llm_model_info(self, model_id: str) -> LLMModelConfig:
        return self.get_model_info("llm_models", model_id)

    def get_embed_model_info(self, model_id: str) -> EmbeddingModelConfig:
        return self.get_model_info("embed_models", model_id)

    def get_rerank_model_info(self, model_id: str) -> RerankingModelConfig:
        return self.get_model_info("rerank_models", model_id)

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_pricing() -> Price:
        # Validate JSON file
        with open(ENV_CONFIG.owl_pricing_config, "r") as f:
            pricing = Price.model_validate_json(f.read())
        return pricing

    def get_pricing(self) -> Price:
        pricing_json = self.get(PRICES_KEY)
        if pricing_json is None:
            pricing = self._load_pricing()
            self[PRICES_KEY] = pricing.model_dump_json()
            logger.warning(f"Pricing set to: {pricing}")
            return pricing
        return Price.model_validate_json(pricing_json)

    def set_pricing(self, body: Price) -> None:
        pricing_json = body.model_dump_json()
        self[PRICES_KEY] = pricing_json
        logger.info(f"Pricing set to: {body}")
        try:
            with open(ENV_CONFIG.owl_pricing_config, "w") as f:
                f.write(pricing_json)
        except Exception as e:
            logger.warning(f"Failed to update `{ENV_CONFIG.owl_pricing_config}`: {e}")

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_llm_pricing() -> Price:
        # Validate JSON file
        with open(ENV_CONFIG.owl_llm_pricing_config, "r") as f:
            pricing = Price.model_validate_json(f.read())
        return pricing

    def get_llm_pricing(self) -> Price:
        pricing_json = self.get(LLM_PRICES_KEY)
        if pricing_json is None:
            pricing = self._load_llm_pricing()
            self[LLM_PRICES_KEY] = pricing.model_dump_json()
            logger.warning(f"LLM pricing set to: {pricing}")
            return pricing
        return Price.model_validate_json(pricing_json)

    def set_llm_pricing(self, body: Price) -> None:
        pricing_json = body.model_dump_json()
        self[PRICES_KEY] = pricing_json
        logger.info(f"Pricing set to: {body}")
        try:
            with open(ENV_CONFIG.owl_llm_pricing_config, "w") as f:
                f.write(pricing_json)
        except Exception as e:
            logger.warning(f"Failed to update `{ENV_CONFIG.owl_llm_pricing_config}`: {e}")


CONFIG = Config()
