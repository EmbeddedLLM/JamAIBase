from typing import TYPE_CHECKING, Any, Sequence

from owl.types import (
    MultiRowAddRequest,
    MultiRowRegenRequest,
    RegenStrategy,
    RowAdd,
    RowRegen,
)
from owl.utils.exceptions import BadInputError

if TYPE_CHECKING:
    from owl.db.gen_table import ColumnMetadata


def determine_concurrent_batches(
    *,
    columns: Sequence["ColumnMetadata"],
    body: MultiRowAddRequest | MultiRowRegenRequest | RowAdd | RowRegen,
    concurrent: bool,
    multi_turn: bool,
    cell_limit: int,
    max_concurrent_cols: int | None,
) -> tuple[int, int]:
    """
    Determine optimal concurrent column and row batch sizes for a request.

    This function balances between maximizing parallelism and respecting
    column dependencies to ensure correct generation ordering.

    Args:
        columns: Sequence of column metadata objects
        body: Request body containing generation parameters
        concurrent: Whether concurrent processing is enabled
        multi_turn: Whether multi-turn generation is enabled
        cell_limit: Maximum number of cells to process concurrently

    Returns:
        Tuple of (column_batch_size, row_batch_size)
    """
    if not concurrent:
        return _handle_non_concurrent_case(multi_turn, cell_limit)

    if max_concurrent_cols is None:
        raise BadInputError("max_concurrent_cols must be provided when concurrency is enabled.")

    # Count how many outputs need to be generated
    estimated_outputs = _estimate_outputs_to_generate(columns, body)

    # Calculate optimal batch sizes
    return _calculate_batch_sizes(
        estimated_outputs=estimated_outputs,
        max_concurrent_cols=max_concurrent_cols,
        multi_turn=multi_turn,
        cell_limit=cell_limit,
    )


def _handle_non_concurrent_case(multi_turn: bool, cell_limit: int) -> tuple[int, int]:
    """Handle the simple case where concurrent processing is disabled."""
    if multi_turn:
        return 1, 1
    return 1, max(1, cell_limit)


def _estimate_outputs_to_generate(
    columns: Sequence["ColumnMetadata"],
    body: MultiRowAddRequest | MultiRowRegenRequest | RowAdd | RowRegen,
) -> int:
    """Estimate how many output columns need to be generated."""
    output_columns = [col for col in columns if col.is_output_column]
    if not output_columns:
        return 1

    def count_missing_outputs(row_data: dict[str, Any]) -> int:
        """Count how many outputs are missing from the provided data."""
        if not isinstance(row_data, dict):
            return len(output_columns)
        provided = set(row_data.keys())
        return sum(1 for col in output_columns if col.column_id not in provided)

    # Estimate based on request type
    match body:
        case RowAdd():
            return max(1, count_missing_outputs(body.data))
        case MultiRowAddRequest():
            if not body.data:
                return len(output_columns)
            return max(count_missing_outputs(row) for row in body.data)
        case RowRegen():
            return _estimate_regen_outputs(
                strategy=body.regen_strategy,
                output_column_id=body.output_column_id,
                output_column_ids=[col.column_id for col in output_columns],
            )
        case MultiRowRegenRequest():
            return _estimate_regen_outputs(
                strategy=body.regen_strategy,
                output_column_id=body.output_column_id,
                output_column_ids=[col.column_id for col in output_columns],
            )


def _calculate_batch_sizes(
    *,
    estimated_outputs: int,
    max_concurrent_cols: int,
    multi_turn: bool,
    cell_limit: int,
) -> tuple[int, int]:
    """Calculate optimal column and row batch sizes based on constraints."""
    max_cells = max(1, cell_limit)

    # Column batch is constrained by dependencies, estimated outputs, and cell limit
    col_batch_size = max(1, min(max_concurrent_cols, estimated_outputs, max_cells))

    if multi_turn:
        row_batch_size = 1
    else:
        # Row batch uses remaining capacity
        row_batch_size = max(1, max_cells // col_batch_size)

    return col_batch_size, row_batch_size


def _estimate_regen_outputs(
    *,
    strategy: RegenStrategy,
    output_column_id: str | None,
    output_column_ids: Sequence[str],
) -> int:
    if not output_column_ids:
        return 0
    if strategy == RegenStrategy.RUN_SELECTED:
        return 1
    if output_column_id not in output_column_ids or output_column_id is None:
        return len(output_column_ids)
    idx = output_column_ids.index(output_column_id)
    if strategy == RegenStrategy.RUN_BEFORE:
        return idx + 1
    if strategy == RegenStrategy.RUN_AFTER:
        return len(output_column_ids) - idx
    return len(output_column_ids)
