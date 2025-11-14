import os
import shutil
import sqlite3
from datetime import datetime, timezone
from glob import glob
from os.path import basename, dirname, join

import lancedb
import orjson
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from jamaibase.types import ColumnSchema


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", cli_parse_args=False
    )
    owl_db_dir: str = "db"


ENV_CONFIG = EnvConfig()
NOW = datetime.now(tz=timezone.utc).isoformat()


def backup_db(db_path: str, backup_dir: str):
    """Backup SQLite database."""
    db_path_components = db_path.split(os.sep)
    if db_path_components[-1] == "main.db":
        bak_db_path = join(backup_dir, db_path_components[-1])
    else:
        bak_db_path = join(backup_dir, *db_path_components[-3:])
    os.makedirs(dirname(bak_db_path), exist_ok=True)
    with sqlite3.connect(db_path) as src, sqlite3.connect(bak_db_path) as dst:
        src.backup(dst)
    print(f"└─ Backed up SQLite database: {db_path} to {bak_db_path}")


def backup_lance_db(lance_dir: str, backup_dir: str):
    """Backup LanceDB directory."""
    lance_dir_components = lance_dir.split(os.sep)
    bak_lance_dir = join(backup_dir, *lance_dir_components[-3:])
    os.makedirs(dirname(bak_lance_dir), exist_ok=True)

    # Copy the .lance directory
    shutil.copytree(lance_dir, bak_lance_dir, ignore=shutil.ignore_patterns("*.lock"))
    print(f"└─ Backed up LanceDB directory: {lance_dir} to {bak_lance_dir}")


def find_sqlite_files(directory):
    """Find all SQLite files in the directory."""
    sqlite_files = []
    for root, dirs, filenames in os.walk(directory, topdown=True):
        # Don't visit Lance directories
        lance_dirs = [d for d in dirs if d.endswith(".lance")]
        for d in lance_dirs:
            dirs.remove(d)
        for filename in filenames:
            if filename.endswith(".lock"):
                continue
            if filename.endswith(".db"):
                sqlite_files.append(join(root, filename))
    return sqlite_files


def find_lance_dirs(directory, table_type):
    """Find all LanceDB directories in the directory."""
    lance_dirs = []
    for root, dirs, _ in os.walk(directory, topdown=True):
        for dir_name in dirs:
            if dir_name.endswith(".lance"):
                dir_components = dir_name.split(os.sep)
                if root.split(os.sep)[-1] == table_type:
                    lance_dirs.append(join(root, *dir_components[:-1]))
    return list(set(lance_dirs))


def reset_column_dtype_from_file_to_image(db_path: str):
    """Reset column dtype from 'file' to 'image' in SQLite tables."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Fetch all TableMeta records
        cursor.execute("SELECT id, cols FROM TableMeta")
        records = cursor.fetchall()

        for i, record in enumerate(records):
            table_id = record[0]
            cols = orjson.loads(record[1])

            updated_cols = []
            print(f"└─ (Table {i + 1:,d}/{len(records):,d}) Modifying table: {table_id}")
            for col in cols:
                col = ColumnSchema.model_validate(col)
                if col.dtype == "file":
                    col.dtype = "image"
                col = col.model_dump()
                updated_cols.append(col)

            # Update the TableMeta record with the new cols
            updated_cols_json = orjson.dumps(updated_cols).decode("utf-8")
            cursor.execute(
                "UPDATE TableMeta SET cols = ? WHERE id = ?",
                (updated_cols_json, table_id),
            )
            conn.commit()
            print(
                f"└─ (Table {i + 1:,d}/{len(records):,d}) Updated 'file' dtype to 'image' in table: {table_id}"
            )
        # Checking
        cursor.execute("SELECT id, cols FROM TableMeta")
        records = cursor.fetchall()
        for i, record in enumerate(records):
            table_id = record[0]
            cols = orjson.loads(record[1])
            print(f"└─ (Table {i + 1:,d}/{len(records):,d}) Checking table: {table_id}")
            print(
                f"\t└─ Current (column, dtype) pairs: {[(col['id'], col['dtype']) for col in cols]}"
            )
        cursor.close()
        conn.close()
    except Exception as e:
        logger.exception(f"└─ Error updating GenTable column due to {e}: {record}")


def add_page_column(db_path: str):
    """Add 'Page' column to SQLite tables."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Fetch all TableMeta records
        cursor.execute("SELECT id, cols FROM TableMeta")
        records = cursor.fetchall()
        PAGE_COLUMN_ID = "Page"
        for i, record in enumerate(records):
            table_id = record[0]
            print(f"└─ (Table {i + 1:,d}/{len(records):,d}) Modifying table: {table_id}")
            cols = orjson.loads(record[1])
            has_page_column = False
            for col in cols:
                col = ColumnSchema.model_validate(col)
                if col.id == PAGE_COLUMN_ID:
                    has_page_column = True
                    break
            if not has_page_column:
                cols.append(
                    ColumnSchema(
                        id=PAGE_COLUMN_ID,
                        dtype="int",
                    ).model_dump()
                )
                cols.append(
                    ColumnSchema(
                        id=f"{PAGE_COLUMN_ID}_",
                        dtype="str",
                    ).model_dump()
                )
                updated_cols_json = orjson.dumps(cols).decode("utf-8")
                cursor.execute(
                    "UPDATE TableMeta SET cols = ? WHERE id = ?",
                    (updated_cols_json, table_id),
                )
                conn.commit()
                print(
                    f"└─ (Table {i + 1:,d}/{len(records):,d}) Added '{PAGE_COLUMN_ID}' column to table: {table_id}"
                )
            else:
                print(
                    f"└─ (Table {i + 1:,d}/{len(records):,d}) Table: {table_id} already has '{PAGE_COLUMN_ID}' column"
                )
        # Checking
        cursor.execute("SELECT id, cols FROM TableMeta")
        records = cursor.fetchall()
        for i, record in enumerate(records):
            table_id = record[0]
            cols = orjson.loads(record[1])
            print(f"└─ (Table {i + 1:,d}/{len(records):,d}) Checking table: {table_id}")
            print(f"\t└─ Current columns: {[col['id'] for col in cols]}")
        cursor.close()
        conn.close()
    except Exception as e:
        logger.exception(f"└─ Error adding columns due to {e}")


def add_page_column_to_lance_table(lance_dir: str):
    """Add 'Page' column to LanceDB tables."""
    try:
        db = lancedb.connect(lance_dir)
        table_names = [
            basename(table_dir).replace(".lance", "")
            for table_dir in glob(join(lance_dir, "*.lance"))
        ]
        for i, table_name in enumerate(table_names):
            print(
                f"└─ (Table {i + 1:,d}/{len(table_names):,d}) Modifying LanceDB table: {table_name}"
            )
            tbl = db.open_table(table_name)
            if "Page" not in tbl.schema.names:
                tbl.add_columns(
                    {
                        "Page": "cast(NULL as bigint)",
                        "Page_": "cast('{\"is_null\": true}' as string)",
                    }
                )
                print(f"\t└─ Added 'Page' column to LanceDB table: {table_name}")
            else:
                print(f"\t└─ LanceDB table: {table_name} already has 'Page' column")
            print(f"\t└─ Current columns: {tbl.schema.names}")
    except Exception as e:
        logger.exception(f"└─ Error adding columns to LanceDB table due to {e}")


if __name__ == "__main__":
    backup_dir = f"{ENV_CONFIG.owl_db_dir}_BAK_{NOW}"
    os.makedirs(backup_dir, exist_ok=False)

    # Backup SQLite files
    sqlite_files = find_sqlite_files(ENV_CONFIG.owl_db_dir)
    for j, db_file in enumerate(sqlite_files):
        print(f"(DB {j + 1:,d}/{len(sqlite_files):,d}): Processing: {db_file}")
        backup_db(db_file, backup_dir)
        if not db_file.endswith("main.db"):
            reset_column_dtype_from_file_to_image(db_file)
        if db_file.endswith("knowledge.db"):
            add_page_column(db_file)

    # Backup and process knowledge table LanceDB files
    kt_lance_dirs = find_lance_dirs(ENV_CONFIG.owl_db_dir, "knowledge")
    for k, kt_lance_dir in enumerate(kt_lance_dirs):
        print(f"(LanceDB {k + 1:,d}/{len(kt_lance_dirs):,d}): Processing: {kt_lance_dir}")
        backup_lance_db(kt_lance_dir, backup_dir)
        add_page_column_to_lance_table(kt_lance_dir)
