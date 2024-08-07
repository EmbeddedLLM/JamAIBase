from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal
from os.path import join
from tempfile import TemporaryDirectory
from time import sleep
from typing import Any, Type

import pandas as pd
import pytest
from flaky import flaky
from pydantic import ValidationError

from jamaibase import JamAI
from jamaibase import protocol as p
from jamaibase.utils.io import csv_to_df, df_to_csv, json_loads

CLIENT_CLS = [JamAI]
TABLE_TYPES = [p.TableType.action, p.TableType.knowledge, p.TableType.chat]

TABLE_ID_A = "documents"
TABLE_ID_B = "xx"
TABLE_ID_C = "yy"
TABLE_ID_X = "zz"
TEXT = '"Arrival" is a 2016 American science fiction drama film directed by Denis Villeneuve and adapted by Eric Heisserer.'
TEXT_CN = (
    '"Arrival" 《降临》是一部 2016 年美国科幻剧情片，由丹尼斯·维伦纽瓦执导，埃里克·海瑟尔改编。'
)
TEXT_JP = '"Arrival" 「Arrival」は、ドゥニ・ヴィルヌーヴが監督し、エリック・ハイセラーが脚色した2016年のアメリカのSFドラマ映画です。'


def _delete_tables():
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


@pytest.fixture(scope="module", autouse=True)
def delete_tables():
    _delete_tables()
    yield
    _delete_tables()


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


def _rerun_on_fs_error_with_delay(err, *args):
    sleep(1)
    return "LanceError(IO): Generic LocalFileSystem error" in str(err)


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
        data["Text"] = '"Dune: Part Two" is a 2024 American epic science fiction film.'
    elif table_type == p.TableType.chat:
        data["User"] = "Tell me a joke."
    else:
        raise ValueError(f"Invalid table type: {table_type}")

    response = jamai.add_table_rows(
        table_type,
        p.RowAddRequest(table_id=table_name, data=[data], stream=stream),
    )
    if stream:
        return response
    assert isinstance(response, p.GenTableRowsChatCompletionChunks)
    assert len(response.rows) == 1
    return response.rows[0]


def _assert_is_vector(x: Any):
    assert isinstance(x, list), f"Not a list: {x}"
    assert len(x) > 0, f"Not a non-empty list: {x}"
    assert all(isinstance(v, float) for v in x), f"Not a list of floats: {x}"


def _collect_text(responses: list[p.GenTableStreamChatCompletionChunk], col: str):
    return "".join(r.text for r in responses if r.output_column_name == col)


def _get_exponent(x: float) -> int:
    return Decimal(str(x)).as_tuple().exponent


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", [p.TableType.action, p.TableType.chat])
def test_create_table_with_valid_knowledge_table(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    knowledge_table_id = "test_knowledge_table"

    try:
        # Create Knowledge Table
        with _create_table(
            jamai, p.TableType.knowledge, name=knowledge_table_id
        ) as knowledge_table:
            assert isinstance(knowledge_table, p.TableMetaResponse)

            # Define schema for Action/Chat Table with a valid Knowledge Table reference
            schema = p.TableSchemaCreate(
                id=TABLE_ID_A,
                cols=[
                    p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                    p.ColumnSchemaCreate(
                        id="AI",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[
                                p.ChatEntry.system("You are a concise assistant."),
                                p.ChatEntry.user("Summarize: ${User}"),
                            ],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=10,
                            rag_params=p.RAGParams(table_id=knowledge_table_id),  # Valid reference
                        ).model_dump(),
                    ),
                ],
            )
            schema_dict = schema.model_dump()

            if table_type == p.TableType.action:
                table = jamai.create_action_table(p.ActionTableSchemaCreate(**schema_dict))
            elif table_type == p.TableType.chat:
                table = jamai.create_chat_table(p.ChatTableSchemaCreate(**schema_dict))
            else:
                raise ValueError(f"Invalid table type: {table_type}")

            assert isinstance(table, p.TableMetaResponse)
            assert table.id == TABLE_ID_A
    except Exception:
        raise
    finally:
        jamai.delete_table(p.TableType.knowledge, knowledge_table_id)
        jamai.delete_table(table_type, TABLE_ID_A)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", [p.TableType.action, p.TableType.chat])
def test_create_table_with_invalid_knowledge_table(
    client_cls: Type[JamAI], table_type: p.TableType
):
    jamai = client_cls()
    invalid_knowledge_table_id = "nonexistent_table"

    try:
        # Define Schema for Action/Chat Table with an INVALID Knowledge Table reference
        schema = p.TableSchemaCreate(
            id=TABLE_ID_A,
            cols=[
                p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                p.ColumnSchemaCreate(
                    id="AI",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[
                            p.ChatEntry.system("You are a concise assistant."),
                            p.ChatEntry.user("Summarize: ${User}"),
                        ],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                        rag_params=p.RAGParams(
                            table_id=invalid_knowledge_table_id
                        ),  # Invalid reference
                    ).model_dump(),
                ),
            ],
        )
        schema_dict = schema.model_dump()

        # Expect a RuntimeError (server-side ResourceNotFoundError)
        with pytest.raises(RuntimeError):
            if table_type == p.TableType.action:
                jamai.create_action_table(p.ActionTableSchemaCreate(**schema_dict))
            elif table_type == p.TableType.chat:
                jamai.create_chat_table(p.ChatTableSchemaCreate(**schema_dict))
            else:
                raise ValueError(f"Invalid table type: {table_type}")
    except Exception:
        raise
    finally:
        jamai.delete_table(table_type, TABLE_ID_A)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", [p.TableType.action, p.TableType.chat])
def test_create_table_with_valid_reranking_model(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    knowledge_table_id = "test_knowledge_table"
    # Get a valid reranking model
    valid_reranking_model = _get_reranking_model()

    try:
        # Create Knowledge Table
        with _create_table(
            jamai, p.TableType.knowledge, name=knowledge_table_id
        ) as knowledge_table:
            assert isinstance(knowledge_table, p.TableMetaResponse)

            # Define schema for Action/Chat Table with a VALID Reranking Model
            schema = p.TableSchemaCreate(
                id=TABLE_ID_A,
                cols=[
                    p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                    p.ColumnSchemaCreate(
                        id="AI",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[
                                p.ChatEntry.system("You are a concise assistant."),
                                p.ChatEntry.user("Summarize: ${User}"),
                            ],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=10,
                            rag_params=p.RAGParams(
                                table_id=knowledge_table_id, reranking_model=valid_reranking_model
                            ),  # Valid reranking model
                        ).model_dump(),
                    ),
                ],
            )
            schema_dict = schema.model_dump()

            if table_type == p.TableType.action:
                table = jamai.create_action_table(p.ActionTableSchemaCreate(**schema_dict))
            elif table_type == p.TableType.chat:
                table = jamai.create_chat_table(p.ChatTableSchemaCreate(**schema_dict))
            else:
                raise ValueError(f"Invalid table type: {table_type}")

            assert isinstance(table, p.TableMetaResponse)
            assert table.id == TABLE_ID_A
    except Exception:
        raise
    finally:
        jamai.delete_table(p.TableType.knowledge, knowledge_table_id)
        jamai.delete_table(table_type, TABLE_ID_A)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", [p.TableType.action, p.TableType.chat])
def test_create_table_with_invalid_reranking_model(
    client_cls: Type[JamAI], table_type: p.TableType
):
    jamai = client_cls()
    knowledge_table_id = "test_knowledge_table"
    invalid_reranking_model = "nonexistent_reranker_model"

    try:
        # Create Knowledge Table
        with _create_table(
            jamai, p.TableType.knowledge, name=knowledge_table_id
        ) as knowledge_table:
            assert isinstance(knowledge_table, p.TableMetaResponse)
            # Define schema for Action/Chat Table with an INVALID Reranking Model
            schema = p.TableSchemaCreate(
                id=TABLE_ID_A,
                cols=[
                    p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                    p.ColumnSchemaCreate(
                        id="AI",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[
                                p.ChatEntry.system("You are a concise assistant."),
                                p.ChatEntry.user("Summarize: ${User}"),
                            ],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=10,
                            rag_params=p.RAGParams(
                                table_id=knowledge_table_id,
                                reranking_model=invalid_reranking_model,
                            ),  # Invalid reranking model
                        ).model_dump(),
                    ),
                ],
            )
            schema_dict = schema.model_dump()

            with pytest.raises(RuntimeError):
                if table_type == p.TableType.action:
                    jamai.create_action_table(p.ActionTableSchemaCreate(**schema_dict))
                elif table_type == p.TableType.chat:
                    jamai.create_chat_table(p.ChatTableSchemaCreate(**schema_dict))
                else:
                    raise ValueError(f"Invalid table type: {table_type}")

    except Exception:
        raise
    finally:
        jamai.delete_table(p.TableType.knowledge, knowledge_table_id)
        jamai.delete_table(table_type, TABLE_ID_A)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_create_table_without_llm_model(
    client_cls: Type[JamAI], table_type: p.TableType, stream: bool
):
    jamai = client_cls()
    try:
        kwargs = dict(
            id=TABLE_ID_A,
            cols=[
                p.ColumnSchemaCreate(id="inputs", dtype=p.DtypeCreateEnum.str_),
                p.ColumnSchemaCreate(
                    id="summary",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model="",
                        messages=[
                            p.ChatEntry.system("You are a concise assistant."),
                            # Interpolate string and non-string input columns
                            p.ChatEntry.user("Summarise ${inputs}"),
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
        assert isinstance(table, p.TableMetaResponse)
        assert table.id == TABLE_ID_A
        summary_col = [c for c in table.cols if c.id == "summary"][0]
        assert summary_col.gen_config["model"] is not None
        assert len(summary_col.gen_config["model"]) > 0

        # Try adding row
        data = dict(
            inputs="LanceDB is an open-source vector database for AI that's designed to store, manage, query and retrieve embeddings on large-scale multi-modal data."
        )
        if table_type == p.TableType.knowledge:
            data["Title"] = "Dune: Part Two."
            data["Text"] = "Dune: Part Two is a 2024 American epic science fiction film."
        response = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(table_id=TABLE_ID_A, data=[data], stream=stream),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == p.TableType.chat:
                assert all(r.output_column_name in ("summary", "AI") for r in responses)
            else:
                assert all(r.output_column_name == "summary" for r in responses)
        else:
            assert isinstance(response, p.GenTableRowsChatCompletionChunks)
            assert len(response.rows) == 1
            row = response.rows[0]
            assert isinstance(row, p.GenTableChatCompletionChunks)
            assert "summary" in row.columns
    except Exception:
        raise
    finally:
        jamai.delete_table(table_type, TABLE_ID_A)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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
        # Test adding new rows
        for i in range(5):
            _add_row(
                jamai,
                table_type,
                False,
                data=dict(
                    good=True,
                    words=5 + i,
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
        assert len(rows.items) == 6
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
        assert len(rows.items) == 6
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        # Test adding a few rows
        for i in range(5):
            _add_row(
                jamai,
                table_type,
                False,
                data=dict(words=5 + i, inputs=TEXT, add_float=0.0),
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
        assert len(rows.items) == 13
        assert all(set(r.keys()) == expected_cols for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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

        # --- Test validation --- #
        column_names = ["inputs", "good", "stars", "summary", "words"]
        if table_type == p.TableType.action:
            pass
        elif table_type == p.TableType.knowledge:
            column_names += ["Title", "Title Embed", "Text", "Text Embed", "File ID"]
        elif table_type == p.TableType.chat:
            column_names += ["User", "AI"]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        with pytest.raises(RuntimeError, match="validation_error"):
            jamai.reorder_columns(
                table_type,
                p.ColumnReorderRequest(table_id=TABLE_ID_A, column_names=column_names),
            )


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_update_gen_config(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        table = jamai.update_gen_config(
            table_type,
            p.GenConfigUpdateRequest(
                table_id=TABLE_ID_A,
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
        # Check gen config
        table = jamai.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, p.TableMetaResponse)
        assert table.cols[-1].id == "summary"
        assert table.cols[-1].gen_config is not None
        assert "unicorn" in table.cols[-1].gen_config["messages"][-1]["content"]
        # Test adding row
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
            p.RowAddRequest(table_id=TABLE_ID_A, data=[data], stream=stream),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == p.TableType.chat:
                assert all(r.output_column_name in ("summary", "AI") for r in responses)
            else:
                assert all(r.output_column_name == "summary" for r in responses)
            assert "unicorn" in "".join(r.text for r in responses)
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            assert all(isinstance(r.usage, p.CompletionUsage) for r in responses)
            assert all(isinstance(r.prompt_tokens, int) for r in responses)
            assert all(isinstance(r.completion_tokens, int) for r in responses)
        else:
            assert isinstance(response, p.GenTableRowsChatCompletionChunks)
            assert len(response.rows) == 1
            row = response.rows[0]
            assert isinstance(row, p.GenTableChatCompletionChunks)
            assert row.object == "gen_table.completion.chunks"
            assert "unicorn" in row.columns["summary"].text
            assert isinstance(row.columns["summary"].usage, p.CompletionUsage)
            assert isinstance(row.columns["summary"].prompt_tokens, int)
            assert isinstance(row.columns["summary"].completion_tokens, int)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", [p.TableType.action, p.TableType.chat])
def test_update_gen_config_with_valid_knowledge_table(
    client_cls: Type[JamAI], table_type: p.TableType
):
    jamai = client_cls()
    current_table_id = TABLE_ID_A
    knowledge_table_id = "test_knowledge_table"

    try:
        # Create a Knowledge Table
        with _create_table(
            jamai, p.TableType.knowledge, name=knowledge_table_id
        ) as knowledge_table:
            assert isinstance(knowledge_table, p.TableMetaResponse)

            jamai.delete_table(table_type, current_table_id)
            # Create a Action/Chat Table
            schema = p.TableSchemaCreate(
                id=current_table_id,
                cols=[
                    p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                    p.ColumnSchemaCreate(
                        id="AI",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[
                                p.ChatEntry.system("You are a concise assistant."),
                                p.ChatEntry.user("Summarize: ${User}"),
                            ],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=10,
                        ).model_dump(),
                    ),
                ],
            )
            schema_dict = schema.model_dump()

            if table_type == p.TableType.action:
                table = jamai.create_action_table(p.ActionTableSchemaCreate(**schema_dict))
            elif table_type == p.TableType.chat:
                table = jamai.create_chat_table(p.ChatTableSchemaCreate(**schema_dict))
            else:
                raise ValueError(f"Invalid table type: {table_type}")

            # Update gen_config with valid Knowledge Table reference in RAGParams
            updated_config = p.ChatRequest(
                model=_get_chat_model(),
                messages=[
                    p.ChatEntry.system("You are a concise assistant."),
                    p.ChatEntry.user('Say "Hello, world!"'),
                ],
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
                rag_params=p.RAGParams(table_id=knowledge_table_id),  # Reference Knowledge Table
            ).model_dump()

            table = jamai.update_gen_config(
                table_type,
                p.GenConfigUpdateRequest(
                    table_id=current_table_id,
                    column_map=dict(AI=updated_config),
                ),
            )

            assert isinstance(table, p.TableMetaResponse)
            assert table.cols[-1].id == "AI"
            assert table.cols[-1].gen_config is not None
            assert table.cols[-1].gen_config["rag_params"]["table_id"] == knowledge_table_id

    except Exception:
        raise
    finally:
        jamai.delete_table(p.TableType.knowledge, knowledge_table_id)
        jamai.delete_table(table_type, current_table_id)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", [p.TableType.action, p.TableType.chat])
def test_update_gen_config_with_invalid_knowledge_table(
    client_cls: Type[JamAI], table_type: p.TableType
):
    jamai = client_cls()
    current_table_id = TABLE_ID_A
    invalid_knowledge_table_id = "nonexistent_table"

    try:
        with _create_table(jamai, table_type) as action_table:
            assert isinstance(action_table, p.TableMetaResponse)

            jamai.delete_table(table_type, current_table_id)
            # Create a Action/Chat Table
            schema = p.TableSchemaCreate(
                id=current_table_id,
                cols=[
                    p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                    p.ColumnSchemaCreate(
                        id="AI",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[
                                p.ChatEntry.system("You are a concise assistant."),
                                p.ChatEntry.user("Summarize: ${User}"),
                            ],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=10,
                        ).model_dump(),
                    ),
                ],
            )
            schema_dict = schema.model_dump()

            if table_type == p.TableType.action:
                jamai.create_action_table(p.ActionTableSchemaCreate(**schema_dict))
            elif table_type == p.TableType.chat:
                jamai.create_chat_table(p.ChatTableSchemaCreate(**schema_dict))
            else:
                raise ValueError(f"Invalid table type: {table_type}")

            # Update gen_config with an INVALID Knowledge Table reference in RAGParams
            updated_config = p.ChatRequest(
                model=_get_chat_model(),
                messages=[
                    p.ChatEntry.system("You are a concise assistant."),
                    p.ChatEntry.user('Say "Hello, world!"'),
                ],
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
                rag_params=p.RAGParams(table_id=invalid_knowledge_table_id),  # Invalid reference!
            ).model_dump()

            # Expect a RuntimeError (server-side ResourceNotFoundError)
            with pytest.raises(RuntimeError):
                jamai.update_gen_config(
                    table_type,
                    p.GenConfigUpdateRequest(
                        table_id=current_table_id,
                        column_map=dict(summary=updated_config),
                    ),
                )
    except Exception:
        raise
    finally:
        jamai.delete_table(table_type, current_table_id)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", [p.TableType.action, p.TableType.chat])
def test_update_gen_config_with_valid_reranking_model(
    client_cls: Type[JamAI], table_type: p.TableType
):
    jamai = client_cls()
    current_table_id = TABLE_ID_A
    knowledge_table_id = "test_knowledge_table"
    # Get a valid reranking model
    valid_reranking_model = _get_reranking_model()

    try:
        # Create a Knowledge Table
        with _create_table(
            jamai, p.TableType.knowledge, name=knowledge_table_id
        ) as knowledge_table:
            assert isinstance(knowledge_table, p.TableMetaResponse)

            jamai.delete_table(table_type, current_table_id)
            # Create a Action/Chat Table
            schema = p.TableSchemaCreate(
                id=current_table_id,
                cols=[
                    p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                    p.ColumnSchemaCreate(
                        id="AI",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[
                                p.ChatEntry.system("You are a concise assistant."),
                                p.ChatEntry.user("Summarize: ${User}"),
                            ],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=10,
                        ).model_dump(),
                    ),
                ],
            )
            schema_dict = schema.model_dump()

            if table_type == p.TableType.action:
                table = jamai.create_action_table(p.ActionTableSchemaCreate(**schema_dict))
            elif table_type == p.TableType.chat:
                table = jamai.create_chat_table(p.ChatTableSchemaCreate(**schema_dict))
            else:
                raise ValueError(f"Invalid table type: {table_type}")

            # Update gen_config with valid reranking model in RAGParams
            updated_config = p.ChatRequest(
                model=_get_chat_model(),
                messages=[
                    p.ChatEntry.system("You are a concise assistant."),
                    p.ChatEntry.user('Say "Hello, world!"'),
                ],
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
                rag_params=p.RAGParams(
                    table_id=knowledge_table_id, reranking_model=valid_reranking_model
                ),  # Valid reranking model
            ).model_dump()

            table = jamai.update_gen_config(
                table_type,
                p.GenConfigUpdateRequest(
                    table_id=current_table_id,
                    column_map=dict(AI=updated_config),
                ),
            )

            assert isinstance(table, p.TableMetaResponse)
            assert table.cols[-1].id == "AI"
            assert table.cols[-1].gen_config is not None
            assert table.cols[-1].gen_config["rag_params"]["table_id"] == knowledge_table_id
            assert (
                table.cols[-1].gen_config["rag_params"]["reranking_model"] == valid_reranking_model
            )

    except Exception:
        raise
    finally:
        jamai.delete_table(p.TableType.knowledge, knowledge_table_id)
        jamai.delete_table(table_type, current_table_id)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", [p.TableType.action, p.TableType.chat])
def test_update_gen_config_with_invalid_reranking_model(
    client_cls: Type[JamAI], table_type: p.TableType
):
    jamai = client_cls()
    current_table_id = TABLE_ID_A
    knowledge_table_id = "test_knowledge_table"
    invalid_reranking_model = "nonexistent_reranker_model"

    try:
        # Create a Knowledge Table
        with _create_table(
            jamai, p.TableType.knowledge, name=knowledge_table_id
        ) as knowledge_table:
            assert isinstance(knowledge_table, p.TableMetaResponse)

            jamai.delete_table(table_type, current_table_id)
            # Create a Action/Chat Table
            schema = p.TableSchemaCreate(
                id=current_table_id,
                cols=[
                    p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                    p.ColumnSchemaCreate(
                        id="AI",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[
                                p.ChatEntry.system("You are a concise assistant."),
                                p.ChatEntry.user("Summarize: ${User}"),
                            ],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=10,
                        ).model_dump(),
                    ),
                ],
            )
            schema_dict = schema.model_dump()

            if table_type == p.TableType.action:
                jamai.create_action_table(p.ActionTableSchemaCreate(**schema_dict))
            elif table_type == p.TableType.chat:
                jamai.create_chat_table(p.ChatTableSchemaCreate(**schema_dict))
            else:
                raise ValueError(f"Invalid table type: {table_type}")

            # Update gen_config with valid reranking model in RAGParams
            updated_config = p.ChatRequest(
                model=_get_chat_model(),
                messages=[
                    p.ChatEntry.system("You are a concise assistant."),
                    p.ChatEntry.user('Say "Hello, world!"'),
                ],
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
                rag_params=p.RAGParams(
                    table_id=knowledge_table_id, reranking_model=invalid_reranking_model
                ),  # Invalid reranking model
            ).model_dump()

            with pytest.raises(RuntimeError):
                jamai.update_gen_config(
                    table_type,
                    p.GenConfigUpdateRequest(
                        table_id=current_table_id,
                        column_map=dict(summary=updated_config),
                    ),
                )
    except Exception:
        raise
    finally:
        jamai.delete_table(p.TableType.knowledge, knowledge_table_id)
        jamai.delete_table(table_type, current_table_id)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_null_gen_config(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
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
def test_gen_config_empty_prompts(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    stream: bool,
):
    jamai = client_cls()
    table_name = TABLE_ID_A
    jamai.delete_table(table_type, table_name)
    try:
        kwargs = dict(
            id=table_name,
            cols=[
                p.ColumnSchemaCreate(id="words", dtype=p.DtypeCreateEnum.int_),
                p.ColumnSchemaCreate(
                    id="summary",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[p.ChatEntry.system(""), p.ChatEntry.user("")],
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
                        messages=[p.ChatEntry.system("")],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=5,
                    ).model_dump(),
                ),
            ] + kwargs["cols"]
            table = jamai.create_chat_table(p.ChatTableSchemaCreate(**kwargs))

        assert isinstance(table, p.TableMetaResponse)
        data = dict(words=5)
        if table_type == p.TableType.knowledge:
            data["Title"] = "Dune: Part Two."
            data["Text"] = "Dune: Part Two is a 2024 American epic science fiction film."
        response = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(table_id=table_name, data=[data], stream=stream),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            summary = "".join(r.text for r in responses if r.output_column_name == "summary")
            assert len(summary) > 0
            if table_type == p.TableType.chat:
                ai = "".join(r.text for r in responses if r.output_column_name == "AI")
                assert len(ai) > 0
        else:
            assert isinstance(response.rows[0], p.GenTableChatCompletionChunks)
    except Exception:
        raise
    finally:
        jamai.delete_table(table_type, table_name)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_gen_config_no_message(
    client_cls: Type[JamAI],
    table_type: p.TableType,
):
    jamai = client_cls()
    table_name = TABLE_ID_A
    jamai.delete_table(table_type, table_name)
    try:
        with pytest.raises(ValidationError, match="at least 1 item"):
            kwargs = dict(
                id=table_name,
                cols=[
                    p.ColumnSchemaCreate(id="words", dtype=p.DtypeCreateEnum.int_),
                    p.ColumnSchemaCreate(
                        id="summary",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=10,
                        ).model_dump(),
                    ),
                ],
            )
            if table_type == p.TableType.action:
                jamai.create_action_table(p.ActionTableSchemaCreate(**kwargs))
            elif table_type == p.TableType.knowledge:
                jamai.create_knowledge_table(
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
                            messages=[],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=5,
                        ).model_dump(),
                    ),
                ] + kwargs["cols"]
                jamai.create_chat_table(p.ChatTableSchemaCreate(**kwargs))
    except Exception:
        raise
    finally:
        jamai.delete_table(table_type, table_name)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False])
def test_knowledge_table_embedding(client_cls: Type[JamAI], stream: bool):
    jamai = client_cls()
    try:
        # Create Knowledge Table and add some rows
        knowledge_table_id = TABLE_ID_A
        table_type = p.TableType.knowledge
        jamai.delete_table(table_type, knowledge_table_id)
        table = jamai.create_knowledge_table(
            p.KnowledgeTableSchemaCreate(
                id=knowledge_table_id, cols=[], embedding_model=_get_embedding_model()
            )
        )
        assert isinstance(table, p.TableMetaResponse)
        # Don't include embeddings
        data = [
            dict(
                Title="Six-spot burnet",
                Text="The six-spot burnet is a day-flying moth of the family Zygaenidae.",
            ),
            # Test missing Title
            dict(
                Text="In machine learning, a neural network is a model inspired by biological neural networks in animal brains.",
            ),
            # Test missing Text
            dict(
                Title="A supercomputer is a type of computer with a high level of performance as compared to a general-purpose computer.",
            ),
        ]
        response = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(table_id=knowledge_table_id, data=data, stream=stream),
        )
        if stream:
            responses = [r for r in response]
            assert len(responses) == 0  # We currently dont return anything if LLM is not called
        else:
            assert isinstance(response.rows[0], p.GenTableChatCompletionChunks)
        # Check embeddings
        rows = jamai.list_table_rows(table_type, knowledge_table_id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 3
        row = rows.items[2]
        assert row["Title"]["value"] == data[0]["Title"], row
        assert row["Text"]["value"] == data[0]["Text"], row
        _assert_is_vector(row["Title Embed"]["value"])
        _assert_is_vector(row["Text Embed"]["value"])
        row = rows.items[1]
        assert row["Title"]["value"] is None, row
        assert row["Text"]["value"] == data[1]["Text"], row
        _assert_is_vector(row["Text Embed"]["value"])
        row = rows.items[0]
        assert row["Title"]["value"] == data[2]["Title"], row
        assert row["Text"]["value"] is None, row
        _assert_is_vector(row["Title Embed"]["value"])
    except Exception:
        raise
    finally:
        jamai.delete_table(table_type, TABLE_ID_A)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_rag(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
    jamai = client_cls()
    try:
        # Create Knowledge Table and add some rows
        knowledge_table_id = TABLE_ID_A
        jamai.delete_table(p.TableType.knowledge, knowledge_table_id)
        table = jamai.create_knowledge_table(
            p.KnowledgeTableSchemaCreate(
                id=knowledge_table_id, cols=[], embedding_model=_get_embedding_model()
            )
        )
        assert isinstance(table, p.TableMetaResponse)
        response = jamai.add_table_rows(
            p.TableType.knowledge,
            p.RowAddRequest(
                table_id=knowledge_table_id,
                data=[
                    dict(
                        Title="Six-spot burnet",
                        Text="The six-spot burnet is a day-flying moth of the family Zygaenidae.",
                    ),
                    # Test missing Title
                    dict(
                        Text="In machine learning, a neural network is a model inspired by biological neural networks in animal brains.",
                    ),
                    # Test missing Text
                    dict(
                        Title="A supercomputer is a type of computer with a high level of performance as compared to a general-purpose computer.",
                    ),
                ],
                stream=False,
            ),
        )
        assert isinstance(response, p.GenTableRowsChatCompletionChunks)
        assert isinstance(response.rows[0], p.GenTableChatCompletionChunks)
        rows = jamai.list_table_rows(p.TableType.knowledge, knowledge_table_id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 3

        # Create the other table
        name = TABLE_ID_B
        jamai.delete_table(table_type, name)
        kwargs = dict(
            id=name,
            cols=[
                p.ColumnSchemaCreate(id="question", dtype=p.DtypeCreateEnum.str_),
                p.ColumnSchemaCreate(id="words", dtype=p.DtypeCreateEnum.int_),
                p.ColumnSchemaCreate(
                    id="rag",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[
                            p.ChatEntry.system("You are a concise assistant."),
                            p.ChatEntry.user("${question}? Summarise in ${words} words"),
                        ],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                        rag_params=p.RAGParams(
                            table_id=knowledge_table_id,
                            reranking_model=_get_reranking_model(),
                            search_query="",  # Generate using LM
                            rerank=True,
                        ),
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
        assert isinstance(table, p.TableMetaResponse)
        # Perform RAG
        data = dict(question="What is a burnet?", words=5)
        response = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(table_id=name, data=[data], stream=stream),
        )
        if stream:
            responses = [r for r in response]
            assert len(responses) > 0
            if table_type == p.TableType.chat:
                responses = [r for r in responses if r.output_column_name == "rag"]
            assert isinstance(responses[0], p.GenTableStreamReferences)
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses[1:])
        else:
            assert len(response.rows) > 0
            for row in response.rows:
                assert isinstance(row, p.GenTableChatCompletionChunks)
                assert len(row.columns) > 0
                if table_type == p.TableType.chat:
                    assert "AI" in row.columns
                assert "rag" in row.columns
                assert isinstance(row.columns["rag"], p.ChatCompletionChunk)
                assert isinstance(row.columns["rag"].references, p.References)

    except Exception:
        raise
    finally:
        jamai.delete_table(p.TableType.knowledge, TABLE_ID_A)
        jamai.delete_table(table_type, TABLE_ID_B)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False])
def test_knowledge_table_null_source(
    client_cls: Type[JamAI],
    stream: bool,
):
    jamai = client_cls()
    table_name = TABLE_ID_A
    table_type = p.TableType.knowledge
    jamai.delete_table(table_type, table_name)
    try:
        kwargs = dict(
            id=table_name,
            cols=[
                p.ColumnSchemaCreate(id="words", dtype=p.DtypeCreateEnum.int_),
                p.ColumnSchemaCreate(
                    id="summary",
                    dtype=p.DtypeCreateEnum.str_,
                    gen_config=p.ChatRequest(
                        model=_get_chat_model(),
                        messages=[p.ChatEntry.system(""), p.ChatEntry.user("")],
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ).model_dump(),
                ),
            ],
        )
        table = jamai.create_knowledge_table(
            p.KnowledgeTableSchemaCreate(embedding_model=_get_embedding_model(), **kwargs)
        )
        assert isinstance(table, p.TableMetaResponse)
        # Purposely leave out Title and Text
        data = dict(words=5)
        response = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(table_id=table_name, data=[data], stream=stream),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            summary = "".join(r.text for r in responses if r.output_column_name == "summary")
            assert len(summary) > 0
            if table_type == p.TableType.chat:
                ai = "".join(r.text for r in responses if r.output_column_name == "AI")
                assert len(ai) > 0
        else:
            assert isinstance(response.rows[0], p.GenTableChatCompletionChunks)
    except Exception:
        raise
    finally:
        jamai.delete_table(table_type, table_name)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False])
def test_conversation_starter(client_cls: Type[JamAI], stream: bool):
    jamai = client_cls()
    table_name = TABLE_ID_A
    table_type = p.TableType.chat
    jamai.delete_table(table_type, table_name)
    try:
        table = jamai.create_chat_table(
            p.ChatTableSchemaCreate(
                id=table_name,
                cols=[
                    p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                    p.ColumnSchemaCreate(
                        id="AI",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[p.ChatEntry.system("You help remember facts.")],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=10,
                        ).model_dump(),
                    ),
                    p.ColumnSchemaCreate(id="words", dtype=p.DtypeCreateEnum.int_),
                    p.ColumnSchemaCreate(
                        id="summary",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=_get_chat_model(),
                            messages=[p.ChatEntry.system("You are an assistant")],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=5,
                        ).model_dump(),
                    ),
                ],
            )
        )
        assert isinstance(table, p.TableMetaResponse)
        # Add the starter
        response = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(table_id=table_name, data=[dict(AI="x = 5")], stream=stream),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
        else:
            assert isinstance(response.rows[0], p.GenTableChatCompletionChunks)
        # Chat with it
        response = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=table_name,
                data=[dict(User="x = ")],
                stream=stream,
            ),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            answer = "".join(r.text for r in responses if r.output_column_name == "AI")
            assert "5" in answer
            summary = "".join(r.text for r in responses if r.output_column_name == "summary")
            assert len(summary) > 0
        else:
            assert isinstance(response.rows[0], p.GenTableChatCompletionChunks)
    except Exception:
        raise
    finally:
        jamai.delete_table(table_type, table_name)


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
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            assert all(isinstance(r.usage, p.CompletionUsage) for r in responses)
            assert all(isinstance(r.prompt_tokens, int) for r in responses)
            assert all(isinstance(r.completion_tokens, int) for r in responses)
        else:
            assert isinstance(response, p.GenTableChatCompletionChunks)
            assert response.object == "gen_table.completion.chunks"
            assert len(response.columns["summary"].text) > 0
            assert isinstance(response.columns["summary"].usage, p.CompletionUsage)
            assert isinstance(response.columns["summary"].prompt_tokens, int)
            assert isinstance(response.columns["summary"].completion_tokens, int)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["good"]["value"] is True, row["good"]
        assert row["words"]["value"] == 5, row["words"]
        assert row["stars"]["value"] == 7.9, row["stars"]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_add_row_wrong_dtype(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
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
@pytest.mark.parametrize("stream", [True, False])
def test_add_row_missing_columns(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
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

        # Test adding data with missing column
        response = _add_row(
            jamai,
            table_type,
            stream,
            TABLE_ID_A,
            data=dict(good="dummy1", inputs=TEXT),
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
        assert "original" not in row["words"], row["words"]
        assert row["stars"]["value"] is None, row["stars"]
        assert "original" not in row["stars"], row["stars"]


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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
        _add_row(jamai, table_type, False, data=data)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=7.9, inputs=TEXT_CN),
        )
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=7.9, inputs=TEXT_JP),
        )
        ori_rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(ori_rows.items, list)
        assert len(ori_rows.items) == 6
        delete_id = ori_rows.items[0]["ID"]

        # Delete one row
        response = jamai.delete_table_row(table_type, TABLE_ID_A, delete_id)
        assert isinstance(response, p.OkResponse)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 5
        row_ids = set(r["ID"] for r in rows.items)
        assert delete_id not in row_ids
        # Delete multiple rows
        delete_ids = [r["ID"] for r in ori_rows.items[1:4]]
        response = jamai.delete_table_rows(
            table_type,
            p.RowDeleteRequest(
                table_id=TABLE_ID_A,
                row_ids=delete_ids,
            ),
        )
        assert isinstance(response, p.OkResponse)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        row_ids = set(r["ID"] for r in rows.items)
        assert len(set(row_ids) & set(delete_ids)) == 0


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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
            data=dict(good=True, words=5, stars=5 / 3, inputs=TEXT, summary="<dummy>"),
        )
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=1 / 3, inputs=TEXT_CN, summary="<dummy>"),
        )
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=False, words=5, stars=-5 / 3, inputs=TEXT_JP, summary="<sunny>"),
        )
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=False, words=5, stars=-1 / 3, inputs=TEXT, summary="<yummy>"),
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
        assert stars[0] == -1 / 3
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
        assert stars[0] == -1 / 3
        assert stars[-1] == 1 / 3

        rows = jamai.list_table_rows(table_type, TABLE_ID_A, offset=1, limit=3)
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 1
        assert rows.limit == 3
        assert len(rows.items) == 3
        stars = [r["stars"]["value"] for r in rows.items]
        assert stars[0] == -5 / 3
        assert stars[-1] == 5 / 3

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

        # Test search query
        rows = jamai.list_table_rows(
            table_type,
            TABLE_ID_A,
            offset=0,
            limit=3,
            search_query="dummy",
            columns=["summary"],
        )
        assert isinstance(rows.items, list)
        assert rows.total == 2
        assert rows.offset == 0
        assert rows.limit == 3
        assert len(rows.items) == 2
        assert all(set(r.keys()) == {"ID", "Updated at", "summary"} for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]
        rows = jamai.list_table_rows(
            table_type,
            TABLE_ID_A,
            offset=1,
            limit=3,
            search_query="dummy",
            columns=["summary"],
        )
        assert isinstance(rows.items, list)
        assert rows.total == 2
        assert rows.offset == 1
        assert rows.limit == 3
        assert len(rows.items) == 1
        assert all(set(r.keys()) == {"ID", "Updated at", "summary"} for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]
        rows = jamai.list_table_rows(
            table_type,
            TABLE_ID_A,
            offset=0,
            limit=100,
            search_query="yummy",
            columns=["summary"],
        )
        assert isinstance(rows.items, list)
        assert rows.total == 1
        assert rows.offset == 0
        assert rows.limit == 100
        assert len(rows.items) == 1
        assert all(set(r.keys()) == {"ID", "Updated at", "summary"} for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]

        # --- Test precision --- #
        # At least 10 decimals
        rows = jamai.list_table_rows(table_type, TABLE_ID_A, limit=4)
        assert isinstance(rows.items, list)
        exponents = [_get_exponent(r["stars"]["value"]) for r in rows.items]
        assert all(e < -10 for e in exponents)
        for row in rows.items:
            for v in row.values():
                if not isinstance(v, list):
                    continue
                exponents = [_get_exponent(v["value"]) for r in rows.items]
                assert all(e < -10 for e in exponents)
        # 5 decimals
        rows = jamai.list_table_rows(
            table_type, TABLE_ID_A, limit=4, float_decimals=5, vec_decimals=5
        )
        assert isinstance(rows.items, list)
        exponents = [_get_exponent(r["stars"]["value"]) for r in rows.items]
        assert all(e == -5 for e in exponents)
        for row in rows.items:
            for v in row.values():
                if not isinstance(v, list):
                    continue
                exponents = [_get_exponent(v["value"]) for r in rows.items]
                assert all(e == -5 for e in exponents)
        # 1 decimal
        rows = jamai.list_table_rows(
            table_type, TABLE_ID_A, limit=4, float_decimals=1, vec_decimals=1
        )
        assert isinstance(rows.items, list)
        exponents = [_get_exponent(r["stars"]["value"]) for r in rows.items]
        assert all(e == -1 for e in exponents)
        for row in rows.items:
            for v in row.values():
                if not isinstance(v, list):
                    continue
                exponents = [_get_exponent(v["value"]) for r in rows.items]
                assert all(e == -1 for e in exponents)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_get_and_list_tables(client_cls: Type[JamAI], table_type: p.TableType):
    _delete_tables()
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


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
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
        assert len(rows.rows) == 1
        second_row_id = rows.rows[0].row_id
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

        # --- Test row ID filtering --- #
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(User="What is love?", AI="Baby don't hurt me", **data)],
                stream=False,
            ),
        )
        # No filter
        chat = jamai.get_conversation_thread(TABLE_ID_A)
        assert isinstance(chat, p.ChatThread)
        assert len(chat.thread) == 7
        # Filter (include = True)
        chat = jamai.get_conversation_thread(TABLE_ID_A, second_row_id)
        assert isinstance(chat, p.ChatThread)
        assert len(chat.thread) == 5
        assert chat.thread[3].content == "Who's there?"
        # Filter (include = False)
        chat = jamai.get_conversation_thread(TABLE_ID_A, second_row_id, False)
        assert isinstance(chat, p.ChatThread)
        assert len(chat.thread) == 3
        assert chat.thread[1].content == "Tell me a joke."


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False])
def test_chat_regen(client_cls: Type[JamAI], stream: bool):
    jamai = client_cls()
    table_type = p.TableType.chat
    model = _get_chat_model()
    try:
        table = jamai.create_chat_table(
            p.ChatTableSchemaCreate(
                id=TABLE_ID_A,
                cols=[
                    p.ColumnSchemaCreate(id="User", dtype=p.DtypeCreateEnum.str_),
                    p.ColumnSchemaCreate(
                        id="AI",
                        dtype=p.DtypeCreateEnum.str_,
                        gen_config=p.ChatRequest(
                            model=model,
                            messages=[p.ChatEntry.system("Follow instructions strictly.")],
                            temperature=0.001,
                            top_p=0.001,
                            max_tokens=50,
                        ).model_dump(),
                    ),
                ],
            )
        )
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[
                    dict(
                        User="Make a Python list, add 1 to it. Reply the list only.",
                        AI="[1]",
                    )
                ],
                stream=False,
            ),
        )
        assert isinstance(rows, p.GenTableRowsChatCompletionChunks)
        assert len(rows.rows) == 1
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(User="Add 2 to it")],
                stream=False,
            ),
        )
        assert isinstance(rows, p.GenTableRowsChatCompletionChunks)
        assert len(rows.rows) == 1
        assert json_loads(rows.rows[0].columns["AI"].text) == [1, 2]
        second_row_id = rows.rows[0].row_id
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(User="Add 3 to it")],
                stream=False,
            ),
        )
        rows = jamai.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(User="Add 4 to it")],
                stream=False,
            ),
        )
        assert isinstance(rows, p.GenTableRowsChatCompletionChunks)
        assert len(rows.rows) == 1
        assert json_loads(rows.rows[0].columns["AI"].text) == [1, 2, 3, 4]
        # Test regen
        response = jamai.regen_table_rows(
            table_type,
            p.RowRegenRequest(table_id=TABLE_ID_A, row_ids=[second_row_id], stream=stream),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            assert all(r.output_column_name == "AI" for r in responses)
            assert json_loads("".join(r.text for r in responses)) == [1, 2]
        else:
            assert isinstance(response, p.GenTableRowsChatCompletionChunks)
            assert response.rows[0].object == "gen_table.completion.chunks"
            assert json_loads(response.rows[0].columns["AI"].text) == [1, 2]
    finally:
        jamai.delete_table(table_type, TABLE_ID_A)


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
        # hybrid_search without reranker (RRF only)
        rows = jamai.hybrid_search(
            table_type,
            p.SearchRequest(
                table_id=TABLE_ID_A,
                query="language",
                reranking_model=None,
                limit=2,
            ),
        )
        assert len(rows) == 2
        assert "BPE" in rows[0]["Text"]["value"], rows


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize(
    "file_path",
    [
        "clients/python/tests/pdf/salary 总结.pdf",
        "clients/python/tests/pdf/1970_PSS_ThAT_mechanism.pdf",
        "clients/python/tests/pdf_scan/1978_APL_FP_detrapping.PDF",
        "clients/python/tests/pdf_mixed/digital_scan_combined.pdf",
        "clients/python/tests/md/creative-story.md",
        "clients/python/tests/txt/creative-story.txt",
        "clients/python/tests/html/RAG and LLM Integration Guide.html",
        "clients/python/tests/html/multilingual-code-examples.html",
        "clients/python/tests/html/table.html",
        "clients/python/tests/xml/weather-forecast-service.xml",
        "clients/python/tests/json/company-profile.json",
        "clients/python/tests/jsonl/llm-models.jsonl",
        "clients/python/tests/docx/Recommendation Letter.docx",
        "clients/python/tests/doc/Recommendation Letter.doc",
        "clients/python/tests/pptx/(2017.06.30) Neural Machine Translation in Linear Time (ByteNet).pptx",
        "clients/python/tests/ppt/(2017.06.30) Neural Machine Translation in Linear Time (ByteNet).ppt",
        "clients/python/tests/xlsx/Claims Form.xlsx",
        "clients/python/tests/xls/Claims Form.xls",
        "clients/python/tests/tsv/weather_observations.tsv",
        "clients/python/tests/csv/company-profile.csv",
        "clients/python/tests/csv/weather_observations_long.csv",
    ],
)
def test_upload_file(client_cls: Type[JamAI], file_path: str):
    jamai = client_cls()
    table_type = p.TableType.knowledge
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
        response = jamai.upload_file(p.FileUploadRequest(file_path=file_path, table_id=TABLE_ID_A))
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


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_upload_long_file(client_cls: Type[JamAI]):
    table_type = p.TableType.knowledge
    table_id = TABLE_ID_A
    with TemporaryDirectory() as tmp_dir:
        try:
            # Create a long CSV
            data = [
                {"bool": True, "float": 0.0, "int": 0, "str": ""},
                {"bool": False, "float": -1.0, "int": -2, "str": "testing"},
                {"bool": None, "float": None, "int": None, "str": None},
            ]
            file_path = join(tmp_dir, "long.csv")
            df_to_csv(pd.DataFrame.from_dict(data * 100), file_path)
            # Embed the CSV
            jamai = client_cls()
            table = jamai.create_knowledge_table(
                p.KnowledgeTableSchemaCreate(
                    id=table_id,
                    cols=[],
                    embedding_model=_get_embedding_model(),
                )
            )
            assert isinstance(table, p.TableMetaResponse)
            assert all(isinstance(c, p.ColumnSchema) for c in table.cols)
            response = jamai.upload_file(
                p.FileUploadRequest(file_path=file_path, table_id=table_id)
            )
            assert isinstance(response, p.OkResponse)
            rows = jamai.list_table_rows(table_type, table_id)
            assert isinstance(rows.items, list)
            assert all(isinstance(r, dict) for r in rows.items)
            assert rows.total == 300
            assert rows.offset == 0
            assert rows.limit == 100
            assert len(rows.items) == 100
            assert all(isinstance(r["Title"]["value"], str) for r in rows.items)
            assert all(len(r["Title"]["value"]) > 0 for r in rows.items)
            assert all(isinstance(r["Text"]["value"], str) for r in rows.items)
            assert all(len(r["Text"]["value"]) > 0 for r in rows.items)
        except Exception:
            raise
        finally:
            jamai.delete_table(table_type, table_id)


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_import_data_complete(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        # Complete CSV
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_data_complete.csv")
            chat_data = {"User": ".", "AI": "."}
            data = [
                {"good": True, "words": 5, "stars": 0.0, "inputs": "", "summary": "", **chat_data},
                {
                    "good": False,
                    "words": 5,
                    "stars": 1.0,
                    "inputs": TEXT,
                    "summary": "",
                    **chat_data,
                },
                {
                    "good": True,
                    "words": 5,
                    "stars": 2.0,
                    "inputs": TEXT_CN,
                    "summary": "",
                    **chat_data,
                },
                {
                    "good": False,
                    "words": 5,
                    "stars": 3.0,
                    "inputs": TEXT_JP,
                    "summary": "",
                    **chat_data,
                },
            ]
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "good": "bool",
                    "words": "int32",
                    "stars": "float32",
                    "inputs": "string",
                    "summary": "string",
                }
            )
            df_to_csv(df, file_path)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=TABLE_ID_A,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) == 0
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"

        rows = jamai.list_table_rows(table_type, TABLE_ID_A, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 4
        for row, d in zip(rows.items[::-1], data):
            for k, v in d.items():
                if k not in row:
                    continue
                if v == "":
                    assert (
                        row[k]["value"] is None
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"
                else:
                    assert (
                        row[k]["value"] == v
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_import_data_incomplete(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        # CSV without input column
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_data_complete.csv")
            cols = ["good", "words", "stars", "inputs", "summary"]
            chat_data = {"User": ".", "AI": "."}
            data = [
                {"good": True, "stars": 0.0, "inputs": TEXT, "summary": TEXT, **chat_data},
                {"good": False, "stars": 1.0, "inputs": TEXT, "summary": TEXT, **chat_data},
                {"good": True, "stars": 2.0, "inputs": TEXT_CN, "summary": TEXT, **chat_data},
                {"good": False, "stars": 3.0, "inputs": TEXT_JP, "summary": TEXT, **chat_data},
            ]
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "good": "bool",
                    "stars": "float32",
                    "inputs": "string",
                    "summary": "string",
                }
            )
            df_to_csv(df, file_path)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=TABLE_ID_A,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) == 0
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"

        rows = jamai.list_table_rows(table_type, TABLE_ID_A, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 4
        for row, d in zip(rows.items[::-1], data):
            for k in cols:
                if k not in d:
                    assert (
                        row[k]["value"] is None
                    ), f"Imported data should be None: col=`{k}`  val={row[k]}"
                else:
                    assert (
                        row[k]["value"] == d[k]
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{d[k]}`"


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_import_data_with_generation(
    client_cls: Type[JamAI], table_type: p.TableType, stream: bool
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        # CSV without output column
        with TemporaryDirectory() as tmp_dir:
            chat_data = {"User": ".", "AI": "."}
            data = [
                {"good": False, "words": 5, "stars": 1.0, "inputs": TEXT, **chat_data},
                {"good": False, "words": 5, "stars": 3.0, "inputs": TEXT_JP, **chat_data},
            ]
            file_path = join(tmp_dir, "test_import_data_with_generation.csv")
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "good": "bool",
                    "words": "int32",
                    "stars": "float32",
                    "inputs": "string",
                }
            )
            df_to_csv(df, file_path)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=TABLE_ID_A,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) > 0
                assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
                assert all(r.object == "gen_table.completion.chunk" for r in responses)
                assert all(r.output_column_name == "summary" for r in responses)
                summaries = defaultdict(list)
                for r in responses:
                    if r.output_column_name != "summary":
                        continue
                    summaries[r.row_id].append(r.text)
                summaries = {k: "".join(v) for k, v in summaries.items()}
                assert len(summaries) == 2
                assert all(len(v) > 0 for v in summaries.values())
                assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
                assert all(isinstance(r.usage, p.CompletionUsage) for r in responses)
                assert all(isinstance(r.prompt_tokens, int) for r in responses)
                assert all(isinstance(r.completion_tokens, int) for r in responses)
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"
                for row in response.rows:
                    assert len(row.columns["summary"].text) > 0
                    assert isinstance(row.columns["summary"].usage, p.CompletionUsage)
                    assert isinstance(row.columns["summary"].prompt_tokens, int)
                    assert isinstance(row.columns["summary"].completion_tokens, int)

        rows = jamai.list_table_rows(table_type, TABLE_ID_A, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        for row, d in zip(rows.items[::-1], data):
            for k, v in d.items():
                if k not in row:
                    continue
                if v == "":
                    assert (
                        row[k]["value"] is None
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"
                else:
                    assert (
                        row[k]["value"] == v
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_import_data_empty(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        with TemporaryDirectory() as tmp_dir:
            # Empty
            file_path = join(tmp_dir, "empty.csv")
            df_to_csv(pd.DataFrame(columns=[]), file_path)
            with pytest.raises(RuntimeError, match="invalid"):
                response = jamai.import_table_data(
                    table_type,
                    p.TableDataImportRequest(
                        file_path=file_path, table_id=TABLE_ID_A, stream=stream
                    ),
                )
                if stream:
                    response = list(response)
            # No rows
            file_path = join(tmp_dir, "empty.csv")
            df_to_csv(
                pd.DataFrame(columns=["good", "words", "stars", "inputs", "summary"]), file_path
            )
            with pytest.raises(RuntimeError, match="empty"):
                response = jamai.import_table_data(
                    table_type,
                    p.TableDataImportRequest(
                        file_path=file_path, table_id=TABLE_ID_A, stream=stream
                    ),
                )
                if stream:
                    response = list(response)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 0


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_export_data(client_cls: Type[JamAI], table_type: p.TableType):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        data = [
            {"good": True, "words": 5, "stars": 0.0, "inputs": TEXT, "summary": TEXT},
            {"good": False, "words": 5, "stars": 1.0, "inputs": TEXT, "summary": TEXT},
            {"good": True, "words": 5, "stars": 2.0, "inputs": TEXT_CN, "summary": TEXT},
            {"good": False, "words": 5, "stars": 3.0, "inputs": TEXT_JP, "summary": TEXT},
        ]
        for d in data:
            _add_row(jamai, table_type, False, data=d)
        rows = jamai.list_table_rows(table_type, TABLE_ID_A, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 4

        csv_data = jamai.export_table_data(table_type, TABLE_ID_A).decode("utf-8")
        exported_rows = csv_to_df(csv_data).to_dict(orient="records")
        assert len(exported_rows) == 4
        for row, d in zip(exported_rows, data):
            for k, v in d.items():
                assert row[k] == v, f"Exported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"


@flaky(max_runs=3, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_import_export_round_trip(client_cls: Type[JamAI], table_type: p.TableType, stream: bool):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        with TemporaryDirectory() as tmp_dir:
            assert isinstance(table, p.TableMetaResponse)
            data = [
                {"good": True, "words": 5, "stars": 0.0, "inputs": TEXT, "summary": TEXT},
                {"good": False, "words": 5, "stars": 1.0, "inputs": TEXT, "summary": TEXT},
                {"good": True, "words": 5, "stars": 2.0, "inputs": TEXT_CN, "summary": TEXT},
                {"good": False, "words": 5, "stars": 3.0, "inputs": TEXT_JP, "summary": TEXT},
            ]
            file_path = join(tmp_dir, "test_import_export_round_trip.csv")
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "good": "bool",
                    "words": "int32",
                    "stars": "float32",
                    "inputs": "string",
                    "summary": "string",
                }
            )
            df_to_csv(df, file_path)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=TABLE_ID_A,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                if table_type == p.TableType.chat:
                    assert len(responses) > 0
                else:
                    assert len(responses) == 0
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"

            csv_data = jamai.export_table_data(table_type, TABLE_ID_A).decode("utf-8")
            exported_df = csv_to_df(csv_data)[df.columns.tolist()]
            assert df.eq(exported_df).all(axis=None)


if __name__ == "__main__":
    test_import_export_round_trip(JamAI, p.TableType.chat, True)
