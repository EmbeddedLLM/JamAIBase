from owl.db.gen_executor import _Executor
from owl.db.gen_table import ColumnMetadata
from owl.types import (
    ColumnDtype,
    EmbedGenConfig,
    LLMGenConfig,
    MultiRowAddRequest,
    MultiRowRegenRequest,
    PythonGenConfig,
    RegenStrategy,
    RowAdd,
)
from owl.utils.concurrency import determine_concurrent_batches

DEFAULT_CELL_LIMIT = 15
TABLE_ID = "tbl"
EMBED_MODEL = "embed-model"


def _column(
    column_id: str,
    *,
    gen_config: LLMGenConfig | EmbedGenConfig | PythonGenConfig | None = None,
) -> ColumnMetadata:
    return ColumnMetadata(
        table_id=TABLE_ID,
        column_id=column_id,
        dtype=ColumnDtype.STR,
        vlen=0,
        gen_config=gen_config,
        column_order=0,
    )


def _llm_column(column_id: str, *, prompt: str = "Input") -> ColumnMetadata:
    return _column(column_id, gen_config=LLMGenConfig(prompt=prompt))


def _python_column(column_id: str, *, code: str) -> ColumnMetadata:
    return _column(column_id, gen_config=PythonGenConfig(python_code=code))


def _embed_column(column_id: str, *, source_column: str) -> ColumnMetadata:
    return _column(
        column_id,
        gen_config=EmbedGenConfig(embedding_model=EMBED_MODEL, source_column=source_column),
    )


def _plan(body, columns, *, concurrent=True, multi_turn=False):
    max_cols = _Executor.get_max_concurrent_columns(columns)
    return determine_concurrent_batches(
        columns=columns,
        body=body,
        concurrent=concurrent,
        multi_turn=multi_turn,
        cell_limit=DEFAULT_CELL_LIMIT,
        max_concurrent_cols=max_cols,
    )


def test_single_output_prefers_rows():
    columns = [_column("input"), _llm_column("output")]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    assert col_batch == 1
    assert row_batch == DEFAULT_CELL_LIMIT


def test_multiple_outputs_balances_columns_and_rows():
    columns = [_column("input")]
    columns.extend(_llm_column(f"o{i}") for i in range(3))
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    assert col_batch == 3
    assert row_batch == DEFAULT_CELL_LIMIT // 3


def test_existing_output_values_reduce_column_batch():
    columns = [_column("input")]
    columns.extend(_llm_column(f"o{i}") for i in range(1, 4))
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value", "o1": "existing"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    assert col_batch == 2
    assert row_batch == DEFAULT_CELL_LIMIT // 2


def test_row_add_uses_missing_outputs():
    columns = [_column("input"), _llm_column("output")]
    body = RowAdd(table_id="tbl", data={"input": "value"}, stream=True)
    col_batch, row_batch = _plan(body, columns)
    assert col_batch == 1
    assert row_batch == DEFAULT_CELL_LIMIT


def test_multi_row_regen_run_selected():
    columns = [_column("input")]
    columns.extend(_llm_column(f"o{i}") for i in range(1, 4))
    body = MultiRowRegenRequest(
        table_id="tbl",
        row_ids=["r1", "r2"],
        regen_strategy=RegenStrategy.RUN_SELECTED,
        output_column_id="o2",
        stream=True,
    )
    col_batch, row_batch = _plan(body, columns)
    assert col_batch == 1
    assert row_batch == DEFAULT_CELL_LIMIT


def test_multi_row_regen_run_after():
    columns = [_column("input")]
    columns.extend(_llm_column(f"o{i}") for i in range(1, 5))
    body = MultiRowRegenRequest(
        table_id="tbl",
        row_ids=["r1"],
        regen_strategy=RegenStrategy.RUN_AFTER,
        output_column_id="o2",
        stream=True,
    )
    col_batch, row_batch = _plan(body, columns)
    assert col_batch == 3
    assert row_batch == DEFAULT_CELL_LIMIT // 3


def test_multi_turn_forces_single_row():
    columns = [_column("input"), _llm_column("output")]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns, multi_turn=True)
    assert col_batch == 1
    assert row_batch == 1


def test_non_concurrent_uses_defaults():
    columns = [_column("input"), _llm_column("output")]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value"}],
        stream=True,
        concurrent=False,
    )
    col_batch, row_batch = determine_concurrent_batches(
        columns=columns,
        body=body,
        concurrent=False,
        multi_turn=False,
        cell_limit=DEFAULT_CELL_LIMIT,
        max_concurrent_cols=None,
    )
    assert col_batch == 1
    assert row_batch == DEFAULT_CELL_LIMIT


def test_linear_dependencies_reduce_column_batch():
    """Test that linear dependencies (A->B->C) reduce column batch size to 1."""
    # Create columns with linear dependencies: A -> B -> C
    columns = [
        _llm_column("A", prompt="Input"),
        _llm_column("B", prompt="${A}"),
        _llm_column("C", prompt="${B}"),
    ]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    # With dependencies A->B->C, only 1 column can be processed at a time
    assert col_batch == 1
    # But we can process all 15 rows for that column
    assert row_batch == DEFAULT_CELL_LIMIT


def test_independent_columns_allow_larger_batches():
    """Test that independent columns allow larger column batches."""
    # Create independent columns
    columns = [
        _llm_column("A", prompt="Input"),
        _llm_column("B", prompt="Input"),
        _llm_column("C", prompt="Input"),
    ]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    # With no dependencies, all 3 columns can be processed concurrently
    assert col_batch == 3
    assert row_batch == DEFAULT_CELL_LIMIT // 3


def test_mixed_dependencies():
    """Test mixed scenario with both dependent and independent columns."""
    # Create mixed dependencies: A -> B, C (independent)
    columns = [
        _llm_column("A", prompt="Input"),
        _llm_column("B", prompt="${A}"),
        _llm_column("C", prompt="Input"),
    ]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    # Level 0: A, C (2 columns)
    # Level 1: B (1 column, depends on A)
    # So max concurrent columns is 2
    assert col_batch == 2
    assert row_batch == DEFAULT_CELL_LIMIT // 2


def test_python_config_dependencies():
    """Test PythonGenConfig dependencies (depends on all columns to the left)."""
    # Create columns where Python config depends on all left columns
    columns = [
        _llm_column("A", prompt="Input"),
        _python_column("B", code="return row['A']"),
        _python_column("C", code="return row['B']"),
    ]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    # B depends on A, C depends on B (and implicitly on A)
    # So only 1 column can be processed at a time
    assert col_batch == 1
    assert row_batch == DEFAULT_CELL_LIMIT


def test_embed_config_dependencies():
    """Test EmbedGenConfig dependencies."""
    # Create columns with embedding dependencies
    columns = [
        _column("text"),
        _embed_column("embed", source_column="text"),
    ]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"text": "value"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    # Only 1 output column, so batch size should be 1
    assert col_batch == 1
    assert row_batch == DEFAULT_CELL_LIMIT


def test_branching_dependencies():
    """Test branching dependencies (A -> B, A -> C)."""
    # Create branching dependencies: A -> B, A -> C
    columns = [
        _llm_column("A", prompt="Input"),
        _llm_column("B", prompt="${A}"),
        _llm_column("C", prompt="${A}"),
    ]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"input": "value"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    # Level 0: A (1 column)
    # Level 1: B, C (2 columns, both depend on A)
    # So max concurrent columns is 2
    assert col_batch == 2
    assert row_batch == DEFAULT_CELL_LIMIT // 2


def test_inputs_do_not_block_dependency_levels():
    """Ensure dependencies on input columns do not prevent downstream concurrency."""
    columns = [
        _column("A"),
        _column("B"),
        _llm_column("C", prompt="${A}${B}"),
        _llm_column("D", prompt="${C}"),
        _llm_column("E", prompt="${C}"),
        _llm_column("F", prompt="${E}"),
    ]
    body = MultiRowAddRequest(
        table_id="tbl",
        data=[{"A": "foo", "B": "bar"}, {"A": "baz", "B": "qux"}],
        stream=True,
        concurrent=True,
    )
    col_batch, row_batch = _plan(body, columns)
    assert col_batch == 2
    assert row_batch == DEFAULT_CELL_LIMIT // 2
