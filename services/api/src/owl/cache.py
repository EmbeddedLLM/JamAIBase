from typing import Any

import redis
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    owl_redis_host: str = "dragonfly"
    owl_workers: int = 2


CONFIG = Config()


class Cache:
    def __init__(self):
        self.use_redis = CONFIG.owl_workers > 1
        if self.use_redis:
            logger.info("Using Redis as cache.")
            self._redis = redis.Redis(host=CONFIG.owl_redis_host, port=6379, db=0)
        else:
            logger.info("Using in-memory dict as cache.")
        self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def set(self, key: str, value: str) -> None:
        self[key] = value

    def purge(self):
        if self.use_redis:
            for key in self._redis.scan_iter("<owl>*"):
                self._redis.delete(key)
        else:
            self._data = {}

    def __setitem__(self, key: str, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"`value` must be a str, received: {type(value)}")
        if not (isinstance(key, str) and key.startswith("<owl>")):
            raise ValueError(f'`key` must be a str that starts with "<owl>", received: {key}')
        if self.use_redis:
            self._redis.set(key, value)
        else:
            self._data[key] = value

    def __getitem__(self, key: str) -> str:
        if self.use_redis:
            item = self._redis.get(key)
            if item is None:
                raise KeyError(key)
            return item.decode("utf-8")
        else:
            return self._data[key]

    def __delitem__(self, key) -> None:
        if self.use_redis:
            self._redis.delete(key)
        else:
            if key in self._data:
                del self._data[key]

    def __contains__(self, key) -> bool:
        if self.use_redis:
            self._redis.exists(key)
        else:
            key in self._data

    def __repr__(self) -> str:
        if self.use_redis:
            _data = {key.decode("utf-8"): self[key] for key in self._redis.scan_iter("<owl>*")}
        else:
            _data = self._data
        return repr(_data)


CACHE = Cache()
