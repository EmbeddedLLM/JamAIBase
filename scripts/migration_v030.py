import os
import re
import sqlite3
from datetime import datetime, timezone
from os.path import dirname, isdir, join
from shutil import copy2

import orjson
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

import owl
from jamaibase.types import GEN_CONFIG_VAR_PATTERN, ColumnSchema, LLMGenConfig


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", cli_parse_args=False
    )
    owl_db_dir: str = "db"


ENV_CONFIG = EnvConfig()
NOW = datetime.now(tz=timezone.utc).isoformat()


def backup_db(db_path: str, backup_dir: str):
    db_path_components = db_path.split(os.sep)
    if db_path_components[-1] == "main.db":
        bak_db_path = join(backup_dir, db_path_components[-1])
    else:
        bak_db_path = join(backup_dir, *db_path_components[-3:])
    os.makedirs(dirname(bak_db_path), exist_ok=True)
    with sqlite3.connect(db_path) as src, sqlite3.connect(bak_db_path) as dst:
        src.backup(dst)


def restore(db_dir: str):
    for org_id in os.listdir(db_dir):
        org_dir = join(db_dir, org_id)
        if not isdir(org_dir):
            continue
        for proj_id in os.listdir(org_dir):
            proj_dir = join(org_dir, proj_id)
            if not isdir(proj_dir):
                continue
            for table_type in ["action", "knowledge", "chat"]:
                bak_files = list(
                    sorted(
                        f
                        for f in os.listdir(proj_dir)
                        if f.startswith(table_type) and f.endswith(".db_BAK")
                    )
                )
                src_path = join(proj_dir, bak_files[0])
                dst_path = join(proj_dir, f"{bak_files[0].split('_')[0]}.db")
                os.remove(dst_path)
                copy2(src_path, dst_path)


def find_sqlite_files(directory):
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
                sqlite_files.append(os.path.join(root, filename))
    return sqlite_files


def add_table_meta_columns(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(TableMeta)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        # Add "version" if it does not exist
        if "version" not in column_names:
            default_version = owl.__version__
            cursor.execute(
                f"ALTER TABLE TableMeta ADD COLUMN version TEXT DEFAULT '{default_version}'"
            )
            conn.commit()
            print(f"└─ Added 'version' column with default value '{default_version}'.")
        else:
            print("└─ 'version' column already exists.")

        # Add "meta" if it does not exist
        if "meta" not in column_names:
            cursor.execute("ALTER TABLE TableMeta ADD COLUMN meta JSON DEFAULT '{}'")
            conn.commit()
            print("└─ Added 'meta' column with default value '{}'.")
        else:
            print("└─ 'meta' column already exists.")

        cursor.close()
        conn.close()
    except Exception as e:
        logger.exception(f"└─ Error adding columns due to {e}")


def update_gen_table(db_path: str):
    record = None
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
            print(f"└─ (Table {i + 1:,d}/{len(records):,d}) Checking table: {table_id}")
            for col in cols:
                col = ColumnSchema.model_validate(col)
                if db_path.endswith("chat.db") and col.id.lower() == "ai":
                    if col.gen_config is None:
                        col.gen_config = LLMGenConfig(
                            system_prompt=(
                                f'You are an agent named "{table_id}". Be helpful. Provide answers based on the information given. '
                                "Ensuring that your reply is easy to understand and is accessible to all users. "
                                "Be factual and do not hallucinate."
                            ),
                            prompt="${User}",
                            multi_turn=True,
                        )
                    else:
                        col.gen_config.multi_turn = True
                    ref_col_ids = re.findall(GEN_CONFIG_VAR_PATTERN, col.gen_config.prompt)
                    if "User" in ref_col_ids:
                        if len(ref_col_ids) == 1:
                            col.gen_config.prompt = "${User}"
                    else:
                        col.gen_config.prompt = f"${{User}} {col.gen_config.prompt}"
                col = col.model_dump()
                updated_cols.append(col)

            # Update the TableMeta record with the new cols
            updated_cols_json = orjson.dumps(updated_cols).decode("utf-8")
            cursor.execute(
                "UPDATE TableMeta SET cols = ? WHERE id = ?",
                (updated_cols_json, table_id),
            )
            conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.exception(f"└─ Error updating GenTable column due to {e}: {record}")


if __name__ == "__main__":
    sqlite_files = find_sqlite_files(ENV_CONFIG.owl_db_dir)
    backup_dir = f"{ENV_CONFIG.owl_db_dir}_BAK_{NOW}"
    print(f'Backing up DB dir "{ENV_CONFIG.owl_db_dir}" to "{backup_dir}"')
    os.makedirs(backup_dir, exist_ok=False)

    for j, db_file in enumerate(sqlite_files):
        print(f"(DB {j + 1:,d}/{len(sqlite_files):,d}): Processing: {db_file}")
        backup_db(db_file, backup_dir)
        add_table_meta_columns(db_file)
        update_gen_table(db_file)
