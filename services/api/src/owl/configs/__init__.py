import os
from os.path import join

from celery import Celery

from owl.utils.cache import Cache

try:
    from owl.configs.cloud import EnvConfig
except ImportError:
    from owl.configs.oss import EnvConfig

ENV_CONFIG = EnvConfig()
CACHE = Cache(
    redis_url=f"redis://{ENV_CONFIG.redis_host}:{ENV_CONFIG.redis_port}/1",
    clickhouse_buffer_key=ENV_CONFIG.clickhouse_buffer_key,
)


celery_app = Celery("tasks", broker=f"redis://{ENV_CONFIG.redis_host}:{ENV_CONFIG.redis_port}/0")

# Configure Celery
CELERY_SCHEDULER_DB = "_scheduler"
os.makedirs(CELERY_SCHEDULER_DB, exist_ok=True)
celery_app.conf.update(
    result_backend=f"redis://{ENV_CONFIG.redis_host}:{ENV_CONFIG.redis_port}/0",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=36000,
    # TODO: Update to use DB via sqlalchemy-celery-beat
    beat_schedule_filename=join(CELERY_SCHEDULER_DB, "celerybeat-schedule"),
)
