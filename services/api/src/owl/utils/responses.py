from typing import Mapping

from fastapi import Request, status
from fastapi.responses import ORJSONResponse
from loguru import logger
from starlette.exceptions import HTTPException

from jamaibase.exceptions import JamaiException

INTERNAL_ERROR_MESSAGE = "Opss sorry we ran into an unexpected error. Please try again later."


def make_request_log_str(request: Request, status_code: int) -> str:
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
    org_id = ""
    project_id = ""
    try:
        org_id = request.state.org_id
        project_id = request.state.project_id
    except Exception:
        pass
    return (
        f"{request.state.id} - "
        f'"{request.method} {request.url.path}{query}" {status_code} - '
        f"org_id={org_id} project_id={project_id}"
    )


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
    request_headers = dict(request.headers)
    if "authorization" in request_headers:
        request_headers["authorization"] = (
            f'{request_headers["authorization"][:2]}*****{request_headers["authorization"][-1:]}'
        )
    response = ORJSONResponse(
        status_code=status_code,
        content={
            "object": "error",
            "error": error,
            "message": message,
            "detail": detail,
            "request_id": request.state.id,
            "exception": exception.__class__.__name__ if exception else None,
            "headers": request_headers,
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


def unauthorized_response(
    request: Request,
    message: str,
    *,
    detail: str | None = None,
    error: str = "unauthorized",
    exception: Exception | None = None,
    headers: Mapping[str, str] | None = None,
) -> ORJSONResponse:
    """
    HTTP 401.
    The client should provide or correct their authentication information.
    Often used when a user is not logged in or their session has expired.

    Args:
        request (Request): Starlette request object.
        message (str): User-friendly error message to be displayed by frontend or SDK.
        detail (str | None, optional): Error message with potentially more details.
            Defaults to None (message + headers).
        error (str, optional): Short error name. Defaults to "unauthorized".
        exception (Exception | None, optional): Exception that occurred. Defaults to None.
        headers (Mapping[str, str] | None, optional): Response headers. Defaults to None.

    Returns:
        response (ORJSONResponse): Response object.
    """
    return make_response(
        request=request,
        message=message,
        error=error,
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        exception=exception,
        headers=headers,
    )


def forbidden_response(
    request: Request,
    message: str,
    *,
    detail: str | None = None,
    error: str = "forbidden",
    exception: Exception | None = None,
    headers: Mapping[str, str] | None = None,
) -> ORJSONResponse:
    """
    HTTP 403.
    The client does not have access rights to the content.
    Authentication will not help, as the client is not allowed to perform the requested action.

    Args:
        request (Request): Starlette request object.
        message (str): User-friendly error message to be displayed by frontend or SDK.
        detail (str | None, optional): Error message with potentially more details.
            Defaults to None (message + headers).
        error (str, optional): Short error name. Defaults to "forbidden".
        exception (Exception | None, optional): Exception that occurred. Defaults to None.
        headers (Mapping[str, str] | None, optional): Response headers. Defaults to None.

    Returns:
        response (ORJSONResponse): Response object.
    """
    return make_response(
        request=request,
        message=message,
        error=error,
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
        exception=exception,
        headers=headers,
    )


def resource_not_found_response(
    request: Request,
    message: str,
    *,
    detail: str | None = None,
    error: str = "resource_not_found",
    exception: Exception | None = None,
    headers: Mapping[str, str] | None = None,
) -> ORJSONResponse:
    """
    HTTP 404.
    The server can not find the requested resource.

    Args:
        request (Request): Starlette request object.
        message (str): User-friendly error message to be displayed by frontend or SDK.
        detail (str | None, optional): Error message with potentially more details.
            Defaults to None (message + headers).
        error (str, optional): Short error name. Defaults to "resource_not_found".
        exception (Exception | None, optional): Exception that occurred. Defaults to None.
        headers (Mapping[str, str] | None, optional): Response headers. Defaults to None.

    Returns:
        response (ORJSONResponse): Response object.
    """
    return make_response(
        request=request,
        message=message,
        error=error,
        status_code=status.HTTP_404_NOT_FOUND,
        detail=detail,
        exception=exception,
        headers=headers,
    )


def resource_exists_response(
    request: Request,
    message: str,
    *,
    detail: str | None = None,
    error: str = "resource_exists",
    exception: Exception | None = None,
    headers: Mapping[str, str] | None = None,
) -> ORJSONResponse:
    """
    HTTP 409.
    The request cannot be processed because it conflicts with the current state of the resource.

    Args:
        request (Request): Starlette request object.
        message (str): User-friendly error message to be displayed by frontend or SDK.
        detail (str | None, optional): Error message with potentially more details.
            Defaults to None (message + headers).
        error (str, optional): Short error name. Defaults to "resource_exists".
        exception (Exception | None, optional): Exception that occurred. Defaults to None.
        headers (Mapping[str, str] | None, optional): Response headers. Defaults to None.

    Returns:
        response (ORJSONResponse): Response object.
    """
    return make_response(
        request=request,
        message=message,
        error=error,
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
        exception=exception,
        headers=headers,
    )


def bad_input_response(
    request: Request,
    message: str,
    *,
    detail: str | None = None,
    error: str = "bad_input",
    exception: Exception | None = None,
    headers: Mapping[str, str] | None = None,
) -> ORJSONResponse:
    """
    HTTP 422.
    The request contains errors and cannot be processed.

    Args:
        request (Request): Starlette request object.
        message (str): User-friendly error message to be displayed by frontend or SDK.
        detail (str | None, optional): Error message with potentially more details.
            Defaults to None (message + headers).
        error (str, optional): Short error name. Defaults to "bad_input".
        exception (Exception | None, optional): Exception that occurred. Defaults to None.
        headers (Mapping[str, str] | None, optional): Response headers. Defaults to None.

    Returns:
        response (ORJSONResponse): Response object.
    """
    return make_response(
        request=request,
        message=message,
        error=error,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=detail,
        exception=exception,
        headers=headers,
    )


def internal_server_error_response(
    request: Request,
    message: str = INTERNAL_ERROR_MESSAGE,
    *,
    detail: str | None = None,
    error: str = "unexpected_error",
    exception: Exception | None = None,
    headers: Mapping[str, str] | None = None,
) -> ORJSONResponse:
    """
    HTTP 500.
    The server encountered an unexpected condition that prevented it from fulfilling the request.

    Args:
        request (Request): Starlette request object.
        message (str): User-friendly error message to be displayed by frontend or SDK.
        detail (str | None, optional): Error message with potentially more details.
            Defaults to None (message + headers).
        error (str, optional): Short error name. Defaults to "unexpected_error".
        exception (Exception | None, optional): Exception that occurred. Defaults to None.
        headers (Mapping[str, str] | None, optional): Response headers. Defaults to None.

    Returns:
        response (ORJSONResponse): Response object.
    """
    return make_response(
        request=request,
        message=message,
        error=error,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
        exception=exception,
        headers=headers,
    )


def server_busy_response(
    request: Request,
    message: str,
    *,
    detail: str | None = None,
    error: str = "busy",
    exception: Exception | None = None,
    headers: Mapping[str, str] | None = None,
) -> ORJSONResponse:
    """
    HTTP 503.
    The server is currently unable to handle the request due to a temporary overloading or maintenance.

    Args:
        request (Request): Starlette request object.
        message (str): User-friendly error message to be displayed by frontend or SDK.
        detail (str | None, optional): Error message with potentially more details.
            Defaults to None (message + headers).
        error (str, optional): Short error name. Defaults to "busy".
        exception (Exception | None, optional): Exception that occurred. Defaults to None.
        headers (Mapping[str, str] | None, optional): Response headers. Defaults to None.

    Returns:
        response (ORJSONResponse): Response object.
    """
    return make_response(
        request=request,
        message=message,
        error=error,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
        exception=exception,
        headers=headers,
    )
