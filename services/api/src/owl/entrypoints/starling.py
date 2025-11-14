"""
Starling server.

```shell
$ celery -A owl.entrypoints.starling worker --loglevel=info --max-memory-per-child 976562 --autoscale=4,2
$ celery -A owl.entrypoints.starling beat --loglevel=info
(Optional) $ celery -A owl.entrypoints.starling flower --loglevel=info
```
"""

from datetime import timedelta

from celery.schedules import crontab
from celery.signals import worker_process_init
from loguru import logger
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from owl.configs import ENV_CONFIG, celery_app
from owl.utils import uuid7_str
from owl.utils.logging import (
    replace_logging_handlers,
    setup_logger_sinks,
    suppress_logging_handlers,
)
from owl.utils.loguru_otlp_handler import OTLPHandler

logger.enable("")
setup_logger_sinks(None)
replace_logging_handlers(["uvicorn.access"], False)
suppress_logging_handlers(["uvicorn", "litellm", "azure", "openmeter", "pottery"], True)


@worker_process_init.connect(weak=False)
def init_celery_tracing(*args, **kwargs):
    CeleryInstrumentor().instrument()

    resource = Resource.create(
        {
            "service.name": "starling",
            "service.instance.id": uuid7_str(),
        }
    )
    # Meter provider configuration
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=f"http://{ENV_CONFIG.opentelemetry_host}:{ENV_CONFIG.opentelemetry_port}"
        ),
        export_interval_millis=1,
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    # Trace provider configuration
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"http://{ENV_CONFIG.opentelemetry_host}:{ENV_CONFIG.opentelemetry_port}"
            ),
            schedule_delay_millis=1,
        )
    )
    trace.set_tracer_provider(trace_provider)

    otlp_exporter = OTLPLogExporter(
        endpoint=f"http://{ENV_CONFIG.opentelemetry_host}:{ENV_CONFIG.opentelemetry_port}"
    )

    # Create an instance of OTLPHandler
    otlp_handler = OTLPHandler.create(
        service_name="starling",
        exporter=otlp_exporter,
        development_mode=False,  # Set to True for development
        export_interval_ms=1,
    )

    logger.add(otlp_handler.sink, level="INFO")


# Load task modules
celery_app.conf.imports = [
    # "owl.tasks.checks",
    "owl.tasks.database",
    "owl.tasks.gen_table",
    "owl.tasks.genitor",
]

# Configure the scheduler
# celery_app.conf.beat_schedule = {
#     "periodic-model-check": {
#         "task": "owl.tasks.checks.test_models",
#         "schedule": crontab(minute="*/10"),
#     }
# }

# Add periodic storage update task if service_key_plain is not empty
if ENV_CONFIG.service_key_plain != "":
    celery_app.conf.beat_schedule["periodic-flush-clickhouse-buffer"] = {
        "task": "owl.tasks.database.run_periodic_flush_buffer",
        "schedule": timedelta(seconds=ENV_CONFIG.flush_clickhouse_buffer_sec),
    }

# Check if S3-related environment variables are present and non-empty
if all(
    getattr(ENV_CONFIG, attr, "")  # Use getattr to safely access attributes
    for attr in [
        "s3_endpoint",
        "s3_access_key_id",
        "s3_secret_access_key",
        "s3_backup_bucket_name",
    ]
):
    logger.info("S3 Backup tasks has been configured.")
    celery_app.conf.beat_schedule.update(
        {
            "backup-to-s3": {
                "task": "owl.tasks.genitor.backup_to_s3",
                "schedule": crontab(minute="0", hour="*"),
            },
            "s3-cleanup": {
                "task": "owl.tasks.genitor.s3_cleanup",
                "schedule": crontab(minute="0", hour="*/24"),
            },
        }
    )
else:
    logger.info("S3 Backup tasks is not configured.")
