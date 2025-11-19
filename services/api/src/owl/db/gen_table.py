import asyncio
import contextlib
import re
from asyncio import Semaphore
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from inspect import iscoroutinefunction
from pathlib import Path
from time import perf_counter
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    BinaryIO,
    Callable,
    ClassVar,
    Literal,
    Self,
    Type,
    override,
)
from uuid import UUID

import asyncpg
import bm25s
import nltk
import numpy as np
import orjson
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from asyncpg import Connection, Pool
from asyncpg.exceptions import (
    DataError,
    DuplicateColumnError,
    DuplicateTableError,
    InvalidParameterValueError,
    PostgresSyntaxError,
    UndefinedColumnError,
    UndefinedFunctionError,
    UndefinedTableError,
    UniqueViolationError,
)
from loguru import logger
from numpy import array, ndarray
from pgvector.asyncpg import register_vector
from pydantic import (
    BaseModel,
    Field,
    GetCoreSchemaHandler,
    ValidationError,
    create_model,
    field_validator,
    model_validator,
)
from pydantic_core import core_schema

from owl.configs import CACHE, ENV_CONFIG
from owl.db import async_session
from owl.db.models.oss import ModelConfig, Project
from owl.types import (
    GEN_CONFIG_VAR_PATTERN,
    ChatThreadEntry,
    ChatThreadResponse,
    CodeGenConfig,
    ColName,
    ColumnDtype,
    ColumnSchema,
    CSVDelimiter,
    DatetimeUTC,
    DiscriminatedGenConfig,
    EmbedGenConfig,
    LLMGenConfig,
    ModelCapability,
    ModelConfig_,
    ModelConfigRead,
    Page,
    PositiveInt,
    ProgressState,
    Project_,
    PythonGenConfig,
    S3Content,
    SanitisedNonEmptyStr,
    SanitisedStr,
    TableImportProgress,
    TableMeta,
    TableMetaResponse,
    TableName,
    TableType,
    TextContent,
)
from owl.utils import merge_dict, uuid7_draft2_str, validate_where_expr
from owl.utils.crypt import hash_string_blake2b as blake2b_hash
from owl.utils.dates import now, utc_datetime_from_iso
from owl.utils.exceptions import (
    BadInputError,
    JamaiException,
    ModelCapabilityError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from owl.utils.io import (
    df_to_csv,
    guess_mime,
    json_dumps,
    json_loads,
    open_uri_async,
    s3_upload,
)
from owl.version import __version__ as owl_version

# Regex for tokenization
digits = r"([0-9]+)"
letters = r"([a-zA-Z]+)"
hanzi = r"([\u4e00-\u9fff])"
# Other non-whitespace, non-letter, non-digit, non-hanzi characters
other = r"([^\s0-9a-zA-Z\u4e00-\u9fff])"
# Combine patterns with OR (|)
TOKEN_PATTERN = re.compile(f"{digits}|{letters}|{hanzi}|{other}")
stemmer = nltk.stem.SnowballStemmer("english")


"""
Postgres has limitation for identifier length at 63 characters.

We need to support up to 100.

But we cannot set the limit at 63 since Postgres will add suffix like `_id_pkey` ("ID" column as primary key).

Solution is to use a mapping from `id` (len <= 46) to `table_id` (len <= 100).

Consumers of a table will use `table_id`, `id` is for internal use.

1. `len(table_id) <= 100`:
   - `id` will be a truncated version of `table_id`:
     1. If `len(table_id) <= 29`: `id = table_id`
     2. If `len(table_id) > 29`: `id = f"{table_id[:29]}-{blake2b_hash(table_id, 16)}"` where the hash is 16 characters.
   - During table duplication with auto-naming:
     1. `len(table_id) <= 70`: Suffix will be appended `{table_id} 2025-10-06-22-03-18 (9999)`
     2. `len(table_id) > 70`: `table_id` will be truncated as `f"{table_id[:53]}-{blake2b_hash(table_id, 16)}"` before appending suffix
     3. In both cases, `id` will be a truncated version of `table_id` as usual
2. `len(table_id) > 100`:
   - Raise validation error

Column ID works the same way with a mapping from `id` (len <= 46) to `column_id` (len <= 100), but care has to be taken for state column IDs.

Index naming:

1. FTS index: `f"{table_id[:25]}_{blake2b_hash(table_id, 24)}_fts_idx"`
2. Vector index: `f"{short_table_id[:25]}_{blake2b_hash(f"{short_table_id}_{short_column_id}", 24)}_vec_idx"`
"""


TABLE_ID_DST_MAX_ITER = 9_999
IMPORT_BATCH_SIZE = 100
S3_MAX_CONCURRENCY = 20


def get_internal_id(long_id: str) -> str:
    is_file_col = long_id.endswith("__")
    is_state_col = long_id.endswith("_")
    if is_file_col:
        long_id = long_id[:-2]
    elif is_state_col:
        long_id = long_id[:-1]
    else:
        pass
    if len(long_id) <= 29:
        short_id = long_id
    else:
        short_id = f"{long_id[:29]}-{blake2b_hash(long_id, 16)}"
    if is_file_col:
        short_id = f"{short_id}__"
    elif is_state_col:
        short_id = f"{short_id}_"
    else:
        pass
    return short_id


def truncate_table_id(table_id: str) -> str:
    if len(table_id) <= 70:
        return table_id
    return f"{table_id[:53]}-{blake2b_hash(table_id, 16)}"


def fts_index_id(table_id: str) -> str:
    return f"{table_id[:25]}_{blake2b_hash(table_id, 24)}_fts_idx"


def vector_index_id(table_id: str, col_id: str) -> str:
    return f"{table_id[:25]}_{blake2b_hash(f'{table_id}_{col_id}', 24)}_vec_idx"


class NumpyArray:
    """Wrapper class for numpy arrays with Pydantic schema support"""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.union_schema(
                [
                    core_schema.is_instance_schema(ndarray),
                    core_schema.list_schema(core_schema.float_schema()),
                ]
            ),
        )

    @staticmethod
    def validate(value: Any) -> ndarray:
        if isinstance(value, list):
            # Convert list of floats to a NumPy array
            return array(value, dtype=float)
        elif isinstance(value, ndarray):
            return value
        else:
            raise ValueError("Value must be a numpy array or a list of floats")


class _TableBase(BaseModel):
    version: str = Field(
        default=owl_version,
        description="Table version, following owl version.",
    )
    meta: dict[str, Any] = Field(
        default={},
        description="Additional metadata about the table.",
    )


class TableMetadata(_TableBase):
    """
    Table metadata
        - Primary key: table_id
        - Data table name: table_id
    * Remember to update the SQL when making changes to this model
    """

    table_id: TableName = Field(
        description="Table name.",
    )
    short_id: SanitisedNonEmptyStr = Field(
        "",
        description="Internal short table ID derived from `table_id`.",
    )
    title: SanitisedStr = Field(
        "",
        description='Chat title. Defaults to "".',
    )
    parent_id: TableName | None = Field(
        None,
        description="The parent table ID. If None (default), it means this is a parent table.",
    )
    created_by: SanitisedNonEmptyStr | None = Field(
        None,
        description="ID of the user that created this table. Defaults to None.",
    )
    updated_at: DatetimeUTC = Field(
        default_factory=now,
        description="Table last update datetime (UTC).",
    )

    @model_validator(mode="after")
    def generate_internal_id(self) -> Self:
        if not self.short_id:
            self.short_id = get_internal_id(self.table_id)
        return self

    @staticmethod
    def sql_create(schema_id: str) -> str:
        return f"""
            CREATE TABLE IF NOT EXISTS "{schema_id}"."TableMetadata" (
                table_id TEXT PRIMARY KEY,
                short_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                parent_id TEXT,
                created_by TEXT,
                updated_at TIMESTAMPTZ NOT NULL,
                version TEXT NOT NULL,
                meta JSONB NOT NULL
            );
        """

    @classmethod
    @lru_cache(maxsize=1)
    def str_cols(cls) -> list[str]:
        """Return every column name that is a string."""
        return [k for k, v in cls.model_fields.items() if v.annotation is str]


class ColumnMetadata(_TableBase):
    """
    Column metadata
        - Primary key: table_id, column_id
        - Foreign key: table_id
    * Remember to update the SQL when making changes to this model
    """

    INFO_COLUMNS: ClassVar[set[str]] = {"id", "updated at"}

    table_id: TableName = Field(
        description="Associated Table name.",
    )
    column_id: str = Field(
        pattern=r"^[A-Za-z0-9]([A-Za-z0-9.?!@#$%^&*_()\- ]*[A-Za-z0-9.?!()\-])?_*$",
        min_length=1,
        max_length=101,
        description="Column name.",
    )
    short_table_id: SanitisedNonEmptyStr = Field(
        "",
        description="Internal short table ID derived from `table_id`.",
    )
    short_id: SanitisedNonEmptyStr = Field(
        "",
        description="Internal short column ID derived from `column_id`.",
    )
    dtype: ColumnDtype = Field(
        ColumnDtype.STR,
        description=f"Column data type, one of {list(map(str, ColumnDtype))}.",
    )
    vlen: PositiveInt = Field(
        0,
        description=(
            "_Optional_. vector length. If provided, then this column will be a VECTOR column type."
            "ex: embedding size."
        ),
        examples=[1024],
    )
    gen_config: DiscriminatedGenConfig | None = Field(
        None,
        description=(
            '_Optional_. Generation config. If provided, then this column will be an "Output Column". '
            "Table columns on its left can be referenced by `${column-name}`."
        ),
    )
    column_order: int = Field(
        0,
        description="Order of the column in the table. Usually you don't need to set this.",
        examples=[0, 1],
    )

    @model_validator(mode="after")
    def generate_internal_id(self) -> Self:
        if not self.short_table_id:
            self.short_table_id = get_internal_id(self.table_id)
        if not self.short_id:
            self.short_id = get_internal_id(self.column_id)
        return self

    @field_validator("dtype", mode="before")
    @classmethod
    def validate_dtype(cls, value: Any) -> str:
        """
        Handles some special cases for dtype.
        """
        if value in ["float32", "float16"]:
            return ColumnDtype.FLOAT
        if value == "int8":
            return ColumnDtype.INT
        return value

    @property
    def is_output_column(self) -> bool:
        return self.gen_config is not None

    @property
    def is_text_column(self) -> bool:
        return self.dtype == ColumnDtype.STR and self.column_id.lower() not in self.INFO_COLUMNS

    @property
    def is_chat_column(self) -> bool:
        return getattr(self.gen_config, "multi_turn", False)

    @property
    def is_vector_column(self) -> bool:
        return self.dtype in (ColumnDtype.FLOAT,) and self.vlen > 0

    @property
    def is_image_column(self) -> bool:
        return self.dtype == ColumnDtype.IMAGE

    @property
    def is_audio_column(self) -> bool:
        return self.dtype == ColumnDtype.AUDIO

    @property
    def is_document_column(self) -> bool:
        return self.dtype == ColumnDtype.DOCUMENT

    @property
    def is_file_column(self) -> bool:
        return self.dtype in (ColumnDtype.IMAGE, ColumnDtype.AUDIO, ColumnDtype.DOCUMENT)

    @property
    def is_info_column(self) -> bool:
        return self.column_id.lower() in self.INFO_COLUMNS

    @property
    def is_state_column(self) -> bool:
        return self.column_id.endswith("_")

    @staticmethod
    def sql_create(schema_id: str) -> str:
        return f"""
            CREATE TABLE IF NOT EXISTS "{schema_id}"."ColumnMetadata" (
                table_id TEXT NOT NULL,
                column_id TEXT NOT NULL,
                short_table_id TEXT NOT NULL,
                short_id TEXT NOT NULL,
                dtype TEXT NOT NULL,
                vlen INT DEFAULT 0 NOT NULL,
                gen_config JSONB,
                column_order INT NOT NULL,
                version TEXT,
                meta JSONB NOT NULL,
                PRIMARY KEY (table_id, column_id),
                UNIQUE (short_table_id, short_id),
                CONSTRAINT "fk_ColumnMetadataTable_table_id"
                    FOREIGN KEY (table_id)
                    REFERENCES "{schema_id}"."TableMetadata" (table_id)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE,
                CONSTRAINT "fk_ColumnMetadataTable_short_id"
                    FOREIGN KEY (short_table_id)
                    REFERENCES "{schema_id}"."TableMetadata" (short_id)
                    ON UPDATE CASCADE
            );
        """


class DataTableRow(BaseModel, coerce_numbers_to_str=True):
    @classmethod
    def get_column_ids(
        cls,
        *,
        exclude_info: bool = False,
        exclude_state: bool = False,
    ) -> list[str]:
        columns = list(cls.model_fields.keys())
        if exclude_info:
            columns = [c for c in columns if c.lower() not in ("id", "updated at")]
        if exclude_state:
            columns = [c for c in columns if not c.endswith("_")]
        return columns


class DBengine:
    _instance = None
    _conn_pool: Pool = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_conn_pool(self) -> Pool:
        """Get or create a PostgreSQL connection pool with proper configuration."""
        if self._conn_pool is None:
            self._conn_pool = await asyncpg.create_pool(
                dsn=re.sub(r"\+\w+", "", ENV_CONFIG.db_path),
                min_size=2,
                max_size=5,
                max_inactive_connection_lifetime=300.0,
                timeout=30.0,
                command_timeout=60.0,
                max_queries=1000,
                # Do not cache statement plan since Generative Table's schema can change
                statement_cache_size=0,
                init=self._setup_connection,
            )
            self._initialized = True
        return self._conn_pool

    async def close(self):
        """Close the connection pool."""
        if self._conn_pool and not self._conn_pool._closed:
            await self._conn_pool.close()
            self._conn_pool = None
            self._initialized = False

    async def _setup_connection(self, conn: Connection) -> None:
        """Configure a new connection with required settings."""
        # Remember to update the InitApplicationSQL in the yaml for extension creation
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pgroonga;")
        # If `transaction_timeout` <= `idle_in_transaction_session_timeout` or `statement_timeout`
        # then the longer timeout is ignored.
        await conn.execute("SET statement_timeout = 20000")
        await conn.execute("SET transaction_timeout = 20000")
        await conn.execute("SET idle_in_transaction_session_timeout = 20000")
        await register_vector(conn)
        await conn.set_type_codec(
            "jsonb",
            encoder=lambda obj: orjson.dumps(obj).decode("utf-8"),
            decoder=orjson.loads,
            schema="pg_catalog",
        )

    @contextlib.asynccontextmanager
    async def transaction(self, schema_id: str = None) -> AsyncIterator[Connection]:
        """Provide a transactional scope for a series of operations."""
        async with (await self.get_conn_pool()).acquire() as conn:
            async with conn.transaction():
                try:
                    if schema_id:
                        await conn.execute(f'SET search_path TO "{schema_id}"')
                    yield conn
                except JamaiException:
                    # No need to log these errors
                    raise
                except Exception as e:
                    logger.error(f"Transaction failed: {e}")
                    raise


GENTABLE_ENGINE = DBengine()


class GenerativeTableCore:
    """
    Core class for managing generative tables in PostgreSQL with schema-based organization.
    Devs should use `GenerativeTable` instead.
    """

    INFO_COLUMNS = {"id", "updated at"}
    FIXED_COLUMN_IDS = ["ID", "Updated at"]

    def __init__(
        self,
        *,
        # TODO: We should directly pass in `Project_` instead of fetching it again
        project_id: str,
        table_type: TableType,
        table_metadata: TableMetadata,
        column_metadata_list: list[ColumnMetadata],
        num_rows: int = -1,
        request_id: str = "",
    ) -> None:
        self.project_id = project_id
        self.table_type = table_type
        self.table_metadata = table_metadata
        self.column_metadata = column_metadata_list
        self.num_rows = num_rows
        self.request_id = request_id
        self.schema_id = f"{project_id}_{table_type}"
        self.data_table_model = self._create_data_table_row_model(
            table_metadata.table_id, column_metadata_list
        )
        self.text_column_names = [
            col.column_id for col in self.column_metadata if col.is_text_column
        ]
        self.vector_column_names = [
            col.column_id for col in self.column_metadata if col.is_vector_column
        ]
        self.map_to_short_col_id = {c.column_id: c.short_id for c in column_metadata_list}
        self.map_to_long_col_id = {c.short_id: c.column_id for c in column_metadata_list}

    @property
    def table_id(self) -> str:
        return self.table_metadata.table_id

    @table_id.setter
    def table_id(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("`table_id` must be a string.")
        short_id = get_internal_id(value)
        self.table_metadata.table_id = value
        self.table_metadata.short_id = short_id
        for col in self.column_metadata:
            col.table_id = value
            col.short_table_id = short_id

    @property
    def short_table_id(self) -> str:
        return self.table_metadata.short_id

    @property
    def v1_meta(self) -> TableMeta:
        meta = TableMeta(
            id=self.table_id,
            version=self.table_metadata.version,
            meta=self.table_metadata.meta,
            cols=[
                ColumnSchema(
                    id=col.column_id,
                    dtype=col.dtype,
                    vlen=col.vlen,
                    gen_config=col.gen_config,
                )
                for col in self.column_metadata
            ],
            parent_id=self.table_metadata.parent_id,
            created_by=self.table_metadata.created_by,
            title=self.table_metadata.title,
            updated_at=self.table_metadata.updated_at,
            num_rows=self.num_rows,
        )
        return meta

    @property
    def v1_meta_response(self) -> TableMetaResponse:
        meta = TableMetaResponse(
            id=self.table_id,
            version=self.table_metadata.version,
            meta=self.table_metadata.meta,
            cols=[
                ColumnSchema(
                    id=col.column_id,
                    dtype=col.dtype,
                    vlen=col.vlen,
                    gen_config=col.gen_config,
                )
                for col in self.column_metadata
            ],
            parent_id=self.table_metadata.parent_id,
            created_by=self.table_metadata.created_by,
            title=self.table_metadata.title,
            updated_at=self.table_metadata.updated_at,
            num_rows=self.num_rows,
        )
        return meta

    def _log(self, msg: str, level: str = "INFO"):
        _log = f"{self.__class__.__name__}: {msg}"
        if self.request_id:
            _log = f"{self.request_id} - {_log}"
        logger.log(level, _log)

    @staticmethod
    async def _fetch_project(project_id: str) -> Project_:
        async with async_session() as session:
            project = await Project.get(session, project_id)
        return Project_.model_validate(project)

    @staticmethod
    async def _fetch_model(model: str, organization_id: str) -> ModelConfigRead:
        async with async_session() as session:
            cfg = await ModelConfig.get(session, model)
        cfg = ModelConfigRead.model_validate(cfg)
        if (not cfg.is_active) or (not cfg.allowed(organization_id)):
            raise ResourceNotFoundError(f'Model "{model}" is not found.')
        return cfg

    @staticmethod
    async def _fetch_model_with_capabilities(
        *,
        capabilities: list[ModelCapability],
        organization_id: str,
    ) -> ModelConfig_:
        from owl.utils.lm import LMEngine

        async with async_session() as session:
            models = (
                await ModelConfig.list_(
                    session=session,
                    return_type=ModelConfig_,
                    organization_id=organization_id,
                    capabilities=capabilities,
                    exclude_inactive=True,
                )
            ).items
        if len(models) == 0:
            raise ModelCapabilityError(
                f"No model found with capabilities: {list(map(str, capabilities))}"
            )
        model = LMEngine.pick_best_model(models, capabilities)
        return model

    @classmethod
    async def _check_columns(
        cls,
        conn: Connection,
        *,
        project_id: str,
        table_type: TableType,
        table_metadata: TableMetadata,
        column_metadata_list: list[ColumnMetadata],
        set_default_prompts: bool,
        replace_unavailable_models: bool,
        allow_nonexistent_refs: bool = False,
    ) -> list[ColumnMetadata]:
        del table_type  # Not used for now
        table_id = table_metadata.table_id
        if len(set(c.column_id.lower() for c in column_metadata_list)) != len(
            column_metadata_list
        ):
            raise BadInputError(
                f'Table "{table_id}": There are repeated column names (case-insensitive).'
            )
        project = await cls._fetch_project(project_id)
        column_map = {c.column_id: c for c in column_metadata_list}
        for i, col in enumerate(column_metadata_list):
            gen_config = col.gen_config
            if gen_config is None:
                continue
            available_cols = [
                c
                for c in column_metadata_list[:i]
                if not (c.is_info_column or c.is_state_column or c.is_vector_column)
            ]
            valid_col_ids = [c.column_id for c in available_cols]
            if isinstance(gen_config, EmbedGenConfig):
                if not col.is_vector_column:
                    raise BadInputError(
                        f'Table "{table_id}": '
                        f'Embedding column "{col.column_id}" must be a vector column with float data type.'
                    )
                if (not allow_nonexistent_refs) and (
                    gen_config.source_column not in valid_col_ids
                ):
                    raise BadInputError(
                        (
                            f'Table "{table_id}": '
                            f'Embedding config of column "{col.column_id}" referenced '
                            f'an invalid source column "{gen_config.source_column}". '
                            "Make sure you only reference non-vector columns on its left. "
                            f"Available columns: {valid_col_ids}."
                        )
                    )
                # Validate and assign default model
                embedding_model = gen_config.embedding_model.strip()
                if embedding_model:
                    # Validate model capabilities
                    try:
                        model = await cls._fetch_model(embedding_model, project.organization_id)
                        if ModelCapability.EMBED not in model.capabilities:
                            raise ModelCapabilityError(
                                (
                                    f'Table "{table_id}": Model "{model.id}" used in Embedding column "{col.column_id}" '
                                    f"does not support embedding."
                                )
                            )
                    except ModelCapabilityError:
                        # Embedding model is not interchangeable
                        raise
                    except ResourceNotFoundError as e:
                        # Embedding model is not interchangeable
                        raise BadInputError(
                            f'Table "{table_id}": '
                            f'Embedding model "{embedding_model}" used by column "{col.column_id}" is not found.'
                        ) from e
                # Do not use `elif` here
                if not embedding_model:
                    # Assign default model
                    try:
                        model = await cls._fetch_model_with_capabilities(
                            capabilities=[ModelCapability.EMBED],
                            organization_id=project.organization_id,
                        )
                    except ModelCapabilityError as e:
                        raise ModelCapabilityError(f'Table "{table_id}": {e}') from e
                    gen_config.embedding_model = model.id
            elif isinstance(gen_config, LLMGenConfig):
                if col.is_vector_column:
                    raise BadInputError(
                        f'Table "{table_id}": '
                        f'LLM column "{col.column_id}" must not be a vector column.'
                    )
                if not col.is_text_column:
                    raise BadInputError(
                        f'Table "{table_id}": '
                        f'LLM column "{col.column_id}" must be a string (text) column.'
                    )
                # Insert default prompts if needed
                if set_default_prompts:
                    # We only put input columns into default prompt
                    _input_cols = [c for c in available_cols if c.gen_config is None]
                    _text_cols = "\n\n".join(
                        f"{c.column_id}: ${{{c.column_id}}}"
                        for c in _input_cols
                        if not (c.is_image_column or c.is_audio_column)
                    )
                    _image_audio_cols = " ".join(
                        f"${{{c.column_id}}}"
                        for c in _input_cols
                        if (c.is_image_column or c.is_audio_column)
                    )
                    # We place image and audio columns first, which will then be replaced with "" and stripped out
                    if gen_config.multi_turn:
                        default_system_prompt = (
                            f'You are an agent named "{table_id}". Be helpful. '
                            "Ensure that your reply is easy to understand and is accessible to all users. "
                            "Provide answers based on the information given. "
                            "Be factual and do not hallucinate."
                        ).strip()
                        default_user_prompt = f"{_image_audio_cols}\n\n{_text_cols}".strip()
                    else:
                        default_system_prompt = (
                            "You are a versatile data generator. "
                            "Your task is to process information from input data and generate appropriate responses "
                            "based on the specified column name and input data. "
                            "Adapt your output format and content according to the column name provided."
                        ).strip()
                        if _text_cols:
                            _text_cols = f"{_text_cols}\n\n"
                        default_user_prompt = (
                            f"{_image_audio_cols}\n\n"
                            f'Table name: "{table_id}"\n\n'
                            f"{_text_cols}"
                            "Based on the available information, "
                            f'provide an appropriate response for the column "{col.column_id}".\n'
                            "Be factual and do not hallucinate. "
                            "Remember to act as a cell in a spreadsheet and provide concise, "
                            "relevant information without explanations unless specifically requested."
                        ).strip()
                    if not gen_config.system_prompt:
                        gen_config.system_prompt = default_system_prompt
                    if not gen_config.prompt:
                        gen_config.prompt = default_user_prompt
                # Check references
                ref_cols = re.findall(GEN_CONFIG_VAR_PATTERN, gen_config.prompt)
                if allow_nonexistent_refs:
                    ref_cols = [c for c in ref_cols if c in column_map]
                if len(invalid_cols := [c for c in ref_cols if c not in valid_col_ids]) > 0:
                    raise BadInputError(
                        (
                            f'Table "{table_id}": '
                            f'LLM Generation prompt of column "{col.column_id}" referenced '
                            f"invalid source columns: {invalid_cols}. "
                            "Make sure you only reference non-vector columns on its left. "
                            f"Available columns: {valid_col_ids}."
                        )
                    )
                # Validate and assign default model
                ref_image_cols = [c for c in ref_cols if column_map[c].is_image_column]
                ref_audio_cols = [c for c in ref_cols if column_map[c].is_audio_column]
                capabilities = [ModelCapability.CHAT]
                if len(ref_image_cols) > 0:
                    capabilities.append(ModelCapability.IMAGE)
                if len(ref_audio_cols) > 0:
                    capabilities.append(ModelCapability.AUDIO)
                chat_model = gen_config.model.strip()
                if chat_model:
                    # Validate model capabilities
                    try:
                        model = await cls._fetch_model(gen_config.model, project.organization_id)
                        unsupported = list(set(capabilities) - set(model.capabilities))
                        if len(unsupported) > 0:
                            raise ModelCapabilityError(
                                (
                                    f'Table "{table_id}": Model "{model.id}" used in LLM column "{col.column_id}" '
                                    f"lack these capabilities: {', '.join(unsupported)}."
                                )
                            )
                    except ModelCapabilityError:
                        if replace_unavailable_models:
                            # We replace the unavailable model with a default model below
                            chat_model = ""
                        else:
                            raise
                    except ResourceNotFoundError as e:
                        if replace_unavailable_models:
                            # We replace the unavailable model with a default model below
                            chat_model = ""
                        else:
                            raise BadInputError(
                                f'Table "{table_id}": '
                                f'LLM model "{gen_config.model}" used by column "{col.column_id}" is not found.'
                            ) from e
                # Do not use `elif` here
                if not chat_model:
                    # Assign default model
                    try:
                        model = await cls._fetch_model_with_capabilities(
                            capabilities=capabilities,
                            organization_id=project.organization_id,
                        )
                    except ModelCapabilityError as e:
                        raise ModelCapabilityError(f'Table "{table_id}": {e}') from e
                    gen_config.model = model.id
                # Check RAG params
                if gen_config.rag_params is not None:
                    kt_id = gen_config.rag_params.table_id
                    if not allow_nonexistent_refs:
                        if kt_id.strip() == "":
                            raise BadInputError(
                                (
                                    f'Table "{table_id}": Column "{col.column_id}" '
                                    f"referenced a Knowledge Table with an empty ID."
                                )
                            )
                        kt_metadata = await conn.fetchrow(
                            f'SELECT * FROM "{project_id}_knowledge"."TableMetadata" WHERE table_id = $1',
                            kt_id,
                        )
                        if kt_metadata is None:
                            raise BadInputError(
                                (
                                    f'Table "{table_id}": Column "{col.column_id}" '
                                    f'referenced a Knowledge Table "{kt_id}" that does not exist.'
                                )
                            )
                    # Validate and assign default Reranking Model
                    reranking_model = gen_config.rag_params.reranking_model
                    if reranking_model is not None:
                        reranking_model = reranking_model.strip()
                        if reranking_model:
                            # Validate model capabilities
                            try:
                                model = await cls._fetch_model(
                                    reranking_model, project.organization_id
                                )
                                if ModelCapability.RERANK not in model.capabilities:
                                    raise ModelCapabilityError(
                                        (
                                            f'Table "{table_id}": Model "{reranking_model}" '
                                            f'used in LLM column "{col.column_id}" '
                                            f"does not support reranking."
                                        )
                                    )
                            except ModelCapabilityError:
                                if replace_unavailable_models:
                                    # We replace the unavailable model with a default model below
                                    reranking_model = ""
                                else:
                                    raise
                            except ResourceNotFoundError as e:
                                if replace_unavailable_models:
                                    # We replace the unavailable model with a default model below
                                    reranking_model = ""
                                else:
                                    raise BadInputError(
                                        f'Table "{table_id}": '
                                        f'Reranking model "{gen_config.model}" used by column "{col.column_id}" is not found.'
                                    ) from e
                        # Do not use `elif` here
                        if not reranking_model:
                            model = await cls._fetch_model_with_capabilities(
                                capabilities=[str(ModelCapability.RERANK)],
                                organization_id=project.organization_id,
                            )
                            gen_config.rag_params.reranking_model = model.id
            elif isinstance(gen_config, CodeGenConfig):
                if col.is_vector_column:
                    raise BadInputError(
                        f'Table "{table_id}": '
                        f'Code Execution column "{col.column_id}" must not be a vector column.'
                    )
                if col.dtype not in (ColumnDtype.STR, ColumnDtype.IMAGE, ColumnDtype.AUDIO):
                    raise BadInputError(
                        f'Table "{table_id}": '
                        f'Code Execution column "{col.column_id}" must be a string (text) or image column or audio column.'
                    )
                valid_col_ids = [c.column_id for c in available_cols if c.dtype == ColumnDtype.STR]
                if (not allow_nonexistent_refs) and (
                    gen_config.source_column not in valid_col_ids
                ):
                    raise BadInputError(
                        (
                            f'Table "{table_id}": '
                            f'Code Execution config of column "{col.column_id}" referenced '
                            f'an invalid source column "{gen_config.source_column}". '
                            "Make sure you only reference string (text) columns on its left. "
                            f"Available columns: {valid_col_ids}."
                        )
                    )
            elif isinstance(gen_config, PythonGenConfig):
                if col.is_vector_column:
                    raise BadInputError(
                        f'Table "{table_id}": '
                        f'Python Function column "{col.column_id}" must not be a vector column.'
                    )
                if col.dtype not in (ColumnDtype.STR, ColumnDtype.IMAGE, ColumnDtype.AUDIO):
                    raise BadInputError(
                        f'Table "{table_id}": '
                        f'Python Function column "{col.column_id}" must be a string (text) or image column or audio column.'
                    )

        return column_metadata_list

    @classmethod
    async def _create_table(
        cls,
        *,
        project_id: str,
        table_type: TableType,
        table_metadata: TableMetadata,
        column_metadata_list: list[ColumnMetadata],
        request_id: str = "",
        set_default_prompts: bool = True,
        replace_unavailable_models: bool = False,
        allow_nonexistent_refs: bool = False,
        create_indexes: bool = True,
    ) -> Self:
        """
        Create a new table.
        This method is created so that the public method `create_table` can be overridden
        without affecting table creation logic.

        Args:
            project_id (str): Project ID.
            table_type (str): Table type.
            table_metadata (TableMetadata): Table metadata.
            column_metadata_list (list[ColumnMetadata]): List of column metadata.
            request_id (str, optional): Request ID for logging. Defaults to "".
            set_default_prompts (bool, optional): Set default prompts.
                Useful when importing table which does not need to set prompts. Defaults to True.
            replace_unavailable_models (bool, optional): Replace unavailable models with default models.
                Useful when importing old tables. Defaults to False.
            allow_nonexistent_refs (bool, optional): Ignore non-existent column and Knowledge Table references.
                Otherwise will raise an error. Useful when importing old tables and performing maintenance.
                Defaults to False.
            create_indexes (bool, optional): Create indexes for the table.
                Setting to False can be useful when importing tables
                where you want to create indexes after all rows are added.
                Defaults to True.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        schema_id = f"{project_id}_{table_type}"

        ### --- VALIDATIONS --- ###
        # Override info and state columns
        column_metadata_list = [
            col for col in column_metadata_list if not (col.is_info_column or col.is_state_column)
        ]
        state_columns = [
            ColumnMetadata(
                table_id=table_metadata.table_id,
                column_id=f"{col.column_id}_",
                dtype=ColumnDtype.JSON,
            )
            for col in column_metadata_list
        ]
        info_columns = [
            ColumnMetadata(
                table_id=table_metadata.table_id,
                column_id="ID",
                dtype=ColumnDtype.STR,
            ),
            ColumnMetadata(
                table_id=table_metadata.table_id,
                column_id="Updated at",
                dtype=ColumnDtype.DATE_TIME,
            ),
        ]
        column_metadata_list = info_columns + column_metadata_list + state_columns

        ### --- Create metadata tables --- ###
        await cls.create_schemas(project_id)
        async with GENTABLE_ENGINE.transaction() as conn:
            # Validate column metadata
            await cls._check_columns(
                conn=conn,
                project_id=project_id,
                table_type=table_type,
                table_metadata=table_metadata,
                column_metadata_list=column_metadata_list,
                set_default_prompts=set_default_prompts,
                replace_unavailable_models=replace_unavailable_models,
                allow_nonexistent_refs=allow_nonexistent_refs,
            )
            # Override column order
            for i, col_meta in enumerate(column_metadata_list):
                col_meta.column_order = i
            ### --- Create data table --- ###
            # Create the data table
            await cls._create_data_table(
                conn=conn,
                schema_id=schema_id,
                table_metadata=table_metadata,
                column_metadata_list=column_metadata_list,
                create_indexes=create_indexes,
            )
            # Create metadata entries
            await cls._upsert_table_metadata(conn, schema_id, table_metadata)
            for col_metadata in column_metadata_list:
                await cls._upsert_column_metadata(conn, schema_id, col_metadata)
        # Reload table
        async with GENTABLE_ENGINE.transaction() as conn:
            return await cls._open_table(
                conn=conn,
                project_id=project_id,
                table_type=table_type,
                table_id=table_metadata.table_id,
                request_id=request_id,
            )

    async def _count_rows(self, conn: Connection) -> int:
        """
        Count the number of rows.

        Args:
            conn (Connection): PostgreSQL connection.

        Returns:
            num_rows (int): Number of rows in the table.
        """
        # If we don't need a 100% exact count and a very fast, rough estimate is good enough
        # SELECT reltuples::bigint AS estimate FROM pg_class WHERE relname = 'your_table';
        try:
            self.num_rows = await conn.fetchval(
                f'SELECT COUNT("ID") FROM "{self.schema_id}"."{self.short_table_id}"'
            )
        except (UndefinedTableError, UndefinedColumnError) as e:
            logger.error(
                (
                    f'Data table `"{self.schema_id}"."{self.short_table_id}"` '
                    "is not found but table and column metadata exist !!! "
                    f"Error: {repr(e)}"
                )
            )
            raise ResourceNotFoundError(
                f'Table "{self.table_id}" is not found. Please contact support if this is unexpected.'
            ) from e
        # await conn.fetch("SET LOCAL enable_seqscan = off;")
        return self.num_rows

    @classmethod
    async def _open_table(
        cls,
        conn: Connection,
        *,
        project_id: str,
        table_type: TableType,
        table_id: str,
        request_id: str = "",
    ) -> Self:
        """
        Open an existing table.

        Args:
            conn (Connection): PostgreSQL connection.
            project_id (str): Project ID.
            table_type (str): Table type.
            table_id (str): Name of the table.
            request_id (str, optional): Request ID for logging. Defaults to "".

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        schema_id = f"{project_id}_{table_type}"

        ### --- Read table and column metadata --- ###
        try:
            table_metadata = await conn.fetchrow(
                f'SELECT * FROM "{schema_id}"."TableMetadata" WHERE table_id = $1', table_id
            )
        except UndefinedTableError as e:
            raise ResourceNotFoundError(f'Table "{table_id}" is not found.') from e
        except Exception as e:
            raise BadInputError(e) from e
        if table_metadata is None:
            raise ResourceNotFoundError(f'Table metadata for "{table_id}" is not found.')
        try:
            column_metadata = await conn.fetch(
                f'SELECT * FROM "{schema_id}"."ColumnMetadata" WHERE table_id = $1 ORDER BY column_order ASC',
                table_id,
            )
        except UndefinedTableError as e:
            raise ResourceNotFoundError(f'Table "{table_id}" is not found.') from e
        except Exception as e:
            raise BadInputError(e) from e
        if len(column_metadata) == 0:
            raise ResourceNotFoundError(f'Column metadata for "{table_id}" is not found.')
        self = cls(
            project_id=project_id,
            table_type=table_type,
            table_metadata=TableMetadata.model_validate(dict(table_metadata)),
            column_metadata_list=[
                ColumnMetadata.model_validate(dict(col)) for col in column_metadata
            ],
            request_id=request_id,
        )
        await self._count_rows(conn)
        return self

    async def _reload_table(self, conn: Connection) -> Self:
        self = await self._open_table(
            conn=conn,
            project_id=self.project_id,
            table_type=self.table_type,
            table_id=self.table_id,
            request_id=self.request_id,
        )
        await self._check_columns(
            conn=conn,
            project_id=self.project_id,
            table_type=self.table_type,
            table_metadata=self.table_metadata,
            column_metadata_list=self.column_metadata,
            set_default_prompts=False,
            replace_unavailable_models=False,
        )
        return self

    @staticmethod
    async def _recreate_fts_index(
        conn: Connection,
        *,
        schema_id: str,
        table_id: str,
        columns: list[str],
    ) -> None:
        if len(columns) == 0:
            return
        index_id = fts_index_id(table_id)
        await conn.execute(f'DROP INDEX IF EXISTS "{schema_id}"."{index_id}"')
        await conn.execute(
            f"""
            CREATE INDEX "{index_id}"
            ON "{schema_id}"."{get_internal_id(table_id)}"
            USING pgroonga ((ARRAY[{", ".join(f'"{get_internal_id(col)}"' for col in columns)}]));
            """,
            timeout=300.0,
        )

    @staticmethod
    async def _recreate_vector_index(
        conn: Connection,
        *,
        schema_id: str,
        table_id: str,
        columns: list[str],
    ) -> None:
        if len(columns) == 0:
            return
        # pgvector doesn't support multi-column index, as of: 2025-03-04
        for col in columns:
            index_id = vector_index_id(table_id, col)
            await conn.execute(f'DROP INDEX IF EXISTS "{schema_id}"."{index_id}"')
            await conn.execute(
                f"""
                CREATE INDEX "{index_id}"
                ON "{schema_id}"."{get_internal_id(table_id)}"
                USING diskann ("{get_internal_id(col)}" vector_cosine_ops);
                """,
                timeout=600.0,
            )

    @staticmethod
    def _state_column_sql(short_column_id: str) -> str:
        return f""""{short_column_id}_" JSONB NOT NULL DEFAULT '{{}}'::JSONB"""

    @classmethod
    async def _create_data_table(
        cls,
        conn: Connection,
        *,
        schema_id: str,
        table_metadata: TableMetadata,
        column_metadata_list: list[ColumnMetadata],
        create_indexes: bool = True,
    ) -> None:
        table_id = table_metadata.table_id
        # All data table have "ID" and "Updated at" columns
        column_defs = []
        column_defs.append('"ID" UUID PRIMARY KEY')
        column_defs.append('"Updated at" TIMESTAMPTZ')

        # Generate the SQL column definitions for the CREATE TABLE statement
        text_cols = []
        vec_cols = []
        for col in column_metadata_list:
            if col.is_info_column or col.is_state_column:
                continue
            dtype = col.dtype
            if col.is_vector_column:
                dtype = f"VECTOR({col.vlen})"
                vec_cols.append(col.column_id)
            else:
                dtype = dtype.to_postgres_type()
            if col.is_text_column:
                text_cols.append(col.column_id)
            column_defs.append(f'"{col.short_id}" {dtype}')
            column_defs.append(cls._state_column_sql(col.short_id))
        try:
            # Create the table in the database
            await conn.execute(f"""
            CREATE TABLE "{schema_id}"."{table_metadata.short_id}" (
                {", ".join(column_defs)}
            );
            """)
            if create_indexes:
                await cls._recreate_fts_index(
                    conn,
                    schema_id=schema_id,
                    table_id=table_id,
                    columns=text_cols,
                )
                await cls._recreate_vector_index(
                    conn,
                    schema_id=schema_id,
                    table_id=table_id,
                    columns=vec_cols,
                )
        except DuplicateTableError as e:
            raise ResourceExistsError(f'Table "{table_id}" already exists.') from e

    @staticmethod
    async def _upsert_table_metadata(
        conn: Connection,
        schema_id: str,
        table_metadata: TableMetadata,
    ) -> None:
        query = f"""
        INSERT INTO "{schema_id}"."TableMetadata" (
            table_id, short_id, title, parent_id, created_by, updated_at, version, meta
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (table_id) DO UPDATE SET
            title =  COALESCE(EXCLUDED.title, "TableMetadata".title),
            parent_id = EXCLUDED.parent_id,
            created_by = EXCLUDED.created_by,
            updated_at = COALESCE(EXCLUDED.updated_at, "TableMetadata".updated_at),
            version = COALESCE(EXCLUDED.version, "TableMetadata".version),
            meta = COALESCE(EXCLUDED.meta, "TableMetadata".meta);
        """
        values = [
            table_metadata.table_id,
            table_metadata.short_id,
            table_metadata.title,
            table_metadata.parent_id,
            table_metadata.created_by,
            table_metadata.updated_at,
            table_metadata.version,
            table_metadata.meta,
        ]
        await conn.execute(query, *values)

    @staticmethod
    async def _upsert_column_metadata(
        conn: Connection,
        schema_id: str,
        column_metadata: ColumnMetadata,
    ) -> None:
        query = f"""
        INSERT INTO "{schema_id}"."ColumnMetadata" (
            table_id, column_id, short_table_id, short_id, dtype, vlen, gen_config, column_order, version, meta
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (table_id, column_id) DO UPDATE SET
            dtype = COALESCE(EXCLUDED.dtype, "ColumnMetadata".dtype),
            vlen = COALESCE(EXCLUDED.vlen, "ColumnMetadata".vlen),
            gen_config = EXCLUDED.gen_config,
            column_order = EXCLUDED.column_order,
            version = COALESCE(EXCLUDED.version, "ColumnMetadata".version),
            meta = COALESCE(EXCLUDED.meta, "ColumnMetadata".meta);
        """
        values = [
            column_metadata.table_id,
            column_metadata.column_id,
            column_metadata.short_table_id,
            column_metadata.short_id,
            column_metadata.dtype,
            column_metadata.vlen,
            column_metadata.gen_config.model_dump() if column_metadata.gen_config else None,
            column_metadata.column_order,
            column_metadata.version,
            column_metadata.meta,
        ]
        await conn.execute(query, *values)

    async def _set_updated_at(
        self,
        conn: Connection,
        updated_at: datetime | None = None,
    ) -> None:
        if updated_at is None:
            updated_at = now()
        stmt = f'UPDATE "{self.schema_id}"."TableMetadata" SET "updated_at" = $1 WHERE "table_id" = $2;'
        await conn.execute(stmt, updated_at, self.table_id)
        self.table_metadata.updated_at = updated_at

    @staticmethod
    def _create_data_table_row_model(
        table_id: str,
        columns: list["ColumnMetadata"],
    ) -> Type[DataTableRow]:
        """
        Dynamically creates the Pydantic model class for a data table row.

        Args:
            table_id (str): Table ID.
            columns (list[ColumnMetadata]): List of column metadata.

        Returns:
            model_cls (Type[DataTableRow]): The Pydantic model class.
        """

        @field_validator("ID", mode="before")
        @classmethod
        def id_validator(cls, v: Any):
            if isinstance(v, UUID):
                return str(v)
            return v

        field_definitions = {
            "ID": (
                str,
                Field(default_factory=uuid7_draft2_str, description="Row ID."),
            ),
            "Updated at": (
                DatetimeUTC,
                Field(default_factory=now, description="Last updated timestamp."),
            ),
        }
        validators = {
            "validate_id": id_validator,
        }

        for col in columns:
            if col.is_info_column or col.is_state_column:
                continue
            if col.is_vector_column:
                # Create vector validator
                def create_vector_validator(col: ColumnMetadata):
                    @field_validator(col.column_id, mode="after")
                    @classmethod
                    def vector_validator(cls, v: np.ndarray | None) -> np.ndarray | None:
                        if v is not None and len(v) != col.vlen:
                            raise ValueError(
                                f"Array input for column {col.column_id} must have length {col.vlen}"
                            )
                        return v

                    return vector_validator

                validators[f"validate_{col.column_id}"] = create_vector_validator(col)
                field_definitions[col.column_id] = (NumpyArray | None, Field(default=None))
            else:
                # if col.is_file_column:
                #     # Create URL validator
                #     def create_url_validator(col: ColumnMetadata):
                #         @field_validator(col.column_id, mode="after")
                #         @classmethod
                #         def url_validator(cls, v: str | None) -> str | None:
                #             return validate_url(v) if v else None

                #         return url_validator

                #     validators[f"validate_{col.column_id}"] = create_url_validator(col)
                # Get the Python type from ColumnDtype
                py_type = col.dtype.to_python_type()
                field_definitions[col.column_id] = (py_type | None, Field(default=None))
            # Add state column (ending with '_')
            state_col_id = f"{col.column_id}_"
            field_definitions[state_col_id] = (
                dict[str, Any],
                Field(default={}, description=f"State of {col.column_id} column."),
            )

        return create_model(
            table_id,
            **field_definitions,
            __base__=DataTableRow,
            __validators__=validators,
        )

    @classmethod
    async def create_schemas(cls, project_id: str) -> None:
        """
        Create the project's schemas and metadata tables.
        """
        try:
            async with GENTABLE_ENGINE.transaction() as conn:
                for table_type in TableType:
                    schema_id = f"{project_id}_{table_type}"
                    await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_id}"')
                    await conn.execute(TableMetadata.sql_create(schema_id))
                    await conn.execute(ColumnMetadata.sql_create(schema_id))
        except (UniqueViolationError, DuplicateTableError):
            # Just to be safe, even though catching `UniqueViolationError` is sufficient
            return

    @classmethod
    async def drop_schemas(cls, project_id: str) -> None:
        """
        Drops the project's schemas along with all metadata and data tables.
        """
        async with GENTABLE_ENGINE.transaction() as conn:
            for table_type in TableType:
                schema_id = f"{project_id}_{table_type}"
                await conn.execute(f'DROP SCHEMA IF EXISTS "{schema_id}" CASCADE')

    @classmethod
    async def drop_schema(
        cls,
        *,
        project_id: str,
        table_type: TableType,
    ) -> None:
        """
        Drops the project's schema along with all metadata and data tables.
        """
        schema_id = f"{project_id}_{table_type}"
        async with GENTABLE_ENGINE.transaction() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema_id}" CASCADE')

    ### --- Table CRUD --- ###

    # Table Create Ops
    @classmethod
    async def create_table(
        cls,
        *,
        project_id: str,
        table_type: TableType,
        table_metadata: TableMetadata,
        column_metadata_list: list[ColumnMetadata],
        set_default_prompts: bool = True,
    ) -> Self:
        """
        Create a new table.

        Args:
            project_id (str): Project ID.
            table_type (str): Table type.
            table_metadata (TableMetadata): Table metadata.
            column_metadata_list (list[ColumnMetadata]): List of column metadata.
            set_default_prompts (bool, optional): If True, set default prompts.
                Useful when importing table which does not need to set prompts. Defaults to True.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        return await cls._create_table(
            project_id=project_id,
            table_type=table_type,
            table_metadata=table_metadata,
            column_metadata_list=column_metadata_list,
            set_default_prompts=set_default_prompts,
        )

    @classmethod
    async def duplicate_table(
        cls,
        *,
        project_id: str,
        table_type: TableType,
        table_id_src: str,
        table_id_dst: str | None = None,
        include_data: bool = True,
        create_as_child: bool = False,
        created_by: str | None = None,
        request_id: str = "",
    ) -> Self:
        """
        Duplicate an existing table including schema, data and metadata.

        Args:
            project_id (str): Project ID.
            table_type (str): Table type.
            table_id_src (str): Name of the table to be duplicated.
            table_id_dst (str | None, optional): Name for the new table.
                Defaults to None (automatically find the next available table name).
            include_data (bool, optional): If True, include data. Defaults to True.
            create_as_child (bool, optional): If True, create the new table as a child of the source table.
                Defaults to False.
            created_by (str | None, optional): User ID of the user who created the table.
                Defaults to None.
            request_id (str, optional): Request ID for logging. Defaults to "".

        Raises:
            BadInputError: If `table_id_dst` is not None or a non-empty string.
            ResourceNotFoundError: If table or column metadata cannot be found.

        Returns:
            self (GenerativeTableCore): The duplicated table instance.
        """
        schema_id = f"{project_id}_{table_type}"
        if create_as_child:
            include_data = True
        if isinstance(table_id_dst, str):
            table_id_dst = table_id_dst.strip()
        async with GENTABLE_ENGINE.transaction() as conn:
            try:
                if table_id_dst:
                    try:
                        table_metadata = await conn.fetchrow(
                            f'SELECT * FROM "{schema_id}"."TableMetadata" WHERE table_id = $1',
                            table_id_dst,
                        )
                    except UndefinedTableError as e:
                        # TableMetadata does not exist, meaning this schema is empty
                        raise ResourceNotFoundError(f'Table "{table_id_src}" not found.') from e
                    if table_metadata is not None:
                        raise ResourceExistsError(f'Table "{table_id_dst}" already exists.')
                else:
                    # Might need to truncate table name
                    now_str = now().strftime("%Y-%m-%d-%H-%M-%S")
                    base_name = f"{truncate_table_id(table_id_src)} {now_str}"
                    # Automatically find the next available table name
                    # The function will raise UndefinedTableError if the table does not exist
                    await conn.execute(
                        f"""
                            CREATE OR REPLACE FUNCTION duplicate_table()
                            RETURNS TEXT AS $$
                            DECLARE
                                new_table_name TEXT;
                                suffix INTEGER := 1;
                                max_iterations INTEGER := {TABLE_ID_DST_MAX_ITER};
                            BEGIN
                            -- Loop to find the next available table name
                            WHILE suffix <= max_iterations LOOP
                                new_table_name := format('%s (%s)', '{base_name}', suffix);
                                -- Check if the new table name already exists
                                IF NOT EXISTS (
                                    SELECT 1 FROM "{schema_id}"."TableMetadata"
                                    WHERE table_id = new_table_name
                                ) THEN
                                    RETURN new_table_name; -- Return the new table name
                                END IF;
                                suffix := suffix + 1;
                            END LOOP;
                            -- If we've reached the maximum number of iterations without finding an available name
                            RETURN NULL; -- Return NULL to indicate failure
                            END;
                            $$ LANGUAGE plpgsql;
                    """,
                    )
                    table_id_dst: str | None = await conn.fetchval("SELECT duplicate_table();")
                    if table_id_dst is None:
                        raise ResourceExistsError(
                            f'Could not find a name for table "{table_id_src}" after {TABLE_ID_DST_MAX_ITER:,d} attempts.'
                        )
                # Create the data table
                # Exclude indexes to set our own index name
                short_id_src = get_internal_id(table_id_src)
                short_id_dst = get_internal_id(table_id_dst)
                if include_data:
                    await conn.execute(
                        f'CREATE TABLE "{schema_id}"."{short_id_dst}" AS TABLE "{schema_id}"."{short_id_src}"'
                    )
                else:
                    await conn.execute(
                        (
                            f'CREATE TABLE "{schema_id}"."{short_id_dst}" '
                            f'(LIKE "{schema_id}"."{short_id_src}" INCLUDING ALL EXCLUDING INDEXES)'
                        )
                    )

                # It's required to explicitly add primary key
                await conn.execute(
                    f'ALTER TABLE "{schema_id}"."{short_id_dst}" ADD PRIMARY KEY ("ID")'
                )
                # Copy metadata
                table_meta = await conn.fetchrow(
                    f'SELECT * FROM "{schema_id}"."TableMetadata" WHERE table_id = $1',
                    table_id_src,
                )
                if table_meta is None:
                    raise ResourceNotFoundError(
                        f'Table metadata for "{table_id_src}" is not found.'
                    )
                table_meta = dict(table_meta)
                table_meta["table_id"] = table_id_dst
                table_meta.pop("short_id", None)
                table_meta["created_by"] = created_by
                if create_as_child:
                    table_meta["parent_id"] = table_id_src
                table_meta = TableMetadata.model_validate(table_meta)
                await cls._upsert_table_metadata(conn, schema_id, table_meta)

                # Copy column metadata
                column_metas = await conn.fetch(
                    f'SELECT * FROM "{schema_id}"."ColumnMetadata" WHERE table_id = $1',
                    table_id_src,
                )
                if len(column_metas) == 0:
                    raise ResourceNotFoundError(
                        f'Column metadata for "{table_id_src}" is not found.'
                    )
                column_metas = [ColumnMetadata.model_validate(dict(m)) for m in column_metas]
                for meta in column_metas:
                    meta.table_id = table_meta.table_id
                    meta.short_table_id = table_meta.short_id
                    await cls._upsert_column_metadata(conn, schema_id, meta)

                # Recreate indexes
                text_cols = [col.column_id for col in column_metas if col.is_text_column]
                vector_cols = [col.column_id for col in column_metas if col.is_vector_column]
                await cls._recreate_fts_index(
                    conn, schema_id=schema_id, table_id=table_id_dst, columns=text_cols
                )
                await cls._recreate_vector_index(
                    conn, schema_id=schema_id, table_id=table_id_dst, columns=vector_cols
                )

                return await cls._open_table(
                    conn=conn,
                    project_id=project_id,
                    table_type=table_type,
                    table_id=table_id_dst,
                    request_id=request_id,
                )

            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{table_id_src}" is not found.') from e
            except DuplicateTableError as e:
                raise ResourceExistsError(f'Table "{table_id_dst}" already exists.') from e
            except ValidationError as e:
                raise BadInputError(str(e)) from e

    # Table Create Ops
    @classmethod
    async def open_table(
        cls,
        *,
        project_id: str,
        table_type: TableType,
        table_id: str,
        created_by: str | None = None,
        request_id: str = "",
    ) -> Self:
        """
        Open an existing table.

        Args:
            project_id (str): Project ID.
            table_type (str): Table type.
            table_id (str): Name of the table.
            created_by (str | None, optional): User who created the table.
                If provided, will check if the table was created by the user. Defaults to None (any user).
            request_id (str, optional): Request ID for logging. Defaults to "".

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        async with GENTABLE_ENGINE.transaction() as conn:
            table = await cls._open_table(
                conn=conn,
                project_id=project_id,
                table_type=table_type,
                table_id=table_id,
                request_id=request_id,
            )
            if created_by is not None and table.table_metadata.created_by != created_by:
                raise ResourceNotFoundError(f'Table "{table_id}" not found.')
            return table

    @classmethod
    async def list_tables(
        cls,
        *,
        project_id: str,
        table_type: TableType,
        limit: int | None = 100,
        offset: int = 0,
        order_by: Literal["id", "updated_at"] = "updated_at",
        order_ascending: bool = True,
        created_by: str | None = None,
        parent_id: str | None = None,
        search_query: str = "",
        search_columns: list[str] = None,
        count_rows: bool = False,
    ) -> Page[TableMetaResponse]:
        """
        List tables.

        Args:
            project_id (str): Project ID.
            limit (int | None, optional): Maximum number of tables to return.
                Defaults to 100. Pass None to return all tables.
            offset (int, optional): Offset for pagination. Defaults to 0.
            order_by (Literal["id", "updated_at"], optional): Sort tables by this attribute.
                Defaults to "updated_at".
            order_ascending (bool, optional): Whether to sort by ascending order.
                Defaults to True.
            created_by (str | None, optional): Return tables created by this user.
                Defaults to None (return all tables).
            parent_id (str | None, optional): Parent ID of tables to return.
                Defaults to None (no parent ID filtering).
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
            search_query (str, optional): A string to search for within table names.
                The string is interpreted as both POSIX regular expression and literal string.
                Defaults to "".
            search_columns (list[str], optional): List of columns to search within.
                Defaults to None (search table ID).
            count_rows (bool, optional): Whether to count the rows of the tables.
                Defaults to False.

        Returns:
            tables (Page[TableMetaResponse]): List of tables.
        """
        schema_id = f"{project_id}_{table_type}"
        search_query = search_query.strip()
        filters = []
        params = []
        if search_columns is None:
            search_columns = ["table_id"]
        if created_by:
            params.append(str(created_by))
            filters.append(f"(created_by = ${len(params)})")
        if parent_id:
            if parent_id == "_agent_":
                filters.append("(parent_id IS NULL)")
            elif parent_id == "_chat_":
                filters.append("(parent_id IS NOT NULL)")
            else:
                params.append(parent_id)
                filters.append(f"(parent_id = ${len(params)})")
        if search_query:
            search_filters = []
            for search_column in search_columns:
                search_column = "table_id" if search_column == "id" else search_column
                # Literal (escaped) search
                params.append(re.escape(search_query))
                literal_expr = f"({search_column}::text ~* ${len(params)})"
                # Regex search
                params.append(search_query)
                regex_expr = f"({search_column}::text ~* ${len(params)})"
                search_filters.append(f"({literal_expr} OR {regex_expr})")
            filters.append("(" + " OR ".join(search_filters) + ")")
        if order_by == "id":
            order_by = "table_id"
        if order_by in TableMetadata.str_cols():
            order_by = f'LOWER("{order_by}")'
        else:
            order_by = f'"{order_by}"'
        order_direction = "ASC" if order_ascending else "DESC"
        where = f"WHERE {' AND '.join(filters)}" if len(filters) > 0 else ""
        async with GENTABLE_ENGINE.transaction() as conn:
            try:
                total = await conn.fetchval(
                    f'SELECT COUNT(*) FROM "{schema_id}"."TableMetadata" {where}',
                    *params,
                )
                sql = f"""
                SELECT * FROM "{schema_id}"."TableMetadata" {where}
                ORDER BY {order_by} {order_direction}
                """
                if limit is not None:
                    params.append(limit)
                    sql += f" LIMIT ${len(params)}"
                table_metas = await conn.fetch(f"{sql} OFFSET ${len(params) + 1}", *params, offset)
            except UndefinedColumnError as e:
                # raise ResourceNotFoundError(f'Attribute "{order_by}" is not found.') from e
                raise ResourceNotFoundError(str(e)) from e
            except UndefinedTableError:
                total = 0
                return Page[TableMetaResponse](
                    items=[],
                    offset=offset,
                    limit=total if limit is None else limit,
                    total=total,
                )
            meta_responses = []
            for table_meta in table_metas:
                table_meta = TableMetadata.model_validate(dict(table_meta))
                column_metas = await conn.fetch(
                    f"""
                    SELECT * FROM "{schema_id}"."ColumnMetadata"
                    WHERE table_id = $1 ORDER BY column_order ASC
                    """,
                    table_meta.table_id,
                )
                column_metas = [ColumnMetadata.model_validate(dict(col)) for col in column_metas]
                if count_rows:
                    num_rows = await conn.fetchval(
                        f'SELECT COUNT("ID") FROM "{schema_id}"."{table_meta.short_id}"'
                    )
                else:
                    num_rows = -1
                meta_responses.append(
                    TableMetaResponse(
                        id=table_meta.table_id,
                        cols=[
                            ColumnSchema(
                                id=col.column_id,
                                dtype=col.dtype,
                                vlen=col.vlen,
                                gen_config=col.gen_config,
                            )
                            for col in column_metas
                        ],
                        parent_id=table_meta.parent_id,
                        title=table_meta.title,
                        created_by=table_meta.created_by,
                        updated_at=table_meta.updated_at.isoformat(),
                        num_rows=num_rows,
                        version=table_meta.version,
                        meta=table_meta.meta,
                    )
                )
        return Page[TableMetaResponse](
            items=meta_responses,
            offset=offset,
            limit=total if limit is None else limit,
            total=total,
        )

    async def count_rows(self) -> int:
        """
        Count the number of rows.

        Returns:
            num_rows (int): Number of rows in the table.
        """
        async with GENTABLE_ENGINE.transaction() as conn:
            return await self._count_rows(conn)
        return self.num_rows

    # Table Update Ops
    async def rename_table(self, table_id_dst: TableName) -> Self:
        """
        Rename a table.

        Args:
            table_id_dst (str): New name for the table.

        Raises:
            ResourceNotFoundError: If the table is not found.
            ResourceExistsError: If the table already exists.

        Returns:
            self (GenerativeTableCore): The renamed table instance.
        """
        table_id_src = self.table_id
        short_id_src = self.short_table_id
        short_id_dst = get_internal_id(table_id_dst)
        async with GENTABLE_ENGINE.transaction() as conn:
            try:
                # Rename data table
                await conn.execute(
                    f'ALTER TABLE "{self.schema_id}"."{short_id_src}" RENAME TO "{short_id_dst}"'
                )
                # Rename primary key index (only for consistency purposes, no operational impact even without rename)
                await conn.execute(
                    f"""
                    ALTER TABLE "{self.schema_id}"."{short_id_dst}"
                    RENAME CONSTRAINT "{short_id_src}_pkey" TO "{short_id_dst}_pkey"
                    """
                )
                # Rename indexes
                await conn.execute(
                    f"""
                    ALTER INDEX "{self.schema_id}"."{fts_index_id(table_id_src)}"
                    RENAME TO "{fts_index_id(table_id_dst)}"
                    """
                )
                for col in self.vector_column_names:
                    await conn.execute(
                        f"""
                        ALTER INDEX "{self.schema_id}"."{vector_index_id(table_id_src, col)}"
                        RENAME TO "{vector_index_id(table_id_dst, col)}"
                        """
                    )
                # Update table metadata entry
                await conn.execute(
                    f"""
                    UPDATE "{self.schema_id}"."TableMetadata"
                    SET table_id = $1, short_id = $2 WHERE table_id = $3
                    """,
                    table_id_dst,
                    short_id_dst,
                    table_id_src,
                )
                # Update any child tables' parent_id references
                await conn.execute(
                    f'UPDATE "{self.schema_id}"."TableMetadata" SET parent_id = $1 WHERE parent_id = $2',
                    table_id_dst,
                    table_id_src,
                )
                self.table_id = table_id_dst
                # Set updated at time
                await self._set_updated_at(conn)
                return self
            except UndefinedTableError as e:
                # Index or table not found
                raise ResourceNotFoundError(f'Table "{table_id_src}" is not found.') from e
            except DuplicateTableError as e:
                raise ResourceExistsError(f'Table "{table_id_dst}" already exists.') from e

    async def update_table_title(self, title: str) -> Self:
        """
        Update the table title.
        """
        updated_at = now()
        query = f"""
        UPDATE "{self.schema_id}"."TableMetadata"
        SET title = $1, updated_at = $2
        WHERE table_id = $3;
        """
        async with GENTABLE_ENGINE.transaction() as conn:
            await conn.execute(query, title, updated_at, self.table_id)
        self.table_metadata.title = title
        self.table_metadata.updated_at = updated_at
        return self

    # Table Delete Ops
    async def drop_table(self) -> None:
        """
        Drop the table.

        Raises:
            ResourceNotFoundError: If the table is not found.
        """
        async with GENTABLE_ENGINE.transaction() as conn:
            try:
                # Drop the data table
                await conn.execute(
                    f'DROP TABLE IF EXISTS "{self.schema_id}"."{self.short_table_id}" CASCADE'
                )
                # Drop row from table metadata, this will cascade to the associated column metadata
                await conn.execute(
                    f'DELETE FROM "{self.schema_id}"."TableMetadata" WHERE table_id = $1',
                    self.table_id,
                )
            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e

    @staticmethod
    def _coerce_column_to_pa_dtype(
        data: list[Any],
        dtype: pa.DataType,
    ) -> pa.Array:
        """Convert column data to appropriate Arrow array type"""
        if len(data) == 0:
            return pa.array([], dtype)
        if isinstance(data[0], UUID):
            data = [str(d) for d in data]
        elif isinstance(data[0], dict):
            data = [json_dumps(d) for d in data]
        return pa.array(data, dtype)

    # Table Import Export Ops
    async def export_table(
        self,
        dest: str | Path | BinaryIO,
        *,
        compression: Literal["NONE", "ZSTD", "LZ4", "SNAPPY"] = "ZSTD",
        verbose: bool = False,
    ) -> None:
        """
        Export a table's data and metadata to a specified output path.

        Args:
            output_path (str | Path): Path to save the exported data.
            compression (str, optional): Compression type for the output file.
                Options are "NONE", "ZSTD", "LZ4", or "SNAPPY". Defaults to "ZSTD".
            verbose (bool, optional): If True, will produce verbose logging messages.
                Defaults to False.

        Raises:
            ResourceNotFoundError: If the output path is invalid.
        """
        log_level = "INFO" if verbose else "DEBUG"
        if isinstance(dest, (str, Path)):
            dest = Path(dest)
            if dest.is_dir():
                dest = dest / f"{self.table_id}.parquet"
            else:
                if (suffix := Path(dest).suffix) != ".parquet":
                    raise BadInputError(f'Output extension "{suffix}" is invalid.')
        rows: list[dict[str, Any]] = (
            await self.list_rows(
                limit=None,
                offset=0,
                order_by=["ID"],
                order_ascending=True,
                columns=None,
                remove_state_cols=False,
            )
        ).items
        col_dtype_map = {
            col.column_id: pa.list_(pa.float32())
            if col.is_vector_column
            else col.dtype.to_pyarrow_type()
            for col in self.column_metadata
        }

        # Add file data into Arrow Table
        async def _download(uri: str | None) -> tuple[str, bytes, str]:
            if not uri:
                return (uri, b"", "")
            async with semaphore:
                try:
                    async with open_uri_async(uri) as (f, mime):
                        return (uri, await f.read(), mime)
                except Exception:
                    return (uri, b"", "")

        async def _download_files(col_ids: list[str]) -> dict[str, tuple[bytes, str]]:
            download_coros = []
            _uri_bytes: dict[str, tuple[bytes, str]] = {}
            for col_id in col_ids:
                if f"{col_id}__" in col_dtype_map:
                    raise BadInputError(f'Table "{self.table_id}" has bad column "{col_id}__".')
                for row in rows:
                    uri: str | None = row[col_id]
                    if uri in _uri_bytes:
                        continue
                    # Create the coroutine
                    download_coros.append(_download(uri))
                    _uri_bytes[uri] = (b"", "")
            self._log(
                (
                    f'Importing table "{self.table_id}": '
                    f"Downloading {len(download_coros):,d} files "
                    f"with concurrency limit of {S3_MAX_CONCURRENCY}."
                ),
                log_level,
            )
            for fut in asyncio.as_completed(download_coros):
                uri, content, mime = await fut
                _uri_bytes[uri] = (content, mime)
            return _uri_bytes

        semaphore = Semaphore(S3_MAX_CONCURRENCY)
        pa_file_columns = []
        self._log(
            f'Importing table "{self.table_id}": Downloading files in file columns.',
            log_level,
        )
        file_col_ids = [col.column_id for col in self.column_metadata if col.is_file_column]
        uri_bytes = await _download_files(file_col_ids)
        uris_seen = set()
        for col_id in file_col_ids:
            col_bytes = []
            for row in rows:
                uri = row[col_id]
                if uri in uris_seen:
                    col_bytes.append(b"")
                    continue
                content, mime = uri_bytes.get(uri, (b"", ""))
                col_bytes.append(content)
                if mime:
                    row[f"{col_id}_"].update({"_mime_type": mime})
                uris_seen.add(uri)
            if len(col_bytes) > 0:
                pa_file_columns.append((pa.field(f"{col_id}__", pa.binary()), [col_bytes]))

        # Add Knowledge Table file data
        if self.table_type == TableType.KNOWLEDGE:
            self._log(
                f'Importing table "{self.table_id}": Downloading Knowledge Table files.',
                log_level,
            )
            file_col_ids = ["File ID"]
            uri_bytes = await _download_files(file_col_ids)
            uris_seen = set()
            for col_id in file_col_ids:
                col_bytes = []
                for row in rows:
                    uri = row[col_id]
                    if uri in uris_seen:
                        col_bytes.append(b"")
                        continue
                    content, mime = uri_bytes.get(uri, (b"", ""))
                    col_bytes.append(content)
                    if mime:
                        row[f"{col_id}_"].update({"_mime_type": mime})
                    uris_seen.add(uri)
                if len(col_bytes) > 0:
                    pa_file_columns.append((pa.field(f"{col_id}__", pa.binary()), [col_bytes]))
        # Create Parquet table
        self._log(f'Importing table "{self.table_id}": Creating Parquet table.', log_level)
        pa_table = pa.table(
            {
                col.column_id: self._coerce_column_to_pa_dtype(
                    [row[col.column_id] for row in rows], col_dtype_map[col.column_id]
                )
                for col in self.column_metadata
            },
            metadata=dict(gen_table_meta=self.v1_meta.model_dump_json()),
        )
        # Append byte column
        for pa_col in pa_file_columns:
            pa_table = pa_table.append_column(*pa_col)
        # Write to Parquet
        self._log(f'Importing table "{self.table_id}": Writing Parquet table.', log_level)
        try:
            pq.write_table(pa_table, dest, compression=compression)
        except (FileNotFoundError, OSError) as e:
            raise ResourceNotFoundError(f'Output path "{dest}" is invalid.') from e
        self._log(f'Importing table "{self.table_id}": Export completed.', log_level)

    @classmethod
    async def _import_table(
        cls,
        *,
        project_id: str,
        table_type: TableType,
        source: str | Path | BinaryIO,
        table_id_dst: str | None,
        reupload_files: bool = True,
        progress_key: str = "",
        verbose: bool = False,
    ) -> Self:
        def _measure_ram() -> str:
            import psutil

            GiB = 1024**3
            mem = psutil.virtual_memory()
            return f"RAM usage: {mem.used / GiB:,.2f} / {mem.total / GiB:,.2f} GiB ({mem.percent:.1f} %)"

        # Check if project exists
        project = await cls._fetch_project(project_id)
        organization_id = project.organization_id

        # Load Parquet file
        filename = source if isinstance(source, str) else getattr(source, "name", "")
        try:
            pa_table: pa.Table = pq.read_table(
                source, columns=None, use_threads=False, memory_map=True
            )
        except FileNotFoundError as e:
            raise ResourceNotFoundError(f'Parquet file "{filename}" is not found.') from e
        except Exception as e:
            logger.info(f'Parquet file "{filename}" contains bad data: {repr(e)}')
            raise BadInputError(f'Parquet file "{filename}" contains bad data.') from e
        try:
            pa_meta = TableMeta.model_validate_json(pa_table.schema.metadata[b"gen_table_meta"])
        except KeyError as e:
            raise BadInputError("Missing table metadata in the Parquet file.") from e
        except Exception as e:
            logger.warning(f"Invalid table metadata in the Parquet file: {repr(e)}")
            raise BadInputError("Invalid table metadata in the Parquet file.") from e
        # Check for existing table
        if table_id_dst is None:
            table_id_dst = pa_meta.id
        if verbose:
            logger.info(
                f'Importing table "{table_id_dst}": Parquet data loaded successfully. {_measure_ram()}'
            )
        prog = TableImportProgress(key=progress_key)
        if not (await CACHE.set_progress(prog, nx=True)):
            raise ResourceExistsError(
                f'There is an in-progress import for table "{table_id_dst}".'
            )
        prog.data["table_id_dst"] = table_id_dst
        prog.load_data.progress = 100
        await CACHE.set_progress(prog)

        async with GENTABLE_ENGINE.transaction() as conn:
            schema_id = f"{project_id}_{table_type}"
            try:
                table_metadata = await conn.fetchrow(
                    f'SELECT * FROM "{schema_id}"."TableMetadata" WHERE table_id = $1',
                    table_id_dst,
                )
            except UndefinedTableError:
                table_metadata = None
        if table_metadata is not None:
            raise ResourceExistsError(f'Table "{table_id_dst}" already exists.')
        # Check for required columns
        pa_meta_cols = {c.id for c in pa_meta.cols}
        # Sometimes Chat Table has "user" instead of "User"
        if table_type == TableType.CHAT and "user" in pa_meta_cols and "User" not in pa_meta_cols:
            for col in pa_meta.cols:
                if col.id == "user":
                    col.id = "User"
                    break
            pa_meta_cols = {c.id for c in pa_meta.cols}
        required_columns = set(cls.FIXED_COLUMN_IDS)
        if len(required_columns - pa_meta_cols) > 0:
            raise BadInputError(
                f"Missing table columns in the Parquet file: {list(required_columns - pa_meta_cols)}."
            )
        # Recreate table and column metadata
        table_metadata = TableMetadata(
            table_id=table_id_dst,
            title=pa_meta.title,
            parent_id=pa_meta.parent_id,
            updated_at=pa_meta.updated_at,
        )
        column_metadata = []
        for col in pa_meta.cols:
            if isinstance(col.gen_config, LLMGenConfig):
                # LLM columns are always string typed
                col.dtype = ColumnDtype.STR
                # Handle RAG params
                if col.gen_config.rag_params:
                    params = col.gen_config.rag_params.model_dump(exclude_unset=True)
                    col.gen_config.rag_params.inline_citations = params.get(
                        "inline_citations", False
                    )
            column_metadata.append(
                ColumnMetadata(
                    table_id=table_id_dst,
                    column_id=col.id,
                    dtype=col.dtype,
                    vlen=col.vlen,
                    gen_config=col.gen_config,
                )
            )

        # Create the new table
        if verbose:
            logger.info(
                f'Importing table "{table_id_dst}": Creating Generative Table. {_measure_ram()}'
            )
        prog.parse_data.progress = 50
        await CACHE.set_progress(prog)
        self = await cls._create_table(
            project_id=project_id,
            table_type=table_type,
            table_metadata=table_metadata,
            column_metadata_list=column_metadata,
            set_default_prompts=False,
            replace_unavailable_models=True,  # Old tables may have deprecated models
            allow_nonexistent_refs=True,  # Old tables may have non-existent columns
            create_indexes=False,
        )

        # Load data
        if verbose:
            logger.info(
                f'Importing table "{self.table_id}": Pre-processing Parquet data. {_measure_ram()}'
            )
        rows: list[dict[str, Any]] = pa_table.to_pylist()
        # Process state JSON
        for row in rows:
            for col_id in row:
                if col_id.endswith("__"):
                    # File byte column
                    continue
                if not col_id.endswith("_"):
                    # Regular column
                    continue
                state = json_loads(row[col_id] or "{}")
                # Legacy attribute
                if state.pop("is_null", False):
                    row[col_id[:-1]] = None
                row[col_id] = state
            # HACK: special handling for importing v1 knowledge table. To be remove in the future
            if self.table_type == TableType.KNOWLEDGE:
                file_id = row.get("File ID", None)
                if file_id and file_id.startswith("file://file"):
                    row["File ID"] = file_id.replace("file://file", ENV_CONFIG.file_dir)

        # Upload files to S3
        if verbose:
            if reupload_files:
                logger.info(f'Importing table "{self.table_id}": Uploading files to S3.')
            else:
                logger.info(f'Importing table "{self.table_id}": Skipped S3 upload.')
        prog.parse_data.progress = 100
        await CACHE.set_progress(prog)

        async def _upload(
            old_uri: str,
            content: bytes,
            content_type: str,
            filename: str,
        ) -> tuple[str, str]:
            async with semaphore:
                new_uri = await s3_upload(
                    organization_id,
                    project_id,
                    content,
                    content_type=content_type,
                    filename=filename,
                )
                return (old_uri, new_uri)

        uris_seen: dict[str, str] = {}  # Old URI to new URI
        semaphore = Semaphore(S3_MAX_CONCURRENCY)
        upload_coros = []
        for row in rows:
            file_byte_cols = [c for c in row.keys() if c.endswith("__")]
            for col_id in file_byte_cols:
                state_col_id = col_id[:-1]
                uri_col_id = col_id[:-2]
                uri: str = row[uri_col_id]
                if uri in uris_seen:
                    continue
                if not reupload_files:
                    uris_seen[uri] = uri
                    continue
                file_bytes = row[col_id]
                if len(file_bytes) == 0:
                    # Could be file download error or duplicate URI
                    continue
                mime_type = row[state_col_id].pop("_mime_type", None)
                # Attempt MIME type detection based on URI
                if mime_type is None:
                    mime_type = guess_mime(uri)
                # Attempt MIME type detection based on file content
                if mime_type is None:
                    mime_type = guess_mime(file_bytes)
                # Create the coroutine
                upload_coros.append(_upload(uri, file_bytes, mime_type, uri.split("/")[-1]))
                # Set to old URI for now
                uris_seen[uri] = uri
        total, completed = len(upload_coros), 0
        if verbose:
            logger.info(
                (
                    f'Importing table "{self.table_id}": Uploading {total:,d} files '
                    f"with concurrency limit of {S3_MAX_CONCURRENCY}. {_measure_ram()}"
                )
            )
        for fut in asyncio.as_completed(upload_coros):
            old_uri, new_uri = await fut
            uris_seen[old_uri] = new_uri
            completed += 1
            prog.upload_files.progress = int((completed / total) * 100)
            await CACHE.set_progress(prog)
        # Set new URI and remove file byte column from row
        for row in rows:
            file_byte_cols = [c for c in row.keys() if c.endswith("__")]
            for col_id in file_byte_cols:
                uri_col_id = col_id[:-2]
                row[uri_col_id] = uris_seen.get(row[uri_col_id], None)
                state_col_id = col_id[:-1]
                row[state_col_id].pop("_mime_type", None)
                row.pop(col_id, None)
        prog.upload_files.progress = 100
        await CACHE.set_progress(prog)

        # Add data to table batch by batch
        n = len(rows)
        if verbose:
            logger.info(f'Importing table "{self.table_id}": Adding {n:,d} rows. {_measure_ram()}')
        for i in range(0, n, IMPORT_BATCH_SIZE):
            j = min(i + IMPORT_BATCH_SIZE, n)
            self = await self.add_rows(
                rows[i:j],
                ignore_info_columns=False,
                ignore_state_columns=False,
                set_updated_at=False,
            )
            if verbose:
                logger.info(
                    f'Importing table "{self.table_id}": Added {j:,d} / {n:,d} rows. {_measure_ram()}'
                )
            prog.add_rows.progress = int((j / n) * 100)
            await CACHE.set_progress(prog)
        prog.add_rows.progress = 100
        # Perform indexing
        async with GENTABLE_ENGINE.transaction() as conn:
            await self._recreate_fts_index(
                conn,
                schema_id=self.schema_id,
                table_id=self.table_id,
                columns=self.text_column_names,
            )
        logger.info(f'Importing table "{self.table_id}": Created FTS index.')
        async with GENTABLE_ENGINE.transaction() as conn:
            await self._recreate_vector_index(
                conn,
                schema_id=self.schema_id,
                table_id=self.table_id,
                columns=self.vector_column_names,
            )
        logger.info(f'Importing table "{self.table_id}": Created vector index.')
        prog.index.progress = 100
        prog.state = ProgressState.COMPLETED
        prog.data["table_meta"] = self.v1_meta_response.model_dump(mode="json")
        await CACHE.set_progress(prog)
        return self

    @classmethod
    async def import_table(
        cls,
        *,
        project_id: str,
        table_type: TableType,
        source: str | Path | BinaryIO,
        table_id_dst: TableName | None,
        reupload_files: bool = True,
        progress_key: str = "",
        verbose: bool = False,
    ) -> Self:
        """
        Recreate a table (data and metadata) from a Parquet file.

        Args:
            project_id (str): Project ID.
            table_type (str): Table type.
            input_path (str | Path): The path to the import file.
            table_id_dst (TableName): Name or ID of the new table.
                If None, the table ID in the Parquet metadata will be used.
            reupload_files (bool, optional): If True, will reupload files to S3 with new URI.
                Otherwise skip reupload and keep the original S3 paths for file columns.
                Defaults to True.
            progress_key (str, optional): Progress publish key. Defaults to "" (disabled).
            verbose (bool, optional): If True, will produce verbose logging messages.
                Defaults to False.

        Raises:
            ResourceExistsError: If the table already exists.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        try:
            self = await cls._import_table(
                project_id=project_id,
                table_type=table_type,
                source=source,
                table_id_dst=table_id_dst,
                reupload_files=reupload_files,
                progress_key=progress_key,
                verbose=verbose,
            )
        except Exception as e:
            if not isinstance(e, JamaiException):
                logger.exception(repr(e))
            try:
                prog = await CACHE.get_progress(progress_key, TableImportProgress)
                if table_id := (prog.data.get("table_id_dst", None)):
                    # Might need to clean up
                    async with GENTABLE_ENGINE.transaction() as conn:
                        try:
                            schema_id = f"{project_id}_{table_type}"
                            # Drop the data table
                            await conn.execute(f'DROP TABLE IF EXISTS "{schema_id}"."{table_id}"')
                            # Drop row from table metadata, this will automatically drop the associated column metadata
                            await conn.execute(
                                f'DELETE FROM "{schema_id}"."TableMetadata" WHERE table_id = $1',
                                table_id,
                            )
                        except Exception as e:
                            logger.info(
                                f'Encountered error cleaning up table "{table_id}" after failed import: {repr(e)}'
                            )
                prog.state = ProgressState.FAILED
                prog.error = repr(e)
                await CACHE.set_progress(prog)
            except Exception as e:
                logger.error(f"Encountered error setting progress after failed import: {repr(e)}")
                logger.error(repr(e))
            raise
        return self

    def _filter_columns(
        self,
        columns: list[str] | None,
        *,
        exclude_state: bool,
    ) -> list[str]:
        data_columns = self.data_table_model.get_column_ids(exclude_state=exclude_state)
        if columns:
            if not exclude_state:
                columns += [f"{c}_" for c in columns]
            columns = [c for c in data_columns if c in columns]
            if "Updated at" not in columns:
                columns.insert(0, "Updated at")
            if "ID" not in columns:
                columns.insert(0, "ID")
        else:
            columns = data_columns
        return columns

    async def export_data(
        self,
        output_path: str | Path,
        *,
        columns: list[str] | None = None,
        where: str = "",
        limit: int | None = None,
        offset: int = 0,
        delimiter: CSVDelimiter = CSVDelimiter.COMMA,
    ) -> None:
        """
        Export table data to CSV file.

        Args:
            output_path (str | Path): Path to save the CSV file.
            columns (list[str] | None, optional): A list of column names to include in the returned rows.
                Defaults to None (return all columns).
            where (str, optional): SQL WHERE clause to filter rows. Defaults to "".
            limit (int | None, optional): Maximum number of rows to export. Defaults to None.
            offset (int | None, optional): Offset for pagination. Defaults to None.
            delimiter (str, optional): CSV delimiter, either "," or "\\t". Defaults to ",".

        Raises:
            BadInputError: If the delimiter is invalid.
            ResourceNotFoundError: If the table is not found.
        """
        if delimiter not in CSVDelimiter:
            raise BadInputError(f"Invalid delimiter: {delimiter}")
        columns = self._filter_columns(columns, exclude_state=True)
        # Get table data
        rows = (
            await self.list_rows(
                limit=limit,
                offset=offset,
                order_by=["ID"],
                order_ascending=True,
                columns=columns,
                where=where,
                remove_state_cols=True,
            )
        ).items
        try:
            df = pd.DataFrame(rows, columns=columns)
            # Convert special types
            col_meta_map = {col.column_id: col for col in self.column_metadata}
            dtype = {}
            for col in columns:
                if col_meta_map[col].dtype == ColumnDtype.DATE_TIME:
                    df[col] = df[col].apply(lambda x: x.isoformat())
                    dtype[col] = pd.StringDtype()
                elif col_meta_map[col].is_vector_column:
                    df[col] = df[col].apply(lambda x: x.tolist())
                    dtype[col] = pd.StringDtype()
                else:
                    dtype[col] = col_meta_map[col].dtype.to_pandas_type()
            df = df.astype(dtype, errors="raise")
        except Exception as e:
            raise BadInputError(
                f'Failed to export table "{self.table_id}" due to error: {e}'
            ) from e
        try:
            df_to_csv(df=df, file_path=output_path, sep=delimiter)
        except (FileNotFoundError, OSError) as e:
            raise BadInputError(f'Output path "{output_path}" is not found.') from e

    async def read_csv(
        self,
        input_path: str | Path | BinaryIO,
        *,
        column_id_mapping: dict[str, str] | None = None,
        delimiter: CSVDelimiter = CSVDelimiter.COMMA,
        ignore_info_columns: bool = True,
    ) -> Self:
        col_meta_map = {col.column_id: col for col in self.column_metadata}
        dtype = {
            col.column_id: pd.StringDtype() if col.is_vector_column else col.dtype.to_pandas_type()
            for col in self.column_metadata
        }
        # Read CSV file
        try:
            df = pd.read_csv(input_path, dtype=dtype, delimiter=delimiter, keep_default_na=True)
        except FileNotFoundError as e:
            raise ResourceNotFoundError(f'Input file "{input_path}" is not found.') from e
        except pd.errors.EmptyDataError as e:
            raise BadInputError(f'Input file "{input_path}" is empty.') from e
        if len(df) == 0:
            raise BadInputError(f'Input file "{input_path}" has no rows.')
        try:
            # Apply column mapping if provided
            if column_id_mapping:
                df = df.rename(columns=column_id_mapping)
            # Remove "ID" and "Updated at" columns if needed
            if ignore_info_columns:
                df = df[[col for col in df.columns if col.lower() not in self.INFO_COLUMNS]]

            # Create a mapping of column names to their metadata for faster lookup
            col_meta_map = {col.column_id: col for col in self.column_metadata}
            # Keep only valid columns
            df = df[[col for col in df.columns if col in col_meta_map]]
            # Convert special types
            for col in df.columns:
                if col_meta_map[col].dtype == ColumnDtype.DATE_TIME:
                    df[col] = df[col].apply(lambda x: utc_datetime_from_iso(x))
                elif col_meta_map[col].is_vector_column:
                    df[col] = df[col].apply(json_loads)
                    # Check vector length
                    array_lengths = df[col].apply(len)
                    if array_lengths.nunique() != 1:
                        raise BadInputError("All vectors must have the same length.")
                    array_length = int(array_lengths[0])
                    if array_length != col_meta_map[col].vlen:
                        raise BadInputError(
                            (
                                f'Vector column "{col}" expects vectors of length {col_meta_map[col].vlen:,d} '
                                f"but got vectors of length {array_length:,d}."
                            )
                        )
            # Convert to list of dicts
            rows = df.to_dict(orient="records")
        except Exception as e:
            raise BadInputError(
                f'Failed to import data into table "{self.table_id}" due to error: {e}'
            ) from e
        return rows

    async def import_data(
        self,
        input_path: str | Path,
        *,
        column_id_mapping: dict[str, str] | None = None,
        delimiter: CSVDelimiter = CSVDelimiter.COMMA,
        ignore_info_columns: bool = True,
        verbose: bool = False,
    ) -> Self:
        """
        Import data into the Generative Table from a CSV file.

        Args:
            input_path (str | Path): Path to the CSV file.
            column_id_mapping (dict[str, str] | None, optional): Mapping of CSV column ID to table column ID.
                Defaults to None.
            delimiter (str, optional): CSV delimiter, either "," or "\\t". Defaults to ",".
            ignore_info_columns (bool, optional): Whether to ignore "ID" and "Updated at" columns.
                Defaults to True.
            verbose (bool, optional): If True, will produce verbose logging messages.
                Defaults to False.

        Raises:
            ResourceNotFoundError: If the file or table is not found.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        rows = await self.read_csv(
            input_path=input_path,
            column_id_mapping=column_id_mapping,
            delimiter=delimiter,
            ignore_info_columns=ignore_info_columns,
        )
        if verbose:
            self._log(f'Importing table "{self.table_id}": Import data loaded successfully.')
        # Insert rows
        n = len(rows)
        if verbose:
            self._log(f'Importing table "{self.table_id}": Adding {n:,d} rows.')
        for i in range(0, n, IMPORT_BATCH_SIZE):
            j = min(i + IMPORT_BATCH_SIZE, n)
            self = await self.add_rows(rows[i:j])
            if verbose:
                self._log(f'Importing table "{self.table_id}": Added {j:,d} / {n:,d} rows.')
        return self

    ### --- Column CRUD --- ###

    # Column Create Ops
    async def add_column(
        self,
        metadata: ColumnMetadata,
        request_id: str = "",
    ) -> Self:
        """
        Add a new column to the table.

        Args:
            metadata (ColumnMetadata): Metadata for the new column.
            request_id (str, optional): Request ID for logging. Defaults to "".

        Raises:
            BadInputError: If the column is a state column.
            ResourceNotFoundError: If table cannot be found.
            ResourceExistsError: If the column already exists in the table.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        if self.table_metadata.parent_id is not None:
            # TODO: Test this
            raise BadInputError(f'Table "{self.table_id}": Cannot add column to a child table.')
        if metadata.is_state_column:
            # TODO: Test this
            raise BadInputError(f'Table "{self.table_id}": Cannot add state column.')
        async with GENTABLE_ENGINE.transaction() as conn:
            column_metadata_list = await self._check_columns(
                conn=conn,
                project_id=self.project_id,
                table_type=self.table_type,
                table_metadata=self.table_metadata,
                column_metadata_list=self.column_metadata + [metadata],
                set_default_prompts=True,
                replace_unavailable_models=False,
            )
            metadata = column_metadata_list[-1]
            # Define column definition
            if metadata.is_vector_column:
                column_def = f'"{metadata.short_id}" VECTOR({metadata.vlen})'
            else:
                column_def = f'"{metadata.short_id}" {metadata.dtype.to_postgres_type()}'
            # Add new and state column to the data table
            try:
                await conn.execute(
                    f"""
                    ALTER TABLE "{self.schema_id}"."{self.short_table_id}"
                    ADD COLUMN {column_def},
                    ADD COLUMN {self._state_column_sql(metadata.short_id)};
                    """
                )
            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
            except DuplicateColumnError as e:
                raise ResourceExistsError(
                    f"Column {metadata.column_id} already exists in table {self.table_id}"
                ) from e
            # Add column metadata
            metadata.column_order = len(self.column_metadata)
            await self._upsert_column_metadata(conn, self.schema_id, metadata)
            state_meta = ColumnMetadata(
                table_id=self.table_id,
                column_id=f"{metadata.column_id}_",
                dtype=ColumnDtype.JSON,
                column_order=len(self.column_metadata) + 1,
            )
            await self._upsert_column_metadata(conn, self.schema_id, state_meta)
            # Set updated at time
            await self._set_updated_at(conn)
            # Reload table
            self = await self._open_table(
                conn=conn,
                project_id=self.project_id,
                table_type=self.table_type,
                table_id=self.table_id,
                request_id=request_id,
            )
            if metadata.is_text_column:
                await self._recreate_fts_index(
                    conn,
                    schema_id=self.schema_id,
                    table_id=self.table_id,
                    columns=self.text_column_names,
                )
            elif metadata.is_vector_column:
                await self._recreate_vector_index(
                    conn,
                    schema_id=self.schema_id,
                    table_id=self.table_id,
                    columns=self.vector_column_names,
                )
        return self

    # Column Read ops are implemented as table ops
    # Column Update Ops
    async def rename_columns(
        self,
        column_map: dict[str, ColName],
    ) -> Self:
        """
        Rename columns of the Generative Table.

        Args:
            column_map (dict[str, str]): Mapping of old column names to new column names.

        Raises:
            ResourceNotFoundError: If the table or any of the columns cannot be found.
            ResourceExistsError: If any of the new column names already exists in the table.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        if self.table_metadata.parent_id is not None:
            # TODO: Test this
            raise BadInputError(
                f'Table "{self.table_id}": Cannot rename columns of a child table.'
            )
        fixed_cols = {c.lower() for c in self.FIXED_COLUMN_IDS}
        if invalid_cols := {c.lower() for c in column_map}.intersection(fixed_cols):
            # TODO: Test this especially for Knowledge Table
            raise BadInputError(
                f'Table "{self.table_id}": Cannot rename fixed columns: {list(invalid_cols)}'
            )
        if invalid_cols := [c for c in column_map if c.endswith("_")]:
            # TODO: Test this
            raise BadInputError(
                f'Table "{self.table_id}": Cannot rename state columns: {invalid_cols}'
            )
        async with GENTABLE_ENGINE.transaction() as conn:
            for col_id_src, col_id_dst in column_map.items():
                col_meta = next(
                    (col for col in self.column_metadata if col.column_id == col_id_src), None
                )
                if col_meta is None:
                    continue
                # Rename data and state columns
                short_table_id = self.short_table_id
                short_id_src = get_internal_id(col_id_src)
                short_id_dst = get_internal_id(col_id_dst)
                try:
                    await conn.execute(
                        f"""
                        ALTER TABLE "{self.schema_id}"."{short_table_id}"
                        RENAME COLUMN "{short_id_src}" TO "{short_id_dst}"
                        """
                    )
                    await conn.execute(
                        f"""
                        ALTER TABLE "{self.schema_id}"."{short_table_id}"
                        RENAME COLUMN "{short_id_src}_" TO "{short_id_dst}_"
                        """
                    )
                    # Rename vector index
                    if col_meta.is_vector_column:
                        await conn.execute(
                            (
                                f'ALTER INDEX "{self.schema_id}"."{vector_index_id(self.table_id, col_id_src)}" '
                                f'RENAME TO "{vector_index_id(self.table_id, col_id_dst)}"'
                            )
                        )
                except UndefinedTableError as e:
                    # Index or table not found
                    raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
                except (UndefinedColumnError, IndexError) as e:
                    raise ResourceNotFoundError(
                        f'Column "{col_id_src}" is not found in table "{self.table_id}".'
                    ) from e
                except DuplicateColumnError as e:
                    raise ResourceExistsError(
                        f'Column "{col_id_dst}" already exists in table "{self.table_id}".'
                    ) from e
                # Update column metadata entries
                await conn.execute(
                    f"""
                    UPDATE "{self.schema_id}"."ColumnMetadata"
                    SET column_id = $1, short_id = $2
                    WHERE table_id = $3 AND column_id = $4
                    """,
                    col_id_dst,
                    short_id_dst,
                    self.table_id,
                    col_id_src,
                )
                await conn.execute(
                    f"""
                    UPDATE "{self.schema_id}"."ColumnMetadata"
                    SET column_id = $1, short_id = $2
                    WHERE table_id = $3 AND column_id = $4
                    """,
                    f"{col_id_dst}_",
                    f"{short_id_dst}_",
                    self.table_id,
                    f"{col_id_src}_",
                )
                # Update gen config references
                for col in self.column_metadata:
                    if col.column_id == col_id_dst or col.column_id == col_id_src:
                        continue
                    if not isinstance(col.gen_config, LLMGenConfig):
                        continue
                    for k in ("system_prompt", "prompt"):
                        setattr(
                            col.gen_config,
                            k,
                            re.sub(
                                GEN_CONFIG_VAR_PATTERN,
                                lambda m: f"${{{column_map.get(m.group(1), m.group(1))}}}",
                                getattr(col.gen_config, k),
                            ),
                        )
                    await conn.execute(
                        f"""
                        UPDATE "{self.schema_id}"."ColumnMetadata" SET gen_config = $1
                        WHERE table_id = $2 AND column_id = $3
                        """,
                        col.gen_config.model_dump(),
                        self.table_id,
                        col.column_id,
                    )
            # Set updated at time
            await self._set_updated_at(conn)
            return await self._reload_table(conn)

    async def update_gen_config(
        self,
        update_mapping: dict[str, DiscriminatedGenConfig | None],
        *,
        allow_nonexistent_refs: bool = False,
        request_id: str = "",
    ) -> Self:
        """
        Update the generation configuration for a column.

        Args:
            update_mapping (dict[str, DiscriminatedGenConfig]): Mapping of column IDs to new generation configurations.
            allow_nonexistent_refs (bool, optional): Ignore non-existent column and Knowledge Table references.
                Otherwise will raise an error. Useful when importing old tables and performing maintenance.
                Defaults to False.
            request_id (str, optional): Request ID for logging. Defaults to "".

        Raises:
            ResourceNotFoundError: If the column is not found.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        # Verify column exists
        columns_to_update = []
        async with GENTABLE_ENGINE.transaction() as conn:
            for column_id, config in update_mapping.items():
                column = next(
                    (col for col in self.column_metadata if col.column_id == column_id), None
                )
                if not column:
                    # TODO: Test this
                    raise ResourceNotFoundError(
                        f'Column "{column_id}" is not found in table "{self.table_id}".'
                    )
                if column.is_state_column:
                    # TODO: Test this
                    raise BadInputError(
                        f'Column "{column_id}" is a state column and cannot be updated.'
                    )
                # Disallow update of vector column if the table has data
                has_data: bool = await conn.fetchval(
                    f'SELECT EXISTS (SELECT 1 FROM "{self.schema_id}"."{self.short_table_id}" LIMIT 1)'
                )
                if column.is_vector_column and has_data:
                    # TODO: Test this
                    raise BadInputError(
                        f'Column "{column_id}" contains data thus its Embedding config cannot be updated.'
                    )
                # Update column metadata in-place
                if config is None or column.gen_config is None:
                    column.gen_config = config
                else:
                    column.gen_config = type(column.gen_config).model_validate(
                        merge_dict(
                            column.gen_config.model_dump(),
                            config.model_dump(exclude_unset=True),
                        )
                    )
                columns_to_update.append(column)
            # Validate
            await self._check_columns(
                conn=conn,
                project_id=self.project_id,
                table_type=self.table_type,
                table_metadata=self.table_metadata,
                column_metadata_list=self.column_metadata,
                set_default_prompts=False,
                replace_unavailable_models=False,
                allow_nonexistent_refs=allow_nonexistent_refs,
            )
            for column in columns_to_update:
                await self._upsert_column_metadata(conn, self.schema_id, column)
            # Set updated at time
            await self._set_updated_at(conn)
            self = await self._open_table(
                conn=conn,
                project_id=self.project_id,
                table_type=self.table_type,
                table_id=self.table_id,
                request_id=request_id,
            )
        return self

    async def reorder_columns(
        self,
        column_names: list[str],
    ) -> Self:
        """
        Reorder columns in the table.

        Args:
            column_names (list[str]): List of column name in the desired order.

        Raises:
            BadInputError: If the list of columns to reorder does not match the table columns.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        if column_names[0].lower() != "id":
            raise BadInputError('First column must be "ID".')
        if column_names[1].lower() != "updated at":
            raise BadInputError('Second column must be "Updated at".')
        if len(set(n.lower() for n in column_names)) != len(column_names):
            raise BadInputError("Column names must be unique (case-insensitive).")
        columns = self.data_table_model.get_column_ids(exclude_state=True)
        if set(column_names) != set(columns):
            raise BadInputError("The list of columns to reorder does not match the table columns.")
        state_columns = [f"{col}_" for col in column_names if col.lower() not in self.INFO_COLUMNS]
        async with GENTABLE_ENGINE.transaction() as conn:
            # Update column order
            for idx, column_id in enumerate(column_names + state_columns):
                await conn.execute(
                    f"""
                    UPDATE "{self.schema_id}"."ColumnMetadata"
                    SET column_order = $1
                    WHERE table_id = $2 AND column_id = $3
                    """,
                    idx,
                    self.table_id,
                    column_id,
                )
            # Set updated at time
            await self._set_updated_at(conn)
            return await self._reload_table(conn)

    # Column Delete Ops
    async def drop_columns(
        self,
        column_ids: list[str],
    ) -> Self:
        """
        Drop columns from the Generative Table.

        Args:
            column_ids (list[str]): List of column IDs to drop.

        Raises:
            ResourceNotFoundError: If any of the columns is not found.
        """
        if self.table_metadata.parent_id is not None:
            # TODO: Test this
            raise BadInputError(f'Table "{self.table_id}": Cannot drop column from a child table.')
        fixed_cols = {c.lower() for c in self.FIXED_COLUMN_IDS}
        if invalid_cols := {c.lower() for c in column_ids}.intersection(fixed_cols):
            # TODO: Test this especially for Knowledge Table
            raise BadInputError(
                f'Table "{self.table_id}": Cannot drop fixed columns: {list(invalid_cols)}'
            )
        if len(invalid_cols := [c for c in column_ids if c.endswith("_")]) > 0:
            # TODO: Test this
            raise BadInputError(
                f'Table "{self.table_id}": Cannot drop state columns: {invalid_cols}'
            )
        async with GENTABLE_ENGINE.transaction() as conn:
            short_table_id = self.short_table_id
            for column_id in column_ids:
                # Drop column and state column
                short_id = get_internal_id(column_id)
                try:
                    await conn.execute(
                        f'ALTER TABLE "{self.schema_id}"."{short_table_id}" DROP COLUMN "{short_id}"'
                    )
                    await conn.execute(
                        f'ALTER TABLE "{self.schema_id}"."{short_table_id}" DROP COLUMN "{short_id}_"'
                    )
                except UndefinedColumnError as e:
                    raise ResourceNotFoundError(
                        f'Column "{column_id}" is not found in table "{self.table_id}".'
                    ) from e
                except Exception as e:
                    raise ResourceNotFoundError(
                        f'Column "{column_id}" is not found in table "{self.table_id}".'
                    ) from e
                # Remove column metadata and the associated state column
                await conn.execute(
                    f'DELETE FROM "{self.schema_id}"."ColumnMetadata" WHERE table_id = $1 AND column_id = $2',
                    self.table_id,
                    column_id,
                )
                await conn.execute(
                    f'DELETE FROM "{self.schema_id}"."ColumnMetadata" WHERE table_id = $1 AND column_id = $2',
                    self.table_id,
                    f"{column_id}_",
                )
            # Update column order
            columns = self.data_table_model.get_column_ids(exclude_state=False)
            columns = [col for col in columns if col not in column_ids]
            for idx, column_id in enumerate(columns):
                await conn.execute(
                    f"""
                    UPDATE "{self.schema_id}"."ColumnMetadata"
                    SET column_order = $1
                    WHERE table_id = $2 AND column_id = $3
                    """,
                    idx,
                    self.table_id,
                    column_id,
                )
            # Set updated at time
            await self._set_updated_at(conn)
            # Rebuild indexes if needed
            if any(c.is_text_column for c in self.column_metadata if c.column_id in column_ids):
                await self._recreate_fts_index(
                    conn,
                    schema_id=self.schema_id,
                    table_id=self.table_id,
                    columns=[
                        c.column_id
                        for c in self.column_metadata
                        if c.column_id not in column_ids and c.is_text_column
                    ],
                )
            if any(c.is_vector_column for c in self.column_metadata if c.column_id in column_ids):
                await self._recreate_vector_index(
                    conn,
                    schema_id=self.schema_id,
                    table_id=self.table_id,
                    columns=[
                        c.column_id
                        for c in self.column_metadata
                        if c.column_id not in column_ids and c.is_vector_column
                    ],
                )
            return await self._reload_table(conn)

    ### --- Row CRUD --- ###
    @staticmethod
    def _jsonify(x: Any) -> Any:
        return x.tolist() if isinstance(x, np.ndarray) else x

    def _validate_row_data(self, data: dict[str, Any]) -> DataTableRow:
        try:
            row = self.data_table_model.model_validate(data, strict=False)
        except ValidationError as e:
            # Set invalid value to None, and save original value to state
            for error in e.errors():
                if len(error["loc"]) > 1:
                    raise BadInputError(f"Input data contains errors: {e}") from e
                col = error["loc"][0]
                state = data.get(f"{col}_", {})
                data[col], data[f"{col}_"] = (
                    None,
                    {"original": self._jsonify(data[col]), "error": error.get("msg", ""), **state},
                )
            # Try validating again
            try:
                row = self.data_table_model.model_validate(data, strict=False)
            except ValidationError as e:
                raise BadInputError(f"Input data contains errors: {e}") from e
        return row

    # Row Create Ops
    async def add_rows(
        self,
        data_list: list[dict[str, Any]],
        *,
        ignore_info_columns: bool = True,
        ignore_state_columns: bool = True,
        set_updated_at: bool = True,
    ) -> Self:
        """
        Add multiple rows to the Generative Table.

        Args:
            data_list (list[dict[str, Any]]): List of row data dictionaries.
            ignore_info_columns (bool, optional): Whether to ignore "ID" and "Updated at" columns.
                Defaults to True.
            ignore_state_columns (bool, optional): Whether to ignore state columns.
                Defaults to True.
            set_updated_at (bool, optional): Whether to set the "Updated at" time to now.
                Defaults to True.

        Raises:
            TypeError: If the data is not a list of dictionaries.
            ResourceNotFoundError: If the table is not found.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        if not (isinstance(data_list, list) and all(isinstance(row, dict) for row in data_list)):
            # We raise TypeError here since this is a programming error
            raise TypeError("`data_list` must be a list of dicts.")
        # Filter out non-existent fields
        columns = set(
            self.data_table_model.get_column_ids(
                exclude_info=ignore_info_columns,
                exclude_state=ignore_state_columns,
            )
        )
        data_list = [{k: v for k, v in row.items() if k in columns} for row in data_list]
        data_list = [row for row in data_list if len(row) > 0]
        if len(data_list) == 0:
            return self
        rows = [self._validate_row_data(data) for data in data_list]
        # Build SQL statement
        all_columns = self.data_table_model.get_column_ids()
        _sql_cols = [f'"{self.map_to_short_col_id[c]}"' for c in all_columns]
        stmt = (
            f'INSERT INTO "{self.schema_id}"."{self.short_table_id}" ({", ".join(_sql_cols)}) '
            f"VALUES ({', '.join(f'${i + 1}' for i in range(len(all_columns)))})"
        )
        values = [[getattr(row, c) for c in all_columns] for row in rows]
        async with GENTABLE_ENGINE.transaction() as conn:
            # Insert rows with retries
            for _ in range(3):
                try:
                    # Use executemany for batch operations
                    await conn.executemany(stmt, values)
                    break
                except UndefinedTableError as e:
                    raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
                except DataError as e:
                    self._log(
                        f"Failed to insert {len(rows):,d} rows due to: {repr(e)}.\nSQL:\n{stmt}\nValues:\n{values}",
                        "WARNING",
                    )
                    if isinstance(e, InvalidParameterValueError) and "pgroonga" in str(e):
                        pass
                    else:
                        raise BadInputError(f"Bad input: {e}") from e
            # Set updated at time
            if set_updated_at:
                await self._set_updated_at(conn)
        return self

    # Row Read Ops
    async def list_rows(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        order_by: list[str] | None = None,
        order_ascending: bool = True,
        columns: list[str] | None = None,
        where: str = "",
        search_query: str = "",
        search_columns: list[str] | None = None,
        remove_state_cols: bool = False,
    ) -> Page[dict[str, Any]]:
        """
        List rows with filtering and sorting.

        Args:
            limit (int | None, optional): Maximum number of rows to return. Defaults to None.
            offset (int, optional): Offset for pagination. Defaults to 0.
            order_by (list[str] | None, optional): Order the rows by these columns. Defaults to None (order by row ID).
            order_ascending (bool, optional): Order the rows in ascending order. Defaults to True.
            columns (list[str] | None, optional): A list of column names to include in the returned rows.
                Defaults to None (return all columns).
            where (str, optional): SQL where clause. Defaults to "" (no filter).
                It will be combined other filters using `AND`.
            search_query (str, optional): A string to search for within row data.
                The string is interpreted as both POSIX regular expression and literal string.
                Defaults to "".
            search_columns (list[str] | None, optional): A list of column names to search for search_query.
                Defaults to None (search all columns).
            remove_state_cols (bool, optional): If True, remove state columns. Defaults to False.

        Raises:
            ResourceNotFoundError: If the table or column(s) is not found.

        Returns:
            rows (Page[dict[str, Any]]): A page of row data dictionaries.
        """
        columns = self._filter_columns(columns, exclude_state=remove_state_cols)
        # Build SQL query
        params = []
        query = f"""
            SELECT {",".join([f'"{self.map_to_short_col_id[c]}"' for c in columns])}
            FROM "{self.schema_id}"."{self.short_table_id}"
        """
        total = f'SELECT COUNT("ID") FROM "{self.schema_id}"."{self.short_table_id}"'
        filters = []
        where = where.strip()
        if where:
            try:
                where = f"({validate_where_expr(where, id_map=self.map_to_short_col_id)})"
            except Exception as e:
                raise BadInputError(str(e)) from e
            filters.append(where)
        if search_query:
            _cols = search_columns or [
                col.column_id
                for col in self.column_metadata
                if not (
                    col.is_info_column
                    or col.is_file_column
                    or col.is_vector_column
                    or col.is_state_column
                )
            ]
            search_filters = []
            for c in _cols:
                c = self.map_to_short_col_id.get(c, None)
                if c is None:
                    continue
                # Literal (escaped) search
                params.append(re.escape(search_query))
                literal_expr = f'("{c}"::text ~* ${len(params)})'
                # Regex search
                params.append(search_query)
                regex_expr = f'("{c}"::text ~* ${len(params)})'
                search_filters.append(f"({literal_expr} OR {regex_expr})")
            filters.append(f"({' OR '.join(search_filters)})")
        if filters:
            query += f" WHERE {' AND '.join(filters)}"
            total += f" WHERE {' AND '.join(filters)}"
        async with GENTABLE_ENGINE.transaction() as conn:
            # Row count
            try:
                total = await conn.fetchval(total, *params)
            except UndefinedColumnError as e:
                raise ResourceNotFoundError(
                    f'One or more columns is not found in table "{self.table_id}".'
                ) from e
            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
            except (PostgresSyntaxError, UndefinedFunctionError) as e:
                raise BadInputError(f"Bad SQL statement: `{query}`") from e
            # Sorting
            order_direction = "ASC" if order_ascending else "DESC"
            order_clauses = []
            if order_by:
                for c in order_by:
                    cs = self.map_to_short_col_id.get(c, None)
                    if cs is None:
                        continue
                    if c in self.text_column_names:
                        order_clauses.append(f'LOWER("{cs}") {order_direction}')
                    else:
                        order_clauses.append(f'"{cs}" {order_direction}')
            order_clauses.append(f'"ID" {order_direction}')
            query += " ORDER BY " + ", ".join(order_clauses)
            # Pagination
            if limit:
                params.append(limit)
                query += f" LIMIT ${len(params)}"
            if offset:
                params.append(offset)
                query += f" OFFSET ${len(params)}"
            # Execute query
            try:
                rows = await conn.fetch(query, *params)
            except UndefinedColumnError as e:
                raise ResourceNotFoundError(
                    f'One or more columns is not found in table "{self.table_id}".'
                ) from e
            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
            except (PostgresSyntaxError, UndefinedFunctionError) as e:
                raise BadInputError(f"Bad SQL statement: `{query}`") from e
        # Map short column IDs back to long column IDs
        rows = [{self.map_to_long_col_id[k]: v for k, v in dict(row).items()} for row in rows]
        return Page[dict[str, Any]](
            items=rows,
            offset=offset,
            limit=total if limit is None else limit,
            total=total,
        )

    async def get_row(
        self,
        row_id: str,
        *,
        columns: list[str] | None = None,
        remove_state_cols: bool = False,
    ) -> dict[str, Any]:
        """
        Get a single row by its row ID.

        Args:
            row_id (str): ID of the row to be retrieved.
            columns (list[str] | None, optional): A list of column names to include in the returned rows.
                Defaults to None (return all columns).
            remove_state_cols (bool, optional): If True, remove state columns. Defaults to False.

        Raises:
            ResourceNotFoundError: If the table or row is not found.

        Returns:
            row (dict[str, Any]): The row data dictionary.
        """
        columns = self._filter_columns(columns, exclude_state=remove_state_cols)
        query = f"""
            SELECT {",".join([f'"{self.map_to_short_col_id[c]}"' for c in columns])}
            FROM "{self.schema_id}"."{self.short_table_id}"
        """
        # Get row
        row = None
        async with GENTABLE_ENGINE.transaction() as conn:
            try:
                row = await conn.fetchrow(f'{query} WHERE "ID" = $1', row_id)
            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
            if not row:
                raise ResourceNotFoundError(
                    f'Row "{row_id}" is not found in table "{self.table_id}".'
                )
        # Map short column ID back to long column ID
        row = {self.map_to_long_col_id[k]: v for k, v in dict(row).items()}
        return row

    def postprocess_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        include_state: bool = True,
    ) -> list[dict[str, Any]]:
        if not (isinstance(rows, list) and all(isinstance(r, dict) for r in rows)):
            # We raise TypeError here since this is a programming error
            raise TypeError("`rows` must be a list of dicts.")
        for row in rows:
            columns = list(row.keys())
            # Process data
            for col_name in columns:
                if col_name.endswith("_"):
                    continue
                col_value = row[col_name]
                # Process UUID and datetime
                if isinstance(col_value, UUID):
                    col_value = str(col_value)
                elif isinstance(col_value, datetime):
                    col_value = col_value.isoformat()
                else:
                    # Rounding logic
                    if float_decimals > 0 and isinstance(col_value, float):
                        col_value = round(col_value, float_decimals)
                    if isinstance(col_value, np.ndarray):
                        if vec_decimals < 0:
                            del row[col_name]
                            continue
                        if vec_decimals > 0:
                            col_value = [round(v, vec_decimals) for v in col_value.tolist()]
                        else:
                            col_value = col_value.tolist()
                # Process state
                state = row.get(f"{col_name}_", None)
                if state is None:
                    # Columns like "ID", "Updated at" do not have state
                    row[col_name] = col_value
                    continue
                try:
                    state.pop("is_null", None)  # Legacy attribute
                except Exception as e:
                    self._log(
                        f'Failed to process state of column "{col_name}" due to {repr(e)} {type(state)=} {state=}',
                        "WARNING",
                    )
                row[col_name] = {"value": col_value, **state} if include_state else col_value
            # Remove state
            for col_name in columns:
                if col_name.endswith("_"):
                    del row[col_name]
        return rows

    def check_multiturn_column(self, column_id: str) -> LLMGenConfig:
        cols = {c.column_id: c for c in self.column_metadata}
        multiturn_cols = [c.column_id for c in self.column_metadata if c.is_chat_column]
        column = cols.get(column_id, None)
        if column is None:
            raise ResourceNotFoundError(
                (
                    f'Table "{self.table_id}": Column "{column_id}" is not found. '
                    f"Available multi-turn columns: {multiturn_cols}"
                )
            )
        gen_config = column.gen_config
        if not (isinstance(gen_config, LLMGenConfig) and gen_config.multi_turn):
            raise ResourceNotFoundError(
                (
                    f'Table "{self.table_id}": Column "{column_id}" is not a multi-turn LLM column. '
                    f"Available multi-turn columns: {multiturn_cols}"
                )
            )
        return gen_config

    def interpolate_column(
        self,
        prompt: str,
        row: dict[str, Any],
    ) -> str | list[TextContent | S3Content]:
        """
        Replaces / interpolates column references in the prompt with their contents.

        Args:
            prompt (str): The original prompt with zero or more column references.
            row (dict[str, Any]): The row data containing column values.
            content_injection (bool, optional): If True, injects column content in the prompt.
                If False, user prompt will be unchanged. Defaults to True.

        Returns:
            content (str | list[TextContent | S3Content]): Message content with column references replaced.
        """
        column_map = {c.column_id: c for c in self.column_metadata}
        s3_contents: list[S3Content] = []

        def _replace(match: re.Match) -> str:
            col_id = match.group(1)
            try:
                # Referenced column is found
                col = column_map[col_id]
                col_data = row.get(col_id, None)
                if col.is_file_column:
                    # File references will be loaded and interpolated in `GenExecutor`
                    if col_data is None:
                        # If file URI is None, we treat it as no content injection
                        return ""
                    else:
                        # Return URI and retain column reference for downstream interpolation
                        s3_contents.append(S3Content(uri=row[col_id], column_name=col_id))
                        return f"${{{col_id}}}"
                # Non-file references can interpolate directly
                return str(col_data)
            except KeyError:
                # Referenced column is not found
                # Maybe injected contents accidentally contain references
                # We escape it here just in case
                return f"\\${{{col_id}}}"

        prompt = re.sub(GEN_CONFIG_VAR_PATTERN, _replace, prompt).strip()
        if len(s3_contents) == 0:
            return prompt
        return s3_contents + [TextContent(text=prompt)]

    async def get_conversation_thread(
        self,
        *,
        column_id: str,
        row_id: str = "",
        include_row: bool = True,
    ) -> ChatThreadResponse:
        """
        Get a conversation thread for a multi-turn LLM column.

        Args:
            column_id (str): ID of the multi-turn LLM column.
            row_id (str, optional): ID of the last row in the thread.
                Defaults to "" (export all rows)..
            include_row (bool, optional): Whether to include the row specified by `row_id`.
                Defaults to True.

        Returns:
            response (ChatThreadResponse): _description_
        """
        gen_config = self.check_multiturn_column(column_id)
        ref_col_ids = re.findall(GEN_CONFIG_VAR_PATTERN, gen_config.prompt)
        columns = ref_col_ids + [column_id]
        if row_id:
            where = '"ID" ' + (f"<= '{row_id}'" if include_row else f"< '{row_id}'")
        else:
            where = ""
        rows = (
            await self.list_rows(
                limit=None,
                offset=0,
                order_by=None,
                order_ascending=True,
                columns=columns,
                where=where,
                remove_state_cols=False,
            )
        ).items
        ref_cols = set(re.findall(GEN_CONFIG_VAR_PATTERN, gen_config.prompt))
        has_user_prompt = "User" in ref_cols
        thread = []
        if gen_config.system_prompt:
            thread.append(ChatThreadEntry.system(gen_config.system_prompt))
        for row in rows:
            if has_user_prompt:
                user_prompt = row.get("User", None) or None  # Map "" to None
            else:
                user_prompt = None
            row_id = str(row["ID"])
            thread.append(
                ChatThreadEntry.user(
                    self.interpolate_column(gen_config.prompt, row),
                    user_prompt=user_prompt,
                    row_id=row_id,
                )
            )
            thread.append(
                ChatThreadEntry.assistant(
                    row[column_id],
                    references=row.get(f"{column_id}_", {}).get("references", None),
                    row_id=row_id,
                )
            )
        return ChatThreadResponse(thread=thread, column_id=column_id)

    @staticmethod
    def _tokenize_regex_simple(text):
        tokens = []
        for match in TOKEN_PATTERN.finditer(text):
            # Figure out which group matched to determine category and get the string
            if match.group(1):  # Digits
                token_str = match.group(1)
                tokens.append(token_str)
            elif match.group(2):  # Letters
                token_str = match.group(2).lower()  # Lowercase letters
                tokens.append(token_str)
            elif match.group(3):  # Hanzi
                token_str = match.group(3)
                tokens.append(token_str)  # Append Hanzi directly
            elif match.group(4):  # Other
                token_str = match.group(4)
                tokens.append(token_str)  # Append other char directly
        return tokens

    @staticmethod
    def _bm25_ranking(
        fts_results: list[dict[str, Any]],
        *,
        query: str,
        text_column_names: list[str],
        weights: list[int] | None = None,
        ascending: bool = False,
    ) -> list[dict[str, Any]]:
        corpus = [res[col] for res in fts_results for col in text_column_names]
        tokenizer = bm25s.tokenization.Tokenizer(
            splitter=GenerativeTableCore._tokenize_regex_simple,
            stopwords=[
                "english",
            ],
            stemmer=stemmer.stem,
        )
        corpus = ["" if c is None else c for c in corpus]
        corpus_tokens = tokenizer.tokenize(corpus, show_progress=False)
        retriever = bm25s.BM25(backend="numpy")
        retriever.index(corpus_tokens, show_progress=False)
        query_tokens = tokenizer.tokenize([query], show_progress=False)
        results, scores = retriever.retrieve(
            query_tokens, k=len(corpus), show_progress=False, n_threads=1, sorted=True
        )
        # Reshape scores into (n_docs, n_columns) and apply weights
        scores_reshaped = scores[0, results.argsort()].reshape(-1, len(text_column_names))
        if weights:
            scores_reshaped *= np.array(weights)
        # Sum scores across columns
        doc_scores = scores_reshaped.sum(axis=1)

        # Get sorted indices (ascending or descending)
        sorted_indices = np.argsort(doc_scores)
        if not ascending:
            sorted_indices = sorted_indices[::-1]  # Reverse for descending

        # Build sorted results with scores
        ranked_results = [fts_results[i] for i in sorted_indices]

        for res, score in zip(ranked_results, doc_scores[sorted_indices], strict=True):
            res["score"] = float(score)  # Convert numpy.float32 to native Python float
        return ranked_results

    async def fts_search(
        self,
        query: str,
        *,
        weights: dict[str, int] | None = None,
        limit: int = 100,
        offset: int = 0,
        remove_state_cols: bool = False,
        force_use_index: bool = False,
        use_bm25_ranking: bool = False,
        explain: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Perform full-text search across all text columns using pgroonga.

        Args:
            query (str): Search query string.
            limit (int, optional): Maximum number of rows to return. Defaults to 100.
            offset (int, optional): Offset for pagination. Defaults to 0.
            remove_state_cols (bool, optional): If True, remove state columns. Defaults to False.
            force_use_index (bool, optional): If True, force using pgroonga index. Defaults to False.
            use_bm25_ranking (bool, optional): If True, use BM25 ranking. Defaults to False.
            explain (bool, optional): If True, return explain query. Defaults to False.

        Raises:
            ResourceNotFoundError: If the table or column(s) is not found.

        Returns:
            rows (list[dict[str, Any]]): List of row data dictionaries.
        """
        t0 = perf_counter()
        if weights is None:
            weights = [1 for _ in self.text_column_names]
        else:
            weights = [weights.get(n, 1) for n in self.text_column_names]
        if len(weights) == 0:  # if no text columns fts return empty list
            return []
        # Build query
        select_cols = self.data_table_model.get_column_ids(exclude_state=remove_state_cols)
        # Do not enforce idx like: ($1, ARRAY{weights}, '{fts_index_id(self.table_id)}')::pgroonga_full_text_search_condition
        # Pg planner will choose the best plan to run the query efficiently (for smaller number of rows might just use seq scan)
        # for duplicated table with CTAS, if number of rows is small it might always use seq scan regardless, so forcing the index will fail
        # tested a simple 3 col table, if number rows is 1000 then even with NULL index will be used.
        index_name = f"'{fts_index_id(self.table_id)}'" if force_use_index else "NULL"
        stmt = f"""
            SELECT
                {",".join(f'"{self.map_to_short_col_id[c]}"' for c in select_cols)},
                pgroonga_score(tableoid, ctid) AS score
            FROM
                "{self.schema_id}"."{self.short_table_id}"
            WHERE
                ARRAY[{", ".join(f'"{self.map_to_short_col_id[n]}"' for n in self.text_column_names)}] &@~
                ($1, ARRAY{weights}, {index_name})::pgroonga_full_text_search_condition
            ORDER BY score DESC
            LIMIT $2 OFFSET $3
        """
        if explain:
            stmt = f"EXPLAIN ANALYZE {stmt}"
        async with GENTABLE_ENGINE.transaction() as conn:
            # Execute query
            try:
                rows = await conn.fetch(stmt, query, limit, offset)
            except UndefinedColumnError as e:
                raise ResourceNotFoundError(
                    f'One or more columns is not found in table "{self.table_id}".'
                ) from e
            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
            except DataError as e:
                raise BadInputError(f"Bad input: {e}") from e
        # Map short column IDs back to long column IDs
        # Keys contain non-column IDs like "score"
        results = [
            {self.map_to_long_col_id.get(k, k): v for k, v in dict(row).items()} for row in rows
        ]
        if len(results) > 0 and use_bm25_ranking:
            results = self._bm25_ranking(
                fts_results=results,
                query=query,
                text_column_names=self.text_column_names,
                weights=weights,
                ascending=False,
            )
        self._log(f"FTS search took t={(perf_counter() - t0) * 1e3:,.2f} ms.")
        return results

    async def vector_search(
        self,
        query: str,
        *,
        embedding_fn: Callable[[str, str], list[float] | Awaitable[list[float]]],
        vector_column_names: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        remove_state_cols: bool = False,
        explain: bool = False,
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search using cosine distance.

        Args:
            query (str): Search query string.
            embedding_fn (Callable[[str, str], list[float] | Awaitable[list[float]]]): Embedding function that
                takes two string parameters (`str`, `str`) and returns a list of floats.
                Can be either synchronous or asynchronous.
                The first argument is the model ID and the second argument is the query, ie `embedding_fn(model, query)`.
            vector_column_names (list[str] | None, optional): List of vector column name to search.
                Defaults to None (all vector columns are used).
            limit (int, optional): Maximum number of rows to return. Defaults to 100.
            offset (int, optional): Offset for pagination. Defaults to 0.
            remove_state_cols (bool, optional): If True, remove state columns. Defaults to False.
            explain (bool, optional): If True, return explain query. Defaults to False.

        Raises:
            TypeError: If `vector_column_names` is not a list of strings.
            BadInputError: If not all columns are vector columns.
            ResourceNotFoundError: If the table or column(s) is not found.

        Returns:
            rows (list[dict[str, Any]]): List of row data dictionaries.
        """
        t0 = perf_counter()
        if vector_column_names is None:
            vector_column_names = self.vector_column_names
        else:
            if not (
                isinstance(vector_column_names, list)
                and all(isinstance(n, str) for n in vector_column_names)
            ):
                # We raise TypeError here since this is a programming error
                raise TypeError("`vector_column_names` must be a list of strings.")
            # Ensure all columns are vector columns
            if len(invalid_cols := set(vector_column_names) - set(self.vector_column_names)) > 0:
                raise BadInputError(
                    (
                        f'Table "{self.table_id}": All columns to be searched must be vector columns. '
                        f"Invalid columns: {list(invalid_cols)}"
                    )
                )
        if len(vector_column_names) == 0:
            return []
        # Get query vectors
        models: list[str] = list(
            {
                getattr(c.gen_config, "embedding_model", "")
                for c in self.column_metadata
                if c.column_id in vector_column_names
            }
        )
        self._log(f"Embedding using models: {models}")
        if iscoroutinefunction(embedding_fn):
            query_vectors = await asyncio.gather(*[embedding_fn(m, query) for m in models])
        else:
            with ThreadPoolExecutor() as executor:
                query_vectors = list(executor.map(embedding_fn, models, [query] * len(models)))
        query_vectors = {m: v for m, v in zip(models, query_vectors, strict=True)}
        self._log(f"Embedding using {models} took t={(perf_counter() - t0) * 1e3:,.2f} ms.")

        t0 = perf_counter()
        columns = []
        for c in self.column_metadata:
            if c.column_id not in vector_column_names:
                continue
            vec = query_vectors[getattr(c.gen_config, "embedding_model", "")]
            if len(vec) != c.vlen:
                raise BadInputError(
                    f"Vector length mismatch for column {c.column_id}. Expected {c.vlen}, got {len(vec)}."
                )
            columns.append((self.map_to_short_col_id[c.column_id], vec))
        if len(columns) == 0:
            return []
        # CTE query
        # https://learn.microsoft.com/en-us/answers/questions/2118689/how-to-search-across-multiple-vector-indexes-in-po
        subqueries = [
            f"""
            "{col_id}_results" AS (
                SELECT
                    "ID", ("{col_id}" <=> ${i + 1}) AS score
                FROM
                    "{self.schema_id}"."{self.short_table_id}"
                ORDER BY
                    score ASC
        )
        """
            for i, (col_id, _) in enumerate(columns)
        ]
        select_cols = self.data_table_model.get_column_ids(exclude_state=remove_state_cols)
        selects = [f't."{self.map_to_short_col_id[col]}"' for col in select_cols]
        joins = [
            f'JOIN "{col_id}_results" ON "{columns[0][0]}_results"."ID" = "{col_id}_results"."ID"'
            for col_id, _ in columns[1:]
        ]
        join_expr = "\n".join(joins)
        stmt = f"""
            WITH
                {", ".join(subqueries)}
            SELECT
                {", ".join(selects)},
                {" + ".join(f'"{col_id}_results".score' for col_id, _ in columns)} AS score
            FROM
                "{columns[0][0]}_results"
            {join_expr}
            JOIN
                "{self.schema_id}"."{self.short_table_id}" t
            ON
                t."ID" = "{columns[0][0]}_results"."ID"
            ORDER BY
                score ASC
            LIMIT ${len(columns) + 1} OFFSET ${len(columns) + 2};
        """
        if explain:
            stmt = f"EXPLAIN ANALYZE {stmt}"
        async with GENTABLE_ENGINE.transaction() as conn:
            # Execute query
            try:
                rows = await conn.fetch(stmt, *[vec for _, vec in columns], limit, offset)
            except UndefinedColumnError as e:
                raise ResourceNotFoundError(
                    f'One or more columns is not found in table "{self.table_id}".'
                ) from e
            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
            except DataError as e:
                raise BadInputError(f"Bad input: {e}") from e
        # Map short column IDs back to long column IDs
        # Keys contain non-column IDs like "score"
        results = [
            {self.map_to_long_col_id.get(k, k): v for k, v in dict(row).items()} for row in rows
        ]
        self._log(f"Vector search took t={(perf_counter() - t0) * 1e3:,.2f} ms.")
        return results

    @staticmethod
    def _reciprocal_rank_fusion(
        search_results: list[list[dict]],
        result_key: str = "ID",
        K: int = 60,
    ) -> list[dict]:
        """
        Perform reciprocal rank fusion to merge the rank of the search results
        (arbitrary number of results and can vary in length).

        Args:
            search_results (list[list[dict]]): List of search results,
                where each result is a sorted list of dict (descending order of closeness).
            result_key (str, optional): Dictionary key of each item's ID. Defaults to "ID".
            K (int, optional): Const for reciprocal rank fusion. Defaults to 60.
        Return:
            rows (list[dict]): A list of dict of original result with the rrf scores (higher scores, higher ranking).
        """
        rrf_scores = defaultdict(lambda: {"rrf_score": 0.0})
        for search_result in search_results:
            for rank, result in enumerate(search_result, start=1):
                result_id = result[result_key]
                rrf_scores[result_id]["rrf_score"] += 1.0 / (rank + K)
                rrf_scores[result_id].update(result)
        sorted_rrf = sorted(rrf_scores.values(), key=lambda x: x["rrf_score"], reverse=True)
        return sorted_rrf

    async def hybrid_search(
        self,
        fts_query: str,
        vs_query: str,
        *,
        embedding_fn: Callable[[str, str], Awaitable[list[float] | np.ndarray]],
        vector_column_names: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        use_bm25_ranking: bool = True,
        remove_state_cols: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Perform vector similarity search using cosine distance.

        Args:
            fts_query (str): FTS search query string.
            vs_query (str): Vector search query string.
            embedding_fn (Callable[[str, str], Awaitable[list[float] | np.ndarray]]): Async embedding function that
                takes two string parameters (`str`, `str`) and returns a NumPy array or a list of floats.
                The first argument is the model ID and the second argument is the query, ie `embedding_fn(model, query)`.
                The returned NumPy array should be one-dimensional (ie a single vector).
            vector_column_names (list[str] | None, optional): List of vector column name to search.
                Defaults to None (all vector columns are used).
            limit (int, optional): Maximum number of rows to return from FTS and vector searches.
                Note that this means that hybrid search can return more than `limit` rows. Defaults to 100.
            offset (int, optional): Offset for pagination. Defaults to 0.
            use_bm25_ranking (bool, optional): If True, use BM25 ranking. Defaults to True.
            remove_state_cols (bool, optional): If True, remove state columns. Defaults to False.

        Raises:
            BadInputError: If not all columns are vector columns.
            ResourceNotFoundError: If the table or column(s) is not found.

        Returns:
            rows (list[dict[str, Any]]): List of row data dictionaries.
        """
        t0 = perf_counter()
        fts_task = self.fts_search(
            query=fts_query,
            limit=limit,
            offset=offset,
            use_bm25_ranking=use_bm25_ranking,
            remove_state_cols=remove_state_cols,
        )
        vs_task = self.vector_search(
            query=vs_query,
            embedding_fn=embedding_fn,
            vector_column_names=vector_column_names,
            limit=limit,
            offset=offset,
            remove_state_cols=remove_state_cols,
        )
        # Run both tasks concurrently and wait for them to complete
        # asyncio.gather returns results in the order the tasks were passed
        fts_result, vs_result = await asyncio.gather(fts_task, vs_task)
        search_results = [fts_result, vs_result]
        # RRF
        rows = self._reciprocal_rank_fusion(search_results)
        self._log(f"Hybrid search took t={(perf_counter() - t0) * 1e3:,.2f} ms.")
        return rows

    def rows_to_documents(self, rows: list[dict[str, Any]]) -> list[str]:
        cols = {c.column_id for c in self.column_metadata if not c.is_state_column}
        documents = [
            (
                f"Title: {r.get('Title', '')}\nContent: {r.get('Text', '')}\n"
                + "\n".join(
                    f"{k}: {v}"
                    for k, v in r.items()
                    if k not in self.FIXED_COLUMN_IDS and k in cols
                )
            )
            for r in rows
        ]
        return documents

    # Row Update Ops
    async def update_rows(
        self,
        updates: dict[str, dict[str, Any]],
        *,
        ignore_state_columns: bool = True,
    ) -> None:
        """
        Update multiple rows in the Generative Table.

        Args:
            updates (dict[str, dict[str, Any]]): A dictionary mapping row ID to update data.
                Each update data is a dictionary of column name to value.
            ignore_state_columns (bool, optional): Whether to ignore state columns. Defaults to True.

        Raises:
            TypeError: If the data is not a list of dictionaries.
            BadInputError: If any row does not have an "ID" field.
            ResourceNotFoundError: If the table is not found.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        if not (
            isinstance(updates, dict) and all(isinstance(row, dict) for row in updates.values())
        ):
            # We raise TypeError here since this is a programming error
            raise TypeError("`updates` must be a dict of dicts.")
        # Filter out non-existent fields
        columns = set(
            self.data_table_model.get_column_ids(
                exclude_info=True,
                exclude_state=ignore_state_columns,
            )
        )
        # Validate and convert all rows
        try:
            updates = {
                row_id: self._validate_row_data(
                    {k: v for k, v in row.items() if k in columns and k.lower() != "id"}
                ).model_dump(exclude_unset=True)
                for row_id, row in updates.items()
            }
        except ValidationError as e:
            raise BadInputError(f"Input data contains errors: {e}") from e
        async with GENTABLE_ENGINE.transaction() as conn:
            try:
                for row_id, update in updates.items():
                    if len(update) == 0:
                        continue
                    _cols = [k for k in update.keys()]
                    # Build SQL statement
                    set_expr = ", ".join(
                        f'"{self.map_to_short_col_id[col]}" = ${i + 1}'
                        for i, col in enumerate(_cols)
                    )
                    query = (
                        f'UPDATE "{self.schema_id}"."{self.short_table_id}" '
                        f'SET "Updated at" = statement_timestamp(), {set_expr} '
                        f'WHERE "ID" = ${len(_cols) + 1}'
                    )
                    # Update rows
                    await conn.execute(query, *(update[col] for col in _cols), row_id)
                # Set updated at time
                await self._set_updated_at(conn)
            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
            except DataError as e:
                raise BadInputError(f"Bad input: {e}") from e

    # Row Delete Ops
    async def delete_rows(
        self,
        *,
        row_ids: list[str] | None = None,
        where: str = "",
    ) -> Self:
        """
        Delete one or more rows from the Generative Table.

        Args:
            row_ids (list[str] | None, optional): List of row IDs to be deleted.
                Defaults to None (match rows using `where`).
            where (str, optional): SQL where clause. Defaults to "" (no filter).
                It will be combined with `row_ids` using `AND`.

        Raises:
            ResourceNotFoundError: If the table is not found.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        if row_ids is None:
            row_ids = []
        if not (isinstance(row_ids, list) and all(isinstance(i, (str, UUID)) for i in row_ids)):
            # We raise TypeError here since this is a programming error
            raise TypeError("`row_ids` must be a list of strings.")

        # Build SQL query
        filters = []
        if row_ids:
            filters.append('("ID" = $1)')
            row_ids = [(row_id,) for row_id in row_ids]
        where = where.strip()
        if where:
            try:
                where = f"({validate_where_expr(where, id_map=self.map_to_short_col_id)})"
            except Exception as e:
                raise BadInputError(str(e)) from e
            filters.append(where)
        if len(filters) == 0:
            raise BadInputError("Either `row_ids` or `where` must be provided.")
        async with GENTABLE_ENGINE.transaction() as conn:
            try:
                sql = f'DELETE FROM "{self.schema_id}"."{self.short_table_id}" WHERE {" AND ".join(filters)}'
                if row_ids:
                    await conn.executemany(sql, row_ids)
                else:
                    await conn.execute(sql)
                # Set updated at time
                await self._set_updated_at(conn)
            except UndefinedTableError as e:
                raise ResourceNotFoundError(f'Table "{self.table_id}" is not found.') from e
            except PostgresSyntaxError as e:
                raise BadInputError(f"Bad SQL statement: `{sql}`") from e
            return self


class ActionTable(GenerativeTableCore):
    TABLE_TYPE = TableType.ACTION

    @override
    @classmethod
    async def drop_schema(
        cls,
        *,
        project_id: str,
    ) -> None:
        """
        Drops the project's schema along with all data tables.
        """
        return await super().drop_schema(
            project_id=project_id,
            table_type=cls.TABLE_TYPE,
        )

    @override
    @classmethod
    async def create_table(
        cls,
        *,
        project_id: str,
        table_metadata: TableMetadata,
        column_metadata_list: list[ColumnMetadata],
    ) -> Self:
        """
        Create a new Action Table with default prompts (if prompts are not provided).

        Args:
            project_id (str): Project ID.
            table_metadata (TableMetadata): Table metadata.
            column_metadata_list (list[ColumnMetadata]): List of column metadata.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        return await cls._create_table(
            project_id=project_id,
            table_type=cls.TABLE_TYPE,
            table_metadata=table_metadata,
            column_metadata_list=column_metadata_list,
            set_default_prompts=True,
        )

    @classmethod
    async def duplicate_table(
        cls,
        *,
        project_id: str,
        table_id_src: str,
        table_id_dst: TableName | None = None,
        include_data: bool = True,
        create_as_child: bool = False,
        created_by: str | None = None,
    ) -> Self:
        """
        Duplicate an existing table including schema, data and metadata.

        Args:
            project_id (str): Project ID.
            table_id_src (str): Name of the table to be duplicated.
            table_id_dst (str | None, optional): Name for the new table.
                Defaults to None (automatically find the next available table name).
            include_data (bool, optional): If True, include data. Defaults to True.
            create_as_child (bool, optional): If True, create the new table as a child of the source table.
                Defaults to False.
            created_by (str | None, optional): User ID of the user who created the table.
                Defaults to None.

        Raises:
            BadInputError: If `table_id_dst` is not None or a non-empty string.
            ResourceNotFoundError: If table or column metadata cannot be found.

        Returns:
            self (GenerativeTableCore): The duplicated table instance.
        """
        return await super().duplicate_table(
            project_id=project_id,
            table_type=cls.TABLE_TYPE,
            table_id_src=table_id_src,
            table_id_dst=table_id_dst,
            include_data=include_data,
            create_as_child=create_as_child,
            created_by=created_by,
        )

    # Read
    @classmethod
    async def open_table(
        cls,
        *,
        project_id: str,
        table_id: str,
        created_by: str | None = None,
        request_id: str = "",
    ) -> Self:
        """
        Open an existing table.

        Args:
            project_id (str): Project ID.
            table_id (str): Name of the table.
            created_by (str | None, optional): User who created the table.
                If provided, will check if the table was created by the user. Defaults to None (any user).
            request_id (str, optional): Request ID for logging. Defaults to "".

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        return await super().open_table(
            project_id=project_id,
            table_type=cls.TABLE_TYPE,
            table_id=table_id,
            created_by=created_by,
            request_id=request_id,
        )

    @classmethod
    async def list_tables(
        cls,
        *,
        project_id: str,
        limit: int | None = 100,
        offset: int = 0,
        order_by: Literal["id", "updated_at"] = "updated_at",
        order_ascending: bool = True,
        created_by: str | None = None,
        parent_id: str | None = None,
        search_query: str = "",
        search_columns: list[str] = None,
        count_rows: bool = False,
    ) -> Page[TableMetaResponse]:
        """
        List tables.

        Args:
            project_id (str): Project ID.
            limit (int | None, optional): Maximum number of tables to return.
                Defaults to 100. Pass None to return all tables.
            offset (int, optional): Offset for pagination. Defaults to 0.
            order_by (Literal["id", "updated_at"], optional): Sort tables by this attribute.
                Defaults to "updated_at".
            order_ascending (bool, optional): Whether to sort by ascending order.
                Defaults to True.
            created_by (str | None, optional): Return tables created by this user.
                Defaults to None (return all tables).
            parent_id (str | None, optional): Parent ID of tables to return.
                Defaults to None (no parent ID filtering).
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
            search_query (str, optional): A string to search for within table names.
                The string is interpreted as both POSIX regular expression and literal string.
                Defaults to "".
            search_columns (list[str], optional): List of columns to search within.
                Defaults to None (search table ID).
            count_rows (bool, optional): Whether to count the rows of the tables.
                Defaults to False.

        Returns:
            tables (Page[TableMetaResponse]): List of tables.
        """
        return await super().list_tables(
            project_id=project_id,
            table_type=cls.TABLE_TYPE,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_ascending=order_ascending,
            created_by=created_by,
            parent_id=parent_id,
            search_query=search_query,
            search_columns=search_columns,
            count_rows=count_rows,
        )

    @classmethod
    async def import_table(
        cls,
        *,
        project_id: str,
        source: str | Path | BinaryIO,
        table_id_dst: TableName | None,
        reupload_files: bool = True,
        progress_key: str = "",
        verbose: bool = False,
    ) -> Self:
        """
        Recreate a table (data and metadata) from a Parquet file.

        Args:
            project_id (str): Project ID.
            input_path (str | Path): The path to the import file.
            table_id_dst (TableName | None): Name or ID of the new table.
                If None, the table ID in the Parquet metadata will be used.
            reupload_files (bool, optional): If True, will reupload files to S3 with new URI.
                Otherwise skip reupload and keep the original S3 paths for file columns.
                Defaults to True.
            progress_key (str, optional): Progress publish key. Defaults to "" (disabled).
            verbose (bool, optional): If True, will produce verbose logging messages.
                Defaults to False.

        Raises:
            ResourceExistsError: If the table already exists.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        return await super().import_table(
            project_id=project_id,
            table_type=cls.TABLE_TYPE,
            source=source,
            table_id_dst=table_id_dst,
            reupload_files=reupload_files,
            progress_key=progress_key,
            verbose=verbose,
        )


class KnowledgeTable(ActionTable):
    TABLE_TYPE = TableType.KNOWLEDGE
    FIXED_COLUMN_IDS = [
        "ID",
        "Updated at",
        "Title",
        "Title Embed",
        "Text",
        "Text Embed",
        "File ID",
        "Page",
    ]

    @override
    @classmethod
    async def create_table(
        cls,
        *,
        project_id: str,
        table_metadata: TableMetadata,
        column_metadata_list: list[ColumnMetadata],
        embedding_model: str,
    ) -> Self:
        """
        Create a new Knowledge Table with default prompts (if prompts are not provided).

        Args:
            project_id (str): Project ID.
            table_type (str): Table type.
            table_metadata (TableMetadata): Table metadata.
            column_metadata_list (list[ColumnMetadata]): List of column metadata.
            embedding_model (str): ID of the embedding model.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        table_id = table_metadata.table_id
        # Fetch model config
        project = await cls._fetch_project(project_id)
        try:
            # If model is empty string, select a model based on capabilities
            if embedding_model.strip() == "":
                model = await cls._fetch_model_with_capabilities(
                    capabilities=[str(ModelCapability.EMBED)],
                    organization_id=project.organization_id,
                )
            else:
                model = await cls._fetch_model(embedding_model, project.organization_id)
        except ResourceNotFoundError as e:
            raise BadInputError(
                f'Table "{table_id}": Model "{embedding_model}" is not found.'
            ) from e
        # Use `dimensions` if specified; otherwise use `size`
        embed_size = model.final_embedding_size
        fixed_columns = [
            ColumnMetadata(
                table_id=table_id,
                column_id="Title",
                dtype=ColumnDtype.STR,
            ),
            ColumnMetadata(
                table_id=table_id,
                column_id="Title Embed",
                dtype=ColumnDtype.FLOAT,
                vlen=embed_size,
                gen_config=EmbedGenConfig(
                    embedding_model=model.id,
                    source_column="Title",
                ),
            ),
            ColumnMetadata(
                table_id=table_id,
                column_id="Text",
                dtype=ColumnDtype.STR,
            ),
            ColumnMetadata(
                table_id=table_id,
                column_id="Text Embed",
                dtype=ColumnDtype.FLOAT,
                vlen=embed_size,
                gen_config=EmbedGenConfig(
                    embedding_model=model.id,
                    source_column="Text",
                ),
            ),
            ColumnMetadata(
                table_id=table_id,
                column_id="File ID",
                dtype=ColumnDtype.STR,
            ),
            ColumnMetadata(
                table_id=table_id,
                column_id="Page",
                dtype=ColumnDtype.INT,
            ),
        ]
        return await cls._create_table(
            project_id=project_id,
            table_type=cls.TABLE_TYPE,
            table_metadata=table_metadata,
            column_metadata_list=fixed_columns + column_metadata_list,
            set_default_prompts=True,
        )

    async def update_gen_config(
        self,
        update_mapping: dict[str, DiscriminatedGenConfig | None],
        *,
        allow_nonexistent_refs: bool = False,
    ) -> Self:
        """
        Update the generation configuration for a column.

        Args:
            update_mapping (dict[str, DiscriminatedGenConfig]): Mapping of column IDs to new generation configurations.
            allow_nonexistent_refs (bool, optional): Ignore non-existent column and Knowledge Table references.
                Otherwise will raise an error. Useful when importing old tables and performing maintenance.
                Defaults to False.

        Raises:
            ResourceNotFoundError: If the column is not found.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        # "Title Embed" and "Text Embed" columns must always have gen config
        filtered = {
            column_id: config
            for column_id, config in update_mapping.items()
            if not (
                column_id.lower() in {"title embed", "text embed"}
                and not isinstance(config, EmbedGenConfig)
            )
        }

        if not filtered:
            return self

        return await super().update_gen_config(
            update_mapping=filtered, allow_nonexistent_refs=allow_nonexistent_refs
        )

    async def update_rows(
        self,
        updates: dict[str, dict[str, Any]],
        *,
        ignore_state_columns: bool = True,
    ) -> None:
        """
        Update multiple rows in the Generative Table.

        Args:
            updates (dict[str, dict[str, Any]]): A dictionary mapping row ID to update data.
                Each update data is a dictionary of column name to value.
            ignore_state_columns (bool, optional): Whether to ignore state columns. Defaults to True.

        Raises:
            TypeError: If the data is not a list of dictionaries.
            BadInputError: If any row does not have an "ID" field.
            ResourceNotFoundError: If the table is not found.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        return await super().update_rows(
            updates=updates, ignore_state_columns=ignore_state_columns
        )


class ChatTable(ActionTable):
    TABLE_TYPE = TableType.CHAT
    FIXED_COLUMN_IDS = [
        "ID",
        "Updated at",
        "User",
    ]

    @override
    @classmethod
    async def create_table(
        cls,
        *,
        project_id: str,
        table_metadata: TableMetadata,
        column_metadata_list: list[ColumnMetadata],
    ) -> Self:
        """
        Create a new Chat Table with default prompts (if prompts are not provided).

        Args:
            project_id (str): Project ID.
            table_type (str): Table type.
            table_metadata (TableMetadata): Table metadata.
            column_metadata_list (list[ColumnMetadata]): List of column metadata.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        table_id = table_metadata.table_id
        for col in column_metadata_list:
            if col.column_id.lower() == "ai":
                if isinstance(col.gen_config, LLMGenConfig):
                    col.gen_config.multi_turn = True
                else:
                    col.gen_config = LLMGenConfig(multi_turn=True)
        num_chat_cols = len([c for c in column_metadata_list if c.is_chat_column])
        if num_chat_cols == 0:
            raise BadInputError(
                f'Chat Table "{table_id}" must have at least one multi-turn column.'
            )
        return await cls._create_table(
            project_id=project_id,
            table_type=cls.TABLE_TYPE,
            table_metadata=table_metadata,
            column_metadata_list=column_metadata_list,
            set_default_prompts=True,
        )

    async def update_gen_config(
        self,
        update_mapping: dict[str, DiscriminatedGenConfig | None],
        *,
        allow_nonexistent_refs: bool = False,
    ) -> Self:
        """
        Update the generation configuration for a column.

        Args:
            update_mapping (dict[str, DiscriminatedGenConfig]): Mapping of column IDs to new generation configurations.
            allow_nonexistent_refs (bool, optional): Ignore non-existent column and Knowledge Table references.
                Otherwise will raise an error. Useful when importing old tables and performing maintenance.
                Defaults to False.

        Raises:
            ResourceNotFoundError: If the column is not found.

        Returns:
            self (GenerativeTableCore): The table instance.
        """
        for column_id, config in update_mapping.items():
            if column_id.lower() == "ai" and isinstance(config, LLMGenConfig):
                config.multi_turn = True  # in-place mutation is fine
        filtered = {
            column_id: config
            for column_id, config in update_mapping.items()
            if not (column_id.lower() == "ai" and not isinstance(config, LLMGenConfig))
        }
        return await super().update_gen_config(
            update_mapping=filtered, allow_nonexistent_refs=allow_nonexistent_refs
        )

    async def drop_columns(
        self,
        column_ids: list[str],
    ) -> Self:
        """
        Drop columns from the Chat Table.

        Args:
            column_ids (list[str]): List of column IDs to drop.

        Raises:
            ResourceNotFoundError: If any of the columns is not found.
        """
        num_chat_cols = len(
            [c for c in self.column_metadata if c.column_id not in column_ids and c.is_chat_column]
        )
        if num_chat_cols == 0:
            raise BadInputError(
                f'Chat Table "{self.table_id}" must have at least one multi-turn column after column drop.'
            )
        return await super().drop_columns(column_ids)
