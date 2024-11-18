from functools import wraps
from inspect import iscoroutinefunction
from typing import Any, Callable, Type, TypeVar, overload

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from filelock import Timeout
from loguru import logger
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from jamaibase.exceptions import JamaiException, ResourceExistsError, UnexpectedError


def check_type(obj: Any, clss: tuple[Type] | Type, mssg: str) -> None:
    if not isinstance(obj, clss):
        raise TypeError(f"{mssg} Received: {type(obj)}")


F = TypeVar("F", bound=Callable[..., Any])


@overload
def handle_exception(
    func: F,
    *,
    failure_message: str = "",
) -> F: ...


@overload
def handle_exception(
    *,
    failure_message: str = "",
) -> Callable[[F], F]: ...


def handle_exception(
    func: F | None = None,
    *,
    failure_message: str = "",
    handler: Callable[..., Any] | None = None,
) -> Callable[[F], F] | F:
    # TODO: Add support for callable as "failure_message"
    """
    A decorator to handle exceptions for both synchronous and asynchronous functions.
    Its main purpose is to:
    - Provide more meaningful error messages for logging.
    - Transform certain error classes, for example `RequestValidationError` -> `ValidationError`.

    It also allows you to specify a custom exception handler function.
    The handler function should accept a single positional argument (the exception instance)
    and all keyword arguments passed to the decorated function.

    Note that if a handler is provided, you are responsible to re-raise the exception if desired.

    Args:
        func (F | None): The function to be decorated. This can be either a synchronous or
            asynchronous function. When used as a decorator, leave this unset. Defaults to `None`.
        failure_message (str): Optional message to be logged for timeout and unexpected exceptions. Defaults to "".
        handler (Callable[..., None] | None): A custom exception handler function.
            The handler function should accept a single positional argument (the exception instance)
            and all keyword arguments passed to the decorated function.

    Returns:
        func (Callable[[F], F] | F): The decorated function with exception handling applied.

    Raises:
        JamaiException: If the exception is of type JamaiException.
        RequestValidationError: If the exception is a FastAPI RequestValidationError.
        ValidationError: Wraps Pydantic ValidationError as RequestValidationError.
        ResourceExistsError: If an IntegrityError indicates a unique constraint violation in the database.
        UnexpectedError: For any other unhandled exceptions.
    """

    def decorator(fn: F) -> F:
        def _handle_exception(e: Exception, kwargs):
            try:
                if handler is not None:
                    return handler(e, **kwargs)
            except e.__class__:
                pass
            except Exception:
                logger.warning(f"Exception handler failed for exception: {e}")

            if isinstance(e, JamaiException):
                raise
            elif isinstance(e, RequestValidationError):
                raise
            elif isinstance(e, ValidationError):
                # Sometimes ValidationError is raised from additional checking code
                raise RequestValidationError(errors=e.errors()) from e
            elif isinstance(e, IntegrityError):
                err_mssg: str = e.args[0]
                err_mssg = err_mssg.split("UNIQUE constraint failed:")
                if len(err_mssg) > 1:
                    constraint = err_mssg[1].strip()
                    raise ResourceExistsError(f'DB item "{constraint}" already exists.') from e
                else:
                    raise UnexpectedError(f"{e.__class__.__name__}: {e}") from e
            elif isinstance(e, Timeout):
                request: Request | None = kwargs.get("request", None)
                mssg = failure_message if failure_message else "Could not acquire lock"
                mssg = f"{e.__class__.__name__}: {e} - {mssg} - kwargs={kwargs}"
                if request:
                    logger.warning(f"{request.state.id} - {mssg}")
                else:
                    logger.warning(mssg)
                raise
            else:
                request: Request | None = kwargs.get("request", None)
                mssg = failure_message if failure_message else f"Failed to run {fn.__name__}"
                mssg = f"{e.__class__.__name__}: {e} - {mssg} - kwargs={kwargs}"
                if request:
                    logger.error(f"{request.state.id} - {mssg}")
                else:
                    logger.error(mssg)
                raise UnexpectedError(f"{e.__class__.__name__}: {e}") from e

        if iscoroutinefunction(fn):

            @wraps(fn)
            async def wrapper(**kwargs):
                try:
                    return await fn(**kwargs)
                except Exception as e:
                    return _handle_exception(e, kwargs)

        else:

            @wraps(fn)
            def wrapper(**kwargs):
                try:
                    return fn(**kwargs)
                except Exception as e:
                    return _handle_exception(e, kwargs)

        return wrapper

    return decorator if func is None else decorator(func)
