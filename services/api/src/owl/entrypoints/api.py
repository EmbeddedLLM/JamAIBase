"""
API server.
"""

import os
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from filelock import Timeout
from loguru import logger
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from jamaibase import JamAIAsync
from jamaibase.exceptions import (
    AuthorizationError,
    BadInputError,
    ContextOverflowError,
    ExternalAuthError,
    ForbiddenError,
    InsufficientCreditsError,
    ResourceExistsError,
    ResourceNotFoundError,
    ServerBusyError,
    TableSchemaFixedError,
    UnexpectedError,
    UnsupportedMediaTypeError,
    UpgradeTierError,
)
from owl.billing import BillingManager
from owl.configs.manager import CONFIG, ENV_CONFIG
from owl.protocol import COL_NAME_PATTERN, TABLE_NAME_PATTERN, UserAgent
from owl.routers import file, gen_table, llm, org_admin, template
from owl.utils import uuid7_str
from owl.utils.logging import setup_logger_sinks, suppress_logging_handlers
from owl.utils.responses import (
    bad_input_response,
    forbidden_response,
    internal_server_error_response,
    make_request_log_str,
    make_response,
    resource_exists_response,
    resource_not_found_response,
    server_busy_response,
    unauthorized_response,
)

if ENV_CONFIG.is_oss:
    from owl.routers import oss_admin as admin

    cloud_auth = None
else:
    from owl.routers import cloud_admin as admin
    from owl.routers import cloud_auth


NO_AUTH_ROUTES = {"health", "public", "favicon.ico"}

client = JamAIAsync(token=ENV_CONFIG.service_key_plain, timeout=60.0)
logger.enable("owl")
setup_logger_sinks()
# We purposely don't intercept uvicorn logs since it is typically not useful
# We also don't intercept transformers logs
# replace_logging_handlers(["uvicorn.access"], False)
suppress_logging_handlers(["uvicorn", "litellm", "openmeter", "azure"], True)


app = FastAPI(
    logger=logger,
    default_response_class=ORJSONResponse,  # Should be faster
    openapi_url="/api/public/openapi.json",
    docs_url="/api/public/docs",
    redoc_url="/api/public/redoc",
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    servers=[dict(url="https://api.jamaibase.com")],
)
services = [
    (admin.router, ["Backend Admin"], "/api"),
    (admin.public_router, ["Backend Admin"], "/api"),
    (org_admin.router, ["Organization Admin"], "/api/admin/org"),
    (template.router, ["Templates"], "/api"),
    (template.public_router, ["Templates (Public)"], "/api"),
    (llm.router, ["Large Language Model"], "/api"),
    (gen_table.router, ["Generative Table"], "/api"),
    (file.router, ["File"], "/api"),
]

# Mount
for router, tags, prefix in services:
    app.include_router(
        router,
        prefix=prefix,
        tags=tags,
    )
if cloud_auth is not None:
    app.include_router(
        cloud_auth.router,
        prefix="/api",
        tags=["OAuth"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=ENV_CONFIG.owl_session_secret_plain,
        max_age=60 * 60 * 24 * 7,
        https_only=ENV_CONFIG.owl_is_prod,
    )

# Permissive CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    # Router lifespan is broken as of fastapi==0.109.0 and starlette==0.35.1
    # https://github.com/tiangolo/fastapi/discussions/9664
    logger.info(f"Using configuration: {ENV_CONFIG}")
    # Maybe purge Redis data
    if ENV_CONFIG.owl_cache_purge:
        CONFIG.purge()
    if ENV_CONFIG.is_oss:
        logger.opt(colors=True).info("Launching in <b><u><cyan>OSS mode</></></>.")
        from sqlalchemy import func
        from sqlmodel import Session, select

        from owl.db import MAIN_ENGINE
        from owl.db.oss_admin import Organization, Project

        with Session(MAIN_ENGINE) as session:
            org = session.get(Organization, ENV_CONFIG.default_org_id)
            if org is None:
                org = Organization()
                session.add(org)
                session.commit()
                session.refresh(org)
                logger.info(f"Default organization created: {org}")
            else:
                logger.info(f"Default organization found: {org}")
            # Default project could have been deleted
            # As long as there is at least one project it's ok
            project_count = session.exec(select(func.count(Project.id))).one()
            if project_count == 0:
                project = Project(
                    id=ENV_CONFIG.default_project_id,
                    name="Default",
                    organization_id=org.id,
                )
                session.add(project)
                session.commit()
                session.refresh(project)
                logger.info(f"Default project created: {project}")
            else:
                logger.info(f"{project_count:,d} projects found.")
    else:
        logger.opt(colors=True).info("Launching in <b><u><cyan>Cloud mode</></></>.")


@app.middleware("http")
async def log_request(request: Request, call_next):
    """
    Args:
        request (Request): Starlette request object.
        call_next (Callable): A function that will receive the request,
            pass it to the path operation, and returns the response generated.

    Returns:
        response (Response): Response of the path operation.
    """
    # Set request state
    request.state.id = uuid7_str()
    request.state.user_agent = UserAgent.from_user_agent_string(
        request.headers.get("user-agent", "")
    )
    request.state.billing = BillingManager(request=request)

    # OPTIONS are always allowed for CORS preflight:
    if request.method == "OPTIONS":
        return await call_next(request)
    # The following paths are always allowed:
    path_components = [p for p in request.url.path.split("/") if p][:2]
    if request.method in ("GET", "HEAD") and (
        len(path_components) == 0 or path_components[-1] in NO_AUTH_ROUTES
    ):
        return await call_next(request)

    # --- Call request --- #
    response = await call_next(request)
    logger.info(make_request_log_str(request, response.status_code))
    return response


@app.get("/api/health", tags=["Health"])
async def health() -> ORJSONResponse:
    """Health check."""
    return ORJSONResponse(
        status_code=200,
        content={"is_oss": ENV_CONFIG.is_oss},
    )


# --- Order of handlers does not matter --- #


@app.exception_handler(AuthorizationError)
async def authorization_exc_handler(request: Request, exc: ForbiddenError):
    return unauthorized_response(request, str(exc), exception=exc)


@app.exception_handler(ExternalAuthError)
async def external_auth_exc_handler(request: Request, exc: ExternalAuthError):
    return unauthorized_response(
        request, str(exc), error="external_authentication_failed", exception=exc
    )


@app.exception_handler(PermissionError)
async def permission_error_exc_handler(request: Request, exc: PermissionError):
    return forbidden_response(request, str(exc), error="resource_protected", exception=exc)


@app.exception_handler(ForbiddenError)
async def forbidden_exc_handler(request: Request, exc: ForbiddenError):
    return forbidden_response(request, str(exc), exception=exc)


@app.exception_handler(UpgradeTierError)
async def upgrade_tier_exc_handler(request: Request, exc: UpgradeTierError):
    return forbidden_response(request, str(exc), error="upgrade_tier", exception=exc)


@app.exception_handler(InsufficientCreditsError)
async def insufficient_credits_exc_handler(request: Request, exc: InsufficientCreditsError):
    return forbidden_response(request, str(exc), error="insufficient_credits", exception=exc)


@app.exception_handler(FileNotFoundError)
async def file_not_found_exc_handler(request: Request, exc: FileNotFoundError):
    return resource_not_found_response(request, str(exc), exception=exc)


@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_exc_handler(request: Request, exc: ResourceNotFoundError):
    return resource_not_found_response(request, str(exc), exception=exc)


@app.exception_handler(FileExistsError)
async def file_exists_exc_handler(request: Request, exc: FileExistsError):
    return resource_exists_response(request, str(exc), exception=exc)


@app.exception_handler(ResourceExistsError)
async def resource_exists_exc_handler(request: Request, exc: ResourceExistsError):
    return resource_exists_response(request, str(exc), exception=exc)


@app.exception_handler(UnsupportedMediaTypeError)
async def unsupported_media_type_exc_handler(request: Request, exc: UnsupportedMediaTypeError):
    logger.warning(f"{make_request_log_str(request, 415)} - {exc.__class__.__name__}: {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        content={
            "object": "error",
            "error": "unsupported_media_type",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": "",
        },
    )


@app.exception_handler(BadInputError)
async def bad_input_exc_handler(request: Request, exc: BadInputError):
    return bad_input_response(request, str(exc), exception=exc)


@app.exception_handler(TableSchemaFixedError)
async def table_fixed_exc_handler(request: Request, exc: TableSchemaFixedError):
    return bad_input_response(request, str(exc), error="table_schema_fixed", exception=exc)


@app.exception_handler(ContextOverflowError)
async def context_overflow_exc_handler(request: Request, exc: ContextOverflowError):
    return bad_input_response(request, str(exc), error="context_overflow", exception=exc)


class Wrapper(BaseModel):
    body: Any


@app.exception_handler(RequestValidationError)
async def request_validation_exc_handler(request: Request, exc: RequestValidationError):
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
            # Intercept Table and Column ID regex error message
            if TABLE_NAME_PATTERN in msg:
                msg = (
                    "Table name or ID must be unique with at least 1 character and up to 100 characters. "
                    "Must start and end with an alphabet or number. "
                    "Characters in the middle can include `_` (underscore), `-` (dash), `.` (dot)."
                )
            elif COL_NAME_PATTERN in msg:
                msg = (
                    "Column name or ID must be unique with at least 1 character and up to 100 characters. "
                    "Must start and end with an alphabet or number. "
                    "Characters in the middle can include `_` (underscore), `-` (dash), ` ` (space). "
                    'Cannot be called "ID" or "Updated at" (case-insensitive).'
                )

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


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    return internal_server_error_response(request, exception=exc)


@app.exception_handler(UnexpectedError)
async def unexpected_error_handler(request: Request, exc: UnexpectedError):
    return internal_server_error_response(request, exception=exc)


@app.exception_handler(ResponseValidationError)
async def response_validation_error_handler(request: Request, exc: ResponseValidationError):
    return internal_server_error_response(request, exception=exc)


@app.exception_handler(Timeout)
async def write_lock_timeout_exc_handler(request: Request, exc: Timeout):
    return server_busy_response(
        request,
        "This table is currently busy. Please try again later.",
        exception=exc,
        headers={"Retry-After": "10"},
    )


@app.exception_handler(ServerBusyError)
async def busy_exc_handler(request: Request, exc: ServerBusyError):
    return server_busy_response(
        request,
        "The server is currently busy. Please try again later.",
        exception=exc,
        headers={"Retry-After": "30"},
    )


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    return make_response(
        request=request,
        message=str(exc),
        error="http_error",
        status_code=exc.status_code,
        detail=None,
        exception=exc,
        log=exc.status_code != 404,
    )


if not ENV_CONFIG.is_oss:
    openapi_schema = app.openapi()
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "Authentication": {
            "type": "http",
            "scheme": "bearer",
        },
    }
    openapi_schema["security"] = [{"Authentication": []}]
    openapi_schema["info"]["x-logo"] = {"url": "https://www.jamaibase.com/favicon.svg"}
    app.openapi_schema = openapi_schema


if __name__ == "__main__":
    import uvicorn

    if os.name == "nt":
        import asyncio
        from multiprocessing import freeze_support

        logger.warning("The system is Windows, performing asyncio and multiprocessing patches.")
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        freeze_support()

    uvicorn.run(
        "owl.entrypoints.api:app",
        reload=False,
        host=ENV_CONFIG.owl_host,
        port=ENV_CONFIG.owl_port,
        workers=ENV_CONFIG.owl_workers,
        limit_concurrency=ENV_CONFIG.owl_max_concurrency,
    )
