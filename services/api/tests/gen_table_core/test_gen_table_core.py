import asyncio
import csv
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from jamaibase.types import ProjectRead
from owl.db.gen_table import (
    GENTABLE_ENGINE,
    ColumnDtype,
    ColumnMetadata,
    GenerativeTableCore,
    TableMetadata,
)
from owl.types import LLMGenConfig, TableType
from owl.utils.exceptions import BadInputError, ResourceNotFoundError
from owl.utils.test import (
    GPT_41_NANO_CONFIG,
    GPT_41_NANO_DEPLOYMENT,
    create_deployment,
    create_model_config,
    create_project,
    setup_organizations,
)

VECTOR_LEN = 2


@dataclass(slots=True)
class Session:
    projects: list[ProjectRead]
    chat_model_id: str


@dataclass(slots=True)
class Setup:
    projects: list[ProjectRead]
    chat_model_id: str
    table_type: str
    table_id: str
    schema_id: str
    table: GenerativeTableCore


@pytest.fixture(autouse=True, scope="module")
def session():
    with setup_organizations() as ctx:
        with (
            create_project(dict(name="Mickey 17"), user_id=ctx.superuser.id) as p0,
            create_project(dict(name="Mickey 18"), user_id=ctx.superuser.id) as p1,
            create_model_config(GPT_41_NANO_CONFIG) as llm_config,
            create_deployment(GPT_41_NANO_DEPLOYMENT),
        ):
            yield Session(
                projects=[p0, p1],
                chat_model_id=llm_config.id,
            )


@pytest.fixture(autouse=True, scope="function")
async def setup(session: Session):
    """Fixture to set up and tear down test environment"""
    table_type = TableType.ACTION
    table_id = "Table (test)"
    project_id = session.projects[0].id
    schema_id = f"{project_id}_{table_type}"
    # Drop schema
    await GenerativeTableCore.drop_schema(project_id=project_id, table_type=table_type)

    # Create table
    table = await GenerativeTableCore.create_table(
        project_id=project_id,
        table_type=table_type,
        table_metadata=TableMetadata(
            table_id=table_id,
            title="Test Table",
            parent_id=None,
            version="1",
            versioning_enabled=True,
            meta={},
        ),
        column_metadata_list=[
            ColumnMetadata(
                column_id="col (1)",
                table_id=table_id,
                dtype=ColumnDtype.STR,
                vlen=0,
                gen_config=None,
                column_order=1,
                meta={},
            ),
            ColumnMetadata(
                column_id="col (2)",
                table_id=table_id,
                dtype=ColumnDtype.INT,
                vlen=0,
                gen_config=None,
                column_order=2,
                meta={},
            ),
            ColumnMetadata(
                column_id="vector_col",
                table_id=table_id,
                dtype=ColumnDtype.FLOAT,
                vlen=VECTOR_LEN,
                gen_config=None,
                column_order=3,
                meta={},
            ),
        ],
    )
    yield Setup(
        projects=session.projects,
        chat_model_id=session.chat_model_id,
        table_type=table_type,
        table_id=table_id,
        schema_id=schema_id,
        table=table,
    )
    # Clean up table
    async with GENTABLE_ENGINE.transaction() as conn:
        await conn.execute(f"""
        DROP SCHEMA IF EXISTS "{schema_id}" CASCADE
        """)
    # https://github.com/MagicStack/asyncpg/issues/293#issuecomment-395069799
    # Need to close the connection, such that the next test will create pool on the new event loop
    await GENTABLE_ENGINE.close()


@contextmanager
def assert_updated_time(table: GenerativeTableCore):
    """Assert that table "updated_at" has been updated"""
    start_time = table.table_metadata.updated_at
    try:
        yield
    finally:
        assert table.table_metadata.updated_at > start_time


class TestImportExportOperations:
    async def test_export_empty_table(self, setup: Setup, tmp_path):
        """Test exporting and importing an empty table preserves schema"""
        table = setup.table

        # Export empty table
        export_path = tmp_path / "empty_export.parquet"
        await table.export_table(export_path)
        assert export_path.exists()

        # Import empty table
        imported_table = await GenerativeTableCore.import_table(
            project_id=setup.projects[0].id,
            table_type=setup.table_type,
            source=export_path,
            table_id_dst="imported_empty_table",
        )

        # Verify schema preserved
        assert len((await imported_table.list_rows()).items) == 0
        assert len(imported_table.column_metadata) == len(table.column_metadata)
        for orig_col, imp_col in zip(
            table.column_metadata, imported_table.column_metadata, strict=True
        ):
            assert orig_col.column_id == imp_col.column_id
            assert orig_col.dtype == imp_col.dtype
            assert orig_col.vlen == imp_col.vlen

    async def test_import_table_to_new_project(self, setup: Setup, tmp_path):
        """Test exporting and importing an empty table preserves schema"""
        table = setup.table
        new_project_id = setup.projects[1].id
        # cleanup before test
        await GenerativeTableCore.drop_schema(
            project_id=new_project_id, table_type=setup.table_type
        )

        # Export empty table
        export_path = tmp_path / "empty_export.parquet"
        await table.export_table(export_path)
        assert export_path.exists()

        # Import empty table
        imported_table = await GenerativeTableCore.import_table(
            project_id=new_project_id,
            table_type=setup.table_type,
            source=export_path,
            table_id_dst="imported_empty_table",
        )

        # Verify schema preserved
        assert len((await imported_table.list_rows()).items) == 0
        assert len(imported_table.column_metadata) == len(table.column_metadata)
        for orig_col, imp_col in zip(
            table.column_metadata, imported_table.column_metadata, strict=True
        ):
            assert orig_col.column_id == imp_col.column_id
            assert orig_col.dtype == imp_col.dtype
            assert orig_col.vlen == imp_col.vlen

    async def test_state_column_preservation(self, setup: Setup, tmp_path):
        """Test state columns are preserved during export/import"""
        table = setup.table

        # Add row with state values
        new_row = {
            "col (1)": "test",
            "col (2)": 123,
            "vector_col": np.random.rand(VECTOR_LEN),
        }
        await table.add_rows([new_row])

        # Export table
        export_path = tmp_path / "state_export.parquet"
        await table.export_table(export_path)

        # Import table
        imported_table = await GenerativeTableCore.import_table(
            project_id=setup.projects[0].id,
            table_type=setup.table_type,
            source=export_path,
            table_id_dst="imported_state_table",
        )

        # Verify state columns preserved
        rows = (await imported_table.list_rows(remove_state_cols=False)).items
        assert len(rows) == 1
        for state_col, _ in new_row.items():
            assert rows[0].get(f"{state_col}_") is not None

    async def test_export_table_basic(self, setup: Setup, tmp_path):
        """Test basic table export functionality"""
        # Create table
        table = setup.table

        # Add test data
        await table.add_rows(
            [{"col (1)": "test1", "col (2)": 123, "vector_col": np.random.rand(VECTOR_LEN)}]
        )

        # Export table
        export_path = tmp_path / "exported_table.parquet"
        await table.export_table(export_path)

        # Verify file exists
        assert export_path.exists()
        assert export_path.stat().st_size > 0

    async def test_export_table_error_cases(self, setup: Setup, tmp_path):
        """Test error cases for table export"""
        # Create table
        table = setup.table

        # Test invalid path
        invalid_path = Path("/invalid/path/export.parquet")
        with pytest.raises(ResourceNotFoundError):
            await table.export_table(invalid_path)

    async def test_import_table_basic(self, setup: Setup, tmp_path):
        """Test basic table import functionality"""
        # Create and export test table
        table = setup.table
        await table.add_rows(
            [{"col (1)": "test1", "col (2)": 123, "vector_col": np.random.rand(VECTOR_LEN)}]
        )
        export_path = tmp_path / "exported_table.parquet"
        await table.export_table(export_path)

        # Import table with new name
        imported_table = await GenerativeTableCore.import_table(
            project_id=setup.projects[0].id,
            table_type=setup.table_type,
            source=export_path,
            table_id_dst="imported_table",
        )

        # Verify imported data
        rows = (await imported_table.list_rows()).items
        assert len(rows) == 1
        assert rows[0]["col (1)"] == "test1"
        assert rows[0]["col (2)"] == 123
        assert len(rows[0]["vector_col"]) == VECTOR_LEN

    async def test_import_table_error_cases(self, setup: Setup, tmp_path):
        """Test error cases for table import"""
        # Test invalid path
        invalid_path = Path("/invalid/path/import.parquet")
        with pytest.raises(ResourceNotFoundError):
            await GenerativeTableCore.import_table(
                project_id=setup.projects[0].id,
                table_type=setup.table_type,
                source=invalid_path,
                table_id_dst="imported_table",
            )

    async def test_export_import_parquet_basic(self, setup: Setup, tmp_path):
        """Test basic Parquet export/import functionality with detailed verification"""
        table = setup.table

        # Add test data with different types
        test_data = [
            {
                "col (1)": "test1",
                "col (2)": 123,
                "vector_col": np.random.rand(VECTOR_LEN),
            }
        ]
        await table.add_rows(test_data)

        # Get original metadata and columns
        original_metadata = table.table_metadata
        original_columns = table.column_metadata

        # Export to Parquet
        export_path = tmp_path / "exported_table.parquet"
        await table.export_table(export_path)

        # Verify file exists
        assert export_path.exists()
        assert export_path.stat().st_size > 0

        # Import with new name
        imported_table = await GenerativeTableCore.import_table(
            project_id=setup.projects[0].id,
            table_type=setup.table_type,
            source=export_path,
            table_id_dst="imported_table_parquet",
        )

        # Verify imported data
        rows = (await imported_table.list_rows()).items
        assert len(rows) == 1

        # Detailed data comparison
        original_row = (await table.list_rows()).items[0]
        imported_row = rows[0]

        # Compare all fields except internal IDs
        for data in test_data:
            for key in data.keys():
                if isinstance(data[key], np.ndarray):
                    np.testing.assert_array_equal(original_row[key], imported_row[key])
                else:
                    assert original_row[key] == imported_row[key]

        # Verify metadata preservation
        imported_metadata = imported_table.table_metadata
        assert imported_metadata.title == original_metadata.title
        assert imported_metadata.meta == original_metadata.meta
        # assert imported_metadata.version == original_metadata.version

        # Verify column preservation
        imported_columns = imported_table.column_metadata
        assert len(imported_columns) == len(original_columns)

        for orig_col, imp_col in zip(original_columns, imported_columns, strict=True):
            assert orig_col.column_id == imp_col.column_id
            assert orig_col.dtype == imp_col.dtype
            assert orig_col.vlen == imp_col.vlen
            assert orig_col.column_order == imp_col.column_order

    async def test_import_recreates_indexes(self, setup: Setup, tmp_path):
        """Verify imported tables have all indexes recreated"""
        # Export original table
        export_path = tmp_path / "export.parquet"
        await setup.table.export_table(export_path)

        # Import to new table
        imported = await GenerativeTableCore.import_table(
            project_id=setup.projects[0].id,
            table_type=setup.table_type,
            source=export_path,
            table_id_dst="imported_with_indexes",
        )

        # Verify indexes exist
        async with GENTABLE_ENGINE.transaction() as conn:
            # Check FTS index
            fts_index = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pg_indexes
                WHERE schemaname = $1 AND tablename = $2 AND indexname LIKE '%_fts_idx'
            """,
                imported.schema_id,
                imported.table_id,
            )
            assert fts_index > 0

            # Check vector indexes
            vec_indexes = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pg_indexes
                WHERE schemaname = $1 AND tablename = $2 AND indexname LIKE '%_vec_idx'
            """,
                imported.schema_id,
                imported.table_id,
            )
            assert vec_indexes == len(imported.vector_column_names)

    async def test_export_import_parquet_large_data(self, setup: Setup, tmp_path):
        """Test Parquet export/import with large dataset and detailed verification"""
        table = setup.table

        # Add 1000 rows of test data
        test_data = [
            {
                "col (1)": f"test{i}",
                "col (2)": i,
                "vector_col": np.random.rand(VECTOR_LEN),
            }
            for i in range(1000)
        ]
        await table.add_rows(test_data)

        # Get original metadata and columns
        original_metadata = table.table_metadata
        original_columns = table.column_metadata

        # Export to Parquet
        export_path = tmp_path / "large_export.parquet"
        await table.export_table(export_path)

        # Import with new name
        imported_table = await GenerativeTableCore.import_table(
            project_id=setup.projects[0].id,
            table_type=setup.table_type,
            source=export_path,
            table_id_dst="large_import_parquet",
        )

        # Verify all data was imported
        rows = (await imported_table.list_rows(limit=1000)).items
        assert len(rows) == 1000

        # Get original rows for comparison
        original_rows = (await table.list_rows(limit=1000)).items

        # Detailed data comparison
        for orig_row, imp_row in zip(original_rows, rows, strict=True):
            assert orig_row["col (1)"] == imp_row["col (1)"]
            assert orig_row["col (2)"] == imp_row["col (2)"]
            np.testing.assert_array_equal(orig_row["vector_col"], imp_row["vector_col"])

        # Verify metadata preservation
        imported_metadata = imported_table.table_metadata
        assert imported_metadata.title == original_metadata.title
        assert imported_metadata.meta == original_metadata.meta
        # assert imported_metadata.version == original_metadata.version

        # Verify column preservation
        imported_columns = imported_table.column_metadata
        assert len(imported_columns) == len(original_columns)

        for orig_col, imp_col in zip(original_columns, imported_columns, strict=True):
            assert orig_col.column_id == imp_col.column_id
            assert orig_col.dtype == imp_col.dtype
            assert orig_col.vlen == imp_col.vlen
            assert orig_col.column_order == imp_col.column_order

    async def test_export_parquet_error_cases(self, setup: Setup, tmp_path):
        """Test Parquet export error cases"""
        table = setup.table

        # Test invalid path
        invalid_path = Path("/invalid/path/export.parquet")
        with pytest.raises(ResourceNotFoundError):
            await table.export_table(invalid_path)

        # Test invalid format
        with pytest.raises(BadInputError):
            await table.export_table(tmp_path / "test.csv")

    async def test_import_parquet_invalid_path_cases(self, setup: Setup, tmp_path):
        """Test Parquet import invalid case cases"""
        # Test invalid path
        invalid_path = Path("/invalid/path/import.parquet")
        with pytest.raises(ResourceNotFoundError):
            await GenerativeTableCore.import_table(
                project_id=setup.projects[0].id,
                table_type=setup.table_type,
                source=invalid_path,
                table_id_dst="imported_table",
            )

    async def test_import_corrupt_files(self, setup: Setup, tmp_path):
        """Test handling of corrupted import files."""
        # Setup
        corrupt_path = tmp_path / "corrupt.parquet"

        # Test malformed file
        corrupt_path.write_bytes(b"PAR1\x00\x00INVALID\x00PAR1")
        with pytest.raises(BadInputError, match="contains bad data"):
            await GenerativeTableCore.import_table(
                project_id=setup.projects[0].id,
                table_type=setup.table_type,
                source=corrupt_path,
                table_id_dst="corrupt_test_table",
            )

        # Test partial file (truncated)
        with open(corrupt_path, "wb") as f:
            f.write(b"PAR1")  # Only magic bytes
        with pytest.raises(BadInputError, match="contains bad data"):
            await GenerativeTableCore.import_table(
                project_id=setup.projects[0].id,
                table_type=setup.table_type,
                source=corrupt_path,
                table_id_dst="corrupt_test_table",
            )

        # Test invalid metadata
        df = pd.DataFrame({"col (1)": [1, 2, 3]})
        df.to_parquet(corrupt_path)
        # Corrupt the metadata by overwriting footer
        with open(corrupt_path, "r+b") as f:
            f.seek(-100, 2)
            f.write(b"X" * 100)
        with pytest.raises(BadInputError, match="contains bad data"):
            await GenerativeTableCore.import_table(
                project_id=setup.projects[0].id,
                table_type=setup.table_type,
                source=corrupt_path,
                table_id_dst="corrupt_test_table",
            )

    async def test_export_data_basic(self, setup: Setup, tmp_path):
        """Test basic data export to CSV"""
        # Create table
        table = setup.table

        # Add test data
        await table.add_rows(
            [{"col (1)": "test1", "col (2)": 123, "vector_col": np.random.rand(VECTOR_LEN)}]
        )

        # Export data
        export_path = tmp_path / "exported_data.csv"
        await table.export_data(export_path)

        # Verify CSV content
        with open(export_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["col (1)"] == "test1"
            assert rows[0]["col (2)"] == "123"
            assert len(rows[0]["vector_col"].split(",")) == VECTOR_LEN

    async def test_export_data_error_cases(self, setup: Setup, tmp_path):
        """Test error cases for data export"""
        # Create table
        table = setup.table

        # Test invalid path
        invalid_path = Path("/invalid/path/export.csv")
        with pytest.raises(BadInputError):
            await table.export_data(invalid_path)

    async def test_import_data(self, setup: Setup, tmp_path):
        """Test importing data from CSV"""
        # Create table
        table = setup.table

        # Create test CSV
        csv_path = tmp_path / "import.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["col (1)", "col (2)", "vector_col"])
            writer.writeheader()
            writer.writerow(
                {
                    "col (1)": "import1",
                    "col (2)": "1",
                    "vector_col": np.random.rand(VECTOR_LEN).tolist(),
                }
            )
            writer.writerow(
                {
                    "col (1)": "import2",
                    "col (2)": "2",
                    "vector_col": np.random.rand(VECTOR_LEN).tolist(),
                }
            )

        # Import data
        await table.import_data(csv_path)

        # Verify imported data
        rows = (await table.list_rows()).items
        assert len(rows) == 2
        assert rows[0]["col (1)"] == "import1"
        assert rows[0]["col (2)"] == 1
        assert len(rows[0]["vector_col"]) == VECTOR_LEN

    async def test_import_with_column_mapping(self, setup: Setup, tmp_path):
        """Test importing data with column mapping"""
        # Create table
        table = setup.table

        # Create test CSV with different column names
        csv_path = tmp_path / "import.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["csv_col1", "csv_col2", "csv_vector"])
            writer.writeheader()
            writer.writerow(
                {
                    "csv_col1": "mapped1",
                    "csv_col2": "1",
                    "csv_vector": np.random.rand(VECTOR_LEN).tolist(),
                }
            )

        # Import with column mapping
        column_id_mapping = {
            "csv_col1": "col (1)",
            "csv_col2": "col (2)",
            "csv_vector": "vector_col",
        }
        await table.import_data(csv_path, column_id_mapping=column_id_mapping)

        # Verify imported data
        rows = (await table.list_rows()).items
        assert len(rows) == 1
        assert rows[0]["col (1)"] == "mapped1"
        assert rows[0]["col (2)"] == 1
        assert len(rows[0]["vector_col"]) == VECTOR_LEN

    async def test_import_error_handling(self, setup: Setup, tmp_path):
        """Test error handling during import"""
        # Create table
        table = setup.table

        # Test missing file
        with pytest.raises(ResourceNotFoundError):
            await table.import_data(Path("/nonexistent/file.csv"))

        # Test invalid column mapping
        csv_path = tmp_path / "import.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["invalid_col"])
            writer.writeheader()
            writer.writerow({"invalid_col": "value"})
        await table.import_data(csv_path)
        assert len((await table.list_rows()).items) == 0

        # Test invalid vector data
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["vector_col"])
            writer.writeheader()
            writer.writerow({"vector_col": "invalid,vector,data"})
        with pytest.raises(BadInputError):
            await table.import_data(csv_path)


# Include existing test classes here...
class TestTableOperations:
    async def test_table_creation(self, setup: Setup):
        """Test creating a new data table with metadata"""
        # Verify table exists
        async with GENTABLE_ENGINE.transaction() as conn:
            exists = await conn.fetchval(
                f'SELECT EXISTS (SELECT 1 FROM "{setup.schema_id}"."TableMetadata" WHERE table_id = $1)',
                "Table (test)",
            )
            assert exists

    async def test_table_creation_concurrent(self, session: Session):
        """Test creating a new data table with metadata concurrently"""
        table_type = TableType.ACTION
        project_id = session.projects[0].id
        # Drop schema
        await GenerativeTableCore.drop_schemas(project_id)
        # Create table
        num_tables = 3
        await asyncio.gather(
            *[
                GenerativeTableCore.create_table(
                    project_id=project_id,
                    table_type=table_type,
                    table_metadata=TableMetadata(
                        table_id=f"Table {i}",
                        title="Test Table",
                        parent_id=None,
                        version="1",
                        versioning_enabled=True,
                        meta={},
                    ),
                    column_metadata_list=[
                        ColumnMetadata(
                            column_id="col",
                            table_id=f"Table {i}",
                            dtype=ColumnDtype.STR,
                            vlen=0,
                            gen_config=None,
                            column_order=1,
                            meta={},
                        ),
                    ],
                )
                for i in range(num_tables)
            ]
        )
        # Verify table exists
        async with GENTABLE_ENGINE.transaction() as conn:
            for i in range(num_tables):
                exists = await conn.fetchval(
                    f'SELECT EXISTS (SELECT 1 FROM "{project_id}_{table_type}"."TableMetadata" WHERE table_id = $1)',
                    f"Table {i}",
                )
                assert exists

    async def test_table_duplication(self, setup: Setup):
        """Test duplicating a table with data"""
        # Create original table
        table = setup.table

        # Insert test data
        test_data = [
            {
                "col (1)": "value1",
                "col (2)": 1,
            },
            {
                "col (1)": "value2",
                "col (2)": 2,
            },
            {
                "col (1)": None,
                "col (2)": 3,
            },  # Test null handling
        ]
        await table.add_rows(test_data)

        # Duplicate table
        new_table = await GenerativeTableCore.duplicate_table(
            project_id=setup.projects[0].id,
            table_type=setup.table_type,
            table_id_src=setup.table_id,
            table_id_dst="test_table_copy",
        )

        # Verify new table exists
        async with GENTABLE_ENGINE.transaction() as conn:
            exists = await conn.fetchval(
                f'SELECT EXISTS (SELECT 1 FROM "{setup.schema_id}"."TableMetadata" WHERE table_id = $1)',
                "test_table_copy",
            )
            assert exists

        # Verify data was copied correctly
        original_rows = (await table.list_rows()).items
        new_rows = (await new_table.list_rows()).items

        # Verify row count matches
        assert len(new_rows) == len(original_rows)

        # Verify specific data values
        for row, test_row in zip(new_rows, test_data, strict=True):
            assert row["col (1)"] == test_row["col (1)"]
            assert row["col (2)"] == test_row["col (2)"]

    async def test_duplicate_recreates_indexes(self, setup: Setup):
        """Verify duplicated tables have all indexes recreated"""
        original = setup.table
        duplicated = await GenerativeTableCore.duplicate_table(
            project_id=setup.projects[0].id,
            table_type=setup.table_type,
            table_id_src=original.table_id,
            table_id_dst="duplicated_with_indexes",
        )

        # Verify indexes exist
        async with GENTABLE_ENGINE.transaction() as conn:
            # Check FTS index
            fts_index = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pg_indexes
                WHERE schemaname = $1 AND tablename = $2 AND indexname LIKE '%_fts_idx'
            """,
                duplicated.schema_id,
                duplicated.table_id,
            )
            assert fts_index > 0

            # Check vector indexes match original count
            original_vec_count = len(original.vector_column_names)
            duplicated_vec_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pg_indexes
                WHERE schemaname = $1 AND tablename = $2 AND indexname LIKE '%_vec_idx'
            """,
                duplicated.schema_id,
                duplicated.table_id,
            )
            assert duplicated_vec_count == original_vec_count

    async def test_rename_table(self, setup: Setup):
        """Verify renaming table works properly by checking it can be opened and the associated ColumnMetadata and TableMetadata exists"""
        table = setup.table
        new_name = "renamed_table"
        with assert_updated_time(table):
            # Rename table
            await table.rename_table(new_name)
            # Verify table was renamed by opening it.
            new_table = await GenerativeTableCore.open_table(
                project_id=setup.projects[0].id,
                table_type=setup.table_type,
                table_id=new_name,
            )
            # verify associated ColumnMetadata and TableMetadata exist
            assert all([col.table_id == new_name for col in new_table.column_metadata])
            assert new_table.table_metadata.table_id == new_name

    async def test_rename_table_has_indexes(self, setup: Setup):
        """Verify renaming a table updates all associated indexes"""
        table = setup.table
        new_name = "renamed_table"

        # Get original index names
        async with GENTABLE_ENGINE.transaction() as conn:
            original_indexes = await conn.fetch(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname = $1 AND tablename = $2
            """,
                table.schema_id,
                table.table_id,
            )

        # Rename table
        await table.rename_table(new_name)

        # Verify indexes were renamed
        async with GENTABLE_ENGINE.transaction() as conn:
            new_indexes = await conn.fetch(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname = $1 AND tablename = $2
            """,
                table.schema_id,
                new_name,
            )

            # Check all indexes were renamed properly
            assert len(new_indexes) == len(original_indexes)
            for new_idx in new_indexes:
                assert new_name in new_idx["indexname"]

    async def test_table_drop(self, setup: Setup):
        """Test dropping a table"""
        table = setup.table

        # Verify table exists
        async with GENTABLE_ENGINE.transaction() as conn:
            exists = await conn.fetchval(
                f'SELECT EXISTS (SELECT 1 FROM "{setup.schema_id}"."TableMetadata" WHERE table_id = $1)',
                setup.table_id,
            )
            assert exists

        # Drop table
        await table.drop_table()

        # Verify table does not exists
        async with GENTABLE_ENGINE.transaction() as conn:
            # check TableMetadata
            exists = await conn.fetchval(
                f'SELECT EXISTS (SELECT 1 FROM "{setup.schema_id}"."TableMetadata" WHERE table_id = $1)',
                setup.table_id,
            )
            assert not exists
            # check columnmetadata
            exists = await conn.fetchval(
                f'SELECT EXISTS (SELECT 1 FROM "{setup.schema_id}"."ColumnMetadata" WHERE table_id = $1)',
                setup.table_id,
            )
            assert not exists

            # check table not in schema
            ret = await conn.fetch(
                """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = $1
            """,
                setup.schema_id,
            )
            assert setup.table_id not in [r["table_name"] for r in ret]


class TestColumnOperations:
    async def test_add_column(self, setup: Setup):
        """Test adding a new column"""
        table = setup.table
        with assert_updated_time(table):
            # Add new column
            new_column = ColumnMetadata(
                column_id="new_col",
                table_id=setup.table_id,
                dtype=ColumnDtype.FLOAT,
                vlen=0,
                gen_config=None,
                column_order=4,
            )
            await table.add_column(new_column)
            # Verify new column exists
            async with GENTABLE_ENGINE.transaction() as conn:
                exists = await conn.fetchval(
                    f'SELECT EXISTS (SELECT 1 FROM "{setup.schema_id}"."ColumnMetadata" WHERE column_id = $1)',
                    "new_col",
                )
                assert exists

                # Verify column was added to the actual table
                columns = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = $1 AND table_name = $2",
                    setup.schema_id,
                    setup.table_id,
                )
                assert "new_col" in [c["column_name"] for c in columns]

    async def test_drop_columns(self, setup: Setup):
        """Test removing a column"""
        table = setup.table
        with assert_updated_time(table):
            # Remove column
            await table.drop_columns(["col (1)"])
            # Verify column removed
            async with GENTABLE_ENGINE.transaction() as conn:
                exists = await conn.fetchval(
                    f'SELECT EXISTS (SELECT 1 FROM "{setup.schema_id}"."ColumnMetadata" WHERE column_id = $1)',
                    "col (1)",
                )
                assert not exists

    async def test_column_dtype_storage(self, setup: Setup):
        """Verify ColumnMetadata stores original dtype not PostgreSQL type"""
        table = setup.table

        # Check existing columns
        for col in table.column_metadata:
            assert isinstance(col.dtype, ColumnDtype)  # Should be enum value
            assert not col.dtype.isnumeric()  # Shouldn't be PostgreSQL type string

        # Add new column and verify
        new_col = ColumnMetadata(
            column_id="test_dtype",
            table_id=table.table_id,
            dtype=ColumnDtype.FLOAT,
            vlen=VECTOR_LEN,
        )
        table = await table.add_column(new_col)

        # verify dtype
        test_col = next(c for c in table.column_metadata if c.column_id == "test_dtype")
        assert test_col.dtype == ColumnDtype.FLOAT

    async def test_column_ordering(self, setup: Setup):
        """Test column ordering"""
        table = setup.table
        with assert_updated_time(table):
            # Reorder columns
            await table.reorder_columns(["ID", "Updated at", "col (2)", "vector_col", "col (1)"])
            # Verify new order
            async with GENTABLE_ENGINE.transaction() as conn:
                columns = await conn.fetch(
                    f'SELECT column_id FROM "{setup.schema_id}"."ColumnMetadata" ORDER BY column_order'
                )
                columns = [c["column_id"] for c in columns if not c["column_id"].endswith("_")]
                assert columns == ["ID", "Updated at", "col (2)", "vector_col", "col (1)"]

    async def test_update_column_gen_config_to_null(self, setup: Setup):
        """Test updating column gen_config to NULL"""
        table = setup.table
        with assert_updated_time(table):
            # Add column with proper LLMGenConfig instance
            new_column = ColumnMetadata(
                column_id="output_col",
                table_id=setup.table_id,
                dtype=ColumnDtype.STR,
                vlen=0,
                gen_config=LLMGenConfig(
                    model=setup.chat_model_id,
                    temperature=0.7,
                    system_prompt="Test system",
                    prompt="Test prompt",
                    multi_turn=False,
                ),
                column_order=4,
            )
            table = await table.add_column(new_column)
            assert {c.column_id: c for c in table.column_metadata}[
                "output_col"
            ].gen_config is not None
            # Update gen_config to NULL
            table = await table.update_gen_config(update_mapping={"output_col": None})
            assert {c.column_id: c for c in table.column_metadata}["output_col"].gen_config is None

    async def test_update_gen_config_basic(self, setup: Setup):
        """Test basic gen_config updates"""
        table = setup.table
        with assert_updated_time(table):
            # Add column with NULL config
            new_col = ColumnMetadata(
                column_id="output_col",
                table_id=table.table_id,
                dtype=ColumnDtype.STR,
                gen_config=None,
            )
            table = await table.add_column(new_col)
            # Update to valid config
            new_config = LLMGenConfig(
                model=setup.chat_model_id,
                temperature=0.7,
                system_prompt="Test",
                prompt="Test prompt",
            )
            updated = await table.update_gen_config(update_mapping={"output_col": new_config})
            # Verify update
            col = next(c for c in updated.column_metadata if c.column_id == "output_col")
            assert col.gen_config == new_config
            assert col.is_output_column

    async def test_update_gen_config_change_existing(self, setup: Setup):
        """Test updating from one gen_config to another"""
        table = setup.table
        with assert_updated_time(table):
            # Initial config
            initial_config = LLMGenConfig(
                model=setup.chat_model_id,
                temperature=0.5,
                system_prompt="Initial",
                prompt="Initial prompt",
            )

            # Add column with initial config
            new_col = ColumnMetadata(
                column_id="output_col",
                table_id=table.table_id,
                dtype=ColumnDtype.STR,
                gen_config=initial_config,
            )
            table = await table.add_column(new_col)

            # New config with different values
            updated_config = LLMGenConfig(
                model=setup.chat_model_id,
                temperature=0.7,
                system_prompt="Updated",
                prompt="Updated prompt",
            )

            # Update config
            updated = await table.update_gen_config(update_mapping={"output_col": updated_config})

            # Verify all fields changed
            col = next(c for c in updated.column_metadata if c.column_id == "output_col")
            assert col.gen_config.model == setup.chat_model_id
            assert col.gen_config.temperature == 0.7
            assert col.gen_config.system_prompt == "Updated"
            assert col.gen_config.prompt == "Updated prompt"

            # Verify persistence after reload
            table = await GenerativeTableCore.open_table(
                project_id=setup.projects[0].id,
                table_type=setup.table_type,
                table_id=setup.table_id,
            )
            reloaded_col = next(c for c in table.column_metadata if c.column_id == "output_col")
            assert reloaded_col.gen_config == updated_config

    async def test_update_gen_config_invalid_column(self, setup: Setup):
        """Test updating non-existent column"""
        table = setup.table
        config = LLMGenConfig(
            model=setup.chat_model_id,
            temperature=0.7,
            system_prompt="Test",
            prompt="Test prompt",
        )
        with pytest.raises(ResourceNotFoundError):
            await table.update_gen_config(update_mapping={"nonexistent_col": config})

    async def test_update_gen_config_partial_changes(self, setup: Setup):
        """Test updating only some config fields"""
        table = setup.table
        with assert_updated_time(table):
            initial_config = LLMGenConfig(
                model=setup.chat_model_id,
                temperature=0.5,
                system_prompt="Initial",
                prompt="Initial prompt",
            )

            new_col = ColumnMetadata(
                column_id="output_col",
                table_id=table.table_id,
                dtype=ColumnDtype.STR,
                gen_config=initial_config,
            )
            table = await table.add_column(new_col)

            # Only update temperature
            updated_config = LLMGenConfig(
                model=setup.chat_model_id,  # Same model
                temperature=0.8,  # Updated
                system_prompt="Initial",  # Same
                prompt="Initial prompt",  # Same
            )

            updated = await table.update_gen_config(update_mapping={"output_col": updated_config})
            col = next(c for c in updated.column_metadata if c.column_id == "output_col")

            assert col.gen_config.model == setup.chat_model_id
            assert col.gen_config.temperature == 0.8
            assert col.gen_config.system_prompt == "Initial"
            assert col.gen_config.prompt == "Initial prompt"


class TestSearchOperations:
    @pytest.fixture
    def test_vectors(self):
        return {
            "valid_vector": np.random.rand(VECTOR_LEN),
            "empty_vector": np.array([]),
            "wrong_dim_vector": np.random.rand(VECTOR_LEN * 2),
            "list_vector": np.random.rand(VECTOR_LEN).tolist(),
        }

    async def test_vector_search_basic(self, setup: Setup, test_vectors):
        """Test basic vector search functionality"""
        table = setup.table
        # Insert test vectors
        test_data = [
            {"col (1)": "foo", "col (2)": 1, "vector_col": np.random.rand(VECTOR_LEN)},
            {"col (1)": "bar", "col (2)": 2, "vector_col": np.random.rand(VECTOR_LEN)},
            {"col (1)": "baz", "col (2)": 3, "vector_col": np.random.rand(VECTOR_LEN)},
        ]
        await table.add_rows(test_data)

        # Test search with numpy array
        results = await table.vector_search(
            "dummy_query",
            embedding_fn=lambda _, __: test_vectors["valid_vector"],
            vector_column_names=["vector_col"],
        )
        assert len(results) == 3
        assert "score" in results[0]
        # Scores are distances (lower is better)
        assert results[0]["score"] <= results[1]["score"] <= results[2]["score"]

        # Test search with list input
        list_results = await table.vector_search(
            "dummy_query",
            embedding_fn=lambda _, __: test_vectors["list_vector"],
            vector_column_names=["vector_col"],
        )
        assert len(list_results) == 3

    @pytest.mark.asyncio
    async def test_multi_column_vector_search(self, setup: Setup, test_vectors):
        """Test basic vector search functionality on multiple columns"""
        table = setup.table
        # Add vector column
        table = await table.add_column(
            ColumnMetadata(
                column_id="vector_col2",
                table_id="Table (test)",
                dtype=ColumnDtype.FLOAT,
                vlen=VECTOR_LEN,
                gen_config=None,
                column_order=4,
                meta={},
            )
        )
        # Insert test vectors
        test_data = [
            {
                "col (1)": "foo",
                "col (2)": 1,
                "vector_col": test_vectors["valid_vector"],
                "vector_col2": test_vectors["valid_vector"],
            },
            {
                "col (1)": "bar",
                "col (2)": 2,
                "vector_col": test_vectors["valid_vector"],
                "vector_col2": test_vectors["valid_vector"],
            },
            {
                "col (1)": "baz",
                "col (2)": 3,
                "vector_col": np.random.rand(VECTOR_LEN),
                "vector_col2": np.random.rand(VECTOR_LEN),
            },
        ]
        await table.add_rows(test_data)

        # Test search with numpy array
        results = await table.vector_search(
            "dummy_query",
            embedding_fn=lambda _, __: test_vectors["valid_vector"],
            vector_column_names=["vector_col"],
        )
        # Scores are distances (lower is better)
        assert results[0]["score"] <= results[1]["score"] <= results[2]["score"]
        # Ensure not matching row is last
        assert results[2]["col (1)"] == "baz"

    async def test_vector_search_errors(self, setup: Setup, test_vectors):
        """Test vector search error handling"""

        table = setup.table

        # Test invalid input types
        with pytest.raises(BadInputError):
            await table.vector_search(
                "dummy_query",
                embedding_fn=lambda _, __: "invalid_type",
                vector_column_names=["vector_col"],
            )

        # Test empty vector
        with pytest.raises(BadInputError):
            await table.vector_search(
                "dummy_query",
                embedding_fn=lambda _, __: test_vectors["empty_vector"],
                vector_column_names=["vector_col"],
            )

        # Test dimension mismatch
        with pytest.raises(BadInputError):
            await table.vector_search(
                "dummy_query",
                embedding_fn=lambda _, __: test_vectors["wrong_dim_vector"],
                vector_column_names=["vector_col"],
            )

    async def test_fts_search_basic(self, setup: Setup):
        """Test basic full text search functionality"""
        new_column = ColumnMetadata(
            column_id="search_col",
            table_id="Table (test)",
            dtype=ColumnDtype.STR,
            vlen=0,
            gen_config=None,
            column_order=4,
            meta={},
        )

        table = setup.table
        table = await table.add_column(new_column)

        # Insert test data with searchable content
        test_data = [
            {"col (1)": "foo", "col (2)": 1, "search_col": "quick brown fox"},
            {"col (1)": "bar", "col (2)": 2, "search_col": "lazy dog"},
            {"col (1)": "baz", "col (2)": 3, "search_col": "quick dog"},
        ]
        await table.add_rows(test_data)

        # Test basic search
        results = await table.fts_search("quick")
        assert len(results) == 2
        assert {r["search_col"] for r in results} == {"quick brown fox", "quick dog"}

    async def test_fts_uses_index(self, setup: Setup):
        """Verify FTS queries actually use the index"""
        table = setup.table
        rows_to_add = [{"col (1)": "test search term"}]
        await table.add_rows(rows_to_add)

        # Test basic search
        results = await table.fts_search("quick", explain=True)

        # Verify index scan is used
        if not any(["Index Scan" in res["QUERY PLAN"] for res in results]):
            # add more rows to force index scan
            await table.add_rows(rows_to_add * 1000)
            results = await table.fts_search("quick", force_use_index=True, explain=True)
            assert any(["Index Scan" in res["QUERY PLAN"] for res in results])
        else:
            assert True

    async def test_fts_search_pagination(self, setup: Setup):
        """Test search with pagination"""
        # Create table with text column
        new_column = ColumnMetadata(
            column_id="search_col",
            table_id="Table (test)",
            dtype=ColumnDtype.STR,
            vlen=0,
            gen_config=None,
            column_order=4,
            meta={},
        )

        table = setup.table
        table = await table.add_column(new_column)

        # Insert test data with searchable content
        test_data = [
            {"col (1)": "foo", "col (2)": 1, "search_col": "quick brown fox"},
            {"col (1)": "bar", "col (2)": 2, "search_col": "lazy dog"},
            {"col (1)": "baz", "col (2)": 3, "search_col": "quick dog"},
        ]
        await table.add_rows(test_data)

        # Test limit/offset
        page1 = await table.fts_search("dog", limit=1)
        assert len(page1) == 1

        page2 = await table.fts_search("dog", limit=1, offset=1)
        assert len(page2) == 1
        assert page1[0]["ID"] != page2[0]["ID"]

    async def test_fts_search_state_inclusion(self, setup: Setup):
        """Test that state columns are included in search results"""
        # Create table with text and state columns
        new_column = ColumnMetadata(
            column_id="search_col",
            table_id="Table (test)",
            dtype=ColumnDtype.STR,
            vlen=0,
            gen_config=None,
            column_order=4,
        )

        table = setup.table
        table = await table.add_column(new_column)

        # Insert test data
        await table.add_rows(
            [
                {
                    "col (1)": "foo",
                    "col (2)": 1,
                    "search_col": "test value",
                }
            ]
        )

        # Verify that state columns appear in search results
        results = await table.fts_search("value", remove_state_cols=False)
        assert "search_col_" in results[0].keys()

    @pytest.mark.asyncio
    async def test_multi_column_fts_search(self, setup: Setup):
        """Test searches across multiple columns"""
        table = setup.table

        # Add multiple text columns
        table = await table.add_column(
            ColumnMetadata(
                column_id="text1",
                table_id="Table (test)",
                dtype=ColumnDtype.STR,
                vlen=0,
                gen_config=None,
                column_order=4,
            )
        )
        table = await table.add_column(
            ColumnMetadata(
                column_id="text2",
                table_id="Table (test)",
                dtype=ColumnDtype.STR,
                vlen=0,
                gen_config=None,
                column_order=5,
            )
        )

        # Insert test data
        await table.add_rows(
            [
                {"text1": "first column text", "text2": "unrelated"},
                {"text1": "unrelated", "text2": "second column text"},
            ]
        )

        # Test FTS across multiple columns
        results = await table.fts_search("text")
        assert len(results) == 2
        assert {r["text1"] for r in results} == {"first column text", "unrelated"}
        assert {r["text2"] for r in results} == {"unrelated", "second column text"}

    @pytest.mark.parametrize(
        "text",
        [
            "中文测试",  # Chinese
            "日本語テスト",  # Japanese
            "한국어 테스트",  # Korean
        ],
    )
    @pytest.mark.asyncio
    async def test_cjk_search(self, setup: Setup, text: str):
        """Test CJK language support in FTS"""
        table = setup.table
        table = await table.add_column(
            ColumnMetadata(
                column_id="cjk_text",
                table_id="Table (test)",
                dtype=ColumnDtype.STR,
                vlen=0,
                gen_config=None,
                column_order=4,
            )
        )

        # Insert CJK text
        await table.add_rows(
            [
                {"cjk_text": text},
            ]
        )

        # Search for the text
        results = await table.fts_search(text)
        assert len(results) == 1
        assert results[0]["cjk_text"] == text

    @pytest.mark.asyncio
    async def test_multi_term_fts_search(self, setup: Setup):
        """Test FTS with multiple search terms"""
        table = setup.table
        table = await table.add_column(
            ColumnMetadata(
                column_id="multi_text",
                table_id="Table (test)",
                dtype=ColumnDtype.STR,
                vlen=0,
                gen_config=None,
                column_order=4,
            )
        )

        # Insert test data
        await table.add_rows(
            [
                {"multi_text": "quick brown fox"},
                {"multi_text": "lazy dog"},
                {"multi_text": "quick dog"},
            ]
        )

        # Test AND semantics
        results = await table.fts_search("dog Quick")
        assert len(results) == 1
        assert results[0]["multi_text"] == "quick dog"

        # Test OR semantics
        results = await table.fts_search("quick OR lazy")
        assert len(results) == 3

    async def test_hybrid_search_basic(self, setup: Setup):
        """Test basic hybrid search functionality"""
        table = setup.table

        # Add text column for FTS
        text_col = ColumnMetadata(
            column_id="text_col",
            table_id=table.table_id,
            dtype=ColumnDtype.STR,
            vlen=0,
            gen_config=None,
            column_order=4,
        )
        table = await table.add_column(text_col)

        # Insert test data with both text and vector content
        same_vector = np.random.rand(VECTOR_LEN)
        test_data = [
            {"col (1)": "foo", "text_col": "quick brown fox", "vector_col": same_vector},
            {"col (1)": "bar", "text_col": "lazy dog", "vector_col": np.random.rand(VECTOR_LEN)},
            {"col (1)": "bay", "text_col": "slow hound", "vector_col": np.random.rand(VECTOR_LEN)},
            {"col (1)": "baz", "text_col": "quick dog", "vector_col": same_vector},
            {"col (1)": "bax", "text_col": "tardy fox", "vector_col": np.random.rand(VECTOR_LEN)},
        ]
        await table.add_rows(test_data)

        # Mock embedding function
        async def mock_embed_fn(model: str, text: str):
            return same_vector

        # Test hybrid search
        results = await table.hybrid_search(
            fts_query="quick",
            vs_query="quick",
            embedding_fn=mock_embed_fn,
            vector_column_names=["vector_col"],
            use_bm25_ranking=False,
        )

        assert len(results) > 0
        assert all("rrf_score" in r for r in results)  # Check for rrf_score key
        results = sorted(results, key=lambda x: x["rrf_score"], reverse=True)
        # Verify the top results contain 'quick' from FTS and the matching vector
        # The exact ranking depends on RRF scoring, but the relevant items should be highly ranked.
        assert all(["quick" in r["text_col"] for r in results[:2]])

    async def test_hybrid_search_with_bm25(self, setup: Setup):
        """Test hybrid search with bm25 functionality"""
        table = setup.table

        # Add text column for FTS
        text_col = ColumnMetadata(
            column_id="text_col",
            table_id=table.table_id,
            dtype=ColumnDtype.STR,
            vlen=0,
            gen_config=None,
            column_order=4,
        )
        table = await table.add_column(text_col)

        # Insert test data with both text and vector content
        same_vector = np.random.rand(VECTOR_LEN)
        test_data = [
            {"col (1)": "foo", "text_col": "quick brown fox", "vector_col": same_vector},
            {"col (1)": "bar", "text_col": "lazy dog", "vector_col": np.random.rand(VECTOR_LEN)},
            {"col (1)": "bay", "text_col": "slow hound", "vector_col": np.random.rand(VECTOR_LEN)},
            {"col (1)": "baz", "text_col": "quick dog", "vector_col": same_vector},
            {"col (1)": "bax", "text_col": "tardy fox", "vector_col": np.random.rand(VECTOR_LEN)},
        ]
        await table.add_rows(test_data)

        # Mock embedding function
        async def mock_embed_fn(model: str, text: str):
            return same_vector

        # Test hybrid search
        results = await table.hybrid_search(
            fts_query="quick",
            vs_query="quick",
            embedding_fn=mock_embed_fn,
            vector_column_names=["vector_col"],
        )

        assert len(results) > 0
        assert all("rrf_score" in r for r in results)  # Check for rrf_score key
        results = sorted(results, key=lambda x: x["rrf_score"], reverse=True)
        # VS scores should be the same, the difference should comes from FTS
        # longer document reduced BM25 scores
        assert results[0]["text_col"] == "quick dog"
        assert results[1]["text_col"] == "quick brown fox"


class TestRowOperations:
    async def test_add_rows(self, setup: Setup):
        table = setup.table
        with assert_updated_time(table):
            # Insert data
            row_data = [{"col (1)": "test value", "col (2)": 123, "version": "1"}]
            await table.add_rows(row_data)
            # Verify data inserted
            async with GENTABLE_ENGINE.transaction() as conn:
                result = await conn.fetchrow(
                    f'SELECT * FROM "{setup.schema_id}"."{setup.table_id}"'
                )
                assert result["col (1)"] == "test value"
                assert result["col (2)"] == 123

    async def test_add_rows_batch(self, setup: Setup):
        table = setup.table
        with assert_updated_time(table):
            # Insert data
            row_data = [
                {"col (1)": "test value", "col (2)": 1, "version": "1"},
                {"col (1)": "test value 2", "col (2)": 2, "version": "1"},
                {"col (1)": "test value 3", "col (2)": 3, "version": "1"},
            ]
            await table.add_rows(row_data)
            # Verify data inserted
            async with GENTABLE_ENGINE.transaction() as conn:
                result = await conn.fetch(f'SELECT * FROM "{setup.schema_id}"."{setup.table_id}"')
                assert result[0]["col (1)"] == "test value"
                assert result[0]["col (2)"] == 1
                assert result[-1]["col (1)"] == "test value 3"
                assert result[-1]["col (2)"] == 3

    async def test_list_rows(self, setup: Setup):
        table = setup.table
        # Insert data
        row_data = [
            {"col (1)": "llama", "col (2)": 1},
            {"col (1)": "lama", "col (2)": 2},
            {"col (1)": "DROP TABLE", "col (2)": 3},
        ]
        await table.add_rows(row_data)
        # List data
        rows = (await table.list_rows()).items
        rows_reversed = (await table.list_rows(order_ascending=False)).items
        assert all(rr == r for rr, r in zip(rows_reversed[::-1], rows, strict=True))
        # Verify data inserted
        assert rows[0]["col (1)"] == "llama"
        assert rows[0]["col (2)"] == 1
        assert rows[-1]["col (1)"] == "DROP TABLE"
        assert rows[-1]["col (2)"] == 3

    async def test_list_rows_search_query(self, setup: Setup):
        # Create table
        table = setup.table
        # Insert data
        row_data = [
            {"col (1)": "llama", "col (2)": 1},
            {"col (1)": "lama", "col (2)": 2},
            {"col (1)": "1", "col (2)": 3},
        ]
        await table.add_rows(row_data)
        # Search
        rows = (await table.list_rows(search_query="lama")).items
        assert len(rows) == 2
        rows = (await table.list_rows(search_query="^lama")).items
        assert len(rows) == 1
        assert rows[0]["col (1)"] == "lama"
        rows = (
            await table.list_rows(search_query="1", search_columns=["col (1)", "col (2)"])
        ).items
        assert len(rows) == 2
        rows = (await table.list_rows(search_query="1", search_columns=["col (2)"])).items
        assert len(rows) == 1
        assert rows[0]["col (1)"] == "llama"
        assert rows[0]["col (2)"] == 1

    async def test_count_rows(self, setup: Setup):
        """Verify count_rows() returns correct counts"""
        table = setup.table
        # Empty table
        assert await table.count_rows() == 0
        # After insert
        await table.add_rows([{"col (1)": "test"}])
        assert await table.count_rows() == 1
        # After delete
        rows = (await table.list_rows()).items
        await table.delete_rows(row_ids=[rows[0]["ID"]])
        assert await table.count_rows() == 0

    async def test_update_rows(self, setup: Setup, tmp_path):
        """Test updating rows including NULL values"""
        table = setup.table
        with assert_updated_time(table):
            # Insert initial data
            row_data = [{"col (1)": "initial value", "col (2)": 123}]
            row_added = (await (await table.add_rows(row_data)).list_rows()).items

            # Update data
            update_data = {
                "col (1)": "updated value",
                "col (2)": 456,
            }
            await table.update_rows({row_added[0]["ID"]: update_data})

            # Verify data updated
            retrieved_row = await table.get_row(row_added[0]["ID"])
            assert retrieved_row["col (1)"] == update_data["col (1)"]
            assert retrieved_row["col (2)"] == update_data["col (2)"]

            # Test NULL value updates
            # Case 1: Set existing value to NULL
            await table.update_rows({row_added[0]["ID"]: {"col (1)": None}})
            updated = await table.get_row(row_added[0]["ID"])
            assert updated["col (1)"] is None
            assert updated["col (2)"] == 456

            # Case 2: Verify NULLs persist through export/import
            export_path = tmp_path / "null_test.parquet"
            await table.export_table(export_path)
            new_table = await GenerativeTableCore.import_table(
                project_id=setup.projects[0].id,
                table_type=setup.table_type,
                source=export_path,
                table_id_dst="null_test_table",
            )
            imported = await new_table.get_row(row_added[0]["ID"])
            assert imported["col (1)"] is None

    async def test_delete_rows_with_id(self, setup: Setup):
        table = setup.table
        with assert_updated_time(table):
            # Insert data
            row_data = [
                {"col (1)": "test value", "col (2)": 1},
                {"col (1)": "test value", "col (2)": 2},
                {"col (1)": "test value", "col (2)": 3},
            ]
            new_rows = (await (await table.add_rows(row_data)).list_rows()).items

            # Delete data
            await table.delete_rows(row_ids=[new_rows[0]["ID"], new_rows[2]["ID"]])

            # Verify data deleted
            with pytest.raises(ResourceNotFoundError, match="Row .+ not found in table"):
                await table.get_row(new_rows[0]["ID"])
            with pytest.raises(ResourceNotFoundError, match="Row .+ not found in table"):
                await table.get_row(new_rows[2]["ID"])

    async def test_delete_rows_with_where(self, setup: Setup):
        table = setup.table
        with assert_updated_time(table):
            # Insert data
            row_data = [
                {"col (1)": "test value", "col (2)": 1},
                {"col (1)": "test value", "col (2)": 2},
                {"col (1)": "test value", "col (2)": 3},
            ]
            new_rows = (await (await table.add_rows(row_data)).list_rows()).items
            # Delete data
            await table.delete_rows(where='"col (2)" > 1')
            # Verify data deleted
            with pytest.raises(ResourceNotFoundError, match="Row .+ not found in table"):
                await table.get_row(new_rows[1]["ID"])
            with pytest.raises(ResourceNotFoundError, match="Row .+ not found in table"):
                await table.get_row(new_rows[2]["ID"])

    async def test_delete_rows_with_id_where(self, setup: Setup):
        table = setup.table
        with assert_updated_time(table):
            # Insert data
            row_data = [
                {"col (1)": "test value", "col (2)": 1},
                {"col (1)": "test value", "col (2)": 2},
                {"col (1)": "test value", "col (2)": 3},
            ]
            new_rows = (await (await table.add_rows(row_data)).list_rows()).items
            # Delete data
            await table.delete_rows(
                row_ids=[new_rows[1]["ID"], new_rows[2]["ID"]], where='"col (2)" > 2'
            )
            # Verify data deleted
            response = await table.get_row(new_rows[0]["ID"])
            assert isinstance(response, dict)
            response = await table.get_row(new_rows[1]["ID"])
            assert isinstance(response, dict)
            with pytest.raises(ResourceNotFoundError, match="Row .+ not found in table"):
                await table.get_row(new_rows[2]["ID"])


# --- Fixtures and Tests for Stateful Operations ---


async def setup_table_newly_created(table: GenerativeTableCore):
    """Provides an async setup function for the newly created table."""
    # No op needed here, just return the table
    return table


async def setup_table_with_added_column(table: GenerativeTableCore):
    """Provides an async setup function for a table with an added column."""
    new_col = ColumnMetadata(
        column_id="added_col_state_test", table_id=table.table_id, dtype=ColumnDtype.BOOL
    )
    return await table.add_column(new_col)


async def setup_table_with_dropped_column(table: GenerativeTableCore):
    """Provides an async setup function for a table with 'col (1)' dropped."""
    return await table.drop_columns(["col (1)"])


async def setup_table_renamed(table: GenerativeTableCore):
    """Provides an async setup function for a renamed table."""
    new_name = "renamed_state_test"
    return await table.rename_table(new_name)


async def setup_table_duplicated(table: GenerativeTableCore, setup: Setup):
    """Provides an async setup function for a duplicated table."""
    # Add data just before duplicating
    await table.add_rows(
        [{"col (1)": "data_for_dup", "col (2)": 111, "vector_col": np.random.rand(VECTOR_LEN)}]
    )
    return await GenerativeTableCore.duplicate_table(
        project_id=setup.projects[0].id,
        table_type=setup.table_type,
        table_id_src=table.table_id,
        table_id_dst="duplicated_state_test",
    )


async def setup_table_imported(table: GenerativeTableCore, setup: Setup, tmp_path):
    """Provides an async setup function for an imported table."""
    export_path = tmp_path / "state_test_export.parquet"
    # Add data just before exporting
    await table.add_rows(
        [{"col (1)": "data_for_import", "col (2)": 222, "vector_col": np.random.rand(VECTOR_LEN)}]
    )
    await table.export_table(export_path)
    return await GenerativeTableCore.import_table(
        project_id=setup.projects[0].id,
        table_type=setup.table_type,
        source=export_path,
        table_id_dst="imported_state_test",
    )


class TestStatefulOperations:
    # List of setup fixture names to parametrize over
    SETUP_TABLE_STATE_FIXTURES = [
        "setup_table_newly_created",
        "setup_table_with_added_column",
        "setup_table_with_dropped_column",
        "setup_table_renamed",
        "setup_table_duplicated",
        "setup_table_imported",  # Use the new fixture name
    ]

    def parametrized_setup(self, setup_fixture_name, setup: Setup, tmp_path):
        if setup_fixture_name == "setup_table_newly_created":
            return setup_table_newly_created(setup.table)
        elif setup_fixture_name == "setup_table_with_added_column":
            return setup_table_with_added_column(setup.table)
        elif setup_fixture_name == "setup_table_with_dropped_column":
            return setup_table_with_dropped_column(setup.table)
        elif setup_fixture_name == "setup_table_renamed":
            return setup_table_renamed(setup.table)
        elif setup_fixture_name == "setup_table_duplicated":
            return setup_table_duplicated(setup.table, setup)
        elif setup_fixture_name == "setup_table_imported":
            return setup_table_imported(setup.table, setup, tmp_path)

    @pytest.mark.parametrize("setup_fixture_name", SETUP_TABLE_STATE_FIXTURES)
    @pytest.mark.asyncio
    async def test_core_ops_on_various_tables(self, setup_fixture_name, setup: Setup, tmp_path):
        """
        Tests core operations (add row, add col, drop col, search)
        on tables in various states (new, col added, col dropped, renamed, duplicated, imported).
        """
        # --- Setup ---
        # Setup the table as per the parameter
        table = await self.parametrized_setup(setup_fixture_name, setup, tmp_path)

        assert isinstance(table, GenerativeTableCore)  # Ensure we have a table object

        # Store fixture name for easier debugging in asserts/fails
        current_state_name = setup_fixture_name.replace("setup_", "")

        initial_row_count = await table.count_rows()
        initial_col_count = len(table.column_metadata)

        # --- Test Add Row ---
        row_data = {"col (2)": 999}  # Use a column likely to exist across states
        if "col (1)" in table.data_table_model.get_column_ids(exclude_state=True):
            row_data["col (1)"] = f"state_test_{current_state_name}"
        if "vector_col" in table.data_table_model.get_column_ids(exclude_state=True):
            row_data["vector_col"] = np.random.rand(VECTOR_LEN)  # Use correct dimension
        if "added_col_state_test" in table.data_table_model.get_column_ids(exclude_state=True):
            row_data["added_col_state_test"] = True
        await table.add_rows([row_data])
        assert await table.count_rows() == initial_row_count + 1

        # --- Test Add Column ---
        temp_col_id = "temp_col_in_test"
        temp_col_meta = ColumnMetadata(
            column_id=temp_col_id, table_id=table.table_id, dtype=ColumnDtype.FLOAT
        )
        table = await table.add_column(
            temp_col_meta
        )  # Reassign table as add_column returns updated instance
        assert any(col.column_id == temp_col_id for col in table.column_metadata)
        assert (
            len(table.column_metadata) == initial_col_count + 2
        )  # +1 for data col, +1 for state col

        # --- Test Drop Column ---
        table = await table.drop_columns(
            [temp_col_id]
        )  # Reassign table as drop_columns returns updated instance
        assert not any(col.column_id == temp_col_id for col in table.column_metadata)
        assert len(table.column_metadata) == initial_col_count  # Should be back to original count

        # --- Test Search (Index Check) ---
        # FTS Search (ensure index exists and query runs)
        # Use a column that exists in most states or adapt search term
        search_term = (
            "state_test"
            if "col (1)" in table.data_table_model.get_column_ids(exclude_state=True)
            else "a"
        )  # Generic search if col (1) dropped
        try:
            await table.fts_search(search_term, limit=1, explain=False)
        except Exception as e:
            pytest.fail(f"FTS search failed on {current_state_name} state: {e}")

        # Vector Search (ensure index exists and query runs)
        if "vector_col" in table.vector_column_names:

            async def mock_embed_fn(model: str, text: str):
                # Return a vector of the correct dimension for the column
                vlen = next(c.vlen for c in table.column_metadata if c.column_id == "vector_col")
                return np.random.rand(vlen)

            try:
                await table.vector_search(
                    query="dummy",
                    embedding_fn=mock_embed_fn,
                    vector_column_names=["vector_col"],
                    limit=1,
                )
            except Exception as e:
                pytest.fail(f"Vector search failed on {current_state_name} state: {e}")
        elif current_state_name not in [
            "table_with_dropped_column"
        ]:  # Expect vector col unless explicitly dropped
            pytest.fail(
                f"Vector column 'vector_col' missing unexpectedly in {current_state_name} state"
            )
