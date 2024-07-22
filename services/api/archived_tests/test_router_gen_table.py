import random

import httpx
import pytest
from httpx import Timeout
from loguru import logger

from owl.protocol import (
    ColumnDropRequest,
    ColumnRenameRequest,
    ColumnReorderRequest,
    ColumnSchemaCreate,
    GenConfigUpdateRequest,
    Page,
    RowAddRequest,
    RowDeleteRequest,
    RowRegenRequest,
    RowUpdateRequest,
    TableMetaResponse,
    TableSchemaCreate,
    TableType,
)

BASE_TMP_DIR = "db"
BASE_URL = "http://localhost:7770/api"


@pytest.fixture
def client():
    yield httpx.Client(transport=httpx.HTTPTransport(retries=3), timeout=Timeout(5 * 60))


def _create_table(
    client, table_type: TableType, cols_info: tuple[dict[str, str], dict[str, str]] = None
):
    table_id = f"{table_type.value}_{random.randint(10000, 99999)}"
    schema = TableSchemaCreate(
        id=table_id,
        cols=(
            [
                ColumnSchemaCreate(id="article 1", dtype="str"),
                ColumnSchemaCreate(id="summary", dtype="str"),
            ]
            if cols_info is None
            else (
                [ColumnSchemaCreate(id=k, dtype=v) for k, v in cols_info[0].items()]
                + [ColumnSchemaCreate(id=k, dtype=v) for k, v in cols_info[1].items()]
            )
        ),
    )
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{table_type.value}", json=schema.model_dump()
    )
    response.raise_for_status()
    meta = TableMetaResponse(**response.json())
    return meta, table_id


def _add_row(client, table_type: TableType, table_id: str, row=dict[str, str]):
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{table_type.value}/rows/add",
        json=RowAddRequest(table_id=table_id, data=row, stream=False).model_dump(),
    )
    response.raise_for_status()
    logger.info(response.json())
    return


def _update_gen_config(client, gen_config: GenConfigUpdateRequest):
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/gen_config/update",
        json=gen_config.model_dump(),
    )
    response.raise_for_status()


# passed, TODO: check create chat table
def test_create_table(client):
    meta, table_id = _create_table(client, TableType.action)
    assert meta.id == table_id
    assert meta.num_rows == 0

    meta, table_id = _create_table(client, TableType.knowledge)
    assert meta.id == table_id
    assert meta.num_rows == 0

    # meta, table_id = _create_table(client, TableType.chat)
    # assert meta.id == table_id
    # assert meta.num_rows == 0


# passed, TODO: check list chat table
def test_list_tables(client):
    for table_type in (TableType.action, TableType.knowledge, TableType.chat):
        if table_type is TableType.chat:  # temp
            continue
        meta, table_id = _create_table(client, table_type)
        response = client.get(f"{BASE_URL}/v1/gen_tables/{table_type.value}")
        response.raise_for_status()
        page = Page[TableMetaResponse](**response.json())
        # assert len(page.items) == 1
        assert page.items[0].id == table_id


# passed
def test_get_table(client):
    meta, table_id = _create_table(client, TableType.action)
    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}")
    response.raise_for_status()
    meta = TableMetaResponse(**response.json())
    assert meta.id == table_id
    assert meta.num_rows == 0


# passed
def test_duplicate_table(client):
    meta, table_id = _create_table(client, TableType.action)

    # Duplicate table
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/duplicate/{table_id}/documents_copy"
    )
    response.raise_for_status()
    new_meta = TableMetaResponse(**response.json())
    assert new_meta.id == "documents_copy"
    assert new_meta.parent_id is None

    # Duplicate table with deploy
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/duplicate/{table_id}/documents_deploy?deploy=True"
    )
    response.raise_for_status()
    new_meta = TableMetaResponse(**response.json())
    assert new_meta.id == "documents_deploy"
    assert new_meta.parent_id == meta.id

    # Duplicate table with schema only
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/duplicate/{table_id}/documents_schema?include_data=False"
    )
    response.raise_for_status()
    new_meta = TableMetaResponse(**response.json())
    assert new_meta.id == "documents_schema"
    assert new_meta.parent_id is None


# passed
def test_rename_table(client):
    meta, table_id = _create_table(client, TableType.action)

    # Rename table
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/rename/{table_id}/documents_renamed"
    )
    response.raise_for_status()
    new_meta = TableMetaResponse(**response.json())
    assert new_meta.id == "documents_renamed"


# passed
def test_delete_table(client):
    meta, table_id = _create_table(client, TableType.action)

    # Delete table
    response = client.delete(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}")
    response.raise_for_status()


# passed
def test_update_gen_config(client):
    meta, table_id = _create_table(client, TableType.action)

    # Update generation config
    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "summary": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {"role": "user", "content": "Summarize ${article 1}"},
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 2000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)


# passed
def test_add_rows(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Article 1": "str", "Article 2": "str"},
            {"Summary 1": "str", "Summary 2": "str", "Overall Rewrite": "str"},
        ),
    )

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Summary 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {"role": "user", "content": "Summarize ${Article 1}"},
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Summary 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {"role": "user", "content": "Summarize ${Article 2}"},
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Overall Rewrite": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "[Summary 1]:\n ${Summary 1} \n\n [Summary 2]:\n ${Summary 2} \n\n Understand Summary 1 and Summary 2, rewrite them.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 2000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    rows = [
        {
            "Article 1": "Arrival is a 2016 science fiction drama film",
            "Article 2": "Arrival is not a 2026 science fiction drama film",
        },
        {
            "Article 1": "llama-3-70B is as good or better than sonnet but ~10x cheaper, about as cheap as Haiku. Llama has just demolished everything below gpt-4 level",
            "Article 2": "llama-3-70B is as good or better than sonnet but ~10x cheaper, about as cheap as Haiku. Llama has just demolished everything below gpt-4 level",
        },
    ]
    for row in rows:
        _add_row(client, TableType.action, table_id, row)


# passed
def test_get_rows(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Article 1": "str", "Article 2": "str"},
            {},
        ),
    )
    row_count = 3
    for _ in range(row_count):
        _add_row(
            client,
            TableType.action,
            table_id,
            row={"Article 1": "random text", "Article 2": "another random text"},
        )

    # Get rows
    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == row_count

    # Get specific row
    row_id = page.items[0]["ID"]
    response = client.get(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows/{row_id}"
    )
    response.raise_for_status()


# passed
def test_add_columns(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Article 1": "str", "Article 2": "str"},
            {},
        ),
    )
    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Article 1": "random text", "Article 2": "another random text"},
    )

    # Add columns
    schema = TableSchemaCreate(
        id=table_id,
        cols=[
            ColumnSchemaCreate(id="title", dtype="str"),
            ColumnSchemaCreate(id="page", dtype="int"),
        ],
    )
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/add",
        json=schema.model_dump(),
    )
    response.raise_for_status()


# passed
def test_add_columns_and_add_rows(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str"},
            {
                "Story 1": "str",
                "Story 2": "str",
            },
        ),
    )
    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Story 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Meguro"},
    )

    # Add columns
    schema = TableSchemaCreate(
        id=table_id,
        cols=[
            ColumnSchemaCreate(id="Keyword 3", dtype="str"),
            ColumnSchemaCreate(id="Story 3", dtype="str", gen_config={}),
            ColumnSchemaCreate(id="Title Story 3", dtype="str", gen_config={}),
        ],
    )
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/add",
        json=schema.model_dump(),
    )
    response.raise_for_status()

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 3": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 3}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Title Story 3": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Read story: '${Story 3}' \n\n. Generate a title.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Dragon Torii Shrine", "Keyword 2": "Sakura", "Keyword 3": "Sensoji"},
    )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 2


# passed
def test_drop_columns(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Article 1": "str", "Article 2": "str"},
            {},
        ),
    )
    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Article 1": "random text", "Article 2": "another random text"},
    )

    # Drop columns
    body = ColumnDropRequest(table_id=table_id, column_names=["Article 2"])
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/drop",
        json=body.model_dump(),
    )
    response.raise_for_status()


# passed
def test_drop_column_and_add_row(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Article 1": "str", "Article 2": "str"},
            {},
        ),
    )
    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Article 1": "random text", "Article 2": "another random text"},
    )

    # Drop columns
    body = ColumnDropRequest(table_id=table_id, column_names=["Article 2"])
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/drop",
        json=body.model_dump(),
    )
    response.raise_for_status()

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Article 1": "random text next row"},
    )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 2


# passed
def test_drop_last_output_column_and_add_row(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str"},
            {"Story 1": "str", "Story 2": "str", "Summary": "str"},
        ),
    )

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Story 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Summary": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "[Story 1]:\n ${Story 1} \n\n [Story 2]:\n ${Story 2} \n\n Understand Story 1 and Story 2, summarize them.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 2000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )

    # Drop columns
    body = ColumnDropRequest(table_id=table_id, column_names=["Summary"])
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/drop",
        json=body.model_dump(),
    )
    response.raise_for_status()

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 1

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Mobile Phone", "Keyword 2": "eSim"},
    )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 2


# TODO: issue - lance db can't find the last column when list row (table.search())
# OSError: Io error: Execution error: LanceError(Arrow): Schema error: field Summary does not exist in the RecordBatch, /home/runner/work/lance/lance/rust/lance/src/dataset/fragment.rs:900:12
# Hot Fixed by duplicate table and copy non-dropping columns
def test_drop_output_column_and_add_row(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str"},
            {"Story 1": "str", "Story 2": "str", "Summary": "str"},
        ),
    )

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' and '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Story 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Summary": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Understand ${Story 1}, summarize it.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 2000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )

    # Drop columns
    body = ColumnDropRequest(table_id=table_id, column_names=["Story 2"])
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/drop",
        json=body.model_dump(),
    )
    response.raise_for_status()

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 1

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Mobile Phone", "Keyword 2": "eSim"},
    )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 2


# TODO: issue - lance db can't find the last column when list row (table.search())
# Hot Fixed by duplicate table and copy non-dropping columns
def test_empty_table_drop_input_column_and_add_row(client):
    # meta, table_id = _create_table(
    #     client,
    #     TableType.action,
    #     cols_info=(
    #         {"Keyword 1": "str", "Keyword 2": "str", "Keyword 3": "str"},
    #         {"Story": "str", "Summary": "str"},
    #     ),
    # )
    # response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    # response.raise_for_status()
    # page = Page[dict](**response.json())
    # assert len(page.items) == 0

    # # Drop columns
    # body = ColumnDropRequest(table_id=table_id, column_names=["Keyword 3"])
    # response = client.post(
    #     f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/drop",
    #     json=body.model_dump(),
    # )
    # response.raise_for_status()

    # response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    # response.raise_for_status()
    # page = Page[dict](**response.json())
    # assert len(page.items) == 0

    # gen_config = GenConfigUpdateRequest(
    #     table_id=table_id,
    #     column_map={
    #         "Story": {
    #             "id": "",
    #             "model": "openai/gpt-3.5-turbo",
    #             "messages": [
    #                 {
    #                     "role": "system",
    #                     "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
    #                 },
    #                 {"role": "user", "content": "Use word '${Keyword 1}' and '${Keyword 2}' to create a short story."},
    #             ],
    #             "functions": [],
    #             "function_call": "auto",
    #             "temperature": 0.1,
    #             "top_p": 0.01,
    #             "stream": False,
    #             "stop": [],
    #             "max_tokens": 1000,
    #             "presence_penalty": 0,
    #             "frequency_penalty": 0,
    #         },
    #         "Summary": {
    #             "id": "",
    #             "model": "openai/gpt-3.5-turbo",
    #             "messages": [
    #                 {
    #                     "role": "system",
    #                     "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
    #                 },
    #                 {
    #                     "role": "user",
    #                     "content": "Summarize ${Story}.",
    #                 },
    #             ],
    #             "functions": [],
    #             "function_call": "auto",
    #             "temperature": 0.1,
    #             "top_p": 0.01,
    #             "stream": False,
    #             "stop": [],
    #             "max_tokens": 2000,
    #             "presence_penalty": 0,
    #             "frequency_penalty": 0,
    #         },
    #     },
    # )
    # _update_gen_config(client, gen_config)

    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str", "Keyword 3": "str"},
            {"Story": "str"},
        ),
    )
    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 0

    # Drop columns
    body = ColumnDropRequest(table_id=table_id, column_names=["Keyword 3"])
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/drop",
        json=body.model_dump(),
    )
    response.raise_for_status()

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 0

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' and '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Sakura"},
    )
    logger.info(meta)

    # _add_row(
    #     client,
    #     TableType.action,
    #     table_id,
    #     row={"Keyword 1": "Mobile Phone", "Keyword 2": "eSim"},
    # )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 1


# passed
def test_rename_columns(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str"},
            {"Story 1": "str", "Story 2": "str"},
        ),
    )

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' and '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Story 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )

    # Rename columns
    body = ColumnRenameRequest(
        table_id=table_id, column_map={"Story 1": "Short Story 1", "Story 2": "Short Story 2"}
    )
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/rename",
        json=body.model_dump(),
    )
    response.raise_for_status()

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Sakura", "Keyword 2": "Akihabara"},
    )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 2


# passed
def test_reorder_columns(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str"},
            {"Story 1": "str", "Story 2": "str"},
        ),
    )

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' and '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Story 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )
    # Reorder columns
    body = ColumnReorderRequest(
        table_id=table_id, column_names=["Keyword 1", "Keyword 2", "Story 2", "Story 1"]
    )
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/reorder",
        json=body.model_dump(),
    )
    response.raise_for_status()

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Sakura", "Keyword 2": "Akihabara"},
    )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 2

    # Reorder again
    body = ColumnReorderRequest(
        table_id=table_id, column_names=["Story 1", "Story 2", "Keyword 1", "Keyword 2"]
    )
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/columns/reorder",
        json=body.model_dump(),
    )
    response.raise_for_status()

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Sakura", "Keyword 2": "Akihabara"},
    )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 3


# passed
def test_update_row(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str"},
            {"Story 1": "str", "Story 2": "str"},
        ),
    )

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' and '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Story 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 0.1,
                "top_p": 0.01,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )
    # Update row
    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    row_id = page.items[0]["ID"]

    body = RowUpdateRequest(
        table_id=table_id,
        row_id=row_id,
        data={"Keyword 2": "Osaka"},
    )
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/rows/update",
        json=body.model_dump(),
    )
    response.raise_for_status()

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 1
    assert page.items[0]["Keyword 2"] == "Osaka"


# TODO: fix issue - db/gen_executor.py", line 96, in gen_row (if col_id in self.body.data:)
# AttributeError: 'RowRegenRequest' object has no attribute 'data'
def test_regen_row(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str"},
            {"Story 1": "str", "Story 2": "str"},
        ),
    )

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' and '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 1.0,
                "top_p": 0.1,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Story 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 1.0,
                "top_p": 0.1,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    first_result = {"Story 1": page.items[0]["Story 1"], "Story 2": page.items[0]["Story 2"]}
    assert len(page.items) == 1
    # Regen row
    row_id = page.items[0]["ID"]

    body = RowRegenRequest(table_id=table_id, row_id=row_id, stream=False)
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/rows/regen",
        json=body.model_dump(),
    )
    response.raise_for_status()

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    second_result = {"Story 1": page.items[0]["Story 1"], "Story 2": page.items[0]["Story 2"]}
    assert len(page.items) == 1
    assert first_result["Story 1"] != second_result["Story 1"]
    assert first_result["Story 2"] != second_result["Story 2"]


# passed
def test_delete_rows(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str"},
            {"Story 1": "str", "Story 2": "str"},
        ),
    )

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' and '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 1.0,
                "top_p": 0.1,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Story 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 1.0,
                "top_p": 0.1,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )
    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )
    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Two Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )
    # Delete rows
    body = RowDeleteRequest(table_id=table_id, where="`Keyword 1` = 'Torii Shrine'")
    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/rows/delete",
        json=body.model_dump(),
    )
    response.raise_for_status()

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 1


# passed
def test_delete_row(client):
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            {"Keyword 1": "str", "Keyword 2": "str"},
            {"Story 1": "str", "Story 2": "str"},
        ),
    )

    gen_config = GenConfigUpdateRequest(
        table_id=table_id,
        column_map={
            "Story 1": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 1}' and '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 1.0,
                "top_p": 0.1,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            "Story 2": {
                "id": "",
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an artificial intelligent assistant created by EmbeddedLLM. You should give helpful, detailed, and polite answers to the human's questions.",
                    },
                    {
                        "role": "user",
                        "content": "Use word '${Keyword 2}' to create a short story.",
                    },
                ],
                "functions": [],
                "function_call": "auto",
                "temperature": 1.0,
                "top_p": 0.1,
                "stream": False,
                "stop": [],
                "max_tokens": 1000,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
        },
    )
    _update_gen_config(client, gen_config)

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    row_id = page.items[0]["ID"]

    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Dragon Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )
    _add_row(
        client,
        TableType.action,
        table_id,
        row={"Keyword 1": "Dragon Torii Shrine", "Keyword 2": "Fox with Sakura"},
    )

    # Delete row
    response = client.delete(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows/{row_id}"
    )
    response.raise_for_status()

    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    assert len(page.items) == 2
    assert (
        page.items[0]["Keyword 1"] == "Dragon Torii Shrine"
        and page.items[1]["Keyword 1"] == "Dragon Torii Shrine"
    )
