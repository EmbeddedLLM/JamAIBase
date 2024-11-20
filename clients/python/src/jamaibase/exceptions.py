import functools
from typing import Any

from pydantic import ValidationError
from pydantic_core import InitErrorDetails


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


def make_validation_error(
    exception: Exception,
    *,
    object_name: str = "",
    loc: tuple = (),
    input_value: Any = None,
) -> ValidationError:
    return ValidationError.from_exception_data(
        object_name,
        line_errors=[
            InitErrorDetails(
                type="value_error",
                loc=loc,
                input=input_value,
                ctx={"error": exception},
            )
        ],
    )


@docstring_message
class JamaiException(RuntimeError):
    """Base exception class for JamAIBase errors."""

    pass


@docstring_message
class AuthorizationError(JamaiException):
    """You do not have the correct credentials."""


@docstring_message
class ExternalAuthError(JamaiException):
    """Authentication with external provider failed."""


@docstring_message
class ForbiddenError(JamaiException):
    """You do not have access to this resource."""


@docstring_message
class UpgradeTierError(JamaiException):
    """You have exhausted the allocations of your subscribed tier. Please upgrade."""


@docstring_message
class InsufficientCreditsError(JamaiException):
    """Please ensure that you have sufficient credits."""


@docstring_message
class ResourceNotFoundError(JamaiException):
    """Resource with the specified name is not found."""


@docstring_message
class ResourceExistsError(JamaiException):
    """Resource with the specified name already exists."""


@docstring_message
class UnsupportedMediaTypeError(JamaiException):
    """This file type is unsupported."""

    pass


@docstring_message
class BadInputError(JamaiException):
    """Your input is invalid."""


@docstring_message
class TableSchemaFixedError(JamaiException):
    """Table schema cannot be modified."""


@docstring_message
class ContextOverflowError(JamaiException):
    """Model's context length has been exceeded."""


@docstring_message
class UnexpectedError(JamaiException):
    """We ran into an unexpected error."""

    pass


@docstring_message
class ServerBusyError(JamaiException):
    """The server is busy."""

    pass
