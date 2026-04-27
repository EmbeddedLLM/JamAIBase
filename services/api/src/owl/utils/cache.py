import asyncio
from contextlib import asynccontextmanager, suppress
from random import random
from time import time_ns
from typing import Any, AsyncGenerator, Type, TypeVar

from loguru import logger
from pottery import AIORedlock, ReleaseUnlockedLock
from redis import Redis
from redis.asyncio import Redis as RedisAsync
from redis.backoff import EqualJitterBackoff
from redis.exceptions import ConnectionError, TimeoutError
from redis.retry import Retry
from sqlmodel.ext.asyncio.session import AsyncSession

from owl.types import Organization_, Progress, UsageData

ProgressType = TypeVar("ProgressType", bound=Progress)


class Cache:
    def __init__(
        self,
        *,
        redis_url: str,
        clickhouse_buffer_key: str,
        cache_expiration: int = 5 * 60,  # 5 minutes
    ):
        self._redis_kwargs = dict(
            # url=f"redis://[[username]:[password]]@{ENV_CONFIG.redis_host}:{ENV_CONFIG.redis_port}/1",
            url=redis_url,
            # https://redis.io/kb/doc/22wxq63j93/how-to-manage-client-reconnections-in-case-of-errors-with-redis-py
            retry=Retry(EqualJitterBackoff(cap=10, base=1), 5),
            retry_on_error=[ConnectionError, TimeoutError, ConnectionResetError],
            health_check_interval=15,
            decode_responses=True,
        )
        self._redis = Redis.from_url(**self._redis_kwargs)
        self._redis_async: RedisAsync | None = None
        self._redis_async_loop: asyncio.AbstractEventLoop | None = None
        self.clickhouse_buffer_key = clickhouse_buffer_key
        self.cache_expiration = int(cache_expiration)
        # try:
        #     self._redis.ping()
        # except ConnectionError as e:
        #     logger.error(f"Failed to connect to Redis: {repr(e)}")
        #     raise

    def __getitem__(self, key: str) -> str | None:
        """
        Getter method.
        ```
        cache = Cache(...)
        value = cache["key"]
        ```

        Args:
            key (str): Key.

        Returns:
            value (str | None): Value.
        """
        return self._redis.get(key)

    def __setitem__(self, key: str, value: str) -> None:
        """
        Setter method.
        ```
        cache = Cache(...)
        cache["key"] = value
        ```

        Args:
            key (str): Key.
            value (str): Value.
        """
        if not isinstance(value, str):
            raise TypeError(f"`value` must be a str, received: {type(value)}")
        self._redis.set(key, value)

    def __delitem__(self, key) -> None:
        """
        Delete method.
        ```
        cache = Cache(...)
        del cache["key"]
        ```

        Args:
            key (str): Key.
        """
        self._redis.delete(key)

    def __contains__(self, key) -> bool:
        self._redis.exists(key)

    def purge(self):
        self._redis.flushdb()

    async def aclose(self):
        self._redis.close()
        if self._redis_async is not None:
            await self._redis_async.aclose()
            self._redis_async = None
            self._redis_async_loop = None

    async def _aredis(self) -> RedisAsync:
        # redis.asyncio connections are bound to the event loop that created them.
        # Tests and background helpers can use this process-global CACHE from
        # different loops, so recreate the async client when the loop changes.
        loop = asyncio.get_running_loop()
        if (
            self._redis_async is None
            or self._redis_async_loop is None
            or self._redis_async_loop is not loop
            or self._redis_async_loop.is_closed()
        ):
            if self._redis_async is not None and self._redis_async_loop is not None:
                # Closing transports owned by an already-closed loop can raise
                # "Event loop is closed"; in that case just drop the stale client.
                if not self._redis_async_loop.is_closed():
                    try:
                        await self._redis_async.aclose()
                    except Exception as e:
                        logger.warning(f"Failed to close Redis async client: {repr(e)}")
            self._redis_async = RedisAsync.from_url(**self._redis_kwargs)
            self._redis_async_loop = loop
        return self._redis_async

    async def get(self, key: str) -> str | None:
        return await (await self._aredis()).get(key)

    async def set(self, key: str, value: str, **kwargs):
        if not isinstance(value, str):
            raise TypeError(f"`value` must be a str, received: {type(value)}")
        return await (await self._aredis()).set(key, value, **kwargs)

    async def delete(self, key: str) -> None:
        await (await self._aredis()).delete(key)

    async def exists(self, *keys: str) -> int:
        return await (await self._aredis()).exists(*keys)

    async def expire(self, key: str, seconds: int) -> bool:
        return await (await self._aredis()).expire(key, seconds)

    async def acquire_lock_value(self, key: str, value: str, *, ex: int) -> bool:
        return bool(await self.set(key, value, ex=ex, nx=True))

    async def get_lock_value(self, key: str) -> str | None:
        return await self.get(key)

    async def release_lock_value(self, key: str, value: str) -> bool:
        redis = await self._aredis()
        released = await redis.eval(
            """
            if redis.call("GET", KEYS[1]) == ARGV[1] then
                return redis.call("DEL", KEYS[1])
            end
            return 0
            """,
            1,
            key,
            value,
        )
        return bool(released)

    async def refresh_lock_value(self, key: str, value: str, *, ex: int) -> bool:
        redis = await self._aredis()
        refreshed = await redis.eval(
            """
            if redis.call("GET", KEYS[1]) == ARGV[1] then
                return redis.call("EXPIRE", KEYS[1], ARGV[2])
            end
            return 0
            """,
            1,
            key,
            value,
            ex,
        )
        return bool(refreshed)

    async def add_recent_progress_key(
        self,
        index_key: str,
        progress_key: str,
        *,
        ttl_sec: int,
    ) -> None:
        now_ns = time_ns()
        redis = await self._aredis()
        await redis.zremrangebyscore(
            index_key,
            "-inf",
            now_ns - (ttl_sec * 1_000_000_000),
        )
        await redis.zadd(index_key, {progress_key: now_ns}, nx=True)
        await redis.expire(index_key, ttl_sec)

    async def remove_recent_progress_key(
        self,
        index_key: str,
        progress_key: str,
    ) -> None:
        await (await self._aredis()).zrem(index_key, progress_key)

    async def list_recent_progress_keys(
        self,
        index_key: str,
        *,
        ttl_sec: int,
    ) -> list[str]:
        now_ns = time_ns()
        redis = await self._aredis()
        await redis.zremrangebyscore(
            index_key,
            "-inf",
            now_ns - (ttl_sec * 1_000_000_000),
        )
        keys = await redis.zrevrange(index_key, 0, -1)
        keys = [key.decode() if isinstance(key, bytes) else key for key in keys]

        existing_keys: list[str] = []
        missing_keys: list[str] = []
        for key in keys:
            if await self.exists(key):
                existing_keys.append(key)
            else:
                missing_keys.append(key)
        if missing_keys:
            await redis.zrem(index_key, *missing_keys)
        if existing_keys:
            await redis.expire(index_key, ttl_sec)
        return existing_keys

    @asynccontextmanager
    async def alock(
        self,
        key: str,
        blocking: bool = True,
        expire: float = 60.0,
    ) -> AsyncGenerator[bool, None]:
        redis = await self._aredis()
        lock = AIORedlock(
            key=key,
            masters={redis},
            auto_release_time=max(1.0, expire),
        )
        lock_acquired = await lock.acquire(blocking=blocking)
        try:
            yield lock_acquired
        finally:
            if lock_acquired:
                with suppress(ReleaseUnlockedLock):
                    await lock.release()

    async def add_usage_to_buffer(self, usage: UsageData):
        redis = await self._aredis()
        await redis.rpush(self.clickhouse_buffer_key, usage.model_dump_json())
        await redis.incrby(self.clickhouse_buffer_key + "_count", usage.total_usage_events)

    # def retrieve_usage_buffer(self) -> list[UsageData]:
    #     return [
    #         UsageData.model_validate_json(data)
    #         for data in self._redis.lrange(self.clickhouse_buffer_key, 0, -1)
    #     ]

    async def get_usage_buffer_count(self) -> int:
        return int(await (await self._aredis()).get(self.clickhouse_buffer_key + "_count") or 0)

    # def reset_buffer_and_count(self):
    #     # Delete the buffer and count keys
    #     del self[self.clickhouse_buffer_key]
    #     del self[self.clickhouse_buffer_key + "_count"]

    @staticmethod
    def get_capacity_search_keys(deployment_id: str) -> dict[str, str]:
        queue_key = f"capacity_search_model_queue:{deployment_id}"
        active_key = f"capacity_search_model_active:{deployment_id}"
        queue_task_key = f"capacity_search_queue_task:{deployment_id}"
        active_task_key = f"capacity_search_active_task:{deployment_id}"
        return {
            "queue_key": queue_key,
            "active_key": active_key,
            "queue_task_key": queue_task_key,
            "active_task_key": active_task_key,
        }

    @staticmethod
    def get_capacity_search_cancellation_key(task_id: str) -> str:
        return f"capacity_search_cancel:{task_id}"

    async def set_progress(
        self,
        prog: Progress,
        ex: int = 240,
        nx: bool = False,
        **kwargs,
    ) -> bool | None:
        """
        Set progress data into Redis at key `prog.key`.

        Args:
            prog (Progress): Progress instance.
            ex (int, optional): Expiration time in seconds. Defaults to 240.
            nx (bool, optional): Set this key only if it does not exist. Defaults to False.

        Returns:
            response (bool | None): True if published or key is empty, otherwise None.
        """
        if not prog.key:
            return True
        # Returns True if set, None if not
        return await (await self._aredis()).set(
            prog.key,
            prog.model_dump_json(),
            ex=ex,
            nx=nx,
            **kwargs,
        )

    async def get_progress(
        self,
        key: str,
        response_model: Type[ProgressType] | None = Progress,
    ) -> ProgressType | dict[str, Any] | None:
        """
        Get progress data from Redis at key `key`.

        Args:
            key (str): Progress key.
            response_model (Type[ProgressType], optional): Response model. Defaults to `Progress`.

        Returns:
            response (ProgressType | dict[str, Any] | None): The progress data.
        """
        from owl.utils.io import json_loads

        prog = await (await self._aredis()).get(key)
        if response_model is None:
            return json_loads(prog) if prog else prog
        if prog:
            return response_model.model_validate_json(prog)
        return response_model(key=key)

    def _ex_jitter(self) -> int:
        # Jitter to prevent cache stampede
        return int(self.cache_expiration * random() / 2)

    async def clear_all_async(self) -> None:
        redis = await self._aredis()
        pipe = redis.pipeline()
        for prefix in ["user", "organization", "project", "models"]:
            async for key in redis.scan_iter(match=f"{prefix}:*"):
                pipe.delete(key)
        await pipe.execute()

    async def cache_organization_async(self, organization: Organization_) -> None:
        await self.set(
            f"organization:{organization.id}",
            Organization_.model_validate(organization).model_dump_json(),
            ex=self.cache_expiration + self._ex_jitter(),
        )

    async def get_organization_async(
        self,
        organization_id: str,
        session: AsyncSession,
    ) -> Organization_ | None:
        from owl.db.models import Organization

        if data := await self.get(f"organization:{organization_id}"):
            return Organization_.model_validate_json(data)
        organization = await session.get(Organization, organization_id)
        if organization is None:
            return None
        organization = Organization_.model_validate(organization)
        await self.cache_organization_async(organization)
        return organization

    async def clear_organization_async(self, organization_id: str) -> None:
        await self.delete(f"organization:{organization_id}")

    async def refresh_organization_async(
        self,
        organization_id: str,
        session: AsyncSession,
    ) -> Organization_ | None:
        await self.clear_organization_async(organization_id)
        return await self.get_organization_async(organization_id, session)
