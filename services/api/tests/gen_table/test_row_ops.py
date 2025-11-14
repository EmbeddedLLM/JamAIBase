import re
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from os.path import basename, dirname, join, realpath
from tempfile import TemporaryDirectory
from time import sleep
from typing import Generator

import httpx
import pandas as pd
import pytest
from flaky import flaky

from jamaibase import JamAI
from jamaibase.types import (
    ActionTableSchemaCreate,
    AddActionColumnSchema,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    CellCompletionResponse,
    ChatTableSchemaCreate,
    ChatThreadResponse,
    CodeInterpreterTool,
    ColumnReorderRequest,
    ColumnSchema,
    ColumnSchemaCreate,
    DeploymentCreate,
    GenConfigUpdateRequest,
    KnowledgeTableSchemaCreate,
    MultiRowAddRequest,
    MultiRowCompletionResponse,
    MultiRowDeleteRequest,
    MultiRowRegenRequest,
    MultiRowUpdateRequest,
    OkResponse,
    RowCompletionResponse,
    SearchRequest,
    TableMetaResponse,
    WebSearchTool,
)
from jamaibase.utils.io import df_to_csv
from owl.types import (
    ChatRole,
    CloudProvider,
    LLMGenConfig,
    ModelCapability,
    RegenStrategy,
    Role,
    TableType,
)
from owl.utils.exceptions import (
    BadInputError,
    JamaiException,
    ResourceNotFoundError,
)
from owl.utils.test import (
    ELLM_EMBEDDING_CONFIG,
    ELLM_EMBEDDING_DEPLOYMENT,
    GPT_4O_MINI_CONFIG,
    GPT_4O_MINI_DEPLOYMENT,
    GPT_5_MINI_CONFIG,
    GPT_5_MINI_DEPLOYMENT,
    OPENAI_O4_MINI_CONFIG,
    OPENAI_O4_MINI_DEPLOYMENT,
    STREAM_PARAMS,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    add_table_rows,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_user,
    get_file_map,
    list_table_rows,
    regen_table_rows,
    upload_file,
)

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)

TABLE_TYPES = [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]
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


@dataclass(slots=True)
class ServingContext:
    superuser_id: str
    user_id: str
    org_id: str
    project_id: str


@pytest.fixture(scope="module")
def setup():
    """
    Fixture to set up the necessary organization and projects for file tests.
    """
    with (
        # Create superuser
        create_user() as superuser,
        # Create user
        create_user({"email": "testuser@example.com", "name": "Test User"}) as user,
        # Create organization
        create_organization(user_id=superuser.id) as org,
        # Create project
        create_project(dict(name="Bucket A"), user_id=superuser.id, organization_id=org.id) as p0,
    ):
        assert org.id == "0"
        client = JamAI(user_id=superuser.id)
        # Join organization and project
        client.organizations.join_organization(
            user_id=user.id, organization_id=org.id, role=Role.ADMIN
        )
        client.projects.join_project(user_id=user.id, project_id=p0.id, role=Role.ADMIN)

        # Create models
        with (
            create_model_config(GPT_4O_MINI_CONFIG),
            create_model_config(GPT_5_MINI_CONFIG),
            create_model_config(OPENAI_O4_MINI_CONFIG),
            create_model_config(
                {
                    # "id": "openai/Qwen/Qwen-2-Audio-7B",
                    "id": "openai/gpt-4o-mini-audio-preview",
                    "type": "llm",
                    # "name": "ELLM Qwen2 Audio (7B)",
                    "name": "OpenAI GPT-4o Mini Audio Preview",
                    "capabilities": ["chat", "audio"],
                    "context_length": 128000,
                    "languages": ["en"],
                }
            ) as llm_config_audio,
            create_model_config(ELLM_EMBEDDING_CONFIG),
            create_model_config(RERANK_ENGLISH_v3_SMALL_CONFIG),
        ):
            # Create deployments
            with (
                create_deployment(GPT_4O_MINI_DEPLOYMENT),
                create_deployment(GPT_5_MINI_DEPLOYMENT),
                create_deployment(OPENAI_O4_MINI_DEPLOYMENT),
                create_deployment(
                    DeploymentCreate(
                        model_id=llm_config_audio.id,
                        # name="ELLM Qwen2 Audio (7B) Deployment",
                        name="OpenAI GPT-4o Mini Audio Preview Deployment",
                        # provider=CloudProvider.ELLM,
                        provider=CloudProvider.OPENAI,
                        routing_id=llm_config_audio.id,
                        # api_base="https://llmci.embeddedllm.com/audio/v1",
                        api_base="",
                    )
                ),
                create_deployment(ELLM_EMBEDDING_DEPLOYMENT),
                create_deployment(RERANK_ENGLISH_v3_SMALL_DEPLOYMENT),
            ):
                yield ServingContext(
                    superuser_id=superuser.id,
                    user_id=user.id,
                    org_id=org.id,
                    project_id=p0.id,
                )


def _get_chat_model(client: JamAI) -> str:
    models = client.model_ids(prefer="openai/gpt-4o-mini", capabilities=["chat"])
    return models[0]


def _get_reasoning_model(client: JamAI) -> str:
    models = client.model_ids(prefer="openai/gpt-5-mini", capabilities=["reasoning"])
    return models[0]


def _get_reranking_model(client: JamAI) -> str:
    models = client.model_ids(capabilities=["rerank"])
    return models[0]


@contextmanager
def _create_table(
    client: JamAI,
    table_type: TableType,
    table_id: str = TABLE_ID_A,
    cols: list[ColumnSchemaCreate] | None = None,
    chat_cols: list[ColumnSchemaCreate] | None = None,
    embedding_model: str | None = None,
):
    try:
        if cols is None:
            cols = [
                ColumnSchemaCreate(id="good", dtype="bool"),
                ColumnSchemaCreate(id="words", dtype="int"),
                ColumnSchemaCreate(id="stars", dtype="float"),
                ColumnSchemaCreate(id="inputs", dtype="str"),
                ColumnSchemaCreate(id="photo", dtype="image"),
                ColumnSchemaCreate(id="audio", dtype="audio"),
                ColumnSchemaCreate(id="paper", dtype="document"),
                ColumnSchemaCreate(
                    id="summary",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model=_get_chat_model(client),
                        system_prompt="You are a concise assistant.",
                        # Interpolate string and non-string input columns
                        prompt="Summarise this in ${words} words:\n\n${inputs}",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ),
                ),
                ColumnSchemaCreate(
                    id="captioning",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model="",
                        system_prompt="You are a concise assistant.",
                        # Interpolate file input column
                        prompt="${photo} \n\nWhat's in the image?",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=20,
                    ),
                ),
                ColumnSchemaCreate(
                    id="narration",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model="",
                        prompt="${audio} \n\nWhat happened?",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=10,
                    ),
                ),
                ColumnSchemaCreate(
                    id="concept",
                    dtype="str",
                    gen_config=LLMGenConfig(
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
                ColumnSchemaCreate(id="User", dtype="str"),
                ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model=_get_chat_model(client),
                        system_prompt="You are a wacky assistant.",
                        temperature=0.001,
                        top_p=0.001,
                        max_tokens=5,
                    ),
                ),
            ]

        if table_type == TableType.ACTION:
            table = client.table.create_action_table(
                ActionTableSchemaCreate(id=table_id, cols=cols)
            )
        elif table_type == TableType.KNOWLEDGE:
            if embedding_model is None:
                embedding_model = ""
            table = client.table.create_knowledge_table(
                KnowledgeTableSchemaCreate(id=table_id, cols=cols, embedding_model=embedding_model)
            )
        elif table_type == TableType.CHAT:
            table = client.table.create_chat_table(
                ChatTableSchemaCreate(id=table_id, cols=chat_cols + cols)
            )
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, TableMetaResponse)
        yield table
    finally:
        client.table.delete_table(table_type, table_id)


def _add_row(
    client: JamAI,
    table_type: TableType,
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
            photo=upload_file(client, FILES["rabbit.jpeg"]).uri,
            audio=upload_file(client, FILES["turning-a4-size-magazine.mp3"]).uri,
            paper=upload_file(client, FILES["LLMs as Optimizers [DeepMind ; 2023].pdf"]).uri,
        )

    if knowledge_data is None:
        knowledge_data = dict(
            Title="Dune: Part Two.",
            Text='"Dune: Part Two" is a 2024 American epic science fiction film.',
        )
    if chat_data is None:
        chat_data = dict(User="Tell me a joke.")
    if table_type == TableType.ACTION:
        pass
    elif table_type == TableType.KNOWLEDGE:
        data.update(knowledge_data)
    elif table_type == TableType.CHAT:
        data.update(chat_data)
    else:
        raise ValueError(f"Invalid table type: {table_type}")
    response = client.table.add_table_rows(
        table_type,
        MultiRowAddRequest(table_id=table_name, data=[data], stream=stream),
    )
    if stream:
        return response
    assert isinstance(response, MultiRowCompletionResponse)
    assert len(response.rows) == 1
    return response.rows[0]


def _collect_reasoning(
    responses: MultiRowCompletionResponse | Generator[CellCompletionResponse, None, None],
    col: str,
):
    if isinstance(responses, MultiRowCompletionResponse):
        return "".join(r.columns[col].reasoning_content for r in responses.rows)
    return "".join(r.reasoning_content for r in responses if r.output_column_name == col)


def _collect_text(
    responses: MultiRowCompletionResponse | Generator[CellCompletionResponse, None, None],
    col: str,
):
    if isinstance(responses, MultiRowCompletionResponse):
        return "".join(r.columns[col].content for r in responses.rows)
    return "".join(r.content for r in responses if r.output_column_name == col)


def _get_exponent(x: float) -> int:
    return Decimal(str(x)).as_tuple().exponent


@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_full_text_search(
    setup: ServingContext,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [ColumnSchemaCreate(id="text", dtype="str")]
    with _create_table(client, "action", cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        # Add data
        texts = [
            '"Dune: Part Two" 2024 is Denis\'s science-fiction film.',
            '"Dune: Part Two" 2024 is Denis\'s film.',
            '"Arrival" 《降临》是一部 2016 年美国科幻剧情片，由丹尼斯·维伦纽瓦执导。',
            '"Arrival" 『デューン: パート 2』2024 はデニスの映画です。',
        ]
        response = client.table.add_table_rows(
            "action",
            MultiRowAddRequest(
                table_id=table.id, data=[{"text": t} for t in texts], stream=stream
            ),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response, MultiRowCompletionResponse)

        # Search
        def _search(query: str):
            return client.table.hybrid_search(
                "action", SearchRequest(table_id=table.id, query=query)
            )

        assert len(_search("AND")) == 0  # SQL-like statements should still work
        assert len(_search("《")) == 1
        assert len(_search("scien*")) == 1
        assert len(_search("film")) == 2
        assert len(_search("science -fiction")) == 0  # Not supported
        assert len(_search("science-fiction")) == 1
        assert len(_search("science -fiction\n2016")) == 1
        assert len(_search("美国")) == 1


@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_conversation_starter(
    setup: ServingContext,
    stream: bool,
):
    table_type = TableType.CHAT
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="User", dtype="str"),
        ColumnSchemaCreate(
            id="AI",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client),
                system_prompt="You help remember facts.",
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
        ColumnSchemaCreate(id="words", dtype="int"),
        ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client),
                system_prompt="You are an assistant",
                temperature=0.001,
                top_p=0.001,
                max_tokens=5,
            ),
        ),
    ]
    with _create_table(client, table_type, cols=[], chat_cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        # Add the starter
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
                table_id=table.id, data=[dict(AI="Jim has 5 apples.")], stream=stream
            ),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response.rows[0], RowCompletionResponse)
        # Chat with it
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [dict(User="How many apples does Jim have?")],
            stream=stream,
        )
        assert len(response.rows) == 1
        row = response.rows[0]
        assert "summary" in row.columns
        answer = row.columns["AI"].content
        assert "5" in answer or "five" in answer.lower()


@pytest.mark.timeout(180)
@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize(
    "doc",
    [
        FILES["salary 总结.pdf"],
        # FILES["1978_APL_FP_detrapping.PDF"],
        # FILES["digital_scan_combined.pdf"],
        FILES["creative-story.md"],
        FILES["creative-story.txt"],
        FILES["multilingual-code-examples.html"],
        FILES["weather-forecast-service.xml"],
        FILES["ChatMed_TCM-v0.2-5records.jsonl"],
        FILES["Recommendation Letter.docx"],
        FILES["(2017.06.30) NMT in Linear Time (ByteNet).pptx"],
        FILES["Claims Form.xlsx"],
        FILES["weather_observations.tsv"],
        FILES["weather_observations_long.csv"],
    ],
    ids=lambda x: basename(x),
)
def test_add_row_document_dtype(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    doc: str,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="doc", dtype="document"),
        ColumnSchemaCreate(
            id="content",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                prompt="Document: \n${doc} \n\nReply 0 if document received, else -1. Omit any explanation, only answer 0 or -1.",
            ),
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)

        upload_response = upload_file(client, doc)
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [dict(doc=upload_response.uri)],
            stream=stream,
        )
        assert len(response.rows) == 1
        row = response.rows[0]
        assert "content" in row.columns
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 1
        row = rows.values[0]
        assert row["doc"] == upload_response.uri, row["doc"]
        assert "0" in row["content"]


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_regen_with_reordered_columns(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="number", dtype="int"),
        ColumnSchemaCreate(
            id="col1-english",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                prompt=(
                    "Number: ${number} \n\nTell the 'Number' in English, "
                    "only output the answer in uppercase without explanation."
                ),
            ),
        ),
        ColumnSchemaCreate(
            id="col2-malay",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                prompt=(
                    "Number: ${number} \n\nTell the 'Number' in Malay, "
                    "only output the answer in uppercase without explanation."
                ),
            ),
        ),
        ColumnSchemaCreate(
            id="col3-mandarin",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                prompt=(
                    "Number: ${number} \n\nTell the 'Number' in Mandarin (Chinese Character), "
                    "only output the answer in uppercase without explanation."
                ),
            ),
        ),
        ColumnSchemaCreate(
            id="col4-roman",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                prompt=(
                    "Number: ${number} \n\nTell the 'Number' in Roman Numerals, "
                    "only output the answer in uppercase without explanation."
                ),
            ),
        ),
    ]

    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        row = _add_row(
            client,
            table_type,
            False,
            data=dict(number=1),
        )
        assert isinstance(row, RowCompletionResponse)
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 1
        row = rows.values[0]
        _id = row["ID"]
        assert row["number"] == 1, row["number"]
        assert row["col1-english"] == "ONE", row["col1-english"]
        assert row["col2-malay"] == "SATU", row["col2-malay"]
        assert row["col3-mandarin"] in ("一", "壹"), row["col3-mandarin"]
        assert row["col4-roman"] == "I", row["col4-roman"]

        # Update Input + Regen
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={_id: dict(number=2)},
            ),
        )

        response = client.table.regen_table_rows(
            table_type,
            MultiRowRegenRequest(
                table_id=table.id,
                row_ids=[_id],
                regen_strategy=RegenStrategy.RUN_ALL,
                stream=stream,
            ),
        )
        if stream:
            _ = [r for r in response]

        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 1
        row = rows.values[0]
        assert row["number"] == 2, row["number"]
        assert row["col1-english"] == "TWO", row["col1-english"]
        assert row["col2-malay"] == "DUA", row["col2-malay"]
        assert row["col3-mandarin"] == "二", row["col3-mandarin"]
        assert row["col4-roman"] == "II", row["col4-roman"]

        # Reorder + Update Input + Regen
        # [1, 2, 3, 4] -> [3, 1, 4, 2]
        new_cols = [
            "ID",
            "Updated at",
            "number",
            "col3-mandarin",
            "col1-english",
            "col4-roman",
            "col2-malay",
        ]
        if table_type == TableType.KNOWLEDGE:
            new_cols += ["Title", "Text", "Title Embed", "Text Embed", "File ID", "Page"]
        elif table_type == TableType.CHAT:
            new_cols += ["User", "AI"]
        client.table.reorder_columns(
            table_type=table_type,
            request=ColumnReorderRequest(
                table_id=TABLE_ID_A,
                column_names=new_cols,
            ),
        )
        # RUN_SELECTED
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={_id: dict(number=5)},
            ),
        )
        response = client.table.regen_table_rows(
            table_type,
            MultiRowRegenRequest(
                table_id=TABLE_ID_A,
                row_ids=[_id],
                regen_strategy=RegenStrategy.RUN_SELECTED,
                output_column_id="col1-english",
                stream=stream,
            ),
        )
        if stream:
            _ = [r for r in response]
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 1
        row = rows.values[0]
        assert row["number"] == 5, row["number"]
        assert row["col3-mandarin"] == "二", row["col3-mandarin"]
        assert row["col1-english"] == "FIVE", row["col1-english"]
        assert row["col4-roman"] == "II", row["col4-roman"]
        assert row["col2-malay"] == "DUA", row["col2-malay"]

        # RUN_BEFORE
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={_id: dict(number=6)},
            ),
        )
        response = client.table.regen_table_rows(
            table_type,
            MultiRowRegenRequest(
                table_id=TABLE_ID_A,
                row_ids=[_id],
                regen_strategy=RegenStrategy.RUN_BEFORE,
                output_column_id="col4-roman",
                stream=stream,
            ),
        )
        if stream:
            _ = [r for r in response]
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 1
        row = rows.values[0]
        assert row["number"] == 6, row["number"]
        assert row["col3-mandarin"] == "六", row["col3-mandarin"]
        assert row["col1-english"] == "SIX", row["col1-english"]
        assert row["col4-roman"] == "VI", row["col4-roman"]
        assert row["col2-malay"] == "DUA", row["col2-malay"]

        # RUN_AFTER
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={_id: dict(number=7)},
            ),
        )
        response = client.table.regen_table_rows(
            table_type,
            MultiRowRegenRequest(
                table_id=TABLE_ID_A,
                row_ids=[_id],
                regen_strategy=RegenStrategy.RUN_AFTER,
                output_column_id="col4-roman",
                stream=stream,
            ),
        )
        if stream:
            _ = [r for r in response]
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 1
        row = rows.values[0]
        assert row["number"] == 7, row["number"]
        assert row["col3-mandarin"] == "六", row["col3-mandarin"]
        assert row["col1-english"] == "SIX", row["col1-english"]
        assert row["col4-roman"] == "VII", row["col4-roman"]
        assert row["col2-malay"] == "TUJUH", row["col2-malay"]


# @pytest.mark.parametrize("table_type", TABLE_TYPES)
# @pytest.mark.parametrize("stream", [True, False])
# def test_add_row_file_type_output_column(
#     setup: ServingContext,
#     table_type: TableType,
#     stream: bool,
# ):
#     client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
#     cols = [
#         ColumnSchemaCreate(id="photo", dtype="image"),
#         ColumnSchemaCreate(id="question", dtype="str"),
#         ColumnSchemaCreate(
#             id="captioning",
#             dtype="file",
#             gen_config=LLMGenConfig(model="", prompt="${photo} What's in the image?"),
#         ),
#         ColumnSchemaCreate(
#             id="answer",
#             dtype="file",
#             gen_config=LLMGenConfig(
#                 model="",
#                 prompt="${photo} ${question}?",
#             ),
#         ),
#         ColumnSchemaCreate(
#             id="compare",
#             dtype="image",
#             gen_config=LLMGenConfig(
#                 model="",
#                 prompt="Compare ${captioning} and ${answer}.",
#             ),
#         ),
#     ]
#     with _create_table(client, table_type, cols=cols) as table:
#         assert isinstance(table, TableMetaResponse)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_add_row_output_column_referred_image_input_with_chat_model(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="photo", dtype="image"),
        ColumnSchemaCreate(
            id="captioning",
            dtype="str",
            gen_config=LLMGenConfig(model="", prompt="${photo} What's in the image?"),
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        with create_model_config(
            {
                "id": "openai/Qwen/Qwen2.5-7B-Instruct",
                "type": "llm",
                "name": "OpenAI GPT-4o Mini",
                "capabilities": ["chat"],
                "context_length": 32000,
                "languages": ["en"],
            }
        ) as llm_config_chat_only_model:
            with create_deployment(
                DeploymentCreate(
                    model_id=llm_config_chat_only_model.id,
                    name="ELLM Qwen2.5 (7B) Deployment",
                    provider=CloudProvider.OPENAI,
                    routing_id=llm_config_chat_only_model.id,
                    api_base="http://192.168.80.2:9192/v1",
                )
            ):
                # Add output column that referred to image file, but using chat model
                # (Notes: chat model can be set due to default prompt was added afterward)
                chat_only_model = llm_config_chat_only_model.id
                cols = [
                    ColumnSchemaCreate(
                        id="captioning2",
                        dtype="str",
                        gen_config=LLMGenConfig(model=chat_only_model),
                    ),
                ]
                with pytest.raises(BadInputError):
                    if table_type == TableType.ACTION:
                        client.table.add_action_columns(
                            AddActionColumnSchema(id=table.id, cols=cols)
                        )
                    elif table_type == TableType.KNOWLEDGE:
                        client.table.add_knowledge_columns(
                            AddKnowledgeColumnSchema(id=table.id, cols=cols)
                        )
                    elif table_type == TableType.CHAT:
                        client.table.add_chat_columns(AddChatColumnSchema(id=table.id, cols=cols))
                    else:
                        raise ValueError(f"Invalid table type: {table_type}")
                    assert isinstance(table, TableMetaResponse)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False])
def test_add_row_sequential_completion_with_error(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input", dtype="str"),
        ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                prompt="Summarise ${input}.",
            ),
        ),
        ColumnSchemaCreate(
            id="rephrase",
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                prompt="Rephrase ${summary}",
            ),
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [dict(input="a" * 10000000)],
            stream=stream,
        )
        assert len(response.rows) == 1
        row = response.rows[0]
        assert "summary" in row.columns
        assert "rephrase" in row.columns
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 1
        row = rows.values[0]
        assert row["summary"].startswith("[ERROR] ")
        second_output = (row["rephrase"]).upper()
        if stream:
            assert second_output.startswith("[ERROR] ")
        else:
            assert "WARNING" in second_output or "ERROR" in second_output


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize(
    "img_filename",
    [
        "s3://image-bucket/bmp/cifar10-deer.bmp",
        "s3://image-bucket/tiff/cifar10-deer.tiff",
        "file://image-bucket/tiff/rabbit.tiff",
    ],
)
def test_add_row_image_file_column_invalid_extension(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    img_filename: str,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        with pytest.raises(
            BadInputError,
            match=re.compile(
                f"^.*{re.escape('Unsupported file type. Make sure the file belongs to one of the following formats:')}.*"
                f"{re.escape('[Image File Types]:')}.*"
                f"{re.escape('[Audio File Types]:')}.*"
                f"{re.escape('[Document File Types]:')}.*$"
            ),
        ):
            response = _add_row(
                client,
                table_type,
                stream,
                data=dict(photo=img_filename),
            )
            if stream:
                _ = [r for r in response]


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_add_row_wrong_dtype(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [
                dict(
                    good=True,
                    words=5,
                    stars=7.9,
                    inputs=TEXT,
                    photo=upload_file(client, FILES["rabbit.jpeg"]).uri,
                    audio=upload_file(client, FILES["turning-a4-size-magazine.mp3"]).uri,
                    paper=upload_file(
                        client, FILES["LLMs as Optimizers [DeepMind ; 2023].pdf"]
                    ).uri,
                )
            ],
            stream=stream,
        )
        assert len(response.rows) == 1
        row = response.rows[0]
        assert "summary" in row.columns
        assert "captioning" in row.columns
        assert "narration" in row.columns
        assert "concept" in row.columns

        # Test adding data with wrong dtype
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [dict(good="dummy1", words="dummy2", stars="dummy3", inputs=TEXT)],
            stream=stream,
        )
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 2
        row = rows.items[-1]
        assert row["good"]["value"] is None, row["good"]
        assert row["good"]["original"] == "dummy1", row["good"]
        assert row["words"]["value"] is None, row["words"]
        assert row["words"]["original"] == "dummy2", row["words"]
        assert row["stars"]["value"] is None, row["stars"]
        assert row["stars"]["original"] == "dummy3", row["stars"]


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_add_row_missing_columns(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        response = add_table_rows(
            client,
            table_type,
            table.id,
            [
                dict(
                    good=True,
                    words=5,
                    stars=7.9,
                    inputs=TEXT,
                    photo=upload_file(client, FILES["rabbit.jpeg"]).uri,
                    audio=upload_file(client, FILES["turning-a4-size-magazine.mp3"]).uri,
                    paper=upload_file(
                        client, FILES["LLMs as Optimizers [DeepMind ; 2023].pdf"]
                    ).uri,
                )
            ],
            stream=stream,
        )
        assert len(response.rows) == 1
        row = response.rows[0]
        assert "summary" in row.columns
        assert "captioning" in row.columns
        assert "narration" in row.columns
        assert "concept" in row.columns

        # Test adding data with missing column
        response = _add_row(
            client,
            table_type,
            stream,
            TABLE_ID_A,
            data=dict(good="dummy1", inputs=TEXT),
        )
        if stream:
            responses = [r for r in response]
            assert all(isinstance(r, CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response, RowCompletionResponse)
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 2
        row = rows.items[-1]
        assert row["good"]["value"] is None, row["good"]
        assert row["good"]["original"] == "dummy1", row["good"]
        assert row["words"]["value"] is None, row["words"]
        assert "original" not in row["words"], row["words"]
        assert row["stars"]["value"] is None, row["stars"]
        assert "original" not in row["stars"], row["stars"]


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_add_rows_all_input(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="0", dtype="int"),
        ColumnSchemaCreate(id="1", dtype="float"),
        ColumnSchemaCreate(id="2", dtype="bool"),
        ColumnSchemaCreate(id="3", dtype="str"),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
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
            assert isinstance(response, MultiRowCompletionResponse)
            assert len(response.rows) == 2
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 2


# @flaky(max_runs=5, min_passes=1)
# @pytest.mark.timeout(180)
# @pytest.mark.parametrize("table_type", TABLE_TYPES)
# @pytest.mark.parametrize("stream", **STREAM_PARAMS)
# @pytest.mark.parametrize("reasoning_model", ["openai/gpt-5-mini", "openai/o4-mini"][:1])
# def test_reasoning_model_with_reasoning_effort(
#     setup: ServingContext,
#     table_type: TableType,
#     stream: bool,
#     reasoning_model: str,
# ):
#     """
#     Tests that different `reasoning.effort` levels produce different outputs
#     when using a reasoning model with the Responses API.
#     """
#     client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

#     system_prompt = "You are a brilliant logician. Always think twice and give your reasoning before answering!"
#     prompt = (
#         "Solve this riddle: "
#         "If a plane crashes on the border between the USA and Canada, "
#         "where do you bury the survivors? "
#     )

#     cols = [
#         ColumnSchemaCreate(id="Riddle", dtype="str"),
#         ColumnSchemaCreate(
#             id="LowEffortAnswer",
#             dtype="str",
#             gen_config=LLMGenConfig(
#                 model=reasoning_model,
#                 system_prompt=system_prompt,
#                 prompt=prompt,
#                 reasoning_effort="low",
#                 reasoning_summary="auto",
#             ),
#         ),
#         ColumnSchemaCreate(
#             id="MediumEffortAnswer",
#             dtype="str",
#             gen_config=LLMGenConfig(
#                 model=reasoning_model,
#                 system_prompt=system_prompt,
#                 prompt=prompt,
#                 reasoning_effort="medium",
#                 reasoning_summary="auto",
#             ),
#         ),
#         ColumnSchemaCreate(
#             id="MinimalEffortAnswer",
#             dtype="str",
#             gen_config=LLMGenConfig(
#                 model=reasoning_model,
#                 system_prompt=system_prompt,
#                 prompt=prompt,
#                 reasoning_effort="minimal",
#                 reasoning_summary="auto",
#             ),
#         ),
#     ]

#     with _create_table(client, table_type, cols=cols) as table:
#         assert isinstance(table, TableMetaResponse)

#         response = add_table_rows(
#             client,
#             table_type,
#             table.id,
#             [dict(Riddle="Trigger")],
#             stream=stream,
#         )

#         low_effort_reasoning = _collect_reasoning(response, "LowEffortAnswer").lower()
#         medium_effort_reasoning = _collect_reasoning(response, "MediumEffortAnswer").lower()
#         minimal_effort_reasoning = _collect_reasoning(response, "MinimalEffortAnswer").lower()
#         assert "survivors" in low_effort_reasoning
#         assert "survivors" in medium_effort_reasoning

#         assert (len(medium_effort_reasoning) > len(low_effort_reasoning)) or (
#             len(low_effort_reasoning) > len(minimal_effort_reasoning)
#         )

#         low_effort_result = _collect_text(response, "LowEffortAnswer").lower()
#         medium_effort_result = _collect_text(response, "MediumEffortAnswer").lower()
#         minimal_effort_result = _collect_text(response, "MinimalEffortAnswer").lower()

#         assert "bury" in low_effort_result and "survivors" in low_effort_result
#         assert "bury" in medium_effort_result and "survivors" in medium_effort_result
#         if reasoning_model == "openai/gpt-5-mini":
#             assert "bury" in minimal_effort_result and "survivors" in minimal_effort_result
#         else:
#             assert "'minimal' is not supported" in minimal_effort_result

#         assert response.rows[0].columns["LowEffortAnswer"].usage is not None
#         assert response.rows[0].columns["MediumEffortAnswer"].usage is not None
#         assert response.rows[0].columns["MinimalEffortAnswer"].usage is not None


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("table_type", TABLE_TYPES[:1])
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("capability", [ModelCapability.CHAT, ModelCapability.REASONING])
def test_agentic_column_with_web_search(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    capability: ModelCapability,
):
    """
    Tests an agentic column that uses web_search to perform a fact-checking task.
    Also validates usage metrics.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="Claim", dtype="str"),
        ColumnSchemaCreate(
            id="FactCheck",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client)
                if capability == ModelCapability.CHAT
                else _get_reasoning_model(client),
                prompt="You are a meticulous fact-checker. Your goal is to verify the following claim: `${Claim}`. "
                "Use web search to determine if the claim is true or false and provide a brief explanation.",
                tools=[WebSearchTool()],
                reasoning_effort="low" if capability == ModelCapability.REASONING else None,
            ),
        ),
    ]

    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)

        response = add_table_rows(
            client,
            table_type,
            table.id,
            [dict(Claim="The sun revolves around the Earth.")],
            stream=stream,
        )

        reasoning = _collect_reasoning(response, "FactCheck")
        assert "Searched the web for " in reasoning and "Ran Python code:" not in reasoning
        reasoning = reasoning.lower()
        assert "earth" in reasoning
        assert "sun" in reasoning
        assert "revolve" in reasoning or "orbit" in reasoning

        result = _collect_text(response, "FactCheck").lower()
        assert result is not None
        assert "false" in result
        assert "earth" in result
        assert "sun" in result
        assert "revolve" in result or "orbit" in result

        usage = response.rows[0].columns["FactCheck"].usage
        assert usage is not None
        assert usage.prompt_tokens > 0
        assert usage.completion_tokens > 0
        assert usage.tool_usage_details is not None
        assert usage.tool_usage_details.web_search_calls > 0
        assert usage.tool_usage_details.code_interpreter_calls == 0


@flaky(max_runs=3, min_passes=1)
@pytest.mark.timeout(120)
@pytest.mark.parametrize("table_type", TABLE_TYPES[:1])
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("capability", [ModelCapability.CHAT, ModelCapability.REASONING])
def test_agentic_column_with_code_interpreter(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    capability: ModelCapability,
):
    """
    Tests an agentic column that reads numerical data from other columns
    and uses the code_interpreter to perform a calculation. Also validates usage metrics.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="Revenue", dtype="int"),
        ColumnSchemaCreate(id="Expenses", dtype="int"),
        ColumnSchemaCreate(
            id="ProfitMargin",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client)
                if capability == ModelCapability.CHAT
                else _get_reasoning_model(client),
                prompt="You are a financial analyst. Check the Revenue: `${Revenue}` and Expenses: `${Expenses}`."
                "Then, use the code interpreter to calculate the profit margin percentage. "
                "The formula is `(Revenue - Expenses) / Revenue * 100`. "
                "Return only the final numerical answer, formatted as a percentage string like '25.0%'.",
                tools=[CodeInterpreterTool()],
                reasoning_effort="low" if capability == ModelCapability.REASONING else None,
            ),
        ),
    ]

    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)

        response = add_table_rows(
            client,
            table_type,
            table.id,
            [dict(Revenue=200000, Expenses=50000)],
            stream=stream,
        )

        reasoning = _collect_reasoning(response, "ProfitMargin")
        assert "Ran Python code:" in reasoning and "Searched the web for " not in reasoning
        assert "200000" in reasoning
        assert "50000" in reasoning

        result = _collect_text(response, "ProfitMargin")
        assert result is not None
        assert "75" in result  # 150000 / 200000 = 0.75
        assert "%" in result

        usage = response.rows[0].columns["ProfitMargin"].usage
        assert usage is not None
        assert usage.prompt_tokens > 0
        assert usage.completion_tokens > 0
        assert usage.tool_usage_details is not None
        assert usage.tool_usage_details.web_search_calls == 0
        assert usage.tool_usage_details.code_interpreter_calls > 0


@flaky(max_runs=3, min_passes=1)
@pytest.mark.timeout(180)
@pytest.mark.parametrize("table_type", TABLE_TYPES[:1])
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("capability", [ModelCapability.CHAT, ModelCapability.REASONING])
def test_agentic_column_with_multiple_tools(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    capability: ModelCapability,
):
    """
    Tests an agentic column that requires chaining multiple tools (web search and code interpreter)
    to complete its goal, and validates the usage metrics for both.
    """
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="Country", dtype="str"),
        ColumnSchemaCreate(
            id="PopulationDensityReport",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client)
                if capability == ModelCapability.CHAT
                else _get_reasoning_model(client),
                system_prompt="You are a geography research assistant. Always give short and concise answers.",
                prompt="Your task is for the country '${Country}'. "
                "1. First, use web search to find its current estimated population. "
                "2. Second, use web search to find its total land area in square kilometers. "
                "3. Third, use the code interpreter to calculate the population density (population / area). "
                "4. Finally, report the result in a single sentence, including the calculated density.",
                tools=[WebSearchTool(), CodeInterpreterTool()],
                reasoning_effort="low" if capability == ModelCapability.REASONING else None,
            ),
        ),
    ]

    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)

        response = add_table_rows(
            client,
            table_type,
            table.id,
            [dict(Country="Japan")],
            stream=stream,
        )

        reasoning = _collect_reasoning(response, "PopulationDensityReport")
        assert "Searched the web for " in reasoning and "Ran Python code:" in reasoning
        reasoning = reasoning.lower()
        assert "japan" in reasoning
        assert "population" in reasoning
        assert "density" in reasoning

        result = _collect_text(response, "PopulationDensityReport").lower()
        assert result is not None
        assert "japan" in result
        assert "population" in result
        assert "density" in result
        # Check for a number, which would be the calculated density
        assert any(char.isdigit() for char in result)

        usage = response.rows[0].columns["PopulationDensityReport"].usage
        assert usage is not None
        assert usage.prompt_tokens > 0
        assert usage.completion_tokens > 0
        assert usage.tool_usage_details is not None
        assert usage.tool_usage_details.web_search_calls > 0
        assert usage.tool_usage_details.code_interpreter_calls > 0


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_regen_rows(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)

        image_upload_response = upload_file(client, FILES["rabbit.jpeg"])
        audio_upload_response = upload_file(client, FILES["turning-a4-size-magazine.mp3"])
        response = _add_row(
            client,
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
        assert isinstance(response, RowCompletionResponse)
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 1
        row = rows.values[0]
        _id = row["ID"]
        original_ts = row["Updated at"]
        assert "arrival" in row["summary"].lower()
        # Regen
        client.table.update_table_rows(
            table_type,
            MultiRowUpdateRequest(
                table_id=table.id,
                data={
                    _id: dict(
                        inputs="Dune: Part Two is a 2024 American epic science fiction film directed and produced by Denis Villeneuve"
                    )
                },
            ),
        )
        response = regen_table_rows(client, table_type, table.id, [_id], stream=stream)
        row = response.rows[0]
        assert "summary" in row.columns
        assert "captioning" in row.columns
        assert "narration" in row.columns
        assert "concept" in row.columns
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 1
        row = rows.values[0]
        assert row["good"] is True
        assert row["words"] == 10
        assert row["stars"] == 9.9
        assert row["photo"] == image_upload_response.uri
        assert row["audio"] == audio_upload_response.uri
        assert row["Updated at"] > original_ts
        assert "dune" in row["summary"].lower()


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_regen_rows_all_input(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="0", dtype="int"),
        ColumnSchemaCreate(id="1", dtype="float"),
        ColumnSchemaCreate(id="2", dtype="bool"),
        ColumnSchemaCreate(id="3", dtype="str"),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
                table_id=table.id,
                data=[
                    {"0": 1, "1": 2.0, "2": False, "3": "days"},
                    {"0": 0, "1": 1.0, "2": True, "3": "of"},
                ],
                stream=False,
            ),
        )
        assert isinstance(response, MultiRowCompletionResponse)
        assert len(response.rows) == 2
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 2
        # Regen
        response = client.table.regen_table_rows(
            table_type,
            MultiRowRegenRequest(
                table_id=table.id, row_ids=[r["ID"] for r in rows.items], stream=stream
            ),
        )
        if stream:
            responses = [r for r in response if r.output_column_name != "AI"]
            assert len(responses) == 0
        else:
            assert isinstance(response, MultiRowCompletionResponse)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_delete_rows(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        data = dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="dummy")
        _add_row(client, table_type, False, data=data)
        _add_row(client, table_type, False, data=data)
        _add_row(client, table_type, False, data=data)
        _add_row(client, table_type, False, data=data)
        _add_row(
            client,
            table_type,
            False,
            data=dict(good=True, words=5, stars=7.9, inputs=TEXT_CN),
        )
        _add_row(
            client,
            table_type,
            False,
            data=dict(good=True, words=5, stars=7.9, inputs=TEXT_JP),
        )
        ori_rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(ori_rows.items) == 6
        delete_id = ori_rows.values[0]["ID"]

        # Delete one row
        response = client.table.delete_table_row(table_type, TABLE_ID_A, delete_id)
        assert isinstance(response, OkResponse)
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 5
        row_ids = set(r["ID"] for r in rows.values)
        assert delete_id not in row_ids
        # Delete multiple rows
        delete_ids = [r["ID"] for r in ori_rows.values[1:4]]
        response = client.table.delete_table_rows(
            table_type,
            MultiRowDeleteRequest(
                table_id=TABLE_ID_A,
                row_ids=delete_ids,
            ),
        )
        assert isinstance(response, OkResponse)
        rows = list_table_rows(client, table_type, TABLE_ID_A)
        assert len(rows.items) == 2
        row_ids = set(r["ID"] for r in rows.values)
        assert len(set(row_ids) & set(delete_ids)) == 0


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_column_interpolate(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

    cols = [
        ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client),
                system_prompt="You are a concise assistant.",
                prompt='Say "Jan has 5 apples.".',
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
        ColumnSchemaCreate(id="input0", dtype="int"),
        ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client),
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
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)

        def _add_row_wrapped(stream, data):
            return _add_row(
                client,
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
        answer = response.columns["output1"].content
        assert "yes" in answer.lower(), f'columns={response.columns}  answer="{answer}"'
        response = _add_row_wrapped(False, dict(input0=6))
        answer = response.columns["output1"].content
        assert "no" in answer.lower(), f'columns={response.columns}  answer="{answer}"'


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_chat_history_and_sequential_add(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input", dtype="str"),
        ColumnSchemaCreate(
            id="output",
            dtype="str",
            gen_config=LLMGenConfig(
                system_prompt="You are a calculator.",
                prompt="${input}",
                multi_turn=True,
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        # Initialise chat thread and set output format
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
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
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
                table_id=table.id,
                data=[dict(input="Add 1")],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "5" in output, output
        # Test adding multiple rows
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
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


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_chat_history_and_sequential_regen(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input", dtype="str"),
        ColumnSchemaCreate(
            id="output",
            dtype="str",
            gen_config=LLMGenConfig(
                system_prompt="You are a calculator.",
                prompt="${input}",
                multi_turn=True,
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        # Initialise chat thread and set output format
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
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
        response = client.table.regen_table_rows(
            table_type,
            MultiRowRegenRequest(
                table_id=table.id,
                row_ids=row_ids[3:4],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "4" in output, output
        # Test regen multiple rows
        # Also test if regen proceeds in correct order from earliest row to latest
        response = client.table.regen_table_rows(
            table_type,
            MultiRowRegenRequest(
                table_id=table.id,
                row_ids=row_ids[3:][::-1],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "4" in output, output
        assert "5" in output, output
        assert "8" in output, output


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
def test_convert_into_multi_turn(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input", dtype="str"),
        ColumnSchemaCreate(
            id="output",
            dtype="str",
            gen_config=LLMGenConfig(
                system_prompt="You are a calculator.",
                prompt="${input}",
                multi_turn=False,
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        # Initialise chat thread and set output format
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
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
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
                table_id=table.id,
                data=[dict(input="x += 1")],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "4" not in output, output
        # Convert into multi-turn
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=table.id,
                column_map=dict(
                    output=LLMGenConfig(
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
        assert isinstance(table, TableMetaResponse)
        # Regen
        rows = list_table_rows(client, table_type, table.id)
        response = client.table.regen_table_rows(
            table_type,
            MultiRowRegenRequest(
                table_id=table.id,
                row_ids=[rows.values[-1]["ID"]],
                stream=stream,
            ),
        )
        output = _collect_text(response, "output")
        assert "4" in output, output


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_get_conversation_thread(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input", dtype="str"),
        ColumnSchemaCreate(
            id="output",
            dtype="str",
            gen_config=LLMGenConfig(
                system_prompt="You are a calculator.",
                prompt="${input}",
                multi_turn=True,
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        # Initialise chat thread and set output format
        data = [
            dict(input="x = 0", output="0"),
            dict(input="Add 1", output="1"),
            dict(input="Add 2", output="3"),
            dict(input="Add 3", output="6"),
        ]
        response = client.table.add_table_rows(
            table_type, MultiRowAddRequest(table_id=table.id, data=data, stream=False)
        )
        row_ids = sorted([r.row_id for r in response.rows])

        def _check_thread(_chat):
            assert isinstance(_chat, ChatThreadResponse)
            for i, message in enumerate(_chat.thread):
                assert isinstance(message.content, str)
                assert len(message.content) > 0
                if i == 0:
                    assert message.role == ChatRole.SYSTEM
                elif i % 2 == 1:
                    assert message.role == ChatRole.USER
                    assert message.content == data[(i - 1) // 2]["input"]
                else:
                    assert message.role == ChatRole.ASSISTANT
                    assert message.content == data[(i // 2) - 1]["output"]

        # --- Fetch complete thread --- #
        chat = client.table.get_conversation_threads(
            table_type,
            table.id,
            ["output"],
        ).threads["output"]
        _check_thread(chat)
        assert len(chat.thread) == 9
        assert chat.thread[-1].content == "6"
        # --- Row ID filtering --- #
        # Filter (include = True)
        chat = client.table.get_conversation_threads(
            table_type,
            table.id,
            ["output"],
            row_id=row_ids[2],
        ).threads["output"]
        _check_thread(chat)
        assert len(chat.thread) == 7
        assert chat.thread[-1].content == "3"
        # Filter (include = False)
        chat = client.table.get_conversation_threads(
            table_type,
            table.id,
            ["output"],
            row_id=row_ids[2],
            include_row=False,
        ).threads["output"]
        _check_thread(chat)
        assert len(chat.thread) == 5
        assert chat.thread[-1].content == "1"
        # --- Non-existent column --- #
        with pytest.raises(
            ResourceNotFoundError,
            match="Column .*x.* is not found. Available multi-turn columns:.*output.*",
        ):
            client.table.get_conversation_threads(table_type, table.id, ["x"])
        # --- Invalid column --- #
        with pytest.raises(
            ResourceNotFoundError,
            match="Column .*input.* is not a multi-turn LLM column. Available multi-turn columns:.*output.*",
        ):
            client.table.get_conversation_threads(table_type, table.id, ["input"])


def test_hybrid_search(
    setup: ServingContext,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    table_type = TableType.KNOWLEDGE
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        data = dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="dummy")
        rows = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(Title="Resume 2012", Text="Hi there, I am a farmer.", **data)],
                stream=False,
            ),
        )
        assert isinstance(rows, MultiRowCompletionResponse)
        rows = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
                table_id=TABLE_ID_A,
                data=[dict(Title="Resume 2013", Text="Hi there, I am a carpenter.", **data)],
                stream=False,
            ),
        )
        assert isinstance(rows, MultiRowCompletionResponse)
        rows = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(
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
        assert isinstance(rows, MultiRowCompletionResponse)
        sleep(1)  # Optional, give it some time to index
        # Rely on embedding
        rows = client.table.hybrid_search(
            table_type,
            SearchRequest(
                table_id=TABLE_ID_A,
                query="language",
                reranking_model=_get_reranking_model(client),
                limit=2,
            ),
        )
        assert len(rows) == 2
        assert "BPE" in rows[0]["Text"]["value"], rows
        # Rely on FTS
        rows = client.table.hybrid_search(
            table_type,
            SearchRequest(
                table_id=TABLE_ID_A,
                query="candidate 2013",
                reranking_model=_get_reranking_model(client),
                limit=2,
            ),
        )
        assert len(rows) == 2
        assert "2013" in rows[0]["Title"]["value"], rows
        # hybrid_search without reranker (RRF only)
        rows = client.table.hybrid_search(
            table_type,
            SearchRequest(
                table_id=TABLE_ID_A,
                query="language",
                reranking_model=None,
                limit=2,
            ),
        )
        assert len(rows) == 2
        assert "BPE" in rows[0]["Text"]["value"], rows


FILE_PAGES = {
    FILES["salary 总结.pdf"]: 1,
    FILES["Swire_AR22_e_230406_sample.pdf"]: 5,
    FILES["1978_APL_FP_detrapping.PDF"]: 4,
    FILES["digital_scan_combined.pdf"]: 15,
    FILES["(2017.06.30) NMT in Linear Time (ByteNet).pptx"]: 3,
    FILES["Claims Form.xlsx"]: 2,
}


@pytest.mark.parametrize(
    "file_path",
    [
        FILES["salary 总结.pdf"],
        FILES["Swire_AR22_e_230406_sample.pdf"],
        # FILES["1978_APL_FP_detrapping.PDF"],
        # FILES["digital_scan_combined.pdf"],
        FILES["creative-story.md"],
        FILES["creative-story.txt"],
        FILES["RAG and LLM Integration Guide.html"],
        FILES["multilingual-code-examples.html"],
        FILES["table.html"],
        FILES["weather-forecast-service.xml"],
        FILES["company-profile.json"],
        FILES["llm-models.jsonl"],
        FILES["ChatMed_TCM-v0.2-5records.jsonl"],
        FILES["Recommendation Letter.docx"],
        FILES["(2017.06.30) NMT in Linear Time (ByteNet).pptx"],
        FILES["Claims Form.xlsx"],
        FILES["weather_observations.tsv"],
        FILES["company-profile.csv"],
        FILES["weather_observations_long.csv"],
    ],
    ids=lambda x: basename(x),
)
def test_embed_file(
    setup: ServingContext,
    file_path: str,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    table_type = TableType.KNOWLEDGE
    with _create_table(client, table_type, cols=[]) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        response = client.table.embed_file(file_path, table.id)
        assert isinstance(response, OkResponse)
        rows = list_table_rows(client, table_type, table.id)
        assert rows.total > 0
        assert rows.offset == 0
        assert rows.limit == 100
        assert len(rows.items) > 0
        for r in rows.values:
            assert isinstance(r["Title"], str)
            assert len(r["Title"]) > 0
            assert isinstance(r["Text"], str)
            assert len(r["Text"]) > 0
            assert r["Page"] > 0
            assert isinstance(r["Title Embed"], list)
            assert len(r["Title Embed"]) > 0
            assert all(isinstance(v, float) for v in r["Title Embed"])
            assert isinstance(r["Text Embed"], list)
            assert len(r["Text Embed"]) > 0
            assert all(isinstance(v, float) for v in r["Text Embed"])
        if file_path in FILE_PAGES:
            assert r["Page"] == FILE_PAGES[file_path]
        else:
            assert r["Page"] == 1


@pytest.mark.parametrize(
    "file_path",
    [
        FILES["empty.pdf"],
        FILES["empty_3pages.pdf"],
        FILES["empty.txt"],
        FILES["empty.csv"],
    ],
    ids=lambda x: basename(x),
)
def test_embed_empty_file(
    setup: ServingContext,
    file_path: str,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    table_type = TableType.KNOWLEDGE
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        with pytest.raises(BadInputError, match="is empty"):
            response = client.table.embed_file(file_path, table.id)
            assert isinstance(response, OkResponse)


@pytest.mark.parametrize(
    "file_path",
    [
        FILES["rabbit.jpeg"],
        join(dirname(dirname(TEST_FILE_DIR)), "pyproject.toml"),
    ],
    ids=lambda x: basename(x),
)
def test_embed_file_invalid_file_type(
    setup: ServingContext,
    file_path: str,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    table_type = TableType.KNOWLEDGE
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        with pytest.raises(JamaiException, match=r"File type .+ is unsupported"):
            client.table.embed_file(file_path, table.id)


def test_embed_file_options(setup: ServingContext):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

    response = client.table.embed_file_options()

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


def test_embed_long_file(
    setup: ServingContext,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, "knowledge", cols=[]) as table:
        assert isinstance(table, TableMetaResponse)
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
            assert isinstance(table, TableMetaResponse)
            assert all(isinstance(c, ColumnSchema) for c in table.cols)
            response = client.table.embed_file(file_path, table.id)
            assert isinstance(response, OkResponse)
            rows = list_table_rows(client, "knowledge", table.id)
            assert rows.total == 300
            assert rows.offset == 0
            assert rows.limit == 100
            assert len(rows.items) == 100
            assert all(isinstance(r["Title"], str) for r in rows.values)
            assert all(len(r["Title"]) > 0 for r in rows.values)
            assert all(isinstance(r["Text"], str) for r in rows.values)
            assert all(len(r["Text"]) > 0 for r in rows.values)
            assert all(r["Page"] > 0 for r in rows.values)
