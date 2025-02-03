import os
import re
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from os import listdir
from os.path import exists, isdir, join
from pathlib import Path
from shutil import copytree, ignore_patterns, move, rmtree
from time import perf_counter, sleep
from typing import Any, BinaryIO, Literal, override

import filetype
import lancedb
import numpy as np
import pandas as pd
import pyarrow as pa
from filelock import FileLock
from lancedb.table import LanceTable
from loguru import logger
from sqlmodel import Session, select
from tenacity import retry, stop_after_attempt, wait_exponential
from typing_extensions import Self

from jamaibase.exceptions import (
    BadInputError,
    ResourceExistsError,
    ResourceNotFoundError,
    TableSchemaFixedError,
    make_validation_error,
)
from jamaibase.utils.io import df_to_csv, json_loads
from owl.configs.manager import ENV_CONFIG
from owl.db import cached_text, create_sql_tables, create_sqlite_engine
from owl.models import CloudEmbedder, CloudReranker
from owl.protocol import (
    COL_NAME_PATTERN,
    GEN_CONFIG_VAR_PATTERN,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    ChatEntry,
    ChatTableSchemaCreate,
    ChatThread,
    Chunk,
    ColName,
    ColumnDtype,
    ColumnSchema,
    CSVDelimiter,
    EmbedGenConfig,
    GenConfig,
    GenConfigUpdateRequest,
    GenTableOrderBy,
    KnowledgeTableSchemaCreate,
    ModelListConfig,
    PositiveInt,
    RowAddData,
    RowUpdateData,
    TableMeta,
    TableMetaResponse,
    TableName,
    TableSchema,
    TableSchemaCreate,
    TableSQLModel,
    TableType,
)
from owl.utils import datetime_now_iso, uuid7_draft2_str
from owl.utils.io import open_uri_sync, upload_file_to_s3

# Lance only support null values in string column
_py_type_default = {
    "int": 0,
    "int8": 0,
    "float": 0.0,
    "float32": 0.0,
    "float16": 0.0,
    "bool": False,
    "str": "''",
    "image": "''",
    "audio": "''",
}


class GenerativeTable:
    """
    Smart Table class.

    Note that by default, this class assumes that each method uses a new LanceDB connection.
    Otherwise, consider passing in `read_consistency_interval=timedelta(seconds=0)` during init.
    """

    FIXED_COLUMN_IDS = []

    def __init__(
        self,
        db_url: str,
        vector_db_url: str,
        *,
        read_consistency_interval: timedelta | None = None,
        create_sqlite_tables: bool = True,
    ) -> None:
        self.db_url = Path(db_url)
        self.vector_db_url = Path(vector_db_url)
        self.read_consistency_interval = read_consistency_interval
        self.sqlite_engine = create_sqlite_engine(db_url)
        if create_sqlite_tables:
            create_sql_tables(TableSQLModel, self.sqlite_engine)
        self._lance_db = None
        self.organization_id = db_url.split(os.sep)[-3]
        self.project_id = db_url.split(os.sep)[-2]
        # Thread and process safe lock
        self.lock_name_prefix = vector_db_url
        self.locks = {}

    @classmethod
    def from_ids(
        cls,
        org_id: str,
        project_id: str,
        table_type: str | TableType,
    ) -> Self:
        lance_path = join(ENV_CONFIG.owl_db_dir, org_id, project_id, table_type)
        sqlite_path = f"sqlite:///{lance_path}.db"
        read_consistency_interval = timedelta(seconds=0)
        if table_type == TableType.ACTION:
            return ActionTable(
                sqlite_path,
                lance_path,
                read_consistency_interval=read_consistency_interval,
            )
        elif table_type == TableType.KNOWLEDGE:
            return KnowledgeTable(
                sqlite_path,
                lance_path,
                read_consistency_interval=read_consistency_interval,
            )
        else:
            return ChatTable(
                sqlite_path,
                lance_path,
                read_consistency_interval=read_consistency_interval,
            )

    @property
    def lance_db(self):
        if self._lance_db is None:
            self._lance_db = lancedb.connect(
                self.vector_db_url, read_consistency_interval=self.read_consistency_interval
            )
        return self._lance_db

    def lock(self, name: str, timeout: int = ENV_CONFIG.owl_table_lock_timeout_sec):
        name = join(self.lock_name_prefix, f"{name}.lock")
        self.locks[name] = self.locks.get(name, FileLock(name, timeout=timeout))
        return self.locks[name]

    def create_session(self):
        return Session(self.sqlite_engine)

    def has_info_col_names(self, names: list[str]) -> bool:
        return sum(n.lower() in ("id", "updated at") for n in names) > 0

    def has_state_col_names(self, names: list[str]) -> bool:
        return any(n.endswith("_") for n in names)

    def num_output_columns(self, meta: TableMeta) -> int:
        return len(
            [col for col in meta.cols if col["gen_config"] is not None and col["vlen"] == 0]
        )

    def _create_table(
        self,
        session: Session,
        schema: TableSchemaCreate,
        remove_state_cols: bool = False,
        add_info_state_cols: bool = True,
    ) -> tuple[LanceTable, TableMeta]:
        table_id = schema.id
        with self.lock(table_id):
            meta = session.get(TableMeta, table_id)
            if meta is None:
                # Add metadata
                if add_info_state_cols:
                    schema = schema.add_info_cols().add_state_cols()
                meta = TableMeta(
                    id=table_id,
                    parent_id=None,
                    cols=[c.model_dump() for c in schema.cols],
                )
                session.add(meta)
                session.commit()
                session.refresh(meta)
                # Create Lance table
                table = self.lance_db.create_table(table_id, schema=schema.pyarrow)
            else:
                raise ResourceExistsError(f'Table "{table_id}" already exists.')
            if remove_state_cols:
                meta.cols = [c for c in meta.cols if not c["id"].endswith("_")]
        return table, meta

    def create_table(
        self,
        session: Session,
        schema: TableSchemaCreate,
        remove_state_cols: bool = False,
        add_info_state_cols: bool = True,
    ) -> tuple[LanceTable, TableMeta]:
        if not isinstance(schema, TableSchema):
            raise TypeError("`schema` must be an instance of `TableSchema`.")
        fixed_cols = set(c.lower() for c in self.FIXED_COLUMN_IDS)
        if len(fixed_cols.intersection(set(c.id.lower() for c in schema.cols))) != len(fixed_cols):
            raise BadInputError(f"Schema must contain fixed columns: {self.FIXED_COLUMN_IDS}")
        return self._create_table(
            session=session,
            schema=schema,
            remove_state_cols=remove_state_cols,
            add_info_state_cols=add_info_state_cols,
        )

    def open_table(self, table_id: TableName) -> LanceTable:
        try:
            table = self.lance_db.open_table(table_id)
        except FileNotFoundError as e:
            raise ResourceNotFoundError(f'Table "{table_id}" is not found.') from e
        return table

    def open_meta(
        self,
        session: Session,
        table_id: TableName,
        remove_state_cols: bool = False,
    ) -> TableMeta:
        meta = session.get(TableMeta, table_id)
        if meta is None:
            raise ResourceNotFoundError(f'Table "{table_id}" is not found.')
        if remove_state_cols:
            meta.cols = [c for c in meta.cols if not c["id"].endswith("_")]
        return meta

    def open_table_meta(
        self,
        session: Session,
        table_id: TableName,
        remove_state_cols: bool = False,
    ) -> tuple[LanceTable, TableMeta]:
        meta = self.open_meta(session, table_id, remove_state_cols=remove_state_cols)
        table = self.open_table(table_id)
        return table, meta

    def list_meta(
        self,
        session: Session,
        *,
        offset: int,
        limit: int,
        parent_id: str | None = None,
        search_query: str = "",
        order_by: str = GenTableOrderBy.UPDATED_AT,
        order_descending: bool = True,
        count_rows: bool = False,
        remove_state_cols: bool = False,
    ) -> tuple[list[TableMetaResponse], int]:
        t0 = perf_counter()
        search_query = search_query.strip()
        if parent_id is None:
            selection = select(TableMeta)
        elif parent_id.lower() == "_agent_":
            selection = select(TableMeta).where(TableMeta.parent_id == None)  # noqa
        elif parent_id.lower() == "_chat_":
            selection = select(TableMeta).where(TableMeta.parent_id != None)  # noqa
        else:
            selection = select(TableMeta).where(TableMeta.parent_id == parent_id)
        if search_query != "":
            selection = selection.where(TableMeta.id.ilike(f"%{search_query}%"))
        total = len(session.exec(selection).all())
        metas = session.exec(
            selection.order_by(
                cached_text(f"{order_by} DESC" if order_descending else f"{order_by} ASC")
            )
            .offset(offset)
            .limit(limit)
        ).all()
        t1 = perf_counter()
        meta_responses = []
        for meta in metas:
            try:
                num_rows = self.count_rows(meta.id) if count_rows else -1
            except Exception:
                table_path = self.vector_db_url / f"{meta.id}.lance"
                if exists(table_path) and len(listdir(table_path)) > 0:
                    logger.error(f"Lance table FAILED to be opened: {meta.id}")
                else:
                    logger.warning(f"Lance table MISSING, removing metadata: {meta.id}")
                    session.delete(meta)
                    continue
            meta_responses.append(
                TableMetaResponse.model_validate(meta, update={"num_rows": num_rows})
            )
        t2 = perf_counter()
        num_metas = len(metas)
        time_per_table = (t2 - t1) * 1000 / num_metas if num_metas > 0 else 0.0
        logger.info(
            (
                f"Listing {num_metas:,d} table metas took: {(t2 - t0) * 1000:.2f} ms  "
                f"SQLite query = {(t1 - t0) * 1000:.2f} ms  "
                f"Count rows (total) = {(t2 - t1) * 1000:.2f} ms  "
                f"Count rows (per table) = {time_per_table:.2f} ms"
            )
        )
        if remove_state_cols:
            for meta in meta_responses:
                meta.cols = [c for c in meta.cols if not c.id.endswith("_")]
        return meta_responses, total

    def count_rows(self, table_id: TableName, filter: str | None = None) -> int:
        return self.open_table(table_id).count_rows(filter)

    def duplicate_table(
        self,
        session: Session,
        table_id_src: TableName,
        table_id_dst: TableName,
        include_data: bool = True,
        create_as_child: bool = False,
    ) -> TableMeta:
        dst_meta = session.get(TableMeta, table_id_dst)
        if dst_meta is not None:
            raise ResourceExistsError(f'Table "{table_id_dst}" already exists.')
        # Duplicate metadata
        with self.lock(table_id_src):
            meta = self.open_meta(session, table_id_src)
            new_meta = TableMeta.model_validate(
                meta,
                update={
                    "id": table_id_dst,
                    "parent_id": table_id_src if create_as_child else None,
                },
            )
            session.add(new_meta)
            session.commit()
            session.refresh(new_meta)
            # Duplicate LanceTable
            if include_data:
                copytree(
                    self.vector_db_url / f"{table_id_src}.lance",
                    self.vector_db_url / f"{table_id_dst}.lance",
                    ignore=ignore_patterns("_indices"),
                )
                with self.create_session() as session:
                    self.create_indexes(session, table_id_dst, force=True)
            else:
                schema = TableSchema.model_validate(new_meta)
                self.lance_db.create_table(table_id_dst, schema=schema.pyarrow)
        return new_meta

    def rename_table(
        self,
        session: Session,
        table_id_src: TableName,
        table_id_dst: TableName,
    ) -> TableMeta:
        # Check
        dst_meta = session.get(TableMeta, table_id_dst)
        if dst_meta is not None:
            raise ResourceExistsError(f'Table "{table_id_dst}" already exists.')
        # Rename metadata
        with self.lock(table_id_src):
            meta = self.open_meta(session, table_id_src)
            meta.id = table_id_dst
            meta.updated_at = datetime_now_iso()
            session.add(meta)
            # Rename all parent IDs
            session.exec(
                cached_text(
                    f"UPDATE TableMeta SET parent_id = '{table_id_dst}' WHERE parent_id = '{table_id_src}'"
                )
            )
            session.commit()
            session.refresh(meta)
            # Rename LanceTable
            # self.lance_db.rename_table(table_id_src, table_id_dst)  # Seems like not implemented
            move(
                self.vector_db_url / f"{table_id_src}.lance",
                self.vector_db_url / f"{table_id_dst}.lance",
            )
        return meta

    def delete_table(self, session: Session, table_id: TableName) -> None:
        with self.lock(table_id):
            # Delete LanceTable
            for _ in range(10):
                # Try 10 times
                try:
                    rmtree(self.vector_db_url / f"{table_id}.lance")
                except FileNotFoundError as e:
                    raise ResourceNotFoundError(f'Table "{table_id}" is not found.') from e
                except Exception:
                    # There might be ongoing operations
                    sleep(0.5)
                else:
                    break
            # Delete metadata
            meta = session.get(TableMeta, table_id)
            if meta is None:
                raise ResourceNotFoundError(f'Table "{table_id}" is not found.')
            session.delete(meta)
            session.commit()
        return

    def update_gen_config(self, session: Session, updates: GenConfigUpdateRequest) -> TableMeta:
        table_id = updates.table_id
        meta = session.get(TableMeta, table_id)
        if meta is None:
            raise ResourceNotFoundError(f'Table "{table_id}" is not found.')
        meta_col_ids = set(c["id"] for c in meta.cols)
        update_col_ids = set(updates.column_map.keys())
        if len(update_col_ids - meta_col_ids) > 0:
            raise make_validation_error(
                ValueError(
                    f"Some columns are not found in the table: {update_col_ids - meta_col_ids}"
                ),
                loc=("body", "column_map"),
            )
        cols = deepcopy(meta.cols)
        for c in cols:
            # Validate and update
            gen_config = updates.column_map.get(c["id"], c["gen_config"])
            c["gen_config"] = (
                gen_config.model_dump() if isinstance(gen_config, GenConfig) else gen_config
            )
        meta.cols = [c.model_dump() for c in TableSchema(id=meta.id, cols=cols).cols]
        session.add(meta)
        session.commit()
        session.refresh(meta)
        return meta

    def add_columns(
        self, session: Session, schema: TableSchemaCreate
    ) -> tuple[LanceTable, TableMeta]:
        """
        Adds one or more input or output column.

        Args:
            session (Session): SQLAlchemy session.
            schema (TableSchemaCreate): Schema of the columns to be added.

        Raises:
            ResourceNotFoundError: If the table is not found.
            ValueError: If any of the columns exists.

        Returns:
            table (LanceTable): Lance table.
            meta (TableMeta): Table metadata.
        """
        if not isinstance(schema, TableSchema):
            raise TypeError("`schema` must be an instance of `TableSchema`.")
        table_id = schema.id
        # Check
        meta = self.open_meta(session, table_id)
        schema = schema.add_state_cols()
        cols = meta.cols_schema + schema.cols
        if len(set(c.id for c in cols)) != len(cols):
            raise make_validation_error(
                ValueError("Schema and table contain overlapping column names."),
                loc=("body", "cols"),
            )
        meta.cols = [
            c.model_dump()
            for c in TableSchema(id=meta.id, cols=[c.model_dump() for c in cols]).cols
        ]

        with self.lock(table_id):
            # Add columns to LanceDB
            table = self.open_table(table_id)
            # Non-vector columns can be added using SQL statement
            # TODO: Investigate adding vector columns using BatchUDF
            cols_to_add = {
                c.id: f"{_py_type_default[c.dtype]}" for c in schema.cols if c.vlen == 0
            }
            if len(cols_to_add) > 0:
                table.add_columns(cols_to_add)
            # Add vector columns to Lance Table using merge op (this is very slow)
            vectors = [
                [np.zeros(shape=[c.vlen], dtype=c.dtype)] for c in schema.cols if c.vlen > 0
            ]
            if len(vectors) > 0:
                _id = table.search().limit(1).to_list()
                _id = _id[0]["ID"] if len(_id) > 0 else "0"
                vec_schema = schema.pa_vec_schema
                vec_schema = vec_schema.insert(0, table.schema.field("ID"))
                pa_table = pa.table([[_id]] + vectors, schema=vec_schema)
                table.merge(pa_table, left_on="ID")

            # Add Table Metadata
            meta.updated_at = datetime_now_iso()
            session.add(meta)
            session.commit()
            session.refresh(meta)
        return table, meta

    def _drop_columns(
        self,
        session: Session,
        table_id: TableName,
        col_names: list[ColName],
    ) -> tuple[LanceTable, TableMeta]:
        """
        NOTE: This is broken until lance issue is resolved
        https://github.com/lancedb/lancedb/pull/1227

        Drops one or more input or output column.

        Args:
            session (Session): SQLAlchemy session.
            table_id (str): Table ID.
            col_names (list[str]): List of column ID to drop.

        Raises:
            TypeError: If `col_names` is not a list.
            ResourceNotFoundError: If the table is not found.
            ResourceNotFoundError: If any of the columns is not found.

        Returns:
            table (LanceTable): Lance table.
            meta (TableMeta): Table metadata.
        """
        if not isinstance(col_names, list):
            raise TypeError("`col_names` must be a list.")
        if self.has_state_col_names(col_names):
            raise make_validation_error(
                ValueError("Cannot drop state columns."),
                loc=("body", "column_names"),
            )
        if self.has_info_col_names(col_names):
            raise make_validation_error(
                ValueError('Cannot drop "ID" or "Updated at".'),
                loc=("body", "column_names"),
            )
        with self.lock(table_id):
            meta = self.open_meta(session, table_id)
            col_names += [f"{n}_" for n in col_names]
            table = self.open_table(table_id)
            try:
                table.drop_columns(col_names)
            except ValueError as e:
                raise ResourceNotFoundError(e) from e
            meta.cols = [c.model_dump() for c in meta.cols_schema if c.id not in col_names]
            meta.updated_at = datetime_now_iso()
            session.add(meta)
            session.commit()
            session.refresh(meta)
        return table, meta

    # Look at this instead !!
    def drop_columns(
        self,
        session: Session,
        table_id: TableName,
        column_names: list[ColName],
    ) -> tuple[LanceTable, TableMeta]:
        """
        Drops one or more input or output column.

        Args:
            session (Session): SQLAlchemy session.
            table_id (str): Table ID.
            column_names (list[str]): List of column ID to drop.

        Raises:
            TypeError: If `column_names` is not a list.
            ResourceNotFoundError: If the table is not found.
            ResourceNotFoundError: If any of the columns is not found.

        Returns:
            table (LanceTable): Lance table.
            meta (TableMeta): Table metadata.
        """
        if not isinstance(column_names, list):
            raise TypeError("`column_names` must be a list.")
        if self.has_state_col_names(column_names):
            raise BadInputError("Cannot drop state columns.")
        if self.has_info_col_names(column_names):
            raise BadInputError('Cannot drop "ID" or "Updated at".')
        fixed_cols = set(c.lower() for c in self.FIXED_COLUMN_IDS)
        if len(fixed_cols.intersection(set(c.lower() for c in column_names))) > 0:
            raise BadInputError(f"Cannot drop fixed columns: {self.FIXED_COLUMN_IDS}")

        with self.lock(table_id):
            # Get table metadata
            meta = self.open_meta(session, table_id)
            # Create new table with dropped columns
            new_table_id = f"{table_id}_dropped_{uuid7_draft2_str()}"
            column_names += [f"{col_name}_" for col_name in column_names]
            new_schema = TableSchema(
                id=new_table_id,
                cols=[c for c in meta.cols_schema if c.id not in column_names],
            )
            new_table, new_meta = self._create_table(
                session, new_schema, add_info_state_cols=False
            )

            # Copy data from old table to new table
            old_table = self.open_table(table_id)
            if old_table.count_rows() > 0:
                data = old_table._dataset.to_table(
                    columns=[c.id for c in new_schema.cols]
                ).to_pylist()
                new_table.add(data)

            # Delete old table and rename
            self.delete_table(session, table_id)
            new_meta = self.rename_table(session, new_table_id, table_id)
            new_table = self.open_table(table_id)
        return new_table, new_meta

    def rename_columns(
        self,
        session: Session,
        table_id: TableName,
        column_map: dict[ColName, ColName],
    ) -> TableMeta:
        new_col_names = set(column_map.values())
        if self.has_state_col_names(column_map.keys()):
            raise BadInputError("Cannot rename state columns.")
        if self.has_info_col_names(column_map.keys()):
            raise BadInputError('Cannot rename "ID" or "Updated at".')
        fixed_cols = set(c.lower() for c in self.FIXED_COLUMN_IDS)
        if len(fixed_cols.intersection(set(c.lower() for c in column_map))) > 0:
            raise BadInputError(f"Cannot rename fixed columns: {self.FIXED_COLUMN_IDS}")
        if len(new_col_names) != len(column_map):
            raise BadInputError("`column_map` contains repeated new column names.")
        if not all(re.match(COL_NAME_PATTERN, v) for v in column_map.values()):
            raise BadInputError("`column_map` contains invalid new column names.")
        meta = self.open_meta(session, table_id)
        col_names = set(c.id for c in meta.cols_schema)
        overlap_col_names = col_names.intersection(new_col_names)
        if len(overlap_col_names) > 0:
            raise BadInputError(
                (
                    "`column_map` contains new column names that "
                    f"overlap with existing column names: {overlap_col_names}"
                )
            )
        not_found = set(column_map.keys()) - col_names
        if len(not_found) > 0:
            raise ResourceNotFoundError(f"Some columns are not found: {list(not_found)}.")
        # Add state columns
        for k in list(column_map.keys()):
            column_map[f"{k}_"] = f"{column_map[k]}_"
        # Modify metadata
        cols = []
        for col in meta.cols:
            col = deepcopy(col)
            _id = col["id"]
            col["id"] = column_map.get(_id, _id)
            if (
                col["gen_config"] is not None
                and col["gen_config"].get("object", "") == "gen_config.llm"
            ):
                for k in ("system_prompt", "prompt"):
                    col["gen_config"][k] = re.sub(
                        GEN_CONFIG_VAR_PATTERN,
                        lambda m: f"${{{column_map.get(m.group(1), m.group(1))}}}",
                        col["gen_config"][k],
                    )
            cols.append(col)
        with self.lock(table_id):
            meta.cols = cols
            meta.updated_at = datetime_now_iso()
            session.add(meta)
            session.commit()
            session.refresh(meta)
            # Modify LanceTable
            alterations = [{"path": k, "name": v} for k, v in column_map.items()]
            table = self.open_table(table_id)
            table.alter_columns(*alterations)
        return meta

    def reorder_columns(
        self,
        session: Session,
        table_id: TableName,
        column_names: list[ColName],
    ) -> TableMeta:
        column_names_low = [n.lower() for n in column_names]
        if len(set(column_names_low)) != len(column_names):
            raise BadInputError("Column names must be unique (case-insensitive).")
        if self.has_state_col_names(column_names):
            raise BadInputError("Cannot reorder state columns.")
        if self.has_info_col_names(column_names) and column_names_low[:2] != ["id", "updated at"]:
            raise BadInputError('Cannot reorder "ID" or "Updated at".')
        order = ["ID", "Updated at"]
        for c in column_names:
            order += [c, f"{c}_"]
        meta = self.open_meta(session, table_id)
        try:
            meta.cols = [
                c.model_dump() for c in sorted(meta.cols_schema, key=lambda x: order.index(x.id))
            ]
        except ValueError as e:
            raise ResourceNotFoundError(e) from e
        meta.updated_at = datetime_now_iso()
        # Validate changes
        TableSchema.model_validate(meta.model_dump())
        session.add(meta)
        session.commit()
        session.refresh(meta)
        return meta

    async def add_rows(
        self,
        session: Session,
        table_id: TableName,
        data: list[dict[ColName, Any]],
        errors: list[list[str]] | None = None,
    ) -> Self:
        if not isinstance(data, list):
            raise TypeError("`data` must be a list.")
        with self.lock(table_id):
            with await lancedb.connect_async(
                uri=self.vector_db_url,
                read_consistency_interval=self.read_consistency_interval,
            ) as db:
                try:
                    with await db.open_table(table_id) as table:
                        meta = self.open_meta(session, table_id)
                        # Validate data and generate ID & timestamp under write lock
                        data = RowAddData(table_meta=meta, data=data, errors=errors).set_id().data
                        # Add to Lance Table
                        await table.add(data)
                        # Update metadata
                        meta.updated_at = datetime_now_iso()
                        session.add(meta)
                        session.commit()
                except FileNotFoundError as e:
                    raise ResourceNotFoundError(f'Table "{table_id}" is not found.') from e
        return self

    def update_rows(
        self,
        session: Session,
        table_id: TableName,
        *,
        where: str | None,
        values: dict[str, Any],
        errors: list[str] | None = None,
    ) -> Self:
        with self.lock(table_id):
            table = self.open_table(table_id)
            meta = self.open_meta(session, table_id)
            # Validate data and generate ID & timestamp under write lock
            values = RowUpdateData(
                table_meta=meta,
                data=[values],
                errors=None if errors is None else [errors],
            )
            values = values.sql_escape().data[0]
            # TODO: Vector column update seems to be broken
            values = {k: v for k, v in values.items() if not isinstance(v, np.ndarray)}
            table.update(where=where, values=values)
            # Update metadata
            meta.updated_at = datetime_now_iso()
            session.add(meta)
            session.commit()
        return self

    @staticmethod
    def _filter_col(
        col_id: str,
        columns: list[str] | None = None,
        remove_state_cols: bool = False,
    ) -> bool:
        if remove_state_cols and col_id.endswith("_"):
            return False
        # Hybrid search distance and match scores
        if col_id.startswith("_"):
            return False
        if columns is not None:
            columns = {"id", "updated at"} | {c.lower() for c in columns}
            return col_id.lower() in columns
        return True

    @staticmethod
    def _process_cell(
        row: dict[str, Any],
        col_id: str,
        convert_null: bool,
        include_original: bool,
        float_decimals: int,
        vec_decimals: int,
    ):
        state_id = f"{col_id}_"
        data = row[col_id]
        if state_id not in row:
            # Some columns like "ID", "Updated at" do not have state cols
            return data
        # Process precision
        if float_decimals > 0 and isinstance(data, float):
            data = round(data, float_decimals)
        elif vec_decimals > 0 and isinstance(data, list):
            data = np.asarray(data).round(vec_decimals).tolist()
        state = row[state_id]
        if state == "" or state is None:
            data = None if convert_null else data
            return {"value": data} if include_original else data
        state = json_loads(state)
        data = None if convert_null and state["is_null"] else data
        if include_original:
            ret = {"value": data}
            if "original" in state:
                ret["original"] = state["original"]
            # if "error" in state:
            #     ret["error"] = state["error"]
            return ret
        else:
            return data

    @staticmethod
    def _post_process_rows(
        rows: list[dict[str, Any]],
        *,
        columns: list[str] | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        include_original: bool = False,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ):
        if json_safe:
            rows = [
                {k: v.isoformat() if isinstance(v, datetime) else v for k, v in row.items()}
                for row in rows
            ]
        rows = [
            {
                k: GenerativeTable._process_cell(
                    row,
                    k,
                    convert_null=convert_null,
                    include_original=include_original,
                    float_decimals=float_decimals,
                    vec_decimals=vec_decimals,
                )
                for k in row
                if not (vec_decimals < 0 and isinstance(row[k], list))
            }
            for row in rows
        ]
        rows = [
            {
                k: v
                for k, v in row.items()
                if GenerativeTable._filter_col(
                    k, columns=columns, remove_state_cols=remove_state_cols
                )
            }
            for row in rows
        ]
        return rows

    @staticmethod
    def _post_process_rows_df(
        df: pd.DataFrame,
        *,
        columns: list[str] | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        include_original: bool = False,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ):
        dt_columns = set(df.select_dtypes(include="datetimetz").columns.to_list())
        float_columns = set(df.select_dtypes(include="float").columns.to_list())

        def _process_row(row: pd.Series):
            for col_id in row.index.to_list():
                state_id = f"{col_id}_"
                try:
                    data = row[col_id]
                except KeyError:
                    # The column is dropped
                    continue
                if json_safe and col_id in dt_columns:
                    row[col_id] = data.isoformat()
                if state_id not in row:
                    # Some columns like "ID", "Updated at" do not have state cols
                    # State cols also do not have their state cols
                    continue
                state = row[state_id]
                # Process precision
                if isinstance(data, np.ndarray):
                    if vec_decimals < 0:
                        row.drop([col_id, state_id], inplace=True)
                        continue
                    elif vec_decimals == 0:
                        if json_safe:
                            data = data.tolist()
                    elif vec_decimals > 0:
                        if json_safe:
                            data = [round(d, vec_decimals) for d in data.tolist()]
                        else:
                            data = data.round(vec_decimals)
                elif float_decimals > 0 and col_id in float_columns:
                    row[col_id] = round(data, float_decimals)
                # Convert null
                if state == "" or state is None:
                    data = None if convert_null else data
                    row[col_id] = {"value": data} if include_original else data
                    continue
                state = json_loads(state)
                data = None if convert_null and state["is_null"] else data
                if include_original:
                    ret = {"value": data}
                    if "original" in state:
                        ret["original"] = state["original"]
                    # if "error" in state:
                    #     ret["error"] = state["error"]
                    row[col_id] = ret
                else:
                    row[col_id] = data
            return row

        df = df.apply(_process_row, axis=1)
        # Remove hybrid search distance and match score columns
        keep_cols = [c for c in df.columns.to_list() if not c.startswith("_")]
        # Remove state columns
        if remove_state_cols:
            keep_cols = [c for c in keep_cols if not c.endswith("_")]
        # Column selection
        if columns is not None:
            columns = {"id", "updated at"} | {c.lower() for c in columns}
            keep_cols = [c for c in keep_cols if c.lower() in columns]
        df = df[keep_cols]
        return df

    def get_row(
        self,
        table_id: TableName,
        row_id: str,
        *,
        columns: list[str] | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        include_original: bool = False,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ) -> dict[str, Any]:
        table = self.open_table(table_id)
        rows = table.search().where(where=f"`ID` = '{row_id}'", prefilter=True).to_list()
        if len(rows) == 0:
            raise ResourceNotFoundError(f'Row "{row_id}" is not found.')
        elif len(rows) > 1:
            logger.warning(f"More than one row in table {table_id} with ID {row_id}")
        rows = self._post_process_rows(
            rows,
            columns=columns,
            convert_null=convert_null,
            remove_state_cols=remove_state_cols,
            json_safe=json_safe,
            include_original=include_original,
            float_decimals=float_decimals,
            vec_decimals=vec_decimals,
        )
        return rows[0]

    @staticmethod
    def _count_rows_query(table_name: str) -> str:
        return f"SELECT COUNT(*) FROM '{table_name}'"

    @staticmethod
    def _list_rows_query(
        table_name: str,
        *,
        sort_by: str,
        sort_order: Literal["ASC", "DESC"] = "ASC",
        starting_after: str | int | None = None,
        id_column: str = "ID",
        offset: int = 0,
        limit: int = 100,
    ) -> str:
        if starting_after is None:
            query = (
                f"""SELECT * FROM '{table_name}' ORDER BY "{sort_by}" {sort_order} LIMIT {limit}"""
            )
        else:
            query = f"""
    WITH sorted_rows AS (
        SELECT
        *,
        ROW_NUMBER() OVER (
            ORDER BY "{sort_by}" {sort_order}
        ) AS _row_num
        FROM '{table_name}'
        ),
    cursor_position AS (
        SELECT _row_num
        FROM sorted_rows
        WHERE "{id_column}" = '{starting_after}'
    )
    SELECT sr.*
    FROM sorted_rows sr, cursor_position cp
    WHERE sr._row_num > cp._row_num OR cp._row_num IS NULL
    ORDER BY sr._row_num
    OFFSET {offset}
    LIMIT {limit}
    """
        return query

    def list_rows(
        self,
        table_id: TableName,
        *,
        offset: int = 0,
        limit: int = 1_000,
        columns: list[ColName] | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        include_original: bool = False,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        order_descending: bool = True,
    ) -> tuple[list[dict[str, Any]], int]:
        try:
            table = self.open_table(table_id)
            total = self.count_rows(table_id)
        except ValueError as e:
            raise ResourceNotFoundError(f'Table "{table_id}" is not found.') from e
        offset, limit = max(0, offset), max(1, limit)
        if offset >= total:
            rows = []
        else:
            if offset + limit > total:
                limit = total - offset
            if order_descending:
                offset = max(0, total - limit - offset)
            rows = table._dataset.to_table(offset=offset, limit=limit).to_pylist()
            rows = sorted(rows, reverse=order_descending, key=lambda r: r["ID"])
            rows = self._post_process_rows(
                rows,
                columns=columns,
                convert_null=convert_null,
                remove_state_cols=remove_state_cols,
                json_safe=json_safe,
                include_original=include_original,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            )
        return rows, total

    def delete_row(self, session: Session, table_id: TableName, row_id: str) -> Self:
        with self.lock(table_id):
            table = self.open_table(table_id)
            table.delete(f"`ID` = '{row_id}'")
            # Update metadata
            meta = self.open_meta(session, table_id)
            meta.updated_at = datetime_now_iso()
            session.add(meta)
            session.commit()
        return self

    def delete_rows(
        self,
        session: Session,
        table_id: TableName,
        row_ids: list[str] | None = None,
        where: str | None = "",
    ) -> Self:
        if row_ids is None:
            row_ids = []
        with self.lock(table_id):
            table = self.open_table(table_id)
            for row_id in row_ids:
                table.delete(f"`ID` = '{row_id}'")
            if where:
                table.delete(where)
            # Update metadata
            meta = self.open_meta(session, table_id)
            meta.updated_at = datetime_now_iso()
            session.add(meta)
            session.commit()
        return self

    @staticmethod
    def _interpolate_column(
        prompt: str,
        column_dtypes: dict[str, str],
        column_contents: dict[str, Any],
    ) -> str:
        """
        Replaces / interpolates column references in the prompt with their contents.

        Args:
            prompt (str): The original prompt with zero or more column references.

        Returns:
            new_prompt (str): The prompt with column references replaced.
        """

        def replace_match(match):
            col_id = match.group(1)
            try:
                if column_dtypes[col_id] == "image":
                    return "<image_file>"
                elif column_dtypes[col_id] == "audio":
                    return "<audio_file>"
                return str(column_contents[col_id])
            except KeyError as e:
                raise KeyError(f'Referenced column "{col_id}" is not found.') from e

        return re.sub(GEN_CONFIG_VAR_PATTERN, replace_match, prompt)

    def get_conversation_thread(
        self,
        table_id: TableName,
        column_id: str,
        row_id: str = "",
        include: bool = True,
    ) -> ChatThread:
        with self.create_session() as session:
            meta = self.open_meta(session, table_id)
        cols = {c.id: c for c in meta.cols_schema}
        chat_cols = {c.id: c for c in cols.values() if getattr(c.gen_config, "multi_turn", False)}
        try:
            gen_config = chat_cols[column_id].gen_config
        except KeyError as e:
            raise ResourceNotFoundError(
                f'Column "{column_id}" is not found. Available chat columns: {list(chat_cols.keys())}'
            ) from e
        ref_col_ids = re.findall(GEN_CONFIG_VAR_PATTERN, gen_config.prompt)
        rows, _ = self.list_rows(
            table_id=table_id,
            offset=0,
            limit=1_000_000,
            columns=ref_col_ids + [column_id],
            convert_null=True,
            remove_state_cols=True,
            json_safe=True,
            float_decimals=0,
            vec_decimals=0,
            order_descending=False,
        )
        if row_id:
            row_ids = [r["ID"] for r in rows]
            try:
                rows = rows[: row_ids.index(row_id) + (1 if include else 0)]
            except ValueError as e:
                raise make_validation_error(
                    ValueError(f'Row ID "{row_id}" is not found in table "{table_id}".'),
                    loc=("body", "row_id"),
                ) from e
        thread = []
        if gen_config.system_prompt:
            thread.append(ChatEntry.system(gen_config.system_prompt))
        for row in rows:
            thread.append(
                ChatEntry.user(
                    self._interpolate_column(
                        gen_config.prompt,
                        {c.id: c.dtype for c in cols.values()},
                        row,
                    )
                )
            )
            thread.append(ChatEntry.assistant(row[column_id]))
        return ChatThread(thread=thread)

    def export_csv(
        self,
        table_id: TableName,
        columns: list[ColName] | None = None,
        file_path: str = "",
        delimiter: CSVDelimiter | str = ",",
    ) -> pd.DataFrame:
        if isinstance(delimiter, str):
            try:
                delimiter = CSVDelimiter[delimiter]
            except KeyError as e:
                raise make_validation_error(
                    ValueError(f'Delimiter can only be "," or "\\t", received: {delimiter}'),
                    loc=("body", "delimiter"),
                ) from e
        rows, total = self.list_rows(
            table_id=table_id,
            offset=0,
            limit=self.count_rows(table_id),
            columns=columns,
            convert_null=True,
            remove_state_cols=True,
            json_safe=True,
            include_original=False,
            float_decimals=0,
            vec_decimals=0,
            order_descending=False,
        )
        df = pd.DataFrame.from_dict(rows, orient="columns", dtype=None, columns=None)
        if len(df) != total:
            logger.error(
                f"Table {table_id} has {total:,d} rows but exported DF has {len(df):,d} rows !!!"
            )
        if file_path == "":
            return df
        if delimiter == CSVDelimiter.COMMA and not file_path.endswith(".csv"):
            file_path = f"{file_path}.csv"
        elif delimiter == CSVDelimiter.TAB and not file_path.endswith(".tsv"):
            file_path = f"{file_path}.tsv"
        df_to_csv(df, file_path, sep=delimiter.value)
        return df

    def dump_parquet(
        self,
        session: Session,
        table_id: TableName,
        dest: str | BinaryIO,
        *,
        compression: Literal["NONE", "ZSTD", "LZ4", "SNAPPY"] = "ZSTD",
    ) -> None:
        from pyarrow.parquet import write_table

        with self.lock(table_id):
            meta = self.open_meta(session, table_id)
            table = self.open_table(table_id)
            # Convert into Arrow Table
            pa_table = table._dataset.to_table(offset=None, limit=None)
            # Add file data into Arrow Table
            file_col_ids = [col.id for col in meta.cols_schema if col.dtype in ["image", "audio"]]
            for col_id in file_col_ids:
                file_bytes = []
                for uri in pa_table.column(col_id).to_pylist():
                    if not uri:
                        file_bytes.append(b"")
                        continue
                    with open_uri_sync(uri) as f:
                        file_bytes.append(f.read())
                # Append byte column
                pa_table = pa_table.append_column(
                    pa.field(f"{col_id}__", pa.binary()), [file_bytes]
                )
            # Add Generative Table metadata
            pa_meta = pa_table.schema.metadata or {}
            pa_table = pa_table.replace_schema_metadata(
                {"gen_table_meta": meta.model_dump_json(), **pa_meta}
            )
            if isinstance(dest, str):
                if isdir(dest):
                    dest = join(dest, f"{table_id}.parquet")
                elif not dest.endswith(".parquet"):
                    dest = f"{dest}.parquet"
            write_table(pa_table, dest, compression=compression)

    async def import_parquet(
        self,
        session: Session,
        source: str | BinaryIO,
        table_id_dst: str | None,
    ) -> tuple[LanceTable, TableMeta]:
        from pyarrow.parquet import read_table

        # Check metadata
        pa_table = read_table(source, columns=None, use_threads=False, memory_map=True)
        try:
            meta = TableMeta.model_validate_json(pa_table.schema.metadata[b"gen_table_meta"])
        except KeyError as e:
            raise BadInputError("Missing table metadata in the Parquet file.") from e
        except Exception as e:
            raise BadInputError("Invalid table metadata in the Parquet file.") from e
        # Check for required columns
        required_columns = set(self.FIXED_COLUMN_IDS)
        meta_cols = {c.id for c in meta.cols_schema}
        if len(required_columns - meta_cols) > 0:
            raise BadInputError(
                f"Missing columns in table metadata: {list(required_columns - meta_cols)}."
            )
        # Table ID must not exist
        if table_id_dst is None:
            table_id_dst = meta.id
        with self.lock(table_id_dst):
            if session.get(TableMeta, table_id_dst) is not None:
                raise ResourceExistsError(f'Table "{table_id_dst}" already exists.')
            # Upload files
            file_col_ids = [col.id for col in meta.cols_schema if col.dtype in ["image", "audio"]]
            for col_id in file_col_ids:
                new_uris = []
                for old_uri, content in zip(
                    pa_table.column(col_id).to_pylist(),
                    pa_table.column(f"{col_id}__").to_pylist(),
                    strict=True,
                ):
                    if len(content) == 0:
                        new_uris.append(None)
                        continue
                    mime_type = filetype.guess(content).mime
                    if mime_type is None:
                        mime_type = "application/octet-stream"
                    uri = await upload_file_to_s3(
                        self.organization_id,
                        self.project_id,
                        content,
                        mime_type,
                        old_uri.split("/")[-1],
                    )
                    new_uris.append(uri)
                # Drop old columns
                pa_table = pa_table.drop_columns([col_id, f"{col_id}__"])
                # Append new column
                pa_table = pa_table.append_column(pa.field(col_id, pa.utf8()), [new_uris])
            # Import Generative Table
            meta.id = table_id_dst
            session.add(meta)
            session.commit()
            session.refresh(meta)
            table = self.lance_db.create_table(meta.id, data=pa_table, schema=pa_table.schema)
            self.create_indexes(
                session=session,
                table_id=meta.id,
                force=True,
            )
            session.refresh(meta)
        return table, meta

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _run_query(
        self,
        session: Session,
        table_id: TableName,
        table: LanceTable,
        query: np.ndarray | list | str | None = None,
        column_name: str | None = None,
        where: str | None = None,
        limit: PositiveInt = 10_000,
        metric: str = "cosine",
        nprobes: PositiveInt = 50,
        refine_factor: PositiveInt = 20,
    ) -> list[dict[str, Any]]:
        is_vector = isinstance(query, (list, np.ndarray))
        if query is None:
            column_name = None
            query_type = "auto"
        elif is_vector:
            query_type = "vector"
        elif isinstance(query, str):
            query = re.sub(r"[\W\s]", " ", query.lower())
            query_type = "fts"
        else:
            raise TypeError("`query` must be one of [np.ndarray | list | str | None].")
        query_builder = table.search(
            query=query,
            vector_column_name=column_name,
            query_type=query_type,
        )
        if is_vector:
            query_builder = (
                query_builder.metric(metric).nprobes(nprobes).refine_factor(refine_factor)
            )
        if where:
            query_builder = query_builder.where(where, prefilter=True)
        try:
            results = query_builder.limit(limit).to_list()
        except ValueError:
            logger.exception(
                f'Failed to perform search on table "{table_id}" !!! Attempting index rebuild ...'
            )
            index_ok = self.create_indexes(session, table_id, force=True)
            if index_ok:
                logger.warning(f'Reindex table "{table_id}" OK, retrying search ...')
            else:
                logger.error(
                    f'Failed to reindex table "{table_id}" !!! Retrying search anyway ...'
                )
            results = query_builder.limit(limit).to_list()
        return results

    @staticmethod
    def _reciprocal_rank_fusion(
        search_results: list[list[dict]], result_key: str = "ID", K: int = 60
    ):
        """
        Perform reciprocal rank fusion to merge the rank of the search results (arbitrary number of results and can be varying in length)
        Args:
            search_results: list of search results from lance query, search result is a sorted list of dict (descending order of closeness)
            result_key: dict key of the search result
            K: const (def=60) for reciprocal rank fusion
        Return:
            A list of dict of original result with the rrf scores (higher scores, higher ranking)
        """
        rrf_scores = defaultdict(lambda: {"rrf_score": 0.0})
        for search_result in search_results:
            for rank, result in enumerate(search_result, start=1):
                result_id = result[result_key]
                rrf_scores[result_id]["rrf_score"] += 1.0 / (rank + K)
                rrf_scores[result_id].update(result)
        sorted_rrf = sorted(rrf_scores.values(), key=lambda x: x["rrf_score"], reverse=True)
        return sorted_rrf

    def regex_search(
        self,
        session: Session,
        table_id: TableName,
        query: str | None,
        *,
        columns: list[ColName] | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        include_original: bool = False,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        order_descending: bool = True,
    ) -> list[dict[str, Any]]:
        table, meta = self.open_table_meta(session, table_id)
        if self.count_rows(table_id) == 0:
            return []
        if not isinstance(query, str):
            raise TypeError(f"`query` must be string, received: {type(query)}")
        rows = []
        t0 = perf_counter()
        cols = self.fts_cols(meta)
        for col in cols:
            rows += table.search().where(f"regexp_match(`{col.id}`, '{query}')").to_list()
        logger.info(f"Regex search timings ({len(cols)} cols): {perf_counter() - t0:,.3f}")
        # De-duplicate and sort
        rows = {r["ID"]: r for r in rows}.values()
        rows = sorted(rows, reverse=order_descending, key=lambda r: r["ID"])
        rows = self._post_process_rows(
            rows,
            columns=columns,
            convert_null=convert_null,
            remove_state_cols=remove_state_cols,
            json_safe=json_safe,
            include_original=include_original,
            float_decimals=float_decimals,
            vec_decimals=vec_decimals,
        )
        return rows

    async def hybrid_search(
        self,
        session: Session,
        table_id: TableName,
        query: str | None,
        *,
        where: str | None = None,
        limit: PositiveInt = 100,
        columns: list[ColName] | None = None,
        metric: str = "cosine",
        nprobes: PositiveInt = 50,
        refine_factor: PositiveInt = 20,
        embedder: CloudEmbedder | None = None,
        reranker: CloudReranker | None = None,
        reranking_model: str | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        include_original: bool = False,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ) -> list[dict[str, Any]]:
        if not (isinstance(limit, int) and limit > 0):
            # TODO: Currently LanceDB is bugged, limit in theory can be None or 0 or negative
            # https://github.com/lancedb/lancedb/issues/1151
            raise TypeError("`limit` must be a positive non-zero integer.")
        t0 = perf_counter()
        table, meta = self.open_table_meta(session, table_id)
        if self.count_rows(table_id) == 0:
            return []
        timings = {}
        if query is None:
            t1 = perf_counter()
            rows = self._run_query(
                session=session,
                table_id=table_id,
                table=table,
                query=None,
                column_name=None,
                where=where,
                limit=limit,
            )
            timings["no_query"] = perf_counter() - t1
        else:
            if not isinstance(query, str):
                raise TypeError(f"`query` must be string, received: {type(query)}")
            search_results = []
            # 2024-06 (BUG?): lance fts works on all indexed cols at once (can't specify the col to be searched)
            # Thus no need to loop through indexed col one by one
            if len(self.fts_cols(meta)) > 0:
                t1 = perf_counter()
                fts_result = self._run_query(
                    session=session,
                    table_id=table_id,
                    table=table,
                    query=query,
                    # column_name=c.id,
                    where=where,
                    limit=limit,
                    metric=metric,
                    nprobes=nprobes,
                    refine_factor=refine_factor,
                )
                timings["FTS:"] = perf_counter() - t1
                search_results.append(fts_result)
            for c in self.embedding_cols(meta):
                t1 = perf_counter()
                embedding = await embedder.embed_queries(
                    c.gen_config.embedding_model, texts=[query]
                )
                # TODO: Benchmark this
                # Searching using float16 seems to be faster on float32 and float16 indexes
                # 2024-05-21, lance 0.6.13, pylance 0.10.12
                embedding = np.asarray(embedding.data[0].embedding, dtype=np.float16)
                embedding = embedding / np.linalg.norm(embedding)
                timings[f"Embed ({c.gen_config.embedding_model}): {c.id}"] = perf_counter() - t1
                t1 = perf_counter()
                sub_rows = self._run_query(
                    session=session,
                    table_id=table_id,
                    table=table,
                    query=embedding,
                    column_name=c.id,
                    where=where,
                    limit=limit,
                    metric=metric,
                    nprobes=nprobes,
                    refine_factor=refine_factor,
                )
                # vector_score from lance is 1.0 - cosine similarity (0. exact match)
                search_results.append(sub_rows)
                timings[f"VS: {c.id}"] = perf_counter() - t1
            # list of search results with rrf_score
            rows = self._reciprocal_rank_fusion(search_results)
            if reranker is None:
                # No longer do a linear combination for hybrid scores, use RRF score instead.
                _scores = [(f'(RRF_score={r["rrf_score"]:.1f}, ') for r in rows]
                logger.info(f"Hybrid search scores: {_scores}")
            else:
                t1 = perf_counter()
                chunks = await reranker.rerank_chunks(
                    reranking_model,
                    chunks=[
                        Chunk(
                            text="" if row["Text"] is None else row["Text"],
                            title="" if row["Title"] is None else row["Title"],
                        )
                        for row in rows
                    ],
                    query=query,
                )
                rerank_order = [c[2] for c in chunks]
                rows = [rows[idx] for idx in rerank_order]
                timings[f"Rerank ({reranking_model})"] = perf_counter() - t1
            rows = rows[:limit]
        rows = self._post_process_rows(
            rows,
            columns=columns,
            convert_null=convert_null,
            remove_state_cols=remove_state_cols,
            json_safe=json_safe,
            include_original=include_original,
            float_decimals=float_decimals,
            vec_decimals=vec_decimals,
        )
        timings["Total"] = perf_counter() - t0
        timings = {k: f"{v:,.3f}" for k, v in timings.items()}
        logger.info(f"Hybrid search timings: {timings}")
        return rows

    def scalar_cols(self, meta: TableMeta) -> list[ColumnSchema]:
        return [c for c in meta.cols_schema if c.id.lower() in ("id", "updated at")]

    def embedding_cols(self, meta: TableMeta) -> list[ColumnSchema]:
        return [c for c in meta.cols_schema if c.vlen > 0]

    def fts_cols(self, meta: TableMeta) -> list[ColumnSchema]:
        return [c for c in meta.cols_schema if c.dtype == ColumnDtype.STR and c.id.lower() != "id"]

    def create_fts_index(
        self,
        session: Session,
        table_id: TableName,
        *,
        force: bool = False,
    ) -> bool:
        table, meta = self.open_table_meta(session, table_id)
        fts_cols = [c.id for c in self.fts_cols(meta)]
        # Maybe can skip reindexing
        if (
            (not force)
            and meta.indexed_at_fts is not None
            and meta.indexed_at_fts > meta.updated_at
        ):
            return False
        num_rows = table.count_rows()
        if num_rows == 0:
            return False
        if len(fts_cols) == 0:
            return False
        index_datetime = datetime_now_iso()
        table.create_fts_index(fts_cols, replace=True)
        # Update metadata
        meta.indexed_at_fts = index_datetime
        session.add(meta)
        session.commit()
        return True

    def create_scalar_index(
        self,
        session: Session,
        table_id: TableName,
        *,
        force: bool = False,
    ) -> bool:
        table, meta = self.open_table_meta(session, table_id)
        # Maybe can skip reindexing
        if (
            (not force)
            and meta.indexed_at_sca is not None
            and meta.indexed_at_sca > meta.updated_at
        ):
            return False
        num_rows = table.count_rows()
        if num_rows == 0:
            return False
        index_datetime = datetime_now_iso()
        for c in self.scalar_cols(meta):
            table.create_scalar_index(c.id, replace=True)
        # Update metadata
        meta.indexed_at_sca = index_datetime
        session.add(meta)
        session.commit()
        return True

    def create_vector_index(
        self,
        session: Session,
        table_id: TableName,
        force: bool = False,
        *,
        metric: str = "cosine",
        num_partitions: int | None = None,
        num_sub_vectors: int | None = None,
        accelerator: str | None = None,
        index_cache_size: int | None = None,
    ) -> bool:
        """
        Creates a vector IVF-PQ index for each vector column. Existing indexes will be replaced.
        This is a no-op if number of rows is less than 1,000.

        Args:
            session (Session): SQLAlchemy session.
            table_id (TableName): Table ID.
            force (bool, optional): If True, force reindex. Defaults to False.
            metric (str, optional): The distance metric type.
                "L2" (alias to "euclidean"), "cosine" or "dot" (dot product). Defaults to "dot".
            num_partitions (int, optional): The number of IVF partitions to create.
                By default the number of partitions is the square root of the number of rows.
                for example the square root of the number of rows. Defaults to None.
            num_sub_vectors (int, optional): Number of sub-vectors of PQ.
                This value controls how much the vector is compressed during the quantization step.
                The more sub vectors there are the less the vector is compressed.
                The default is the dimension of the vector divided by 16.
                If the dimension is not evenly divisible by 16 we use the dimension divided by 8.
                The above two cases are highly preferred.
                Having 8 or 16 values per subvector allows us to use efficient SIMD instructions.
                If the dimension is not visible by 8 then we use 1 subvector.
                This is not ideal and will likely result in poor performance.
                Defaults to None.
            accelerator (str | None, optional): str or `torch.Device`, optional.
                If set, use an accelerator to speed up the index training process.
                Accepted accelerator: "cuda" (Nvidia GPU) and "mps" (Apple Silicon GPU).
                If not set, use the CPU. Defaults to None.
            index_cache_size (int | None, optional): The size of the index cache in number of entries. Defaults to None.
            index_cache_size (int | None, optional): The size of the index cache in number of entries. Defaults to None.

        Returns:
            reindexed (bool): Whether the reindex operation is performed.
        """
        table, meta = self.open_table_meta(session, table_id)
        # Maybe can skip reindexing
        if (
            (not force)
            and meta.indexed_at_vec is not None
            and meta.indexed_at_vec > meta.updated_at
        ):
            return False
        num_rows = table.count_rows()
        if num_rows < 10_000:
            return False
        index_datetime = datetime_now_iso()
        num_partitions = num_partitions or max(1, int(np.sqrt(num_rows)))
        for c in self.embedding_cols(meta):
            if num_sub_vectors is None:
                if c.vlen % 16 == 0:
                    num_sub_vectors = c.vlen // 16
                elif c.vlen % 8 == 0:
                    num_sub_vectors = c.vlen // 8
                else:
                    num_sub_vectors = 1
            table.create_index(
                vector_column_name=c.id,
                replace=True,
                metric=metric,
                num_partitions=num_partitions,
                num_sub_vectors=num_sub_vectors,
                accelerator=accelerator,
                index_cache_size=index_cache_size,
            )
        # Update metadata
        meta.indexed_at_vec = index_datetime
        session.add(meta)
        session.commit()
        return True

    def create_indexes(
        self,
        session: Session,
        table_id: TableName,
        *,
        force: bool = False,
    ) -> bool:
        """Creates scalar, vector, FTS indexes.

        Args:
            session (Session): SQLAlchemy session.
            table_id (TableName): Table ID.
            force (bool, optional): If True, force reindex. Defaults to False.

        Returns:
            index_ok (bool): Whether at least one reindexing operation is performed.
        """
        t0 = perf_counter()
        sca_reindexed = self.create_scalar_index(session, table_id, force=force)
        t1 = perf_counter()
        fts_reindexed = self.create_fts_index(session, table_id, force=force)
        t2 = perf_counter()
        vec_reindexed = self.create_vector_index(session, table_id, force=force)
        t3 = perf_counter()
        timings = []
        if sca_reindexed:
            timings.append(f"scalar={t1-t0:,.2f} s")
        if fts_reindexed:
            timings.append(f"FTS={t2-t1:,.2f} s")
        if vec_reindexed:
            timings.append(f"vector={t3-t2:,.2f} s")
        if len(timings) > 0:
            timings = ", ".join(timings)
            num_rows = self.open_table(table_id).count_rows()
            logger.info(
                (
                    f'Index creation for table "{table_id}" with {num_rows:,d} rows took {t3-t0:,.2f} s '
                    f"({timings})."
                )
            )
        return len(timings) > 0

    def compact_files(self, table_id: TableName, *args, **kwargs) -> bool:
        with self.lock(table_id):
            table = self.open_table(table_id)
            num_rows = table.count_rows()
            if num_rows < 10:
                return False
            table.compact_files(*args, **kwargs)
        return True

    def cleanup_old_versions(
        self,
        table_id: TableName,
        older_than: timedelta | None = None,
        delete_unverified: bool = False,
    ) -> bool:
        with self.lock(table_id):
            table = self.open_table(table_id)
            num_rows = table.count_rows()
            if num_rows < 3:
                return False
            table.cleanup_old_versions(older_than=older_than, delete_unverified=delete_unverified)
        return True

    def update_title(self, session: Session, table_id: TableName, title: str):
        meta = self.open_meta(session, table_id)
        meta.title = title
        session.add(meta)
        session.commit()


class ActionTable(GenerativeTable):
    pass


class KnowledgeTable(GenerativeTable):
    FIXED_COLUMN_IDS = ["Title", "Title Embed", "Text", "Text Embed", "File ID", "Page"]

    @override
    def create_table(
        self,
        session: Session,
        schema: KnowledgeTableSchemaCreate,
        model_list: ModelListConfig,
        remove_state_cols: bool = False,
        add_info_state_cols: bool = True,
    ) -> tuple[LanceTable, TableMeta]:
        if not isinstance(schema, KnowledgeTableSchemaCreate):
            raise TypeError("`schema` must be an instance of `KnowledgeTableSchemaCreate`.")
        schema = TableSchema(
            id=schema.id,
            cols=[
                ColumnSchema(id="Title", dtype=ColumnDtype.STR),
                ColumnSchema(
                    id="Title Embed",
                    # TODO: Benchmark this
                    # float32 index creation is 2x faster than float16
                    # float32 vector search is 10% to 50% faster than float16
                    # 2024-05-21, lance 0.6.13, pylance 0.10.12
                    # https://github.com/lancedb/lancedb/issues/1312
                    dtype=ColumnDtype.FLOAT32,
                    vlen=model_list.get_embed_model_info(schema.embedding_model).embedding_size,
                    gen_config=EmbedGenConfig(
                        embedding_model=schema.embedding_model,
                        source_column="Title",
                    ),
                ),
                ColumnSchema(id="Text", dtype=ColumnDtype.STR),
                ColumnSchema(
                    id="Text Embed",
                    dtype=ColumnDtype.FLOAT32,
                    vlen=model_list.get_embed_model_info(schema.embedding_model).embedding_size,
                    gen_config=EmbedGenConfig(
                        embedding_model=schema.embedding_model,
                        source_column="Text",
                    ),
                ),
                ColumnSchema(id="File ID", dtype=ColumnDtype.STR),
                ColumnSchema(id="Page", dtype=ColumnDtype.INT),
            ]
            + schema.cols,
        )
        return super().create_table(session, schema, remove_state_cols, add_info_state_cols)

    @override
    def update_gen_config(
        self,
        session: Session,
        updates: GenConfigUpdateRequest,
    ) -> TableMeta:
        with self.create_session() as session:
            table, meta = self.open_table_meta(session, updates.table_id)
        num_rows = table.count_rows()
        id2col = {c["id"]: c for c in meta.cols}
        for col_id in updates.column_map:
            if num_rows > 0 and id2col[col_id]["vlen"] > 0:
                raise TableSchemaFixedError(
                    "Knowledge Table contains data, cannot update embedding config."
                )
        return super().update_gen_config(session, updates)

    @override
    def add_columns(
        self,
        session: Session,
        schema: AddKnowledgeColumnSchema,
    ) -> tuple[LanceTable, TableMeta]:
        """
        Adds one or more input or output column.

        Args:
            session (Session): SQLAlchemy session.
            schema (AddKnowledgeColumnSchema): Schema of the columns to be added.

        Raises:
            ResourceNotFoundError: If the table is not found.
            ValueError: If any of the columns exists.

        Returns:
            table (LanceTable): Lance table.
            meta (TableMeta): Table metadata.
        """
        if not isinstance(schema, AddKnowledgeColumnSchema):
            raise TypeError("`schema` must be an instance of `AddKnowledgeColumnSchema`.")
        # if self.open_table(schema.id).count_rows() > 0:
        #     raise TableSchemaFixedError("Knowledge Table contains data, cannot add columns.")
        return super().add_columns(session, schema)


class ChatTable(GenerativeTable):
    FIXED_COLUMN_IDS = ["User"]

    @override
    def create_table(
        self,
        session: Session,
        schema: ChatTableSchemaCreate,
        remove_state_cols: bool = False,
        add_info_state_cols: bool = True,
    ) -> tuple[LanceTable, TableMeta]:
        if not isinstance(schema, ChatTableSchemaCreate):
            raise TypeError("`schema` must be an instance of `ChatTableSchemaCreate`.")
        num_chat_cols = len([c for c in schema.cols if c.gen_config and c.gen_config.multi_turn])
        if num_chat_cols == 0:
            raise BadInputError("The table must have at least one multi-turn column.")
        return super().create_table(session, schema, remove_state_cols, add_info_state_cols)

    @override
    def add_columns(
        self,
        session: Session,
        schema: AddChatColumnSchema,
    ) -> tuple[LanceTable, TableMeta]:
        """
        Adds one or more input or output column.

        Args:
            session (Session): SQLAlchemy session.
            schema (AddChatColumnSchema): Schema of the columns to be added.

        Raises:
            ResourceNotFoundError: If the table is not found.
            ValueError: If any of the columns exists.

        Returns:
            table (LanceTable): Lance table.
            meta (TableMeta): Table metadata.
        """
        if not isinstance(schema, AddChatColumnSchema):
            raise TypeError("`schema` must be an instance of `AddChatColumnSchema`.")
        with self.create_session() as session:
            meta = self.open_meta(session, schema.id)
        if meta.parent_id is not None:
            raise TableSchemaFixedError("Unable to add columns to a conversation table.")
        return super().add_columns(session, schema)

    @override
    def drop_columns(
        self,
        session: Session,
        table_id: TableName,
        column_names: list[ColName],
    ) -> tuple[LanceTable, TableMeta]:
        """
        Drops one or more input or output column.

        Args:
            session (Session): SQLAlchemy session.
            table_id (str): The ID of the table.
            column_names (list[str]): List of column ID to drop.

        Raises:
            TypeError: If `column_names` is not a list.
            ResourceNotFoundError: If the table is not found.
            ResourceNotFoundError: If any of the columns is not found.

        Returns:
            table (LanceTable): Lance table.
            meta (TableMeta): Table metadata.
        """
        with self.create_session() as session:
            meta = self.open_meta(session, table_id)
        if meta.parent_id is not None:
            raise TableSchemaFixedError("Unable to drop columns from a conversation table.")
        num_chat_cols = len(
            [
                c
                for c in meta.cols_schema
                if c.id not in column_names and c.gen_config and c.gen_config.multi_turn
            ]
        )
        if num_chat_cols == 0:
            raise BadInputError("The table must have at least one multi-turn column.")
        return super().drop_columns(session, table_id, column_names)

    @override
    def rename_columns(
        self,
        session: Session,
        table_id: TableName,
        column_map: dict[ColName, ColName],
    ) -> TableMeta:
        with self.create_session() as session:
            meta = self.open_meta(session, table_id)
        if meta.parent_id is not None:
            raise TableSchemaFixedError("Unable to rename columns of a conversation table.")
        return super().rename_columns(session, table_id, column_map)
