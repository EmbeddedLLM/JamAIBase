"""
Adapted from: https://github.com/s71m/opentelemetry-loguru-telegram/blob/master/utils/loguru_otlp_handler.py
"""

import atexit
import queue
import signal
import sys
import threading
import time
import traceback
from time import time_ns
from typing import Any, ClassVar, Dict

from loguru import logger
from opentelemetry import trace
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs._internal import LoggerProvider, LogRecord
from opentelemetry.sdk._logs._internal.export import BatchLogRecordProcessor, LogExporter
from opentelemetry.sdk.resources import Resource

# Constants
MAX_QUEUE_SIZE = 10000

# Simplified severity mapping
SEVERITY_MAPPING = {
    10: SeverityNumber.DEBUG,
    20: SeverityNumber.INFO,
    30: SeverityNumber.WARN,
    40: SeverityNumber.ERROR,
    50: SeverityNumber.FATAL,
}


class OTLPHandler:
    _instances: ClassVar[list["OTLPHandler"]] = []  # Changed from set to list for safe iteration
    _shutdown_lock: ClassVar[threading.Lock] = threading.Lock()
    _is_shutting_down: ClassVar[bool] = False

    def __init__(
        self,
        service_name: str,
        exporter: LogExporter,
        max_queue_size: int = MAX_QUEUE_SIZE,
        batch_size: int = 100,
        export_interval_ms: int = 1000,
    ):
        self._resource = Resource(
            {
                "service.name": service_name,
                # "service.instance.id": uuid7_str(),
            }
        )
        self._queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=max_queue_size)
        self._shutdown_event = threading.Event()
        # self._flush_complete = threading.Event()

        # Initialize logger provider with resource
        self._logger_provider = LoggerProvider(resource=self._resource)
        self._logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                exporter,
                max_export_batch_size=batch_size,
                schedule_delay_millis=export_interval_ms,
                export_timeout_millis=5000,
            )
        )
        self._logger = self._logger_provider.get_logger(service_name)

        # Start worker thread
        self._worker = threading.Thread(target=self._process_queue, name="loguru_otlp_worker")
        self._worker.daemon = True
        self._worker.start()

        # Register this instance
        with self._shutdown_lock:
            self.__class__._instances.append(self)

        # Register shutdown handlers only once
        if len(self._instances) == 1:
            atexit.register(self._shutdown_all_handlers)
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

    def _get_trace_context(self) -> tuple:
        """Get the current trace context."""
        span_context = trace.get_current_span().get_span_context()
        return (
            span_context.trace_id if span_context.is_valid else 0,
            span_context.span_id if span_context.is_valid else 0,
            span_context.trace_flags if span_context.is_valid else 0,
        )

    def _get_severity(self, level_no: int) -> tuple:
        """Map Loguru level to OpenTelemetry severity."""
        base_level = (level_no // 10) * 10
        return (
            SEVERITY_MAPPING.get(base_level, SeverityNumber.UNSPECIFIED),
            "CRITICAL"
            if level_no >= 50
            else "ERROR"
            if level_no >= 40
            else "WARNING"
            if level_no >= 30
            else "INFO"
            if level_no >= 20
            else "DEBUG",
        )

    def _extract_attributes(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Extract attributes from the record."""
        attributes = {
            "code.filepath": record["file"].path,
            "code.function": record["function"],
            "code.lineno": record["line"],
            "filename": record["file"].name,
        }

        # Add extra attributes if present
        extra = record.get("extra", {})
        if isinstance(extra, dict):
            for k, v in extra.items():
                if isinstance(v, (str, int, float, bool)):
                    attributes[k] = v
                else:
                    attributes[k] = repr(v)
        else:
            pass

        # Handle exception information
        if "exception" in record and record["exception"]:
            exc_type, exc_value, exc_tb = record["exception"]
            if exc_type:
                attributes.update(
                    {
                        "exception.type": exc_type.__name__,
                        "exception.message": str(exc_value) if exc_value else "No message",
                        "exception.stacktrace": "".join(
                            traceback.format_exception(exc_type, exc_value, exc_tb)
                        )
                        if exc_tb
                        else "No stacktrace",
                    }
                )

        return attributes

    def _create_log_record(self, record: Dict[str, Any]) -> LogRecord:
        """Create an OpenTelemetry LogRecord."""
        severity_number, severity_text = self._get_severity(record["level"].no)
        trace_id, span_id, trace_flags = self._get_trace_context()

        if "exception" in record and record["exception"]:
            severity_number = SeverityNumber.FATAL
            severity_text = "CRITICAL"

        return LogRecord(
            timestamp=int(record["time"].timestamp() * 1e9),
            observed_timestamp=time_ns(),
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=trace_flags,
            severity_text=severity_text,
            severity_number=severity_number,
            body=record["message"],
            resource=self._logger.resource,
            attributes=self._extract_attributes(record),
        )

    @classmethod
    def _shutdown_all_handlers(cls):
        """Shutdown all handler instances safely."""
        with cls._shutdown_lock:
            if cls._is_shutting_down:
                return
            cls._is_shutting_down = True

            # Create a copy of instances for safe iteration
            handlers = cls._instances.copy()

        # Shutdown each handler
        for handler in handlers:
            try:
                handler.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down handler: {e}", file=sys.stderr)

        # Clear the instances list
        with cls._shutdown_lock:
            cls._instances.clear()

    @classmethod
    def _signal_handler(cls, signum, frame):
        """Handle termination signals."""
        logger.info("\nShutting down logger...", file=sys.stderr)
        cls._shutdown_all_handlers()
        sys.exit(0)

    def _process_queue(self) -> None:
        """Process logs from the queue until shutdown."""
        while not self._shutdown_event.is_set() or not self._queue.empty():
            try:
                try:
                    record = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if record is None:
                    self._queue.task_done()
                    continue

                log_record = self._create_log_record(record)
                self._logger.emit(log_record)
                self._queue.task_done()

            except Exception as e:
                logger.warning(f"Error processing log record: {e}", file=sys.stderr)

    def sink(self, message) -> None:
        """Add log message to queue."""
        if self._shutdown_event.is_set():
            return

        try:
            self._queue.put_nowait(message.record)
        except queue.Full:
            logger.warning("Warning: Log queue full, dropping message", file=sys.stderr)

    def shutdown(self) -> None:
        """Graceful shutdown of the handler."""
        if self._shutdown_event.is_set():
            return

        try:
            # Signal shutdown
            self._shutdown_event.set()
            # Wait for queue to empty
            try:
                # Wait with timeout
                if not self._queue.empty():
                    # Give some time for the queue to process
                    timeout = 5.0  # 5 seconds timeout
                    start_time = time.time()

                    while not self._queue.empty() and (time.time() - start_time) < timeout:
                        time.sleep(0.1)

                    if not self._queue.empty():
                        logger.warning("Warning: Queue not empty after timeout", file=sys.stderr)

                # Force flush remaining logs
                # self._logger_provider.force_flush(timeout_millis=5000)

                # Wait for flush completion
                # self._flush_complete.wait(timeout=1.0)

            except Exception as e:
                logger.warning(f"Error during queue processing: {e}", file=sys.stderr)

            # Final shutdown of logger provider
            self._logger_provider.shutdown()

        except Exception as e:
            logger.warning(f"Error during shutdown: {e}", file=sys.stderr)

    @classmethod
    def create(
        cls,
        service_name: str,
        exporter: LogExporter,
        development_mode: bool = False,
        export_interval_ms: int = 1000,
    ) -> "OTLPHandler":
        """Factory method with environment-specific configurations."""
        if development_mode:
            return cls(
                service_name=service_name,
                exporter=exporter,
                max_queue_size=1000,
                batch_size=50,
                export_interval_ms=500,
            )

        return cls(
            service_name=service_name,
            exporter=exporter,
            max_queue_size=MAX_QUEUE_SIZE,
            batch_size=100,
            export_interval_ms=export_interval_ms,
        )
