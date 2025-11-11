import os
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from os.path import basename, join
from typing import Any, Generator, Self, TypeVar

from loguru import logger
from pydantic import BaseModel, model_validator

from jamaibase import JamAI
from jamaibase.types import (
    ActionTableSchemaCreate,
    CellCompletionResponse,
    CellReferencesResponse,
    ChatCompletionChunkResponse,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatTableSchemaCreate,
    ColumnSchemaCreate,
    ConversationCreateRequest,
    ConversationMetaResponse,
    DeploymentCreate,
    DeploymentRead,
    FileUploadResponse,
    KnowledgeTableSchemaCreate,
    LLMGenConfig,
    ModelConfigCreate,
    ModelConfigRead,
    MultiRowAddRequest,
    MultiRowCompletionResponse,
    MultiRowRegenRequest,
    OkResponse,
    OrganizationCreate,
    OrganizationRead,
    Page,
    PasswordLoginRequest,
    PricePlanCreate,
    PricePlanRead,
    Products,
    ProjectCreate,
    ProjectRead,
    References,
    RowCompletionResponse,
    StripePaymentInfo,
    TableDataImportRequest,
    TableMetaResponse,
    UserCreate,
    UserRead,
)
from owl.configs import ENV_CONFIG
from owl.db.models import BASE_PLAN_ID
from owl.types import CloudProvider, ModelCapability, ModelType, TableType
from owl.utils.crypt import generate_key
from owl.utils.dates import utc_iso_from_uuid7_draft2

EMAIL = "carl@up.com"
DS_PARAMS = dict(argvalues=["clickhouse", "victoriametrics"], ids=["ch", "vm"])


def get_file_map(test_file_dir: str) -> dict[str, str]:
    _files = [join(root, f) for root, _, files in os.walk(test_file_dir) for f in files]
    file_map = {basename(f): f for f in _files}
    if not len(_files) == len(file_map):
        raise ValueError(f'There are duplicate file names in "{test_file_dir}"')
    return file_map


@contextmanager
def register_password(
    body: dict[str, Any],
    *,
    token: str = ENV_CONFIG.service_key_plain,
):
    user = JamAI(token=token).auth.register_password(UserCreate(**body))
    try:
        assert isinstance(user, UserRead)
        assert user.email == body["email"]
        assert user.name == body["name"]
        if "password" in body:
            assert user.password_hash == "***"
        else:
            assert user.password_hash is None
        yield user
    finally:
        try:
            JamAI(user_id=user.id, token=token).users.delete_user()
        except Exception as e:
            logger.error(f"User cleanup failed: {repr(e)}")


@contextmanager
def create_plan(
    body: dict[str, Any],
    *,
    user_id: str,
    token: str = ENV_CONFIG.service_key_plain,
):
    client = JamAI(user_id=user_id, token=token)
    plan = client.prices.create_price_plan(body)
    try:
        yield plan
    finally:
        client.prices.delete_price_plan(plan.id, missing_ok=True)


@contextmanager
def create_user(
    body: dict[str, Any] | None = None,
    *,
    token: str = ENV_CONFIG.service_key_plain,
):
    if body is None:
        body = dict(email=EMAIL, name="System Admin")
    user = JamAI(token=token).users.create_user(UserCreate(**body))
    try:
        assert isinstance(user, UserRead)
        assert user.email == body["email"]
        assert user.name == body["name"]
        if "password" in body:
            assert user.password_hash == "***", f"{user.password_hash=}"
            # Test password login
            user = JamAI(token=token).auth.login_password(
                PasswordLoginRequest(email=body["email"], password=body["password"])
            )
            assert isinstance(user, UserRead)
        else:
            assert user.password_hash is None
        yield user
    finally:
        try:
            JamAI(user_id=user.id, token=token).users.delete_user()
        except Exception as e:
            logger.error(f"User cleanup failed: {repr(e)}")


@contextmanager
def create_organization(
    body: OrganizationCreate | dict | None = None,
    *,
    user_id: str,
    token: str = ENV_CONFIG.service_key_plain,
    subscribe_plan: bool = True,
):
    client = JamAI(user_id=user_id, token=token)
    if body is None:
        body = OrganizationCreate(name="Clubhouse")
    # Create org
    org = client.organizations.create_organization(body)
    try:
        assert isinstance(org, OrganizationRead)
        assert org.created_by == user_id, f"{org.created_by=}, {user_id=}"
        # Try to create price plan
        if ENV_CONFIG.is_cloud:
            plans = client.prices.list_price_plans()
            if plans.total <= 1:
                client.prices.create_price_plan(
                    PricePlanCreate(
                        id="pro",
                        name="Pro plan",
                        stripe_price_id_live="price_223",
                        stripe_price_id_test="price_1RT2EdCcpbd72IcYeAFWrbxw",
                        flat_cost=25.0,
                        credit_grant=15.0,
                        max_users=None,
                        products=Products.unlimited(),
                    )
                )
                client.prices.create_price_plan(
                    PricePlanCreate(
                        id="team",
                        name="Team plan",
                        stripe_price_id_live="price_323",
                        stripe_price_id_test="price_1RT2FfCcpbd72IcYPGIGyXmj",
                        flat_cost=250.0,
                        credit_grant=150.0,
                        max_users=None,
                        products=Products.unlimited(),
                    )
                )
            base_plan = next((p for p in plans.items if p.id == BASE_PLAN_ID), None)
            assert isinstance(base_plan, PricePlanRead)
            assert base_plan.flat_cost == 0.0
            if subscribe_plan and org.price_plan_id is None:
                response = client.organizations.subscribe_plan(org.id, base_plan.id)
                assert isinstance(response, StripePaymentInfo)
                org.price_plan_id = base_plan.id
                org.price_plan = base_plan
            response = JamAI(user_id="0", token=token).organizations.set_credit_grant(
                organization_id=org.id, amount=150
            )
            assert isinstance(response, OkResponse)
        if isinstance(body, BaseModel):
            body = body.model_dump()
        assert org.name == body["name"]
        yield org
    finally:
        try:
            client.organizations.delete_organization(org.id)
        except Exception as e:
            logger.error(f"Organization cleanup failed: {repr(e)}")


@contextmanager
def create_project(
    body: dict[str, Any] | None = None,
    *,
    user_id: str = "0",
    organization_id: str = "0",
    token: str = ENV_CONFIG.service_key_plain,
):
    client = JamAI(user_id=user_id, token=token)
    if body is None:
        body = dict(name="Mickey 17")
    body["organization_id"] = organization_id
    project = client.projects.create_project(ProjectCreate(**body))
    try:
        assert isinstance(project, ProjectRead)
        assert project.created_by == user_id, f"{project.created_by=}, {user_id=}"
        assert project.name.startswith(body["name"])
        yield project
    finally:
        try:
            client.projects.delete_project(project.id)
        except Exception as e:
            logger.error(f"Project cleanup failed: {repr(e)}")


@contextmanager
def create_model_config(
    body: ModelConfigCreate,
    *,
    user_id: str = "0",
    token: str = ENV_CONFIG.service_key_plain,
):
    client = JamAI(user_id=user_id, token=token)
    model = client.models.create_model_config(body)
    try:
        assert isinstance(model, ModelConfigRead)
        yield model
    finally:
        try:
            client.models.delete_model_config(model.id)
        except Exception as e:
            logger.error(f"Model cleanup failed: {repr(e)}")


@contextmanager
def create_deployment(
    body: DeploymentCreate | dict,
    *,
    user_id: str = "0",
    token: str = ENV_CONFIG.service_key_plain,
):
    client = JamAI(user_id=user_id, token=token)
    deployment = client.models.create_deployment(body)
    try:
        assert isinstance(deployment, DeploymentRead)
        yield deployment
    finally:
        try:
            client.models.delete_deployment(deployment.id)
        except Exception as e:
            logger.error(f"Deployment cleanup failed: {repr(e)}")


class OrgContext(BaseModel):
    superuser: UserRead
    user: UserRead
    superorg: OrganizationRead
    org: OrganizationRead


@contextmanager
def setup_organizations():
    with (
        create_user() as superuser,
        create_user(dict(email=f"russell-{generate_key(8)}@up.com", name="User")) as user,
    ):
        assert user.id != "0"
        with (
            create_organization(
                OrganizationCreate(name="System"), user_id=superuser.id
            ) as superorg,
            create_organization(OrganizationCreate(name="Clubhouse"), user_id=user.id) as org,
        ):
            assert superorg.id == "0"
            assert org.id != "0"
            yield OrgContext(superuser=superuser, user=user, superorg=superorg, org=org)


class ProjectContext(OrgContext):
    projects: list[ProjectRead]


@contextmanager
def setup_projects():
    with setup_organizations() as ctx:
        with (
            create_project(user_id=ctx.superuser.id, organization_id=ctx.superorg.id) as p0,
            create_project(user_id=ctx.user.id, organization_id=ctx.org.id) as p1,
        ):
            assert p0.organization_id == ctx.superorg.id
            assert p1.organization_id == ctx.org.id
            # Using `**model_dump()` leads to serialization warnings
            yield ProjectContext(
                projects=[p0, p1],
                superuser=ctx.superuser,
                user=ctx.user,
                superorg=ctx.superorg,
                org=ctx.org,
            )


SMOL_LM2_CONFIG = ModelConfigCreate(
    id="ellm/smollm2:135m",
    name="ELLM SmolLM2 135M",
    type=ModelType.LLM,
    capabilities=[ModelCapability.CHAT],
    context_length=4096,
    owned_by="ellm",
)
CLAUDE_HAIKU_CONFIG = ModelConfigCreate(
    id="anthropic/claude-3-5-haiku-latest",
    name="Anthropic Claude 3.5 Haiku",
    type=ModelType.LLM,
    capabilities=[
        ModelCapability.CHAT,
        ModelCapability.IMAGE,
        ModelCapability.TOOL,
    ],
    context_length=128000,
    languages=["en"],
)
GPT_41_MINI_CONFIG = ModelConfigCreate(
    id="openai/gpt-4.1-mini",
    name="OpenAI GPT-4.1 mini",
    type=ModelType.LLM,
    capabilities=[
        ModelCapability.CHAT,
        ModelCapability.IMAGE,
        ModelCapability.TOOL,
    ],
    context_length=1047576,
    languages=["en"],
)
GPT_41_NANO_CONFIG = ModelConfigCreate(
    id="openai/gpt-4.1-nano",
    name="OpenAI GPT-4.1 nano",
    type=ModelType.LLM,
    capabilities=[
        ModelCapability.CHAT,
        ModelCapability.IMAGE,
        ModelCapability.TOOL,
    ],
    context_length=1047576,
    languages=["en"],
)
GPT_4O_MINI_CONFIG = ModelConfigCreate(
    id="openai/gpt-4o-mini",
    name="OpenAI GPT-4o mini",
    type=ModelType.LLM,
    capabilities=[
        ModelCapability.CHAT,
        ModelCapability.IMAGE,
        ModelCapability.TOOL,
    ],
    context_length=128000,
    languages=["en"],
)
GPT_5_MINI_CONFIG = ModelConfigCreate(
    id="openai/gpt-5-mini",
    name="OpenAI GPT-5 mini",
    type=ModelType.LLM,
    capabilities=[
        ModelCapability.CHAT,
        ModelCapability.REASONING,
        ModelCapability.IMAGE,
        ModelCapability.TOOL,
    ],
    context_length=1280000,
    languages=["en"],
)
OPENAI_O4_MINI_CONFIG = ModelConfigCreate(
    id="openai/o4-mini",
    name="OpenAI o4 mini",
    type=ModelType.LLM,
    capabilities=[
        ModelCapability.CHAT,
        ModelCapability.REASONING,
        ModelCapability.IMAGE,
        ModelCapability.TOOL,
    ],
    context_length=1280000,
    languages=["en"],
)
ELLM_DESCRIBE_CONFIG = ModelConfigCreate(
    id="ellm/describe",
    name="Describe Message",
    type=ModelType.LLM,
    capabilities=[
        ModelCapability.CHAT,
        ModelCapability.IMAGE,
        ModelCapability.AUDIO,
    ],
    context_length=128000,
    languages=["en"],
    owned_by="ellm",
)
TEXT_EMBEDDING_3_SMALL_CONFIG = ModelConfigCreate(
    id="openai/text-embedding-3-small",
    name="OpenAI Text Embedding 3 Small",
    type=ModelType.EMBED,
    capabilities=[ModelCapability.EMBED],
    context_length=8192,
    embedding_size=1536,
    embedding_dimensions=256,
    languages=["en"],
)
ELLM_EMBEDDING_CONFIG = ModelConfigCreate(
    id="ellm/embed-dim-256",
    name="Mock Embedding (256-dim)",
    type=ModelType.EMBED,
    capabilities=[ModelCapability.EMBED],
    context_length=8192,
    embedding_size=256,
    embedding_dimensions=256,
    languages=["en"],
    owned_by="ellm",
)
RERANK_ENGLISH_v3_SMALL_CONFIG = ModelConfigCreate(
    id="cohere/rerank-english-v3.0",
    name="Cohere Rerank English v3.0",
    type=ModelType.RERANK,
    capabilities=[ModelCapability.RERANK],
    context_length=512,
    languages=["en"],
)

CLAUDE_HAIKU_DEPLOYMENT = DeploymentCreate(
    model_id=CLAUDE_HAIKU_CONFIG.id,
    name=f"{CLAUDE_HAIKU_CONFIG.name} Deployment",
    provider=CloudProvider.ANTHROPIC,
    routing_id=CLAUDE_HAIKU_CONFIG.id,
    api_base="",
)
GPT_41_MINI_DEPLOYMENT = DeploymentCreate(
    model_id=GPT_41_MINI_CONFIG.id,
    name=f"{GPT_41_MINI_CONFIG.name} Deployment",
    provider=CloudProvider.OPENAI,
    routing_id=GPT_41_MINI_CONFIG.id,
    api_base="",
)
GPT_41_NANO_DEPLOYMENT = DeploymentCreate(
    model_id=GPT_41_NANO_CONFIG.id,
    name=f"{GPT_41_NANO_CONFIG.name} Deployment",
    provider=CloudProvider.OPENAI,
    routing_id=GPT_41_NANO_CONFIG.id,
    api_base="",
)
GPT_4O_MINI_DEPLOYMENT = DeploymentCreate(
    model_id=GPT_4O_MINI_CONFIG.id,
    name=f"{GPT_4O_MINI_CONFIG.name} Deployment",
    provider=CloudProvider.OPENAI,
    routing_id=GPT_4O_MINI_CONFIG.id,
    api_base="",
)
GPT_5_MINI_DEPLOYMENT = DeploymentCreate(
    model_id=GPT_5_MINI_CONFIG.id,
    name=f"{GPT_5_MINI_CONFIG.name} Deployment",
    provider=CloudProvider.OPENAI,
    routing_id=GPT_5_MINI_CONFIG.id,
    api_base="",
)
OPENAI_O4_MINI_DEPLOYMENT = DeploymentCreate(
    model_id=OPENAI_O4_MINI_CONFIG.id,
    name=f"{OPENAI_O4_MINI_CONFIG.name} Deployment",
    provider=CloudProvider.OPENAI,
    routing_id=OPENAI_O4_MINI_CONFIG.id,
    api_base="",
)
ELLM_DESCRIBE_DEPLOYMENT = DeploymentCreate(
    model_id=ELLM_DESCRIBE_CONFIG.id,
    name=f"{ELLM_DESCRIBE_CONFIG.name} Deployment",
    provider="custom",
    routing_id=ELLM_DESCRIBE_CONFIG.id,
    api_base=ENV_CONFIG.test_llm_api_base,
)
TEXT_EMBEDDING_3_SMALL_DEPLOYMENT = DeploymentCreate(
    model_id=TEXT_EMBEDDING_3_SMALL_CONFIG.id,
    name=f"{TEXT_EMBEDDING_3_SMALL_CONFIG.name} Deployment",
    provider=CloudProvider.OPENAI,
    routing_id=TEXT_EMBEDDING_3_SMALL_CONFIG.id,
    api_base="",
)
ELLM_EMBEDDING_DEPLOYMENT = DeploymentCreate(
    model_id=ELLM_EMBEDDING_CONFIG.id,
    name=f"{ELLM_EMBEDDING_CONFIG.name} Deployment",
    provider=CloudProvider.VLLM_CLOUD,
    routing_id=ELLM_EMBEDDING_CONFIG.id,
    api_base=ENV_CONFIG.test_llm_api_base,
)
RERANK_ENGLISH_v3_SMALL_DEPLOYMENT = DeploymentCreate(
    model_id=RERANK_ENGLISH_v3_SMALL_CONFIG.id,
    name=f"{RERANK_ENGLISH_v3_SMALL_CONFIG.name} Deployment",
    provider=CloudProvider.COHERE,
    routing_id=RERANK_ENGLISH_v3_SMALL_CONFIG.id,
    api_base="",
)


@lru_cache(maxsize=1000)
def upload_file_cached(user_id: str, project_id: str, file_path: str) -> FileUploadResponse:
    return JamAI(user_id=user_id, project_id=project_id).file.upload_file(file_path)


def upload_file(client: JamAI, file_path: str) -> FileUploadResponse:
    return upload_file_cached(
        user_id=client.user_id,
        project_id=client.project_id,
        file_path=file_path,
    )


STREAM_PARAMS = dict(argvalues=[True, False], ids=["stream", "non-stream"])
TABLE_TYPES = list(TableType)
TEXTS = {
    "EN": '"Arrival" is a 2016 film.',
    "ZH-CN": "《降临》是一部 2016 年科幻片。",
    "ZH-TW": "《異星入境》是2016年的電影。",
    "JA": "「メッセージ」は2016年の映画です。",
    "KR": '"컨택트"는 2016년 영화입니다.',
    "ES": '"La llegada" es una película de 2016.',
    "IT": '"Arrival" è un film del 2016.',
    "IS": '"Arrival" er kvikmynd frá 2016.',
    "AR": '"الوصول" هو فيلم من عام 2016.',
}


@contextmanager
def create_table(
    client: JamAI,
    table_type: TableType,
    table_id: str = "",
    *,
    cols: list[ColumnSchemaCreate] | None = None,
    chat_cols: list[ColumnSchemaCreate] | None = None,
    chat_model: str = "",
    embedding_model: str = "",
):
    try:
        if cols is None:
            dtypes = ["int", "float", "bool", "str", "image", "audio", "document"]
            cols = [ColumnSchemaCreate(id=dtype, dtype=dtype) for dtype in dtypes]
            cols += [
                ColumnSchemaCreate(
                    id="summary",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model=chat_model,
                        system_prompt="",
                        prompt="",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ),
                ),
            ]
        if table_type == TableType.CHAT:
            if chat_cols is None:
                cols = [
                    ColumnSchemaCreate(id="User", dtype="str"),
                    ColumnSchemaCreate(
                        id="AI",
                        dtype="str",
                        gen_config=LLMGenConfig(
                            model="",
                            system_prompt="You are a wacky assistant.",
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=5,
                        ),
                    ),
                ] + cols
            else:
                cols = chat_cols + cols

        # info_col_ids = ["ID", "Updated at"]
        # input_col_ids = [
        #     col.id for col in cols if col.gen_config is None and col.id not in info_col_ids
        # ]
        # # output_col_ids = [col.id for col in cols if col.gen_config is not None]
        # default_sys_prompt_col_ids = [
        #     col.id
        #     for col in cols
        #     if isinstance(col.gen_config, LLMGenConfig) and col.gen_config.system_prompt == ""
        # ]
        # default_prompt_col_ids = [
        #     col.id
        #     for col in cols
        #     if isinstance(col.gen_config, LLMGenConfig) and col.gen_config.prompt == ""
        # ]

        if not table_id:
            table_id = generate_key(80, "table-")
        if table_type == TableType.ACTION:
            table = client.table.create_action_table(
                ActionTableSchemaCreate(id=table_id, cols=cols),
            )
        elif table_type == TableType.KNOWLEDGE:
            table = client.table.create_knowledge_table(
                KnowledgeTableSchemaCreate(id=table_id, cols=cols, embedding_model=embedding_model)
            )
        elif table_type == TableType.CHAT:
            table = client.table.create_chat_table(
                ChatTableSchemaCreate(id=table_id, cols=cols),
            )
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, TableMetaResponse)
        assert table.id == table_id
        # col_map = {col.id: col for col in table.cols}
        # # Check default system prompt
        # default_sys_phrase = (
        #     "You are a versatile data generator. "
        #     "Your task is to process information from input data and generate appropriate responses based on the specified column name and input data."
        # )
        # for col_id in default_sys_prompt_col_ids:
        #     gen_config = col_map[col_id].gen_config
        #     assert default_sys_phrase in gen_config.system_prompt
        # # Check default prompt
        # input_col_refs = ["${" + col + "}" for col in input_col_ids]
        # for col_id in default_prompt_col_ids:
        #     gen_config = col_map[col_id].gen_config
        #     for ref in input_col_refs:
        #         assert ref in gen_config.prompt, f"Missing '{ref}' in '{gen_config.prompt}'"
        #     assert "${ID}" not in gen_config.prompt  # Info columns
        #     assert "${Updated at}" not in gen_config.prompt  # Info columns
        #     if table_type == TableType.KNOWLEDGE:
        #         assert "${Title Embed}" not in gen_config.prompt  # Vector columns
        #         assert "${Text Embed}" not in gen_config.prompt  # Vector columns
        #     elif table_type == TableType.CHAT:
        #         assert "${User}" in gen_config.prompt
        yield table
    finally:
        try:
            client.table.delete_table(table_type, table_id, missing_ok=True)
        except Exception as e:
            logger.error(f"Table cleanup failed: {repr(e)}")


def list_tables(
    client: JamAI,
    table_type: TableType,
    *,
    offset: int = 0,
    limit: int = 100,
    order_by: str = "updated_at",
    order_ascending: bool = True,
    created_by: str | None = None,
    parent_id: str | None = None,
    search_query: str = "",
    count_rows: bool = False,
    **kwargs,
) -> Page[TableMetaResponse]:
    tables = client.table.list_tables(
        table_type,
        offset=offset,
        limit=limit,
        order_by=order_by,
        order_ascending=order_ascending,
        created_by=created_by,
        parent_id=parent_id,
        search_query=search_query,
        count_rows=count_rows,
        **kwargs,
    )
    assert isinstance(tables, Page)
    assert isinstance(tables.items, list)
    assert all(isinstance(t, TableMetaResponse) for t in tables.items)
    return tables


def compile_and_check_row_responses(
    response: (
        MultiRowCompletionResponse
        | Generator[CellReferencesResponse | CellCompletionResponse, None, None]
    ),
    *,
    table_type: TableType,
    stream: bool,
    regen: bool,
    check_usage: bool = True,
) -> MultiRowCompletionResponse:
    if stream:
        responses: list[CellReferencesResponse | CellCompletionResponse] = [r for r in response]
        # dump_json(
        #     [r.model_dump(mode="json") for r in responses], f"stream-{table_type.value}.json"
        # )
        for r in responses:
            if isinstance(r, CellReferencesResponse):
                assert r.object == "gen_table.references"
            elif isinstance(r, CellCompletionResponse):
                assert r.object == "gen_table.completion.chunk"
                assert r.usage is None or isinstance(r.usage, ChatCompletionUsage)
                assert isinstance(r.prompt_tokens, int)
                assert isinstance(r.completion_tokens, int)
                assert isinstance(r.total_tokens, int)
            else:
                raise ValueError(f"Unexpected response type: {type(r)}")
        # Construct MultiRowCompletionResponse
        row_chunks_map: dict[str, list[CellCompletionResponse]] = defaultdict(list)
        refs_map: dict[tuple[str, str], CellReferencesResponse] = {}
        for r in responses:
            if isinstance(r, CellReferencesResponse):
                refs_map[(r.row_id, r.output_column_name)] = r
                continue
            row_chunks_map[r.row_id].append(r)
        rows = []
        for row_id, row_chunks in row_chunks_map.items():
            col_chunks_map: dict[str, list[CellCompletionResponse]] = defaultdict(list)
            for c in row_chunks:
                col_chunks_map[c.output_column_name].append(c)
            columns = {col_id: chunks[0] for col_id, chunks in col_chunks_map.items()}
            for col_id, chunks in col_chunks_map.items():
                content = "".join(
                    getattr(c.choices[0].message, "content", "") or "" for c in chunks
                )
                reasoning_content = "".join(
                    getattr(c.choices[0].message, "reasoning_content", "") or "" for c in chunks
                )
                columns[col_id].choices[0].message.content = content
                columns[col_id].choices[0].message.reasoning_content = reasoning_content
                columns[col_id].choices[0].delta = None
                columns[col_id].usage = chunks[-1].usage  # Last chunk should have usage data
                columns[col_id].references = refs_map.get((row_id, col_id), None)
                # columns[col_id] = ChatCompletionResponse.model_validate(
                #     columns[col_id].model_dump(exclude={"object", "references.object"})
                # )
            rows.append(RowCompletionResponse(columns=columns, row_id=row_id))
        response = MultiRowCompletionResponse(rows=rows)
        # dump_json(response.model_dump(mode="json"), f"stream-{table_type.value}-converted.json")
    # else:
    #     dump_json(response.model_dump(mode="json"), f"nonstream-{table_type.value}-converted.json")
    assert isinstance(response, MultiRowCompletionResponse)
    assert response.object == "gen_table.completion.rows"
    for row in response.rows:
        assert isinstance(row, RowCompletionResponse)
        assert row.object == "gen_table.completion.chunks"
        # if table_type == TableType.CHAT:
        #     assert "AI" in row.columns
        # Check completion lengths
        for completion in row.columns.values():
            assert isinstance(completion, (ChatCompletionChunkResponse, ChatCompletionResponse))
            # assert len(completion.content) > 0, f"{completion=}"
            # Check usage
            if check_usage and not completion.content.startswith("[ERROR] "):
                assert isinstance(completion.usage, ChatCompletionUsage), f"{completion.usage=}"
                assert isinstance(completion.prompt_tokens, int)
                assert isinstance(completion.completion_tokens, int)
                assert isinstance(completion.total_tokens, int)
                # Regen will return zero usage for "RUN_BEFORE", "RUN_AFTER", "RUN_SELECTED"
                min_value = 0 if regen else 1
                assert completion.prompt_tokens >= min_value, f"{completion.content=} {completion.usage=}"  # fmt: off
                assert completion.completion_tokens >= min_value, f"{completion.content=} {completion.usage=}"  # fmt: off
                assert completion.usage.total_tokens >= min_value, f"{completion.content=} {completion.usage=}"  # fmt: off
            # Check references
            if isinstance(completion.references, References):
                assert isinstance(completion.references.chunks, list)
            else:
                assert completion.references is None, (
                    f"Unexpected type: {type(completion.references)=}"
                )
    return response


def add_table_rows(
    client: JamAI,
    table_type: TableType,
    table_name: str,
    data: list[dict, Any],
    *,
    stream: bool,
    check_usage: bool = True,
) -> MultiRowCompletionResponse:
    response = client.table.add_table_rows(
        table_type,
        MultiRowAddRequest(table_id=table_name, data=data, stream=stream),
    )
    return compile_and_check_row_responses(
        response,
        table_type=table_type,
        stream=stream,
        regen=False,
        check_usage=check_usage,
    )


def regen_table_rows(
    client: JamAI,
    table_type: TableType,
    table_name: str,
    row_ids: list[str],
    *,
    stream: bool,
    check_usage: bool = True,
    **kwargs: Any,
) -> MultiRowCompletionResponse:
    response = client.table.regen_table_rows(
        table_type,
        MultiRowRegenRequest(table_id=table_name, row_ids=row_ids, stream=stream, **kwargs),
    )
    return compile_and_check_row_responses(
        response,
        table_type=table_type,
        stream=stream,
        regen=True,
        check_usage=check_usage,
    )


def import_table_data(
    client: JamAI,
    table_type: TableType,
    table_name: str,
    file_path: str,
    *,
    stream: bool,
    delimiter: str = ",",
    check_usage: bool = True,
    **kwargs: Any,
) -> MultiRowCompletionResponse:
    response = client.table.import_table_data(
        table_type,
        TableDataImportRequest(
            file_path=file_path,
            table_id=table_name,
            stream=stream,
            delimiter=delimiter,
            **kwargs,
        ),
    )
    return compile_and_check_row_responses(
        response,
        table_type=table_type,
        stream=stream,
        regen=False,
        check_usage=check_usage,
    )


def assert_is_vector_or_none(x: Any, *, allow_none: bool):
    if allow_none and x is None:
        return
    assert isinstance(x, list), f"Not a list: {x}"
    assert len(x) > 0, f"List is empty: {x}"
    assert all(isinstance(v, float) for v in x), f"Not a list of floats: {x}"


T = TypeVar("T")


class RowPage(Page[T]):
    # For easier testing
    values: list[dict[str, Any]] = []
    originals: list[dict[str, Any]] = []
    references: list[dict[str, References | Any]] = []

    @model_validator(mode="after")
    def flatten_row_data(self) -> Self:
        rows: list[dict[str, Any]] = self.items
        self.values = [
            # `value` key must be present
            {c: v["value"] if isinstance(v, dict) else v for c, v in r.items()}
            for r in rows
        ]
        self.originals = [
            # `original` key may be absent
            {c: v.get("original", None) if isinstance(v, dict) else None for c, v in r.items()}
            for r in rows
        ]
        references = [
            # `references` key may be absent
            {c: v.get("references", None) if isinstance(v, dict) else None for c, v in r.items()}
            for r in rows
        ]
        self.references = [
            {c: References.model_validate(v) if v else None for c, v in r.items()}
            for r in references
        ]
        return self


def _check_fetched_row(
    row: dict[str, Any],
    *,
    table_type: TableType,
    vec_decimals: int = 0,
    columns: list[str] | None = None,
):
    assert isinstance(row, dict)
    # Check info columns
    assert isinstance(row["ID"], str)
    assert isinstance(row["Updated at"], str)
    id_datetime = datetime.fromisoformat(utc_iso_from_uuid7_draft2(row["ID"]))
    updated_at = datetime.fromisoformat(row["Updated at"])
    time_diff = abs(
        (id_datetime.replace(tzinfo=None) - updated_at.replace(tzinfo=None)).total_seconds()
    )
    assert time_diff < (60 * 60), (
        f"ID datetime: {id_datetime}, Updated at: {updated_at}, Diff: {time_diff}"
    )
    # Check vector columns
    if table_type == TableType.KNOWLEDGE:
        if vec_decimals < 0:
            # Vector columns should be removed
            assert "Text Embed" not in row
            assert "Title Embed" not in row
        else:
            if columns is None or "Text Embed" in columns:
                assert_is_vector_or_none(row["Text Embed"]["value"], allow_none=True)
            if columns is None or "Title Embed" in columns:
                assert_is_vector_or_none(row["Title Embed"]["value"], allow_none=True)


def list_table_rows(
    client: JamAI,
    table_type: TableType,
    table_name: str,
    *,
    offset: int = 0,
    limit: int = 100,
    order_by: str = "ID",
    order_ascending: bool = True,
    columns: list[str] | None = None,
    where: str = "",
    search_query: str = "",
    search_columns: list[str] | None = None,
    float_decimals: int = 0,
    vec_decimals: int = 0,
    **kwargs,
) -> RowPage[dict[str, Any]]:
    rows = client.table.list_table_rows(
        table_type,
        table_name,
        offset=offset,
        limit=limit,
        order_by=order_by,
        order_ascending=order_ascending,
        columns=columns,
        where=where,
        search_query=search_query,
        search_columns=search_columns,
        float_decimals=float_decimals,
        vec_decimals=vec_decimals,
        **kwargs,
    )
    assert isinstance(rows, Page)
    assert isinstance(rows.items, list)
    assert rows.offset == offset
    assert rows.limit == limit
    if len(rows.items) > 0:
        row = rows.items[0]
        _check_fetched_row(
            row,
            table_type=table_type,
            vec_decimals=vec_decimals,
            columns=columns,
        )
    rows = RowPage[dict[str, Any]].model_validate(rows.model_dump())
    return rows


def get_table_row(
    client: JamAI,
    table_type: TableType,
    table_name: str,
    row_id: str,
    *,
    columns: list[str] | None = None,
    float_decimals: int = 0,
    vec_decimals: int = 0,
    **kwargs,
) -> dict[str, Any]:
    row = client.table.get_table_row(
        table_type,
        table_name,
        row_id,
        columns=columns,
        float_decimals=float_decimals,
        vec_decimals=vec_decimals,
        **kwargs,
    )
    _check_fetched_row(
        row,
        table_type=table_type,
        vec_decimals=vec_decimals,
        columns=columns,
    )
    return row


def check_rows(
    rows: list[dict[str, Any]],
    data: list[dict[str, Any]],
    *,
    info_cols_equal: bool = True,
):
    assert len(rows) == len(data), f"Row count mismatch: {len(rows)=} != {len(data)=}"
    for row, d in zip(rows, data, strict=True):
        for col in d:
            if col in ["ID", "Updated at"] and not info_cols_equal:
                assert row[col] != d[col], f'Column "{col}" is not regenerated: {d[col]=}'
                continue
            if d[col] is None or d[col] == "":
                assert row[col] is None, f'Column "{col}" mismatch: {row[col]=} != {d[col]=}'
            else:
                assert row[col] == d[col], f'Column "{col}" mismatch: {row[col]=} != {d[col]=}'


def create_conversation(
    client: JamAI,
    agent_id: str,
    data: dict[str, Any],
    title: str | None = None,
) -> list[ConversationMetaResponse | CellReferencesResponse | CellCompletionResponse]:
    chunks = client.conversations.create_conversation(
        ConversationCreateRequest(agent_id=agent_id, data=data, title=title)
    )
    return list(chunks)


# class ModelContext(ProjectContext):
#     tier: ModelTierRead
#     model: ModelConfigRead
#     deployment: DeploymentRead


# @contextmanager
# def setup_model():
#     async with setup_projects() as ctx:
#         async with (
#             create_model_tier(
#                 dict(
#                     id="test-tier",
#                     name="Test PriceTier",
#                     llm_requests_per_minute=100,
#                     llm_tokens_per_minute=1000,
#                 )
#             ) as tier,
#             create_model_config(
#                 ModelConfigCreate(
#                     id="openai/gpt-4o-mini",
#                     name="OpenAI GPT-4o mini",
#                     capabilities=["chat", "image"],
#                     context_length=128000,
#                     type=ModelType.LLM,
#                     languages=["en"],
#                 )
#             ) as model,
#             create_deployment(
#                 DeploymentCreate(
#                     model_id=model.id,
#                     name="Test Deployment",
#                     provider=CloudProvider.OPENAI,
#                     routing_id="openai/gpt-4o-mini",
#                 )
#             ) as deployment,
#         ):
#             assert tier.id == "test-tier"
#             assert model.id == "openai/gpt-4o-mini"
#             assert deployment.model_id == "openai/gpt-4o-mini"
#             # Using `**model_dump()` leads to serialization warnings
#             yield ModelContext(
#                 tier=tier,
#                 model=model,
#                 deployment=deployment,
#                 projects=ctx.projects,
#                 superuser=ctx.superuser,
#                 user=ctx.user,
#                 superorg=ctx.superorg,
#                 org=ctx.org,
#             )
