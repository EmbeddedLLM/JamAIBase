from datetime import datetime
from enum import StrEnum
from os.path import splitext
from typing import Annotated, Any, Generic, Literal, Self, Type, TypeVar

import pandas as pd
import pyarrow as pa
from fastapi import File, UploadFile
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    field_validator,
    model_validator,
)

from jamaibase import types as t
from jamaibase.types import (  # noqa: F401
    CITATION_PATTERN,
    DEFAULT_MUL_LANGUAGES,
    EXAMPLE_CHAT_MODEL_IDS,
    EXAMPLE_EMBEDDING_MODEL_IDS,
    EXAMPLE_RERANKING_MODEL_IDS,
    AgentMetaResponse,
    AudioContent,
    AudioContentData,
    AudioResponse,
    CellCompletionResponse,
    CellReferencesResponse,
    ChatCompletionChoice,
    ChatCompletionChunkResponse,
    ChatCompletionDelta,
    ChatCompletionMessage,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatContent,
    ChatContentS3,
    ChatEntry,
    ChatRequest,
    ChatRole,
    ChatThreadEntry,
    ChatThreadResponse,
    ChatThreadsResponse,
    Chunk,
    CloudProvider,
    CodeGenConfig,
    CodeInterpreterTool,
    ColumnDropRequest,
    ColumnReorderRequest,
    CompletionUsageDetails,
    ConversationCreateRequest,
    ConversationMetaResponse,
    ConversationThreadsResponse,
    CSVDelimiter,
    DatetimeUTC,
    DBStorageUsageData,
    Deployment_,
    DeploymentCreate,
    DeploymentRead,
    DeploymentUpdate,
    DiscriminatedGenConfig,
    EgressUsageData,
    EmbeddingModelPrice,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingResponseData,
    EmbeddingUsage,
    EmbedGenConfig,
    EmbedUsageData,
    EmptyIfNoneStr,
    FilePath,
    FileStorageUsageData,
    FileUploadResponse,
    Function,
    FunctionCall,
    FunctionParameters,
    GenConfigUpdateRequest,
    GetURLRequest,
    GetURLResponse,
    Host,
    ImageContent,
    ImageContentData,
    JSONInput,
    JSONInputBin,
    JSONOutput,
    JSONOutputBin,
    LanguageCodeList,
    LLMGenConfig,
    LLMModelPrice,
    LlmUsageData,
    LogProbs,
    LogProbToken,
    LogQueryResponse,
    MessageAddRequest,
    MessagesRegenRequest,
    MessageUpdateRequest,
    Metric,
    ModelCapability,
    ModelConfig_,
    ModelConfigCreate,
    ModelConfigRead,
    ModelConfigUpdate,
    ModelInfo,
    ModelInfoListResponse,
    ModelInfoRead,
    ModelPrice,
    ModelProvider,
    ModelType,
    MultiRowCompletionResponse,
    MultiRowDeleteRequest,
    NullableStr,
    OkResponse,
    OnPremProvider,
    OrganizationCreate,
    OrganizationUpdate,
    OrgMember_,
    OrgMemberCreate,
    OrgMemberRead,
    OrgMemberUpdate,
    Page,
    PasswordChangeRequest,
    PasswordLoginRequest,
    PaymentState,
    PositiveInt,
    PositiveNonZeroInt,
    PricePlan_,
    PricePlanCreate,
    PricePlanRead,
    PricePlanUpdate,
    PriceTier,
    Product,
    Products,
    ProductType,
    Progress,
    ProgressStage,
    ProgressState,
    Project_,
    ProjectCreate,
    ProjectKey_,
    ProjectKeyCreate,
    ProjectKeyRead,
    ProjectKeyUpdate,
    ProjectMember_,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    ProjectUpdate,
    PromptUsageDetails,
    PythonGenConfig,
    RAGParams,
    RankedRole,
    References,
    RerankingApiVersion,
    RerankingBilledUnits,
    RerankingData,
    RerankingMeta,
    RerankingMetaUsage,
    RerankingModelPrice,
    RerankingRequest,
    RerankingResponse,
    RerankingUsage,
    RerankUsageData,
    Role,
    RowCompletionResponse,
    S3Content,
    SanitisedMultilineStr,
    SanitisedNonEmptyStr,
    SanitisedStr,
    SearchRequest,
    SecretCreate,
    SecretRead,
    SecretUpdate,
    SplitChunksParams,
    SplitChunksRequest,
    StripeEventData,
    StripePaymentInfo,
    TableDataImportRequest,
    TableImportProgress,
    TableImportRequest,
    TableMeta,
    TableMetaResponse,
    TableType,
    TextContent,
    ToolCall,
    ToolChoice,
    ToolChoiceFunction,
    ToolUsageDetails,
    Usage,
    UsageData,
    UsageResponse,
    User_,
    UserAgent,
    UserAuth,
    UserRead,
    UserReadObscured,
    VerificationCode_,
    VerificationCodeCreate,
    VerificationCodeRead,
    VerificationCodeUpdate,
    WebSearchTool,
    YAMLInput,
    YAMLOutput,
    empty_string_to_none,
    none_to_empty_string,
)
from jamaibase.utils import uuid7_str
from owl.types.db import (  # noqa: F401
    Organization_,
    OrganizationRead,
    OrganizationReadDecrypt,
    ProjectKeyReadDecrypt,
    UserCreate,
    UserUpdate,
)
from owl.version import __version__


class StripeEventType(StrEnum):
    INVOICE_PAID = "invoice.paid"
    INVOICE_PAYMENT_FAILED = "invoice.payment_failed"
    INVOICE_MARKED_UNCOLLECTIBLE = "invoice.marked_uncollectible"
    INVOICE_VOIDED = "invoice.voided"
    # PAYMENT_INTENT_PROCESSING = "payment_intent.processing"
    # PAYMENT_INTENT_SUCCEEDED = "payment_intent.succeeded"
    # CUSTOMER_SUBSCRIPTION_DELETED = "customer.subscription.deleted"
    CHARGE_SUCCEEDED = "charge.succeeded"
    CHARGE_REFUNDED = "charge.refunded"


TABLE_NAME_PATTERN = r"^[A-Za-z0-9]([A-Za-z0-9.?!@#$%^&*_()\- ]*[A-Za-z0-9.?!()\-])?$"
COLUMN_NAME_PATTERN = TABLE_NAME_PATTERN
GEN_CONFIG_VAR_PATTERN = r"(?<!\\)\${(.*?)}"


# Postgres defaults to 63 characters max length for identifiers
ColName = Annotated[
    str,
    Field(
        pattern=COLUMN_NAME_PATTERN,
        min_length=1,
        max_length=100,
        description=(
            "Column name or ID. "
            "Must be unique with at least 1 character and up to 100 characters. "
            "Must start with an alphabet or number. "
            "Characters in the middle can include space and these symbols: `.?!@#$%^&*_()-`. "
            "Must end with an alphabet or number or these symbols: `.?!()-`."
            'Cannot be called "ID" or "Updated at" (case-insensitive).'
        ),
    ),
]
TableName = Annotated[
    str,
    Field(
        pattern=TABLE_NAME_PATTERN,
        min_length=1,
        max_length=100,
        description=(
            "Table name or ID. "
            "Must be unique with at least 1 character and up to 100 characters. "
            "Must start with an alphabet or number. "
            "Characters in the middle can include space and these symbols: `.?!@#$%^&*_()-`. "
            "Must end with an alphabet or number or these symbols: `.?!()-`."
        ),
    ),
]


def _str_post_validator(value: str) -> str:
    return value.replace("\0", "")


PostgresSafeStr = Annotated[
    str,
    AfterValidator(_str_post_validator),
]

_MAP_TO_POSTGRES_TYPE = {
    "int": "INTEGER",
    "int8": "INTEGER",
    "float": "FLOAT",
    "float32": "FLOAT",
    "float16": "FLOAT",
    "bool": "BOOL",
    "str": "TEXT",
    "image": "TEXT",
    "audio": "TEXT",
    "document": "TEXT",
    "date-time": "TIMESTAMPTZ",
    "json": "JSONB",
}
_MAP_TO_PYTHON_TYPE = {
    "int": int,
    "int8": int,
    "float": float,
    "float32": float,
    "float16": float,
    "bool": bool,
    "str": PostgresSafeStr,
    "image": PostgresSafeStr,
    "audio": PostgresSafeStr,
    "document": PostgresSafeStr,
    "date-time": datetime,
    "json": dict,
}
_MAP_TO_PANDAS_TYPE = {
    "int": pd.Int64Dtype(),
    "int8": pd.Int8Dtype(),
    "float": pd.Float64Dtype(),
    "float32": pd.Float32Dtype(),
    "float16": pd.Float32Dtype(),
    "bool": pd.BooleanDtype(),
    "str": pd.StringDtype(),
    "image": pd.StringDtype(),
    "audio": pd.StringDtype(),
    "document": pd.StringDtype(),
    "date-time": pd.StringDtype(),  # Convert to ISO format first
    "json": pd.StringDtype(),  # In general, we should not export JSON
}
_MAP_TO_PYARROW_TYPE = {
    "int": pa.int64(),
    "int8": pa.int8(),
    "float": pa.float64(),
    "float32": pa.float32(),
    "float16": pa.float16(),
    "bool": pa.bool_(),
    "str": pa.utf8(),
    "image": pa.utf8(),  # Store URI
    "audio": pa.utf8(),  # Store URI
    "document": pa.utf8(),  # Store URI
    "date-time": pa.timestamp("us", "UTC"),
    "json": pa.utf8(),
}


class DBStorageUsage(BaseModel):
    schema_name: str
    table_names: list[str]
    table_sizes: list[float]

    @property
    def total_size(self) -> float:
        return sum(self.table_sizes)


class ColumnDtype(StrEnum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STR = "str"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    # Internal types
    # INT8 = "int8"
    # FLOAT32 = "float32"
    # FLOAT16 = "float16"
    DATE_TIME = "date-time"
    JSON = "json"

    def to_postgres_type(self) -> str:
        """
        Returns the corresponding PostgreSQL type definition.
        """
        return _MAP_TO_POSTGRES_TYPE[self]

    def to_python_type(self) -> Type[int | float | bool | str | datetime | dict]:
        """
        Returns the corresponding Python type.
        """
        return _MAP_TO_PYTHON_TYPE[self]

    def to_pandas_type(
        self,
    ) -> (
        pd.Int64Dtype
        | pd.Int8Dtype
        | pd.Float64Dtype
        | pd.Float32Dtype
        | pd.BooleanDtype
        | pd.StringDtype
    ):
        """
        Returns the corresponding Python type.
        """
        return _MAP_TO_PANDAS_TYPE[self]

    def to_pyarrow_type(self) -> pa.DataType:
        """
        Returns the corresponding Python type.
        """
        return _MAP_TO_PYARROW_TYPE[self]


class ColumnDtypeCreate(StrEnum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STR = "str"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"

    def to_column_type(self) -> ColumnDtype:
        """
        Returns the corresponding ColumnDtype.
        """
        return ColumnDtype(self)


class ColumnSchema(t.ColumnSchema):
    dtype: ColumnDtype = Field(
        ColumnDtype.STR,
        description=f"Column data type, one of {list(map(str, ColumnDtype))}.",
    )


class ColumnSchemaCreate(t.ColumnSchemaCreate):
    id: ColName = Field(
        description="Column name.",
    )
    dtype: ColumnDtypeCreate = Field(
        ColumnDtypeCreate.STR,
        description=f"Column data type, one of {list(map(str, ColumnDtypeCreate))}.",
    )

    @field_validator("dtype", mode="before")
    @classmethod
    def map_file_dtype_to_image(cls, v: Any) -> Any:
        if v == "file":
            v = ColumnDtype.IMAGE
        return v


class TableSchemaCreate(t.TableSchemaCreate):
    id: TableName = Field(
        description="Table name.",
    )
    version: str = Field(
        __version__,
        description="Table version, following jamaibase version.",
    )
    cols: list[ColumnSchemaCreate] = Field(
        description="List of column schema.",
    )


class ActionTableSchemaCreate(TableSchemaCreate):
    pass


class AddActionColumnSchema(ActionTableSchemaCreate):
    pass


class KnowledgeTableSchemaCreate(TableSchemaCreate):
    embedding_model: str


class AddKnowledgeColumnSchema(TableSchemaCreate):
    pass


class ChatTableSchemaCreate(TableSchemaCreate):
    pass


class AddChatColumnSchema(TableSchemaCreate):
    pass


class ColumnRenameRequest(t.ColumnRenameRequest):
    column_map: dict[str, ColName] = Field(
        description="Mapping of old column names to new column names.",
    )


IMAGE_FILE_EXTENSIONS = [".jpeg", ".jpg", ".png", ".gif", ".webp"]
AUDIO_FILE_EXTENSIONS = [".mp3", ".wav"]
DOCUMENT_FILE_EXTENSIONS = [
    ".csv",
    ".docx",
    ".html",
    ".json",
    ".jsonl",
    ".md",
    ".pdf",
    ".pptx",
    ".tsv",
    ".txt",
    ".xlsx",
    ".xml",
]
ALLOWED_FILE_EXTENSIONS = set(
    IMAGE_FILE_EXTENSIONS + AUDIO_FILE_EXTENSIONS + DOCUMENT_FILE_EXTENSIONS
)


def check_data(value: Any) -> Any:
    if isinstance(value, str) and (value.startswith("s3://") or value.startswith("file://")):
        extension = splitext(value)[1].lower()
        if extension not in ALLOWED_FILE_EXTENSIONS:
            raise ValueError(
                "Unsupported file type. Make sure the file belongs to "
                "one of the following formats: \n"
                f"[Image File Types]: \n{IMAGE_FILE_EXTENSIONS} \n"
                f"[Audio File Types]: \n{AUDIO_FILE_EXTENSIONS} \n"
                f"[Document File Types]: \n{DOCUMENT_FILE_EXTENSIONS}"
            )
    return value


CellValue = Annotated[Any, AfterValidator(check_data)]


class RowAdd(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    data: dict[str, CellValue] = Field(
        description="Mapping of column names to its value.",
    )
    stream: bool = Field(
        default=True,
        description="Whether or not to stream the LLM generation.",
    )
    concurrent: bool = Field(
        default=True,
        description="_Optional_. Whether or not to concurrently generate the output columns.",
    )


class MultiRowAddRequest(t.MultiRowAddRequest):
    data: list[dict[str, CellValue]] = Field(
        min_length=1,
        description=(
            "List of mapping of column names to its value. "
            "In other words, each item in the list is a row, and each item is a mapping. "
            "Minimum 1 row, maximum 100 rows."
        ),
    )


class MultiRowAddRequestWithLimit(MultiRowAddRequest):
    data: list[dict[str, CellValue]] = Field(
        min_length=1,
        max_length=100,
        description=(
            "List of mapping of column names to its value. "
            "In other words, each item in the list is a row, and each item is a mapping. "
            "Minimum 1 row, maximum 100 rows."
        ),
    )


class MultiRowUpdateRequest(t.MultiRowUpdateRequest):
    data: dict[str, dict[str, CellValue]] = Field(
        min_length=1,
        description="Mapping of row IDs to row data, where each row data is a mapping of column names to its value.",
    )


class MultiRowUpdateRequestWithLimit(MultiRowUpdateRequest):
    data: dict[str, dict[str, CellValue]] = Field(
        min_length=1,
        max_length=100,
        description="Mapping of row IDs to row data, where each row data is a mapping of column names to its value.",
    )


class RowUpdateRequest(t.RowUpdateRequest):
    data: dict[str, CellValue] = Field(
        description="Mapping of column names to its value.",
    )


class RegenStrategy(StrEnum):
    """Strategies for selecting columns during row regeneration."""

    RUN_ALL = "run_all"
    RUN_BEFORE = "run_before"
    RUN_SELECTED = "run_selected"
    RUN_AFTER = "run_after"


class RowRegen(t.RowRegen):
    regen_strategy: RegenStrategy = Field(
        default=RegenStrategy.RUN_ALL,
        description=(
            "_Optional_. Strategy for selecting columns to regenerate."
            "Choose `run_all` to regenerate all columns in the specified row; "
            "Choose `run_before` to regenerate columns up to the specified column_id; "
            "Choose `run_selected` to regenerate only the specified column_id; "
            "Choose `run_after` to regenerate columns starting from the specified column_id; "
        ),
    )


class MultiRowRegenRequest(t.MultiRowRegenRequest):
    regen_strategy: RegenStrategy = Field(
        default=RegenStrategy.RUN_ALL,
        description=(
            "_Optional_. Strategy for selecting columns to regenerate."
            "Choose `run_all` to regenerate all columns in the specified row; "
            "Choose `run_before` to regenerate columns up to the specified column_id; "
            "Choose `run_selected` to regenerate only the specified column_id; "
            "Choose `run_after` to regenerate columns starting from the specified column_id; "
        ),
    )

    @model_validator(mode="after")
    def check_output_column_id_provided(self) -> Self:
        if self.regen_strategy != RegenStrategy.RUN_ALL and self.output_column_id is None:
            raise ValueError(
                "`output_column_id` is required for regen_strategy other than 'run_all'."
            )
        return self

    @model_validator(mode="after")
    def sort_row_ids(self) -> Self:
        self.row_ids = sorted(self.row_ids)
        return self


class FileEmbedQuery(BaseModel):
    table_id: SanitisedNonEmptyStr = Field(
        description="Table name or ID.",
    )
    file_id: SanitisedNonEmptyStr = Field(
        description="ID of the file.",
    )
    chunk_size: int = Field(
        1000,
        gt=0,
        description="Maximum chunk size (number of characters). Must be > 0.",
    )
    chunk_overlap: int = Field(
        200,
        ge=0,
        description="Overlap in characters between chunks. Must be >= 0.",
    )
    # stream: Annotated[bool, Field(description="Whether or not to stream the LLM generation.")] = (
    #     True
    # )


ORDERED_BY = TypeVar("ORDERED_BY", bound=Literal["id", "name", "created_at", "updated_at"])


class ListQuery(BaseModel, Generic[ORDERED_BY]):
    offset: Annotated[int, Field(ge=0, description="Items offset.")] = 0
    limit: Annotated[int, Field(gt=0, le=1000, description="Number of items.")] = 1000
    order_by: Annotated[ORDERED_BY, Field(description="Sort by this attribute.")] = "updated_at"
    order_ascending: Annotated[bool, Field(description="Whether to sort in ascending order.")] = True  # fmt: skip
    search_query: Annotated[
        str,
        Field(
            max_length=10_000,
            description=(
                "A string to search for as a filter. "
                'The string is interpreted as both POSIX regular expression and literal string. Defaults to "" (no filter). '
                "It will be combined other filters using `AND`."
            ),
        ),
    ] = ""
    search_columns: Annotated[
        list[str],
        Field(
            min_length=1,
            description='A list of attribute names to search for `search_query`. Defaults to `["name"]`.',
        ),
    ] = ["name"]
    after: Annotated[
        str | None,
        Field(
            description=(
                "Opaque cursor token to paginate results. "
                "If provided, the query will return items after this cursor and `offset` will be ignored. "
                "Defaults to `None` (no cursor)."
            ),
        ),
    ] = None


class ListQueryByOrg(ListQuery):
    organization_id: Annotated[SanitisedNonEmptyStr, Field(description="Organization ID.")]


class ListQueryByOrgOptional(ListQuery):
    organization_id: Annotated[
        SanitisedNonEmptyStr | None, Field(None, description="Organization ID.")
    ]


class ListQueryByProject(ListQuery):
    project_id: Annotated[SanitisedNonEmptyStr, Field(description="Project ID.")]


class OrgModelCatalogueQuery(ListQueryByOrg):
    capabilities: list[ModelCapability] | None = Field(
        None,
        min_length=1,
        description="List of capabilities of model.",
    )


class DuplicateTableQuery(BaseModel):
    table_id_src: Annotated[str, Field(description="Name of the table to be duplicated.")]
    table_id_dst: Annotated[
        TableName | None,
        Field(
            description=(
                "Name for the new table. "
                "Defaults to None (automatically find the next available table name)."
            )
        ),
    ] = None
    include_data: Annotated[
        bool,
        Field(description=("Whether to include data from the source table. Defaults to `True`.")),
    ] = True
    create_as_child: Annotated[
        bool,
        Field(
            description=(
                "Whether the new table is a child table. Defaults to `False`. "
                "If this is `True`, then `include_data` will be set to `True`."
            )
        ),
    ] = False


class RenameTableQuery(BaseModel):
    table_id_src: Annotated[str, Field(description="Source table name.")]
    table_id_dst: Annotated[TableName, Field(description="Name for the new table.")]


class GetTableThreadQuery(BaseModel):
    table_id: Annotated[str, Field(description="Table name.")]
    column_id: Annotated[str, Field(description="Column to fetch as a conversation thread.")]
    row_id: Annotated[
        str,
        Field(description='ID of the last row in the thread. Defaults to "" (export all rows).'),
    ] = ""
    include: Annotated[
        bool,
        Field(description="Whether to include the row specified by `row_id`. Defaults to True."),
    ] = True


class GetTableThreadsQuery(BaseModel):
    table_id: Annotated[str, Field(description="Table name.")]
    column_ids: Annotated[
        list[str] | None,
        Field(
            description="Columns to fetch as conversation threads. Defaults to None (fetch all)."
        ),
    ] = None
    row_id: Annotated[
        str,
        Field(description='ID of the last row in the thread. Defaults to "" (export all rows).'),
    ] = ""
    include_row: Annotated[
        bool,
        Field(description="Whether to include the row specified by `row_id`. Defaults to True."),
    ] = True


class GetConversationThreadsQuery(BaseModel):
    conversation_id: Annotated[str, Field(description="Conversation ID.")]
    column_ids: Annotated[
        list[str] | None,
        Field(
            description="Columns to fetch as conversation threads. Defaults to None (fetch all)."
        ),
    ] = None


class ListTableQuery(BaseModel):
    offset: Annotated[
        int,
        Field(ge=0, description="Item offset for pagination. Defaults to 0."),
    ] = 0
    limit: Annotated[
        int,
        Field(
            gt=0,
            le=100,
            description="Number of tables to return (min 1, max 100). Defaults to 100.",
        ),
    ] = 100
    order_by: Annotated[
        Literal["id", "table_id", "updated_at"],
        Field(description='Sort tables by this attribute. Defaults to "updated_at".'),
    ] = "updated_at"
    order_ascending: Annotated[
        bool,
        Field(description="Whether to sort by ascending order. Defaults to True."),
    ] = True
    parent_id: Annotated[
        str | None,
        Field(
            min_length=1,
            description=(
                "Parent ID of tables to return. Defaults to None (return all tables). "
                "Additionally for Chat Table, you can list: "
                '(1) all chat agents by passing in "_agent_"; or '
                '(2) all chats by passing in "_chat_".'
            ),
        ),
    ] = None
    search_query: Annotated[
        str,
        Field(
            max_length=255,
            description='A string to search for within table IDs as a filter. Defaults to "" (no filter).',
        ),
    ] = ""
    count_rows: Annotated[
        bool,
        Field(description="Whether to count the rows of the tables. Defaults to False."),
    ] = False


class ListRowQuery(BaseModel):
    offset: Annotated[
        int,
        Field(ge=0, description="Item offset for pagination. Defaults to 0."),
    ] = 0
    limit: Annotated[
        int,
        Field(
            gt=0,
            le=100,
            description="Number of rows to return (min 1, max 100). Defaults to 100.",
        ),
    ] = 100
    order_by: Annotated[
        str,
        Field(description='Sort rows by this column. Defaults to "ID".'),
    ] = "ID"
    order_ascending: Annotated[
        bool,
        Field(description="Whether to sort by ascending order. Defaults to True."),
    ] = True
    columns: Annotated[
        list[str] | None,
        Field(
            description="A list of column names to include in the response. Default is to return all columns.",
        ),
    ] = None
    where: Annotated[
        EmptyIfNoneStr,
        Field(
            description=(
                "SQL where clause. "
                "Can be nested ie `x = '1' AND (\"y (1)\" = 2 OR z = '3')`. "
                "It will be combined with `row_ids` using `AND`. "
                'Defaults to "" (no filter).'
            ),
        ),
    ] = ""
    search_query: Annotated[
        str,
        Field(
            max_length=10_000,
            description=(
                "A string to search for within row data as a filter. "
                'The string is interpreted as both POSIX regular expression and literal string. Defaults to "" (no filter). '
                "It will be combined other filters using `AND`."
            ),
        ),
    ] = ""
    search_columns: Annotated[
        list[str] | None,
        Field(
            description="A list of column names to search for `search_query`. Defaults to None (search all columns).",
        ),
    ] = None
    float_decimals: Annotated[
        int,
        Field(
            ge=0,
            description="Number of decimals for float values. Defaults to 0 (no rounding).",
        ),
    ] = 0
    vec_decimals: Annotated[
        int,
        Field(
            description="Number of decimals for vectors. If its negative, exclude vector columns. Defaults to 0 (no rounding).",
        ),
    ] = 0


class ListTableRowQuery(ListRowQuery):
    table_id: Annotated[SanitisedNonEmptyStr, Field(description="Table ID or name.")]


class ListMessageQuery(ListRowQuery):
    conversation_id: Annotated[
        SanitisedNonEmptyStr, Field(description="Conversation ID (Table ID) to fetch.")
    ]


class GetTableRowQuery(BaseModel):
    table_id: Annotated[SanitisedNonEmptyStr, Field(description="Table name.")]
    row_id: Annotated[
        SanitisedNonEmptyStr, Field(description="The ID of the specific row to fetch.")
    ]
    columns: Annotated[
        list[SanitisedNonEmptyStr] | None,
        Field(
            description="A list of column names to include in the response. Default is to return all columns.",
        ),
    ] = None
    float_decimals: Annotated[
        int,
        Field(
            ge=0,
            description="Number of decimals for float values. Defaults to 0 (no rounding).",
        ),
    ] = 0
    vec_decimals: Annotated[
        int,
        Field(
            description="Number of decimals for vectors. If its negative, exclude vector columns. Defaults to 0 (no rounding).",
        ),
    ] = 0


class FileEmbedFormData(BaseModel):
    file: Annotated[UploadFile, File(description="The file.")]
    file_name: Annotated[str, Field(description="File name.", deprecated=True)] = ""
    table_id: Annotated[SanitisedNonEmptyStr, Field(description="Knowledge Table ID.")]
    # overwrite: Annotated[
    #     bool, Field(description="Whether to overwrite old file with the same name.")
    # ] = False,
    chunk_size: Annotated[
        int, Field(gt=0, description="Maximum chunk size (number of characters). Must be > 0.")
    ] = 2000
    chunk_overlap: Annotated[
        int, Field(ge=0, description="Overlap in characters between chunks. Must be >= 0.")
    ] = 200


class TableDataImportFormData(BaseModel):
    file: Annotated[UploadFile, File(description="The CSV or TSV file.")]
    file_name: Annotated[str, Field(description="File name.", deprecated=True)] = ""
    table_id: Annotated[
        SanitisedNonEmptyStr,
        Field(description="ID or name of the table that the data should be imported into."),
    ]
    stream: Annotated[bool, Field(description="Whether or not to stream the LLM generation.")] = (
        True
    )
    # List of inputs is bugged as of 2024-07-14: https://github.com/tiangolo/fastapi/pull/9928/files
    # TODO: Maybe we can re-enable these since the bug is for direct `Form` declaration and not Form Model
    # column_names: Annotated[
    #     list[ColName] | None,
    #     Field(
    #         description="_Optional_. A list of columns names if the CSV does not have header row. Defaults to None (read from CSV).",
    #     ),
    # ] = None
    # columns: Annotated[
    #     list[ColName] | None,
    #     Field(
    #         description="_Optional_. A list of columns to be imported. Defaults to None (import all columns except 'ID' and 'Updated at').",
    #     ),
    # ] = None
    delimiter: Annotated[
        CSVDelimiter,
        Field(description='The delimiter, can be "," or "\\t". Defaults to ",".'),
    ] = CSVDelimiter.COMMA


class ExportTableDataQuery(BaseModel):
    table_id: Annotated[SanitisedNonEmptyStr, Field(description="Table name.")]
    delimiter: Annotated[
        CSVDelimiter,
        Field(description='The delimiter, can be "," or "\\t". Defaults to ",".'),
    ] = CSVDelimiter.COMMA
    columns: Annotated[
        list[SanitisedNonEmptyStr] | None,
        Field(
            min_length=1,
            description="_Optional_. A list of columns to be exported. Defaults to None (export all columns).",
        ),
    ] = None


TableImportName = Annotated[
    str,
    Field(
        pattern=TABLE_NAME_PATTERN,
        min_length=1,
        max_length=100,  # Since we will truncate table IDs that are too long anyway
        description=(
            "Table name or ID. "
            "Must be unique with at least 1 character and up to 46 characters. "
            "Must start with an alphabet or number. "
            "Characters in the middle can include space and these symbols: `.?!@#$%^&*_()-`. "
            "Must end with an alphabet or number or these symbols: `.?!()-`."
        ),
    ),
]


class TableImportFormData(BaseModel):
    file: Annotated[UploadFile, File(description="The Parquet file.")]
    table_id_dst: Annotated[
        TableImportName | None,
        BeforeValidator(empty_string_to_none),
        Field(description="The ID or name of the new table."),
    ] = None
    blocking: Annotated[
        bool,
        Field(
            description=(
                "If True, waits until import finishes. "
                "If False, the task is submitted to a task queue and returns immediately."
            ),
        ),
    ] = True
    progress_key: Annotated[
        str,
        Field(
            default_factory=uuid7_str,
            description="The key to use to query progress. Defaults to a random string.",
        ),
    ]
    migrate: Annotated[
        bool,
        Field(description="Whether to import in migration mode (maybe removed without notice)."),
    ] = False
    reupload: Annotated[
        bool,
        Field(description="Whether to reupload in migration mode (maybe removed without notice)."),
    ] = False
