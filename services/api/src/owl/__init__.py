from loguru import logger

from owl.version import __version__

logger.disable("owl")
__all__ = ["__version__"]
