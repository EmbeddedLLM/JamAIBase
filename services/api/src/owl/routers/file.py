import os
from os.path import splitext
from typing import Annotated
from urllib.parse import quote, urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import ORJSONResponse
from loguru import logger

from owl.configs import ENV_CONFIG
from owl.types import (
    FileUploadResponse,
    GetURLRequest,
    GetURLResponse,
    OrganizationRead,
    ProjectRead,
    UserAuth,
)
from owl.utils.auth import auth_user_project, has_permissions
from owl.utils.billing import BillingManager
from owl.utils.exceptions import handle_exception
from owl.utils.io import (
    AUDIO_WHITE_LIST_EXT,
    NON_PDF_DOC_WHITE_LIST_EXT,
    UPLOAD_WHITE_LIST_MIME,
    get_global_thumbnail_path,
    get_s3_aclient,
    guess_mime,
    s3_upload,
)

HTTP_ACLIENT = httpx.AsyncClient(
    timeout=10.0,
    transport=httpx.AsyncHTTPTransport(retries=3),
)
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
            ENV_CONFIG.file_proxy_url,
            "/api/v2/files" + parsed_url.path,
            parsed_url.params,
            parsed_url.query,
            parsed_url.fragment,
        )
    )


@router.get("/v2/files/{path:path}")
@router.get("/v1/files/{path:path}", deprecated=True)
@handle_exception
async def proxy_file(request: Request, path: str) -> Response:
    encoded_path = quote(path)
    original_url = f"{ENV_CONFIG.s3_endpoint}/{encoded_path}?{request.query_params}"
    response = await HTTP_ACLIENT.get(original_url)
    # Set the Content-Disposition header
    response.headers["Content-Disposition"] = "inline"
    # Usually we can get the MIME type from S3 metadata
    if "Content-Type" not in response.headers:
        response.headers["Content-Type"] = guess_mime(path)
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=response.headers,
    )


@router.options(
    "/v2/files/upload",
    summary="Get CORS preflight options for file upload endpoint.",
)
@router.options("/v1/files/upload", deprecated=True)
@handle_exception
async def upload_file_options():
    headers = {
        "Allow": "POST, OPTIONS",
        "Accept": ", ".join(UPLOAD_WHITE_LIST_MIME),
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
    }
    return ORJSONResponse(
        content={"accepted_types": list(UPLOAD_WHITE_LIST_MIME)},
        headers=headers,
    )


@router.post(
    "/v2/files/upload",
    summary="Upload a file to the server.",
    description="Permissions: `organization` OR `project`.",
)
@router.post("/v1/files/upload", deprecated=True)
@handle_exception
async def upload_file(
    request: Request,
    auth_info: Annotated[
        tuple[UserAuth, ProjectRead, OrganizationRead], Depends(auth_user_project)
    ],
    file: UploadFile,
) -> FileUploadResponse:
    user, project, org = auth_info
    has_permissions(
        user,
        ["organization", "project"],
        organization_id=org.id,
        project_id=project.id,
    )
    # Check quota
    billing: BillingManager = request.state.billing
    billing.has_file_storage_quota()
    content = await file.read()
    uri = await s3_upload(
        project.organization.id,
        project.id,
        content,
        content_type=file.content_type,
        filename=file.filename,
    )
    return FileUploadResponse(uri=uri)


@router.post("/v2/files/url/raw")
@router.post("/v1/files/url/raw", deprecated=True)
@handle_exception
async def get_raw_file_urls(body: GetURLRequest) -> GetURLResponse:
    results = []
    async with get_s3_aclient() as aclient:
        for uri in body.uris:
            file_url = ""
            try:
                bucket_name, key = uri[5:].split("/", 1)
                file_url = await _generate_presigned_url(aclient, bucket_name, key)
            except Exception as e:
                err_mssg = str(e)
                if "NoSuchBucket" in err_mssg:
                    pass
                else:
                    logger.exception(
                        f'Error generating URL for "{uri}" due to {e.__class__.__name__}: {e}'
                    )
            results.append(file_url)
    return GetURLResponse(urls=results)


@router.post("/v2/files/url/thumb")
@router.post("/v1/files/url/thumb", deprecated=True)
@handle_exception
async def get_thumbnail_urls(body: GetURLRequest) -> GetURLResponse:
    results = []
    async with get_s3_aclient() as aclient:
        for uri in body.uris:
            file_url = ""
            try:
                ext = splitext(uri)[1].lower()
                bucket_name, key = uri[5:].split("/", 1)
                thumb_ext = "mp3" if ext in AUDIO_WHITE_LIST_EXT else "webp"
                if ext in NON_PDF_DOC_WHITE_LIST_EXT:
                    thumb_key = os.path.join(
                        key[: key.index("raw/")],
                        get_global_thumbnail_path(ext),
                    )
                else:
                    thumb_key = key.replace("raw", "thumb")
                    thumb_key = f"{os.path.splitext(thumb_key)[0]}.{thumb_ext}"
                file_url = await _generate_presigned_url(aclient, bucket_name, thumb_key)
            except Exception as e:
                err_mssg = str(e)
                if "NoSuchBucket" in err_mssg:
                    pass
                else:
                    logger.exception(
                        f'Error generating URL for "{uri}" due to {e.__class__.__name__}: {e}'
                    )
            results.append(file_url)
    return GetURLResponse(urls=results)
