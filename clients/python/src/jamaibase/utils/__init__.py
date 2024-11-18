from asyncio.coroutines import iscoroutine
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Awaitable, Callable, Generator, TypeVar

R = TypeVar("R")


async def run(fn: Callable[..., R | Awaitable[R]], *args: Any, **kwargs: Any) -> R:
    ret = fn(*args, **kwargs)
    if isinstance(ret, Generator):
        return [item for item in ret]
    if iscoroutine(ret):
        ret = await ret
    if isinstance(ret, AsyncGenerator):
        ret = [item async for item in ret]
        return ret
    else:
        return ret


def datetime_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
