import asyncio
import pathlib
from datetime import timedelta
from time import perf_counter

from celery import Celery
from filelock import FileLock, Timeout
from loguru import logger

from jamaibase import JamAI
from owl.billing import BillingManager
from owl.configs.manager import ENV_CONFIG
from owl.db.gen_table import GenerativeTable
from owl.protocol import TableType
from owl.utils.io import get_file_usage, get_storage_usage

logger.info(f"Using configuration: {ENV_CONFIG}")
client = JamAI(token=ENV_CONFIG.service_key_plain, timeout=60.0)

# Set up Celery
app = Celery("tasks", broker=f"redis://{ENV_CONFIG.owl_redis_host}:{ENV_CONFIG.owl_redis_port}/0")

# Configure Celery
app.conf.update(
    result_backend=f"redis://{ENV_CONFIG.owl_redis_host}:{ENV_CONFIG.owl_redis_port}/0",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

logger.info(f"Using configuration: {ENV_CONFIG}")


def _iter_all_tables(batch_size: int = 200):
    table_types = [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]
    db_dir = pathlib.Path(ENV_CONFIG.owl_db_dir)
    for org_dir in db_dir.iterdir():
        if not org_dir.is_dir() or not org_dir.name.startswith(("org_", "default")):
            continue
        for project_dir in org_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for table_type in table_types:
                table = GenerativeTable.from_ids(org_dir.name, project_dir.name, table_type)
                with table.create_session() as session:
                    offset, total = 0, 1
                    while offset < total:
                        metas, total = table.list_meta(
                            session,
                            offset=offset,
                            limit=batch_size,
                            remove_state_cols=True,
                            parent_id=None,
                        )
                        offset += batch_size
                        for meta in metas:
                            yield (
                                session,
                                table,
                                meta,
                                f"{project_dir}/{table_type}/{meta.id}",
                            )


@app.task
def periodic_storage_update():
    # Cloud client
    if ENV_CONFIG.is_oss:
        return

    lock = FileLock(f"{ENV_CONFIG.owl_db_dir}/periodic_storage_update.lock", blocking=False)
    try:
        t0 = perf_counter()
        with lock:
            file_usages = get_file_usage(ENV_CONFIG.owl_db_dir)
            db_usages = get_storage_usage(ENV_CONFIG.owl_db_dir)
            num_ok = num_skipped = num_failed = 0
            for org_id in db_usages:
                if not org_id.startswith("org_"):
                    continue
                db_usage_gib = db_usages[org_id]
                file_usage_gib = file_usages[org_id]
                try:
                    org = client.admin.backend.get_organization(org_id)
                    manager = BillingManager(
                        organization=org,
                        project_id="",
                        user_id="",
                        request=None,
                    )
                    manager.create_storage_events(db_usage_gib, file_usage_gib)
                    asyncio.get_event_loop().run_until_complete(manager.process_all())
                    num_ok += 1
                except Exception as e:
                    logger.warning((f"Storage usage update failed for {org_id}: {e}"))
                    num_failed += 1
            t = perf_counter() - t0
            logger.info(
                (
                    f"Periodic storage usage update completed (t={t:,.3f} s, "
                    f"{num_ok:,d} OK, {num_skipped:,d} skipped, {num_failed:,d} failed)."
                )
            )
    except Timeout:
        pass
    except Exception as e:
        logger.exception(f"Periodic storage usage update failed due to {e}")


@app.task
def lance_periodic_reindex():
    lock = FileLock(f"{ENV_CONFIG.owl_db_dir}/periodic_reindex.lock", timeout=0)
    try:
        with lock:
            t0 = perf_counter()
            num_ok = num_skipped = num_failed = 0
            for session, table, meta, table_path in _iter_all_tables():
                if session is None:
                    continue
                try:
                    reindexed = table.create_indexes(session, meta.id)
                    if reindexed:
                        num_ok += 1
                    else:
                        num_skipped += 1
                except Timeout:
                    logger.warning(f"Periodic Lance re-indexing skipped for table: {table_path}")
                    num_skipped += 1
                except Exception:
                    logger.exception(f"Periodic Lance re-indexing failed for table: {table_path}")
                    num_failed += 1
            t = perf_counter() - t0
        logger.info(
            (
                f"Periodic Lance re-indexing completed (t={t:,.3f} s, "
                f"{num_ok:,d} OK, {num_skipped:,d} skipped, {num_failed:,d} failed)."
            )
        )
    except Timeout:
        logger.info("Periodic Lance re-indexing skipped due to lock.")
    except Exception as e:
        logger.exception(f"Periodic Lance re-indexing failed due to {e}")


@app.task
def lance_periodic_optimize():
    lock = FileLock(f"{ENV_CONFIG.owl_db_dir}/periodic_optimization.lock", timeout=0)
    try:
        with lock:
            t0 = perf_counter()
            num_ok = num_skipped = num_failed = 0
            for _, table, meta, table_path in _iter_all_tables():
                done = True
                try:
                    if meta is None:
                        done = done and table.compact_files()
                        done = done and table.cleanup_old_versions(
                            older_than=timedelta(
                                minutes=ENV_CONFIG.owl_remove_version_older_than_mins
                            ),
                        )
                    else:
                        done = done and table.compact_files(meta.id)
                        done = done and table.cleanup_old_versions(
                            meta.id,
                            older_than=timedelta(
                                minutes=ENV_CONFIG.owl_remove_version_older_than_mins
                            ),
                        )
                    if done:
                        num_ok += 1
                    else:
                        num_skipped += 1
                except Timeout:
                    logger.warning(f"Periodic Lance optimization skipped for table: {table_path}")
                    num_skipped += 1
                except Exception:
                    logger.exception(f"Periodic Lance optimization failed for table: {table_path}")
                    num_failed += 1
            t = perf_counter() - t0
        logger.info(
            (
                f"Periodic Lance optimization completed (t={t:,.3f} s, "
                f"{num_ok:,d} OK, {num_skipped:,d} skipped, {num_failed:,d} failed)."
            )
        )
    except Timeout:
        logger.info("Periodic Lance optimization skipped due to lock.")
    except Exception as e:
        logger.exception(f"Periodic Lance optimization failed due to {e}")
