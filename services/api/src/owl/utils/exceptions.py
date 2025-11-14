from functools import partial, wraps
from inspect import iscoroutinefunction
from typing import Any, Callable, TypeVar, overload

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from loguru import logger
from sqlalchemy.exc import IntegrityError

# Import from jamaibase for use within owl
from jamaibase.utils.exceptions import (  # noqa: F401
    AuthorizationError,
    BadInputError,
    BaseTierCountError,
    ContextOverflowError,
    ExternalAuthError,
    ForbiddenError,
    InsufficientCreditsError,
    JamaiException,
    MethodNotAllowedError,
    ModelCapabilityError,
    ModelOverloadError,
    NoTierError,
    RateLimitExceedError,
    ResourceExistsError,
    ResourceNotFoundError,
    ServerBusyError,
    UnavailableError,
    UnexpectedError,
    UnsupportedMediaTypeError,
    UpgradeTierError,
    UpStreamError,
    docstring_message,
)

F = TypeVar("F", bound=Callable[..., Any])


@overload
def handle_exception(
    func: F,
    *,
    handler: Callable[..., Any] | None = None,
) -> F: ...


@overload
def handle_exception(
    *,
    handler: Callable[..., Any] | None = None,
) -> Callable[[F], F]: ...


def handle_exception(
    func: F | None = None,
    *,
    handler: Callable[..., Any] | None = None,
) -> Callable[[F], F] | F:
    """
    A decorator to handle exceptions for both synchronous and asynchronous functions.
    Its main purpose is to:
    - Produce shorter traceback (160 vs 500 lines) upon unexpected errors (such as `ValueError`).
    - Transform certain error classes, for example `IntegrityError` -> `ResourceExistsError`.

    It also allows you to specify a custom exception handler function.
    The handler function should accept a single positional argument (the exception instance)
    and all keyword arguments passed to the decorated function.

    Note that if a handler is provided, you are responsible to re-raise the exception if desired.

    Args:
        func (F | None): The function to be decorated. This can be either a synchronous or
            asynchronous function. When used as a decorator, leave this unset. Defaults to `None`.
        handler (Callable[..., None] | None): A custom exception handler function.
            The handler function should accept a positional argument (the exception instance)
            followed by all arguments passed to the decorated function.

    Returns:
        func (Callable[[F], F] | F): The decorated function with exception handling applied.

    Raises:
        JamaiException: If `JamaiException` is raised.
        RequestValidationError: If `fastapi.exceptions.RequestValidationError` is raised.
        ResourceExistsError: If `sqlalchemy.exc.IntegrityError` indicates a unique constraint violation in the database.
        UnexpectedError: For all other exception.
    """

    def _default_handler(e: Exception, *args, **kwargs):
        if isinstance(e, JamaiException):
            raise
        elif isinstance(e, RequestValidationError):
            raise
        # elif isinstance(e, ValidationError):
        #     raise RequestValidationError(errors=e.errors()) from e
        elif isinstance(e, IntegrityError):
            err_mssg: str = e.args[0]
            err_mssgs = err_mssg.split("UNIQUE constraint failed:")
            if len(err_mssgs) > 1:
                constraint = err_mssgs[1].strip()
                raise ResourceExistsError(f'DB item "{constraint}" already exists.') from e
            else:
                raise UnexpectedError(f"{e.__class__.__name__}: {e}") from e
        else:
            request: Request | None = kwargs.get("request", None)
            mssg = f"Failed to run {func.__name__}"
            mssg = f"{e.__class__.__name__}: {e} - {mssg} - kwargs={kwargs}"
            if request:
                logger.error(f"{request.state.id} - {mssg}")
            else:
                logger.error(mssg)
            raise UnexpectedError(f"{e.__class__.__name__}: {e}") from e

    if handler is None:
        handler = _default_handler

    if iscoroutinefunction(func):

        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return handler(e, *args, **kwargs)

    else:

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return handler(e, *args, **kwargs)

    return partial(handle_exception, handler=handler) if func is None else wrapper
