import re
from contextlib import contextmanager
from decimal import Decimal
from os.path import basename, join
from tempfile import TemporaryDirectory
from time import sleep
from typing import Any, Generator, Type

import httpx
import pandas as pd
import pytest
from flaky import flaky
from pydantic import ValidationError

from jamaibase import JamAI
from jamaibase import types as t
from jamaibase.types import IMAGE_FILE_EXTENSIONS
from jamaibase.utils.exceptions import ResourceNotFoundError
from jamaibase.utils.io import df_to_csv

CLIENT_CLS = [JamAI]
TABLE_TYPES = [t.TableType.action, t.TableType.knowledge, t.TableType.chat]

TABLE_ID_A = "table_a"
TABLE_ID_B = "table_b"
TABLE_ID_C = "table_c"
TABLE_ID_X = "table_x"
TEXT = '"Arrival" is a 2016 American science fiction drama film directed by Denis Villeneuve and adapted by Eric Heisserer.'
TEXT_CN = (
    '"Arrival" 《降临》是一部 2016 年美国科幻剧情片，由丹尼斯·维伦纽瓦执导，埃里克·海瑟尔改编。'
)
TEXT_JP = '"Arrival" 「Arrival」は、ドゥニ・ヴィルヌーヴが監督し、エリック・ハイセラーが脚色した2016年のアメリカのSFドラマ映画です。'

EMBED_WHITE_LIST_EXT = [
    "application/pdf",  # pdf
    "text/markdown",  # md
    "text/plain",  # txt
    "text/html",  # html
    "text/xml",  # xml
    "application/xml",  # xml
    "application/json",  # json
    "application/jsonl",  # jsonl
    "application/x-ndjson",  # alternative for jsonl
    "application/json-lines",  # another alternative for jsonl
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "text/tab-separated-values",  # tsv
    "text/csv",  # csv
]


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


def _get_audio_model(jamai: JamAI) -> str:
    models = jamai.model_names(prefer="ellm/Qwen/Qwen-2-Audio-7B", capabilities=["audio"])
    return models[0]


def _get_chat_only_model(jamai: JamAI) -> str:
    chat_models = jamai.model_names(
        prefer="ellm/meta-llama/Llama-3.1-8B-Instruct", capabilities=["chat"]
    )
    image_models = jamai.model_names(prefer="", capabilities=["image"])
    return list(set(chat_models) - set(image_models))[0]


def _get_reranking_model(jamai: JamAI) -> str:
    models = jamai.model_names(prefer="cohere/rerank-english-v3.0", capabilities=["rerank"])
    return models[0]


def _rerun_on_fs_error_with_delay(err, *args):
    if "LanceError(IO): Generic LocalFileSystem error" in str(err):
        sleep(1)
        return True
    return False


@contextmanager
def _create_table(
    jamai: JamAI,
    table_type: t.TableType,
    table_id: str = TABLE_ID_A,
    cols: list[t.ColumnSchemaCreate] | None = None,
    chat_cols: list[t.ColumnSchemaCreate] | None = None,
    embedding_model: str | None = None,
    delete_first: bool = True,
):
    try:
        if delete_first:
            jamai.table.delete_table(table_type, table_id)
        if cols is None:
            cols = [
                t.ColumnSchemaCreate(id="good", dtype="bool"),
                t.ColumnSchemaCreate(id="words", dtype="int"),
                t.ColumnSchemaCreate(id="stars", dtype="float"),
                t.ColumnSchemaCreate(id="inputs", dtype="str"),
                t.ColumnSchemaCreate(id="photo", dtype="image"),
                t.ColumnSchemaCreate(id="audio", dtype="audio"),
                t.ColumnSchemaCreate(id="paper", dtype="document"),
                t.ColumnSchemaCreate(
                    id="summary",
                    dtype="str",
                    gen_config=t.LLMGenConfig(
                        model=_get_chat_model(jamai),
                        system_prompt="You are a concise assistant.",
                        # Interpolate string and non-string input columns
                        prompt="Summarise this in ${words} words:\n\n${inputs}",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ),
                ),
                t.ColumnSchemaCreate(
                    id="captioning",
                    dtype="str",
                    gen_config=t.LLMGenConfig(
                        model="",
                        system_prompt="You are a concise assistant.",
                        # Interpolate file input column
                        prompt="${photo} \n\nWhat's in the image?",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=20,
                    ),
                ),
                t.ColumnSchemaCreate(
                    id="narration",
                    dtype="str",
                    gen_config=t.LLMGenConfig(
                        model="",
                        prompt="${audio} \n\nWhat happened?",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ),
                ),
                t.ColumnSchemaCreate(
                    id="concept",
                    dtype="str",
                    gen_config=t.LLMGenConfig(
                        model="",
                        prompt="${paper} \n\nTell the main concept of the paper in 5 words.",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
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
                        model=_get_chat_model(jamai),
                        system_prompt="You are a wacky assistant.",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=5,
                    ),
                ),
            ]

        if table_type == t.TableType.action:
            table = jamai.table.create_action_table(
                t.ActionTableSchemaCreate(id=table_id, cols=cols)
            )
        elif table_type == t.TableType.knowledge:
            if embedding_model is None:
                embedding_model = ""
            table = jamai.table.create_knowledge_table(
                t.KnowledgeTableSchemaCreate(
                    id=table_id, cols=cols, embedding_model=embedding_model
                )
            )
        elif table_type == t.TableType.chat:
            table = jamai.table.create_chat_table(
                t.ChatTableSchemaCreate(id=table_id, cols=chat_cols + cols)
            )
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, t.TableMetaResponse)
        yield table
    finally:
        jamai.table.delete_table(table_type, table_id)


def _add_row(
    jamai: JamAI,
    table_type: t.TableType,
    stream: bool,
    table_name: str = TABLE_ID_A,
    data: dict | None = None,
    knowledge_data: dict | None = None,
    chat_data: dict | None = None,
):
    if data is None:
        image_upload_response = jamai.file.upload_file(
            "clients/python/tests/files/jpeg/rabbit.jpeg"
        )
        audio_upload_response = jamai.file.upload_file(
            "clients/python/tests/files/mp3/turning-a4-size-magazine.mp3"
        )
        document_upload_response = jamai.file.upload_file(
            "clients/python/tests/files/pdf/LLMs as Optimizers [DeepMind ; 2023].pdf"
        )
        data = dict(
            good=True,
            words=5,
            stars=7.9,
            inputs=TEXT,
            photo=image_upload_response.uri,
            audio=audio_upload_response.uri,
            paper=document_upload_response.uri,
        )

    if knowledge_data is None:
        knowledge_data = dict(
            Title="Dune: Part Two.",
            Text='"Dune: Part Two" is a 2024 American epic science fiction film.',
        )
    if chat_data is None:
        chat_data = dict(User="Tell me a joke.")
    if table_type == t.TableType.action:
        pass
    elif table_type == t.TableType.knowledge:
        data.update(knowledge_data)
    elif table_type == t.TableType.chat:
        data.update(chat_data)
    else:
        raise ValueError(f"Invalid table type: {table_type}")
    response = jamai.table.add_table_rows(
        table_type,
        t.MultiRowAddRequest(table_id=table_name, data=[data], stream=stream),
    )
    if stream:
        return response
    assert isinstance(response, t.MultiRowCompletionResponse)
    assert len(response.rows) == 1
    return response.rows[0]


def _assert_is_vector(x: Any):
    assert isinstance(x, list), f"Not a list: {x}"
    assert len(x) > 0, f"Not a non-empty list: {x}"
    assert all(isinstance(v, float) for v in x), f"Not a list of floats: {x}"


def _collect_text(
    responses: t.MultiRowCompletionResponse | Generator[t.CellCompletionResponse, None, None],
    col: str,
):
    if isinstance(responses, t.MultiRowCompletionResponse):
        return "".join(r.columns[col].text for r in responses.rows)
    return "".join(r.text for r in responses if r.output_column_name == col)


def _get_exponent(x: float) -> int:
    return Decimal(str(x)).as_tuple().exponent


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_knowledge_table_embedding(
    client_cls: Type[JamAI],
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, "knowledge", cols=[], embedding_model="") as table:
        assert isinstance(table, t.TableMetaResponse)
        # Don't include embeddings
        data = [
            dict(
                Title="Six-spot burnet",
                Text="The six-spot burnet is a day-flying moth of the family Zygaenidae.",
            ),
            # Test missing Title
            dict(
                Text=(
                    "In machine learning, a neural network is a model inspired by "
                    "biological neural networks in animal brains."
                ),
            ),
            # Test missing Text
            dict(
                Title=(
                    "A supercomputer is a type of computer with a high level of performance "
                    "as compared to a general-purpose computer."
                ),
            ),
        ]
        response = jamai.table.add_table_rows(
            "knowledge",
            t.MultiRowAddRequest(table_id=table.id, data=data, stream=stream),
        )
        if stream:
            responses = [r for r in response]
            assert len(responses) == 0  # We currently dont return anything if LLM is not called
        else:
            assert isinstance(response.rows[0], t.RowCompletionResponse)
        # Check embeddings
        rows = jamai.table.list_table_rows("knowledge", table.id)
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


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_knowledge_table_no_embed_input(
    client_cls: Type[JamAI],
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="words", dtype="int"),
        t.ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model=_get_chat_model(jamai),
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(jamai, "knowledge", cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Purposely leave out Title and Text
        data = dict(words=5)
        response = jamai.table.add_table_rows(
            "knowledge",
            t.MultiRowAddRequest(table_id=table.id, data=[data], stream=stream),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            summary = "".join(r.text for r in responses if r.output_column_name == "summary")
            assert len(summary) > 0
        else:
            assert isinstance(response.rows[0], t.RowCompletionResponse)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_full_text_search(
    client_cls: Type[JamAI],
    stream: bool,
):
    jamai = client_cls()
    cols = [t.ColumnSchemaCreate(id="text", dtype="str")]
    with _create_table(jamai, "action", cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Add data
        texts = [
            '"Dune: Part Two" 2024 is Denis\'s science-fiction film.',
            '"Dune: Part Two" 2024 is Denis\'s film.',
            '"Arrival" 《降临》是一部 2016 年美国科幻剧情片，由丹尼斯·维伦纽瓦执导。',
            '"Arrival" 『デューン: パート 2』2024 はデニスの映画です。',
        ]
        response = jamai.table.add_table_rows(
            "action",
            t.MultiRowAddRequest(
                table_id=table.id, data=[{"text": t} for t in texts], stream=stream
            ),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response, t.MultiRowCompletionResponse)

        # Search
        def _search(query: str):
            return jamai.table.hybrid_search(
                "action", t.SearchRequest(table_id=table.id, query=query)
            )

        assert len(_search("AND")) == 0  # SQL-like statements should still work
        assert len(_search("《")) == 0  # Not supported
        assert len(_search("scien*")) == 0  # Not supported
        assert len(_search("film")) == 2
        assert len(_search("science -fiction")) == 1
        assert len(_search("science-fiction")) == 1
        assert len(_search("science -fiction\n2016")) == 2
        assert len(_search("美国")) == 0  # Not supported


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_rag(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    # Create Knowledge Table and add some rows
    with _create_table(jamai, "knowledge", cols=[]) as ktable:
        assert isinstance(ktable, t.TableMetaResponse)
        response = jamai.table.add_table_rows(
            t.TableType.knowledge,
            t.MultiRowAddRequest(
                table_id=ktable.id,
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
        assert isinstance(response, t.MultiRowCompletionResponse)
        assert isinstance(response.rows[0], t.RowCompletionResponse)
        rows = jamai.table.list_table_rows(t.TableType.knowledge, ktable.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 3

        # Create the other table
        cols = [
            t.ColumnSchemaCreate(id="question", dtype="str"),
            t.ColumnSchemaCreate(id="words", dtype="int"),
            t.ColumnSchemaCreate(
                id="rag",
                dtype="str",
                gen_config=t.LLMGenConfig(
                    model=_get_chat_model(jamai),
                    system_prompt="You are a concise assistant.",
                    prompt="${question}? Summarise in ${words} words",
                    temperature=0.001,
                    top_p=0.001,
                    max_tokens=10,
                    rag_params=t.RAGParams(
                        table_id=ktable.id,
                        reranking_model=_get_reranking_model(jamai),
                        search_query="",  # Generate using LM
                        rerank=True,
                    ),
                ),
            ),
        ]
        with _create_table(jamai, table_type, TABLE_ID_B, cols=cols) as table:
            assert isinstance(table, t.TableMetaResponse)
            # Perform RAG
            data = dict(question="What is a burnet?", words=5)
            response = jamai.table.add_table_rows(
                table_type,
                t.MultiRowAddRequest(table_id=table.id, data=[data], stream=stream),
            )
            if stream:
                responses = [r for r in response if r.output_column_name == "rag"]
                assert len(responses) > 0
                assert isinstance(responses[0], t.CellReferencesResponse)
                responses = responses[1:]
                assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
                rag = "".join(r.text for r in responses)
                assert len(rag) > 0
            else:
                assert len(response.rows) > 0
                for row in response.rows:
                    assert isinstance(row, t.RowCompletionResponse)
                    assert len(row.columns) > 0
                    if table_type == t.TableType.chat:
                        assert "AI" in row.columns
                    assert "rag" in row.columns
                    assert isinstance(row.columns["rag"], t.ChatCompletionChunk)
                    assert isinstance(row.columns["rag"].references, t.References)
                    assert len(row.columns["rag"].text) > 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_rag_with_image_input(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    # Create Knowledge Table and add some rows
    with _create_table(jamai, "knowledge", cols=[]) as ktable:
        assert isinstance(ktable, t.TableMetaResponse)
        response = jamai.table.add_table_rows(
            t.TableType.knowledge,
            t.MultiRowAddRequest(
                table_id=ktable.id,
                data=[
                    dict(
                        Title="Coffee Lover",
                        Text="I called my rabbit as Latte.",
                    ),
                    dict(
                        Title="Coffee Lover",
                        Text="We ordered two cups of cappuccino in rabbit cafe, named Bunny World.",
                    ),
                ],
                stream=False,
            ),
        )
        assert isinstance(response, t.MultiRowCompletionResponse)
        assert isinstance(response.rows[0], t.RowCompletionResponse)
        rows = jamai.table.list_table_rows(t.TableType.knowledge, ktable.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2

        # Create the other table
        cols = [
            t.ColumnSchemaCreate(id="photo", dtype="image"),
            t.ColumnSchemaCreate(id="question", dtype="str"),
            t.ColumnSchemaCreate(id="words", dtype="int"),
            t.ColumnSchemaCreate(
                id="rag",
                dtype="str",
                gen_config=t.LLMGenConfig(
                    model=_get_chat_model(jamai),
                    system_prompt="You are a concise assistant.",
                    prompt="${photo} What's the animal? ${question} Summarise in ${words} words",
                    temperature=0.001,
                    top_p=0.001,
                    max_tokens=10,
                    rag_params=t.RAGParams(
                        table_id=ktable.id,
                        reranking_model=_get_reranking_model(jamai),
                        search_query="",  # Generate using LM
                        rerank=True,
                    ),
                ),
            ),
        ]
        with _create_table(jamai, table_type, TABLE_ID_B, cols=cols) as table:
            assert isinstance(table, t.TableMetaResponse)
            upload_response = jamai.file.upload_file("clients/python/tests/files/jpeg/rabbit.jpeg")
            # Perform RAG
            data = dict(photo=upload_response.uri, question="Get it's name.", words=5)
            response = jamai.table.add_table_rows(
                table_type,
                t.MultiRowAddRequest(table_id=table.id, data=[data], stream=stream),
            )
            if stream:
                responses = [r for r in response if r.output_column_name == "rag"]
                assert len(responses) > 0
                assert isinstance(responses[0], t.CellReferencesResponse)
                responses = responses[1:]
                assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
                rag = "".join(r.text for r in responses)
                assert len(rag) > 0
            else:
                assert len(response.rows) > 0
                for row in response.rows:
                    assert isinstance(row, t.RowCompletionResponse)
                    assert len(row.columns) > 0
                    if table_type == t.TableType.chat:
                        assert "AI" in row.columns
                    assert "rag" in row.columns
                    assert isinstance(row.columns["rag"], t.ChatCompletionChunk)
                    assert isinstance(row.columns["rag"].references, t.References)
                    assert len(row.columns["rag"].text) > 0

            rows = jamai.table.list_table_rows(table_type, TABLE_ID_B)
            assert isinstance(rows.items, list)
            assert len(rows.items) == 1
            row = rows.items[0]
            assert row["photo"]["value"] == upload_response.uri, row["photo"]["value"]
            assert "Latte" in row["rag"]["value"] and "Bunny World" not in row["rag"]["value"]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_conversation_starter(
    client_cls: Type[JamAI],
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="User", dtype="str"),
        t.ColumnSchemaCreate(
            id="AI",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model=_get_chat_model(jamai),
                system_prompt="You help remember facts.",
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
        t.ColumnSchemaCreate(id="words", dtype="int"),
        t.ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model=_get_chat_model(jamai),
                system_prompt="You are an assistant",
                temperature=0.001,
                top_p=0.001,
                max_tokens=5,
            ),
        ),
    ]
    with _create_table(jamai, "chat", cols=[], chat_cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Add the starter
        response = jamai.table.add_table_rows(
            "chat",
            t.MultiRowAddRequest(
                table_id=table.id, data=[dict(AI="Jim has 5 apples.")], stream=stream
            ),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response.rows[0], t.RowCompletionResponse)
        # Chat with it
        response = jamai.table.add_table_rows(
            "chat",
            t.MultiRowAddRequest(
                table_id=table.id,
                data=[dict(User="How many apples does Jim have?")],
                stream=stream,
            ),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            answer = "".join(r.text for r in responses if r.output_column_name == "AI")
            assert "5" in answer or "five" in answer.lower()
            summary = "".join(r.text for r in responses if r.output_column_name == "summary")
            assert len(summary) > 0
        else:
            assert isinstance(response.rows[0], t.RowCompletionResponse)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_add_row(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        response = _add_row(jamai, table_type, stream)
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == t.TableType.chat:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept", "AI")
                    for r in responses
                )
            else:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept")
                    for r in responses
                )
            assert len("".join(r.text for r in responses)) > 0
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(isinstance(r.usage, t.CompletionUsage) for r in responses)
            assert all(isinstance(r.prompt_tokens, int) for r in responses)
            assert all(isinstance(r.completion_tokens, int) for r in responses)
        else:
            assert isinstance(response, t.RowCompletionResponse)
            assert response.object == "gen_table.completion.chunks"
            for output_column_name in ("summary", "captioning", "narration", "concept"):
                assert len(response.columns[output_column_name].text) > 0
                assert isinstance(response.columns[output_column_name].usage, t.CompletionUsage)
                assert isinstance(response.columns[output_column_name].prompt_tokens, int)
                assert isinstance(response.columns[output_column_name].completion_tokens, int)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["good"]["value"] is True, row["good"]
        assert row["words"]["value"] == 5, row["words"]
        assert row["stars"]["value"] == 7.9, row["stars"]
        assert row["photo"]["value"].endswith("/rabbit.jpeg"), row["photo"]["value"]
        assert row["audio"]["value"].endswith("/turning-a4-size-magazine.mp3"), row["audio"][
            "value"
        ]
        assert row["paper"]["value"].endswith("/LLMs as Optimizers [DeepMind ; 2023].pdf"), row[
            "paper"
        ]["value"]
        for animal in ["deer", "rabbit"]:
            if animal in row["photo"]["value"].split("_")[0]:
                assert animal in row["captioning"]["value"]
        assert "paper" in row["narration"]["value"] or "turn" in row["narration"]["value"]
        assert (
            "optimization" in row["concept"]["value"].lower()
            or "optimize" in row["concept"]["value"].lower()
        )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.timeout(180)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES[:1])
@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize(
    "docpath",
    [
        "clients/python/tests/files/pdf/salary 总结.pdf",
        "clients/python/tests/files/pdf_scan/1978_APL_FP_detrapping.PDF",
        "clients/python/tests/files/pdf_mixed/digital_scan_combined.pdf",
        "clients/python/tests/files/md/creative-story.md",
        "clients/python/tests/files/txt/creative-story.txt",
        "clients/python/tests/files/html/multilingual-code-examples.html",
        "clients/python/tests/files/xml/weather-forecast-service.xml",
        "clients/python/tests/files/jsonl/ChatMed_TCM-v0.2-5records.jsonl",
        "clients/python/tests/files/docx/Recommendation Letter.docx",
        "clients/python/tests/files/pptx/(2017.06.30) NMT in Linear Time (ByteNet).pptx",
        "clients/python/tests/files/xlsx/Claims Form.xlsx",
        "clients/python/tests/files/tsv/weather_observations.tsv",
        "clients/python/tests/files/csv/weather_observations_long.csv",
    ],
    ids=lambda x: basename(x),
)
def test_add_row_document_dtype(
    client_cls: Type[JamAI], table_type: t.TableType, stream: bool, docpath: str
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="doc", dtype="document"),
        t.ColumnSchemaCreate(
            id="content",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model="",
                prompt="Document: \n${doc} \n\nReply 0 if document received, else -1. Omit any explanation, only answer 0 or -1.",
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)

        upload_response = jamai.file.upload_file(docpath)
        response = _add_row(
            jamai,
            table_type,
            stream,
            TABLE_ID_A,
            data=dict(doc=upload_response.uri),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, t.GenTableStreamChatCompletionChunk) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == t.TableType.chat:
                assert all(r.output_column_name in ("content", "AI") for r in responses)
            else:
                assert all(r.output_column_name in ("content",) for r in responses)
            assert len("".join(r.text for r in responses)) > 0
            assert all(isinstance(r, t.GenTableStreamChatCompletionChunk) for r in responses)
            assert all(isinstance(r.usage, t.CompletionUsage) for r in responses)
            assert all(isinstance(r.prompt_tokens, int) for r in responses)
            assert all(isinstance(r.completion_tokens, int) for r in responses)
        else:
            assert isinstance(response, t.GenTableChatCompletionChunks)
            assert response.object == "gen_table.completion.chunks"
            output_column_name = "content"
            assert len(response.columns[output_column_name].text) > 0
            assert isinstance(response.columns[output_column_name].usage, t.CompletionUsage)
            assert isinstance(response.columns[output_column_name].prompt_tokens, int)
            assert isinstance(response.columns[output_column_name].completion_tokens, int)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["doc"]["value"] == upload_response.uri, row["doc"]["value"]
        assert "0" in row["content"]["value"]


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_regen_with_reordered_columns(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="number", dtype="int"),
        t.ColumnSchemaCreate(
            id="col1-english",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model="",
                prompt=(
                    "Number: ${number} \n\nTell the 'Number' in English, "
                    "only output the answer in uppercase without explanation."
                ),
            ),
        ),
        t.ColumnSchemaCreate(
            id="col2-malay",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model="",
                prompt=(
                    "Number: ${number} \n\nTell the 'Number' in Malay, "
                    "only output the answer in uppercase without explanation."
                ),
            ),
        ),
        t.ColumnSchemaCreate(
            id="col3-mandarin",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model="",
                prompt=(
                    "Number: ${number} \n\nTell the 'Number' in Mandarin (Chinese Character), "
                    "only output the answer in uppercase without explanation."
                ),
            ),
        ),
        t.ColumnSchemaCreate(
            id="col4-roman",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model="",
                prompt=(
                    "Number: ${number} \n\nTell the 'Number' in Roman Numerals, "
                    "only output the answer in uppercase without explanation."
                ),
            ),
        ),
    ]

    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        row = _add_row(
            jamai,
            table_type,
            False,
            data=dict(number=1),
        )
        assert isinstance(row, t.RowCompletionResponse)
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        _id = row["ID"]
        assert row["number"]["value"] == 1, row["number"]
        assert row["col1-english"]["value"] == "ONE", row["col1-english"]
        assert row["col2-malay"]["value"] == "SATU", row["col2-malay"]
        assert row["col3-mandarin"]["value"] == "一", row["col3-mandarin"]
        assert row["col4-roman"]["value"] == "I", row["col4-roman"]

        # Update Input + Regen
        jamai.table.update_table_row(
            table_type,
            t.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=_id,
                data=dict(number=2),
            ),
        )

        response = jamai.table.regen_table_rows(
            table_type,
            t.MultiRowRegenRequest(
                table_id=table.id,
                row_ids=[_id],
                regen_strategy=t.RegenStrategy.RUN_ALL,
                stream=stream,
            ),
        )
        if stream:
            _ = [r for r in response]

        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["number"]["value"] == 2, row["number"]
        assert row["col1-english"]["value"] == "TWO", row["col1-english"]
        assert row["col2-malay"]["value"] == "DUA", row["col2-malay"]
        assert row["col3-mandarin"]["value"] == "二", row["col3-mandarin"]
        assert row["col4-roman"]["value"] == "II", row["col4-roman"]

        # Reorder + Update Input + Regen
        # [1, 2, 3, 4] -> [3, 1, 4, 2]
        new_cols = [
            "number",
            "col3-mandarin",
            "col1-english",
            "col4-roman",
            "col2-malay",
        ]
        if table_type == t.TableType.knowledge:
            new_cols += ["Title", "Text", "Title Embed", "Text Embed", "File ID", "Page"]
        elif table_type == t.TableType.chat:
            new_cols += ["User", "AI"]
        jamai.table.reorder_columns(
            table_type=table_type,
            request=t.ColumnReorderRequest(
                table_id=TABLE_ID_A,
                column_names=new_cols,
            ),
        )
        # RUN_SELECTED
        jamai.table.update_table_row(
            table_type,
            t.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=_id,
                data=dict(number=5),
            ),
        )
        response = jamai.table.regen_table_rows(
            table_type,
            t.MultiRowRegenRequest(
                table_id=TABLE_ID_A,
                row_ids=[_id],
                regen_strategy=t.RegenStrategy.RUN_SELECTED,
                output_column_id="col1-english",
                stream=stream,
            ),
        )
        if stream:
            _ = [r for r in response]
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["number"]["value"] == 5, row["number"]
        assert row["col3-mandarin"]["value"] == "二", row["col3-mandarin"]
        assert row["col1-english"]["value"] == "FIVE", row["col1-english"]
        assert row["col4-roman"]["value"] == "II", row["col4-roman"]
        assert row["col2-malay"]["value"] == "DUA", row["col2-malay"]

        # RUN_BEFORE
        jamai.table.update_table_row(
            table_type,
            t.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=_id,
                data=dict(number=6),
            ),
        )
        response = jamai.table.regen_table_rows(
            table_type,
            t.MultiRowRegenRequest(
                table_id=TABLE_ID_A,
                row_ids=[_id],
                regen_strategy=t.RegenStrategy.RUN_BEFORE,
                output_column_id="col4-roman",
                stream=stream,
            ),
        )
        if stream:
            _ = [r for r in response]
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["number"]["value"] == 6, row["number"]
        assert row["col3-mandarin"]["value"] == "六", row["col3-mandarin"]
        assert row["col1-english"]["value"] == "SIX", row["col1-english"]
        assert row["col4-roman"]["value"] == "VI", row["col4-roman"]
        assert row["col2-malay"]["value"] == "DUA", row["col2-malay"]

        # RUN_AFTER
        jamai.table.update_table_row(
            table_type,
            t.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=_id,
                data=dict(number=7),
            ),
        )
        response = jamai.table.regen_table_rows(
            table_type,
            t.MultiRowRegenRequest(
                table_id=TABLE_ID_A,
                row_ids=[_id],
                regen_strategy=t.RegenStrategy.RUN_AFTER,
                output_column_id="col4-roman",
                stream=stream,
            ),
        )
        if stream:
            _ = [r for r in response]
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["number"]["value"] == 7, row["number"]
        assert row["col3-mandarin"]["value"] == "六", row["col3-mandarin"]
        assert row["col1-english"]["value"] == "SIX", row["col1-english"]
        assert row["col4-roman"]["value"] == "VII", row["col4-roman"]
        assert row["col2-malay"]["value"] == "TUJUH", row["col2-malay"]


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_add_row_sequential_image_model_completion(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="photo", dtype="image"),
        t.ColumnSchemaCreate(id="photo2", dtype="image"),
        t.ColumnSchemaCreate(
            id="caption",
            dtype="str",
            gen_config=t.LLMGenConfig(model="", prompt="${photo} What's in the image?"),
        ),
        t.ColumnSchemaCreate(
            id="question",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model="",
                prompt="Caption: ${caption}\n\nImage: ${photo2}\n\nDoes the caption match? Reply True or False.",
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)

        upload_response = jamai.file.upload_file("clients/python/tests/files/jpeg/rabbit.jpeg")
        response = _add_row(
            jamai,
            table_type,
            stream,
            TABLE_ID_A,
            data=dict(photo=upload_response.uri, photo2=upload_response.uri),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == t.TableType.chat:
                assert all(
                    r.output_column_name in ("caption", "question", "AI") for r in responses
                )
            else:
                assert all(r.output_column_name in ("caption", "question") for r in responses)
            assert len("".join(r.text for r in responses)) > 0
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(isinstance(r.usage, t.CompletionUsage) for r in responses)
            assert all(isinstance(r.prompt_tokens, int) for r in responses)
            assert all(isinstance(r.completion_tokens, int) for r in responses)
        else:
            assert isinstance(response, t.RowCompletionResponse)
            assert response.object == "gen_table.completion.chunks"
            for output_column_name in ("caption", "question"):
                assert len(response.columns[output_column_name].text) > 0
                assert isinstance(response.columns[output_column_name].usage, t.CompletionUsage)
                assert isinstance(response.columns[output_column_name].prompt_tokens, int)
                assert isinstance(response.columns[output_column_name].completion_tokens, int)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["photo"]["value"] == upload_response.uri, row["photo"]["value"]
        assert row["photo2"]["value"] == upload_response.uri, row["photo"]["value"]
        for animal in ["deer", "rabbit"]:
            if animal in row["photo"]["value"].split("_")[0]:
                assert animal in row["caption"]["value"]
            if animal in row["photo2"]["value"].split("_")[0]:
                assert "true" in row["question"]["value"].lower()


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_add_row_map_dtype_file_to_image(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="photo", dtype="file"),
        t.ColumnSchemaCreate(id="photo2", dtype="image"),
        t.ColumnSchemaCreate(
            id="caption",
            dtype="str",
            gen_config=t.LLMGenConfig(model="", prompt="${photo} What's in the image?"),
        ),
        t.ColumnSchemaCreate(
            id="question",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model="",
                prompt="Caption: ${caption}\n\nImage: ${photo2}\n\nDoes the caption match? Reply True or False.",
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)

        upload_response = jamai.file.upload_file("clients/python/tests/files/jpeg/rabbit.jpeg")
        response = _add_row(
            jamai,
            table_type,
            stream,
            TABLE_ID_A,
            data=dict(photo=upload_response.uri, photo2=upload_response.uri),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == t.TableType.chat:
                assert all(
                    r.output_column_name in ("caption", "question", "AI") for r in responses
                )
            else:
                assert all(r.output_column_name in ("caption", "question") for r in responses)
            assert len("".join(r.text for r in responses)) > 0
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(isinstance(r.usage, t.CompletionUsage) for r in responses)
            assert all(isinstance(r.prompt_tokens, int) for r in responses)
            assert all(isinstance(r.completion_tokens, int) for r in responses)
        else:
            assert isinstance(response, t.RowCompletionResponse)
            assert response.object == "gen_table.completion.chunks"
            for output_column_name in ("caption", "question"):
                assert len(response.columns[output_column_name].text) > 0
                assert isinstance(response.columns[output_column_name].usage, t.CompletionUsage)
                assert isinstance(response.columns[output_column_name].prompt_tokens, int)
                assert isinstance(response.columns[output_column_name].completion_tokens, int)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["photo"]["value"] == upload_response.uri, row["photo"]["value"]
        assert row["photo2"]["value"] == upload_response.uri, row["photo"]["value"]
        for animal in ["deer", "rabbit"]:
            if animal in row["photo"]["value"].split("_")[0]:
                assert animal in row["caption"]["value"]
            if animal in row["photo2"]["value"].split("_")[0]:
                assert "true" in row["question"]["value"].lower()
        meta = jamai.table.get_table(table_type, TABLE_ID_A)
        for col in meta.cols:
            if col.id == "photo":
                assert col.dtype == "image"


# @flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
# @pytest.mark.parametrize("client_cls", CLIENT_CLS)
# @pytest.mark.parametrize("table_type", TABLE_TYPES)
# @pytest.mark.parametrize("stream", [True, False])
# def test_add_row_file_type_output_column(
#     client_cls: Type[JamAI],
#     table_type: p.TableType,
#     stream: bool,
# ):
#     jamai = client_cls()
#     cols = [
#         p.ColumnSchemaCreate(id="photo", dtype="image"),
#         p.ColumnSchemaCreate(id="question", dtype="str"),
#         p.ColumnSchemaCreate(
#             id="captioning",
#             dtype="file",
#             gen_config=p.LLMGenConfig(model="", prompt="${photo} What's in the image?"),
#         ),
#         p.ColumnSchemaCreate(
#             id="answer",
#             dtype="file",
#             gen_config=p.LLMGenConfig(
#                 model="",
#                 prompt="${photo} ${question}?",
#             ),
#         ),
#         p.ColumnSchemaCreate(
#             id="compare",
#             dtype="image",
#             gen_config=p.LLMGenConfig(
#                 model="",
#                 prompt="Compare ${captioning} and ${answer}.",
#             ),
#         ),
#     ]
#     with _create_table(jamai, table_type, cols=cols) as table:
#         assert isinstance(table, p.TableMetaResponse)
@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_add_row_output_column_referred_image_input_with_chat_model(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="photo", dtype="image"),
        t.ColumnSchemaCreate(
            id="captioning",
            dtype="str",
            gen_config=t.LLMGenConfig(model="", prompt="${photo} What's in the image?"),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)

        # Add output column that referred to image file, but using chat model
        # (Notes: chat model can be set due to default prompt was added afterward)
        chat_only_model = _get_chat_only_model(jamai)
        cols = [
            t.ColumnSchemaCreate(
                id="captioning2",
                dtype="str",
                gen_config=t.LLMGenConfig(model=chat_only_model),
            ),
        ]
        with pytest.raises(RuntimeError):
            if table_type == t.TableType.action:
                jamai.table.add_action_columns(t.AddActionColumnSchema(id=table.id, cols=cols))
            elif table_type == t.TableType.knowledge:
                jamai.table.add_knowledge_columns(
                    t.AddKnowledgeColumnSchema(id=table.id, cols=cols)
                )
            elif table_type == t.TableType.chat:
                jamai.table.add_chat_columns(t.AddChatColumnSchema(id=table.id, cols=cols))
            else:
                raise ValueError(f"Invalid table type: {table_type}")
            assert isinstance(table, t.TableMetaResponse)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_add_row_sequential_completion_with_error(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input", dtype="str"),
        t.ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model="",
                prompt="Summarise ${input}.",
            ),
        ),
        t.ColumnSchemaCreate(
            id="rephrase",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model="",
                prompt="Rephrase ${summary}",
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)

        response = _add_row(
            jamai,
            table_type,
            stream,
            TABLE_ID_A,
            data=dict(input="a" * 10000000),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == t.TableType.chat:
                assert all(
                    r.output_column_name in ("summary", "rephrase", "AI") for r in responses
                )
            else:
                assert all(r.output_column_name in ("summary", "rephrase") for r in responses)
            assert len("".join(r.text for r in responses)) > 0
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response, t.RowCompletionResponse)
            assert response.object == "gen_table.completion.chunks"
            for output_column_name in ("summary", "rephrase"):
                assert len(response.columns[output_column_name].text) > 0

        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["summary"]["value"].startswith("[ERROR] ")
        second_output = (row["rephrase"]["value"]).upper()
        if stream:
            assert second_output.startswith("[ERROR] ")
        else:
            assert "WARNING" in second_output or "ERROR" in second_output


@flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
@pytest.mark.parametrize(
    "img_filename",
    [
        "clients/python/tests/files/jpeg/cifar10-deer.jpg",
        "clients/python/tests/files/jpeg/rabbit.jpeg",
        "clients/python/tests/files/png/rabbit.png",
        "clients/python/tests/files/webp/rabbit_cifar10-deer.webp",
        "clients/python/tests/files/gif/rabbit_cifar10-deer.gif",
    ],
    ids=lambda x: basename(x),
)
def test_add_row_image_file_type_with_generation(
    client_cls: Type[JamAI], table_type: t.TableType, stream: bool, img_filename: str
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)

        upload_response = jamai.file.upload_file(img_filename)
        response = _add_row(
            jamai,
            table_type,
            stream,
            data=dict(
                photo=upload_response.uri,
            ),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == t.TableType.chat:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept", "AI")
                    for r in responses
                )
            else:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept")
                    for r in responses
                )
            assert len("".join(r.text for r in responses)) > 0
        else:
            assert isinstance(response, t.RowCompletionResponse)
            assert response.object == "gen_table.completion.chunks"
            assert len(response.columns["captioning"].text) > 0
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["photo"]["value"] == upload_response.uri, row["photo"]["value"]
        result_caption = row["captioning"]["value"]
        for animal in ["deer", "rabbit"]:
            if animal in img_filename.split("_")[0]:
                if "cifar10" in img_filename:
                    assert (
                        animal in result_caption
                        or "see" in result_caption
                        or "can't" in result_caption
                    )
                else:
                    assert animal in result_caption


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
@pytest.mark.parametrize(
    "img_filename",
    [
        "s3://image-bucket/bmp/cifar10-deer.bmp",
        "s3://image-bucket/tiff/cifar10-deer.tiff",
        "file://image-bucket/tiff/rabbit.tiff",
    ],
)
def test_add_row_image_file_column_invalid_extension(
    client_cls: Type[JamAI], table_type: t.TableType, stream: bool, img_filename: str
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        with pytest.raises(
            ValidationError,
            match=(
                "Unsupported file type. Make sure the file belongs to "
                "one of the following formats: \n"
                f"[Image File Types]: \n{IMAGE_FILE_EXTENSIONS}"
            )
            .replace("[", "\\[")
            .replace("]", "\\]"),
        ):
            _add_row(
                jamai,
                table_type,
                stream,
                data=dict(photo=img_filename),
            )


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_add_row_validate_one_image_per_completion(
    client_cls: Type[JamAI], table_type: t.TableType, stream: bool = True
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)

        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    captioning=t.LLMGenConfig(
                        system_prompt="You are a concise assistant.",
                        prompt="${photo} ${photo}\n\nWhat's in the image?",
                    ),
                ),
            ),
        )

        upload_response = jamai.file.upload_file("clients/python/tests/files/jpeg/rabbit.jpeg")
        response = _add_row(
            jamai,
            table_type,
            stream,
            data=dict(
                photo=upload_response.uri,
            ),
        )
        responses = [r for r in response]
        assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
        assert all(r.object == "gen_table.completion.chunk" for r in responses)
        if table_type == t.TableType.chat:
            assert all(
                r.output_column_name in ("summary", "captioning", "narration", "concept", "AI")
                for r in responses
            )
        else:
            assert all(
                r.output_column_name in ("summary", "captioning", "narration", "concept")
                for r in responses
            )
        assert len("".join(r.text for r in responses)) > 0

        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["photo"]["value"] == row["photo"]["value"], row["photo"]["value"]
        assert row["captioning"]["value"] == "[ERROR] Only one image is supported per completion."


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_add_row_wrong_dtype(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        response = _add_row(jamai, table_type, stream)
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == t.TableType.chat:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept", "AI")
                    for r in responses
                )
            else:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept")
                    for r in responses
                )
            assert len("".join(r.text for r in responses)) > 0
        else:
            assert isinstance(response, t.RowCompletionResponse)
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
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response, t.RowCompletionResponse)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        row = rows.items[0]
        assert row["good"]["value"] is None, row["good"]
        assert row["good"]["original"] == "dummy1", row["good"]
        assert row["words"]["value"] is None, row["words"]
        assert row["words"]["original"] == "dummy2", row["words"]
        assert row["stars"]["value"] is None, row["stars"]
        assert row["stars"]["original"] == "dummy3", row["stars"]


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_add_row_missing_columns(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        response = _add_row(jamai, table_type, stream)
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == t.TableType.chat:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept", "AI")
                    for r in responses
                )
            else:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept")
                    for r in responses
                )
            assert len("".join(r.text for r in responses)) > 0
        else:
            assert isinstance(response, t.RowCompletionResponse)
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
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response, t.RowCompletionResponse)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        row = rows.items[0]
        assert row["good"]["value"] is None, row["good"]
        assert row["good"]["original"] == "dummy1", row["good"]
        assert row["words"]["value"] is None, row["words"]
        assert "original" not in row["words"], row["words"]
        assert row["stars"]["value"] is None, row["stars"]
        assert "original" not in row["stars"], row["stars"]


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_add_rows_all_input(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="0", dtype="int"),
        t.ColumnSchemaCreate(id="1", dtype="float"),
        t.ColumnSchemaCreate(id="2", dtype="bool"),
        t.ColumnSchemaCreate(id="3", dtype="str"),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        response = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=table.id,
                data=[
                    {"0": 1, "1": 2.0, "2": False, "3": "days"},
                    {"0": 0, "1": 1.0, "2": True, "3": "of"},
                ],
                stream=stream,
            ),
        )
        if stream:
            responses = [r for r in response if r.output_column_name != "AI"]
            assert len(responses) == 0
        else:
            assert isinstance(response, t.MultiRowCompletionResponse)
            assert len(response.rows) == 2
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_update_row(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        row = _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="dummy"),
        )
        assert isinstance(row, t.RowCompletionResponse)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        original_ts = row["Updated at"]
        assert row["good"]["value"] is True, row["good"]
        assert row["words"]["value"] == 5, row["words"]
        assert row["stars"]["value"] == 9.9, row["stars"]
        # Regular update
        response = jamai.table.update_table_row(
            table_type,
            t.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=row["ID"],
                data=dict(good=False, stars=1.0),
            ),
        )
        assert isinstance(response, t.OkResponse)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["good"]["value"] is False, row["good"]
        assert row["words"]["value"] == 5, row["words"]
        assert row["stars"]["value"] == 1.0, row["stars"]
        assert row["Updated at"] > original_ts

        # Test updating data with wrong dtype
        response = jamai.table.update_table_row(
            table_type,
            t.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=row["ID"],
                data=dict(good="dummy", words="dummy", stars="dummy"),
            ),
        )
        assert isinstance(response, t.OkResponse)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["good"]["value"] is None, row["good"]
        assert row["words"]["value"] is None, row["words"]
        assert row["stars"]["value"] is None, row["stars"]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_regen_rows(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)

        image_upload_response = jamai.file.upload_file(
            "clients/python/tests/files/jpeg/rabbit.jpeg"
        )
        audio_upload_response = jamai.file.upload_file(
            "clients/python/tests/files/mp3/turning-a4-size-magazine.mp3"
        )
        response = _add_row(
            jamai,
            table_type,
            False,
            data=dict(
                good=True,
                words=10,
                stars=9.9,
                inputs=TEXT,
                photo=image_upload_response.uri,
                audio=audio_upload_response.uri,
            ),
        )
        assert isinstance(response, t.RowCompletionResponse)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        _id = row["ID"]
        original_ts = row["Updated at"]
        assert "arrival" in row["summary"]["value"].lower()
        # Regen
        jamai.table.update_table_row(
            table_type,
            t.RowUpdateRequest(
                table_id=TABLE_ID_A,
                row_id=_id,
                data=dict(
                    inputs="Dune: Part Two is a 2024 American epic science fiction film directed and produced by Denis Villeneuve"
                ),
            ),
        )
        response = jamai.table.regen_table_rows(
            table_type, t.MultiRowRegenRequest(table_id=TABLE_ID_A, row_ids=[_id], stream=stream)
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            assert all(r.object == "gen_table.completion.chunk" for r in responses)
            if table_type == t.TableType.chat:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept", "AI")
                    for r in responses
                )
            else:
                assert all(
                    r.output_column_name in ("summary", "captioning", "narration", "concept")
                    for r in responses
                )
            assert len("".join(r.text for r in responses)) > 0
        else:
            assert isinstance(response, t.MultiRowCompletionResponse)
            assert response.rows[0].object == "gen_table.completion.chunks"
            assert len(response.rows[0].columns["summary"].text) > 0
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["good"]["value"] is True
        assert row["words"]["value"] == 10
        assert row["stars"]["value"] == 9.9
        assert row["photo"]["value"] == image_upload_response.uri
        assert row["audio"]["value"] == audio_upload_response.uri
        assert row["Updated at"] > original_ts
        assert "dune" in row["summary"]["value"].lower()


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_regen_rows_all_input(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="0", dtype="int"),
        t.ColumnSchemaCreate(id="1", dtype="float"),
        t.ColumnSchemaCreate(id="2", dtype="bool"),
        t.ColumnSchemaCreate(id="3", dtype="str"),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        response = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=table.id,
                data=[
                    {"0": 1, "1": 2.0, "2": False, "3": "days"},
                    {"0": 0, "1": 1.0, "2": True, "3": "of"},
                ],
                stream=False,
            ),
        )
        assert isinstance(response, t.MultiRowCompletionResponse)
        assert len(response.rows) == 2
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        # Regen
        response = jamai.table.regen_table_rows(
            table_type,
            t.MultiRowRegenRequest(
                table_id=table.id, row_ids=[r["ID"] for r in rows.items], stream=stream
            ),
        )
        if stream:
            responses = [r for r in response if r.output_column_name != "AI"]
            assert len(responses) == 0
        else:
            assert isinstance(response, t.MultiRowCompletionResponse)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_delete_rows(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
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
        ori_rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(ori_rows.items, list)
        assert len(ori_rows.items) == 6
        delete_id = ori_rows.items[0]["ID"]

        # Delete one row
        response = jamai.table.delete_table_row(table_type, TABLE_ID_A, delete_id)
        assert isinstance(response, t.OkResponse)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 5
        row_ids = set(r["ID"] for r in rows.items)
        assert delete_id not in row_ids
        # Delete multiple rows
        delete_ids = [r["ID"] for r in ori_rows.items[1:4]]
        response = jamai.table.delete_table_rows(
            table_type,
            t.MultiRowDeleteRequest(
                table_id=TABLE_ID_A,
                row_ids=delete_ids,
            ),
        )
        assert isinstance(response, t.OkResponse)
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        row_ids = set(r["ID"] for r in rows.items)
        assert len(set(row_ids) & set(delete_ids)) == 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_get_and_list_rows(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
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
        expected_cols = {
            "ID",
            "Updated at",
            "good",
            "words",
            "stars",
            "inputs",
            "photo",
            "audio",
            "paper",
            "summary",
            "captioning",
            "narration",
            "concept",
        }
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == t.TableType.chat:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A)
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
        row = jamai.table.get_table_row(table_type, TABLE_ID_A, _id)
        assert row["ID"] == _id
        assert set(row.keys()) == expected_cols
        row = jamai.table.get_table_row(table_type, TABLE_ID_A, _id, columns=["good"])
        assert row["ID"] == _id
        assert set(row.keys()) == {"ID", "Updated at", "good"}

        # Test various offset and limit
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A, offset=0, limit=3)
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 0
        assert rows.limit == 3
        assert len(rows.items) == 3
        stars = [r["stars"]["value"] for r in rows.items]
        assert stars[0] == -1 / 3
        assert stars[-1] == 1 / 3

        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A, offset=1, limit=3)
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 1
        assert rows.limit == 3
        assert len(rows.items) == 3
        stars = [r["stars"]["value"] for r in rows.items]
        assert stars[0] == -5 / 3
        assert stars[-1] == 5 / 3

        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A, offset=4, limit=3)
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 4
        assert rows.limit == 3
        assert len(rows.items) == 1
        stars = [r["stars"]["value"] for r in rows.items]
        assert stars[0] == 7.9

        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A, offset=6, limit=3)
        assert isinstance(rows.items, list)
        assert rows.total == 5
        assert rows.offset == 6
        assert rows.limit == 3
        assert len(rows.items) == 0

        # Test specifying columns
        rows = jamai.table.list_table_rows(
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
            jamai.table.list_table_rows(table_type, TABLE_ID_A, offset=0, limit=0)
        with pytest.raises(RuntimeError):
            jamai.table.list_table_rows(table_type, TABLE_ID_A, offset=-1, limit=1)

        # Test search query
        rows = jamai.table.list_table_rows(
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
        rows = jamai.table.list_table_rows(
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
        rows = jamai.table.list_table_rows(
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
        # At least 10 decimals or above
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A, limit=4)
        assert isinstance(rows.items, list)
        for row in rows.items:
            for cell in row.values():
                if not isinstance(cell, dict):
                    continue
                cell = cell["value"]
                if isinstance(cell, float):
                    exponent = _get_exponent(cell)
                    assert exponent <= -10, exponent
                elif isinstance(cell, list):
                    exponents = [_get_exponent(vv) for vv in cell]
                    assert all(e <= -10 for e in exponents), exponents
                else:
                    continue
        # 5 decimals or below
        rows = jamai.table.list_table_rows(
            table_type, TABLE_ID_A, limit=4, float_decimals=5, vec_decimals=5
        )
        assert isinstance(rows.items, list)
        for row in rows.items:
            for cell in row.values():
                if not isinstance(cell, dict):
                    continue
                cell = cell["value"]
                if isinstance(cell, float):
                    exponent = _get_exponent(cell)
                    assert exponent >= -5, exponent
                elif isinstance(cell, list):
                    exponents = [_get_exponent(vv) for vv in cell]
                    assert all(e >= -5 for e in exponents), exponents
                else:
                    continue
        # 1 decimal or below
        rows = jamai.table.list_table_rows(
            table_type, TABLE_ID_A, limit=4, float_decimals=1, vec_decimals=1
        )
        assert isinstance(rows.items, list)
        for row in rows.items:
            for cell in row.values():
                if not isinstance(cell, dict):
                    continue
                cell = cell["value"]
                if isinstance(cell, float):
                    exponent = _get_exponent(cell)
                    assert exponent >= -1, exponent
                elif isinstance(cell, list):
                    exponents = [_get_exponent(vv) for vv in cell]
                    assert all(e >= -1 for e in exponents), exponents
                else:
                    continue

        # --- Vector column exclusion --- #
        # 5 decimals
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A, limit=4, vec_decimals=5)
        if table_type == "knowledge":
            for row in rows.items:
                vec_cols = [
                    cell
                    for cell in row.values()
                    if isinstance(cell, dict) and isinstance(cell["value"], list)
                ]
                assert len(vec_cols) > 0
        # No vector columns
        rows = jamai.table.list_table_rows(table_type, TABLE_ID_A, limit=4, vec_decimals=-1)
        for row in rows.items:
            vec_cols = [
                cell
                for cell in row.values()
                if isinstance(cell, dict) and isinstance(cell["value"], list)
            ]
            assert len(vec_cols) == 0


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_column_interpolate(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()

    cols = [
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model=_get_chat_model(jamai),
                system_prompt="You are a concise assistant.",
                prompt='Say "Jan has 5 apples.".',
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
        t.ColumnSchemaCreate(id="input0", dtype="int"),
        t.ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model=_get_chat_model(jamai),
                system_prompt="You are a concise assistant.",
                prompt=(
                    "1. ${output0}\n2. Jan has ${input0} apples.\n\n"
                    "Do the statements agree with each other? Reply Yes or No."
                ),
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)

        def _add_row_wrapped(stream, data):
            return _add_row(
                jamai,
                table_type=table_type,
                stream=stream,
                table_name=table.id,
                data=data,
                knowledge_data=None,
                chat_data=dict(User='Say "Jan has 5 apples.".'),
            )

        # Streaming
        response = list(_add_row_wrapped(True, dict(input0=5)))
        output0 = _collect_text(response, "output0")
        ai = _collect_text(response, "AI")
        answer = _collect_text(response, "output1")
        assert "yes" in answer.lower(), f'output0="{output0}"  ai="{ai}"  answer="{answer}"'
        response = list(_add_row_wrapped(True, dict(input0=6)))
        output0 = _collect_text(response, "output0")
        ai = _collect_text(response, "AI")
        answer = _collect_text(response, "output1")
        assert "no" in answer.lower(), f'output0="{output0}"  ai="{ai}"  answer="{answer}"'
        # Non-streaming
        response = _add_row_wrapped(False, dict(input0=5))
        answer = response.columns["output1"].text
        assert "yes" in answer.lower(), f'columns={response.columns}  answer="{answer}"'
        response = _add_row_wrapped(False, dict(input0=6))
        answer = response.columns["output1"].text
        assert "no" in answer.lower(), f'columns={response.columns}  answer="{answer}"'


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_chat_history_and_sequential_add(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input", dtype="str"),
        t.ColumnSchemaCreate(
            id="output",
            dtype="str",
            gen_config=t.LLMGenConfig(
                system_prompt="You are a calculator.",
                prompt="${input}",
                multi_turn=True,
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Initialise chat thread and set output format
        response = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=table.id,
                data=[
                    dict(input="x = 0", output="0"),
                    dict(input="Add 1", output="1"),
                    dict(input="Add 1", output="2"),
                    dict(input="Add 1", output="3"),
                    dict(input="Add 1", output="4"),
                ],
                stream=False,
            ),
        )
        # Test adding one row
        response = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=table.id,
                data=[dict(input="Add 1")],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "5" in output, output
        # Test adding multiple rows
        response = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=table.id,
                data=[
                    dict(input="Add 1"),
                    dict(input="Add 2"),
                    dict(input="Add 1"),
                ],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "6" in output, output
        assert "8" in output, output
        assert "9" in output, output


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_chat_history_and_sequential_regen(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input", dtype="str"),
        t.ColumnSchemaCreate(
            id="output",
            dtype="str",
            gen_config=t.LLMGenConfig(
                system_prompt="You are a calculator.",
                prompt="${input}",
                multi_turn=True,
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Initialise chat thread and set output format
        response = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=table.id,
                data=[
                    dict(input="x = 0", output="0"),
                    dict(input="Add 1", output="1"),
                    dict(input="Add 1", output="2"),
                    dict(input="Add 2", output="9"),  # Wrong answer on purpose
                    dict(input="Add 1", output="9"),  # Wrong answer on purpose
                    dict(input="Add 3", output="9"),  # Wrong answer on purpose
                ],
                stream=False,
            ),
        )
        row_ids = sorted([r.row_id for r in response.rows])
        # Test regen one row
        response = jamai.table.regen_table_rows(
            table_type,
            t.MultiRowRegenRequest(
                table_id=table.id,
                row_ids=row_ids[3:4],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "4" in output, output
        # Test regen multiple rows
        # Also test if regen proceeds in correct order from earliest row to latest
        response = jamai.table.regen_table_rows(
            table_type,
            t.MultiRowRegenRequest(
                table_id=table.id,
                row_ids=row_ids[3:][::-1],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "4" in output, output
        assert "5" in output, output
        assert "8" in output, output


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_convert_into_multi_turn(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input", dtype="str"),
        t.ColumnSchemaCreate(
            id="output",
            dtype="str",
            gen_config=t.LLMGenConfig(
                system_prompt="You are a calculator.",
                prompt="${input}",
                multi_turn=False,
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Initialise chat thread and set output format
        response = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=table.id,
                data=[
                    dict(input="x = 0", output="0"),
                    dict(input="x += 1", output="1"),
                    dict(input="x += 1", output="2"),
                    dict(input="x += 1", output="3"),
                ],
                stream=False,
            ),
        )
        # Test adding one row as single-turn
        response = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=table.id,
                data=[dict(input="x += 1")],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "4" not in output, output
        # Convert into multi-turn
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    output=t.LLMGenConfig(
                        system_prompt="You are a calculator.",
                        prompt="${input}",
                        multi_turn=True,
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ),
                ),
            ),
        )
        assert isinstance(table, t.TableMetaResponse)
        # Regen
        rows = jamai.table.list_table_rows(table_type, table.id)
        response = jamai.table.regen_table_rows(
            table_type,
            t.MultiRowRegenRequest(
                table_id=table.id,
                row_ids=[rows.items[0]["ID"]],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "4" in output, output


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_get_conversation_thread(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input", dtype="str"),
        t.ColumnSchemaCreate(
            id="output",
            dtype="str",
            gen_config=t.LLMGenConfig(
                system_prompt="You are a calculator.",
                prompt="${input}",
                multi_turn=True,
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Initialise chat thread and set output format
        data = [
            dict(input="x = 0", output="0"),
            dict(input="Add 1", output="1"),
            dict(input="Add 2", output="3"),
            dict(input="Add 3", output="6"),
        ]
        response = jamai.table.add_table_rows(
            table_type, t.MultiRowAddRequest(table_id=table.id, data=data, stream=False)
        )
        row_ids = sorted([r.row_id for r in response.rows])

        def _check_thread(_chat):
            assert isinstance(_chat, t.ChatThreadResponse)
            for i, message in enumerate(_chat.thread):
                assert isinstance(message.content, str)
                assert len(message.content) > 0
                if i == 0:
                    assert message.role == t.ChatRole.SYSTEM
                elif i % 2 == 1:
                    assert message.role == t.ChatRole.USER
                    assert message.content == data[(i - 1) // 2]["input"]
                else:
                    assert message.role == t.ChatRole.ASSISTANT
                    assert message.content == data[(i // 2) - 1]["output"]

        # --- Fetch complete thread --- #
        chat = jamai.table.get_conversation_thread(table_type, table.id, "output")
        _check_thread(chat)
        assert len(chat.thread) == 9
        assert chat.thread[-1].content == "6"
        # --- Row ID filtering --- #
        # Filter (include = True)
        chat = jamai.table.get_conversation_thread(
            table_type, table.id, "output", row_id=row_ids[2]
        )
        _check_thread(chat)
        assert len(chat.thread) == 7
        assert chat.thread[-1].content == "3"
        # Filter (include = False)
        chat = jamai.table.get_conversation_thread(
            table_type, table.id, "output", row_id=row_ids[2], include=False
        )
        _check_thread(chat)
        assert len(chat.thread) == 5
        assert chat.thread[-1].content == "1"
        # --- Invalid column --- #
        with pytest.raises(
            ResourceNotFoundError,
            match="Column .*input.* is not found. Available chat columns:.*output.*",
        ):
            jamai.table.get_conversation_thread(table_type, table.id, "input")


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_hybrid_search(
    client_cls: Type[JamAI],
):
    jamai = client_cls()
    table_type = t.TableType.knowledge
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        data = dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="dummy")
        rows = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(Title="Resume 2012", Text="Hi there, I am a farmer.", **data)],
                stream=False,
            ),
        )
        assert isinstance(rows, t.MultiRowCompletionResponse)
        rows = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(Title="Resume 2013", Text="Hi there, I am a carpenter.", **data)],
                stream=False,
            ),
        )
        assert isinstance(rows, t.MultiRowCompletionResponse)
        rows = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(
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
        assert isinstance(rows, t.MultiRowCompletionResponse)
        sleep(1)  # Optional, give it some time to index
        # Rely on embedding
        rows = jamai.table.hybrid_search(
            table_type,
            t.SearchRequest(
                table_id=TABLE_ID_A,
                query="language",
                reranking_model=_get_reranking_model(jamai),
                limit=2,
            ),
        )
        assert len(rows) == 2
        assert "BPE" in rows[0]["Text"]["value"], rows
        # Rely on FTS
        rows = jamai.table.hybrid_search(
            table_type,
            t.SearchRequest(
                table_id=TABLE_ID_A,
                query="candidate 2013",
                reranking_model=_get_reranking_model(jamai),
                limit=2,
            ),
        )
        assert len(rows) == 2
        assert "2013" in rows[0]["Title"]["value"], rows
        # hybrid_search without reranker (RRF only)
        rows = jamai.table.hybrid_search(
            table_type,
            t.SearchRequest(
                table_id=TABLE_ID_A,
                query="language",
                reranking_model=None,
                limit=2,
            ),
        )
        assert len(rows) == 2
        assert "BPE" in rows[0]["Text"]["value"], rows


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.timeout(180)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize(
    "file_path",
    [
        "clients/python/tests/files/pdf/salary 总结.pdf",
        "clients/python/tests/files/pdf_scan/1978_APL_FP_detrapping.PDF",
        "clients/python/tests/files/pdf_mixed/digital_scan_combined.pdf",
        "clients/python/tests/files/md/creative-story.md",
        "clients/python/tests/files/txt/creative-story.txt",
        "clients/python/tests/files/html/RAG and LLM Integration Guide.html",
        "clients/python/tests/files/html/multilingual-code-examples.html",
        "clients/python/tests/files/html/table.html",
        "clients/python/tests/files/xml/weather-forecast-service.xml",
        "clients/python/tests/files/json/company-profile.json",
        "clients/python/tests/files/jsonl/llm-models.jsonl",
        "clients/python/tests/files/jsonl/ChatMed_TCM-v0.2-5records.jsonl",
        "clients/python/tests/files/docx/Recommendation Letter.docx",
        "clients/python/tests/files/pptx/(2017.06.30) NMT in Linear Time (ByteNet).pptx",
        "clients/python/tests/files/xlsx/Claims Form.xlsx",
        "clients/python/tests/files/tsv/weather_observations.tsv",
        "clients/python/tests/files/csv/company-profile.csv",
        "clients/python/tests/files/csv/weather_observations_long.csv",
    ],
    ids=lambda x: basename(x),
)
def test_upload_file(
    client_cls: Type[JamAI],
    file_path: str,
):
    jamai = client_cls()
    table_type = t.TableType.knowledge
    with _create_table(jamai, table_type, cols=[]) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        response = jamai.table.embed_file(file_path, table.id)
        assert isinstance(response, t.OkResponse)
        rows = jamai.table.list_table_rows(table_type, table.id)
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
        assert all(r["Page"]["value"] > 0 for r in rows.items)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.timeout(180)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize(
    "file_path",
    [
        "clients/python/tests/files/pdf/empty.pdf",
        "clients/python/tests/files/pdf/empty_3pages.pdf",
        "clients/python/tests/files/txt/empty.txt",
        "clients/python/tests/files/csv/empty.csv",
    ],
    ids=lambda x: basename(x),
)
def test_upload_empty_file(
    client_cls: Type[JamAI],
    file_path: str,
):
    jamai = client_cls()
    table_type = t.TableType.knowledge
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)

        pattern = re.compile("There is no text or content to embed")
        with pytest.raises(RuntimeError, match=pattern):
            response = jamai.table.embed_file(file_path, table.id)
            assert isinstance(response, t.OkResponse)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.timeout(180)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize(
    "file_path",
    [
        "clients/python/tests/files/jpeg/rabbit.jpeg",
        "clients/python/pyproject.toml",
    ],
    ids=lambda x: basename(x),
)
def test_upload_file_invalid_file_type(
    client_cls: Type[JamAI],
    file_path: str,
):
    jamai = client_cls()
    table_type = t.TableType.knowledge
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        with pytest.raises(RuntimeError, match=r"File type .+ is unsupported"):
            jamai.table.embed_file(file_path, table.id)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_upload_file_options(client_cls: Type[JamAI]):
    jamai = client_cls()

    response = jamai.table.embed_file_options()

    assert isinstance(response, httpx.Response)
    assert response.status_code == 200

    assert "Allow" in response.headers
    assert "POST" in response.headers["Allow"]
    assert "OPTIONS" in response.headers["Allow"]

    assert "Accept" in response.headers
    for content_type in EMBED_WHITE_LIST_EXT:
        assert content_type in response.headers["Accept"]

    assert "Access-Control-Allow-Methods" in response.headers
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
    assert "OPTIONS" in response.headers["Access-Control-Allow-Methods"]

    assert "Access-Control-Allow-Headers" in response.headers
    assert "Content-Type" in response.headers["Access-Control-Allow-Headers"]

    # Ensure the response body is empty
    assert response.content == b""


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.timeout(180)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_upload_long_file(
    client_cls: Type[JamAI],
):
    jamai = client_cls()
    with _create_table(jamai, "knowledge", cols=[], embedding_model="") as table:
        assert isinstance(table, t.TableMetaResponse)
        with TemporaryDirectory() as tmp_dir:
            # Create a long CSV
            data = [
                {"bool": True, "float": 0.0, "int": 0, "str": ""},
                {"bool": False, "float": -1.0, "int": -2, "str": "testing"},
                {"bool": None, "float": None, "int": None, "str": None},
            ]
            file_path = join(tmp_dir, "long.csv")
            df_to_csv(pd.DataFrame.from_dict(data * 100), file_path)
            # Embed the CSV
            assert isinstance(table, t.TableMetaResponse)
            assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
            response = jamai.table.embed_file(file_path, table.id)
            assert isinstance(response, t.OkResponse)
            rows = jamai.table.list_table_rows("knowledge", table.id)
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
            assert all(r["Page"]["value"] > 0 for r in rows.items)


if __name__ == "__main__":
    test_get_conversation_thread(JamAI, t.TableType.action)
