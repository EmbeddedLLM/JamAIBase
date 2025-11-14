from functools import cached_property
from typing import Literal, Self, Union

from natsort import natsorted
from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from jamaibase.types.common import (
    EXAMPLE_CHAT_MODEL_IDS,
    EXAMPLE_EMBEDDING_MODEL_IDS,
    EXAMPLE_RERANKING_MODEL_IDS,
)
from jamaibase.types.db import ModelInfoRead


class ModelInfoListResponse(BaseModel):
    object: Literal["models.info"] = Field(
        "models.info",
        description="Type of API response object.",
        examples=["models.info"],
    )
    data: list[ModelInfoRead] = Field(
        description="List of model information.",
    )

    @model_validator(mode="after")
    def sort_models(self) -> Self:
        self.data = list(natsorted(self.data, key=self._sort_key))
        return self

    @staticmethod
    def _sort_key(x: ModelInfoRead) -> str:
        return (int(not x.id.startswith("ellm")), x.name)


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
    llm_input_cost_per_mtoken: float = Field(
        description="Cost in USD per million input / prompt token.",
    )
    llm_output_cost_per_mtoken: float = Field(
        description="Cost in USD per million output / completion token.",
    )


class EmbeddingModelPrice(_ModelPrice):
    embedding_cost_per_mtoken: float = Field(
        description="Cost in USD per million embedding tokens.",
    )


class RerankingModelPrice(_ModelPrice):
    reranking_cost_per_ksearch: float = Field(
        description="Cost in USD for a thousand (kilo) searches."
    )


class ModelPrice(BaseModel):
    object: Literal["prices.models"] = Field(
        "prices.models",
        description="Type of API response object.",
        examples=["prices.models"],
    )
    llm_models: list[LLMModelPrice] = []
    embed_models: list[EmbeddingModelPrice] = []
    rerank_models: list[RerankingModelPrice] = []

    @cached_property
    def model_map(
        self,
    ) -> dict[str, Union[LLMModelPrice, EmbeddingModelPrice, RerankingModelPrice]]:
        """
        Build and cache a dictionary of models for faster lookups.

        Returns:
            Dict[str, Union[LLMModelPrice, EmbeddingModelPrice, RerankingModelPrice]]: A dictionary mapping model IDs to their price information.
        """
        cache = {}
        for model in self.llm_models:
            cache[model.id] = model
        for model in self.embed_models:
            cache[model.id] = model
        for model in self.rerank_models:
            cache[model.id] = model
        return cache

    def get(self, model_id: str) -> Union[LLMModelPrice, EmbeddingModelPrice, RerankingModelPrice]:
        """
        Retrieve the price information for a specific model by its ID.

        Args:
            model_id (str): The ID of the model to retrieve.

        Returns:
            Union[LLMModelPrice, EmbeddingModelPrice, RerankingModelPrice]:
                The pricing information for the requested model.

        Raises:
            ValueError: If the model ID is not found in the `model_map`.
        """
        try:
            return self.model_map[model_id]
        except KeyError as e:
            raise ValueError(
                f"Invalid model ID: {model_id}. Available models: {list(self.model_map.keys())}"
            ) from e
