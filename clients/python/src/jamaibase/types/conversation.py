from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from jamaibase.types.common import DatetimeUTC, SanitisedNonEmptyStr, SanitisedStr
from jamaibase.types.gen_table import ColumnSchema, TableMetaResponse


class _MetaResponse(BaseModel):
    meta: dict[SanitisedNonEmptyStr, Any] | None = Field(
        None,
        description="Additional metadata about the table.",
    )
    cols: list[ColumnSchema] = Field(
        description="List of column schema.",
    )
    title: SanitisedStr = Field(
        description="Conversation title.",
    )
    created_by: SanitisedNonEmptyStr = Field(
        description="ID of the user that created this table.",
    )
    updated_at: DatetimeUTC = Field(
        description="Table last update datetime (UTC).",
    )
    num_rows: int = Field(
        -1,
        description="Number of rows in the table. Defaults to -1 (not counted).",
    )
    version: str = Field(
        description="Version.",
    )

    @model_validator(mode="after")
    def remove_state_cols(self) -> Self:
        self.cols = [c for c in self.cols if not c.id.endswith("_")]
        return self


class AgentMetaResponse(_MetaResponse):
    agent_id: SanitisedNonEmptyStr = Field(
        description="Agent ID.",
    )

    @classmethod
    def from_table_meta(cls, meta: TableMetaResponse) -> Self:
        """Returns an instance from TableMetaResponse."""
        return cls(agent_id=meta.id, **meta.model_dump(exclude={"id"}))


class ConversationMetaResponse(_MetaResponse):
    conversation_id: SanitisedNonEmptyStr = Field(
        description="Conversation ID.",
    )
    parent_id: SanitisedNonEmptyStr | None = Field(
        description="The parent table ID. If None, it means this is a parent table.",
    )

    @classmethod
    def from_table_meta(cls, meta: TableMetaResponse) -> Self:
        """Returns an instance from TableMetaResponse."""
        return cls(conversation_id=meta.id, **meta.model_dump(exclude={"id"}))


class _MessageBase(BaseModel):
    data: dict[str, Any] = Field(
        description="Mapping of column names to its value.",
    )


class ConversationCreateRequest(_MessageBase):
    """Request to create a new conversation."""

    agent_id: SanitisedNonEmptyStr = Field(
        description="Agent ID (parent Chat Table ID).",
    )
    title: SanitisedStr | None = Field(
        None,
        min_length=1,
        description="The title of the conversation.",
    )


class MessageAddRequest(_MessageBase):
    conversation_id: SanitisedNonEmptyStr = Field(
        description="Conversation ID.",
    )


class MessageUpdateRequest(BaseModel):
    """Request to update a single message in a conversation."""

    conversation_id: str = Field(description="Unique ID of the conversation (table_id).")
    row_id: str = Field(description="The ID of the message (row) to update.")
    data: dict[str, Any] = Field(
        description="The new data for the message, e.g. `{'User': 'new content'}`.",
        min_length=1,
    )


class MessagesRegenRequest(BaseModel):
    """Request to regenerate the current message (and the rest of the messages) in a conversation."""

    conversation_id: str = Field(description="Unique ID of the conversation (table_id).")
    row_id: str = Field(description="Message IDs (rows) to regenerate.")
