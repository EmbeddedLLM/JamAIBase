import functools
from typing import Any, Type

import numpy as np


def docstring_message(cls):
    """
    Decorates an exception to make its docstring its default message.
    https://stackoverflow.com/a/66491013
    """
    # Must use cls_init name, not cls.__init__ itself, in closure to avoid recursion
    cls_init = cls.__init__

    @functools.wraps(cls.__init__)
    def wrapped_init(self, msg=cls.__doc__, *args, **kwargs):
        cls_init(self, msg, *args, **kwargs)

    cls.__init__ = wrapped_init
    return cls


def check_type(obj: Any, clss: tuple[Type] | Type, mssg: str) -> None:
    if not isinstance(obj, clss):
        raise TypeError(f"{mssg} Received: {type(obj)}")


def check_iterable_element_type(obj: Any, clss: tuple[Type] | Type, mssg: str) -> None:
    if not all(isinstance(o, clss) for o in obj):
        raise TypeError(mssg)


def check_xy_arr(obj: Any, name: str):
    if not (isinstance(obj, (list, np.ndarray)) and len(obj) == 2):
        raise ValueError(f"{name} must be a list or `np.ndarray` with len == 2, received: {obj}")


def check_xyz_arr(obj: Any, name: str):
    if not (isinstance(obj, (list, np.ndarray)) and len(obj) == 3):
        raise ValueError(f"{name} must be a list or `np.ndarray` with len == 3, received: {obj}")


@docstring_message
class OwlException(Exception):
    """Generic owl exception for easy error handling."""

    pass


@docstring_message
class TableSchemaFixedError(OwlException):
    """Table schema cannot be modified."""


@docstring_message
class ResourceExistsError(OwlException):
    """Resource with the specified name already exists."""


@docstring_message
class ResourceNotFoundError(OwlException):
    """Resource with the specified name cannot be found."""


@docstring_message
class ContextOverflowError(OwlException):
    """Model's context length has been exceeded."""


@docstring_message
class UpgradeTierError(OwlException):
    """You have exhausted the allocations of your subscribed tier. Please upgrade."""


@docstring_message
class InsufficientCreditsError(OwlException):
    """Please ensure that you have sufficient credits."""
