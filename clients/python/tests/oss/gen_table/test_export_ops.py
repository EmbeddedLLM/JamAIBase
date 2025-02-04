from collections import defaultdict
from contextlib import contextmanager
from os.path import join
from tempfile import TemporaryDirectory
from time import sleep
from typing import Type

import httpx
import numpy as np
import pandas as pd
import pytest
from flaky import flaky

from jamaibase import JamAI
from jamaibase import protocol as p
from jamaibase.utils.io import csv_to_df, df_to_csv

CLIENT_CLS = [JamAI]
TABLE_TYPES = [p.TableType.action, p.TableType.knowledge, p.TableType.chat]

TABLE_ID_A = "table_a"
TABLE_ID_B = "table_b"
TABLE_ID_C = "table_c"
TABLE_ID_X = "table_x"
TEXT = '"Arrival" is a 2016 American science fiction drama film directed by Denis Villeneuve and adapted by Eric Heisserer.'
TEXT_CN = (
    '"Arrival" 《降临》是一部 2016 年美国科幻剧情片，由丹尼斯·维伦纽瓦执导，埃里克·海瑟尔改编。'
)
TEXT_JP = '"Arrival" 「Arrival」は、ドゥニ・ヴィルヌーヴが監督し、エリック・ハイセラーが脚色した2016年のアメリカのSFドラマ映画です。'


@pytest.fixture(scope="module", autouse=True)
def setup():
    client = JamAI()
    _delete_tables(client)
    yield
    _delete_tables(client)


def _delete_tables(jamai: JamAI):
    batch_size = 100
    for table_type in TABLE_TYPES:
        offset, total = 0, 1
        while offset < total:
            tables = jamai.table.list_tables(table_type, offset=offset, limit=batch_size)
            assert isinstance(tables.items, list)
            for table in tables.items:
                jamai.table.delete_table(table_type, table.id)
            total = tables.total
            offset += batch_size


def _get_chat_model(jamai: JamAI) -> str:
    models = jamai.model_names(prefer="openai/gpt-4o-mini", capabilities=["chat"])
    return models[0]


def _rerun_on_fs_error_with_delay(err, *args):
    if "LanceError(IO): Generic LocalFileSystem error" in str(err):
        sleep(1)
        return True
    return False


@contextmanager
def _create_table(
    jamai: JamAI,
    table_type: p.TableType,
    table_id: str = TABLE_ID_A,
    cols: list[p.ColumnSchemaCreate] | None = None,
    chat_cols: list[p.ColumnSchemaCreate] | None = None,
    embedding_model: str | None = None,
    delete_first: bool = True,
):
    try:
        if delete_first:
            jamai.table.delete_table(table_type, table_id)
        if cols is None:
            cols = [
                p.ColumnSchemaCreate(id="good", dtype="bool"),
                p.ColumnSchemaCreate(id="words", dtype="int"),
                p.ColumnSchemaCreate(id="stars", dtype="float"),
                p.ColumnSchemaCreate(id="inputs", dtype="str"),
                p.ColumnSchemaCreate(id="photo", dtype="image"),
                p.ColumnSchemaCreate(
                    id="summary",
                    dtype="str",
                    gen_config=p.LLMGenConfig(
                        model=_get_chat_model(jamai),
                        system_prompt="You are a concise assistant.",
                        # Interpolate string and non-string input columns
                        prompt="Summarise this in ${words} words:\n\n${inputs}",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ),
                ),
                p.ColumnSchemaCreate(
                    id="captioning",
                    dtype="str",
                    gen_config=p.LLMGenConfig(
                        model="",
                        system_prompt="You are a concise assistant.",
                        # Interpolate file input column
                        prompt="${photo} \n\nWhat's in the image?",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=300,
                    ),
                ),
            ]
        if chat_cols is None:
            chat_cols = [
                p.ColumnSchemaCreate(id="User", dtype="str"),
                p.ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=p.LLMGenConfig(
                        model=_get_chat_model(jamai),
                        system_prompt="You are a wacky assistant.",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=5,
                    ),
                ),
            ]

        if table_type == p.TableType.action:
            table = jamai.table.create_action_table(
                p.ActionTableSchemaCreate(id=table_id, cols=cols)
            )
        elif table_type == p.TableType.knowledge:
            if embedding_model is None:
                embedding_model = ""
            table = jamai.table.create_knowledge_table(
                p.KnowledgeTableSchemaCreate(
                    id=table_id, cols=cols, embedding_model=embedding_model
                )
            )
        elif table_type == p.TableType.chat:
            table = jamai.table.create_chat_table(
                p.ChatTableSchemaCreate(id=table_id, cols=chat_cols + cols)
            )
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, p.TableMetaResponse)
        yield table
    finally:
        jamai.table.delete_table(table_type, table_id)


def _add_row(
    jamai: JamAI,
    table_type: p.TableType,
    stream: bool,
    table_name: str = TABLE_ID_A,
    data: dict | None = None,
    knowledge_data: dict | None = None,
    chat_data: dict | None = None,
):
    if data is None:
        upload_response = jamai.file.upload_file("clients/python/tests/files/jpeg/rabbit.jpeg")
        data = dict(
            good=True,
            words=5,
            stars=7.9,
            inputs=TEXT,
            photo=upload_response.uri,
        )

    if knowledge_data is None:
        knowledge_data = dict(
            Title="Dune: Part Two.",
            Text='"Dune: Part Two" is a 2024 American epic science fiction film.',
        )
    if chat_data is None:
        chat_data = dict(User="Tell me a joke.")
    if table_type == p.TableType.action:
        pass
    elif table_type == p.TableType.knowledge:
        data.update(knowledge_data)
    elif table_type == p.TableType.chat:
        data.update(chat_data)
    else:
        raise ValueError(f"Invalid table type: {table_type}")
    response = jamai.table.add_table_rows(
        table_type,
        p.RowAddRequest(table_id=table_name, data=[data], stream=stream),
    )
    if stream:
        return response
    assert isinstance(response, p.GenTableRowsChatCompletionChunks)
    assert len(response.rows) == 1
    return response.rows[0]


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
@pytest.mark.parametrize("delimiter", [","], ids=["comma_delimiter"])
def test_import_data_complete(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    stream: bool,
    delimiter: str,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        # Complete CSV
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_data_complete.csv")
            chat_data = {"User": ".", "AI": ".", "Extra Data": TEXT}
            data = [
                {
                    "good": True,
                    "words": 5,
                    "stars": 0.0,
                    "inputs": "",
                    "summary": "",
                    "captioning": "",
                    **chat_data,
                },
                {
                    "good": False,
                    "words": 5,
                    "stars": 1.0,
                    "inputs": TEXT,
                    "summary": "",
                    "captioning": "",
                    **chat_data,
                },
                {
                    "good": True,
                    "words": 5,
                    "stars": 2.0,
                    "inputs": TEXT_CN,
                    "summary": "",
                    "captioning": "",
                    **chat_data,
                },
                {
                    "good": False,
                    "words": 5,
                    "stars": 3.0,
                    "inputs": TEXT_JP,
                    "summary": "",
                    "captioning": "",
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
                    "captioning": "string",
                }
            )
            df_to_csv(df, file_path, delimiter)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=table.id,
                    stream=stream,
                    delimiter=delimiter,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) == 0
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"

        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 4
        for row, d in zip(rows.items[::-1], data, strict=True):
            if table_type == p.TableType.knowledge:
                assert isinstance(row["Text Embed"]["value"], list)
                assert len(row["Text Embed"]["value"]) > 0
                assert isinstance(row["Title Embed"]["value"], list)
                assert len(row["Title Embed"]["value"]) > 0
            for k, v in d.items():
                if k not in row and k in chat_data:
                    continue
                if v == "":
                    assert (
                        row[k]["value"] is None
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"
                else:
                    assert (
                        row[k]["value"] == v
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_import_data_cast_to_string(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    stream: bool,
):
    jamai = client_cls()
    gen_cfg = p.LLMGenConfig()
    cols = [
        p.ColumnSchemaCreate(id="bool", dtype="str"),
        p.ColumnSchemaCreate(id="int", dtype="str"),
        p.ColumnSchemaCreate(id="float", dtype="str"),
        p.ColumnSchemaCreate(id="str", dtype="str"),
        # p.ColumnSchemaCreate(id="bool_out", dtype="bool", gen_config=gen_cfg),
        # p.ColumnSchemaCreate(id="int_out", dtype="int", gen_config=gen_cfg),
        # p.ColumnSchemaCreate(id="float_out", dtype="float", gen_config=gen_cfg),
        p.ColumnSchemaCreate(id="str_out", dtype="str", gen_config=gen_cfg),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, p.TableMetaResponse)

        # Complete CSV
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_data_cast_to_string.csv")
            chat_data = {"User": ".", "AI": ".", "Extra Data": TEXT}
            data = [
                {
                    "bool": True,
                    # "bool_out": False,
                    "int": 5,
                    # "int_out": -5,
                    "float": 5.1,
                    # "float_out": -5.1,
                    "str": "True",
                    "str_out": "False",
                    **chat_data,
                },
            ]
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "bool": "bool",
                    # "bool_out": "bool",
                    "int": "int32",
                    # "int_out": "int32",
                    "float": "float64",
                    # "float_out": "float64",
                    "str": "string",
                    "str_out": "string",
                }
            )
            df_to_csv(df, file_path)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=table.id,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) == 0
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"

        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        for row, d in zip(rows.items[::-1], data, strict=True):
            if table_type == p.TableType.knowledge:
                assert isinstance(row["Text Embed"]["value"], list)
                assert len(row["Text Embed"]["value"]) > 0
                assert isinstance(row["Title Embed"]["value"], list)
                assert len(row["Title Embed"]["value"]) > 0
            for k, v in d.items():
                if k not in row and k in chat_data:
                    continue
                assert row[k]["value"] == str(
                    v
                ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_import_data_cast_from_string(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    stream: bool,
):
    jamai = client_cls()
    gen_cfg = p.LLMGenConfig()
    cols = [
        p.ColumnSchemaCreate(id="bool", dtype="bool"),
        p.ColumnSchemaCreate(id="int", dtype="int"),
        p.ColumnSchemaCreate(id="float", dtype="float"),
        p.ColumnSchemaCreate(id="str", dtype="str"),
        # p.ColumnSchemaCreate(id="bool_out", dtype="bool", gen_config=gen_cfg),
        # p.ColumnSchemaCreate(id="int_out", dtype="int", gen_config=gen_cfg),
        # p.ColumnSchemaCreate(id="float_out", dtype="float", gen_config=gen_cfg),
        p.ColumnSchemaCreate(id="str_out", dtype="str", gen_config=gen_cfg),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, p.TableMetaResponse)

        # Complete CSV
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_data_cast_to_string.csv")
            chat_data = {"User": ".", "AI": ".", "Extra Data": TEXT}
            data = [
                {
                    "bool": "True",
                    # "bool_out": "False",
                    "int": "5",
                    # "int_out": "-5",
                    "float": "5.1",
                    # "float_out": "-5.1",
                    "str": "True",
                    "str_out": "False",
                    **chat_data,
                },
            ]
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "bool": "string",
                    # "bool_out": "string",
                    "int": "string",
                    # "int_out": "string",
                    "float": "string",
                    # "float_out": "string",
                    "str": "string",
                    "str_out": "string",
                }
            )
            df_to_csv(df, file_path)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=table.id,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) == 0
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"

        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        for row, d in zip(rows.items[::-1], data, strict=True):
            if table_type == p.TableType.knowledge:
                assert isinstance(row["Text Embed"]["value"], list)
                assert len(row["Text Embed"]["value"]) > 0
                assert isinstance(row["Title Embed"]["value"], list)
                assert len(row["Title Embed"]["value"]) > 0
            for k, v in d.items():
                if k not in row and k in chat_data:
                    continue
                assert (
                    str(row[k]["value"]) == v
                ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_import_data_cast_dtype(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        # Complete CSV
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_data_cast_dtype.csv")
            chat_data = {"User": ".", "AI": ".", "Extra Data": TEXT}
            gt_data = [
                {
                    "good": True,
                    "words": 5,
                    "stars": 0.0,
                    "inputs": "50",
                    "summary": "",
                    "captioning": "",
                    **chat_data,
                }
            ]
            data = [
                {
                    "good": "True",
                    "words": "5.0",
                    "stars": 0,
                    "inputs": 50,
                    "summary": "",
                    "captioning": "",
                    **chat_data,
                },
            ]
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "good": "string",
                    "words": "string",
                    "stars": "int32",
                    "inputs": "int32",
                    "summary": "string",
                    "captioning": "string",
                }
            )
            df_to_csv(df, file_path)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=table.id,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) == 0
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"

        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == len(data)
        for row, d in zip(rows.items[::-1], gt_data, strict=True):
            if table_type == p.TableType.knowledge:
                assert isinstance(row["Text Embed"]["value"], list)
                assert len(row["Text Embed"]["value"]) > 0
                assert isinstance(row["Title Embed"]["value"], list)
                assert len(row["Title Embed"]["value"]) > 0
            for k, v in d.items():
                if k not in row and k in chat_data:
                    continue
                if v == "":
                    assert (
                        row[k]["value"] is None
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"
                else:
                    assert (
                        row[k]["value"] == v
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_import_data_incomplete(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        # CSV without input column
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_data_complete.csv")
            cols = ["good", "words", "stars", "inputs", "summary"]
            chat_data = {"User": ".", "AI": "."}
            data = [
                {
                    "good": True,
                    "stars": 0.0,
                    "inputs": TEXT,
                    "summary": TEXT,
                    "captioning": "",
                    **chat_data,
                },
                {
                    "good": False,
                    "stars": 1.0,
                    "inputs": TEXT,
                    "summary": TEXT,
                    "captioning": "",
                    **chat_data,
                },
                {
                    "good": True,
                    "stars": 2.0,
                    "inputs": TEXT_CN,
                    "summary": TEXT,
                    "captioning": "",
                    **chat_data,
                },
                {
                    "good": False,
                    "stars": 3.0,
                    "inputs": TEXT_JP,
                    "summary": TEXT,
                    "captioning": "",
                    **chat_data,
                },
            ]
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "good": "bool",
                    "stars": "float32",
                    "inputs": "string",
                    "summary": "string",
                    "captioning": "string",
                }
            )
            df_to_csv(df, file_path)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=table.id,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) == 0
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"

        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 4
        for row, d in zip(rows.items[::-1], data, strict=True):
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
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_import_data_with_generation(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        # CSV without output column
        with TemporaryDirectory() as tmp_dir:
            chat_data = {"User": ".", "AI": "."}
            data = [
                {
                    "good": False,
                    "words": 5,
                    "stars": 1.0,
                    "inputs": TEXT,
                    **chat_data,
                },
                {
                    "good": False,
                    "words": 5,
                    "stars": 3.0,
                    "inputs": TEXT_JP,
                    **chat_data,
                },
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
                    table_id=table.id,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) > 0
                assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
                assert all(r.object == "gen_table.completion.chunk" for r in responses)
                assert all(r.output_column_name in ("summary", "captioning") for r in responses)
                summaries = defaultdict(list)
                for r in responses:
                    if r.output_column_name != "summary":
                        continue
                    summaries[r.row_id].append(r.text)
                summaries = {k: "".join(v) for k, v in summaries.items()}
                assert len(summaries) == 2
                assert all(len(v) > 0 for v in summaries.values())
                assert all(isinstance(r, p.GenTableStreamChatCompletionChunk) for r in responses)
                assert all(
                    isinstance(r.usage, p.CompletionUsage)
                    for r in responses
                    if r.output_column_name in ("summary", "captioning")
                )
                assert all(
                    isinstance(r.prompt_tokens, int)
                    for r in responses
                    if r.output_column_name in ("summary", "captioning")
                )
                assert all(
                    isinstance(r.completion_tokens, int)
                    for r in responses
                    if r.output_column_name in ("summary", "captioning")
                )
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"
                for row in response.rows:
                    for output_column_name in ("summary", "captioning"):
                        assert len(row.columns[output_column_name].text) > 0
                        assert isinstance(row.columns[output_column_name].usage, p.CompletionUsage)
                        assert isinstance(row.columns[output_column_name].prompt_tokens, int)
                        assert isinstance(row.columns[output_column_name].completion_tokens, int)

        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        for row, d in zip(rows.items[::-1], data, strict=True):
            for k, v in d.items():
                if k not in row and k in chat_data:
                    continue
                if v == "":
                    assert (
                        row[k]["value"] is None
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"
                else:
                    assert (
                        row[k]["value"] == v
                    ), f"Imported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_import_data_empty(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        with TemporaryDirectory() as tmp_dir:
            # Empty
            file_path = join(tmp_dir, "empty.csv")
            df_to_csv(pd.DataFrame(columns=[]), file_path)
            with pytest.raises(RuntimeError, match="No columns to parse"):
                response = jamai.import_table_data(
                    table_type,
                    p.TableDataImportRequest(
                        file_path=file_path, table_id=table.id, stream=stream
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
                        file_path=file_path, table_id=table.id, stream=stream
                    ),
                )
                if stream:
                    response = list(response)
        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_import_data_with_vector(
    client_cls: Type[JamAI],
    stream: bool,
):
    table_type = p.TableType.knowledge
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)

        # Add a row first to figure out the vector length
        response = jamai.table.add_table_rows(
            table_type,
            p.RowAddRequest(
                table_id=table.id,
                data=[
                    {
                        "good": True,
                        "words": 5,
                        "stars": 0.0,
                        "inputs": "",
                        "summary": "",
                    }
                ],
                stream=False,
            ),
        )
        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        vector_len = len(rows.items[0]["Text Embed"]["value"])

        # CSV with vector data
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_data_with_vector.csv")
            vector_data = {
                "Text Embed": np.random.rand(vector_len).tolist(),
                "Title Embed": np.random.rand(vector_len).tolist(),
                "Extra Data": TEXT,
            }
            data = [
                {
                    "good": True,
                    "words": 5,
                    "stars": 0.0,
                    "inputs": "",
                    "summary": "",
                    "captioning": "",
                    **vector_data,
                },
                {
                    "good": False,
                    "words": 5,
                    "stars": 1.0,
                    "inputs": TEXT,
                    "summary": "",
                    "captioning": "",
                    **vector_data,
                },
                {
                    "good": True,
                    "words": 5,
                    "stars": 2.0,
                    "inputs": TEXT_CN,
                    "summary": "",
                    "captioning": "",
                    **vector_data,
                },
                {
                    "good": False,
                    "words": 5,
                    "stars": 3.0,
                    "inputs": TEXT_JP,
                    "summary": "",
                    "captioning": "",
                    **vector_data,
                },
            ]
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "good": "bool",
                    "words": "int32",
                    "stars": "float32",
                    "inputs": "string",
                    "summary": "string",
                    "captioning": "string",
                }
            )
            df_to_csv(df, file_path)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=table.id,
                    stream=stream,
                ),
            )
            if stream:
                responses = [r for r in response]
                assert len(responses) == 0
            else:
                assert isinstance(response, p.GenTableRowsChatCompletionChunks)
                assert response.object == "gen_table.completion.rows"

        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 5, len(rows.items)
        for row in rows.items[::-1]:
            assert isinstance(row["Text Embed"]["value"], list)
            assert len(row["Text Embed"]["value"]) > 0
            assert isinstance(row["Title Embed"]["value"], list)
            assert len(row["Title Embed"]["value"]) > 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("delimiter", [","], ids=["comma_delimiter"])
def test_export_data(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    delimiter: str,
):
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
        rows = jamai.table.list_table_rows(table_type, table.id, vec_decimals=2)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 4
        # All columns
        csv_data = jamai.export_table_data(table_type, table.id, delimiter=delimiter)
        csv_df = csv_to_df(csv_data.decode("utf-8"), sep=delimiter)
        exported_rows = csv_df.to_dict(orient="records")
        assert len(exported_rows) == 4
        for row, d in zip(exported_rows, data, strict=True):
            for k, v in d.items():
                assert row[k] == v, f"Exported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"
        # Subset of columns
        columns = ["good", "words"]
        csv_data = jamai.export_table_data(table_type, table.id, columns, delimiter)
        csv_df = csv_to_df(csv_data.decode("utf-8"), sep=delimiter)
        exported_rows = csv_df.to_dict(orient="records")
        assert len(exported_rows) == 4
        for row, d in zip(exported_rows, data, strict=True):
            for k, v in d.items():
                if k in columns:
                    assert (
                        row[k] == v
                    ), f"Exported data is wrong: col=`{k}`  val={row[k]}  ori=`{v}`"
                else:
                    assert k not in row


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
@pytest.mark.parametrize("delimiter", [",", "\t"], ids=["comma_delimiter", "tab_delimiter"])
def test_import_export_data_round_trip(
    client_cls: Type[JamAI],
    table_type: p.TableType,
    stream: bool,
    delimiter: str,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        with TemporaryDirectory() as tmp_dir:
            data = [
                {
                    "good": True,
                    "words": 5,
                    "stars": 0.0,
                    "inputs": TEXT,
                    "summary": TEXT,
                    "captioning": "",
                },
                {
                    "good": False,
                    "words": 5,
                    "stars": 1.0,
                    "inputs": TEXT,
                    "summary": TEXT,
                    "captioning": "",
                },
                {
                    "good": True,
                    "words": 5,
                    "stars": 2.0,
                    "inputs": TEXT_CN,
                    "summary": TEXT,
                    "captioning": "",
                },
                {
                    "good": False,
                    "words": 5,
                    "stars": 3.0,
                    "inputs": TEXT_JP,
                    "summary": TEXT,
                    "captioning": "",
                },
            ]
            file_path = join(tmp_dir, "test_import_export_round_trip.csv")
            df = pd.DataFrame.from_dict(data).astype(
                {
                    "good": "bool",
                    "words": "int32",
                    "stars": "float32",
                    "inputs": "string",
                    "summary": "string",
                    "captioning": "string",
                }
            )
            df_to_csv(df, file_path, delimiter)
            response = jamai.import_table_data(
                table_type,
                p.TableDataImportRequest(
                    file_path=file_path,
                    table_id=table.id,
                    stream=stream,
                    delimiter=delimiter,
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

            csv_data = jamai.export_table_data(table_type, table.id, delimiter=delimiter)
            csv_df = csv_to_df(csv_data.decode("utf-8"), sep=delimiter)
            exported_df = csv_df[df.columns.tolist()]
            assert df.eq(exported_df).all(axis=None)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_import_export_round_trip(
    client_cls: Type[JamAI],
    table_type: p.TableType,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, p.TableMetaResponse)
        _add_row(jamai, table_type, False)
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
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert len(rows.items) == 3
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_export_round_trip.parquet")
            # Export
            with open(file_path, "wb") as f:
                f.write(jamai.table.export_table(table_type, table.id))
            # Import
            table_id_dst = f"{table.id}_import"
            try:
                imported_table = jamai.table.import_table(
                    table_type,
                    p.TableImportRequest(
                        file_path=file_path,
                        table_id_dst=table_id_dst,
                    ),
                )
                assert isinstance(imported_table, p.TableMetaResponse)
                assert imported_table.id == table_id_dst
                imported_rows = jamai.table.list_table_rows(table_type, imported_table.id)
                assert len(imported_rows.items) == len(rows.items)
                assert imported_rows.items[0]["photo"]["value"] is None
                assert imported_rows.items[1]["photo"]["value"] is None
                assert isinstance(imported_rows.items[2]["photo"]["value"], str)
                raw_urls = jamai.file.get_raw_urls(
                    [rows.items[2]["photo"]["value"], imported_rows.items[2]["photo"]["value"]]
                )
                raw_files = [
                    httpx.get(url, headers={"X-PROJECT-ID": "default"}).content
                    for url in raw_urls.urls
                ]
                assert (
                    raw_urls.urls[0] != raw_urls.urls[1]
                )  # URL is different but file should match
                assert raw_files[0] == raw_files[1]
                rows.items[2]["photo"]["value"] = raw_files[0]
                imported_rows.items[2]["photo"]["value"] = raw_files[1]
                assert imported_rows.items == rows.items
            finally:
                jamai.table.delete_table(table_type, table_id_dst)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_import_export_wrong_table_type(
    client_cls: Type[JamAI],
):
    jamai = client_cls()
    with _create_table(jamai, "action") as table:
        assert isinstance(table, p.TableMetaResponse)
        _add_row(jamai, "action", False)
        _add_row(
            jamai,
            "action",
            False,
            data=dict(good=True, words=5, stars=5 / 3, inputs=TEXT, summary="<dummy>"),
        )
        rows = jamai.table.list_table_rows("action", table.id)
        assert len(rows.items) == 2
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_import_export_round_trip.parquet")
            # Export
            with open(file_path, "wb") as f:
                f.write(jamai.export_table("action", table.id))
            table_id_dst = f"{table.id}_import"
            # Import as knowledge
            with pytest.raises(RuntimeError):
                jamai.import_table(
                    "knowledge",
                    p.TableImportRequest(
                        file_path=file_path,
                        table_id_dst=table_id_dst,
                    ),
                )
            # Import as chat
            with pytest.raises(RuntimeError):
                jamai.import_table(
                    "chat",
                    p.TableImportRequest(
                        file_path=file_path,
                        table_id_dst=table_id_dst,
                    ),
                )


if __name__ == "__main__":
    test_import_export_round_trip(JamAI, p.TableType.action)
