from typing import Any, Mapping

import orjson
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from owl.utils import mask_string
from owl.utils.exceptions import (
    AuthorizationError,
    BadInputError,
    ContextOverflowError,
    ExternalAuthError,
    ForbiddenError,
    InsufficientCreditsError,
    JamaiException,
    MethodNotAllowedError,
    ModelOverloadError,
    RateLimitExceedError,
    ResourceExistsError,
    ResourceNotFoundError,
    ServerBusyError,
    UnavailableError,
    UnsupportedMediaTypeError,
    UpgradeTierError,
)

INTERNAL_ERROR_MESSAGE = "Oops sorry we ran into an unexpected error. Please try again later."


def make_request_log_str(request: Request, status_code: int | None = None) -> str:
    """
    Generate a string for logging, given a request object and an HTTP status code.

    Args:
        request (Request): Starlette request object.
        status_code (int): HTTP error code.

    Returns:
        str: A string in the format
            '<request_state_id> - "<request_method> <request_url_path><query>" <status_code>'
    """
    query = request.url.query
    query = f"?{query}" if query else ""
    msg = f'{request.state.id} - "{request.method} {request.url.path}{query}"'
    if status_code is not None:
        msg = f"{msg} {status_code}"
    return msg


def make_response(
    request: Request,
    message: str,
    error: str,
    status_code: int,
    *,
    detail: str | None = None,
    exception: Exception | None = None,
    headers: Mapping[str, str] | None = None,
    log: bool = True,
) -> ORJSONResponse:
    """
    Create a Response object.

    Args:
        request (Request): Starlette request object.
        message (str): User-friendly error message to be displayed by frontend or SDK.
        error (str): Short error name.
        status_code (int): HTTP error code.
        detail (str | None, optional): Error message with potentially more details.
            Defaults to None (message + headers).
        exception (Exception | None, optional): Exception that occurred. Defaults to None.
        headers (Mapping[str, str] | None, optional): Response headers. Defaults to None.
        log (bool, optional): Whether to log the response. Defaults to True.

    Returns:
        response (ORJSONResponse): Response object.
    """
    if detail is None:
        detail = f"{message}\nException:{repr(exception)}"
    if headers is None:
        headers = {}
    headers["x-request-id"] = request.headers.get("x-request-id", "")
    request_headers = {k.lower(): v for k, v in request.headers.items()}
    token = request_headers.get("authorization", "")
    if token.lower().startswith("bearer "):
        request_headers["authorization"] = (
            f"{token[:6]} {mask_string(token[7:], include_len=False)}"
        )
    else:
        request_headers["authorization"] = mask_string(token, include_len=False)
    response = ORJSONResponse(
        status_code=status_code,
        content={
            "object": "error",
            "error": error,
            "message": message,
            "detail": detail,
            "request_id": request.state.id,
            "exception": exception.__class__.__name__ if exception else None,
            "request_headers": request_headers,
        },
        headers=headers,
    )
    mssg = make_request_log_str(request, response.status_code)
    if not log:
        return response
    if status_code == 500:
        log_fn = logger.exception
    elif status_code > 500:
        log_fn = logger.warning
    elif exception is None:
        log_fn = logger.info
    elif isinstance(exception, (JamaiException, HTTPException)):
        log_fn = logger.info
    else:
        log_fn = logger.warning
    if exception:
        log_fn(f"{mssg} - {exception.__class__.__name__}: {exception}")
    else:
        log_fn(mssg)
    return response


class Wrapper(BaseModel):
    body: Any


async def _request_validation_exc_handler(request: Request, exc: RequestValidationError):
    content = None
    try:
        logger.info(
            f"{make_request_log_str(request, 422)} - RequestValidationError: {exc.errors()}"
        )
        errors, messages = [], []
        for i, e in enumerate(exc.errors()):
            try:
                msg = str(e["ctx"]["error"]).strip()
            except Exception:
                msg = e["msg"].strip()
            if not msg.endswith("."):
                msg = f"{msg}."

            path = ""
            for j, x in enumerate(e.get("loc", [])):
                if isinstance(x, str):
                    if j > 0:
                        path += "."
                    path += x
                elif isinstance(x, int):
                    path += f"[{x}]"
                else:
                    raise TypeError("Unexpected type")
            if path:
                path += " : "
            messages.append(f"{i + 1}. {path}{msg}")
            error = {k: v for k, v in e.items() if k != "ctx"}
            if "ctx" in e:
                error["ctx"] = {k: repr(v) if k == "error" else v for k, v in e["ctx"].items()}
            if "input" in e:
                error["input"] = repr(e["input"])
            errors.append(error)
        message = "\n".join(messages)
        message = f"Your request contains errors:\n{message}"
        content = {
            "object": "error",
            "error": "validation_error",
            "message": message,
            "detail": errors,
            "request_id": request.state.id,
            "exception": "",
            **Wrapper(body=exc.body).model_dump(),
        }
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=content,
        )
    except Exception:
        if content is None:
            content = repr(exc)
        logger.exception(f"{request.state.id} - Failed to parse error data: {content}")
        message = str(exc)
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "object": "error",
                "error": "validation_error",
                "message": message,
                "detail": message,
                "request_id": request.state.id,
                "exception": exc.__class__.__name__,
            },
        )


async def path_not_found_handler(request: Request, e: HTTPException):
    return make_response(
        request=request,
        message=f"The path '{request.url.path}' was not found.",
        error="http_error",
        status_code=e.status_code,
        exception=e,
        log=False,
    )


async def exception_handler(request: Request, e: Exception):
    if isinstance(e, RequestValidationError):
        return await _request_validation_exc_handler(request, e)
    # elif isinstance(e, ValidationError):
    #     raise RequestValidationError(errors=e.errors()) from e
    elif isinstance(e, AuthorizationError):
        return make_response(
            request=request,
            message=str(e),
            error="unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            exception=e,
        )
    elif isinstance(e, ExternalAuthError):
        return make_response(
            request=request,
            message=str(e),
            error="external_authentication_failed",
            status_code=status.HTTP_401_UNAUTHORIZED,
            exception=e,
        )
    elif isinstance(e, PermissionError):
        return make_response(
            request=request,
            message=str(e),
            error="resource_protected",
            status_code=status.HTTP_403_FORBIDDEN,
            exception=e,
        )
    elif isinstance(e, ForbiddenError):
        return make_response(
            request=request,
            message=str(e),
            error="forbidden",
            status_code=status.HTTP_403_FORBIDDEN,
            exception=e,
        )
    elif isinstance(e, UpgradeTierError):
        return make_response(
            request=request,
            message=str(e),
            error="upgrade_tier",
            status_code=status.HTTP_403_FORBIDDEN,
            exception=e,
        )
    elif isinstance(e, InsufficientCreditsError):
        return make_response(
            request=request,
            message=str(e),
            error="insufficient_credits",
            status_code=status.HTTP_403_FORBIDDEN,
            exception=e,
        )
    elif isinstance(e, (ResourceNotFoundError, FileNotFoundError)):
        return make_response(
            request=request,
            message=str(e),
            error="resource_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
            exception=e,
        )
    elif isinstance(e, (ResourceExistsError, FileExistsError)):
        return make_response(
            request=request,
            message=str(e),
            error="resource_exists",
            status_code=status.HTTP_409_CONFLICT,
            exception=e,
        )
    elif isinstance(e, UnsupportedMediaTypeError):
        return make_response(
            request=request,
            message=str(e),
            error="unsupported_media_type",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            exception=e,
        )
    elif isinstance(e, BadInputError):
        return make_response(
            request=request,
            message=str(e),
            error="bad_input",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            exception=e,
        )
    elif isinstance(e, ContextOverflowError):
        return make_response(
            request=request,
            message=str(e),
            error="context_overflow",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            exception=e,
        )
    elif isinstance(e, RateLimitExceedError):
        retry_after = "30" if e.retry_after is None else str(e.retry_after)
        used = str(e.limit) if e.used is None else str(e.used)
        meta = "{}" if e.meta is None else orjson.dumps(e.meta).decode("utf-8")
        return make_response(
            request=request,
            message=str(e),
            error="rate_limit_exceeded",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            exception=e,
            headers={
                "X-RateLimit-Limit": str(e.limit),
                "X-RateLimit-Remaining": str(e.remaining),
                "X-RateLimit-Reset": str(e.reset_at),
                "Retry-After": retry_after,
                "X-RateLimit-Used": used,
                "X-RateLimit-Meta": meta,
            },
        )
    elif isinstance(e, UnavailableError):
        return make_response(
            request=request,
            message=str(e),
            error="not_implemented",
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            exception=e,
        )
    elif isinstance(e, ServerBusyError):
        return make_response(
            request=request,
            message="The server is currently busy. Please try again later.",
            error="busy",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            exception=e,
            headers={"Retry-After": "30"},
        )
    elif isinstance(e, ModelOverloadError):
        return make_response(
            request=request,
            message="The model is overloaded. Please try again later.",
            error="busy",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            exception=e,
            headers={"Retry-After": "30"},
        )
    elif isinstance(e, HTTPException):
        return make_response(
            request=request,
            message=e.detail,
            error="http_error",
            status_code=e.status_code,
            exception=e,
            log=e.status_code != 404,
        )
    elif isinstance(e, IntegrityError):
        err_mssg: str = e.args[0]
        err_mssgs = err_mssg.split("UNIQUE constraint failed:")
        if len(err_mssgs) > 1:
            constraint = err_mssgs[1].strip()
            return make_response(
                request=request,
                message=f'DB item "{constraint}" already exists.',
                error="resource_exists",
                status_code=status.HTTP_409_CONFLICT,
                exception=e,
            )
        else:
            return make_response(
                request=request,
                message=INTERNAL_ERROR_MESSAGE,
                error="unexpected_error",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                exception=e,
            )
    elif isinstance(e, MethodNotAllowedError):
        return make_response(
            request=request,
            message=str(e),
            error="method_not_allowed",
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            exception=e,
        )
    else:
        return make_response(
            request=request,
            message=INTERNAL_ERROR_MESSAGE,
            error="unexpected_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            exception=e,
        )
