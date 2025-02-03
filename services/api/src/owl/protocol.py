"""
NOTES:

- Pydantic supports setting mutable values as default.
  This is in contrast to native `dataclasses` where it is not supported.

- Pydantic supports setting default fields in any order.
  This is in contrast to native `dataclasses` where fields with default values must be defined after non-default fields.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum, EnumMeta
from functools import cached_property, reduce
from os.path import splitext
from typing import Annotated, Any, Generic, Literal, Sequence, Type, TypeVar, Union

import numpy as np
import pyarrow as pa
from loguru import logger
from natsort import natsorted
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    computed_field,
    create_model,
    field_validator,
    model_validator,
)
from sqlmodel import JSON, Column, MetaData, SQLModel
from sqlmodel import Field as sql_Field
from typing_extensions import Self

from jamaibase import protocol as p
from jamaibase.exceptions import ResourceNotFoundError
from jamaibase.utils.io import json_dumps
from owl.utils import datetime_now_iso, uuid7_draft2_str
from owl.version import __version__ as owl_version

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

Name = Annotated[
    str,
    BeforeValidator(lambda v, _: v.strip() if isinstance(v, str) else v),
    Field(
        pattern=r"\w+",
        max_length=100,
        description=(
            "Name or ID. Must be unique with at least 1 non-symbol character and up to 100 characters."
        ),
    ),
]


class UserAgent(BaseModel):
    is_browser: bool = Field(
        default=True,
        description="Whether the request originates from a browser or an app.",
        examples=[True, False],
    )
    agent: str = Field(
        description="The agent, such as 'SDK', 'Chrome', 'Firefox', 'Edge', or an empty string if it cannot be determined.",
        examples=["", "SDK", "Chrome", "Firefox", "Edge"],
    )
    agent_version: str = Field(
        default="",
        description="The agent version, or an empty string if it cannot be determined.",
        examples=["", "5.0", "0.3.0"],
    )
    os: str = Field(
        default="",
        description="The system/OS name and release, such as 'Windows NT 10.0', 'Linux 5.15.0-113-generic', or an empty string if it cannot be determined.",
        examples=["", "Windows NT 10.0", "Linux 5.15.0-113-generic"],
    )
    architecture: str = Field(
        default="",
        description="The machine type, such as 'AMD64', 'x86_64', or an empty string if it cannot be determined.",
        examples=["", "AMD64", "x86_64"],
    )
    language: str = Field(
        default="",
        description="The SDK language, such as 'TypeScript', 'Python', or an empty string if it is not applicable.",
        examples=["", "TypeScript", "Python"],
    )
    language_version: str = Field(
        default="",
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


class ExternalKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    custom: str = ""
    openai: str = ""
    anthropic: str = ""
    gemini: str = ""
    cohere: str = ""
    groq: str = ""
    together_ai: str = ""
    jina: str = ""
    voyage: str = ""
    hyperbolic: str = ""
    cerebras: str = ""
    sambanova: str = ""
    deepseek: str = ""


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


class TemplateMeta(BaseModel):
    """Template metadata."""

    name: Name
    description: str
    tags: list[str]
    created_at: str = Field(
        default_factory=datetime_now_iso,
        description="Creation datetime (ISO 8601 UTC).",
    )


class ModelCapability(str, Enum):
    COMPLETION = "completion"
    CHAT = "chat"
    IMAGE = "image"
    AUDIO = "audio"
    TOOL = "tool"
    EMBED = "embed"
    RERANK = "rerank"

    def __str__(self) -> str:
        return self.value


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
        default="",
        description="The organization that owns the model. Defaults to the provider in model ID.",
        examples=["openai"],
    )
    capabilities: list[ModelCapability] = Field(
        description="List of capabilities of model.",
        examples=[[ModelCapability.CHAT]],
    )

    @model_validator(mode="after")
    def check_owned_by(self) -> Self:
        if self.owned_by.strip() == "":
            self.owned_by = self.id.split("/")[0]
        return self


class ModelInfoResponse(BaseModel):
    object: str = Field(
        default="chat.model_info",
        description="Type of API response object.",
        examples=["chat.model_info"],
    )
    data: list[ModelInfo] = Field(
        description="List of model information.",
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
        [],
        description="List of model deployment configs.",
    )
    litellm_id: str = Field(
        default="",
        deprecated=True,
        description=(
            "Deprecated. Retained for compatibility. "
            "LiteLLM routing / mapping ID. "
            'For example, you can map "openai/gpt-4o" calls to "openai/gpt-4o-2024-08-06". '
            'For vLLM with OpenAI compatible server, use "openai/<vllm_model_id>".'
        ),
        examples=EXAMPLE_CHAT_MODEL_IDS,
    )
    api_base: str = Field(
        default="",
        deprecated=True,
        description="Deprecated. Retained for compatibility. Hosting url for the model.",
    )

    @model_validator(mode="after")
    def compat_deployments(self) -> Self:
        if len(self.deployments) > 0:
            return self
        self.deployments = [
            ModelDeploymentConfig(
                litellm_id=self.litellm_id,
                api_base=self.api_base,
                provider=self.id.split("/")[0],
            )
        ]
        return self


class LLMModelConfig(ModelConfig):
    input_cost_per_mtoken: float = Field(
        default=-1.0,
        description="Cost in USD per million (mega) input / prompt token.",
    )
    output_cost_per_mtoken: float = Field(
        default=-1.0,
        description="Cost in USD per million (mega) output / completion token.",
    )
    capabilities: list[ModelCapability] = Field(
        default=[ModelCapability.CHAT],
        description="List of capabilities of model.",
        examples=[[ModelCapability.CHAT]],
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
    capabilities: list[ModelCapability] = Field(
        default=[ModelCapability.EMBED],
        description="List of capabilities of model.",
        examples=[[ModelCapability.EMBED]],
    )
    cost_per_mtoken: float = Field(
        default=-1,
        description="Cost in USD per million embedding tokens.",
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
    capabilities: list[ModelCapability] = Field(
        default=[ModelCapability.RERANK],
        description="List of capabilities of model.",
        examples=[[ModelCapability.RERANK]],
    )
    cost_per_ksearch: float = Field(
        default=-1,
        description="Cost in USD for a thousand searches.",
    )

    @model_validator(mode="after")
    def check_cost_per_ksearch(self) -> Self:
        # Cohere rerank-multilingual-v3.0 pricing (2024-09-09)
        if self.cost_per_ksearch < 0:
            self.cost_per_ksearch = 2.0
        return self


class ModelListConfig(BaseModel):
    object: str = Field(
        default="configs.models",
        description="Type of API response object.",
        examples=["configs.models"],
    )
    llm_models: list[LLMModelConfig] = []
    embed_models: list[EmbeddingModelConfig] = []
    rerank_models: list[RerankingModelConfig] = []

    @cached_property
    def models(self) -> list[LLMModelConfig | EmbeddingModelConfig | RerankingModelConfig]:
        """A list of all the models."""
        return self.llm_models + self.embed_models + self.rerank_models

    @cached_property
    def model_map(self) -> dict[str, LLMModelConfig | EmbeddingModelConfig | RerankingModelConfig]:
        """A map of all the models."""
        return {m.id: m for m in self.models}

    def get_model_info(
        self, model_id: str
    ) -> LLMModelConfig | EmbeddingModelConfig | RerankingModelConfig:
        try:
            return self.model_map[model_id]
        except KeyError:
            raise ValueError(
                f"Invalid model ID: {model_id}. Available models: {[m.id for m in self.models]}"
            ) from None

    def get_llm_model_info(self, model_id: str) -> LLMModelConfig:
        return self.get_model_info(model_id)

    def get_embed_model_info(self, model_id: str) -> EmbeddingModelConfig:
        return self.get_model_info(model_id)

    def get_rerank_model_info(self, model_id: str) -> RerankingModelConfig:
        return self.get_model_info(model_id)

    def get_default_model(self, capabilities: list[str] | None = None) -> str:
        models = self.models
        if capabilities is not None:
            for capability in capabilities:
                models = [m for m in models if capability in m.capabilities]
            # if `capabilities`` is chat only, filter out audio model
            if capabilities == ["chat"]:
                models = [m for m in models if "audio" not in m.capabilities]
        if len(models) == 0:
            raise ResourceNotFoundError(f"No model found with capabilities: {capabilities}")
        model = natsorted(models, key=self._sort_key_with_priority)[0]
        return model.id

    @staticmethod
    def _sort_key_with_priority(
        x: LLMModelConfig | EmbeddingModelConfig | RerankingModelConfig,
    ) -> str:
        return (int(not x.id.startswith("ellm")), -x.priority, x.name)

    @model_validator(mode="after")
    def sort_models(self) -> Self:
        self.llm_models = list(natsorted(self.llm_models, key=self._sort_key))
        self.embed_models = list(natsorted(self.embed_models, key=self._sort_key))
        self.rerank_models = list(natsorted(self.rerank_models, key=self._sort_key))
        return self

    @model_validator(mode="after")
    def unique_model_ids(self) -> Self:
        if len(set(m.id for m in self.models)) != len(self.models):
            raise ValueError("There are repeated model IDs in the config.")
        return self

    @staticmethod
    def _sort_key(
        x: LLMModelConfig | EmbeddingModelConfig | RerankingModelConfig,
    ) -> str:
        return (int(not x.id.startswith("ellm")), x.name)

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


class Chunk(p.Chunk):
    pass


class SplitChunksParams(p.SplitChunksParams):
    pass


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
    starting_after: Annotated[
        str | int | None, Field(description="Pagination cursor.", examples=["31a0552", 0, None])
    ] = None


def nd_array_before_validator(x):
    return np.array(x) if isinstance(x, list) else x


def datetime_str_before_validator(x):
    return x.isoformat() if isinstance(x, datetime) else str(x)


COL_NAME_PATTERN = r"^[A-Za-z0-9]([A-Za-z0-9 _-]{0,98}[A-Za-z0-9])?$"
TABLE_NAME_PATTERN = r"^[A-Za-z0-9]([A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$"
ODD_SINGLE_QUOTE = r"(?<!')'(?!')"
GEN_CONFIG_VAR_PATTERN = r"(?<!\\)\${(.*?)}"
NdArray = Annotated[
    np.ndarray,
    BeforeValidator(nd_array_before_validator),
]
DateTimeStr = Annotated[
    str,
    BeforeValidator(datetime_str_before_validator),
]
ColName = Annotated[
    str,
    Field(
        pattern=COL_NAME_PATTERN,
        description=(
            "Column name or ID. "
            "Must be unique with at least 1 character and up to 100 characters. "
            "Must start and end with an alphabet or number. "
            "Characters in the middle can include `_` (underscore), `-` (dash), ` ` (space). "
            'Cannot be called "ID" or "Updated at" (case-insensitive).'
        ),
    ),
]
TableName = Annotated[
    str,
    Field(
        pattern=TABLE_NAME_PATTERN,
        description=(
            "Table name or ID. "
            "Must be unique with at least 1 character and up to 100 characters. "
            "Must start and end with an alphabet or number. "
            "Characters in the middle can include `_` (underscore), `-` (dash), `.` (dot)."
        ),
    ),
]
_str_to_arrow = {
    "date-time": pa.timestamp("us", tz="UTC"),
    "int": pa.int64(),
    "int8": pa.int8(),
    "float": pa.float64(),
    "float32": pa.float32(),
    "float16": pa.float16(),
    "bool": pa.bool_(),
    "str": pa.utf8(),  # Alias for `pa.string()`
    "chat": pa.utf8(),
    "image": pa.utf8(),
    "audio": pa.utf8(),
}
_str_to_py_type = {
    "int": int,
    "int8": int,
    "float": float,
    "float64": np.float64,
    "float32": np.float32,
    "float16": np.float16,
    "bool": bool,
    "str": str,
    "date-time": datetime,
    "chat": str,
    "image": str,
    "audio": str,
}


def str_to_py_type(py_type: str, vlen: int = 0, json_safe: bool = False):
    if vlen > 0:
        return list[float] if json_safe else NdArray
    return _str_to_py_type[py_type]


class MetaEnum(EnumMeta):
    def __contains__(cls, x):
        try:
            cls[x]
        except KeyError:
            return False
        return True


class CSVDelimiter(Enum, metaclass=MetaEnum):
    COMMA = ","
    """Comma-separated"""
    TAB = "\t"
    """Tab-separated"""

    def __str__(self) -> str:
        return self.value


class ColumnDtype(str, Enum, metaclass=MetaEnum):
    INT = "int"
    INT8 = "int8"
    FLOAT = "float"
    FLOAT32 = "float32"
    FLOAT16 = "float16"
    BOOL = "bool"
    STR = "str"
    DATE_TIME = "date-time"
    IMAGE = "image"
    AUDIO = "audio"

    def __str__(self) -> str:
        return self.value


class ColumnDtypeCreate(str, Enum, metaclass=MetaEnum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STR = "str"
    IMAGE = "image"
    AUDIO = "audio"

    def __str__(self) -> str:
        return self.value


class TableType(str, Enum, metaclass=MetaEnum):
    ACTION = "action"
    """Action table."""
    KNOWLEDGE = "knowledge"
    """Knowledge table."""
    CHAT = "chat"
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


class CodeGenConfig(p.CodeGenConfig):
    pass


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
    dtype: ColumnDtype = Field(
        default=ColumnDtype.STR,
        description='Column data type, one of ["int", "int8", "float", "float32", "float16", "bool", "str", "date-time", "image"]',
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

    @model_validator(mode="after")
    def check_vector_column_dtype(self) -> Self:
        if self.vlen > 0 and self.dtype not in (ColumnDtype.FLOAT32, ColumnDtype.FLOAT16):
            raise ValueError("Vector columns must contain float32 or float16 only.")
        return self


class ColumnSchemaCreate(ColumnSchema):
    id: ColName = Field(description="Column name.")
    dtype: ColumnDtypeCreate = Field(
        default=ColumnDtypeCreate.STR,
        description='Column data type, one of ["int", "float", "bool", "str", "image", "audio"]',
    )

    @model_validator(mode="before")
    def match_column_dtype_file_to_image(self) -> Self:
        if self.get("dtype", "") == "file":
            self["dtype"] = ColumnDtype.IMAGE
        return self

    @model_validator(mode="after")
    def check_output_column_dtype(self) -> Self:
        if self.gen_config is not None and self.vlen == 0:
            if isinstance(self.gen_config, CodeGenConfig):
                if self.dtype not in (ColumnDtype.STR, ColumnDtype.IMAGE):
                    raise ValueError(
                        "Output column must be either string or image column when gen_config is CodeGenConfig."
                    )
            elif self.dtype != ColumnDtype.STR:
                raise ValueError("Output column must be string column.")
        return self


class TableSQLModel(SQLModel):
    metadata = MetaData()


class TableBase(TableSQLModel):
    id: str = sql_Field(primary_key=True, description="Table name.")
    version: str = sql_Field(
        default=owl_version, description="Table version, following owl version."
    )
    meta: dict[str, Any] = sql_Field(
        sa_column=Column(JSON),
        default={},
        description="Additional metadata about the table.",
    )


class TableSchema(TableBase):
    cols: list[ColumnSchema] = sql_Field(description="List of column schema.")

    def get_col(self, id: str):
        return [c for c in self.cols if c.id.lower() == id.lower()][0]

    @staticmethod
    def _get_col_dtype(py_type: str, vlen: int = 0):
        if vlen > 0:
            return pa.list_(_str_to_arrow[py_type], vlen)
        return _str_to_arrow[py_type]

    @property
    def pyarrow(self) -> pa.Schema:
        return pa.schema(
            [pa.field(c.id, self._get_col_dtype(c.dtype.value, c.vlen)) for c in self.cols]
        )

    @property
    def pyarrow_vec(self) -> pa.Schema:
        return pa.schema(
            [
                pa.field(c.id, self._get_col_dtype(c.dtype.value, c.vlen))
                for c in self.cols
                if c.vlen > 0
            ]
        )

    def add_state_cols(self) -> Self:
        """
        Adds state columns.

        Returns:
            self (TableSchemaCreate): TableSchemaCreate
        """
        cols = []
        for c in self.cols:
            cols.append(c)
            if c.id.lower() not in ("id", "updated at"):
                cols.append(ColumnSchema(id=f"{c.id}_", dtype=ColumnDtype.STR))
        self.cols = cols
        return self

    def add_info_cols(self) -> Self:
        """
        Adds "ID", "Updated at" columns.

        Returns:
            self (TableSchemaCreate): TableSchemaCreate
        """
        self.cols = [
            ColumnSchema(id="ID", dtype=ColumnDtype.STR),
            ColumnSchema(id="Updated at", dtype=ColumnDtype.DATE_TIME),
        ] + self.cols
        return self

    @staticmethod
    def get_default_prompts(
        table_id: str,
        curr_column: ColumnSchema,
        column_ids: list[str],
    ) -> tuple[str, str]:
        input_cols = "\n\n".join(c + ": ${" + c + "}" for c in column_ids)
        if getattr(curr_column.gen_config, "multi_turn", False):
            system_prompt = (
                f'You are an agent named "{table_id}". Be helpful. Provide answers based on the information given. '
                "Ensuring that your reply is easy to understand and is accessible to all users. "
                "Be factual and do not hallucinate."
            )
            user_prompt = "${User}"
        else:
            system_prompt = (
                "You are a versatile data generator. "
                "Your task is to process information from input data and generate appropriate responses "
                "based on the specified column name and input data. "
                "Adapt your output format and content according to the column name provided."
            )
            user_prompt = (
                f'Table name: "{table_id}"\n\n'
                f"{input_cols}\n\n"
                f'Based on the available information, provide an appropriate response for the column "{curr_column.id}".\n'
                "Remember to act as a cell in a spreadsheet and provide concise, "
                "relevant information without explanations unless specifically requested."
            )
        return system_prompt, user_prompt

    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        for i, col in enumerate(self.cols):
            gen_config = col.gen_config
            if gen_config is None:
                continue
            available_cols = [
                col
                for col in self.cols[:i]
                if (not col.id.endswith("_"))
                and col.id.lower() not in ("id", "updated at")
                and col.vlen == 0
            ]
            col_ids = [col.id for col in available_cols]
            col_ids_set = set(col_ids)
            if isinstance(gen_config, EmbedGenConfig):
                if gen_config.source_column not in col_ids_set:
                    raise ValueError(
                        (
                            f"Table '{self.id}': "
                            f"Embedding config of column '{col.id}' referenced "
                            f"an invalid source column '{gen_config.source_column}'. "
                            "Make sure you only reference columns on its left. "
                            f"Available columns: {col_ids}."
                        )
                    )
            elif isinstance(gen_config, CodeGenConfig):
                source_col = next(
                    (c for c in available_cols if c.id == gen_config.source_column), None
                )
                if source_col is None:
                    raise ValueError(
                        (
                            f"Table '{self.id}': "
                            f"Code Execution config of column '{col.id}' referenced "
                            f"an invalid source column '{gen_config.source_column}'. "
                            "Make sure you only reference columns on its left. "
                            f"Available columns: {col_ids}."
                        )
                    )
                if source_col.dtype != ColumnDtype.STR:
                    raise ValueError(
                        (
                            f"Table '{self.id}': "
                            f"Code Execution config of column '{col.id}' referenced "
                            f"a source column '{gen_config.source_column}' with an invalid datatype of '{source_col.dtype}'. "
                            "Make sure the source column is Str typed."
                        )
                    )
            elif isinstance(gen_config, LLMGenConfig):
                # Insert default prompts if needed
                system_prompt, user_prompt = self.get_default_prompts(
                    table_id=self.id,
                    curr_column=col,
                    column_ids=[col.id for col in available_cols if col.gen_config is None],
                )
                if not gen_config.system_prompt.strip():
                    gen_config.system_prompt = system_prompt
                if not gen_config.prompt.strip():
                    gen_config.prompt = user_prompt
                # Check references
                for message in (gen_config.system_prompt, gen_config.prompt):
                    for key in re.findall(GEN_CONFIG_VAR_PATTERN, message):
                        if key not in col_ids_set:
                            raise ValueError(
                                (
                                    f"Table '{self.id}': "
                                    f"Generation prompt of column '{col.id}' referenced "
                                    f"an invalid source column '{key}'. "
                                    "Make sure you only reference columns on its left. "
                                    f"Available columns: {col_ids}."
                                )
                            )
        return self


class TableSchemaCreate(TableSchema):
    id: TableName = Field(description="Table name.")
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
    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        # Check gen config using TableSchema
        return self


class KnowledgeTableSchemaCreate(TableSchemaCreate):
    embedding_model: str

    @model_validator(mode="after")
    def check_cols(self) -> Self:
        super().check_cols()
        num_text_cols = sum(
            c.id.lower() in ("text", "title", "file id", "page") for c in self.cols
        )
        if num_text_cols != 0:
            raise ValueError(
                "Schema cannot contain column names: 'Text', 'Title', 'File ID', 'Page'."
            )
        return self

    @staticmethod
    def get_default_prompts(*args, **kwargs) -> tuple[str, str]:
        # This should act as if its AddKnowledgeColumnSchema
        return "", ""


class AddKnowledgeColumnSchema(TableSchemaCreate):
    @model_validator(mode="after")
    def check_cols(self) -> Self:
        super().check_cols()
        num_text_cols = sum(
            c.id.lower() in ("text", "title", "file id", "page") for c in self.cols
        )
        if num_text_cols != 0:
            raise ValueError(
                "Schema cannot contain column names: 'Text', 'Title', 'File ID', 'Page'."
            )
        return self

    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        # Check gen config using TableSchema
        return self


class ChatTableSchemaCreate(TableSchemaCreate):
    pass


class AddChatColumnSchema(TableSchemaCreate):
    @model_validator(mode="after")
    def check_cols(self) -> Self:
        super().check_cols()
        return self

    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        # Check gen config using TableSchema
        return self


class TableMeta(TableBase, table=True):
    cols: list[dict[str, Any]] = sql_Field(
        sa_column=Column(JSON), description="List of column schema."
    )
    parent_id: str | None = sql_Field(
        default=None,
        description="The parent table ID. If None (default), it means this is a template table.",
    )
    title: str = sql_Field(
        default="",
        description="Chat title. Defaults to ''.",
    )
    updated_at: str = sql_Field(
        default_factory=datetime_now_iso,
        description="Table last update timestamp (ISO 8601 UTC).",
    )  # SQLite does not support TZ
    indexed_at_fts: str | None = sql_Field(
        default=None, description="Table last FTS index timestamp (ISO 8601 UTC)."
    )
    indexed_at_vec: str | None = sql_Field(
        default=None, description="Table last vector index timestamp (ISO 8601 UTC)."
    )
    indexed_at_sca: str | None = sql_Field(
        default=None, description="Table last scalar index timestamp (ISO 8601 UTC)."
    )

    @property
    def cols_schema(self) -> list[ColumnSchema]:
        return [ColumnSchema.model_validate(c) for c in deepcopy(self.cols)]

    @property
    def regular_cols(self) -> list[ColumnSchema]:
        return [c for c in self.cols_schema if not c.id.endswith("_")]


class TableMetaResponse(TableSchema):
    parent_id: TableName | None = Field(
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
    num_rows: int = Field(
        default=-1,
        description="Number of rows in the table. Defaults to -1 (not counted).",
    )

    @model_validator(mode="after")
    def check_gen_configs(self) -> Self:
        return self

    @model_validator(mode="after")
    def remove_state_cols(self) -> Self:
        self.cols = [c for c in self.cols if not c.id.endswith("_")]
        return self


class RowAddData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    table_meta: TableMeta = Field(description="Table metadata.")
    data: list[dict[ColName, Any]] = Field(
        description="List of row data to add or update. Each list item is a mapping of column ID to its value."
    )
    errors: list[list[str]] | None = Field(
        default=None,
        description=(
            "List of row columns that encountered errors (perhaps LLM generation failed mid-stream). "
            "Each list item is a list of column IDs."
        ),
    )

    @model_validator(mode="after")
    def check_errors(self) -> Self:
        if self.errors is None:
            return self
        if len(self.errors) != len(self.data):
            raise ValueError(
                (
                    "`errors` must contain same number of items as `data`, "
                    f"received: len(errors)={len(self.errors)}   len(data)={len(self.data)}"
                )
            )
        return self

    @model_validator(mode="after")
    def check_data(self) -> Self:
        if "updated at" in self.data:
            raise ValueError("`data` cannot contain keys: 'Updated at'.")
        return self

    @model_validator(mode="after")
    def handle_nulls_and_validate(self) -> Self:
        return self._handle_nulls_and_validate()

    def _handle_nulls_and_validate(self, check_missing_cols: bool = True) -> Self:
        cols = {
            c.id: c
            for c in self.table_meta.cols_schema
            if not (c.id.lower() in ("id", "updated at") or c.id.endswith("_"))
        }
        # Create the row schema for validation
        PydanticSchema: Type[BaseModel] = create_model(
            f"{self.__class__.__name__}Schema",
            __config__=ConfigDict(arbitrary_types_allowed=True),
            **{c.id: (str_to_py_type(c.dtype.value, c.vlen) | None, None) for c in cols.values()},
        )
        self.errors = [[] for _ in self.data]

        # Validate
        for d, err in zip(self.data, self.errors, strict=True):
            # Fill in missing cols
            if check_missing_cols:
                for k in cols:
                    if k not in d:
                        d[k] = None
            try:
                PydanticSchema.model_validate(d)
            except ValidationError as e:
                failed_cols = set(reduce(lambda a, b: a + b, (err["loc"] for err in e.errors())))
                logger.info(
                    f"Table {self.table_meta.id}: These columns failed validation: {failed_cols}"
                )
            else:
                failed_cols = {}
            for k in list(d.keys()):
                if k not in cols:
                    continue
                col = cols[k]
                state = {}
                if k in failed_cols:
                    d[k], state["original"] = None, d[k]
                if k in err:
                    d[k] = None
                    # state["error"] = True
                if d[k] is None:
                    if col.dtype == ColumnDtype.INT:
                        d[k] = 0
                    elif col.dtype == ColumnDtype.FLOAT:
                        d[k] = 0.0
                    elif col.dtype == ColumnDtype.BOOL:
                        d[k] = False
                    elif col.dtype in (ColumnDtype.STR, ColumnDtype.IMAGE):
                        # Store null string as ""
                        # https://github.com/lancedb/lancedb/issues/1160
                        d[k] = ""
                    elif col.vlen > 0:
                        # TODO: Investigate setting null vectors to np.nan
                        # Pros: nan vectors won't show up in vector search
                        # Cons: May cause error during vector indexing
                        d[k] = np.zeros([col.vlen], dtype=_str_to_py_type[col.dtype.value])
                    state["is_null"] = True
                else:
                    if col.vlen > 0:
                        d[k] = np.asarray(d[k], dtype=_str_to_py_type[col.dtype.value])
                    state["is_null"] = False
                d[f"{k}_"] = json_dumps(state)
            d["Updated at"] = datetime.now(timezone.utc)
        return self

    def set_id(self) -> Self:
        """
        Sets ID,

        Returns:
            self (RowAddData): RowAddData
        """
        for d in self.data:
            if "ID" not in d:
                d["ID"] = uuid7_draft2_str()
        return self

    def sql_escape(self) -> Self:
        cols = {c.id: c for c in self.table_meta.cols_schema}
        for d in self.data:
            for k in list(d.keys()):
                if cols[k].dtype == ColumnDtype.STR:
                    d[k] = re.sub(ODD_SINGLE_QUOTE, "''", d[k])
        return self


class RowUpdateData(RowAddData):
    @model_validator(mode="after")
    def check_data(self) -> Self:
        if sum(n.lower() in ("id", "updated at") for d in self.data for n in d) > 0:
            raise ValueError("`data` cannot contain keys: 'ID' or 'Updated at'.")
        return self

    @model_validator(mode="after")
    def handle_nulls_and_validate(self) -> Self:
        return self._handle_nulls_and_validate(check_missing_cols=False)


class GenConfigUpdateRequest(BaseModel):
    table_id: TableName = Field(description="Table name or ID.")
    column_map: dict[ColName, DiscriminatedGenConfig | None] = Field(
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
    table_id: TableName = Field(description="Table name or ID.")
    column_map: dict[ColName, ColName] = Field(
        description="Mapping of old column names to new column names."
    )

    @model_validator(mode="after")
    def check_column_map(self) -> Self:
        if sum(n.lower() in ("id", "updated at") for n in self.column_map) > 0:
            raise ValueError("`column_map` cannot contain keys: 'ID' or 'Updated at'.")
        return self


class ColumnReorderRequest(BaseModel):
    table_id: TableName = Field(description="Table name or ID.")
    column_names: list[ColName] = Field(description="List of column ID in the desired order.")

    @field_validator("column_names", mode="after")
    @classmethod
    def check_unique_column_names(cls, value: list[ColName]) -> list[ColName]:
        if len(set(n.lower() for n in value)) != len(value):
            raise ValueError("Column names must be unique (case-insensitive).")
        return value


class ColumnDropRequest(BaseModel):
    table_id: TableName = Field(description="Table name or ID.")
    column_names: list[ColName] = Field(description="List of column ID to drop.")

    @model_validator(mode="after")
    def check_column_names(self) -> Self:
        if sum(n.lower() in ("id", "updated at") for n in self.column_names) > 0:
            raise ValueError("`column_names` cannot contain keys: 'ID' or 'Updated at'.")
        return self


class Task(BaseModel):
    output_column_name: str
    body: LLMGenConfig


class RowAdd(BaseModel):
    table_id: TableName = Field(
        description="Table name or ID.",
    )
    data: dict[ColName, Any] = Field(
        description="Mapping of column names to its value.",
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
        description="_Optional_. Whether or not to concurrently generate the output columns.",
    )


class RowAddRequest(BaseModel):
    table_id: TableName = Field(
        description="Table name or ID.",
    )
    data: list[dict[ColName, Any]] = Field(
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
            for row in self.data
            for k, v in row.items()
        ]
        return (
            f"{self.__class__.__name__}("
            f"table_id={self.table_id}  stream={self.stream}  reindex={self.reindex}"
            f"concurrent={self.concurrent}  data={_data}"
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
    data: list[dict[ColName, Any]] = Field(
        min_length=1,
        max_length=100,
        description=(
            "List of mapping of column names to its value. "
            "In other words, each item in the list is a row, and each item is a mapping. "
            "Minimum 1 row, maximum 100 rows."
        ),
    )


class RowUpdateRequest(BaseModel):
    table_id: TableName = Field(
        description="Table name or ID.",
    )
    row_id: str = Field(
        description="ID of the row to update.",
    )
    data: dict[ColName, Any] = Field(
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
    table_id: TableName = Field(
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
    table_id: TableName = Field(
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
    table_id: TableName = Field(description="Table name or ID.")
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
    table_id: TableName = Field(description="Table name or ID.")
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
    table_id: TableName = Field(description="Table name or ID.")
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
        str,
        Field(description='The delimiter of the file: can be "," or "\\t". Defaults to ",".'),
    ] = ","


class FileUploadResponse(p.FileUploadResponse):
    pass


class GetURLRequest(p.GetURLRequest):
    pass


class GetURLResponse(p.GetURLResponse):
    pass
