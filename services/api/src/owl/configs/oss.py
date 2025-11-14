from functools import cached_property
from os.path import abspath
from pathlib import Path
from typing import Annotated, Literal, Self

from loguru import logger
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CURR_DIR = Path(__file__).resolve().parent


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="owl_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        cli_parse_args=False,
    )
    # API configs
    db_path: str = "postgresql+psycopg://owlpguser:owlpgpassword@pgbouncer:5432/jamaibase_owl"  # Default to Postgres
    log_dir: str = "logs"
    host: str = "0.0.0.0"
    port: int = 6969
    workers: int = 1  # The suggested number of workers is (2*CPU)+1
    max_concurrency: int = 300
    db_init: bool | None = None  # None means unset
    db_reset: bool = False
    db_init_max_users: int = 5
    cache_reset: bool = False
    enable_byok: bool = True
    disable_billing: bool = False
    log_timings: bool = False
    # Services
    redis_host: str = "dragonfly"
    redis_port: int = 6379
    file_proxy_url: str = "localhost:6969"
    file_dir: str = "s3://file"
    s3_endpoint: str = "http://minio:9000"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: SecretStr = "minioadmin"
    code_executor_endpoint: str = "http://kopi:3000"
    docling_url: str = "http://docling:5001"
    docling_timeout_sec: Annotated[int, Field(gt=0, le=60 * 60)] = 20 * 60
    test_llm_api_base: str = "http://test-llm:6970/v1"
    # Configs
    embed_file_upload_max_bytes: int = 200 * 1024 * 1024  # 200MiB in bytes
    image_file_upload_max_bytes: int = 20 * 1024 * 1024  # 20MiB in bytes
    audio_file_upload_max_bytes: int = 120 * 1024 * 1024  # 120MiB in bytes
    compute_storage_period_sec: Annotated[float, Field(ge=0, le=60 * 60)] = 60 * 5
    document_loader_cache_ttl_sec: int = 60 * 15  # 15 minutes
    # Starling configs
    s3_backup_bucket_name: str = ""
    # Starling database configs
    flush_clickhouse_buffer_sec: int = 60
    # Generative Table configs
    concurrent_rows_batch_size: int = 3
    concurrent_cols_batch_size: int = 5
    max_write_batch_size: int = 100
    max_file_cache_size: int = 20
    # PDF Loader configs
    fast_pdf_parsing: bool = True
    # LLM configs
    llm_timeout_sec: Annotated[int, Field(gt=0, le=60 * 60)] = 60
    embed_timeout_sec: Annotated[int, Field(gt=0, le=60 * 60)] = 60
    code_timeout_sec: Annotated[int, Field(gt=0, le=60 * 60)] = 120
    cohere_api_base: str = "https://api.cohere.ai/v1"
    jina_ai_api_base: str = "https://api.jina.ai/v1"
    voyage_api_base: str = "https://api.voyageai.com/v1"
    # Keys
    encryption_key: SecretStr = ""
    service_key: SecretStr = ""
    service_key_alt: SecretStr = ""
    # OpenTelemetry configs
    opentelemetry_host: str = "otel-collector"
    opentelemetry_port: int = 4317
    # VictoriaMetrics configs
    victoria_metrics_host: str = "vmauth"
    victoria_metrics_port: int = 8427
    victoria_metrics_user: str = "owl"
    victoria_metrics_password: SecretStr = "owl-vm"
    # Clickhouse configs
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8123
    clickhouse_user: str = "owluser"
    clickhouse_password: SecretStr = "owlpassword"
    clickhouse_db: str = "jamaibase_owl"
    clickhouse_max_buffer_queue_size: int = 10000
    # Clickhouse Redis queue buffer
    clickhouse_buffer_key: str = "<owl>clickhouse_insert_buffer"
    # Stripe & Billing
    stripe_api_key: SecretStr = ""
    stripe_publishable_key_live: SecretStr = ""
    stripe_publishable_key_test: SecretStr = ""
    stripe_webhook_secret_live: SecretStr = ""
    stripe_webhook_secret_test: SecretStr = ""
    payment_lapse_max_days: int = 7
    # Auth0
    auth0_api_key: SecretStr = ""
    # Keys
    unstructuredio_api_key: SecretStr = "ellm"
    anthropic_api_key: SecretStr = ""
    azure_api_key: SecretStr = ""
    azure_ai_api_key: SecretStr = ""
    bedrock_api_key: SecretStr = ""
    cerebras_api_key: SecretStr = ""
    cohere_api_key: SecretStr = ""
    deepseek_api_key: SecretStr = ""
    ellm_api_key: SecretStr = ""
    gemini_api_key: SecretStr = ""
    groq_api_key: SecretStr = ""
    hyperbolic_api_key: SecretStr = ""
    jina_ai_api_key: SecretStr = ""
    openai_api_key: SecretStr = ""
    openrouter_api_key: SecretStr = ""
    sagemaker_api_key: SecretStr = ""
    sambanova_api_key: SecretStr = ""
    together_ai_api_key: SecretStr = ""
    vertex_ai_api_key: SecretStr = ""
    voyage_api_key: SecretStr = ""

    @model_validator(mode="after")
    def check_db_init(self) -> Self:
        if self.db_init is None:
            self.db_init = True if self.is_oss else False
        return self

    @model_validator(mode="after")
    def make_paths_absolute(self) -> Self:
        self.log_dir = abspath(self.log_dir)
        return self

    @model_validator(mode="after")
    def check_alternate_service_key(self) -> Self:
        if self.service_key_alt.get_secret_value().strip() == "":
            self.service_key_alt = self.service_key
        return self

    @model_validator(mode="after")
    def validate_db_path(self) -> Self:
        """
        Validates that `db_path` starts with either `rqlite+pyrqlite://` or `sqlite://` or `sqlite+libsql://` or `postgresql`.
        """
        if not (
            self.db_path.startswith("rqlite+pyrqlite://")
            or self.db_path.startswith("sqlite://")
            or self.db_path.startswith("sqlite+libsql://")
            or self.db_path.startswith("postgresql")
        ):
            raise ValueError(f'`db_path` "{self.db_path}" has an invalid dialect.')
        return self

    @property
    def db_dialect(self) -> Literal["rqlite", "libsql", "postgresql", "sqlite"]:
        """
        Show the sqlite dialect that's in use based on the `db_path`.
        """
        if self.db_path.startswith("rqlite+pyrqlite://"):
            return "rqlite"
        elif self.db_path.startswith("sqlite+libsql://"):
            return "libsql"
        elif self.db_path.startswith("postgresql"):
            return "postgresql"
        elif self.db_path.startswith("sqlite://"):
            return "sqlite"

    @cached_property
    def is_oss(self) -> bool:
        logger.opt(colors=True).info("Launching in <b><u><cyan>OSS mode</></></>.")
        return True

    @cached_property
    def is_cloud(self) -> bool:
        return not self.is_oss

    @property
    def s3_secret_access_key_plain(self) -> str:
        return self.s3_secret_access_key.get_secret_value()

    @property
    def victoria_metrics_password_plain(self) -> str:
        return self.victoria_metrics_password.get_secret_value().strip()

    @property
    def is_stripe_live(self) -> bool:
        return self.stripe_api_key_plain.startswith("sk_live")

    @property
    def stripe_api_key_plain(self) -> str:
        return self.stripe_api_key.get_secret_value()

    @property
    def stripe_webhook_secret_plain(self) -> str:
        return (
            self.stripe_webhook_secret_live.get_secret_value()
            if self.is_stripe_live
            else self.stripe_webhook_secret_test.get_secret_value()
        )

    @property
    def stripe_publishable_key_plain(self) -> str:
        return (
            self.stripe_publishable_key_live.get_secret_value()
            if self.is_stripe_live
            else self.stripe_publishable_key_test.get_secret_value()
        )

    @property
    def auth0_api_key_plain(self) -> str:
        return self.auth0_api_key.get_secret_value()

    @property
    def encryption_key_plain(self) -> str:
        return self.encryption_key.get_secret_value()

    @property
    def service_key_plain(self) -> str:
        return self.service_key.get_secret_value()

    @property
    def service_key_alt_plain(self) -> str:
        return self.service_key_alt.get_secret_value()

    @property
    def unstructuredio_api_key_plain(self) -> str:
        return self.unstructuredio_api_key.get_secret_value()

    @property
    def anthropic_api_key_plain(self) -> str:
        return self.anthropic_api_key.get_secret_value()

    @property
    def azure_api_key_plain(self) -> str:
        return self.azure_api_key.get_secret_value()

    @property
    def azure_ai_api_key_plain(self) -> str:
        return self.azure_ai_api_key.get_secret_value()

    @property
    def bedrock_api_key_plain(self) -> str:
        return self.azure_ai_api_key.get_secret_value()

    @property
    def cerebras_api_key_plain(self) -> str:
        return self.cerebras_api_key.get_secret_value()

    @property
    def cohere_api_key_plain(self) -> str:
        return self.cohere_api_key.get_secret_value()

    @property
    def deepseek_api_key_plain(self) -> str:
        return self.deepseek_api_key.get_secret_value()

    @property
    def ellm_api_key_plain(self) -> str:
        return self.ellm_api_key.get_secret_value()

    @property
    def gemini_api_key_plain(self) -> str:
        return self.gemini_api_key.get_secret_value()

    @property
    def groq_api_key_plain(self) -> str:
        return self.groq_api_key.get_secret_value()

    @property
    def hyperbolic_api_key_plain(self) -> str:
        return self.hyperbolic_api_key.get_secret_value()

    @property
    def jina_ai_api_key_plain(self) -> str:
        return self.jina_ai_api_key.get_secret_value()

    @property
    def openai_api_key_plain(self) -> str:
        return self.openai_api_key.get_secret_value()

    @property
    def openrouter_api_key_plain(self) -> str:
        return self.openrouter_api_key.get_secret_value()

    @property
    def sagemaker_api_key_plain(self) -> str:
        return self.sagemaker_api_key.get_secret_value()

    @property
    def sambanova_api_key_plain(self) -> str:
        return self.sambanova_api_key.get_secret_value()

    @property
    def together_ai_api_key_plain(self) -> str:
        return self.together_ai_api_key.get_secret_value()

    @property
    def vertex_ai_api_key_plain(self) -> str:
        return self.vertex_ai_api_key.get_secret_value()

    @property
    def voyage_api_key_plain(self) -> str:
        return self.voyage_api_key.get_secret_value()

    def get_api_key(self, provider: str, default: str = "") -> str:
        return getattr(self, f"{provider}_api_key_plain", default)
