"""
Configure handlers and formats for application loggers.

https://gist.github.com/nkhitrov/a3e31cfcc1b19cba8e1b626276148c49
"""

import inspect
import logging

from loguru import logger


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
        if include_submodules:
            logger_names += [n for n in logging.root.manager.loggerDict if n.startswith(name)]
        else:
            logger_names += [n for n in logging.root.manager.loggerDict if n == name]
    logger.info(f"Replacing logger handlers: {logger_names}")
    loggers = (logging.getLogger(n) for n in logger_names)
    for lgg in loggers:
        lgg.handlers = [InterceptHandler()]
    # logging.getLogger(name).handlers = [InterceptHandler()]


def setup_logger_sinks():
    import sys
    from copy import deepcopy

    from owl.config import LOGS

    logger.remove()
    log_cfg = deepcopy(LOGS)
    stderr_cfg = log_cfg.pop("stderr", None)
    if stderr_cfg is not None:
        logger.add(sys.stderr, **stderr_cfg)
    for path, cfg in log_cfg.items():
        logger.add(sink=path, **cfg)
        logger.info(f"Writing logs to: {path}")
