from contextlib import asynccontextmanager
from io import BytesIO
from typing import Type

import pytest

from jamaibase import JamAI, JamAIAsync
from jamaibase import types as t
from jamaibase.utils import run

CLIENT_CLS = [JamAI, JamAIAsync]
TABLE_TYPES = [t.TableType.action, t.TableType.knowledge, t.TableType.chat]


@asynccontextmanager
async def _create_gen_table(
    jamai: JamAI,
    table_type: t.TableType,
    table_id: str,
    model_id: str = "",
    cols: list[t.ColumnSchemaCreate] | None = None,
    chat_cols: list[t.ColumnSchemaCreate] | None = None,
    embedding_model: str = "",
    delete_first: bool = True,
    delete: bool = True,
):
    try:
        if delete_first:
            await run(jamai.table.delete_table, table_type, table_id)
        if cols is None:
            cols = [
                t.ColumnSchemaCreate(id="input", dtype="str"),
                t.ColumnSchemaCreate(
                    id="output",
                    dtype="str",
                    gen_config=t.LLMGenConfig(
                        model=model_id,
                        prompt="${input}",
                        max_tokens=3,
                    ),
                ),
            ]
        if chat_cols is None:
            chat_cols = [
                t.ColumnSchemaCreate(id="User", dtype="str"),
                t.ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=t.LLMGenConfig(
                        model=model_id,
                        system_prompt="You are an assistant.",
                        max_tokens=3,
                    ),
                ),
            ]
        if table_type == t.TableType.action:
            table = await run(
                jamai.table.create_action_table, t.ActionTableSchemaCreate(id=table_id, cols=cols)
            )
        elif table_type == t.TableType.knowledge:
            table = await run(
                jamai.table.create_knowledge_table,
                t.KnowledgeTableSchemaCreate(
                    id=table_id, cols=cols, embedding_model=embedding_model
                ),
            )
        elif table_type == t.TableType.chat:
            table = await run(
                jamai.table.create_chat_table,
                t.ChatTableSchemaCreate(id=table_id, cols=chat_cols + cols),
            )
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, t.TableMetaResponse)
        yield table
    finally:
        if delete:
            await run(jamai.table.delete_table, table_type, table_id)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_populate_templates(client_cls: Type[JamAI]):
    client = client_cls()
    response = await run(client.admin.backend.populate_templates)
    assert isinstance(response, t.OkResponse)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_list_templates(client_cls: Type[JamAI]):
    client = client_cls()
    response = await run(client.template.list_templates)
    assert len(response.items) == response.total
    templates = response.items
    assert len(templates) > 0
    assert all(isinstance(t, t.Template) for t in templates)
    for template in templates:
        assert len(template.id) > 0
        assert len(template.name) > 0


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_get_template(client_cls: Type[JamAI]):
    client = client_cls()
    # List templates
    templates = (await run(client.template.list_templates)).items
    assert len(templates) > 0
    template_id = templates[0].id
    # Fetch template
    template = await run(client.template.get_template, template_id)
    assert isinstance(template, t.Template)
    assert len(template.id) > 0
    assert len(template.name) > 0
    assert len(template.created_at) > 0
    assert len(template.tags) > 0
    assert all(isinstance(t, t.TemplateTag) for t in template.tags)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_list_tables(client_cls: Type[JamAI]):
    client = client_cls()
    # List templates
    templates = (await run(client.template.list_templates)).items
    assert len(templates) > 0
    template_id = templates[0].id
    # List tables
    tables: list[t.TableMetaResponse] = []
    for table_type in TABLE_TYPES:
        tables += (await run(client.template.list_tables, template_id, table_type)).items
    assert len(tables) > 0
    assert all(isinstance(t, t.TableMetaResponse) for t in tables)
    for table in tables:
        assert len(table.id) > 0
        assert len(table.cols) > 0
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        assert len(table.updated_at) > 0

    # Create a template by exporting default project
    async with _create_gen_table(client, "action", "b"):
        async with _create_gen_table(client, "action", "a"):
            data = await run(
                client.admin.organization.export_project_as_template,
                "default",
                name="Template 试验",
                tags=["sector:finance", "sector:科技"],
                description="テンプレート description",
            )
            new_template_id = "test_template"
            with BytesIO(data) as f:
                response = await run(client.admin.backend.add_template, f, new_template_id, True)
                assert isinstance(response, t.OkResponse)

    # Search query
    tables = (
        await run(client.template.list_tables, new_template_id, "action", search_query="xxx")
    ).items
    assert len(tables) == 0
    tables = (
        await run(client.template.list_tables, new_template_id, "action", search_query="a")
    ).items
    assert len(tables) == 1

    # Sort
    tables = (await run(client.template.list_tables, new_template_id, "action")).items
    assert [t.id for t in tables] == ["a", "b"]
    tables = (
        await run(client.template.list_tables, new_template_id, "action", order_descending=False)
    ).items
    assert [t.id for t in tables] == ["b", "a"]
    tables = (
        await run(
            client.template.list_tables,
            new_template_id,
            "action",
            order_by="id",
            order_descending=False,
        )
    ).items
    assert [t.id for t in tables] == ["a", "b"]

    # Offset and limit
    tables = (
        await run(
            client.template.list_tables,
            new_template_id,
            "action",
            offset=0,
            limit=1,
            order_by="id",
            order_descending=False,
        )
    ).items
    assert [t.id for t in tables] == ["a"]
    tables = (
        await run(
            client.template.list_tables,
            new_template_id,
            "action",
            offset=1,
            limit=1,
            order_by="id",
            order_descending=False,
        )
    ).items
    assert [t.id for t in tables] == ["b"]


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_get_table(client_cls: Type[JamAI]):
    client = client_cls()
    # Get template ID
    templates = (await run(client.template.list_templates)).items
    assert len(templates) > 0
    template_id = templates[0].id
    # Get table
    table_count = 0
    for table_type in TABLE_TYPES:
        tables = (await run(client.template.list_tables, template_id, table_type)).items
        if len(tables) == 0:
            continue
        table_count += len(tables)
        table_id = tables[0].id
        table = await run(client.template.get_table, template_id, table_type, table_id)
        assert isinstance(table, t.TableMetaResponse)
        assert len(table.id) > 0
        assert len(table.cols) > 0
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        assert len(table.updated_at) > 0
    assert table_count > 0


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_list_table_rows(client_cls: Type[JamAI]):
    client = client_cls()
    # Get template ID
    templates = (await run(client.template.list_templates)).items
    assert len(templates) > 0
    template_id = templates[0].id
    # Get table
    table_count = 0
    for table_type in TABLE_TYPES:
        tables = (await run(client.template.list_tables, template_id, table_type)).items
        if len(tables) == 0:
            continue
        table_count += len(tables)
        table_id = tables[0].id
        table = await run(client.template.get_table, template_id, table_type, table_id)
        assert isinstance(table, t.TableMetaResponse)
        assert len(table.id) > 0
        assert len(table.cols) > 0
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        assert len(table.updated_at) > 0
        # List rows
        rows = (
            await run(client.template.list_table_rows, template_id, table_type, table_id, limit=5)
        ).items
        assert len(rows) > 4
        assert all(isinstance(r, dict) for r in rows)
        for row in rows:
            assert len({"ID", "Updated at"} - set(row.keys())) == 0
        # Test starting_after
        subset = (
            await run(
                client.template.list_table_rows,
                template_id,
                table_type,
                table_id,
                starting_after=rows[1]["ID"],
                limit=2,
            )
        ).items
        assert subset[0]["ID"] == rows[2]["ID"]
        # Test starting_after + offset
        subset = (
            await run(
                client.template.list_table_rows,
                template_id,
                table_type,
                table_id,
                starting_after=rows[1]["ID"],
                offset=1,
                limit=2,
            )
        ).items
        assert subset[0]["ID"] == rows[3]["ID"]
        # Test vector decimal rounding
        subset = (
            await run(
                client.template.list_table_rows,
                template_id,
                table_type,
                table_id,
                starting_after=rows[1]["ID"],
                offset=1,
                limit=2,
                vec_decimals=-1,
            )
        ).items
        assert subset[0]["ID"] == rows[3]["ID"]
        subset = (
            await run(
                client.template.list_table_rows,
                template_id,
                table_type,
                table_id,
                starting_after=rows[1]["ID"],
                offset=1,
                limit=2,
                vec_decimals=1,
            )
        ).items
        assert subset[0]["ID"] == rows[3]["ID"]
    assert table_count > 0


if __name__ == "__main__":
    print(JamAI().template.list_templates())
