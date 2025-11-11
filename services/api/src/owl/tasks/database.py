import asyncio

from owl.configs import celery_app
from owl.utils.billing import CLICKHOUSE_CLIENT


@celery_app.task
def run_periodic_flush_buffer():
    """
    Flush redis buffer to clickhouse.
    """
    asyncio.get_event_loop().run_until_complete(CLICKHOUSE_CLIENT.flush_buffer())
