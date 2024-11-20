import os
import pathlib
from io import BytesIO
from shutil import rmtree
from time import perf_counter
from typing import Annotated, Any

import duckdb
import pyarrow as pa
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Path,
    Query,
    Request,
    UploadFile,
)
from filelock import FileLock, Timeout
from loguru import logger
from pyarrow.parquet import read_table as read_parquet_table
from sqlmodel import Session, select

from jamaibase.exceptions import (
    BadInputError,
    ResourceExistsError,
    ResourceNotFoundError,
    UnexpectedError,
)
from jamaibase.utils.io import dump_json, json_loads, read_json
from owl.db import create_sql_tables, create_sqlite_engine
from owl.db.gen_table import GenerativeTable
from owl.db.template import Tag, Template, TemplateRead, TemplateSQLModel
from owl.protocol import (
    TABLE_NAME_PATTERN,
    ColName,
    GenTableOrderBy,
    OkResponse,
    Page,
    TableMetaResponse,
    TableType,
    TemplateMeta,
)
from owl.utils.auth import auth_internal
from owl.utils.exceptions import handle_exception

CURR_DIR = pathlib.Path(__file__).resolve().parent
TEMPLATE_DIR = CURR_DIR.parent / "templates"
DB_PATH = TEMPLATE_DIR / "template.db"
TEMPLATE_ID_PATTERN = r"^[A-Za-z0-9]([A-Za-z0-9_-]{0,98}[A-Za-z0-9])?$"

router = APIRouter(dependencies=[Depends(auth_internal)])
public_router = APIRouter()


@router.on_event("startup")
async def startup():
    global ENGINE
    ENGINE = create_sqlite_engine(f"sqlite:///{DB_PATH}")
    _populate_template_db()


def _populate_template_db(timeout: float = 0.0):
    lock = FileLock(TEMPLATE_DIR / "template.lock", timeout=timeout)
    try:
        with lock:
            t0 = perf_counter()
            if DB_PATH.exists():
                os.remove(DB_PATH)
            create_sql_tables(TemplateSQLModel, ENGINE)
            metas = []
            for template_dir in TEMPLATE_DIR.iterdir():
                if not template_dir.is_dir():
                    continue
                template_filepath = template_dir / "template_meta.json"
                if not template_filepath.is_file():
                    logger.warning(f"Missing template metadata JSON in {template_dir}")
                    continue
                metas.append((template_dir.name, read_json(template_dir / "template_meta.json")))
            tags = sum([meta["tags"] for _, meta in metas], [])
            tags = {t: t for t in tags}
            with Session(ENGINE) as session:
                for tag in tags:
                    tag = Tag(id=tag)
                    session.add(tag)
                    tags[tag.id] = tag
                session.commit()
                for template_id, meta in metas:
                    meta = TemplateMeta.model_validate(meta)
                    session.add(
                        Template(
                            id=template_id,
                            name=meta.name,
                            description=meta.description,
                            created_at=meta.created_at,
                            tags=[tags[t] for t in meta.tags],
                        )
                    )
                session.commit()
            logger.info(f"Populated template DB in {perf_counter() - t0:,.2f} s")
    except Timeout:
        pass
    except Exception as e:
        logger.exception(f"Failed to populate template DB due to {e}")


def _get_session():
    with Session(ENGINE) as session:
        yield session


@router.post("/admin/backend/v1/templates/import")
@handle_exception
async def add_template(
    *,
    request: Request,
    file: Annotated[UploadFile, File(description="Template Parquet file.")],
    template_id_dst: Annotated[
        str, Form(pattern=TEMPLATE_ID_PATTERN, description="The ID of the new template.")
    ],
    exist_ok: Annotated[
        bool, Form(description="_Optional_. Whether to overwrite existing template.")
    ] = False,
) -> OkResponse:
    t0 = perf_counter()
    dst_dir = TEMPLATE_DIR / template_id_dst
    if exist_ok:
        try:
            rmtree(dst_dir)
        except (NotADirectoryError, FileNotFoundError):
            pass
    elif dst_dir.is_dir():
        raise ResourceExistsError(f'Template "{template_id_dst}" already exists.')
    os.makedirs(dst_dir, exist_ok=True)
    try:
        with BytesIO(await file.read()) as source:
            # Write the template metadata JSON
            pa_table = read_parquet_table(source, columns=None, use_threads=False, memory_map=True)
            metadata = pa_table.schema.metadata
            try:
                template_meta = json_loads(metadata[b"template_meta"])
            except KeyError as e:
                raise BadInputError("Missing template metadata in the Parquet file.") from e
            except Exception as e:
                raise BadInputError("Invalid template metadata in the Parquet file.") from e
            dump_json(template_meta, dst_dir / "template_meta.json")
            # Write the table parquet files
            try:
                type_metas = json_loads(metadata[b"table_metas"])
            except KeyError as e:
                raise BadInputError("Missing table metadata in the Parquet file.") from e
            except Exception as e:
                raise BadInputError("Invalid table metadata in the Parquet file.") from e
            for row, type_meta in zip(pa_table.to_pylist(), type_metas, strict=True):
                table_type = type_meta["table_type"]
                table_id = type_meta["table_meta"]["id"]
                os.makedirs(dst_dir / table_type, exist_ok=True)
                with open(dst_dir / table_type / f"{table_id}.parquet", "wb") as f:
                    f.write(row["data"])
        logger.info(
            f'{request.state.id} - Template "{template_id_dst}" imported in {perf_counter() - t0:,.2f} s.'
        )
    except pa.ArrowInvalid as e:
        raise BadInputError(str(e)) from e
    _populate_template_db(30.0)
    return OkResponse()


@router.post("/admin/backend/v1/templates/populate")
@handle_exception
def populate_templates(
    *,
    timeout: Annotated[
        float,
        Query(ge=0, description="_Optional_. Timeout in seconds, must be >= 0. Defaults to 30.0."),
    ] = 30.0,
) -> OkResponse:
    _populate_template_db(timeout=timeout)
    return OkResponse()


@public_router.get("/public/v1/templates")
@handle_exception
def list_templates(
    *,
    session: Annotated[Session, Depends(_get_session)],
    search_query: Annotated[
        str,
        Query(
            max_length=10_000,
            description='_Optional_. A string to search for within template names. Defaults to "" (no filter).',
        ),
    ] = "",
) -> Page[TemplateRead]:
    selection = select(Template)
    if search_query != "":
        selection = selection.where(Template.name.ilike(f"%{search_query}%"))
    items = session.exec(selection).all()
    total = len(items)
    return Page[TemplateRead](items=items, offset=0, limit=total, total=total)


@public_router.get("/public/v1/templates/{template_id}")
@handle_exception
def get_template(
    *,
    session: Annotated[Session, Depends(_get_session)],
    template_id: Annotated[
        str,
        Path(max_length=10_000, description="Template ID."),
    ],
) -> TemplateRead:
    template = session.get(Template, template_id)
    if template is None:
        raise ResourceNotFoundError(f'Template "{template_id}" is not found.')
    return template


@public_router.get("/public/v1/templates/{template_id}/gen_tables/{table_type}")
@handle_exception
def list_tables(
    *,
    template_id: Annotated[
        str,
        Path(max_length=10_000, description="Template ID."),
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="_Optional_. Item offset for pagination. Defaults to 0.",
        ),
    ] = 0,
    limit: Annotated[
        int,
        Query(
            gt=0,
            le=100,
            description="_Optional_. Number of tables to return (min 1, max 100). Defaults to 100.",
        ),
    ] = 100,
    search_query: Annotated[
        str,
        Query(
            max_length=100,
            description='_Optional_. A string to search for within table IDs as a filter. Defaults to "" (no filter).',
        ),
    ] = "",
    order_by: Annotated[
        GenTableOrderBy,
        Query(
            min_length=1,
            description='_Optional_. Sort tables by this attribute. Defaults to "updated_at".',
        ),
    ] = GenTableOrderBy.UPDATED_AT,
    order_descending: Annotated[
        bool,
        Query(description="_Optional_. Whether to sort by descending order. Defaults to True."),
    ] = True,
) -> Page[TableMetaResponse]:
    template_dir = TEMPLATE_DIR / template_id
    if not template_dir.is_dir():
        raise ResourceNotFoundError(f'Template "{template_id}" is not found.')
    table_dir = template_dir / table_type
    if not table_dir.is_dir():
        return Page[TableMetaResponse](items=[], offset=0, limit=100, total=0)
    metas: list[TableMetaResponse] = []
    for table_path in sorted(table_dir.iterdir()):
        table = read_parquet_table(table_path, columns=[], use_threads=False, memory_map=True)
        try:
            table_meta = table.schema.metadata[b"gen_table_meta"]
        except KeyError as e:
            raise UnexpectedError(
                f'Missing table metadata in "templates/{template_id}/gen_tables/{table_type}/{table_path.name}".'
            ) from e
        except Exception as e:
            raise UnexpectedError(
                f'Invalid table metadata in "templates/{template_id}/gen_tables/{table_type}/{table_path.name}".'
            ) from e
        metas.append(TableMetaResponse.model_validate_json(table_meta))
    metas = [
        m
        for m in sorted(metas, key=lambda m: getattr(m, order_by), reverse=order_descending)
        if search_query.lower() in m.id.lower()
    ]
    total = len(metas)
    return Page[TableMetaResponse](
        items=metas[offset : offset + limit], offset=offset, limit=limit, total=total
    )


@public_router.get("/public/v1/templates/{template_id}/gen_tables/{table_type}/{table_id}")
@handle_exception
def get_table(
    *,
    template_id: Annotated[
        str,
        Path(max_length=10_000, description="Template ID."),
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(pattern=TABLE_NAME_PATTERN, description="Table ID or name."),
) -> TableMetaResponse:
    template_dir = TEMPLATE_DIR / template_id
    if not template_dir.is_dir():
        raise ResourceNotFoundError(f'Template "{template_id}" is not found.')
    table_path = template_dir / table_type / f"{table_id}.parquet"
    if not table_path.is_file():
        raise ResourceNotFoundError(f'Table "{table_id}" is not found.')
    table = read_parquet_table(table_path, columns=[], use_threads=False, memory_map=True)
    try:
        meta = TableMetaResponse.model_validate_json(table.schema.metadata[b"gen_table_meta"])
    except KeyError as e:
        raise UnexpectedError(
            f'Missing table metadata in "templates/{template_id}/gen_tables/{table_type}/{table_path.name}".'
        ) from e
    except Exception as e:
        raise UnexpectedError(
            f'Invalid table metadata in "templates/{template_id}/gen_tables/{table_type}/{table_path.name}".'
        ) from e
    return meta


@public_router.get("/public/v1/templates/{template_id}/gen_tables/{table_type}/{table_id}/rows")
@handle_exception
def list_table_rows(
    *,
    template_id: Annotated[
        str,
        Path(max_length=10_000, description="Template ID."),
    ],
    table_type: Annotated[TableType, Path(description="Table type.")],
    table_id: str = Path(pattern=TABLE_NAME_PATTERN, description="Table ID or name."),
    starting_after: Annotated[
        str | None,
        Query(
            min_length=1,
            description=(
                "_Optional_. A cursor for use in pagination. Only rows with ID > `starting_after` will be returned. "
                'For instance, if your call receives 100 rows ending with ID "x", '
                'your subsequent call can include `starting_after="x"` in order to fetch the next page of the list.'
            ),
        ),
    ] = None,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="_Optional_. Item offset. Defaults to 0.",
        ),
    ] = 0,
    limit: Annotated[
        int,
        Query(
            gt=0,
            le=100,
            description="_Optional_. Number of rows to return (min 1, max 100). Defaults to 100.",
        ),
    ] = 100,
    order_by: Annotated[
        str,
        Query(
            min_length=1,
            description='_Optional_. Sort rows by this column. Defaults to "Updated at".',
        ),
    ] = "Updated at",
    order_descending: Annotated[
        bool,
        Query(description="_Optional_. Whether to sort by descending order. Defaults to True."),
    ] = True,
    float_decimals: int = Query(
        default=0,
        ge=0,
        description="_Optional_. Number of decimals for float values. Defaults to 0 (no rounding).",
    ),
    vec_decimals: int = Query(
        default=0,
        description="_Optional_. Number of decimals for vectors. If its negative, exclude vector columns. Defaults to 0 (no rounding).",
    ),
) -> Page[dict[ColName, Any]]:
    template_dir = TEMPLATE_DIR / template_id
    if not template_dir.is_dir():
        raise ResourceNotFoundError(f'Template "{template_id}" is not found.')
    table_path = template_dir / table_type / f"{table_id}.parquet"
    if not table_path.is_file():
        raise ResourceNotFoundError(f'Table "{table_id}" is not found.')

    query = GenerativeTable._list_rows_query(
        table_name=table_path,
        sort_by=order_by,
        sort_order="DESC" if order_descending else "ASC",
        starting_after=starting_after,
        id_column="ID",
        offset=offset,
        limit=limit,
    )
    df = duckdb.sql(query).df()
    df = GenerativeTable._post_process_rows_df(
        df,
        columns=None,
        convert_null=True,
        remove_state_cols=True,
        json_safe=True,
        include_original=True,
        float_decimals=float_decimals,
        vec_decimals=vec_decimals,
    )
    rows = df.to_dict("records")
    total = duckdb.sql(GenerativeTable._count_rows_query(table_path)).fetchone()[0]
    return Page[dict[ColName, Any]](
        items=rows,
        offset=offset,
        limit=limit,
        total=total,
        starting_after=starting_after,
    )
