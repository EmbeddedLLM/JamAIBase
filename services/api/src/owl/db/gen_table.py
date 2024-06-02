import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from shutil import copytree, move
from time import perf_counter, sleep
from typing import Any, Type

import lancedb
import numpy as np
import pyarrow as pa
from filelock import FileLock
from lancedb.table import LanceTable
from loguru import logger
from sqlalchemy import desc
from sqlmodel import Session, SQLModel, select
from typing_extensions import Self
from uuid_extensions import uuid7str

from jamaibase import protocol as p
from jamaibase.utils.io import json_loads
from owl.config import get_embed_model_info
from owl.db import create_sql_tables, create_sqlite_engine
from owl.models import CloudEmbedder, CloudReranker
from owl.utils import get_api_key
from owl.utils.exceptions import ResourceExistsError, ResourceNotFoundError, TableSchemaFixedError

# Lance only support null values in string column
_py_type_default = {
    "int": 0,
    "int8": 0,
    "float": 0.0,
    "float32": 0.0,
    "float16": 0.0,
    "bool": False,
    "str": "''",
}


class GenerativeTable:
    model_class: Type[SQLModel] = p.TableSQLModel
    """
    Smart Table class.

    Note that by default, this class assumes that each method uses a new LanceDB connection.
    Otherwise, consider passing in `read_consistency_interval=timedelta(seconds=0)` during init.
    """

    def __init__(
        self,
        db_url: str,
        vector_db_url: str,
        read_consistency_interval: timedelta | None = None,
        create_sqlite_tables: bool = True,
    ) -> None:
        self.lance_db = lancedb.connect(
            vector_db_url, read_consistency_interval=read_consistency_interval
        )
        self.sqlite_engine = create_sqlite_engine(db_url)
        # Thread and process safe lock
        self.lock_name_prefix = vector_db_url
        self.locks = {}
        self.read_consistency_interval = read_consistency_interval
        if create_sqlite_tables:
            create_sql_tables(p.TableSQLModel, self.sqlite_engine)
        self.db_url = Path(db_url)
        self.vector_db_url = Path(vector_db_url)

    def lock(self, name: str, timeout: int = 5):
        name = f"{self.lock_name_prefix}/{name}.lock"
        self.locks[name] = self.locks.get(name, FileLock(name, timeout=timeout))
        return self.locks[name]

    def create_session(self):
        return Session(self.sqlite_engine)

    def has_info_col_names(self, names: list[str]) -> bool:
        return sum(n.lower() in ("id", "updated at") for n in names) > 0

    def has_state_col_names(self, names: list[str]) -> bool:
        return any(n.endswith("_") for n in names)

    def num_output_columns(self, meta: p.TableMeta) -> int:
        return len(
            [col for col in meta.cols if col["gen_config"] is not None and col["vlen"] == 0]
        )

    def _create_table(
        self,
        session: Session,
        schema: p.TableSchemaCreate,
        remove_state_cols: bool = False,
        add_info_state_cols: bool = True,
    ) -> tuple[LanceTable, p.TableMeta]:
        table_id = schema.id
        meta = session.get(p.TableMeta, table_id)
        if meta is None:
            # Add metadata
            if add_info_state_cols:
                schema = schema.add_info_cols().add_state_cols()
            meta = p.TableMeta(
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
            raise ResourceExistsError(f"Table '{table_id}' already exists.")
        if remove_state_cols:
            meta.cols = [c for c in meta.cols if not c["id"].endswith("_")]
        return table, meta

    def create_table(
        self,
        session: Session,
        schema: p.TableSchemaCreate,
        remove_state_cols: bool = False,
        add_info_state_cols: bool = True,
    ) -> tuple[LanceTable, p.TableMeta]:
        if not isinstance(schema, p.TableSchema):
            raise TypeError("`schema` must be an instance of `p.TableSchema`.")
        return self._create_table(
            session=session,
            schema=schema,
            remove_state_cols=remove_state_cols,
            add_info_state_cols=add_info_state_cols,
        )

    def open_table(self, table_id: p.TableName) -> LanceTable:
        try:
            table = self.lance_db.open_table(table_id)
        except FileNotFoundError:
            raise ResourceNotFoundError(f"Table '{table_id}' cannot be found.")
        return table

    def open_meta(
        self,
        session: Session,
        table_id: p.TableName,
        remove_state_cols: bool = False,
    ) -> p.TableMeta:
        meta = session.get(p.TableMeta, table_id)
        if meta is None:
            raise ResourceNotFoundError(f"Table '{table_id}' cannot be found.")
        if remove_state_cols:
            meta.cols = [c for c in meta.cols if not c["id"].endswith("_")]
        return meta

    def open_table_meta(
        self,
        session: Session,
        table_id: p.TableName,
        remove_state_cols: bool = False,
    ) -> tuple[LanceTable, p.TableMeta]:
        meta = self.open_meta(session, table_id, remove_state_cols=remove_state_cols)
        table = self.open_table(table_id)
        return table, meta

    def _list_meta_selection(self, parent_id: str | None = None):
        del parent_id
        return select(p.TableMeta)

    def list_meta(
        self,
        session: Session,
        offset: int,
        limit: int,
        remove_state_cols: bool = False,
        parent_id: str | None = None,
    ) -> tuple[list[p.TableMetaResponse], int]:
        selection = self._list_meta_selection(parent_id)
        # # Validate
        # metas = []
        # for meta in session.exec(selection.order_by(desc(p.TableMeta.updated_at))).all():
        #     try:
        #         self.open_table(meta.id)
        #     except ResourceNotFoundError:
        #         logger.warning(f"Lance table missing: {meta.id}")
        #         session.delete(meta)
        #     else:
        #         metas.append(deepcopy(meta))
        # session.commit()
        # meta_responses = []
        # for meta in metas[offset : offset + limit]:
        #     num_rows = self.count_rows(meta.id)
        #     meta_responses.append(
        #         p.TableMetaResponse.model_validate(meta, update={"num_rows": num_rows})
        #     )
        total = len(session.exec(selection).all())
        metas = session.exec(
            selection.order_by(desc(p.TableMeta.updated_at)).offset(offset).limit(limit)
        ).all()
        meta_responses = []
        for meta in metas:
            num_rows = self.count_rows(meta.id)
            meta_responses.append(
                p.TableMetaResponse.model_validate(meta, update={"num_rows": num_rows})
            )
        if remove_state_cols:
            for meta in meta_responses:
                meta.cols = [c for c in meta.cols if not c.id.endswith("_")]
        return meta_responses, total

    def count_rows(self, table_id: p.TableName, filter: str | None = None) -> int:
        return self.open_table(table_id).count_rows(filter)

    def duplicate_table(
        self,
        session: Session,
        table_id_src: p.TableName,
        table_id_dst: p.TableName,
        include_data: bool = True,
        deploy: bool = False,
    ) -> p.TableMeta:
        dst_meta = session.get(p.TableMeta, table_id_dst)
        if dst_meta is not None:
            raise ResourceExistsError(f"Table '{table_id_dst}' already exists.")
        # Duplicate metadata
        with self.lock(table_id_src):
            meta = self.open_meta(session, table_id_src)
            new_meta = p.TableMeta.model_validate(
                meta, update={"id": table_id_dst, "parent_id": table_id_src if deploy else None}
            )
            session.add(new_meta)
            session.commit()
            session.refresh(new_meta)
            # Duplicate LanceTable
            if include_data:
                copytree(
                    self.vector_db_url / f"{table_id_src}.lance",
                    self.vector_db_url / f"{table_id_dst}.lance",
                )
            else:
                schema = p.TableSchema.model_validate(new_meta)
                self.lance_db.create_table(table_id_dst, schema=schema.pyarrow)
        return new_meta

    def rename_table(
        self,
        session: Session,
        table_id_src: p.TableName,
        table_id_dst: p.TableName,
    ) -> p.TableMeta:
        # Check
        dst_meta = session.get(p.TableMeta, table_id_dst)
        if dst_meta is not None:
            raise ResourceExistsError(f"Table '{table_id_dst}' already exists.")
        # Rename metadata
        with self.lock(table_id_src):
            meta = self.open_meta(session, table_id_src)
            meta.id = table_id_dst
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(meta)
            session.commit()
            session.refresh(meta)
            # Rename LanceTable
            # self.lance_db.rename_table(table_id_src, table_id_dst)
            move(
                self.vector_db_url / f"{table_id_src}.lance",
                self.vector_db_url / f"{table_id_dst}.lance",
            )
        return meta

    def delete_table(self, session: Session, table_id: p.TableName) -> None:
        with self.lock(table_id):
            # Delete metadata
            meta = session.get(p.TableMeta, table_id)
            if meta is not None:
                session.delete(meta)
                session.commit()
            # Delete LanceTable
            delete_ok = False
            while not delete_ok:
                try:
                    self.lance_db.drop_table(table_id, ignore_missing=True)
                except OSError:
                    # There might be ongoing operations
                    sleep(1)
                else:
                    delete_ok = True
            # try:
            #     rmtree(self.vector_db_url / f"{table_id}.lance")
            # except FileNotFoundError:
            #     pass
        return

    def update_gen_config(
        self, session: Session, updates: p.GenConfigUpdateRequest
    ) -> p.TableMeta:
        table_id = updates.table_id
        meta = session.get(p.TableMeta, table_id)
        meta_col_ids = set(c.id for c in meta.cols_schema)
        update_col_ids = set(updates.column_map.keys())
        if len(update_col_ids - meta_col_ids) > 0:
            raise ValueError(
                f"Some columns are not found in the table: {update_col_ids - meta_col_ids}"
            )
        cols = deepcopy(meta.cols)
        for c in cols:
            c["gen_config"] = updates.column_map.get(c["id"], c["gen_config"])
        meta.cols = cols
        p.TableSchema.model_validate(meta)
        session.add(meta)
        session.commit()
        session.refresh(meta)
        return meta

    def add_columns(
        self, session: Session, schema: p.AddColumnSchema
    ) -> tuple[LanceTable, p.TableMeta]:
        """
        Adds one or more input or output column.

        Args:
            session (Session): SQLAlchemy session.
            schema (AddColumnSchema): Schema of the columns to be added.

        Raises:
            ResourceNotFoundError: If the table is not found.
            ValueError: If any of the columns exists.

        Returns:
            table (LanceTable): Lance table.
            meta (TableMeta): Table metadata.
        """
        if not isinstance(schema, p.TableSchema):
            raise TypeError("`schema` must be an instance of `p.TableSchema`.")
        table_id = schema.id
        # Check
        meta = self.open_meta(session, table_id)
        schema = schema.add_state_cols()
        cols = meta.cols_schema + schema.cols
        if len(set(c.id for c in cols)) != len(cols):
            raise ValueError("Schema and table contain overlapping column names.")
        meta.cols = [c.model_dump() for c in cols]
        p.TableSchema.model_validate(meta)

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
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(meta)
            session.commit()
            session.refresh(meta)
        return table, meta

    def _drop_columns(
        self, session: Session, table_id: p.TableName, col_names: list[p.Name]
    ) -> tuple[LanceTable, p.TableMeta]:
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
            raise ValueError("Cannot drop state columns.")
        if self.has_info_col_names(col_names):
            raise ValueError("Cannot drop 'ID' or 'Updated at'.")
        with self.lock(table_id):
            meta = self.open_meta(session, table_id)
            col_names += [f"{n}_" for n in col_names]
            table = self.open_table(table_id)
            try:
                table.drop_columns(col_names)
            except ValueError as e:
                raise ResourceNotFoundError(e)
            meta.cols = [c.model_dump() for c in meta.cols_schema if c.id not in col_names]
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(meta)
            session.commit()
            session.refresh(meta)
        return table, meta

    def drop_columns(
        self, session: Session, table_id: p.TableName, col_names: list[p.Name]
    ) -> tuple[LanceTable, p.TableMeta]:
        """
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
            raise ValueError("Cannot drop state columns.")
        if self.has_info_col_names(col_names):
            raise ValueError("Cannot drop 'ID' or 'Updated at'.")

        with self.lock(table_id):
            # Get table metadata
            meta = self.open_meta(session, table_id)
            # Create new table with dropped columns
            new_table_id = f"{table_id}_dropped_{uuid7str()}"
            col_names += [f"{col_name}_" for col_name in col_names]
            new_schema = p.TableSchema(
                id=new_table_id,
                cols=[c for c in meta.cols_schema if c.id not in col_names],
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
        self, session: Session, table_id: p.TableName, name_map: dict[p.Name, p.Name]
    ) -> p.TableMeta:
        if self.has_state_col_names(name_map.keys()):
            raise ValueError("Cannot rename state columns.")
        if self.has_info_col_names(name_map.keys()):
            raise ValueError("Cannot rename 'ID' or 'Updated at'.")
        if not all(re.match(p.NAME_PATTERN, v) for v in name_map.values()):
            raise ValueError("`name_map` contains invalid new column names.")
        meta = self.open_meta(session, table_id)
        table = self.open_table(table_id)
        col_names = set(table.schema.names)
        not_found = set(name_map.keys()) - col_names
        if len(not_found) > 0:
            raise ResourceNotFoundError(f"Some columns are not found: {list(not_found)}.")
        # Add state columns
        for k in list(name_map.keys()):
            name_map[f"{k}_"] = f"{name_map[k]}_"
        # Modify metadata
        cols = []
        for col in meta.cols:
            col = deepcopy(col)
            _id = col["id"]
            col["id"] = name_map.get(_id, _id)
            if col["gen_config"] is not None and col["vlen"] == 0:
                for message in col["gen_config"]["messages"]:
                    message["content"] = re.sub(
                        p.GEN_CONFIG_VAR_PATTERN,
                        lambda m: f"${{{name_map.get(m.group(1), m.group(1))}}}",
                        message["content"],
                    )
            cols.append(col)
        with self.lock(table_id):
            meta.cols = cols
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(meta)
            session.commit()
            session.refresh(meta)
            # Modify LanceTable
            alterations = [{"path": k, "name": v} for k, v in name_map.items()]
            table.alter_columns(*alterations)
        return meta

    def reorder_columns(
        self, session: Session, table_id: p.TableName, columns: list[p.Name]
    ) -> p.TableMeta:
        if self.has_state_col_names(columns):
            raise ValueError("Cannot reorder state columns.")
        if self.has_info_col_names(columns):
            raise ValueError("Cannot reorder 'ID' or 'Updated at'.")
        order = ["ID", "Updated at"]
        for c in columns:
            order += [c, f"{c}_"]
        meta = self.open_meta(session, table_id)
        try:
            meta.cols = [
                c.model_dump() for c in sorted(meta.cols_schema, key=lambda x: order.index(x.id))
            ]
        except ValueError as e:
            raise ResourceNotFoundError(e)
        meta.updated_at = datetime.now(timezone.utc).isoformat()
        session.add(meta)
        session.commit()
        session.refresh(meta)
        return meta

    def add_rows(
        self, session: Session, table_id: p.TableName, data: list[dict[p.Name, Any]]
    ) -> Self:
        if not isinstance(data, list):
            raise TypeError("`data` must be a list.")
        with self.lock(table_id):
            table = self.open_table(table_id)
            meta = self.open_meta(session, table_id)
            # Validate data and generate ID & timestamp under write lock
            data = p.RowAddData(table_meta=meta, data=data).set_id().data
            # Add to Lance Table
            table.add(data)
            # Update metadata
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(meta)
            session.commit()
        return self

    def update_rows(
        self,
        session: Session,
        table_id: p.TableName,
        where: str | None = None,
        *,
        values: dict | None = None,
    ) -> Self:
        with self.lock(table_id):
            table = self.open_table(table_id)
            meta = self.open_meta(session, table_id)
            # Validate data and generate ID & timestamp under write lock
            values = p.RowUpdateData(table_meta=meta, data=[values]).sql_escape().data[0]
            # TODO: Vector column update seems to be broken
            values = {k: v for k, v in values.items() if not isinstance(v, np.ndarray)}
            table.update(where=where, values=values)
            # Update metadata
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(meta)
            session.commit()
        return self

    def _filter_col(
        self,
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
    ):
        state_id = f"{col_id}_"
        data = row[col_id]
        if state_id not in row:
            # Some columns like "ID", "Updated at" do not have state cols
            return data
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
            return ret
        else:
            return data

    def _post_process_rows(
        self,
        rows: list[dict[str, Any]],
        columns: list[str] | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        include_original: bool = False,
    ):
        if json_safe:
            rows = [
                {k: v.isoformat() if isinstance(v, datetime) else v for k, v in row.items()}
                for row in rows
            ]
        rows = [
            {k: self._process_cell(row, k, convert_null, include_original) for k in row}
            for row in rows
        ]
        rows = [
            {
                k: v
                for k, v in row.items()
                if self._filter_col(k, columns=columns, remove_state_cols=remove_state_cols)
            }
            for row in rows
        ]
        return rows

    def get_row(
        self,
        table_id: p.TableName,
        row_id: str,
        columns: list[str] | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        include_original: bool = False,
    ) -> dict[str, Any]:
        table = self.open_table(table_id)
        rows = table.search().where(where=f"`ID` = '{row_id}'", prefilter=True).to_list()
        if len(rows) == 0:
            raise ResourceNotFoundError("Row with the specified ID cannot be found.")
        elif len(rows) > 1:
            logger.warning(f"More than one row in table {table_id} with ID {row_id}")
        rows = self._post_process_rows(
            rows,
            columns=columns,
            convert_null=convert_null,
            remove_state_cols=remove_state_cols,
            json_safe=json_safe,
            include_original=include_original,
        )
        return rows[0]

    def list_rows(
        self,
        table_id: p.TableName,
        *,
        offset: int = 0,
        limit: int = 1_000,
        columns: list[p.Name] | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        sort_descending: bool = True,
        include_original: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        table = self.open_table(table_id)
        total = self.count_rows(table_id)
        offset, limit = max(0, offset), max(1, limit)
        if offset >= total:
            rows = []
        else:
            if offset + limit > total:
                limit = total - offset
            if sort_descending:
                offset = max(0, total - limit - offset)
            rows = table._dataset.to_table(offset=offset, limit=limit).to_pylist()
            rows = sorted(rows, reverse=sort_descending, key=lambda r: r["ID"])
            rows = self._post_process_rows(
                rows,
                columns=columns,
                convert_null=convert_null,
                remove_state_cols=remove_state_cols,
                json_safe=json_safe,
                include_original=include_original,
            )
        return rows, total

    def delete_row(self, session: Session, table_id: p.TableName, row_id: str) -> Self:
        with self.lock(table_id):
            table = self.open_table(table_id)
            table.delete(f"`ID` = '{row_id}'")
            # Update metadata
            meta = self.open_meta(session, table_id)
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(meta)
            session.commit()
        return self

    def delete_rows(self, session: Session, table_id: p.TableName, where: str) -> Self:
        with self.lock(table_id):
            table = self.open_table(table_id)
            table.delete(where)
            # Update metadata
            meta = self.open_meta(session, table_id)
            meta.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(meta)
            session.commit()
        return self

    @staticmethod
    def _run_query(
        table: LanceTable,
        query: np.ndarray | list | str | None = None,
        column_name: str | None = None,
        where: str | None = None,
        limit: p.PositiveInt = 10_000,
        metric: str = "dot",
        nprobes: p.PositiveInt = 50,
        refine_factor: p.PositiveInt = 50,
    ) -> list[dict[str, Any]]:
        is_vector = isinstance(query, (list, np.ndarray))
        if query is None:
            column_name = None
            query_type = "auto"
        elif is_vector:
            query_type = "vector"
        elif isinstance(query, str):
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
        return query_builder.limit(limit).to_list()

    @staticmethod
    def _merge_sub_rows(rows: dict, sub_rows: list[dict], score_key: str, merge_op):
        for r in sub_rows:
            _id = r["ID"]
            if _id in rows:
                if score_key in rows[_id]:
                    r[score_key] = merge_op(r[score_key], rows[_id][score_key])
                rows[_id].update(r)
            else:
                rows[_id] = r
        return rows

    def hybrid_search(
        self,
        session: Session,
        table_id: p.TableName,
        query: str | None,
        *,
        where: str | None = None,
        limit: p.PositiveInt = 100,
        columns: list[p.Name] | None = None,
        metric: str = "dot",
        nprobes: p.PositiveInt = 50,
        refine_factor: p.PositiveInt = 50,
        reranking_model: str | None = None,
        convert_null: bool = True,
        remove_state_cols: bool = False,
        json_safe: bool = False,
        include_original: bool = False,
        openai_api_key: str = "",
        anthropic_api_key: str = "",
        gemini_api_key: str = "",
        cohere_api_key: str = "",
        groq_api_key: str = "",
        together_api_key: str = "",
        jina_api_key: str = "",
        voyage_api_key: str = "",
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
                table=table,
                query=None,
                column_name=None,
                where=where,
                limit=limit,
            )
            timings["No query search"] = perf_counter() - t1
        else:
            if not isinstance(query, str):
                raise TypeError(f"`query` must be string, received: {type(query)}")
            rows = {}
            for c in self.fts_cols(meta):
                t1 = perf_counter()
                sub_rows = self._run_query(
                    table=table,
                    query=re.sub(r"[^\w\s]", "", query).replace("\n", " "),
                    column_name=c.id,
                    where=where,
                    limit=limit,
                    metric=metric,
                    nprobes=nprobes,
                    refine_factor=refine_factor,
                )
                rows = self._merge_sub_rows(rows, sub_rows, "score", max)
                timings[f"FTS: {c.id}"] = perf_counter() - t1
            for c in self.embedding_cols(meta):
                t1 = perf_counter()
                gen_config = p.EmbedGenConfig.model_validate(c.gen_config)
                api_key = get_api_key(
                    gen_config.embedding_model,
                    openai_api_key=openai_api_key,
                    anthropic_api_key=anthropic_api_key,
                    gemini_api_key=gemini_api_key,
                    cohere_api_key=cohere_api_key,
                    groq_api_key=groq_api_key,
                    together_api_key=together_api_key,
                    jina_api_key=jina_api_key,
                    voyage_api_key=voyage_api_key,
                )
                embedder = CloudEmbedder(
                    embedder_name=gen_config.embedding_model,
                    api_key=api_key,
                )
                embedding = embedder.embed_documents(texts=[query])
                # TODO: Benchmark this
                # Searching using float16 seems to be faster on float32 and float16 indexes
                # 2024-05-21, lance 0.6.13, pylance 0.10.12
                embedding = np.asarray(embedding[0], dtype=np.float16)
                embedding = embedding / np.linalg.norm(embedding)
                timings[f"Embed ({gen_config.embedding_model}): {c.id}"] = perf_counter() - t1
                t1 = perf_counter()
                sub_rows = self._run_query(
                    table=table,
                    query=embedding,
                    column_name=c.id,
                    where=where,
                    limit=limit,
                    metric=metric,
                    nprobes=nprobes,
                    refine_factor=refine_factor,
                )
                for r in sub_rows:
                    r["vector_score"] = 3.0 - r["_distance"]
                rows = self._merge_sub_rows(rows, sub_rows, "vector_score", max)
                timings[f"VS: {c.id}"] = perf_counter() - t1
            rows = list(rows.values())
            if reranking_model is None:
                for r in rows:
                    r["hybrid_score"] = r.get("score", 0.0) + r.get("vector_score", 0.0)
                rows = list(sorted(rows, key=lambda r: r["hybrid_score"], reverse=True))
                _scores = [
                    (
                        f'(hybrid_score={r["hybrid_score"]:.1f}, '
                        f'fts_score={r.get("score", 0.0):.1f}, '
                        f'vector_score={r.get("vector_score", 0.0):.1f})'
                    )
                    for r in rows
                ]
                logger.info(f"Hybrid search scores: {_scores}")
            else:
                t1 = perf_counter()
                api_key = get_api_key(
                    reranking_model,
                    openai_api_key=openai_api_key,
                    anthropic_api_key=anthropic_api_key,
                    gemini_api_key=gemini_api_key,
                    cohere_api_key=cohere_api_key,
                    groq_api_key=groq_api_key,
                    together_api_key=together_api_key,
                    jina_api_key=jina_api_key,
                    voyage_api_key=voyage_api_key,
                )
                reranker = CloudReranker(
                    reranker_name=reranking_model,
                    api_key=api_key,
                )
                chunks = reranker.rerank_chunks(
                    chunks=[p.Chunk(text=row["Text"], title=row["Title"]) for row in rows],
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
        )
        timings["Total"] = perf_counter() - t0
        timings = {k: f"{v:,.3f}" for k, v in timings.items()}
        logger.info(f"Hybrid search timings: {timings}")
        return rows

    def scalar_cols(self, meta: p.TableMeta) -> list[p.ColumnSchema]:
        return [c for c in meta.cols_schema if c.id.lower() in ("id", "updated at")]

    def embedding_cols(self, meta: p.TableMeta) -> list[p.ColumnSchema]:
        return [c for c in meta.cols_schema if c.vlen > 0]

    def fts_cols(self, meta: p.TableMeta) -> list[p.ColumnSchema]:
        return [
            c for c in meta.cols_schema if c.dtype == p.DtypeEnum.str_ and c.id.lower() != "id"
        ]

    def create_fts_index(self, session: Session, table_id: p.TableName) -> bool:
        meta = self.open_meta(session, table_id)
        if meta.indexed_at_fts is not None and meta.indexed_at_fts > meta.updated_at:
            return False
        table = self.open_table(table_id)
        num_rows = table.count_rows()
        if num_rows == 0:
            return False
        fts_cols = [c.id for c in self.fts_cols(meta)]
        if len(fts_cols) == 0:
            return False
        with self.lock(table_id):
            table.create_fts_index(fts_cols, replace=True)
            # Update metadata
            meta.indexed_at_fts = datetime.now(timezone.utc).isoformat()
            session.add(meta)
            session.commit()
        return True

    def create_scalar_index(self, session: Session, table_id: p.TableName) -> bool:
        meta = self.open_meta(session, table_id)
        if meta.indexed_at_sca is not None and meta.indexed_at_sca > meta.updated_at:
            return False
        table = self.open_table(table_id)
        num_rows = table.count_rows()
        if num_rows == 0:
            return False
        for c in self.scalar_cols(meta):
            with self.lock(table_id):
                table.create_scalar_index(c.id, replace=True)
        # Update metadata
        meta.indexed_at_sca = datetime.now(timezone.utc).isoformat()
        session.add(meta)
        session.commit()
        return True

    def create_vector_index(
        self,
        session: Session,
        table_id: p.TableName,
        metric: str = "dot",
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

        Returns:
            reindexed (bool): Whether the reindex operation is performed.
        """
        meta = self.open_meta(session, table_id)
        if meta.indexed_at_vec is not None and meta.indexed_at_vec > meta.updated_at:
            return False
        table = self.open_table(table_id)
        num_rows = table.count_rows()
        if num_rows < 10_000:
            return False
        num_partitions = num_partitions or max(1, int(np.sqrt(num_rows)))
        for c in self.embedding_cols(meta):
            if num_sub_vectors is None:
                if c.vlen % 16 == 0:
                    num_sub_vectors = c.vlen // 16
                elif c.vlen % 8 == 0:
                    num_sub_vectors = c.vlen // 8
                else:
                    num_sub_vectors = 1
            with self.lock(table_id):
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
        meta.indexed_at_vec = datetime.now(timezone.utc).isoformat()
        session.add(meta)
        session.commit()
        return True

    def create_indexes(self, session: Session, table_id: p.TableName) -> bool:
        t0 = perf_counter()
        sca_reindexed = self.create_scalar_index(session, table_id)
        t1 = perf_counter()
        fts_reindexed = self.create_fts_index(session, table_id)
        t2 = perf_counter()
        vec_reindexed = self.create_vector_index(session, table_id)
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
                    f"Index creation for table '{table_id}' with {num_rows:,d} rows took {t3-t0:,.2f} s "
                    f"({timings})."
                )
            )
        return len(timings) > 0

    def compact_files(self, table_id: p.TableName, *args, **kwargs) -> bool:
        with self.lock(table_id):
            table = self.open_table(table_id)
            num_rows = table.count_rows()
            if num_rows < 10:
                return False
            table.compact_files(*args, **kwargs)
        return True

    def cleanup_old_versions(
        self,
        table_id: p.TableName,
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


class ActionTable(GenerativeTable):
    pass


class KnowledgeTable(GenerativeTable):
    def create_table(
        self,
        session: Session,
        schema: p.KnowledgeTableSchemaCreate,
        remove_state_cols: bool = False,
        add_info_state_cols: bool = True,
    ) -> tuple[LanceTable, p.TableMeta]:
        if not isinstance(schema, p.KnowledgeTableSchemaCreate):
            raise TypeError("`schema` must be an instance of `KnowledgeTableSchemaCreate`.")
        schema = p.TableSchema(
            id=schema.id,
            cols=[
                p.ColumnSchema(id="Title", dtype=p.DtypeEnum.str_),
                p.ColumnSchema(
                    id="Title Embed",
                    # TODO: Benchmark this
                    # float32 index creation is 2x faster than float16
                    # float32 vector search is 10% to 50% faster than float16
                    # 2024-05-21, lance 0.6.13, pylance 0.10.12
                    # https://github.com/lancedb/lancedb/issues/1312
                    dtype=p.DtypeEnum.float32,
                    vlen=get_embed_model_info(schema.embedding_model).embedding_size,
                    gen_config={
                        "embedding_model": schema.embedding_model,
                        "source_column": "Title",
                    },
                ),
                p.ColumnSchema(id="Text", dtype=p.DtypeEnum.str_),
                p.ColumnSchema(
                    id="Text Embed",
                    dtype=p.DtypeEnum.float32,
                    vlen=get_embed_model_info(schema.embedding_model).embedding_size,
                    gen_config={
                        "embedding_model": schema.embedding_model,
                        "source_column": "Text",
                    },
                ),
                p.ColumnSchema(id="File ID", dtype=p.DtypeEnum.str_),
            ]
            + schema.cols,
        )
        return super().create_table(session, schema, remove_state_cols, add_info_state_cols)

    def update_gen_config(
        self, session: Session, updates: p.GenConfigUpdateRequest
    ) -> p.TableMeta:
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

    def add_columns(
        self, session: Session, schema: p.AddKnowledgeColumnSchema
    ) -> tuple[LanceTable, p.TableMeta]:
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
        if not isinstance(schema, p.AddKnowledgeColumnSchema):
            raise TypeError("`schema` must be an instance of `AddKnowledgeColumnSchema`.")
        # if self.open_table(schema.id).count_rows() > 0:
        #     raise TableSchemaFixedError("Knowledge Table contains data, cannot add columns.")
        return super().add_columns(session, schema)

    def drop_columns(
        self, session: Session, table_id: p.TableName, col_names: list[p.Name]
    ) -> tuple[LanceTable, p.TableMeta]:
        """
        Drops one or more input or output column.

        Args:
            session (Session): SQLAlchemy session.
            table_id (str): The ID of the table.
            col_names (list[str]): List of column ID to drop.

        Raises:
            TypeError: If `col_names` is not a list.
            ResourceNotFoundError: If the table is not found.
            ResourceNotFoundError: If any of the columns is not found.

        Returns:
            table (LanceTable): Lance table.
            meta (TableMeta): Table metadata.
        """
        if sum(n.lower() in ("text", "text embed", "title", "title embed") for n in col_names) > 0:
            raise TableSchemaFixedError(
                "Cannot drop 'Text', 'Text Embed', 'Title' or 'Title Embed'."
            )
        # if self.open_table(table_id).count_rows() > 0:
        #     raise TableSchemaFixedError("Knowledge Table contains data, cannot drop columns.")
        return super().drop_columns(session, table_id, col_names)

    def rename_columns(
        self, session: Session, table_id: p.TableName, name_map: dict[p.Name, p.Name]
    ) -> p.TableMeta:
        if sum(n.lower() in ("text", "text embed", "title", "title embed") for n in name_map) > 0:
            raise TableSchemaFixedError(
                "Cannot rename 'Text', 'Text Embed', 'Title' or 'Title Embed'."
            )
        # if self.open_table(table_id).count_rows() > 0:
        #     raise TableSchemaFixedError("Knowledge Table contains data, cannot rename columns.")
        return super().rename_columns(session, table_id, name_map)

    def update_rows(
        self,
        session: Session,
        table_id: p.TableName,
        where: str | None = None,
        *,
        values: dict | None = None,
    ) -> Self:
        # Validate data
        return super().update_rows(
            session=session,
            table_id=table_id,
            where=where,
            values=values,
        )


class ChatTable(GenerativeTable):
    def create_table(
        self,
        session: Session,
        schema: p.ChatTableSchemaCreate,
        remove_state_cols: bool = False,
        add_info_state_cols: bool = True,
    ) -> tuple[LanceTable, p.TableMeta]:
        if not isinstance(schema, p.ChatTableSchemaCreate):
            raise TypeError("`schema` must be an instance of `ChatTableSchemaCreate`.")
        return super().create_table(session, schema, remove_state_cols, add_info_state_cols)

    def update_title(self, session: Session, table_id: p.TableName, title: str):
        meta = self.open_meta(session, table_id)
        meta.title = title
        session.add(meta)
        session.commit()

    def add_columns(
        self, session: Session, schema: p.AddChatColumnSchema
    ) -> tuple[LanceTable, p.TableMeta]:
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
        if not isinstance(schema, p.AddChatColumnSchema):
            raise TypeError("`schema` must be an instance of `p.AddChatColumnSchema`.")
        with self.create_session() as session:
            meta = self.open_meta(session, schema.id)
        if meta.parent_id is not None:
            raise TableSchemaFixedError("Unable to add columns to a conversation table.")
        return super().add_columns(session, schema)

    def drop_columns(
        self, session: Session, table_id: p.TableName, col_names: list[p.Name]
    ) -> tuple[LanceTable, p.TableMeta]:
        """
        Drops one or more input or output column.

        Args:
            session (Session): SQLAlchemy session.
            table_id (str): The ID of the table.
            col_names (list[str]): List of column ID to drop.

        Raises:
            TypeError: If `col_names` is not a list.
            ResourceNotFoundError: If the table is not found.
            ResourceNotFoundError: If any of the columns is not found.

        Returns:
            table (LanceTable): Lance table.
            meta (TableMeta): Table metadata.
        """
        if sum(n.lower() in ("user", "ai") for n in col_names) > 0:
            raise ValueError("Cannot drop 'User' or 'AI'.")
        with self.create_session() as session:
            meta = self.open_meta(session, table_id)
        if meta.parent_id is not None:
            raise TableSchemaFixedError("Unable to drop columns from a conversation table.")
        return super().drop_columns(session, table_id, col_names)

    def update_gen_config(
        self, session: Session, updates: p.GenConfigUpdateRequest
    ) -> p.TableMeta:
        with self.create_session() as session:
            meta = self.open_meta(session, updates.table_id)
        if meta.parent_id is not None:
            raise TableSchemaFixedError(
                "Unable to update generation config of a conversation table."
            )
        return super().update_gen_config(session, updates)

    def rename_columns(
        self, session: Session, table_id: p.TableName, name_map: dict[p.Name, p.Name]
    ) -> p.TableMeta:
        if sum(n.lower() in ("user", "ai") for n in name_map) > 0:
            raise TableSchemaFixedError("Cannot rename 'User' or 'AI'.")
        with self.create_session() as session:
            meta = self.open_meta(session, table_id)
        if meta.parent_id is not None:
            raise TableSchemaFixedError("Unable to rename columns of a conversation table.")
        return super().rename_columns(session, table_id, name_map)

    def _list_meta_selection(self, parent_id: str | None = None):
        if parent_id is None:
            selection = select(p.TableMeta)
        elif parent_id.lower() == "_agent_":
            selection = select(p.TableMeta).where(p.TableMeta.parent_id == None)  # noqa
        elif parent_id.lower() == "_chat_":
            selection = select(p.TableMeta).where(p.TableMeta.parent_id != None)  # noqa
        else:
            selection = select(p.TableMeta).where(p.TableMeta.parent_id == parent_id)
        return selection

    def get_conversation_thread(self, table_id: p.TableName) -> p.ChatThread:
        rows, _ = self.list_rows(
            table_id=table_id,
            offset=0,
            limit=1_000_000,
            columns=None,
            convert_null=True,
            remove_state_cols=True,
            json_safe=True,
            sort_descending=False,
        )
        with self.create_session() as session:
            meta = self.open_meta(session, table_id)
        ai_col = [c for c in meta.cols if c["id"] == "AI"][0]
        gen_config = p.ChatRequest.model_validate(ai_col["gen_config"])

        thread = []
        if gen_config.messages[0].role in (p.ChatRole.SYSTEM.value, p.ChatRole.SYSTEM):
            thread.append(gen_config.messages[0])
        for row in rows:
            if row["User"]:
                thread.append(p.ChatEntry.user(content=row["User"]))
            if row["AI"]:
                thread.append(p.ChatEntry.assistant(content=row["AI"]))
        return p.ChatThread(thread=thread)
