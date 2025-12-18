from functools import cached_property
from typing import Annotated, Any, Literal, Self, Union

import numpy as np
from pydantic import (
    BaseModel,
    Discriminator,
    Field,
    Tag,
    field_validator,
    model_validator,
)

from jamaibase.types.common import (
    EXAMPLE_EMBEDDING_MODEL_IDS,
    DatetimeUTC,
    EmptyIfNoneStr,
    PositiveInt,
    SanitisedNonEmptyMultilineStr,
    SanitisedNonEmptyStr,
)
from jamaibase.types.lm import (
    ChatCompletionChunkResponse,
    ChatCompletionResponse,
    ChatRequestBase,
    References,
)
from jamaibase.utils.types import StrEnum


class CSVDelimiter(StrEnum):
    COMMA = ","
    TAB = "\t"


class TableType(StrEnum):
    ACTION = "action"
    KNOWLEDGE = "knowledge"
    CHAT = "chat"


class CellReferencesResponse(References):
    object: Literal["gen_table.references"] = Field(
        "gen_table.references",
        description="Type of API response object.",
        examples=["gen_table.references"],
    )
    output_column_name: str
    row_id: str


class CellCompletionResponse(ChatCompletionChunkResponse):
    object: Literal["gen_table.completion.chunk"] = Field(
        "gen_table.completion.chunk",
        description="Type of API response object.",
        examples=["gen_table.completion.chunk"],
    )
    output_column_name: str
    row_id: str


class RowCompletionResponse(BaseModel):
    object: Literal["gen_table.completion.chunks"] = Field(
        "gen_table.completion.chunks",
        description="Type of API response object.",
        examples=["gen_table.completion.chunks"],
    )
    # Union just to satisfy "object" discriminator
    # columns: dict[str, ChatCompletionResponse | ChatCompletionChunkResponse]
    columns: dict[str, ChatCompletionResponse]
    row_id: str


class MultiRowCompletionResponse(BaseModel):
    object: Literal["gen_table.completion.rows"] = Field(
        "gen_table.completion.rows",
        description="Type of API response object.",
        examples=["gen_table.completion.rows"],
    )
    rows: list[RowCompletionResponse]


class LLMGenConfig(ChatRequestBase):
    object: Literal["gen_config.llm"] = Field(
        "gen_config.llm",
        description='The object type, which is always "gen_config.llm".',
        examples=["gen_config.llm"],
    )
    system_prompt: str = Field(
        "",
        description="System prompt for the LLM.",
    )
    prompt: str = Field(
        "",
        description="Prompt for the LLM.",
    )
    multi_turn: bool = Field(
        False,
        description="Whether this column is a multi-turn chat with history along the entire column.",
    )

    @model_validator(mode="before")
    @classmethod
    def compat(cls, data: dict[str, Any] | BaseModel) -> dict[str, Any]:
        if isinstance(data, BaseModel):
            data = data.model_dump()
        if not isinstance(data, dict):
            raise TypeError(
                f"Input to `LLMGenConfig` must be a dict or BaseModel, received: {type(data)}"
            )
        if data.get("system_prompt", None) or data.get("prompt", None):
            return data
        messages: list[dict[str, Any]] = data.get("messages", [])
        num_prompts = len(messages)
        if num_prompts >= 2:
            data["system_prompt"] = messages[0]["content"]
            data["prompt"] = messages[1]["content"]
        elif num_prompts == 1:
            if messages[0]["role"] == "system":
                data["system_prompt"] = messages[0]["content"]
                data["prompt"] = ""
            elif messages[0]["role"] == "user":
                data["system_prompt"] = ""
                data["prompt"] = messages[0]["content"]
            else:
                raise ValueError(
                    f'Attribute "messages" cannot contain only assistant messages: {messages}'
                )
        data["object"] = "gen_config.llm"
        return data


class EmbedGenConfig(BaseModel):
    object: Literal["gen_config.embed"] = Field(
        "gen_config.embed",
        description='The object type, which is always "gen_config.embed".',
        examples=["gen_config.embed"],
    )
    embedding_model: SanitisedNonEmptyStr = Field(
        description="The embedding model to use.",
        examples=EXAMPLE_EMBEDDING_MODEL_IDS,
    )
    source_column: SanitisedNonEmptyStr = Field(
        description="The source column for embedding.",
        examples=["text_column"],
    )


class CodeGenConfig(BaseModel):
    object: Literal["gen_config.code"] = Field(
        "gen_config.code",
        description='The object type, which is always "gen_config.code".',
        examples=["gen_config.code"],
    )
    source_column: SanitisedNonEmptyStr = Field(
        description="The source column for python code to execute.",
        examples=["code_column"],
    )


class PythonGenConfig(BaseModel):
    object: Literal["gen_config.python"] = Field(
        "gen_config.python",
        description='The object type, which is always "gen_config.python".',
        examples=["gen_config.python"],
    )
    python_code: SanitisedNonEmptyMultilineStr = Field(
        description="The python code to execute.",
        examples=["row['output_column']='Hello World!'"],
    )


def _gen_config_discriminator(x: Any) -> str | None:
    object_attr = getattr(x, "object", None)
    if object_attr:
        return object_attr
    if isinstance(x, BaseModel):
        x = x.model_dump()
    if isinstance(x, dict):
        if "object" in x:
            return x["object"]
        if "embedding_model" in x:
            return "gen_config.embed"
        if "source_column" in x:
            return "gen_config.code"
        if "python_code" in x:
            return "gen_config.python"
        else:
            return "gen_config.llm"
    return None


DiscriminatedGenConfig = Annotated[
    Union[
        # Annotated[CodeGenConfig, Tag("gen_config.code")],
        Annotated[PythonGenConfig, Tag("gen_config.python")],
        Annotated[LLMGenConfig, Tag("gen_config.llm")],
        Annotated[LLMGenConfig, Tag("gen_config.chat")],
        Annotated[EmbedGenConfig, Tag("gen_config.embed")],
    ],
    Discriminator(_gen_config_discriminator),
]


class ColumnSchema(BaseModel):
    id: str = Field(description="Column name.")
    dtype: str = Field(
        "str",
        description="Column data type.",
    )
    vlen: PositiveInt = Field(  # type: ignore
        0,
        description=(
            "_Optional_. Vector length. "
            "If this is larger than zero, then `dtype` must be one of the floating data types. Defaults to zero."
        ),
    )
    index: bool = Field(
        True,
        description=(
            "_Optional_. Whether to build full-text-search (FTS) or vector index for this column. "
            "Only applies to string and vector columns. Defaults to True."
        ),
    )
    gen_config: DiscriminatedGenConfig | None = Field(
        None,
        description=(
            '_Optional_. Generation config. If provided, then this column will be an "Output Column". '
            "Table columns on its left can be referenced by `${column-name}`."
        ),
    )


class ColumnSchemaCreate(ColumnSchema):
    id: SanitisedNonEmptyStr = Field(description="Column name.")
    dtype: Literal["int", "float", "bool", "str", "file", "image", "audio", "document"] = Field(
        "str",
        description=(
            'Column data type, one of ["int", "float", "bool", "str", "file", "image", "audio", "document"]'
            ". Data type 'file' is deprecated, use 'image' instead."
        ),
    )


class _TableBase(BaseModel):
    id: str = Field(
        description="Table name.",
    )


class TableSchemaCreate(_TableBase):
    id: SanitisedNonEmptyStr = Field(
        description="Table name.",
    )
    cols: list[ColumnSchemaCreate] = Field(
        description="List of column schema.",
    )


class ActionTableSchemaCreate(TableSchemaCreate):
    pass


class AddActionColumnSchema(ActionTableSchemaCreate):
    # TODO: Deprecate this
    pass


class KnowledgeTableSchemaCreate(TableSchemaCreate):
    # TODO: Maybe deprecate this and use EmbedGenConfig instead ?
    embedding_model: str


class AddKnowledgeColumnSchema(TableSchemaCreate):
    # TODO: Deprecate this
    pass


class ChatTableSchemaCreate(TableSchemaCreate):
    pass


class AddChatColumnSchema(TableSchemaCreate):
    # TODO: Deprecate this
    pass


class TableMeta(_TableBase):
    meta: dict[str, Any] | None = Field(
        None,
        description="Additional metadata about the table.",
    )
    cols: list[ColumnSchema] = Field(
        description="List of column schema.",
    )
    parent_id: str | None = Field(
        description="The parent table ID. If None (default), it means this is a parent table.",
    )
    title: str = Field(
        description='Chat title. Defaults to "".',
    )
    created_by: str | None = Field(
        None,
        description="ID of the user that created this table. Defaults to None.",
    )
    updated_at: DatetimeUTC = Field(
        description="Table last update datetime (UTC).",
    )
    num_rows: int = Field(
        -1,
        description="Number of rows in the table. Defaults to -1 (not counted).",
    )
    version: str = Field(
        description="Version.",
    )

    @cached_property
    def col_map(self) -> dict[str, ColumnSchema]:
        return {c.id: c for c in self.cols}

    @cached_property
    def cfg_map(self) -> dict[str, DiscriminatedGenConfig | None]:
        return {c.id: c.gen_config for c in self.cols}


class TableMetaResponse(TableMeta):
    # Legacy, for backwards compatibility
    indexed_at_fts: str | None = Field(
        None,
        description="Table last FTS index timestamp (ISO 8601 UTC).",
    )
    indexed_at_vec: str | None = Field(
        None,
        description="Table last vector index timestamp (ISO 8601 UTC).",
    )
    indexed_at_sca: str | None = Field(
        None,
        description="Table last scalar index timestamp (ISO 8601 UTC).",
    )

    @model_validator(mode="after")
    def remove_state_cols(self) -> Self:
        self.cols = [c for c in self.cols if not c.id.endswith("_")]
        return self


class GenConfigUpdateRequest(BaseModel):
    table_id: str = Field(description="Table name or ID.")
    column_map: dict[str, DiscriminatedGenConfig | None] = Field(
        description=(
            "Mapping of column ID to generation config JSON in the form of `GenConfig`. "
            "Table columns on its left can be referenced by `${column-name}`."
        )
    )

    @model_validator(mode="after")
    def check_column_map(self) -> Self:
        if sum(n.lower() in ("id", "updated at") for n in self.column_map) > 0:
            raise ValueError("column_map cannot contain keys: 'ID' or 'Updated at'.")
        return self


class ColumnRenameRequest(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    column_map: dict[str, str] = Field(
        min_length=1,
        description="Mapping of old column names to new column names.",
    )

    @model_validator(mode="after")
    def check_column_map(self) -> Self:
        if sum(n.lower() in ("id", "updated at") for n in self.column_map) > 0:
            raise ValueError("`column_map` cannot contain keys: 'ID' or 'Updated at'.")
        return self


class ColumnReorderRequest(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    column_names: list[str] = Field(
        min_length=1,
        description="List of column ID in the desired order.",
    )

    @field_validator("column_names", mode="after")
    @classmethod
    def check_column_order(cls, values: list[str]) -> list[str]:
        if values[0].lower() != "id":
            values.insert(0, "ID")
        if values[1].lower() != "updated at":
            values.insert(1, "Updated at")
        return values

    @field_validator("column_names", mode="after")
    @classmethod
    def check_unique_column_names(cls, values: list[str]) -> list[str]:
        if len(set(n.lower() for n in values)) != len(values):
            raise ValueError("Column names must be unique (case-insensitive).")
        return values

    @field_validator("column_names", mode="after")
    @classmethod
    def check_state_column(cls, values: list[str]) -> list[str]:
        if len(invalid_cols := [n for n in values if n.endswith("_")]) > 0:
            raise ValueError(f"State columns cannot be reordered: {invalid_cols}")
        return values


class ColumnDropRequest(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    column_names: list[str] = Field(
        min_length=1,
        description="List of column ID to drop.",
    )

    @model_validator(mode="after")
    def check_column_names(self) -> Self:
        if sum(n.lower() in ("id", "updated at") for n in self.column_names) > 0:
            raise ValueError("`column_names` cannot contain keys: 'ID' or 'Updated at'.")
        return self


class MultiRowAddRequest(BaseModel):
    table_id: SanitisedNonEmptyStr = Field(
        description="Table name or ID.",
    )
    data: list[dict[str, Any]] = Field(
        min_length=1,
        description=(
            "List of mapping of column names to its value. "
            "In other words, each item in the list is a row, and each item is a mapping. "
            "Minimum 1 row, maximum 100 rows."
        ),
    )
    stream: bool = Field(
        True,
        description="Whether or not to stream the LLM generation.",
    )
    concurrent: bool = Field(
        True,
        description="_Optional_. Whether or not to concurrently generate the output rows and columns.",
    )

    def __repr__(self):
        _data = [
            {
                k: (
                    {"type": type(v), "shape": v.shape, "dtype": v.dtype}
                    if isinstance(v, np.ndarray)
                    else v
                )
                for k, v in d.items()
            }
            for d in self.data
        ]
        return (
            f"{self.__class__.__name__}("
            f"table_id={self.table_id}  stream={self.stream} "
            f"concurrent={self.concurrent} data={_data}"
            ")"
        )


class RowUpdateRequest(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    row_id: str = Field(
        description="ID of the row to update.",
    )
    data: dict[str, Any] = Field(
        description="Mapping of column names to its value.",
    )


class MultiRowUpdateRequest(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    data: dict[str, dict[str, Any]] = Field(
        min_length=1,
        description="Mapping of row IDs to row data, where each row data is a mapping of column names to its value.",
    )


class MultiRowUpdateRequestWithLimit(MultiRowUpdateRequest):
    data: dict[str, dict[str, Any]] = Field(
        min_length=1,
        max_length=100,
        description="Mapping of row IDs to row data, where each row data is a mapping of column names to its value.",
    )


class RowRegen(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    row_id: str = Field(
        description="ID of the row to regenerate.",
    )
    regen_strategy: str = Field(
        "run_all",
        description=(
            "_Optional_. Strategy for selecting columns to regenerate."
            "Choose `run_all` to regenerate all columns in the specified row; "
            "Choose `run_before` to regenerate columns up to the specified column_id; "
            "Choose `run_selected` to regenerate only the specified column_id; "
            "Choose `run_after` to regenerate columns starting from the specified column_id; "
        ),
    )
    output_column_id: str | None = Field(
        None,
        min_length=1,
        description=(
            "_Optional_. Output column name to indicate the starting or ending point of regen for `run_before`, "
            "`run_selected` and `run_after` strategies. Required if `regen_strategy` is not 'run_all'. "
            "Given columns are 'C1', 'C2', 'C3' and 'C4', if column_id is 'C3': "
            "`run_before` regenerate columns 'C1', 'C2' and 'C3'; "
            "`run_selected` regenerate only column 'C3'; "
            "`run_after` regenerate columns 'C3' and 'C4'; "
        ),
    )
    stream: bool = Field(
        description="Whether or not to stream the LLM generation.",
    )
    concurrent: bool = Field(
        True,
        description="_Optional_. Whether or not to concurrently generate the output columns.",
    )


class MultiRowRegenRequest(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    row_ids: list[str] = Field(
        min_length=1,
        max_length=100,
        description="List of ID of the row to regenerate. Minimum 1 row, maximum 100 rows.",
    )
    regen_strategy: str = Field(
        "run_all",
        description=(
            "_Optional_. Strategy for selecting columns to regenerate."
            "Choose `run_all` to regenerate all columns in the specified row; "
            "Choose `run_before` to regenerate columns up to the specified column_id; "
            "Choose `run_selected` to regenerate only the specified column_id; "
            "Choose `run_after` to regenerate columns starting from the specified column_id; "
        ),
    )
    output_column_id: str | None = Field(
        None,
        min_length=1,
        description=(
            "_Optional_. Output column name to indicate the starting or ending point of regen for `run_before`, "
            "`run_selected` and `run_after` strategies. Required if `regen_strategy` is not 'run_all'. "
            "Given columns are 'C1', 'C2', 'C3' and 'C4', if column_id is 'C3': "
            "`run_before` regenerate columns 'C1', 'C2' and 'C3'; "
            "`run_selected` regenerate only column 'C3'; "
            "`run_after` regenerate columns 'C3' and 'C4'; "
        ),
    )
    stream: bool = Field(
        True,
        description="Whether or not to stream the LLM generation.",
    )
    concurrent: bool = Field(
        True,
        description="Whether or not to concurrently generate the output rows and columns. Defaults to True.",
    )


class MultiRowDeleteRequest(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    row_ids: list[str] | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="List of row IDs to be deleted. Maximum 100 rows. Defaults to None (match rows using `where`).",
    )
    where: EmptyIfNoneStr = Field(
        "",
        description=(
            "SQL where clause. "
            "Can be nested ie `x = '1' AND (\"y (1)\" = 2 OR z = '3')`. "
            "It will be combined with `row_ids` using `AND`. "
            'Defaults to "" (no filter).'
        ),
    )


class SearchRequest(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    query: str = Field(
        min_length=1,
        description="Query for full-text-search (FTS) and vector search. Must not be empty.",
    )
    limit: Annotated[int, Field(gt=0, le=1_000)] = Field(
        100,
        description="_Optional_. Min 1, max 1000. Number of rows to return.",
    )
    metric: str = Field(
        "cosine",
        description='_Optional_. Vector search similarity metric. Defaults to "cosine".',
    )
    float_decimals: int = Field(
        0,
        description="_Optional_. Number of decimals for float values. Defaults to 0 (no rounding).",
    )
    vec_decimals: int = Field(
        0,
        description="_Optional_. Number of decimals for vectors. If its negative, exclude vector columns. Defaults to 0 (no rounding).",
    )
    reranking_model: Annotated[
        str | None, Field(description="Reranking model to use for hybrid search.")
    ] = None


class TableDataImportRequest(BaseModel):
    file_path: Annotated[str, Field(description="CSV or TSV file path.")]
    table_id: Annotated[
        str, Field(description="ID or name of the table that the data should be imported into.")
    ]
    stream: Annotated[bool, Field(description="Whether or not to stream the LLM generation.")] = (
        True
    )
    # column_names: Annotated[
    #     list[str] | None,
    #     Field(
    #         description="A list of columns names if the CSV does not have header row. Defaults to None (read from CSV)."
    #     ),
    # ] = None
    # columns: Annotated[
    #     list[str] | None,
    #     Field(
    #         description="A list of columns to be imported. Defaults to None (import all columns except 'ID' and 'Updated at')."
    #     ),
    # ] = None
    delimiter: Annotated[
        Literal[",", "\t"],
        Field(description='The delimiter of the content can be "," or "\\t". Defaults to ",".'),
    ] = ","


class TableImportRequest(BaseModel):
    file_path: Annotated[str, Field(description="The parquet file path.")]
    table_id_dst: Annotated[
        str | None, Field(description="_Optional_. The ID or name of the new table.")
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
