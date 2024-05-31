from typing import Type

from loguru import logger
from sqlalchemy import Engine, NullPool, Pool, event
from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, create_engine


def _pragma_on_connect(dbapi_con, con_record):
    dbapi_con.execute("pragma foreign_keys = ON;\n")
    dbapi_con.execute("pragma journal_mode = WAL;\n")
    dbapi_con.execute("pragma synchronous = normal;\n")
    # dbapi_con.execute("pragma temp_store = memory;\n")
    # dbapi_con.execute("pragma mmap_size = 30000000000;\n")


def create_sqlite_engine(
    db_url: str,
    connect_args: dict | None = None,
    poolclass: Type[Pool] | None = None,
    echo: bool = False,
    **kwargs,
) -> Engine:
    engine = create_engine(
        db_url,
        connect_args=connect_args or {"check_same_thread": False},
        poolclass=poolclass or NullPool,
        echo=echo,
        **kwargs,
    )
    event.listen(engine, "connect", _pragma_on_connect)
    return engine


def create_sql_tables(db_class: Type[SQLModel], engine: Engine):
    try:
        db_class.metadata.create_all(engine)
    except OperationalError as e:
        logger.warning(f"Failed to create DB tables: {e}")
