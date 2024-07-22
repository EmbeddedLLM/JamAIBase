"""
NOTES:

- Pydantic supports setting mutable values as default.
  This is in contrast to native `dataclasses` where it is not supported.

- Pydantic supports setting default fields in any order.
  This is in contrast to native `dataclasses` where fields with default values must be defined after non-default fields.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum, EnumMeta
from typing import Annotated, Any, Generic, Literal, Sequence, TypeVar

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from pydantic.functional_validators import AfterValidator
from typing_extensions import Self

PositiveInt = Annotated[int, Field(ge=0, description="Positive integer.")]
PositiveNonZeroInt = Annotated[int, Field(gt=0, description="Positive non-zero integer.")]


def sanitise_document_id(v: str) -> str:
    if v.startswith('"') and v.endswith('"'):
        v = v[1:-1]
    return v


def sanitise_document_id_list(v: list[str]) -> list[str]:
    return [sanitise_document_id(vv) for vv in v]


DocumentID = Annotated[str, AfterValidator(sanitise_document_id)]
DocumentIDList = Annotated[list[str], AfterValidator(sanitise_document_id_list)]


class OkResponse(BaseModel):
    ok: bool = True


class Document(BaseModel):
    """Document class for use in DocIO."""

    page_content: str
    metadata: dict = {}


class Chunk(BaseModel):
    """Class for storing a piece of text and associated metadata."""

    text: str = Field(description="Document chunk text.")
    title: str = Field(default="", description='Document title. Defaults to "".')
    page: int = Field(default=0, description="Page number. Defaults to 0.")
    file_name: str = Field(default="", description="Document file name.")
    file_path: str = Field(default="", description="Document file path.")
    document_id: str = Field(default="", description="Document ID.")
    chunk_id: str = Field(default="", description="Chunk ID.")
    metadata: dict = Field(
        default_factory=dict,
        description="Arbitrary metadata about the page content (e.g., source, relationships to other documents, etc.).",
    )


class SplitChunksParams(BaseModel):
    method: str = Field(
        default="RecursiveCharacterTextSplitter",
        description="Name of the splitter.",
        examples=["RecursiveCharacterTextSplitter"],
    )
    chunk_size: PositiveNonZeroInt = Field(
        default=1000,
        description="Maximum chunk size (number of characters). Must be > 0.",
        examples=[1000],
    )
    chunk_overlap: PositiveInt = Field(
        default=200,
        description="Overlap in characters between chunks. Must be >= 0.",
        examples=[200],
    )


class SplitChunksRequest(BaseModel):
    id: str = Field(
        default="",
        description="Request ID for logging purposes.",
        examples=["018ed5f1-6399-71f7-86af-fc18d4a3e3f5"],
    )
    chunks: list[Chunk] = Field(
        description="List of `Chunk` where each will be further split into chunks.",
        examples=[
            [
                Chunk(
                    text="The Name of the Title is Hope\n\n...",
                    title="The Name of the Title is Hope",
                    page=0,
                    file_name="sample_tables.pdf",
                    file_path="amagpt/sample_tables.pdf",
                    metadata={
                        "total_pages": 3,
                        "Author": "Ben Trovato",
                        "CreationDate": "D:20231031072817Z",
                        "Creator": "LaTeX with acmart 2023/10/14 v1.92 Typesetting articles for the Association for Computing Machinery and hyperref 2023-07-08 v7.01b Hypertext links for LaTeX",
                        "Keywords": "Image Captioning, Deep Learning",
                        "ModDate": "D:20231031073146Z",
                        "PTEX.Fullbanner": "This is pdfTeX, Version 3.141592653-2.6-1.40.25 (TeX Live 2023) kpathsea version 6.3.5",
                        "Producer": "3-Heights(TM) PDF Security Shell 4.8.25.2 (http://www.pdf-tools.com) / pdcat (www.pdf-tools.com)",
                        "Trapped": "False",
                    },
                )
            ]
        ],
    )
    params: SplitChunksParams = Field(
        default=SplitChunksParams(),
        description="How to split each document. Defaults to `RecursiveCharacterTextSplitter` with chunk_size = 1000 and chunk_overlap = 200.",
        examples=[SplitChunksParams()],
    )

    def str_trunc(self) -> str:
        return f"id={self.id} len(chunks)={len(self.chunks)} params={self.params}"


class RAGParams(BaseModel):
    table_id: str = Field(description="Knowledge Table ID", examples=["my-dataset"], min_length=2)
    reranking_model: Annotated[
        str | None, Field(description="Reranking model to use for hybrid search.")
    ] = None
    search_query: str = Field(
        default="",
        description="Query used to retrieve items from the KB database. If not provided (default), it will be generated using LLM.",
    )
    k: Annotated[int, Field(gt=0, le=1024)] = Field(
        default=3,
        gt=0,
        le=1024,
        description="Top-k closest text in terms of embedding distance. Must be in [1, 1024]. Defaults to 3.",
        examples=[3],
    )
    rerank: bool = Field(
        default=True,
        description="Flag to perform rerank on the retrieved results. Defaults to True.",
        examples=[True, False],
    )
    concat_reranker_input: bool = Field(
        default=False,
        description="Flag to concat title and content as reranker input. Defaults to False.",
        examples=[True, False],
    )


class VectorSearchRequest(RAGParams):
    id: str = Field(
        default="",
        description="Request ID for logging purposes.",
        examples=["018ed5f1-6399-71f7-86af-fc18d4a3e3f5"],
    )
    search_query: str = Field(description="Query used to retrieve items from the KB database.")


class VectorSearchResponse(BaseModel):
    object: str = Field(
        default="kb.search_response",
        description="Type of API response object.",
        examples=["kb.search_response"],
    )
    chunks: list[Chunk] = Field(
        default=[],
        description="A list of `Chunk`.",
        examples=[
            [
                Chunk(
                    text="The Name of the Title is Hope\n\n...",
                    title="The Name of the Title is Hope",
                    page=0,
                    file_name="sample_tables.pdf",
                    file_path="amagpt/sample_tables.pdf",
                    metadata={
                        "total_pages": 3,
                        "Author": "Ben Trovato",
                        "CreationDate": "D:20231031072817Z",
                        "Creator": "LaTeX with acmart 2023/10/14 v1.92 Typesetting articles for the Association for Computing Machinery and hyperref 2023-07-08 v7.01b Hypertext links for LaTeX",
                        "Keywords": "Image Captioning, Deep Learning",
                        "ModDate": "D:20231031073146Z",
                        "PTEX.Fullbanner": "This is pdfTeX, Version 3.141592653-2.6-1.40.25 (TeX Live 2023) kpathsea version 6.3.5",
                        "Producer": "3-Heights(TM) PDF Security Shell 4.8.25.2 (http://www.pdf-tools.com) / pdcat (www.pdf-tools.com)",
                        "Trapped": "False",
                    },
                )
            ]
        ],
    )


class ModelCapability(str, Enum):
    completion = "completion"
    chat = "chat"
    image = "image"
    embed = "embed"
    rerank = "rerank"


class ModelInfo(BaseModel):
    id: str = Field(
        description="Unique identifier of the model.",
        examples=["openai/gpt-3.5-turbo"],
    )
    object: str = Field(
        default="model",
        description="Type of API response object.",
        examples=["model"],
    )
    name: str = Field(
        default="openai/gpt-3.5-turbo",
        description="Name of model.",
        examples=["openai/gpt-3.5-turbo"],
    )
    context_length: int = Field(
        description="Context length of model.",
        examples=[16384],
    )
    languages: list[str] = Field(
        description="List of languages which the model is well-versed in.",
        examples=[["en"]],
    )
    capabilities: list[Literal["completion", "chat", "image", "embed", "rerank"]] = Field(
        description="List of capabilities of model.",
        examples=[["chat"]],
    )
    owned_by: str = Field(
        description="The organization that owns the model.",
        examples=["openai"],
    )


class ModelInfoResponse(BaseModel):
    object: str = Field(
        default="chat.model_info",
        description="Type of API response object.",
        examples=["chat.model_info"],
    )
    data: list[ModelInfo] = Field(
        description="List of model information.",
    )


class LLMModelConfig(ModelInfo):
    litellm_id: str = Field(
        default="",
        description="LiteLLM routing name for self-hosted models.",
        # exclude=True,
    )
    api_base: str = Field(
        default="",
        description="Hosting url for the model.",
    )


class EmbeddingModelConfig(BaseModel):
    id: str = Field(
        description=(
            "Provider and model name in this format {provider}/{model}, "
            "for self-host model with infinity do ellm/{org}/{model}"
        )
    )
    litellm_id: str = Field(
        description="LiteLLM compatible model ID.",
    )
    owned_by: str = Field(
        description="The organization that owns the model.",
        examples=["openai"],
    )
    context_length: int = Field(
        description="Max context length of the model.",
    )
    embedding_size: int = Field(
        description="Embedding size of the model",
    )
    dimensions: int | None = Field(
        default=None,
        description="Dimensions, a reduced embedding size (openai specs).",
    )  # currently only useful for openai
    languages: list[str] | None = Field(
        default=["en"],
        description="Supported language",
    )
    transform_query: str | None = Field(
        default=None,
        description="Transform query that might be needed, esp. for hf models",
    )  # most likely only useful for hf models
    api_base: str = Field(
        default="",
        description="Hosting url for the model.",
    )
    capabilities: list[Literal["embed"]] = Field(
        default=["embed"],
        description="List of capabilities of model.",
        examples=[["embed"]],
    )


class RerankingModelConfig(BaseModel):
    id: str = Field(
        description=(
            "Provider and model name in this format {provider}/{model}, "
            "for self-host model with infinity do ellm/{org}/{model}"
        )
    )
    owned_by: str = Field(
        description="The organization that owns the model.",
        examples=["openai"],
    )
    context_length: int = Field(
        description="Max context length of the model.",
    )
    languages: list[str] | None = Field(
        default=["en"],
        description="Supported language.",
    )
    api_base: str = Field(
        default="",
        description="Hosting url for the model.",
    )
    capabilities: list[Literal["rerank"]] = Field(
        default=["rerank"],
        description="List of capabilities of model.",
        examples=[["rerank"]],
    )


class ModelListConfig(BaseModel):
    llm_models: list[LLMModelConfig]
    embed_models: list[EmbeddingModelConfig]
    rerank_models: list[RerankingModelConfig]


class ChatRole(str, Enum):
    """Represents who said a chat message."""

    SYSTEM = "system"
    """The message is from the system (usually a steering prompt)."""
    USER = "user"
    """The message is from the user."""
    ASSISTANT = "assistant"
    """The message is from the language model."""
    # FUNCTION = "function"
    # """The message is the result of a function call."""


pat = re.compile(r"[^a-zA-Z0-9_-]")


def sanitise_name(v: str) -> str:
    """Replace any non-alphanumeric and dash characters with space.

    Args:
        v (str): Raw name string.

    Returns:
        out (str): Sanitised name string that is safe for OpenAI.
    """
    return re.sub(pat, "_", v).strip()


MessageName = Annotated[str, AfterValidator(sanitise_name)]


class ChatEntry(BaseModel):
    """Represents a message in the chat context."""

    model_config = ConfigDict(
        use_enum_values=True,
        frozen=True,
    )

    role: ChatRole
    """Who said the message?"""
    content: str
    """The content of the message."""
    name: MessageName | None = None
    """The name of the user who sent the message, if set (user messages only)."""

    @classmethod
    def system(cls, content: str, **kwargs):
        """Create a new system message."""
        return cls(role=ChatRole.SYSTEM, content=content, **kwargs)

    @classmethod
    def user(cls, content: str, **kwargs):
        """Create a new user message."""
        return cls(role=ChatRole.USER, content=content, **kwargs)

    @classmethod
    def assistant(cls, content: str | None, **kwargs):
        """Create a new assistant message."""
        return cls(role=ChatRole.ASSISTANT, content=content, **kwargs)

    @field_validator("content", mode="before")
    @classmethod
    def handle_null_content(cls, v: Any) -> Any:
        return "" if v is None else v


class ChatThread(BaseModel):
    object: str = Field(
        default="chat.thread",
        description="Type of API response object.",
        examples=["chat.thread"],
    )
    thread: list[ChatEntry] = Field(
        default=[],
        description="List of chat messages.",
        examples=[
            [
                ChatEntry.system(content="You are an assistant."),
                ChatEntry.user(content="Hello."),
            ]
        ],
    )


class CompletionUsage(BaseModel):
    prompt_tokens: int = Field(default=0, description="Number of tokens in the prompt.")
    completion_tokens: int = Field(
        default=0, description="Number of tokens in the generated completion."
    )
    total_tokens: int = Field(
        default=0, description="Total number of tokens used in the request (prompt + completion)."
    )


class ChatCompletionChoice(BaseModel):
    message: ChatEntry = Field(description="A chat completion message generated by the model.")
    index: int = Field(description="The index of the choice in the list of choices.")
    finish_reason: str | None = Field(
        default=None,
        description=(
            "The reason the model stopped generating tokens. "
            "This will be stop if the model hit a natural stop point or a provided stop sequence, "
            "length if the maximum number of tokens specified in the request was reached."
        ),
    )

    @property
    def text(self) -> str:
        """The text of the most recent chat completion."""
        return self.message.content


class ChatCompletionChoiceDelta(ChatCompletionChoice):
    @computed_field
    @property
    def delta(self) -> ChatEntry:
        return self.message


class References(BaseModel):
    object: str = Field(
        default="chat.references",
        description="The object type, which is always `chat.references`.",
        examples=["chat.references"],
    )
    chunks: list[Chunk] = Field(
        default=[],
        description="A list of `Chunk`.",
        examples=[
            [
                Chunk(
                    text="The Name of the Title is Hope\n\n...",
                    title="The Name of the Title is Hope",
                    page=0,
                    file_name="sample_tables.pdf",
                    file_path="amagpt/sample_tables.pdf",
                    metadata={
                        "total_pages": 3,
                        "Author": "Ben Trovato",
                        "CreationDate": "D:20231031072817Z",
                        "Creator": "LaTeX with acmart 2023/10/14 v1.92 Typesetting articles for the Association for Computing Machinery and hyperref 2023-07-08 v7.01b Hypertext links for LaTeX",
                        "Keywords": "Image Captioning, Deep Learning",
                        "ModDate": "D:20231031073146Z",
                        "PTEX.Fullbanner": "This is pdfTeX, Version 3.141592653-2.6-1.40.25 (TeX Live 2023) kpathsea version 6.3.5",
                        "Producer": "3-Heights(TM) PDF Security Shell 4.8.25.2 (http://www.pdf-tools.com) / pdcat (www.pdf-tools.com)",
                        "Trapped": "False",
                    },
                )
            ]
        ],
    )
    search_query: str = Field(description="Query used to retrieve items from the KB database.")
    finish_reason: Literal["stop", "context_overflow"] | None = Field(
        default=None,
        description="""
In streaming mode, reference chunk will be streamed first.
However, if the model's context length is exceeded, then there will be no further completion chunks.
In this case, "finish_reason" will be set to "context_overflow".
Otherwise, it will be None or null.
""",
    )

    def remove_contents(self):
        copy = self.model_copy(deep=True)
        for d in copy.documents:
            d.page_content = ""
        return copy


class GenTableStreamReferences(References):
    object: str = Field(
        default="gen_table.references",
        description="The object type, which is always `gen_table.references`.",
        examples=["gen_table.references"],
    )
    output_column_name: str


class GenTableChatCompletionChunks(BaseModel):
    object: str = Field(
        default="gen_table.completion.chunks",
        description="The object type, which is always `gen_table.completion.chunks`.",
        examples=["gen_table.completion.chunks"],
    )
    columns: dict[str, ChatCompletionChunk]
    row_id: str


class GenTableRowsChatCompletionChunks(BaseModel):
    object: str = Field(
        default="gen_table.completion.rows",
        description="The object type, which is always `gen_table.completion.rows`.",
        examples=["gen_table.completion.rows"],
    )
    rows: list[GenTableChatCompletionChunks]


class ChatCompletionChunk(BaseModel):
    id: str = Field(
        description="A unique identifier for the chat completion. Each chunk has the same ID."
    )
    object: str = Field(
        default="chat.completion.chunk",
        description="The object type, which is always `chat.completion.chunk`.",
        examples=["chat.completion.chunk"],
    )
    created: int = Field(
        description="The Unix timestamp (in seconds) of when the chat completion was created."
    )
    model: str = Field(description="The model used for the chat completion.")
    usage: CompletionUsage | None = Field(
        description="Number of tokens consumed for the completion request.",
        examples=[CompletionUsage(), None],
    )
    choices: list[ChatCompletionChoice | ChatCompletionChoiceDelta] = Field(
        description="A list of chat completion choices. Can be more than one if `n` is greater than 1."
    )
    references: References | None = Field(
        default=None,
        description="Contains the references retrieved from database when performing chat completion with RAG.",
    )

    @property
    def message(self) -> ChatEntry | None:
        return self.choices[0].message if len(self.choices) > 0 else None

    @property
    def prompt_tokens(self) -> int:
        return self.usage.prompt_tokens

    @property
    def completion_tokens(self) -> int:
        return self.usage.completion_tokens

    @property
    def text(self) -> str | None:
        """The text of the most recent chat completion."""
        return self.message.content if len(self.choices) > 0 else None

    @property
    def finish_reason(self) -> str | None:
        return self.choices[0].finish_reason if len(self.choices) > 0 else None


class GenTableStreamChatCompletionChunk(ChatCompletionChunk):
    object: str = Field(
        default="gen_table.completion.chunk",
        description="The object type, which is always `gen_table.completion.chunk`.",
        examples=["gen_table.completion.chunk"],
    )
    output_column_name: str
    row_id: str


class ChatRequest(BaseModel):
    id: str = Field(
        default="",
        description="Chat ID. Must be unique against document ID for it to be embeddable. Defaults to ''.",
    )
    model: str = Field(
        default="",
        description="ID of the model to use. See the model endpoint compatibility table for details on which models work with the Chat API.",
    )
    messages: list[ChatEntry] = Field(
        description="A list of messages comprising the conversation so far.",
        min_length=1,
    )
    rag_params: RAGParams | None = Field(
        default=None,
        description="Retrieval Augmented Generation search params. Defaults to None (disabled).",
        examples=[None],
    )
    temperature: Annotated[float, Field(ge=0.001, le=2.0)] = Field(
        default=1.0,
        description="""
What sampling temperature to use, in [0.001, 2.0].
Higher values like 0.8 will make the output more random,
while lower values like 0.2 will make it more focused and deterministic.
""",
        examples=[1.0],
    )
    top_p: Annotated[float, Field(ge=0.001, le=1.0)] = Field(
        default=1.0,
        description="""
An alternative to sampling with temperature, called nucleus sampling,
where the model considers the results of the tokens with top_p probability mass.
So 0.1 means only the tokens comprising the top 10% probability mass are considered.
Must be in [0.001, 1.0].
""",
        examples=[1.0],
    )
    n: int = Field(
        default=1,
        description="How many chat completion choices to generate for each input message.",
        examples=[1],
    )
    stream: bool = Field(
        default=True,
        description="""
If set, partial message deltas will be sent, like in ChatGPT.
Tokens will be sent as server-sent events as they become available,
with the stream terminated by a 'data: [DONE]' message.
""",
        examples=[True],
    )
    stop: list[str] | None = Field(
        default=None,
        description="Up to 4 sequences where the API will stop generating further tokens.",
        examples=[None],
    )
    max_tokens: PositiveNonZeroInt = Field(
        default=2048,
        description="""
The maximum number of tokens to generate in the chat completion.
Must be in [1, context_length - 1). Default is 2048.
The total length of input tokens and generated tokens is limited by the model's context length.
""",
        examples=[2048],
    )
    presence_penalty: float = Field(
        default=0.0,
        description="""
Number between -2.0 and 2.0. Positive values penalize new tokens based on whether they appear in the text so far,
increasing the model's likelihood to talk about new topics.
""",
        examples=[0.0],
    )
    frequency_penalty: float = Field(
        default=0.0,
        description="""
Number between -2.0 and 2.0. Positive values penalize new tokens based on their existing frequency in the text so far,
decreasing the model's likelihood to repeat the same line verbatim.
""",
        examples=[0.0],
    )
    logit_bias: dict = Field(
        default={},
        description="""
Modify the likelihood of specified tokens appearing in the completion.
Accepts a json object that maps tokens (specified by their token ID in the tokenizer)
to an associated bias value from -100 to 100.
Mathematically, the bias is added to the logits generated by the model prior to sampling.
The exact effect will vary per model, but values between -1 and 1 should decrease or increase likelihood of selection;
values like -100 or 100 should result in a ban or exclusive selection of the relevant token.
""",
        examples=[{}],
    )
    user: str = Field(
        default="",
        description="A unique identifier representing your end-user. For monitoring and debugging purposes.",
        examples=[""],
    )

    @model_validator(mode="after")
    def convert_stop(self) -> Self:
        # TODO: Introduce this in v0.3
        # if isinstance(self.stop, list) and len(self.stop) == 0:
        #     self.stop = None
        if self.stop is None:
            self.stop = []
        return self


class EmbeddingRequest(BaseModel):
    input: str | list[str] = Field(
        description=(
            "Input text to embed, encoded as a string or array of strings "
            "(to embed multiple inputs in a single request). "
            "The input must not exceed the max input tokens for the model, and cannot contain empty string."
        ),
        examples=["What is a llama?", ["What is a llama?", "What is an alpaca?"]],
    )
    model: str = Field(
        description=(
            "The ID of the model to use. "
            "You can use the List models API to see all of your available models."
        ),
        examples=["openai/text-embedding-3-small-512"],
    )
    type: Literal["query", "document"] = Field(
        default="document",
        description=(
            'Whether the input text is a "query" (used to retrieve) or a "document" (to be retrieved).'
        ),
        examples=["query", "document"],
    )
    encoding_format: Literal["float", "base64"] = Field(
        default="float",
        description=(
            '_Optional_. The format to return the embeddings in. Can be either "float" or "base64". '
            "`base64` string should be decoded as a `float32` array. "
            "Example: `np.frombuffer(base64.b64decode(response), dtype=np.float32)`"
        ),
        examples=["float", "base64"],
    )


class EmbeddingResponseData(BaseModel):
    object: str = Field(
        default="embedding",
        description="The object type, which is always `embedding`.",
        examples=["embedding"],
    )
    embedding: list[float] | str = Field(
        description=(
            "The embedding vector, which is a list of floats or a base64-encoded string. "
            "The length of vector depends on the model."
        ),
        examples=[[0.0, 1.0, 2.0], []],
    )
    index: int = Field(
        default=0,
        description="The index of the embedding in the list of embeddings.",
        examples=[0, 1],
    )


class EmbeddingResponse(BaseModel):
    object: str = Field(
        default="list",
        description="The object type, which is always `list`.",
        examples=["list"],
    )
    data: list[EmbeddingResponseData] = Field(
        description="List of `EmbeddingResponseData`.",
        examples=[[EmbeddingResponseData(embedding=[0.0, 1.0, 2.0])]],
    )
    model: str = Field(
        description="The ID of the model used.",
        examples=["openai/text-embedding-3-small-512"],
    )
    usage: CompletionUsage = Field(
        default=CompletionUsage(),
        description="The number of tokens consumed.",
        examples=[CompletionUsage()],
    )


class ClipInputData(BaseModel):
    """Data model for Clip input data, assume if image_filename is None then it have to be text, otherwise, the input is an image with bytes content"""

    content: str | bytes
    """content of this input data, either be str of text or an """
    image_filename: str | None
    """image filename of the content, None if the content is text"""


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: Annotated[
        Sequence[T], Field(description="List of items paginated items.", examples=[[]])
    ] = []
    offset: Annotated[int, Field(description="Number of skipped items.", examples=[0])] = 0
    limit: Annotated[int, Field(description="Number of items per page.", examples=[0])] = 0
    total: Annotated[int, Field(description="Total number of items.", examples=[0])] = 0


def nd_array_before_validator(x):
    return np.array(x) if isinstance(x, list) else x


def datetime_str_before_validator(x):
    return x.isoformat() if isinstance(x, datetime) else str(x)


COL_NAME_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_ \-]{0,98}[a-zA-Z0-9]$"
TABLE_NAME_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{0,98}[a-zA-Z0-9]$"
ODD_SINGLE_QUOTE = r"(?<!')'(?!')"
GEN_CONFIG_VAR_PATTERN = r"(?<!\\)\${(.*?)}"


class MetaEnum(EnumMeta):

    def __contains__(cls, x):
        try:
            cls[x]
        except KeyError:
            return False
        return True


class CSVDelimiter(Enum, metaclass=MetaEnum):
    comma = ","
    """Comma-separated"""
    tab = "\t"
    """Tab-separated"""


class DtypeEnum(str, Enum, metaclass=MetaEnum):
    int_ = "int"
    int8 = "int8"
    float_ = "float"
    float32 = "float32"
    float16 = "float16"
    bool_ = "bool"
    str_ = "str"
    date_time = "date-time"


class DtypeCreateEnum(str, Enum, metaclass=MetaEnum):
    int_ = "int"
    float_ = "float"
    bool_ = "bool"
    str_ = "str"


class TableType(str, Enum, metaclass=MetaEnum):
    action = "action"
    """Action table."""
    knowledge = "knowledge"
    """Knowledge table."""
    chat = "chat"
    """Chat table."""


class ColumnSchema(BaseModel):
    id: str = Field(description="Column name.")
    dtype: DtypeEnum = Field(
        default=DtypeEnum.str_,
        description='Column data type, one of ["int", "int8", "float", "float32", "float16", "bool", "str", "date-time"]',
    )
    vlen: PositiveInt = Field(  # type: ignore
        default=0,
        description=(
            "_Optional_. Vector length. "
            "If this is larger than zero, then `dtype` must be one of the floating data types. Defaults to zero."
        ),
    )
    index: bool = Field(
        default=True,
        description=(
            "_Optional_. Whether to build full-text-search (FTS) or vector index for this column. "
            "Only applies to string and vector columns. Defaults to True."
        ),
    )
    gen_config: dict[str, Any] | None = Field(
        default=None,
        description=(
            '_Optional_. Generation config in the form of `ChatRequest`. If provided, then this column will be an "Output Column". '
            "Table columns on its left can be referenced by `${column-name}`."
        ),
    )

    @model_validator(mode="after")
    def check_vector_column_dtype(self) -> Self:
        if self.vlen > 0 and self.dtype not in (DtypeEnum.float32, DtypeEnum.float16):
            raise ValueError("Vector columns must contain float32 or float16 only.")
        return self

    @model_validator(mode="after")
    def validate_gen_config(self) -> Self:
        if self.gen_config is not None:
            # Validate
            if "embedding_model" in self.gen_config:
                self.gen_config = EmbedGenConfig.model_validate(self.gen_config).model_dump()
            else:
                self.gen_config = ChatRequest.model_validate(self.gen_config).model_dump()
        return self


class ColumnSchemaCreate(ColumnSchema):
    id: str = Field(description="Column name.")
    dtype: DtypeCreateEnum = Field(
        default=DtypeCreateEnum.str_,
        description='Column data type, one of ["int", "float", "bool", "str"]',
    )


class TableBase(BaseModel):
    id: str = Field(primary_key=True, description="Table name.")
    # version: int = 0


class TableSchema(TableBase):
    cols: list[ColumnSchema] = Field(description="List of column schema.")

    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        for i, col in enumerate(self.cols):
            gen_config = col.gen_config
            if gen_config is None:
                continue
            col_ids = set(col.id for col in self.cols[:i] if not col.id.endswith("_"))
            if col.vlen > 0:
                gen_config = EmbedGenConfig.model_validate(gen_config)
                if gen_config.source_column not in col_ids:
                    raise ValueError(
                        (
                            f"Table '{self.id}': "
                            f"Embedding config of column '{col.id}' referenced "
                            f"an invalid source column '{gen_config.source_column}'. "
                            "Make sure you only reference columns on its left. "
                            f"Available columns: {list(col_ids)}."
                        )
                    )
            else:
                num_prompts = len(gen_config["messages"])
                if num_prompts > 2:
                    self.cols[i].gen_config["messages"] = self.cols[i].gen_config["messages"][:2]
                elif num_prompts == 2:
                    pass
                elif num_prompts == 1:
                    self.cols[i].gen_config["messages"].append(
                        ChatEntry.user(content=".").model_dump()
                    )
                else:
                    raise ValueError(
                        f"`gen_config.messages` must be a list of at least length 1, received: {num_prompts:,d}"
                    )
                gen_config = ChatRequest.model_validate(self.cols[i].gen_config)
                if gen_config.messages[0].role not in (ChatRole.SYSTEM, ChatRole.SYSTEM.value):
                    raise ValueError(
                        (
                            f"Table '{self.id}': "
                            "The first `ChatEntry` in `gen_config.messages` "
                            f"of column '{col.id}' is not a system prompt. "
                            f"Saw {gen_config.messages[0].role} message."
                        )
                    )
                if gen_config.messages[1].role not in (ChatRole.USER, ChatRole.USER.value):
                    raise ValueError(
                        (
                            f"Table '{self.id}': "
                            "The second `ChatEntry` in `gen_config.messages` "
                            f"of column '{col.id}' is not a user prompt. "
                            f"Saw {gen_config.messages[1].role} message."
                        )
                    )
                for message in gen_config.messages:
                    for key in re.findall(GEN_CONFIG_VAR_PATTERN, message.content):
                        if key not in col_ids:
                            raise ValueError(
                                (
                                    f"Table '{self.id}': "
                                    f"Generation prompt of column '{col.id}' referenced "
                                    f"an invalid source column '{key}'. "
                                    "Make sure you only reference columns on its left. "
                                    f"Available columns: {list(col_ids)}."
                                )
                            )
        return self


class TableSchemaCreate(TableSchema):
    id: str = Field(description="Table name.")
    cols: list[ColumnSchemaCreate] = Field(description="List of column schema.")

    @model_validator(mode="after")
    def check_cols(self) -> Self:
        if len(set(c.id.lower() for c in self.cols)) != len(self.cols):
            raise ValueError("There are repeated column names (case-insensitive) in the schema.")
        if sum(c.id.lower() in ("id", "updated at") for c in self.cols) > 0:
            raise ValueError("Schema cannot contain column names: 'ID' or 'Updated at'.")
        if sum(c.vlen > 0 for c in self.cols) > 0:
            raise ValueError("Schema cannot contain columns with `vlen` > 0.")
        return self


class AddColumnSchema(TableSchemaCreate):
    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        # Check gen config using TableSchema
        return self


class ActionTableSchemaCreate(TableSchemaCreate):
    pass


class AddActionColumnSchema(ActionTableSchemaCreate):
    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        # Check gen config using TableSchema
        return self


class KnowledgeTableSchemaCreate(TableSchemaCreate):
    embedding_model: str

    @model_validator(mode="after")
    def check_cols(self) -> Self:
        super().check_cols()
        num_text_cols = sum(c.id.lower() in ("text", "title", "file id") for c in self.cols)
        if num_text_cols != 0:
            raise ValueError("Schema cannot contain column names: 'Text', 'Title', 'File ID'.")
        return self


class AddKnowledgeColumnSchema(TableSchemaCreate):
    @model_validator(mode="after")
    def check_cols(self) -> Self:
        super().check_cols()
        num_text_cols = sum(c.id.lower() in ("text", "title", "file id") for c in self.cols)
        if num_text_cols != 0:
            raise ValueError("Schema cannot contain column names: 'Text', 'Title', 'File ID'.")
        return self

    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        # Check gen config using TableSchema
        return self


class ChatTableSchemaCreate(TableSchemaCreate):
    @model_validator(mode="after")
    def check_cols(self) -> Self:
        super().check_cols()
        num_text_cols = sum(c.id.lower() in ("user", "ai") for c in self.cols)
        if num_text_cols != 2:
            raise ValueError("Schema must contain column names: 'User' and 'AI'.")
        return self


class AddChatColumnSchema(TableSchemaCreate):
    @model_validator(mode="after")
    def check_cols(self) -> Self:
        super().check_cols()
        return self

    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        # Check gen config using TableSchema
        return self


class TableMeta(TableBase):
    cols: list[dict[str, Any]] = Field(description="List of column schema.")
    parent_id: str | None = Field(
        default=None,
        description="The parent table ID. If None (default), it means this is a template table.",
    )
    title: str = Field(
        default="",
        description="Chat title. Defaults to ''.",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Table last update timestamp (ISO 8601 UTC).",
    )  # SQLite does not support TZ
    indexed_at_fts: str | None = Field(
        default=None, description="Table last FTS index timestamp (ISO 8601 UTC)."
    )
    indexed_at_vec: str | None = Field(
        default=None, description="Table last vector index timestamp (ISO 8601 UTC)."
    )
    indexed_at_sca: str | None = Field(
        default=None, description="Table last scalar index timestamp (ISO 8601 UTC)."
    )

    @property
    def cols_schema(self) -> list[ColumnSchema]:
        return [ColumnSchema.model_validate(c) for c in self.cols]

    @property
    def regular_cols(self) -> list[ColumnSchema]:
        return [c for c in self.cols_schema if not c.id.endswith("_")]


class TableMetaResponse(TableSchema):
    parent_id: str | None = Field(
        description="The parent table ID. If None (default), it means this is a template table.",
    )
    title: str = Field(description="Chat title. Defaults to ''.")
    updated_at: str = Field(
        description="Table last update timestamp (ISO 8601 UTC).",
    )  # SQLite does not support TZ
    indexed_at_fts: str | None = Field(
        description="Table last FTS index timestamp (ISO 8601 UTC)."
    )
    indexed_at_vec: str | None = Field(
        description="Table last vector index timestamp (ISO 8601 UTC)."
    )
    indexed_at_sca: str | None = Field(
        description="Table last scalar index timestamp (ISO 8601 UTC)."
    )
    num_rows: int = Field(description="Number of rows in the table.")

    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        return self

    @model_validator(mode="after")
    def remove_state_cols(self) -> Self:
        self.cols = [c for c in self.cols if not c.id.endswith("_")]
        return self


class EmbedGenConfig(BaseModel):
    embedding_model: str
    source_column: str


class GenConfigUpdateRequest(BaseModel):
    table_id: str = Field(description="Table name or ID.")
    column_map: dict[str, dict | None] = Field(
        description=(
            "Mapping of column ID to generation config JSON in the form of `ChatRequest`. "
            "Table columns on its left can be referenced by `${column-name}`."
        )
    )

    @model_validator(mode="after")
    def check_column_map(self) -> Self:
        if sum(n.lower() in ("id", "updated at") for n in self.column_map) > 0:
            raise ValueError("`column_map` cannot contain keys: 'ID' or 'Updated at'.")
        return self


class ColumnRenameRequest(BaseModel):
    table_id: str = Field(description="Table name or ID.")
    column_map: dict[str, str] = Field(
        description="Mapping of old column names to new column names."
    )

    @model_validator(mode="after")
    def check_column_map(self) -> Self:
        if sum(n.lower() in ("id", "updated at") for n in self.column_map) > 0:
            raise ValueError("`column_map` cannot contain keys: 'ID' or 'Updated at'.")
        return self


class ColumnReorderRequest(BaseModel):
    table_id: str = Field(description="Table name or ID.")
    column_names: list[str] = Field(description="List of column ID in the desired order.")


class ColumnDropRequest(BaseModel):
    table_id: str = Field(description="Table name or ID.")
    column_names: list[str] = Field(description="List of column ID to drop.")

    @model_validator(mode="after")
    def check_column_names(self) -> Self:
        if sum(n.lower() in ("id", "updated at") for n in self.column_names) > 0:
            raise ValueError("`column_names` cannot contain keys: 'ID' or 'Updated at'.")
        return self


class RowAddRequest(BaseModel):
    table_id: str = Field(
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
        default=True,
        description="Whether or not to stream the LLM generation.",
    )
    reindex: bool | None = Field(
        default=None,
        description=(
            "_Optional_. If True, reindex immediately. If False, wait until next periodic reindex. "
            "If None (default), reindex immediately for smaller tables."
        ),
    )
    concurrent: bool = Field(
        default=True,
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
            }
            for k, v in self.data.items()
        ]
        return (
            f"{self.__class__.__name__}("
            f"table_id={self.table_id}  stream={self.stream}  reindex={self.reindex}"
            f"concurrent={self.concurrent}  data={_data}"
            ")"
        )


class RowAddRequestWithLimit(RowAddRequest):
    data: list[dict[str, Any]] = Field(
        min_length=1,
        max_length=100,
        description=(
            "List of mapping of column names to its value. "
            "In other words, each item in the list is a row, and each item is a mapping. "
            "Minimum 1 row, maximum 100 rows."
        ),
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
    reindex: bool | None = Field(
        default=None,
        description=(
            "_Optional_. If True, reindex immediately. If False, wait until next periodic reindex. "
            "If None (default), reindex immediately for smaller tables."
        ),
    )


class RowRegen(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    row_id: str = Field(
        description="ID of the row to regenerate.",
    )
    stream: bool = Field(
        description="Whether or not to stream the LLM generation.",
    )
    reindex: bool | None = Field(
        default=None,
        description=(
            "_Optional_. If True, reindex immediately. If False, wait until next periodic reindex. "
            "If None (default), reindex immediately for smaller tables."
        ),
    )
    concurrent: bool = Field(
        default=True,
        description="_Optional_. Whether or not to concurrently generate the output columns.",
    )


class RowRegenRequest(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    row_ids: list[str] = Field(
        min_length=1,
        max_length=100,
        description="List of ID of the row to regenerate. Minimum 1 row, maximum 100 rows.",
    )
    stream: bool = Field(
        description="Whether or not to stream the LLM generation.",
    )
    reindex: bool | None = Field(
        default=None,
        description=(
            "_Optional_. If True, reindex immediately. If False, wait until next periodic reindex. "
            "If None (default), reindex immediately for smaller tables."
        ),
    )
    concurrent: bool = Field(
        default=True,
        description="_Optional_. Whether or not to concurrently generate the output rows and columns.",
    )


class RowDeleteRequest(BaseModel):
    table_id: str = Field(description="Table name or ID.")
    row_ids: list[str] | None = Field(
        min_length=1,
        max_length=100,
        default=None,
        description="List of ID of the row to delete. Minimum 1 row, maximum 100 rows.",
    )
    where: str | None = Field(
        default=None,
        description="_Optional_. SQL where clause. If not provided, will match all rows and thus deleting all table content.",
    )
    reindex: bool | None = Field(
        default=None,
        description=(
            "_Optional_. If True, reindex immediately. If False, wait until next periodic reindex. "
            "If None (default), reindex immediately for smaller tables."
        ),
    )


class EmbedFileRequest(BaseModel):
    table_id: str = Field(description="Table name or ID.")
    file_id: str = Field(description="ID of the file.")
    chunk_size: Annotated[
        int, Field(description="Maximum chunk size (number of characters). Must be > 0.", gt=0)
    ] = 1000
    chunk_overlap: Annotated[
        int, Field(description="Overlap in characters between chunks. Must be >= 0.", ge=0)
    ] = 200
    # stream: Annotated[bool, Field(description="Whether or not to stream the LLM generation.")] = (
    #     True
    # )


class SearchRequest(BaseModel):
    table_id: str = Field(description="Table name or ID.")
    query: str = Field(
        min_length=1,
        description="Query for full-text-search (FTS) and vector search. Must not be empty.",
    )
    where: str | None = Field(
        default=None,
        description="_Optional_. SQL where clause. If not provided, will match all rows.",
    )
    limit: Annotated[int, Field(gt=0, le=1_000)] = Field(
        default=100, description="_Optional_. Min 1, max 1000. Number of rows to return."
    )
    metric: str = Field(
        default="cosine",
        description='_Optional_. Vector search similarity metric. Defaults to "cosine".',
    )
    nprobes: Annotated[int, Field(gt=0, le=1000)] = Field(
        default=50,
        description=(
            "_Optional_. Set the number of partitions to search (probe)."
            "This argument is only used when the vector column has an IVF PQ index. If there is no index then this value is ignored. "
            "The IVF stage of IVF PQ divides the input into partitions (clusters) of related values. "
            "The partition whose centroids are closest to the query vector will be exhaustively searched to find matches. "
            "This parameter controls how many partitions should be searched. "
            "Increasing this value will increase the recall of your query but will also increase the latency of your query. Defaults to 50."
        ),
    )
    refine_factor: Annotated[int, Field(gt=0, le=1000)] = Field(
        default=20,
        description=(
            "_Optional_. A multiplier to control how many additional rows are taken during the refine step. "
            "This argument is only used when the vector column has an IVF PQ index. "
            "If there is no index then this value is ignored. "
            "An IVF PQ index stores compressed (quantized) values. "
            "They query vector is compared against these values and, since they are compressed, the comparison is inaccurate. "
            "This parameter can be used to refine the results. "
            "It can improve both improve recall and correct the ordering of the nearest results. "
            "To refine results LanceDb will first perform an ANN search to find the nearest limit * refine_factor results. "
            "In other words, if refine_factor is 3 and limit is the default (10) then the first 30 results will be selected. "
            "LanceDb then fetches the full, uncompressed, values for these 30 results. "
            "The results are then reordered by the true distance and only the nearest 10 are kept. Defaults to 50."
        ),
    )
    float_decimals: int = Field(
        default=0,
        description="_Optional_. Number of decimals for float values. Defaults to 0 (no rounding).",
    )
    vec_decimals: int = Field(
        default=0,
        description="_Optional_. Number of decimals for vectors. Defaults to 0 (no rounding).",
    )
    reranking_model: Annotated[
        str | None, Field(description="Reranking model to use for hybrid search.")
    ] = None


class FileUploadRequest(BaseModel):
    file_path: Annotated[str, Field(description="File path of the document to be uploaded.")]
    table_id: Annotated[str, Field(description="Knowledge Table name / ID.")]
    chunk_size: Annotated[
        int, Field(description="Maximum chunk size (number of characters). Must be > 0.", gt=0)
    ] = 1000
    chunk_overlap: Annotated[
        int, Field(description="Overlap in characters between chunks. Must be >= 0.", ge=0)
    ] = 200
    # overwrite: Annotated[
    #     bool,
    #     Field(
    #         description="Whether to overwrite the file.",
    #         examples=[True, False],
    #     ),
    # ] = False


class TableDataImportRequest(BaseModel):
    file_path: Annotated[str, Field(description="CSV or TSV file path.")]
    table_id: Annotated[str, Field(description="Table name / ID.")]
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
        str, Field(description='The delimiter of the file: can be "," or "\\t". Defaults to ",".')
    ] = ","
