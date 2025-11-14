import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import lancedb
from filelock import FileLock

from owl.db.gen_table import (
    ColumnDtype,
    ColumnMetadata,
    GenerativeTableCore,
    TableMetadata,
)
from owl.types import ColName, TableName, TableType

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class V1DatabaseReader:
    """Class to read data from v1 database format."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.locks: Dict[str, FileLock] = {}

    def get_org_projects(self) -> List[Dict[str, str]]:
        """Get list of all org/project directories."""
        org_projects = []
        for org_dir in self.base_path.iterdir():
            if org_dir.is_dir():
                for project_dir in org_dir.iterdir():
                    if project_dir.is_dir():
                        org_projects.append(
                            {
                                "org_id": org_dir.name,
                                "project_id": project_dir.name,
                                "path": str(project_dir),
                            }
                        )
        return org_projects

    def get_tables_for_project(self, project_path: str) -> List[Dict[str, str]]:
        """Get list of tables for a project."""
        tables = []
        for table_type in ["action", "chat", "knowledge"]:
            db_path = Path(project_path) / f"{table_type}.db"
            if db_path.exists():
                # Get all .lance directories in the table_type folder
                table_dir = db_path.parent / table_type
                if table_dir.exists():
                    for lance_dir in table_dir.iterdir():
                        if lance_dir.is_dir() and lance_dir.suffix == ".lance":
                            tables.append(
                                {
                                    "type": table_type,
                                    "sqlite_path": str(db_path),
                                    "lance_path": str(lance_dir),
                                    "table_name": lance_dir.stem,
                                }
                            )
        return tables

    def read_table_metadata(self, sqlite_path: str) -> List[Dict[str, Any]]:
        """Read table metadata from SQLite database."""
        with sqlite3.connect(sqlite_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all table metadata
            cursor.execute("SELECT * FROM TableMeta")
            meta_rows = cursor.fetchall()
            if not meta_rows:
                return []

            # Process all metadata rows
            metadata_list = []
            for row in meta_rows:
                metadata = dict(row)

                # Parse columns if present
                if "cols" in metadata and metadata["cols"]:
                    import json

                    # Handle both string and dict formats
                    if isinstance(metadata["cols"], str):
                        try:
                            metadata["cols"] = json.loads(metadata["cols"])
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse columns metadata for {sqlite_path}")
                            metadata["cols"] = []
                    # Convert columns to structured format
                    if isinstance(metadata["cols"], (list, dict)):
                        if isinstance(metadata["cols"], dict):
                            metadata["cols"] = [metadata["cols"]]
                        for col in metadata["cols"]:
                            col["dtype"] = col.get("dtype", "str")
                            col["vlen"] = col.get("vlen", 0)
                            if "gen_config" in col and col["gen_config"]:
                                if isinstance(col["gen_config"], str):
                                    try:
                                        col["gen_config"] = json.loads(col["gen_config"])
                                    except json.JSONDecodeError:
                                        col["gen_config"] = {}

                metadata_list.append(metadata)

            return metadata_list

    def _process_state_column(self, value: Any) -> Any:
        """Process state column values."""
        if isinstance(value, str):
            if value == "":
                return {}
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse state column value: {value}")
                return {}
        return value

    def read_table_data(self, lance_path: str) -> List[Dict[str, Any]]:
        """Read table data from LanceDB."""
        # Connect to parent directory of the .lance folder
        db = lancedb.connect(str(Path(lance_path).parent))
        # Open table using the directory name
        table_name = Path(lance_path).stem
        data = db.open_table(table_name).to_pandas().to_dict("records")

        # Process state columns
        for row in data:
            for col_name in list(row.keys()):
                if col_name.endswith("_"):
                    row[col_name] = self._process_state_column(row[col_name])
        return data

    def lock_table(self, table_path: str) -> FileLock:
        """Acquire a file lock for the table."""
        lock_path = f"{table_path}.lock"
        self.locks[lock_path] = FileLock(lock_path)
        self.locks[lock_path].acquire()
        return self.locks[lock_path]

    def release_table_lock(self, table_path: str) -> None:
        """Release the file lock for the table."""
        lock_path = f"{table_path}.lock"
        if lock_path in self.locks:
            self.locks[lock_path].release()
            del self.locks[lock_path]


class V2Migrator:
    """Class to handle v2 migration using GenerativeTableCore."""

    def __init__(self, migrate: bool = False):
        self.v1_conn = None
        self.migrate = migrate

    # Mapping between v1 and v2 ColumnDtype values
    _DTYPE_MAPPING = {
        "int": "INTEGER",
        "int8": "INTEGER",
        "float": "FLOAT",
        "float32": "FLOAT",
        "float16": "FLOAT",
        "bool": "BOOL",
        "str": "TEXT",
        "date-time": "TIMESTAMPTZ",
        "image": "TEXT",
        "audio": "TEXT",
        "document": "TEXT",
    }

    def _map_dtype(self, dtype: str) -> str:
        """Map v1 dtype to v2 ColumnDtype."""
        dtype = dtype.lower()
        return self._DTYPE_MAPPING.get(dtype, "TEXT")

    async def connect(self):
        """Connect to SQLite database"""
        self.v1_conn = sqlite3.connect(":memory:")  # Will attach v1 databases

    async def close(self):
        """Close database connections"""
        if self.v1_conn:
            self.v1_conn.close()

    async def migrate_table(
        self,
        proj_id: str,
        table_type: TableType,
        table_name: TableName,
        metadata_list: List[Dict[str, Any]],
        data: List[Dict[str, Any]],
    ):
        """Migrate a single table"""
        logger.info(f"Validating table {table_name} for migration")

        # Validate metadata
        if not metadata_list:
            logger.warning(f"No metadata found for table {table_name}")
            return

        # Find metadata for this specific table
        metadata = next((m for m in metadata_list if m.get("id") == table_name), None)
        if not metadata:
            logger.warning(f"No matching metadata found for table {table_name}")
            return

        # Log migration details
        logger.info(f"Table {table_name} would be migrated with:")
        if data:
            logger.info(f"- {len(data)} rows")
            logger.info(f"- Columns: {list(data[0].keys())}")
        else:
            logger.info("- Empty table (0 rows)")

        # Skip actual migration unless --migrate is specified
        if not self.migrate:
            logger.info(f"Dry-run mode: Table {table_name} would be migrated")
            return

        # Create PostgreSQL schema and metadata tables
        schema_id = f"{proj_id}_{table_type}"
        # clean up before migration
        await GenerativeTableCore.drop_schema(proj_id, table_type)
        await GenerativeTableCore.create_schema(proj_id, table_type)
        await GenerativeTableCore.create_metadata_tables(schema_id)

        # System columns that are handled automatically
        SYSTEM_COLUMNS = ["ID", "Updated at"]
        # TODO: Are these columns really migrated? There seems to be a mismatch between the data model and this

        # Create PostgreSQL table
        columns = []
        if metadata.get("cols"):
            # Use column metadata from v1 if available
            col_order_counter = 1  # Initialize the counter
            for col in metadata["cols"]:
                if col["id"] not in SYSTEM_COLUMNS and not col["id"].endswith("_"):
                    columns.append(
                        ColumnMetadata(
                            column_id=ColName(col["id"]),
                            table_id=table_name,
                            dtype=ColumnDtype.FLOAT
                            if col.get("vlen")
                            else ColumnDtype(self._map_dtype(col.get("dtype", "str"))),
                            vlen=col.get("vlen"),
                            gen_config=col.get("gen_config"),
                            column_order=col_order_counter,  # Use the counter here
                        )
                    )
                    col_order_counter += 1  # Increment the counter only when the condition is True
        else:
            raise ValueError("No column metadata found for table")
        # elif data:
        #     # Fallback to creating metadata from data if no v1 metadata
        #     columns = [
        #         ColumnMetadataCreate(
        #             column_id=ColName(col),
        #             table_id=table_name,
        #             dtype=ColumnDtype.STR,  # Default to STR if no type info
        #             vlen=None,
        #             gen_config=None,
        #             column_order=idx + 1
        #         )
        #         for idx, col in enumerate(data[0].keys())
        #         if col not in SYSTEM_COLUMNS
        #     ]
        logger.info(f"Creating table {table_name} with {[c.column_id for c in columns]} columns")
        table = await GenerativeTableCore.create_data_table(
            project_id=proj_id,
            table_id=table_name,
            table_type=table_type,
            table_metadata=TableMetadata(
                table_id=table_name,
                title=metadata.get("title", ""),
                parent_id=metadata.get("parent_id", ""),
            ),
            column_metadata_list=columns,
        )

        # Migrate data if present
        if data:
            await table.add_rows(data_list=data)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Migrate data from v1 to v2 database format")
    parser.add_argument("-i", "--input", required=True, help="Path to v1 database directory")
    parser.add_argument(
        "--org-project", help="Specific org_id/project_id to migrate (format: org_id/project_id)"
    )
    parser.add_argument("--org-id", help="Specific org_id to migrate")
    parser.add_argument("--project-id", help="Specific project_id to migrate")
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Actually perform the migration (default is dry-run)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    # Initialize reader and migrator
    reader = V1DatabaseReader(args.input)
    migrator = V2Migrator(args.migrate)

    try:
        await migrator.connect()

        # Get org/project directories to process
        org_projects = reader.get_org_projects()

        # Filter for specific org/project if specified
        if args.org_project:
            org_id, project_id = args.org_project.split("/")
            org_projects = [
                p for p in org_projects if p["org_id"] == org_id and p["project_id"] == project_id
            ]
            if not org_projects:
                logger.error(f"Could not find org/project: {args.org_project}")
                return
        else:
            # Filter by org_id if specified
            if args.org_id:
                org_projects = [p for p in org_projects if p["org_id"] == args.org_id]
                if not org_projects:
                    logger.error(f"Could not find org: {args.org_id}")
                    return

            # Filter by project_id if specified
            if args.project_id:
                org_projects = [p for p in org_projects if p["project_id"] == args.project_id]
                if not org_projects:
                    logger.error(f"Could not find project: {args.project_id}")
                    return

        # Process each project
        for project in org_projects:
            logger.info(f"Processing project: {project['project_id']}")

            # Get tables for project
            tables = reader.get_tables_for_project(project["path"])

            # Process each table
            for table in tables:
                logger.info(
                    f"Processing table: {table['type']}, sqlite: {table['sqlite_path']}, lance: {table['lance_path']}"
                )
                try:
                    # Acquire lock
                    reader.lock_table(table["lance_path"])

                    # Read metadata and data
                    metadata = reader.read_table_metadata(table["sqlite_path"])
                    data = reader.read_table_data(table["lance_path"])

                    # Migrate table
                    await migrator.migrate_table(
                        project["project_id"],
                        TableType(table["type"]),
                        TableName(table["table_name"]),
                        metadata,
                        data,
                    )
                    if args.migrate:
                        logger.info(f"Migrated table: {table['type']} with {len(data)} rows")

                except Exception as e:
                    logger.error(f"Error processing table {table['type']}: {str(e)}")
                    raise e
                finally:
                    # Release lock and log
                    reader.release_table_lock(table["lance_path"])
                    logger.debug(f"Released lock for table: {table['type']}")

    finally:
        await migrator.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
