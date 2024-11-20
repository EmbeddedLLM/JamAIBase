import os
import sqlite3
from datetime import datetime, timezone
from os.path import dirname, isdir, join
from shutil import copy2

from pydantic_settings import BaseSettings, SettingsConfigDict


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
                dst_path = join(proj_dir, f'{bak_files[0].split("_")[0]}.db')
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


if __name__ == "__main__":
    sqlite_files = find_sqlite_files(ENV_CONFIG.owl_db_dir)
    backup_dir = f"{ENV_CONFIG.owl_db_dir}_BAK_{NOW}"
    print(f'Backing up DB dir "{ENV_CONFIG.owl_db_dir}" to "{backup_dir}"')
    os.makedirs(backup_dir, exist_ok=False)

    for j, db_file in enumerate(sqlite_files):
        print(f"(DB {j+1:,d}/{len(sqlite_files):,d}): Processing: {db_file}")
        backup_db(db_file, backup_dir)
