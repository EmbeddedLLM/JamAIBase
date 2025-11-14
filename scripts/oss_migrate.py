"""
Script to migrate oss JamaiBase from V1 to V2.
"""

import concurrent.futures
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from os import makedirs, remove
from pathlib import Path
from time import perf_counter, sleep
from typing import Generator
from zoneinfo import ZoneInfo

import boto3
import httpx
from botocore.exceptions import ClientError, NoCredentialsError
from loguru import logger
from pydantic import Field
from sqlalchemy import NullPool
from sqlmodel import Session, create_engine, text

from jamaibase import JamAI
from owl.configs import ENV_CONFIG
from owl.db import SCHEMA, JamaiSQLModel, init_db
from owl.db.models import (
    Deployment,
    ModelConfig,
    Organization,
    OrgMember,
    Project,
    ProjectMember,
)
from owl.types import (
    ModelType,
    OrganizationRead,
    OrgMember_,
    Page,
    Project_,
    TableImportRequest,
    TableMetaResponse,
    TableType,
)
from owl.utils.crypt import decrypt
from owl.utils.dates import now_iso, utc_datetime_from_iso
from owl.utils.exceptions import ResourceNotFoundError
from owl.utils.io import dump_json, json_loads
from owl.utils.types import CLI

TZ = "Asia/Kuala_Lumpur"

os.environ["TZ"] = TZ
time.tzset()


@lru_cache(maxsize=100_000)
def _decrypt(value: str, encryption_key: str) -> str:
    return decrypt(value, encryption_key)


class Config(CLI):
    db_v1_path: str = Field(
        description="Path to V1 SQLite database file.",
    )
    db_v2_host: str = Field(
        "localhost",
        description="Host to V2 Postgres database.",
    )
    db_v2_port: int = Field(
        5432,
        description="Port to V2 Postgres database.",
    )
    db_v2_user: str = Field(
        "owlpguser",
        description="User to V2 Postgres database.",
    )
    db_v2_db: str = Field(
        "jamaibase_owl",
        description="Database to V2 Postgres database.",
    )
    db_v2_password: str = Field(
        "owlpgpassword",
        description="Password to V2 Postgres database.",
    )
    encryption_key: str = Field(
        ENV_CONFIG.encryption_key.get_secret_value(),
        description="Encryption key.",
    )
    service_key: str = Field(
        ENV_CONFIG.service_key.get_secret_value(),
        description="Service key.",
    )
    api_base_src: str = Field(
        "http://localhost:26969/api",
        description="Source API base URL (v1 JamAIBase).",
    )
    api_base_dst: str = Field(
        "http://localhost:6969/api",
        description="Destination API base URL (v2 JamAIBase).",
    )
    cache_dir: str = Field(
        "./migration_temp/",
        description="A temporary cache directory to store logs and files.",
    )
    # s3_endpoint_src: str = Field(
    #     description="Source S3 endpoint.",
    # )
    # s3_access_key_src: str = Field(
    #     description="Source S3 access key.",
    # )
    # s3_secret_key_src: str = Field(
    #     description="Source S3 secret key.",
    # )
    # s3_bucket_src: str = Field(
    #     "file",
    #     description="Source S3 bucket.",
    # )
    v1_file_path: str = Field(
        description="Source V1 full file path.",
    )
    s3_endpoint_dst: str = Field(
        "http://localhost:9000",
        description="Destination S3 endpoint.",
    )
    s3_access_key_dst: str = Field(
        ENV_CONFIG.s3_access_key_id,
        description="Destination S3 access key, should be same as EMU_S3_ACCESS_KEY_ID.",
    )
    s3_secret_key_dst: str = Field(
        ENV_CONFIG.s3_secret_access_key.get_secret_value(),
        description="Destination S3 secret key, should be same as EMU_S3_SECRET_ACCESS_KEY.",
    )
    s3_bucket_dst: str = Field(
        "file",
        description="Destination S3 bucket, change this if file_dir is updated with EMU_FILE_DIR.",
    )
    workers: int = Field(
        2,
        description="Number of worker threads.",
    )
    reset: bool = Field(
        False,
        description="Reset destination DB.",
    )
    migrate: bool = Field(
        False,
        description="Migrate organization data. Default is dry-run.",
    )
    verbose: bool = Field(
        False,
        description="Enable verbose output (shows SQL queries).",
    )


@contextmanager
def sync_session_v1(config: Config) -> Generator[Session, None, None]:
    with Session(create_engine(f"sqlite:///{config.db_v1_path}", poolclass=NullPool)) as session:
        yield session


@contextmanager
def sync_session_v2(config: Config) -> Generator[Session, None, None]:
    engine = create_engine(
        f"postgresql+psycopg://{config.db_v2_user}:{config.db_v2_password}@{config.db_v2_host}:{config.db_v2_port}/{config.db_v2_db}",
        poolclass=NullPool,
    )
    with Session(engine) as session:
        yield session


def migrate_organization(
    config: Config,
    org_id_src: str,
    *,
    org_id_dst: str = "",
):
    t0 = perf_counter()
    with sync_session_v1(config) as sess_v1:
        stmt = "SELECT * FROM organization where id = :organization_id"
        row = sess_v1.exec(text(stmt), params=dict(organization_id=org_id_src)).one()
    if not row:
        logger.error(f"FAILED to fetch organization {org_id_src} from V1 DB.")
        return
    org_data = dict(row._mapping)
    org_data["external_keys"] = {
        k: v
        for k, v in json_loads(org_data.get("external_keys", "{}")).items()
        if _decrypt(v, config.encryption_key)
    }
    org_models = json_loads(org_data.pop("models", "{}"))
    name: str = org_data.pop("name")

    organization_id = org_id_dst if org_id_dst else org_id_src
    if organization_id != "0" and len(org_models) > 0:
        logger.warning(
            f'Organization "{name}" ({organization_id}) has {len(org_models):,d} internal models.'
        )
        dump_json(org_models, Path(config.cache_dir) / f"{organization_id}_internal_models.json")

    with sync_session_v2(config) as sess_v2:
        if org_id_dst:
            logger.info(
                f'\n{"-" * 10} Migrating organization "{name}" ({org_id_src} -> {org_id_dst}) {"-" * 10}'
            )
        else:
            logger.info(
                f'\n{"-" * 10} Migrating organization "{name}" ({organization_id}) {"-" * 10}'
            )

    # if org_id_dst == "0" do an inplace update
    if org_id_dst == "0":
        with sync_session_v2(config) as sess_v2:
            logger.info("Updating admin organization...")
            dst_org = sess_v2.get(Organization, org_id_dst)
            dst_org.external_keys = org_data["external_keys"]
            dst_org.created_at = utc_datetime_from_iso(org_data["created_at"])
            dst_org.updated_at = utc_datetime_from_iso(org_data["updated_at"])
            dst_org.timezone = org_data["timezone"]
            sess_v2.commit()
            org = OrganizationRead.model_validate(dst_org)
            om = sess_v2.get(OrgMember, (org.owner, org_id_dst))
            org_member = OrgMember_.model_validate(om)

        # Migrate models and deployments
        # Get v1 models and deployments
        try:
            response = httpx.get(
                f"{config.api_base_src}/admin/backend/v1/models",
                timeout=None,
            )
            response.raise_for_status()
            model_data = response.json()
        except Exception:
            logger.error("FAILED to fetch models from V1.")
            return
        _migrate_models(config, admin_models=model_data, org_models=org_models)

    # Migrate projects and create project members
    t1 = perf_counter()
    with sync_session_v1(config) as sess_v1:
        stmt = "SELECT * FROM project where organization_id = :organization_id"
        rows = sess_v1.exec(text(stmt), params=dict(organization_id=org_id_src)).all()
        projects = [dict(row._mapping) for row in rows]
    logger.info(f"Migrating {len(projects):,d} projects ...")
    # get OrgMembers (it should only really have 1 member (the owner/user: "0")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _migrate_project, config, p, org, [org_member], idx=i, total=len(projects)
            )
            for i, p in enumerate(projects)
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
        migrated = sum(r is True for r in results)
        failed = sum(r is False for r in results)
        logger.info(f"{migrated:,d}/{len(projects)} projects migrated, {failed:,d} failed.")
    logger.info(f"Project migration completed in t={(perf_counter() - t1):,.2f} s")
    logger.info(f"Organization migration completed in t={(perf_counter() - t0):,.2f} s")


def _migrate_models(
    config: Config,
    *,
    admin_models: dict,
    org_models: dict,
):
    llm_models = []
    llm_deployments = []
    embed_models = []
    embed_deployments = []
    rerank_models = []
    rerank_deployments = []
    for model in admin_models["llm_models"] + org_models["llm_models"]:
        # example model:
        # {
        #   "id": "anthropic/claude-3-haiku-20240307",
        #   "object": "model",
        #   "name": "Anthropic Claude 3 Haiku",
        #   "context_length": 200000,
        #   "languages": [
        #     "mul"
        #   ],
        #   "owned_by": "anthropic",
        #   "capabilities": [
        #     "chat"
        #   ],
        #   "priority": 0,
        #   "deployments": [
        #     {
        #       "litellm_id": "",
        #       "api_base": "",
        #       "provider": "anthropic"
        #     }
        #   ],
        #   "litellm_id": "",
        #   "api_base": "",
        #   "input_cost_per_mtoken": 0.15,
        #   "output_cost_per_mtoken": 0.6
        # }
        llm_deployments.extend(
            [
                Deployment(
                    model_id=model["id"],
                    name=model["name"],
                    # best effort routing id mapping
                    routing_id=_d["litellm_id"][7:]
                    if _d["provider"] != "openai" and _d["litellm_id"].startswith("openai/")
                    else _d["litellm_id"]
                    if _d["litellm_id"]
                    else model["id"],
                    api_base=_d["api_base"],
                    provider=_d["provider"],
                )
                for _d in model["deployments"]
            ]
        )
        llm_models.extend(
            [
                ModelConfig(
                    id=model["id"],
                    name=model["name"],
                    context_length=model["context_length"],
                    capabilities=model["capabilities"],
                    owned_by=model["owned_by"],
                    priority=model["priority"],
                    type=ModelType.LLM,
                    languages=["en"],  # For simplicity just use "en"
                    llm_input_cost_per_mtoken=model["input_cost_per_mtoken"],
                    llm_output_cost_per_mtoken=model["output_cost_per_mtoken"],
                )
            ]
        )
    for model in admin_models["embed_models"] + org_models["embed_models"]:
        # {
        #   "id": "ellm/BAAI/bge-small-en-v1.5",
        #   "object": "model",
        #   "name": "ELLM BAAI BGE Small EN v1.5",
        #   "context_length": 512,
        #   "languages": [
        #     "mul"
        #   ],
        #   "owned_by": "ellm",
        #   "capabilities": [
        #     "embed"
        #   ],
        #   "priority": 0,
        #   "deployments": [
        #     {
        #       "litellm_id": "openai/BAAI/bge-small-en-v1.5",
        #       "api_base": "http://infinity:6909",
        #       "provider": "ellm"
        #     }
        #   ],
        #   "litellm_id": "",
        #   "api_base": "",
        #   "embedding_size": 384,
        #   "dimensions": null,
        #   "transform_query": null,
        #   "cost_per_mtoken": 0.022
        # }
        embed_deployments.extend(
            [
                Deployment(
                    model_id=model["id"],
                    name=model["name"],
                    # best effort routing id mapping
                    routing_id=_d["litellm_id"][7:]
                    if _d["provider"] != "openai" and _d["litellm_id"].startswith("openai/")
                    else _d["litellm_id"]
                    if _d["litellm_id"]
                    else model["id"],
                    api_base=_d["api_base"],
                    provider=_d["provider"],
                )
                for _d in model["deployments"]
            ]
        )
        embed_models.extend(
            [
                ModelConfig(
                    id=model["id"],
                    name=model["name"],
                    context_length=model["context_length"],
                    capabilities=model["capabilities"],
                    owned_by=model["owned_by"],
                    priority=model["priority"],
                    type=ModelType.EMBED,
                    languages=model["languages"],
                    embedding_size=model["embedding_size"],
                    embedding_dimensions=model["dimensions"],
                    embedding_transform_query=model["transform_query"],
                    embedding_cost_per_mtoken=model["cost_per_mtoken"],
                )
            ]
        )
    for model in admin_models["rerank_models"] + org_models["rerank_models"]:
        # {
        #   "id": "ellm/mixedbread-ai/mxbai-rerank-xsmall-v1",
        #   "object": "model",
        #   "name": "ELLM MxBAI Rerank XSmall v1",
        #   "context_length": 512,
        #   "languages": [
        #     "en"
        #   ],
        #   "owned_by": "ellm",
        #   "capabilities": [
        #     "rerank"
        #   ],
        #   "priority": 0,
        #   "deployments": [
        #     {
        #       "litellm_id": "",
        #       "api_base": "http://infinity:6909",
        #       "provider": "ellm"
        #     }
        #   ],
        #   "litellm_id": "",
        #   "api_base": "",
        #   "cost_per_ksearch": 2.0
        # }
        rerank_deployments.extend(
            [
                Deployment(
                    model_id=model["id"],
                    name=model["name"],
                    # best effort routing id mapping
                    routing_id=_d["litellm_id"][9:]
                    if _d["litellm_id"].startswith("infinity/")
                    else _d["litellm_id"]
                    if _d["litellm_id"]
                    else model["id"],
                    api_base=_d["api_base"],
                    provider="infinity"
                    if _d["litellm_id"].startswith("infinity/")
                    else _d["provider"],
                )
                for _d in model["deployments"]
            ]
        )
        rerank_models.extend(
            [
                ModelConfig(
                    id=model["id"],
                    name=model["name"],
                    context_length=model["context_length"],
                    capabilities=model["capabilities"],
                    owned_by=model["owned_by"],
                    priority=model["priority"],
                    type=ModelType.RERANK,
                    languages=model["languages"],
                    reranking_cost_per_ksearch=model["cost_per_ksearch"],
                )
            ]
        )
    models = llm_models + embed_models + rerank_models
    deployments = llm_deployments + embed_deployments + rerank_deployments
    with sync_session_v2(config) as sess_v2:
        if len(models) > 0:
            sess_v2.add_all(models)
            sess_v2.commit()
            logger.info(f"Migrated {len(models):,d} models.")
        if len(deployments) > 0:
            sess_v2.add_all(deployments)
            sess_v2.commit()
            logger.info(f"Migrated {len(deployments):,d} deployments.")


def _upload_knowledge_table_file(
    config: Config,
    table_id: str,
    client_src: JamAI,
) -> None:
    s3_client = _get_s3_client(
        config.s3_endpoint_dst, config.s3_access_key_dst, config.s3_secret_key_dst
    )
    _curr = 0
    _total = 1
    src_rows = []
    while _curr < _total:
        _rows = client_src.table.list_table_rows(
            table_id=table_id,
            table_type=TableType.KNOWLEDGE,
            offset=_curr,
            limit=100,
            columns=["File ID"],
            v1=True,
        )
        _curr += len(_rows.items)
        _total = _rows.total
        src_rows += _rows.items
    distinct_file_ids = set([r.get("File ID") for r in src_rows])
    # attempt to upload file to dst s3
    for file_id in distinct_file_ids:
        _upload_file_to_s3(
            file_id=file_id,
            bucket_name=config.s3_bucket_dst,
            s3_client=s3_client,
            local_base_path=config.v1_file_path,
        )


def _migrate_project(
    config: Config,
    data: dict,
    org: OrganizationRead,
    org_members: list[OrgMember_],
    *,
    idx: int,
    total: int,
):
    project_id: str = data["id"]
    project_name: str = data["name"]
    logger.info(f'{idx + 1:03d}/{total}: Migrating project "{project_name} ({project_id})"')
    with sync_session_v2(config) as sess_v2:
        project = Project(
            id=project_id,
            organization_id=org.id,
            name=project_name,
            description=project_name,
            created_by=org.owner,
            owner=org.owner,
            created_at=utc_datetime_from_iso(data["created_at"]),
            updated_at=utc_datetime_from_iso(data["updated_at"]),
        )
        project_members = []
        for m in org_members:
            if sess_v2.get(ProjectMember, (m.user_id, project_id)):
                continue
            project_members.append(
                ProjectMember(
                    user_id=m.user_id,
                    project_id=project_id,
                    role=m.role,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                )
            )
        if not config.migrate:
            return True
        if sess_v2.get(Project, project_id) is None:
            sess_v2.add(project)
            sess_v2.commit()
        if len(project_members) > 0:
            sess_v2.add_all(project_members)
            sess_v2.commit()
        project = Project_.model_validate(project)

    with sync_session_v1(config) as session:
        project = (
            session.exec(
                text("SELECT * FROM project WHERE id=:id"),
                params=dict(id=project_id),
            )
            .one_or_none()
            ._mapping
        )
        # there's really just 1 user, "0"
        owner_v1 = "0"
    # Migrate tables
    for table_type in [TableType.KNOWLEDGE, TableType.ACTION, TableType.CHAT]:
        # Copy new tables
        try:
            _curr = 0
            total = 1
            src_tables = []
            while _curr < total:
                response = httpx.get(
                    f"{config.api_base_src}/v1/gen_tables/{table_type}",
                    headers={
                        "X-PROJECT-ID": project_id,
                    },
                    timeout=None,
                    params=dict(offset=_curr, limit=100),
                )
                response.raise_for_status()
                r = response.json()
                total = r["total"]
                _curr += len(r["items"])
                src_tables += Page[TableMetaResponse].model_validate_json(response.text).items
        except Exception as e:
            logger.error(f"FAILED to fetch src table list due to error: {repr(e)}")
            return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=config.workers) as executor:
            futures = [
                executor.submit(
                    _migrate_gen_table,
                    config,
                    owner_v1,
                    org.owner,
                    org.id,
                    project_id,
                    project_name,
                    table.id,
                    table_type,
                    idx=j,
                    total=len(src_tables),
                )
                for j, table in enumerate(src_tables)
            ]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
            migrated = sum(r is True for r in results)
            failed = sum(r is False for r in results)
            skipped = sum(r is None for r in results)
            logger.info(
                (
                    f"{migrated:,d}/{len(src_tables)} {table_type} tables migrated, "
                    f"{skipped:,d} skipped, {failed:,d} failed."
                )
            )
        # Remove deleted tables
        src_tables_ids = {t.id for t in src_tables}
        with sync_session_v2(config) as sess_v2:
            schema_id = f"{project_id}_{table_type}"
            if not (
                sess_v2.exec(
                    text(f"""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_schema = '{schema_id}' AND table_name = 'TableMetadata'
                        );
                    """)
                )
            ).scalar():
                continue
            dst_table_ids = {
                dict(r._mapping)["table_id"]
                for r in sess_v2.exec(
                    text(f'SELECT table_id FROM "{schema_id}"."TableMetadata"')
                ).all()
            }
            if len(src_tables_ids - dst_table_ids) > 0:
                logger.warning(
                    f'Project "{project_id}" migrated with missing tables: {src_tables_ids - dst_table_ids}'
                )
            if len(dst_table_ids - src_tables_ids) == 0:
                continue
            logger.warning(
                f'Project "{project_id}": Deleting tables not found in V1: {dst_table_ids - src_tables_ids}'
            )
            for table_id in dst_table_ids - src_tables_ids:
                JamAI(
                    user_id=org.owner,
                    project_id=project_id,
                    api_base=config.api_base_dst,
                    token=config.service_key,
                ).table.delete_table(table_type, table_id, missing_ok=True)
    # Reset project updated at
    with sync_session_v2(config) as sess_v2:
        sess_v2.exec(
            text(
                """UPDATE "jamai"."Project" SET updated_at = :updated_at WHERE id = :project_id"""
            ),
            params=dict(updated_at=project.updated_at, project_id=project_id),
        )
        sess_v2.commit()
    return True


def _migrate_gen_table(
    config: Config,
    user_id_src: str,
    user_id_dst: str,
    organization_id: str,
    project_id: str,
    project_name: str,
    table_id: str,
    table_type: str,
    *,
    idx: int,
    total: int,
):
    client_src = JamAI(
        user_id=user_id_src,
        project_id=project_id,
        api_base=config.api_base_src,
    )
    client_dst = JamAI(
        user_id=user_id_dst,
        project_id=project_id,
        api_base=config.api_base_dst,
    )
    try:
        # Check source and destination tables
        for _ in range(3):
            try:
                src_table = client_src.table.get_table(table_type, table_id, v1=True)
                break
            except Exception as e:
                logger.warning(
                    f'Retrying fetch src {table_type} table "{table_id}" due to error {repr(e)}'
                )
                sleep(1.0)
        else:
            raise RuntimeError(f'FAILED to fetch src {table_type} table "{table_id}"')
        dst_table = None
        for _ in range(3):
            try:
                dst_table = client_dst.table.get_table(table_type, table_id)
                break
            except ResourceNotFoundError:
                break
            except Exception as e:
                logger.warning(
                    f'Retrying fetch dst {table_type} table "{table_id}" due to error {repr(e)}'
                )
                sleep(1.0)
        else:
            raise RuntimeError(f'FAILED to fetch dst {table_type} table "{table_id}"')

        # Skip tables with the same number of rows and updated time
        if dst_table is not None and (
            src_table.num_rows == dst_table.num_rows
            and src_table.updated_at <= dst_table.updated_at
        ):
            logger.info(
                (
                    f'{idx + 1:03d}/{total}: Skipped {table_type} table "{table_id}": '
                    f"Same number of rows and updated time."
                )
            )
            return None

        # Export parquet
        pq_dir = Path(config.cache_dir) / organization_id / project_id / table_type
        pq_path = pq_dir / f"{table_id}.parquet"
        if pq_path.is_file() and src_table.updated_at <= datetime.fromtimestamp(
            os.stat(pq_path).st_ctime, ZoneInfo("UTC")
        ):
            with open(pq_path, "rb") as f:
                pq_content = f.read()
            logger.info(
                f'{idx + 1:03d}/{total}: Loaded {table_type} table "{table_id}" parquet file.'
            )
        else:
            try:
                pq_content = client_src.table.export_table(
                    table_type, table_id, v1=True, timeout=300
                )
            except Exception as e:
                raise RuntimeError(
                    f'FAILED to export {table_type} table "{table_id}" due to error {repr(e)}'
                ) from e
            # Cache the parquet
            try:
                makedirs(pq_dir, exist_ok=True)
                with open(pq_path, "wb") as f:
                    f.write(pq_content)
            except KeyboardInterrupt:
                try:
                    remove(pq_path)
                finally:
                    raise
            logger.info(
                f'{idx + 1:03d}/{total}: Cached {table_type} table "{table_id}" parquet file.'
            )

        # Drop the data table
        if config.migrate:
            client_dst.table.delete_table(table_type, table_id, missing_ok=True)

        # Import table
        if config.migrate:
            response = client_dst.table.import_table(
                table_type,
                TableImportRequest(file_path=str(pq_path), table_id_dst=table_id, blocking=False),
                migrate=True,
                reupload=True,
            )
            # Poll progress
            prog = client_dst.tasks.poll_progress(response.progress_key, verbose=True)
            assert isinstance(prog, dict)
            if table_meta := prog["data"].get("table_meta", None):
                table = TableMetaResponse.model_validate(table_meta)
                assert table.id == table_id
            # special handling of knowledge table files
            if table_type == TableType.KNOWLEDGE:
                _upload_knowledge_table_file(
                    config=config,
                    table_id=table_id,
                    client_src=client_src,
                )
            # Check num rows
            for _ in range(3):
                try:
                    dst_table = client_dst.table.get_table(table_type, table_id)
                except Exception:
                    sleep(1.0)
                else:
                    if src_table.num_rows == dst_table.num_rows:
                        break
                    else:
                        raise RuntimeError(
                            f"Mismatched number of rows: {src_table.num_rows=} {dst_table.num_rows=}"
                        )
        logger.info(f'{idx + 1:03d}/{total}: Migrated {table_type} table "{table_id}".')
        with open(Path(config.cache_dir) / "migrated_tables.tsv", "a") as f:
            f.write(
                "\t".join(
                    [now_iso(TZ), organization_id, project_name, project_id, table_type, table_id]
                )
                + "\n"
            )
        return True
    except Exception as e:
        logger.error(
            f'{idx + 1:03d}/{total}: Failed to migrate {table_type} table "{table_id}" due to error: {repr(e)}'
        )
        with open(Path(config.cache_dir) / "failed_tables.tsv", "a") as f:
            f.write(
                "\t".join(
                    [
                        now_iso(TZ),
                        organization_id,
                        project_name,
                        project_id,
                        table_type,
                        table_id,
                        repr(e),
                    ]
                )
                + "\n"
            )
        return False


def _get_s3_client(endpoint, access_key, secret_key):
    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        client.list_buckets()
        # logger.info(f"Successfully connected to MinIO at {endpoint}")
        return client
    except (NoCredentialsError, ClientError) as e:
        logger.error(f"Failed to connect to MinIO at {endpoint}. Error: {e}")
        return None


def _upload_file_to_s3(
    file_id: str, bucket_name: str, s3_client: boto3.client, local_base_path: str
) -> bool:
    """
    Upload files from file_id to S3

    Args:
        file_id (str): in format file://file/raw/default/default/...
        bucket_name (str): S3 bucket name
        s3_client: Initialized boto3 S3 client
        local_base_path (str): Base path where local files are stored
    """

    try:
        # Extract the S3 key from the file ID
        # Remove the 'file://file' prefix to get the S3 key
        if file_id.startswith("file://file/"):
            s3_key = file_id.replace("file://file/", "")
        else:
            s3_key = file_id

        # Determine local file path
        if local_base_path:
            # If base path is provided, construct full local path
            local_file_path = os.path.join(local_base_path, s3_key)

        # Check if local file exists
        if not os.path.exists(local_file_path):
            logger.error(f"File not found: {local_file_path}")
            return False

        # Upload to S3
        s3_client.upload_file(local_file_path, bucket_name, s3_key)
        logger.info(f"Successfully uploaded: {s3_key} to bucket: {bucket_name}")
        return True

    except ClientError as e:
        error_msg = f"S3 upload error: {e}"
        logger.error(f"Failed to upload {file_id}: {error_msg}")
        return False
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(f"Failed to upload {file_id}: {error_msg}")
        return False


def maybe_reset_db(config: Config):
    if not config.reset:
        return
    with sync_session_v2(config) as sess_v2:
        logger.info("Resetting database ...")
        logger.info(f'Dropping schema "{SCHEMA}"')
        if config.migrate:
            sess_v2.exec(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            sess_v2.exec(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
            sess_v2.commit()
        # for oss there's a proj with id: "default"
        stmt = """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE (schema_name LIKE 'proj_%' OR schema_name LIKE 'default_%')
        AND (schema_name LIKE '%_action' OR schema_name LIKE '%_knowledge' OR schema_name LIKE '%_chat');
        """
        schemas = [r[0] for r in sess_v2.exec(text(stmt)).all()]
        logger.info(f'Dropping Generative Table schemas: "{schemas}"')
        for schema in schemas:
            if config.migrate:
                sess_v2.exec(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        sess_v2.commit()
    JamaiSQLModel.metadata.create_all(
        create_engine(
            f"postgresql+psycopg://{config.db_v2_user}:{config.db_v2_password}@{config.db_v2_host}:{config.db_v2_port}/{config.db_v2_db}",
            poolclass=NullPool,
        )
    )
    import asyncio

    asyncio.run(init_db())


def main(config: Config):
    """
    Steps:
    - Create user "0" in new V2
    - Migrate all users from V1 to new V2
    - Migrate internal organizations from old V2 to new V2
    - Migrate all organizations from V1 to new V2
    - Migrate keys from V1 to new V2
    - Migrate S3
    """
    if config.verbose:
        logger.info(f"Connecting to database: {config.db_v1_path}")
    try:
        ### --- From V1 to new V2 --- ###
        # OSS has no user in V1
        # tables that v2 has in a fresh start.
        #  ModelConfig: empty
        #  Deployment: empty
        #  PricePlan: 1 entry, free plan
        #  Organization: 2 entries, org 0 and org template
        #  User: 1 entry, user 0 (user@local.com)
        #  OrgMember: 2 entries, user 0 in org 0 and org template
        #  Project: empty
        #  ProjectMember: empty
        maybe_reset_db(config)

        ### --- From V1 to new V2 --- ###
        # There should only be 1 org in v1: default will be mapped to 0
        migrate_organization(config, "default", org_id_dst="0")

    except Exception as e:
        logger.error(f"Error: {repr(e)}")
        raise


def main_cli():
    config = Config.parse_args()
    logger.configure(
        handlers=[
            {
                "sink": sys.stderr,
                "level": "INFO",
                "serialize": False,
                "backtrace": False,
                "diagnose": True,
                "enqueue": True,
                "catch": True,
            },
            {
                "sink": Path(config.cache_dir) / "migration.log",
                "level": "INFO",
                "serialize": False,
                "backtrace": False,
                "diagnose": True,
                "enqueue": True,
                "catch": True,
                "rotation": "50 MB",
                "delay": False,
                "watch": False,
            },
            {
                "sink": Path(config.cache_dir) / "migration-warnings.log",
                "level": "WARNING",
                "serialize": False,
                "backtrace": False,
                "diagnose": True,
                "enqueue": True,
                "catch": True,
                "rotation": "50 MB",
                "delay": False,
                "watch": False,
            },
        ]
    )
    main(config)


if __name__ == "__main__":
    main_cli()
