from enum import IntEnum
from typing import Annotated, Any

from fastapi.exceptions import RequestValidationError
from pydantic import (
    AnyUrl,
    BaseModel,
    BeforeValidator,
    EmailStr,
    Field,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_extra_types.currency_code import ISO4217
from pydantic_extra_types.timezone_name import TimeZoneName
from typing_extensions import Self

from jamaibase.types.common import (
    DEFAULT_MUL_LANGUAGES,
    DatetimeUTC,
    LanguageCodeList,
    PositiveNonZeroInt,
    SanitisedMultilineStr,
    SanitisedNonEmptyStr,
    SanitisedStr,
)
from jamaibase.types.gen_table import TableMetaResponse
from jamaibase.utils import uuid7_str
from jamaibase.utils.dates import now
from jamaibase.utils.exceptions import BadInputError
from jamaibase.utils.types import StrEnum, get_enum_validator


class _BaseModel(BaseModel, from_attributes=True, str_strip_whitespace=True):
    meta: dict[str, Any] = Field(
        {},
        description="Metadata.",
    )

    @classmethod
    def validate_updates(
        cls,
        base: Self,
        updates: dict[str, Any],
        *,
        raise_request_error: bool = True,
    ) -> Self:
        try:
            updates = {k: v for k, v in updates.items() if k in cls.model_fields}
            new = cls.model_validate(base.model_dump() | updates)
        except ValidationError as e:
            if raise_request_error:
                raise RequestValidationError(errors=e.errors()) from e
            else:
                raise
        return new


class _TableBase(BaseModel):
    created_at: DatetimeUTC = Field(
        description="Creation datetime (UTC).",
    )
    updated_at: DatetimeUTC = Field(
        description="Update datetime (UTC).",
    )

    def allowed(
        self,
        filter_id: str,
        *,
        allow_list_attr: str = "allowed_orgs",
        block_list_attr: str = "blocked_orgs",
    ) -> bool:
        allow_list: list[str] = getattr(self, allow_list_attr)
        block_list: list[str] | None = getattr(self, block_list_attr, None)
        # Allow list
        allowed = len(allow_list) == 0 or filter_id in allow_list
        if block_list is None:
            # No block list, just allow list
            return allowed
        else:
            # Block list
            return allowed and filter_id not in block_list


# TODO: Perhaps need to implement OveragePolicy


class PriceTier(BaseModel):
    """
    https://docs.stripe.com/api/prices/object#price_object-tiers
    """

    unit_cost: float = Field(
        description="Per unit price for units relevant to the tier.",
    )
    up_to: float | None = Field(
        description=(
            "Up to and including to this quantity will be contained in the tier. "
            "`None` means infinite quantity."
        ),
    )

    @classmethod
    def null(cls):
        return cls(
            unit_cost=0.0,
            up_to=0.0,
        )

    @classmethod
    def unlimited(cls, unit_cost: float = 0.0):
        return cls(
            unit_cost=unit_cost,
            up_to=None,
        )


class Product(BaseModel):
    name: SanitisedNonEmptyStr = Field(
        max_length=255,
        description="Product name.",
    )
    included: PriceTier = Field(
        description="Free tier. The `unit_cost` of this tier will always be `0.0`.",
    )
    tiers: list[PriceTier] = Field(
        description=(
            "Additional tiers so that we may charge a different price for the first usage band versus the next. "
            "For example, `included=PriceTier(unit_cost=0.0, up_to=0.5), "
            "tiers=[PriceTier(unit_cost=1.0, up_to=1.0), PriceTier(unit_cost=2.0, up_to=None)]` "
            "would be free for the first `0.5` units, `$1.0` per unit for the next `1.0` units, and `$2.0` per unit for the rest. "
            "In this case, a usage of `2.0` units would cost `$2.0`."
        ),
    )
    unit: SanitisedNonEmptyStr = Field(
        description="Unit of measurement for reference.",
    )

    @model_validator(mode="after")
    def check_included_cost(self) -> Self:
        # Included tier should be free
        self.included.unit_cost = 0.0
        return self

    @classmethod
    def null(cls, name: str, unit: str):
        return cls(
            name=name,
            included=PriceTier.null(),
            tiers=[],
            unit=unit,
        )

    @classmethod
    def unlimited(cls, name: str, unit: str, unit_cost: float = 0.0):
        return cls(
            name=name,
            included=PriceTier.unlimited(unit_cost=unit_cost),
            tiers=[],
            unit=unit,
        )


class Products(BaseModel):
    llm_tokens: Product = Field(
        description="LLM token quota to this plan or tier.",
    )
    embedding_tokens: Product = Field(
        description="Embedding token quota to this plan or tier.",
    )
    reranker_searches: Product = Field(
        description="Reranker search quota to this plan or tier.",
    )
    db_storage: Product = Field(
        description="Database storage quota to this plan or tier.",
    )
    file_storage: Product = Field(
        description="File storage quota to this plan or tier.",
    )
    egress: Product = Field(
        description="Egress bandwidth quota to this plan or tier.",
    )

    @classmethod
    def null(cls):
        return cls(
            llm_tokens=Product.null("ELLM tokens", "Million Tokens"),
            embedding_tokens=Product.null("Embedding tokens", "Million Tokens"),
            reranker_searches=Product.null("Reranker searches", "Thousand Searches"),
            db_storage=Product.null("Database storage", "GiB"),
            file_storage=Product.null("File storage", "GiB"),
            egress=Product.null("Egress bandwidth", "GiB"),
        )

    @classmethod
    def unlimited(cls, unit_cost: float = 0.0):
        return cls(
            llm_tokens=Product.unlimited("ELLM tokens", "Million Tokens", unit_cost),
            embedding_tokens=Product.unlimited("Embedding tokens", "Million Tokens", unit_cost),
            reranker_searches=Product.unlimited(
                "Reranker searches", "Thousand Searches", unit_cost
            ),
            db_storage=Product.unlimited("Database storage", "GiB", unit_cost),
            file_storage=Product.unlimited("File storage", "GiB", unit_cost),
            egress=Product.unlimited("Egress bandwidth", "GiB", unit_cost),
        )


_product2column = dict(
    credit=("credit",),
    credit_grant=("credit_grant",),
    llm_tokens=("llm_tokens_quota_mtok", "llm_tokens_usage_mtok"),
    embedding_tokens=(
        "embedding_tokens_quota_mtok",
        "embedding_tokens_usage_mtok",
    ),
    reranker_searches=("reranker_quota_ksearch", "reranker_usage_ksearch"),
    db_storage=("db_quota_gib", "db_usage_gib"),
    file_storage=("file_quota_gib", "file_usage_gib"),
    egress=("egress_quota_gib", "egress_usage_gib"),
)


class ProductType(StrEnum):
    CREDIT = "credit"
    CREDIT_GRANT = "credit_grant"
    LLM_TOKENS = "llm_tokens"
    EMBEDDING_TOKENS = "embedding_tokens"
    RERANKER_SEARCHES = "reranker_searches"
    DB_STORAGE = "db_storage"
    FILE_STORAGE = "file_storage"
    EGRESS = "egress"

    @property
    def quota_column(self) -> str:
        return _product2column[self.value][0]

    @property
    def usage_column(self) -> str:
        return _product2column[self.value][-1]

    @classmethod
    def exclude_credits(cls) -> list["ProductType"]:
        return [p for p in cls if not p.value.startswith("credit")]


class PricePlanUpdate(_BaseModel):
    stripe_price_id_live: SanitisedNonEmptyStr = Field(
        "",
        description="Stripe price ID (live mode).",
    )
    stripe_price_id_test: SanitisedNonEmptyStr = Field(
        "",
        description="Stripe price ID (test mode).",
    )
    name: SanitisedNonEmptyStr = Field(
        "",
        max_length=255,
        description="Price plan name.",
    )
    flat_cost: float = Field(
        0.0,
        ge=0.0,
        description="Base price for the entire tier.",
    )
    credit_grant: float = Field(
        0.0,
        ge=0.0,
        description="Credit amount included in USD.",
    )
    max_users: int | None = Field(
        0,
        ge=1,
        description="Maximum number of users per organization. `None` means no limit.",
    )
    products: Products = Field(
        Products.null(),
        description="Mapping of product ID to product.",
    )
    allowed_orgs: list[str] = Field(
        [],
        description=(
            "List of IDs of organizations allowed to use this price plan. "
            "If empty, all orgs are allowed."
        ),
    )

    @classmethod
    def free(
        cls,
        stripe_price_id_live: str = "price_123",
        stripe_price_id_test: str = "price_1RT2CqCcpbd72IcYEvy6U3GR",
    ):
        return cls(
            name="Free plan",
            stripe_price_id_live=stripe_price_id_live,
            stripe_price_id_test=stripe_price_id_test,
            flat_cost=0.0,
            credit_grant=0.0,
            max_users=2,  # For ease of testing
            products=Products(
                llm_tokens=Product(
                    name="ELLM tokens",
                    included=PriceTier(unit_cost=0.5, up_to=0.75),
                    tiers=[],
                    unit="Million Tokens",
                ),
                embedding_tokens=Product(
                    name="Embedding tokens",
                    included=PriceTier(unit_cost=0.5, up_to=0.75),
                    tiers=[],
                    unit="Million Tokens",
                ),
                reranker_searches=Product(
                    name="Reranker searches",
                    included=PriceTier(unit_cost=0.5, up_to=0.75),
                    tiers=[],
                    unit="Thousand Searches",
                ),
                db_storage=Product(
                    name="Database storage",
                    included=PriceTier(unit_cost=0.5, up_to=0.75),
                    tiers=[],
                    unit="GiB",
                ),
                file_storage=Product(
                    name="File storage",
                    included=PriceTier(unit_cost=0.5, up_to=0.75),
                    tiers=[],
                    unit="GiB",
                ),
                egress=Product(
                    name="Egress bandwidth",
                    included=PriceTier(unit_cost=0.5, up_to=0.75),
                    tiers=[],
                    unit="GiB",
                ),
            ),
        )


class PricePlanCreate(PricePlanUpdate):
    id: str = Field(
        "",
        description="Price plan ID.",
    )
    name: SanitisedNonEmptyStr = Field(
        max_length=255,
        description="Price plan name.",
    )
    stripe_price_id_live: SanitisedNonEmptyStr = Field(
        description="Stripe price ID (live mode).",
    )
    stripe_price_id_test: SanitisedNonEmptyStr = Field(
        description="Stripe price ID (test mode).",
    )
    flat_cost: float = Field(
        ge=0.0,
        description="Base price for the entire tier.",
    )
    credit_grant: float = Field(
        ge=0.0,
        description="Credit amount included in USD.",
    )
    max_users: int | None = Field(
        ge=1,
        description="Maximum number of users per organization. `None` means no limit.",
    )
    products: Products = Field(
        description="Mapping of product ID to product.",
    )


class PricePlan_(PricePlanCreate, _TableBase):
    # Computed fields
    is_private: bool = Field(
        description="Whether this is a private price plan visible only to select organizations.",
    )
    stripe_price_id: str = Field(
        description="Stripe Price ID (either live or test based on API key).",
    )


class PricePlanRead(PricePlan_):
    pass


class OnPremProvider(StrEnum):
    VLLM = "vllm"
    VLLM_AMD = "vllm_amd"
    OLLAMA = "ollama"
    INFINITY = "infinity"
    INFINITY_CPU = "infinity_cpu"

    @classmethod
    def list_(cls) -> list[str]:
        return list(map(str, cls))


class CloudProvider(StrEnum):
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    AZURE_AI = "azure_ai"
    BEDROCK = "bedrock"
    CEREBRAS = "cerebras"
    COHERE = "cohere"
    DEEPSEEK = "deepseek"
    ELLM = "ellm"
    FIREWORKS_AI = "fireworks_ai"
    GEMINI = "gemini"
    GROQ = "groq"
    HYPERBOLIC = "hyperbolic"
    INFINITY_CLOUD = "infinity_cloud"
    JINA_AI = "jina_ai"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    SAGEMAKER = "sagemaker"
    SAMBANOVA = "sambanova"
    TOGETHER_AI = "together_ai"
    # VERTEX_AI = "vertex_ai"
    VLLM_CLOUD = "vllm_cloud"
    VOYAGE = "voyage"

    @classmethod
    def list_(cls) -> list[str]:
        return list(map(str, cls))


class ModelProvider(StrEnum):
    ANTHROPIC = "anthropic"
    COHERE = "cohere"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    JINA_AI = "jina_ai"
    OPENAI = "openai"

    @classmethod
    def list_(cls) -> list[str]:
        return list(map(str, cls))


class DeploymentStatus(StrEnum):
    ACTIVE = "active"


class DeploymentUpdate(_BaseModel):
    name: SanitisedNonEmptyStr = Field(
        "",
        max_length=255,
        description="Name for the deployment.",
    )
    routing_id: SanitisedNonEmptyStr = Field(
        "",
        description=(
            "Model ID that the inference provider expects (whereas `model_id` is what the users will see). "
            "OpenAI example: `model_id` CAN be `openai/gpt-5` but `routing_id` SHOULD be `gpt-5`."
        ),
    )
    api_base: str = Field(
        "",
        description=(
            "(Optional) Hosting url. "
            "Required for creating external cloud deployment using custom providers. "
            "Example: `http://vllm-endpoint.xyz/v1`."
        ),
    )
    provider: SanitisedNonEmptyStr = Field(
        "",
        description=(
            f"Inference provider of the model. "
            f"Standard cloud providers are {CloudProvider.list_()}."
        ),
    )
    weight: int = Field(
        1,
        description="Routing weight. Must be >= 0. A deployment is selected according to its relative weight.",
    )
    cooldown_until: DatetimeUTC = Field(
        default_factory=now,
        description="Cooldown until datetime (UTC).",
    )


class DeploymentCreate(DeploymentUpdate):
    model_id: SanitisedNonEmptyStr = Field(
        description="Model ID.",
    )
    name: SanitisedNonEmptyStr = Field(
        max_length=255,
        description="Name for the deployment.",
    )


class Deployment_(DeploymentCreate, _TableBase):
    id: str = Field(
        description="Deployment ID.",
    )


class DeploymentRead(Deployment_):
    model: "ModelConfig_" = Field(
        description="Model config.",
    )

    @computed_field(description='Status of the deployment. Will always be "ACTIVE".')
    @property
    def status(self) -> str:
        return DeploymentStatus.ACTIVE


class ModelType(StrEnum):
    COMPLETION = "completion"
    LLM = "llm"
    EMBED = "embed"
    RERANK = "rerank"


# This is needed because DB stores Enums as keys but Pydantic loads via values
_ModelType = Annotated[ModelType, BeforeValidator(get_enum_validator(ModelType))]


class ModelCapability(StrEnum):
    COMPLETION = "completion"
    CHAT = "chat"
    TOOL = "tool"
    IMAGE = "image"  # TODO: Maybe change to "image_in" & "image_out"
    AUDIO = "audio"
    EMBED = "embed"
    RERANK = "rerank"
    REASONING = "reasoning"


_ModelCapability = Annotated[ModelCapability, BeforeValidator(get_enum_validator(ModelCapability))]


class ModelInfo(_BaseModel):
    id: SanitisedNonEmptyStr = Field(
        description=(
            "Unique identifier. "
            "Users will specify this to select a model. "
            "Must follow the following format: `{provider}/{model_id}`. "
            "Examples=['openai/gpt-4o-mini', 'Qwen/Qwen2.5-0.5B']"
        ),
        examples=["openai/gpt-4o-mini", "Qwen/Qwen2.5-0.5B"],
    )
    type: _ModelType = Field(
        "",
        description="Model type. Can be completion, llm, embed, or rerank.",
        examples=[ModelType.LLM],
    )
    name: SanitisedNonEmptyStr = Field(
        "",
        max_length=255,
        description="Model name that is more user friendly.",
        examples=["OpenAI GPT-4o Mini"],
    )
    owned_by: SanitisedStr = Field(
        "",
        description="Model provider (usually organization that trained the model).",
    )
    capabilities: list[_ModelCapability] = Field(
        [],
        min_length=1,
        description="List of capabilities of model.",
        examples=[[ModelCapability.CHAT], [ModelCapability.CHAT, ModelCapability.AUDIO]],
    )
    context_length: int = Field(
        4096,
        gt=0,
        description="Context length of model.",
        examples=[4096],
    )
    languages: LanguageCodeList = Field(
        ["en"],
        description=f'List of languages which the model is well-versed in. "*" and "mul" resolves to {DEFAULT_MUL_LANGUAGES}.',
        examples=[["en"], ["en", "zh-CN"]],
    )
    max_output_tokens: int | None = Field(
        None,
        gt=0,
        description="Maximum number of output tokens, if not specified, will be based on context length.",
        # examples=[8192],
    )

    @field_validator("id", mode="after")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if len(v.split("/")) < 2:
            raise ValueError(
                "Model `id` must follow the following format: `{provider}/{model_id}`."
            )
        return v

    @property
    def capabilities_set(self) -> set[str]:
        return set(map(str, self.capabilities))


class ModelInfoRead(ModelInfo, _TableBase):
    pass


class ModelConfigUpdate(ModelInfo):
    # --- All models --- #
    id: SanitisedNonEmptyStr = Field(
        "",
        description=(
            "Unique identifier. "
            "Users will specify this to select a model. "
            "Must follow the following format: `{provider}/{model_id}`. "
            "Examples=['openai/gpt-4o-mini', 'Qwen/Qwen2.5-0.5B']"
        ),
    )
    timeout: float = Field(
        30 * 60 * 60,
        description="Timeout in seconds. Must be greater than 0. Defaults to 30 minutes.",
    )
    priority: int = Field(
        0,
        description="Priority for fallback model selection. The larger the number, the higher the priority.",
    )
    allowed_orgs: list[str] = Field(
        [],
        description=(
            "List of IDs of organizations allowed to use this model. "
            "If empty, all orgs are allowed. Allow list is applied first, followed by block list."
        ),
    )
    blocked_orgs: list[str] = Field(
        [],
        description=(
            "List of IDs of organizations NOT allowed to use this model. "
            "If empty, no org is blocked. Allow list is applied first, followed by block list."
        ),
    )
    # --- LLM models --- #
    llm_input_cost_per_mtoken: float = Field(
        -1.0,
        description="Cost in USD per million (mega) input / prompt token.",
    )
    llm_output_cost_per_mtoken: float = Field(
        -1.0,
        description="Cost in USD per million (mega) output / completion token.",
    )
    # --- Embedding models --- #
    embedding_size: PositiveNonZeroInt | None = Field(
        None,
        description=(
            "The default embedding size of the model. "
            "For example: `openai/text-embedding-3-large` has `embedding_size` of 3072 "
            "but can be shortened to `embedding_dimensions` of 256; "
            "`cohere/embed-v4.0` has `embedding_size` of 1536 "
            "but can be shortened to `embedding_dimensions` of 256."
        ),
    )
    # Matryoshka embedding dimension
    embedding_dimensions: PositiveNonZeroInt | None = Field(
        None,
        description=(
            "The number of dimensions the resulting output embeddings should have. "
            "Can be overridden by `dimensions` for each request. "
            "Defaults to None (no reduction). "
            "Note that this parameter will only be used when using models that support Matryoshka embeddings. "
            "For example: `openai/text-embedding-3-large` has `embedding_size` of 3072 "
            "but can be shortened to `embedding_dimensions` of 256; "
            "`cohere/embed-v4.0` has `embedding_size` of 1536 "
            "but can be shortened to `embedding_dimensions` of 256."
        ),
    )
    # Most likely only useful for HuggingFace models
    embedding_transform_query: SanitisedNonEmptyStr | None = Field(
        None,
        description="Transform query that might be needed, especially for HuggingFace models.",
    )
    embedding_cost_per_mtoken: float = Field(
        -1.0,
        description="Cost in USD per million embedding tokens.",
    )
    # --- Reranking models --- #
    reranking_cost_per_ksearch: float = Field(
        -1.0,
        description="Cost in USD for a thousand searches.",
    )

    @property
    def final_embedding_size(self) -> int:
        embed_size = self.embedding_dimensions or self.embedding_size
        if embed_size is None:
            raise BadInputError(
                f'Both `embedding_dimensions` and `embedding_size` are None for embedding model "{self.id}".'
            )
        return embed_size

    @model_validator(mode="after")
    def check_chat_cost_per_mtoken(self) -> Self:
        # GPT-4o-mini pricing (2024-08-10)
        if self.llm_input_cost_per_mtoken < 0:
            self.llm_input_cost_per_mtoken = 0.150
        if self.llm_output_cost_per_mtoken < 0:
            self.llm_output_cost_per_mtoken = 0.600
        return self

    @model_validator(mode="after")
    def check_embed_cost_per_mtoken(self) -> Self:
        # OpenAI text-embedding-3-small pricing (2024-09-09)
        if self.embedding_cost_per_mtoken < 0:
            self.embedding_cost_per_mtoken = 0.022
        return self

    @model_validator(mode="after")
    def check_rerank_cost_per_ksearch(self) -> Self:
        # Cohere rerank-multilingual-v3.0 pricing (2024-09-09)
        if self.reranking_cost_per_ksearch < 0:
            self.reranking_cost_per_ksearch = 2.0
        return self


class ModelConfigCreate(ModelConfigUpdate):
    # Overrides to make these field required in ModelConfigCreate.
    type: _ModelType = Field(
        description="Model type. Can be completion, chat, embed, or rerank.",
    )
    name: SanitisedNonEmptyStr = Field(
        max_length=255,
        description="Model name that is more user friendly.",
    )
    context_length: int = Field(
        gt=0,
        description="Context length of model. Examples=[4096]",
    )
    capabilities: list[_ModelCapability] = Field(
        description="List of capabilities of model.",
    )
    owned_by: SanitisedStr = Field(
        "",
        description="Model provider (usually organization that trained the model).",
    )

    @model_validator(mode="after")
    def validate_owned_by_ellm_id_match(self) -> Self:
        ellm_owned = self.owned_by == "ellm"
        ellm_id = self.id.startswith("ellm/")
        if (ellm_owned and not ellm_id) or (ellm_id and not ellm_owned):
            raise ValueError('ELLM models must have `owned_by="ellm"` and `id="ellm/..."`.')
        return self


class ModelConfig_(ModelConfigCreate, _TableBase):
    # Computed fields
    is_private: bool = Field(
        False,
        description="Whether this is a private model visible only to select organizations.",
    )

    @model_validator(mode="after")
    def validate_owned_by_ellm_id_match(self) -> Self:
        # Don't validate when reading from DB
        return self


class ModelConfigRead(ModelConfig_):
    deployments: list[Deployment_] = Field(
        description="List of model deployment configs.",
    )
    # Computed fields
    # Since this depends on Deployment, we put here to avoid circular dependency
    is_active: bool = Field(
        description="Whether this model is active and ready for inference.",
    )


class Role(StrEnum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    GUEST = "GUEST"

    @property
    def rank(self) -> "RankedRole":
        return RankedRole[self.value]


class RankedRole(IntEnum):
    GUEST = 0
    MEMBER = 1
    ADMIN = 2

    @classmethod
    def get(cls, role: str) -> int:
        try:
            return int(RankedRole[role])
        except KeyError:
            return -1


_Role = Annotated[Role, BeforeValidator(get_enum_validator(Role))]


class OrgMemberUpdate(_BaseModel):
    role: _Role = Field(
        description="Organization role.",
    )


class OrgMemberCreate(OrgMemberUpdate):
    user_id: SanitisedNonEmptyStr = Field(
        description="User ID.",
    )
    organization_id: SanitisedNonEmptyStr = Field(
        description="Organization ID.",
    )


class OrgMember_(OrgMemberCreate, _TableBase):
    pass


class OrgMemberRead(OrgMember_):
    user: "User_" = Field(description="User.")
    organization: "Organization_" = Field(description="Organization.")


class ProjectMemberUpdate(_BaseModel):
    role: _Role = Field(
        description="Project role.",
    )


class ProjectMemberCreate(ProjectMemberUpdate):
    user_id: SanitisedNonEmptyStr = Field(
        description="User ID.",
    )
    project_id: SanitisedNonEmptyStr = Field(
        description="Project ID.",
    )


class ProjectMember_(ProjectMemberCreate, _TableBase):
    pass


class ProjectMemberRead(ProjectMember_):
    user: "User_" = Field(description="User.")
    project: "Project_" = Field(description="Project.")


class _UserBase(_BaseModel):
    name: SanitisedNonEmptyStr = Field(
        "",
        max_length=255,
        description="User's preferred name.",
    )
    email: EmailStr = Field(
        "",
        description="User's email.",
    )
    picture_url: AnyUrl | None = Field(
        None,
        description="User picture URL.",
    )
    google_id: SanitisedNonEmptyStr | None = Field(
        None,
        description="Google user ID.",
    )
    google_name: SanitisedNonEmptyStr | None = Field(
        None,
        description="Google user's preferred name.",
    )
    google_username: SanitisedNonEmptyStr | None = Field(
        None,
        description="Google username.",
    )
    google_email: EmailStr | None = Field(
        None,
        description="Google email.",
    )
    google_picture_url: SanitisedNonEmptyStr | None = Field(
        None,
        description="Google user picture URL.",
    )
    google_updated_at: DatetimeUTC | None = Field(
        None,
        description="Google user info update datetime (UTC).",
    )
    github_id: SanitisedNonEmptyStr | None = Field(
        None,
        description="GitHub user ID.",
    )
    github_name: SanitisedNonEmptyStr | None = Field(
        None,
        description="GitHub user's preferred name.",
    )
    github_username: SanitisedNonEmptyStr | None = Field(
        None,
        description="GitHub username.",
    )
    github_email: EmailStr | None = Field(
        None,
        description="GitHub email.",
    )
    github_picture_url: SanitisedNonEmptyStr | None = Field(
        None,
        description="GitHub user picture URL.",
    )
    github_updated_at: DatetimeUTC | None = Field(
        None,
        description="GitHub user info update datetime (UTC).",
    )


class UserUpdate(_UserBase):
    password: SanitisedNonEmptyStr = Field(
        "",
        max_length=72,
        description="Password in plain text.",
    )


class UserCreate(UserUpdate):
    id: SanitisedNonEmptyStr = Field(
        default_factory=uuid7_str,
        description="User ID.",
    )
    name: SanitisedNonEmptyStr = Field(
        max_length=255,
        description="User's preferred name.",
    )
    email: EmailStr = Field(
        description="User's email.",
    )


def _obscure_password_hash(value: Any) -> Any:
    if value is not None:
        return "***"
    else:
        return value


class User_(_UserBase, _TableBase):
    id: SanitisedNonEmptyStr = Field(
        default_factory=uuid7_str,
        description="User ID.",
    )
    email_verified: bool = Field(
        description="Whether the email address is verified.",
    )
    password_hash: Annotated[str | None, BeforeValidator(_obscure_password_hash)] = Field(
        description="Password hash.",
    )
    refresh_counter: int = Field(
        0,
        description="Counter used as refresh token version for invalidation.",
    )
    # Computed fields
    preferred_name: str = Field(
        "",
        description="Name for display.",
    )
    preferred_email: str = Field(
        "",
        description="Email for display.",
    )
    preferred_picture_url: str | None = Field(
        None,
        description="Picture URL for display.",
    )
    preferred_username: str | None = Field(
        None,
        description="Username for display.",
    )


class UserAuth(User_):
    org_memberships: list[OrgMember_] = Field(
        description="List of organization memberships.",
    )
    proj_memberships: list[ProjectMember_] = Field(
        description="List of project memberships.",
    )


class UserRead(UserAuth):
    organizations: list["Organization_"] = Field(
        description="List of organizations that this user is a member of.",
    )
    projects: list["Project_"] = Field(
        description="List of projects that this user is a member of.",
    )


class UserReadObscured(UserRead):
    password_hash: Annotated[str | None, BeforeValidator(_obscure_password_hash)] = Field(
        description="Password hash.",
    )


class PaymentState(StrEnum):
    NONE = "NONE"  # When an organization is created
    SUCCESS = "SUCCESS"  # Payment is completed
    PROCESSING = "PROCESSING"  # Payment is initiated but yet to complete
    FAILED = "FAILED"  # Payment failed


class OrganizationUpdate(_BaseModel):
    name: SanitisedNonEmptyStr = Field(
        "",
        max_length=255,
        description="Organization name.",
    )
    timezone: TimeZoneName | None = Field(
        None,
        description="Timezone specifier.",
    )
    external_keys: dict[SanitisedNonEmptyStr, str] = Field(
        {},
        description="Mapping of external service provider to its API key.",
    )

    @field_validator("external_keys", mode="before")
    @classmethod
    def validate_external_keys(cls, v: dict[str, str]) -> dict[str, str]:
        # Remove empty API keys, and ensure provider is lowercase
        v = {k.strip().lower(): v.strip() for k, v in v.items() if v.strip()}
        return v


class OrganizationCreate(OrganizationUpdate):
    name: SanitisedNonEmptyStr = Field(
        max_length=255,
        description="Organization name.",
    )


class Organization_(OrganizationCreate, _TableBase):
    id: str = Field(
        description="Organization ID.",
    )
    currency: ISO4217 = Field(
        "USD",
        description="Currency of the organization.",
    )
    created_by: str = Field(
        description="ID of the user that created this organization.",
    )
    owner: str = Field(
        description="ID of the user that owns this organization.",
    )
    stripe_id: SanitisedNonEmptyStr | None = Field(
        description="Stripe Customer ID.",
    )
    # stripe_subscription_id: SanitisedNonEmptyStr = Field(
    #     "",
    #     description="Stripe Subscription ID.",
    # )
    price_plan_id: SanitisedNonEmptyStr | None = Field(
        description="Price plan ID.",
    )
    payment_state: PaymentState = Field(
        description="Payment state of the organization.",
    )
    last_subscription_payment_at: DatetimeUTC | None = Field(
        description="Datetime of the last successful subscription payment (UTC).",
    )
    quota_reset_at: DatetimeUTC = Field(
        description="Quota reset datetime (UTC).",
    )
    credit: float = Field(
        description="Credit paid by the customer. Unused credit will be carried forward to the next billing cycle.",
    )
    credit_grant: float = Field(
        description="Credit granted to the customer. Unused credit will NOT be carried forward.",
    )
    llm_tokens_quota_mtok: float | None = Field(
        description="LLM token quota in millions of tokens.",
    )
    llm_tokens_usage_mtok: float = Field(
        description="LLM token usage in millions of tokens.",
    )
    embedding_tokens_quota_mtok: float | None = Field(
        description="Embedding token quota in millions of tokens.",
    )
    embedding_tokens_usage_mtok: float = Field(
        description="Embedding token quota in millions of tokens.",
    )
    reranker_quota_ksearch: float | None = Field(
        description="Reranker quota for every thousand searches.",
    )
    reranker_usage_ksearch: float = Field(
        description="Reranker usage for every thousand searches.",
    )
    db_quota_gib: float | None = Field(
        description="DB storage quota in GiB.",
    )
    db_usage_gib: float = Field(
        description="DB storage usage in GiB.",
    )
    db_usage_updated_at: DatetimeUTC = Field(
        description="Datetime of the last successful DB usage update (UTC).",
    )
    file_quota_gib: float | None = Field(
        description="File storage quota in GiB.",
    )
    file_usage_gib: float = Field(
        description="File storage usage in GiB.",
    )
    file_usage_updated_at: DatetimeUTC = Field(
        description="Datetime of the last successful File usage update (UTC).",
    )
    egress_quota_gib: float | None = Field(
        description="Egress quota in GiB.",
    )
    egress_usage_gib: float = Field(
        description="Egress usage in GiB.",
    )
    # Computed fields
    active: bool = Field(
        description="Whether the organization's quota is active (paid).",
    )
    quotas: dict[str, dict[str, float | None]] = Field(
        description="Quota snapshot.",
    )


class OrganizationRead(Organization_):
    price_plan: PricePlan_ | None = Field(
        description="Subscribed plan.",
    )


class ProjectUpdate(_BaseModel):
    name: SanitisedNonEmptyStr = Field(
        "",
        max_length=255,
        description="Project name.",
    )
    description: SanitisedMultilineStr = Field(
        "",
        description="Project description.",
    )
    tags: list[str] = Field(
        [],
        description="Project tags.",
    )
    profile_picture_url: str | None = Field(
        None,
        description="URL of the profile picture.",
    )
    cover_picture_url: str | None = Field(
        None,
        description="URL of the cover picture.",
    )


class ProjectCreate(ProjectUpdate):
    organization_id: SanitisedNonEmptyStr = Field(
        description="Organization ID.",
    )
    name: SanitisedNonEmptyStr = Field(
        max_length=255,
        description="Project name.",
    )


class Project_(ProjectCreate, _TableBase):
    id: str = Field(
        description="Project ID.",
    )
    created_by: str = Field(
        description="ID of the user that created this project.",
    )
    owner: str = Field(
        description="ID of the user that owns this project.",
    )


class ProjectRead(Project_):
    organization: "Organization_" = Field(
        description="Organization.",
    )
    chat_agents: list[TableMetaResponse] | None = Field(
        None,
        description=(
            "List of ID of chat agents in this project. "
            "Empty list means no chat agents are available in this project. "
            "Note that by default, the list is not populated will be None."
        ),
    )


class VerificationCodeUpdate(_BaseModel):
    name: SanitisedStr = Field(
        "",
        max_length=255,
        description="Code name.",
    )
    role: SanitisedNonEmptyStr | None = Field(
        None,
        description="Organization or project role.",
    )


class VerificationCodeCreate(VerificationCodeUpdate):
    user_email: EmailStr = Field(
        description="User email.",
    )
    expiry: DatetimeUTC = Field(
        description="Code expiry datetime (UTC).",
    )
    organization_id: SanitisedNonEmptyStr | None = Field(
        None,
        description="Organization ID.",
    )
    project_id: SanitisedNonEmptyStr | None = Field(
        None,
        description="Project ID.",
    )


class VerificationCode_(VerificationCodeCreate, _TableBase):
    id: str = Field(
        description="The code.",
    )
    purpose: str | None = Field(
        None,
        description="Code purpose.",
    )
    used_at: DatetimeUTC | None = Field(
        None,
        description="Code usage datetime (UTC).",
    )
    revoked_at: DatetimeUTC | None = Field(
        None,
        description="Code revocation datetime (UTC).",
    )


class VerificationCodeRead(VerificationCode_):
    pass


class ProjectKeyUpdate(_BaseModel):
    name: SanitisedNonEmptyStr = Field(
        "",
        max_length=255,
        description="Name.",
    )
    expiry: DatetimeUTC | None = Field(
        None,
        description="Expiry datetime (UTC). If None, never expires.",
    )


class ProjectKeyCreate(ProjectKeyUpdate):
    name: SanitisedNonEmptyStr = Field(
        max_length=255,
        description="Name.",
    )
    project_id: SanitisedNonEmptyStr | None = Field(
        None,
        description="Project ID.",
    )


class ProjectKey_(ProjectKeyCreate, _TableBase):
    id: str = Field(
        description="The token.",
    )
    user_id: str = Field(
        description="User ID.",
    )


class ProjectKeyRead(ProjectKey_):
    pass


class SecretUpdate(BaseModel):
    """Schema for updating a secret (name cannot be changed)."""

    value: str | None = Field(default=None, description="Secret value")
    allowed_projects: list[str] | None = Field(
        default=None,
        description=(
            "Updated allowed projects list. None means all projects are allowed. "
            "Empty list [] means no projects are allowed."
        ),
    )


class SecretCreate(SecretUpdate):
    name: str = Field(
        ...,
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description=(
            "Secret name (case-insensitive, saved in uppercase). Must start with a letter or underscore"
            " and contain only alphanumeric characters and underscores."
        ),
    )


class Secret_(SecretCreate, _TableBase):
    organization_id: str = Field(description="Organization ID that owns this secret.")


class SecretRead(Secret_):
    pass
