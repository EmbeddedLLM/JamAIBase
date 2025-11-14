from enum import IntEnum
from typing import Any, Generic, Literal, TypeVar

from pydantic import AnyUrl, BaseModel, Field


# Standard JSON-RPC error codes
class JSONRPCErrorCode(IntEnum):
    """Standard JSON-RPC error codes as defined by the JSON-RPC 2.0 specification."""

    # Standard error codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Custom error codes
    UNAUTHORIZED = -32001
    FORBIDDEN = -32003


ProgressToken = str | int
Cursor = str
Role = Literal["user", "assistant"]
# AnyFunction: TypeAlias = Callable[..., Any]

MetaT = TypeVar("ParamsT", bound=dict[str, Any])


class RequestParamsMeta(BaseModel, extra="allow"):
    """Metadata for request parameters."""

    progressToken: ProgressToken | None = Field(
        None,
        description=(
            "If specified, the caller is requesting out-of-band progress notifications for this request (as represented by notifications/progress). "
            "The value of this parameter is an opaque token that will be attached to any subsequent notifications. "
            "The receiver is not obligated to provide these notifications."
        ),
    )


class Params(BaseModel, Generic[MetaT], extra="allow"):
    meta: MetaT | None = Field(
        None,
        alias="_meta",
        description="This parameter name is reserved by MCP to allow clients and servers to attach additional metadata.",
    )


ParamsT = TypeVar("ParamsT", bound=Params)


class PaginatedRequestParams(Params):
    cursor: str | None = Field(
        None,
        description=(
            "An opaque token representing the current pagination position. "
            "If provided, the server should return results starting after this cursor."
        ),
    )


class JSONRPCBase(BaseModel, extra="allow"):
    jsonrpc: Literal["2.0"] = "2.0"


class JSONRPCRequest(JSONRPCBase, Generic[ParamsT]):
    """Base request interface."""

    id: str | int = Field(description="Request ID.")
    method: str
    params: ParamsT | None = Field(
        None,
        description="Parameters for the request.",
    )


class PaginatedRequest(JSONRPCRequest[PaginatedRequestParams]):
    pass


class JSONRPCNotification(JSONRPCBase, Generic[ParamsT]):
    method: str
    params: ParamsT | None = Field(
        None,
        description="This parameter name is reserved by MCP to allow clients and servers to attach additional metadata to their notifications.",
    )


class InitializedNotification(JSONRPCNotification[Params]):
    method: Literal["notifications/initialized"] = "notifications/initialized"


class Result(BaseModel, extra="allow"):
    """
    Base result class that allows for additional metadata and arbitrary fields.
    """

    meta: dict[str, Any] | None = Field(
        None,
        alias="_meta",
        description="This result property is reserved by the protocol to allow clients and servers to attach additional metadata to their responses.",
    )


ResultT = TypeVar("ResultT", bound=Result)


class JSONRPCResponse(JSONRPCBase, Generic[ResultT]):
    id: str | int = Field(description="Request ID that this response corresponds to.")
    result: ResultT | None = None


class JSONRPCEmptyResponse(JSONRPCBase):
    id: str | int = Field(description="Request ID that this response corresponds to.")
    result: dict[str, Any] = {}


class ErrorData(BaseModel, extra="allow"):
    """Error information for JSON-RPC error responses."""

    code: int = Field(
        description="The error code, which is a negative integer as defined by the JSON-RPC specification.",
    )
    message: str = Field(
        description="A short description of the error. This message should be concise and limited to a single sentence.",
    )
    data: Any | None = Field(
        None,
        description=(
            "Additional information about the error. "
            "The value of this member is defined by the sender (e.g. detailed error information, nested errors etc.)."
        ),
    )


class JSONRPCError(JSONRPCBase):
    id: str | int = Field(description="Request ID that this response corresponds to.")
    error: ErrorData


class Capability(BaseModel):
    """Capabilities related to prompt templates."""

    listChanged: bool = Field(
        False,
        description="Whether this server supports notifications for changes to the prompt list.",
    )


class ResourcesCapability(Capability):
    """Capabilities related to resources."""

    subscribe: bool | None = Field(
        None,
        description="Whether this server supports subscribing to resource updates.",
    )


class ServerCapabilities(BaseModel, extra="allow"):
    """
    Capabilities that a server may support. Known capabilities are defined here,
    in this schema, but this is not a closed set: any server can define its own,
    additional capabilities.
    """

    experimental: dict[str, dict[str, Any]] | None = Field(
        None,
        description="Experimental, non-standard capabilities that the server supports.",
    )
    logging: dict[str, Any] | None = Field(
        None,
        description="Present if the server supports sending log messages to the client.",
    )
    completions: dict[str, Any] | None = Field(
        None,
        description="Present if the server supports argument autocompletion suggestions.",
    )
    prompts: Capability | None = Field(
        None,
        description="Present if the server offers any prompt templates.",
    )
    resources: ResourcesCapability | None = Field(
        None,
        description="Present if the server offers any resources to read.",
    )
    tools: Capability | None = Field(
        Capability(listChanged=False),
        description="Present if the server offers any tools to call.",
    )


class Implementation(BaseModel):
    name: str
    version: str


class InitializeRequestParams(BaseModel):
    protocolVersion: str
    capabilities: dict[str, Any]
    clientInfo: Implementation


class InitializeRequest(JSONRPCRequest[InitializeRequestParams]):
    method: Literal["initialize"] = "initialize"


class InitializeResult(Result):
    protocolVersion: Literal["2025-03-26"] = "2025-03-26"
    capabilities: ServerCapabilities
    serverInfo: Implementation
    instructions: str | None = Field(
        None,
        description=(
            "Instructions describing how to use the server and its features."
            "This can be used by clients to improve the LLM's understanding of available tools, resources, etc. "
            'It can be thought of like a "hint" to the model. '
            "For example, this information MAY be added to the system prompt."
        ),
    )


class ListToolsRequest(PaginatedRequest):
    method: Literal["tools/list"] = "tools/list"


class ToolAnnotations(BaseModel):
    """
    Additional properties describing a Tool to clients.

    NOTE: all properties in ToolAnnotations are *hints*.
    They are not guaranteed to provide a faithful description of
    tool behavior (including descriptive properties like `title`).

    Clients should never make tool use decisions based on ToolAnnotations
    received from untrusted servers.
    """

    title: str | None = Field(
        None,
        description="A human-readable title for the tool.",
    )
    readOnlyHint: bool | None = Field(
        False,
        description="If true, the tool does not modify its environment. Default: False",
    )
    destructiveHint: bool | None = Field(
        True,
        description=(
            "If true, the tool may perform destructive updates to its environment. "
            "If false, the tool performs only additive updates. "
            "(This property is meaningful only when `readOnlyHint == false`) Default: True"
        ),
    )
    idempotentHint: bool | None = Field(
        False,
        description=(
            "If true, calling the tool repeatedly with the same arguments "
            "will have no additional effect on the its environment. "
            "(This property is meaningful only when `readOnlyHint == false`) Default: False"
        ),
    )
    openWorldHint: bool | None = Field(
        True,
        description=(
            "If true, this tool may interact with an 'open world' of external "
            "entities. If false, the tool's domain of interaction is closed. "
            "For example, the world of a web search tool is open, whereas that "
            "of a memory tool is not. Default: True"
        ),
    )


class ToolInputSchema(BaseModel):
    """JSON Schema object defining the expected parameters for the tool."""

    type: Literal["object"] = "object"
    properties: dict[str, dict[str, Any]] | None = Field(
        None,
        description="Schema properties defining the tool parameters.",
    )
    required: list[str] | None = Field(
        None,
        description="List of required parameter names.",
    )


class ToolAPIInfo(BaseModel):
    path: str
    method: str
    args_types: dict[str, Literal["header", "query", "path", "body"]]
    method_info: dict[str, Any]


class Tool(BaseModel):
    """Definition for a tool the client can call."""

    name: str = Field(
        description="The name of the tool.",
    )
    description: str | None = Field(
        None,
        description=(
            "A human-readable description of the tool. "
            "This can be used by clients to improve the LLM's understanding of available tools. "
            "It can be thought of like a 'hint' to the model."
        ),
    )
    input_schema: ToolInputSchema = Field(
        alias="inputSchema",
        description="A JSON Schema object defining the expected parameters for the tool.",
    )
    annotations: ToolAnnotations | None = Field(
        None,
        description="Optional additional tool information.",
    )


class ToolAPI(Tool):
    """Definition for a tool the client can call."""

    api_info: ToolAPIInfo | None = Field(
        None,
        description="API information.",
    )


class ListToolsResult(Result):
    tools: list[Tool]


class CallToolRequestParams(Params):
    """Parameters specific to tool call requests."""

    name: str = Field(
        description="The name of the tool to call.",
    )
    arguments: dict[str, Any] | None = Field(
        None,
        description="Arguments to pass to the tool.",
    )


class CallToolRequest(JSONRPCRequest[CallToolRequestParams]):
    """Used by the client to invoke a tool provided by the server."""

    method: Literal["tools/call"] = "tools/call"


class Annotations(BaseModel):
    """
    Optional annotations for the client. The client can use annotations to inform how objects are used or displayed
    """

    audience: list[Role] | None = Field(
        None,
        description="Describes who the intended customer of this object or data is. "
        "It can include multiple entries to indicate content useful for multiple audiences (e.g., ['user', 'assistant']).",
    )
    priority: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Describes how important this data is for operating the server. "
        "A value of 1 means 'most important,' and indicates that the data is "
        "effectively required, while 0 means 'least important,' and indicates that "
        "the data is entirely optional.",
    )


class Content(BaseModel):
    annotations: Annotations | None = Field(
        None,
        description="Optional annotations for the client.",
    )


class TextContent(Content):
    """Text provided to or from an LLM."""

    type: Literal["text"] = "text"
    text: str = Field(
        description="The text content of the message.",
    )


class ImageContent(Content):
    """An image provided to or from an LLM."""

    type: Literal["image"] = "image"
    data: str = Field(
        description="The base64-encoded image data.",
    )
    mimeType: str = Field(
        description="The MIME type of the image. Different providers may support different image types.",
    )


class AudioContent(Content):
    """Audio provided to or from an LLM."""

    type: Literal["audio"] = "audio"
    data: str = Field(
        description="The base64-encoded audio data.",
    )
    mimeType: str = Field(
        description="The MIME type of the audio. Different providers may support different audio types.",
    )


class ResourceContents(BaseModel):
    """The contents of a specific resource or sub-resource."""

    uri: AnyUrl = Field(description="The URI of this resource.")
    mimeType: str | None = Field(
        None,
        description="The MIME type of this resource, if known.",
    )


class TextResourceContents(ResourceContents):
    """Resource contents with text data."""

    text: str = Field(
        description="The text of the item. This must only be set if the item can actually be represented as text (not binary data).",
    )


class BlobResourceContents(ResourceContents):
    """Resource contents with binary data."""

    blob: str = Field(
        description="A base64-encoded string representing the binary data of the item."
    )


class EmbeddedResource(Content):
    """
    The contents of a resource, embedded into a prompt or tool call result.

    It is up to the client how best to render embedded resources for the benefit
    of the LLM and/or the user.
    """

    type: Literal["resource"] = "resource"
    resource: TextResourceContents | BlobResourceContents = Field(
        description="The resource contents, either text or binary data."
    )


class CallToolResult(Result):
    content: list[TextContent | ImageContent | AudioContent | EmbeddedResource]
    isError: bool | None = Field(
        False,
        description=(
            "Whether the tool call ended in an error. "
            "If not set, this is assumed to be false (the call was successful)."
        ),
    )
