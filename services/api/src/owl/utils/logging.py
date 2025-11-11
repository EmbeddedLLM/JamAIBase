"""
Configure handlers and formats for application loggers.

https://gist.github.com/nkhitrov/a3e31cfcc1b19cba8e1b626276148c49
"""

import inspect
import logging
import sys
from typing import Any

import httpx
from loguru import logger

from owl.client import VictoriaMetricsAsync
from owl.configs import ENV_CONFIG
from owl.types import LogQueryResponse
from owl.utils.io import json_loads


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
        # Get corresponding Loguru level if it exists.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def replace_logging_handlers(names: list[str], include_submodules: bool = True):
    """
    Replaces logging handlers with `InterceptHandler` for use with `loguru`.
    """
    if not isinstance(names, (list, tuple)):
        raise TypeError("`names` should be a list of str.")
    logger_names = []
    for name in names:
        name = name.lower()
        if include_submodules:
            logger_names += [
                n for n in logging.root.manager.loggerDict if n.lower().startswith(name)
            ]
        else:
            logger_names += [n for n in logging.root.manager.loggerDict if n.lower() == name]
    logger.info(f"Replacing logger handlers: {logger_names}")
    loggers = (logging.getLogger(n) for n in logger_names)
    for lgg in loggers:
        lgg.handlers = [InterceptHandler()]
    # logging.getLogger(name).handlers = [InterceptHandler()]


def suppress_logging_handlers(names: list[str], include_submodules: bool = True):
    """
    Suppresses logging handlers by setting them to `WARNING`.
    """
    if not isinstance(names, (list, tuple)):
        raise TypeError("`names` should be a list of str.")
    logger_names = []
    for name in names:
        name = name.lower()
        if include_submodules:
            logger_names += [
                n for n in logging.root.manager.loggerDict if n.lower().startswith(name)
            ]
        else:
            logger_names += [n for n in logging.root.manager.loggerDict if n.lower() == name]
    logger.info(f"Suppressing logger handlers: {logger_names}")
    loggers = (logging.getLogger(n) for n in logger_names)
    for lgg in loggers:
        lgg.setLevel("ERROR")


def setup_logger_sinks(log_filepath: str | None = f"{ENV_CONFIG.log_dir}/owl.log"):
    logger.remove()
    logger.level("INFO", color="")
    handlers = [
        {
            "sink": sys.stderr,
            "level": "INFO",
            "serialize": False,
            "backtrace": False,
            "diagnose": True,
            "enqueue": True,
            "catch": True,
        },
    ]
    if log_filepath is not None:
        handlers.append(
            {
                "sink": log_filepath,
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
        )
    logger.configure(handlers=handlers)


class VictoriaLogClient(VictoriaMetricsAsync):
    __QUERY_ENDPOINT = "/select/logsql/query"

    def _construct_query(
        self,
        time: str = None,
        severity: str = None,
        org_ids: list[str] = None,
        proj_ids: list[str] = None,
        user_ids: list[str] = None,
    ) -> str:
        """
        Constructs a query string for the VictoriaMetrics log query.

        Args:
            time (str, optional): The time range for the query defaults to 5m.
            severity (str, optional): The severity level of the logs.
            org_ids (list[str], optional): organization IDs.
            proj_ids (list[str], optional): project IDs.
            user_ids (list[str], optional): user IDs.

        Returns:
            str: A query string starting with '_time:5m' if no parameters are provided,
                otherwise a string of key:value pairs joined by ' AND '.
        """

        query_params = {
            "_time": time or "5m",
            "severity": severity.upper() if severity else None,
        }

        query_parts = [
            f"{key}:{value}" for key, value in query_params.items() if value is not None
        ]

        if org_ids:
            org_values = " OR ".join(org_ids)
            query_parts.append(f"org_id:({org_values})")

        if proj_ids:
            proj_values = " OR ".join(proj_ids)
            query_parts.append(f"proj_id:({proj_values})")

        if user_ids:
            user_values = " OR ".join(user_ids)
            query_parts.append(f"user_id:({user_values})")

        return " AND ".join(query_parts)

    async def query_logs(
        self,
        time: str = None,
        severity: str = None,
        org_ids: list[str] = None,
        proj_ids: list[str] = None,
        user_ids: list[str] = None,
    ) -> LogQueryResponse:
        """
        Queries logs from VictoriaMetrics using the constructed query parameters.

        Args:
            time (str, optional): The time range for the query.
            severity (str, optional): The severity level of the logs.
            org_ids (list[str], optional): organization IDs.
            proj_ids (list[str], optional): project IDs.
            user_ids (list[str], optional): user IDs.

        Returns:
            LogQueryResponse: A list of JSON objects representing the logs.
        """
        params = {"query": self._construct_query(time, severity, org_ids, proj_ids, user_ids)}
        response = await self._fetch_victoria_metrics(self.__QUERY_ENDPOINT, params)
        return LogQueryResponse(logs=self._process_logs(response))

    def _process_logs(self, response: httpx.Response) -> list[dict[str, Any]]:
        """
        Processes the HTTP response from VictoriaMetrics and extracts log entries.

        Args:
            response (httpx.Response): The HTTP response object.

        Returns:
            list: A list of JSON objects parsed from the response.
        """
        return [json_loads(line) for line in response.iter_lines() if line]
