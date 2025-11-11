import base64
import pickle
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import filetype
import httpx
from fastapi import Request
from loguru import logger

from owl.configs import ENV_CONFIG
from owl.types import AUDIO_FILE_EXTENSIONS, IMAGE_FILE_EXTENSIONS, ColumnDtype
from owl.utils.billing import OPENTELEMETRY_CLIENT
from owl.utils.io import s3_upload

REQ_COUNTER = OPENTELEMETRY_CLIENT.get_counter("code_executor_requests_total")
REQ_SECONDS = OPENTELEMETRY_CLIENT.get_histogram("code_executor_duration_seconds")
RES_BYTES = OPENTELEMETRY_CLIENT.get_histogram("code_executor_result_bytes")


def _status_class(code: int | None) -> str:
    if code is None:
        return "none"
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "none"
    return f"{c // 100}xx" if 100 <= c <= 599 else "none"


@asynccontextmanager
async def observe_code_execution(
    *,
    organization_id: str,
    project_id: str,
    dtype: str,
):
    start = time.monotonic()
    outcome: str = "ok"
    error_type: str | None = None

    rec: dict[str, Any] = {
        "result_bytes": 0,
        "status_code": None,
    }

    class Recorder:
        def set_result_bytes(self, n: int) -> None:
            rec["result_bytes"] = max(0, int(n))

        def set_status_code(self, code: int) -> None:
            rec["status_code"] = int(code)

    try:
        yield Recorder()
    except Exception as exc:
        outcome = "error"
        error_type = exc.__class__.__name__
        raise
    finally:
        duration = time.monotonic() - start
        labels = {
            "outcome": outcome,
            "error_type": error_type or "",
            "status_class": _status_class(rec["status_code"]),
            "status_code": rec["status_code"] or 0,
            "org_id": organization_id,
            "proj_id": project_id,
            "dtype": dtype,
        }
        REQ_COUNTER.add(1, labels)
        REQ_SECONDS.record(duration, labels)
        RES_BYTES.record(rec["result_bytes"], labels)


async def code_executor(
    *,
    request: Request,
    organization_id: str,
    project_id: str,
    source_code: str,
    output_column: str,
    row_data: dict | None,
    dtype: str,
) -> str:
    async with observe_code_execution(
        organization_id=organization_id,
        project_id=project_id,
        dtype=dtype,
    ) as rec:
        try:
            async with httpx.AsyncClient(timeout=ENV_CONFIG.code_timeout_sec) as client:
                row_data = base64.b64encode(pickle.dumps(row_data)).decode("utf-8")
                response = await client.post(
                    f"{ENV_CONFIG.code_executor_endpoint}/execute",
                    json={
                        "source_code": source_code,
                        "output_column": output_column,
                        "row_data": row_data,
                    },
                )
                rec.set_status_code(response.status_code)
                response.raise_for_status()
                result = pickle.loads(base64.b64decode(response.text.strip('"')))

                # Return early if output column is ColumnDtype.STR
                if dtype == ColumnDtype.STR:
                    rec.set_result_bytes(len(str(result).encode("utf-8")))
                    logger.info(
                        f"Code Executor: {request.state.id} - Python code execution completed for column {output_column}"
                    )
                    return str(result)

                if not isinstance(result, bytes):
                    raise Exception(
                        f"Expected type bytes for {dtype}, got {type(result)}:\n\n{str(result)[:100]}"
                    )

                rec.set_result_bytes(len(result))

                content_type = filetype.guess(result)
                if not content_type:
                    raise Exception("Result is bytes but could not determine content type")

                file_extension = f".{content_type.extension}"

                # Handle different data types
                if (dtype == ColumnDtype.IMAGE and file_extension in IMAGE_FILE_EXTENSIONS) or (
                    dtype == ColumnDtype.AUDIO and file_extension in AUDIO_FILE_EXTENSIONS
                ):
                    filename = f"{uuid.uuid4()}{file_extension}"
                    # Upload the file
                    uri = await s3_upload(
                        organization_id=organization_id,
                        project_id=project_id,
                        content=result,
                        content_type=content_type.mime,
                        filename=filename,
                    )
                    logger.info(
                        f"Code Executor: {request.state.id} - Python code execution completed for column {output_column}"
                    )
                    return uri

        except Exception as e:
            logger.error(
                f"Code Executor: {request.state.id} - Python code execution encountered error for column {output_column} : {e}"
            )
            raise
