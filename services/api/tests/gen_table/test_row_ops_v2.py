import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from os.path import basename, dirname, join, realpath
from tempfile import TemporaryDirectory
from types import NoneType
from typing import Any

import httpx
import pytest
from flaky import flaky

from jamaibase import JamAI
from jamaibase.types import (
    CITATION_PATTERN,
    CellCompletionResponse,
    ChatCompletionChunkResponse,
    ChatCompletionResponse,
    ColumnSchemaCreate,
    GenConfigUpdateRequest,
    GetURLResponse,
    LLMGenConfig,
    MultiRowAddRequest,
    MultiRowCompletionResponse,
    MultiRowUpdateRequest,
    OkResponse,
    OrganizationCreate,
    PythonGenConfig,
    RAGParams,
    References,
    RowCompletionResponse,
    S3Content,
    TextContent,
    WebSearchTool,
)
from owl.configs import ENV_CONFIG
from owl.types import (
    ModelCapability,
    ModelType,
    RegenStrategy,
    TableType,
)
from owl.utils.exceptions import BadInputError, ResourceNotFoundError
from owl.utils.test import (
    ELLM_DESCRIBE_CONFIG,
    ELLM_DESCRIBE_DEPLOYMENT,
    GPT_5_MINI_CONFIG,
    GPT_5_MINI_DEPLOYMENT,
    GPT_41_MINI_CONFIG,
    GPT_41_MINI_DEPLOYMENT,
    STREAM_PARAMS,
    TABLE_TYPES,
    TEXT_EMBEDDING_3_SMALL_CONFIG,
    TEXT_EMBEDDING_3_SMALL_DEPLOYMENT,
    TEXTS,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    add_table_rows,
    assert_is_vector_or_none,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_table,
    create_user,
    get_file_map,
    get_table_row,
    list_table_rows,
    regen_table_rows,
    upload_file,
)

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)

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


@dataclass(slots=True)
class ServingContext:
    superuser_id: str
    superorg_id: str
    project_id: str
    embedding_size: int
    image_uri: str
    audio_uri: str
    document_uri: str
    gpt_llm_model_id: str
    gpt_llm_reasoning_config_id: str
    desc_llm_model_id: str
    lorem_llm_model_id: str
    short_llm_model_id: str
    echo_model_id: str
    embed_model_id: str
    rerank_model_id: str


@pytest.fixture(scope="module")
def setup():
    """
    Fixture to set up the necessary organization and projects for file tests.
    """
    with (
        create_user() as superuser,
        create_organization(
            body=OrganizationCreate(name="Superorg"), user_id=superuser.id
        ) as superorg,
        create_project(
            dict(name="Superorg Project"), user_id=superuser.id, organization_id=superorg.id
        ) as p0,
    ):
        assert superorg.id == "0"
        # Create models
        with (
            create_model_config(GPT_41_MINI_CONFIG) as gpt_llm_config,
            create_model_config(GPT_5_MINI_CONFIG) as gpt_llm_reasoning_config,
            create_model_config(ELLM_DESCRIBE_CONFIG) as desc_llm_config,
            create_model_config(
                dict(
                    id="ellm/lorem-ttft-20-tpot-10",  # TTFT 20 ms, TPOT 10 ms
                    type=ModelType.LLM,
                    name="ELLM Lorem Ipsum Generator",
                    capabilities=[
                        ModelCapability.CHAT,
                        ModelCapability.IMAGE,
                        ModelCapability.AUDIO,
                    ],
                    context_length=128000,
                    languages=["en"],
                    owned_by="ellm",
                )
            ) as lorem_llm_config,
            create_model_config(
                dict(
                    # Max context length = 10
                    id="ellm/lorem-context-10",
                    type=ModelType.LLM,
                    name="Short-Context Chat Model",
                    capabilities=[ModelCapability.CHAT],
                    context_length=5,
                    languages=["en"],
                    owned_by="ellm",
                )
            ) as short_llm_config,
            create_model_config(
                dict(
                    id="ellm/echo-prompt",
                    type=ModelType.LLM,
                    name="Echo Prompt Model",
                    capabilities=[ModelCapability.CHAT],
                    context_length=1000000,
                    languages=["en"],
                    owned_by="ellm",
                )
            ) as echo_config,
            create_model_config(TEXT_EMBEDDING_3_SMALL_CONFIG) as embed_config,
            create_model_config(RERANK_ENGLISH_v3_SMALL_CONFIG) as rerank_config,
        ):
            # Create deployments
            with (
                create_deployment(GPT_41_MINI_DEPLOYMENT),
                create_deployment(GPT_5_MINI_DEPLOYMENT),
                create_deployment(ELLM_DESCRIBE_DEPLOYMENT),
                create_deployment(
                    dict(
                        model_id=lorem_llm_config.id,
                        name=f"{lorem_llm_config.name} Deployment",
                        provider="custom",
                        routing_id=lorem_llm_config.id,
                        api_base=ENV_CONFIG.test_llm_api_base,
                    )
                ),
                create_deployment(
                    dict(
                        model_id=short_llm_config.id,
                        name="Short chat Deployment",
                        provider="custom",
                        routing_id=short_llm_config.id,
                        api_base=ENV_CONFIG.test_llm_api_base,
                    )
                ),
                create_deployment(
                    dict(
                        model_id=echo_config.id,
                        name="Echo Prompt Deployment",
                        provider="custom",
                        routing_id=echo_config.id,
                        api_base=ENV_CONFIG.test_llm_api_base,
                    )
                ),
                create_deployment(TEXT_EMBEDDING_3_SMALL_DEPLOYMENT),
                create_deployment(RERANK_ENGLISH_v3_SMALL_DEPLOYMENT),
            ):
                client = JamAI(user_id=superuser.id, project_id=p0.id)
                image_uri = upload_file(client, FILES["rabbit.jpeg"]).uri
                audio_uri = upload_file(client, FILES["gutter.mp3"]).uri
                document_uri = upload_file(
                    client, FILES["LLMs as Optimizers [DeepMind ; 2023].pdf"]
                ).uri
                yield ServingContext(
                    superuser_id=superuser.id,
                    superorg_id=superorg.id,
                    project_id=p0.id,
                    embedding_size=embed_config.final_embedding_size,
                    image_uri=image_uri,
                    audio_uri=audio_uri,
                    document_uri=document_uri,
                    gpt_llm_model_id=gpt_llm_config.id,
                    gpt_llm_reasoning_config_id=gpt_llm_reasoning_config.id,
                    desc_llm_model_id=desc_llm_config.id,
                    lorem_llm_model_id=lorem_llm_config.id,
                    short_llm_model_id=short_llm_config.id,
                    echo_model_id=echo_config.id,
                    embed_model_id=embed_config.id,
                    rerank_model_id=rerank_config.id,
                )


@dataclass(slots=True)
class Data:
    data_list: list[dict[str, Any]]
    action_data_list: list[dict[str, Any]]
    knowledge_data: dict[str, Any]
    chat_data: dict[str, Any]
    extra_data: dict[str, Any]


INPUT_COLUMNS = ["int", "float", "bool", "str", "image", "audio", "document"]
FILE_COLUMNS = ["image", "audio", "document"]
OUTPUT_COLUMNS = ["summary (1.0)", "summary (2.0)"]


def _default_data(setup: ServingContext):
    action_data_list = [
        {
            "ID": str(i),
            "Updated at": "1990-05-13T09:01:50.010756+00:00",
            "int": 1 if i % 2 == 0 else (1.0 if i % 4 == 1 else None),
            "float": -1.25 if i % 2 == 0 else (5 if i % 4 == 1 else None),
            "bool": True if i % 2 == 0 else (False if i % 4 == 1 else None),
            # `str` will sort in opposite order to ID
            "str": f"{100 - i:04d}: {t}",
            "image": setup.image_uri if i % 2 == 0 else None,
            "audio": setup.audio_uri if i % 2 == 0 else None,
            "document": setup.document_uri if i % 2 == 0 else None,
        }
        for i, t in enumerate(list(TEXTS.values()) + ["", None])
    ]
    # Assert integers and floats contain a mix of int, float, None
    _ints = [type(d["int"]) for d in action_data_list]
    assert int in _ints
    assert float in _ints
    assert NoneType in _ints
    _floats = [type(d["float"]) for d in action_data_list]
    assert int in _floats
    assert float in _floats
    assert NoneType in _floats
    # Assert booleans contain a mix of True, False, None
    _bools = [d["bool"] for d in action_data_list]
    assert True in _bools
    assert False in _bools
    assert None in _bools
    # # Assert strings contain a mix of empty string and None
    # _summaries = [d["str"] for d in action_data_list]
    # assert None in _summaries
    # assert "" in _summaries
    knowledge_data = {
        "Title": "Dune: Part Two.",
        "Text": '"Dune: Part Two" is a film.',
        # We use values that can be represented exactly as IEEE floats to ease comparison
        "Title Embed": [-1.25] * setup.embedding_size,
        "Text Embed": [0.25] * setup.embedding_size,
    }
    chat_data = dict(User=".")
    extra_data = dict(good=True, words=5)
    return Data(
        data_list=[
            dict(**d, **knowledge_data, **chat_data, **extra_data) for d in action_data_list
        ],
        action_data_list=action_data_list,
        knowledge_data=knowledge_data,
        chat_data=chat_data,
        extra_data=extra_data,
    )


def _add_row_default_data(
    setup: ServingContext,
    client: JamAI,
    *,
    table_type: TableType,
    table_name: str,
    stream: bool,
) -> tuple[MultiRowCompletionResponse, Data]:
    data = _default_data(setup)
    response = add_table_rows(client, table_type, table_name, data.data_list, stream=stream)
    # Check returned chunks / response
    for row in response.rows:
        for col_name, col_value in row.columns.items():
            assert isinstance(col_name, str)
            assert isinstance(col_value, (ChatCompletionResponse, ChatCompletionChunkResponse))
            assert isinstance(col_value.content, str)
            assert len(col_value.content) > 0
    assert len(response.rows) == len(data.data_list)
    # Check expected output columns
    expected_columns = set(OUTPUT_COLUMNS)
    if table_type == TableType.CHAT:
        expected_columns |= {"AI"}
    assert all(set(r.columns.keys()) == expected_columns for r in response.rows), (
        f"{response.rows[0].columns.keys()=}"
    )
    return response, data


def _check_rows(
    rows: list[dict[str, Any]],
    data: list[dict[str, Any]],
):
    assert len(rows) == len(data), f"Row count mismatch: {len(rows)=} != {len(data)=}"
    for row, d in zip(rows, data, strict=True):
        assert row["image"] is None or row["image"].endswith("/rabbit.jpeg"), row["image"]
        assert row["audio"] is None or row["audio"].endswith("/gutter.mp3"), row["audio"]
        assert row["document"] is None or row["document"].endswith(
            "/LLMs as Optimizers [DeepMind ; 2023].pdf"
        ), row["document"]
        for col in d:
            if col in ["ID", "Updated at"]:
                assert row[col] != d[col], f'Column "{col}" is not regenerated: {d[col]=}'
                continue
            if col in FILE_COLUMNS:
                continue
            if d[col] not in [None, ""] or col == "str":
                assert row[col] == d[col], f'Column "{col}" mismatch: {row[col]=} != {d[col]=}'
            else:
                assert row[col] is None, f'Column "{col}" mismatch: {row[col]=} != {d[col]=}'


def _check_knowledge_chat_data(
    table_type: TableType,
    rows: list[dict[str, Any]],
    data: Data,
):
    if table_type == TableType.KNOWLEDGE:
        _check_rows(rows, [data.knowledge_data] * len(data.data_list))
    elif table_type == TableType.CHAT:
        _check_rows(rows, [data.chat_data] * len(data.data_list))


def _check_columns(
    table_type: TableType,
    rows: list[dict[str, Any]],
):
    expected_cols = set(["ID", "Updated at"] + INPUT_COLUMNS + OUTPUT_COLUMNS)
    if table_type == TableType.ACTION:
        pass
    elif table_type == TableType.KNOWLEDGE:
        expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
    elif table_type == TableType.CHAT:
        expected_cols |= {"User", "AI"}
    else:
        raise ValueError(f"Invalid table type: {table_type}")
    assert all(isinstance(r, dict) for r in rows)
    assert all(set(r.keys()) == expected_cols for r in rows), [list(r.keys()) for r in rows]


def _get_exponent(x: float) -> int:
    return Decimal(str(x)).as_tuple().exponent


def _extract_number(text: str) -> int:
    match = re.search(r"\[(\d+)\]", text)
    return int(match.group(1)) if match else 0


def _assert_dict_equal(d1: dict[str, Any], d2: dict[str, Any], exclude: list[str] | None = None):
    if exclude is None:
        exclude = []
    d1 = {k: v for k, v in d1.items() if k not in exclude}
    d2 = {k: v for k, v in d2.items() if k not in exclude}
    assert d1 == d2


# TODO: Test add row with complete data including output columns


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_multi_image_input(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    """

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream (SSE) or not.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    image_uris = [
        upload_file(client, FILES["rabbit.jpeg"]).uri,
        upload_file(client, FILES["doe.jpg"]).uri,
    ]
    cols = [
        ColumnSchemaCreate(id="file", dtype="file"),  # Test `file` dtype compatibility
        ColumnSchemaCreate(id="image", dtype="image"),
        ColumnSchemaCreate(
            id="o1",
            dtype="str",
            gen_config=LLMGenConfig(model=setup.desc_llm_model_id),
        ),
        ColumnSchemaCreate(
            id="o2",
            dtype="str",
            gen_config=LLMGenConfig(model=setup.desc_llm_model_id, prompt="${image} ${o1}"),
        ),
    ]
    with create_table(client, table_type, cols=cols) as table:
        # Add rows
        data = [
            dict(file=image_uris[0], image=image_uris[1]),
            dict(file=image_uris[0], image=image_uris[1], o1="yeah"),
        ]
        response = add_table_rows(client, table_type, table.id, data, stream=stream)
        assert len(response.rows) == len(data)
        rows = {r.row_id: {k: v.content for k, v in r.columns.items()} for r in response.rows}
        for row in response.rows:
            o2 = row.columns["o2"].content
            assert "image with MIME type [image/jpeg], shape [(307, 205, 3)]" in o2
            if "o1" in row.columns:
                assert "text with [47] tokens" in o2
                o1 = row.columns["o1"].content
                assert "image with MIME type [image/jpeg], shape [(1200, 1600, 3)]" in o1
                assert "image with MIME type [image/jpeg], shape [(307, 205, 3)]" in o1
            else:
                assert "text with [1] tokens" in o2
        # List rows
        _rows = list_table_rows(client, table_type, table.id)
        assert len(_rows.items) == 2
        for row in _rows.values:
            assert row["file"] == image_uris[0]
            assert row["image"] == image_uris[1]
            assert row["o1"] == rows[row["ID"]].get("o1", "yeah")
            assert row["o2"] == rows[row["ID"]]["o2"]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_reasoning_model_and_agentic_tools(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    """
    Tests reasoning and non-reasoning models, with and without web search tool.

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream (SSE) or not.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="Question", dtype="str"),
        ColumnSchemaCreate(
            id="Reasoning Model",
            dtype="str",
            gen_config=LLMGenConfig(
                model=setup.gpt_llm_reasoning_config_id,
                prompt="${Question}",
                reasoning_effort="low",
            ),
        ),
        ColumnSchemaCreate(
            id="Reasoning Model with Agent Mode",
            dtype="str",
            gen_config=LLMGenConfig(
                model=setup.gpt_llm_reasoning_config_id,
                prompt="${Question}",
                tools=[WebSearchTool()],
                reasoning_effort="low",
            ),
        ),
        ColumnSchemaCreate(
            id="Chat Model",
            dtype="str",
            gen_config=LLMGenConfig(
                model=setup.gpt_llm_model_id,
                prompt="${Question}",
            ),
        ),
        ColumnSchemaCreate(
            id="Chat Model with Agent Mode",
            dtype="str",
            gen_config=LLMGenConfig(
                model=setup.gpt_llm_model_id,
                prompt="${Question}",
                tools=[WebSearchTool()],
            ),
        ),
    ]
    with create_table(client, table_type, cols=cols) as table:
        data = [dict(Question="What is the current US interest rate?")]
        response = add_table_rows(client, table_type, table.id, data, stream=stream)
        assert len(response.rows) == len(data)
        for row in response.rows:
            reasoning = row.columns["Reasoning Model"].reasoning_content
            assert "Searched the web for " not in reasoning
            assert len(reasoning) > 0
            answer = row.columns["Reasoning Model"].content.lower()
            assert len(answer) > 0
            assert "ERROR" not in answer

            reasoning = row.columns["Reasoning Model with Agent Mode"].reasoning_content
            assert "Searched the web for " in reasoning
            reasoning = reasoning.lower()
            assert len(reasoning) > 0
            answer = row.columns["Reasoning Model with Agent Mode"].content.lower()
            assert len(answer) > 0
            assert "ERROR" not in answer

            reasoning = row.columns["Chat Model"].reasoning_content
            assert reasoning is None or reasoning == ""
            answer = row.columns["Chat Model"].content.lower()
            assert len(answer) > 0
            assert "ERROR" not in answer

            reasoning = row.columns["Chat Model with Agent Mode"].reasoning_content
            assert "Searched the web for " in reasoning
            answer = row.columns["Chat Model with Agent Mode"].content.lower()
            assert len(answer) > 0
            assert "ERROR" not in answer
        # List rows
        _rows = list_table_rows(client, table_type, table.id)
        assert len(_rows.items) == 1


@pytest.mark.parametrize("table_type", [TableType.KNOWLEDGE])
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_knowledge_table_embedding(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    """
    Test Knowledge Table embeddings:
    - Missing Title, Text, or both
    - Embedding vector with invalid length

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream (SSE) or not.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type, cols=[]) as table:
        data = [
            # Complete
            dict(
                Title="Six-spot burnet",
                Text="The six-spot burnet is a moth of the family Zygaenidae.",
            ),
            # Missing Title
            dict(
                Text="A neural network is a model inspired by biological neural networks.",
            ),
            # Missing Text
            dict(
                Title="A supercomputer has a high level of performance.",
            ),
            # Missing both
            dict(),
        ]
        response = add_table_rows(client, table_type, table.id, data, stream=stream)
        # We currently dont return anything if LLM is not called
        assert len(response.rows) == 0 if stream else len(data)
        assert all(len(r.columns) == 0 for r in response.rows)
        rows = list_table_rows(client, table_type, table.id)
        assert rows.total == len(data)
        # Check embeddings
        for row in rows.values:
            assert_is_vector_or_none(row["Title Embed"], allow_none=False)
            assert_is_vector_or_none(row["Text Embed"], allow_none=False)
        # Check values
        row = rows.values[0]
        assert row["Title"] == data[0]["Title"], row
        assert row["Text"] == data[0]["Text"], row
        row = rows.values[1]
        assert row["Title"] is None, row
        assert row["Text"] == data[1]["Text"], row
        row = rows.values[2]
        assert row["Title"] == data[2]["Title"], row
        assert row["Text"] is None, row
        row = rows.values[3]
        assert row["Title"] is None, row
        assert row["Text"] is None, row
        # If embedding with invalid length is added, it will be coerced to None
        # Original vector will be saved into state
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [{"Title": "test", "Title Embed": [1, 2, 3]}],
            stream=stream,
        )
        # We currently dont return anything if LLM is not called
        assert len(response.rows) == 0 if stream else 1
        assert all(len(r.columns) == 0 for r in response.rows)
        # Check the vectors
        rows = list_table_rows(client, table_type, table.id)
        assert rows.total == 5
        row = rows.values[-1]
        assert row["Title"] == "test", f"{row['Title']=}"
        assert row["Title Embed"] is None, f"{row['Title Embed']=}"
        assert row["Text"] is None, f"{row['Title']=}"
        assert_is_vector_or_none(row["Text Embed"], allow_none=False)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_rag(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    """
    Test RAG:
    - Empty Knowledge Table
    - Text query
        - Single-turn and multi-turn
        - Add and regen
    - Text + Image query
        - Single-turn and multi-turn
        - Add and regen
    - Chat thread references
    - Inline citations

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream (SSE) or not.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(
        client, TableType.KNOWLEDGE, cols=[ColumnSchemaCreate(id="Species", dtype="str")]
    ) as kt:
        ### --- Perform RAG --- ###
        system_prompt = 'Reply "Unsure" if you don\'t know the answer. Do not guess. Be concise.'
        gen_config_kwargs = dict(
            model=setup.gpt_llm_model_id,
            system_prompt=system_prompt,
            prompt="${image}\n\nquestion: ${question}" if table_type == TableType.CHAT else "",
            max_tokens=50,
            temperature=0.001,
            top_p=0.001,
        )
        rag_kwargs = dict(
            table_id=kt.id,
            search_query="",  # Generate using LM
            k=2,
        )
        cols = [
            ColumnSchemaCreate(id="question", dtype="str"),
            ColumnSchemaCreate(id="image", dtype="image"),
            ColumnSchemaCreate(
                id="single",
                dtype="str",
                gen_config=LLMGenConfig(
                    multi_turn=False,
                    rag_params=RAGParams(reranking_model=None, **rag_kwargs),
                    **gen_config_kwargs,
                ),
            ),
            ColumnSchemaCreate(
                id="single-rerank",
                dtype="str",
                gen_config=LLMGenConfig(
                    multi_turn=False,
                    rag_params=RAGParams(reranking_model="", inline_citations=False, **rag_kwargs),
                    **gen_config_kwargs,
                ),
            ),
            ColumnSchemaCreate(
                id="multi",
                dtype="str",
                gen_config=LLMGenConfig(
                    multi_turn=True,
                    rag_params=RAGParams(
                        reranking_model=None, inline_citations=False, **rag_kwargs
                    ),
                    **gen_config_kwargs,
                ),
            ),
        ]

        def _check_references(ref: References | None):
            if ref is None:
                return
            _rows = list_table_rows(client, TableType.KNOWLEDGE, kt.id).values
            ref_document_ids = {d["File ID"] for d in _rows[:2]}
            document_ids = set(r.document_id for r in ref.chunks)
            assert document_ids == ref_document_ids
            ref_texts = {d["Text"] for d in _rows[:2]}
            texts = set(r.text for r in ref.chunks)
            assert len(texts) == min(len(_rows), rag_kwargs["k"])
            assert texts == ref_texts
            contexts = [r.context for r in ref.chunks]
            assert all("Species" in m for m in contexts)
            metas = [r.metadata for r in ref.chunks]
            assert all("rrf_score" in m for m in metas)

        def _check_row_references(references: list[dict[str, References]]):
            for ref in references:
                for r in ref.values():
                    _check_references(r)

        def _get_content(row: RowCompletionResponse, col: str) -> str:
            ref = row.columns[col].references
            assert isinstance(ref, References)
            _check_references(ref)
            return row.columns[col].content.lower().strip()

        ### --- RAG on empty Knowledge Table --- ###
        with create_table(client, table_type, cols=cols) as table:
            col_map = {col.id: col.gen_config for col in table.cols}
            # Assert that a default reranking model is set
            assert col_map["single-rerank"].rag_params.reranking_model == setup.rerank_model_id
            assert col_map["single"].rag_params.reranking_model is None
            assert col_map["multi"].rag_params.reranking_model is None
            # RAG
            data = [dict(question="What is the name of the rabbit?")]
            response = add_table_rows(client, table_type, table.id, data, stream=stream)
            assert len(response.rows) == len(data)
            # List rows (should have references)
            rows = list_table_rows(client, table_type, table.id)
            assert rows.total == len(data)
            assert len(rows.references) == len(data)
            _check_row_references(rows.references)

        ### --- Add data into Knowledge Table --- ###
        data = [
            # Context
            {
                "Title": "Animal",
                "Text": "Its name is Latte.",
                "Species": "rabbit",
                "File ID": "s3://animal-rabbit.jpeg",
            },
            {
                "Title": "Animal",
                "Text": "Its name is Bambi.",
                "Species": "doe",
                "File ID": "s3://animal-doe.jpeg",
            },
            # Distractor
            {
                "Title": "Country",
                "Text": "Kuala Lumpur is the capital of Malaysia.",
                "File ID": "s3://country-kuala-lumpur.pdf",
            },
        ]
        response = add_table_rows(client, TableType.KNOWLEDGE, kt.id, data, stream=False)
        assert len(response.rows) == len(data)
        kt_rows = list_table_rows(client, TableType.KNOWLEDGE, kt.id)
        assert kt_rows.total == len(data)

        ### Text query
        with create_table(client, table_type, cols=cols) as table:
            col_map = {col.id: col.gen_config for col in table.cols}
            # Assert that a default reranking model is set
            assert col_map["single-rerank"].rag_params.reranking_model == setup.rerank_model_id
            assert col_map["single"].rag_params.reranking_model is None
            assert col_map["multi"].rag_params.reranking_model is None
            # RAG
            data = [
                dict(question="What is the name of the rabbit?"),  # Latte
                dict(question="What is its name again?"),  # Unsure (single), Latte (multi)
            ]
            response = add_table_rows(client, table_type, table.id, data, stream=stream)
            assert len(response.rows) == len(data)
            # List rows (should have references)
            rows = list_table_rows(client, table_type, table.id)
            assert rows.total == len(data)
            assert len(rows.references) == len(data)
            _check_row_references(rows.references)
            # Check answers
            single = _get_content(response.rows[0], "single")
            assert "latte" in single
            assert len(re.findall(CITATION_PATTERN, single)) > 0
            assert "latte" in _get_content(response.rows[0], "single-rerank")
            assert "latte" in _get_content(response.rows[0], "multi")
            # "Unsure" tests are fragile
            # assert "unsure" in _get_content(response.rows[1], "single")
            # assert "unsure" in _get_content(response.rows[1], "single-rerank")
            assert len(_get_content(response.rows[1], "single")) > 0
            assert len(_get_content(response.rows[1], "single-rerank")) > 0
            assert "latte" in _get_content(response.rows[1], "multi")
            ### Update and regen
            # Update question
            row_ids = [r["ID"] for r in rows.items]
            response = client.table.update_table_rows(
                table_type,
                MultiRowUpdateRequest(
                    table_id=table.id,
                    data={row_ids[0]: dict(question="What is the name of the deer?")},  # Bambi
                ),
            )
            assert isinstance(response, OkResponse)
            response = regen_table_rows(client, table_type, table.id, row_ids, stream=stream)
            assert len(response.rows) == len(data)
            # Check answers
            single = _get_content(response.rows[0], "single")
            assert "bambi" in single
            assert len(re.findall(CITATION_PATTERN, single)) > 0
            assert "bambi" in _get_content(response.rows[0], "single-rerank")
            assert "bambi" in _get_content(response.rows[0], "multi")
            assert len(_get_content(response.rows[1], "single")) > 0
            assert len(_get_content(response.rows[1], "single-rerank")) > 0
            assert "bambi" in _get_content(response.rows[1], "multi")

        ### Text + Image query
        image_uri = upload_file(client, FILES["rabbit.jpeg"]).uri
        with create_table(client, table_type, cols=cols) as table:
            col_map = {col.id: col.gen_config for col in table.cols}
            # Assert that a default reranking model is set
            assert col_map["single-rerank"].rag_params.reranking_model == setup.rerank_model_id
            assert col_map["single"].rag_params.reranking_model is None
            assert col_map["multi"].rag_params.reranking_model is None
            # RAG
            data = [
                # Latte
                dict(question="What is the name of the animal?", image=image_uri, User="lala"),
                # Unsure (single), Latte (multi)
                dict(question="What is its name again?", User="lala"),
            ]
            response = add_table_rows(client, table_type, table.id, data, stream=stream)
            assert len(response.rows) == len(data)
            # List rows (should have references)
            rows = list_table_rows(client, table_type, table.id)
            assert rows.total == len(data)
            assert len(rows.references) == len(data)
            _check_row_references(rows.references)
            assert "latte" in _get_content(response.rows[0], "single")
            assert "latte" in _get_content(response.rows[0], "single-rerank")
            assert "latte" in _get_content(response.rows[0], "multi")
            # "Unsure" tests are fragile
            # assert "unsure" in _get_content(response.rows[1], "single")
            # assert "unsure" in _get_content(response.rows[1], "single-rerank")
            assert len(_get_content(response.rows[1], "single")) > 0
            assert len(_get_content(response.rows[1], "single-rerank")) > 0
            assert "latte" in _get_content(response.rows[1], "multi")
            ### Update and regen
            # Update KT
            kt_row_ids = [r["ID"] for r in kt_rows.items]
            response = client.table.update_table_rows(
                TableType.KNOWLEDGE,
                MultiRowUpdateRequest(
                    table_id=kt.id,
                    data={kt_row_ids[1]: dict(Text="Its name is Daisy")},
                ),
            )
            assert isinstance(response, OkResponse)
            # Update image
            row_ids = [r["ID"] for r in rows.items]
            image_uri = upload_file(client, FILES["doe.jpg"]).uri
            response = client.table.update_table_rows(
                table_type,
                MultiRowUpdateRequest(
                    table_id=table.id,
                    # Daisy
                    data={row_ids[0]: dict(image=image_uri)},
                ),
            )
            assert isinstance(response, OkResponse)
            response = regen_table_rows(client, table_type, table.id, row_ids, stream=stream)
            assert len(response.rows) == len(data)
            # Check answers
            assert "daisy" in _get_content(response.rows[0], "single")
            assert "daisy" in _get_content(response.rows[0], "single-rerank")
            assert "daisy" in _get_content(response.rows[0], "multi")
            assert len(_get_content(response.rows[1], "single")) > 0
            assert len(_get_content(response.rows[1], "single-rerank")) > 0
            assert "daisy" in _get_content(response.rows[1], "multi")

            ### Chat thread references
            col = "multi"
            response = client.table.get_conversation_threads(table_type, table.id)
            assert col in response.threads
            assert response.table_id == table.id
            thread = response.threads[col].thread
            assert response.threads[col].column_id == col
            for message in thread:
                if message.role == "assistant":
                    assert isinstance(message.references, References)
                    assert len(message.references.chunks) == rag_kwargs["k"]
                    _check_references(message.references)
                    assert isinstance(message.row_id, str)
                    assert len(message.row_id) > 0
                elif message.role == "user":
                    assert isinstance(message.row_id, str)
                    assert len(message.row_id) > 0
                    assert message.user_prompt is None
                else:
                    assert isinstance(message.content, str)
                    assert message.row_id is None
            message = thread[1]
            assert message.role == "user"
            assert isinstance(message.content, list)
            assert len(message.content) == 2
            assert isinstance(message.content[0], S3Content)
            assert message.content[0].uri == image_uri
            assert isinstance(message.content[1], TextContent)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_column_dependency(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    """
    Test column dependency graph.
    - Add and regen rows
    - No dependency (single-turn, multi-turn)
    - Single dependency (single-turn, multi-turn)
    - Chain dependency
    - Fan-in (with and without chain) and fan-out dependencies
    - Multi-single-multi
    - Gen config partial update

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream (SSE) or not.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    gen_config_kwargs = dict(model=setup.echo_model_id, system_prompt="^")
    cols = [
        ColumnSchemaCreate(id="c0", dtype="str"),
        # ["s1", "m1", "s2", "s3", "m2", "s4", "s5", "s6", "s7", "m3", "s8", "m4"]
        # Single dependency (single-turn)
        ColumnSchemaCreate(
            id="s1",
            dtype="str",
            gen_config=LLMGenConfig(prompt="s1 ${c0}", **gen_config_kwargs),
        ),
        # Single dependency (multi-turn)
        ColumnSchemaCreate(
            id="m1",
            dtype="str",
            gen_config=LLMGenConfig(prompt="m1 ${c0}", multi_turn=True, **gen_config_kwargs),
        ),
        # Chain dependency
        ColumnSchemaCreate(
            id="s2",
            dtype="str",
            gen_config=LLMGenConfig(prompt="s2 ${s1}", **gen_config_kwargs),
        ),
        # No dependency (single-turn)
        ColumnSchemaCreate(
            id="s3",
            dtype="str",
            gen_config=LLMGenConfig(prompt="s3", **gen_config_kwargs),
        ),
        # No dependency (multi-turn)
        ColumnSchemaCreate(
            id="m2",
            dtype="str",
            gen_config=LLMGenConfig(prompt="m2", multi_turn=True, **gen_config_kwargs),
        ),
        # Fan-out after chain dependency
        ColumnSchemaCreate(
            id="s4",
            dtype="str",
            gen_config=LLMGenConfig(prompt="s4 ${s2}", **gen_config_kwargs),
        ),
        ColumnSchemaCreate(
            id="s5",
            dtype="str",
            gen_config=LLMGenConfig(prompt="s5 ${s2}", **gen_config_kwargs),
        ),
        ColumnSchemaCreate(
            id="s6",
            dtype="str",
            gen_config=LLMGenConfig(prompt="s6 ${s5}", **gen_config_kwargs),
        ),
        # Fan-in (single-turn)
        ColumnSchemaCreate(
            id="s7",
            dtype="str",
            gen_config=LLMGenConfig(prompt="s7 ${s4} ${s6}", **gen_config_kwargs),
        ),
        # Fan-in (multi-turn)
        ColumnSchemaCreate(
            id="m3",
            dtype="str",
            gen_config=LLMGenConfig(prompt="m3 ${s4} ${s6}", multi_turn=True, **gen_config_kwargs),
        ),
        # Single dependency (single-turn after multi-turn)
        ColumnSchemaCreate(
            id="s8",
            dtype="str",
            gen_config=LLMGenConfig(prompt="s8 ${m3}", **gen_config_kwargs),
        ),
        # Multi-single-multi
        ColumnSchemaCreate(
            id="m4",
            dtype="str",
            gen_config=LLMGenConfig(prompt="m4 ${s8}", multi_turn=True, **gen_config_kwargs),
        ),
    ]

    def _content(row: RowCompletionResponse, col: str) -> str | None:
        return getattr(row.columns.get(col, None), "content", "").strip()

    def _check(rows: list[RowCompletionResponse], base: str, exc: list[str] = None):
        if exc is None:
            exc = []
        # Check single-turn
        for i, row in enumerate(rows):
            assert "s1" in exc or _content(row, "s1") == f"^ s1 {base}{i}"
            assert "s2" in exc or _content(row, "s2") == f"^ s2 {_content(row, 's1')}"
            assert "s3" in exc or _content(row, "s3") == "^ s3"
            assert "s4" in exc or _content(row, "s4") == f"^ s4 {_content(row, 's2')}"
            assert "s5" in exc or _content(row, "s5") == f"^ s5 {_content(row, 's2')}"
            assert "s6" in exc or _content(row, "s6") == f"^ s6 {_content(row, 's5')}"
            assert "s7" in exc or _content(row, "s7") == f'^ s7 {_content(row, "s4")} {_content(row, "s6")}'  # fmt:off
        # Check multi-turn
        gt = dict(
            m1=[
                f"^ m1 {base}0",
                f"^ m1 {base}0 m1 {base}1",
            ],
            m2=[
                "^ m2",
                "^ m2 m2",
            ],
            m3=[
                f"^ m3 {_content(rows[0], 's4')} {_content(rows[0], 's6')}",
                f"^ m3 {_content(rows[0], 's4')} {_content(rows[0], 's6')} m3 {_content(rows[1], 's4')} {_content(rows[1], 's6')}",
            ],
            s8=[
                f"^ s8 {_content(rows[0], 'm3')}",
                f"^ s8 {_content(rows[1], 'm3')}",
            ],
            m4=[
                f"^ m4 {_content(rows[0], 's8')}",
                f"^ m4 {_content(rows[0], 's8')} m4 {_content(rows[1], 's8')}",
            ],
        )
        for i, row in enumerate(response.rows):
            assert "m1" in exc or _content(row, "m1") == gt["m1"][i]
            assert "m2" in exc or _content(row, "m2") == gt["m2"][i]
            assert "m4" in exc or _content(row, "m3") == gt["m3"][i]
            assert "s8" in exc or _content(row, "s8") == gt["s8"][i]
            assert "m4" in exc or _content(row, "m4") == gt["m4"][i]

    with create_table(client, table_type, cols=cols) as table:
        ### --- Add rows --- ###
        data = [dict(c0="r0"), dict(c0="r1")]
        response = add_table_rows(client, table_type, table.id, data, stream=stream)
        assert len(response.rows) == len(data)
        _check(response.rows, "r")
        ### --- Regen rows --- ###
        row_ids = [r.row_id for r in response.rows]
        # Regen all
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={row.row_id: dict(c0=f"z{i}") for i, row in enumerate(response.rows)},
            ),
        )
        response = regen_table_rows(
            client,
            table_type,
            table.id,
            row_ids,
            stream=stream,
            regen_strategy=RegenStrategy.RUN_ALL,
        )
        assert len(response.rows) == len(data)
        _check(response.rows, "z")
        # Regen before
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={row.row_id: dict(c0=f"aa{i}") for i, row in enumerate(response.rows)},
            ),
        )
        response = regen_table_rows(
            client,
            table_type,
            table.id,
            row_ids,
            stream=stream,
            regen_strategy=RegenStrategy.RUN_BEFORE,
            output_column_id="m3",
        )
        assert len(response.rows) == len(data)
        # _check(response.rows, "z", ["s1", "m1", "s2", "s3", "m2", "s4", "s5", "s6", "s7", "m3"])
        _check(response.rows, "aa", ["s8", "m4"])
        # Regen after
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={row.row_id: dict(c0=f"bb{i}") for i, row in enumerate(response.rows)},
            ),
        )
        response = regen_table_rows(
            client,
            table_type,
            table.id,
            row_ids,
            stream=stream,
            regen_strategy=RegenStrategy.RUN_AFTER,
            output_column_id="s2",
        )
        assert len(response.rows) == len(data)
        assert _content(response.rows[0], "s2") == "^ s2 ^ s1 aa0"  # Still "aa"
        assert _content(response.rows[1], "s2") == "^ s2 ^ s1 aa1"  # Still "aa"
        _check(response.rows, "aa", ["s1", "m1", "s2"])  # Still "aa"
        response = regen_table_rows(
            client,
            table_type,
            table.id,
            row_ids,
            stream=stream,
            regen_strategy=RegenStrategy.RUN_AFTER,
            output_column_id="s1",
        )
        assert len(response.rows) == len(data)
        _check(response.rows, "bb")
        # Regen selected
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={row.row_id: dict(c0=f"cc{i}") for i, row in enumerate(response.rows)},
            ),
        )
        response = regen_table_rows(
            client,
            table_type,
            table.id,
            row_ids,
            stream=stream,
            regen_strategy=RegenStrategy.RUN_SELECTED,
            output_column_id="m1",
        )
        assert len(response.rows) == len(data)
        # _check(response.rows, "bb", ["m1"])
        assert _content(response.rows[0], "m1") == "^ m1 cc0"
        assert _content(response.rows[1], "m1") == "^ m1 cc0 m1 cc1"
        # Update gen config and regen
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id, column_map=dict(s8=LLMGenConfig(prompt="s8 ${m2}"))
            ),
        )
        gen_configs = {c.id: c.gen_config for c in table.cols}
        assert gen_configs["s8"].system_prompt == "^"
        assert gen_configs["s8"].prompt == "s8 ${m2}"
        response = regen_table_rows(
            client,
            table_type,
            table.id,
            row_ids,
            stream=stream,
            regen_strategy=RegenStrategy.RUN_AFTER,
            output_column_id="s8",
        )
        assert _content(response.rows[0], "m4") == "^ m4 ^ s8 ^ m2"
        assert _content(response.rows[1], "m4") == "^ m4 ^ s8 ^ m2 m4 ^ s8 ^ m2 m2"


@pytest.mark.parametrize(
    "python_code",
    [
        {
            "input": "Hello, World!",
            "code": "row['result_column']=row['input']",
            "expected": "Hello, World!",
        },
        {
            "input": "2",
            "code": "row['result_column'] = int(row['input']) + int(row['input'])",
            "expected": "4",
        },
        # Test error handling:
        {
            "input": "DUMMY",
            "code": "row['result_column']=row['undefined']",
            "expected": "KeyError: 'undefined'",
        },
    ],
)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
async def test_python_fixed_function_str(
    setup: ServingContext,
    stream: bool,
    python_code: dict,
):
    table_type = TableType.ACTION
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input", dtype="str"),
        ColumnSchemaCreate(
            id="result_column",
            dtype="str",
            gen_config=PythonGenConfig(python_code=python_code["code"]),
        ),
    ]
    with create_table(client, table_type, cols=cols) as table:
        data = [{"input": python_code["input"]}]
        # Add rows
        response = add_table_rows(
            client, table_type, table.id, data, stream=stream, check_usage=False
        )
        assert len(response.rows) == len(data)
        rows = list_table_rows(client, table_type, table.id)
        row_ids = [r.row_id for r in response.rows]
        assert rows.total == len(data)
        assert rows.values[0]["result_column"] == python_code["expected"]
        # Regen rows
        response = regen_table_rows(
            client, table_type, table.id, row_ids, stream=stream, check_usage=False
        )
        assert len(response.rows) == len(data)
        rows = list_table_rows(client, table_type, table.id)
        assert rows.total == len(data)
        assert rows.values[0]["result_column"] == python_code["expected"]


def _read_file_content(file_path):
    with open(file_path, "rb") as f:
        return f.read()


@pytest.mark.parametrize(
    "image_path",
    [
        FILES["cifar10-deer.jpg"],
        FILES["rabbit.png"],
        FILES["rabbit_cifar10-deer.gif"],
        FILES["rabbit_cifar10-deer.webp"],
    ],
    ids=lambda x: basename(x),
)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
async def test_python_fixed_function_image(
    setup: ServingContext,
    stream: bool,
    image_path: str,
):
    table_type = TableType.ACTION
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="source_image", dtype="image"),
        ColumnSchemaCreate(
            id="result_column",
            dtype="image",
            gen_config=PythonGenConfig(python_code="row['result_column']=row['source_image']"),
        ),
    ]

    with create_table(client, table_type, cols=cols) as table:
        image_uri = upload_file(client, image_path).uri
        data = [{"source_image": image_uri}]
        # Add rows
        response = add_table_rows(
            client, table_type, table.id, data, stream=stream, check_usage=False
        )
        assert len(response.rows) == len(data)
        rows = list_table_rows(client, table_type, table.id)
        row_ids = [r.row_id for r in response.rows]
        assert rows.total == len(data)
        file_uri = rows.values[0]["result_column"]
        assert file_uri.startswith(("file://", "s3://"))
        response = client.file.get_raw_urls([file_uri])
        assert isinstance(response, GetURLResponse)
        # Compare the contents
        downloaded_content = httpx.get(response.urls[0]).content
        original_content = _read_file_content(image_path)
        assert original_content == downloaded_content, f"Content mismatch for file: {image_path}"
        # Regen rows
        response = regen_table_rows(
            client, table_type, table.id, row_ids, stream=stream, check_usage=False
        )
        assert len(response.rows) == len(data)
        rows = list_table_rows(client, table_type, table.id)
        assert rows.total == len(data)
        file_uri = rows.values[0]["result_column"]
        assert file_uri.startswith(("file://", "s3://"))
        response = client.file.get_raw_urls([file_uri])
        assert isinstance(response, GetURLResponse)
        # Compare the contents
        downloaded_content = httpx.get(response.urls[0]).content
        original_content = _read_file_content(image_path)
        assert original_content == downloaded_content, f"Content mismatch for file: {image_path}"


def _assert_context_error(content: str) -> None:
    assert "maximum context length is 10 tokens" in content
    assert content.startswith("[ERROR]")


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_error_cases(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    """
    Test error cases.
    - Row add & regen: Downstream columns exceed context length
    - Row add & regen: All columns exceed context length
    - Error circuit breaker
    - Non-existent output column during regen

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream (SSE) or not.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    max_tokens = 8
    num_output_cols = 2
    cols = [ColumnSchemaCreate(id="c0", dtype="str")]
    cols += [
        ColumnSchemaCreate(
            id=f"c{i + 1}",
            dtype="str",
            gen_config=LLMGenConfig(
                model=setup.short_llm_model_id,
                system_prompt=".",
                prompt=f"${{c{i}}}",
                max_tokens=max_tokens,
            ),
        )
        for i in range(num_output_cols)
    ]
    with create_table(client, table_type, cols=cols) as table:
        ### --- Context length --- ###
        ### Downstream exceed context length
        # Row add
        data = [dict(c0="0"), dict(c0="1")]
        response = add_table_rows(client, table_type, table.id, data, stream=stream)
        assert len(response.rows) == len(data)
        for row in response.rows:
            assert "Lorem ipsum dolor sit amet" in row.columns["c1"].content
            _assert_context_error(row.columns["c2"].content)
        # Row regen
        response = regen_table_rows(
            client,
            table_type,
            table.id,
            [r.row_id for r in response.rows],
            stream=stream,
            regen_strategy=RegenStrategy.RUN_ALL,
        )
        for row in response.rows:
            assert "Lorem ipsum dolor sit amet" in row.columns["c1"].content
            _assert_context_error(row.columns["c2"].content)
        ### All exceed context length
        # Row add
        data = [dict(c0="0 0"), dict(c0="1 1")]
        response = add_table_rows(client, table_type, table.id, data, stream=stream)
        assert len(response.rows) == len(data)
        for row in response.rows:
            _assert_context_error(row.columns["c1"].content)
            assert "Upstream columns errored out" in row.columns["c2"].content
        # Row regen
        response = regen_table_rows(
            client,
            table_type,
            table.id,
            [r.row_id for r in response.rows],
            stream=stream,
            regen_strategy=RegenStrategy.RUN_ALL,
        )
        for row in response.rows:
            _assert_context_error(row.columns["c1"].content)
            assert "Upstream columns errored out" in row.columns["c2"].content

        ### --- Regen rows with invalid column --- ###
        row_ids = [r.row_id for r in response.rows]
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map={
                    f"c{i + 1}": LLMGenConfig(max_tokens=2) for i in range(num_output_cols)
                },
            ),
        )
        strategies = [
            RegenStrategy.RUN_ALL,
            RegenStrategy.RUN_BEFORE,
            RegenStrategy.RUN_AFTER,
            RegenStrategy.RUN_SELECTED,
        ]
        for strategy in strategies:
            with pytest.raises(ResourceNotFoundError):
                regen_table_rows(
                    client,
                    table_type,
                    table.id,
                    row_ids,
                    stream=stream,
                    regen_strategy=strategy,
                    output_column_id="x",
                )


def _assert_consecutive(lst: list) -> bool:
    """
    Assert that identical elements occur consecutively in the list.

    Args:
        lst: List of strings

    Raises:
        AssertionError: If identical elements are not grouped together
    """
    if not lst:
        raise AssertionError("List is empty")
    seen = {lst[0]}
    current_element = lst[0]
    for element in lst[1:]:
        if element != current_element:
            # We're starting a new group
            if element in seen:
                return False
            seen.add(element)
            current_element = element
    return True


@flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_concurrency_stream(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    max_tokens = 10
    num_output_cols = 3
    num_rows = 2
    cols = [ColumnSchemaCreate(id="str", dtype="str")]
    cols += [
        ColumnSchemaCreate(
            id=f"o{i + 1}",
            dtype="str",
            gen_config=LLMGenConfig(
                model=setup.lorem_llm_model_id,
                system_prompt="",
                prompt="",
                max_tokens=max_tokens,
            ),
        )
        for i in range(num_output_cols)
    ]
    with create_table(client, table_type, cols=cols) as table:
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
                table_id=table.id,
                data=[dict(str="Lorem ipsum dolor sit amet")] * num_rows,
                stream=True,
            ),
        )
        chunks = [r for r in response if isinstance(r, CellCompletionResponse)]
        ### --- Column concurrency --- ###
        # Assert that all columns are concurrently generated
        rows: dict[str, list[CellCompletionResponse]] = defaultdict(list)
        for c in chunks:
            rows[c.row_id].append(c)
        for row in rows.values():
            chunk_cols = [r.output_column_name for r in row]
            assert len(chunk_cols) > num_output_cols * num_rows
            _cols = set(chunk_cols[: len(chunk_cols) // 2])
            assert len(_cols) >= 1
            assert not _assert_consecutive(chunk_cols)
        ### --- Row concurrency --- ###
        row_ids = list(rows.keys())
        chunk_rows = [c.row_id for c in chunks]
        # print(f"{[row_ids.index(c.row_id) for c in chunks]=}")
        multiturn_cols = [c for c in table.cols if getattr(c.gen_config, "multi_turn", False)]
        if len(multiturn_cols) > 0:
            # Tables with multi-turn column must have its rows are sequentially generated
            for i, row_id in enumerate(row_ids):
                chunks_per_row = len(chunk_rows) // len(row_ids)
                _chunks = chunk_rows[i * chunks_per_row : (i + 1) * chunks_per_row]
                assert row_id in _chunks
            assert _assert_consecutive(chunk_rows)
        else:
            # Tables without must have its rows concurrently generated
            _rows = set(chunk_rows[: len(chunk_rows) // num_rows])
            assert len(_rows) == num_rows
            for row_id in row_ids:
                assert row_id in _rows
            assert not _assert_consecutive(chunk_rows)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_multimodal_multiturn(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    """
    Tests multimodal multiturn generation.
    - Ensure files are fetched/interpolated from the correct row in a multiturn setting
    - Ensure files in history are updated after an earlier row is updated
    - Add and regen row

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream (SSE) or not.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="str", dtype="str"),
        ColumnSchemaCreate(id="image", dtype="image"),
        ColumnSchemaCreate(id="audio", dtype="audio"),
        ColumnSchemaCreate(id="document", dtype="document"),
        ColumnSchemaCreate(
            id="chat",
            dtype="str",
            gen_config=LLMGenConfig(
                model=setup.desc_llm_model_id,
                system_prompt="",
                prompt="${str} ${image} ${audio} ${document}",
                max_tokens=20,
                multi_turn=True,
            ),
        ),
    ]
    with (
        TemporaryDirectory() as tmp_dir,
        create_table(client, table_type, cols=cols) as table,
    ):
        text_fp = join(tmp_dir, "test.txt")
        with open(text_fp, "w") as f:
            f.write("Two tokens")
        doc_uri = upload_file(client, text_fp).uri
        image_uri = upload_file(client, FILES["rabbit.jpeg"]).uri
        audio_uri = upload_file(client, FILES["gutter.mp3"]).uri
        ### --- Add rows --- ###
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [
                dict(str="one", image=image_uri, audio=audio_uri, document=doc_uri),
                dict(str="one", image=image_uri, audio=audio_uri, document=doc_uri),
            ],
            stream=stream,
        )
        # Check returned chunks / response
        for row in response.rows:
            chat = row.columns["chat"].content
            # print(chat)
            chat_contents = chat.split("\n")
            assert "System prompt:" in chat_contents[0]
            assert _extract_number(chat_contents[0]) > 10
            assert "[image/jpeg], shape [(1200, 1600, 3)]" in chat
            assert "[image/jpeg], shape [(32, 32, 3)]" not in chat
            assert "[audio/mpeg]" in chat
            assert "text with [5] tokens" in chat
        assert len(response.rows) == 2
        chat = response.rows[0].columns["chat"].content
        chat_contents = chat.split("\n")
        assert len(chat.split("\n")) == 4
        chat = response.rows[1].columns["chat"].content
        chat_contents = chat.split("\n")
        assert len(chat.split("\n")) == 7
        # Update image in first row
        image_uri = upload_file(client, FILES["cifar10-deer.jpg"]).uri
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={response.rows[0].row_id: dict(image=image_uri)},
            ),
        )
        # Add a row
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [dict(str="one")],
            stream=stream,
        )
        assert len(response.rows) == 1
        chat = response.rows[0].columns["chat"].content
        # print(chat)
        assert "[image/jpeg], shape [(1200, 1600, 3)]" in chat
        assert "[image/jpeg], shape [(32, 32, 3)]" in chat  # Updated image
        assert "[audio/mpeg]" in chat
        assert "text with [5] tokens" in chat
        assert "text with [1] tokens" in chat
        ### --- Regen row --- ###
        row = response.rows[0]
        response = regen_table_rows(client, table_type, table.id, [row.row_id], stream=stream)
        assert len(response.rows) == 1
        chat = response.rows[0].columns["chat"].content
        assert "[image/jpeg], shape [(1200, 1600, 3)]" in chat
        assert "[image/jpeg], shape [(32, 32, 3)]" in chat  # Updated image
        assert "[audio/mpeg]" in chat
        assert "text with [5] tokens" in chat
        assert "text with [1] tokens" in chat


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_add_get_list_rows(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    """
    Test adding a row to a table.
    - All column dtypes
    - Various languages

    Test get row and list rows from a table.
    - offset and limit
    - order_by and order_ascending
    - where
    - search_query and search_columns
    - column subset
    - float & vector precision
    - vector column exclusion

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream (SSE) or not.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    cols = [ColumnSchemaCreate(id=c, dtype=c) for c in INPUT_COLUMNS]
    cols += [
        ColumnSchemaCreate(
            id=c,
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                system_prompt="",
                prompt="",
                max_tokens=10,
            ),
        )
        for c in OUTPUT_COLUMNS
    ]
    with create_table(client, table_type, cols=cols) as table:
        ### --- Add row with all dtypes --- ###
        _, data = _add_row_default_data(
            setup,
            client,
            table_type=table_type,
            table_name=table.id,
            stream=stream,
        )
        num_data = len(data.data_list)
        return

        ### --- List rows --- ###
        rows = list_table_rows(client, table_type, table.id)
        # Check row count
        assert len(rows.items) == len(data.data_list), (
            f"Row count mismatch: {len(rows.items)=} != {num_data=}"
        )
        assert rows.total == len(data.data_list), (
            f"Row count mismatch: {rows.total=} != {num_data=}"
        )
        # Check row data
        _check_rows(rows.values, data.action_data_list)
        _check_knowledge_chat_data(table_type, rows.values, data)
        # Check output columns
        for row in rows.values:
            for c in OUTPUT_COLUMNS:
                summary = row[c]
                assert "There is a text" in summary, summary
                if row["image"]:
                    assert "There is an image with MIME type [image/jpeg]" in summary, summary
                if row["audio"]:
                    assert "There is an audio with MIME type [audio/mpeg]" in summary, summary
        # Check columns
        _check_columns(table_type, rows.items)

        ### --- Get row --- ###
        for row in rows.items:
            _row = get_table_row(client, table_type, table.id, row["ID"])
            assert _row == row, f'Row "{row["ID"]}" mismatch: {_row=} != {row=}'

        ### --- List rows (offset and limit) --- ###
        _rows = list_table_rows(client, table_type, table.id, offset=0, limit=1)
        assert len(_rows.items) == 1
        assert _rows.total == num_data
        assert _rows.items[0]["ID"] == rows.items[0]["ID"], f"{_rows.items=}"
        _rows = list_table_rows(client, table_type, table.id, offset=1, limit=1)
        assert len(_rows.items) == 1
        assert _rows.total == num_data
        assert _rows.items[0]["ID"] == rows.items[1]["ID"], f"{_rows.items=}"
        # Offset >= num rows
        _rows = list_table_rows(client, table_type, table.id, offset=num_data, limit=1)
        assert len(_rows.items) == 0
        assert _rows.total == num_data
        _rows = list_table_rows(client, table_type, table.id, offset=num_data + 1, limit=1)
        assert len(_rows.items) == 0
        assert _rows.total == num_data
        # Invalid offset and limit
        with pytest.raises(BadInputError):
            list_table_rows(client, table_type, table.id, offset=0, limit=0)
        with pytest.raises(BadInputError):
            list_table_rows(client, table_type, table.id, offset=-1, limit=1)

        ### --- List rows (order_by and order_ascending) --- ###
        _rows = list_table_rows(client, table_type, table.id, order_ascending=False)
        assert len(_rows.items) == num_data
        assert _rows.total == num_data
        assert _rows.items[::-1] == rows.items
        _rows = list_table_rows(client, table_type, table.id, order_by="str")
        assert len(_rows.items) == num_data
        assert _rows.total == num_data
        assert _rows.items[::-1] == rows.items

        ### --- List rows (where) --- ###
        _rows = list_table_rows(client, table_type, table.id, search_query="Arri")
        assert len(_rows.items) == 3
        assert _rows.total == 3
        assert _rows.total != num_data
        _id = rows.items[0]["ID"]
        _rows = list_table_rows(
            client, table_type, table.id, search_query="Arri", where=f""""ID" > '{_id}'"""
        )
        assert len(_rows.items) == 2
        assert _rows.total == 2
        _rows = list_table_rows(client, table_type, table.id, where=f""""ID" = '{_id}'""")
        assert len(_rows.items) == 1
        assert _rows.total == 1

        ### --- List rows (search_query and search_columns) --- ###
        _rows = list_table_rows(client, table_type, table.id, search_query="Arri")
        assert len(_rows.items) == 3
        assert _rows.total == 3
        assert _rows.total != num_data
        _rows = list_table_rows(client, table_type, table.id, search_query="Arri", offset=1)
        assert len(_rows.items) == 2
        assert _rows.total == 3
        assert _rows.total != num_data
        _rows = list_table_rows(
            client, table_type, table.id, search_query="Arri", search_columns=["str"]
        )
        assert len(_rows.items) == 3
        assert _rows.total == 3
        assert _rows.total != num_data
        _rows = list_table_rows(
            client, table_type, table.id, search_query="Arri", search_columns=OUTPUT_COLUMNS
        )
        assert len(_rows.items) == 0
        assert _rows.total == 0

        ### --- Get & List rows (column subset) --- ###
        _rows = list_table_rows(client, table_type, table.id, limit=2, columns=["str", "bool"])
        expected_columns = {"ID", "Updated at", "str", "bool"}
        for row in _rows.items:
            cols = set(row.keys())
            assert cols == expected_columns, (
                f"Column order mismatch: {cols=} != {expected_columns=}"
            )
            _row = get_table_row(client, table_type, table.id, row["ID"], columns=["str", "bool"])
            assert _row == row, f'Row "{row["ID"]}" mismatch: {_row=} != {row=}'
            assert "value" in row["bool"], _row
            assert "value" in _row["bool"], _row

        ### --- Get & List rows (float & vector precision) --- ###
        # Round to 1 decimal
        _rows = list_table_rows(
            client, table_type, table.id, limit=2, float_decimals=1, vec_decimals=1
        )
        for row in _rows.items:
            exponent = _get_exponent(row["float"]["value"])
            assert exponent >= -1, exponent
            if table_type == TableType.KNOWLEDGE:
                for col in ["Title Embed", "Text Embed"]:
                    exponents = [_get_exponent(v) for v in row[col]["value"]]
                    assert all(e >= -1 for e in exponents), exponents
            _row = get_table_row(
                client, table_type, table.id, row["ID"], float_decimals=1, vec_decimals=1
            )
            assert _row == row, f'Row "{row["ID"]}" mismatch: {_row=} != {row=}'
        # No vector columns
        _rows = list_table_rows(
            client, table_type, table.id, limit=2, float_decimals=1, vec_decimals=-1
        )
        for row in _rows.items:
            exponent = _get_exponent(row["float"]["value"])
            assert exponent >= -1, exponent
            assert "Title Embed" not in row
            assert "Text Embed" not in row
            _row = get_table_row(
                client, table_type, table.id, row["ID"], float_decimals=1, vec_decimals=-1
            )
            assert _row == row, f'Row "{row["ID"]}" mismatch: {_row=} != {row=}'


def test_list_rows_case_insensitive_sort(setup: ServingContext):
    table_type = TableType.ACTION
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    cols = [ColumnSchemaCreate(id="str", dtype="str")]
    with create_table(client, table_type, cols=cols) as table:
        add_table_rows(
            client,
            table_type,
            table.id,
            [dict(str="a"), dict(str="B"), dict(str="C"), dict(str="d")][::-1],
            stream=False,
        )
        ### --- List rows --- ###
        rows = list_table_rows(client, table_type, table.id)
        assert [r["str"] for r in rows.values] == ["a", "B", "C", "d"][::-1]
        rows = list_table_rows(client, table_type, table.id, order_by="str")
        assert [r["str"] for r in rows.values] == ["a", "B", "C", "d"]


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_update_row(
    setup: ServingContext,
    table_type: TableType,
):
    """
    Test row updates.
    - All column dtypes
    - ID should not be updated even if provided
    - Updating data with wrong dtype or vector length should store None
    - Updating embedding directly should work

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        ### --- Add row with all dtypes --- ###
        data = [
            {
                "ID": "0",
                "Updated at": "1990-05-13T09:01:50.010756+00:00",
                "int": 1,
                "float": -1.25,
                "bool": True,
                "str": "moka",
                "image": setup.image_uri,
                "audio": setup.audio_uri,
                "document": setup.document_uri,
                "Title": "Dune: Part Two.",
                "Text": '"Dune: Part Two" is a film.',
                "Title Embed": [-1.25] * setup.embedding_size,
                "Text Embed": [0.25] * setup.embedding_size,
                "User": "Hi",
                "AI": "Hello",
            }
        ]
        add_table_rows(client, table_type, table.id, data, stream=False)
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 1
        row = rows.values[0]
        t0 = datetime.fromisoformat(row["Updated at"])

        # ID should not be updated, the rest OK
        data = dict(ID="2", float=1.0, bool=False)
        response = client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(table_id=table.id, data={row["ID"]: data}),
        )
        assert isinstance(response, OkResponse)
        _rows = list_table_rows(client, table_type, table.id)
        assert len(_rows.items) == 1
        _row = _rows.values[0]
        t1 = datetime.fromisoformat(_row["Updated at"])
        assert _row["float"] == data["float"]
        assert _row["bool"] == data["bool"]
        _assert_dict_equal(row, _row, exclude=["Updated at", "float", "bool"])
        assert t1 > t0

        # Test updating data with wrong dtype
        data = dict(ID="2", int="str", float="str", bool="str")
        response = client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(table_id=table.id, data={row["ID"]: data}),
        )
        assert isinstance(response, OkResponse)
        _rows = list_table_rows(client, table_type, table.id)
        assert len(_rows.items) == 1
        _row = _rows.values[0]
        t2 = datetime.fromisoformat(_row["Updated at"])
        assert _row["int"] is None
        assert _row["float"] is None
        assert _row["bool"] is None
        _assert_dict_equal(row, _row, exclude=["Updated at", "int", "float", "bool"])
        assert t2 > t1

        if table_type == TableType.KNOWLEDGE:
            # Test updating embedding columns directly
            response = client.table.update_table_rows(
                table_type,
                MultiRowUpdateRequest(
                    table_id=table.id,
                    data={
                        row["ID"]: {
                            "Title Embed": [0] * len(row["Title Embed"]),
                            "Text Embed": [1] * len(row["Text Embed"]),
                        }
                    },
                ),
            )
            assert isinstance(response, OkResponse)
            _rows = list_table_rows(client, table_type, table.id)
            assert len(_rows.items) == 1
            _row = _rows.values[0]
            t3 = datetime.fromisoformat(_row["Updated at"])
            assert sum(_row["Title Embed"]) == 0
            assert sum(_row["Text Embed"]) == len(row["Text Embed"])
            assert t3 > t2
            # Test updating embedding columns with wrong length
            response = client.table.update_table_rows(
                table_type,
                MultiRowUpdateRequest(
                    table_id=table.id,
                    data={row["ID"]: {"Title Embed": [0], "Text Embed": [0]}},
                ),
            )
            assert isinstance(response, OkResponse)
            _rows = list_table_rows(client, table_type, table.id)
            assert len(_rows.items) == 1
            _row = _rows.values[0]
            t4 = datetime.fromisoformat(_row["Updated at"])
            assert _row["Title Embed"] is None
            assert _row["Text Embed"] is None
            assert t4 > t3


@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_regen_embedding(
    setup: ServingContext,
    stream: bool,
):
    table_type = TableType.KNOWLEDGE
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type, cols=[]) as table:
        # Add row
        data = [{"Title": "Dune: Part Two.", "Text": '"Dune: Part Two" is a film.'}]
        add_table_rows(client, table_type, table.id, data, stream=False)
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 1
        r0 = rows.values[0]
        t0 = datetime.fromisoformat(r0["Updated at"])
        # Update row
        response = client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={r0["ID"]: {"Title": "hi", "Text": "papaya"}},
            ),
        )
        assert isinstance(response, OkResponse)
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 1
        r1 = rows.values[0]
        t1 = datetime.fromisoformat(r1["Updated at"])
        assert t1 > t0
        assert r1["Title"] != r0["Title"]
        assert r1["Text"] != r0["Text"]
        assert r1["Title Embed"] == r0["Title Embed"]
        assert r1["Text Embed"] == r0["Text Embed"]
        # Regen row
        regen_table_rows(client, table_type, table.id, [r0["ID"]], stream=stream)
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 1
        r2 = rows.values[0]
        t2 = datetime.fromisoformat(r2["Updated at"])
        assert t2 > t1
        assert r2["Title"] != r0["Title"]
        assert r2["Text"] != r0["Text"]
        assert r2["Title Embed"] != r0["Title Embed"]
        assert r2["Text Embed"] != r0["Text Embed"]


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_multiturn_regen(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    """
    Tests multiturn row regen.
    - Each row correctly sees the regenerated output of the previous row

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream (SSE) or not.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="User", dtype="str"),
        ColumnSchemaCreate(
            id="AI",
            dtype="str",
            gen_config=LLMGenConfig(
                model=setup.gpt_llm_model_id,
                system_prompt="",
                prompt="${User}",
                max_tokens=20,
                multi_turn=True,
            ),
        ),
    ]
    if table_type == TableType.CHAT:
        chat_cols, cols = cols, []
    else:
        chat_cols = None
    with create_table(client, table_type, cols=cols, chat_cols=chat_cols) as table:
        ### --- Add rows --- ###
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [
                dict(User="Hi", AI="How are you?"),
                dict(User="Repeat your previous response."),
                dict(User="Repeat your previous response."),
            ],
            stream=stream,
        )
        # Check returned chunks / response
        if stream:
            assert len(response.rows) == 2
        else:
            assert len(response.rows) == 3
            response.rows = response.rows[1:]
        for row in response.rows:
            chat = row.columns["AI"].content.strip()
            assert chat == "How are you?", f"{row.columns=}"
        # Update the second row
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={response.rows[0].row_id: dict(User="Good. What is 5+5?")},
            ),
        )
        ### --- Regen rows --- ###
        response = regen_table_rows(
            client,
            table_type,
            table.id,
            [response.rows[0].row_id, response.rows[1].row_id],
            stream=stream,
        )
        assert len(response.rows) == 2
        for row in response.rows:
            chat = row.columns["AI"].content.strip()
            assert chat != "How are you?", f"{row.columns=}"
            assert "10" in chat, f"{row.columns=}"
