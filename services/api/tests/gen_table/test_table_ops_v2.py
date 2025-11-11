from copy import deepcopy
from dataclasses import dataclass
from os.path import dirname, join, realpath
from tempfile import TemporaryDirectory

import pytest
from sqlmodel import text

from jamaibase import JamAI
from jamaibase.types import (
    AddActionColumnSchema,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    ColumnSchemaCreate,
    GenConfigUpdateRequest,
    OkResponse,
    OrganizationCreate,
    OrgMemberRead,
    ProjectMemberRead,
    RAGParams,
    TableImportRequest,
    TableMetaResponse,
)
from owl.db import sync_session
from owl.types import (
    LLMGenConfig,
    Role,
    TableType,
)
from owl.utils.exceptions import BadInputError, ResourceNotFoundError
from owl.utils.test import (
    ELLM_DESCRIBE_CONFIG,
    ELLM_DESCRIBE_DEPLOYMENT,
    ELLM_EMBEDDING_CONFIG,
    ELLM_EMBEDDING_DEPLOYMENT,
    GPT_41_NANO_CONFIG,
    GPT_41_NANO_DEPLOYMENT,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    add_table_rows,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_table,
    create_user,
    list_table_rows,
    list_tables,
)

TEST_DIR = dirname(dirname(realpath(__file__)))
TABLE_TYPES = [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]


@dataclass(slots=True)
class ServingContext:
    superuser_id: str
    user_id: str
    superorg_id: str
    project_id: str
    llm_model_id: str
    desc_llm_model_id: str
    rerank_model_id: str


@pytest.fixture(scope="module")
def setup():
    """
    Fixture to set up the necessary organization and projects for file tests.
    """
    with (
        # Create superuser and user
        create_user() as superuser,
        create_user(dict(email="user@up.com", name="User")) as user,
        # Create organization
        create_organization(
            body=OrganizationCreate(name="Clubhouse"), user_id=superuser.id
        ) as superorg,
        # Create project
        create_project(
            dict(name="Project"), user_id=superuser.id, organization_id=superorg.id
        ) as p0,
    ):
        assert superuser.id == "0"
        assert superorg.id == "0"
        # Join organization and project as member
        client = JamAI(user_id=superuser.id)
        membership = client.organizations.join_organization(
            user.id,
            organization_id=superorg.id,
            role=Role.MEMBER,
        )
        assert isinstance(membership, OrgMemberRead)
        membership = client.projects.join_project(
            user.id,
            project_id=p0.id,
            role=Role.MEMBER,
        )
        assert isinstance(membership, ProjectMemberRead)

        # Create models
        gpt_config = deepcopy(GPT_41_NANO_CONFIG)
        gpt_config.name = "A OpenAI GPT-4.1 nano"
        with (
            # Purposely include a model name that starts with A to test default model sorting
            create_model_config(gpt_config) as llm_config,
            # Default model should still prefer ELLM model
            create_model_config(ELLM_DESCRIBE_CONFIG) as desc_llm_config,
            create_model_config(ELLM_EMBEDDING_CONFIG),
            create_model_config(RERANK_ENGLISH_v3_SMALL_CONFIG) as rerank_config,
        ):
            # Create deployments
            with (
                create_deployment(GPT_41_NANO_DEPLOYMENT),
                create_deployment(ELLM_DESCRIBE_DEPLOYMENT),
                create_deployment(ELLM_EMBEDDING_DEPLOYMENT),
                create_deployment(RERANK_ENGLISH_v3_SMALL_DEPLOYMENT),
            ):
                yield ServingContext(
                    superuser_id=superuser.id,
                    user_id=user.id,
                    superorg_id=superorg.id,
                    project_id=p0.id,
                    llm_model_id=llm_config.id,
                    desc_llm_model_id=desc_llm_config.id,
                    rerank_model_id=rerank_config.id,
                )


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_default_model_default_prompts(
    setup: ServingContext,
    table_type: TableType,
):
    """
    Test default model and prompts:
    - Default model
    - Default prompts
        - Table creation (should set default prompts)
        - Multi-turn column
        - Column add (should set default prompts)
        - Gen config update (should NOT set default prompts)

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="str", dtype="str"),
        # Default for system prompt and prompt
        ColumnSchemaCreate(
            id="o1",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                system_prompt="",
                prompt="",
            ),
        ),
        ColumnSchemaCreate(id="float", dtype="float"),
        # Default for system prompt
        ColumnSchemaCreate(
            id="o2",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                system_prompt="",
                prompt="What is love?",
            ),
        ),
        # Default for prompt
        ColumnSchemaCreate(
            id="o3",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                system_prompt="Baby don't hurt me",
                prompt="",
            ),
        ),
        # Default for system prompt and prompt (multi-turn)
        ColumnSchemaCreate(
            id="o4",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                system_prompt="",
                prompt="",
                multi_turn=True,
            ),
        ),
    ]
    with create_table(client, table_type, cols=cols) as table:
        table = client.table.get_table(table_type, table.id)
        assert isinstance(table, TableMetaResponse)
        ### --- Default model --- ###
        for col in ["o1", "o2", "o3", "o4"]:
            gen_config = table.cfg_map[col]
            assert isinstance(gen_config, LLMGenConfig)
            assert gen_config.model == setup.desc_llm_model_id
        ### --- Default prompts --- ###
        default_sys_phrase = (
            "You are a versatile data generator. "
            "Your task is to process information from input data and generate appropriate responses based on the specified column name and input data."
        )
        # Table creation
        assert default_sys_phrase in table.cfg_map["o1"].system_prompt
        assert default_sys_phrase in table.cfg_map["o2"].system_prompt
        assert table.cfg_map["o3"].system_prompt == "Baby don't hurt me"
        assert "You are an agent named" in table.cfg_map["o4"].system_prompt

        def _check_prompt(prompt: str):
            assert "${str}" in prompt
            assert "${ID}" not in prompt  # Info columns
            assert "${Updated at}" not in prompt  # Info columns
            if table_type == TableType.KNOWLEDGE:
                assert "${Title}" in prompt
                assert "${Text}" in prompt
                assert "${File ID}" in prompt
                assert "${Page}" in prompt
                assert "${Title Embed}" not in prompt  # Vector columns
                assert "${Text Embed}" not in prompt  # Vector columns
            elif table_type == TableType.CHAT:
                assert "${User}" in prompt

        gen_config = table.cfg_map["o1"]
        assert "${float}" not in gen_config.prompt  # Columns on its right
        _check_prompt(gen_config.prompt)
        assert table.cfg_map["o2"].prompt == "What is love?"
        gen_config = table.cfg_map["o3"]
        assert "${float}" in gen_config.prompt
        _check_prompt(gen_config.prompt)
        gen_config = table.cfg_map["o4"]
        assert "${float}" in gen_config.prompt
        _check_prompt(gen_config.prompt)
        # Column add
        cols = [
            ColumnSchemaCreate(
                id="o5",
                dtype="str",
                gen_config=LLMGenConfig(
                    model="",
                    system_prompt="",
                    prompt="",
                ),
            ),
        ]
        if table_type == TableType.ACTION:
            client.table.add_action_columns(AddActionColumnSchema(id=table.id, cols=cols))
        elif table_type == TableType.KNOWLEDGE:
            client.table.add_knowledge_columns(AddKnowledgeColumnSchema(id=table.id, cols=cols))
        else:
            client.table.add_chat_columns(AddChatColumnSchema(id=table.id, cols=cols))
        table = client.table.get_table(table_type, table.id)
        gen_config = table.cfg_map["o5"]
        assert default_sys_phrase in gen_config.system_prompt
        assert "${float}" in gen_config.prompt
        _check_prompt(gen_config.prompt)
        # Update gen config to empty prompt
        client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map={
                    "o5": LLMGenConfig(
                        model="",
                        system_prompt="",
                        prompt="",
                    )
                },
            ),
        )
        table = client.table.get_table(table_type, table.id)
        gen_config = table.cfg_map["o5"]
        assert isinstance(gen_config, LLMGenConfig)
        assert gen_config.model == setup.desc_llm_model_id  # Default model
        assert gen_config.system_prompt == ""
        assert gen_config.prompt == ""


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_delete_table(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        # Delete
        response = client.table.delete_table(table_type, table.id)
        assert isinstance(response, OkResponse)
        # After deleting
        with pytest.raises(ResourceNotFoundError, match="is not found."):
            client.table.get_table(table_type, table.id)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_get_list_tables(
    setup: ServingContext,
    table_type: TableType,
):
    """
    Test get table and list tables.
    - offset and limit
    - order_by and order_ascending
    - created_by
    - parent_id (list project with agents, chat agent, chat, all tables)
    - search_query

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
    """
    super_client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [ColumnSchemaCreate(id="int", dtype="int")]

    ### --- Test get and list on DB without schemas --- ###
    with sync_session() as session:
        for table_type in TableType:
            session.exec(text(f'DROP SCHEMA IF EXISTS "{setup.project_id}_{table_type}" CASCADE'))
        session.commit()
    tables = list_tables(client, table_type)
    assert len(tables.items) == 0
    assert tables.total == 0
    with pytest.raises(ResourceNotFoundError, match="Table .+ is not found."):
        client.table.get_table(table_type, "123")

    ### --- Create tables --- ###
    with (
        create_table(super_client, table_type, "Table 2", cols=cols) as t0,
        create_table(super_client, table_type, "table 1", cols=cols) as t1,
        create_table(client, table_type, "Table 0", cols=cols) as t2,
    ):
        assert isinstance(t0, TableMetaResponse)
        assert isinstance(t1, TableMetaResponse)
        assert isinstance(t2, TableMetaResponse)
        num_tables = 3
        ### --- List tables --- ###
        tables = list_tables(client, table_type)
        assert len(tables.items) == num_tables
        assert tables.total == num_tables
        assert [t.id for t in tables.items] == [t0.id, t1.id, t2.id]

        ### --- Get table --- ###
        for table in tables.items:
            _table = client.table.get_table(table_type, table.id)
            assert isinstance(_table, TableMetaResponse)
            assert _table.model_dump(exclude={"num_rows"}) == table.model_dump(
                exclude={"num_rows"}
            )

        ### --- List tables (case-insensitive sort) --- ###
        _tables = list_tables(client, table_type, order_by="id")
        assert _tables.total == num_tables
        assert [t.id for t in _tables.items] == [t2.id, t1.id, t0.id]

        ### --- List tables (offset and limit) --- ###
        _tables = list_tables(client, table_type, offset=0, limit=1)
        assert len(_tables.items) == 1
        assert _tables.total == num_tables
        assert _tables.items[0].id == tables.items[0].id, f"{_tables.items=}"
        _tables = list_tables(client, table_type, offset=1, limit=1)
        assert len(_tables.items) == 1
        assert _tables.total == num_tables
        assert _tables.items[0].id == tables.items[1].id, f"{_tables.items=}"
        # Offset >= num tables
        _tables = list_tables(client, table_type, offset=num_tables, limit=1)
        assert len(_tables.items) == 0
        assert _tables.total == num_tables
        _tables = list_tables(client, table_type, offset=num_tables + 1, limit=1)
        assert len(_tables.items) == 0
        assert _tables.total == num_tables
        # Invalid offset and limit
        with pytest.raises(BadInputError):
            list_tables(client, table_type, offset=0, limit=0)
        with pytest.raises(BadInputError):
            list_tables(client, table_type, offset=-1, limit=1)

        ### --- List tables (order_by and order_ascending) --- ###
        _tables = list_tables(client, table_type, order_ascending=False)
        assert len(tables.items) == num_tables
        assert _tables.total == num_tables
        assert [t.id for t in _tables.items[::-1]] == [t.id for t in tables.items]
        _tables = list_tables(client, table_type, order_by="id")
        assert len(tables.items) == num_tables
        assert _tables.total == num_tables
        assert [t.id for t in _tables.items[::-1]] == [t.id for t in tables.items]

        ### --- List tables (created_by) --- ###
        _tables = list_tables(client, table_type, created_by=setup.superuser_id)
        assert len(_tables.items) == 2
        assert _tables.total == 2
        assert _tables.total != num_tables
        _tables = list_tables(client, table_type, created_by=setup.user_id)
        assert len(_tables.items) == 1
        assert _tables.total == 1
        assert _tables.total != num_tables

        ### --- List tables (parent_id) --- ###
        if table_type == TableType.CHAT:
            # Create a child table
            _table = client.table.duplicate_table(table_type, t0.id, None, create_as_child=True)
            try:
                assert isinstance(_table, TableMetaResponse)
                # List projects with chat agent list
                projects = client.projects.list_projects(setup.superorg_id, list_chat_agents=True)
                assert len(projects.items) == 1
                assert projects.total == 1
                _project = projects.items[0]
                assert len(_project.chat_agents) == num_tables
                # List all chat agents
                _tables = list_tables(client, table_type, parent_id="_agent_")
                assert len(_tables.items) == num_tables
                assert _tables.total == num_tables
                assert {t.id for t in _tables.items} == {t.id for t in _project.chat_agents}
                _tables = list_tables(client, table_type, parent_id="_agent_", offset=1)
                assert len(_tables.items) == num_tables - 1
                assert _tables.total == num_tables
                # List all chats
                _tables = list_tables(client, table_type, parent_id="_chat_")
                assert len(_tables.items) == 1
                assert _tables.total == 1
                # List all tables
                _tables = list_tables(client, table_type, parent_id=None)
                assert len(_tables.items) == num_tables + 1
                assert _tables.total == num_tables + 1
            finally:
                client.table.delete_table(table_type, _table.id)

        ### --- List tables (search_query) --- ###
        _tables = list_tables(client, table_type, search_query="1")
        assert len(_tables.items) == 1
        assert _tables.total == 1
        assert _tables.total != num_tables
        assert _tables.items[0].id == t1.id
        _tables = list_tables(client, table_type, search_query="1", offset=1)
        assert len(_tables.items) == 0
        assert _tables.total == 1


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_update_gen_config(
    setup: ServingContext,
    table_type: TableType,
):
    """
    Test updating table generation config:
    - Partial update
    - Switch to/from None
    - Chat AI column must always have gen config
    - Chat AI column multi-turn must always be True
    - Invalid column reference
    - Invalid LLM model
    - Invalid knowledge table ID
    - Invalid reranker model

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="i0", dtype="str"),
        ColumnSchemaCreate(id="o0", dtype="str", gen_config=LLMGenConfig()),
        ColumnSchemaCreate(id="o1", dtype="str", gen_config=None),
    ]
    with (
        create_table(client, TableType.KNOWLEDGE) as kt,
        create_table(client, table_type, cols=cols) as table,
    ):
        assert isinstance(table.cfg_map["o0"], LLMGenConfig)
        assert len(table.cfg_map["o0"].system_prompt) > 0
        assert len(table.cfg_map["o0"].prompt) > 0
        assert table.cfg_map["o1"] is None
        if table_type == TableType.CHAT:
            assert isinstance(table.cfg_map["AI"], LLMGenConfig)

        # --- Partial update --- #
        old_cfg = table.cfg_map["o0"].model_dump()
        # Update prompt
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(o0=LLMGenConfig(prompt="test")),
            ),
        )
        assert isinstance(table, TableMetaResponse)
        assert isinstance(table.cfg_map["o0"], LLMGenConfig)
        assert len(table.cfg_map["o0"].system_prompt) > 0
        assert table.cfg_map["o0"].prompt == "test"
        new_cfg = table.cfg_map["o0"].model_dump()
        assert old_cfg != new_cfg
        old_cfg["prompt"] = "test"
        assert old_cfg == new_cfg

        # --- Switch to/from None --- #
        # Flip configs
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(o0=None, o1=LLMGenConfig()),
            ),
        )
        assert isinstance(table, TableMetaResponse)
        assert table.cfg_map["o0"] is None
        assert isinstance(table.cfg_map["o1"], LLMGenConfig)
        assert len(table.cfg_map["o1"].system_prompt) == 0
        assert len(table.cfg_map["o1"].prompt) == 0
        if table_type == TableType.CHAT:
            assert isinstance(table.cfg_map["AI"], LLMGenConfig)

        # --- Chat AI column must always have gen config --- #
        # --- Chat AI column multi-turn must always be True --- #
        if table_type == TableType.CHAT:
            table = client.table.update_gen_config(
                table_type,
                GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(AI=None),
                ),
            )
            assert isinstance(table, TableMetaResponse)
            assert isinstance(table.cfg_map["AI"], LLMGenConfig)
            table.cfg_map["AI"].multi_turn = False
            table = client.table.update_gen_config(
                table_type,
                GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(AI=table.cfg_map["AI"]),
                ),
            )
            assert isinstance(table, TableMetaResponse)
            assert isinstance(table.cfg_map["AI"], LLMGenConfig)
            assert table.cfg_map["AI"].multi_turn is True

        # --- Invalid column reference --- #
        with pytest.raises(BadInputError, match="invalid source columns"):
            table = client.table.update_gen_config(
                table_type,
                GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(o1=LLMGenConfig(prompt="${o2}")),
                ),
            )
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(o1=LLMGenConfig(prompt="${o0}")),
            ),
        )
        assert table.cfg_map["o1"].prompt == "${o0}"

        # --- Invalid LLM model --- #
        with pytest.raises(BadInputError, match="LLM model .+ is not found"):
            table = client.table.update_gen_config(
                table_type,
                GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(o0=LLMGenConfig(model="INVALID")),
                ),
            )
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(o0=LLMGenConfig(model=setup.llm_model_id)),
            ),
        )
        assert table.cfg_map["o0"].model == setup.llm_model_id

        # --- Invalid knowledge table ID --- #
        with pytest.raises(BadInputError, match="Knowledge Table .+ does not exist"):
            table = client.table.update_gen_config(
                table_type,
                GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(
                        o0=LLMGenConfig(rag_params=RAGParams(table_id="INVALID")),
                    ),
                ),
            )
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    o0=LLMGenConfig(rag_params=RAGParams(table_id=kt.id)),
                ),
            ),
        )
        assert isinstance(table.cfg_map["o0"].rag_params, RAGParams)
        assert table.cfg_map["o0"].rag_params.table_id == kt.id

        # --- Invalid reranker model --- #
        with pytest.raises(BadInputError, match="Reranking model .+ is not found"):
            table = client.table.update_gen_config(
                table_type,
                GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(
                        o0=LLMGenConfig(rag_params=RAGParams(reranking_model="INVALID")),
                    ),
                ),
            )
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    o0=LLMGenConfig(
                        rag_params=RAGParams(reranking_model=setup.rerank_model_id),
                    ),
                ),
            ),
        )
        assert isinstance(table.cfg_map["o0"].rag_params, RAGParams)
        assert table.cfg_map["o0"].rag_params.reranking_model == setup.rerank_model_id
        assert table.cfg_map["o0"].rag_params.table_id == kt.id


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_long_table_column_ids(
    setup: ServingContext,
    table_type: TableType,
):
    """
    Test various table and row operations on a table with long table and column IDs (100 characters).
    - Check default prompts
    - Update gen config
    - Rename table and column
    - Add row before and after:
      - Table and column renames
      - Column add and drop
    - List rows
    - Hybrid search
    - RAG
    - Import and export

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # 100 characters
    kt_id = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen (0)"
    table_id = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen (1)"
    col_ids = [table_id, table_id.replace("one", "111"), table_id.replace("one", "112")]
    cols = [
        ColumnSchemaCreate(id=col_ids[0], dtype="str").model_dump(),
        ColumnSchemaCreate(
            id=col_ids[1], dtype="str", gen_config=LLMGenConfig(model=setup.desc_llm_model_id)
        ).model_dump(),
        ColumnSchemaCreate(
            id=col_ids[2],
            dtype="str",
            gen_config=LLMGenConfig(
                model=setup.desc_llm_model_id, rag_params=RAGParams(table_id=kt_id)
            ),
        ),
    ]
    with (
        create_table(client, TableType.KNOWLEDGE, table_id=kt_id, cols=[]) as kt,
        create_table(client, table_type, table_id=table_id, cols=cols) as table,
    ):
        assert kt.id == kt_id
        assert table.id == table_id
        col_map = {c.id: c for c in table.cols}
        # Add knowledge data
        add_table_rows(client, TableType.KNOWLEDGE, kt.id, [dict(), dict()], stream=False)
        rows = list_table_rows(client, TableType.KNOWLEDGE, kt.id)
        assert len(rows.values) == 2
        assert rows.total == 2
        # Check default prompts
        gen_cfg = col_map[col_ids[1]].gen_config
        assert isinstance(gen_cfg, LLMGenConfig)
        assert isinstance(gen_cfg.system_prompt, str)
        assert len(gen_cfg.system_prompt) > 1
        assert isinstance(gen_cfg.prompt, str)
        assert len(gen_cfg.prompt) > 1
        assert f'Table name: "{table.id}"' in gen_cfg.prompt
        assert f"{col_ids[0]}: ${{{col_ids[0]}}}" in gen_cfg.prompt
        assert f'column "{col_ids[1]}"' in gen_cfg.prompt
        # Update prompt and multi-turn
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map={
                    col_ids[1]: LLMGenConfig(prompt=f"${{{col_ids[0]}}}", multi_turn=True)
                },
            ),
        )
        assert isinstance(table, TableMetaResponse)
        # Add row
        row_data = {"Title": "", "Text": "", "User": "Hi", "AI": "Hello"}
        response = add_table_rows(
            client, table_type, table.id, [{col_ids[0]: "one", **row_data}], stream=False
        )
        content = response.rows[0].columns[col_ids[1]].content
        assert "System prompt: There is a text with [40] tokens." in content
        assert "There is a text with [1] tokens." in content
        # Rename table
        table_id_dst = table.id.replace("one", "two")
        table = client.table.rename_table(table_type, table.id, table_id_dst)
        assert isinstance(table, TableMetaResponse)
        assert table.id == table_id_dst
        # Rename column
        col_id_dst = col_ids[1].replace("111", "222")
        table = client.table.rename_columns(
            table_type,
            dict(table_id=table.id, column_map={col_ids[1]: col_id_dst}),
        )
        assert isinstance(table, TableMetaResponse)
        col_ids[1] = col_id_dst
        col_map = {c.id: c for c in table.cols}
        assert col_id_dst in col_map
        # Add row
        response = add_table_rows(
            client, table_type, table.id, [{col_ids[0]: "one two", **row_data}], stream=True
        )
        content = response.rows[0].columns[col_ids[1]].content
        assert "System prompt: There is a text with [40] tokens." in content
        assert "There is a text with [1] tokens." in content
        assert "There is a text with [2] tokens." in content
        # Add column
        new_col_id = col_ids[1].replace("222", "333")
        new_cols = [
            ColumnSchemaCreate(
                id=new_col_id, dtype="str", gen_config=LLMGenConfig(model=setup.desc_llm_model_id)
            ).model_dump(),
        ]
        if table_type == TableType.ACTION:
            table = client.table.add_action_columns(dict(id=table.id, cols=new_cols))
        elif table_type == TableType.KNOWLEDGE:
            table = client.table.add_knowledge_columns(dict(id=table.id, cols=new_cols))
        elif table_type == TableType.CHAT:
            table = client.table.add_chat_columns(dict(id=table.id, cols=new_cols))
        else:
            raise ValueError(f"Unknown table type: {table_type}")
        col_map = {c.id: c for c in table.cols}
        assert new_col_id in col_map
        # Check default prompts
        gen_cfg = col_map[new_col_id].gen_config
        assert isinstance(gen_cfg, LLMGenConfig)
        assert isinstance(gen_cfg.system_prompt, str)
        assert len(gen_cfg.system_prompt) > 1
        assert isinstance(gen_cfg.prompt, str)
        assert len(gen_cfg.prompt) > 1
        assert f'Table name: "{table.id}"' in gen_cfg.prompt
        assert f"{col_ids[0]}: ${{{col_ids[0]}}}" in gen_cfg.prompt
        assert f'column "{new_col_id}"' in gen_cfg.prompt
        # Add row
        response = add_table_rows(
            client, table_type, table.id, [{col_ids[0]: "a b c", **row_data}], stream=True
        )
        content = response.rows[0].columns[col_ids[1]].content
        assert "System prompt: There is a text with [40] tokens." in content
        assert "There is a text with [1] tokens." in content
        assert "There is a text with [2] tokens." in content
        assert "There is a text with [3] tokens." in content
        content = response.rows[0].columns[new_col_id].content
        assert "There is a text with" in content
        # Drop column
        table = client.table.drop_columns(
            table_type, dict(table_id=table.id, column_names=[new_col_id])
        )
        assert isinstance(table, TableMetaResponse)
        col_map = {c.id: c for c in table.cols}
        assert new_col_id not in col_map
        # Add row
        response = add_table_rows(
            client, table_type, table.id, [{col_ids[0]: "a b c d", **row_data}], stream=True
        )
        content = response.rows[0].columns[col_ids[1]].content
        assert "System prompt: There is a text with [40] tokens." in content
        assert "There is a text with [1] tokens." in content
        assert "There is a text with [2] tokens." in content
        assert "There is a text with [3] tokens." in content
        assert "There is a text with [4] tokens." in content
        assert len(response.rows[0].columns) == 2
        # List rows
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.values) == 4
        assert rows.total == 4
        for r in rows.references:
            assert len(r[col_ids[2]].chunks) == 2
        rows = list_table_rows(client, table_type, table.id, where=f""""{col_ids[1]}" ~* '3'""")
        assert len(rows.values) == 2
        assert rows.total == 2
        with pytest.raises(BadInputError):
            list_table_rows(client, table_type, table.id, where=f""""{col_ids[1]}" ~* 3""")
        # Hybrid search
        results = client.table.hybrid_search(
            table_type, dict(table_id=table.id, query="token", limit=2)
        )
        assert isinstance(results, list)
        assert len(results) == 2
        for r in results:
            assert "rrf_score" in r
            for c in col_ids:
                assert c in r
        # Export table
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, f"{table.id}.parquet")
            with open(file_path, "wb") as f:
                f.write(client.table.export_table(table_type, table.id))
            # Import table
            import_table_id = table.id.replace("(1)", "(2)")
            response = client.table.import_table(
                table_type,
                TableImportRequest(
                    file_path=file_path, table_id_dst=import_table_id, blocking=True
                ),
            )
            rows = list_table_rows(client, table_type, import_table_id)
            assert len(rows.values) == 4
            assert rows.total == 4
            for r in rows.references:
                assert len(r[col_ids[2]].chunks) == 2
