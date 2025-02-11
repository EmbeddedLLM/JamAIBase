"""
NOTES:

- Pydantic supports setting mutable values as default.
  This is in contrast to native `dataclasses` where it is not supported.

- Pydantic supports setting default fields in any order.
  This is in contrast to native `dataclasses` where fields with default values must be defined after non-default fields.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum, EnumMeta
from os.path import splitext
from typing import Annotated, Any, Generic, Literal, Sequence, TypeVar, Union
from warnings import warn

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic.functional_validators import AfterValidator
from typing_extensions import Self, deprecated

from jamaibase.utils import datetime_now_iso
from jamaibase.version import __version__ as jamaibase_version

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

EXAMPLE_CHAT_MODEL_IDS = ["openai/gpt-4o-mini"]
# for openai embedding models doc: https://platform.openai.com/docs/guides/embeddings
# for cohere embedding models doc: https://docs.cohere.com/reference/embed
# for jina embedding models doc: https://jina.ai/embeddings/
# for voyage embedding models doc: https://docs.voyageai.com/docs/embeddings
# for hf embedding models doc: check the respective hf model page, name should be ellm/{org}/{model}
EXAMPLE_EMBEDDING_MODEL_IDS = [
    "openai/text-embedding-3-small-512",
    "ellm/sentence-transformers/all-MiniLM-L6-v2",
]
# for cohere reranking models doc: https://docs.cohere.com/reference/rerank-1
# for jina reranking models doc: https://jina.ai/reranker
# for colbert reranking models doc: https://docs.voyageai.com/docs/reranker
# for hf embedding models doc: check the respective hf model page, name should be ellm/{org}/{model}
EXAMPLE_RERANKING_MODEL_IDS = [
    "cohere/rerank-multilingual-v3.0",
    "ellm/cross-encoder/ms-marco-TinyBERT-L-2",
]

IMAGE_FILE_EXTENSIONS = [".jpeg", ".jpg", ".png", ".gif", ".webp"]
AUDIO_FILE_EXTENSIONS = [".mp3", ".wav"]
DOCUMENT_FILE_EXTENSIONS = [
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".xml",
    ".html",
    ".json",
    ".csv",
    ".tsv",
    ".jsonl",
    ".xlsx",
    ".xls",
]


class OkResponse(BaseModel):
    ok: bool = True


class StringResponse(BaseModel):
    object: Literal["string"] = Field(
        default="string",
        description='The object type, which is always "string".',
        examples=["string"],
    )
    data: str = Field(
        description="The string data.",
        examples=["text"],
    )


class AdminOrderBy(str, Enum):
    ID = "id"
    """Sort by `id` column."""
    NAME = "name"
    """Sort by `name` column."""
    CREATED_AT = "created_at"
    """Sort by `created_at` column."""
    UPDATED_AT = "updated_at"
    """Sort by `updated_at` column."""

    def __str__(self) -> str:
        return self.value


class GenTableOrderBy(str, Enum):
    ID = "id"
    """Sort by `id` column."""
    UPDATED_AT = "updated_at"
    """Sort by `updated_at` column."""

    def __str__(self) -> str:
        return self.value


class Tier(BaseModel):
    """
    https://docs.stripe.com/api/prices/object#price_object-tiers
    """

    unit_amount_decimal: Decimal = Field(
        description="Per unit price for units relevant to the tier.",
    )
    up_to: float | None = Field(
        description=(
            "Up to and including to this quantity will be contained in the tier. "
            "None means infinite quantity."
        ),
    )


class Product(BaseModel):
    name: str = Field(
        min_length=1,
        description="Plan name.",
    )
    included: Tier = Tier(unit_amount_decimal=0, up_to=0)
    tiers: list[Tier]
    unit: str = Field(
        description="Unit of measurement.",
    )


class Plan(BaseModel):
    name: str
    stripe_price_id_live: str
    stripe_price_id_test: str
    flat_amount_decimal: Decimal = Field(
        description="Base price for the entire tier.",
    )
    credit_grant: float = Field(
        description="Credit amount included in USD.",
    )
    max_users: int = Field(
        description="Maximum number of users per organization.",
    )
    products: dict[str, Product] = Field(
        description="Mapping of price name to tier list where each element represents a pricing tier.",
    )


class Price(BaseModel):
    plans: dict[str, Plan] = Field(
        description="Mapping of price plan name to price plan.",
    )


class _ModelPrice(BaseModel):
    id: str = Field(
        description=(
            'Unique identifier in the form of "{provider}/{model_id}". '
            "Users will specify this to select a model."
        ),
        examples=[
            EXAMPLE_CHAT_MODEL_IDS[0],
            EXAMPLE_EMBEDDING_MODEL_IDS[0],
            EXAMPLE_RERANKING_MODEL_IDS[0],
        ],
    )
    name: str = Field(
        description="Name of the model.",
        examples=["OpenAI GPT-4o Mini"],
    )


class LLMModelPrice(_ModelPrice):
    input_cost_per_mtoken: float = Field(
        description="Cost in USD per million input / prompt token.",
    )
    output_cost_per_mtoken: float = Field(
        description="Cost in USD per million output / completion token.",
    )


class EmbeddingModelPrice(_ModelPrice):
    cost_per_mtoken: float = Field(
        description="Cost in USD per million embedding tokens.",
    )


class RerankingModelPrice(_ModelPrice):
    cost_per_ksearch: float = Field(description="Cost in USD for a thousand (kilo) searches.")


class ModelPrice(BaseModel):
    object: str = Field(
        default="prices.models",
        description="Type of API response object.",
        examples=["prices.models"],
    )
    llm_models: list[LLMModelPrice] = []
    embed_models: list[EmbeddingModelPrice] = []
    rerank_models: list[RerankingModelPrice] = []


class _OrgMemberBase(BaseModel):
    user_id: str = Field(description="User ID. Must be unique.")
    organization_id: str = Field(
        default="",
        description="Organization ID. Must be unique.",
    )
    role: Literal["admin", "member", "guest"] = "admin"
    """User role."""


class OrgMemberCreate(_OrgMemberBase):
    invite_token: str = Field(
        default="",
        description="User-org link creation datetime (ISO 8601 UTC).",
    )


class OrgMemberRead(_OrgMemberBase):
    created_at: str = Field(
        description="User-org link creation datetime (ISO 8601 UTC).",
    )
    updated_at: str = Field(
        description="User-org link update datetime (ISO 8601 UTC).",
    )
    organization_name: str = ""
    """Organization name. To be populated later."""


class UserUpdate(BaseModel):
    id: str
    """User ID. Must be unique."""
    name: str | None = None
    """The user's full name or business name."""
    description: str | None = None
    """An arbitrary string that you can attach to a customer object."""
    email: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    """User's email address. This may be up to 512 characters."""
    meta: dict | None = None
    """
    Additional metadata about the user.
    """


class UserCreate(BaseModel):
    id: str
    """User ID. Must be unique."""
    name: str
    """The user's full name or business name."""
    description: str = ""
    """An arbitrary string that you can attach to a customer object."""
    email: Annotated[str, Field(min_length=1, max_length=512)]
    """User's email address. This may be up to 512 characters."""
    meta: dict = {}
    """
    Additional metadata about the user.
    """


class UserRead(UserCreate):
    created_at: str = Field(description="User creation datetime (ISO 8601 UTC).")
    updated_at: str = Field(description="User update datetime (ISO 8601 UTC).")
    member_of: list[OrgMemberRead]
    """List of organizations that this user is associated with and their role."""


class PATCreate(BaseModel):
    user_id: str = Field(description="User ID.")
    expiry: str = Field(
        default="",
        description="PAT expiry datetime (ISO 8601 UTC). If empty, never expires.",
    )


class PATRead(PATCreate):
    id: str = Field(description="The token.")
    created_at: str = Field(description="Creation datetime (ISO 8601 UTC).")
    # user: UserRead = Field(description="User that this Personal Access Token is associated with.")


class ProjectCreate(BaseModel):
    name: str = Field(
        description="Project name.",
    )
    organization_id: str = Field(
        description="Organization ID.",
    )


class ProjectUpdate(BaseModel):
    id: str
    """Project ID."""
    name: str | None = Field(
        default=None,
        description="Project name.",
    )


class ProjectRead(ProjectCreate):
    id: str = Field(
        description="Project ID.",
    )
    created_at: str = Field(
        description="Project creation datetime (ISO 8601 UTC).",
    )
    updated_at: str = Field(
        description="Project update datetime (ISO 8601 UTC).",
    )
    organization: Union["OrganizationRead", None] = Field(
        default=None,
        description="Organization that this project is associated with.",
    )


class OrganizationCreate(BaseModel):
    creator_user_id: str = Field(
        default="",
        description="User that created this organization.",
    )
    name: str = Field(
        description="Organization name.",
    )
    external_keys: dict[str, str] = Field(
        default={},
        description="Mapping of service provider to its API key.",
    )
    tier: str = Field(
        default="",
        description="Subscribed tier.",
    )
    active: bool = Field(
        default=True,
        description="Whether the organization's quota is active (paid).",
    )
    timezone: str | None = Field(
        default=None,
        description="Timezone specifier.",
    )
    credit: float = Field(
        default=0.0,
        description="Credit paid by the customer. Unused credit will be carried forward to the next billing cycle.",
    )
    credit_grant: float = Field(
        default=0.0,
        description="Credit granted to the customer. Unused credit will NOT be carried forward.",
    )
    llm_tokens_quota_mtok: float = Field(
        default=0.0,
        description="LLM token quota in millions of tokens.",
    )
    llm_tokens_usage_mtok: float = Field(
        default=0.0,
        description="LLM token usage in millions of tokens.",
    )
    embedding_tokens_quota_mtok: float = Field(
        default=0.0,
        description="Embedding token quota in millions of tokens",
    )
    embedding_tokens_usage_mtok: float = Field(
        default=0.0,
        description="Embedding token quota in millions of tokens",
    )
    reranker_quota_ksearch: float = Field(
        default=0.0,
        description="Reranker quota for every thousand searches",
    )
    reranker_usage_ksearch: float = Field(
        default=0.0,
        description="Reranker usage for every thousand searches",
    )
    db_quota_gib: float = Field(
        default=0.0,
        description="DB storage quota in GiB.",
    )
    db_usage_gib: float = Field(
        default=0.0,
        description="DB storage usage in GiB.",
    )
    file_quota_gib: float = Field(
        default=0.0,
        description="File storage quota in GiB.",
    )
    file_usage_gib: float = Field(
        default=0.0,
        description="File storage usage in GiB.",
    )
    egress_quota_gib: float = Field(
        default=0.0,
        description="Egress quota in GiB.",
    )
    egress_usage_gib: float = Field(
        default=0.0,
        description="Egress usage in GiB.",
    )
    models: dict[str, Any] = Field(
        default={},
        description="The organization's custom model list, in addition to the provided default list.",
    )


class OrganizationRead(OrganizationCreate):
    id: str = Field(
        description="Organization ID.",
    )
    quota_reset_at: str = Field(
        default="",
        description="Previous quota reset date. Could be used as event key.",
    )
    stripe_id: str | None = Field(
        default=None,
        description="Organization Stripe ID.",
    )
    openmeter_id: str | None = Field(
        default=None,
        description="Organization OpenMeter ID.",
    )
    created_at: str = Field(
        description="Organization creation datetime (ISO 8601 UTC).",
    )
    updated_at: str = Field(
        description="Organization update datetime (ISO 8601 UTC).",
    )
    members: list[OrgMemberRead] | None = Field(
        default=None,
        description="List of organization members and roles.",
    )
    api_keys: list["ApiKeyRead"] | None = Field(
        default=None,
        description="List of API keys.",
    )
    projects: list[ProjectRead] | None = Field(
        default=None,
        description="List of projects.",
    )
    quotas: dict[str, dict[str, float]] = Field(
        default=None,
        description="Entitlements.",
    )


class OrganizationUpdate(BaseModel):
    id: str
    """Organization ID."""
    name: str | None = None
    """Organization name."""
    external_keys: dict[str, str] | None = Field(
        default=None,
        description="Mapping of service provider to its API key.",
    )
    credit: float | None = Field(
        default=None,
        description="Credit paid by the customer. Unused credit will be carried forward to the next billing cycle.",
    )
    credit_grant: float | None = Field(
        default=None,
        description="Credit granted to the customer. Unused credit will NOT be carried forward.",
    )
    llm_tokens_quota_mtok: float | None = Field(
        default=None,
        description="LLM token quota in millions of tokens.",
    )
    llm_tokens_usage_mtok: float | None = Field(
        default=None,
        description="LLM token usage in millions of tokens.",
    )
    embedding_tokens_quota_mtok: float | None = Field(
        default=None,
        description="Embedding token quota in millions of tokens",
    )
    embedding_tokens_usage_mtok: float | None = Field(
        default=None,
        description="Embedding token quota in millions of tokens",
    )
    reranker_quota_ksearch: float | None = Field(
        default=None,
        description="Reranker quota for every thousand searches",
    )
    reranker_usage_ksearch: float | None = Field(
        default=None,
        description="Reranker usage for every thousand searches",
    )
    db_quota_gib: float | None = Field(
        default=None,
        description="DB storage quota in GiB.",
    )
    db_usage_gib: float | None = Field(
        default=None,
        description="DB storage usage in GiB.",
    )
    file_quota_gib: float | None = Field(
        default=None,
        description="File storage quota in GiB.",
    )
    file_usage_gib: float | None = Field(
        default=None,
        description="File storage usage in GiB.",
    )
    egress_quota_gib: float | None = Field(
        default=None,
        description="Egress quota in GiB.",
    )
    egress_usage_gib: float | None = Field(
        default=None,
        description="Egress usage in GiB.",
    )
    tier: str | None = Field(
        default=None,
        description="Subscribed tier.",
    )
    active: bool | None = Field(
        default=None,
        description="Whether the organization's quota is active (paid).",
    )
    timezone: str | None = Field(default=None)
    """
    Timezone specifier.
    """
    stripe_id: str | None = Field(default=None)
    """Organization Stripe ID."""
    openmeter_id: str | None = Field(default=None)
    """Organization OpenMeter ID."""


class ApiKeyCreate(BaseModel):
    organization_id: str = Field(description="Organization ID.")


class ApiKeyRead(ApiKeyCreate):
    id: str = Field(description="The key.")
    created_at: str = Field(description="Creation datetime (ISO 8601 UTC).")


class EventCreate(BaseModel):
    id: str = Field(
        min_length=1,
        description="Event ID for idempotency. Must be unique.",
    )
    organization_id: str = Field(
        description="Organization ID.",
    )
    deltas: dict[str, float | int] = Field(
        default={},
        description="Delta changes to the values.",
    )
    values: dict[str, float | int] = Field(
        default={},
        description="New values (in-place update). Note that this will override any delta changes.",
    )
    pending: bool = Field(
        default=False,
        description="Whether the event is pending (in-progress)",
    )
    meta: dict[str, Any] = Field(
        default={},
        description="Metadata.",
    )


class EventRead(EventCreate):
    created_at: str = Field(
        description="Event creation datetime (ISO 8601 UTC).",
    )


class TemplateTag(BaseModel):
    id: str = Field(description="Tag ID.")


class Template(BaseModel):
    id: str = Field(description="Template ID.")
    name: str = Field(description="Template name.")
    created_at: str = Field(description="Template creation datetime (ISO 8601 UTC).")
    tags: list[TemplateTag] = Field(description="List of template tags")


class Chunk(BaseModel):
    """Class for storing a piece of text and associated metadata."""

    text: str = Field(description="Chunk text.")
    title: str = Field(default="", description='Document title. Defaults to "".')
    page: int | None = Field(default=None, description="Document page the chunk text from.")
    file_name: str = Field(default="", description="File name.")
    file_path: str = Field(default="", description="File path.")
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
    reranking_model: str | None = Field(
        default=None,
        description="Reranking model to use for hybrid search.",
        examples=[EXAMPLE_RERANKING_MODEL_IDS[0], None],
    )
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


class ModelInfo(BaseModel):
    id: str = Field(
        description=(
            'Unique identifier in the form of "{provider}/{model_id}". '
            "Users will specify this to select a model."
        ),
        examples=EXAMPLE_CHAT_MODEL_IDS,
    )
    object: str = Field(
        default="model",
        description="Type of API response object.",
        examples=["model"],
    )
    name: str = Field(
        description="Name of the model.",
        examples=["OpenAI GPT-4o Mini"],
    )
    context_length: int = Field(
        description="Context length of model.",
        examples=[16384],
    )
    languages: list[str] = Field(
        description="List of languages which the model is well-versed in.",
        examples=[["en"]],
    )
    owned_by: str = Field(
        description="The organization that owns the model.",
        examples=["openai"],
    )
    capabilities: list[
        Literal["completion", "chat", "image", "audio", "tool", "embed", "rerank"]
    ] = Field(
        description="List of capabilities of model.",
        examples=[["chat"]],
    )


class ModelDeploymentConfig(BaseModel):
    litellm_id: str = Field(
        default="",
        description=(
            "LiteLLM routing / mapping ID. "
            'For example, you can map "openai/gpt-4o" calls to "openai/gpt-4o-2024-08-06". '
            'For vLLM with OpenAI compatible server, use "openai/<vllm_model_id>".'
        ),
        examples=EXAMPLE_CHAT_MODEL_IDS,
    )
    api_base: str = Field(
        default="",
        description="Hosting url for the model.",
    )
    provider: str = Field(
        default="",
        description="Provider of the model.",
    )


class ModelConfig(ModelInfo):
    priority: int = Field(
        default=0,
        ge=0,
        description="Priority when assigning default model. Larger number means higher priority.",
    )
    deployments: list[ModelDeploymentConfig] = Field(
        description="List of model deployment configs.",
        min_length=1,
    )


class LLMModelConfig(ModelConfig):
    input_cost_per_mtoken: float = Field(
        default=-1.0,
        description="Cost in USD per million (mega) input / prompt token.",
    )
    output_cost_per_mtoken: float = Field(
        default=-1.0,
        description="Cost in USD per million (mega) output / completion token.",
    )

    @model_validator(mode="after")
    def check_cost_per_mtoken(self) -> Self:
        # GPT-4o-mini pricing (2024-08-10)
        if self.input_cost_per_mtoken <= 0:
            self.input_cost_per_mtoken = 0.150
        if self.output_cost_per_mtoken <= 0:
            self.output_cost_per_mtoken = 0.600
        return self


class EmbeddingModelConfig(ModelConfig):
    id: str = Field(
        description=(
            'Unique identifier in the form of "{provider}/{model_id}". '
            'For self-hosted models with Infinity, use "ellm/{org}/{model}". '
            "Users will specify this to select a model."
        ),
        examples=EXAMPLE_EMBEDDING_MODEL_IDS,
    )
    embedding_size: int = Field(
        description="Embedding size of the model",
    )
    # Currently only useful for openai
    dimensions: int | None = Field(
        default=None,
        description="Dimensions, a reduced embedding size (openai specs).",
    )
    # Most likely only useful for hf models
    transform_query: str | None = Field(
        default=None,
        description="Transform query that might be needed, esp. for hf models",
    )
    cost_per_mtoken: float = Field(
        default=-1, description="Cost in USD per million embedding tokens."
    )

    @model_validator(mode="after")
    def check_cost_per_mtoken(self) -> Self:
        # OpenAI text-embedding-3-small pricing (2024-09-09)
        if self.cost_per_mtoken < 0:
            self.cost_per_mtoken = 0.022
        return self


class RerankingModelConfig(ModelConfig):
    id: str = Field(
        description=(
            'Unique identifier in the form of "{provider}/{model_id}". '
            'For self-hosted models with Infinity, use "ellm/{org}/{model}". '
            "Users will specify this to select a model."
        ),
        examples=EXAMPLE_RERANKING_MODEL_IDS,
    )
    capabilities: list[Literal["rerank"]] = Field(
        default=["rerank"],
        description="List of capabilities of model.",
        examples=[["rerank"]],
    )
    cost_per_ksearch: float = Field(default=-1, description="Cost in USD for a thousand searches.")

    @model_validator(mode="after")
    def check_cost_per_ksearch(self) -> Self:
        # Cohere rerank-multilingual-v3.0 pricing (2024-09-09)
        if self.cost_per_ksearch < 0:
            self.cost_per_ksearch = 2.0
        return self


class ModelListConfig(BaseModel):
    llm_models: list[LLMModelConfig] = []
    embed_models: list[EmbeddingModelConfig] = []
    rerank_models: list[RerankingModelConfig] = []

    @property
    def models(self) -> list[LLMModelConfig | EmbeddingModelConfig | RerankingModelConfig]:
        """A list of all the models."""
        return self.llm_models + self.embed_models + self.rerank_models

    def __add__(self, other: ModelListConfig) -> ModelListConfig:
        if isinstance(other, ModelListConfig):
            self_ids = set(m.id for m in self.models)
            other_ids = set(m.id for m in other.models)
            repeated_ids = self_ids.intersection(other_ids)
            if len(repeated_ids) != 0:
                raise ValueError(
                    f"There are repeated model IDs among the two configs: {list(repeated_ids)}"
                )
            return ModelListConfig(
                llm_models=self.llm_models + other.llm_models,
                embed_models=self.embed_models + other.embed_models,
                rerank_models=self.rerank_models + other.rerank_models,
            )
        else:
            raise TypeError(
                f"Unsupported operand type(s) for +: 'ModelListConfig' and '{type(other)}'"
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

    def __str__(self) -> str:
        return self.value


def sanitise_name(v: str) -> str:
    """Replace any non-alphanumeric and dash characters with space.

    Args:
        v (str): Raw name string.

    Returns:
        out (str): Sanitised name string that is safe for OpenAI.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", v).strip()


MessageName = Annotated[str, AfterValidator(sanitise_name)]


class MessageToolCallFunction(BaseModel):
    arguments: str
    name: str | None


class MessageToolCall(BaseModel):
    id: str | None
    function: MessageToolCallFunction
    type: str


class ChatEntry(BaseModel):
    """Represents a message in the chat context."""

    model_config = ConfigDict(use_enum_values=True)

    role: ChatRole
    """Who said the message?"""
    content: str | list[dict[str, str | dict[str, str]]]
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
    def assistant(cls, content: str | list[dict[str, str]] | None, **kwargs):
        """Create a new assistant message."""
        return cls(role=ChatRole.ASSISTANT, content=content, **kwargs)

    @field_validator("content", mode="before")
    @classmethod
    def coerce_input(cls, value: Any) -> str | list[dict[str, str | dict[str, str]]]:
        if isinstance(value, list):
            return [cls.coerce_input(v) for v in value]
        if isinstance(value, dict):
            return {k: cls.coerce_input(v) for k, v in value.items()}
        if isinstance(value, str):
            return value
        if value is None:
            return ""
        return str(value)


class ChatCompletionChoiceOutput(ChatEntry):
    tool_calls: list[MessageToolCall] | None = None
    """List of tool calls if the message includes tool call responses."""


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
    message: ChatEntry | ChatCompletionChoiceOutput = Field(
        description="A chat completion message generated by the model."
    )
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
    def delta(self) -> ChatEntry | ChatCompletionChoiceOutput:
        return self.message


class References(BaseModel):
    object: str = Field(
        default="chat.references",
        description="Type of API response object.",
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
        description="Type of API response object.",
        examples=["gen_table.references"],
    )
    output_column_name: str


class GenTableChatCompletionChunks(BaseModel):
    object: str = Field(
        default="gen_table.completion.chunks",
        description="Type of API response object.",
        examples=["gen_table.completion.chunks"],
    )
    columns: dict[str, ChatCompletionChunk]
    row_id: str


class GenTableRowsChatCompletionChunks(BaseModel):
    object: str = Field(
        default="gen_table.completion.rows",
        description="Type of API response object.",
        examples=["gen_table.completion.rows"],
    )
    rows: list[GenTableChatCompletionChunks]


class ChatCompletionChunk(BaseModel):
    id: str = Field(
        description="A unique identifier for the chat completion. Each chunk has the same ID."
    )
    object: str = Field(
        default="chat.completion.chunk",
        description="Type of API response object.",
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
    def message(self) -> ChatEntry | ChatCompletionChoiceOutput | None:
        return self.choices[0].message if len(self.choices) > 0 else None

    @property
    def prompt_tokens(self) -> int:
        return self.usage.prompt_tokens

    @property
    def completion_tokens(self) -> int:
        return self.usage.completion_tokens

    @property
    def text(self) -> str:
        """The text of the most recent chat completion."""
        return self.message.content if len(self.choices) > 0 else ""

    @property
    def finish_reason(self) -> str | None:
        return self.choices[0].finish_reason if len(self.choices) > 0 else None


class GenTableStreamChatCompletionChunk(ChatCompletionChunk):
    object: str = Field(
        default="gen_table.completion.chunk",
        description="Type of API response object.",
        examples=["gen_table.completion.chunk"],
    )
    output_column_name: str
    row_id: str


class FunctionParameter(BaseModel):
    type: str = Field(
        default="", description="The type of the parameter, e.g., 'string', 'number'."
    )
    description: str = Field(default="", description="A description of the parameter.")
    enum: list[str] = Field(
        default=[], description="An optional list of allowed values for the parameter."
    )


class FunctionParameters(BaseModel):
    type: str = Field(
        default="object", description="The type of the parameters object, usually 'object'."
    )
    properties: dict[str, FunctionParameter] = Field(
        description="The properties of the parameters object."
    )
    required: list[str] = Field(description="A list of required parameter names.")
    additionalProperties: bool = Field(
        default=False, description="Whether additional properties are allowed."
    )


class Function(BaseModel):
    name: str = Field(default="", description="The name of the function.")
    description: str = Field(default="", description="A description of what the function does.")
    parameters: FunctionParameters = Field(description="The parameters for the function.")


class Tool(BaseModel):
    type: str = Field(default="function", description="The type of the tool, e.g., 'function'.")
    function: Function = Field(description="The function details of the tool.")


class ToolChoiceFunction(BaseModel):
    name: str = Field(default="", description="The name of the function.")


class ToolChoice(BaseModel):
    type: str = Field(default="function", description="The type of the tool, e.g., 'function'.")
    function: ToolChoiceFunction = Field(description="Select a tool for the chat model to use.")


class ChatRequest(BaseModel):
    id: str = Field(
        default="",
        description='Chat ID. Will be replaced with request ID. Defaults to "".',
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
        default=0.2,
        description="""
What sampling temperature to use, in [0.001, 2.0].
Higher values like 0.8 will make the output more random,
while lower values like 0.2 will make it more focused and deterministic.
""",
        examples=[0.2],
    )
    top_p: Annotated[float, Field(ge=0.001, le=1.0)] = Field(
        default=0.6,
        description="""
An alternative to sampling with temperature, called nucleus sampling,
where the model considers the results of the tokens with top_p probability mass.
So 0.1 means only the tokens comprising the top 10% probability mass are considered.
Must be in [0.001, 1.0].
""",
        examples=[0.6],
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

    @field_validator("stop", mode="after")
    @classmethod
    def convert_stop(cls, v: list[str] | None) -> list[str] | None:
        if isinstance(v, list) and len(v) == 0:
            v = None
        return v


class ChatRequestWithTools(ChatRequest):
    tools: list[Tool] = Field(
        description="A list of tools available for the chat model to use.",
        min_length=1,
        examples=[
            # --- [Tool Function] ---
            # def get_delivery_date(order_id: str) -> datetime:
            #     # Connect to the database
            #     conn = sqlite3.connect('ecommerce.db')
            #     cursor = conn.cursor()
            #     # ...
            [
                Tool(
                    type="function",
                    function=Function(
                        name="get_delivery_date",
                        description="Get the delivery date for a customer's order.",
                        parameters=FunctionParameters(
                            type="object",
                            properties={
                                "order_id": FunctionParameter(
                                    type="string", description="The customer's order ID."
                                )
                            },
                            required=["order_id"],
                            additionalProperties=False,
                        ),
                    ),
                )
            ],
        ],
    )
    tool_choice: str | ToolChoice = Field(
        default="auto",
        description="Set `auto` to let chat model pick a tool or select a tool for the chat model to use.",
        examples=[
            "auto",
            ToolChoice(type="function", function=ToolChoiceFunction(name="get_delivery_date")),
        ],
    )


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
        description="Type of API response object.",
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


ODD_SINGLE_QUOTE = r"(?<!')'(?!')"
GEN_CONFIG_VAR_PATTERN = r"(?<!\\)\${(.*?)}"


class MetaEnum(EnumMeta):
    def __contains__(cls, x):
        try:
            cls[x]
        except KeyError:
            return False
        return True


ENUM_DEPRECATE_MSSG = (
    "`DtypeCreateEnum` is deprecated and will be removed in v0.4, use a string instead. "
    'For example `DtypeCreateEnum.int_` -> "int".'
)


@deprecated(ENUM_DEPRECATE_MSSG, category=FutureWarning, stacklevel=1)
class DtypeCreateEnum(str, Enum, metaclass=MetaEnum):
    int_ = "int"
    float_ = "float"
    bool_ = "bool"
    str_ = "str"
    image_ = "image"
    audio_ = "audio"

    def __getattribute__(cls, *args, **kwargs):
        warn(ENUM_DEPRECATE_MSSG, FutureWarning, stacklevel=1)
        return super().__getattribute__(*args, **kwargs)

    def __getitem__(cls, *args, **kwargs):
        warn(ENUM_DEPRECATE_MSSG, FutureWarning, stacklevel=1)
        return super().__getitem__(*args, **kwargs)

    def __call__(cls, *args, **kwargs):
        warn(ENUM_DEPRECATE_MSSG, FutureWarning, stacklevel=1)
        return super().__call__(*args, **kwargs)

    def __str__(self) -> str:
        return self.value


class TableType(str, Enum, metaclass=MetaEnum):
    action = "action"
    """Action table."""
    knowledge = "knowledge"
    """Knowledge table."""
    chat = "chat"
    """Chat table."""

    def __str__(self) -> str:
        return self.value


class LLMGenConfig(BaseModel):
    object: Literal["gen_config.llm"] = Field(
        default="gen_config.llm",
        description='The object type, which is always "gen_config.llm".',
        examples=["gen_config.llm"],
    )
    model: str = Field(
        default="",
        description="ID of the model to use. See the model endpoint compatibility table for details on which models work with the Chat API.",
    )
    system_prompt: str = Field(
        default="",
        description="System prompt for the LLM.",
    )
    prompt: str = Field(
        default="",
        description="Prompt for the LLM.",
    )
    multi_turn: bool = Field(
        default=False,
        description="Whether this column is a multi-turn chat with history along the entire column.",
    )
    rag_params: RAGParams | None = Field(
        default=None,
        description="Retrieval Augmented Generation search params. Defaults to None (disabled).",
        examples=[None],
    )
    temperature: Annotated[float, Field(ge=0.001, le=2.0)] = Field(
        default=0.2,
        description="""
What sampling temperature to use, in [0.001, 2.0].
Higher values like 0.8 will make the output more random,
while lower values like 0.2 will make it more focused and deterministic.
""",
        examples=[0.2],
    )
    top_p: Annotated[float, Field(ge=0.001, le=1.0)] = Field(
        default=0.6,
        description="""
An alternative to sampling with temperature, called nucleus sampling,
where the model considers the results of the tokens with top_p probability mass.
So 0.1 means only the tokens comprising the top 10% probability mass are considered.
Must be in [0.001, 1.0].
""",
        examples=[0.6],
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

    @model_validator(mode="before")
    @classmethod
    def compat(cls, data: Any) -> Any:
        data_type = type(data).__name__
        if isinstance(data, BaseModel):
            data = data.model_dump()
        if not isinstance(data, dict):
            raise TypeError(
                f"Input to `LLMGenConfig` must be a dict or BaseModel, received: {data_type}"
            )
        if data.get("system_prompt", None) or data.get("prompt", None):
            return data
        warn(
            (
                f'Using {data_type} as input to "gen_config" is deprecated and will be disabled in v0.4, '
                f"use {cls.__name__} instead."
            ),
            FutureWarning,
            stacklevel=3,
        )
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

    @field_validator("stop", mode="after")
    @classmethod
    def convert_stop(cls, v: list[str] | None) -> list[str] | None:
        if isinstance(v, list) and len(v) == 0:
            v = None
        return v


class EmbedGenConfig(BaseModel):
    object: Literal["gen_config.embed"] = Field(
        default="gen_config.embed",
        description='The object type, which is always "gen_config.embed".',
        examples=["gen_config.embed"],
    )
    embedding_model: str = Field(
        description="The embedding model to use.",
        examples=EXAMPLE_EMBEDDING_MODEL_IDS,
    )
    source_column: str = Field(
        description="The source column for embedding.",
        examples=["text_column"],
    )


class CodeGenConfig(BaseModel):
    object: Literal["gen_config.code"] = Field(
        default="gen_config.code",
        description='The object type, which is always "gen_config.code".',
        examples=["gen_config.code"],
    )
    source_column: str = Field(
        description="The source column for python code to execute.",
        examples=["code_column"],
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
        else:
            return "gen_config.llm"
    return None


GenConfig = LLMGenConfig | EmbedGenConfig | CodeGenConfig
DiscriminatedGenConfig = Annotated[
    Union[
        Annotated[CodeGenConfig, Tag("gen_config.code")],
        Annotated[LLMGenConfig, Tag("gen_config.llm")],
        Annotated[LLMGenConfig, Tag("gen_config.chat")],
        Annotated[EmbedGenConfig, Tag("gen_config.embed")],
    ],
    Discriminator(_gen_config_discriminator),
]


class ColumnSchema(BaseModel):
    id: str = Field(description="Column name.")
    dtype: str = Field(
        default="str",
        description="Column data type.",
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
    gen_config: DiscriminatedGenConfig | None = Field(
        default=None,
        description=(
            '_Optional_. Generation config. If provided, then this column will be an "Output Column". '
            "Table columns on its left can be referenced by `${column-name}`."
        ),
    )


class ColumnSchemaCreate(ColumnSchema):
    id: str = Field(description="Column name.")
    dtype: Literal["int", "float", "bool", "str", "file", "image", "audio"] = Field(
        default="str",
        description=(
            'Column data type, one of ["int", "float", "bool", "str", "file", "image", "audio"]'
            ". Data type 'file' is deprecated, use 'image' instead."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def compat(cls, data: Any) -> Any:
        data_type = type(data).__name__
        if isinstance(data, BaseModel):
            data = data.model_dump()
        if not isinstance(data, dict):
            raise TypeError(
                f"Input to `ColumnSchemaCreate` must be a dict or BaseModel, received: {data_type}"
            )
        if isinstance(data.get("dtype", None), DtypeCreateEnum):
            data["dtype"] = data["dtype"].value
        return data


class TableBase(BaseModel):
    id: str = Field(primary_key=True, description="Table name.")
    version: str = Field(
        default=jamaibase_version, description="Table version, following jamaibase version."
    )
    meta: dict[str, Any] = Field(
        default={},
        description="Additional metadata about the table.",
    )


class TableSchema(TableBase):
    cols: list[ColumnSchema] = Field(description="List of column schema.")


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
        default_factory=datetime_now_iso,
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
            f"table_id={self.table_id}  stream={self.stream}  reindex={self.reindex} "
            f"concurrent={self.concurrent} data={_data}"
            ")"
        )

    @model_validator(mode="after")
    def check_data(self) -> Self:
        for row in self.data:
            for value in row.values():
                if isinstance(value, str) and (
                    value.startswith("s3://") or value.startswith("file://")
                ):
                    extension = splitext(value)[1].lower()
                    if extension not in IMAGE_FILE_EXTENSIONS + AUDIO_FILE_EXTENSIONS:
                        raise ValueError(
                            "Unsupported file type. Make sure the file belongs to "
                            "one of the following formats: \n"
                            f"[Image File Types]: \n{IMAGE_FILE_EXTENSIONS} \n"
                            f"[Audio File Types]: \n{AUDIO_FILE_EXTENSIONS}"
                        )
        return self


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

    @model_validator(mode="after")
    def check_data(self) -> Self:
        for value in self.data.values():
            if isinstance(value, str) and (
                value.startswith("s3://") or value.startswith("file://")
            ):
                extension = splitext(value)[1].lower()
                if extension not in IMAGE_FILE_EXTENSIONS + AUDIO_FILE_EXTENSIONS:
                    raise ValueError(
                        "Unsupported file type. Make sure the file belongs to "
                        "one of the following formats: \n"
                        f"[Image File Types]: \n{IMAGE_FILE_EXTENSIONS} \n"
                        f"[Audio File Types]: \n{AUDIO_FILE_EXTENSIONS}"
                    )
        return self


class RegenStrategy(str, Enum):
    """Strategies for selecting columns during row regeneration."""

    RUN_ALL = "run_all"
    RUN_BEFORE = "run_before"
    RUN_SELECTED = "run_selected"
    RUN_AFTER = "run_after"

    def __str__(self) -> str:
        return self.value


class RowRegen(BaseModel):
    table_id: str = Field(
        description="Table name or ID.",
    )
    row_id: str = Field(
        description="ID of the row to regenerate.",
    )
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
    output_column_id: str | None = Field(
        default=None,
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
    output_column_id: str | None = Field(
        default=None,
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
        description="_Optional_. Number of decimals for vectors. If its negative, exclude vector columns. Defaults to 0 (no rounding).",
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
        Field(description='The delimiter of the file: can be "," or "\\t". Defaults to ",".'),
    ] = ","


class TableImportRequest(BaseModel):
    file_path: Annotated[str, Field(description="The parquet file path.")]
    table_id_dst: Annotated[
        str | None, Field(description="_Optional_. The ID or name of the new table.")
    ] = None
    table_id_dst: Annotated[str, Field(description="The ID or name of the new table.")]


class FileUploadResponse(BaseModel):
    object: Literal["file.upload"] = Field(
        default="file.upload",
        description='The object type, which is always "file.upload".',
        examples=["file.upload"],
    )
    uri: str = Field(
        description="The URI of the uploaded file.",
        examples=[
            "s3://bucket-name/raw/org_id/project_id/uuid/filename.ext",
            "file:///path/to/raw/file.ext",
        ],
    )


class GetURLRequest(BaseModel):
    uris: list[str] = Field(
        description=(
            "A list of file URIs for which pre-signed URLs or local file paths are requested. "
            "The service will return a corresponding list of pre-signed URLs or local file paths."
        ),
    )


class GetURLResponse(BaseModel):
    object: Literal["file.urls"] = Field(
        default="file.urls",
        description='The object type, which is always "file.urls".',
        examples=["file.urls"],
    )
    urls: list[str] = Field(
        description="A list of pre-signed URLs or local file paths.",
        examples=[
            "https://presigned-url-for-file1.ext",
            "/path/to/file2.ext",
        ],
    )
