import asyncio
import io
import time
from contextlib import asynccontextmanager

import httpx
import pytest
from flaky import flaky
from PIL import Image

from jamaibase import JamAI, JamAIAsync
from jamaibase.exceptions import ResourceNotFoundError
from jamaibase.protocol import (
    CodeGenConfig,
    ColumnSchemaCreate,
    GenConfigUpdateRequest,
    GenTableRowsChatCompletionChunks,
    GenTableStreamChatCompletionChunk,
    GetURLResponse,
    RegenStrategy,
    RowAddRequest,
    RowRegenRequest,
    RowUpdateRequest,
    TableSchemaCreate,
    TableType,
)
from jamaibase.utils import run

CLIENT_CLS = [JamAI, JamAIAsync]
REGEN_STRATEGY = [
    RegenStrategy.RUN_ALL,
    RegenStrategy.RUN_BEFORE,
    RegenStrategy.RUN_SELECTED,
    RegenStrategy.RUN_AFTER,
]

TABLE_ID_A = "table_a"

IN_COLS = [
    ColumnSchemaCreate(id="in_01", dtype="str"),
    ColumnSchemaCreate(id="in_02", dtype="str"),
    ColumnSchemaCreate(id="in_03", dtype="str"),
]

OUT_COLS = [
    ColumnSchemaCreate(id="out_01", dtype="str"),
    ColumnSchemaCreate(id="out_02", dtype="str"),
    ColumnSchemaCreate(id="out_03", dtype="str"),
    ColumnSchemaCreate(id="out_04", dtype="str"),
    ColumnSchemaCreate(id="out_05", dtype="str"),
    ColumnSchemaCreate(id="out_06", dtype="str"),
]


def column_prompt(
    user_content: str,
    max_tokens: int,
    model: str = "anthropic/claude-3-haiku-20240307",
):
    return {
        "id": "",
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a concise assistant.",
            },
            {
                "role": "user",
                "content": user_content,
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


COLUMN_MAP_CONCURRENCY = {
    "out_01": column_prompt(
        "Count from `${in_01} plus -1 plus 2` to `${in_02}`, seperated by comma. Reply answer only",
        1000,
    ),
    "out_02": column_prompt(
        "Count from `${in_01} plus 2 minus 1` to `${in_02}`, seperated by comma. Reply answer only",
        1000,
    ),
    "out_03": column_prompt(
        "Count from `${in_01} minus 1 plus 2` to `${in_02}`, seperated by comma. Reply answer only",
        1000,
    ),
}

COLUMN_MAP_DEPENDENCY = {
    "out_01": column_prompt(
        "Solve: ${in_01} + ${in_02}, reply answer only.",
        10,
    ),
    "out_02": column_prompt(
        "Solve: ${in_02} - ${in_01}, reply answer only.",
        10,
    ),
    "out_03": column_prompt(
        "Solve: ${out_01} x ${out_02}, reply answer only.",
        10,
    ),
    "out_04": column_prompt(
        "Solve: ${out_02} x ${out_03}, reply answer only.",
        10,
    ),
    "out_05": column_prompt(
        "Solve: ${out_04} x 1 / 3, reply answer only, in 2 decimal places.",
        10,
    ),
}


@asynccontextmanager
async def _create_table(
    jamai: JamAI | JamAIAsync,
    table_type: TableType,
    cols: list[ColumnSchemaCreate],
    table_id: str = TABLE_ID_A,
):
    schema = TableSchemaCreate(
        id=table_id,
        cols=cols,
    )
    try:
        if table_type == TableType.action:
            _ = await run(jamai.table.create_action_table, schema)
        else:
            raise ValueError(f"Invalid table type: {table_type}")
        yield table_id
    finally:
        await run(jamai.table.delete_table, table_type, table_id)


async def _update_gen_config(
    jamai: JamAI | JamAIAsync, table_type: TableType, gen_config: GenConfigUpdateRequest
):
    await run(jamai.table.update_gen_config, table_type, gen_config)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("long_context_column_name", ["out_01", "out_04", "out_06"])
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
async def test_exceed_context_length(
    client_cls: JamAI | JamAIAsync,
    long_context_column_name: str,
    stream: bool,
):
    jamai = client_cls()
    cols = IN_COLS[:] + OUT_COLS[:]
    async with _create_table(jamai, TableType.action, cols) as table_id:
        row_input_data = {"in_01": "Bouldering", "in_02": "Olympics 2024", "in_03": "Paris"}
        model_name = "openai/gpt-4o-mini"
        column_map = {
            "out_01": column_prompt(
                "Tell a very short story about ${in_01}, ${in_02} and ${in_03}.", 100, model_name
            ),
            "out_02": column_prompt("Rephrase ${out_01}.", 100, model_name),
            "out_03": column_prompt("Rephrase ${out_02}.", 100, model_name),
            "out_04": column_prompt("Rephrase ${out_03}.", 100, model_name),
            "out_05": column_prompt("Rephrase ${out_04}.", 100, model_name),
            "out_06": column_prompt("Rephrase ${out_05}.", 100, model_name),
        }

        column_map[long_context_column_name]["messages"][-1]["content"] = "".join(
            column_map[long_context_column_name]["messages"][-1]["content"] * 50000
        )

        gen_config = GenConfigUpdateRequest(
            table_id=table_id,
            column_map=column_map,
        )
        await _update_gen_config(jamai, TableType.action, gen_config)

        chunks = await run(
            jamai.table.add_table_rows,
            TableType.action,
            RowAddRequest(table_id=table_id, data=[row_input_data], stream=stream),
        )
        if stream:
            assert isinstance(chunks[0], GenTableStreamChatCompletionChunk)
        else:
            assert isinstance(chunks, GenTableRowsChatCompletionChunks)

        # Get rows
        rows = await run(jamai.table.list_table_rows, TableType.action, table_id)
        row_id = rows.items[0]["ID"]
        row = await run(jamai.table.get_table_row, TableType.action, table_id, row_id)

        column_gen = row[long_context_column_name]["value"]
        assert column_gen.startswith("[ERROR]")


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
async def test_multicols_concurrency_timing(
    client_cls: JamAI | JamAIAsync,
    stream: bool,
):
    jamai = client_cls()
    cols = IN_COLS[:2] + OUT_COLS[:3]
    async with _create_table(jamai, TableType.action, cols) as table_id:
        row_input_data = {"in_01": "0", "in_02": "100"}
        column_map = COLUMN_MAP_CONCURRENCY.copy()

        async def execute():
            gen_config = GenConfigUpdateRequest(
                table_id=table_id,
                column_map=column_map,
            )
            await _update_gen_config(jamai, TableType.action, gen_config)

            start_time = time.time()
            chunks = await run(
                jamai.table.add_table_rows,
                TableType.action,
                RowAddRequest(
                    table_id=table_id, data=[row_input_data], stream=stream, concurrent=True
                ),
            )
            if stream:
                assert isinstance(chunks[0], GenTableStreamChatCompletionChunk)
            else:
                assert isinstance(chunks, GenTableRowsChatCompletionChunks)
            execution_time = time.time() - start_time
            return execution_time

        execution_time_3_cols = await execute()
        column_map.pop("out_02")
        column_map.pop("out_03")
        execution_time_1_col = await execute()

        assert abs(execution_time_3_cols - execution_time_1_col) < (execution_time_1_col * 1.5)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
async def test_multirows_multicols_concurrency_timing(
    client_cls: JamAI | JamAIAsync,
    stream: bool,
):
    jamai = client_cls()
    cols = IN_COLS[:2] + OUT_COLS[:3]
    async with _create_table(jamai, TableType.action, cols) as table_id:
        rows_input_data = [
            {"in_01": "0", "in_02": "200"},
            {"in_01": "1", "in_02": "201"},
            {"in_01": "2", "in_02": "202"},
        ]
        column_map = COLUMN_MAP_CONCURRENCY

        async def execute():
            gen_config = GenConfigUpdateRequest(
                table_id=table_id,
                column_map=column_map,
            )
            await _update_gen_config(jamai, TableType.action, gen_config)

            start_time = time.time()
            chunks = await run(
                jamai.table.add_table_rows,
                TableType.action,
                RowAddRequest(
                    table_id=table_id, data=rows_input_data, stream=stream, concurrent=True
                ),
            )
            if stream:
                assert isinstance(chunks[0], GenTableStreamChatCompletionChunk)
            else:
                assert isinstance(chunks, GenTableRowsChatCompletionChunks)
            execution_time = time.time() - start_time
            return execution_time

        execution_time_3_rows = await execute()
        rows_input_data = rows_input_data[:1]
        execution_time_1_row = await execute()

        assert abs(execution_time_3_rows - execution_time_1_row) < (execution_time_1_row * 1.5)


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
async def test_multicols_dependency(
    client_cls: JamAI | JamAIAsync,
    stream: bool,
):
    jamai = client_cls()
    cols = IN_COLS[:2] + OUT_COLS[:5]
    async with _create_table(jamai, TableType.action, cols) as table_id:
        row_input_data = {"in_01": "8", "in_02": "2"}
        column_map = COLUMN_MAP_DEPENDENCY
        ground_truths = {
            "out_01": "10",
            "out_02": "-6",
            "out_03": "-60",
            "out_04": "360",
            "out_05": "120",
        }

        gen_config = GenConfigUpdateRequest(
            table_id=table_id,
            column_map=column_map,
        )
        await _update_gen_config(jamai, TableType.action, gen_config)

        chunks = await run(
            jamai.table.add_table_rows,
            TableType.action,
            RowAddRequest(table_id=table_id, data=[row_input_data], stream=stream),
        )
        if stream:
            assert isinstance(chunks[0], GenTableStreamChatCompletionChunk)
        else:
            assert isinstance(chunks, GenTableRowsChatCompletionChunks)

        # Get rows
        rows = await run(jamai.table.list_table_rows, TableType.action, table_id)
        row_id = rows.items[0]["ID"]
        row = await run(jamai.table.get_table_row, TableType.action, table_id, row_id)

        for output_column_name in column_map.keys():
            assert ground_truths[output_column_name] in row[output_column_name]["value"]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("regen_strategy", REGEN_STRATEGY)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
@pytest.mark.parametrize(
    "cols",
    [
        # input columns + output columns
        IN_COLS[:2] + OUT_COLS[:5],
        # input columns and output columns interleaved
        IN_COLS[:2] + OUT_COLS[:2] + IN_COLS[2:] + OUT_COLS[2:],
        # only input columns
        IN_COLS[:2],
    ],
)
async def test_multicols_regen(
    client_cls: JamAI | JamAIAsync,
    regen_strategy: RegenStrategy,
    stream: bool,
    cols,
):
    jamai = client_cls()
    only_input_columns = True if len([col for col in cols if col in OUT_COLS]) == 0 else False
    async with _create_table(jamai, TableType.action, cols) as table_id:
        row_input_data = {"in_01": "8", "in_02": "2"}
        regen_row_input_data = {"in_01": "9", "in_02": "8"}
        column_map = COLUMN_MAP_DEPENDENCY
        ground_truths = {
            "out_01": "10",
            "out_02": "-6",
            "out_03": "-60",
            "out_04": "360",
            "out_05": "120",
        }
        if regen_strategy == RegenStrategy.RUN_ALL:
            output_column_id = None
            regen_ground_truths = {
                "out_01": "17",
                "out_02": "-1",
                "out_03": "-17",
                "out_04": "17",
                "out_05": "5.67",
            }
        elif regen_strategy == RegenStrategy.RUN_BEFORE:
            output_column_id = "out_03"
            regen_ground_truths = {
                "out_01": "17",
                "out_02": "-1",
                "out_03": "-17",
                "out_04": "360",
                "out_05": "120",
            }
        elif regen_strategy == RegenStrategy.RUN_SELECTED:
            output_column_id = "out_02"
            regen_ground_truths = {
                "out_01": "10",
                "out_02": "-1",
                "out_03": "-60",
                "out_04": "360",
                "out_05": "120",
            }
        elif regen_strategy == RegenStrategy.RUN_AFTER:
            output_column_id = "out_02"
            regen_ground_truths = {
                "out_01": "10",
                "out_02": "-1",
                "out_03": "-10",
                "out_04": "10",
                "out_05": "3.33",
            }

        if not only_input_columns:
            gen_config = GenConfigUpdateRequest(
                table_id=table_id,
                column_map=column_map,
            )
            await _update_gen_config(jamai, TableType.action, gen_config)

        chunks = await run(
            jamai.table.add_table_rows,
            TableType.action,
            RowAddRequest(table_id=table_id, data=[row_input_data], stream=stream),
        )
        if not only_input_columns:
            if stream:
                assert isinstance(chunks[0], GenTableStreamChatCompletionChunk)
            else:
                assert isinstance(chunks, GenTableRowsChatCompletionChunks)

        # Get rows
        rows = await run(jamai.table.list_table_rows, TableType.action, table_id)
        row_id = rows.items[0]["ID"]
        row = await run(jamai.table.get_table_row, TableType.action, table_id, row_id)

        if not only_input_columns:
            for output_column_name in column_map.keys():
                assert ground_truths[output_column_name] in row[output_column_name]["value"]

        # Update input columns value
        await run(
            jamai.table.update_table_row,
            TableType.action,
            RowUpdateRequest(table_id=table_id, row_id=row_id, data=regen_row_input_data),
        )

        # Regen
        chunks = await run(
            jamai.table.regen_table_rows,
            TableType.action,
            RowRegenRequest(
                table_id=table_id,
                row_ids=[row_id],
                regen_strategy=regen_strategy,
                output_column_id=output_column_id,
                stream=stream,
                concurrent=True,
            ),
        )
        if not only_input_columns:
            if stream:
                assert isinstance(chunks[0], GenTableStreamChatCompletionChunk)
            else:
                assert isinstance(chunks, GenTableRowsChatCompletionChunks)

        # Get rows
        rows = await run(jamai.table.list_table_rows, TableType.action, table_id)
        row_id = rows.items[0]["ID"]
        row = await run(jamai.table.get_table_row, TableType.action, table_id, row_id)

        if not only_input_columns:
            for output_column_name in column_map.keys():
                assert regen_ground_truths[output_column_name] in row[output_column_name]["value"]


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("regen_strategy", REGEN_STRATEGY)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
async def test_multicols_regen_invalid_column_id(
    client_cls: JamAI | JamAIAsync,
    regen_strategy,
    stream: bool,
):
    jamai = client_cls()
    cols = IN_COLS[:2] + OUT_COLS[:5]
    invalid_output_column_id = "out_13"
    async with _create_table(jamai, TableType.action, cols) as table_id:
        row_input_data = {"in_01": "8", "in_02": "2"}
        regen_row_input_data = {"in_01": "9", "in_02": "8"}
        column_map = COLUMN_MAP_DEPENDENCY
        ground_truths = {
            "out_01": "10",
            "out_02": "-6",
            "out_03": "-60",
            "out_04": "360",
            "out_05": "120",
        }

        gen_config = GenConfigUpdateRequest(
            table_id=table_id,
            column_map=column_map,
        )
        await _update_gen_config(jamai, TableType.action, gen_config)

        chunks = await run(
            jamai.table.add_table_rows,
            TableType.action,
            RowAddRequest(table_id=table_id, data=[row_input_data], stream=stream),
        )
        if stream:
            assert isinstance(chunks[0], GenTableStreamChatCompletionChunk)
        else:
            assert isinstance(chunks, GenTableRowsChatCompletionChunks)

        # Get rows
        rows = await run(jamai.table.list_table_rows, TableType.action, table_id)
        row_id = rows.items[0]["ID"]
        row = await run(jamai.table.get_table_row, TableType.action, table_id, row_id)

        for output_column_name in column_map.keys():
            assert ground_truths[output_column_name] in row[output_column_name]["value"]

        # Update input columns value
        await run(
            jamai.table.update_table_row,
            TableType.action,
            RowUpdateRequest(table_id=table_id, row_id=row_id, data=regen_row_input_data),
        )

        # Regen
        with pytest.raises(
            ResourceNotFoundError,
            match=(
                f'`output_column_id` .*{invalid_output_column_id}.* is not found. '
                f"Available output columns:.*{'.*'.join(ground_truths.keys())}.*"
            ),
        ):
            await run(
                jamai.table.regen_table_rows,
                TableType.action,
                RowRegenRequest(
                    table_id=table_id,
                    row_ids=[row_id],
                    regen_strategy=regen_strategy,
                    output_column_id=invalid_output_column_id,
                    stream=stream,
                    concurrent=True,
                ),
            )


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
async def test_code_str(client_cls: JamAI | JamAIAsync, stream: bool):
    jamai = client_cls()
    cols = [
        ColumnSchemaCreate(id="code_column", dtype="str"),
        ColumnSchemaCreate(
            id="result_column", dtype="str", gen_config=CodeGenConfig(source_column="code_column")
        ),
    ]

    async with _create_table(jamai, TableType.action, cols) as table_id:
        test_cases = [
            {"code": "print('Hello, World!')", "expected": "Hello, World!"},
            {"code": "result = 2 + 2\nprint(result)", "expected": "4"},
            {"code": "import math\nprint(math.pi)", "expected": "3.141592653589793"},
            {"code": "result = 5 * 5", "expected": "25"},
            {"code": "result = 'Python' + ' ' + 'Programming'", "expected": "Python Programming"},
            {"code": "result = [1, 2, 3, 4, 5]\nresult = sum(result)", "expected": "15"},
            # Define factorial function as globals namespace to be able to executed recursive calls.
            # exec() creates a new local scope for the code it's executing, and the recursive calls can't access the function name in this temporary scope.
            {
                "code": "def factorial(n):\n    return 1 if n == 0 else n * factorial(n-1)\nglobals()['factorial'] = factorial\nresult = factorial(5)",
                "expected": "120",
            },
            {
                "code": "result = {x: x**2 for x in range(1, 6)}",
                "expected": "{1: 1, 2: 4, 3: 9, 4: 16, 5: 25}",
            },
        ]

        for case in test_cases:
            row_input_data = {"code_column": case["code"]}
            chunks = await run(
                jamai.table.add_table_rows,
                TableType.action,
                RowAddRequest(table_id=table_id, data=[row_input_data], stream=stream),
            )

            if stream:
                print(chunks[0])
                assert isinstance(chunks[0], GenTableStreamChatCompletionChunk)
            else:
                print(chunks)
                assert isinstance(chunks, GenTableRowsChatCompletionChunks)

            # Get rows
            rows = await run(jamai.table.list_table_rows, TableType.action, table_id)
            row_id = rows.items[0]["ID"]
            row = await run(jamai.table.get_table_row, TableType.action, table_id, row_id)
            assert row["result_column"]["value"].strip() == case["expected"]

        # Test error handling
        error_code = "print(undefined_variable)"
        row_input_data = {"code_column": error_code}
        chunks = await run(
            jamai.table.add_table_rows,
            TableType.action,
            RowAddRequest(table_id=table_id, data=[row_input_data], stream=stream),
        )
        rows = await run(jamai.table.list_table_rows, TableType.action, table_id)
        row_id = rows.items[0]["ID"]
        row = await run(jamai.table.get_table_row, TableType.action, table_id, row_id)
        assert "name 'undefined_variable' is not defined" in row["result_column"]["value"]


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "non-stream"])
async def test_code_image(client_cls: JamAI | JamAIAsync, stream: bool):
    jamai = client_cls()
    cols = [
        ColumnSchemaCreate(id="code_column", dtype="str"),
        ColumnSchemaCreate(
            id="result_column",
            dtype="image",
            gen_config=CodeGenConfig(source_column="code_column"),
        ),
    ]

    async with _create_table(jamai, TableType.action, cols) as table_id:
        test_cases = [
            {
                "code": """
import matplotlib.pyplot as plt
import io

plt.figure(figsize=(10, 5))
plt.plot([1, 2, 3, 4], [1, 4, 2, 3])
plt.title('Simple Line Plot')
buf = io.BytesIO()
plt.savefig(buf, format='png')
buf.seek(0)
result = buf.getvalue()
""",
                "expected_format": "PNG",
            },
            {
                "code": """
from PIL import Image, ImageDraw
import io

img = Image.new('RGB', (200, 200), color='red')
draw = ImageDraw.Draw(img)
draw.ellipse((50, 50, 150, 150), fill='blue')
buf = io.BytesIO()
img.save(buf, format='JPEG')
buf.seek(0)
result = buf.getvalue()
""",
                "expected_format": "JPEG",
            },
            {
                "code": """
result = b'This is not a valid image file'
""",
                "expected_format": None,
            },
        ]

        for case in test_cases:
            row_input_data = {"code_column": case["code"]}
            chunks = await run(
                jamai.table.add_table_rows,
                TableType.action,
                RowAddRequest(table_id=table_id, data=[row_input_data], stream=stream),
            )

            if stream:
                print(chunks[0])
                assert isinstance(chunks[0], GenTableStreamChatCompletionChunk)
            else:
                print(chunks)
                assert isinstance(chunks, GenTableRowsChatCompletionChunks)

            # Get rows
            rows = await run(jamai.table.list_table_rows, TableType.action, table_id)
            row_id = rows.items[0]["ID"]
            row = await run(jamai.table.get_table_row, TableType.action, table_id, row_id)
            file_uri = row["result_column"]["value"]

            if case["expected_format"] is None:
                assert file_uri is None
            else:
                assert file_uri.startswith(("file://", "s3://"))

                response = await run(jamai.file.get_raw_urls, [file_uri])
                assert isinstance(response, GetURLResponse)
                for url in response.urls:
                    if url.startswith(("http://", "https://")):
                        # Handle HTTP/HTTPS URLs
                        HEADERS = {"X-PROJECT-ID": "default"}
                        with httpx.Client() as client:
                            downloaded_content = client.get(url, headers=HEADERS).content

                        image = Image.open(io.BytesIO(downloaded_content))
                        assert image.format == case["expected_format"]

        # Test error handling
        error_code = "result = 1 / 0"
        row_input_data = {"code_column": error_code}
        chunks = await run(
            jamai.table.add_table_rows,
            TableType.action,
            RowAddRequest(table_id=table_id, data=[row_input_data], stream=stream),
        )

        rows = await run(jamai.table.list_table_rows, TableType.action, table_id)
        row_id = rows.items[0]["ID"]
        row = await run(jamai.table.get_table_row, TableType.action, table_id, row_id)

        assert row["result_column"]["value"] is None


if __name__ == "__main__":
    asyncio.run(test_multicols_regen_invalid_column_id(CLIENT_CLS[-1], REGEN_STRATEGY[1], True))
