import re
from contextlib import contextmanager
from time import sleep
from typing import Generator, Type

import pytest
from flaky import flaky
from pydantic import ValidationError

from jamaibase import JamAI
from jamaibase import types as t
from jamaibase.utils.exceptions import ResourceNotFoundError

CLIENT_CLS = [JamAI]
TABLE_TYPES = [t.TableType.action, t.TableType.knowledge, t.TableType.chat]
REGULAR_COLUMN_DTYPES: list[str] = ["int", "float", "bool", "str"]
SAMPLE_DATA = {
    "int": -1,
    "float": -0.9,
    "bool": True,
    "str": '"Arrival" is a 2016 science fiction film. "Arrival" è un film di fantascienza del 2016. 「Arrival」は2016年のSF映画です。',
}
KT_FIXED_COLUMN_IDS = ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
CT_FIXED_COLUMN_IDS = ["User"]

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


def _get_image_models(jamai: JamAI) -> str:
    models = jamai.model_names(prefer="openai/gpt-4o-mini", capabilities=["image"])
    return models


def _get_chat_only_model(jamai: JamAI) -> str:
    chat_models = jamai.model_names(capabilities=["chat"])
    image_models = _get_image_models(jamai)
    chat_only_models = [model for model in chat_models if model not in image_models]
    return chat_only_models[0]


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
                        max_tokens=300,
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


@contextmanager
def _create_table_v2(
    jamai: JamAI,
    table_type: t.TableType,
    table_id: str = TABLE_ID_A,
    cols: list[t.ColumnSchemaCreate] | None = None,
    chat_cols: list[t.ColumnSchemaCreate] | None = None,
    llm_model: str = "",
    embedding_model: str = "",
    system_prompt: str = "",
    prompt: str = "",
    delete_first: bool = True,
) -> Generator[t.TableMetaResponse, None, None]:
    try:
        if delete_first:
            jamai.table.delete_table(table_type, table_id)
        if cols is None:
            _input_cols = [
                t.ColumnSchemaCreate(id=f"in_{dtype}", dtype=dtype)
                for dtype in REGULAR_COLUMN_DTYPES
            ]
            _output_cols = [
                t.ColumnSchemaCreate(
                    id=f"out_{dtype}",
                    dtype=dtype,
                    gen_config=t.LLMGenConfig(
                        model=llm_model,
                        system_prompt=system_prompt,
                        prompt=" ".join(f"${{{col.id}}}" for col in _input_cols) + prompt,
                        max_tokens=10,
                    ),
                )
                for dtype in ["str"]
            ]
            cols = _input_cols + _output_cols
        if chat_cols is None:
            chat_cols = [
                t.ColumnSchemaCreate(id="User", dtype="str"),
                t.ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=t.LLMGenConfig(
                        model=llm_model,
                        system_prompt=system_prompt,
                        max_tokens=10,
                    ),
                ),
            ]

        expected_cols = {"ID", "Updated at"}
        expected_cols |= {c.id for c in cols}
        if table_type == t.TableType.action:
            table = jamai.table.create_action_table(
                t.ActionTableSchemaCreate(id=table_id, cols=cols)
            )
        elif table_type == t.TableType.knowledge:
            table = jamai.table.create_knowledge_table(
                t.KnowledgeTableSchemaCreate(
                    id=table_id, cols=cols, embedding_model=embedding_model
                )
            )
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == t.TableType.chat:
            table = jamai.table.create_chat_table(
                t.ChatTableSchemaCreate(id=table_id, cols=chat_cols + cols)
            )
            expected_cols |= {c.id for c in chat_cols}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, t.TableMetaResponse)
        col_ids = set(c.id for c in table.cols)
        assert col_ids == expected_cols
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
        data = dict(
            good=True,
            words=5,
            stars=7.9,
            inputs=TEXT,
            photo="s3://bucket-images/rabbit.jpeg",
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


def _add_row_v2(
    jamai: JamAI,
    table_type: t.TableType,
    stream: bool,
    table_name: str = TABLE_ID_A,
    data: dict | None = None,
    knowledge_data: dict | None = None,
    chat_data: dict | None = None,
    include_output_data: bool = False,
) -> t.MultiRowCompletionResponse:
    if data is None:
        data = {f"in_{dtype}": SAMPLE_DATA[dtype] for dtype in REGULAR_COLUMN_DTYPES}
        if include_output_data:
            data.update({f"out_{dtype}": SAMPLE_DATA[dtype] for dtype in ["str"]})

    if knowledge_data is None:
        knowledge_data = dict(
            Title="Dune: Part Two.",
            Text='"Dune: Part Two" is a 2024 American epic science fiction film.',
        )
        if include_output_data:
            knowledge_data.update({"Title Embed": None, "Text Embed": None})
    if chat_data is None:
        chat_data = dict(User="Tell me a joke.")
        if include_output_data:
            chat_data.update({"AI": "Nah"})
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
        chunks = [r for r in response]
        assert all(isinstance(c, t.CellCompletionResponse) for c in chunks)
        assert all(c.object == "gen_table.completion.chunk" for c in chunks)
        assert len(set(c.row_id for c in chunks)) == 1
        columns = {c.output_column_name: c for c in chunks}
        return t.MultiRowCompletionResponse(
            rows=[t.RowCompletionResponse(columns=columns, row_id=chunks[0].row_id)]
        )
    assert isinstance(response, t.MultiRowCompletionResponse)
    assert response.object == "gen_table.completion.rows"
    assert len(response.rows) == 1
    return response


@contextmanager
def _rename_table(
    jamai: JamAI,
    table_type: t.TableType,
    table_id_src: str,
    table_id_dst: str,
    delete_first: bool = True,
):
    try:
        if delete_first:
            jamai.table.delete_table(table_type, table_id_dst)
        table = jamai.table.rename_table(table_type, table_id_src, table_id_dst)
        assert isinstance(table, t.TableMetaResponse)
        yield table
    finally:
        jamai.table.delete_table(table_type, table_id_dst)


@contextmanager
def _duplicate_table(
    jamai: JamAI,
    table_type: t.TableType,
    table_id_src: str,
    table_id_dst: str,
    include_data: bool = True,
    deploy: bool = False,
    delete_first: bool = True,
):
    try:
        if delete_first:
            jamai.table.delete_table(table_type, table_id_dst)
        table = jamai.table.duplicate_table(
            table_type,
            table_id_src,
            table_id_dst,
            include_data=include_data,
            create_as_child=deploy,
        )
        assert isinstance(table, t.TableMetaResponse)
        yield table
    finally:
        jamai.table.delete_table(table_type, table_id_dst)


@contextmanager
def _create_child_table(
    jamai: JamAI,
    table_type: t.TableType,
    table_id_src: str,
    table_id_dst: str | None,
    delete_first: bool = True,
):
    try:
        if delete_first and isinstance(table_id_dst, str):
            jamai.table.delete_table(table_type, table_id_dst)
        table = jamai.table.duplicate_table(
            table_type, table_id_src, table_id_dst, create_as_child=True
        )
        table_id_dst = table.id
        assert isinstance(table, t.TableMetaResponse)
        yield table
    finally:
        if isinstance(table_id_dst, str):
            jamai.table.delete_table(table_type, table_id_dst)


def _collect_text(
    responses: t.MultiRowCompletionResponse | Generator[t.CellCompletionResponse, None, None],
    col: str,
):
    if isinstance(responses, t.MultiRowCompletionResponse):
        return "".join(r.columns[col].text for r in responses.rows)
    return "".join(r.text for r in responses if r.output_column_name == col)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_delete_table(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table_v2(jamai, table_type) as table_a:
        with _create_table_v2(jamai, table_type, TABLE_ID_B) as table_b:
            assert isinstance(table_a, t.TableMetaResponse)
            assert table_a.id == TABLE_ID_A
            assert table_b.id == TABLE_ID_B
            assert isinstance(table_a.cols, list)
            assert all(isinstance(c, t.ColumnSchema) for c in table_a.cols)
            table = jamai.table.get_table(table_type, TABLE_ID_B)
            assert isinstance(table, t.TableMetaResponse)
        # After deleting table B
        with pytest.raises(ResourceNotFoundError, match="is not found."):
            jamai.table.get_table(table_type, TABLE_ID_B)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize(
    "table_id", ["a", "0", "a.b", "a-b", "a_b", "a-_b", "a-_0b", "a.-_0b", "0_0"]
)
def test_create_table_valid_table_id(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    table_id: str,
):
    jamai = client_cls()
    with _create_table(jamai, table_type, table_id) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert table.id == table_id


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_table_valid_column_id(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    table_id = TABLE_ID_A
    col_ids = ["a", "0", "a b", "a-b", "a_b", "a-_b", "a-_0b", "a -_0b", "0_0"]
    jamai = client_cls()

    # --- Test input column --- #
    cols = [t.ColumnSchemaCreate(id=_id, dtype="str") for _id in col_ids]
    with _create_table(jamai, table_type, table_id, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert len(set(col_ids) - {c.id for c in table.cols}) == 0

    # --- Test output column --- #
    cols = [
        t.ColumnSchemaCreate(
            id=_id,
            dtype="str",
            gen_config=t.LLMGenConfig(),
        )
        for _id in col_ids
    ]
    with _create_table(jamai, table_type, table_id, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert len(set(col_ids) - {c.id for c in table.cols}) == 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize(
    "column_id", ["a_", "_a", "_aa", "aa_", "_a_", "-a", "a-", ".a", "a.", "a.b", "a?b", "a" * 101]
)
def test_create_table_invalid_table_id(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    column_id: str,
):
    table_id = TABLE_ID_A
    jamai = client_cls()

    # --- Test input column --- #
    cols = [
        t.ColumnSchemaCreate(id=column_id, dtype="str"),
    ]
    with pytest.raises(RuntimeError):
        with _create_table(jamai, table_type, table_id, cols=cols):
            pass

    # --- Test output column --- #
    cols = [
        t.ColumnSchemaCreate(
            id=column_id,
            dtype="str",
            gen_config=t.LLMGenConfig(),
        ),
    ]
    with pytest.raises(RuntimeError):
        with _create_table(jamai, table_type, table_id, cols=cols):
            pass


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize(
    "column_id", ["a_", "_a", "_aa", "aa_", "_a_", "-a", "a-", ".a", "a.", "a.b", "a?b", "a" * 101]
)
def test_create_table_invalid_column_id(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    column_id: str,
):
    table_id = TABLE_ID_A
    jamai = client_cls()

    # --- Test input column --- #
    cols = [
        t.ColumnSchemaCreate(id=column_id, dtype="str"),
    ]
    with pytest.raises(RuntimeError):
        with _create_table(jamai, table_type, table_id, cols=cols):
            pass

    # --- Test output column --- #
    cols = [
        t.ColumnSchemaCreate(
            id=column_id,
            dtype="str",
            gen_config=t.LLMGenConfig(),
        ),
    ]
    with pytest.raises(RuntimeError):
        with _create_table(jamai, table_type, table_id, cols=cols):
            pass


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_table_invalid_model(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    table_id = TABLE_ID_A
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="str"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(model="INVALID"),
        ),
    ]
    with pytest.raises(ResourceNotFoundError):
        with _create_table(jamai, table_type, table_id, cols=cols):
            pass


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_table_invalid_column_ref(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    table_id = TABLE_ID_A
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="str"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(prompt="Summarise ${input2}"),
        ),
    ]
    with pytest.raises(RuntimeError):
        with _create_table(jamai, table_type, table_id, cols=cols):
            pass


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_table_invalid_rag(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()

    # Create the knowledge table first
    with _create_table(jamai, "knowledge", TABLE_ID_B, cols=[]) as ktable:
        # --- Valid knowledge table ID --- #
        cols = [
            t.ColumnSchemaCreate(id="input0", dtype="str"),
            t.ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=t.LLMGenConfig(
                    rag_params=t.RAGParams(table_id=ktable.id),
                ),
            ),
        ]
        with _create_table(jamai, table_type, cols=cols) as table:
            assert isinstance(table, t.TableMetaResponse)
        # --- Invalid knowledge table ID --- #
        cols = [
            t.ColumnSchemaCreate(id="input0", dtype="str"),
            t.ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=t.LLMGenConfig(
                    rag_params=t.RAGParams(table_id="INVALID"),
                ),
            ),
        ]
        with pytest.raises(ResourceNotFoundError):
            with _create_table(jamai, table_type, cols=cols):
                pass

        # --- Valid reranker --- #
        cols = [
            t.ColumnSchemaCreate(id="input0", dtype="str"),
            t.ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=t.LLMGenConfig(
                    rag_params=t.RAGParams(
                        table_id=ktable.id, reranking_model=_get_reranking_model(jamai)
                    ),
                ),
            ),
        ]
        with _create_table(jamai, table_type, cols=cols) as table:
            assert isinstance(table, t.TableMetaResponse)

        # --- Invalid reranker --- #
        cols = [
            t.ColumnSchemaCreate(id="input0", dtype="str"),
            t.ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=t.LLMGenConfig(
                    rag_params=t.RAGParams(table_id=ktable.id, reranking_model="INVALID"),
                ),
            ),
        ]
        with pytest.raises(ResourceNotFoundError):
            with _create_table(jamai, table_type, cols=cols):
                pass


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_default_llm_model(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="str"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(),
        ),
        t.ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=None,
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.GenConfig)
        assert isinstance(cols["output0"].gen_config.model, str)
        assert len(cols["output0"].gen_config.model) > 0
        assert cols["output1"].gen_config is None
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)
            assert isinstance(cols["AI"].gen_config.model, str)
            assert len(cols["AI"].gen_config.model) > 0

        # --- Update gen config --- #
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=TABLE_ID_A,
                column_map=dict(
                    output0=None,
                    output1=t.LLMGenConfig(),
                ),
            ),
        )
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert cols["output0"].gen_config is None
        assert isinstance(cols["output1"].gen_config, t.GenConfig)
        assert isinstance(cols["output1"].gen_config.model, str)
        assert len(cols["output1"].gen_config.model) > 0
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)
            assert isinstance(cols["AI"].gen_config.model, str)
            assert len(cols["AI"].gen_config.model) > 0

        # --- Add column --- #
        cols = [
            t.ColumnSchemaCreate(
                id="output2",
                dtype="str",
                gen_config=None,
            ),
            t.ColumnSchemaCreate(
                id="output3",
                dtype="str",
                gen_config=t.LLMGenConfig(),
            ),
        ]
        if table_type == t.TableType.action:
            table = jamai.table.add_action_columns(t.AddActionColumnSchema(id=table.id, cols=cols))
        elif table_type == t.TableType.knowledge:
            table = jamai.table.add_knowledge_columns(
                t.AddKnowledgeColumnSchema(id=table.id, cols=cols)
            )
        elif table_type == t.TableType.chat:
            table = jamai.table.add_chat_columns(t.AddChatColumnSchema(id=table.id, cols=cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert cols["output0"].gen_config is None
        assert isinstance(cols["output1"].gen_config, t.GenConfig)
        assert isinstance(cols["output1"].gen_config.model, str)
        assert len(cols["output1"].gen_config.model) > 0
        assert cols["output2"].gen_config is None
        assert isinstance(cols["output3"].gen_config, t.GenConfig)
        assert isinstance(cols["output3"].gen_config.model, str)
        assert len(cols["output3"].gen_config.model) > 0
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)
            assert isinstance(cols["AI"].gen_config.model, str)
            assert len(cols["AI"].gen_config.model) > 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_default_image_model(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    available_image_models = _get_image_models(jamai)
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="image"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(prompt="${input0}"),
        ),
        t.ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=None,
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.GenConfig)
        assert isinstance(cols["output0"].gen_config.model, str)
        assert cols["output0"].gen_config.model in available_image_models
        assert cols["output1"].gen_config is None
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)
            assert isinstance(cols["AI"].gen_config.model, str)
            assert cols["AI"].gen_config.model in available_image_models

        # --- Update gen config --- #
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=TABLE_ID_A,
                column_map=dict(
                    output0=None,
                    output1=t.LLMGenConfig(prompt="${input0}"),
                ),
            ),
        )
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert cols["output0"].gen_config is None
        assert isinstance(cols["output1"].gen_config, t.GenConfig)
        assert isinstance(cols["output1"].gen_config.model, str)
        assert cols["output1"].gen_config.model in available_image_models

        # --- Add column --- #
        cols = [
            t.ColumnSchemaCreate(
                id="output2",
                dtype="str",
                gen_config=t.LLMGenConfig(prompt="${input0}"),
            ),
            t.ColumnSchemaCreate(id="file_input1", dtype="image"),
            t.ColumnSchemaCreate(
                id="output3",
                dtype="str",
                gen_config=t.LLMGenConfig(prompt="${file_input1}"),
            ),
        ]
        if table_type == t.TableType.action:
            table = jamai.table.add_action_columns(t.AddActionColumnSchema(id=table.id, cols=cols))
        elif table_type == t.TableType.knowledge:
            table = jamai.table.add_knowledge_columns(
                t.AddKnowledgeColumnSchema(id=table.id, cols=cols)
            )
        elif table_type == t.TableType.chat:
            table = jamai.table.add_chat_columns(t.AddChatColumnSchema(id=table.id, cols=cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        # Add a column with default prompt
        cols = [
            t.ColumnSchemaCreate(
                id="output4",
                dtype="str",
                gen_config=t.LLMGenConfig(),
            ),
        ]
        if table_type == t.TableType.action:
            table = jamai.table.add_action_columns(t.AddActionColumnSchema(id=table.id, cols=cols))
        elif table_type == t.TableType.knowledge:
            table = jamai.table.add_knowledge_columns(
                t.AddKnowledgeColumnSchema(id=table.id, cols=cols)
            )
        elif table_type == t.TableType.chat:
            table = jamai.table.add_chat_columns(t.AddChatColumnSchema(id=table.id, cols=cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert cols["output0"].gen_config is None
        for output_column_name in ["output1", "output2", "output3", "output4"]:
            assert isinstance(cols[output_column_name].gen_config, t.GenConfig)
            model = cols[output_column_name].gen_config.model
            assert isinstance(model, str)
            assert model in available_image_models, (
                f'Column {output_column_name} has invalid default model "{model}". Valid: {available_image_models}'
            )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_invalid_image_model(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    available_image_models = _get_image_models(jamai)
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="image"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(model=_get_chat_only_model(jamai), prompt="${input0}"),
        ),
    ]
    with pytest.raises(RuntimeError):
        with _create_table(jamai, table_type, cols=cols) as table:
            pass

    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="image"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(prompt="${input0}"),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.GenConfig)
        assert isinstance(cols["output0"].gen_config.model, str)
        assert cols["output0"].gen_config.model in available_image_models
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)
            assert isinstance(cols["AI"].gen_config.model, str)
            assert cols["AI"].gen_config.model in available_image_models

        # --- Update gen config --- #
        with pytest.raises(RuntimeError):
            table = jamai.table.update_gen_config(
                table_type,
                t.GenConfigUpdateRequest(
                    table_id=TABLE_ID_A,
                    column_map=dict(
                        output0=t.LLMGenConfig(
                            model=_get_chat_only_model(jamai),
                            prompt="${input0}",
                        ),
                    ),
                ),
            )
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=TABLE_ID_A,
                column_map=dict(
                    output0=t.LLMGenConfig(prompt="${input0}"),
                ),
            ),
        )
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.GenConfig)
        assert isinstance(cols["output0"].gen_config.model, str)
        assert cols["output0"].gen_config.model in available_image_models
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)
            assert isinstance(cols["AI"].gen_config.model, str)
            assert cols["AI"].gen_config.model in available_image_models

        # --- Add column --- #
        cols = [
            t.ColumnSchemaCreate(
                id="output1",
                dtype="str",
                gen_config=t.LLMGenConfig(model=_get_chat_only_model(jamai), prompt="${input0}"),
            )
        ]
        with pytest.raises(RuntimeError):
            if table_type == t.TableType.action:
                table = jamai.table.add_action_columns(
                    t.AddActionColumnSchema(id=table.id, cols=cols)
                )
            elif table_type == t.TableType.knowledge:
                table = jamai.table.add_knowledge_columns(
                    t.AddKnowledgeColumnSchema(id=table.id, cols=cols)
                )
            elif table_type == t.TableType.chat:
                table = jamai.table.add_chat_columns(t.AddChatColumnSchema(id=table.id, cols=cols))
            else:
                raise ValueError(f"Invalid table type: {table_type}")


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_default_embedding_model(
    client_cls: Type[JamAI],
):
    jamai = client_cls()
    with _create_table(jamai, "knowledge", cols=[], embedding_model="") as table:
        assert isinstance(table, t.TableMetaResponse)
        for col in table.cols:
            if col.vlen == 0:
                continue
            assert len(col.gen_config.embedding_model) > 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_default_reranker(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    # Create the knowledge table first
    with _create_table(jamai, "knowledge", TABLE_ID_B, cols=[]) as ktable:
        cols = [
            t.ColumnSchemaCreate(id="input0", dtype="str"),
            t.ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=t.LLMGenConfig(
                    rag_params=t.RAGParams(table_id=ktable.id, reranking_model=""),
                ),
            ),
        ]
        with _create_table(jamai, table_type, cols=cols) as table:
            assert isinstance(table, t.TableMetaResponse)
            cols = {c.id: c for c in table.cols}
            reranking_model = cols["output0"].gen_config.rag_params.reranking_model
            assert isinstance(reranking_model, str)
            assert len(reranking_model) > 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize(
    "messages",
    [
        [t.ChatEntry.system(""), t.ChatEntry.user("")],
        [t.ChatEntry.user("")],
    ],
    ids=["system + user", "user only"],
)
def test_default_prompts(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    messages: list[t.ChatEntry],
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="str"),
        t.ColumnSchemaCreate(id="input1", dtype="str"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.ChatRequest(messages=messages),
        ),
        t.ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=t.ChatRequest(messages=messages),
        ),
        t.ColumnSchemaCreate(
            id="output2",
            dtype="str",
            gen_config=t.LLMGenConfig(
                system_prompt="You are an assistant.",
                prompt="Summarise ${input0}.",
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # ["output0", "output1"] should have default prompts
        input_cols = {"input0", "input1"}
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            input_cols |= {"Title", "Text", "File ID", "Page"}
        else:
            input_cols |= {"User"}
        cols = {c.id: c for c in table.cols}
        for col_id in ["output0", "output1"]:
            assert isinstance(cols[col_id].gen_config, t.LLMGenConfig)
            user_prompt = cols[col_id].gen_config.prompt
            referenced_cols = set(re.findall(t.GEN_CONFIG_VAR_PATTERN, user_prompt))
            assert input_cols == referenced_cols, (
                f"Expected input cols = {input_cols}, referenced cols = {referenced_cols}"
            )
        # ["output2"] should have provided prompts
        input_cols = {"input0"}
        cols = {c.id: c for c in table.cols}
        for col_id in ["output2"]:
            assert isinstance(cols[col_id].gen_config, t.LLMGenConfig)
            user_prompt = cols[col_id].gen_config.prompt
            referenced_cols = set(re.findall(t.GEN_CONFIG_VAR_PATTERN, user_prompt))
            assert input_cols == referenced_cols, (
                f"Expected input cols = {input_cols}, referenced cols = {referenced_cols}"
            )

        # --- Add column --- #
        cols = [
            t.ColumnSchemaCreate(
                id="input2",
                dtype="int",
            ),
            t.ColumnSchemaCreate(
                id="output3",
                dtype="str",
                gen_config=t.LLMGenConfig(),
            ),
        ]
        if table_type == t.TableType.action:
            table = jamai.table.add_action_columns(t.AddActionColumnSchema(id=table.id, cols=cols))
        elif table_type == t.TableType.knowledge:
            table = jamai.table.add_knowledge_columns(
                t.AddKnowledgeColumnSchema(id=table.id, cols=cols)
            )
        elif table_type == t.TableType.chat:
            table = jamai.table.add_chat_columns(t.AddChatColumnSchema(id=table.id, cols=cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, t.TableMetaResponse)
        # ["output0", "output1"] should have default prompts
        input_cols = {"input0", "input1"}
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            input_cols |= {"Title", "Text", "File ID", "Page"}
        else:
            input_cols |= {"User"}
        cols = {c.id: c for c in table.cols}
        for col_id in ["output0", "output1"]:
            assert isinstance(cols[col_id].gen_config, t.LLMGenConfig)
            user_prompt = cols[col_id].gen_config.prompt
            referenced_cols = set(re.findall(t.GEN_CONFIG_VAR_PATTERN, user_prompt))
            assert input_cols == referenced_cols, (
                f"Expected input cols = {input_cols}, referenced cols = {referenced_cols}"
            )
        # ["output3"] should have default prompts
        input_cols = {"input0", "input1", "input2"}
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            input_cols |= {"Title", "Text", "File ID", "Page"}
        else:
            input_cols |= {"User"}
        for col_id in ["output3"]:
            assert isinstance(cols[col_id].gen_config, t.LLMGenConfig)
            user_prompt = cols[col_id].gen_config.prompt
            referenced_cols = set(re.findall(t.GEN_CONFIG_VAR_PATTERN, user_prompt))
            assert input_cols == referenced_cols, (
                f"Expected input cols = {input_cols}, referenced cols = {referenced_cols}"
            )
        # ["output2"] should have provided prompts
        input_cols = {"input0"}
        for col_id in ["output2"]:
            assert isinstance(cols[col_id].gen_config, t.LLMGenConfig)
            user_prompt = cols[col_id].gen_config.prompt
            referenced_cols = set(re.findall(t.GEN_CONFIG_VAR_PATTERN, user_prompt))
            assert input_cols == referenced_cols, (
                f"Expected input cols = {input_cols}, referenced cols = {referenced_cols}"
            )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_add_drop_columns(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table_v2(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        _add_row_v2(
            jamai,
            table_type,
            stream=False,
            include_output_data=False,
        )

        # --- COLUMN ADD --- #
        _input_cols = [
            t.ColumnSchemaCreate(id=f"add_in_{dtype}", dtype=dtype)
            for dtype in REGULAR_COLUMN_DTYPES
        ]
        _output_cols = [
            t.ColumnSchemaCreate(
                id=f"add_out_{dtype}",
                dtype=dtype,
                gen_config=t.LLMGenConfig(
                    model="",
                    system_prompt="",
                    prompt=" ".join(f"${{{col.id}}}" for col in _input_cols),
                    max_tokens=10,
                ),
            )
            for dtype in ["str"]
        ]
        cols = _input_cols + _output_cols
        expected_cols = {"ID", "Updated at"}
        expected_cols |= {f"in_{dtype}" for dtype in REGULAR_COLUMN_DTYPES}
        expected_cols |= {f"out_{dtype}" for dtype in ["str"]}
        expected_cols |= {f"add_in_{dtype}" for dtype in REGULAR_COLUMN_DTYPES}
        expected_cols |= {f"add_out_{dtype}" for dtype in ["str"]}
        if table_type == t.TableType.action:
            table = jamai.table.add_action_columns(t.AddActionColumnSchema(id=table.id, cols=cols))
        elif table_type == t.TableType.knowledge:
            table = jamai.table.add_knowledge_columns(
                t.AddKnowledgeColumnSchema(id=table.id, cols=cols)
            )
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == t.TableType.chat:
            expected_cols |= {"User", "AI"}
            table = jamai.table.add_chat_columns(t.AddChatColumnSchema(id=table.id, cols=cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        # Existing row of new columns should contain None
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 1
        row = rows.items[0]
        for col_id, col in row.items():
            if not col_id.startswith("add_"):
                continue
            assert col["value"] is None
        # Test adding a new row
        data = {}
        for dtype in REGULAR_COLUMN_DTYPES:
            data[f"in_{dtype}"] = SAMPLE_DATA[dtype]
            data[f"out_{dtype}"] = SAMPLE_DATA[dtype]
            data[f"add_in_{dtype}"] = SAMPLE_DATA[dtype]
            data[f"add_out_{dtype}"] = SAMPLE_DATA[dtype]
        _add_row_v2(jamai, table_type, False, data=data)
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 2
        row = rows.items[0]
        for col_id, col in row.items():
            if not col_id.startswith("add_"):
                continue
            assert col["value"] is not None

        # --- COLUMN DROP --- #
        table = jamai.table.drop_columns(
            table_type,
            t.ColumnDropRequest(
                table_id=table.id,
                column_names=[f"in_{dtype}" for dtype in REGULAR_COLUMN_DTYPES]
                + [f"out_{dtype}" for dtype in ["str"]],
            ),
        )
        expected_cols = {"ID", "Updated at"}
        expected_cols |= {f"add_in_{dtype}" for dtype in REGULAR_COLUMN_DTYPES}
        expected_cols |= {f"add_out_{dtype}" for dtype in ["str"]}
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == t.TableType.chat:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        # Test adding a new row
        _add_row_v2(jamai, table_type, False, data=data)
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 3
        assert all(set(r.keys()) == expected_cols for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_add_drop_file_column(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table_v2(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        _add_row_v2(
            jamai,
            table_type,
            stream=False,
            include_output_data=False,
        )

        # --- COLUMN ADD --- #
        cols = [
            t.ColumnSchemaCreate(id="add_in_file", dtype="image"),
            t.ColumnSchemaCreate(
                id="add_out_str",
                dtype="str",
                gen_config=t.LLMGenConfig(
                    model="",
                    system_prompt="",
                    prompt="Describe image ${add_in_file}",
                    max_tokens=10,
                ),
            ),
        ]
        expected_cols = {"ID", "Updated at", "add_in_file", "add_out_str"}
        expected_cols |= {f"in_{dtype}" for dtype in REGULAR_COLUMN_DTYPES}
        expected_cols |= {f"out_{dtype}" for dtype in ["str"]}
        if table_type == t.TableType.action:
            table = jamai.table.add_action_columns(t.AddActionColumnSchema(id=table.id, cols=cols))
        elif table_type == t.TableType.knowledge:
            table = jamai.table.add_knowledge_columns(
                t.AddKnowledgeColumnSchema(id=table.id, cols=cols)
            )
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == t.TableType.chat:
            expected_cols |= {"User", "AI"}
            table = jamai.table.add_chat_columns(t.AddChatColumnSchema(id=table.id, cols=cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        # Existing row of new columns should contain None
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 1
        row = rows.items[0]
        for col_id, col in row.items():
            if not col_id.startswith("add_"):
                continue
            assert col["value"] is None
        # Test adding a new row
        upload_response = jamai.file.upload_file("clients/python/tests/files/jpeg/rabbit.jpeg")
        data = {"add_in_file": upload_response.uri}
        for dtype in REGULAR_COLUMN_DTYPES:
            data[f"in_{dtype}"] = SAMPLE_DATA[dtype]
        response = _add_row_v2(jamai, table_type, False, data=data)
        assert len(response.rows[0].columns["add_out_str"].text) > 0
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 2
        row = rows.items[0]
        for col_id, col in row.items():
            if not col_id.startswith("add_in_"):
                continue
            assert col["value"] is not None

        # Block file output column
        with pytest.raises(RuntimeError):
            cols = [
                t.ColumnSchemaCreate(
                    id="add_out_file",
                    dtype="image",
                    gen_config=t.LLMGenConfig(
                        model="",
                        system_prompt="",
                        prompt="Describe image ${add_in_file}",
                        max_tokens=10,
                    ),
                ),
            ]
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

        # --- COLUMN DROP --- #
        table = jamai.table.drop_columns(
            table_type,
            t.ColumnDropRequest(
                table_id=table.id,
                column_names=[f"in_{dtype}" for dtype in REGULAR_COLUMN_DTYPES]
                + [f"out_{dtype}" for dtype in ["str"]],
            ),
        )
        expected_cols = {"ID", "Updated at", "add_in_file", "add_out_str"}
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == t.TableType.chat:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 2
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        # Test adding a new row
        _add_row_v2(jamai, table_type, False, data={"add_in_file": upload_response.uri})
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 3
        assert all(set(r.keys()) == expected_cols for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_kt_drop_invalid_columns(client_cls: Type[JamAI]):
    table_type = "knowledge"
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        for col in KT_FIXED_COLUMN_IDS:
            with pytest.raises(RuntimeError):
                jamai.table.drop_columns(
                    table_type,
                    t.ColumnDropRequest(table_id=table.id, column_names=[col]),
                )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_ct_drop_invalid_columns(client_cls: Type[JamAI]):
    table_type = "chat"
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        for col in CT_FIXED_COLUMN_IDS:
            with pytest.raises(RuntimeError):
                jamai.table.drop_columns(
                    table_type,
                    t.ColumnDropRequest(table_id=table.id, column_names=[col]),
                )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_rename_columns(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="x", dtype="str"),
        t.ColumnSchemaCreate(
            id="y",
            dtype="str",
            gen_config=t.LLMGenConfig(prompt=r"Summarise ${x}, \${x}"),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        # Test rename on empty table
        table = jamai.table.rename_columns(
            table_type,
            t.ColumnRenameRequest(table_id=table.id, column_map=dict(y="z")),
        )
        assert isinstance(table, t.TableMetaResponse)
        expected_cols = {"ID", "Updated at", "x", "z"}
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == t.TableType.chat:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols

        table = jamai.table.get_table(table_type, table.id)
        assert isinstance(table, t.TableMetaResponse)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols
        # Test adding data with new column names
        _add_row(jamai, table_type, False, data=dict(x="True", z="<dummy>"))
        # Test rename table with data
        # Test also auto gen config reference update
        table = jamai.table.rename_columns(
            table_type,
            t.ColumnRenameRequest(table_id=table.id, column_map=dict(x="a")),
        )
        assert isinstance(table, t.TableMetaResponse)
        expected_cols = {"ID", "Updated at", "a", "z"}
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == t.TableType.chat:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols
        table = jamai.table.get_table(table_type, table.id)
        assert isinstance(table, t.TableMetaResponse)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols
        # Test auto gen config reference update
        cols = {c.id: c for c in table.cols}
        prompt = cols["z"].gen_config.prompt
        assert "${a}" in prompt
        assert "\\${x}" in prompt  # Escaped reference syntax

        # Repeated new column names
        with pytest.raises(RuntimeError):
            jamai.table.rename_columns(
                table_type,
                t.ColumnRenameRequest(table_id=table.id, column_map=dict(a="b", z="b")),
            )

        # Overlapping new and old column names
        with pytest.raises(RuntimeError):
            jamai.table.rename_columns(
                table_type,
                t.ColumnRenameRequest(table_id=table.id, column_map=dict(a="b", z="a")),
            )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_kt_rename_invalid_columns(client_cls: Type[JamAI]):
    table_type = "knowledge"
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        for col in KT_FIXED_COLUMN_IDS:
            with pytest.raises(RuntimeError):
                jamai.table.rename_columns(
                    table_type,
                    t.ColumnRenameRequest(table_id=table.id, column_map={col: col}),
                )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_ct_rename_invalid_columns(client_cls: Type[JamAI]):
    table_type = "chat"
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        for col in CT_FIXED_COLUMN_IDS:
            with pytest.raises(RuntimeError):
                jamai.table.rename_columns(
                    table_type,
                    t.ColumnRenameRequest(table_id=table.id, column_map={col: col}),
                )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_reorder_columns(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        table = jamai.table.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, t.TableMetaResponse)

        column_names = [
            "inputs",
            "good",
            "words",
            "stars",
            "photo",
            "summary",
            "captioning",
        ]
        expected_order = [
            "ID",
            "Updated at",
            "good",
            "words",
            "stars",
            "inputs",
            "photo",
            "summary",
            "captioning",
        ]
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            column_names += ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
            expected_order = (
                expected_order[:2]
                + ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
                + expected_order[2:]
            )
        elif table_type == t.TableType.chat:
            column_names += ["User", "AI"]
            expected_order = expected_order[:2] + ["User", "AI"] + expected_order[2:]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols
        # Test reorder empty table
        table = jamai.table.reorder_columns(
            table_type,
            t.ColumnReorderRequest(table_id=TABLE_ID_A, column_names=column_names),
        )
        expected_order = [
            "ID",
            "Updated at",
            "inputs",
            "good",
            "words",
            "stars",
            "photo",
            "summary",
            "captioning",
        ]
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            expected_order += ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
        elif table_type == t.TableType.chat:
            expected_order += ["User", "AI"]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols
        table = jamai.table.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, t.TableMetaResponse)
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


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_reorder_columns_invalid(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        assert all(isinstance(c, t.ColumnSchema) for c in table.cols)
        table = jamai.table.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, t.TableMetaResponse)

        column_names = [
            "inputs",
            "good",
            "words",
            "stars",
            "photo",
            "summary",
            "captioning",
        ]
        expected_order = [
            "ID",
            "Updated at",
            "good",
            "words",
            "stars",
            "inputs",
            "photo",
            "summary",
            "captioning",
        ]
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            column_names += ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
            expected_order = (
                expected_order[:2]
                + ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
                + expected_order[2:]
            )
        elif table_type == t.TableType.chat:
            column_names += ["User", "AI"]
            expected_order = expected_order[:2] + ["User", "AI"] + expected_order[2:]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols

        # --- Test validation by putting "summary" on the left of "words" --- #
        column_names = [
            "inputs",
            "good",
            "stars",
            "summary",
            "words",
            "photo",
            "captioning",
        ]
        if table_type == t.TableType.action:
            pass
        elif table_type == t.TableType.knowledge:
            column_names += ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
        elif table_type == t.TableType.chat:
            column_names += ["User", "AI"]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        with pytest.raises(RuntimeError, match="referenced an invalid source column"):
            jamai.table.reorder_columns(
                table_type,
                t.ColumnReorderRequest(table_id=TABLE_ID_A, column_names=column_names),
            )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_update_gen_config(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="str"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(),
        ),
        t.ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=None,
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.LLMGenConfig)
        assert isinstance(cols["output0"].gen_config.system_prompt, str)
        assert isinstance(cols["output0"].gen_config.prompt, str)
        assert len(cols["output0"].gen_config.system_prompt) > 0
        assert len(cols["output0"].gen_config.prompt) > 0
        assert cols["output1"].gen_config is None
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)

        # --- Switch gen config --- #
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    output0=None,
                    output1=t.LLMGenConfig(),
                ),
            ),
        )
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert cols["output0"].gen_config is None
        assert isinstance(cols["output1"].gen_config, t.LLMGenConfig)
        assert isinstance(cols["output1"].gen_config.system_prompt, str)
        assert isinstance(cols["output1"].gen_config.prompt, str)
        assert len(cols["output1"].gen_config.system_prompt) > 0
        assert len(cols["output1"].gen_config.prompt) > 0
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)

        # --- Update gen config --- #
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    output0=t.LLMGenConfig(),
                ),
            ),
        )
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.GenConfig)
        assert isinstance(cols["output1"].gen_config, t.GenConfig)
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)

        # --- Update gen config --- #
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    output1=None,
                ),
            ),
        )
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.GenConfig)
        assert cols["output1"].gen_config is None
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)

        # --- Chat AI column must always have gen config --- #
        if table_type == t.TableType.chat:
            table = jamai.table.update_gen_config(
                table_type,
                t.GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(AI=None),
                ),
            )
            assert isinstance(table, t.TableMetaResponse)
            cols = {c.id: c for c in table.cols}
            assert cols["AI"].gen_config is not None

        # --- Chat AI column multi-turn must always be True --- #
        if table_type == t.TableType.chat:
            chat_cfg = {c.id: c for c in table.cols}["AI"].gen_config
            chat_cfg.multi_turn = False
            table = jamai.table.update_gen_config(
                table_type,
                t.GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(AI=chat_cfg),
                ),
            )
            assert isinstance(table, t.TableMetaResponse)
            cols = {c.id: c for c in table.cols}
            assert cols["AI"].gen_config.multi_turn is True


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_update_gen_config_invalid_model(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="str"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(),
        ),
        t.ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=None,
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.GenConfig)
        assert cols["output1"].gen_config is None
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)

        # --- Update gen config --- #
        with pytest.raises(ResourceNotFoundError):
            table = jamai.table.update_gen_config(
                table_type,
                t.GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(
                        output0=t.LLMGenConfig(model="INVALID"),
                    ),
                ),
            )
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    output0=t.LLMGenConfig(model=_get_chat_model(jamai)),
                ),
            ),
        )


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_update_gen_config_invalid_column_ref(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="str"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(),
        ),
        t.ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=None,
        ),
    ]
    with _create_table(jamai, table_type, cols=cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        # Check gen configs
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.LLMGenConfig)
        assert isinstance(cols["output0"].gen_config.system_prompt, str)
        assert isinstance(cols["output0"].gen_config.prompt, str)
        assert len(cols["output0"].gen_config.system_prompt) > 0
        assert len(cols["output0"].gen_config.prompt) > 0
        assert cols["output1"].gen_config is None
        if table_type == t.TableType.chat:
            assert isinstance(cols["AI"].gen_config, t.GenConfig)

        # --- Update gen config --- #
        with pytest.raises(RuntimeError):
            table = jamai.table.update_gen_config(
                table_type,
                t.GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(
                        output0=t.LLMGenConfig(prompt="Summarise ${input2}"),
                    ),
                ),
            )
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    output0=t.LLMGenConfig(prompt="Summarise ${input0}"),
                ),
            ),
        )
        cols = {c.id: c for c in table.cols}
        assert isinstance(cols["output0"].gen_config, t.LLMGenConfig)
        assert isinstance(cols["output0"].gen_config.system_prompt, str)
        assert isinstance(cols["output0"].gen_config.prompt, str)
        assert len(cols["output0"].gen_config.system_prompt) > 0
        assert len(cols["output0"].gen_config.prompt) > 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_update_gen_config_invalid_rag(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="input0", dtype="str"),
        t.ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=t.LLMGenConfig(),
        ),
        t.ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=None,
        ),
    ]
    with _create_table(jamai, "knowledge", cols=[]) as ktable:
        assert isinstance(ktable, t.TableMetaResponse)
        with _create_table(jamai, table_type, cols=cols) as table:
            assert isinstance(table, t.TableMetaResponse)
            # Check gen configs
            cols = {c.id: c for c in table.cols}
            assert isinstance(cols["output0"].gen_config, t.GenConfig)
            assert cols["output1"].gen_config is None
            if table_type == t.TableType.chat:
                assert isinstance(cols["AI"].gen_config, t.GenConfig)

            # --- Invalid knowledge table ID --- #
            with pytest.raises(ResourceNotFoundError):
                table = jamai.table.update_gen_config(
                    table_type,
                    t.GenConfigUpdateRequest(
                        table_id=table.id,
                        column_map=dict(
                            output0=t.LLMGenConfig(
                                rag_params=t.RAGParams(table_id="INVALID"),
                            ),
                        ),
                    ),
                )
            # --- Valid knowledge table ID --- #
            table = jamai.table.update_gen_config(
                table_type,
                t.GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(
                        output0=t.LLMGenConfig(
                            rag_params=t.RAGParams(table_id=ktable.id),
                        ),
                    ),
                ),
            )

            # --- Invalid reranker --- #
            with pytest.raises(ResourceNotFoundError):
                table = jamai.table.update_gen_config(
                    table_type,
                    t.GenConfigUpdateRequest(
                        table_id=table.id,
                        column_map=dict(
                            output0=t.LLMGenConfig(
                                rag_params=t.RAGParams(
                                    table_id=ktable.id, reranking_model="INVALID"
                                ),
                            ),
                        ),
                    ),
                )
            # --- Valid reranker --- #
            table = jamai.table.update_gen_config(
                table_type,
                t.GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(
                        output0=t.LLMGenConfig(
                            rag_params=t.RAGParams(table_id=ktable.id, reranking_model=None),
                        ),
                    ),
                ),
            )
            cols = {c.id: c for c in table.cols}
            assert cols["output0"].gen_config.rag_params.reranking_model is None
            table = jamai.table.update_gen_config(
                table_type,
                t.GenConfigUpdateRequest(
                    table_id=table.id,
                    column_map=dict(
                        output0=t.LLMGenConfig(
                            rag_params=t.RAGParams(table_id=ktable.id, reranking_model=""),
                        ),
                    ),
                ),
            )
            cols = {c.id: c for c in table.cols}
            assert isinstance(cols["output0"].gen_config.rag_params.reranking_model, str)
            assert len(cols["output0"].gen_config.rag_params.reranking_model) > 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_null_gen_config(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    stream: bool,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        table = jamai.table.update_gen_config(
            table_type,
            t.GenConfigUpdateRequest(table_id=table.id, column_map=dict(summary=None)),
        )
        response = _add_row(
            jamai, table_type, stream, data=dict(good=True, words=5, stars=9.9, inputs=TEXT)
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response, t.RowCompletionResponse)
        rows = jamai.table.list_table_rows(table_type, table.id)
        assert isinstance(rows.items, list)
        assert len(rows.items) == 1
        row = rows.items[0]
        assert row["summary"]["value"] is None


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_invalid_referenced_column(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    # --- Non-existent column --- #
    cols = [
        t.ColumnSchemaCreate(id="words", dtype="int"),
        t.ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model=_get_chat_model(jamai),
                system_prompt="You are a concise assistant.",
                prompt="Summarise ${inputs}",
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with pytest.raises(RuntimeError, match="invalid source column"):
        with _create_table(jamai, table_type, cols=cols):
            pass

    # --- Vector column --- #
    cols = [
        t.ColumnSchemaCreate(id="words", dtype="int"),
        t.ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model=_get_chat_model(jamai),
                system_prompt="You are a concise assistant.",
                prompt="Summarise ${Text Embed}",
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ).model_dump(),
        ),
    ]
    with pytest.raises(RuntimeError, match="invalid source column"):
        with _create_table(jamai, table_type, cols=cols):
            pass


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_gen_config_empty_prompts(
    client_cls: Type[JamAI],
    table_type: t.TableType,
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
    chat_cols = [
        t.ColumnSchemaCreate(id="User", dtype="str"),
        t.ColumnSchemaCreate(
            id="AI",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model=_get_chat_model(jamai),
                temperature=0.001,
                top_p=0.001,
                max_tokens=5,
            ),
        ),
    ]
    with _create_table(jamai, table_type, cols=cols, chat_cols=chat_cols) as table:
        assert isinstance(table, t.TableMetaResponse)
        data = dict(words=5)
        if table_type == t.TableType.knowledge:
            data["Title"] = "Dune: Part Two."
            data["Text"] = "Dune: Part Two is a 2024 American epic science fiction film."
        response = jamai.table.add_table_rows(
            table_type,
            t.MultiRowAddRequest(table_id=table.id, data=[data], stream=stream),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, t.CellCompletionResponse) for r in responses)
            summary = "".join(r.text for r in responses if r.output_column_name == "summary")
            assert len(summary) > 0
            if table_type == t.TableType.chat:
                ai = "".join(r.text for r in responses if r.output_column_name == "AI")
                assert len(ai) > 0
        else:
            assert isinstance(response.rows[0], t.RowCompletionResponse)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_gen_config_no_message(
    client_cls: Type[JamAI],
):
    jamai = client_cls()
    with pytest.raises(ValidationError, match="at least 1 item"):
        _ = [
            t.ColumnSchemaCreate(id="words", dtype="int"),
            t.ColumnSchemaCreate(
                id="summary",
                dtype="str",
                gen_config=t.ChatRequest(
                    model=_get_chat_model(jamai),
                    messages=[],
                    temperature=0.001,
                    top_p=0.001,
                    max_tokens=10,
                ),
            ),
        ]


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_get_and_list_tables(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    _delete_tables(jamai)
    with (
        _create_table(jamai, table_type) as table,
        _create_table(jamai, table_type, TABLE_ID_B),
        _create_table(jamai, table_type, TABLE_ID_C),
        _create_table(jamai, table_type, TABLE_ID_X),
    ):
        assert isinstance(table, t.TableMetaResponse)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )

        # Regular case
        table = jamai.table.get_table(table_type, TABLE_ID_B)
        assert isinstance(table, t.TableMetaResponse)
        assert table.id == TABLE_ID_B

        tables = jamai.table.list_tables(table_type)
        assert isinstance(tables.items, list)
        assert tables.total == 4
        assert tables.offset == 0
        assert tables.limit == 100
        assert len(tables.items) == 4
        assert all(isinstance(r, t.TableMetaResponse) for r in tables.items)

        # Test various offset and limit
        tables = jamai.table.list_tables(table_type, offset=3, limit=2)
        assert isinstance(tables.items, list)
        assert tables.total == 4
        assert tables.offset == 3
        assert tables.limit == 2
        assert len(tables.items) == 1
        assert all(isinstance(r, t.TableMetaResponse) for r in tables.items)

        tables = jamai.table.list_tables(table_type, offset=4, limit=2)
        assert isinstance(tables.items, list)
        assert tables.total == 4
        assert tables.offset == 4
        assert tables.limit == 2
        assert len(tables.items) == 0

        tables = jamai.table.list_tables(table_type, offset=5, limit=2)
        assert isinstance(tables.items, list)
        assert tables.total == 4
        assert tables.offset == 5
        assert tables.limit == 2
        assert len(tables.items) == 0


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_table_search_and_parent_id(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    _delete_tables(jamai)
    with (
        _create_table(jamai, table_type, "beast") as table,
        _create_table(jamai, table_type, "feast"),
        _create_table(jamai, table_type, "bear"),
        _create_table(jamai, table_type, "fear"),
    ):
        assert isinstance(table, t.TableMetaResponse)
        with (
            _create_child_table(jamai, table_type, "beast", "least"),
            _create_child_table(jamai, table_type, "beast", "lease"),
            _create_child_table(jamai, table_type, "beast", "yeast"),
        ):
            # Regular list
            tables = jamai.table.list_tables(table_type, limit=3)
            assert isinstance(tables.items, list)
            assert tables.total == 7
            assert tables.offset == 0
            assert tables.limit == 3
            assert len(tables.items) == 3
            assert all(isinstance(r, t.TableMetaResponse) for r in tables.items)
            # Search
            tables = jamai.table.list_tables(table_type, search_query="be", limit=3)
            assert isinstance(tables.items, list)
            assert tables.total == 2
            assert tables.offset == 0
            assert tables.limit == 3
            assert len(tables.items) == 2
            assert all(isinstance(r, t.TableMetaResponse) for r in tables.items)
            # Search
            tables = jamai.table.list_tables(table_type, search_query="ast", limit=3)
            assert isinstance(tables.items, list)
            assert tables.total == 4
            assert tables.offset == 0
            assert tables.limit == 3
            assert len(tables.items) == 3
            assert all(isinstance(r, t.TableMetaResponse) for r in tables.items)
            # Search with parent ID
            tables = jamai.table.list_tables(table_type, search_query="ast", parent_id="beast")
            assert isinstance(tables.items, list)
            assert tables.total == 2
            assert tables.offset == 0
            assert tables.limit == 100
            assert len(tables.items) == 2
            assert all(isinstance(r, t.TableMetaResponse) for r in tables.items)
            # Search with parent ID
            tables = jamai.table.list_tables(table_type, search_query="as", parent_id="beast")
            assert isinstance(tables.items, list)
            assert tables.total == 3
            assert tables.offset == 0
            assert tables.limit == 100
            assert len(tables.items) == 3
            assert all(isinstance(r, t.TableMetaResponse) for r in tables.items)


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_duplicate_table(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )

        # Duplicate with data
        with _duplicate_table(jamai, table_type, TABLE_ID_A, TABLE_ID_B) as table:
            # Add another to table A
            _add_row(
                jamai,
                table_type,
                False,
                table_name=TABLE_ID_A,
                data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
            )
            assert table.id == TABLE_ID_B
            rows = jamai.table.list_table_rows(table_type, TABLE_ID_B)
            assert len(rows.items) == 1

        # Duplicate without data
        with _duplicate_table(
            jamai, table_type, TABLE_ID_A, TABLE_ID_C, include_data=False
        ) as table:
            assert table.id == TABLE_ID_C
            rows = jamai.table.list_table_rows(table_type, TABLE_ID_C)
            assert len(rows.items) == 0

        # Deploy with data
        with _duplicate_table(jamai, table_type, TABLE_ID_A, TABLE_ID_B, deploy=True) as table:
            assert table.id == TABLE_ID_B
            assert table.parent_id == TABLE_ID_A
            rows = jamai.table.list_table_rows(table_type, TABLE_ID_B)
            assert len(rows.items) == 2

        # Deploy will always include data
        with _duplicate_table(
            jamai, table_type, TABLE_ID_A, TABLE_ID_C, deploy=True, include_data=False
        ) as table:
            assert table.id == TABLE_ID_C
            assert table.parent_id == TABLE_ID_A
            rows = jamai.table.list_table_rows(table_type, TABLE_ID_C)
            assert len(rows.items) == 2


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize(
    "table_id_dst",
    ["a_", "_a", "_aa", "aa_", "_a_", "-a", "a-", ".a", "a.", "a?b", "a b", "a" * 101],
)
def test_duplicate_table_invalid_name(
    client_cls: Type[JamAI],
    table_type: t.TableType,
    table_id_dst: str,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table:
        assert isinstance(table, t.TableMetaResponse)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )

        with pytest.raises(RuntimeError):
            with _duplicate_table(jamai, table_type, TABLE_ID_A, table_id_dst):
                pass


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_child_table(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table(jamai, table_type) as table_a:
        assert isinstance(table_a, t.TableMetaResponse)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )
        # Duplicate with data
        with _create_child_table(jamai, table_type, TABLE_ID_A, TABLE_ID_B) as table_b:
            assert isinstance(table_b, t.TableMetaResponse)
            # Add another to table A
            _add_row(
                jamai,
                table_type,
                False,
                data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
            )
            assert table_b.id == TABLE_ID_B
            # Ensure the the parent id meta data has been correctly set.
            assert table_b.parent_id == TABLE_ID_A
            rows = jamai.table.list_table_rows(table_type, TABLE_ID_B)
            assert len(rows.items) == 1

        # Create child table with no dst id
        with _create_child_table(jamai, table_type, TABLE_ID_A, None) as table_c:
            assert isinstance(table_c.id, str)
            assert table_c.id.startswith(TABLE_ID_A)
            assert table_c.id != TABLE_ID_A
            # Ensure the the parent id meta data has been correctly set.
            assert table_c.parent_id == TABLE_ID_A
            rows = jamai.table.list_table_rows(table_type, table_c.id)
            assert len(rows.items) == 2


@flaky(max_runs=5, min_passes=1, rerun_filter=_rerun_on_fs_error_with_delay)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_rename_table(
    client_cls: Type[JamAI],
    table_type: t.TableType,
):
    jamai = client_cls()
    with _create_table(jamai, table_type, TABLE_ID_A) as table:
        assert isinstance(table, t.TableMetaResponse)
        _add_row(
            jamai,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )
        # Create child table
        with _create_child_table(jamai, table_type, TABLE_ID_A, TABLE_ID_B) as child:
            assert isinstance(child, t.TableMetaResponse)
            # Rename
            with _rename_table(jamai, table_type, TABLE_ID_A, TABLE_ID_C) as table:
                rows = jamai.table.list_table_rows(table_type, TABLE_ID_C)
                assert len(rows.items) == 1
                # Assert the old table is gone
                with pytest.raises(ResourceNotFoundError):
                    jamai.table.list_table_rows(table_type, TABLE_ID_A)
                # Assert the child table parent ID is updated
                assert jamai.table.get_table(table_type, child.id).parent_id == TABLE_ID_C
                # Add rows to both tables
                _add_row(
                    jamai,
                    table_type,
                    False,
                    TABLE_ID_B,
                    data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
                )
                _add_row(
                    jamai,
                    table_type,
                    False,
                    TABLE_ID_C,
                    data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
                )


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
def test_chat_table_gen_config(
    client_cls: Type[JamAI],
):
    jamai = client_cls()
    cols = [
        t.ColumnSchemaCreate(id="User", dtype="str"),
        t.ColumnSchemaCreate(
            id="AI",
            dtype="str",
            gen_config=t.LLMGenConfig(
                model=_get_chat_model(jamai),
                system_prompt="You are a concise assistant.",
                multi_turn=False,
                temperature=0.001,
                top_p=0.001,
                max_tokens=20,
            ),
        ),
    ]
    with _create_table(jamai, "chat", cols=[], chat_cols=cols) as table:
        cols = {c.id: c for c in table.cols}
        # AI column gen config will be multi turn regardless of input params
        assert cols["AI"].gen_config.multi_turn is True


if __name__ == "__main__":
    test_add_drop_columns(JamAI, t.TableType.action)
