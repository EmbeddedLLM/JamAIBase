from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any, Self, Type, TypeVar

from pydantic import BaseModel, computed_field
from pydantic_extra_types.currency_code import ISO4217
from pydantic_extra_types.timezone_name import TimeZoneName
from sqlalchemy.orm import declared_attr, selectinload
from sqlalchemy.sql.base import ExecutableOption
from sqlmodel import (
    VARCHAR,
    AutoString,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    Relationship,
    SQLModel,
    String,
    Unicode,
    and_,
    asc,
    desc,
    exists,
    func,
    literal,
    nulls_first,
    nulls_last,
    or_,
    select,
    text,
    tuple_,
)
from sqlmodel import Field as SqlField
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql._expression_select_cls import SelectBase
from sqlmodel.sql.expression import SelectOfScalar

from owl.configs import ENV_CONFIG
from owl.types import (
    DEFAULT_MUL_LANGUAGES,
    CloudProvider,
    DatetimeUTC,
    LanguageCodeList,
    ModelCapability,
    ModelType,
    Page,
    PaymentState,
    PositiveNonZeroInt,
    Role,
    SanitisedNonEmptyStr,
    SanitisedStr,
    SecretRead,
)
from owl.utils import uuid7_str
from owl.utils.crypt import decrypt, generate_key
from owl.utils.dates import now
from owl.utils.exceptions import (
    BadInputError,
    InsufficientCreditsError,
    NoTierError,
    ResourceNotFoundError,
)
from owl.utils.io import json_dumps, json_loads
from owl.utils.types import JSON

TEMPLATE_ORG_ID = "template"
BASE_PLAN_ID = "base"


def _encode_cursor(values: dict[str, Any]) -> str:
    return urlsafe_b64encode(json_dumps(values).encode()).decode()


def _decode_cursor(token: str) -> dict[str, Any]:
    raw = json_loads(urlsafe_b64decode(token.encode()).decode())
    if "created_at" in raw and isinstance(raw["created_at"], str):
        raw["created_at"] = datetime.fromisoformat(raw["created_at"])
    elif "updated_at" in raw and isinstance(raw["updated_at"], str):
        raw["updated_at"] = datetime.fromisoformat(raw["updated_at"])
    return raw


def _relationship(
    back_populates: str | None = None,
    link_model: Any | None = None,
    *,
    selectin: bool = True,
    cascade: str | None = "all, delete-orphan",
    sa_kwargs: dict[str, Any] | None = None,
):
    sa_relationship_kwargs = dict(viewonly=True)
    if isinstance(sa_kwargs, dict):
        sa_relationship_kwargs.update(sa_kwargs)
    if selectin:
        sa_relationship_kwargs["lazy"] = "selectin"
    if cascade:
        sa_relationship_kwargs["cascade"] = cascade
    return Relationship(
        back_populates=back_populates,
        link_model=link_model,
        sa_relationship_kwargs=sa_relationship_kwargs,
    )


class JamaiSQLModel(SQLModel):
    metadata = MetaData(schema="jamai")

    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__


ItemType = TypeVar("ItemType", bound=BaseModel)


class _TableBase(JamaiSQLModel, str_strip_whitespace=True):
    meta: dict[str, Any] = SqlField(
        {},
        sa_type=JSON,
        description="Metadata.",
    )
    created_at: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Creation datetime (UTC).",
    )
    updated_at: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Update datetime (UTC).",
    )

    @classmethod
    @lru_cache(maxsize=1)
    def pk(cls) -> list[str]:
        """Return every column name that is a primary key."""
        return [c.name for c in cls.__table__.primary_key]

    @classmethod
    @lru_cache(maxsize=1)
    def str_cols(cls) -> list[str]:
        """Return every column name that is a string."""
        return [
            c.name
            for c in cls.__table__.columns
            if isinstance(c.type, (AutoString, VARCHAR, Unicode, String))
        ]

    @classmethod
    @lru_cache(maxsize=1)
    def nullable_cols(cls) -> list[str]:
        """Return every column name that is nullable."""
        return [c.name for c in cls.__table__.columns if c.nullable]

    @classmethod
    @lru_cache(maxsize=1)
    def indexed_cols(cls) -> list[str]:
        """
        Return every column name that participates in any declared index.

        Even though for Postgres, unique constraint creates an index automatically,
        we still only list columns that explicitly declare an index.
        https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#postgresql-index-reflection
        """
        tbl = cls.__table__
        # flagged = {c.name for c in tbl.columns if c.index or c.unique or c.primary_key}
        cols = {c.name for idx in tbl.indexes for c in idx.columns}
        return [c.name for c in tbl.columns if c.name in cols]

    @classmethod
    def _where_filter(
        cls,
        selection: SelectBase,
        filters: dict[str, Any | list[Any]] | None,
    ) -> SelectBase:
        if filters:
            selection = selection.where(
                and_(
                    *[
                        or_(*[getattr(cls, k) == vv for vv in v])
                        if isinstance(v, list)
                        else getattr(cls, k) == v
                        for k, v in filters.items()
                    ]
                )
            )
        return selection

    @classmethod
    def _search_query_filter(
        cls,
        selection: SelectBase,
        *,
        search_query: str | None,
        search_columns: list[str] | None,
    ) -> SelectBase:
        # Apply search filters
        if search_query:
            if not search_columns:
                search_columns = cls.str_cols()
            search_conditions = []
            for column_name in search_columns:
                if (column := getattr(cls, column_name, None)) is not None:
                    # Using case-insensitive regex match (~*)
                    search_conditions.append(column.op("~*")(search_query))
            if search_conditions:
                selection = selection.where(or_(*search_conditions))
        return selection

    @classmethod
    def _allow_block_list_filter(
        cls,
        selection: SelectBase,
        filter_id: str,
        *,
        allow_list_attr: str = "allowed_orgs",
        block_list_attr: str = "blocked_orgs",
    ) -> SelectBase:
        allow_list = getattr(cls, allow_list_attr)
        block_list = getattr(cls, block_list_attr, None)
        # Allow list
        allow = or_(allow_list == [], allow_list.contains([filter_id]))
        if block_list is None:
            # No block list, just allow list
            selection = selection.where(allow)
        else:
            # Block list
            selection = selection.where(and_(allow, ~block_list.contains([filter_id])))
        return selection

    @classmethod
    def _pagination(
        cls,
        selection: SelectBase,
        *,
        offset: int,
        limit: int | None,
        order_by: str,
        order_ascending: bool,
        after: str | None = None,
    ) -> SelectBase:
        # Apply ordering
        order_col = getattr(cls, order_by, None)
        if order_col is None:
            raise BadInputError(f'Unable to order by column "{order_by}" as it does not exist.')
        is_nullable = order_col.nullable
        # Postgres index sorts nulls last (nulls are larger than non-null)
        # But it is hard to get a string null coalesce value, so we sort null first
        null_order_func = nulls_first if order_ascending else nulls_last
        # Keyset pagination
        # cursor = before or after
        cursor = after
        if cursor:
            # if before:
            #     op = "__lt__" if order_ascending else "__gt__"
            # else:
            #     op = "__gt__" if order_ascending else "__lt__"
            op = "__gt__" if order_ascending else "__lt__"
            try:
                vals = _decode_cursor(cursor)
            except Exception as e:
                raise BadInputError(f'Pagination failed due to invalid cursor: "{cursor}"') from e
            try:
                pk_cols = tuple(getattr(cls, pk) for pk in cls.pk())
                pk_vals = tuple(vals[pk] for pk in cls.pk())
                cmp_val = vals[order_by]
            except KeyError as e:
                raise BadInputError(
                    f'Unable to order by column "{order_by}" as it is not found in the cursor.'
                ) from e
            if is_nullable:
                # This is mainly for JamaiBase rather than TokenVisor
                if isinstance(order_col.type, Integer):
                    coalesce_val = literal(-(2**31 - 1))  # Standard 32-bit signed integer
                elif isinstance(order_col.type, Numeric):
                    coalesce_val = literal(float("-inf"))
                elif isinstance(order_col.type, Boolean):
                    coalesce_val = False
                else:
                    coalesce_val = ""
                # else:
                #     raise BadInputError(
                #         f'Unable to order by nullable column "{order_by}" of type {order_col.type}.'
                #     )
                if cmp_val is None:
                    cmp_val = coalesce_val
                order_by_expr = func.coalesce(order_col, coalesce_val)
            else:
                order_by_expr = order_col
            filter_cond = or_(
                getattr(order_by_expr, op)(cmp_val),
                and_(order_by_expr == cmp_val, getattr(tuple_(*pk_cols), op)(pk_vals)),
            )
            selection = selection.where(filter_cond)
        else:
            selection = selection.offset(offset)
        # Postgres ordering on Linux seems to be case-insensitive by default
        # https://dba.stackexchange.com/a/131471
        # Apply LOWER() on text columns
        if order_by in cls.str_cols():
            order_col = func.lower(order_col)
        # Determine order function based on sort direction
        order_func = asc if order_ascending else desc
        # Pagination
        if is_nullable:
            order_by_expr = null_order_func(order_func(order_col))
        else:
            order_by_expr = order_func(order_col)
        selection = selection.order_by(
            order_by_expr, *(order_func(getattr(cls, pk)) for pk in cls.pk())
        )
        if limit is not None:
            selection = selection.limit(limit)
        return selection

    def _generate_cursor(self, order_by: str) -> str:
        cursor_keys = [order_by, *self.pk()]
        cursor_values = {k: getattr(self, k) for k in cursor_keys}
        return _encode_cursor(cursor_values)

    @classmethod
    def _list(
        cls,
        *,
        offset: int,
        limit: int | None,
        order_by: str,
        order_ascending: bool,
        search_query: str | None,
        search_columns: list[str] | None,
        filters: dict[str, Any | list[Any]] | None = None,
        options: list[ExecutableOption] | None = None,
        after: str | None = None,
    ) -> tuple[SelectOfScalar[Self], SelectOfScalar[int]]:
        ### --- Main query --- ###
        items = cls._search_query_filter(
            cls._where_filter(select(cls), filters),
            search_query=search_query,
            search_columns=search_columns,
        )
        if options:
            items = items.options(*options)
        items = cls._pagination(
            items,
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_ascending=order_ascending,
            after=after,
        )
        ### --- Count --- ###
        # Same filters but without pagination
        total = cls._search_query_filter(
            cls._where_filter(select(func.count(getattr(cls, cls.pk()[0]))), filters),
            search_query=search_query,
            search_columns=search_columns,
        )
        return items, total

    @classmethod
    async def _fetch_list_and_cursor(
        cls,
        session: AsyncSession,
        items: SelectOfScalar[Self],
        total: SelectOfScalar[int],
        order_by: str,
    ) -> tuple[list[Self], int, str | None]:
        items: list[Self] = (await session.exec(items)).all()
        total: int = (await session.exec(total)).one()
        if items:
            end_cursor = items[-1]._generate_cursor(order_by)
        else:
            end_cursor = None
        return items, total, end_cursor

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        body: dict[str, Any] | BaseModel,
    ) -> Self:
        item = cls.model_validate(body)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    @classmethod
    async def list_(
        cls,
        session: AsyncSession,
        return_type: Type[ItemType],
        *,
        offset: int = 0,
        limit: int | None = None,
        order_by: str | None = None,
        order_ascending: bool = True,
        search_query: str | None = None,
        search_columns: list[str] | None = None,
        filters: dict[str, Any | list[Any]] | None = None,
        options: list[ExecutableOption] | None = None,
        after: str | None = None,
    ) -> Page[ItemType]:
        if order_by is None:
            order_by = cls.pk()[0]
        items, total = cls._list(
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_ascending=order_ascending,
            search_query=search_query,
            search_columns=search_columns,
            filters=filters,
            options=options,
            after=after,
        )
        items, total, end_cursor = await cls._fetch_list_and_cursor(
            session=session,
            items=items,
            total=total,
            order_by=order_by,
        )
        return Page[return_type](
            items=items,
            offset=offset,
            limit=total if limit is None else limit,
            total=total,
            end_cursor=end_cursor,
        )

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        item_id: str,
        *,
        name: str = "",
        **kwargs,
    ) -> Self:
        item = await session.get(cls, item_id, **kwargs)
        if item is None:
            raise ResourceNotFoundError(
                f'{name if name else cls.__name__} "{item_id}" is not found.'
            )
        return item

    @classmethod
    async def _update(
        cls,
        session: AsyncSession,
        item_id: str,
        updates: dict[str, Any],
        *,
        name: str = "",
    ) -> Self:
        item = await cls.get(session, item_id, name=name)
        for key, value in updates.items():
            setattr(item, key, value)
        item.updated_at = now()
        session.add(item)
        return item

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        item_id: str,
        body: BaseModel,
        *,
        name: str = "",
    ) -> tuple[Self, dict[str, Any]]:
        updates = body.model_dump(exclude_unset=True)
        item = await cls._update(session, item_id, updates, name=name)
        await session.commit()
        await session.refresh(item)
        return item, updates

    @classmethod
    async def delete(
        cls,
        session: AsyncSession,
        item_id: str,
        *,
        name: str = "",
    ) -> None:
        item = await cls.get(session, item_id, name=name)
        await session.delete(item)
        await session.commit()


class PricePlan(_TableBase, table=True):
    id: SanitisedNonEmptyStr = SqlField(
        default_factory=lambda: generate_key(8, "plan_"),
        primary_key=True,
        description="Price plan ID.",
    )
    name: str = SqlField(
        unique=True,
        description="Price plan name. Must be unique.",
    )
    stripe_price_id_live: str = SqlField(
        index=True,
        unique=True,
        description="Stripe price ID (live mode). Must be unique.",
    )
    stripe_price_id_test: str = SqlField(
        index=True,
        unique=True,
        description="Stripe price ID (test mode). Must be unique.",
    )
    flat_cost: float = SqlField(
        description="Base price for the entire tier (in USD decimal terms).",
    )
    credit_grant: float = SqlField(
        description="Credit amount included (in USD decimal terms).",
    )
    max_users: int | None = SqlField(
        description="Maximum number of users per organization. `None` means no limit.",
    )
    products: dict[str, Any] = SqlField(
        sa_type=JSON,
        description="Mapping of product ID to product.",
    )
    allowed_orgs: list[str] = SqlField(
        [],
        index=True,
        sa_type=JSON,
        description=(
            "List of IDs of organizations allowed to use this price plan. "
            "If empty, all orgs are allowed."
        ),
    )
    organizations: "Organization" = _relationship("price_plan", selectin=False)

    @computed_field(description="Stripe Price ID.")
    @property
    def stripe_price_id(self) -> str:
        return (
            self.stripe_price_id_live
            if ENV_CONFIG.stripe_api_key_plain.startswith("sk_live")
            else self.stripe_price_id_test
        )

    @computed_field(
        description="Whether this is a private price plan visible only to select organizations."
    )
    @property
    def is_private(self) -> bool:
        return len(self.allowed_orgs) > 0

    @classmethod
    async def list_public(
        cls,
        session: AsyncSession,
        return_type: Type[ItemType],
        *,
        offset: int,
        limit: int | None,
        order_by: str,
        order_ascending: bool,
        search_query: str | None,
        search_columns: list[str] | None,
        filters: dict[str, Any | list[Any]] | None = None,
        after: str | None = None,
    ) -> Page[ItemType]:
        # List
        items, total = cls._list(
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_ascending=order_ascending,
            search_query=search_query,
            search_columns=search_columns,
            filters=filters,
            after=after,
        )
        # Filter
        items = items.where(cls.allowed_orgs == [])
        total = total.where(cls.allowed_orgs == [])
        items, total, end_cursor = await cls._fetch_list_and_cursor(
            session=session,
            items=items,
            total=total,
            order_by=order_by,
        )
        return Page[return_type](
            items=items,
            offset=offset,
            limit=total if limit is None else limit,
            total=total,
            end_cursor=end_cursor,
        )

    @classmethod
    async def list_(
        cls,
        session: AsyncSession,
        return_type: Type[ItemType],
        *,
        offset: int = 0,
        limit: int | None = None,
        order_by: str | None = None,
        order_ascending: bool = True,
        search_query: str | None = None,
        search_columns: list[str] | None = None,
        filters: dict[str, Any | list[Any]] | None = None,
        after: str | None = None,
    ) -> Page[ItemType]:
        if order_by is None:
            order_by = cls.pk()[0]
        items, total = cls._list(
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_ascending=order_ascending,
            search_query=search_query,
            search_columns=search_columns,
            filters=filters,
            after=after,
        )
        items, total, end_cursor = await cls._fetch_list_and_cursor(
            session=session,
            items=items,
            total=total,
            order_by=order_by,
        )
        return Page[return_type](
            items=items,
            offset=offset,
            limit=total if limit is None else limit,
            total=total,
            end_cursor=end_cursor,
        )


class Deployment(_TableBase, table=True):
    id: SanitisedNonEmptyStr = SqlField(
        default_factory=uuid7_str,
        primary_key=True,
        description="Deployment ID.",
    )
    model_id: str = SqlField(
        sa_column_args=[ForeignKey("ModelConfig.id", ondelete="CASCADE", onupdate="CASCADE")],
        index=True,
        description="Model ID.",
    )
    name: str = SqlField(
        description="Name for the deployment.",
    )
    routing_id: str = SqlField(
        "",
        description=(
            "Model ID that the inference provider expects (whereas `model_id` is what the users will see). "
            "OpenAI example: `model_id` CAN be `openai/gpt-5` but `routing_id` SHOULD be `gpt-5`."
        ),
    )
    api_base: str = SqlField(
        "",
        description=(
            "(Optional) Hosting url. "
            "Required for creating external cloud deployment using custom providers. "
            "Example: `http://vllm-endpoint.xyz/v1`."
        ),
    )
    provider: str = SqlField(
        "",
        description=(
            f"Inference provider of the model. "
            f"Standard cloud providers are {CloudProvider.list_()}."
        ),
    )
    weight: int = SqlField(
        1,
        ge=0,
        description="Routing weight. Must be >= 0. A deployment is selected according to its relative weight.",
    )
    cooldown_until: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Cooldown until datetime (UTC).",
    )
    model: "ModelConfig" = _relationship("deployments")


class ModelInfo(_TableBase):
    id: str = SqlField(
        primary_key=True,
        description=(
            "Unique identifier. "
            "Users will specify this to select a model. "
            "Must follow the following format: `{provider}/{model_id}`. "
            "Examples=['openai/gpt-4o-mini', 'Qwen/Qwen2.5-0.5B']"
        ),
    )
    type: ModelType = SqlField(
        ModelType.LLM,
        description="Model type. Can be completion, llm, embed, or rerank.",
    )
    name: str = SqlField(
        "",
        description="Model name that is more user friendly.",
    )
    owned_by: str = SqlField(
        "",
        description="Model provider (usually organization that trained the model).",
    )
    capabilities: list[ModelCapability] = SqlField(
        [ModelCapability.CHAT],
        sa_type=JSON,
        description="List of capabilities of model.",
    )
    context_length: int = SqlField(
        4096,
        description="Context length of model.",
    )
    languages: LanguageCodeList = SqlField(
        ["en"],
        sa_type=JSON,
        description=f'List of languages which the model is well-versed in. "*" and "mul" resolves to {DEFAULT_MUL_LANGUAGES}.',
    )
    max_output_tokens: int | None = SqlField(
        None,
        description="Maximum number of output tokens, if not specified, will be based on context length.",
        # examples=[8192],
    )


class ModelConfig(ModelInfo, table=True):
    # --- All models --- #
    type: ModelType = SqlField(
        description="Model type. Can be completion, chat, embed, or rerank.",
    )
    name: str = SqlField(
        description="Model name that is more user friendly.",
    )
    context_length: int = SqlField(
        description="Context length of model. Examples=[4096]",
    )
    capabilities: list[ModelCapability] = SqlField(
        sa_type=JSON,
        description="List of capabilities of model.",
    )
    owned_by: str = SqlField(
        "",
        description="Model provider (usually organization that trained the model).",
    )
    timeout: float = SqlField(
        15 * 60,
        gt=0,
        nullable=False,
        description="Timeout in seconds. Must be greater than 0. Defaults to 15 minutes.",
    )
    priority: int = SqlField(
        0,
        description="Priority for fallback model selection. The larger the number, the higher the priority.",
    )
    allowed_orgs: list[str] = SqlField(
        [],
        index=True,
        sa_type=JSON,
        description=(
            "List of IDs of organizations allowed to use this model. "
            "If empty, all orgs are allowed. Allow list is applied first, followed by block list."
        ),
    )
    blocked_orgs: list[str] = SqlField(
        [],
        index=True,
        sa_type=JSON,
        description=(
            "List of IDs of organizations NOT allowed to use this model. "
            "If empty, no org is blocked. Allow list is applied first, followed by block list."
        ),
    )
    # --- Chat models --- #
    llm_input_cost_per_mtoken: float = SqlField(
        -1.0,
        description=(
            "Cost in USD per million (mega) input / prompt token. "
            "Can be zero. Negative values will be overridden with a default value."
        ),
    )
    llm_output_cost_per_mtoken: float = SqlField(
        -1.0,
        description=(
            "Cost in USD per million (mega) output / completion token. "
            "Can be zero. Negative values will be overridden with a default value."
        ),
    )
    # --- Embedding models --- #
    embedding_size: PositiveNonZeroInt | None = SqlField(
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
    embedding_dimensions: PositiveNonZeroInt | None = SqlField(
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
    embedding_transform_query: str | None = SqlField(
        None,
        description="Transform query that might be needed, esp. for hf models",
    )
    embedding_cost_per_mtoken: float = SqlField(
        -1.0,
        description=(
            "Cost in USD per million (mega) embedding tokens. "
            "Can be zero. Negative values will be overridden with a default value."
        ),
    )
    # --- Reranking models --- #
    reranking_cost_per_ksearch: float = SqlField(
        -1.0,
        description=(
            "Cost in USD per thousand (kilo) searches. "
            "Can be zero. Negative values will be overridden with a default value."
        ),
    )
    deployments: list[Deployment] = _relationship("model")

    @computed_field(
        description="Whether this is a private model visible only to select organizations."
    )
    @property
    def is_private(self) -> bool:
        return len(self.allowed_orgs) > 0 or len(self.blocked_orgs) > 0

    @computed_field(description="Whether this model is active and ready for inference.")
    @property
    def is_active(self) -> bool:
        return len(self.deployments) > 0

    @classmethod
    async def list_(
        cls,
        session: AsyncSession,
        return_type: Type[ItemType],
        *,
        organization_id: str | None,
        offset: int = 0,
        limit: int | None = None,
        order_by: str | None = None,
        order_ascending: bool = True,
        search_query: str | None = None,
        search_columns: list[str] | None = None,
        filters: dict[str, Any | list[Any]] | None = None,
        after: str | None = None,
        capabilities: list[ModelCapability] | None = None,
        exclude_inactive: bool = False,
    ) -> Page[ItemType]:
        if order_by is None:
            order_by = cls.pk()[0]
        items, total = cls._list(
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_ascending=order_ascending,
            search_query=search_query,
            search_columns=search_columns,
            filters=filters,
            after=after,
        )
        # Filter
        if organization_id:
            items = cls._allow_block_list_filter(items, organization_id)
            total = cls._allow_block_list_filter(total, organization_id)
        # Filter by capability
        if capabilities is not None:
            items = items.where(cls.capabilities.contains(capabilities))
            total = total.where(cls.capabilities.contains(capabilities))
        if exclude_inactive:
            subquery = select(Deployment).where(Deployment.model_id == cls.id)
            items = items.where(exists(subquery))
            total = total.where(exists(subquery))
        items, total, end_cursor = await cls._fetch_list_and_cursor(
            session=session,
            items=items,
            total=total,
            order_by=order_by,
        )
        return Page[return_type](
            items=items,
            offset=offset,
            limit=total if limit is None else limit,
            total=total,
            end_cursor=end_cursor,
        )


class OrgMember(_TableBase, table=True):
    user_id: str = SqlField(
        foreign_key="User.id",
        primary_key=True,
        ondelete="CASCADE",
        description="User ID.",
    )
    organization_id: str = SqlField(
        foreign_key="Organization.id",
        primary_key=True,
        ondelete="CASCADE",
        description="Organization ID.",
    )
    role: Role = SqlField(
        Role.GUEST,
        description="Organization role.",
    )
    user: "User" = _relationship("org_memberships")
    organization: "Organization" = _relationship("members")


class ProjectMember(_TableBase, table=True):
    user_id: str = SqlField(
        foreign_key="User.id",
        primary_key=True,
        ondelete="CASCADE",
        description="User ID.",
    )
    project_id: str = SqlField(
        foreign_key="Project.id",
        primary_key=True,
        ondelete="CASCADE",
        description="Project ID.",
    )
    role: Role = SqlField(
        Role.GUEST,
        description="Project role.",
    )
    user: "User" = _relationship("proj_memberships")
    project: "Project" = _relationship("members")


class User(_TableBase, table=True):
    id: str = SqlField(
        default_factory=uuid7_str,
        primary_key=True,
        description="User ID.",
    )
    name: str = SqlField(
        index=True,
        description="User's preferred name.",
    )
    email: str = SqlField(
        unique=True,
        index=True,
        description="User's email.",
    )
    email_verified: bool = SqlField(
        False,
        description="Whether the email address is verified.",
    )
    password_hash: str | None = SqlField(
        None,
        index=True,
        description="Password hash.",
    )
    picture_url: str | None = SqlField(
        None,
        description="User picture URL.",
    )
    refresh_counter: int = SqlField(
        0,
        description="Counter used as refresh token version for invalidation.",
    )
    google_id: str | None = SqlField(
        None,
        index=True,
        description="Google user ID.",
    )
    google_name: str | None = SqlField(
        None,
        description="Google user's preferred name.",
    )
    google_username: str | None = SqlField(
        None,
        description="Google username.",
    )
    google_email: str | None = SqlField(
        None,
        description="Google email.",
    )
    google_picture_url: str | None = SqlField(
        None,
        description="Google user picture URL.",
    )
    google_updated_at: DatetimeUTC | None = SqlField(
        None,
        sa_type=DateTime(timezone=True),
        description="Google user info update datetime (UTC).",
    )
    github_id: str | None = SqlField(
        None,
        index=True,
        description="GitHub user ID.",
    )
    github_name: str | None = SqlField(
        None,
        description="GitHub user's preferred name.",
    )
    github_username: str | None = SqlField(
        None,
        description="GitHub username.",
    )
    github_email: str | None = SqlField(
        None,
        description="GitHub email.",
    )
    github_picture_url: str | None = SqlField(
        None,
        description="GitHub user picture URL.",
    )
    github_updated_at: DatetimeUTC | None = SqlField(
        None,
        sa_type=DateTime(timezone=True),
        description="GitHub user info update datetime (UTC).",
    )
    org_memberships: list[OrgMember] = _relationship("user")
    proj_memberships: list[ProjectMember] = _relationship("user")
    organizations: list["Organization"] = _relationship(None, link_model=OrgMember, selectin=False)
    projects: list["Project"] = _relationship(None, link_model=ProjectMember, selectin=False)
    # keys: list["ProjectKey"] = _relationship("user")

    @computed_field(description="Name for display.")
    @property
    def preferred_name(self) -> str:
        return self.name or self.google_name or self.github_name

    @computed_field(description="Email for display.")
    @property
    def preferred_email(self) -> str:
        return self.email or self.google_email or self.github_email

    @computed_field(description="Picture URL for display.")
    @property
    def preferred_picture_url(self) -> str | None:
        return self.picture_url or self.google_picture_url or self.github_picture_url

    @computed_field(description="Username for display.")
    @property
    def preferred_username(self) -> str | None:
        return self.google_username or self.github_username

    @classmethod
    async def list_(
        cls,
        session: AsyncSession,
        return_type: Type[ItemType],
        *,
        offset: int = 0,
        limit: int | None = None,
        order_by: str | None = None,
        order_ascending: bool = True,
        search_query: str | None = None,
        search_columns: list[str] | None = None,
        filters: dict[str, Any | list[Any]] | None = None,
        after: str | None = None,
    ) -> Page[ItemType]:
        return await super().list_(
            session=session,
            return_type=return_type,
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_ascending=order_ascending,
            search_query=search_query,
            search_columns=search_columns,
            filters=filters,
            options=[selectinload(cls.organizations), selectinload(cls.projects)],
            after=after,
        )

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        item_id: str,
        *,
        name: str = "",
        **kwargs,
    ) -> Self:
        where_expr = cls.id == item_id
        if item_id.startswith("google-oauth2|"):
            where_expr = or_(where_expr, cls.google_id == item_id.split("|")[1])
        elif item_id.startswith("github|"):
            where_expr = or_(where_expr, cls.github_id == item_id.split("|")[1])
        item = (
            await session.exec(
                select(User)
                .where(where_expr)
                .options(selectinload(cls.organizations), selectinload(cls.projects)),
                execution_options=kwargs,
            )
        ).one_or_none()
        if item is None:
            raise ResourceNotFoundError(
                f'{name if name else cls.__name__} "{item_id}" is not found.'
            )
        return item


class Organization(_TableBase, table=True):
    id: SanitisedNonEmptyStr = SqlField(
        default_factory=lambda: generate_key(24, "org_"),
        primary_key=True,
        description="Organization ID.",
    )
    name: SanitisedStr = SqlField(
        description="Organization name.",
    )
    currency: ISO4217 = SqlField(
        "USD",
        description="Currency of the organization.",
    )
    timezone: TimeZoneName | None = SqlField(
        None,
        description="Timezone specifier.",
    )
    external_keys: dict[str, str] = SqlField(
        {},
        sa_type=JSON,
        description="Mapping of external service provider to its API key.",
    )
    stripe_id: str | None = SqlField(
        None,
        index=True,
        description="Stripe Customer ID.",
    )
    # stripe_subscription_id: SanitisedIdStr | None = SqlField(
    #     None,
    #     description="Stripe Subscription ID.",
    # )
    price_plan_id: str | None = SqlField(
        None,
        foreign_key="PricePlan.id",
        index=True,
        nullable=True,
        description="Subscribed plan ID.",
    )
    payment_state: PaymentState = SqlField(
        PaymentState.NONE,
        description=f"Payment state of the organization, one of {list(map(str, PaymentState))}.",
    )
    last_subscription_payment_at: DatetimeUTC | None = SqlField(
        None,
        sa_type=DateTime(timezone=True),
        description="Datetime of the last successful subscription payment (UTC).",
    )
    quota_reset_at: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Quota reset datetime (UTC).",
    )
    credit: float = SqlField(
        0.0,
        sa_type=Numeric(21, 12),
        description=(
            "Credit paid by the customer. "
            "Unused credit will be carried forward to the next billing cycle. "
            "Must be in the range [-999_999_999.0, 999_999_999.0] with up to 12 decimal places."
        ),
    )
    credit_grant: float = SqlField(
        0.0,
        sa_type=Numeric(21, 12),
        description=(
            "Credit granted to the customer. "
            "Unused credit will NOT be carried forward. "
            "Must be in the range [-999_999_999.0, 999_999_999.0] with up to 12 decimal places."
        ),
    )
    llm_tokens_quota_mtok: float | None = SqlField(
        0.0,
        description="LLM token quota in millions of tokens.",
    )
    llm_tokens_usage_mtok: float = SqlField(
        0.0,
        description="LLM token usage in millions of tokens.",
    )
    llm_tokens_usage_updated_at: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Datetime of the last successful LLM token usage update (UTC).",
    )
    embedding_tokens_quota_mtok: float | None = SqlField(
        0.0,
        description="Embedding token quota in millions of tokens.",
    )
    embedding_tokens_usage_mtok: float = SqlField(
        0.0,
        description="Embedding token quota in millions of tokens.",
    )
    embedding_tokens_usage_updated_at: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Datetime of the last successful Embedding token usage update (UTC).",
    )
    reranker_quota_ksearch: float | None = SqlField(
        0.0,
        description="Reranker quota for every thousand searches.",
    )
    reranker_usage_ksearch: float = SqlField(
        0.0,
        description="Reranker usage for every thousand searches.",
    )
    reranker_usage_updated_at: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Datetime of the last successful Reranker usage update (UTC).",
    )
    db_quota_gib: float | None = SqlField(
        0.0,
        description="DB storage quota in GiB.",
    )
    db_usage_gib: float = SqlField(
        0.0,
        description="DB storage usage in GiB.",
    )
    db_usage_updated_at: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Datetime of the last successful DB usage update (UTC).",
    )
    file_quota_gib: float | None = SqlField(
        0.0,
        description="File storage quota in GiB.",
    )
    file_usage_gib: float = SqlField(
        0.0,
        description="File storage usage in GiB.",
    )
    file_usage_updated_at: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Datetime of the last successful File usage update (UTC).",
    )
    egress_quota_gib: float | None = SqlField(
        0.0,
        description="Egress quota in GiB.",
    )
    egress_usage_gib: float = SqlField(
        0.0,
        description="Egress usage in GiB.",
    )
    egress_usage_updated_at: DatetimeUTC = SqlField(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        description="Datetime of the last successful egress usage update (UTC).",
    )
    created_by: str = SqlField(
        description="ID of the user that created this organization.",
    )
    owner: str = SqlField(
        description="ID of the user that owns this organization.",
    )
    users: list[User] = _relationship("organizations", link_model=OrgMember, selectin=False)
    members: list[OrgMember] = _relationship("organization", selectin=False)
    projects: list["Project"] = _relationship("organization", selectin=False)
    secrets: list["Secret"] = _relationship("organization", selectin=False)
    price_plan: PricePlan | None = _relationship("organizations")

    @staticmethod
    def status_check(org: "Organization", *, raise_error: bool = False) -> bool:
        """Whether the organization's quota is active (paid)."""
        if ENV_CONFIG.is_oss or ENV_CONFIG.disable_billing:
            return True
        if org.id in ("0", TEMPLATE_ORG_ID):
            return True
        if org.price_plan_id is None:
            if raise_error:
                raise NoTierError
            else:
                return False
        if org.last_subscription_payment_at is None:
            payment_on_time = False
        else:
            payment_on_time = (
                now() - org.last_subscription_payment_at
            ).days <= ENV_CONFIG.payment_lapse_max_days
        payment_ok = (
            org.payment_state in [PaymentState.SUCCESS, PaymentState.PROCESSING] or payment_on_time
        )
        if payment_ok or (float(org.credit) + float(org.credit_grant)) > 0:
            return True
        elif raise_error:
            raise InsufficientCreditsError
        else:
            return False

    @computed_field(description="Whether the organization's quota is active (paid).")
    @property
    def active(self) -> bool:
        return self.status_check(self, raise_error=False)

    @computed_field(description="Quota snapshot.")
    @property
    def quotas(self) -> dict[str, dict[str, float | None]]:
        return {
            "llm_tokens": {
                "quota": self.llm_tokens_quota_mtok,
                "usage": self.llm_tokens_usage_mtok,
            },
            "embedding_tokens": {
                "quota": self.embedding_tokens_quota_mtok,
                "usage": self.embedding_tokens_usage_mtok,
            },
            "reranker_searches": {
                "quota": self.reranker_quota_ksearch,
                "usage": self.reranker_usage_ksearch,
            },
            "db_storage": {
                "quota": self.db_quota_gib,
                "usage": self.db_usage_gib,
            },
            "file_storage": {
                "quota": self.file_quota_gib,
                "usage": self.file_usage_gib,
            },
            "egress": {
                "quota": self.egress_quota_gib,
                "usage": self.egress_usage_gib,
            },
        }

    @classmethod
    async def list_base_tier_orgs(
        cls,
        session: AsyncSession,
        user_id: str,
    ) -> list[Self]:
        return (
            await session.exec(
                select(cls).where(
                    cls.id != "0",  # Internal org "0" is not counted against the limit
                    cls.price_plan_id == BASE_PLAN_ID,
                    exists(
                        select(OrgMember).where(
                            OrgMember.user_id == user_id,
                            OrgMember.organization_id == cls.id,
                        )
                    ),
                )
            )
        ).all()

    async def add_credit_grant(
        self,
        session: AsyncSession,
        amount: float | Decimal,
    ) -> None:
        await session.exec(
            text(
                f"""
            SELECT id FROM {JamaiSQLModel.metadata.schema}.add_credit_grant(
                '{self.id}'::TEXT,
                {amount:.12f}::NUMERIC(21, 12)
            );
            """
            )
        )


class Project(_TableBase, table=True):
    id: str = SqlField(
        default_factory=lambda: generate_key(24, "proj_"),
        primary_key=True,
        description="Project ID.",
    )
    organization_id: str = SqlField(
        foreign_key="Organization.id",
        index=True,
        description="Organization ID.",
        ondelete="CASCADE",
    )
    name: str = SqlField(
        description="Project name.",
    )
    description: str = SqlField(
        description="Project description.",
    )
    tags: list[str] = SqlField(
        [],
        sa_type=JSON,
        description="Project tags.",
    )
    profile_picture_url: str | None = SqlField(
        None,
        description="URL of the profile picture.",
    )
    cover_picture_url: str | None = SqlField(
        None,
        description="URL of the cover picture.",
    )
    created_by: str = SqlField(
        description="ID of the user that created this project.",
    )
    quotas: dict[str, Any] = SqlField(
        {},
        sa_type=JSON,
        description="Quotas allotted to this project.",
    )
    owner: str = SqlField(
        foreign_key="User.id",
        description="ID of the user that owns this organization.",
    )
    organization: Organization = _relationship("projects")
    users: list[User] = _relationship("projects", link_model=ProjectMember, selectin=False)
    members: list[ProjectMember] = _relationship("project", selectin=False)
    # keys: list["ProjectKey"] = _relationship("project")

    @classmethod
    async def list_(
        cls,
        session: AsyncSession,
        return_type: Type[ItemType],
        *,
        offset: int = 0,
        limit: int | None = None,
        order_by: str | None = None,
        order_ascending: bool = True,
        search_query: str | None = None,
        search_columns: list[str] | None = None,
        filters: dict[str, Any | list[Any]] | None = None,
        after: str | None = None,
        filter_by_user: str = "",
    ) -> Page[ItemType]:
        if order_by is None:
            order_by = cls.pk()[0]
        items, total = cls._list(
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_ascending=order_ascending,
            search_query=search_query,
            search_columns=search_columns,
            filters=filters,
            after=after,
        )
        if filter_by_user:
            subquery = select(ProjectMember).where(
                ProjectMember.user_id == filter_by_user,
                ProjectMember.project_id == cls.id,
            )
            items = items.where(exists(subquery))
            total = total.where(exists(subquery))
        items, total, end_cursor = await cls._fetch_list_and_cursor(
            session=session,
            items=items,
            total=total,
            order_by=order_by,
        )
        return Page[return_type](
            items=items,
            offset=offset,
            limit=total if limit is None else limit,
            total=total,
            end_cursor=end_cursor,
        )


class Secret(_TableBase, table=True):
    """Secret model for storing sensitive information with project access control."""

    organization_id: str = SqlField(
        foreign_key="Organization.id",
        primary_key=True,
        index=True,
        description="Organization ID.",
        ondelete="CASCADE",
    )
    name: str = SqlField(
        primary_key=True,
        max_length=255,
        description="Secret name (case-insensitive, saved in uppercase).",
    )
    value: str = SqlField(
        min_length=1,
        description="Secret value (cannot be empty).",
    )
    allowed_projects: list[str] | None = SqlField(
        default=None,
        sa_type=JSON,
        index=True,
        description=(
            "List of project IDs allowed to access this secret. "
            "None means all projects are allowed. "
            "Empty list [] means no projects are allowed."
        ),
    )
    organization: Organization = _relationship("secrets", selectin=False)

    def to_read(self) -> SecretRead:
        """Convert to SecretRead with decrypted value."""
        decrypted_value = decrypt(self.value, ENV_CONFIG.encryption_key_plain)
        kwargs = self.model_dump()
        kwargs["value"] = decrypted_value
        return SecretRead(**kwargs)

    def to_read_masked(self) -> SecretRead:
        """Convert to SecretRead with masked value."""
        kwargs = self.model_dump()
        kwargs["value"] = "***"  # Mask the value
        return SecretRead(**kwargs)

    @classmethod
    def _search_query_filter(
        cls,
        selection: SelectBase,
        *,
        search_query: str | None,
        search_columns: list[str] | None,
    ) -> SelectBase:
        """Apply search filters with special handling for allowed_projects."""
        # Apply search filters
        if search_query and search_columns:
            search_conditions = []
            for column_name in search_columns:
                if column_name == "allowed_projects":
                    # Special handling for JSON allowed_projects column
                    column = getattr(cls, column_name)
                    if search_query == "[]":
                        # Search for empty allowed projects array (not NULL)
                        # Check: NOT NULL AND is array type AND array length is 0
                        search_conditions.append(
                            and_(
                                column.is_not(None),
                                func.jsonb_typeof(column) == "array",
                                func.jsonb_array_length(column) == 0,
                            )
                        )
                    else:
                        # Use the ? operator to check if the JSON array contains the search query
                        # Only search in non-NULL values that are arrays
                        search_conditions.append(
                            and_(
                                column.is_not(None),
                                func.jsonb_typeof(column) == "array",
                                column.op("?")(search_query),
                            )
                        )
                else:
                    # For other columns, use the case-insensitive regex match
                    column = getattr(cls, column_name, None)
                    if column is not None:
                        search_conditions.append(column.op("~*")(search_query))

            if search_conditions:
                selection = selection.where(or_(*search_conditions))
        return selection
