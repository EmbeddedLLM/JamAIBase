from pydantic import Field
from typing_extensions import deprecated

from jamaibase.types.gen_table import (
    CellCompletionResponse,
    CellReferencesResponse,
    MultiRowAddRequest,
    MultiRowCompletionResponse,
    MultiRowDeleteRequest,
    MultiRowRegenRequest,
    RowCompletionResponse,
)
from jamaibase.types.lm import (
    ChatCompletionChoice,
    ChatCompletionChunkResponse,
    ChatCompletionMessage,
    ChatCompletionUsage,
    ChatRequest,
    ChatThreadResponse,
    Function,
    ToolCall,
    ToolCallFunction,
)
from jamaibase.types.model import ModelInfoListResponse
from jamaibase.utils.types import StrEnum


@deprecated(
    "AdminOrderBy is deprecated, use string instead.",
    category=FutureWarning,
    stacklevel=1,
)
class AdminOrderBy(StrEnum):
    ID = "id"
    """Sort by `id` column."""
    NAME = "name"
    """Sort by `name` column."""
    CREATED_AT = "created_at"
    """Sort by `created_at` column."""
    UPDATED_AT = "updated_at"
    """Sort by `updated_at` column."""


@deprecated(
    "GenTableOrderBy is deprecated, use string instead.",
    category=FutureWarning,
    stacklevel=1,
)
class GenTableOrderBy(StrEnum):
    ID = "id"
    """Sort by `id` column."""
    UPDATED_AT = "updated_at"
    """Sort by `updated_at` column."""


@deprecated(
    "ModelInfoResponse is deprecated, use ModelInfoListResponse instead.",
    category=FutureWarning,
    stacklevel=1,
)
class ModelInfoResponse(ModelInfoListResponse):
    object: str = Field(
        default="chat.model_info",
        description="Type of API response object.",
        examples=["chat.model_info"],
    )


@deprecated(
    "MessageToolCallFunction is deprecated, use ToolCallFunction instead.",
    category=FutureWarning,
    stacklevel=1,
)
class MessageToolCallFunction(ToolCallFunction):
    pass


@deprecated(
    "MessageToolCall is deprecated, use ToolCall instead.",
    category=FutureWarning,
    stacklevel=1,
)
class MessageToolCall(ToolCall):
    pass


@deprecated(
    "ChatCompletionChoiceDelta is deprecated, use ChatCompletionChoice instead.",
    category=FutureWarning,
    stacklevel=1,
)
class ChatCompletionChoiceDelta(ChatCompletionChoice):
    pass


@deprecated(
    "CompletionUsage is deprecated, use ChatCompletionUsage instead.",
    category=FutureWarning,
    stacklevel=1,
)
class CompletionUsage(ChatCompletionUsage):
    pass


@deprecated(
    "ChatCompletionChunk is deprecated, use ChatCompletionChunkResponse instead.",
    category=FutureWarning,
    stacklevel=1,
)
class ChatCompletionChunk(ChatCompletionChunkResponse):
    pass


@deprecated(
    "ChatCompletionChoiceOutput is deprecated, use ChatCompletionMessage instead.",
    category=FutureWarning,
    stacklevel=1,
)
class ChatCompletionChoiceOutput(ChatCompletionMessage):
    pass


@deprecated(
    "ChatThread is deprecated, use ChatThreadResponse instead.",
    category=FutureWarning,
    stacklevel=1,
)
class ChatThread(ChatThreadResponse):
    pass


@deprecated(
    "ToolFunction is deprecated, use Function instead.",
    category=FutureWarning,
    stacklevel=1,
)
class ToolFunction(Function):
    pass


@deprecated(
    "ChatRequestWithTools is deprecated, use ChatRequest instead.",
    category=FutureWarning,
    stacklevel=1,
)
class ChatRequestWithTools(ChatRequest):
    pass


@deprecated(
    "GenTableStreamReferences is deprecated, use CellReferencesResponse instead.",
    category=FutureWarning,
    stacklevel=1,
)
class GenTableStreamReferences(CellReferencesResponse):
    pass


@deprecated(
    "GenTableStreamChatCompletionChunk is deprecated, use CellCompletionResponse instead.",
    category=FutureWarning,
    stacklevel=1,
)
class GenTableStreamChatCompletionChunk(CellCompletionResponse):
    pass


@deprecated(
    "GenTableChatCompletionChunks is deprecated, use RowCompletionResponse instead.",
    category=FutureWarning,
    stacklevel=1,
)
class GenTableChatCompletionChunks(RowCompletionResponse):
    pass


@deprecated(
    "GenTableRowsChatCompletionChunks is deprecated, use MultiRowCompletionResponse instead.",
    category=FutureWarning,
    stacklevel=1,
)
class GenTableRowsChatCompletionChunks(MultiRowCompletionResponse):
    pass


@deprecated(
    "RowAddRequest is deprecated, use MultiRowAddRequest instead.",
    category=FutureWarning,
    stacklevel=1,
)
class RowAddRequest(MultiRowAddRequest):
    pass


@deprecated(
    "RowRegenRequest is deprecated, use MultiRowRegenRequest instead.",
    category=FutureWarning,
    stacklevel=1,
)
class RowRegenRequest(MultiRowRegenRequest):
    pass


@deprecated(
    "RowDeleteRequest is deprecated, use MultiRowDeleteRequest instead.",
    category=FutureWarning,
    stacklevel=1,
)
class RowDeleteRequest(MultiRowDeleteRequest):
    pass
