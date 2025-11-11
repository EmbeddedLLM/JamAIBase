import re
from contextlib import contextmanager
from dataclasses import dataclass
from os.path import dirname, join, realpath
from typing import Generator

import pytest

from jamaibase import JamAI
from jamaibase.types import (
    ActionTableSchemaCreate,
    AddActionColumnSchema,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    CellCompletionResponse,
    ChatCompletionResponse,  # Assuming this might be needed for detailed checks later
    ChatTableSchemaCreate,
    ColumnDropRequest,
    ColumnRenameRequest,
    ColumnReorderRequest,
    ColumnSchema,
    ColumnSchemaCreate,
    DeploymentCreate,
    GenConfigUpdateRequest,
    KnowledgeTableSchemaCreate,
    MultiRowAddRequest,
    MultiRowCompletionResponse,
    OrganizationCreate,
    RAGParams,
    RowCompletionResponse,
    TableMetaResponse,
)
from owl.types import (
    CloudProvider,
    LLMGenConfig,
    Role,
    TableType,
)
from owl.utils.exceptions import (
    BadInputError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from owl.utils.test import (
    ELLM_EMBEDDING_CONFIG,
    ELLM_EMBEDDING_DEPLOYMENT,
    GPT_4O_MINI_CONFIG,
    GPT_4O_MINI_DEPLOYMENT,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_user,
    get_file_map,
    list_table_rows,
    upload_file,
)

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)
EMBEDDING_MODEL = "openai/text-embedding-3-small"
TABLE_TYPES = [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]
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
        create_organization(
            body=OrganizationCreate(name="Clubhouse"), user_id=superuser.id
        ) as org,
        # Create project
        create_project(dict(name="Bucket A"), user_id=superuser.id, organization_id=org.id) as p0,
    ):
        assert superuser.id == "0"
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
            create_model_config(
                {
                    "id": "openai/Qwen/Qwen-2-Audio-7B",
                    "type": "llm",
                    "name": "ELLM Qwen2 Audio (7B)",
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
                create_deployment(
                    DeploymentCreate(
                        model_id=llm_config_audio.id,
                        name="ELLM Qwen2 Audio (7B) Deployment",
                        provider=CloudProvider.ELLM,
                        routing_id=llm_config_audio.id,
                        api_base="https://llmci.embeddedllm.com/audio/v1",
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


def _get_image_models(client: JamAI) -> list[str]:
    models = client.model_ids(prefer="openai/gpt-4o-mini", capabilities=["image"])
    return models


def _get_chat_only_model(client: JamAI) -> str:
    chat_models = client.model_ids(capabilities=["chat"])
    image_models = _get_image_models(client)
    chat_only_models = [model for model in chat_models if model not in image_models]
    if not chat_only_models:
        pytest.skip("No chat-only model available for testing.")
    return chat_only_models[0]


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
                        max_tokens=300,
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
        try:
            client.table.delete_table(table_type, table_id)
        except ResourceNotFoundError:
            pass  # Ignore if already deleted


@contextmanager
def _create_table_v2(
    client: JamAI,
    table_type: TableType,
    table_id: str = TABLE_ID_A,
    cols: list[ColumnSchemaCreate] | None = None,
    chat_cols: list[ColumnSchemaCreate] | None = None,
    llm_model: str = "",
    embedding_model: str = "",
    system_prompt: str = "",
    prompt: str = "",
) -> Generator[TableMetaResponse, None, None]:
    try:
        if cols is None:
            _input_cols = [
                ColumnSchemaCreate(id=f"in_{dtype}", dtype=dtype)
                for dtype in REGULAR_COLUMN_DTYPES
            ]
            _output_cols = [
                ColumnSchemaCreate(
                    id=f"out_{dtype}",
                    dtype=dtype,
                    gen_config=LLMGenConfig(
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
                ColumnSchemaCreate(id="User", dtype="str"),
                ColumnSchemaCreate(
                    id="AI",
                    dtype="str",
                    gen_config=LLMGenConfig(
                        model=llm_model,
                        system_prompt=system_prompt,
                        max_tokens=10,
                    ),
                ),
            ]

        expected_cols = {"ID", "Updated at"}
        expected_cols |= {c.id for c in cols}
        if table_type == TableType.ACTION:
            table = client.table.create_action_table(
                ActionTableSchemaCreate(id=table_id, cols=cols)
            )
        elif table_type == TableType.KNOWLEDGE:
            table = client.table.create_knowledge_table(
                KnowledgeTableSchemaCreate(id=table_id, cols=cols, embedding_model=embedding_model)
            )
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == TableType.CHAT:
            table = client.table.create_chat_table(
                ChatTableSchemaCreate(id=table_id, cols=chat_cols + cols)
            )
            expected_cols |= {c.id for c in chat_cols}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, TableMetaResponse)
        col_ids = set(c.id for c in table.cols)
        assert col_ids == expected_cols
        yield table
    finally:
        try:
            client.table.delete_table(table_type, table_id)
        except Exception:
            pass  # Ignore if already deleted


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
        # Use a placeholder URI, actual file upload isn't needed for table ops tests
        data = dict(
            good=True,
            words=5,
            stars=7.9,
            inputs=TEXT,
            photo="rabbit.jpeg",
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
        # Consume the stream to ensure completion for tests that need data populated
        return response
        # list(response)
        # return None  # Streamed responses are handled differently
    assert isinstance(response, MultiRowCompletionResponse)
    assert len(response.rows) == 1
    return response.rows[0]


def _add_row_v2(
    client: JamAI,
    table_type: TableType,
    stream: bool,
    table_name: str = TABLE_ID_A,
    data: dict | None = None,
    knowledge_data: dict | None = None,
    chat_data: dict | None = None,
    include_output_data: bool = False,
) -> MultiRowCompletionResponse | None:
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
        # Consume the stream
        _ = list(response)
        # For simplicity in table ops tests, we might not need to reconstruct the full response
        return None
    assert isinstance(response, MultiRowCompletionResponse)
    assert response.object == "gen_table.completion.rows"
    assert len(response.rows) == 1
    return response


@contextmanager
def _rename_table(
    client: JamAI,
    table_type: TableType,
    table_id_src: str,
    table_id_dst: str,
):
    try:
        table = client.table.rename_table(table_type, table_id_src, table_id_dst)
        assert isinstance(table, TableMetaResponse)
        yield table
    finally:
        try:
            client.table.delete_table(table_type, table_id_dst)
        except ResourceNotFoundError:
            pass  # Ignore if already deleted


@contextmanager
def _duplicate_table(
    client: JamAI,
    table_type: TableType,
    table_id_src: str,
    table_id_dst: str,
    include_data: bool = True,
    create_as_child: bool = False,
):
    try:
        table = client.table.duplicate_table(
            table_type,
            table_id_src,
            table_id_dst,
            include_data=include_data,
            create_as_child=create_as_child,
        )
        assert isinstance(table, TableMetaResponse)
        yield table
    finally:
        try:
            client.table.delete_table(table_type, table_id_dst)
        except ResourceNotFoundError:
            pass  # Ignore if already deleted


@contextmanager
def _create_child_table(
    client: JamAI,
    table_type: TableType,
    table_id_src: str,
    table_id_dst: str | None,
):
    created_id = None
    try:
        table = client.table.duplicate_table(
            table_type, table_id_src, table_id_dst, create_as_child=True
        )
        created_id = table.id  # Store the actual ID created
        assert isinstance(table, TableMetaResponse)
        yield table
    finally:
        if created_id:
            try:
                client.table.delete_table(table_type, created_id)
            except ResourceNotFoundError:
                pass  # Ignore if already deleted


def _collect_text(
    responses: MultiRowCompletionResponse | Generator[ChatCompletionResponse, None, None],
    col: str,
):
    if isinstance(responses, MultiRowCompletionResponse):
        # Assuming only one row for simplicity in these tests
        if col in responses.rows[0].columns:
            return responses.rows[0].columns[col].content
        else:
            return ""  # Column might not exist (e.g., AI in non-chat table)
    # Handling stream (simplified for table ops)
    content = ""
    for r in responses:
        if hasattr(r, "output_column_name") and r.output_column_name == col:
            content += r.content
    return content


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize(
    "table_id", ["a", "0", "a.b", "a-b", "a_b", "a-_b", "a-_0b", "a.-_0b", "0_0"]
)
def test_create_table_valid_table_id(
    setup: ServingContext,
    table_type: TableType,
    table_id: str,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type, table_id) as table:
        assert isinstance(table, TableMetaResponse)
        assert table.id == table_id


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_table_valid_column_id(
    setup: ServingContext,
    table_type: TableType,
):
    table_id = TABLE_ID_A
    col_ids = ["a", "0", "a b", "a-b", "a_b", "a-_b", "a-_0b", "a -_0b", "0_0"]
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

    # --- Test input column --- #
    cols = [ColumnSchemaCreate(id=_id, dtype="str") for _id in col_ids]
    with _create_table(client, table_type, table_id, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        created_col_ids = {c.id for c in table.cols if c.id in col_ids}
        assert created_col_ids == set(col_ids)

    client.table.delete_table(table_type, table_id)
    # --- Test output column --- #
    cols = [
        ColumnSchemaCreate(
            id=_id,
            dtype="str",
            gen_config=LLMGenConfig(
                model="",
                system_prompt="You are a concise assistant.",
                prompt="Reply yes",
                temperature=0.001,
                top_p=0.001,
                max_tokens=3,
            ),
        )
        for _id in col_ids
    ]
    with _create_table(client, table_type, table_id, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        created_col_ids = {c.id for c in table.cols if c.id in col_ids}
        assert created_col_ids == set(col_ids)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize(
    "invalid_table_id", ["a_", "_a", "_aa", "aa_", "_a_", "-a", ".a", "a" * 101]
)
def test_create_table_invalid_table_id(
    setup: ServingContext,
    table_type: TableType,
    invalid_table_id: str,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [ColumnSchemaCreate(id="valid_col", dtype="str")]
    with pytest.raises(BadInputError):
        with _create_table(client, table_type, invalid_table_id, cols=cols):
            pass


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("column_id", ["a_", "_a", "_aa", "aa_", "_a_", "-a", ".a", "a" * 101])
def test_create_table_invalid_column_id(
    setup: ServingContext,
    table_type: TableType,
    column_id: str,
):
    table_id = TABLE_ID_A
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

    # --- Test input column --- #
    cols = [
        ColumnSchemaCreate(id=column_id, dtype="str"),
    ]
    with pytest.raises(BadInputError):
        with _create_table(client, table_type, table_id, cols=cols):
            pass

    # --- Test output column --- #
    cols = [
        ColumnSchemaCreate(
            id=column_id,
            dtype="str",
            gen_config=LLMGenConfig(),
        ),
    ]
    with pytest.raises(BadInputError):
        with _create_table(client, table_type, table_id, cols=cols):
            pass


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_table_invalid_model(
    setup: ServingContext,
    table_type: TableType,
):
    table_id = TABLE_ID_A
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input0", dtype="str"),
        ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=LLMGenConfig(model="INVALID_MODEL_ID"),
        ),
    ]
    with pytest.raises(BadInputError):
        with _create_table(client, table_type, table_id, cols=cols):
            pass


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_table_invalid_column_ref(
    setup: ServingContext,
    table_type: TableType,
):
    table_id = TABLE_ID_A
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input0", dtype="str"),
        ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=LLMGenConfig(prompt="Summarise ${input_non_existent}"),
        ),
    ]
    with pytest.raises(BadInputError):
        with _create_table(client, table_type, table_id, cols=cols):
            pass


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_table_invalid_rag(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

    # Create the knowledge table first
    with _create_table(client, TableType.KNOWLEDGE, TABLE_ID_B, cols=[]) as ktable:
        # --- Valid knowledge table ID --- #
        cols = [
            ColumnSchemaCreate(id="input0", dtype="str"),
            ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=LLMGenConfig(
                    rag_params=RAGParams(table_id=ktable.id),
                ),
            ),
        ]
        # --- Invalid knowledge table ID --- #
        cols = [
            ColumnSchemaCreate(id="input0", dtype="str"),
            ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=LLMGenConfig(
                    rag_params=RAGParams(table_id="INVALID_KT_ID"),
                ),
            ),
        ]
        with pytest.raises(BadInputError):
            with _create_table(client, table_type, cols=cols):
                pass

        # --- Valid reranker --- #
        cols = [
            ColumnSchemaCreate(id="input0", dtype="str"),
            ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=LLMGenConfig(
                    rag_params=RAGParams(
                        table_id=ktable.id, reranking_model=_get_reranking_model(client)
                    ),
                ),
            ),
        ]
        with _create_table(client, table_type, cols=cols) as table:
            assert isinstance(table, TableMetaResponse)

        # --- Invalid reranker --- #
        cols = [
            ColumnSchemaCreate(id="input0", dtype="str"),
            ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=LLMGenConfig(
                    rag_params=RAGParams(table_id=ktable.id, reranking_model="INVALID_RERANKER"),
                ),
            ),
        ]
        with pytest.raises(BadInputError):
            with _create_table(client, table_type, cols=cols):
                pass


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_default_llm_model(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input0", dtype="str"),
        ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=LLMGenConfig(),
        ),
        ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=None,
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        # Check gen configs
        cols_dict = {c.id: c for c in table.cols}
        assert isinstance(cols_dict["output0"].gen_config, LLMGenConfig)
        assert isinstance(cols_dict["output0"].gen_config.model, str)
        assert len(cols_dict["output0"].gen_config.model) > 0
        assert cols_dict["output1"].gen_config is None
        if table_type == TableType.CHAT:
            assert isinstance(cols_dict["AI"].gen_config, LLMGenConfig)
            assert isinstance(cols_dict["AI"].gen_config.model, str)
            assert len(cols_dict["AI"].gen_config.model) > 0

        # --- Update gen config --- #
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=TABLE_ID_A,
                column_map=dict(
                    output0=None,
                    output1=LLMGenConfig(),
                ),
            ),
        )
        assert isinstance(table, TableMetaResponse)
        # Check gen configs
        cols_dict = {c.id: c for c in table.cols}
        assert cols_dict["output0"].gen_config is None
        assert isinstance(cols_dict["output1"].gen_config, LLMGenConfig)
        assert isinstance(cols_dict["output1"].gen_config.model, str)
        assert len(cols_dict["output1"].gen_config.model) > 0
        if table_type == TableType.CHAT:
            assert isinstance(cols_dict["AI"].gen_config, LLMGenConfig)
            assert isinstance(cols_dict["AI"].gen_config.model, str)
            assert len(cols_dict["AI"].gen_config.model) > 0

        # --- Add column --- #
        add_cols = [
            ColumnSchemaCreate(
                id="output2",
                dtype="str",
                gen_config=None,
            ),
            ColumnSchemaCreate(
                id="output3",
                dtype="str",
                gen_config=LLMGenConfig(),
            ),
        ]
        if table_type == TableType.ACTION:
            table = client.table.add_action_columns(
                AddActionColumnSchema(id=table.id, cols=add_cols)
            )
        elif table_type == TableType.KNOWLEDGE:
            table = client.table.add_knowledge_columns(
                AddKnowledgeColumnSchema(id=table.id, cols=add_cols)
            )
        elif table_type == TableType.CHAT:
            table = client.table.add_chat_columns(AddChatColumnSchema(id=table.id, cols=add_cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        # Check gen configs
        cols_dict = {c.id: c for c in table.cols}
        assert cols_dict["output0"].gen_config is None
        assert isinstance(cols_dict["output1"].gen_config, LLMGenConfig)
        assert isinstance(cols_dict["output1"].gen_config.model, str)
        assert len(cols_dict["output1"].gen_config.model) > 0
        assert cols_dict["output2"].gen_config is None
        assert isinstance(cols_dict["output3"].gen_config, LLMGenConfig)
        assert isinstance(cols_dict["output3"].gen_config.model, str)
        assert len(cols_dict["output3"].gen_config.model) > 0
        if table_type == TableType.CHAT:
            assert isinstance(cols_dict["AI"].gen_config, LLMGenConfig)
            assert isinstance(cols_dict["AI"].gen_config.model, str)
            assert len(cols_dict["AI"].gen_config.model) > 0


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_default_image_model(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    available_image_models = _get_image_models(client)
    if not available_image_models:
        pytest.skip("No image model available for testing.")

    cols = [
        ColumnSchemaCreate(id="input0", dtype="image"),
        ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=LLMGenConfig(prompt="${input0}"),
        ),
        ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=None,
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        # Check gen configs
        cols_dict = {c.id: c for c in table.cols}
        assert isinstance(cols_dict["output0"].gen_config, LLMGenConfig)
        assert isinstance(cols_dict["output0"].gen_config.model, str)
        assert cols_dict["output0"].gen_config.model in available_image_models
        assert cols_dict["output1"].gen_config is None
        if table_type == TableType.CHAT:
            assert isinstance(cols_dict["AI"].gen_config, LLMGenConfig)
            assert isinstance(cols_dict["AI"].gen_config.model, str)
            # Default AI model might not be an image model if not needed
            # assert cols_dict["AI"].gen_config.model in available_image_models

        # --- Update gen config --- #
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=TABLE_ID_A,
                column_map=dict(
                    output0=None,
                    output1=LLMGenConfig(prompt="${input0}"),
                ),
            ),
        )
        assert isinstance(table, TableMetaResponse)
        # Check gen configs
        cols_dict = {c.id: c for c in table.cols}
        assert cols_dict["output0"].gen_config is None
        assert isinstance(cols_dict["output1"].gen_config, LLMGenConfig)
        assert isinstance(cols_dict["output1"].gen_config.model, str)
        assert cols_dict["output1"].gen_config.model in available_image_models

        # --- Add column --- #
        add_cols_1 = [
            ColumnSchemaCreate(
                id="output2",
                dtype="str",
                gen_config=LLMGenConfig(prompt="${input0}"),
            ),
            ColumnSchemaCreate(id="file_input1", dtype="image"),
            ColumnSchemaCreate(
                id="output3",
                dtype="str",
                gen_config=LLMGenConfig(prompt="${file_input1}"),
            ),
        ]
        if table_type == TableType.ACTION:
            table = client.table.add_action_columns(
                AddActionColumnSchema(id=table.id, cols=add_cols_1)
            )
        elif table_type == TableType.KNOWLEDGE:
            table = client.table.add_knowledge_columns(
                AddKnowledgeColumnSchema(id=table.id, cols=add_cols_1)
            )
        elif table_type == TableType.CHAT:
            table = client.table.add_chat_columns(
                AddChatColumnSchema(id=table.id, cols=add_cols_1)
            )
        else:
            raise ValueError(f"Invalid table type: {table_type}")

        # Add a column with default prompt (should pick image model if image inputs exist)
        add_cols_2 = [
            ColumnSchemaCreate(
                id="output4",
                dtype="str",
                gen_config=LLMGenConfig(),
            ),
        ]
        if table_type == TableType.ACTION:
            table = client.table.add_action_columns(
                AddActionColumnSchema(id=table.id, cols=add_cols_2)
            )
        elif table_type == TableType.KNOWLEDGE:
            table = client.table.add_knowledge_columns(
                AddKnowledgeColumnSchema(id=table.id, cols=add_cols_2)
            )
        elif table_type == TableType.CHAT:
            table = client.table.add_chat_columns(
                AddChatColumnSchema(id=table.id, cols=add_cols_2)
            )
        else:
            raise ValueError(f"Invalid table type: {table_type}")

        # Check gen configs
        cols_dict = {c.id: c for c in table.cols}
        assert cols_dict["output0"].gen_config is None
        for output_column_name in ["output1", "output2", "output3", "output4"]:
            assert isinstance(cols_dict[output_column_name].gen_config, LLMGenConfig)
            model = cols_dict[output_column_name].gen_config.model
            assert isinstance(model, str)
            assert model in available_image_models, (
                f'Column {output_column_name} has invalid default model "{model}". Valid: {available_image_models}'
            )


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_invalid_image_model(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    available_image_models = _get_image_models(client)
    if not available_image_models:
        pytest.skip("No image model available for testing.")
    try:
        chat_only_model = _get_chat_only_model(client)
    except IndexError:
        pytest.skip("No chat-only model available for testing.")

    cols = [
        ColumnSchemaCreate(id="input0", dtype="image"),
        ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=LLMGenConfig(model=chat_only_model, prompt="${input0}"),
        ),
    ]
    with pytest.raises(BadInputError):
        with _create_table(client, table_type, cols=cols):
            pass

    cols_valid = [
        ColumnSchemaCreate(id="input0", dtype="image"),
        ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=LLMGenConfig(prompt="${input0}"),
        ),
    ]
    with _create_table(client, table_type, cols=cols_valid) as table:
        assert isinstance(table, TableMetaResponse)
        # Check gen configs
        cols_dict = {c.id: c for c in table.cols}
        assert isinstance(cols_dict["output0"].gen_config, LLMGenConfig)
        assert isinstance(cols_dict["output0"].gen_config.model, str)
        assert cols_dict["output0"].gen_config.model in available_image_models

        # --- Update gen config --- #
        with pytest.raises(BadInputError):
            table = client.table.update_gen_config(
                table_type,
                GenConfigUpdateRequest(
                    table_id=TABLE_ID_A,
                    column_map=dict(
                        output0=LLMGenConfig(
                            model=chat_only_model,
                            prompt="${input0}",
                        ),
                    ),
                ),
            )
        # Ensure update with valid model works
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(
                table_id=TABLE_ID_A,
                column_map=dict(
                    output0=LLMGenConfig(prompt="${input0}"),
                ),
            ),
        )
        assert isinstance(table, TableMetaResponse)
        # Check gen configs
        cols_dict = {c.id: c for c in table.cols}
        assert isinstance(cols_dict["output0"].gen_config, LLMGenConfig)
        assert isinstance(cols_dict["output0"].gen_config.model, str)
        assert cols_dict["output0"].gen_config.model in available_image_models

        # --- Add column --- #
        add_cols = [
            ColumnSchemaCreate(
                id="output1",
                dtype="str",
                gen_config=LLMGenConfig(model=chat_only_model, prompt="${input0}"),
            )
        ]
        with pytest.raises(BadInputError):
            if table_type == TableType.ACTION:
                table = client.table.add_action_columns(
                    AddActionColumnSchema(id=table.id, cols=add_cols)
                )
            elif table_type == TableType.KNOWLEDGE:
                table = client.table.add_knowledge_columns(
                    AddKnowledgeColumnSchema(id=table.id, cols=add_cols)
                )
            elif table_type == TableType.CHAT:
                table = client.table.add_chat_columns(
                    AddChatColumnSchema(id=table.id, cols=add_cols)
                )
            else:
                raise ValueError(f"Invalid table type: {table_type}")


def test_default_embedding_model(
    setup: ServingContext,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, TableType.KNOWLEDGE, cols=[], embedding_model="") as table:
        assert isinstance(table, TableMetaResponse)
        for col in table.cols:
            if col.vlen == 0:
                continue
            assert len(col.gen_config.embedding_model) > 0


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_default_reranker(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # Create the knowledge table first
    with _create_table(client, TableType.KNOWLEDGE, TABLE_ID_B, cols=[]) as ktable:
        cols = [
            ColumnSchemaCreate(id="input0", dtype="str"),
            ColumnSchemaCreate(
                id="output0",
                dtype="str",
                gen_config=LLMGenConfig(
                    rag_params=RAGParams(table_id=ktable.id, reranking_model=""),
                ),
            ),
        ]
        with _create_table(client, table_type, cols=cols) as table:
            assert isinstance(table, TableMetaResponse)
            cols_dict = {c.id: c for c in table.cols}
            rag_params = cols_dict["output0"].gen_config.rag_params
            assert isinstance(rag_params, RAGParams)
            reranking_model = rag_params.reranking_model
            assert isinstance(reranking_model, str)
            assert len(reranking_model) > 0


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_default_prompts(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="input0", dtype="str"),
        ColumnSchemaCreate(id="input1", dtype="str"),
        ColumnSchemaCreate(
            id="output0",
            dtype="str",
            gen_config=LLMGenConfig(),  # Empty gen_config to trigger defaults
        ),
        ColumnSchemaCreate(
            id="output1",
            dtype="str",
            gen_config=LLMGenConfig(),  # Empty gen_config to trigger defaults
        ),
        ColumnSchemaCreate(
            id="output2",
            dtype="str",
            gen_config=LLMGenConfig(
                system_prompt="You are an assistant.",
                prompt="Summarise ${input0}.",
            ),
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        # Define expected input columns based on table type
        input_cols_set = {"input0", "input1"}
        if table_type == TableType.KNOWLEDGE:
            input_cols_set |= {"Title", "Text", "File ID", "Page"}
        elif table_type == TableType.CHAT:
            input_cols_set |= {"User"}

        cols_dict = {c.id: c for c in table.cols}

        # Check ["output0", "output1"] for default prompts referencing all inputs
        for col_id in ["output0", "output1"]:
            gen_config = cols_dict[col_id].gen_config
            assert isinstance(gen_config, LLMGenConfig)
            assert isinstance(gen_config.prompt, str)
            referenced_cols = set(re.findall(r"\$\{(\w+(?:\s\w+)*)\}", gen_config.prompt))
            # Default prompt should reference all non-ID, non-updated_at, non-output, non-vector columns
            expected_referenced = {
                c.id
                for c in table.cols
                if c.id not in ("ID", "Updated at")
                and c.gen_config is None
                and "Embed" not in c.id
            }
            assert referenced_cols == expected_referenced, (
                f"Col {col_id}: Expected {expected_referenced}, got {referenced_cols}"
            )

        # Check ["output2"] for provided prompts
        gen_config_2 = cols_dict["output2"].gen_config
        assert isinstance(gen_config_2, LLMGenConfig)
        assert gen_config_2.system_prompt == "You are an assistant."
        assert gen_config_2.prompt == "Summarise ${input0}."
        referenced_cols_2 = set(re.findall(r"\$\{(\w+(?:\s\w+)*)\}", gen_config_2.prompt))
        assert referenced_cols_2 == {"input0"}

        # --- Add column --- #
        add_cols = [
            ColumnSchemaCreate(
                id="input2",
                dtype="int",
            ),
            ColumnSchemaCreate(
                id="output3",
                dtype="str",
                gen_config=LLMGenConfig(),  # Trigger default prompt
            ),
        ]
        if table_type == TableType.ACTION:
            table = client.table.add_action_columns(
                AddActionColumnSchema(id=table.id, cols=add_cols)
            )
        elif table_type == TableType.KNOWLEDGE:
            table = client.table.add_knowledge_columns(
                AddKnowledgeColumnSchema(id=table.id, cols=add_cols)
            )
        elif table_type == TableType.CHAT:
            table = client.table.add_chat_columns(AddChatColumnSchema(id=table.id, cols=add_cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, TableMetaResponse)

        cols_dict = {c.id: c for c in table.cols}

        # Check ["output3"] for default prompt referencing all *current* inputs
        gen_config_3 = cols_dict["output3"].gen_config
        assert isinstance(gen_config_3, LLMGenConfig)
        assert isinstance(gen_config_3.prompt, str)
        referenced_cols_3 = set(re.findall(r"\$\{(\w+(?:\s\w+)*)\}", gen_config_3.prompt))
        expected_referenced_3 = {
            c.id
            for c in table.cols
            if c.id not in ("ID", "Updated at") and c.gen_config is None and "Embed" not in c.id
        }
        assert referenced_cols_3 == expected_referenced_3, (
            f"Col output3: Expected {expected_referenced_3}, got {referenced_cols_3}"
        )


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_add_drop_columns(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table_v2(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        _add_row_v2(
            client,
            table_type,
            stream=False,
            include_output_data=False,
        )

        # --- COLUMN ADD --- #
        _input_cols = [
            ColumnSchemaCreate(id=f"add_in_{dtype}", dtype=dtype)
            for dtype in REGULAR_COLUMN_DTYPES
        ]
        _output_cols = [
            ColumnSchemaCreate(
                id=f"add_out_{dtype}",
                dtype=dtype,
                gen_config=LLMGenConfig(
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
        if table_type == TableType.ACTION:
            table = client.table.add_action_columns(AddActionColumnSchema(id=table.id, cols=cols))
        elif table_type == TableType.KNOWLEDGE:
            table = client.table.add_knowledge_columns(
                AddKnowledgeColumnSchema(id=table.id, cols=cols)
            )
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == TableType.CHAT:
            expected_cols |= {"User", "AI"}
            table = client.table.add_chat_columns(AddChatColumnSchema(id=table.id, cols=cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        # Existing row of new columns should contain None
        rows = list_table_rows(client, table_type, table.id)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 1
        row = rows.values[0]
        for col_id, col in row.items():
            if not col_id.startswith("add_"):
                continue
            assert col is None
        # Test adding a new row
        data = {}
        for dtype in REGULAR_COLUMN_DTYPES:
            data[f"in_{dtype}"] = SAMPLE_DATA[dtype]
            data[f"out_{dtype}"] = SAMPLE_DATA[dtype]
            data[f"add_in_{dtype}"] = SAMPLE_DATA[dtype]
            data[f"add_out_{dtype}"] = SAMPLE_DATA[dtype]
        _add_row_v2(client, table_type, False, data=data)
        rows = list_table_rows(client, table_type, table.id)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 2
        row = rows.values[-1]
        for col_id, col in row.items():
            if not col_id.startswith("add_"):
                continue
            assert col is not None

        # --- COLUMN DROP --- #
        table = client.table.drop_columns(
            table_type,
            ColumnDropRequest(
                table_id=table.id,
                column_names=[f"in_{dtype}" for dtype in REGULAR_COLUMN_DTYPES]
                + [f"out_{dtype}" for dtype in ["str"]],
            ),
        )
        expected_cols = {"ID", "Updated at"}
        expected_cols |= {f"add_in_{dtype}" for dtype in REGULAR_COLUMN_DTYPES}
        expected_cols |= {f"add_out_{dtype}" for dtype in ["str"]}
        if table_type == TableType.ACTION:
            pass
        elif table_type == TableType.KNOWLEDGE:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == TableType.CHAT:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 2
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        # Test adding a new row
        _add_row_v2(client, table_type, False, data=data)
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 3
        assert all(set(r.keys()) == expected_cols for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_add_drop_file_column(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table_v2(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        _add_row_v2(
            client,
            table_type,
            stream=False,
            include_output_data=False,
        )

        # --- COLUMN ADD --- #
        cols = [
            ColumnSchemaCreate(id="add_in_file", dtype="image"),
            ColumnSchemaCreate(
                id="add_out_str",
                dtype="str",
                gen_config=LLMGenConfig(
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
        if table_type == TableType.ACTION:
            table = client.table.add_action_columns(AddActionColumnSchema(id=table.id, cols=cols))
        elif table_type == TableType.KNOWLEDGE:
            table = client.table.add_knowledge_columns(
                AddKnowledgeColumnSchema(id=table.id, cols=cols)
            )
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == TableType.CHAT:
            expected_cols |= {"User", "AI"}
            table = client.table.add_chat_columns(AddChatColumnSchema(id=table.id, cols=cols))
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        # Existing row of new columns should contain None
        rows = list_table_rows(client, table_type, table.id)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 1
        row = rows.values[0]
        for col_id, col in row.items():
            if not col_id.startswith("add_"):
                continue
            assert col is None
        # Test adding a new row
        upload_response = upload_file(client, FILES["rabbit.jpeg"])
        data = {"add_in_file": upload_response.uri}
        for dtype in REGULAR_COLUMN_DTYPES:
            data[f"in_{dtype}"] = SAMPLE_DATA[dtype]
        response = _add_row_v2(client, table_type, False, data=data)
        assert len(response.rows[0].columns["add_out_str"].content) > 0
        rows = list_table_rows(client, table_type, table.id)
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        assert len(rows.items) == 2
        row = rows.values[-1]
        for col_id, col in row.items():
            if not col_id.startswith("add_in_"):
                continue
            assert col is not None

        # Block file output column
        with pytest.raises(BadInputError):
            cols = [
                ColumnSchemaCreate(
                    id="add_out_file",
                    dtype="image",
                    gen_config=LLMGenConfig(
                        model="",
                        system_prompt="",
                        prompt="Describe image ${add_in_file}",
                        max_tokens=10,
                    ),
                ),
            ]
            if table_type == TableType.ACTION:
                client.table.add_action_columns(AddActionColumnSchema(id=table.id, cols=cols))
            elif table_type == TableType.KNOWLEDGE:
                client.table.add_knowledge_columns(
                    AddKnowledgeColumnSchema(id=table.id, cols=cols)
                )
            elif table_type == TableType.CHAT:
                client.table.add_chat_columns(AddChatColumnSchema(id=table.id, cols=cols))
            else:
                raise ValueError(f"Invalid table type: {table_type}")

        # --- COLUMN DROP --- #
        table = client.table.drop_columns(
            table_type,
            ColumnDropRequest(
                table_id=table.id,
                column_names=[f"in_{dtype}" for dtype in REGULAR_COLUMN_DTYPES]
                + [f"out_{dtype}" for dtype in ["str"]],
            ),
        )
        expected_cols = {"ID", "Updated at", "add_in_file", "add_out_str"}
        if table_type == TableType.ACTION:
            pass
        elif table_type == TableType.KNOWLEDGE:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == TableType.CHAT:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols, cols
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 2
        assert all(set(r.keys()) == expected_cols for r in rows.items)
        # Test adding a new row
        _add_row_v2(client, table_type, False, data={"add_in_file": upload_response.uri})
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 3
        assert all(set(r.keys()) == expected_cols for r in rows.items), [
            list(r.keys()) for r in rows.items
        ]


def test_kt_drop_invalid_columns(setup: ServingContext):
    table_type = "knowledge"
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        for col in KT_FIXED_COLUMN_IDS:
            with pytest.raises(BadInputError):
                client.table.drop_columns(
                    table_type,
                    ColumnDropRequest(table_id=table.id, column_names=[col]),
                )


def test_ct_drop_invalid_columns(setup: ServingContext):
    table_type = "chat"
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        for col in CT_FIXED_COLUMN_IDS:
            with pytest.raises(BadInputError):
                client.table.drop_columns(
                    table_type,
                    ColumnDropRequest(table_id=table.id, column_names=[col]),
                )


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_rename_columns(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="x", dtype="str"),
        ColumnSchemaCreate(
            id="y",
            dtype="str",
            gen_config=LLMGenConfig(prompt=r"Summarise ${x}, \${x}"),
        ),
    ]
    with _create_table(client, table_type, cols=cols) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        # Test rename on empty table
        table = client.table.rename_columns(
            table_type,
            ColumnRenameRequest(table_id=table.id, column_map=dict(y="z")),
        )
        assert isinstance(table, TableMetaResponse)
        expected_cols = {"ID", "Updated at", "x", "z"}
        if table_type == TableType.ACTION:
            pass
        elif table_type == TableType.KNOWLEDGE:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == TableType.CHAT:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols

        table = client.table.get_table(table_type, table.id)
        assert isinstance(table, TableMetaResponse)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols
        # Test adding data with new column names
        _add_row(client, table_type, False, data=dict(x="True", z="<dummy>"))
        # Test rename table with data
        # Test also auto gen config reference update
        table = client.table.rename_columns(
            table_type,
            ColumnRenameRequest(table_id=table.id, column_map=dict(x="a")),
        )
        assert isinstance(table, TableMetaResponse)
        expected_cols = {"ID", "Updated at", "a", "z"}
        if table_type == TableType.ACTION:
            pass
        elif table_type == TableType.KNOWLEDGE:
            expected_cols |= {"Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"}
        elif table_type == TableType.CHAT:
            expected_cols |= {"User", "AI"}
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols
        table = client.table.get_table(table_type, table.id)
        assert isinstance(table, TableMetaResponse)
        cols = set(c.id for c in table.cols)
        assert cols == expected_cols
        # Test auto gen config reference update
        cols = {c.id: c for c in table.cols}
        prompt = cols["z"].gen_config.prompt
        assert "${a}" in prompt
        assert "\\${x}" in prompt  # Escaped reference syntax

        # Repeated new column names
        with pytest.raises(ResourceExistsError):
            client.table.rename_columns(
                table_type,
                ColumnRenameRequest(table_id=table.id, column_map=dict(a="b", z="b")),
            )
        # Rename to existing column name
        with pytest.raises(ResourceExistsError):
            client.table.rename_columns(
                table_type,
                ColumnRenameRequest(table_id=table.id, column_map=dict(z="a")),
            )
        # Overlapping new and old column names is OK depending on rename order
        client.table.rename_columns(
            table_type,
            ColumnRenameRequest(table_id=table.id, column_map=dict(a="b", z="a")),
        )
        table = client.table.get_table(table_type, table.id)
        assert isinstance(table, TableMetaResponse)
        cols = set(c.id for c in table.cols)
        assert len({"ID", "Updated at", "b", "a"} - cols) == 0


def test_kt_rename_invalid_columns(setup: ServingContext):
    table_type = "knowledge"
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        for col in KT_FIXED_COLUMN_IDS:
            with pytest.raises(BadInputError):
                client.table.rename_columns(
                    table_type,
                    ColumnRenameRequest(table_id=table.id, column_map={col: col}),
                )


def test_ct_rename_invalid_columns(setup: ServingContext):
    table_type = "chat"
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        for col in CT_FIXED_COLUMN_IDS:
            with pytest.raises(BadInputError):
                client.table.rename_columns(
                    table_type,
                    ColumnRenameRequest(table_id=table.id, column_map={col: col}),
                )


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_reorder_columns(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        table = client.table.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, TableMetaResponse)

        column_names = [
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
        if table_type == TableType.ACTION:
            pass
        elif table_type == TableType.KNOWLEDGE:
            column_names += ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
            expected_order = (
                expected_order[:2]
                + ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
                + expected_order[2:]
            )
        elif table_type == TableType.CHAT:
            column_names += ["User", "AI"]
            expected_order = expected_order[:2] + ["User", "AI"] + expected_order[2:]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols
        # Test reorder empty table
        table = client.table.reorder_columns(
            table_type,
            ColumnReorderRequest(table_id=TABLE_ID_A, column_names=column_names),
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
        if table_type == TableType.ACTION:
            pass
        elif table_type == TableType.KNOWLEDGE:
            expected_order += ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
        elif table_type == TableType.CHAT:
            expected_order += ["User", "AI"]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols
        table = client.table.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, TableMetaResponse)
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols
        # Test add row
        response = _add_row(
            client,
            table_type,
            True,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT),
        )
        summary = _collect_text(list(response), "summary")
        assert len(summary) > 0


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_reorder_columns_invalid(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        assert all(isinstance(c, ColumnSchema) for c in table.cols)
        table = client.table.get_table(table_type, TABLE_ID_A)
        assert isinstance(table, TableMetaResponse)

        column_names = [
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
        if table_type == TableType.ACTION:
            pass
        elif table_type == TableType.KNOWLEDGE:
            column_names += ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
            expected_order = (
                expected_order[:2]
                + ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
                + expected_order[2:]
            )
        elif table_type == TableType.CHAT:
            column_names += ["User", "AI"]
            expected_order = expected_order[:2] + ["User", "AI"] + expected_order[2:]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        cols = [c.id for c in table.cols]
        assert cols == expected_order, cols

        # --- Test validation by putting "summary" on the left of "words" --- #
        column_names = [
            "ID",
            "Updated at",
            "inputs",
            "good",
            "stars",
            "summary",
            "words",
            "photo",
            "captioning",
        ]
        if table_type == TableType.ACTION:
            pass
        elif table_type == TableType.KNOWLEDGE:
            column_names += ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]
        elif table_type == TableType.CHAT:
            column_names += ["User", "AI"]
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        with pytest.raises(BadInputError):
            client.table.reorder_columns(
                table_type,
                ColumnReorderRequest(table_id=TABLE_ID_A, column_names=column_names),
            )


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_null_gen_config(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        table = client.table.update_gen_config(
            table_type,
            GenConfigUpdateRequest(table_id=table.id, column_map=dict(summary=None)),
        )
        response = _add_row(
            client, table_type, stream, data=dict(good=True, words=5, stars=9.9, inputs=TEXT)
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, CellCompletionResponse) for r in responses)
        else:
            assert isinstance(response, RowCompletionResponse)
        rows = list_table_rows(client, table_type, table.id)
        assert len(rows.items) == 1
        row = rows.values[0]
        assert row["summary"] is None


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_invalid_referenced_column(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # --- Non-existent column --- #
    cols = [
        ColumnSchemaCreate(id="words", dtype="int"),
        ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client),
                system_prompt="You are a concise assistant.",
                prompt="Summarise ${inputs}",
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    with pytest.raises(BadInputError):
        with _create_table(client, table_type, cols=cols):
            pass

    # --- Vector column --- #
    cols = [
        ColumnSchemaCreate(id="words", dtype="int"),
        ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client),
                system_prompt="You are a concise assistant.",
                prompt="Summarise ${Text Embed}",
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ).model_dump(),
        ),
    ]
    with pytest.raises(BadInputError):
        with _create_table(client, table_type, cols=cols):
            pass


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
def test_gen_config_empty_prompts(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="words", dtype="int"),
        ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client),
                temperature=0.001,
                top_p=0.001,
                max_tokens=10,
            ),
        ),
    ]
    chat_cols = [
        ColumnSchemaCreate(id="User", dtype="str"),
        ColumnSchemaCreate(
            id="AI",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client),
                temperature=0.001,
                top_p=0.001,
                max_tokens=5,
            ),
        ),
    ]
    with _create_table(client, table_type, cols=cols, chat_cols=chat_cols) as table:
        assert isinstance(table, TableMetaResponse)
        data = dict(words=5)
        if table_type == TableType.KNOWLEDGE:
            data["Title"] = "Dune: Part Two."
            data["Text"] = "Dune: Part Two is a 2024 American epic science fiction film."
        response = client.table.add_table_rows(
            table_type,
            MultiRowAddRequest(table_id=table.id, data=[data], stream=stream),
        )
        if stream:
            # Must wait until stream ends
            responses = [r for r in response]
            assert all(isinstance(r, CellCompletionResponse) for r in responses)
            summary = "".join(r.content for r in responses if r.output_column_name == "summary")
            assert len(summary) > 0
            if table_type == TableType.CHAT:
                ai = "".join(r.content for r in responses if r.output_column_name == "AI")
                assert len(ai) > 0
        else:
            assert isinstance(response.rows[0], RowCompletionResponse)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_table_search_and_parent_id(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # _delete_tables(client)
    with (
        _create_table(client, table_type, "beast") as table,
        _create_table(client, table_type, "feast"),
        _create_table(client, table_type, "bear"),
        _create_table(client, table_type, "fear"),
    ):
        assert isinstance(table, TableMetaResponse)
        with (
            _create_child_table(client, table_type, "beast", "least"),
            _create_child_table(client, table_type, "beast", "lease"),
            _create_child_table(client, table_type, "beast", "yeast"),
        ):
            # Regular list
            tables = client.table.list_tables(table_type, limit=3)
            assert isinstance(tables.items, list)
            assert tables.total == 7
            assert tables.offset == 0
            assert tables.limit == 3
            assert len(tables.items) == 3
            assert all(isinstance(r, TableMetaResponse) for r in tables.items)
            # Search
            tables = client.table.list_tables(table_type, search_query="be", limit=3)
            assert isinstance(tables.items, list)
            assert tables.total == 2
            assert tables.offset == 0
            assert tables.limit == 3
            assert len(tables.items) == 2
            assert all(isinstance(r, TableMetaResponse) for r in tables.items)
            # Search
            tables = client.table.list_tables(table_type, search_query="ast", limit=3)
            assert isinstance(tables.items, list)
            assert tables.total == 4
            assert tables.offset == 0
            assert tables.limit == 3
            assert len(tables.items) == 3
            assert all(isinstance(r, TableMetaResponse) for r in tables.items)
            # Search with parent ID
            tables = client.table.list_tables(table_type, search_query="ast", parent_id="beast")
            assert isinstance(tables.items, list)
            assert tables.total == 2
            assert tables.offset == 0
            assert tables.limit == 100
            assert len(tables.items) == 2
            assert all(isinstance(r, TableMetaResponse) for r in tables.items)
            # Search with parent ID
            tables = client.table.list_tables(table_type, search_query="as", parent_id="beast")
            assert isinstance(tables.items, list)
            assert tables.total == 3
            assert tables.offset == 0
            assert tables.limit == 100
            assert len(tables.items) == 3
            assert all(isinstance(r, TableMetaResponse) for r in tables.items)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_duplicate_table(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        _add_row(
            client,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )

        # Duplicate with data
        with _duplicate_table(client, table_type, TABLE_ID_A, TABLE_ID_B) as table:
            # Add another to table A
            _add_row(
                client,
                table_type,
                False,
                table_name=TABLE_ID_A,
                data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
            )
            assert table.id == TABLE_ID_B
            rows = list_table_rows(client, table_type, TABLE_ID_B)
            assert len(rows.items) == 1

        # Duplicate without data
        with _duplicate_table(
            client, table_type, TABLE_ID_A, TABLE_ID_C, include_data=False
        ) as table:
            assert table.id == TABLE_ID_C
            rows = list_table_rows(client, table_type, TABLE_ID_C)
            assert len(rows.items) == 0

        # # Deploy with data
        # with _duplicate_table(client, table_type, TABLE_ID_A, TABLE_ID_B, deploy=True) as table:
        #     assert table.id == TABLE_ID_B
        #     assert table.parent_id == TABLE_ID_A
        #     rows = list_table_rows(client,table_type, TABLE_ID_B)
        #     assert len(rows.items) == 2

        # # Deploy will always include data
        # with _duplicate_table(
        #     client, table_type, TABLE_ID_A, TABLE_ID_C, deploy=True, include_data=False
        # ) as table:
        #     assert table.id == TABLE_ID_C
        #     assert table.parent_id == TABLE_ID_A
        #     rows = list_table_rows(client,table_type, TABLE_ID_C)
        #     assert len(rows.items) == 2


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("table_id_dst", ["Y", None])
@pytest.mark.parametrize("include_data", [True, False])
@pytest.mark.parametrize("create_as_child", [True, False])
def test_duplicate_table_nonexistent(
    setup: ServingContext,
    table_type: TableType,
    table_id_dst: str | None,
    include_data: bool,
    create_as_child: bool,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with pytest.raises(ResourceNotFoundError):
        client.table.duplicate_table(
            table_type,
            "X",
            table_id_dst,
            include_data=include_data,
            create_as_child=create_as_child,
        )


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize(
    "table_id_dst",
    ["a_", "_a", "_aa", "aa_", "_a_", "-a", ".a", "a" * 101],
)
def test_duplicate_table_invalid_name(
    setup: ServingContext,
    table_type: TableType,
    table_id_dst: str,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table:
        assert isinstance(table, TableMetaResponse)
        _add_row(
            client,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )

        with pytest.raises(BadInputError):
            with _duplicate_table(client, table_type, TABLE_ID_A, table_id_dst):
                pass


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_create_child_table(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type) as table_a:
        assert isinstance(table_a, TableMetaResponse)
        _add_row(
            client,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )
        # Duplicate with data
        with _create_child_table(client, table_type, TABLE_ID_A, TABLE_ID_B) as table_b:
            assert isinstance(table_b, TableMetaResponse)
            # Add another to table A
            _add_row(
                client,
                table_type,
                False,
                data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
            )
            assert table_b.id == TABLE_ID_B
            # Ensure the the parent id meta data has been correctly set.
            assert table_b.parent_id == TABLE_ID_A
            rows = list_table_rows(client, table_type, TABLE_ID_B)
            assert len(rows.items) == 1

        # Create child table with no dst id
        with _create_child_table(client, table_type, TABLE_ID_A, None) as table_c:
            assert isinstance(table_c.id, str)
            assert table_c.id.startswith(TABLE_ID_A)
            assert table_c.id != TABLE_ID_A
            # Ensure the the parent id meta data has been correctly set.
            assert table_c.parent_id == TABLE_ID_A
            rows = list_table_rows(client, table_type, table_c.id)
            assert len(rows.items) == 2


@pytest.mark.parametrize("table_type", TABLE_TYPES)
def test_rename_table(
    setup: ServingContext,
    table_type: TableType,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    with _create_table(client, table_type, TABLE_ID_A) as table:
        assert isinstance(table, TableMetaResponse)
        _add_row(
            client,
            table_type,
            False,
            data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
        )
        # Create child table
        with _create_child_table(client, table_type, TABLE_ID_A, TABLE_ID_B) as child:
            assert isinstance(child, TableMetaResponse)
            # Rename
            with _rename_table(client, table_type, TABLE_ID_A, TABLE_ID_C) as table:
                rows = list_table_rows(client, table_type, TABLE_ID_C)
                assert len(rows.items) == 1
                # Assert the old table is gone
                with pytest.raises(ResourceNotFoundError):
                    list_table_rows(client, table_type, TABLE_ID_A)
                # Assert the child table parent ID is updated
                assert client.table.get_table(table_type, child.id).parent_id == TABLE_ID_C
                # Add rows to both tables
                _add_row(
                    client,
                    table_type,
                    False,
                    TABLE_ID_B,
                    data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
                )
                _add_row(
                    client,
                    table_type,
                    False,
                    TABLE_ID_C,
                    data=dict(good=True, words=5, stars=9.9, inputs=TEXT, summary="<dummy>"),
                )


def test_chat_table_gen_config(
    setup: ServingContext,
):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    cols = [
        ColumnSchemaCreate(id="User", dtype="str"),
        ColumnSchemaCreate(
            id="AI",
            dtype="str",
            gen_config=LLMGenConfig(
                model=_get_chat_model(client),
                system_prompt="You are a concise assistant.",
                multi_turn=False,
                temperature=0.001,
                top_p=0.001,
                max_tokens=20,
            ),
        ),
    ]
    with _create_table(client, "chat", cols=[], chat_cols=cols) as table:
        cfg_map = {c.id: c.gen_config for c in table.cols}
        # AI column gen config will be multi turn regardless of input params
        assert cfg_map["AI"].multi_turn is True
