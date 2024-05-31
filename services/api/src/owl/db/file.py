from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from filelock import FileLock
from lancedb.table import LanceTable
from loguru import logger
from typing_extensions import Self
from uuid_extensions import uuid7str

from jamaibase.protocol import Name, TableName


class FileTable:
    """
    File Table class.

    Note that by default, this class assumes that each method uses a new LanceDB connection.
    Otherwise, consider passing in `read_consistency_interval=timedelta(seconds=0)` during init.
    """

    def __init__(
        self,
        vector_db_url: str,
        table_name: TableName,
        read_consistency_interval: timedelta | None = None,
    ) -> None:
        self.lance_db = lancedb.connect(
            vector_db_url, read_consistency_interval=read_consistency_interval
        )
        self.read_consistency_interval = read_consistency_interval
        self.vector_db_url = Path(vector_db_url)
        self.table_name = table_name
        self.lock_name_prefix = vector_db_url
        self.locks = {}
        # Maybe create table
        try:
            self.lance_db.open_table(table_name)
        except FileNotFoundError:
            pa_schema = pa.schema(
                [
                    pa.field("ID", pa.utf8()),
                    pa.field("Updated at", pa.timestamp("us", tz="UTC")),
                    pa.field("File Name", pa.utf8()),
                    pa.field("Content", pa.binary()),
                    pa.field("File Size", pa.int64()),
                    pa.field("BLAKE2b Checksum", pa.utf8()),
                ]
            )
            self.lance_db.create_table(table_name, schema=pa_schema)

    def lock(self, name: str, timeout: int = 60):
        name = f"{self.lock_name_prefix}/{name}.lock"
        self.locks[name] = self.locks.get(name, FileLock(name, timeout=timeout))
        return self.locks[name]

    def open_table(self) -> LanceTable:
        return self.lance_db.open_table(self.table_name)

    def add_file(self, file_name: str, content: bytes, blake2b_checksum: str) -> dict[str, Any]:
        if not isinstance(file_name, str):
            raise TypeError("`file_name` must be str.")
        if not isinstance(content, bytes):
            raise TypeError("`content` must be bytes.")
        table = self.open_table()
        with self.lock(self.table_name):
            # Validate data
            # rows = table.search().where(where=f"`File Name` = '{file_name}'", prefilter=True).to_list()
            # if len(rows) > 0:
            #     raise FileExistsError("File exists, please choose another name.")
            data = [
                {
                    "ID": uuid7str(),
                    "Updated at": datetime.now(timezone.utc),
                    "File Name": file_name,
                    "Content": content,
                    "File Size": len(content),
                    "BLAKE2b Checksum": blake2b_checksum,
                }
            ]
            table.add(data)
        return data[0]

    def rename_file(self, file_id: str, file_name: str) -> Self:
        if not isinstance(file_id, str):
            raise TypeError("`file_id` must be str.")
        if not isinstance(file_name, str):
            raise TypeError("`file_name` must be str.")
        table = self.open_table()
        with self.lock(self.table_name):
            table.update(where=f"`ID` = '{file_id}'", values={"File Name": file_name})
        return self

    def delete_file(self, file_id: str | None = None, file_name: str | None = None) -> Self:
        if file_id == "" or file_name == "":
            raise ValueError("`file_id` or `file_name` cannot be empty string.")
        if file_id is not None and file_name is not None:
            raise ValueError("Cannot specify both `file_id` and `file_name`.")
        table = self.open_table()
        with self.lock(self.table_name):
            if file_id:
                table.delete(f"`ID` = '{file_id}'")
            elif file_name:
                table.delete(f"`File Name` = '{file_name}'")
            else:
                raise ValueError("Must specify either `file_id` or `file_name`.")
        return self

    def get_file(
        self,
        file_id: str | None = None,
        file_name: str | None = None,
        columns: list[str] | None = None,
    ) -> dict[Name, Any]:
        if file_id == "" or file_name == "":
            raise ValueError("`file_id` or `file_name` cannot be empty string.")
        if file_id is not None and file_name is not None:
            raise ValueError("Cannot specify both `file_id` and `file_name`.")
        table = self.open_table()
        if file_id:
            rows = table.search().where(where=f"`ID` = '{file_id}'", prefilter=True).to_list()
        elif file_name:
            rows = (
                table.search()
                .where(where=f"`File Name` = '{file_name}'", prefilter=True)
                .to_list()
            )
        else:
            raise ValueError("Must specify either `file_id` or `file_name`.")
        if len(rows) == 0:
            # logger.info(f"File not found: file_id={file_id}   file_name={file_name}")
            raise FileNotFoundError("File not found.")
        elif len(rows) > 1:
            logger.warning(f"More than one row in table {self.table_name} with ID {file_id}")
        row = rows[0]
        if columns is not None:
            row = {k: v for k, v in row.items() if k in columns}
        return row

    def compact_files(self, *args, **kwargs) -> bool:
        with self.lock(self.table_name):
            table = self.open_table()
            num_rows = table.count_rows()
            if num_rows < 10:
                return False
            table.compact_files(*args, **kwargs)
        return True

    def cleanup_old_versions(
        self,
        older_than: timedelta | None = None,
        delete_unverified: bool = False,
    ) -> bool:
        with self.lock(self.table_name):
            table = self.open_table()
            num_rows = table.count_rows()
            if num_rows < 3:
                return False
            table.cleanup_old_versions(older_than=older_than, delete_unverified=delete_unverified)
        return True
