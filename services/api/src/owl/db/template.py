from sqlmodel import Field as sql_Field
from sqlmodel import MetaData, Relationship, SQLModel

from owl.protocol import Name
from owl.utils import datetime_now_iso


class TemplateSQLModel(SQLModel):
    metadata = MetaData()


class TagTemplateLink(TemplateSQLModel, table=True):
    tag_id: str = sql_Field(
        primary_key=True,
        foreign_key="tag.id",
        description="Tag ID.",
    )
    template_id: str = sql_Field(
        primary_key=True,
        foreign_key="template.id",
        description="Template ID.",
    )


class Tag(TemplateSQLModel, table=True):
    id: str = sql_Field(
        primary_key=True,
        description="Tag ID.",
    )
    templates: list["Template"] = Relationship(back_populates="tags", link_model=TagTemplateLink)


class _TemplateBase(TemplateSQLModel):
    id: str = sql_Field(
        primary_key=True,
        description="Template ID.",
    )
    name: Name = sql_Field(
        description="Template name.",
    )
    created_at: str = sql_Field(
        default_factory=datetime_now_iso,
        description="Template creation datetime (ISO 8601 UTC).",
    )


class Template(_TemplateBase, table=True):
    tags: list[Tag] = Relationship(
        back_populates="templates",
        link_model=TagTemplateLink,
    )


class TemplateRead(_TemplateBase):
    tags: list[Tag]
