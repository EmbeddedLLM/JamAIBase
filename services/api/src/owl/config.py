from functools import lru_cache
from pathlib import Path

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from jamaibase.protocol import (
    EmbeddingModelConfig,
    LLMModelConfig,
    ModelListConfig,
    RerankingModelConfig,
)
from owl.cache import CACHE

CURR_DIR = Path(__file__).resolve().parent


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    owl_log_dir: str = "logs"
    owl_models_config: str = str(CURR_DIR / "models.json")


CONFIG = Config()
MODEL_CONFIG_KEY = "<owl> models"
PRICES_KEY = "<owl> prices"
LLM_PRICES_KEY = "<owl> llm_prices"


@lru_cache(maxsize=1)
def _load_model_config() -> ModelListConfig:
    # Validate JSON file
    with open(CONFIG.owl_models_config, "r") as f:
        models = ModelListConfig.model_validate_json(f.read())
    return models


def get_model_json() -> str:
    models = CACHE.get(MODEL_CONFIG_KEY)
    if models is None:
        models = _load_model_config().model_dump_json()
        CACHE[MODEL_CONFIG_KEY] = models
        logger.warning(f"Model config set to: {models}")
        return models
    return models


def get_model_info(
    model_type: str, model_id: str
) -> LLMModelConfig | EmbeddingModelConfig | RerankingModelConfig:
    models = CACHE.get(MODEL_CONFIG_KEY)
    if models is None:
        models = get_model_json()
    models = ModelListConfig.model_validate_json(models)
    models = getattr(models, model_type)
    infos = [m for m in models if m.id == model_id]
    if len(infos) == 0:
        raise ValueError(
            f"Invalid model ID: {model_id}. Available models: {[m.id for m in models]}"
        )
    return infos[0]


def get_llm_model_info(model_id: str) -> LLMModelConfig:
    return get_model_info("llm_models", model_id)


def get_embed_model_info(model_id: str) -> EmbeddingModelConfig:
    return get_model_info("embed_models", model_id)


def get_rerank_model_info(model_id: str) -> RerankingModelConfig:
    return get_model_info("rerank_models", model_id)


LOGS = {
    "stderr": {
        "level": "INFO",
        "serialize": False,
        "backtrace": False,
        "diagnose": True,
        "enqueue": True,
        "catch": True,
    },
    f"{CONFIG.owl_log_dir}/owl.log": {
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
