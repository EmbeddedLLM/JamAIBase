import time
from asyncio.coroutines import iscoroutine
from typing import Any, AsyncGenerator, Awaitable, Callable, Generator, TypeVar

import numpy as np
from uuid_extensions import uuid7str as _uuid7_draft2_str
from uuid_utils import uuid7 as _uuid7

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


def get_non_empty(mapping: dict[str, Any], key: str, default: Any):
    value = mapping.get(key, None)
    return value if value else default


def uuid7_draft2_str(prefix: str = "") -> str:
    return f"{prefix}{_uuid7_draft2_str()}"


def uuid7_str(prefix: str = "") -> str:
    return f"{prefix}{_uuid7()}"


def get_ttl_hash(seconds: int = 3600) -> int:
    """Return the same value within `seconds` time period"""
    return round(time.time() / max(1, seconds))


def mask_string(x: str | None, *, include_len: bool = True) -> str | None:
    if x is None or x == "":
        return x
    str_len = len(x)
    if str_len < 4:
        return f"{'*' * str_len} ({str_len=})"
    visible_len = min(100, str_len // 5)
    x = f"{x[:visible_len]}***{x[-visible_len:]}"
    return f"{x} ({str_len=})" if include_len else x


def mask_content(x: str | list | dict | np.ndarray | Any) -> str | list | dict | None:
    if isinstance(x, str):
        return mask_string(x)
    if isinstance(x, list):
        return [mask_content(v) for v in x]
    if isinstance(x, dict):
        return {k: mask_content(v) for k, v in x.items()}
    if isinstance(x, np.ndarray):
        return f"array(shape={x.shape}, dtype={x.dtype})"
    return None


def merge_dict(d: dict | Any, update: dict | Any):
    if isinstance(d, dict) and isinstance(update, dict):
        for k, v in update.items():
            d[k] = merge_dict(d.get(k, {}), v)
        return d
    return update


def mask_dict(value: dict[str, str | Any]) -> dict[str, str]:
    return {k: "***" if v else v for k, v in value.items()}
