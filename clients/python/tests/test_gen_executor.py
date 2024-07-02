import random
import time
from asyncio.coroutines import iscoroutine
from typing import AsyncGenerator, Generator

import pytest
from flaky import flaky
from loguru import logger

from jamaibase import JamAI, JamAIAsync
from jamaibase.protocol import (
    ColumnSchemaCreate,
    GenConfigUpdateRequest,
    GenTableRowsChatCompletionChunks,
    RowAddRequest,
    RowRegenRequest,
    TableSchemaCreate,
    TableType,
)

CLIENT_CLS = [JamAI, JamAIAsync]
GEN_TYPES = ["REGEN"]
DATA_LENGTHS = ["normal", "exceed"]


async def run(fn, *args, **kwargs):
    ret = fn(*args, **kwargs)
    if iscoroutine(ret):
        return await ret
    return ret


async def run_gen_async(fn, *args, **kwargs):
    ret = fn(*args, **kwargs)
    if iscoroutine(ret):
        ret = await ret
    if isinstance(ret, AsyncGenerator):
        async for item in ret:
            yield item
    else:
        yield ret


def run_gen_sync(fn, *args, **kwargs):
    ret = fn(*args, **kwargs)
    if isinstance(ret, Generator):
        for item in ret:
            yield item
    else:
        yield ret


async def _create_table(
    jamai: JamAI | JamAIAsync,
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
    if table_type == TableType.action:
        table = await run(jamai.create_action_table, schema)
    else:
        raise ValueError(f"Invalid table type: {table_type}")
    return table, table_id


async def _update_gen_config(
    jamai: JamAI | JamAIAsync, table_type: TableType, gen_config: GenConfigUpdateRequest
):
    await run(jamai.update_gen_config, table_type, gen_config)


# ---------------------------------------------------------
# Test Cases for concurrent Execution
# ---------------------------------------------------------
def column_map_prompt(content: str, max_tokens: int):
    return {
        "id": "",
        # "model": "openai/gpt-3.5-turbo",
        # "model": "openai/gpt-4-turbo",
        "model": "openai/gpt-4o",
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


def column_map_long_prompt(content: str, max_tokens: int):
    return {
        "id": "",
        "model": "ellm/meta-llama/Llama-3-8B-Instruct",
        # "model": "together/Qwen/Qwen1.5-0.5B-Chat",
        "messages": [
            {
                "role": "system",
                "content": "You are a concise assistant.",
            },
            {
                "role": "user",
                "content": " ".join([content] * 5000),
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


def data(data_lengths=["normal"]):
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
        # {
        #     "aa": (["xx"], "<xx:1>"),
        #     "bb": (["yy"], "<yy:2>"),
        #     "cc": (["zz"], "<zz:3>"),
        #     # "dd": (["xx"], "<xx:1>"),
        #     # "ee": (["yy"], "<yy:2>"),
        #     # "ff": (["zz"], "<zz:3>"),
        # },
        {
            "aa": (["xx"], "<xx:1>"),
            "bb": (["yy"], "<yy:2>"),
            "cc": (["zz"], "<zz:3>"),
            "dd": (["aa"], "<aa:<xx:1>>"),
            "ee": (["bb"], "<bb:<yy:2>>"),
            "ff": (["cc"], "<cc:<zz:3>>"),
        },
        # {
        #     "aa": (["xx"], "<xx:1>"),
        #     "bb": (["yy"], "<yy:2>"),
        #     "cc": (["zz"], "<zz:3>"),
        #     "dd": (["aa", "bb"], "(<aa:<xx:1>> & <bb:<yy:2>>)"),
        #     "ee": (["cc"], "<cc:<zz:3>>"),
        #     "ff": (
        #         ["dd", "ee"],
        #         "(<dd:(<aa:<xx:1>> & <bb:<yy:2>>)> & <ee:<cc:<zz:3>>>)",
        #     ),
        # },
        # {
        #     "aa": (["xx"], "<xx:1>"),
        #     "bb": (["yy"], "<yy:2>"),
        #     "cc": (["zz"], "<zz:3>"),
        #     "dd": (["aa", "bb"], "(<aa:<xx:1>> & <bb:<yy:2>>)"),
        #     "ee": (["cc", "dd"], "(<cc:<zz:3>> & <dd:(<aa:<xx:1>> & <bb:<yy:2>>)>)"),
        #     "ff": (
        #         ["dd", "ee"],
        #         "(<dd:(<aa:<xx:1>> & <bb:<yy:2>>)> & <ee:(<cc:<zz:3>> & <dd:(<aa:<xx:1>> & <bb:<yy:2>>)>)>)",
        #     ),
        # },
        # {
        #     "aa": (["xx", "yy"], "(<xx:1> & <yy:2>)"),
        #     "bb": (["aa"], "<aa:(<xx:1> & <yy:2>)>"),
        #     "cc": (["zz", "bb"], "(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)"),
        #     "dd": (["cc"], "<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)>"),
        #     "ee": (
        #         ["cc", "dd"],
        #         "(<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)> & <dd:<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)>>)",
        #     ),
        #     "ff": (
        #         ["aa", "bb", "cc", "dd", "ee"],
        #         "(<aa:(<xx:1> & <yy:2>)> & <bb:<aa:(<xx:1> & <yy:2>)>> & <cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)> & <dd:<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)>> & <ee:(<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)> & <dd:<cc:(<zz:3> & <bb:<aa:(<xx:1> & <yy:2>)>>)>>)>)",
        #     ),
        # },
        # {
        #     "aa": (["xx", "yy", "zz"], "(<xx:1> & <yy:2> & <zz:3>)"),
        #     "bb": (["aa"], "<aa:(<xx:1> & <yy:2> & <zz:3>)>"),
        #     "cc": (["bb"], "<bb:<aa:(<xx:1> & <yy:2> & <zz:3>)>>"),
        #     "dd": (["cc"], "<cc:<bb:<aa:(<xx:1> & <yy:2> & <zz:3>)>>>"),
        #     "ee": (["yy", "zz"], "(<yy:2> & <zz:3>)"),
        #     "ff": (
        #         ["dd", "ee"],
        #         "(<dd:<cc:<bb:<aa:(<xx:1> & <yy:2> & <zz:3>)>>>> & <ee:(<yy:2> & <zz:3>)>)",
        #     ),
        # },
        # {
        #     "aa": (["xx"], "<xx:1>"),
        #     "bb": (["yy"], "<yy:2>"),
        #     "cc": (["zz"], "<zz:3>"),
        #     "dd": (["xx"], "<xx:1>"),
        #     "ee": (["yy"], "<yy:2>"),
        #     "ff": (["zz"], "<zz:3>"),
        # },
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
        },
        # {
        #     "aa": (["xx"], "<xx:1>"),
        #     "bb": (["xx"], "<xx:1>"),
        #     "cc": (["xx"], "<xx:1>"),
        #     # ---
        #     "dd": (["xx"], "<xx:1>"),
        #     "ee": (["xx"], "<xx:1>"),
        #     "ff": (["xx"], "<xx:1>"),
        #     "dd2": (["xx"], "<xx:1>"),
        #     "ee2": (["xx"], "<xx:1>"),
        #     "ff2": (["xx"], "<xx:1>"),
        #     # ---
        #     "aa3": (["xx"], "<xx:1>"),
        #     "bb3": (["xx"], "<xx:1>"),
        #     "cc3": (["xx"], "<xx:1>"),
        #     "dd3": (["xx"], "<xx:1>"),
        #     "ee3": (["xx"], "<xx:1>"),
        #     "ff3": (["xx"], "<xx:1>"),
        #     "dd23": (["xx"], "<xx:1>"),
        #     "ee23": (["xx"], "<xx:1>"),
        #     "ff23": (["xx"], "<xx:1>"),
        # }
    ]

    def get_nodes_data(inv_nodes, output_dict, content_postfix, max_tokens, data_length):
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
                column_map[end] = (
                    column_map_prompt(content, max_tokens)
                    if data_length == "normal"
                    else column_map_long_prompt(content, max_tokens)
                )
                expected_column_gen[end] = expected_gen
            nodes_data.append(
                (input_dict, output_dict, column_map, row, expected_column_gen, data_length)
            )
        return nodes_data

    content_postfix = "Output exactly the content above, don't include any other information."
    content_postfix2 = "Output exactly the content above, don't include any other information. Then create a story."
    # all_nodes_data = get_nodes_data(inv_nodes2, output_dict2, content_postfix2, max_tokens=5)
    # all_nodes_data = get_nodes_data(inv_nodes2, output_dict2, content_postfix2, max_tokens=1000)
    # all_nodes_data = get_nodes_data(inv_nodes2, output_dict2, content_postfix2, max_tokens=500)
    # all_nodes_data = get_nodes_data(inv_nodes2, output_dict2, content_postfix2, max_tokens=300)
    # all_nodes_data = get_nodes_data(inv_nodes2, output_dict2, content_postfix, max_tokens=100)
    all_nodes_data = []
    for data_length in data_lengths:
        all_nodes_data += get_nodes_data(
            # inv_nodes, output_dict, content_postfix, max_tokens=100, data_length=data_length
            inv_nodes2,
            output_dict2,
            content_postfix,
            max_tokens=100,
            data_length=data_length,
        )
    # all_nodes_data = get_nodes_data(inv_nodes, output_dict, content_postfix2, max_tokens=300)
    return all_nodes_data


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("gen_type", GEN_TYPES)
@pytest.mark.parametrize(
    "input_dict, output_dict, column_map, row, expected_column_gen, data_length", data()
)
async def test_nonstream_concurrent_execution(
    client_cls: JamAI | JamAIAsync,
    gen_type,
    input_dict,
    output_dict,
    column_map,
    row,
    expected_column_gen,
    data_length,
):
    """
    Tests concurrent execution in non-streaming mode with dependencies.
    """
    jamai = client_cls(project_id="", api_key="")
    meta, table_id = await _create_table(
        jamai,
        TableType.action,
        cols_info=(
            input_dict,
            output_dict,
        ),
    )
    gen_config = GenConfigUpdateRequest(table_id=table_id, column_map=column_map)
    await _update_gen_config(jamai, TableType.action, gen_config)

    if isinstance(jamai, JamAIAsync):
        response = [
            r
            async for r in run_gen_async(
                jamai.add_table_rows,
                TableType.action,
                RowAddRequest(table_id=table_id, data=[row], stream=False, concurrent=True),
            )
        ]

    else:
        response = [
            r
            for r in run_gen_sync(
                jamai.add_table_rows,
                TableType.action,
                RowAddRequest(table_id=table_id, data=[row], stream=False, concurrent=True),
            )
        ]

    response = response[0]
    assert isinstance(response, GenTableRowsChatCompletionChunks)

    # Verify all output columns were executed
    for response in response.rows:
        for output_column_name in output_dict.keys():
            assert output_column_name in response.columns

    if gen_type == "REGEN":
        rows = await run(jamai.list_table_rows, TableType.action, table_id)
        row_id = rows.items[0]["ID"]
        if isinstance(jamai, JamAIAsync):
            response = [
                r
                async for r in run_gen_async(
                    jamai.regen_table_rows,
                    TableType.action,
                    RowRegenRequest(
                        table_id=table_id, row_ids=[row_id], stream=False, concurrent=True
                    ),
                )
            ]

        else:
            response = [
                r
                for r in run_gen_sync(
                    jamai.regen_table_rows,
                    TableType.action,
                    RowRegenRequest(
                        table_id=table_id, row_ids=[row_id], stream=False, concurrent=True
                    ),
                )
            ]
    response = response[0]
    assert isinstance(response, GenTableRowsChatCompletionChunks)

    # Get rows
    rows = await run(jamai.list_table_rows, TableType.action, table_id)
    for i in range(len(response.rows)):
        row_id = rows.items[i]["ID"]
        row = await run(jamai.get_table_row, TableType.action, table_id, row_id)

        # Compare generated outputs with expected outputs
        for output_column_name in output_dict.keys():
            expected_gen = expected_column_gen[output_column_name]
            column_gen = row[output_column_name]["value"]
            len_expected_gen = len(expected_gen)
            len_column_gen = len(column_gen)
            if len_column_gen >= len_expected_gen:
                assert column_gen[:len_expected_gen] == expected_gen
            else:
                assert column_gen == expected_gen[:len_column_gen]

    await run(jamai.delete_table, TableType.action, table_id)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("gen_type", GEN_TYPES)
@pytest.mark.parametrize(
    "input_dict, output_dict, column_map, row, expected_column_gen, data_length",
    data(DATA_LENGTHS),
)
async def test_stream_concurrent_execution(
    client_cls: JamAI | JamAIAsync,
    gen_type,
    input_dict,
    output_dict,
    column_map,
    row,
    expected_column_gen,
    data_length,
):
    """
    Tests concurrent execution in streaming mode with dependencies.
    """
    jamai = client_cls(project_id="", api_key="")
    meta, table_id = await _create_table(
        jamai,
        TableType.action,
        cols_info=(
            input_dict,
            output_dict,
        ),
    )
    gen_config = GenConfigUpdateRequest(table_id=table_id, column_map=column_map)
    await _update_gen_config(jamai, TableType.action, gen_config)

    total_start_time = time.time()
    first_chunk_times = {}
    chunks = []
    if isinstance(jamai, JamAIAsync):
        async for chunk in run_gen_async(
            jamai.add_table_rows,
            TableType.action,
            RowAddRequest(
                table_id=table_id,
                data=[row],
                stream=True,
                concurrent=True,
            ),
        ):
            chunks.append(chunk)
            if chunk.row_id not in first_chunk_times.keys():
                first_chunk_times[chunk.row_id] = {}
            if chunk.output_column_name not in first_chunk_times[chunk.row_id].keys():
                first_chunk_times[chunk.row_id][chunk.output_column_name] = (
                    time.time() - total_start_time
                )

    else:
        for chunk in run_gen_sync(
            jamai.add_table_rows,
            TableType.action,
            RowAddRequest(
                table_id=table_id,
                data=[row],
                stream=True,
                concurrent=True,
            ),
        ):
            chunks.append(chunk)
            if chunk.row_id not in first_chunk_times.keys():
                first_chunk_times[chunk.row_id] = {}
            if chunk.output_column_name not in first_chunk_times[chunk.row_id].keys():
                first_chunk_times[chunk.row_id][chunk.output_column_name] = (
                    time.time() - total_start_time
                )

    for row_id_ in first_chunk_times.keys():
        for output_column_name in first_chunk_times[row_id_].keys():
            logger.debug(
                f"> [Test] Time to first chunk for {output_column_name}: {first_chunk_times[row_id_].get(output_column_name, 'N/A'):.2f} seconds"
            )
        break

    logger.debug(
        f"> [Test] Stream Total Add Rows Time: {time.time() - total_start_time:.2f} seconds"
    )

    if gen_type == "REGEN":
        rows = await run(jamai.list_table_rows, TableType.action, table_id)
        row_id = rows.items[0]["ID"]
        total_start_time = time.time()
        first_chunk_times = {}
        chunks = []
        if isinstance(jamai, JamAIAsync):
            async for chunk in run_gen_async(
                jamai.regen_table_rows,
                TableType.action,
                RowRegenRequest(
                    table_id=table_id,
                    row_ids=[row_id],
                    stream=True,
                    concurrent=True,
                ),
            ):
                chunks.append(chunk)
                if chunk.row_id not in first_chunk_times.keys():
                    first_chunk_times[chunk.row_id] = {}
                if chunk.output_column_name not in first_chunk_times[chunk.row_id].keys():
                    first_chunk_times[chunk.row_id][chunk.output_column_name] = (
                        time.time() - total_start_time
                    )

        else:
            for chunk in run_gen_sync(
                jamai.regen_table_rows,
                TableType.action,
                RowRegenRequest(
                    table_id=table_id,
                    row_ids=[row_id],
                    stream=True,
                    concurrent=True,
                ),
            ):
                chunks.append(chunk)
                if chunk.row_id not in first_chunk_times.keys():
                    first_chunk_times[chunk.row_id] = {}
                if chunk.output_column_name not in first_chunk_times[chunk.row_id].keys():
                    first_chunk_times[chunk.row_id][chunk.output_column_name] = (
                        time.time() - total_start_time
                    )

        for row_id_ in first_chunk_times.keys():
            for output_column_name in first_chunk_times[row_id_].keys():
                logger.debug(
                    f"> [Test] Time to first chunk for {output_column_name}: {first_chunk_times[row_id_].get(output_column_name, 'N/A'):.2f} seconds"
                )
            break

        logger.debug(
            f"> [Test] Stream Total Regen Rows Time: {time.time() - total_start_time:.2f} seconds"
        )

    # Get first rows
    rows = await run(jamai.list_table_rows, TableType.action, table_id)
    row_id = rows.items[0]["ID"]
    row = await run(jamai.get_table_row, TableType.action, table_id, row_id)

    # Compare generated outputs with expected outputs
    for output_column_name in output_dict.keys():
        expected_gen = expected_column_gen[output_column_name]
        column_gen = row[output_column_name]["value"]
        len_expected_gen = len(expected_gen)
        len_column_gen = len(column_gen) if column_gen is not None else 0
        if data_length == "normal":
            if len_column_gen >= len_expected_gen:
                assert column_gen[:len_expected_gen] == expected_gen
            else:
                assert column_gen == expected_gen[:len_column_gen]
        else:
            assert column_gen.startswith("[ERROR]")

    await run(jamai.delete_table, TableType.action, table_id)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("gen_type", GEN_TYPES)
@pytest.mark.parametrize(
    "input_dict, output_dict, column_map, row, expected_column_gen, data_length", data()
)
async def test_multirows_nonstream_concurrent_execution(
    client_cls: JamAI | JamAIAsync,
    gen_type,
    input_dict,
    output_dict,
    column_map,
    row,
    expected_column_gen,
    data_length,
):
    """
    Tests concurrent execution in non-streaming mode with dependencies.
    """
    jamai = client_cls(project_id="", api_key="")
    meta, table_id = await _create_table(
        jamai,
        TableType.action,
        cols_info=(
            input_dict,
            output_dict,
        ),
    )
    gen_config = GenConfigUpdateRequest(table_id=table_id, column_map=column_map)
    await _update_gen_config(jamai, TableType.action, gen_config)

    total_start_time = time.time()
    if isinstance(jamai, JamAIAsync):
        response = [
            r
            async for r in run_gen_async(
                jamai.add_table_rows,
                TableType.action,
                RowAddRequest(
                    table_id=table_id, data=[row, row, row], stream=False, concurrent=True
                ),
            )
        ]

    else:
        response = [
            r
            for r in run_gen_sync(
                jamai.add_table_rows,
                TableType.action,
                RowAddRequest(
                    table_id=table_id, data=[row, row, row], stream=False, concurrent=True
                ),
            )
        ]

    response = response[0]
    assert isinstance(response, GenTableRowsChatCompletionChunks)
    logger.debug(f"> Non-Stream Total Rows Time: {time.time() - total_start_time}")

    # Verify all output columns were executed
    for response in response.rows:
        for output_column_name in output_dict.keys():
            assert output_column_name in response.columns

    if gen_type == "REGEN":
        total_start_time = time.time()
        rows = await run(jamai.list_table_rows, TableType.action, table_id)
        if isinstance(jamai, JamAIAsync):
            response = [
                r
                async for r in run_gen_async(
                    jamai.regen_table_rows,
                    TableType.action,
                    RowRegenRequest(
                        table_id=table_id,
                        row_ids=[row_item["ID"] for row_item in rows.items],
                        stream=False,
                        concurrent=True,
                    ),
                )
            ]

        else:
            response = [
                r
                for r in run_gen_sync(
                    jamai.regen_table_rows,
                    TableType.action,
                    RowRegenRequest(
                        table_id=table_id,
                        row_ids=[row_item["ID"] for row_item in rows.items],
                        stream=False,
                        concurrent=True,
                    ),
                )
            ]
    response = response[0]
    assert isinstance(response, GenTableRowsChatCompletionChunks)
    logger.debug(f"> Non-Stream Total Regen Rows Time: {time.time() - total_start_time}")

    # Get rows
    rows = await run(jamai.list_table_rows, TableType.action, table_id)
    for i in range(len(response.rows)):
        row_id = rows.items[i]["ID"]
        row = await run(jamai.get_table_row, TableType.action, table_id, row_id)

        # Compare generated outputs with expected outputs
        for output_column_name in output_dict.keys():
            expected_gen = expected_column_gen[output_column_name]
            column_gen = row[output_column_name]["value"]
            len_expected_gen = len(expected_gen)
            len_column_gen = len(column_gen)
            if len_column_gen >= len_expected_gen:
                assert column_gen[:len_expected_gen] == expected_gen
            else:
                assert column_gen == expected_gen[:len_column_gen]

    await run(jamai.delete_table, TableType.action, table_id)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("gen_type", GEN_TYPES)
@pytest.mark.parametrize(
    "input_dict, output_dict, column_map, row, expected_column_gen, data_length",
    data(DATA_LENGTHS),
)
async def test_multirows_stream_concurrent_execution(
    client_cls: JamAI | JamAIAsync,
    gen_type,
    input_dict,
    output_dict,
    column_map,
    row,
    expected_column_gen,
    data_length,
):
    """
    Tests concurrent execution in streaming mode with dependencies.
    """
    jamai = client_cls(project_id="", api_key="")
    meta, table_id = await _create_table(
        jamai,
        TableType.action,
        cols_info=(
            input_dict,
            output_dict,
        ),
    )
    gen_config = GenConfigUpdateRequest(table_id=table_id, column_map=column_map)
    await _update_gen_config(jamai, TableType.action, gen_config)

    total_start_time = time.time()
    first_chunk_times = {}
    chunks = []
    if isinstance(jamai, JamAIAsync):
        async for chunk in run_gen_async(
            jamai.add_table_rows,
            TableType.action,
            RowAddRequest(
                table_id=table_id,
                data=[row, row, row],
                stream=True,
                concurrent=True,
            ),
        ):
            chunks.append(chunk)
            # if isinstance(chunk, ErrorChunk):
            #     logger.debug(f"Error Chunk: {chunk}")
            # else:
            if chunk.row_id not in first_chunk_times.keys():
                first_chunk_times[chunk.row_id] = {}
            if chunk.output_column_name not in first_chunk_times[chunk.row_id].keys():
                first_chunk_times[chunk.row_id][chunk.output_column_name] = (
                    time.time() - total_start_time
                )

    else:
        for chunk in run_gen_sync(
            jamai.add_table_rows,
            TableType.action,
            RowAddRequest(
                table_id=table_id,
                data=[row],
                stream=True,
                concurrent=True,
            ),
        ):
            chunks.append(chunk)
            # if isinstance(chunk, ErrorChunk):
            #     logger.debug(f"Error Chunk: {chunk}")
            # else:
            if chunk.row_id not in first_chunk_times.keys():
                first_chunk_times[chunk.row_id] = {}
            if chunk.output_column_name not in first_chunk_times[chunk.row_id].keys():
                first_chunk_times[chunk.row_id][chunk.output_column_name] = (
                    time.time() - total_start_time
                )

    for row_id_ in first_chunk_times.keys():
        for output_column_name in first_chunk_times[row_id_].keys():
            logger.debug(
                f"> [Test] Time to first chunk for {output_column_name}: {first_chunk_times[row_id_].get(output_column_name, 'N/A'):.2f} seconds"
            )
        break

    logger.debug(
        f"> [Test] Stream Total Add Rows Time: {time.time() - total_start_time:.2f} seconds"
    )

    if gen_type == "REGEN":
        rows = await run(jamai.list_table_rows, TableType.action, table_id)
        total_start_time = time.time()
        total_start_time = time.time()
        first_chunk_times = {}
        chunks = []
        if isinstance(jamai, JamAIAsync):
            async for chunk in run_gen_async(
                jamai.regen_table_rows,
                TableType.action,
                RowRegenRequest(
                    table_id=table_id,
                    row_ids=[row_item["ID"] for row_item in rows.items],
                    stream=True,
                    concurrent=True,
                ),
            ):
                chunks.append(chunk)
                # if isinstance(chunk, ErrorChunk):
                #     logger.debug(f"Error Chunk: {chunk}")
                # else:
                if chunk.row_id not in first_chunk_times.keys():
                    first_chunk_times[chunk.row_id] = {}
                if chunk.output_column_name not in first_chunk_times[chunk.row_id].keys():
                    first_chunk_times[chunk.row_id][chunk.output_column_name] = (
                        time.time() - total_start_time
                    )

        else:
            for chunk in run_gen_sync(
                jamai.regen_table_rows,
                TableType.action,
                RowRegenRequest(
                    table_id=table_id,
                    row_ids=[row_item["ID"] for row_item in rows.items],
                    stream=True,
                    concurrent=True,
                ),
            ):
                chunks.append(chunk)
                # if isinstance(chunk, ErrorChunk):
                #     logger.debug(f"Error Chunk: {chunk}")
                # else:
                if chunk.row_id not in first_chunk_times.keys():
                    first_chunk_times[chunk.row_id] = {}
                if chunk.output_column_name not in first_chunk_times[chunk.row_id].keys():
                    first_chunk_times[chunk.row_id][chunk.output_column_name] = (
                        time.time() - total_start_time
                    )

        for row_id_ in first_chunk_times.keys():
            for output_column_name in first_chunk_times[row_id_].keys():
                logger.debug(
                    f"> [Test] Time to first chunk for {output_column_name}: {first_chunk_times[row_id_].get(output_column_name, 'N/A'):.2f} seconds"
                )
            break

        logger.debug(
            f"> [Test] Stream Total Regen Rows Time: {time.time() - total_start_time:.2f} seconds"
        )

    # Get first rows
    rows = await run(jamai.list_table_rows, TableType.action, table_id)
    row_id = rows.items[0]["ID"]
    row = await run(jamai.get_table_row, TableType.action, table_id, row_id)

    # Compare generated outputs with expected outputs
    for output_column_name in output_dict.keys():
        expected_gen = expected_column_gen[output_column_name]
        column_gen = row[output_column_name]["value"]
        len_expected_gen = len(expected_gen)
        len_column_gen = len(column_gen) if column_gen is not None else 0
        if data_length == "normal":
            if len_column_gen >= len_expected_gen:
                assert column_gen[:len_expected_gen] == expected_gen
            else:
                assert column_gen == expected_gen[:len_column_gen]
        else:
            assert column_gen.startswith("[ERROR]")

    await run(jamai.delete_table, TableType.action, table_id)
