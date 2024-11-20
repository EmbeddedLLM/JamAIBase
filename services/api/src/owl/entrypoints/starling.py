"""
Starling server.

```shell
$ celery -A owl.entrypoints.starling worker --loglevel=info --max-memory-per-child 976562 --autoscale=4,2
$ celery -A owl.entrypoints.starling beat --loglevel=info
(Optional) $ celery -A owl.entrypoints.starling flower --loglevel=info
```
"""

import os

from celery import Celery
from celery.schedules import crontab
from loguru import logger

from owl.configs.manager import CONFIG, ENV_CONFIG
from owl.utils.logging import (
    replace_logging_handlers,
    setup_logger_sinks,
    suppress_logging_handlers,
)

# Maybe purge Redis data
if ENV_CONFIG.owl_cache_purge:
    CONFIG.purge()

SCHEDULER_DB = f"{ENV_CONFIG.owl_db_dir}/_scheduler"
logger.enable("")
setup_logger_sinks(f"{ENV_CONFIG.owl_log_dir}/starling.log")
replace_logging_handlers(["uvicorn.access"], False)
suppress_logging_handlers(["litellm", "openmeter", "azure"], True)


try:
    if not os.path.exists(SCHEDULER_DB):
        os.makedirs(SCHEDULER_DB, exist_ok=True)
        logger.info(f"Created scheduler directory at {SCHEDULER_DB}")
    else:
        logger.info(f"Scheduler directory already exists at {SCHEDULER_DB}")
except Exception as e:
    logger.error(f"Error creating scheduler directory: {e}")


# Set up Celery
app = Celery("tasks", broker=f"redis://{ENV_CONFIG.owl_redis_host}:{ENV_CONFIG.owl_redis_port}/0")

# Configure Celery
app.conf.update(
    result_backend=f"redis://{ENV_CONFIG.owl_redis_host}:{ENV_CONFIG.owl_redis_port}/0",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=36000,
    timezone="UTC",
    enable_utc=True,
    beat_schedule_filename=os.path.join(SCHEDULER_DB, "celerybeat-schedule"),
)

# Load task modules
app.conf.imports = [
    "owl.tasks.genitor",
    "owl.tasks.storage",
]

# Configure the scheduler
app.conf.beat_schedule = {}

# Add periodic storage update task if service_key_plain is not empty
if ENV_CONFIG.service_key_plain != "":
    app.conf.beat_schedule["periodic-storage-update"] = {
        "task": "owl.tasks.storage.periodic_storage_update",
        "schedule": crontab(minute=f"*/{ENV_CONFIG.owl_compute_storage_period_min}"),
    }

# Add Lance-related tasks
app.conf.beat_schedule.update(
    {
        "lance-periodic-reindex": {
            "task": "owl.tasks.storage.lance_periodic_reindex",
            "schedule": crontab(minute=f"*/{max(1,ENV_CONFIG.owl_reindex_period_sec//60)}"),
        },
        "lance-periodic-optimize": {
            "task": "owl.tasks.storage.lance_periodic_optimize",
            "schedule": crontab(minute=f"*/{max(1,ENV_CONFIG.owl_optimize_period_sec//60)}"),
        },
    }
)

# Check if S3-related environment variables are present and non-empty
if all(
    getattr(ENV_CONFIG, attr, "")  # Use getattr to safely access attributes
    for attr in [
        "s3_endpoint",
        "s3_access_key_id",
        "s3_secret_access_key",
        "s3_backup_bucket_name",
    ]
):
    logger.info("S3 Backup tasks has been configured.")
    app.conf.beat_schedule.update(
        {
            "backup-to-s3": {
                "task": "owl.tasks.genitor.backup_to_s3",
                "schedule": crontab(minute="0", hour="*"),
            },
            "s3-cleanup": {
                "task": "owl.tasks.genitor.s3_cleanup",
                "schedule": crontab(minute="0", hour="*/24"),
            },
        }
    )
else:
    logger.info("S3 Backup tasks is not configured.")
