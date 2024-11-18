"""
Configure handlers and formats for application loggers.

https://gist.github.com/nkhitrov/a3e31cfcc1b19cba8e1b626276148c49
"""

import inspect
import logging
import sys

from loguru import logger

from owl.configs.manager import ENV_CONFIG


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


def setup_logger_sinks(log_filepath: str = f"{ENV_CONFIG.owl_log_dir}/owl.log"):
    logger.remove()
    logger.level("INFO", color="")
    logger.configure(
        handlers=[
            {
                "sink": sys.stderr,
                "level": "INFO",
                "serialize": False,
                "backtrace": False,
                "diagnose": True,
                "enqueue": True,
                "catch": True,
            },
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
        ],
    )
