from contextlib import asynccontextmanager, contextmanager
from inspect import signature
from io import BytesIO
from os.path import join
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Generator, Type

import pytest
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from jamaibase import JamAI, JamAIAsync
from jamaibase.protocol import (
    ActionTableSchemaCreate,
    AdminOrderBy,
    ChatTableSchemaCreate,
    ColumnSchemaCreate,
    EventCreate,
    GenTableRowsChatCompletionChunks,
    GenTableStreamChatCompletionChunk,
    KnowledgeTableSchemaCreate,
    LLMGenConfig,
    LLMModelConfig,
    ModelDeploymentConfig,
    ModelListConfig,
    OkResponse,
    OrganizationCreate,
    OrganizationRead,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    RowAddRequest,
    TableMetaResponse,
    TableType,
    UserCreate,
    UserRead,
)
from jamaibase.utils import run
from owl.configs.manager import PlanName, ProductType
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


@asynccontextmanager
async def _set_org_model_config(
    jamai: JamAI | JamAIAsync,
    org_id: str,
    config: ModelListConfig,
):
    old_config = await run(jamai.admin.organization.get_org_model_config, org_id)
    try:
        response = await run(jamai.admin.organization.set_org_model_config, org_id, config)
        assert isinstance(response, OkResponse)
        yield response
    finally:
        await run(jamai.admin.organization.set_org_model_config, org_id, old_config)


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


def _add_row(
    jamai: JamAI,
    table_type: TableType,
    table_id: str,
    stream: bool = False,
    data: dict | None = None,
    knowledge_data: dict | None = None,
    chat_data: dict | None = None,
):
    if data is None:
        data = dict(input="nano", output="shimmer")

    if knowledge_data is None:
        knowledge_data = dict(
            Title="Dune: Part Two.",
            Text='"Dune: Part Two" is a 2024 American epic science fiction film.',
        )
    if chat_data is None:
        chat_data = dict(User="Tell me a joke.", AI="Who's there?")
    if table_type == TableType.action:
        pass
    elif table_type == TableType.knowledge:
        data.update(knowledge_data)
    elif table_type == TableType.chat:
        data.update(chat_data)
    else:
        raise ValueError(f"Invalid table type: {table_type}")
    response = jamai.table.add_table_rows(
        table_type,
        RowAddRequest(table_id=table_id, data=[data], stream=stream),
    )
    if stream:
        response = list(response)
        assert all(isinstance(r, GenTableStreamChatCompletionChunk) for r in response)
    else:
        assert isinstance(response, GenTableRowsChatCompletionChunks)
    return response


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_get_set_org_model_config(client_cls: Type[JamAI | JamAIAsync]):
    owl = client_cls()
    # Get model config
    config = await run(owl.admin.backend.get_model_config)
    assert isinstance(config, ModelListConfig)
    assert isinstance(config.models, list)
    assert len(config.models) > 3
    assert isinstance(config.llm_models, list)
    assert isinstance(config.embed_models, list)
    assert isinstance(config.rerank_models, list)
    assert len(config.llm_models) > 1
    assert len(config.embed_models) > 1
    assert len(config.rerank_models) > 1
    public_model_ids = [m.id for m in config.models]
    assert "ellm/new_model" not in public_model_ids
    # Set organization model config
    with _create_user(owl) as duncan:
        with (
            _create_org(owl, duncan.id) as org,
            _create_org(owl, duncan.id, name="personal", tier=PlanName.PRO) as personal,
        ):
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            assert isinstance(personal.id, str)
            assert len(personal.id) > 0
            with _create_project(owl, org.id) as p0, _create_project(owl, personal.id) as p1:
                assert isinstance(p0.id, str)
                assert len(p0.id) > 0
                assert isinstance(p1.id, str)
                assert len(p1.id) > 0
                # Set
                jamai = JamAI(project_id=p0.id)
                new_model_config = ModelListConfig(
                    llm_models=[
                        LLMModelConfig(
                            id="ellm/new_model",
                            name="ELLM hyperbolic Llama3.2-3B",
                            context_length=8000,
                            languages=["mul"],
                            capabilities=["chat"],
                            owned_by="ellm",
                            deployments=[
                                ModelDeploymentConfig(
                                    litellm_id="openai/meta-llama/Llama-3.2-3B-Instruct",
                                    api_base="https://api.hyperbolic.xyz/v1",
                                    provider="hyperbolic",
                                ),
                            ],
                        )
                    ]
                )
                async with _set_org_model_config(jamai, org.id, new_model_config):
                    # Fetch org-level config
                    models = await run(jamai.admin.organization.get_org_model_config, org.id)
                    assert isinstance(models, ModelListConfig)
                    assert isinstance(models.llm_models, list)
                    assert isinstance(models.embed_models, list)
                    assert isinstance(models.rerank_models, list)
                    assert len(models.llm_models) == 1
                    assert len(models.embed_models) == 0
                    assert len(models.rerank_models) == 0
                    # Fetch model list
                    models = await run(jamai.model_names)
                    assert isinstance(models, list)
                    assert set(public_model_ids) - set(models) == set()
                    assert set(models) - set(public_model_ids) == {"ellm/new_model"}
                    # text add row with org_model
                    with _create_gen_table(
                        jamai, TableType.action, "test-org-model", "ellm/new_model", delete=True
                    ):
                        _add_row(jamai, TableType.action, "test-org-model")
                    # Try fetching from another org
                    jamai = JamAI(project_id=p1.id)
                    models = await run(jamai.model_names)
                    assert isinstance(models, list)
                    assert set(public_model_ids) - set(models) == set()
                    assert set(models) - set(public_model_ids) == set()


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_create_project(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            with _create_project(owl, org.id, "my-project") as project:
                assert isinstance(project.id, str)
                assert len(project.id) > 0
                # Duplicate name
                with pytest.raises(RuntimeError):
                    with _create_project(owl, org.id, "my-project"):
                        pass


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize(
    "name", ["a", "0", "冰:淇 淋", "a.b", "_a_", " (a) ", "=a", " " + "a" * 100]
)
def test_create_organization_project_valid_name(
    client_cls: Type[JamAI],
    name: str,
):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id, name=name) as org:
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            with _create_project(owl, org.id, name=name) as project:
                assert isinstance(project.id, str)
                assert len(project.id) > 0
                assert project.name == name.strip()


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("name", ["=", " ", "()", "a" * 101])
def test_create_organization_project_invalid_name(
    client_cls: Type[JamAI],
    name: str,
):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            with pytest.raises(RuntimeError):
                with _create_project(owl, org.id, name=name):
                    pass
        with pytest.raises(RuntimeError):
            with _create_org(owl, duncan.id, name=name):
                pass


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_get_and_list_projects(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with (
            _create_org(owl, duncan.id) as org,
            _create_org(owl, duncan.id, name="Personal", tier=PlanName.PRO) as personal,
        ):
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            assert org.name == "Company"
            assert personal.name == "Personal"
            with (
                _create_project(owl, org.id, "bear") as proj_bear,
                _create_project(owl, personal.id) as personal_default,
            ):
                with _create_project(owl, org.id, "Pear") as proj_pear:
                    with _create_project(owl, org.id, "pearl") as proj_pearl:
                        assert isinstance(proj_bear.id, str)
                        assert len(proj_bear.id) > 0
                        assert isinstance(proj_pear.id, str)
                        assert len(proj_pear.id) > 0

                        # Test fetch
                        project = owl.admin.organization.get_project(proj_bear.id)
                        assert isinstance(project, ProjectRead)
                        assert project.id == proj_bear.id
                        assert project.name == "bear"
                        assert isinstance(project.organization.members, list)
                        assert len(project.organization.members) == 1

                        project = owl.admin.organization.get_project(proj_pear.id)
                        assert isinstance(project, ProjectRead)
                        assert project.id == proj_pear.id
                        assert project.name == "Pear"

                        project = owl.admin.organization.get_project(proj_pearl.id)
                        assert isinstance(project, ProjectRead)
                        assert project.id == proj_pearl.id
                        assert project.name == "pearl"

                        project = owl.admin.organization.get_project(personal_default.id)
                        assert isinstance(project, ProjectRead)
                        assert project.id == personal_default.id
                        assert project.name == "default"

                        # Test association
                        org = owl.admin.backend.get_organization(org.id)
                        assert isinstance(org, OrganizationRead)
                        assert all(isinstance(p, ProjectRead) for p in org.projects)
                        proj_names = [p.name for p in org.projects]
                        assert "bear" in proj_names
                        assert "Pear" in proj_names
                        assert "pearl" in proj_names

                        # Test list
                        projects = owl.admin.organization.list_projects(org.id)
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.total == 3
                        assert projects.offset == 0
                        assert projects.limit == 100
                        assert len(projects.items) == 3

                        projects = owl.admin.organization.list_projects(personal.id)
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.total == 1
                        assert projects.offset == 0
                        assert projects.limit == 100
                        assert len(projects.items) == 1

                        projects = owl.admin.organization.list_projects(org.id, offset=1)
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.total == 3
                        assert projects.offset == 1
                        assert projects.limit == 100
                        assert len(projects.items) == 2

                        projects = owl.admin.organization.list_projects(org.id, limit=1)
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.total == 3
                        assert projects.offset == 0
                        assert projects.limit == 1
                        assert len(projects.items) == 1

                        # Test list with search query
                        projects = owl.admin.organization.list_projects(org.id, "ear")
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.total == 3
                        assert projects.offset == 0
                        assert projects.limit == 100
                        assert len(projects.items) == 3

                        projects = owl.admin.organization.list_projects(org.id, "pe")
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.total == 2
                        assert projects.offset == 0
                        assert projects.limit == 100
                        assert len(projects.items) == 2

                        projects = owl.admin.organization.list_projects(org.id, "pe", offset=1)
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.total == 2
                        assert projects.offset == 1
                        assert projects.limit == 100
                        assert len(projects.items) == 1

                        projects = owl.admin.organization.list_projects(org.id, "pe", limit=1)
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.total == 2
                        assert projects.offset == 0
                        assert projects.limit == 1
                        assert len(projects.items) == 1

                        # Test list with order_by
                        projects = owl.admin.organization.list_projects(org.id, "pe")
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.items[0].name == "pearl"
                        assert projects.items[1].name == "Pear"
                        assert projects.total == 2
                        assert projects.offset == 0
                        assert projects.limit == 100
                        assert len(projects.items) == 2

                        projects = owl.admin.organization.list_projects(
                            org.id, "pe", order_descending=False
                        )
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert projects.items[0].name == "Pear"
                        assert projects.items[1].name == "pearl"
                        assert projects.total == 2
                        assert projects.offset == 0
                        assert projects.limit == 100
                        assert len(projects.items) == 2

                        projects = owl.admin.organization.list_projects(org.id, order_by="name")
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert [p.name for p in projects.items] == ["pearl", "Pear", "bear"]
                        assert projects.total == 3
                        assert projects.offset == 0
                        assert projects.limit == 100
                        assert len(projects.items) == 3

                        projects = owl.admin.organization.list_projects(
                            org.id, order_by="name", order_descending=False
                        )
                        assert isinstance(projects.items, list)
                        assert all(isinstance(r, ProjectRead) for r in projects.items)
                        assert [p.name for p in projects.items] == ["bear", "Pear", "pearl"]
                        assert projects.total == 3
                        assert projects.offset == 0
                        assert projects.limit == 100
                        assert len(projects.items) == 3

                        for order_by in AdminOrderBy:
                            projects = owl.admin.organization.list_projects(
                                org.id, order_by=order_by
                            )
                            assert len(projects.items) == 3
                            proj_ids = [p.id for p in projects.items]
                            projects_desc = owl.admin.organization.list_projects(
                                org.id, order_by=order_by, order_descending=False
                            )
                            assert len(projects_desc.items) == 3
                            proj_desc_ids = [p.id for p in projects_desc.items]
                            assert (
                                proj_ids == proj_desc_ids[::-1]
                            ), f"Failed to order by {order_by}: {proj_ids} != {proj_desc_ids[::-1]}"

                        # # Test starting_after
                        # projects = owl.admin.organization.list_projects(
                        #     org.id, order_by="name", starting_after=proj_pearl.id
                        # )
                        # assert isinstance(projects.items, list)
                        # assert all(isinstance(r, ProjectRead) for r in projects.items)
                        # assert [p.name for p in projects.items] == ["Pear", "bear"]
                        # assert projects.total == 3
                        # assert projects.offset == 0
                        # assert projects.limit == 100
                        # assert len(projects.items) == 2


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_delete_projects(client_cls: Type[JamAI]):
    owl = client_cls()
    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            assert isinstance(org.id, str)
            assert len(org.id) > 0
            with _create_project(owl, org.id) as project:
                assert isinstance(project.id, str)
                assert len(project.id) > 0
                response = owl.admin.organization.delete_project(project.id)
                assert isinstance(response, OkResponse)
                with pytest.raises(RuntimeError, match="Project .+ is not found."):
                    owl.admin.organization.update_project(
                        ProjectUpdate(id=project.id, name="Updated Project")
                    )

                with pytest.raises(RuntimeError, match="Project .+ is not found."):
                    owl.admin.organization.get_project(project.id)

                response = owl.admin.organization.delete_project(project.id)
                assert isinstance(response, OkResponse)
                with pytest.raises(RuntimeError, match="Project .+ is not found."):
                    owl.admin.organization.delete_project(project.id, missing_ok=False)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_update_project(client_cls: Type[JamAI]):
    owl = client_cls()

    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
            with _create_project(owl, org.id) as project:
                updated_project_request = ProjectUpdate(id=project.id, name="Updated Project")
                updated_project_response = owl.admin.organization.update_project(
                    updated_project_request
                )
                assert isinstance(updated_project_response, ProjectRead)
                assert updated_project_response.id == project.id
                assert updated_project_response.name == "Updated Project"


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_project_updated_at(client_cls: Type[JamAI]):
    owl = client_cls()

    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id) as org:
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
            with _create_project(owl, org.id) as project:
                assert isinstance(project.id, str)
                assert len(project.id) > 0
                old_proj_updated_at = project.updated_at
                jamai = JamAI(project_id=project.id)
                # Test gen table
                with _create_gen_table(jamai, TABLE_TYPES[0], "xx"):
                    pass

                @retry(
                    wait=wait_exponential(multiplier=1, min=1, max=10),
                    stop=stop_after_attempt(5),
                    reraise=True,
                )
                def _assert_bumped_updated_at():
                    proj = owl.admin.organization.get_project(project.id)
                    assert isinstance(proj, ProjectRead)
                    assert proj.updated_at > old_proj_updated_at

                t0 = perf_counter()
                _assert_bumped_updated_at()
                logger.info(f"Succeeded after {perf_counter() - t0:,.2f} seconds")


def test_project_update_model():
    sig = signature(ProjectUpdate)
    for name, param in sig.parameters.items():
        if name == "id":
            continue
        assert (
            param.default is None
        ), f'Parameter "{name}" has a default value of {param.default} instead of None.'


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("empty_project", [True, False], ids=["Empty project", "With data"])
def test_project_import_export_round_trip(client_cls: Type[JamAI], empty_project: bool):
    owl = client_cls()

    with _create_user(owl) as duncan:
        with (
            _create_org(owl, duncan.id, name="Personal", tier=PlanName.PRO) as o0,
            _create_org(owl, duncan.id, name="Company", tier=PlanName.PRO) as o1,
        ):
            assert isinstance(o0.id, str)
            assert len(o0.id) > 0
            assert isinstance(o1.id, str)
            assert len(o1.id) > 0
            assert o0.id != o1.id
            # Add credit
            owl.admin.backend.add_event(
                EventCreate(
                    id=f"{o0.quota_reset_at}_credit_{uuid7_str()}",
                    organization_id=o0.id,
                    values={ProductType.CREDIT: 20.0},
                )
            )
            with _create_project(owl, o0.id) as p0, _create_project(owl, o0.id, "p1") as p1:
                assert isinstance(p0.id, str)
                assert len(p0.id) > 0
                # Create some tables
                jamai = JamAI(project_id=p0.id)
                if not empty_project:
                    for table_type in TABLE_TYPES:
                        with _create_gen_table(jamai, table_type, table_type, delete=False):
                            _add_row(jamai, table_type, table_type)

                def _check_tables(_project_id: str):
                    jamai = JamAI(project_id=_project_id)
                    if empty_project:
                        for table_type in TABLE_TYPES:
                            assert jamai.table.list_tables(table_type).total == 0
                    else:
                        for table_type in TABLE_TYPES:
                            assert jamai.table.list_tables(table_type).total == 1
                            rows = jamai.table.list_table_rows(table_type, table_type)
                            assert len(rows.items) == 1

                # --- Export --- #
                data = jamai.admin.organization.export_project(p0.id)

                # --- Import as new project --- #
                # Test file-like object
                with BytesIO(data) as f:
                    new_p0 = jamai.admin.organization.import_project(f, o0.id)
                assert isinstance(new_p0, ProjectRead)
                _check_tables(new_p0.id)
                # List the projects
                proj_ids = set(p.id for p in owl.admin.organization.list_projects(o0.id).items)
                assert len(proj_ids) == 3  # Also ensures uniqueness
                assert p0.id in proj_ids
                assert p1.id in proj_ids
                assert new_p0.id in proj_ids

                # --- Import into existing project --- #
                # Test file path
                with TemporaryDirectory() as tmp_dir:
                    export_filepath = join(tmp_dir, "project.parquet")
                    with open(export_filepath, "wb") as f:
                        f.write(data)
                    new_p1 = jamai.admin.organization.import_project(export_filepath, o0.id, p1.id)
                assert isinstance(new_p1, ProjectRead)
                assert new_p1.id == p1.id
                _check_tables(new_p1.id)
                # List the projects
                proj_ids = set(p.id for p in owl.admin.organization.list_projects(o0.id).items)
                assert len(proj_ids) == 3  # Also ensures uniqueness
                assert p0.id in proj_ids
                assert p1.id in proj_ids
                assert new_p0.id in proj_ids

                # --- Import again, should fail --- #
                if not empty_project:
                    with BytesIO(data) as f:
                        with pytest.raises(RuntimeError):
                            jamai.admin.organization.import_project(f, o0.id, p1.id)

            # --- Import into another organization --- #
            with BytesIO(data) as f:
                project = JamAI().admin.organization.import_project(f, o1.id)
            assert isinstance(project, ProjectRead)
            _check_tables(project.id)
            # List the projects
            proj_ids = set(p.id for p in owl.admin.organization.list_projects(o1.id).items)
            assert len(proj_ids) == 1
            assert project.id in proj_ids


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("empty_project", [True, False], ids=["Empty project", "With data"])
def test_project_import_export_template(client_cls: Type[JamAI], empty_project: bool):
    owl = client_cls()

    with _create_user(owl) as duncan:
        with _create_org(owl, duncan.id, name="Personal") as o0:
            assert isinstance(o0.id, str)
            assert len(o0.id) > 0
            # Add credit
            owl.admin.backend.add_event(
                EventCreate(
                    id=f"{o0.quota_reset_at}_credit_{uuid7_str()}",
                    organization_id=o0.id,
                    values={ProductType.CREDIT: 20.0},
                )
            )
            with (
                _create_project(owl, o0.id) as p0,
                _create_project(owl, o0.id, "p1") as p1,
                _create_project(owl, o0.id, "p2") as p2,
            ):
                assert isinstance(p0.id, str)
                assert len(p0.id) > 0
                # Create some tables
                jamai = JamAI(project_id=p0.id)
                if not empty_project:
                    for table_type in TABLE_TYPES:
                        with _create_gen_table(jamai, table_type, table_type, delete=False):
                            _add_row(jamai, table_type, table_type)

                def _check_tables(_project_id: str):
                    jamai = JamAI(project_id=_project_id)
                    if empty_project:
                        for table_type in TABLE_TYPES:
                            assert jamai.table.list_tables(table_type).total == 0
                    else:
                        for table_type in TABLE_TYPES:
                            assert jamai.table.list_tables(table_type).total == 1
                            rows = jamai.table.list_table_rows(table_type, table_type)
                            assert len(rows.items) == 1

                # --- Export template --- #
                data = jamai.admin.organization.export_project_as_template(
                    p0.id,
                    name="Template 试验",
                    tags=["sector:finance", "sector:科技"],
                    description="テンプレート description",
                )
                with BytesIO(data) as f:
                    # Import as new project
                    new_p0 = jamai.admin.organization.import_project(f, o0.id)
                    assert isinstance(new_p0, ProjectRead)
                    _check_tables(new_p0.id)
                    # Import into existing project
                    new_p1 = jamai.admin.organization.import_project(f, o0.id, p1.id)
                    assert isinstance(new_p1, ProjectRead)
                    assert new_p1.id == p1.id
                    _check_tables(new_p1.id)
                    # List the projects
                    proj_ids = set(p.id for p in owl.admin.organization.list_projects(o0.id).items)
                    assert len(proj_ids) == 4  # Also ensures uniqueness
                    assert p0.id in proj_ids
                    assert p1.id in proj_ids
                    assert p2.id in proj_ids
                    assert new_p0.id in proj_ids

                    # --- Add template --- #
                    new_template_id = "test_template"
                    response = jamai.admin.backend.add_template(f, new_template_id, True)
                    assert isinstance(response, OkResponse)
                    # Add again, should fail
                    with pytest.raises(RuntimeError):
                        jamai.admin.backend.add_template(f, new_template_id)
                    # List templates
                    template_ids = set(t.id for t in jamai.template.list_templates().items)
                    assert new_template_id in template_ids
                    # Import as new project
                    new_p2 = jamai.admin.organization.import_project_from_template(
                        o0.id, new_template_id
                    )
                    assert isinstance(new_p2, ProjectRead)
                    _check_tables(new_p2.id)
                    # Import into existing project
                    new_p3 = jamai.admin.organization.import_project_from_template(
                        o0.id, new_template_id, p2.id
                    )
                    assert isinstance(new_p3, ProjectRead)
                    assert new_p3.id == p2.id
                    _check_tables(new_p3.id)
                    # List the projects
                    proj_ids = set(p.id for p in owl.admin.organization.list_projects(o0.id).items)
                    assert len(proj_ids) == 5  # Also ensures uniqueness
                    assert p0.id in proj_ids
                    assert p1.id in proj_ids
                    assert p2.id in proj_ids
                    assert new_p0.id in proj_ids
                    assert new_p2.id in proj_ids
