from datetime import datetime, timezone

from pydantic import BaseModel, Field

from jamaibase.utils import uuid7_str


class _BaseUsageData(BaseModel):
    id: str = Field(
        default_factory=uuid7_str,
        description="UUID of the insert row.",
    )
    org_id: str = Field(
        description="Organization ID.",
    )
    proj_id: str = Field(
        description="Project ID.",
    )
    user_id: str = Field(
        description="User ID.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC Timestamp (microsecond precision) of the insert.",
    )
    cost: float = Field(
        description="Usage cost (per_million_tokens for LLM and Embedding, per_thousand_searches for Rerank).",
    )

    def as_list(self):
        """Convert the instance to a list, including all fields."""
        return list(self.model_dump().values())


class LlmUsageData(_BaseUsageData):
    model: str = Field(
        description="Model used.",
    )
    input_token: int = Field(
        description="Number of input tokens used.",
    )
    output_token: int = Field(
        description="Number of output tokens used.",
    )
    input_cost: float = Field(
        description="Cost in USD per million input tokens.",
    )
    output_cost: float = Field(
        description="Cost in USD per million output tokens.",
    )


class EmbedUsageData(_BaseUsageData):
    model: str = Field(
        description="Model used.",
    )
    token: int = Field(
        description="Number of tokens used.",
    )


class RerankUsageData(_BaseUsageData):
    model: str = Field(
        description="Model used.",
    )
    number_of_search: int = Field(
        description="Number of searches.",
    )


class EgressUsageData(_BaseUsageData):
    amount_gib: float = Field(
        description="Amount in GiB.",
    )


class FileStorageUsageData(_BaseUsageData):
    amount_gib: float = Field(
        description="Chargeable Amount in GiB.",
    )
    snapshot_gib: float = Field(
        description="Snapshot of amount in GiB.",
    )


class DBStorageUsageData(_BaseUsageData):
    amount_gib: float = Field(
        description="Chargeable Amount in GiB.",
    )
    snapshot_gib: float = Field(
        description="Snapshot of amount in GiB.",
    )


class UsageData(BaseModel):
    llm_usage: list[LlmUsageData] = []
    embed_usage: list[EmbedUsageData] = []
    rerank_usage: list[RerankUsageData] = []
    egress_usage: list[EgressUsageData] = []
    file_storage_usage: list[FileStorageUsageData] = []
    db_storage_usage: list[DBStorageUsageData] = []

    # A computed field to get the per type list
    def as_list_by_type(self) -> dict[str, list[list]]:
        """Returns a dictionary of lists, where each key is a usage type and the value is a list of lists."""
        return {
            "llm_usage": [usage.as_list() for usage in self.llm_usage],
            "embed_usage": [usage.as_list() for usage in self.embed_usage],
            "rerank_usage": [usage.as_list() for usage in self.rerank_usage],
            "egress_usage": [usage.as_list() for usage in self.egress_usage],
            "file_storage_usage": [usage.as_list() for usage in self.file_storage_usage],
            "db_storage_usage": [usage.as_list() for usage in self.db_storage_usage],
        }

    @property
    def total_usage_events(self) -> int:
        """Returns the total number of usage events across all types."""
        return (
            len(self.llm_usage)
            + len(self.embed_usage)
            + len(self.rerank_usage)
            + len(self.egress_usage)
            + len(self.file_storage_usage)
            + len(self.db_storage_usage)
        )

    def __add__(self, other: "UsageData") -> "UsageData":
        """Overload the + operator to combine two UsageData objects."""
        combined = UsageData()
        combined.llm_usage = self.llm_usage + other.llm_usage
        combined.embed_usage = self.embed_usage + other.embed_usage
        combined.rerank_usage = self.rerank_usage + other.rerank_usage
        combined.egress_usage = self.egress_usage + other.egress_usage
        combined.file_storage_usage = self.file_storage_usage + other.file_storage_usage
        combined.db_storage_usage = self.db_storage_usage + other.db_storage_usage
        return combined
