from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlmodel import JSON, Column, Relationship
from sqlmodel import Field as sql_Field
from typing_extensions import Self

from owl.configs.manager import ENV_CONFIG
from owl.db import UserSQLModel
from owl.protocol import ExternalKeys, Name
from owl.utils import datetime_now_iso
from owl.utils.crypt import decrypt, generate_key


class _ProjectBase(UserSQLModel):
    name: str = sql_Field(
        description="Project name.",
    )
    organization_id: str = sql_Field(
        default="default",
        foreign_key="organization.id",
        index=True,
        description="Organization ID.",
    )


class ProjectCreate(_ProjectBase):
    name: Name = sql_Field(
        description="Project name.",
    )


class ProjectUpdate(BaseModel):
    id: str
    """Project ID."""
    name: Name | None = sql_Field(
        default=None,
        description="Project name.",
    )
    updated_at: str = sql_Field(
        default_factory=datetime_now_iso,
        description="Project update datetime (ISO 8601 UTC).",
    )


class Project(_ProjectBase, table=True):
    id: str = sql_Field(
        primary_key=True,
        default_factory=lambda: generate_key(24, "proj_"),
        description="Project ID.",
    )
    created_at: str = sql_Field(
        default_factory=datetime_now_iso,
        description="Project creation datetime (ISO 8601 UTC).",
    )
    updated_at: str = sql_Field(
        default_factory=datetime_now_iso,
        description="Project update datetime (ISO 8601 UTC).",
    )
    organization: "Organization" = Relationship(back_populates="projects")
    """Organization that this project is associated with."""


class ProjectRead(_ProjectBase):
    id: str = sql_Field(
        description="Project ID.",
    )
    created_at: str = sql_Field(
        description="Project creation datetime (ISO 8601 UTC).",
    )
    updated_at: str = sql_Field(
        description="Project update datetime (ISO 8601 UTC).",
    )
    organization: "OrganizationRead" = sql_Field(
        description="Organization that this project is associated with.",
    )


class _OrganizationBase(UserSQLModel):
    id: str = sql_Field(
        default=ENV_CONFIG.default_org_id,
        primary_key=True,
        description="Organization ID.",
    )
    name: str = sql_Field(
        default="Personal",
        description="Organization name.",
    )
    external_keys: dict[str, str] = sql_Field(
        default={},
        sa_column=Column(JSON),
        description="Mapping of service provider to its API key.",
    )
    timezone: str | None = sql_Field(
        default=None,
        description="Timezone specifier.",
    )
    models: dict[str, Any] = sql_Field(
        default={},
        sa_column=Column(JSON),
        description="The organization's custom model list, in addition to the provided default list.",
    )

    @property
    def members(self) -> list:
        # OSS does not support user accounts
        return []


class OrganizationCreate(_OrganizationBase):
    name: str = sql_Field(
        default="Personal",
        description="Organization name.",
    )

    @model_validator(mode="after")
    def check_external_keys(self) -> Self:
        self.external_keys = ExternalKeys.model_validate(self.external_keys).model_dump()
        return self


class OrganizationRead(_OrganizationBase):
    created_at: str = sql_Field(
        description="Organization creation datetime (ISO 8601 UTC).",
    )
    updated_at: str = sql_Field(
        description="Organization update datetime (ISO 8601 UTC).",
    )
    projects: list[Project] | None = sql_Field(
        default=None,
        description="List of projects.",
    )

    def decrypt(self, key: str) -> Self:
        if self.external_keys is not None:
            self.external_keys = {k: decrypt(v, key) for k, v in self.external_keys.items()}
        return self


class Organization(_OrganizationBase, table=True):
    created_at: str = sql_Field(
        default_factory=datetime_now_iso,
        description="Organization creation datetime (ISO 8601 UTC).",
    )
    updated_at: str = sql_Field(
        default_factory=datetime_now_iso,
        description="Organization update datetime (ISO 8601 UTC).",
    )
    projects: list[Project] = Relationship(back_populates="organization")
    """List of projects."""


class OrganizationUpdate(BaseModel):
    id: str
    """Organization ID."""
    name: str | None = None
    """Organization name."""
    external_keys: dict[str, str] | None = Field(
        default=None,
        description="Mapping of service provider to its API key.",
    )
    timezone: str | None = Field(default=None)
    """
    Timezone specifier.
    """

    @model_validator(mode="after")
    def check_external_keys(self) -> Self:
        if self.external_keys is not None:
            self.external_keys = ExternalKeys.model_validate(self.external_keys).model_dump()
        return self
