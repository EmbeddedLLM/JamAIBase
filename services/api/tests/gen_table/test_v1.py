from dataclasses import dataclass
from os.path import dirname, join, realpath
from tempfile import TemporaryDirectory

import pytest

from jamaibase import JamAI
from jamaibase.types import (
    ActionTableSchemaCreate,
    AddActionColumnSchema,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    ChatTableSchemaCreate,
    ChatThreadResponse,
    ColumnDropRequest,
    ColumnRenameRequest,
    ColumnReorderRequest,
    ColumnSchemaCreate,
    GenConfigUpdateRequest,
    KnowledgeTableSchemaCreate,
    MultiRowAddRequest,
    MultiRowCompletionResponse,
    MultiRowDeleteRequest,
    MultiRowRegenRequest,
    OkResponse,
    OrganizationCreate,
    Page,
    RowUpdateRequest,
    SearchRequest,
    TableDataImportRequest,
    TableImportRequest,
    TableMetaResponse,
)
from owl.types import (
    LLMGenConfig,
    TableType,
)
from owl.utils.crypt import generate_key
from owl.utils.test import (
    ELLM_DESCRIBE_CONFIG,
    ELLM_DESCRIBE_DEPLOYMENT,
    ELLM_EMBEDDING_CONFIG,
    ELLM_EMBEDDING_DEPLOYMENT,
    GPT_41_NANO_CONFIG,
    GPT_41_NANO_DEPLOYMENT,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_user,
)

TEST_DIR = dirname(dirname(realpath(__file__)))
TABLE_TYPES = [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]


@dataclass(slots=True)
class ServingContext:
    superuser_id: str
    superorg_id: str
    project_id: str
    llm_model_id: str
    desc_llm_model_id: str


@pytest.fixture(scope="module")
def setup():
    """
    Fixture to set up the necessary organization and projects for file tests.
    """
    with (
        # Create superuser
        create_user() as superuser,
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

        # Create models
        with (
            create_model_config(GPT_41_NANO_CONFIG) as llm_config,
            create_model_config(ELLM_DESCRIBE_CONFIG) as desc_llm_config,
            create_model_config(ELLM_EMBEDDING_CONFIG),
            create_model_config(RERANK_ENGLISH_v3_SMALL_CONFIG),
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
                    superorg_id=superorg.id,
                    project_id=p0.id,
                    llm_model_id=llm_config.id,
                    desc_llm_model_id=desc_llm_config.id,
                )


def _gen_id() -> str:
    return generate_key(8, "table-")


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_gen_table_v1(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="int", dtype="int"),
        ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                system_prompt="",
                prompt="",
                max_tokens=10,
            ),
        ),
    ]
    # Create table
    if table_type == TableType.ACTION:
        table = client.table.create_action_table(
            ActionTableSchemaCreate(id=_gen_id(), cols=cols), v1=True
        )
    elif table_type == TableType.KNOWLEDGE:
        table = client.table.create_knowledge_table(
            KnowledgeTableSchemaCreate(id=_gen_id(), cols=cols, embedding_model=""), v1=True
        )
    elif table_type == TableType.CHAT:
        cols = [
            ColumnSchemaCreate(id="User", dtype="str"),
            ColumnSchemaCreate(
                id="AI",
                dtype="str",
                gen_config=LLMGenConfig(
                    model="",
                    system_prompt="You are a wacky assistant.",
                    max_tokens=5,
                ),
            ),
        ] + cols
        table = client.table.create_chat_table(
            ChatTableSchemaCreate(id=_gen_id(), cols=cols), v1=True
        )
    else:
        raise ValueError(f"Unknown table type: {table_type}")
    assert isinstance(table, TableMetaResponse)
    cols = {c.id: c for c in table.cols}
    assert "int" in cols

    # Duplicate table
    new_table = client.table.duplicate_table(table_type, table_id_src=table.id, v1=True)
    assert isinstance(new_table, TableMetaResponse)
    assert new_table.id != table.id

    # Get table
    _table = client.table.get_table(table_type, table_id=table.id, v1=True)
    assert isinstance(_table, TableMetaResponse)
    assert _table.id == table.id

    # List tables
    tables = client.table.list_tables(table_type, v1=True)
    assert isinstance(tables, Page)
    assert len(tables.items) == 2
    assert tables.total == 2

    # Rename table
    table_id_dst = _gen_id()
    _table = client.table.rename_table(
        table_type, new_table.id, table_id_dst=table_id_dst, v1=True
    )
    assert isinstance(_table, TableMetaResponse)
    assert _table.id != new_table.id
    assert _table.id == table_id_dst
    new_table = _table

    # Delete table
    response = client.table.delete_table(table_type, table_id=new_table.id, v1=True)
    assert isinstance(response, OkResponse)

    # Add columns
    cols = [ColumnSchemaCreate(id="str", dtype="str")]
    if table_type == TableType.ACTION:
        table = client.table.add_action_columns(
            AddActionColumnSchema(id=table.id, cols=cols), v1=True
        )
    elif table_type == TableType.KNOWLEDGE:
        table = client.table.add_knowledge_columns(
            AddKnowledgeColumnSchema(id=table.id, cols=cols), v1=True
        )
    elif table_type == TableType.CHAT:
        table = client.table.add_chat_columns(AddChatColumnSchema(id=table.id, cols=cols), v1=True)
    else:
        raise ValueError(f"Unknown table type: {table_type}")
    assert isinstance(table, TableMetaResponse)
    cols = {c.id: c for c in table.cols}
    assert "int" in cols
    assert "str" in cols

    # Rename columns
    table = client.table.rename_columns(
        table_type,
        ColumnRenameRequest(table_id=table.id, column_map={"int": "integer"}),
        v1=True,
    )
    assert isinstance(table, TableMetaResponse)
    cols = {c.id: c for c in table.cols}
    assert "int" not in cols
    assert "integer" in cols

    # Update gen config
    table = client.table.update_gen_config(
        table_type,
        GenConfigUpdateRequest(table_id=table.id, column_map={"summary": None}),
        v1=True,
    )
    assert isinstance(table, TableMetaResponse)
    cols = {c.id: c for c in table.cols}
    assert cols["summary"].gen_config is None

    # Reorder columns
    if table_type == TableType.ACTION:
        table = client.table.reorder_columns(
            table_type,
            ColumnReorderRequest(table_id=table.id, column_names=["str", "integer", "summary"]),
            v1=True,
        )
        assert isinstance(table, TableMetaResponse)
        assert [c.id for c in table.cols][-3:] == ["str", "integer", "summary"]

    # Drop columns
    table = client.table.drop_columns(
        table_type,
        ColumnDropRequest(table_id=table.id, column_names=["integer"]),
        v1=True,
    )
    assert isinstance(table, TableMetaResponse)
    cols = {c.id: c for c in table.cols}
    assert "integer" not in cols

    # Add rows
    response = client.table.add_table_rows(
        table_type,
        MultiRowAddRequest(
            table_id=table.id, data=[{"str": "foo", "summary": "bar"}] * 3, stream=False
        ),
        v1=True,
    )
    assert isinstance(response, MultiRowCompletionResponse)
    assert len(response.rows) == 3

    # List rows
    rows = client.table.list_table_rows(table_type, table.id, v1=True)
    assert isinstance(rows, Page)
    assert len(rows.items) == 3
    assert rows.total == 3
    for row in rows.items:
        assert "value" in row["str"]

    # List rows (V1 value bug)
    rows = client.table.list_table_rows(table_type, table.id, columns=["str"], v1=True)
    assert isinstance(rows, Page)
    assert len(rows.items) == 3
    assert rows.total == 3
    for row in rows.items:
        assert "value" not in row["str"]

    # Get row
    row_id = rows.items[0]["ID"]
    row = client.table.get_table_row(table_type, table.id, row_id, v1=True)
    assert isinstance(row, dict)

    # Get conversation thread
    if table_type == TableType.CHAT:
        thread = client.table.get_conversation_thread(table_type, table.id, "AI")
        assert isinstance(thread, ChatThreadResponse)

    # Hybrid search
    response = client.table.hybrid_search(
        table_type,
        SearchRequest(table_id=table.id, query="foo"),
        v1=True,
    )
    assert isinstance(response, list)
    assert len(response) == 3

    # Regen rows
    response = client.table.regen_table_rows(
        table_type,
        MultiRowRegenRequest(table_id=table.id, row_ids=[row_id], stream=False),
        v1=True,
    )
    assert isinstance(response, MultiRowCompletionResponse)
    assert len(response.rows) == 1

    # Update row
    response = client.table.update_table_row(
        table_type,
        RowUpdateRequest(table_id=table.id, row_id=row_id, data={"str": "baz"}),
    )
    assert isinstance(response, OkResponse)

    # Delete rows
    response = client.table.delete_table_rows(
        table_type,
        MultiRowDeleteRequest(table_id=table.id, row_ids=[row_id]),
        v1=True,
    )
    assert isinstance(response, OkResponse)

    # Delete row
    response = client.table.delete_table_row(table_type, table.id, rows.items[1]["ID"])
    assert isinstance(response, OkResponse)

    # Data import export
    csv_bytes = client.table.export_table_data(table_type, table.id, v1=True)
    assert len(csv_bytes) > 0
    with TemporaryDirectory() as tmp_dir:
        fp = join(tmp_dir, "test.csv")
        with open(fp, "wb") as f:
            f.write(csv_bytes)
        response = client.table.import_table_data(
            table_type,
            TableDataImportRequest(file_path=fp, table_id=table.id, stream=False),
            v1=True,
        )
        assert isinstance(response, MultiRowCompletionResponse)
        assert len(response.rows) == 1

    # Table import export
    parquet_bytes = client.table.export_table(table_type, table.id, v1=True)
    assert len(parquet_bytes) > 0
    with TemporaryDirectory() as tmp_dir:
        fp = join(tmp_dir, "test.parquet")
        with open(fp, "wb") as f:
            f.write(parquet_bytes)
        _table = client.table.import_table(
            table_type,
            TableImportRequest(file_path=fp, table_id_dst=_gen_id()),
            v1=True,
        )
        assert isinstance(_table, TableMetaResponse)
        assert _table.id != table.id

    # Embed file
    if table_type == TableType.KNOWLEDGE:
        with TemporaryDirectory() as tmp_dir:
            fp = join(tmp_dir, "test.txt")
            with open(fp, "w") as f:
                f.write("Lorem ipsum")
            response = client.table.embed_file(fp, table.id, v1=True)
            assert isinstance(response, OkResponse)
