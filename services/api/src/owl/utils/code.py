import base64
import uuid

import filetype
import httpx
from fastapi import Request
from loguru import logger

from owl.configs.manager import ENV_CONFIG
from owl.utils.io import upload_file_to_s3


async def code_executor(source_code: str, dtype: str, request: Request) -> str | None:
    response = None

    try:
        if dtype == "image":
            dtype = "file"  # for code execution endpoint usage
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ENV_CONFIG.code_executor_endpoint}/execute",
                json={"code": source_code},
            )
            response.raise_for_status()
            result = response.json()

            if dtype == "file":
                if result["type"].startswith("image"):
                    image_content = base64.b64decode(result["result"])
                    content_type = filetype.guess(image_content)
                    if content_type is None:
                        raise ValueError("Unable to determine file type")
                    filename = f"{uuid.uuid4()}.{content_type.extension}"

                    # Upload the file
                    uri = await upload_file_to_s3(
                        organization_id=request.state.org_id,
                        project_id=request.state.project_id,
                        content=image_content,
                        content_type=content_type.mime,
                        filename=filename,
                    )
                    response = uri
                else:
                    logger.warning(
                        f"Code Executor: {request.state.id} - Unsupported file type: {result['type']}"
                    )
                    response = None
            else:
                response = str(result["result"])

            logger.info(f"Code Executor: {request.state.id} - Python code execution completed")

    except Exception as e:
        logger.error(f"Code Executor: {request.state.id} - An unexpected error occurred: {e}")
        response = None

    return response
