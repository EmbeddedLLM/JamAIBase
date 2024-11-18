from functools import lru_cache
from os import makedirs
from os.path import dirname
from typing import Type
from urllib.parse import urlsplit

from loguru import logger
from sqlalchemy import Engine, NullPool, Pool, QueuePool, event
from sqlalchemy.exc import OperationalError
from sqlmodel import MetaData, SQLModel, create_engine, text

from owl.configs.manager import ENV_CONFIG


def _pragma_on_connect(dbapi_con, con_record):
    dbapi_con.execute("pragma foreign_keys = ON;\n")
    dbapi_con.execute("pragma journal_mode = WAL;\n")
    dbapi_con.execute("pragma synchronous = normal;\n")
    dbapi_con.execute("pragma journal_size_limit = 6144000;\n")
    # dbapi_con.execute("pragma temp_store = memory;\n")
    # dbapi_con.execute("pragma mmap_size = 30000000000;\n")


def _do_connect(dbapi_connection, connection_record):
    # Disable pysqlite's emitting of the BEGIN statement entirely.
    # Also stops it from emitting COMMIT before any DDL.
    dbapi_connection.isolation_level = None


def _do_begin(conn):
    # Emit our own BEGIN
    conn.exec_driver_sql("BEGIN")


def create_sqlite_engine(
    db_url: str,
    *,
    connect_args: dict | None = None,
    poolclass: Type[Pool] | None = None,
    echo: bool = False,
    **kwargs,
) -> Engine:
    db_dir = dirname(urlsplit(db_url).path.replace("/", "", 1))
    makedirs(db_dir, exist_ok=True)
    engine = create_engine(
        db_url,
        connect_args=connect_args or {"check_same_thread": False},
        poolclass=poolclass or NullPool,
        echo=echo,
        **kwargs,
    )
    event.listen(engine, "connect", _pragma_on_connect)
    # Enabling these seems to lead to DB locking issues
    # https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#pysqlite-serializable
    # https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#aiosqlite-serializable
    # event.listen(engine, "connect", _do_connect)
    # event.listen(engine, "begin", _do_begin)
    return engine


def create_sql_tables(db_class: Type[SQLModel], engine: Engine):
    try:
        db_class.metadata.create_all(engine)
    except Exception as e:
        logger.exception(f"Failed to create DB tables: {e}")
        if not isinstance(e, OperationalError):
            raise


@lru_cache(maxsize=1000)
def cached_text(query: str):
    return text(query)


MAIN_ENGINE = create_sqlite_engine(
    f"sqlite:///{ENV_CONFIG.owl_db_dir}/main.db",
    # https://github.com/bluesky/tiled/issues/663
    poolclass=QueuePool,
    pool_pre_ping=True,
    pool_size=ENV_CONFIG.owl_max_concurrency,
    max_overflow=ENV_CONFIG.owl_max_concurrency,
    pool_timeout=30,
    pool_recycle=300,
)


class UserSQLModel(SQLModel):
    metadata = MetaData()
