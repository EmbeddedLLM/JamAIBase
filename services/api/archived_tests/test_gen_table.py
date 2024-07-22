from datetime import datetime, timedelta, timezone
from os import makedirs
from tempfile import TemporaryDirectory

import numpy as np
import pytest
from lancedb.table import LanceTable
from pydantic import ValidationError

from jamaibase.utils.io import json_loads
from owl.db.gen_table import ActionTable, ChatTable, GenerativeTable, KnowledgeTable
from owl.protocol import (
    ChatTableSchemaCreate,
    ColumnSchemaCreate,
    EmbedGenConfig,
    GenConfigUpdateRequest,
    KnowledgeTableSchemaCreate,
    TableSchema,
    TableSchemaCreate,
)
from owl.utils.exceptions import ResourceExistsError, ResourceNotFoundError

TABLE_ID_A = "documents"
TABLE_ID_B = "xx"
TABLE_ID_C = "yy"
TABLE_ID_X = "zz"
BASE_TMP_DIR = "db"
EMBEDDING_MODEL = "openai/text-embedding-3-small-512"
EMBED_LEN = 512
makedirs(BASE_TMP_DIR, exist_ok=True)


def _create_table(db_dir: str):
    table = GenerativeTable(
        f"sqlite:///{db_dir}/test.db",
        f"{db_dir}/test-lance",
        read_consistency_interval=timedelta(seconds=0),
    )
    with table.create_session() as session:
        lance_table, meta = table.create_table(
            session,
            TableSchemaCreate(
                id=f"{TABLE_ID_A}_XX",
                cols=[
                    ColumnSchemaCreate(id="text", dtype="str"),
                ],
            ),
        )
        lance_table, meta = table.create_table(
            session,
            TableSchema(
                id=TABLE_ID_A,
                cols=[
                    ColumnSchemaCreate(id="text", dtype="str"),
                    ColumnSchemaCreate(id="text embed", dtype="float16", vlen=EMBED_LEN),
                ],
            ),
        )
        with pytest.raises(ValidationError):
            table.create_table(
                session,
                TableSchemaCreate(
                    id=f"{TABLE_ID_A}_XY",
                    cols=[
                        ColumnSchemaCreate(id="text", dtype="str"),
                        ColumnSchemaCreate(id="text embed", dtype="float16", vlen=EMBED_LEN),
                    ],
                ),
            )
    return table, lance_table, meta


def test_create_table():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _create_table(tmp_path)
        # Inspect metadata
        assert isinstance(lance_table, LanceTable)
        assert lance_table.count_rows() == 0
        cols = set(c.id for c in meta.cols_schema)
        assert "ID" in cols
        assert "Updated at" in cols
        assert "text" in cols
        assert "text_" in cols  # State column
        assert "text embed" in cols
        assert "text embed_" in cols  # State column
        regular_cols = set(c.id for c in meta.regular_cols)
        assert "ID" in regular_cols
        assert "Updated at" in regular_cols
        assert "text" in regular_cols
        assert "text_" not in regular_cols  # State column

        with table.create_session() as session:
            # Cannot specify "ID" or "Updated at"
            with pytest.raises(ValidationError):
                table.create_table(
                    session,
                    TableSchemaCreate(
                        id=TABLE_ID_X,
                        cols=[
                            ColumnSchemaCreate(id="ID", dtype="str"),
                            ColumnSchemaCreate(id="text", dtype="str"),
                        ],
                    ),
                )
            with pytest.raises(ValidationError):
                table.create_table(
                    session,
                    TableSchemaCreate(
                        id=TABLE_ID_X,
                        cols=[
                            ColumnSchemaCreate(id="Updated at", dtype="str"),
                        ],
                    ),
                )
            # Cannot contain repeated column names
            with pytest.raises(ValidationError):
                table.create_table(
                    session,
                    TableSchemaCreate(
                        id=TABLE_ID_X,
                        cols=[
                            ColumnSchemaCreate(id="text", dtype="str"),
                            ColumnSchemaCreate(id="text", dtype="str"),
                        ],
                    ),
                )


def test_create_knowledge_table():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as db_dir:
        table = KnowledgeTable(
            f"sqlite:///{db_dir}/test.db",
            f"{db_dir}/test-lance",
            read_consistency_interval=timedelta(seconds=0),
        )
        with table.create_session() as session:
            lance_table, meta = table.create_table(
                session,
                KnowledgeTableSchemaCreate(id=TABLE_ID_A, cols=[]),
            )
        # Inspect metadata
        assert isinstance(lance_table, LanceTable)
        assert lance_table.count_rows() == 0
        cols = set(c.id for c in meta.cols_schema)
        assert "ID" in cols
        assert "Updated at" in cols
        assert "Text" in cols
        assert "Text_" in cols  # State column
        assert "_Text" in cols  # Embed column
        assert "_Text_" in cols  # Embed state column
        assert "Title" in cols
        assert "Title_" in cols  # State column
        assert "_Title" in cols  # Embed column
        assert "_Title_" in cols  # Embed state column
        assert "File ID" in cols
        assert "File ID_" in cols  # State column
        regular_cols = set(c.id for c in meta.regular_cols)
        assert "ID" in regular_cols
        assert "Updated at" in regular_cols
        assert "Text" in regular_cols
        assert "Text_" not in regular_cols  # State column

        with table.create_session() as session:
            lance_table, meta = table.create_table(
                session,
                KnowledgeTableSchemaCreate(
                    id=TABLE_ID_B,
                    cols=[
                        ColumnSchemaCreate(id="Summary", dtype="str"),
                    ],
                ),
            )
        # Inspect metadata
        assert isinstance(lance_table, LanceTable)
        assert lance_table.count_rows() == 0
        cols = set(c.id for c in meta.cols_schema)
        assert "ID" in cols
        assert "Updated at" in cols
        assert "Text" in cols
        assert "Text_" in cols  # State column
        assert "_Text" in cols  # Embed column
        assert "_Text_" in cols  # Embed state column
        assert "Title" in cols
        assert "Title_" in cols  # State column
        assert "_Title" in cols  # Embed column
        assert "_Title_" in cols  # Embed state column
        assert "File ID" in cols
        assert "File ID_" in cols  # State column
        assert "Summary" in cols
        assert "Summary_" in cols  # State column

        with table.create_session() as session:
            # Cannot specify "ID" or "Updated at"
            with pytest.raises(ValidationError):
                table.create_table(
                    session,
                    KnowledgeTableSchemaCreate(
                        id=TABLE_ID_X,
                        cols=[ColumnSchemaCreate(id="ID", dtype="str")],
                    ),
                )
            # Cannot specify "Text" or "Title"
            with pytest.raises(ValidationError):
                table.create_table(
                    session,
                    KnowledgeTableSchemaCreate(
                        id=TABLE_ID_X,
                        cols=[
                            ColumnSchemaCreate(id="Text", dtype="str"),
                        ],
                    ),
                )
            with pytest.raises(ValidationError):
                table.create_table(
                    session,
                    KnowledgeTableSchemaCreate(
                        id=TABLE_ID_X,
                        cols=[
                            ColumnSchemaCreate(id="Title", dtype="str"),
                        ],
                    ),
                )


def test_create_chat_table():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as db_dir:
        table = ChatTable(
            f"sqlite:///{db_dir}/test.db",
            f"{db_dir}/test-lance",
            read_consistency_interval=timedelta(seconds=0),
        )
        with table.create_session() as session:
            lance_table, meta = table.create_table(
                session,
                ChatTableSchemaCreate(id=TABLE_ID_A, cols=[]),
            )
        # Inspect metadata
        assert isinstance(lance_table, LanceTable)
        assert lance_table.count_rows() == 0
        cols = set(c.id for c in meta.cols_schema)
        assert "ID" in cols
        assert "Updated at" in cols
        assert "User" in cols
        assert "User_" in cols  # State column
        assert "AI" in cols
        assert "AI_" in cols  # State column
        regular_cols = set(c.id for c in meta.regular_cols)
        assert "ID" in regular_cols
        assert "Updated at" in regular_cols
        assert "User" in regular_cols
        assert "User_" not in regular_cols  # State column

        with table.create_session() as session:
            lance_table, meta = table.create_table(
                session,
                ChatTableSchemaCreate(
                    id=TABLE_ID_B,
                    cols=[
                        ColumnSchemaCreate(id="Safety Review", dtype="str"),
                    ],
                ),
            )
        # Inspect metadata
        assert isinstance(lance_table, LanceTable)
        assert lance_table.count_rows() == 0
        cols = set(c.id for c in meta.cols_schema)
        assert "ID" in cols
        assert "Updated at" in cols
        assert "User" in cols
        assert "User_" in cols  # State column
        assert "AI" in cols
        assert "AI_" in cols  # State column
        assert "Safety Review" in cols
        assert "Safety Review_" in cols  # State column

        with table.create_session() as session:
            # Cannot specify "ID" or "Updated at"
            with pytest.raises(ValidationError):
                table.create_table(
                    session,
                    ChatTableSchemaCreate(
                        id=TABLE_ID_X,
                        cols=[ColumnSchemaCreate(id="ID", dtype="str")],
                    ),
                )
            # Cannot specify "User" or "AI"
            with pytest.raises(ValidationError):
                table.create_table(
                    session,
                    ChatTableSchemaCreate(
                        id=TABLE_ID_X,
                        cols=[ColumnSchemaCreate(id="User", dtype="str")],
                    ),
                )
            with pytest.raises(ValidationError):
                table.create_table(
                    session,
                    ChatTableSchemaCreate(
                        id=TABLE_ID_X,
                        cols=[ColumnSchemaCreate(id="AI", dtype="str")],
                    ),
                )


def _add_rows(tmp_path: str):
    table, lance_table, meta = _create_table(tmp_path)
    # Add data
    with table.create_session() as session:
        table.add_rows(
            session,
            TABLE_ID_A,
            [
                {
                    "text": "Arrival is a 2016 science fiction drama film",
                    "text embed": np.ones([EMBED_LEN], dtype=np.float16),
                },
                {
                    "text": None,
                    "text embed": None,
                },
            ],
        )
    return table, lance_table, meta


def test_add_rows():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        dt = datetime.now(tz=timezone.utc)
        table, lance_table, meta = _add_rows(tmp_path)
        assert table.count_rows(TABLE_ID_A) == 2
        with table.create_session() as session:
            meta = table.open_meta(session, TABLE_ID_A)
        assert datetime.fromisoformat(meta.updated_at) > dt


def test_get_rows():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_rows(tmp_path)
        rows, total = table.list_rows(TABLE_ID_A)
        assert isinstance(rows[0]["ID"], str)
        assert len(rows[0]["ID"]) > 0
        row = table.get_row(TABLE_ID_A, rows[0]["ID"])
        assert "Arrival" in row["text"]
        assert json_loads(row["text_"])["is_null"] is True
        row = table.get_row(TABLE_ID_A, rows[0]["ID"], remove_state_cols=True)
        assert "text_" not in row
        assert "text embed" in row
        row = table.get_row(TABLE_ID_A, rows[0]["ID"], columns=["text"], remove_state_cols=True)
        assert "text_" not in row
        assert "text embed" not in row


def test_select():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_rows(tmp_path)
        # Select with and without offset
        rows, total = table.list_rows(TABLE_ID_A)
        assert rows[0]["text"] == "Arrival is a 2016 science fiction drama film"
        assert rows[1]["text"] is None
        assert "text_" in rows[0].model_dump()
        rows, total = table.list_rows(TABLE_ID_A, offset=1)
        assert rows[0]["text"] is None
        assert rows[0]["text embed"] is None
        # Convert null
        rows, total = table.list_rows(TABLE_ID_A, convert_null=False)
        assert isinstance(rows[1]["text embed"], np.ndarray)
        rows, total = table.list_rows(TABLE_ID_A, convert_null=True)
        assert rows[1]["text embed"] is None
        # Remove state
        rows, total = table.list_rows(TABLE_ID_A, remove_state_cols=True)
        assert "text_" not in rows[0]
        assert isinstance(rows[0]["text embed"], np.ndarray)
        assert rows[1]["text embed"] is None
        rows, total = table.list_rows(TABLE_ID_A, remove_state_cols=True)
        assert "text_" not in rows[0]
        assert isinstance(rows[0]["text embed"], np.ndarray)
        assert isinstance(rows[0]["Updated at"], datetime)
        # JSON safe
        rows, total = table.list_rows(
            TABLE_ID_A,
            convert_null=True,
            remove_state_cols=True,
            json_safe=True,
        )
        assert rows[0]["text"] == "Arrival is a 2016 science fiction drama film"
        rows, total = table.list_rows(
            TABLE_ID_A,
            convert_null=True,
            remove_state_cols=True,
            json_safe=True,
        )
        assert rows[0]["text"] == "Arrival is a 2016 science fiction drama film"
        assert isinstance(rows[0]["text embed"], list)
        assert isinstance(rows[0]["Updated at"], str)
        assert rows[1]["text"] is None
        assert rows[1]["text embed"] is None
        assert "text_" not in rows[0]


def test_add_columns():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_rows(tmp_path)
        with table.create_session() as session:
            table.add_columns(
                session,
                TableSchemaCreate(
                    id=TABLE_ID_A,
                    cols=[
                        ColumnSchemaCreate(id="title", dtype="str"),
                        ColumnSchemaCreate(id="page", dtype="int"),
                    ],
                ),
            )
        rows, total = table.list_rows(TABLE_ID_A)
        assert rows[0]["title"] is None
        assert json_loads(rows[0]["title_"])["is_null"] is False
        assert rows[1]["title"] is None
        assert rows[0]["page"] is None
        assert json_loads(rows[0]["page_"])["is_null"] is False
        assert rows[1]["page"] is None

        with table.create_session() as session:
            table.add_columns(
                session,
                TableSchema(
                    id=TABLE_ID_A,
                    cols=[
                        ColumnSchemaCreate(id="title embed", dtype="float32", vlen=EMBED_LEN),
                    ],
                ),
            )
            rows, total = table.list_rows(TABLE_ID_A)
            assert rows[0]["title embed"] is None
            assert json_loads(rows[0]["title embed_"])["is_null"] is False
            assert rows[1]["title embed"] is None


def _add_columns_mixed(tmp_path: str):
    table, lance_table, meta = _add_rows(tmp_path)
    # Add columns
    with table.create_session() as session:
        table.add_columns(
            session,
            TableSchema(
                id=TABLE_ID_A,
                cols=[
                    ColumnSchemaCreate(id="title", dtype="str"),
                    ColumnSchemaCreate(id="title embed", dtype="float32", vlen=EMBED_LEN),
                    ColumnSchemaCreate(id="file_content", dtype="file"),
                ],
            ),
        )
    rows, total = table.list_rows(TABLE_ID_A)
    assert rows[0]["title"] is None
    assert rows[1]["title"] is None
    rows, total = table.list_rows(TABLE_ID_A)
    assert rows[0]["title embed"] is None
    assert rows[1]["title embed"] is None

    # Inspect metadata
    with table.create_session() as session:
        lance_table, meta = table.open_table_meta(session, TABLE_ID_A)
        assert isinstance(lance_table, LanceTable)
        assert lance_table.count_rows() == 2
        cols = set(c.id for c in meta.cols_schema)
        assert "ID" in cols
        assert "Updated at" in cols
        assert "text" in cols
        assert "text_" in cols  # State column
        assert "text embed" in cols
        assert "text embed_" in cols  # State column
        assert "title" in cols
        assert "title_" in cols  # State column
        assert "title embed" in cols
        assert "title embed_" in cols  # State column

    # Add data with new column
    with table.create_session() as session:
        table.add_rows(
            session,
            TABLE_ID_A,
            [
                {
                    "text": "Dune is a 2021 epic science fiction film",
                    "text embed": np.full([EMBED_LEN], 2, dtype=np.float16),
                    "title": "Dune",
                    "title embed": np.full([EMBED_LEN], 2, dtype=np.float32),
                    "file_content": "s3:///default/wiki.pdf",
                },
                {
                    "text": None,
                    "text embed": None,
                    "title": None,
                    "title embed": None,
                    "file_content": None,
                },
            ],
        )
    rows, total = table.list_rows(TABLE_ID_A)
    assert rows[0]["title"] is None
    assert rows[1]["title"] is None
    assert rows[2]["title"] == "Dune"
    assert rows[3]["title"] is None
    assert rows[0]["file_content"] is None
    assert rows[1]["file_content"] is None
    assert rows[2]["file_content"] == "s3:///default/wiki.pdf"
    assert rows[3]["file_content"] is None
    return table, lance_table, meta


def test_add_columns_mixed():
    # Unit test must only return None
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_columns_mixed(tmp_path)
        with table.create_session() as session:
            # Invalid embed config
            with pytest.raises(ValidationError):
                table.add_columns(
                    session,
                    TableSchema(
                        id=TABLE_ID_A,
                        cols=[
                            ColumnSchemaCreate(
                                id="embed",
                                dtype="float32",
                                vlen=EMBED_LEN,
                                gen_config=EmbedGenConfig(
                                    embedding_model=EMBEDDING_MODEL,
                                    source_column="xx",
                                ).model_dump(),
                            ),
                        ],
                    ),
                )


def test_duplicate_table():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_columns_mixed(tmp_path)
        # Duplicate table
        with table.create_session() as session:
            new_meta = table.duplicate_table(session, TABLE_ID_A, TABLE_ID_B)
            assert new_meta.id == TABLE_ID_B
            assert new_meta.parent_id is None
            table.delete_table(session, TABLE_ID_B)
            new_meta = table.duplicate_table(session, TABLE_ID_A, TABLE_ID_B, deploy=True)
            assert new_meta.id == TABLE_ID_B
            assert new_meta.parent_id == TABLE_ID_A
            table.update_rows(
                session,
                TABLE_ID_B,
                where=f"regexp_match(`text`, 'Dune')",
                values={
                    "text embed": np.full([EMBED_LEN], 99, dtype=np.float16),
                    "text": "Sicario",
                    "title": "Sicario",
                },
            )
            table.create_fts_index(session, TABLE_ID_A)
            table.create_fts_index(session, TABLE_ID_B)
            rows = table.search(session, TABLE_ID_A, "Dune", limit=2)
            assert len(rows) == 1
            rows = table.search(session, TABLE_ID_B, "Dune", limit=2)
            assert len(rows) == 0
            rows = table.search(session, TABLE_ID_B, "Sicario", limit=2)
            assert len(rows) == 1

            # Duplicate table (schema only)
            new_meta = table.duplicate_table(session, TABLE_ID_A, TABLE_ID_C, include_data=False)
            assert new_meta.parent_id is None
            table.delete_table(session, TABLE_ID_C)
            new_meta = table.duplicate_table(
                session, TABLE_ID_A, TABLE_ID_C, include_data=False, deploy=True
            )
            assert new_meta.id == TABLE_ID_C
            assert new_meta.parent_id == TABLE_ID_A
            rows, total = table.list_rows(TABLE_ID_C)
            assert len(rows) == 0
            assert table.count_rows(TABLE_ID_C) == 0
            assert table.count_rows(TABLE_ID_B) > 0

            # Overlapping name
            with pytest.raises(ResourceExistsError):
                table.duplicate_table(session, TABLE_ID_A, TABLE_ID_B)

            # Duplicate template
            new_meta = table.duplicate_table(
                session, TABLE_ID_A, TABLE_ID_X, include_data=False, deploy=False
            )
            assert new_meta.parent_id is None
            assert table.count_rows(TABLE_ID_X) == 0
            table.delete_table(session, TABLE_ID_X)
            new_meta = table.duplicate_table(
                session, TABLE_ID_A, TABLE_ID_X, include_data=True, deploy=False
            )
            assert new_meta.parent_id is None
            assert table.count_rows(TABLE_ID_X) == 4


def test_rename_table():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_rows(tmp_path)
        # Rename table
        with table.create_session() as session:
            new_meta = table.rename_table(session, TABLE_ID_A, TABLE_ID_B)
            assert new_meta.id == TABLE_ID_B
            assert table.count_rows(TABLE_ID_B) > 0
            with pytest.raises(ResourceNotFoundError):
                table.open_table(TABLE_ID_A)
        # Overlapping name
        with table.create_session() as session:
            with pytest.raises(ResourceExistsError):
                table.rename_table(session, TABLE_ID_A, TABLE_ID_B)


def test_delete_table():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _create_table(tmp_path)
        with table.create_session() as session:
            table.delete_table(session, TABLE_ID_A)


def test_update_gen_configs():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_columns_mixed(tmp_path)
        # Update generation config
        with table.create_session() as session:
            meta = table.update_gen_config(
                session,
                GenConfigUpdateRequest(
                    table_id=TABLE_ID_A,
                    column_map={
                        "text": dict(model="gpt", temperature=0.8),
                        "title embed": dict(
                            embedding_model=EMBEDDING_MODEL,
                            source_column="text",
                        ),
                    },
                ),
            )
            for c in meta.cols_schema:
                if c.id in ("text", "title embed"):
                    assert c.gen_config is not None
                else:
                    assert c.gen_config is None
            # Inspect metadata
            meta = table.open_meta(session, TABLE_ID_A)
            for c in meta.cols_schema:
                if c.id in ("text", "title embed"):
                    assert c.gen_config is not None
                else:
                    assert c.gen_config is None
            # Non-existent columns
            with pytest.raises(ValueError):
                table.update_gen_config(
                    session,
                    GenConfigUpdateRequest(
                        table_id=TABLE_ID_A,
                        column_map={"Paragraph": dict(model="gpt", temperature=0.8)},
                    ),
                )
            # Invalid gen config
            with pytest.raises(ValidationError):
                table.update_gen_config(
                    session,
                    GenConfigUpdateRequest(
                        table_id=TABLE_ID_A,
                        column_map={"text": dict(model="", temperature=0.8)},
                    ),
                )
            with pytest.raises(ValidationError):
                table.update_gen_config(
                    session,
                    GenConfigUpdateRequest(
                        table_id=TABLE_ID_A,
                        column_map={
                            "text": dict(model="gpt", temperature=0.8),
                            "title embed": dict(model="ada", language="en"),
                        },
                    ),
                )
            # Cannot update info columns
            with pytest.raises(ValidationError):
                table.update_gen_config(
                    session,
                    GenConfigUpdateRequest(
                        table_id=TABLE_ID_A,
                        column_map={"ID": dict(model="gpt", temperature=0.8)},
                    ),
                )
            with pytest.raises(ValidationError):
                table.update_gen_config(
                    session,
                    GenConfigUpdateRequest(
                        table_id=TABLE_ID_A,
                        column_map={"Updated at": dict(model="gpt", temperature=0.8)},
                    ),
                )


def test_drop_columns():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_columns_mixed(tmp_path)
        # Drop columns
        rows, total = table.list_rows(TABLE_ID_A)
        assert "title" in rows[0]
        assert "title_" in rows[0]
        assert "title embed" in rows[0]
        assert "title embed_" in rows[0]
        with table.create_session() as session:
            table.drop_columns(session, TABLE_ID_A, ["title", "title embed", "file_content"])
        rows, total = table.list_rows(TABLE_ID_A)
        assert len(rows) == 4
        assert rows[0]["text embed"][0] == 1.0
        assert rows[1]["text embed"] is None
        assert rows[2]["text embed"][0] == 2.0
        assert rows[3]["text embed"] is None
        assert "title" not in rows[0]
        assert "title_" not in rows[0]
        assert "title embed" not in rows[0]
        assert "title embed_" not in rows[0]

        # Inspect metadata
        with table.create_session() as session:
            lance_table, meta = table.open_table_meta(session, TABLE_ID_A)
            assert isinstance(lance_table, LanceTable)
            assert lance_table.count_rows() == 4
            cols = set(c.id for c in meta.cols_schema)
            assert "ID" in cols
            assert "Updated at" in cols
            assert "text" in cols
            assert "text_" in cols  # State column
            assert "text embed" in cols
            assert "text embed_" in cols  # State column
            assert "title" not in cols
            assert "title_" not in cols  # State column
            assert "title embed" not in cols
            assert "title embed_" not in cols  # State column

        # Try adding rows
        with table.create_session() as session:
            table.add_rows(
                session,
                TABLE_ID_A,
                [
                    {
                        "text": "Arrival is a 2016 science fiction drama film",
                        "text embed": np.ones([EMBED_LEN], dtype=np.float16),
                    },
                    {
                        "text": None,
                        "text embed": None,
                    },
                ],
            )
        rows, total = table.list_rows(TABLE_ID_A)
        assert len(rows) == 6


def test_update_rows():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_rows(tmp_path)
        rows, total = table.list_rows(TABLE_ID_A)
        # Update rows
        id_to_update = rows[1]["ID"]
        ori = {row["ID"]: row for row in rows}
        with table.create_session() as session:
            table.update_rows(
                session,
                TABLE_ID_A,
                where=f"`ID` = '{id_to_update}'",
                values={"text embed": np.full([EMBED_LEN], 3, dtype=np.float16)},
            )
        rows, total = table.list_rows(TABLE_ID_A)
        for row in rows:
            if row["ID"] == id_to_update:
                assert row["text embed"][0] == 3.0
                assert np.any(ori[row["ID"]]["text embed"] != row["text embed"])
            else:
                assert np.all(ori[row["ID"]]["text embed"] == row["text embed"])
        # Test update with value containing single-quote character
        with table.create_session() as session:
            table.update_rows(
                session,
                TABLE_ID_A,
                where=f"`ID` = '{id_to_update}'",
                values={"text": f"{ori[id_to_update]['text']}. My brother's car has 4 wheels."},
            )
        rows, total = table.list_rows(TABLE_ID_A)
        for row in rows:
            if row["ID"] == id_to_update:
                assert "brother's car" in row["text"]
                assert np.any(ori[row["ID"]]["text"] != row["text"])
            else:
                assert np.all(ori[row["ID"]]["text"] == row["text"])


def test_delete_rows():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_rows(tmp_path)
        with table.create_session() as session:
            table.add_rows(
                session,
                TABLE_ID_A,
                [
                    {
                        "text": "Blade Runner 2049 is a 2017 American epic neo-noir science fiction film",
                        "text embed": np.ones([EMBED_LEN], dtype=np.float16),
                    },
                ],
            )
            rows, total = table.list_rows(TABLE_ID_A)
            assert len(rows) == 3
            # Test index before deletion
            table.create_indexes(session, TABLE_ID_A)
            rows = table.search(session, TABLE_ID_A, "Arrival", limit=2)
            assert len(rows) == 1
            table.delete_rows(session, TABLE_ID_A, where=f"regexp_match(`text`, 'Arrival')")
            rows = table.search(session, TABLE_ID_A, "Arrival", limit=2)
            assert len(rows) == 1  # FTS index have to be re-built
            table.create_indexes(session, TABLE_ID_A)
            rows = table.search(session, TABLE_ID_A, "Arrival", limit=2)
            assert len(rows) == 0
        rows, total = table.list_rows(TABLE_ID_A)
        assert len(rows) == 2


def test_rename_columns():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_rows(tmp_path)
        rows, total = table.list_rows(TABLE_ID_A)
        with table.create_session() as session:
            # Test index before rename
            table.create_indexes(session, TABLE_ID_A)
            rows = table.search(session, TABLE_ID_A, "Arrival", limit=2)
            assert len(rows) == 1
            meta = table.rename_columns(session, TABLE_ID_A, dict(text="content"))
            cols = set(c.id for c in meta.cols_schema)
            assert "text" not in cols
            assert "content" in cols
            rows, total = table.list_rows(TABLE_ID_A)
            assert "text" not in rows[0]
            assert "text_" not in rows[0]
            assert "content" in rows[0]
            assert "content_" in rows[0]
            # Index does not need to be rebuilt
            rows = table.search(session, TABLE_ID_A, "Arrival", limit=2)
            assert len(rows) == 1
            table.rename_columns(session, TABLE_ID_A, dict(content="text"))
            cols = set(c.id for c in meta.cols_schema)
            assert "text" in cols
            assert "content" not in cols
            # Cannot rename state columns
            with pytest.raises(ValueError):
                table.rename_columns(session, TABLE_ID_A, dict(text="content_"))
            with pytest.raises(ValueError):
                table.rename_columns(session, TABLE_ID_A, dict(text_="text0"))


def test_reorder_columns():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_rows(tmp_path)
        # Reorder columns
        with table.create_session() as session:
            meta = table.open_meta(session, TABLE_ID_A)
            assert meta.cols_schema[0].id == "ID"
            assert meta.cols_schema[1].id == "Updated at"
            assert meta.cols_schema[2].id == "text"
            assert meta.cols_schema[3].id == "text_"
            assert meta.cols_schema[4].id == "text embed"
            assert meta.cols_schema[5].id == "text embed_"
        with table.create_session() as session:
            meta = table.reorder_columns(session, TABLE_ID_A, ["text embed", "text"])
            assert meta.cols_schema[0].id == "ID"
            assert meta.cols_schema[1].id == "Updated at"
            assert meta.cols_schema[2].id == "text embed"
            assert meta.cols_schema[3].id == "text embed_"
            assert meta.cols_schema[4].id == "text"
            assert meta.cols_schema[5].id == "text_"


def test_index_search():
    with TemporaryDirectory(dir=BASE_TMP_DIR) as tmp_path:
        table, lance_table, meta = _add_rows(tmp_path)
        with table.create_session() as session:
            table.create_scalar_index(session, TABLE_ID_A)
            table.create_fts_index(session, TABLE_ID_A)
            # FTS
            rows = table.search(session, TABLE_ID_A, "Arrival", limit=2)
            assert len(rows) == 1  # FTS only returns matches
            # # Hybrid search
            # rows = table.hybrid_search(session, TABLE_ID_A, "Arrival", limit=2)
            # assert len(rows) == 2
            # Vector search without index
            rows = table.search(session, TABLE_ID_A, np.random.rand(EMBED_LEN), limit=2)
            assert len(rows) == 2  # Vector search ranks by distance
            # Vector index with very few vectors
            table.create_vector_index(session, TABLE_ID_A)
            rows = table.search(session, TABLE_ID_A, np.random.rand(EMBED_LEN), limit=3)
            assert len(rows) == 2
            # Vector indexing requires more vectors
            table.add_rows(
                session,
                TABLE_ID_A,
                [
                    {
                        "text": f"text_{i}",
                        "text embed": np.random.rand(EMBED_LEN).astype(np.float16),
                    }
                    for i in range(1000)
                ],
            )
            table.create_vector_index(session, TABLE_ID_A)
            # Search again
            rows = table.search(session, TABLE_ID_A, np.random.rand(EMBED_LEN), limit=3)
            assert len(rows) == 3
            table.create_indexes(session, TABLE_ID_A)


if __name__ == "__main__":
    test_update_gen_configs()
