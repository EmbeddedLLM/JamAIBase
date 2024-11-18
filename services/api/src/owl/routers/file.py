import mimetypes
import os
from typing import Annotated
from urllib.parse import quote, urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

from jamaibase.exceptions import ResourceNotFoundError
from owl.configs.manager import ENV_CONFIG
from owl.protocol import FileUploadResponse, GetURLRequest, GetURLResponse
from owl.utils.auth import ProjectRead, auth_user_project
from owl.utils.exceptions import handle_exception
from owl.utils.io import (
    LOCAL_FILE_DIR,
    S3_CLIENT,
    UPLOAD_WHITE_LIST_MIME,
    get_s3_aclient,
    upload_file_to_s3,
)

HTTP_ACLIENT = httpx.AsyncClient() if S3_CLIENT else None
router = APIRouter()


async def _generate_presigned_url(s3_client, bucket_name: str, key: str) -> str:
    response = await s3_client.list_objects_v2(Bucket=bucket_name, Prefix=key, MaxKeys=1)
    if "Contents" not in response:
        return ""
    presigned_url = await s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": key},
        ExpiresIn=3600,
    )
    parsed_url = urlparse(presigned_url)
    return urlunparse(
        (
            parsed_url.scheme,
            ENV_CONFIG.owl_file_proxy_url,
            "/api/v1/files" + parsed_url.path,
            parsed_url.params,
            parsed_url.query,
            parsed_url.fragment,
        )
    )


@router.get("/v1/files/{path:path}")
@handle_exception
async def proxy_file(request: Request, path: str) -> Response:
    if HTTP_ACLIENT:
        # S3 file handling
        encoded_path = quote(path)
        original_url = f"{ENV_CONFIG.s3_endpoint}/{encoded_path}?{request.query_params}"
        response = await HTTP_ACLIENT.get(original_url)
        # Determine the MIME type
        mime_type, _ = mimetypes.guess_type(original_url)
        if mime_type is None:
            mime_type = "application/octet-stream"
        # Set the Content-Disposition header
        headers = dict(response.headers)
        headers["Content-Disposition"] = "inline"
        headers["Content-Type"] = mime_type
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=headers,
        )

    elif os.path.exists(LOCAL_FILE_DIR):
        # Local file handling
        file_path = os.path.join(LOCAL_FILE_DIR, path)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise ResourceNotFoundError(
                "Requested resource in not found in configured local file store."
            )
        # Determine the MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"
        return FileResponse(
            path=file_path,
            media_type=mime_type,
            filename=os.path.basename(file_path),
            content_disposition_type="inline",
        )

    else:
        raise ResourceNotFoundError("Neither S3 nor local file store is configured")


@router.options("/v1/files/upload/")
@handle_exception
async def upload_file_options():
    headers = {
        "Allow": "POST, OPTIONS",
        "Accept": ", ".join(UPLOAD_WHITE_LIST_MIME),
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
    }
    return JSONResponse(content={"accepted_types": list(UPLOAD_WHITE_LIST_MIME)}, headers=headers)


@router.post("/v1/files/upload/")
@handle_exception
async def upload_file(
    project: Annotated[ProjectRead, Depends(auth_user_project)],
    file: UploadFile,
) -> FileUploadResponse:
    content = await file.read()
    uri = await upload_file_to_s3(
        project.organization.id, project.id, content, file.content_type, file.filename
    )
    return FileUploadResponse(uri=uri)


@router.post("/v1/files/url/raw", response_model=GetURLResponse)
@handle_exception
async def get_raw_file_urls(body: GetURLRequest, request: Request) -> GetURLResponse:
    results = []
    if S3_CLIENT:
        # S3 file store
        async with get_s3_aclient() as aclient:
            for uri in body.uris:
                file_url = ""
                if uri.startswith("s3://"):
                    try:
                        bucket_name, key = uri[5:].split("/", 1)
                        file_url = await _generate_presigned_url(aclient, bucket_name, key)
                    except Exception as e:
                        logger.exception(
                            f'Error generating URL for "{uri}" due to {e.__class__.__name__}: {e}'
                        )
                results.append(file_url)
    else:
        # Local file store
        for uri in body.uris:
            file_url = ""
            if uri.startswith("file://"):
                try:
                    local_path = os.path.abspath(uri[7:])
                    if os.path.exists(local_path):
                        # Generate a URL for the local file
                        relative_path = os.path.relpath(local_path, LOCAL_FILE_DIR)
                        file_url = str(request.url_for("proxy_file", path=relative_path))
                except Exception as e:
                    logger.exception(
                        f'Error generating URL for "{uri}" due to {e.__class__.__name__}: {e}'
                    )
            results.append(file_url)
    return GetURLResponse(urls=results)


@router.post("/v1/files/url/thumb", response_model=GetURLResponse)
@handle_exception
async def get_thumbnail_urls(body: GetURLRequest, request: Request) -> GetURLResponse:
    results = []
    if S3_CLIENT:
        # S3 file store
        async with get_s3_aclient() as aclient:
            for uri in body.uris:
                file_url = ""
                if uri.startswith("s3://"):
                    try:
                        bucket_name, key = uri[5:].split("/", 1)
                        thumb_key = key.replace("raw", "thumb")
                        thumb_key = f"{os.path.splitext(thumb_key)[0]}.webp"
                        file_url = await _generate_presigned_url(aclient, bucket_name, thumb_key)
                    except Exception as e:
                        logger.exception(
                            f'Error generating URL for "{uri}" due to {e.__class__.__name__}: {e}'
                        )
                results.append(file_url)
    else:
        # Local file store
        for uri in body.uris:
            file_url = ""
            if uri.startswith("file://"):
                try:
                    local_path = os.path.abspath(uri[7:])
                    thumb_path = local_path.replace("raw", "thumb")
                    thumb_path = f"{os.path.splitext(thumb_path)[0]}.webp"
                    if os.path.exists(thumb_path):
                        relative_path = os.path.relpath(thumb_path, LOCAL_FILE_DIR)
                        file_url = str(request.url_for("proxy_file", path=relative_path))
                except Exception as e:
                    logger.exception(
                        f'Error generating URL for "{uri}" due to {e.__class__.__name__}: {e}'
                    )
            results.append(file_url)
    return GetURLResponse(urls=results)
