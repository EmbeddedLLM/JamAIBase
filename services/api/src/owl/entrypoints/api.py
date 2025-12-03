import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from gunicorn.app.base import BaseApplication
from loguru import logger
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

from owl.configs import CACHE, ENV_CONFIG
from owl.db import create_db_engine_async, init_db, migrate_db, reset_db
from owl.routers import (
    auth,
    conversation,
    file,
    gen_table,
    gen_table_v1,
    meters,
    models,
    organizations,
    projects,
    serving,
    tasks,
    templates,
    users,
)
from owl.routers.projects import v1 as projects_v1
from owl.types import UserAgent
from owl.utils import uuid7_str
from owl.utils.billing import CLICKHOUSE_CLIENT, BillingManager
from owl.utils.exceptions import JamaiException
from owl.utils.handlers import exception_handler, make_request_log_str, path_not_found_handler
from owl.utils.io import HTTP_ACLIENT
from owl.utils.logging import setup_logger_sinks, suppress_logging_handlers
from owl.utils.mcp import get_mcp_router
from owl.utils.mcp.server import MCP_TOOL_TAG

OVERHEAD_LOG_ROUTES = {r.path for r in serving.router.routes}
# logger.enable("owl")
setup_logger_sinks(None)
# We purposely don't intercept uvicorn logs since it is typically not useful
# We also don't intercept transformers logs
# replace_logging_handlers(["uvicorn.access"], False)
suppress_logging_handlers(["uvicorn", "litellm", "azure", "openmeter", "pottery"], True)

# --- Setup DB --- #
# Maybe reset DB
if ENV_CONFIG.db_reset:
    asyncio.run(reset_db(reset_max_users=ENV_CONFIG.db_init_max_users))
# Migration
asyncio.run(migrate_db())
# Maybe populate DB with demo data
# If OSS and first launch, init user, organization and project
if ENV_CONFIG.db_init:
    asyncio.run(init_db(init_max_users=ENV_CONFIG.db_init_max_users))
# Maybe reset cache
if ENV_CONFIG.cache_reset:
    CACHE.purge()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info(f"Using configuration: {ENV_CONFIG}")
    yield
    logger.info("Shutting down...")

    # Close DB connection
    logger.info("Closing DB connection.")
    try:
        await create_db_engine_async().dispose()
    except Exception as e:
        logger.warning(f"Failed to close DB connection: {repr(e)}")

    # Close Redis connection
    logger.info("Closing Redis connection.")
    try:
        await CACHE.aclose()
    except Exception as e:
        logger.warning(f"Failed to close Redis connection: {repr(e)}")

    # Flush buffer
    logger.info("Flushing redis buffer to database.")
    try:
        await CLICKHOUSE_CLIENT.flush_buffer()
    except Exception as e:
        logger.warning(f"Failed to flush buffer: {repr(e)}")
    finally:
        await CLICKHOUSE_CLIENT.close()

    # Close HTTPX client
    await HTTP_ACLIENT.aclose()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="JamAI Base API",
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
    lifespan=lifespan,
)

# Programmatic Instrumentation
FastAPIInstrumentor.instrument_app(app)
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()

# Mount
internal_api_tag = "" if ENV_CONFIG.is_oss else " (Internal API)"
app.include_router(
    models.router,
    prefix="/api",
    tags=["Models" + internal_api_tag],
)
app.include_router(
    auth.router,
    prefix="/api",
    tags=["Authentication" + internal_api_tag],
)
app.include_router(
    users.router,
    prefix="/api",
    tags=["Users" + internal_api_tag],
)
app.include_router(
    organizations.router,
    prefix="/api",
    tags=["Organizations" + internal_api_tag],
)
app.include_router(
    projects.router,
    prefix="/api",
    tags=["Projects"],
)
app.include_router(
    projects_v1.router,
    deprecated=True,
    prefix="/api/admin/org",
    tags=["Organization Admin (Legacy)"],
)
app.include_router(
    templates.router,
    prefix="/api",
    tags=["Templates"],
)
app.include_router(
    conversation.router,
    prefix="/api",
    tags=["Conversations"],
)
app.include_router(
    gen_table.router,
    prefix="/api",
    tags=["Generative Table (V2)"],
)
app.include_router(
    gen_table_v1.router,
    prefix="/api",
    tags=["Generative Table (V1)"],
    deprecated=True,
)
app.include_router(
    serving.router,
    prefix="/api",
    tags=["Serving"],
)
app.include_router(
    file.router,
    prefix="/api",
    tags=["File"],
)
app.include_router(
    tasks.router,
    prefix="/api",
    tags=["Tasks"],
)
app.include_router(
    meters.router,
    prefix="/api",
    tags=["Meters" + internal_api_tag],
)
if ENV_CONFIG.is_cloud:
    from owl.routers.cloud import logs, prices

    app.include_router(
        prices.router,
        prefix="/api",
        tags=["Prices"],
    )
    app.include_router(
        logs.router,
        prefix="/api",
        tags=["Logs (Internal Cloud-only API)"],
    )
app.include_router(
    get_mcp_router(app),
    prefix="/api",
    tags=["Model Context Protocol (MCP)"],
)


# Permissive CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(JamaiException, exception_handler)  # Suppress starlette traceback
app.add_exception_handler(Exception, exception_handler)
app.add_exception_handler(404, path_not_found_handler)


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
    request.state.request_start_time = perf_counter()
    # Set request state
    request_id = request.headers.get("x-request-id", uuid7_str())
    request.state.id = request_id
    request.state.user_agent = UserAgent.from_user_agent_string(
        request.headers.get("user-agent", "")
    )
    request.state.timing = defaultdict(float)

    # Call request
    path = request.url.path
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        logger.info(make_request_log_str(request))
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    if "api/health" not in path:
        logger.info(make_request_log_str(request, response.status_code))

    # Process billing (this will run BEFORE any responses are sent)
    if hasattr(request.state, "billing"):
        billing: BillingManager = request.state.billing
        # Add egress events
        # This does not include SSE egress, and will need to be captured separately
        egress_bytes = float(response.headers.get("content-length", 0))
        if egress_bytes > 0:
            billing.create_egress_events(egress_bytes / (1024**3))
        # Background tasks will run AFTER streaming responses are sent
        tasks = BackgroundTasks()
        tasks.add_task(billing.process_all)
        response.background = tasks
    # Log timing
    model_start_time = getattr(request.state, "model_start_time", None)
    if (
        ENV_CONFIG.log_timings
        and model_start_time
        and any(p for p in OVERHEAD_LOG_ROUTES if p in path)
    ):
        overhead = model_start_time - request.state.request_start_time
        breakdown = {k: f"{v * 1e3:,.1f} ms" for k, v in request.state.timing.items()}
        logger.info(
            f"{request.state.id} - Total overhead: {overhead * 1e3:,.1f} ms. Breakdown: {breakdown}"
        )
    return response


@app.get("/api/health", tags=["Health"])
async def health() -> ORJSONResponse:
    """Health check."""
    return ORJSONResponse(
        status_code=200,
        content={"is_oss": ENV_CONFIG.is_oss},
    )


# Process OpenAPI docs
openapi_schema = app.openapi()
# Remove MCP and permission tags
for path_info in openapi_schema["paths"].values():
    for method_info in path_info.values():
        tags = method_info["tags"]
        tags = [
            tag
            for tag in tags
            if not (tag == MCP_TOOL_TAG or tag.startswith(("system", "organization", "project")))
        ]
        method_info["tags"] = tags
# Re-order paths to put internal APIs last
if ENV_CONFIG.is_cloud:
    openapi_schema["paths"] = {
        k: openapi_schema["paths"][k]
        for k in sorted(
            openapi_schema["paths"].keys(),
            key=lambda p: internal_api_tag
            in list(openapi_schema["paths"][p].values())[0]["tags"][0],
        )
    }
if ENV_CONFIG.is_cloud:
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "Authentication": {"type": "http", "scheme": "bearer"},
    }
    openapi_schema["security"] = [{"Authentication": []}]
    openapi_schema["info"]["x-logo"] = {"url": "https://www.jamaibase.com/favicon.svg"}
app.openapi_schema = openapi_schema


class StandaloneApplication(BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


# Gunicorn post_fork hook
def post_fork(server, worker):
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from owl.utils.loguru_otlp_handler import OTLPHandler

    # from opentelemetry.instrumentation.auto_instrumentation import sitecustomize
    # trace.set_tracer_provider(trace.get_tracer_provider())
    # metrics.set_meter_provider(metrics.get_meter_provider())

    # for manual instrumentation

    resource = Resource.create(
        {
            "service.name": "owl",
            "service.instance.id": uuid7_str(),
        }
    )
    # Meter provider configuration
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=f"http://{ENV_CONFIG.opentelemetry_host}:{ENV_CONFIG.opentelemetry_port}"
        ),
        export_interval_millis=1000,
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    # Trace provider configuration
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"http://{ENV_CONFIG.opentelemetry_host}:{ENV_CONFIG.opentelemetry_port}"
            )
        )
    )
    trace.set_tracer_provider(trace_provider)

    # # for auto-instrumentation
    # trace.get_tracer_provider()
    # metrics.get_meter_provider()
    # Configure the OTLP Exporter
    otlp_exporter = OTLPLogExporter(
        endpoint=f"http://{ENV_CONFIG.opentelemetry_host}:{ENV_CONFIG.opentelemetry_port}"
    )

    # Create an instance of OTLPHandler
    otlp_handler = OTLPHandler.create(
        service_name="owl",
        exporter=otlp_exporter,
        development_mode=False,  # Set to True for development
    )

    logger.add(otlp_handler.sink, level="INFO")
    server.log.info(f"Worker spawned (pid: {worker.pid})")


if __name__ == "__main__":
    options = {
        "bind": f"{ENV_CONFIG.host}:{ENV_CONFIG.port}",
        "workers": ENV_CONFIG.workers,
        "worker_class": "uvicorn.workers.UvicornWorker",
        "limit_concurrency": ENV_CONFIG.max_concurrency,
        "timeout": 600,
        "graceful_timeout": 60,
        "max_requests": 2000,
        "max_requests_jitter": 200,
        "keepalive": 60,  # AWS ALB and Nginx default to 60 seconds
        "post_fork": post_fork,
        "loglevel": "error",
    }
    StandaloneApplication(app, options).run()
