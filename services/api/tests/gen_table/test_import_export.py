import builtins
from dataclasses import dataclass
from os.path import dirname, join, realpath
from tempfile import TemporaryDirectory
from types import NoneType
from typing import Any

import httpx
import pandas as pd
import pytest

from jamaibase import JamAI
from jamaibase.types import (
    ColumnReorderRequest,
    ColumnSchemaCreate,
    EmbedGenConfig,
    GetURLResponse,
    LLMGenConfig,
    OkResponse,
    OrganizationCreate,
    TableImportRequest,
    TableMetaResponse,
    TableType,
)
from owl.utils.exceptions import (
    BadInputError,
)
from owl.utils.io import csv_to_df, df_to_csv
from owl.utils.test import (
    ELLM_DESCRIBE_CONFIG,
    ELLM_DESCRIBE_DEPLOYMENT,
    ELLM_EMBEDDING_CONFIG,
    ELLM_EMBEDDING_DEPLOYMENT,
    STREAM_PARAMS,
    TABLE_TYPES,
    TEXTS,
    RERANK_ENGLISH_v3_SMALL_CONFIG,
    RERANK_ENGLISH_v3_SMALL_DEPLOYMENT,
    add_table_rows,
    assert_is_vector_or_none,
    check_rows,
    create_deployment,
    create_model_config,
    create_organization,
    create_project,
    create_table,
    create_user,
    get_file_map,
    import_table_data,
    list_table_rows,
    upload_file,
)

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)

FILE_COLUMNS = ["image", "audio", "document", "File ID"]


@dataclass(slots=True)
class ServingContext:
    superuser_id: str
    superorg_id: str
    project_id: str
    embedding_size: int
    image_uri: str
    audio_uri: str
    document_uri: str
    chat_model_id: str
    embed_model_id: str
    rerank_model_id: str


@pytest.fixture(scope="module")
def setup():
    """
    Fixture to set up the necessary organization and projects for file tests.
    """
    with (
        create_user() as superuser,
        create_organization(
            body=OrganizationCreate(name="Superorg"), user_id=superuser.id
        ) as superorg,
        create_project(
            dict(name="Superorg Project"), user_id=superuser.id, organization_id=superorg.id
        ) as p0,
    ):
        assert superorg.id == "0"
        # Create models
        with (
            create_model_config(ELLM_DESCRIBE_CONFIG) as desc_llm_config,
            create_model_config(ELLM_EMBEDDING_CONFIG) as embed_config,
            create_model_config(RERANK_ENGLISH_v3_SMALL_CONFIG) as rerank_config,
        ):
            # Create deployments
            with (
                create_deployment(ELLM_DESCRIBE_DEPLOYMENT),
                create_deployment(ELLM_EMBEDDING_DEPLOYMENT),
                create_deployment(RERANK_ENGLISH_v3_SMALL_DEPLOYMENT),
            ):
                client = JamAI(user_id=superuser.id, project_id=p0.id)
                image_uri = upload_file(client, FILES["rabbit.jpeg"]).uri
                audio_uri = upload_file(client, FILES["gutter.mp3"]).uri
                document_uri = upload_file(
                    client, FILES["LLMs as Optimizers [DeepMind ; 2023].pdf"]
                ).uri
                yield ServingContext(
                    superuser_id=superuser.id,
                    superorg_id=superorg.id,
                    project_id=p0.id,
                    embedding_size=embed_config.final_embedding_size,
                    image_uri=image_uri,
                    audio_uri=audio_uri,
                    document_uri=document_uri,
                    chat_model_id=desc_llm_config.id,
                    embed_model_id=embed_config.id,
                    rerank_model_id=rerank_config.id,
                )


@dataclass(slots=True)
class Data:
    data_list: list[dict[str, Any]]
    action_data_list: list[dict[str, Any]]
    knowledge_data: dict[str, Any]
    chat_data: dict[str, Any]
    extra_data: dict[str, Any]


def _default_data(setup: ServingContext):
    action_data_list = [
        {
            "ID": str(i),
            "Updated at": "1990-05-13T09:01:50.010756+00:00",
            "int": 1 if i % 2 == 0 else (1.0 if i % 4 == 1 else None),
            "float": -1.25 if i % 2 == 0 else (5 if i % 4 == 1 else None),
            "bool": True if i % 2 == 0 else (False if i % 4 == 1 else None),
            "str": t,
            "image": setup.image_uri if i % 2 == 0 else None,
            "audio": setup.audio_uri if i % 2 == 0 else None,
            "document": setup.document_uri if i % 2 == 0 else None,
            "summary": t if i % 2 == 0 else ("" if i % 4 == 1 else None),
        }
        for i, t in enumerate(TEXTS.values())
    ]
    # Assert integers and floats contain a mix of int, float, None
    _ints = [type(d["int"]) for d in action_data_list]
    assert int in _ints
    assert float in _ints
    assert NoneType in _ints
    _floats = [type(d["float"]) for d in action_data_list]
    assert int in _floats
    assert float in _floats
    assert NoneType in _floats
    # Assert booleans contain a mix of True, False, None
    _bools = [d["bool"] for d in action_data_list]
    assert True in _bools
    assert False in _bools
    assert None in _bools
    # Assert strings contain a mix of empty string and None
    _summaries = [d["summary"] for d in action_data_list]
    assert None in _summaries
    assert "" in _summaries
    knowledge_data = {
        "Title": "Dune: Part Two.",
        "Text": '"Dune: Part Two" is a film.',
        # We use values that can be represented exactly as IEEE floats to ease comparison
        "Title Embed": [-1.25] * setup.embedding_size,
        "Text Embed": [0.25] * setup.embedding_size,
        "File ID": setup.document_uri,
    }
    chat_data = dict(User=".", AI=".")
    extra_data = dict(good=True, words=5)
    return Data(
        data_list=[
            dict(**d, **knowledge_data, **chat_data, **extra_data) for d in action_data_list
        ],
        action_data_list=action_data_list,
        knowledge_data=knowledge_data,
        chat_data=chat_data,
        extra_data=extra_data,
    )


def _default_dtype(
    data: list[dict[str, Any]],
    *,
    cast_to_string: bool = False,
) -> dict[str, pd.Int64Dtype | pd.Float32Dtype | pd.BooleanDtype | pd.StringDtype]:
    cols = set()
    for row in data:
        cols |= set(row.keys())
    dtype = {
        "ID": pd.StringDtype(),
        "Updated at": pd.StringDtype(),
        "int": pd.Int64Dtype() if not cast_to_string else pd.StringDtype(),
        "float": pd.Float32Dtype() if not cast_to_string else pd.StringDtype(),
        "bool": pd.BooleanDtype() if not cast_to_string else pd.StringDtype(),
        "str": pd.StringDtype(),
        "image": pd.StringDtype(),
        "audio": pd.StringDtype(),
        "document": pd.StringDtype(),
        "summary": pd.StringDtype(),
        "Title": pd.StringDtype(),
        "Text": pd.StringDtype(),
        "Title Embed": object,
        "Text Embed": object,
        "File ID": pd.StringDtype(),
        "User": pd.StringDtype(),
        "AI": pd.StringDtype(),
        "good": pd.BooleanDtype() if not cast_to_string else pd.StringDtype(),
        "words": pd.Int64Dtype() if not cast_to_string else pd.StringDtype(),
    }
    return {k: v for k, v in dtype.items() if k in cols}


def _as_df(
    data: list[dict[str, Any]],
    *,
    cast_to_string: bool = False,
) -> pd.DataFrame:
    dtype = _default_dtype(data, cast_to_string=cast_to_string)
    if cast_to_string:
        data = [{k: None if v is None else str(v) for k, v in d.items()} for d in data]
    df = pd.DataFrame.from_dict(data).astype(dtype)
    return df


def _check_rows(
    rows: list[dict[str, Any]],
    data: list[dict[str, Any]],
):
    return check_rows(rows, data, info_cols_equal=False)


def _check_knowledge_chat_data(
    table_type: TableType,
    rows: list[dict[str, Any]],
    data: Data,
):
    if table_type == TableType.KNOWLEDGE:
        _check_rows(rows, [data.knowledge_data] * len(data.data_list))
    elif table_type == TableType.CHAT:
        _check_rows(rows, [data.chat_data] * len(data.data_list))


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("delimiter", [","], ids=["comma"])
def test_data_import_complete(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    delimiter: str,
):
    """
    Test table data import.
    - All column types including vector
    - Ensure "ID" and "Updated at" columns are regenerated

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream or not.
        delimiter (str): Delimiter.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_data_import_complete.csv")
            data = _default_data(setup)
            df = _as_df(data.data_list)
            df_to_csv(df, file_path, delimiter)
            response = import_table_data(
                client,
                table_type,
                table.id,
                file_path,
                stream=stream,
                delimiter=delimiter,
            )
            # We currently dont return anything if LLM is not called
            assert len(response.rows) == 0 if stream else len(data.data_list)
            assert all(len(r.columns) == 0 for r in response.rows)
        # Check imported data
        rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
        assert len(rows.items) == len(data.data_list)
        assert rows.total == len(data.data_list)
        _check_rows(rows.values, data.action_data_list)
        _check_knowledge_chat_data(table_type, rows.values, data)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("delimiter", [","], ids=["comma"])
def test_data_import_dtype_coercion(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    delimiter: str,
):
    """
    Test table data import.
    - Column dtype coercion (nulls, int <=> float, bool <=> int)

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream or not.
        delimiter (str): Delimiter.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_data_import_dtype_coercion.csv")
            header = ["int", "float", "bool", "str", "image", "audio", "document", "summary", "AI"]
            data = [
                # Base case
                [1, 2.0, True, '""', '""', '""', '""', '""', '""'],
                # Coercion
                [1.0, 2, 1, '""', "", "", "", "", ""],
                [-1.0, -2, 0, "", "", "", "", "", ""],
                ["", "", "", "", "", "", "", "", ""],
            ]
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"{delimiter.join(header)}\n")
                f.write("\n".join(delimiter.join(map(str, d)) for d in data))
            response = import_table_data(
                client,
                table_type,
                table.id,
                file_path,
                stream=stream,
                delimiter=delimiter,
            )
            # We currently dont return anything if LLM is not called
            assert len(response.rows) == 0 if stream else len(data)
            assert all(len(r.columns) == 0 for r in response.rows)
        # Check imported data
        rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
        assert len(rows.items) == len(data)
        assert rows.total == len(data)
        # All strings are null
        for col in ["str", "image", "audio", "document", "summary", "AI"]:
            assert all(v.get(col, None) is None for v in rows.values)
        # Check values
        for col in ["int", "float", "bool"]:
            for v, d in zip(rows.values, data, strict=True):
                if d[header.index(col)] in ["", '""']:
                    assert v[col] is None
                else:
                    assert v[col] == d[header.index(col)]
                    assert isinstance(v[col], getattr(builtins, col))


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("delimiter", [","], ids=["comma"])
def test_data_import_cast_to_string(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    delimiter: str,
):
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    dtypes = ["int", "float", "bool", "str", "image", "audio", "document"]
    cols = [ColumnSchemaCreate(id=dtype, dtype="str") for dtype in dtypes]
    cols += [
        ColumnSchemaCreate(
            id="summary",
            dtype="str",
            gen_config=LLMGenConfig(model="", system_prompt="", prompt=""),
        ),
    ]
    with create_table(client, table_type, cols=cols) as table:
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_data_import_cast_to_string.csv")
            data = _default_data(setup)
            df = _as_df(data.data_list)
            # Assert some columns are not string type
            assert not all(d == pd.StringDtype() for d in df.dtypes.tolist())
            df_to_csv(df, file_path, delimiter)
            response = import_table_data(
                client,
                table_type,
                table.id,
                file_path,
                stream=stream,
                delimiter=delimiter,
            )
            # We currently dont return anything if LLM is not called
            assert len(response.rows) == 0 if stream else len(data.data_list)
            assert all(len(r.columns) == 0 for r in response.rows)
        # Check imported data
        rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
        assert len(rows.items) == len(data.data_list)
        assert rows.total == len(data.data_list)
        action_data_list = [
            {
                k: None
                if v is None
                else str(int(v) if k == "int" else (float(v) if k == "float" else v))
                for k, v in d.items()
            }
            for d in data.action_data_list
        ]
        _check_rows(rows.values, action_data_list)
        _check_knowledge_chat_data(table_type, rows.values, data)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("delimiter", [","], ids=["comma"])
def test_data_import_cast_from_string(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    delimiter: str,
):
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_data_import_cast_from_string.csv")
            data = _default_data(setup)
            df = _as_df(data.data_list, cast_to_string=True)
            # Assert all columns (except embedding) are string type
            assert all(
                v == pd.StringDtype() for k, v in df.dtypes.to_dict().items() if "Embed" not in k
            ), df.dtypes.to_dict()
            df_to_csv(df, file_path, delimiter)
            response = import_table_data(
                client,
                table_type,
                table.id,
                file_path,
                stream=stream,
                delimiter=delimiter,
            )
            # We currently dont return anything if LLM is not called
            assert len(response.rows) == 0 if stream else len(data.data_list)
            assert all(len(r.columns) == 0 for r in response.rows)
        # Check imported data
        rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
        assert len(rows.items) == len(data.data_list)
        assert rows.total == len(data.data_list)
        _check_rows(rows.values, data.action_data_list)
        _check_knowledge_chat_data(table_type, rows.values, data)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("delimiter", [","], ids=["comma"])
def test_data_import_missing_input_column(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    delimiter: str,
):
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_data_import_missing_input_column.csv")
            data = _default_data(setup)
            df = _as_df(data.data_list)
            df = df.drop(columns=["int"])
            df_to_csv(df, file_path, delimiter)
            response = import_table_data(
                client,
                table_type,
                table.id,
                file_path,
                stream=stream,
                delimiter=delimiter,
            )
            # We currently dont return anything if LLM is not called
            assert len(response.rows) == 0 if stream else len(data.data_list)
            assert all(len(r.columns) == 0 for r in response.rows)
        # Check imported data
        rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
        assert len(rows.items) == len(data.data_list)
        assert rows.total == len(data.data_list)
        _check_rows(
            rows.values,
            [{k: v for k, v in d.items() if k != "int"} for d in data.action_data_list],
        )
        _check_knowledge_chat_data(table_type, rows.values, data)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("delimiter", [","], ids=["comma"])
def test_data_import_with_generation(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    delimiter: str,
):
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_data_import_with_generation.csv")
            data = _default_data(setup)
            df = _as_df(data.data_list)
            df = df.drop(columns=["summary"])
            df_to_csv(df, file_path, delimiter)
            response = import_table_data(
                client,
                table_type,
                table.id,
                file_path,
                stream=stream,
                delimiter=delimiter,
            )
            # LLM is called
            assert len(response.rows) == len(data.data_list)
            assert all(len(r.columns) == 1 for r in response.rows)
            assert all("summary" in r.columns for r in response.rows)
        # Check imported data
        rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
        assert len(rows.items) == len(data.data_list)
        assert rows.total == len(data.data_list)
        _check_rows(
            rows.values,
            [{k: v for k, v in d.items() if k != "summary"} for d in data.action_data_list],
        )
        _check_knowledge_chat_data(table_type, rows.values, data)
        # Check LLM generation
        summaries = [row["summary"] for row in rows.values]
        assert all("There is a text" in s for s in summaries)
        assert sum("There is an image with MIME type [image/jpeg]" in s for s in summaries) > 0
        assert sum("There is an audio with MIME type [audio/mpeg]" in s for s in summaries) > 0


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("delimiter", [","], ids=["comma"])
def test_data_import_empty(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    delimiter: str,
):
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        with TemporaryDirectory() as tmp_dir:
            # Empty file
            file_path = join(tmp_dir, "empty.csv")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("")
            with pytest.raises(BadInputError, match="is empty"):
                import_table_data(
                    client,
                    table_type,
                    table.id,
                    file_path,
                    stream=stream,
                    delimiter=delimiter,
                )
            # No rows
            file_path = join(tmp_dir, "no_rows.csv")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(delimiter.join(c.id for c in table.cols) + "\n")
            with pytest.raises(BadInputError, match="no rows"):
                import_table_data(
                    client,
                    table_type,
                    table.id,
                    file_path,
                    stream=stream,
                    delimiter=delimiter,
                )
        rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
        assert len(rows.items) == 0


def _export_table_rows(
    client: JamAI,
    table_type: TableType,
    table: TableMetaResponse,
    *,
    data: Data,
    delimiter: str,
    columns: list[str] | None = None,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    csv_bytes = client.table.export_table_data(
        table_type,
        table.id,
        delimiter=delimiter,
    )
    dtype = _default_dtype(data.data_list, cast_to_string=False)
    if columns is None:
        columns = [c.id for c in table.cols]
    csv_df = csv_to_df(
        csv_bytes.decode("utf-8"),
        sep=delimiter,
        keep_default_na=True,
    ).astype({k: v for k, v in dtype.items() if k in columns})
    exported_rows = csv_df.to_dict(orient="records")
    assert len(exported_rows) == len(data.data_list)
    assert all(isinstance(row, dict) for row in exported_rows)
    assert all("ID" in row for row in exported_rows)
    assert all("Updated at" in row for row in exported_rows)
    return exported_rows, csv_df


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("stream", **STREAM_PARAMS)
@pytest.mark.parametrize("delimiter", [","], ids=["comma"])
def test_data_export(
    setup: ServingContext,
    table_type: TableType,
    stream: bool,
    delimiter: str,
):
    """
    Test table data export.
    - Export all columns (round trip)
    - Export subset of columns (round trip)
    - Export after column reorder (check column order, round trip)

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
        stream (bool): Stream or not.
        delimiter (str): Delimiter.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_data_export.csv")
            data = _default_data(setup)
            df_original = _as_df(data.data_list)
            df_to_csv(df_original, file_path, delimiter)
            response = import_table_data(
                client,
                table_type,
                table.id,
                file_path,
                stream=stream,
                delimiter=delimiter,
            )
            # We currently dont return anything if LLM is not called
            assert len(response.rows) == 0 if stream else len(data.data_list)
            assert all(len(r.columns) == 0 for r in response.rows)
        # Check imported data
        rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
        assert len(rows.items) == len(data.data_list)
        assert rows.total == len(data.data_list)
        row_ids = [r["ID"] for r in rows.items]

        ### --- Export all columns, round trip --- ###
        exported_rows, _ = _export_table_rows(
            client,
            table_type,
            table,
            data=data,
            delimiter=delimiter,
        )
        # Check row order
        exported_row_ids = [r["ID"] for r in exported_rows]
        assert row_ids == exported_row_ids
        # Check row content
        _check_rows(exported_rows, data.action_data_list)

        ### --- Export subset of columns --- ###
        columns = [c.id for c in table.cols][:2]
        assert len(columns) < len(table.cols)
        exported_rows, _ = _export_table_rows(
            client,
            table_type,
            table,
            data=data,
            delimiter=delimiter,
            columns=columns,
        )
        assert len(exported_rows) == len(data.data_list)
        _check_rows(
            exported_rows,
            [{k: v for k, v in d.items() if k in columns} for d in data.action_data_list],
        )

        ### --- Export after column reorder --- ###
        new_order = ["int", "float", "bool", "str", "image", "audio", "document"][::-1]
        new_order += ["summary"]
        if table_type == TableType.KNOWLEDGE:
            new_order = [
                "Title",
                "Title Embed",
                "Text",
                "Text Embed",
                "File ID",
                "Page",
            ] + new_order
        elif table_type == TableType.CHAT:
            new_order = ["User", "AI"] + new_order
        table = client.table.reorder_columns(
            table_type=table_type,
            request=ColumnReorderRequest(table_id=table.id, column_names=new_order),
        )
        assert isinstance(table, TableMetaResponse)
        exported_rows, exported_df = _export_table_rows(
            client,
            table_type,
            table,
            data=data,
            delimiter=delimiter,
        )
        _check_rows(exported_rows, data.action_data_list)
        # Check column order
        expected_columns = ["ID", "Updated at"] + new_order
        assert expected_columns == list(exported_df.columns)


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("blocking", [True, False], ids=["blocking", "non-blocking"])
def test_table_import_export(
    setup: ServingContext,
    table_type: TableType,
    blocking: bool,
):
    """
    Test table import and export.

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
    """
    stream = False
    delimiter = ","
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, table_type) as table:
        # Export empty table
        pq_data = client.table.export_table(table_type, table.id)
        assert len(pq_data) > 0
        # Add data
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_table_import_export.csv")
            data = _default_data(setup)
            df_original = _as_df(data.data_list)
            df_to_csv(df_original, file_path, delimiter)
            response = import_table_data(
                client,
                table_type,
                table.id,
                file_path,
                stream=stream,
                delimiter=delimiter,
            )
            # We currently dont return anything if LLM is not called
            assert len(response.rows) == 0 if stream else len(data.data_list)
            assert all(len(r.columns) == 0 for r in response.rows)

        ### --- Export table --- ###
        table_id_dst = f"{table.id}_import"
        try:
            with TemporaryDirectory() as tmp_dir:
                file_path = join(tmp_dir, f"{table.id}.parquet")
                with open(file_path, "wb") as f:
                    f.write(client.table.export_table(table_type, table.id))

                ### --- Import table --- ###
                # Bad name
                with pytest.raises(BadInputError):
                    client.table.import_table(
                        table_type,
                        TableImportRequest(
                            file_path=file_path,
                            table_id_dst=f"_{table_id_dst}",
                            blocking=blocking,
                        ),
                    )
                # OK
                response = client.table.import_table(
                    table_type,
                    TableImportRequest(
                        file_path=file_path,
                        table_id_dst=table_id_dst,
                        blocking=blocking,
                    ),
                )
                if blocking:
                    table_dst = response
                else:
                    # Poll progress
                    assert isinstance(response, OkResponse)
                    assert isinstance(response.progress_key, str)
                    assert len(response.progress_key) > 0
                    prog = client.tasks.poll_progress(response.progress_key, max_wait=30)
                    assert isinstance(prog, dict)
                    table_dst = TableMetaResponse.model_validate(prog["data"]["table_meta"])
                assert isinstance(table_dst, TableMetaResponse)
                assert table_dst.id == table_id_dst
            # Source data
            rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
            assert len(rows.items) == len(data.data_list)
            assert rows.total == len(data.data_list)
            # Destination data
            rows_dst = list_table_rows(client, table_type, table_dst.id, vec_decimals=2)
            # Compare
            for row, row_dst in zip(rows.items, rows_dst.items, strict=True):
                assert len(row) == len(row_dst)
                for col in row:
                    if col in FILE_COLUMNS:
                        # File columns should not match due to different S3 URI, unless it is None
                        value_ori = row[col]["value"]
                        value_dst = row_dst[col]["value"]
                        if value_ori is None:
                            assert value_dst is None
                        else:
                            assert value_ori != value_dst
                            # But content should match
                            urls = client.file.get_raw_urls([value_ori, value_dst])
                            assert isinstance(urls, GetURLResponse)
                            file_ori = httpx.get(urls.urls[0]).content
                            file_dst = httpx.get(urls.urls[1]).content
                            assert file_ori == file_dst
                    else:
                        # Regular columns should match exactly (including info columns)
                        assert row[col] == row_dst[col]
            # All "File ID" values should be populated
            if table_type == TableType.KNOWLEDGE:
                for row_dst in rows_dst.values:
                    assert isinstance(row_dst["File ID"], str)
                    assert len(row_dst["File ID"]) > 0
                assert len(set(r["File ID"] for r in rows_dst.values)) == 1
        finally:
            client.table.delete_table(table_type, table_id_dst)


@pytest.mark.parametrize("delimiter", [","], ids=["comma"])
def test_table_import_wrong_type(
    setup: ServingContext,
    delimiter: str,
):
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    with create_table(client, TableType.ACTION) as table:
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_table_import_wrong_type.csv")
            data = _default_data(setup)
            df = _as_df(data.data_list)
            df_to_csv(df, file_path, delimiter)
            response = import_table_data(
                client,
                TableType.ACTION,
                table.id,
                file_path,
                stream=False,
                delimiter=delimiter,
            )
            # We currently dont return anything if LLM is not called
            assert len(response.rows) == len(data.data_list)
            assert all(len(r.columns) == 0 for r in response.rows)
        with TemporaryDirectory() as tmp_dir:
            file_path = join(tmp_dir, "test_table_import_wrong_type.parquet")
            # Export
            with open(file_path, "wb") as f:
                f.write(client.table.export_table(TableType.ACTION, table.id))
            table_id_dst = f"{table.id}_import"
            # Import as knowledge
            with pytest.raises(BadInputError):
                client.table.import_table(
                    TableType.KNOWLEDGE,
                    TableImportRequest(
                        file_path=file_path,
                        table_id_dst=table_id_dst,
                    ),
                )
            # Import as chat
            with pytest.raises(BadInputError):
                client.table.import_table(
                    TableType.CHAT,
                    TableImportRequest(
                        file_path=file_path,
                        table_id_dst=table_id_dst,
                    ),
                )


@pytest.mark.parametrize("table_type", TABLE_TYPES)
@pytest.mark.parametrize("version", ["v0.4"])
def test_table_import_parquet(
    setup: ServingContext,
    table_type: TableType,
    version: str,
):
    """
    Test table import from an existing Parquet file.

    Args:
        setup (ServingContext): Setup.
        table_type (TableType): Table type.
    """
    client = JamAI(user_id=setup.superuser_id, project_id=setup.project_id)
    ### --- Basic tables --- ###
    if table_type == TableType.CHAT:
        parquet_filepath = FILES[f"export-{version}-chat-agent.parquet"]
    else:
        parquet_filepath = FILES[f"export-{version}-{table_type}.parquet"]
    # Embedding model cannot be swapped for another model
    if table_type == TableType.KNOWLEDGE:
        with pytest.raises(BadInputError, match="Embedding model .+ is not found"):
            client.table.import_table(
                table_type,
                TableImportRequest(file_path=parquet_filepath, table_id_dst=None),
            )
    # Add the required embedding model
    embed_model = "ellm/BAAI/bge-m3"
    model = ELLM_EMBEDDING_CONFIG.model_copy(update=dict(id=embed_model, owned_by="ellm"))
    deployment = ELLM_EMBEDDING_DEPLOYMENT.model_copy(update=dict(model_id=embed_model))
    with create_model_config(model), create_deployment(deployment):
        table = client.table.import_table(
            table_type,
            TableImportRequest(file_path=parquet_filepath, table_id_dst=None),
        )
        try:
            assert isinstance(table, TableMetaResponse)
            ### Table ID should be derived from the Parquet data
            if table_type == TableType.CHAT:
                assert table.id == "test-agent"
            else:
                assert table.id == f"test-{table_type}"
            assert table.parent_id is None
            col_map = {c.id: c for c in table.cols}
            embed_cols = ["Title Embed", "Text Embed"]

            ### Check gen config
            if table_type == TableType.ACTION:
                gen_config = col_map["answer"].gen_config
                assert isinstance(gen_config, LLMGenConfig)
                assert gen_config.model == setup.chat_model_id
            elif table_type == TableType.KNOWLEDGE:
                for c in embed_cols:
                    gen_config = col_map[c].gen_config
                    assert isinstance(gen_config, EmbedGenConfig)
                    assert gen_config.embedding_model == embed_model
            else:
                gen_config = col_map["AI"].gen_config
                assert isinstance(gen_config, LLMGenConfig)
                assert gen_config.model == setup.chat_model_id
                assert gen_config.multi_turn is True

            ### List rows
            rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
            assert len(rows.items) == 1
            assert rows.total == 1
            row = rows.values[0]
            if table_type == TableType.ACTION:
                # Check text content
                assert row["question"] == "What is this"
                assert row["answer"] == "This is a deer."
                assert row["null"] == ""
                # Check image content
                urls = client.file.get_raw_urls([row["image"]])
                assert isinstance(urls, GetURLResponse)
                image = httpx.get(urls.urls[0]).content
                with open(FILES["cifar10-deer.jpg"], "rb") as f:
                    assert image == f.read()
            elif table_type == TableType.KNOWLEDGE:
                # Check text content
                assert row["Title"] == "Gunicorn: A Python WSGI HTTP Server"
                assert row["Text"] == "Gunicorn is a Python WSGI HTTP Server."
                # Check vector content
                for c in embed_cols:
                    assert_is_vector_or_none(row[c], allow_none=False)
            else:
                # Check text content
                assert row["User"] == "Hi"
                assert row["AI"] == (
                    "Hello! How can I assist you today? "
                    "Let me know what you're looking for, and I'll do my best to help. 😊"
                )

            ### Try generation
            if table_type == TableType.ACTION:
                response = add_table_rows(
                    client, table_type, table.id, [{"question": "Why"}], stream=False
                )
                assert len(response.rows) == 1
                assert "There is a text" in response.rows[0].columns["answer"].content
            elif table_type == TableType.KNOWLEDGE:
                response = add_table_rows(client, table_type, table.id, [{}], stream=False)
                assert len(response.rows) == 1
            else:
                response = add_table_rows(
                    client, table_type, table.id, [{"User": "Hi"}], stream=False
                )
                assert len(response.rows) == 1
                assert "There is a text" in response.rows[0].columns["AI"].content
            rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
            assert len(rows.items) == 2
            assert rows.total == 2
        finally:
            client.table.delete_table(table_type, table.id)

        ### --- Chat table (child table) --- ###
        if table_type == TableType.CHAT:
            table = client.table.import_table(
                table_type,
                TableImportRequest(
                    file_path=FILES[f"export-{version}-chat-agent-1.parquet"], table_id_dst=None
                ),
            )
            try:
                assert isinstance(table, TableMetaResponse)
                # Table ID should be derived from the Parquet data
                assert table.id == "test-agent-1"
                # TODO: Perhaps need to handle missing parent and RAG table
                assert table.parent_id == "test-agent"
                # List rows
                rows = list_table_rows(client, table_type, table.id, vec_decimals=2)
                assert len(rows.items) == 2
                assert rows.total == 2
                # Check text content
                assert rows.values[0]["User"] == "Hi"
                assert rows.values[0]["AI"].startswith("Hello! How can I assist you today?")
                assert rows.values[1]["User"] == "What is 美洲驼?"
                assert rows.values[1]["AI"].startswith(
                    "**美洲驼** (Měizhōu tuó) 是以下两种南美洲骆驼科动物的中文统称：  \n\n1. **羊驼**"
                )
                rows_r = list_table_rows(
                    client, table_type, table.id, order_ascending=False, vec_decimals=2
                )
                assert all(rr == r for rr, r in zip(rows_r.values[::-1], rows.values, strict=True))
            finally:
                client.table.delete_table(table_type, table.id)
