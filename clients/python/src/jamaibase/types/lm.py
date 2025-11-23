import re
from time import time
from typing import Annotated, Any, Literal, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from jamaibase.types.common import (
    EXAMPLE_EMBEDDING_MODEL_IDS,
    EXAMPLE_RERANKING_MODEL_IDS,
    EmptyIfNoneStr,
    PositiveInt,
    PositiveNonZeroInt,
)
from jamaibase.utils.types import StrEnum

CITATION_PATTERN = r"\[(@[0-9]+)[; ]*\]"


class Chunk(BaseModel):
    """Class for storing a piece of text and associated metadata."""

    text: str = Field(
        description="Chunk text.",
    )
    title: str = Field(
        "",
        description='Document title. Defaults to "".',
    )
    page: int | None = Field(
        None,
        description="Document page the chunk text is from. Defaults to None.",
    )
    file_name: str = Field(
        "",
        description='File name. Defaults to "".',
    )
    file_path: str = Field(
        "",
        description='File path. Defaults to "".',
    )
    document_id: str = Field(
        "",
        description='Document ID. Defaults to "".',
    )
    chunk_id: str = Field(
        "",
        description='Chunk ID. Defaults to "".',
    )
    context: dict[str, str] = Field(
        {},
        description="Additional context that should be included in the RAG prompt. Defaults to an empty dictionary.",
    )
    metadata: dict = Field(
        {},
        description=(
            "Arbitrary metadata about the page content (e.g., source, relationships to other documents, etc.). "
            "Defaults to an empty dictionary."
        ),
    )


class SplitChunksParams(BaseModel):
    method: str = Field(
        "RecursiveCharacterTextSplitter",
        description="Name of the splitter.",
        examples=["RecursiveCharacterTextSplitter"],
    )
    chunk_size: PositiveNonZeroInt = Field(
        1000,
        description="Maximum chunk size (number of characters). Must be > 0.",
        examples=[1000],
    )
    chunk_overlap: PositiveInt = Field(
        200,
        description="Overlap in characters between chunks. Must be >= 0.",
        examples=[200],
    )


class SplitChunksRequest(BaseModel):
    id: str = Field(
        "",
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
                        "Creator": "LaTeX with acmart 2023/10/14 v1.92 Typesetting articles",
                        "Keywords": "Image Captioning, Deep Learning",
                        "ModDate": "D:20231031073146Z",
                    },
                )
            ]
        ],
    )
    params: SplitChunksParams = Field(
        SplitChunksParams(),
        description=(
            "How to split each document. "
            "Defaults to `RecursiveCharacterTextSplitter` with chunk_size = 1000 and chunk_overlap = 200."
        ),
        examples=[SplitChunksParams()],
    )

    def str_trunc(self) -> str:
        return f"id={self.id} len(chunks)={len(self.chunks)} params={self.params}"


class References(BaseModel):
    object: Literal["chat.references"] = Field(
        "chat.references",
        description="Type of API response object.",
        examples=["chat.references"],
    )
    chunks: list[Chunk] = Field(
        [],
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
                        "Creator": "LaTeX with acmart 2023/10/14 v1.92 Typesetting articles",
                        "Keywords": "Image Captioning, Deep Learning",
                        "ModDate": "D:20231031073146Z",
                    },
                )
            ]
        ],
    )
    search_query: str = Field(description="Query used to retrieve items from the Knowledge Table.")
    finish_reason: Literal["stop", "context_overflow"] | None = Field(
        None,
        deprecated=True,
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


class RAGParams(BaseModel):
    table_id: str = Field(
        "",
        description="Knowledge Table ID",
        examples=["my-dataset"],
    )
    reranking_model: str | None = Field(
        None,
        description="Reranking model to use for hybrid search. Defaults to None (no reranking).",
        examples=[EXAMPLE_RERANKING_MODEL_IDS[0], None],
    )
    search_query: str = Field(
        "",
        description=(
            "Query used to retrieve items from the Knowledge Table. "
            "If not provided (default), it will be generated using LLM."
        ),
    )
    k: Annotated[int, Field(gt=0, le=1024)] = Field(
        3,
        gt=0,
        le=1024,
        description="Top-k closest text in terms of embedding distance. Must be in [1, 1024]. Defaults to 3.",
        examples=[3],
    )
    rerank: bool = Field(
        True,
        deprecated=True,
        description="(Deprecated) Flag to perform rerank on the retrieved results. Defaults to True.",
        examples=[True, False],
    )
    concat_reranker_input: bool = Field(
        False,
        description="Flag to concat title and content as reranker input. Defaults to False.",
        examples=[True, False],
    )
    inline_citations: bool = Field(
        True,
        description=(
            "If True, the model will cite sources as it writes using Pandoc-style in the form of `[@<number>]`. "
            "The number is the index of the source in the reference list, ie `[@0; @3]` means the 1st and 4th source in `References.chunks`. "
            "Defaults to True."
        ),
        examples=[True, False],
    )


class FunctionCall(BaseModel):
    name: str = Field(
        description="The name of the function to call.",
    )
    arguments: str = Field(
        description="The arguments to call the function with, as generated by the model in JSON format.",
    )


class ToolCallFunction(BaseModel):
    arguments: str
    name: str | None


class ToolCall(BaseModel):
    id: str = Field(
        description="The ID of the tool call.",
    )
    type: Literal["function"] = Field(
        "function",
        description="The type of the tool. Currently, only `function` is supported.",
    )
    function: ToolCallFunction


class AudioResponse(BaseModel):
    id: str = Field(
        description="Unique identifier for this audio response.",
    )
    expires_at: int = Field(
        description="The Unix timestamp (in seconds) for when this audio response will no longer be accessible.",
    )
    data: str = Field(
        description="Base64 encoded audio bytes generated by the model.",
    )
    transcript: str = Field(
        description="Transcript of the audio generated by the model.",
    )


class ChatCompletionDelta(BaseModel):
    role: str = Field(
        "assistant",
        description="The role of the author of this message.",
    )
    content: str | None = Field(
        None,
        description="The contents of the chunk message.",
    )
    reasoning_content: str | None = Field(
        None,
        description="The reasoning contents generated by the model.",
    )
    refusal: str | None = Field(
        None,
        description="The refusal message generated by the model.",
    )
    tool_calls: list[ToolCall] | None = Field(
        None,
        description="The tool calls generated by the model, such as function calls.",
    )
    function_call: FunctionCall | None = Field(
        None,
        deprecated=True,
        description=(
            "Deprecated and replaced by `tool_calls`. "
            "The name and arguments of a function that should be called."
        ),
    )


class ChatCompletionMessage(ChatCompletionDelta):
    # content: str = Field(
    #     description="The contents of the message.",
    # )
    audio: AudioResponse | None = Field(
        None,
        description="If the audio output modality is requested, this object contains data about the audio response from the model.",
    )


class LogProbToken(BaseModel):
    token: str = Field(
        description="The token.",
    )
    logprob: float = Field(
        description=(
            "The log probability of this token, if it is within the top 20 most likely tokens. "
            "Otherwise, the value `-9999.0` is used to signify that the token is very unlikely."
        ),
    )
    bytes: list[int] | None = Field(
        description="A list of integers representing the UTF-8 bytes representation of the token.",
    )


class LogProbs(BaseModel):
    content: list[LogProbToken] | None = Field(
        None,
        description="A list of message content tokens with log probability information.",
    )
    refusal: list[LogProbToken] | None = Field(
        None,
        description="A list of message refusal tokens with log probability information.",
    )


class ChatCompletionChoice(BaseModel):
    index: int = Field(
        description="The index of the choice in the list of choices.",
    )
    message: ChatCompletionMessage | None = Field(
        None,
        description="A chat completion message generated by the model.",
    )
    delta: ChatCompletionDelta | None = Field(
        None,
        description="A chat completion delta generated by streamed model responses.",
    )
    logprobs: LogProbs | None = Field(
        None,
        description="Log probability information for the choice.",
    )
    finish_reason: str | None = Field(
        None,
        description=(
            "The reason the model stopped generating tokens. "
            "This will be `stop` if the model hit a natural stop point or a provided stop sequence, "
            "`length` if the maximum number of tokens specified in the request was reached."
        ),
    )

    @property
    def text(self) -> str:
        """The text of the most recent chat completion."""
        message = self.message or self.delta
        return getattr(message, "content", None) or ""

    @model_validator(mode="after")
    def validate_message_delta(self):
        if self.delta is not None:
            self.message = ChatCompletionMessage.model_validate(self.delta.model_dump())
        return self


def _none_to_zero(v: int | None) -> int:
    if v is None:
        return 0
    return v


ZeroIfNoneInt = Annotated[int, BeforeValidator(_none_to_zero)]


class PromptUsageDetails(BaseModel):
    cached_tokens: ZeroIfNoneInt = Field(
        0,
        description="Cached tokens present in the prompt.",
    )
    audio_tokens: ZeroIfNoneInt = Field(
        0,
        description="Audio input tokens present in the prompt or generated by the model.",
    )


class CompletionUsageDetails(BaseModel):
    audio_tokens: ZeroIfNoneInt = Field(
        0,
        description="Audio input tokens present in the prompt or generated by the model.",
    )
    reasoning_tokens: ZeroIfNoneInt = Field(
        0,
        description="Tokens generated by the model for reasoning.",
    )
    accepted_prediction_tokens: ZeroIfNoneInt = Field(
        0,
        description="When using Predicted Outputs, the number of tokens in the prediction that appeared in the completion.",
    )
    rejected_prediction_tokens: ZeroIfNoneInt = Field(
        0,
        description="When using Predicted Outputs, the number of tokens in the prediction that did not appear in the completion.",
    )


class ToolUsageDetails(BaseModel):
    web_search_calls: ZeroIfNoneInt = Field(
        0,
        description="Number of web search calls.",
    )
    code_interpreter_calls: ZeroIfNoneInt = Field(
        0,
        description="Number of code interpreter calls.",
    )


class ChatCompletionUsage(BaseModel):
    prompt_tokens: ZeroIfNoneInt = Field(
        0,
        description="Number of tokens in the prompt.",
    )
    completion_tokens: ZeroIfNoneInt = Field(
        0,
        description="Number of tokens in the generated completion.",
    )
    total_tokens: ZeroIfNoneInt = Field(
        0,
        description="Total number of tokens used in the request (prompt + completion).",
    )
    prompt_tokens_details: PromptUsageDetails | None = Field(
        None,
        description="Breakdown of tokens used in the prompt.",
    )
    completion_tokens_details: CompletionUsageDetails | None = Field(
        None,
        description="Breakdown of tokens used in a completion.",
    )
    tool_usage_details: ToolUsageDetails | None = Field(
        None,
        description="Breakdown of tool usage details, such as web search and code interpreter calls.",
    )

    @property
    def reasoning_tokens(self) -> int:
        return getattr(self.completion_tokens_details, "reasoning_tokens", 0)


class ChatCompletionResponse(BaseModel):
    id: str = Field(
        description="A unique identifier for the chat completion.",
    )
    object: Literal["chat.completion"] = Field(
        "chat.completion",
        description="The object type, which is always `chat.completion`.",
    )
    created: int = Field(
        default_factory=lambda: int(time()),
        description="The Unix timestamp (in seconds) of when the chat completion was created.",
    )
    model: str = Field(
        description="The model used for the chat completion.",
    )
    choices: list[ChatCompletionChoice] = Field(
        description=(
            "A list of chat completion choices. "
            "Can contain more than one elements if `n` is greater than 1."
        ),
    )
    usage: ChatCompletionUsage = Field(
        description="Usage statistics for the completion request.",
    )
    references: References | None = Field(
        None,
        description="References of this Retrieval Augmented Generation (RAG) response.",
    )
    service_tier: str | None = Field(
        None,
        description="The service tier used for processing the request.",
    )
    system_fingerprint: str | None = Field(
        None,
        description="This fingerprint represents the backend configuration that the model runs with.",
    )

    @field_validator("choices", mode="after")
    @classmethod
    def validate_choices(cls, v: list[ChatCompletionChoice]) -> list[ChatCompletionChoice]:
        if len(v) > 0 and v[0].message is None:
            raise ValueError("`message` must be defined.")
        return v

    @property
    def finish_reason(self) -> str | None:
        return self.choices[0].finish_reason if len(self.choices) > 0 else None

    @property
    def delta(self) -> ChatCompletionMessage | None:
        """The delta of the first chat completion choice."""
        return self.message

    @property
    def message(self) -> ChatCompletionMessage | None:
        """The message of the first chat completion choice."""
        return self.choices[0].message if len(self.choices) > 0 else None

    @property
    def reasoning_content(self) -> str:
        """The reasoning text of the first chat completion choice message."""
        return getattr(self.message, "reasoning_content", None) or ""

    @property
    def content(self) -> str:
        """The text of the first chat completion choice message."""
        return getattr(self.message, "content", None) or ""

    @property
    def text(self) -> str:
        """The text of the most recent chat completion."""
        return self.content

    @property
    def prompt_tokens(self) -> int:
        return getattr(self.usage, "prompt_tokens", 0)

    @property
    def completion_tokens(self) -> int:
        return getattr(self.usage, "completion_tokens", 0)

    @property
    def reasoning_tokens(self) -> int:
        return getattr(self.usage, "reasoning_tokens", 0)

    @property
    def total_tokens(self) -> int:
        return getattr(self.usage, "total_tokens", 0)


class ChatCompletionChunkResponse(ChatCompletionResponse):
    object: Literal["chat.completion.chunk"] = Field(
        "chat.completion.chunk",
        description="The object type, which is always `chat.completion.chunk`.",
    )
    choices: list[ChatCompletionChoice] = Field(
        description=(
            "A list of chat completion choices. "
            "Can contain more than one elements if `n` is greater than 1. "
            'Can also be empty for the last chunk if you set stream_options: `{"include_usage": true}`.'
        ),
    )
    usage: ChatCompletionUsage | None = Field(
        None,
        description="Contains a `null` value except for the last chunk which contains the token usage statistics for the entire request.",
    )

    @field_validator("choices", mode="after")
    @classmethod
    def validate_choices(cls, v: list[ChatCompletionChoice]) -> list[ChatCompletionChoice]:
        # Override
        return v


class TextContent(BaseModel):
    type: Literal["text"] = Field(
        "text",
        description="The type of content.",
    )
    text: EmptyIfNoneStr = Field(
        description="The text content.",
    )


class ImageContentData(BaseModel):
    url: str = Field(
        description=(
            "Either a URL of the image or the base64 encoded image data "
            'in the form of `"data:<mime_type>;base64,{base64_image}"`.'
        ),
    )

    def __repr__(self):
        _url = self.url
        if len(_url) > 12:
            _url = f"{_url[:6]}...{_url[-6:]}"
        return f"{self.__class__.__name__}(url='{_url}')"


class ImageContent(BaseModel):
    type: Literal["image_url"] = Field(
        "image_url",
        description="The type of content.",
    )
    image_url: ImageContentData = Field(
        description="The image content.",
    )


class AudioContentData(BaseModel):
    data: str = Field(
        description="Base-64 encoded audio data.",
    )
    format: Literal["mp3", "wav"] = Field(
        "wav",
        description="The audio format.",
    )

    def __repr__(self):
        _data = self.data
        if len(_data) > 12:
            _data = f"{_data[:6]}...{_data[-6:]}"
        return f"{self.__class__.__name__}(data='{_data}', format='{self.format}')"


class AudioContent(BaseModel):
    type: Literal["input_audio"] = Field(
        "input_audio",
        description="The type of content.",
    )
    input_audio: AudioContentData = Field(
        description="The audio content.",
    )


# class AudioURLData(BaseModel):
#     url: str = Field(
#         description=(
#             "Either a URL of the audio or the base64 encoded audio data "
#             'in the form of `"data:<mime_type>;base64,{base64_audio}"`.'
#         ),
#     )

#     def __repr__(self):
#         _url = self.url
#         if len(_url) > 12:
#             _url = f"{_url[:6]}...{_url[-6:]}"
#         return f"{self.__class__.__name__}(url='{_url}')"


# class AudioURL(BaseModel):
#     type: Literal["audio_url"] = Field(
#         "audio_url",
#         description="The type of content.",
#     )
#     audio_url: AudioURLData = Field(
#         description="The audio content.",
#     )


class S3Content(BaseModel):
    type: Literal["input_s3"] = Field(
        "input_s3",
        description="The type of content.",
    )
    uri: str = Field(
        description="The S3 URI.",
    )
    column_name: str = Field(
        description="The column holding this data.",
    )


ChatContent = Annotated[
    Union[TextContent, ImageContent, AudioContent],
    Field(discriminator="type"),
]
ChatContentS3 = Annotated[
    Union[TextContent, S3Content],
    Field(discriminator="type"),
]


class ChatRole(StrEnum):
    """Represents who said a chat message."""

    SYSTEM = "system"
    """The message is from the system (usually a steering prompt)."""
    USER = "user"
    """The message is from the user."""
    ASSISTANT = "assistant"
    """The message is from the language model."""
    # FUNCTION = "function"
    # """The message is the result of a function call."""


def _sanitise_name(v: str) -> str:
    """Replace any non-alphanumeric and dash characters with space.

    Args:
        v (str): Raw name string.

    Returns:
        out (str): Sanitised name string that is safe for OpenAI.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", v).strip()


class ChatEntry(BaseModel):
    """Represents a message in the chat context."""

    model_config = ConfigDict(use_enum_values=True)

    role: ChatRole = Field(
        description="Who said the message?",
    )
    content: EmptyIfNoneStr | list[ChatContent] = Field(
        description="The content of the message.",
    )
    name: Annotated[str, AfterValidator(_sanitise_name)] | None = Field(
        None,
        description="The name of the user who sent the message, if set (user messages only).",
    )

    @property
    def text_content(self) -> str:
        if isinstance(self.content, str):
            return self.content
        text_contents = [c for c in self.content if isinstance(c, TextContent)]
        if len(text_contents) > 0:
            return "\n".join(c.text for c in text_contents)
        return ""

    @property
    def has_text_only(self) -> bool:
        # Explicitly use `isinstance(self.content, str)` to help the type checker
        return isinstance(self.content, str) or all(
            isinstance(c, TextContent) for c in self.content
        )

    @property
    def has_image(self) -> bool:
        # Explicitly use `isinstance(self.content, str)` to help the type checker
        return (not isinstance(self.content, str)) and any(
            isinstance(c, ImageContent) for c in self.content
        )

    @property
    def has_audio(self) -> bool:
        # Explicitly use `isinstance(self.content, str)` to help the type checker
        return (not isinstance(self.content, str)) and any(
            isinstance(c, AudioContent) for c in self.content
        )

    @classmethod
    def system(cls, content: str | list[ChatContent | ChatContentS3], **kwargs):
        """Create a new system message."""
        return cls(role="system", content=content, **kwargs)

    @classmethod
    def user(cls, content: str | list[ChatContent | ChatContentS3], **kwargs):
        """Create a new user message."""
        return cls(role="user", content=content, **kwargs)

    @classmethod
    def assistant(cls, content: str | None, **kwargs):
        """Create a new assistant message."""
        return cls(role="assistant", content=content, **kwargs)


class ChatThreadEntry(ChatEntry):
    """Represents a message in the chat thread response."""

    content: EmptyIfNoneStr | list[ChatContentS3] = Field(
        description="The content of the message.",
    )
    reasoning_content: str | None = Field(
        None,
        description="The reasoning content generated by the model. Defaults to None (not applicable).",
    )
    reasoning_time: float | None = Field(
        None,
        description=(
            "Time spent by the model generating the reasoning content. "
            "Defaults to None (not applicable)."
        ),
    )
    user_prompt: str | None = Field(
        None,
        description=(
            "Original prompt sent by the user without content interpolation/injection. "
            'Only applicable for Chat Table column that references the "User" column. '
            "Defaults to None (not applicable)."
        ),
    )
    references: References | None = Field(
        None,
        description=(
            "References of this Retrieval Augmented Generation (RAG) response. "
            "Defaults to None (not applicable)."
        ),
    )
    row_id: str | None = Field(
        None,
        description="Table row ID of this chat message. Defaults to None (not applicable).",
    )


class ChatThreadResponse(BaseModel):
    object: Literal["chat.thread"] = Field(
        "chat.thread",
        description="Type of API response object.",
        examples=["chat.thread"],
    )
    thread: list[ChatThreadEntry] = Field(
        [],
        description="List of chat messages.",
        examples=[
            [
                ChatThreadEntry.system("You are an assistant."),
                ChatThreadEntry.user("Hello."),
                ChatThreadEntry.assistant(
                    "Hello.",
                    references=References(
                        chunks=[Chunk(title="Title", text="Text")],
                        search_query="hello",
                    ),
                ),
            ]
        ],
    )
    column_id: str = Field(
        "",
        description="Table column ID of this chat thread.",
    )


class _ChatThreadsBase(BaseModel):
    object: Literal["chat.threads"] = Field(
        "chat.threads",
        description="Type of API response object.",
        examples=["chat.threads"],
    )
    threads: dict[str, ChatThreadResponse] = Field(
        [],
        description="List of chat threads.",
        examples=[
            dict(
                AI=ChatThreadResponse(
                    thread=[
                        ChatThreadEntry.system("You are an assistant."),
                        ChatThreadEntry.user("Hello."),
                        ChatThreadEntry.assistant(
                            "Hello.",
                            references=References(
                                chunks=[Chunk(title="Title", text="Text")],
                                search_query="hello",
                            ),
                        ),
                    ]
                ),
            )
        ],
    )


class ChatThreadsResponse(_ChatThreadsBase):
    table_id: str = Field(
        "",
        description="Table ID of the chat threads.",
    )


class ConversationThreadsResponse(_ChatThreadsBase):
    conversation_id: str = Field(
        "",
        description="Conversation ID of the chat threads.",
    )


class FunctionParameter(BaseModel):
    type: str = Field(
        "",
        description="The type of the parameter, e.g., 'string', 'number'.",
    )
    description: str = Field(
        "",
        description="A description of the parameter.",
    )
    enum: list[str] = Field(
        [],
        description="An optional list of allowed values for the parameter.",
    )


class FunctionParameters(BaseModel):
    type: str = Field(
        "object",
        description="The type of the parameters object, usually 'object'.",
    )
    properties: dict[str, FunctionParameter] = Field(
        description="The properties of the parameters object.",
    )
    required: list[str] = Field(
        description="A list of required parameter names.",
    )
    additionalProperties: bool = Field(
        False,
        description="Whether additional properties are allowed.",
    )


class Function(BaseModel):
    name: str = Field(
        max_length=64,
        description=(
            "The name of the function to be called. "
            "Must be a-z, A-Z, 0-9, or contain underscores and dashes, with a maximum length of 64."
        ),
    )
    description: str | None = Field(
        None,
        description="A description of what the function does, used by the model to choose when and how to call the function.",
    )
    parameters: FunctionParameters | None = Field(
        None,
        description="The parameters the functions accepts, described as a JSON Schema object.",
    )
    strict: bool = Field(
        False,
        description=(
            "Whether to enable strict schema adherence when generating the function call. "
            "If set to `true`, the model will follow the exact schema defined in the `parameters` field. "
            "Only a subset of JSON Schema is supported when `strict` is `true`."
        ),
    )


class FunctionTool(BaseModel):
    type: Literal["function"] = Field(
        "function",
        description="The type of the tool. Currently, only `function` is supported.",
    )
    function: Function


class WebSearchTool(BaseModel):
    type: Literal["web_search"] = Field(
        "web_search",
        description="The type of tool.",
    )


class CodeInterpreterTool(BaseModel):
    type: Literal["code_interpreter"] = Field(
        "code_interpreter",
        description="The type of tool.",
    )
    container: dict[str, str] = Field(
        {"type": "auto"},
        description="The code interpreter container.",
    )


Tool = Annotated[
    WebSearchTool | CodeInterpreterTool | FunctionTool,
    Field(
        discriminator="type",
        description=(
            "The type of tool. "
            "Currently, one of `web_search`, `code_interpreter`, or `function`. "
            "Note that `web_search` and `code_interpreter` are only supported with OpenAI models. "
            "They will be ignored with other models."
        ),
    ),
]


class ToolChoiceFunction(BaseModel):
    name: str = Field(
        description="The name of the function to call.",
    )


class ToolChoice(BaseModel):
    type: str = Field(
        "function",
        description="The type of the tool. Currently, only `function` is supported.",
    )
    function: ToolChoiceFunction = Field(
        description="The function that should be called.",
    )


def _empty_list_to_none(v: list[str]) -> list[str] | None:
    if len(v) == 0:
        v = None
    return v


class ChatRequestBase(BaseModel):
    """
    Base for chat request and LLM gen config.
    """

    model: str = Field(
        "",
        description='ID of the model to use. Defaults to "".',
    )
    rag_params: RAGParams | None = Field(
        None,
        description="Retrieval Augmented Generation params. Defaults to None (disabled).",
        examples=[RAGParams(table_id="papers"), None],
    )
    tools: list[Tool] | None = Field(
        None,
        description=(
            "A list of tools available for the chat model to use. "
            "Note that `web_search` and `code_interpreter` are only supported with OpenAI models. "
            "They will be ignored with other models."
        ),
        min_length=1,
        examples=[
            [
                WebSearchTool(),
                CodeInterpreterTool(),
                FunctionTool(
                    type="function",
                    function=Function(
                        name="get_weather",
                        description="Get current temperature for a given location.",
                        parameters=FunctionParameters(
                            type="object",
                            properties={
                                "location": FunctionParameter(
                                    type="string",
                                    description="City and country e.g. Bogotá, Colombia",
                                )
                            },
                            required=["location"],
                            additionalProperties=False,
                        ),
                    ),
                ),
            ],
        ],
    )
    tool_choice: Literal["none", "auto", "required"] | ToolChoice | None = Field(
        None,
        description=(
            "Controls which (if any) tool is called by the model. "
            '`"none"` means the model will not call any tool and instead generates a message. '
            '`"auto"` means the model can pick between generating a message or calling one or more tools. '
            '`"required"` means the model must call one or more tools. '
            'Specifying a particular tool via `{"type": "function", "function": {"name": "my_function"}` forces the model to call that tool. '
            '`"none"` is the default when no tools are present. '
            '`"auto"` is the default if tools are present.'
        ),
        examples=[
            "auto",
            ToolChoice(type="function", function=ToolChoiceFunction(name="get_delivery_date")),
        ],
    )
    temperature: float = Field(
        0.2,
        ge=0,
        description=(
            "What sampling temperature to use. "
            "Higher values like 0.8 will make the output more random, "
            "while lower values like 0.2 will make it more focused and deterministic. "
            "Note that this parameter will be ignored when using that do not support it, "
            "such as OpenAI's reasoning models and Anthropic with extended thinking."
        ),
        examples=[0.2],
    )
    top_p: float = Field(
        0.6,
        ge=0.001,
        description=(
            "An alternative to sampling with temperature, called nucleus sampling, "
            "where the model considers the results of the tokens with top_p probability mass. "
            "So 0.1 means only the tokens comprising the top 10% probability mass are considered. "
            "Note that this parameter will be ignored when using that do not support it, "
            "such as OpenAI's reasoning models and Anthropic with extended thinking."
        ),
        examples=[0.6],
    )
    stream: bool = Field(
        True,
        description=(
            "If set, partial message deltas will be sent, like in ChatGPT. "
            "Tokens will be sent as server-sent events (SSE) as they become available, "
            "with the stream terminated by a `data: [DONE]` message."
        ),
        examples=[True, False],
    )
    max_tokens: PositiveNonZeroInt = Field(
        2048,
        description=(
            "The maximum number of tokens to generate in the chat completion. "
            "Must be in [1, context_length - 1). Default is 2048. "
            "The total length of input tokens and generated tokens is limited by the model's context length."
        ),
        examples=[2048],
    )
    stop: Annotated[list[str], AfterValidator(_empty_list_to_none)] | None = Field(
        None,
        min_length=1,
        description=(
            "A list of sequences where the API will stop generating further tokens. "
            "Note that this parameter will be ignored when using that do not support it, "
            "such as OpenAI's reasoning models."
        ),
        examples=[None],
    )
    presence_penalty: float = Field(
        0.0,
        description=(
            "Number between -2.0 and 2.0. Positive values penalize new tokens based on whether they appear in the text so far, "
            "increasing the model's likelihood to talk about new topics. "
            "Note that this parameter will be ignored when using that do not support it, "
            "such as OpenAI's reasoning models."
        ),
        examples=[0.0],
    )
    frequency_penalty: float = Field(
        0.0,
        description=(
            "Number between -2.0 and 2.0. Positive values penalize new tokens based on their existing frequency in the text so far, "
            "decreasing the model's likelihood to repeat the same line verbatim. "
            "Note that this parameter will be ignored when using that do not support it, "
            "such as OpenAI's reasoning models."
        ),
        examples=[0.0],
    )
    logit_bias: dict = Field(
        {},
        description=(
            "Modify the likelihood of specified tokens appearing in the completion. "
            "Accepts a JSON object that maps tokens (specified by their token ID in the tokenizer) "
            "to an associated bias value from -100 to 100. "
            "Mathematically, the bias is added to the logits generated by the model prior to sampling. "
            "The exact effect will vary per model, but values between -1 and 1 should decrease or increase likelihood of selection; "
            "values like -100 or 100 should result in a ban or exclusive selection of the relevant token. "
            "Note that this parameter will be ignored when using that do not support it, "
            "such as OpenAI's reasoning models."
        ),
        examples=[{}],
    )
    reasoning_effort: Literal["disable", "minimal", "low", "medium", "high"] | None = Field(
        "minimal",
        description=(
            "Constrains effort on reasoning for reasoning models. "
            "Currently supported values are `disable`, `minimal`, `low`, `medium`, and `high`. "
            "Reducing reasoning effort can result in faster responses and fewer tokens used on reasoning in a response. "
            "For non-OpenAI models, `low` ~ 1024 tokens, `medium` ~ 2048 tokens, `high` ~ 4096 tokens. "
            "Note that this parameter will be ignored when using models that do not support it, "
            "such as non-reasoning models."
        ),
        examples=["low"],
    )
    reasoning_effort: Literal["disable", "minimal", "low", "medium", "high"] | None = Field(
        None,
        description=(
            "Constrains effort on reasoning for reasoning models. "
            "Currently supported values are `disable`, `minimal`, `low`, `medium`, and `high`. "
            "Reducing reasoning effort can result in faster responses and fewer tokens used on reasoning in a response. "
            "For non-OpenAI models, `low` ~ 1024 tokens, `medium` ~ 4096 tokens, `high` ~ 8192 tokens. "
            "Note that this parameter will be ignored when using models that do not support it, "
            "such as non-reasoning models."
        ),
        examples=["low"],
    )
    thinking_budget: int | None = Field(
        None,
        ge=0,
        description=(
            "Model reasoning budget in tokens. "
            "Set to zero to disable reasoning if supported. "
            "For OpenAI models, 1 <= budget <= 1024 is low, 1025 <= budget <= 4096 is medium, 4097 <= budget <= 8192 is high. "
            "Note that this parameter will be ignored when using models that do not support it, "
            "such as non-reasoning models."
        ),
        examples=[1024],
    )
    reasoning_summary: Literal["auto", "concise", "detailed"] = Field(
        "auto",
        description=(
            "To access the most detailed summarizer available for a model, set the value of this parameter to auto. "
            "auto will be equivalent to detailed for most reasoning models today, "
            "but there may be more granular settings in the future. "
            "Will be ignored if the model does not support it."
        ),  # https://platform.openai.com/docs/guides/reasoning/advice-on-prompting#reasoning-summaries
    )

    @property
    def hyperparams(self) -> dict[str, Any]:
        # object key could cause issue to some LLM provider, ex: Anthropic
        return self.model_dump(exclude_none=True, exclude={"object", "messages", "rag_params"})


class ChatRequest(ChatRequestBase):
    id: str = Field(
        "",
        description='Chat ID for logging. Defaults to "".',
    )
    messages: list[ChatEntry] = Field(
        min_length=1,
        description="A list of messages comprising the conversation so far.",
    )
    max_completion_tokens: PositiveNonZeroInt | None = Field(
        None,
        description=(
            "An upper bound for the number of tokens that can be generated for a completion, "
            "including visible output tokens and reasoning tokens. "
            "Must be in [1, context_length - 1). Default is 2048. "
            "If both `max_completion_tokens` and `max_tokens` are set, `max_completion_tokens` will be used. "
        ),
        examples=[2048],
    )
    n: int = Field(
        1,
        description=(
            "How many chat completion choices to generate for each input message. "
            "Note that this parameter will be ignored when using models and tools that do not support it."
        ),
        examples=[1],
    )
    user: str = Field(
        "",
        description="A unique identifier representing your end-user. For monitoring and debugging purposes.",
        examples=[""],
    )
    stream: bool = Field(
        False,
        description=(
            "If set, partial message deltas will be sent, like in ChatGPT. "
            "Tokens will be sent as server-sent events (SSE) as they become available, "
            "with the stream terminated by a 'data: [DONE]' message."
        ),
        examples=[True, False],
    )

    @model_validator(mode="after")
    def validate_params(self):
        self.max_tokens = self.max_completion_tokens or self.max_tokens
        if self.thinking_budget and self.thinking_budget > self.max_tokens:
            raise ValueError("`thinking_budget` cannot be higher than `max_tokens`.")
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
        examples=EXAMPLE_EMBEDDING_MODEL_IDS,
    )
    type: Literal["query", "document"] = Field(
        "document",
        description=(
            'Whether the input text is a "query" (used to retrieve) or a "document" (to be retrieved).'
        ),
        examples=["query", "document"],
    )
    encoding_format: Literal["float", "base64"] = Field(
        "float",
        description=(
            '_Optional_. The format to return the embeddings in. Can be either "float" or "base64". '
            "`base64` string should be decoded as a `float32` array. "
            "Example: `np.frombuffer(base64.b64decode(response), dtype=np.float32)`"
        ),
        examples=["float", "base64"],
    )
    dimensions: PositiveNonZeroInt | None = Field(
        None,
        description=(
            "The number of dimensions the resulting output embeddings should have. "
            "Note that this parameter will only be used when using models that support Matryoshka embeddings."
        ),
    )


class EmbeddingResponseData(BaseModel):
    object: Literal["embedding"] = Field(
        "embedding",
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
        0,
        description="The index of the embedding in the list of embeddings.",
        examples=[0, 1],
    )


class EmbeddingUsage(BaseModel):
    prompt_tokens: ZeroIfNoneInt = Field(
        0,
        description="Number of tokens in the prompt.",
    )
    total_tokens: ZeroIfNoneInt = Field(
        0,
        description="Total number of tokens used in the request.",
    )


class EmbeddingResponse(BaseModel):
    object: Literal["list"] = Field(
        "list",
        description="Type of API response object.",
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
    usage: EmbeddingUsage = Field(
        EmbeddingUsage(),
        description="The number of tokens consumed.",
        examples=[EmbeddingUsage()],
    )


class RerankingRequest(BaseModel):
    model: str = Field(
        description=(
            "The ID of the model to use. "
            "You can use the List models API to see all of your available models."
        ),
        examples=EXAMPLE_RERANKING_MODEL_IDS,
    )
    documents: list[str]
    query: str


class RerankingData(BaseModel):
    object: Literal["reranking"] = Field(
        "reranking",
        description="Type of API response object.",
        examples=["reranking"],
    )
    index: int
    relevance_score: float


class RerankingApiVersion(BaseModel):
    version: str = Field(
        "",
        description="API version.",
        examples=["2"],
    )
    is_deprecated: bool = Field(
        False,
        description="Whether it is deprecated.",
        examples=[False],
    )
    is_experimental: bool = Field(
        False,
        description="Whether it is experimental.",
        examples=[False],
    )


class RerankingBilledUnits(BaseModel):
    images: int | None = Field(None, description="The number of billed images.")
    input_tokens: int | None = Field(None, description="The number of billed input tokens.")
    output_tokens: int | None = Field(None, description="The number of billed output tokens.")
    search_units: float | None = Field(None, description="The number of billed search units.")
    classifications: float | None = Field(
        None, description="The number of billed classifications units."
    )


class RerankingMetaUsage(BaseModel):
    input_tokens: int | None = Field(
        None,
        description="The number of tokens used as input to the model.",
    )
    output_tokens: int | None = Field(
        None,
        description="The number of tokens produced by the model.",
    )


class RerankingUsage(RerankingMetaUsage):
    documents: ZeroIfNoneInt = Field(
        description="The number of documents processed.",
    )


class RerankingMeta(BaseModel):
    model: str = Field(
        description="The ID of the model used.",
        examples=["cohere/rerank-multilingual-v3.0"],
    )
    api_version: RerankingApiVersion | None = Field(
        None,
        description="API version.",
        examples=[RerankingApiVersion(), None],
    )
    billed_units: RerankingBilledUnits | None = Field(
        None,
        description="Billed units.",
        examples=[RerankingBilledUnits(), None],
    )
    tokens: RerankingMetaUsage | None = Field(
        None,
        description="Token usage.",
        examples=[RerankingMetaUsage(input_tokens=500), None],
    )
    warnings: list[str] | None = Field(
        None,
        description="Warnings.",
        examples=[["This is a warning."], None],
    )


class RerankingResponse(BaseModel):
    object: Literal["list"] = Field(
        "list",
        description="Type of API response object.",
        examples=["list"],
    )
    results: list[RerankingData] = Field(
        description="List of `RerankingResponseData`.",
        examples=[[RerankingData(index=0, relevance_score=0.0032)]],
    )
    usage: RerankingUsage = Field(
        description="Usage.",
        examples=[RerankingUsage(documents=10), None],
    )
    meta: RerankingMeta = Field(
        description="Reranking metadata from Cohere.",
    )
