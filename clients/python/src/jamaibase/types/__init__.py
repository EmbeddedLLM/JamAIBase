import re
from decimal import Decimal
from typing import Annotated, Generic, Self, TypeVar

from pydantic import BaseModel, EmailStr, Field, computed_field

from jamaibase.types.billing import (  # noqa: F401
    DBStorageUsageData,
    EgressUsageData,
    EmbedUsageData,
    FileStorageUsageData,
    ImageGenUsageData,
    LlmUsageData,
    RerankUsageData,
    UsageData,
)
from jamaibase.types.common import (  # noqa: F401
    DEFAULT_MUL_LANGUAGES,
    EXAMPLE_CHAT_MODEL_IDS,
    EXAMPLE_EMBEDDING_MODEL_IDS,
    EXAMPLE_RERANKING_MODEL_IDS,
    DatetimeUTC,
    EmptyIfNoneStr,
    FilePath,
    JSONInput,
    JSONInputBin,
    JSONOutput,
    JSONOutputBin,
    LanguageCodeList,
    NullableStr,
    PositiveInt,
    PositiveNonZeroInt,
    Progress,
    ProgressStage,
    ProgressState,
    SanitisedMultilineStr,
    SanitisedNonEmptyStr,
    SanitisedStr,
    TableImportProgress,
    YAMLInput,
    YAMLOutput,
    empty_string_to_none,
    none_to_empty_string,
)
from jamaibase.types.compat import (  # noqa: F401
    AdminOrderBy,
    ChatCompletionChoiceDelta,
    ChatCompletionChoiceOutput,
    ChatCompletionChunk,
    ChatRequestWithTools,
    ChatThread,
    CompletionUsage,
    GenTableChatCompletionChunks,
    GenTableOrderBy,
    GenTableRowsChatCompletionChunks,
    GenTableStreamChatCompletionChunk,
    GenTableStreamReferences,
    MessageToolCall,
    MessageToolCallFunction,
    ModelInfoResponse,
    RowAddRequest,
    RowDeleteRequest,
    RowRegenRequest,
    ToolFunction,
)
from jamaibase.types.conversation import (  # noqa: F401
    AgentMetaResponse,
    ConversationCreateRequest,
    ConversationMetaResponse,
    MessageAddRequest,
    MessagesRegenRequest,
    MessageUpdateRequest,
)
from jamaibase.types.db import (  # noqa: F401
    CloudProvider,
    Deployment_,
    DeploymentCreate,
    DeploymentRead,
    DeploymentUpdate,
    ModelCapability,
    ModelConfig_,
    ModelConfigCreate,
    ModelConfigRead,
    ModelConfigUpdate,
    ModelInfo,
    ModelInfoRead,
    ModelProvider,
    ModelType,
    OnPremProvider,
    Organization_,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    OrgMember_,
    OrgMemberCreate,
    OrgMemberRead,
    OrgMemberUpdate,
    PaymentState,
    PricePlan_,
    PricePlanCreate,
    PricePlanRead,
    PricePlanUpdate,
    PriceTier,
    Product,
    Products,
    ProductType,
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
    RankedRole,
    Role,
    Secret_,
    SecretCreate,
    SecretRead,
    SecretUpdate,
    User_,
    UserAuth,
    UserCreate,
    UserRead,
    UserReadObscured,
    UserUpdate,
    VerificationCode_,
    VerificationCodeCreate,
    VerificationCodeRead,
    VerificationCodeUpdate,
)
from jamaibase.types.file import (  # noqa: F401
    FileUploadResponse,
    GetURLRequest,
    GetURLResponse,
)
from jamaibase.types.gen_table import (  # noqa: F401
    ActionTableSchemaCreate,
    AddActionColumnSchema,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    CellCompletionResponse,
    CellReferencesResponse,
    ChatTableSchemaCreate,
    CodeGenConfig,
    ColumnDropRequest,
    ColumnRenameRequest,
    ColumnReorderRequest,
    ColumnSchema,
    ColumnSchemaCreate,
    CSVDelimiter,
    DiscriminatedGenConfig,
    EmbedGenConfig,
    GenConfigUpdateRequest,
    ImageGenConfig,
    KnowledgeTableSchemaCreate,
    LLMGenConfig,
    MultiRowAddRequest,
    MultiRowCompletionResponse,
    MultiRowDeleteRequest,
    MultiRowRegenRequest,
    MultiRowUpdateRequest,
    MultiRowUpdateRequestWithLimit,
    PythonGenConfig,
    RowCompletionResponse,
    RowRegen,
    RowUpdateRequest,
    SearchRequest,
    TableDataImportRequest,
    TableImportRequest,
    TableMeta,
    TableMetaResponse,
    TableSchemaCreate,
    TableType,
)
from jamaibase.types.legacy import (  # noqa: F401
    VectorSearchRequest,
    VectorSearchResponse,
)
from jamaibase.types.lm import (  # noqa: F401
    CITATION_PATTERN,
    AudioContent,
    AudioContentData,
    AudioResponse,
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
    CodeInterpreterTool,
    CompletionUsageDetails,
    ConversationThreadsResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingResponseData,
    EmbeddingUsage,
    Function,
    FunctionCall,
    FunctionParameters,
    ImageContent,
    ImageContentData,
    LogProbs,
    LogProbToken,
    PromptUsageDetails,
    RAGParams,
    References,
    RerankingApiVersion,
    RerankingBilledUnits,
    RerankingData,
    RerankingMeta,
    RerankingMetaUsage,
    RerankingRequest,
    RerankingResponse,
    RerankingUsage,
    S3Content,
    SplitChunksParams,
    SplitChunksRequest,
    TextContent,
    ToolCall,
    ToolChoice,
    ToolChoiceFunction,
    ToolUsageDetails,
    WebSearchTool,
)
from jamaibase.types.logs import LogQueryResponse  # noqa: F401
from jamaibase.types.model import (  # noqa: F401
    EmbeddingModelPrice,
    LLMModelPrice,
    ModelInfoListResponse,
    ModelPrice,
    RerankingModelPrice,
)
from jamaibase.types.telemetry import (  # noqa: F401
    Host,
    Metric,
    Usage,
    UsageResponse,
)


class OkResponse(BaseModel):
    ok: bool = True
    progress_key: str = ""


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: Annotated[
        list[T], Field(description="List of items paginated items.", examples=[[]])
    ] = []
    offset: Annotated[int, Field(description="Number of skipped items.", examples=[0])] = 0
    limit: Annotated[int, Field(description="Number of items per page.", examples=[0])] = 0
    total: Annotated[int, Field(description="Total number of items.", examples=[0])] = 0
    # start_cursor: Annotated[
    #     str | None,
    #     Field(
    #         description=(
    #             "Opaque token for the first item in this page. "
    #             "Pass it as `before=<start_cursor>` to request the page that precedes the current window."
    #         )
    #     ),
    # ] = None
    end_cursor: Annotated[
        str | None,
        Field(
            description=(
                "Opaque cursor token for the last item in this page. "
                "Pass it as `after=<end_cursor>` to request the page that follows the current window."
            )
        ),
    ] = None


class UserAgent(BaseModel):
    is_browser: bool = Field(
        True,
        description="Whether the request originates from a browser or an app.",
        examples=[True, False],
    )
    agent: str = Field(
        description="The agent, such as 'SDK', 'Chrome', 'Firefox', 'Edge', or an empty string if it cannot be determined.",
        examples=["", "SDK", "Chrome", "Firefox", "Edge"],
    )
    agent_version: str = Field(
        "",
        description="The agent version, or an empty string if it cannot be determined.",
        examples=["", "5.0", "0.3.0"],
    )
    os: str = Field(
        "",
        description="The system/OS name and release, such as 'Windows NT 10.0', 'Linux 5.15.0-113-generic', or an empty string if it cannot be determined.",
        examples=["", "Windows NT 10.0", "Linux 5.15.0-113-generic"],
    )
    architecture: str = Field(
        "",
        description="The machine type, such as 'AMD64', 'x86_64', or an empty string if it cannot be determined.",
        examples=["", "AMD64", "x86_64"],
    )
    language: str = Field(
        "",
        description="The SDK language, such as 'TypeScript', 'Python', or an empty string if it is not applicable.",
        examples=["", "TypeScript", "Python"],
    )
    language_version: str = Field(
        "",
        description="The SDK language version, such as '4.9', '3.10.14', or an empty string if it is not applicable.",
        examples=["", "4.9", "3.10.14"],
    )

    @computed_field(
        description="The system/OS name, such as 'Linux', 'Darwin', 'Java', 'Windows', or an empty string if it cannot be determined.",
        examples=["", "Windows NT", "Linux"],
    )
    @property
    def system(self) -> str:
        return self._split_os_string()[0]

    @computed_field(
        description="The system's release, such as '2.2.0', 'NT', or an empty string if it cannot be determined.",
        examples=["", "10", "5.15.0-113-generic"],
    )
    @property
    def system_version(self) -> str:
        return self._split_os_string()[1]

    def _split_os_string(self) -> tuple[str, str]:
        match = re.match(r"([^\d]+) ([\d.]+).*$", self.os)
        if match:
            os_name = match.group(1).strip()
            os_version = match.group(2).strip()
            return os_name, os_version
        else:
            return "", ""

    @classmethod
    def from_user_agent_string(cls, ua_string: str) -> Self:
        if not ua_string:
            return cls(is_browser=False, agent="")

        # SDK pattern
        sdk_match = re.match(r"SDK/(\S+) \((\w+)/(\S+); ([^;]+); (\w+)\)", ua_string)
        if sdk_match:
            return cls(
                is_browser=False,
                agent="SDK",
                agent_version=sdk_match.group(1),
                os=sdk_match.group(4),
                architecture=sdk_match.group(5),
                language=sdk_match.group(2),
                language_version=sdk_match.group(3),
            )

        # Browser pattern
        browser_match = re.match(r"Mozilla/5.0 \(([^)]+)\).*", ua_string)
        if browser_match:
            os_info = browser_match.group(1).split(";")
            # Microsoft Edge
            match = re.match(r".+(Edg/.+)$", ua_string)
            if match:
                return cls(
                    agent="Edge",
                    agent_version=match.group(1).split("/")[-1].strip(),
                    os=os_info[0].strip(),
                    architecture=os_info[-1].strip() if len(os_info) == 3 else "",
                    language="",
                    language_version="",
                )
            # Firefox
            match = re.match(r".+(Firefox/.+)$", ua_string)
            if match:
                return cls(
                    agent="Firefox",
                    agent_version=match.group(1).split("/")[-1].strip(),
                    os=os_info[0].strip(),
                    architecture=os_info[-1].strip() if len(os_info) == 3 else "",
                    language="",
                    language_version="",
                )
            # Chrome
            match = re.match(r".+(Chrome/.+)$", ua_string)
            if match:
                return cls(
                    agent="Chrome",
                    agent_version=match.group(1).split("/")[-1].strip(),
                    os=os_info[0].strip(),
                    architecture=os_info[-1].strip() if len(os_info) == 3 else "",
                    language="",
                    language_version="",
                )
        return cls(is_browser="mozilla" in ua_string.lower(), agent="")


class PasswordLoginRequest(BaseModel):
    email: EmailStr = Field(min_length=1, description="Email.")
    password: str = Field(min_length=1, max_length=72, description="Password.")


class PasswordChangeRequest(BaseModel):
    email: EmailStr = Field(min_length=1, description="Email.")
    password: str = Field(min_length=1, max_length=72, description="Password.")
    new_password: str = Field(min_length=1, max_length=72, description="New password.")


class StripePaymentInfo(BaseModel):
    status: str = Field(
        description="Stripe invoice payment status.",
    )
    subscription_id: str | None = Field(
        pattern=r"^sub_.+",
        description="Stripe subscription ID.",
    )
    payment_intent_id: str | None = Field(
        pattern=r"^pi_.+",
        description="Stripe payment intent ID.",
    )
    client_secret: str | None = Field(
        description="Stripe client secret.",
    )
    amount_due: Decimal = Field(
        decimal_places=2,
        description="Amount due.",
    )
    amount_overpaid: Decimal = Field(
        decimal_places=2,
        description="Amount overpaid.",
    )
    amount_paid: Decimal = Field(
        decimal_places=2,
        description="Amount paid.",
    )
    amount_remaining: Decimal = Field(
        decimal_places=2,
        description="Amount remaining.",
    )
    currency: str = Field(
        description="Currency.",
    )


class StripeEventData(BaseModel):
    event_type: str = Field(
        description="Stripe event type.",
    )
    event_id: str = Field(
        pattern=r"^evt_.+",
        description="Stripe event ID.",
    )
    invoice_id: str | None = Field(
        pattern=r"^in_.+",
        description="Stripe invoice ID.",
    )
    subscription_id: str | None = Field(
        pattern=r"^sub_.+",
        description="Stripe subscription ID.",
    )
    price_id: str | None = Field(
        pattern=r"^price_.+",
        description="Stripe price ID.",
    )
    payment_method: str | None = Field(
        pattern=r"^pm_.+",
        description="Stripe payment method.",
    )
    customer_id: str = Field(
        pattern=r"^cus_.+",
        description="Stripe customer ID.",
    )
    organization_id: str = Field(
        description="Organization ID.",
    )
    collection_method: str = Field(
        description="Stripe collection method.",
    )
    billing_reason: str = Field(
        description="Stripe billing reason.",
    )
    amount_paid: Decimal = Field(
        decimal_places=2,
        description="Amount paid.",
    )
    currency: str = Field(
        description="Currency.",
    )
    status: str = Field(
        description="Stripe subscription status.",
    )
    receipt_url: str = Field(
        "",
        description="Stripe receipt URL.",
    )
    invoice_url: str = Field(
        "",
        description="Stripe invoice URL.",
    )
    invoice_pdf: str = Field(
        "",
        description="Stripe invoice PDF URL.",
    )
