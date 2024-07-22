import random

import httpx
import pytest
from httpx import Timeout
from loguru import logger

from owl.protocol import (
    ColumnSchemaCreate,
    GenConfigUpdateRequest,
    Page,
    RowAddRequest,
    TableMetaResponse,
    TableSchemaCreate,
    TableType,
)

BASE_URL = "http://localhost:6969/api"


@pytest.fixture
def client():
    yield httpx.Client(transport=httpx.HTTPTransport(retries=3), timeout=Timeout(5 * 60))


def _create_table(
    client,
    table_type: TableType,
    cols_info: tuple[dict[str, str], dict[str, str]] = None,
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
        json=RowAddRequest(table_id=table_id, data=row, stream=False, parallel=False).model_dump(),
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


# ---------------------------------------------------------
# Test Cases for Parallel Execution
# ---------------------------------------------------------


def column_map_prompt(content: str, max_tokens: int):
    return {
        "id": "",
        # "model": "openai/gpt-3.5-turbo",
        "model": "openai/gpt-4-turbo",
        "messages": [
            {
                "role": "system",
                "content": "You are a concise assistant.",
            },
            {
                "role": "user",
                "content": content,
            },
        ],
        "functions": [],
        "function_call": "auto",
        "temperature": 0.01,
        "top_p": 0.1,
        "stream": False,
        "stop": [],
        "max_tokens": max_tokens,
    }


def data():
    input_dict = {"xx": "str", "yy": "str", "zz": "str"}
    output_dict = {
        "aa": "str",
        "bb": "str",
        "cc": "str",
        "dd": "str",
        "ee": "str",
        "ff": "str",
    }
    output_dict2 = {
        "aa": "str",
        "bb": "str",
        "cc": "str",
        # ---
        "dd": "str",
        "ee": "str",
        "ff": "str",
        "dd2": "str",
        "ee2": "str",
        "ff2": "str",
        # ---
        "aa3": "str",
        "bb3": "str",
        "cc3": "str",
        "dd3": "str",
        "ee3": "str",
        "ff3": "str",
        "dd23": "str",
        "ee23": "str",
        "ff23": "str",
    }
    row = {"xx": "1", "yy": "2", "zz": "3"}

    inv_nodes = [  # map - end: (start, expected_gen_output)
        {
            "aa": (["xx"], "<xx:1>"),
            "bb": (["yy"], "<yy:2>"),
            "cc": (["zz"], "<zz:3>"),
            "dd": (["aa"], "<aa:<xx:1>>"),
            "ee": (["bb"], "<bb:<yy:2>>"),
            "ff": (["cc"], "<cc:<zz:3>>"),
        },
        {
            "aa": (["xx"], "<xx:1>"),
            "bb": (["yy"], "<yy:2>"),
            "cc": (["zz"], "<zz:3>"),
            "dd": (["aa", "bb"], "(<aa:<xx:1>> & <bb:<yy:2>>)"),
            "ee": (["cc"], "<cc:<zz:3>>"),
            "ff": (
                ["dd", "ee"],
                "(<dd:(<aa:<xx:1>> & <bb:<yy:2>>)> & <ee:<cc:<zz:3>>>)",
            ),
        },
        {
            "aa": (["xx"], "<xx:1>"),
            "bb": (["yy"], "<yy:2>"),
            "cc": (["zz"], "<zz:3>"),
            "dd": (["aa", "bb"], "(<aa:<xx:1>> & <bb:<yy:2>>)"),
            "ee": (["cc", "dd"], "(<cc:<zz:3>> & <dd:(<aa:<xx:1>> & <bb:<yy:2>>)>)"),
            "ff": (
                ["dd", "ee"],
                "(<dd:(<aa:<xx:1>> & <bb:<yy:2>>)> & <ee:(<cc:<zz:3>> & <dd:(<aa:<xx:1>> & <bb:<yy:2>>)>)>)",
            ),
        },
        {
            "aa": (["xx", "yy"], "(<xx:1> & <yy:2>)"),
            "bb": (["aa"], "<aa:(<xx:1> & <yy:2>)>"),
            "cc": (["zz", "bb"], "(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)"),
            "dd": (["cc"], "<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)>"),
            "ee": (
                ["cc", "dd"],
                "(<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)> & <dd:<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)>>)",
            ),
            "ff": (
                ["aa", "bb", "cc", "dd", "ee"],
                "(<aa:(<xx:1> & <yy:2>)> & <bb:<aa:(<xx:1> & <yy:2>)>> & <cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)> & <dd:<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)>> & <ee:(<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)> & <dd:<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)>>)>)",
            ),
        },
        {
            "aa": (["xx", "yy", "zz"], "(<xx:1> & <yy:2> & <zz:3>)"),
            "bb": (["aa"], "<aa:(<xx:1> & <yy:2> & <zz:3>)>"),
            "cc": (["bb"], "<bb:<aa:(<xx:1> & <yy:2> & <zz:3>)>>"),
            "dd": (["cc"], "<cc:<bb:<aa:(<xx:1> & <yy:2> & <zz:3>)>>>"),
            "ee": (["yy", "zz"], "(<yy:2> & <zz:3>)"),
            "ff": (
                ["dd", "ee"],
                "(<dd:<cc:<bb:<aa:(<xx:1> & <yy:2> & <zz:3>)>>>> & <ee:(<yy:2> & <zz:3>)>)",
            ),
        },
        {
            "aa": (["xx"], "<xx:1>"),
            "bb": (["yy"], "<yy:2>"),
            "cc": (["zz"], "<zz:3>"),
            "dd": (["xx"], "<xx:1>"),
            "ee": (["yy"], "<yy:2>"),
            "ff": (["zz"], "<zz:3>"),
        },
    ]

    inv_nodes2 = [  # map - end: (start, expected_gen_output)
        {
            "aa": (["xx"], "<xx:1>"),
            "bb": (["yy"], "<yy:2>"),
            "cc": (["zz"], "<zz:3>"),
            # ---
            "dd": (["aa"], "<aa:<xx:1>>"),
            "ee": (["bb"], "<bb:<yy:2>>"),
            "ff": (["cc"], "<cc:<zz:3>>"),
            "dd2": (["aa"], "<aa:<xx:1>>"),
            "ee2": (["bb"], "<bb:<yy:2>>"),
            "ff2": (["cc"], "<cc:<zz:3>>"),
            # ---
            "aa3": (["dd2"], "<dd2:<aa:<xx:1>>>"),
            "bb3": (["ee2"], "<ee2:<bb:<yy:2>>>"),
            "cc3": (["ff2"], "<ff2:<cc:<zz:3>>>"),
            "dd3": (["dd2"], "<dd2:<aa:<xx:1>>>"),
            "ee3": (["ee2"], "<ee2:<bb:<yy:2>>>"),
            "ff3": (["ee2"], "<ee2:<bb:<yy:2>>>"),
            "dd23": (["dd2"], "<dd2:<aa:<xx:1>>>"),
            "ee23": (["ee2"], "<ee2:<bb:<yy:2>>>"),
            "ff23": (["ee2"], "<ee2:<bb:<yy:2>>>"),
        }
    ]

    def get_nodes_data(inv_nodes, output_dict, content_postfix, max_tokens):
        nodes_data = []
        for inv_node in inv_nodes:
            column_map = {}
            expected_column_gen = {}
            for end, (starts, expected_gen) in inv_node.items():
                sub_contents = [f"<{start}:${{{start}}}>" for start in starts]
                if len(sub_contents) > 1:
                    sub_content = "(" + " & ".join(sub_contents) + ")"
                else:
                    sub_content = sub_contents[0]
                logger.info(end, starts)
                logger.info(sub_content)
                content = f"{sub_content} \n\n{content_postfix}"
                column_map[end] = column_map_prompt(content, max_tokens)
                expected_column_gen[end] = expected_gen

            nodes_data.append((input_dict, output_dict, column_map, row, expected_column_gen))
        return nodes_data

    content_postfix = "Output exactly the content above, don't include any other information."
    content_postfix2 = "Output exactly the content above, don't include any other information. Then create a story."
    all_nodes_data = get_nodes_data(inv_nodes, output_dict, content_postfix, max_tokens=100)
    # all_nodes_data += get_nodes_data(inv_nodes2, output_dict2, content_postfix2, max_tokens=1000)

    return all_nodes_data


@pytest.mark.asyncio
@pytest.mark.parametrize("input_dict, output_dict, column_map, row, expected_column_gen", data())
async def test_nonstream_parallel_execution(
    client, input_dict, output_dict, column_map, row, expected_column_gen
):
    """
    Tests parallel execution in non-streaming mode with dependencies.
    """
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            input_dict,
            output_dict,
        ),
    )
    gen_config = GenConfigUpdateRequest(table_id=table_id, column_map=column_map)
    _update_gen_config(client, gen_config)

    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/rows/add",
        json=RowAddRequest(table_id=table_id, data=row, stream=False, parallel=True).model_dump(),
    )
    response.raise_for_status()
    response_data = response.json()
    logger.info(f"response_data: {response_data}")

    # Verify all output columns were executed
    for output_column_name in output_dict.keys():
        assert output_column_name in response_data["columns"]

    # Get first rows
    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    row_id = page.items[0]["ID"]
    response = client.get(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows/{row_id}"
    )
    response.raise_for_status()

    # Compare generated outputs with expected outputs
    logger.info(response.json())
    response_json = response.json()
    for output_column_name in output_dict.keys():
        expected_gen = expected_column_gen[output_column_name]
        column_gen = response_json[output_column_name]
        len_expected_gen = len(expected_gen)
        len_column_gen = len(column_gen)
        if len_column_gen >= len_expected_gen:
            assert column_gen[:len_expected_gen] == expected_gen
        else:
            assert column_gen == expected_gen[:len_column_gen]


@pytest.mark.asyncio
@pytest.mark.parametrize("input_dict, output_dict, column_map, row, expected_column_gen", data())
async def test_stream_parallel_execution(
    client, input_dict, output_dict, column_map, row, expected_column_gen
):
    """
    Tests parallel execution in streaming mode with dependencies.
    """
    meta, table_id = _create_table(
        client,
        TableType.action,
        cols_info=(
            input_dict,
            output_dict,
        ),
    )
    gen_config = GenConfigUpdateRequest(table_id=table_id, column_map=column_map)
    _update_gen_config(client, gen_config)

    response = client.post(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/rows/add",
        json=RowAddRequest(table_id=table_id, data=row, stream=True, parallel=True).model_dump(),
    )
    response.raise_for_status()

    # Collect streaming responses
    chunks = []
    async for chunk in response.aiter_text():
        if chunk.strip() == "[DONE]":
            break
        chunks.append(chunk)

    # Verify all output columns were executed
    for output_column_name in output_dict.keys():
        assert any(output_column_name in chunk for chunk in chunks)

    # Get first rows
    response = client.get(f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows")
    response.raise_for_status()
    page = Page[dict](**response.json())
    row_id = page.items[0]["ID"]
    response = client.get(
        f"{BASE_URL}/v1/gen_tables/{TableType.action.value}/{table_id}/rows/{row_id}"
    )
    response.raise_for_status()

    # Compare generated outputs with expected outputs
    logger.info(response.json())
    response_json = response.json()
    for output_column_name in output_dict.keys():
        expected_gen = expected_column_gen[output_column_name]
        column_gen = response_json[output_column_name]
        len_expected_gen = len(expected_gen)
        len_column_gen = len(column_gen)
        if len_column_gen >= len_expected_gen:
            assert column_gen[:len_expected_gen] == expected_gen
        else:
            assert column_gen == expected_gen[:len_column_gen]
