from contextlib import contextmanager
from time import sleep
from typing import Type

import pytest
from flaky import flaky

from jamaibase import JamAI
from jamaibase import protocol as p

CLIENT_CLS = [JamAI]
TABLE_TYPES = [p.TableType.action, p.TableType.knowledge, p.TableType.chat]

TABLE_ID_A = "documents"
TABLE_ID_B = "xx"
TABLE_ID_C = "yy"
TABLE_ID_X = "zz"
TEXT = """Arrival is a 2016 American science fiction drama film directed by Denis Villeneuve and adapted by Eric Heisserer."""


@pytest.fixture(scope="module", autouse=True)
def delete_tables():
    yield
    batch_size = 100
    jamai = JamAI()
    for table_type in TABLE_TYPES:
        offset, total = 0, 1
        while offset < total:
            tables = jamai.list_tables(table_type, offset, batch_size)
            assert isinstance(tables.items, list)
            for table in tables.items:
                jamai.delete_table(table_type, table.id)
            total = tables.total
            offset += batch_size


def _get_chat_model() -> str:
    models = JamAI().model_names(prefer="openai/gpt-3.5-turbo", capabilities=["chat"])
    return models[0]


def _get_embedding_model() -> str:
    models = JamAI().model_names(
        prefer="openai/text-embedding-3-small-512", capabilities=["embed"]
    )
    return models[0]


def _get_reranking_model() -> str:
    models = JamAI().model_names(prefer="cohere/rerank-english-v3.0", capabilities=["rerank"])
    return models[0]


@contextmanager
def _create_table(jamai: JamAI, table_type: p.TableType, name: str = TABLE_ID_A):
    jamai.delete_table(table_type, name)
    kwargs = dict(
        id=name,
        cols=[
            p.ColumnSchemaCreate(id="good", dtype=p.DtypeCreateEnum.bool_),
            p.ColumnSchemaCreate(id="words", dtype=p.DtypeCreateEnum.int_),
            p.ColumnSchemaCreate(id="stars", dtype=p.DtypeEnum.float_),
            p.ColumnSchemaCreate(id="inputs", dtype=p.DtypeCreateEnum.str_),
            p.ColumnSchemaCreate(
                id="summary",
                dtype=p.DtypeCreateEnum.str_,
                gen_config=p.ChatRequest(
                    model=_get_chat_model(),
                    messages=[
                        p.ChatEntry.system("You are a concise assistant."),
                        # Interpolate string and non-string input columns
                        p.ChatEntry.user("Summarise this in ${words} words:\n\n${inputs}"),
                    ],
                    temperature=0.001,
                    top_p=0.001,
                    max_tokens=10,
                ).model_dump(),
            ),
        ],
    )
    if table_type == p.TableType.action:
        table = jamai.create_action_table(p.ActionTableSchemaCreate(**kwargs))
    elif table_type == p.TableType.knowledge:
        table = jamai.create_knowledge_table(
            p.KnowledgeTableSchemaCreate(embedding_model=_get_embedding_model(), **kwargs)
        )
    elif table_type == p.TableType.chat:
        kwargs["cols"] = [
            p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
            p.ColumnSchemaCreate(
                id="AI",
                dtype=p.DtypeCreateEnum.str_,
                gen_config=p.ChatRequest(
                    model=_get_chat_model(),
                    messages=[p.ChatEntry.system("You are a wacky assistant.")],
                    temperature=0.001,
                    top_p=0.001,
                    max_tokens=5,
                ).model_dump(),
            ),
        ] + kwargs["cols"]
        table = jamai.create_chat_table(p.ChatTableSchemaCreate(**kwargs))
    else:
        raise ValueError(f"Invalid table type: {table_type}")
    try:
        yield table
    except Exception:
        raise
    finally:
        jamai.delete_table(table_type, name)


def _add_row(
    jamai: JamAI,
    table_type: p.TableType,
    stream: bool,
    table_name: str = TABLE_ID_A,
    data: dict | None = None,
):
    if data is None:
        data = dict(good=True, words=5, stars=7.9, inputs=TEXT)
    if table_type == p.TableType.action:
        pass
    elif table_type == p.TableType.knowledge:
        data["Title"] = "Dune: Part Two."
        data["Text"] = "Dune: Part Two is a 2024 American epic science fiction film."
    elif table_type == p.TableType.chat:
        data["User"] = "Tell me a joke."
    else:
        raise ValueError(f"Invalid table type: {table_type}")

    response = jamai.add_table_rows(
        table_type,
        p.RowAddRequest(table_id=table_name, data=[data], stream=stream),
    )
    return response if stream else response.rows[0]


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_delete_table(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table, _create_table(jamai, table_type, TABLE_ID_B):
        assert isinstance(table, p.TableMetaResponse)
        assert table.id == TABLE_ID_A
        assert isinstance(table.cols, list)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        # Delete table B
        table = jamai.get_table(table_type, TABLE_ID_B)
        assert isinstance(table, p.TableMetaResponse)
        jamai.delete_table(table_type, TABLE_ID_B)
        with pytest.raises(RuntimeError):
            jamai.get_table(table_type, TABLE_ID_B)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_add_drop_columns(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )

        # --- COLUMN ADD --- #
        cols = [
            p.ColumnSchemaCreate(id="add_bool", dtype=p.DtypeCreateEnum.bool_),
            p.ColumnSchemaCreate(id="add_int", dtype=p.DtypeCreateEnum.int_),
            p.ColumnSchemaCreate(id="add_float", dtype=p.DtypeCreateEnum.float_),
            p.ColumnSchemaCreate(id="add_str", dtype=p.DtypeCreateEnum.str_),
        ]
        expected_cols = {
            "ID",
            "Updated at",
            "good",
            "words",
            "stars",
            "inputs",
            "summary",
            "add_bool",
            "add_int",
            "add_float",
            "add_str",
        }
        if table_type == p.TableType.action:
            table = jamai.add_action_columns(p.AddActionColumnSchema(id=TABLE_ID_A, cols=cols))
        elif table_type == p.TableType.knowledge:
            table = jamai.add_knowledge_columns(
                p.AddKnowledgeColumnSchema(id=TABLE_ID_A, cols=cols)
            )
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID"}
        elif table_type == p.TableType.chat:
            expected_cols |= {"User", "AI"}
            table = jamai.add_chat_columns(p.AddChatColumnSchema(id=TABLE_ID_A, cols=cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        # Existing row of new columns should contain None
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 1
        row = rows.items[0]
        for col in ["add_bool", "add_int", "add_float", "add_str"]:
            assert row[col]["value"] is None
        # Test adding new row
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(
                good=True,
                words=5,
                stars=9.9,
                inputs=TEXT,
                summary="<dummy>",
                add_bool=False,
                add_int=0,
                add_float=1.0,
                add_str="pretty",
            ),
        )
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 2
        row = rows.items[0]  # Should retrieve the latest row
        for col in ["add_bool", "add_int", "add_float", "add_str"]:
            assert row[col]["value"] is not None

        # --- COLUMN DROP --- #
        table = jamai.drop_columns(
            table_type,
            p.ColumnDropRequest(
                table_id=TABLE_ID_A,
                column_names=["good", "stars", "add_bool", "add_int", "add_str"],
            ),
        )
        expected_cols = {
            "ID",
            "Updated at",
            "words",
            "inputs",
            "summary",
            "add_float",
        }
        if table_type == p.TableType.action:
            pass
        elif table_type == p.TableType.knowledge:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID"}
        elif table_type == p.TableType.chat:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        # Test adding a few rows
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(words=5, inputs=TEXT, add_float=0.0),
        )
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(words=4, inputs=TEXT, summary="<dummy0>", add_float=1.0),
        )
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(words=3, inputs=TEXT, summary="<dummy1>", add_float=2.0),
        )
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 5
        assert all(set(r.keys()) == expected_cols for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_rename_columns(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        # Test rename empty table
        table = jamai.rename_columns(
            table_type,
            p.ColumnRenameRequest(table_id=TABLE_ID_A, column_map=dict(good="nice")),
        )
        assert isinstance(table, p.TableMetaResponse)
        expected_cols = {"ID", "Updated at", "nice", "words", "stars", "inputs", "summary"}
        if table_type == p.TableType.action:
            pass
        elif table_type == p.TableType.knowledge:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID"}
        elif table_type == p.TableType.chat:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols

        table = jamai.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, p.TableMetaResponse)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols
        # Test adding data with new column names
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(nice=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )
        # Test rename table with data
        # Test also auto gen config reference update
        table = jamai.rename_columns(
            table_type,
            p.ColumnRenameRequest(table_id=TABLE_ID_A, column_map=dict(words="length")),
        )
        assert isinstance(table, p.TableMetaResponse)
        expected_cols = {"ID", "Updated at", "nice", "length", "stars", "inputs", "summary"}
        if table_type == p.TableType.action:
            pass
        elif table_type == p.TableType.knowledge:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID"}
        elif table_type == p.TableType.chat:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols
        table = jamai.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, p.TableMetaResponse)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols
        # Test auto gen config reference update
        response = _add_row(
            jamai,
            table_type,
            True,
            data=dict(nice=True, length=5, stars=9.9, inputs=TEXT),
        )
        summary = _collect_text(list(response), "summary")
        assert len(summary) > 0


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_reorder_columns(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        table = jamai.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, p.TableMetaResponse)

        column_names = ["inputs", "good", "words", "stars", "summary"]
        expected_order = ["ID", "Updated at", "good", "words", "stars", "inputs", "summary"]
        if table_type == p.TableType.action:
            pass
        elif table_type == p.TableType.knowledge:
            column_names += ["Title", "Title Embed", "Text", "Text Embed", "File ID"]
            expected_order = (
                expected_order[:2]
                + ["Title", "Title Embed", "Text", "Text Embed", "File ID"]
                + expected_order[2:]
            )
        elif table_type == p.TableType.chat:
            column_names += ["User", "AI"]
            expected_order = expected_order[:2] + ["User", "AI"] + expected_order[2:]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols
        # Test reorder empty table
        table = jamai.reorder_columns(
            table_type,
            p.ColumnReorderRequest(table_id=TABLE_ID_A, column_names=column_names),
        )
        expected_order = ["ID", "Updated at", "inputs", "good", "words", "stars", "summary"]
        if table_type == p.TableType.action:
            pass
        elif table_type == p.TableType.knowledge:
            expected_order += ["Title", "Title Embed", "Text", "Text Embed", "File ID"]
        elif table_type == p.TableType.chat:
            expected_order += ["User", "AI"]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols
        table = jamai.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, p.TableMetaResponse)
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols
        # Test add row
        response = _add_row(
            jamai,
            table_type,
            True,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT),
        )
        summary = _collect_text(list(response), "summary")
        assert len(summary) > 0


def _update_gen_config(
    jamai: JamAI,
    table_type: p.TableType,
    table_id: str = TABLE_ID_A,
) -> p.TableMetaResponse:
    table = jamai.update_gen_config(
        table_type,
        p.GenConfigUpdateRequest(
            table_id=table_id,
            column_map=dict(
                summary=p.ChatRequest(
                    model=_get_chat_model(),
                    messages=[
                        p.ChatEntry.system("You are a concise assistant."),
                        p.ChatEntry.user('Say "I am a unicorn.".'),
                    ],
                    temperature=0.001,
                    top_p=0.001,
                    max_tokens=10,
                ).model_dump()
            ),
        ),
    )
    assert isinstance(table, p.TableMetaResponse)
    return table


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_update_gen_config(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        _update_gen_config(jamai, table_type)

        table = jamai.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, p.TableMetaResponse)
        assert table.cols[-1].id == "summary"
        assert table.cols[-1].gen_config is not None
        assert "unicorn" in table.cols[-1].gen_config["messages"][-1]["content"]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_empty_gen_config(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        table = jamai.update_gen_config(
            table_type,
            p.GenConfigUpdateRequest(table_id=TABLE_ID_A, column_map=dict(summary=None)),
        )
        response = _add_row(
            jamai, table_type, stream, data=dict(good=True, words=5, stars=9.9, inputs=TEXT)
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
        else:
            assert isinstance(response, p.GenTableChatCompletionChunks)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["summary"]["value"] is None


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_add_row(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        response = _add_row(jamai, table_type, stream)
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == p.TableType.chat:
                assert all(r.output_column_name in ("summary", "AI") for r in responses)
            else:
                assert all(r.output_column_name == "summary" for r in responses)
            assert len("".join(r.text for r in responses)) > 0
        else:
            assert isinstance(response, p.GenTableChatCompletionChunks)
            assert response.object == "gen_table.completion.chunks"
            assert len(response.columns["summary"].text) > 0
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["good"]["value"] is True, row["good"]
        assert row["words"]["value"] == 5, row["words"]
        assert row["stars"]["value"] == 7.9, row["stars"]

        # Test adding data with wrong dtype
        response = _add_row(
            jamai,
            table_type,
            stream,
            TABLE_ID_A,
            data=dict(good="dummy1", words="dummy2", stars="dummy3", inputs=TEXT),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
        else:
            assert isinstance(response, p.GenTableChatCompletionChunks)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        row = rows.items[0]
        assert row["good"]["value"] is None, row["good"]
        assert row["good"]["original"] == "dummy1", row["good"]
        assert row["words"]["value"] is None, row["words"]
        assert row["words"]["original"] == "dummy2", row["words"]
        assert row["stars"]["value"] is None, row["stars"]
        assert row["stars"]["original"] == "dummy3", row["stars"]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_update_row(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        row = _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="dummy"),
        )
        assert isinstance(row, p.GenTableChatCompletionChunks)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        original_ts = row["Updated at"]
        assert row["good"]["value"] is True, row["good"]
        assert row["words"]["value"] == 5, row["words"]
        assert row["stars"]["value"] == 9.9, row["stars"]
        # Regular update
        response = jamai.update_table_row(
            table_type,
            p.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=row["ID"],
                data=dict(good=False, stars=1.0),
            ),
        )
        assert isinstance(response, p.OkResponse)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["good"]["value"] is False, row["good"]
        assert row["words"]["value"] == 5, row["words"]
        assert row["stars"]["value"] == 1.0, row["stars"]
        assert row["Updated at"] > original_ts

        # Test updating data with wrong dtype
        response = jamai.update_table_row(
            table_type,
            p.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=row["ID"],
                data=dict(good="dummy", words="dummy", stars="dummy"),
            ),
        )
        assert isinstance(response, p.OkResponse)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["good"]["value"] is None, row["good"]
        assert row["words"]["value"] is None, row["words"]
        assert row["stars"]["value"] is None, row["stars"]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_regen_rows(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        response = _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=10, stars=9.9, inputs=TEXT),
        )
        assert isinstance(response, p.GenTableChatCompletionChunks)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        _id = row["ID"]
        original_ts = row["Updated at"]
        assert "arrival" in row["summary"]["value"].lower()
        # Regen
        jamai.update_table_row(
            table_type,
            p.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=_id,
                data=dict(
                    inputs="Dune: Part Two is a 2024 American epic science fiction film directed and produced by Denis Villeneuve"
                ),
            ),
        )
        response = jamai.regen_table_rows(
            table_type, p.RowRegenRequest(table_id=TABLE_ID_A, row_ids=[_id], stream=stream)
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == p.TableType.chat:
                assert all(r.output_column_name in ("summary", "AI") for r in responses)
            else:
                assert all(r.output_column_name == "summary" for r in responses)
            assert len("".join(r.text for r in responses)) > 0
        else:
            assert isinstance(response, p.GenTableRowsChatCompletionChunks)
            assert response.rows[0].object == "gen_table.completion.chunks"
            assert len(response.rows[0].columns["summary"].text) > 0
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["good"]["value"] is True
        assert row["words"]["value"] == 10
        assert row["stars"]["value"] == 9.9
        assert row["Updated at"] > original_ts
        assert "dune" in row["summary"]["value"].lower()


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_delete_rows(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        data = dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="dummy")
        _add_row(jamai, table_type, False, data=data)
        _add_row(jamai, table_type, False, data=data)
        _add_row(jamai, table_type, False, data=data)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 3
        delete_id = rows.items[0]["ID"]

        response = jamai.delete_table_row(table_type, TABLE_ID_A, delete_id)
        assert isinstance(response, p.OkResponse)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        row_ids = set(r["ID"] for r in rows.items)
        assert delete_id not in row_ids


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_get_and_list_rows(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        _add_row(jamai, table_type, False)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=8.9, inputs=TEXT, summary="<dummy>"),
        )
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=False, words=5, stars=-0.9, inputs=TEXT, summary="<dummy>"),
        )
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=False, words=5, stars=-1.9, inputs=TEXT, summary="<dummy>"),
        )
        # Regular case
        expected_cols = {"ID", "Updated at", "good", "words", "stars", "inputs", "summary"}
        if table_type == p.TableType.action:
            pass
        elif table_type == p.TableType.knowledge:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID"}
        elif table_type == p.TableType.chat:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert all(isinstance(r, dict) for r in rows.items)
        assert rows.total == 5
        assert rows.offset == 0
        assert rows.limit == 100
        assert len(rows.items) == 5
        stars = [r["stars"]["value"] for r in rows.items]
        assert stars[0] == -1.9
        assert stars[-1] == 7.9
        assert all(set(r.keys()) == expected_cols for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]
        # Test get row
        _id = rows.items[0]["ID"]
        row = jamai.get_table_row(table_type, TABLE_ID_A, _id)
        assert row["ID"] == _id
        assert set(row.keys()) == expected_cols
        row = jamai.get_table_row(table_type, TABLE_ID_A, _id, columns=["good"])
        assert row["ID"] == _id
        assert set(row.keys()) == {"ID", "Updated at", "good"}

        # Test various offset and limit
        rows = jamai.list_table_rows(table_type, TABLE_ID_A, offset=0, limit=3)
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 0
        assert rows.limit == 3
        assert len(rows.items) == 3
        stars = [r["stars"]["value"] for r in rows.items]
        assert stars[0] == -1.9
        assert stars[-1] == 9.9

        rows = jamai.list_table_rows(table_type, TABLE_ID_A, offset=1, limit=3)
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 1
        assert rows.limit == 3
        assert len(rows.items) == 3
        stars = [r["stars"]["value"] for r in rows.items]
        assert stars[0] == -0.9
        assert stars[-1] == 8.9

        rows = jamai.list_table_rows(table_type, TABLE_ID_A, offset=4, limit=3)
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 4
        assert rows.limit == 3
        assert len(rows.items) == 1
        stars = [r["stars"]["value"] for r in rows.items]
        assert stars[0] == 7.9

        rows = jamai.list_table_rows(table_type, TABLE_ID_A, offset=6, limit=3)
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 6
        assert rows.limit == 3
        assert len(rows.items) == 0

        # Test specifying columns
        rows = jamai.list_table_rows(
            table_type, TABLE_ID_A, offset=1, limit=3, columns=["stars", "good"]
        )
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 1
        assert rows.limit == 3
        assert len(rows.items) == 3
        assert all(set(r.keys()) == {"ID", "Updated at", "good", "stars"} for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]

        # Invalid offset and limit
        with pytest.raises(RuntimeError):
            jamai.list_table_rows(table_type, TABLE_ID_A, offset=0, limit=0)
        with pytest.raises(RuntimeError):
            jamai.list_table_rows(table_type, TABLE_ID_A, offset=-1, limit=1)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_get_and_list_tables(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with (
        _create_table(jamai, table_type) as table,
        _create_table(jamai, table_type, TABLE_ID_B),
        _create_table(jamai, table_type, TABLE_ID_C),
        _create_table(jamai, table_type, TABLE_ID_X),
    ):
        assert isinstance(table, p.TableMetaResponse)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )

        # Regular case
        table = jamai.get_table(table_type, TABLE_ID_B)
        assert isinstance(table, p.TableMetaResponse)
        assert table.id == TABLE_ID_B

        tables = jamai.list_tables(table_type)
        assert isinstance(tables.items, list)
        assert tables.total == 4
        assert tables.offset == 0
        assert tables.limit == 100
        assert len(tables.items) == 4
        assert all(isinstance(r, p.TableMetaResponse) for r in tables.items)

        # Test various offset and limit
        tables = jamai.list_tables(table_type, offset=3, limit=2)
        assert isinstance(tables.items, list)
        assert tables.total == 4
        assert tables.offset == 3
        assert tables.limit == 2
        assert len(tables.items) == 1
        assert all(isinstance(r, p.TableMetaResponse) for r in tables.items)

        tables = jamai.list_tables(table_type, offset=4, limit=2)
        assert isinstance(tables.items, list)
        assert tables.total == 4
        assert tables.offset == 4
        assert tables.limit == 2
        assert len(tables.items) == 0

        tables = jamai.list_tables(table_type, offset=5, limit=2)
        assert isinstance(tables.items, list)
        assert tables.total == 4
        assert tables.offset == 5
        assert tables.limit == 2
        assert len(tables.items) == 0


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_duplicate_table(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )

        # Duplicate with data
        table = jamai.duplicate_table(table_type, TABLE_ID_A, TABLE_ID_B)
        # Add another to table A
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )
        assert table.id == TABLE_ID_B
        rows = jamai.list_table_rows(table_type, TABLE_ID_B)
        assert len(rows.items) == 1

        # Duplicate without data
        table = jamai.duplicate_table(table_type, TABLE_ID_A, TABLE_ID_C, include_data=False)
        assert table.id == TABLE_ID_C
        rows = jamai.list_table_rows(table_type, TABLE_ID_C)
        assert len(rows.items) == 0

        # Deploy with data
        jamai.delete_table(table_type, TABLE_ID_B)
        jamai.delete_table(table_type, TABLE_ID_C)
        table = jamai.duplicate_table(table_type, TABLE_ID_A, TABLE_ID_B, deploy=True)
        assert table.id == TABLE_ID_B
        assert table.parent_id == TABLE_ID_A
        rows = jamai.list_table_rows(table_type, TABLE_ID_B)
        assert len(rows.items) == 2

        # Deploy without data
        table = jamai.duplicate_table(
            table_type, TABLE_ID_A, TABLE_ID_C, deploy=True, include_data=False
        )
        assert table.id == TABLE_ID_C
        assert table.parent_id == TABLE_ID_A
        rows = jamai.list_table_rows(table_type, TABLE_ID_C)
        assert len(rows.items) == 0
        jamai.delete_table(table_type, TABLE_ID_B)
        jamai.delete_table(table_type, TABLE_ID_C)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_rename_table(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )
        table = jamai.rename_table(table_type, TABLE_ID_A, TABLE_ID_B)
        rows = jamai.list_table_rows(table_type, TABLE_ID_B)
        assert len(rows.items) == 1
        with pytest.raises(RuntimeError):
            jamai.list_table_rows(table_type, TABLE_ID_A)
        jamai.delete_table(table_type, TABLE_ID_B)


def _collect_text(responses: list[p.GenTableStreamChatCompletionChunk], col: str):
    return "".join(r.text for r in responses if r.output_column_name == col)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_column_interpolate(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()

    @contextmanager
    def _create_table(name: str):
        jamai.delete_table(table_type, name)
        kwargs = dict(
            id=name,
            cols=[
                p.ColumnSchemaCreate(
                    id="output0",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[
                            p.ChatEntry.system("You are a concise assistant."),
                            p.ChatEntry.user('Say "Jan has 5 apples.".'),
                        ],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ).model_dump(),
                ),
                p.ColumnSchemaCreate(id="input0", dtype=p.DtypeCreateEnum.int_),
                p.ColumnSchemaCreate(
                    id="output1",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[
                            p.ChatEntry.system("You are a concise assistant."),
                            # Interpolate string and non-string input columns
                            p.ChatEntry.user(
                                (
                                    "1. ${output0}\n2. Jan has ${input0} apples.\n\n"
                                    "Do the statements agree with each other? Reply Yes or No."
                                )
                            ),
                        ],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ).model_dump(),
                ),
            ],
        )
        if table_type == p.TableType.action:
            table = jamai.create_action_table(p.ActionTableSchemaCreate(**kwargs))
        elif table_type == p.TableType.knowledge:
            table = jamai.create_knowledge_table(
                p.KnowledgeTableSchemaCreate(embedding_model=_get_embedding_model(), **kwargs)
            )
        elif table_type == p.TableType.chat:
            kwargs["cols"] = [
                p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                p.ColumnSchemaCreate(
                    id="AI",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[p.ChatEntry.system("You are a wacky assistant.")],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=5,
                    ).model_dump(),
                ),
                p.ColumnSchemaCreate(id="input0", dtype=p.DtypeCreateEnum.int_),
                p.ColumnSchemaCreate(
                    id="output1",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[
                            p.ChatEntry.system("You are a concise assistant."),
                            # Interpolate string and non-string input columns
                            p.ChatEntry.user(
                                (
                                    "1. ${AI}\n2. Jan has ${input0} apples.\n\n"
                                    "Do the statements agree with each other? Reply Yes or No."
                                )
                            ),
                        ],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ).model_dump(),
                ),
            ]
            table = jamai.create_chat_table(p.ChatTableSchemaCreate(**kwargs))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        try:
            yield table
        except Exception:
            raise
        finally:
            jamai.delete_table(table_type, name)

    def _add_row(table_name, stream, data):
        if table_type == p.TableType.action:
            pass
        elif table_type == p.TableType.knowledge:
            data["Title"] = "Dune: Part Two."
            data["Text"] = "Dune: Part Two is a 2024 American epic science fiction film."
        elif table_type == p.TableType.chat:
            data["User"] = 'Say "Jan has 5 apples.".'
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        response = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(table_id=table_name, data=[data], stream=stream),
        )
        return response if stream else response.rows[0]

    with _create_table(TABLE_ID_A):
        # Streaming
        response = list(_add_row(TABLE_ID_A, True, dict(input0=5)))
        output0 = _collect_text(response, "output0")
        ai = _collect_text(response, "AI")
        answer = _collect_text(response, "output1")
        assert "yes" in answer.lower(), f'output0="{output0}"  ai="{ai}"  answer="{answer}"'
        response = list(_add_row(TABLE_ID_A, True, dict(input0=6)))
        output0 = _collect_text(response, "output0")
        ai = _collect_text(response, "AI")
        answer = _collect_text(response, "output1")
        assert "no" in answer.lower(), f'output0="{output0}"  ai="{ai}"  answer="{answer}"'
        # Non-streaming
        response = _add_row(TABLE_ID_A, False, dict(input0=5))
        answer = response.columns["output1"].text
        assert "yes" in answer.lower(), f'columns={response.columns}  answer="{answer}"'
        response = _add_row(TABLE_ID_A, False, dict(input0=6))
        answer = response.columns["output1"].text
        assert "no" in answer.lower(), f'columns={response.columns}  answer="{answer}"'


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_chat_thread_history(client_cls: Type[JamAI]):
    table_type = p.TableType.chat
    jamai = client_cls()
    table = jamai.create_chat_table(
        p.ChatTableSchemaCreate(
            id=TABLE_ID_A,
            cols=[
                p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                p.ColumnSchemaCreate(
                    id="AI",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[p.ChatEntry.system("You are a concise assistant.")],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=20,
                    ).model_dump(),
                ),
                p.ColumnSchemaCreate(
                    id="output",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[
                            p.ChatEntry.system("You are a concise assistant."),
                            p.ChatEntry.user("Who is mentioned in `${AI}`? Reply with the name."),
                        ],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ).model_dump(),
                ),
            ],
        )
    )
    assert isinstance(table, p.TableMetaResponse)
    response = jamai.add_table_rows(
        table_type,
        p.RowAddRequest(
            table_id=TABLE_ID_A, data=[dict(User=".", AI="Jim has 5 apples.")], stream=True
        ),
    )
    output = _collect_text(list(response), "output").lower()
    assert "jim" in output, output
    response = jamai.add_table_rows(
        table_type,
        p.RowAddRequest(
            table_id=TABLE_ID_A, data=[dict(User=".", AI="Jan has 5 apples.")], stream=True
        ),
    )
    output = _collect_text(list(response), "output").lower()
    assert "jan" in output, output
    response = jamai.add_table_rows(
        table_type,
        p.RowAddRequest(
            table_id=TABLE_ID_A, data=[dict(User=".", AI="Jia has 5 apples.")], stream=True
        ),
    )
    output = _collect_text(list(response), "output").lower()
    assert "jia" in output, output
    response = jamai.add_table_rows(
        table_type,
        p.RowAddRequest(
            table_id=TABLE_ID_A,
            data=[dict(User="List the names of people mentioned. Return JSON.")],
            stream=True,
        ),
    )
    output = _collect_text(list(response), "output").lower()
    assert "jim" in output, output
    assert "jan" in output, output
    assert "jia" in output, output
    jamai.delete_table(table_type, TABLE_ID_A)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_get_conversation_thread(client_cls: Type[JamAI]):
    jamai = client_cls()
    table_type = p.TableType.chat
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        data = dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="dummy")
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(User="Tell me a joke.", AI="Knock knock", **data)],
                stream=False,
            ),
        )
        assert isinstance(rows, p.GenTableRowsChatCompletionChunks)
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(User="Who's there?", **data)],
                stream=False,
            ),
        )
        assert isinstance(rows, p.GenTableRowsChatCompletionChunks)
        chat = jamai.get_conversation_thread(TABLE_ID_A)
        assert isinstance(chat, p.ChatThread)
        assert len(chat.thread) == 5
        assert chat.thread[0].role == p.ChatRole.SYSTEM
        assert chat.thread[1].role == p.ChatRole.USER
        assert chat.thread[2].role == p.ChatRole.ASSISTANT
        assert chat.thread[3].role == p.ChatRole.USER
        assert chat.thread[4].role == p.ChatRole.ASSISTANT
        assert isinstance(chat.thread[-1].content, str)
        assert len(chat.thread[-1].content) > 0


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_hybrid_search(client_cls: Type[JamAI]):
    jamai = client_cls()
    table_type = p.TableType.knowledge
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        data = dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="dummy")
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(Title="Resume 2012", Text="Hi there, I am a farmer.", **data)],
                stream=False,
            ),
        )
        assert isinstance(rows, p.GenTableRowsChatCompletionChunks)
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(Title="Resume 2013", Text="Hi there, I am a carpenter.", **data)],
                stream=False,
            ),
        )
        assert isinstance(rows, p.GenTableRowsChatCompletionChunks)
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[
                    dict(
                        Title="Byte Pair Encoding",
                        Text="BPE is a subword tokenization method.",
                        **data,
                    )
                ],
                stream=False,
            ),
        )
        assert isinstance(rows, p.GenTableRowsChatCompletionChunks)
        sleep(1)  # Optional, give it some time to index
        # Rely on embedding
        rows = jamai.hybrid_search(
            table_type,
            p.SearchRequest(
                table_id=TABLE_ID_A,
                query="language",
                reranking_model=_get_reranking_model(),
                limit=2,
            ),
        )
        assert len(rows) == 2
        assert "BPE" in rows[0]["Text"]["value"], rows
        # Rely on FTS
        rows = jamai.hybrid_search(
            table_type,
            p.SearchRequest(
                table_id=TABLE_ID_A,
                query="candidate 2013",
                reranking_model=_get_reranking_model(),
                limit=2,
            ),
        )
        assert len(rows) == 2
        assert "2013" in rows[0]["Title"]["value"], rows


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_upload_file(client_cls: Type[JamAI]):
    jamai = client_cls()
    table_type = p.TableType.knowledge
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        response = jamai.upload_file(
            p.FileUploadRequest(
                file_path="clients/python/tests/pdf/salary 总结.pdf", table_id=TABLE_ID_A
            )
        )
        assert isinstance(response, p.OkResponse)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert all(isinstance(r, dict) for r in rows.items)
        assert rows.total > 0
        assert rows.offset == 0
        assert rows.limit == 100
        assert len(rows.items) > 0
        assert all(isinstance(r["Title"]["value"], str) for r in rows.items)
        assert all(len(r["Title"]["value"]) > 0 for r in rows.items)
        assert all(isinstance(r["Text"]["value"], str) for r in rows.items)
        assert all(len(r["Text"]["value"]) > 0 for r in rows.items)


if __name__ == "__main__":
    test_upload_file(JamAI)
