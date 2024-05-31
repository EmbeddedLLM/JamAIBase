"""
API server.

```shell
$ python -m owl.entrypoints.api
```
"""

from collections import defaultdict
from os import makedirs
from os.path import exists
from time import perf_counter

import redis
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import ORJSONResponse
from loguru import logger
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.background import BackgroundTasks
from uuid_utils import uuid7

from owl.config import LLM_PRICES_KEY, MODEL_CONFIG_KEY, PRICES_KEY
from owl.routers import gen_table, llm
from owl.utils.exceptions import (
    ContextOverflowError,
    InsufficientCreditsError,
    ResourceExistsError,
    ResourceNotFoundError,
    TableSchemaFixedError,
    UpgradeTierError,
)
from owl.utils.logging import replace_logging_handlers, setup_logger_sinks
from owl.utils.openapi import custom_generate_unique_id

try:
    from owl.cloud_billing import BillingManager
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
    BillingManager = None


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    owl_redis_purge: bool = False
    owl_redis_host: str = "dragonfly"
    owl_db_dir: str = "db"
    owl_port: int = 7770
    owl_host: str = "0.0.0.0"
    owl_workers: int = 2
    owl_service: str = ""
    default_project: str = "default"
    default_org: str = "default"
    service_key: SecretStr = ""
    openai_api_key: SecretStr = ""
    anthropic_api_key: SecretStr = ""
    gemini_api_key: SecretStr = ""
    cohere_api_key: SecretStr = ""
    groq_api_key: SecretStr = ""
    together_api_key: SecretStr = ""
    jina_api_key: SecretStr = ""
    voyage_api_key: SecretStr = ""

    @property
    def service_key_plain(self):
        return self.service_key.get_secret_value()

    @property
    def openai_api_key_plain(self):
        return self.openai_api_key.get_secret_value()

    @property
    def anthropic_api_key_plain(self):
        return self.anthropic_api_key.get_secret_value()

    @property
    def gemini_api_key_plain(self):
        return self.gemini_api_key.get_secret_value()

    @property
    def cohere_api_key_plain(self):
        return self.cohere_api_key.get_secret_value()

    @property
    def groq_api_key_plain(self):
        return self.groq_api_key.get_secret_value()

    @property
    def together_api_key_plain(self):
        return self.together_api_key.get_secret_value()

    @property
    def jina_api_key_plain(self):
        return self.jina_api_key.get_secret_value()

    @property
    def voyage_api_key_plain(self):
        return self.voyage_api_key.get_secret_value()


CONFIG = Config()
setup_logger_sinks()
# We purposely don't intercept uvicorn logs since it is typically not useful
# We also don't intercept transformers logs
replace_logging_handlers(["uvicorn.access"], False)

# Maybe purge Redis data
REDIS = redis.Redis(host=CONFIG.owl_redis_host, port=6379, db=0)
if CONFIG.owl_redis_purge:
    for key in REDIS.scan_iter("<owl>*"):
        REDIS.delete(key)

# Cloud client
if OwlAsync is None or CONFIG.service_key_plain == "":
    owl_client = None
else:
    owl_client = OwlAsync(api_key=CONFIG.service_key_plain)

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
if CONFIG.owl_service != "":
    try:
        router, tags, prefix = services[CONFIG.owl_service]
    except KeyError:
        logger.error(
            f"Invalid service '{CONFIG.owl_service}', choose from: {list(services.keys())}"
        )
        raise
    app.include_router(
        router, prefix=prefix, tags=tags, generate_unique_id_function=custom_generate_unique_id
    )
else:
    # Mount everything
    for service, (router, tags, prefix) in services.items():
        app.include_router(
            router, prefix=prefix, tags=tags, generate_unique_id_function=custom_generate_unique_id
        )


@app.on_event("startup")
async def startup():
    # Temporary for backwards compatibility
    logger.info(f"Using configuration: {CONFIG}")
    # Create db dir
    if not exists(CONFIG.owl_db_dir):
        makedirs(CONFIG.owl_db_dir, exist_ok=True)


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
    project_id, org_id, org_tier = CONFIG.default_project, CONFIG.default_org, "free"
    token, openmeter_id = "", "default"
    quota_reset_at = ""
    quotas = defaultdict(lambda: 1.0)

    # --- OSS Mode --- #
    if CONFIG.service_key_plain == "":
        openai_api_key = CONFIG.openai_api_key_plain
        anthropic_api_key = CONFIG.anthropic_api_key_plain
        gemini_api_key = CONFIG.gemini_api_key_plain
        cohere_api_key = CONFIG.cohere_api_key_plain
        groq_api_key = CONFIG.groq_api_key_plain
        together_api_key = CONFIG.together_api_key_plain
        jina_api_key = CONFIG.jina_api_key_plain
        voyage_api_key = CONFIG.voyage_api_key_plain

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
            if token != CONFIG.service_key_plain:
                _err_mssg = f"Incorrect service key provided: {token}."
                return ORJSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
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
                        "error": "resource_not_found",
                        "message": _err_mssg,
                        "detail": _err_mssg,
                        "request_id": request.state.id,
                        "exception": "ResourceNotFoundError",
                    },
                )
            if token == CONFIG.service_key_plain:
                # Service key auth
                try:
                    project_info = await owl_client.get_project(project_id)
                    org_info = project_info.organization
                    org_id, external_keys = org_info.id, org_info.external_keys
                except ResourceNotFoundError:
                    _err_mssg = f"Project not found: {project_id}."
                    return ORJSONResponse(
                        status_code=status.HTTP_404_NOT_FOUND,
                        content={
                            "error": "resource_not_found",
                            "message": _err_mssg,
                            "detail": f"{_err_mssg} Org data: {org_info}",
                            "request_id": request.state.id,
                            "exception": "ResourceNotFoundError",
                        },
                    )
                except Exception as e:
                    logger.exception(f"Encountered an error while fetching project: {project_id}")
                    return ORJSONResponse(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={
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
                except ResourceNotFoundError:
                    _err_mssg = f"Incorrect API key provided: {token}."
                    return ORJSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={
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
                            "error": "resource_not_found",
                            "message": _err_mssg,
                            "detail": f"{_err_mssg} Org data: {org_info}",
                            "request_id": request.state.id,
                            "exception": "ResourceNotFoundError",
                        },
                    )
                org_id, external_keys = org_info.id, org_info.external_keys
            openmeter_id = org_info.openmeter_id
            quota_reset_at = org_info.quota_reset_at
            org_tier = org_info.tier
            quotas = org_info.quotas
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
    request.state.api_key = token
    request.state.openmeter_id = openmeter_id
    if BillingManager is not None:
        request.state.billing_manager = BillingManager(
            request=request,
            quotas=quotas,
            quota_reset_at=quota_reset_at,
            organization_tier=org_tier,
            openmeter_id=openmeter_id,
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
    if BillingManager is not None:
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


@app.exception_handler(UpgradeTierError)
async def upgrade_tier_exc_handler(request: Request, exc: UpgradeTierError):
    return ORJSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "upgrade_tier",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(InsufficientCreditsError)
async def insufficient_credits_exc_handler(request: Request, exc: InsufficientCreditsError):
    return ORJSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "insufficient_credits",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(PermissionError)
async def permission_error_exc_handler(request: Request, exc: PermissionError):
    return ORJSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "resource_protected",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(FileExistsError)
async def file_exists_exc_handler(request: Request, exc: FileExistsError):
    return ORJSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "resource_exists",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(ResourceExistsError)
async def resource_exists_exc_handler(request: Request, exc: ResourceExistsError):
    return ORJSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "resource_exists",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(FileNotFoundError)
async def file_not_found_exc_handler(request: Request, exc: FileNotFoundError):
    return ORJSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "resource_not_found",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_exc_handler(request: Request, exc: ResourceNotFoundError):
    return ORJSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "resource_not_found",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(TableSchemaFixedError)
async def table_fixed_exc_handler(request: Request, exc: TableSchemaFixedError):
    return ORJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "table_schema_fixed",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(ContextOverflowError)
async def context_overflow_exc_handler(request: Request, exc: ContextOverflowError):
    return ORJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "context_overflow",
            "message": str(exc),
            "detail": str(exc),
            "request_id": request.state.id,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exc_handler(request: Request, exc: RequestValidationError):
    return ORJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Your request contains errors and cannot be processed at this time.",
            "detail": str(exc),
            "request_id": request.state.id,
            "body": exc.body,
            "exception": exc.__class__.__name__,
        },
    )


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    return ORJSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
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
openapi_schema["info"]["x-logo"] = {"url": "https://www.jamaibase.com/favicon.svg"}
app.openapi_schema = openapi_schema

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "owl.entrypoints.api:app",
        reload=False,
        host=CONFIG.owl_host,
        port=CONFIG.owl_port,
        workers=CONFIG.owl_workers,
    )
