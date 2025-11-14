from contextlib import asynccontextmanager, suppress
from random import random
from typing import Any, AsyncGenerator, Type, TypeVar

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
        self._redis_async = RedisAsync.from_url(**self._redis_kwargs)
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
        await self._redis_async.aclose()

    async def get(self, key: str) -> str | None:
        return await self._redis_async.get(key)

    async def set(self, key: str, value: str, **kwargs) -> None:
        if not isinstance(value, str):
            raise TypeError(f"`value` must be a str, received: {type(value)}")
        await self._redis_async.set(key, value, **kwargs)

    async def delete(self, key: str) -> None:
        await self._redis_async.delete(key)

    async def exists(self, *keys: str) -> int:
        return await self._redis_async.exists(*keys)

    @asynccontextmanager
    async def alock(
        self,
        key: str,
        blocking: bool = True,
        expire: float = 60.0,
    ) -> AsyncGenerator[bool, None]:
        lock = AIORedlock(
            key=key,
            masters={self._redis_async},
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
        await self._redis_async.rpush(self.clickhouse_buffer_key, usage.model_dump_json())
        await self._redis_async.incrby(
            self.clickhouse_buffer_key + "_count", usage.total_usage_events
        )

    # def retrieve_usage_buffer(self) -> list[UsageData]:
    #     return [
    #         UsageData.model_validate_json(data)
    #         for data in self._redis.lrange(self.clickhouse_buffer_key, 0, -1)
    #     ]

    async def get_usage_buffer_count(self) -> int:
        return int(await self._redis_async.get(self.clickhouse_buffer_key + "_count") or 0)

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
        return await self._redis_async.set(
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

        prog = await self._redis_async.get(key)
        if response_model is None:
            return json_loads(prog) if prog else prog
        if prog:
            return response_model.model_validate_json(prog)
        return response_model(key=key)

    def _ex_jitter(self) -> int:
        # Jitter to prevent cache stampede
        return int(self.cache_expiration * random() / 2)

    async def clear_all_async(self) -> None:
        pipe = self._redis_async.pipeline()
        for prefix in ["user", "organization", "project", "models"]:
            async for key in self._redis_async.scan_iter(match=f"{prefix}:*"):
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
