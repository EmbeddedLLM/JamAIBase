import os
import sqlite3
from datetime import datetime, timezone
from os.path import join
from pprint import pprint

from pydantic_settings import BaseSettings, SettingsConfigDict

from owl.configs.manager import ENV_CONFIG


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", cli_parse_args=False
    )
    owl_db_dir: str = "db"


NOW = datetime.now(tz=timezone.utc).isoformat()
backup_dir = f"{ENV_CONFIG.owl_db_dir}_BAK_{NOW}"
os.makedirs(backup_dir, exist_ok=False)


def add_columns():
    with sqlite3.connect(join(ENV_CONFIG.owl_db_dir, "main.db")) as src:
        c = src.cursor()
        # Add OAuth columns to user table
        c.execute("ALTER TABLE user ADD COLUMN username TEXT DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN refresh_counter INTEGER DEFAULT 0")
        c.execute("ALTER TABLE user ADD COLUMN google_id TEXT DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN google_name TEXT DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN google_username TEXT DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN google_email TEXT DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN google_picture_url TEXT DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN github_id INTEGER DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN github_name TEXT DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN github_username TEXT DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN github_email TEXT DEFAULT NULL")
        c.execute("ALTER TABLE user ADD COLUMN github_picture_url TEXT DEFAULT NULL")
        src.commit()
        c.execute("CREATE UNIQUE INDEX idx_user_google_id ON user (google_id)")
        c.execute("CREATE UNIQUE INDEX idx_user_github_id ON user (github_id)")
        # Rename table
        c.execute("ALTER TABLE `userorglink` RENAME TO `orgmember`")
        # Flatten quota related columns to organization table
        c.execute("ALTER TABLE organization ADD COLUMN credit REAL DEFAULT 0.0")
        c.execute("ALTER TABLE organization ADD COLUMN credit_grant REAL DEFAULT 0.0")
        c.execute("ALTER TABLE organization ADD COLUMN llm_tokens_quota_mtok REAL DEFAULT 0")
        c.execute("ALTER TABLE organization ADD COLUMN llm_tokens_usage_mtok REAL DEFAULT 0")
        c.execute("ALTER TABLE organization ADD COLUMN embedding_tokens_quota_mtok REAL DEFAULT 0")
        c.execute("ALTER TABLE organization ADD COLUMN embedding_tokens_usage_mtok REAL DEFAULT 0")
        c.execute("ALTER TABLE organization ADD COLUMN reranker_quota_ksearch REAL DEFAULT 0")
        c.execute("ALTER TABLE organization ADD COLUMN reranker_usage_ksearch REAL DEFAULT 0")
        c.execute("ALTER TABLE organization ADD COLUMN db_quota_gib REAL DEFAULT 0.0")
        c.execute("ALTER TABLE organization ADD COLUMN db_usage_gib REAL DEFAULT 0.0")
        c.execute("ALTER TABLE organization ADD COLUMN file_quota_gib REAL DEFAULT 0.0")
        c.execute("ALTER TABLE organization ADD COLUMN file_usage_gib REAL DEFAULT 0.0")
        c.execute("ALTER TABLE organization ADD COLUMN egress_quota_gib REAL DEFAULT 0.0")
        c.execute("ALTER TABLE organization ADD COLUMN egress_usage_gib REAL DEFAULT 0.0")
        c.execute("ALTER TABLE organization ADD COLUMN models JSON DEFAULT '{}'")
        # Remove nested quota column
        c.execute("ALTER TABLE organization DROP COLUMN quotas")
        src.commit()
        c.execute("PRAGMA table_info(organization)")
        pprint(c.fetchall())
        c.close()


def update_oauth_info():
    with sqlite3.connect(join(ENV_CONFIG.owl_db_dir, "main.db")) as src:
        c = src.cursor()
        c.execute("SELECT id FROM User")
        for row in c.fetchall():
            user_id = row[0]
            if user_id.startswith("github|"):
                c.execute(
                    "UPDATE User SET github_id = ? WHERE id = ?",
                    (int(user_id.split("|")[1]), user_id),
                )
                src.commit()
            elif user_id.startswith("google-oauth2|"):
                c.execute(
                    "UPDATE User SET google_id = ? WHERE id = ?",
                    (user_id.split("|")[1], user_id),
                )
                src.commit()
        c.close()


if __name__ == "__main__":
    with sqlite3.connect(join(ENV_CONFIG.owl_db_dir, "main.db")) as src:
        with sqlite3.connect(join(backup_dir, "main.db")) as dst:
            src.backup(dst)
    add_columns()
    update_oauth_info()
