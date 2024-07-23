"""
API server.

```shell
$ python -m owl.entrypoints.api
$ JAMAI_API_BASE=http://localhost:6969/api TZ=Asia/Singapore python -m owl.entrypoints.api
```
"""

import os
from asyncio import sleep
from collections import defaultdict
from time import perf_counter

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from filelock import FileLock, Timeout
from loguru import logger
from starlette.background import BackgroundTasks
from uuid_utils import uuid7

from owl.configs.manager import CONFIG, ENV_CONFIG
from owl.routers import gen_table, llm
from owl.utils.exceptions import (
    ContextOverflowError,
    InsufficientCreditsError,
    ResourceExistsError,
    ResourceNotFoundError,
    TableSchemaFixedError,
    UpgradeTierError,
)
from owl.utils.logging import (
    replace_logging_handlers,
    setup_logger_sinks,
    suppress_logging_handlers,
)
from owl.utils.openapi import custom_generate_unique_id
from owl.utils.tasks import repeat_every

try:
    from owl.cloud_client import OwlAsync
    from owl.routers import cloud_admin
except ImportError as e:
    logger.warning(
        (
            "Failed to import cloud modules. Ignore this warning if you are using OSS mode. "
            f"Exception: {e}"
        )
    )
    OwlAsync = None
    cloud_admin = None
try:
    from owl.cloud_billing import BillingManager
except ImportError as e:
    logger.warning(
        (
            "Failed to import cloud modules. Ignore this warning if you are using OSS mode. "
            f"Exception: {e}"
        )
    )
    from owl.billing import BillingManager


setup_logger_sinks()
# We purposely don't intercept uvicorn logs since it is typically not useful
# We also don't intercept transformers logs
replace_logging_handlers(["uvicorn.access"], False)
suppress_logging_handlers(["litellm", "openmeter", "azure"], True)

# Maybe purge Redis data
if ENV_CONFIG.owl_cache_purge:
    CONFIG.purge()

# Cloud client
if OwlAsync is None or ENV_CONFIG.service_key_plain == "":
    owl_client = None
else:
    owl_client = OwlAsync(api_key=ENV_CONFIG.service_key_plain)

app = FastAPI(
    logger=logger,
    default_response_class=ORJSONResponse,  # Should be faster
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    servers=[dict(url="https://api.jamaibase.com")],
)
services = {
    "llm": (llm.router, ["Large Language Model"], "/api"),
    "gen_table": (gen_table.router, ["Generative Table"], "/api"),
}
if cloud_admin is not None:
    services["cloud_admin"] = (cloud_admin.router, ["Cloud Admin"], "/api/admin")
if ENV_CONFIG.owl_service != "":
    try:
        router, tags, prefix = services[ENV_CONFIG.owl_service]
    except KeyError:
        logger.error(
            f"Invalid service '{ENV_CONFIG.owl_service}', choose from: {list(services.keys())}"
        )
        raise
    app.include_router(
        router,
        prefix=prefix,
        tags=tags,
        generate_unique_id_function=custom_generate_unique_id,
    )
else:
    # Mount everything
    for service, (router, tags, prefix) in services.items():
        app.include_router(
            router,
            prefix=prefix,
            tags=tags,
            generate_unique_id_function=custom_generate_unique_id,
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


@router.on_event("startup")
@repeat_every(seconds=ENV_CONFIG.owl_compute_storage_period_min * 60, wait_first=True)
async def periodic_storage_update():
    if OwlAsync is None:
        return
    # Only let one worker perform this task
    lock = FileLock(f"{ENV_CONFIG.owl_db_dir}/periodic_storage_update.lock", blocking=False)
    try:
        t0 = perf_counter()
        with lock:
            usages = BillingManager.get_storage_usage()
            if usages is None:
                return
            db_usages, file_usages = usages
            num_ok = num_failed = 0
            for org_id in db_usages:
                if org_id == "default":
                    continue
                try:
                    org_info = await owl_client.get_organization(org_id)
                    manager = BillingManager(
                        request=None,
                        openmeter_id=org_info.openmeter_id,
                        quotas=org_info.quotas,
                        quota_reset_at=org_info.quota_reset_at,
                        organization_tier=org_info.tier,
                        organization_id=org_id,
                        project_id="",
                        api_key="",
                    )
                    await manager.process_storage_usage(
                        db_usage=db_usages[org_id],
                        file_usage=file_usages[org_id],
                        last_db_usage=org_info.db_storage_gb,
                        last_file_usage=org_info.file_storage_gb,
                        min_wait_mins=max(5.0, ENV_CONFIG.owl_compute_storage_period_min),
                    )
                    num_ok += 1
                except Exception as e:
                    logger.warning(f"Storage usage update failed for {org_id}: {e}")
                    num_failed += 1
            t = perf_counter() - t0
            # Hold the lock for a while to block other workers
            await sleep(max(0.0, (ENV_CONFIG.owl_compute_storage_period_min * 60 - t) * 0.5))
            logger.info(
                (
                    f"Periodic storage usage update completed (t={t:,.3f} s, "
                    f"{num_ok:,d} OK, {num_failed:,d} failed)."
                )
            )
    except Timeout:
        pass
    except Exception:
        logger.exception("Periodic storage usage update encountered an error.")


NO_AUTH_ROUTES = {"health", "docs", "openapi.json", "favicon.ico"}
ERROR_MESSAGE_URL = "https://cloud.jamaibase.com"
INTERNAL_ERROR_MESSAGE = "Opss sorry we ran into an unexpected error. Please try again later."


@app.middleware("http")
async def authenticate(request: Request, call_next):
    """
    Implement HTTP Bearer Auth.

    Note that despite reports of issues such as:
    - https://github.com/encode/starlette/issues/1438
    - https://github.com/encode/starlette/pull/1640

    The usage of this auth middleware seems to work well with FastAPI BackgroundTasks.

    References:
    - https://fastapi.tiangolo.com/tutorial/middleware/
    - https://stackoverflow.com/a/76583417
    - https://stackoverflow.com/a/70052350

    Args:
        request (Request): The request.
        call_next (Callable): A function that will receive the request,
            pass it to the path operation, and returns the response generated.

    Returns:
        response (Response): Response of the path operation if auth is successful, otherwise a 401.
    """
    request.state.id = str(uuid7())
    # The following paths are always allowed:
    if request.method == "GET" and request.url.path.split("/")[-1] in NO_AUTH_ROUTES:
        return await call_next(request)
    t0 = perf_counter()
    # Defaults
    project_id, org_id, org_tier = ENV_CONFIG.default_project, ENV_CONFIG.default_org, "free"
    token, openmeter_id = "", "default"
    quotas, quota_reset_at = defaultdict(lambda: 1.0), ""

    # --- OSS Mode --- #
    if ENV_CONFIG.service_key_plain == "":
        openai_api_key = ENV_CONFIG.openai_api_key_plain
        anthropic_api_key = ENV_CONFIG.anthropic_api_key_plain
        gemini_api_key = ENV_CONFIG.gemini_api_key_plain
        cohere_api_key = ENV_CONFIG.cohere_api_key_plain
        groq_api_key = ENV_CONFIG.groq_api_key_plain
        together_api_key = ENV_CONFIG.together_api_key_plain
        jina_api_key = ENV_CONFIG.jina_api_key_plain
        voyage_api_key = ENV_CONFIG.voyage_api_key_plain

    # --- Cloud Mode --- #
    else:
        if owl_client is None:
            raise SystemError("Cloud-only module is missing.")
        # Parse auth header, check scheme and token
        auth = request.headers.get("Authorization", "").split("Bearer ")
        if len(auth) < 2 or auth[1] == "":
            return ORJSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "object": "error",
                    "error": "unauthorized",
                    "message": (
                        "You didn't provide an API key. "
                        "You need to provide your API key in an Authorization header using Bearer auth "
                        "(i.e. Authorization: Bearer API_KEY. "
                        f"You can obtain an API key from {ERROR_MESSAGE_URL}"
                    ),
                    "detail": f"No API key provided. Header: {request.headers}.",
                    "request_id": request.state.id,
                    "exception": "PermissionError",
                },
            )
        token = auth[1]
        # Admin API only accepts service key
        if "api/admin" in request.url.path:
            if token != ENV_CONFIG.service_key_plain:
                _err_mssg = f"Incorrect service key provided: {token}."
                return ORJSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "object": "error",
                        "error": "unauthorized",
                        "message": _err_mssg,
                        "detail": _err_mssg,
                        "request_id": request.state.id,
                        "exception": "PermissionError",
                    },
                )
            # Admin API does not require project ID
            external_keys = {}
        # Access non-admin APIs
        else:
            project_id = request.headers.get("X-PROJECT-ID", "").strip()
            if project_id == "":
                _err_mssg = f"Project not found: {project_id}."
                return ORJSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={
                        "object": "error",
                        "error": "resource_not_found",
                        "message": _err_mssg,
                        "detail": _err_mssg,
                        "request_id": request.state.id,
                        "exception": "ResourceNotFoundError",
                    },
                )
            if token == ENV_CONFIG.service_key_plain:
                # Service key auth
                try:
                    project_info = await owl_client.get_project(project_id)
                    org_info = project_info.organization
                    org_id, external_keys = org_info.id, org_info.external_keys
                except (RuntimeError, ResourceNotFoundError):
                    _err_mssg = f"Project not found: {project_id}."
                    return ORJSONResponse(
                        status_code=status.HTTP_404_NOT_FOUND,
                        content={
                            "object": "error",
                            "error": "resource_not_found",
                            "message": _err_mssg,
                            "detail": _err_mssg,
                            "request_id": request.state.id,
                            "exception": "ResourceNotFoundError",
                        },
                    )
                except Exception as e:
                    logger.exception(f"Encountered an error while fetching project: {project_id}")
                    return ORJSONResponse(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={
                            "object": "error",
                            "error": "unexpected_error",
                            "message": INTERNAL_ERROR_MESSAGE,
                            "detail": str(e),
                            "request_id": request.state.id,
                            "exception": e.__class__.__name__,
                        },
                    )
            else:
                # API key auth
                try:
                    org_info = await owl_client.get_organization(token)
                except (RuntimeError, ResourceNotFoundError):
                    _err_mssg = f"Incorrect API key provided: {token}."
                    return ORJSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={
                            "object": "error",
                            "error": "unauthorized",
                            "message": f"{_err_mssg} You can find your API key at {ERROR_MESSAGE_URL}.",
                            "detail": _err_mssg,
                            "request_id": request.state.id,
                            "exception": "PermissionError",
                        },
                    )
                except Exception as e:
                    logger.exception(
                        f"Encountered an error while fetching organization using API key: {token}"
                    )
                    return ORJSONResponse(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={
                            "object": "error",
                            "error": "unexpected_error",
                            "message": INTERNAL_ERROR_MESSAGE,
                            "detail": str(e),
                            "request_id": request.state.id,
                            "exception": e.__class__.__name__,
                        },
                    )
                if not org_info.active:
                    return ORJSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "object": "error",
                            "error": "upgrade_tier",
                            "message": "Please activate your organization.",
                            "detail": f"Organization not active. Org data: {org_info}",
                            "request_id": request.state.id,
                            "exception": "UpgradeTierError",
                        },
                    )
                org_project_ids = set(p.id for p in org_info.projects)
                if project_id not in org_project_ids:
                    _err_mssg = f"Project not found: {project_id}."
                    return ORJSONResponse(
                        status_code=status.HTTP_404_NOT_FOUND,
                        content={
                            "object": "error",
                            "error": "resource_not_found",
                            "message": _err_mssg,
                            "detail": f"{_err_mssg} Org data: {org_info}",
                            "request_id": request.state.id,
                            "exception": "ResourceNotFoundError",
                        },
                    )
                org_id, external_keys = org_info.id, org_info.external_keys
            openmeter_id = org_info.openmeter_id
            org_tier = org_info.tier
            quotas = org_info.quotas
            quota_reset_at = org_info.quota_reset_at
            if openmeter_id is None:
                logger.warning(
                    f"{request.state.id} - Organization {org_id} does not have OpenMeter ID."
                )
        openai_api_key = external_keys.get("openai_api_key", "")
        anthropic_api_key = external_keys.get("anthropic_api_key", "")
        gemini_api_key = external_keys.get("gemini_api_key", "")
        cohere_api_key = external_keys.get("cohere_api_key", "")
        groq_api_key = external_keys.get("groq_api_key", "")
        together_api_key = external_keys.get("together_api_key", "")
        jina_api_key = external_keys.get("jina_api_key", "")
        voyage_api_key = external_keys.get("voyage_api_key", "")

    # --- Set request state and headers --- #
    request.state.org_id = org_id
    request.state.project_id = project_id
    request.state.billing_manager = BillingManager(
        request=request,
        openmeter_id=openmeter_id,
        quotas=quotas,
        quota_reset_at=quota_reset_at,
        organization_tier=org_tier,
        organization_id=org_id,
        project_id=project_id,
        api_key=token,
    )
    # Add API keys into header
    headers = dict(request.scope["headers"])
    if openai_api_key:
        headers[b"openai-api-key"] = openai_api_key.encode()
    if anthropic_api_key:
        headers[b"anthropic-api-key"] = anthropic_api_key.encode()
    if gemini_api_key:
        headers[b"gemini-api-key"] = gemini_api_key.encode()
    if cohere_api_key:
        headers[b"cohere-api-key"] = cohere_api_key.encode()
    if groq_api_key:
        headers[b"groq-api-key"] = groq_api_key.encode()
    if together_api_key:
        headers[b"together-api-key"] = together_api_key.encode()
    if jina_api_key:
        headers[b"jina-api-key"] = jina_api_key.encode()
    if voyage_api_key:
        headers[b"voyage-api-key"] = voyage_api_key.encode()
    request.scope["headers"] = [(k, v) for k, v in headers.items()]

    # --- Call request --- #
    t1 = perf_counter()
    response = await call_next(request)
    t2 = perf_counter()

    # --- Send events --- #
    tasks = BackgroundTasks()
    tasks.add_task(
        request.state.billing_manager.process_all,
        auth_latency_ms=(t1 - t0) * 1e3,
        request_latency_ms=(t2 - t1) * 1e3,
        content_length_gb=float(response.headers.get("content-length", 0)) / (1024**3),
    )
    response.background = tasks
    return response


@app.get("/api/health", tags=["api"])
async def health() -> Response:
    """Health check."""
    return Response(status_code=200)


# --- Order of handlers does not matter --- #


@app.exception_handler(Timeout)
async def write_lock_timeout_exc_handler(request: Request, exc: Timeout):
    logger.warning(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "object": "error",
            "error": "write_lock_timeout",
            "message": "This table is currently busy. Please try again later.",
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
        headers={"Retry-After": 10},
    )


@app.exception_handler(UpgradeTierError)
async def upgrade_tier_exc_handler(request: Request, exc: UpgradeTierError):
    logger.info(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "object": "error",
            "error": "upgrade_tier",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(InsufficientCreditsError)
async def insufficient_credits_exc_handler(request: Request, exc: InsufficientCreditsError):
    logger.info(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "object": "error",
            "error": "insufficient_credits",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(PermissionError)
async def permission_error_exc_handler(request: Request, exc: PermissionError):
    logger.info(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "object": "error",
            "error": "resource_protected",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(FileExistsError)
async def file_exists_exc_handler(request: Request, exc: FileExistsError):
    logger.info(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "object": "error",
            "error": "resource_exists",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(ResourceExistsError)
async def resource_exists_exc_handler(request: Request, exc: ResourceExistsError):
    logger.info(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "object": "error",
            "error": "resource_exists",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(FileNotFoundError)
async def file_not_found_exc_handler(request: Request, exc: FileNotFoundError):
    logger.info(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "object": "error",
            "error": "resource_not_found",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_exc_handler(request: Request, exc: ResourceNotFoundError):
    logger.info(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "object": "error",
            "error": "resource_not_found",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(TableSchemaFixedError)
async def table_fixed_exc_handler(request: Request, exc: TableSchemaFixedError):
    logger.info(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "object": "error",
            "error": "table_schema_fixed",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(ContextOverflowError)
async def context_overflow_exc_handler(request: Request, exc: ContextOverflowError):
    logger.info(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "object": "error",
            "error": "context_overflow",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exc_handler(request: Request, exc: RequestValidationError):
    try:
        logger.info(f"{request.state.id} - RequestValidationError: {exc.errors()}")
        errors, messages = [], []
        for i, e in enumerate(exc.errors()):
            try:
                msg = str(e["ctx"]["error"]).strip()
            except Exception:
                msg = e["msg"].strip()
            if not msg.endswith("."):
                msg = f"{msg}."
            loc = ""
            if len(e["loc"]) > 0:
                loc = ".".join(str(ll) for ll in e["loc"]) + " : "
            messages.append(f"{i + 1}. {loc}{msg}")
            error = {k: v for k, v in e.items() if k != "ctx"}
            if "ctx" in e:
                error["ctx"] = {k: repr(v) if k == "error" else v for k, v in e["ctx"].items()}
            errors.append(error)
        message = "\n".join(messages)
        message = f"Your request contains errors:\n{message}"
        body = exc.body if isinstance(exc.body, dict) else str(exc.body)
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "object": "error",
                "error": "validation_error",
                "message": message,
                "detail": errors,
                "request_id": request.state.id,
                "body": body,
                "exception": exc.__class__.__name__,
            },
        )
    except Exception:
        logger.exception("Failed to parse error data !!!")
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "object": "error",
                "error": "validation_error",
                "message": str(exc),
                "detail": str(exc),
                "request_id": request.state.id,
                "exception": exc.__class__.__name__,
            },
        )


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    logger.warning(f"{request.state.id} - {exc}")
    return ORJSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "object": "error",
            "error": "unexpected_error",
            "message": INTERNAL_ERROR_MESSAGE,
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


openapi_schema = app.openapi()
# Add security schemes
openapi_schema["components"]["securitySchemes"] = {
    "Authentication": {
        "type": "http",
        "scheme": "bearer",
    },
    "X-PROJECT-ID": {
        "type": "apiKey",
        "name": "X-PROJECT-ID",
        "in": "header",
    },
}
openapi_schema["security"] = [{"Authentication": [], "X-PROJECT-ID": []}]
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
    )
