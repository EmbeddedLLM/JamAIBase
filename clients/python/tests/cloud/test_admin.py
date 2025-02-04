from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from inspect import signature
from multiprocessing import Manager, Process
from time import sleep
from typing import Generator, Type

import pytest
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from jamaibase import JamAI
from jamaibase.protocol import (
    ActionTableSchemaCreate,
    AdminOrderBy,
    ApiKeyCreate,
    ApiKeyRead,
    ChatCompletionChunk,
    ChatEntry,
    ChatRequest,
    ChatTableSchemaCreate,
    ColumnSchemaCreate,
    EmbeddingRequest,
    EmbeddingResponse,
    EventCreate,
    EventRead,
    GenTableRowsChatCompletionChunks,
    GenTableStreamChatCompletionChunk,
    KnowledgeTableSchemaCreate,
    LLMGenConfig,
    LLMModelConfig,
    ModelDeploymentConfig,
    ModelListConfig,
    ModelPrice,
    OkResponse,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    OrgMemberCreate,
    OrgMemberRead,
    PATCreate,
    PATRead,
    Price,
    ProjectCreate,
    RowAddRequest,
    TableMetaResponse,
    TableType,
    UserCreate,
    UserRead,
    UserUpdate,
)
from jamaibase.utils import datetime_now_iso
from owl.configs.manager import ENV_CONFIG, PlanName, ProductType
from owl.utils import uuid7_str

CLIENT_CLS = [JamAI]
USER_ID_A = "duncan"
USER_ID_B = "mama"
USER_ID_C = "sus"
TABLE_TYPES = [TableType.action, TableType.knowledge, TableType.chat]


@contextmanager
def _create_user(
    owl: JamAI,
    user_id: str = USER_ID_A,
    **kwargs,
) -> Generator[UserRead, None, None]:
    # TODO: Can make this work with OSS too by yielding a dummy UserRead
    owl.admin.backend.delete_user(user_id)
    try:
        user = owl.admin.backend.create_user(
            UserCreate(
                id=user_id,
                name=kwargs.pop("name", "Duncan Idaho"),
                description=kwargs.pop("description", "A Ginaz Swordmaster from House Atreides."),
                email=kwargs.pop("email", "duncan.idaho@gmail.com"),
                meta=kwargs.pop("meta", {}),
            )
        )
        yield user
    finally:
        owl.admin.backend.delete_user(user_id)


@contextmanager
def _create_org(
    owl: JamAI,
    user_id: str,
    active: bool = True,
    **kwargs,
) -> Generator[OrganizationRead, None, None]:
    org_id = None
    try:
        org = owl.admin.backend.create_organization(
            OrganizationCreate(
                creator_user_id=user_id,
                name=kwargs.pop("name", "Company"),
                external_keys=kwargs.pop("external_keys", {}),
                tier=kwargs.pop("tier", PlanName.FREE),
                active=active,
                **kwargs,
            )
        )
        org_id = org.id
        yield org
    finally:
        if org_id is not None:
            owl.admin.backend.delete_organization(org_id)


def _delete_project(owl: JamAI, project_id: str | None):
    if project_id is not None:
        owl.admin.organization.delete_project(project_id)


@contextmanager
def _create_project(
    owl: JamAI,
    organization_id: str,
    name: str = "default",
) -> Generator[OrganizationRead, None, None]:
    project_id = None
    try:
        project = owl.admin.organization.create_project(
            ProjectCreate(
                organization_id=organization_id,
                name=name,
            )
        )
        project_id = project.id
        yield project
    finally:
        _delete_project(owl, project_id)


@contextmanager
def _set_model_config(owl: JamAI, config: ModelListConfig):
    old_config = owl.admin.backend.get_model_config()
    try:
        response = owl.admin.backend.set_model_config(config)
        assert isinstance(response, OkResponse)
        yield response
    finally:
        owl.admin.backend.set_model_config(old_config)


def _chat(jamai: JamAI, model_id: str):
    request = ChatRequest(
        model=model_id,
        messages=[
            ChatEntry.system("You are a concise assistant."),
            ChatEntry.user("What is a llama?"),
        ],
        temperature=0.001,
        top_p=0.001,
        max_tokens=3,
        stream=False,
    )
    completion = jamai.generate_chat_completions(request)
    assert isinstance(completion, ChatCompletionChunk)
    assert isinstance(completion.text, str)
    assert len(completion.text) > 1


def _embed(jamai: JamAI, model_id: str):
    request = EmbeddingRequest(
        input="什么是 llama?",
        model=model_id,
        type="document",
        encoding_format="float",
    )
    response = jamai.generate_embeddings(request)
    assert isinstance(response, EmbeddingResponse)
    assert isinstance(response.data, list)
    assert isinstance(response.data[0].embedding, list)
    assert len(response.data[0].embedding) > 0


@contextmanager
def _create_gen_table(
    jamai: JamAI,
    table_type: TableType,
    table_id: str,
    model_id: str = "",
    cols: list[ColumnSchemaCreate] | None = None,
    chat_cols: list[ColumnSchemaCreate] | None = None,
    embedding_model: str = "",
    delete_first: bool = True,
    delete: bool = True,
):
    try:
        if delete_first:
            jamai.table.delete_table(table_type, table_id)
        if cols is None:
            cols = [
                ColumnSchemaCreate(id="input", dtype="str"),
                ColumnSchemaCreate(
                    id="output",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model=model_id,
                        prompt="${input}",
                        max_tokens=3,
                    ),
                ),
            ]
        if chat_cols is None:
            chat_cols = [
                ColumnSchemaCreate(id="User", dtype="str"),
                ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model=model_id,
                        system_prompt="You are an assistant.",
                        max_tokens=3,
                    ),
                ),
            ]
        if table_type == TableType.action:
            table = jamai.table.create_action_table(
                ActionTableSchemaCreate(id=table_id, cols=cols)
            )
        elif table_type == TableType.knowledge:
            table = jamai.table.create_knowledge_table(
                KnowledgeTableSchemaCreate(id=table_id, cols=cols, embedding_model=embedding_model)
            )
        elif table_type == TableType.chat:
            table = jamai.table.create_chat_table(
                ChatTableSchemaCreate(id=table_id, cols=chat_cols + cols)
            )
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, TableMetaResponse)
        yield table
    finally:
        if delete:
            jamai.table.delete_table(table_type, table_id)


def test_cors():
    import httpx

    def _assert_cors(_response: httpx.Response):
        assert "Access-Control-Allow-Origin" in _response.headers, _response.headers
        assert "Access-Control-Allow-Methods" in _response.headers, _response.headers
        assert "Access-Control-Allow-Headers" in _response.headers, _response.headers
        assert "Access-Control-Allow-Credentials" in _response.headers, _response.headers
        assert _response.headers["Access-Control-Allow-Credentials"].lower() == "true"

    headers = {
        "Origin": "http://example.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    owl = JamAI()
    # Preflight
    response = httpx.options(owl.api_base, headers=headers)
    _assert_cors(response)

    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            with _create_project(owl, org.id) as p0:
                assert isinstance(p0.id, str)
                endpoint = f"{owl.api_base}/v1/models"
                # Assert preflight no auth
                response = httpx.options(endpoint, headers=headers)
                _assert_cors(response)
                # Assert CORS headers in methods with auth
                response = httpx.get(endpoint, headers=headers)
                assert response.status_code == 401
                response = httpx.get(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {owl.api_key}",
                        "X-PROJECT-ID": p0.id,
                        **headers,
                    },
                )
                assert "Access-Control-Allow-Origin" in response.headers, response.headers
                assert "Access-Control-Allow-Credentials" in response.headers, response.headers
                assert response.headers["Access-Control-Allow-Credentials"].lower() == "true"


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_create_users(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as user:
        assert isinstance(user, UserRead)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_get_and_list_users(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan, _create_user(owl, USER_ID_B) as mama:
        # Test fetch
        user = owl.admin.backend.get_user(duncan.id)
        assert isinstance(user, UserRead)
        assert user.id == duncan.id

        user = owl.admin.backend.get_user(mama.id)
        assert isinstance(user, UserRead)
        assert user.id == mama.id

        # Test list
        users = owl.admin.backend.list_users()
        assert isinstance(users.items, list)
        assert all(isinstance(r, UserRead) for r in users.items)
        assert users.total == 2
        assert users.offset == 0
        assert users.limit == 100
        assert len(users.items) == 2

        users = owl.admin.backend.list_users(offset=1)
        assert isinstance(users.items, list)
        assert all(isinstance(r, UserRead) for r in users.items)
        assert users.total == 2
        assert users.offset == 1
        assert users.limit == 100
        assert len(users.items) == 1

        users = owl.admin.backend.list_users(limit=1)
        assert isinstance(users.items, list)
        assert all(isinstance(r, UserRead) for r in users.items)
        assert users.total == 2
        assert users.offset == 0
        assert users.limit == 1
        assert len(users.items) == 1


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_update_user(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        updated_user_request = UserUpdate(id=duncan.id, name="Updated Duncan")
        updated_user_response = owl.admin.backend.update_user(updated_user_request)
        assert isinstance(updated_user_response, UserRead)
        assert updated_user_response.id == duncan.id
        assert updated_user_response.name == "Updated Duncan"


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_delete_users(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as user:
        assert isinstance(user, UserRead)
        # Assert there is a user
        users = owl.admin.backend.list_users()
        assert isinstance(users.items, list)
        assert users.total == 1
        # Delete
        response = owl.admin.backend.delete_user(user.id)
        assert isinstance(response, OkResponse)
        # Assert there is no user
        users = owl.admin.backend.list_users()
        assert isinstance(users.items, list)
        assert users.total == 0

        with pytest.raises(RuntimeError, match="User .+ is not found."):
            owl.admin.backend.update_user(UserUpdate(id=user.id, name="Updated Name"))

        with pytest.raises(RuntimeError, match="User .+ is not found."):
            owl.admin.backend.get_user(user.id)

        response = owl.admin.backend.delete_user(user.id)
        assert isinstance(response, OkResponse)
        with pytest.raises(RuntimeError, match="User .+ is not found."):
            owl.admin.backend.delete_user(user.id, missing_ok=False)


def test_user_update_pydantic_model():
    sig = signature(UserUpdate)
    for name, param in sig.parameters.items():
        if name == "id":
            continue
        assert (
            param.default is None
        ), f'Parameter "{name}" has a default value of {param.default} instead of None.'


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_pat(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as u0, _create_user(owl, USER_ID_B) as u1:
        with _create_org(owl, u0.id) as o0, _create_org(owl, u1.id):
            with _create_project(owl, o0.id) as p0:
                pat0 = owl.admin.backend.create_pat(PATCreate(user_id=u0.id))
                pat0_expire = owl.admin.backend.create_pat(
                    PATCreate(
                        user_id=u0.id,
                        expiry=(datetime.now(tz=timezone.utc) + timedelta(seconds=1)).isoformat(),
                    )
                )
                assert isinstance(pat0, PATRead)
                pat1 = owl.admin.backend.create_pat(PATCreate(user_id=u1.id))
                assert isinstance(pat1, PATRead)
                # Make some requests using the PAT
                jamai = JamAI(project_id=p0.id, token=pat0.id)
                models = jamai.model_names(capabilities=["chat"])
                assert isinstance(models, list)
                assert len(models) > 0
                # Fetch the user
                user = JamAI().admin.backend.get_user(u0.id)
                assert isinstance(user, UserRead)
                assert user.id == USER_ID_A
                user = JamAI().admin.backend.get_user(u1.id)
                assert isinstance(user, UserRead)
                assert user.id == USER_ID_B
                # Create gen table
                with _create_gen_table(jamai, "action", "xx"):
                    table = jamai.table.get_table("action", "xx")
                    assert isinstance(table, TableMetaResponse)
                    ### --- Test service key auth --- ###
                    table = JamAI(
                        project_id=p0.id,
                        token=ENV_CONFIG.service_key_plain,
                        headers={"X-USER-ID": u0.id},
                    ).table.get_table("action", "xx")
                    assert isinstance(table, TableMetaResponse)
                    # Try using invalid user ID
                    with pytest.raises(RuntimeError):
                        JamAI(
                            project_id=p0.id,
                            token=ENV_CONFIG.service_key_plain,
                            headers={"X-USER-ID": u1.id},
                        ).table.get_table("action", "xx")
                    ### --- Test PAT --- ###
                    # Try using invalid PAT
                    with pytest.raises(RuntimeError):
                        JamAI(project_id=p0.id, token=pat1.id).table.get_table("action", "xx")
                    # Test PAT expiry
                    while datetime_now_iso() < pat0_expire.expiry:
                        sleep(1)
                    with pytest.raises(RuntimeError):
                        JamAI(project_id=p0.id, token=pat0_expire.id).table.get_table(
                            "action", "xx"
                        )
                    # Test PAT fetch
                    pat0_read = owl.admin.backend.get_pat(pat0.id)
                    assert isinstance(pat0_read, PATRead)
                    assert pat0_read.id == pat0.id
                    # Test PAT deletion
                    response = owl.admin.backend.delete_pat(pat0.id)
                    assert isinstance(response, OkResponse)
                    with pytest.raises(RuntimeError):
                        owl.admin.backend.get_pat(pat0.id)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_create_organizations(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id, external_keys=dict(openai="sk-test")) as org:
            assert isinstance(org, OrganizationRead)
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            assert "openai" in org.external_keys
            assert org.external_keys["openai"] == "sk-test"


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_create_organizations_free_tier_check(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with (
            _create_org(owl, duncan.id, name="Free 0", tier=PlanName.FREE) as o0,
            _create_org(owl, duncan.id, name="Free 1", tier=PlanName.FREE) as o1,
            _create_org(owl, duncan.id, name="Paid 0", tier=PlanName.PRO) as o2,
        ):
            assert isinstance(o0, OrganizationRead)
            assert isinstance(o0.id, str)
            assert len(o0.id) > 0
            assert isinstance(o1, OrganizationRead)
            assert isinstance(o1.id, str)
            assert len(o1.id) > 0
            assert isinstance(o2, OrganizationRead)
            assert isinstance(o2.id, str)
            assert len(o2.id) > 0
            assert o0.active is True
            assert o1.active is False
            assert o2.active is True
            with _create_project(owl, o0.id, "Pear"):
                pass
            with pytest.raises(RuntimeError, match="not activated"):
                with _create_project(owl, o1.id, "Pear"):
                    pass
            with _create_project(owl, o2.id, "Pear"):
                pass


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_create_organizations_invalid_key(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with pytest.raises(RuntimeError, match="Unsupported external provider"):
            with _create_org(owl, duncan.id, external_keys=dict(invalid="sk-test")):
                pass


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_get_and_list_organizations(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id, name="company") as company:
            with _create_org(owl, duncan.id, name="Personal"):
                # Test fetch
                org = owl.admin.backend.get_organization(company.id)
                assert isinstance(org, OrganizationRead)
                assert org.id == company.id
                assert isinstance(org.members, list)
                assert isinstance(org.api_keys, list)
                assert isinstance(org.projects, list)
                assert duncan.id in set(u.user_id for u in org.members)
                assert len(org.api_keys) == 0
                assert len(org.projects) == 0

                with (
                    _create_project(owl, company.id, "bear") as p0,
                    _create_project(owl, company.id) as p1,
                ):
                    org = owl.admin.backend.get_organization(company.id)
                    assert isinstance(org, OrganizationRead)
                    assert org.id == company.id
                    assert isinstance(org.members, list)
                    assert isinstance(org.api_keys, list)
                    assert isinstance(org.projects, list)
                    assert duncan.id in set(u.user_id for u in org.members)
                    assert len(org.api_keys) == 0
                    assert len(org.projects) == 2
                    assert p0.id in set(p.id for p in org.projects)
                    assert p1.id in set(p.id for p in org.projects)

                # Test list
                orgs = owl.admin.backend.list_organizations()
                assert isinstance(orgs.items, list)
                assert all(isinstance(r, OrganizationRead) for r in orgs.items)
                assert orgs.total == 2
                assert orgs.offset == 0
                assert orgs.limit == 100
                assert len(orgs.items) == 2

                orgs = owl.admin.backend.list_organizations(offset=1)
                assert isinstance(orgs.items, list)
                assert all(isinstance(r, OrganizationRead) for r in orgs.items)
                assert orgs.total == 2
                assert orgs.offset == 1
                assert orgs.limit == 100
                assert len(orgs.items) == 1

                orgs = owl.admin.backend.list_organizations(limit=1)
                assert isinstance(orgs.items, list)
                assert all(isinstance(r, OrganizationRead) for r in orgs.items)
                assert orgs.total == 2
                assert orgs.offset == 0
                assert orgs.limit == 1
                assert len(orgs.items) == 1

                # Test list with order_by
                orgs = owl.admin.backend.list_organizations(
                    order_by="created_at", order_descending=False
                )
                assert isinstance(orgs.items, list)
                assert all(isinstance(r, OrganizationRead) for r in orgs.items)
                assert orgs.items[0].name == "company"
                assert orgs.items[1].name == "Personal"
                assert orgs.total == 2
                assert orgs.offset == 0
                assert orgs.limit == 100
                assert len(orgs.items) == 2

                # Ensure ordering is case-insensitive, otherwise uppercase will come before lowercase
                orgs = owl.admin.backend.list_organizations(
                    order_by="name", order_descending=False
                )
                assert isinstance(orgs.items, list)
                assert all(isinstance(r, OrganizationRead) for r in orgs.items)
                assert orgs.items[0].name == "company"
                assert orgs.items[1].name == "Personal"
                assert orgs.total == 2
                assert orgs.offset == 0
                assert orgs.limit == 100
                assert len(orgs.items) == 2

                for order_by in AdminOrderBy:
                    orgs = owl.admin.backend.list_organizations(order_by=order_by)
                    org_ids = [org.id for org in orgs.items]
                    assert len(orgs.items) == 2
                    orgs_desc = owl.admin.backend.list_organizations(
                        order_by=order_by, order_descending=False
                    )
                    org_ids_desc = [org.id for org in orgs_desc.items]
                    assert len(orgs_desc.items) == 2
                    assert (
                        org_ids == org_ids_desc[::-1]
                    ), f"Failed to order by {order_by}: {org_ids} != {org_ids_desc[::-1]}"

                # # Test starting_after
                # orgs = owl.admin.backend.list_organizations(
                #     order_by="created_at", order_descending=False, starting_after=company.id
                # )
                # assert isinstance(orgs.items, list)
                # assert all(isinstance(r, OrganizationRead) for r in orgs.items)
                # assert orgs.items[0].name == "Personal"
                # assert orgs.total == 2
                # assert orgs.offset == 0
                # assert orgs.limit == 100
                # assert len(orgs.items) == 1


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_update_organization(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            updated_org = owl.admin.backend.update_organization(
                OrganizationUpdate(
                    id=org.id,
                    name="Company X",
                    active=True,
                    llm_tokens_usage_mtok=100.0,
                )
            )
            assert isinstance(updated_org, OrganizationRead)
            assert updated_org.id == org.id
            assert updated_org.name == "Company X"
            assert updated_org.llm_tokens_usage_mtok == 100.0
            updated_org = owl.admin.backend.update_organization(
                OrganizationUpdate(
                    id=org.id,
                    embedding_tokens_quota_mtok=9.0,
                )
            )
            assert isinstance(updated_org, OrganizationRead)
            org = owl.admin.backend.get_organization(org.id)
            assert isinstance(org, OrganizationRead)
            assert updated_org.llm_tokens_usage_mtok == 100.0
            assert updated_org.embedding_tokens_quota_mtok == 9.0


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_delete_organizations(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            assert isinstance(org, OrganizationRead)
            # Assert there is an org
            orgs = owl.admin.backend.list_organizations()
            assert isinstance(orgs.items, list)
            assert orgs.total == 1

            # Delete the organization
            response = owl.admin.backend.delete_organization(org.id)
            assert isinstance(response, OkResponse)

            # Assert there is no org
            orgs = owl.admin.backend.list_organizations()
            assert isinstance(orgs.items, list)
            assert orgs.total == 0

            response = owl.admin.backend.delete_organization(org.id)
            assert isinstance(response, OkResponse)
            with pytest.raises(RuntimeError, match="Organization .+ is not found."):
                owl.admin.backend.delete_organization(org.id, missing_ok=False)

            with pytest.raises(RuntimeError, match="Organization .+ is not found."):
                owl.admin.backend.update_organization(
                    OrganizationUpdate(id=org.id, name="Updated Name")
                )

            with pytest.raises(RuntimeError, match="Organization .+ is not found."):
                owl.admin.backend.get_organization(org.id)

            with pytest.raises(RuntimeError, match="Organization .+ is not found."):
                owl.admin.organization.create_project(
                    ProjectCreate(name="New Project", organization_id=org.id)
                )

            with pytest.raises(RuntimeError, match="Organization .+ is not found."):
                owl.admin.backend.join_organization(
                    OrgMemberCreate(user_id=duncan.id, organization_id=org.id)
                )

            with pytest.raises(RuntimeError, match="Organization .+ is not found."):
                owl.admin.backend.leave_organization(user_id=duncan.id, organization_id=org.id)


def test_organization_update_pydantic_model():
    sig = signature(OrganizationUpdate)
    for name, param in sig.parameters.items():
        if name == "id":
            continue
        assert (
            param.default is None
        ), f'Parameter "{name}" has a default value of {param.default} instead of None.'


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_refresh_quota(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id, tier=PlanName.FREE) as org:
            free_quota = org.llm_tokens_quota_mtok
            assert org.llm_tokens_usage_mtok == 0.0
            # Set to another tier
            org = owl.admin.backend.update_organization(
                OrganizationUpdate(
                    id=org.id,
                    tier=PlanName.PRO,
                    llm_tokens_usage_mtok=0.2,
                )
            )
            # Quota should be unchanged before refresh
            assert org.llm_tokens_quota_mtok == free_quota
            assert org.llm_tokens_usage_mtok == 0.2
            # Quota should increase after refresh, usage should reset
            org = owl.admin.backend.refresh_quota(org.id)
            assert isinstance(org, OrganizationRead)
            pro_quota = org.llm_tokens_quota_mtok
            assert pro_quota > free_quota
            assert org.llm_tokens_usage_mtok == 0.0
            # Test refresh without resetting usage
            owl.admin.backend.update_organization(
                OrganizationUpdate(
                    id=org.id,
                    tier=PlanName.FREE,
                    llm_tokens_usage_mtok=0.2,
                )
            )
            org = owl.admin.backend.refresh_quota(org.id, False)
            assert org.llm_tokens_quota_mtok < pro_quota
            assert org.llm_tokens_usage_mtok == 0.2


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_create_fetch_delete_api_key(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id, tier=PlanName.PRO) as org:
            # Create API key
            api_key = owl.admin.backend.create_api_key(ApiKeyCreate(organization_id=org.id))
            assert isinstance(api_key, ApiKeyRead)
            print(f"API key created: {api_key}\n")

            # Fetch API key info
            fetched_key = owl.admin.backend.get_api_key(api_key.id)
            assert isinstance(fetched_key, ApiKeyRead)
            assert fetched_key.id == api_key.id
            print(f"API key fetched: {fetched_key}\n")

            # Fetch company using API key
            org = owl.admin.backend.get_organization(api_key.id)
            assert isinstance(org, OrganizationRead)
            print(f"Organization fetched: {org}\n")

            # Delete API key
            response = owl.admin.backend.delete_api_key(api_key.id)
            assert isinstance(response, OkResponse)
            print(f"API key deleted: {api_key.id}\n")


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_fetch_specific_user(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        user = owl.admin.backend.get_user(duncan.id)
        assert isinstance(user, UserRead)
        print(f"User fetched: {user}\n")


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_join_and_leave_organization(client_cls: Type[JamAI]):
    owl = client_cls()
    with (
        _create_user(owl, USER_ID_A, email="a@gmail.com") as u0,
        _create_user(owl, USER_ID_B, email="b@gmail.com") as u1,
        _create_user(owl, USER_ID_C, email="c@gmail.com") as u2,
    ):
        # --- Join without invite link --- #
        with _create_org(owl, u0.id, tier="pro") as pro_org, _create_org(owl, u0.id) as free_org:
            assert u1.id not in set(m.user_id for m in pro_org.members)
            member = owl.admin.backend.join_organization(
                OrgMemberCreate(user_id=u1.id, organization_id=pro_org.id)
            )
            assert isinstance(member, OrgMemberRead)
            assert member.user_id == u1.id
            assert member.organization_id == pro_org.id
            assert member.role == "admin"
            # Cannot join free org
            with pytest.raises(RuntimeError):
                owl.admin.backend.join_organization(
                    OrgMemberCreate(user_id=u1.id, organization_id=free_org.id)
                )
        # --- Join with public invite link --- #
        with _create_org(owl, u0.id, tier="pro") as pro_org:
            assert u1.id not in set(m.user_id for m in pro_org.members)
            invite = owl.admin.backend.generate_invite_token(pro_org.id, user_role="member")
            member = owl.admin.backend.join_organization(
                OrgMemberCreate(
                    user_id=u1.id,
                    organization_id=pro_org.id,
                    role="member",
                    invite_token=invite,
                )
            )
            assert isinstance(member, OrgMemberRead)
            assert member.user_id == u1.id
            assert member.organization_id == pro_org.id
            assert member.role == "member"
        # --- Join with private invite link --- #
        with _create_org(owl, u0.id, tier="pro") as pro_org:
            assert u1.id not in set(m.user_id for m in pro_org.members)
            # Invite token email validation should be case and space insensitive
            invite = owl.admin.backend.generate_invite_token(
                pro_org.id, f" {u1.email.upper()} ", user_role="admin"
            )
            member = owl.admin.backend.join_organization(
                OrgMemberCreate(
                    user_id=u1.id,
                    organization_id=pro_org.id,
                    role="admin",
                    invite_token=invite,
                )
            )
            assert isinstance(member, OrgMemberRead)
            assert member.user_id == u1.id
            assert member.organization_id == pro_org.id
            assert member.role == "admin"
            # Other email should fail
            with pytest.raises(RuntimeError):
                owl.admin.backend.join_organization(
                    OrgMemberCreate(
                        user_id=u2.id,
                        organization_id=pro_org.id,
                        role="admin",
                        invite_token=invite,
                    )
                )
            # --- Leave organization --- #
            leave_response = owl.admin.backend.leave_organization(u0.id, pro_org.id)
            assert isinstance(leave_response, OkResponse)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_add_event(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            response = owl.admin.backend.add_event(
                EventCreate(
                    id=f"{org.id}_token",
                    organization_id=org.id,
                    deltas={ProductType.LLM_TOKENS: -0.5},
                    values={},
                )
            )
            assert isinstance(response, OkResponse)

            event = owl.admin.backend.get_event(f"{org.id}_token")
            assert isinstance(event, EventRead)
            assert event.id == f"{org.id}_token"
            assert event.deltas.get(ProductType.LLM_TOKENS) == -0.5


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_get_event(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            owl.admin.backend.add_event(
                EventCreate(
                    id=f"{org.id}_token",
                    organization_id=org.id,
                    deltas={ProductType.LLM_TOKENS: -0.5},
                    values={},
                )
            )

            event = owl.admin.backend.get_event(f"{org.id}_token")
            assert isinstance(event, EventRead)
            assert event.id == f"{org.id}_token"
            assert event.deltas.get(ProductType.LLM_TOKENS) == -0.5


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_mark_event_as_done(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            owl.admin.backend.add_event(
                EventCreate(
                    id=f"{org.id}_token",
                    organization_id=org.id,
                    deltas={ProductType.LLM_TOKENS: -0.5},
                    values={},
                )
            )

            response = owl.admin.backend.mark_event_as_done(f"{org.id}_token")
            assert isinstance(response, OkResponse)

            event = owl.admin.backend.get_event(f"{org.id}_token")
            assert isinstance(event, EventRead)
            assert event.id == f"{org.id}_token"
            assert event.pending is False
            assert event.deltas.get(ProductType.LLM_TOKENS) == -0.5


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_get_pricing(client_cls: Type[JamAI]):
    owl = client_cls()
    response = owl.admin.backend.get_pricing()
    assert isinstance(response, Price)
    assert len(response.plans) > 0
    response = owl.admin.backend.get_model_pricing()
    assert isinstance(response, ModelPrice)
    assert len(response.llm_models) > 0
    assert len(response.embed_models) > 0
    assert len(response.rerank_models) > 0


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_add_credit(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            assert isinstance(org, OrganizationRead)
            assert isinstance(org.id, str)
            assert len(org.id) > 0

            assert org.credit == 0
            assert org.credit_grant == 0
            assert org.llm_tokens_usage_mtok == 0
            assert org.db_usage_gib == 0
            assert org.file_usage_gib == 0
            assert org.egress_usage_gib == 0
            # Set values
            response = owl.admin.backend.add_event(
                EventCreate(
                    id=f"{org.quota_reset_at}_credit_{uuid7_str()}",
                    organization_id=org.id,
                    values={
                        ProductType.CREDIT: 20.0,
                        ProductType.CREDIT_GRANT: 1,
                        ProductType.LLM_TOKENS: 70,
                        ProductType.DB_STORAGE: 2.0,
                        ProductType.FILE_STORAGE: 3.0,
                        ProductType.EGRESS: 4.0,
                        ProductType.EMBEDDING_TOKENS: 5.0,
                        ProductType.RERANKER_SEARCHES: 6.0,
                    },
                )
            )
            assert isinstance(response, OkResponse)
            org = owl.admin.backend.get_organization(org.id)
            assert org.credit == 20.0
            assert org.credit_grant == 1.0
            assert org.llm_tokens_usage_mtok == 70
            assert org.db_usage_gib == 2.0
            assert org.file_usage_gib == 3.0
            assert org.egress_usage_gib == 4.0
            assert org.embedding_tokens_usage_mtok == 5.0
            assert org.reranker_usage_ksearch == 6.0
            for product in ProductType.exclude_credits():
                assert isinstance(org.quotas[product]["quota"], (int, float))
                assert isinstance(org.quotas[product]["usage"], (int, float))
            # Add deltas
            response = owl.admin.backend.add_event(
                EventCreate(
                    id=f"{org.quota_reset_at}_credit_{uuid7_str()}",
                    organization_id=org.id,
                    deltas={
                        "credit": 1.0,
                        ProductType.CREDIT_GRANT: 1.0,
                        ProductType.LLM_TOKENS: 70,
                        ProductType.DB_STORAGE: 2.0,
                        ProductType.FILE_STORAGE: 3.0,
                        ProductType.EGRESS: 4.0,
                        ProductType.EMBEDDING_TOKENS: 5.0,
                        ProductType.RERANKER_SEARCHES: 6.0,
                    },
                )
            )
            assert isinstance(response, OkResponse)
            org = owl.admin.backend.get_organization(org.id)
            assert org.credit == 21.0
            assert org.credit_grant == 2.0
            assert org.llm_tokens_usage_mtok == 140
            assert org.db_usage_gib == 4.0
            assert org.file_usage_gib == 6.0
            assert org.egress_usage_gib == 8.0
            assert org.embedding_tokens_usage_mtok == 10.0
            assert org.reranker_usage_ksearch == 12.0
            # Ensure values cannot go to negative
            response = owl.admin.backend.add_event(
                EventCreate(
                    id=f"{org.quota_reset_at}_credit_{uuid7_str()}",
                    organization_id=org.id,
                    deltas={
                        "credit": -200.0,
                        ProductType.CREDIT_GRANT: -200.0,
                        ProductType.LLM_TOKENS: -200,
                        ProductType.DB_STORAGE: -200.0,
                        ProductType.FILE_STORAGE: -200.0,
                        ProductType.EGRESS: -200.0,
                        ProductType.EMBEDDING_TOKENS: -200.0,
                        ProductType.RERANKER_SEARCHES: -200.0,
                    },
                )
            )
            assert isinstance(response, OkResponse)
            org = owl.admin.backend.get_organization(org.id)
            assert org.credit == 0
            assert org.credit_grant == 0
            assert org.llm_tokens_usage_mtok == 0
            assert org.db_usage_gib == 0
            assert org.file_usage_gib == 0
            assert org.egress_usage_gib == 0
            assert org.embedding_tokens_usage_mtok == 0.0
            assert org.reranker_usage_ksearch == 0.0


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_get_set_model_config(client_cls: Type[JamAI]):
    owl = client_cls()
    # Initial fetch
    config = owl.admin.backend.get_model_config()
    assert isinstance(config, ModelListConfig)
    assert len(config.llm_models) > 1
    assert len(config.embed_models) > 1
    assert len(config.rerank_models) > 1
    llm_model_ids = [m.id for m in config.llm_models]
    assert "ellm/new_model" not in llm_model_ids
    # Set
    new_config = config.model_copy(deep=True)
    new_config.llm_models.append(
        LLMModelConfig(
            id="ellm/new_model",
            name="ELLM New Model",
            context_length=8000,
            deployments=[
                ModelDeploymentConfig(
                    provider="ellm",
                )
            ],
            languages=["mul"],
            capabilities=["chat"],
            owned_by="ellm",
        )
    )
    with _set_model_config(owl, new_config) as response:
        assert isinstance(response, OkResponse)
        # Fetch again
        new_config = owl.admin.backend.get_model_config()
        assert isinstance(new_config, ModelListConfig)
        assert len(new_config.llm_models) == len(config.llm_models) + 1
        assert len(new_config.embed_models) == len(config.embed_models)
        assert len(new_config.rerank_models) == len(config.rerank_models)
        llm_model_ids = [m.id for m in new_config.llm_models]
        assert "ellm/new_model" in llm_model_ids
        # Fetch model list
        with _create_user(owl) as duncan:
            with _create_org(owl, duncan.id) as org:
                assert isinstance(org.id, str)
                assert len(org.id) > 0
                with _create_project(owl, org.id) as project:
                    assert isinstance(project.id, str)
                    assert len(project.id) > 0
                    jamai = JamAI(project_id=project.id)
                    models = jamai.model_names(capabilities=["chat"])
        assert isinstance(models, list)
        assert "ellm/new_model" in models


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_credit_check_llm(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            assert isinstance(org, OrganizationRead)
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            with _create_project(owl, org.id) as project:
                assert isinstance(project.id, str)
                assert len(project.id) > 0
                # Get model list
                jamai = JamAI(project_id=project.id)
                models = jamai.model_info(capabilities=["chat"]).data
                assert isinstance(models, list)
                models = {m.owned_by: m for m in models}
                model = models["openai"]

                # --- No credit to use 3rd party models --- #
                assert org.credit == 0
                assert len(model.id) > 0
                # Error message should show model ID when called via API
                with pytest.raises(
                    RuntimeError,
                    match=f"Insufficient LLM token quota or credits for model: {model.id}",
                ):
                    _chat(jamai, model.id)
                assert len(model.name) > 0
                assert model.name != model.id
                # Error message should show model name when called via browser
                name = model.name.replace("(", "\\(").replace(")", "\\)")
                with pytest.raises(
                    RuntimeError,
                    match=f"Insufficient LLM token quota or credits for model: {name}",
                ):
                    _chat(
                        JamAI(project_id=project.id, headers={"User-Agent": "Mozilla"}),
                        model.id,
                    )

                @retry(
                    wait=wait_exponential(multiplier=1, min=1, max=10),
                    stop=stop_after_attempt(5),
                    reraise=True,
                )
                def _assert_usage_updated(initial_value: int | float = 0):
                    org_read = owl.admin.backend.get_organization(org.id)
                    assert isinstance(org_read, OrganizationRead)
                    assert org_read.llm_tokens_usage_mtok > initial_value

                @retry(
                    wait=wait_exponential(multiplier=1, min=1, max=10),
                    stop=stop_after_attempt(5),
                    reraise=True,
                )
                def _assert_chat_fail(_model_id: str):
                    # No more credit left
                    try:
                        _chat(jamai, _model_id)
                        logger.warning(
                            f"Org credit grant = {owl.admin.backend.get_organization(org.id).credit_grant}"
                        )
                    except RuntimeError as e:
                        if (
                            f"Insufficient LLM token quota or credits for model: {_model_id}"
                            not in str(e)
                        ):
                            raise ValueError("Error message mismatch") from e
                        # We actually want this to raise RuntimeError
                    else:
                        raise ValueError("Chat attempt did not fail.")

                # --- Test credit --- #
                owl.admin.backend.add_event(
                    EventCreate(
                        id=f"{org.quota_reset_at}_credit_{uuid7_str()}",
                        organization_id=org.id,
                        values={ProductType.CREDIT: 1e-12},
                    )
                )
                _chat(jamai, model.id)
                _assert_chat_fail(model.id)

                # --- Test credit grant --- #
                owl.admin.backend.add_event(
                    EventCreate(
                        id=f"{org.quota_reset_at}_credit_{uuid7_str()}",
                        organization_id=org.id,
                        values={
                            ProductType.CREDIT: 0.0,
                            ProductType.CREDIT_GRANT: 1e-12,
                        },
                    )
                )
                org = owl.admin.backend.get_organization(org.id)
                assert org.credit == 0
                assert org.credit_grant == 1e-12
                _chat(jamai, model.id)
                _assert_chat_fail(model.id)

                # --- Test ELLM model --- #
                # ELLM model ok
                ellm_model_id = "ellm/llama-3.1-8B"
                config = owl.admin.backend.get_model_config()
                config.llm_models.append(
                    LLMModelConfig(
                        id=ellm_model_id,
                        name="ELLM Meta Llama 3.1 (8B)",
                        deployments=[
                            ModelDeploymentConfig(
                                litellm_id="together_ai/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                                provider="together_ai",
                            )
                        ],
                        context_length=8000,
                        languages=["mul"],
                        capabilities=["chat"],
                        owned_by="ellm",
                    )
                )
                with _set_model_config(owl, config):
                    _chat(jamai, ellm_model_id)
                    _assert_usage_updated()
                    # Exhaust the quota
                    owl.admin.backend.add_event(
                        EventCreate(
                            id=f"{org.quota_reset_at}_llm_tokens_{uuid7_str()}",
                            organization_id=org.id,
                            values={
                                ProductType.CREDIT: 0.0,
                                ProductType.CREDIT_GRANT: 0.0,
                                ProductType.LLM_TOKENS: 100000.0,
                            },
                        )
                    )
                    # No quota to use ELLM model
                    _assert_chat_fail(ellm_model_id)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_credit_check_embedding(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            assert isinstance(org, OrganizationRead)
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            with _create_project(owl, org.id) as project:
                assert isinstance(project.id, str)
                assert len(project.id) > 0
                # Get model list
                jamai = JamAI(project_id=project.id)
                models = jamai.model_info(capabilities=["embed"]).data
                assert isinstance(models, list)
                models = {m.owned_by: m for m in models}
                model = models["openai"]

                # --- No credit to use 3rd party models --- #
                assert org.credit == 0
                assert len(model.id) > 0
                # Error message should show model ID when called via API
                with pytest.raises(
                    RuntimeError,
                    match=rf"Insufficient Embedding token quota or credits for model: {model.id}",
                ):
                    _embed(jamai, model.id)
                assert len(model.name) > 0
                assert model.name != model.id
                # Error message should show model name when called via browser
                name = model.name.replace("(", "\\(").replace(")", "\\)")
                with pytest.raises(
                    RuntimeError,
                    match=f"Insufficient Embedding token quota or credits for model: {name}",
                ):
                    _embed(
                        JamAI(project_id=project.id, headers={"User-Agent": "Mozilla"}),
                        model.id,
                    )

                @retry(
                    wait=wait_exponential(multiplier=1, min=1, max=10),
                    stop=stop_after_attempt(5),
                    reraise=True,
                )
                def _assert_usage_updated(initial_value: int | float = 0):
                    org_read = owl.admin.backend.get_organization(org.id)
                    assert isinstance(org_read, OrganizationRead)
                    assert org_read.embedding_tokens_usage_mtok > initial_value

                @retry(
                    wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(10)
                )
                def _assert_embed_fail(_model_id: str):
                    # No more credit left
                    try:
                        _embed(jamai, _model_id)
                        logger.warning(
                            f"Org credit grant = {owl.admin.backend.get_organization(org.id).credit_grant}"
                        )
                    except RuntimeError as e:
                        if (
                            f"Insufficient Embedding token quota or credits for model: {_model_id}"
                            not in str(e)
                        ):
                            raise ValueError("Error message mismatch") from e
                        # We actually want this to raise RuntimeError
                    else:
                        raise ValueError("Embedding attempt did not fail.")

                # --- Test credit --- #
                owl.admin.backend.add_event(
                    EventCreate(
                        id=f"{org.quota_reset_at}_credit_{uuid7_str()}",
                        organization_id=org.id,
                        values={ProductType.CREDIT: 1e-12},
                    )
                )
                _embed(jamai, model.id)
                _assert_embed_fail(model.id)

                # --- Test credit grant --- #
                owl.admin.backend.add_event(
                    EventCreate(
                        id=f"{org.quota_reset_at}_credit_{uuid7_str()}",
                        organization_id=org.id,
                        values={
                            ProductType.CREDIT: 0.0,
                            ProductType.CREDIT_GRANT: 1e-12,
                        },
                    )
                )
                org = owl.admin.backend.get_organization(org.id)
                assert org.credit == 0
                assert org.credit_grant == 1e-12
                _embed(jamai, model.id)
                _assert_embed_fail(model.id)

                # --- Test ELLM model --- #
                # ELLM model ok
                model = models["ellm"]
                _embed(jamai, model.id)
                _assert_usage_updated()
                # Exhaust the quota
                owl.admin.backend.add_event(
                    EventCreate(
                        id=f"{org.quota_reset_at}_llm_tokens_{uuid7_str()}",
                        organization_id=org.id,
                        values={
                            ProductType.CREDIT: 0.0,
                            ProductType.CREDIT_GRANT: 0.0,
                            ProductType.EMBEDDING_TOKENS: 100000.0,
                        },
                    )
                )
                # No quota to use ELLM model
                _assert_embed_fail(model.id)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_external_api_key(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            assert isinstance(org, OrganizationRead)
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            owl.admin.backend.add_event(
                EventCreate(
                    id=f"{org.quota_reset_at}_credit_{uuid7_str()}",
                    organization_id=org.id,
                    values={ProductType.CREDIT: 0.001},
                )
            )
            with _create_project(owl, org.id) as project:
                assert isinstance(project.id, str)
                assert len(project.id) > 0
                # Get model list
                jamai = JamAI(project_id=project.id)
                models = jamai.model_info(capabilities=["chat"]).data
                assert isinstance(models, list)
                models = {m.owned_by: m for m in models}
                model = models["openai"]
                # Will use ELLM's OpenAI API key
                _chat(jamai, model.id)
                # Replace with fake key
                org = owl.admin.backend.update_organization(
                    OrganizationUpdate(id=org.id, external_keys=dict(openai="fake-key"))
                )
                assert org.external_keys["openai"] == "fake-key"
                with pytest.raises(RuntimeError, match="AuthenticationError"):
                    _chat(jamai, model.id)
                # Ensure no cooldown
                org = owl.admin.backend.update_organization(
                    OrganizationUpdate(id=org.id, external_keys=dict())
                )
                _chat(jamai, model.id)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_concurrent_usage(client_cls: Type[JamAI]):
    def _work(worker_id: int, mp_dict: dict):
        owl = client_cls()
        # Fetch model list as external org
        with _create_user(owl, f"user_{worker_id}") as user:
            with _create_org(owl, user.id, name=f"org_{worker_id}") as org:
                assert isinstance(org.id, str)
                assert len(org.id) > 0
                # Add credit
                owl.admin.backend.add_event(
                    EventCreate(
                        id=f"{org.quota_reset_at}_credit_{uuid7_str()}",
                        organization_id=org.id,
                        values={ProductType.CREDIT: 20.0},
                    )
                )
                with _create_project(owl, org.id, name=f"proj_{worker_id}") as project:
                    assert isinstance(project.id, str)
                    assert len(project.id) > 0
                    # Test model list
                    jamai = JamAI(project_id=project.id)
                    models = jamai.model_names(capabilities=["chat"])
                    assert isinstance(models, list)
                    # Test chat
                    _chat(jamai, "")
                    # Test gen table
                    data = dict(
                        input="Hi",
                        Title="Dune: Part Two.",
                        Text='"Dune: Part Two" is a 2024 American epic science fiction film.',
                        User="Tell me a joke.",
                    )
                    for table_type in TABLE_TYPES:
                        with _create_gen_table(
                            jamai, table_type, f"table_{table_type}_{worker_id}"
                        ) as table:
                            response = jamai.table.add_table_rows(
                                table_type,
                                RowAddRequest(table_id=table.id, data=[data], stream=False),
                            )
                            assert isinstance(response, GenTableRowsChatCompletionChunks)
                            assert len(response.rows) > 0
                            response = jamai.table.add_table_rows(
                                table_type,
                                RowAddRequest(table_id=table.id, data=[data], stream=True),
                            )
                            responses = [r for r in response]
                            assert len(responses) > 0
                            assert all(
                                isinstance(r, GenTableStreamChatCompletionChunk) for r in responses
                            )
                            meta = jamai.table.get_table(table_type, table.id)
        mp_dict[str(worker_id)] = meta

    num_workers = 5
    manager = Manager()
    return_dict = manager.dict()
    workers = [Process(target=_work, args=(i, return_dict)) for i in range(num_workers)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert len(return_dict) == num_workers
    metas = list(return_dict.values())
    assert all(isinstance(meta, TableMetaResponse) for meta in metas)
    assert all(meta.num_rows == 2 for meta in metas)


if __name__ == "__main__":
    test_pat(JamAI)
