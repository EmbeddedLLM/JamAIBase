from functools import wraps
from typing import Any


def docstring_message(cls):
    """
    Decorates an exception to make its docstring its default message.
    https://stackoverflow.com/a/66491013
    """
    # Must use cls_init name, not cls.__init__ itself, in closure to avoid recursion
    cls_init = cls.__init__

    @wraps(cls.__init__)
    def wrapped_init(self, msg=cls.__doc__, *args, **kwargs):
        cls_init(self, msg, *args, **kwargs)

    cls.__init__ = wrapped_init
    return cls


@docstring_message
class JamaiException(Exception):
    """Base exception class for Jamai errors."""


@docstring_message
class UpStreamError(JamaiException):
    """One or more upstream columns errored out."""


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
    """Your organization has exhausted the allocations of your subscribed plan. Please upgrade or top up credits."""


@docstring_message
class NoTierError(UpgradeTierError):
    """Your organization has not subscribed to any plan. Please subscribe in Organization Billing Settings."""


@docstring_message
class BaseTierCountError(UpgradeTierError):
    """You can have only one organization with Free Plan. Please upgrade."""


@docstring_message
class InsufficientCreditsError(JamaiException):
    """Your organization has exhausted your credits. Please top up."""


@docstring_message
class ResourceNotFoundError(JamaiException):
    """Resource with the specified name is not found."""


@docstring_message
class ResourceExistsError(JamaiException):
    """Resource with the specified name already exists."""


@docstring_message
class UnsupportedMediaTypeError(JamaiException):
    """This file type is unsupported."""


@docstring_message
class BadInputError(JamaiException):
    """Your input is invalid."""


@docstring_message
class ModelCapabilityError(BadInputError):
    """No model has the specified capabilities."""


@docstring_message
class TableSchemaFixedError(JamaiException):
    """Table schema cannot be modified."""


@docstring_message
class ContextOverflowError(JamaiException):
    """Model's context length has been exceeded."""


@docstring_message
class UnexpectedError(JamaiException):
    """We ran into an unexpected error."""


@docstring_message
class RateLimitExceedError(JamaiException):
    """The rate limit is exceeded."""

    def __init__(
        self,
        *args,
        limit: int,
        remaining: int,
        reset_at: int,
        used: int | None = None,
        retry_after: int | None = None,
        meta: dict[str, Any] | None = None,
    ):
        super().__init__(*args)
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
        self.used = used
        self.retry_after = retry_after
        self.meta = meta


@docstring_message
class UnavailableError(JamaiException):
    """The requested functionality is unavailable."""


@docstring_message
class ServerBusyError(JamaiException):
    """The server is busy."""


@docstring_message
class ModelOverloadError(JamaiException):
    """The model is overloaded."""


@docstring_message
class MethodNotAllowedError(JamaiException):
    """Method is not allowed."""
