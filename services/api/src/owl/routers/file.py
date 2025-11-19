import os
from os.path import splitext
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import ORJSONResponse

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
    HTTP_ACLIENT,
    NON_PDF_DOC_WHITE_LIST_EXT,
    UPLOAD_WHITE_LIST_MIME,
    generate_presigned_s3_url,
    get_global_thumbnail_path,
    get_s3_aclient,
    guess_mime,
    s3_upload,
)

router = APIRouter()


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
            if uri.startswith("s3://"):
                bucket_name, key = uri[5:].split("/", 1)
                file_url = await generate_presigned_s3_url(aclient, bucket_name, key)
            elif uri.startswith(("http://", "https://")):
                file_url = uri
            else:
                file_url = ""
            results.append(file_url)
    return GetURLResponse(urls=results)


@router.post("/v2/files/url/thumb")
@router.post("/v1/files/url/thumb", deprecated=True)
@handle_exception
async def get_thumbnail_urls(body: GetURLRequest) -> GetURLResponse:
    results = []
    async with get_s3_aclient() as aclient:
        for uri in body.uris:
            if uri.startswith("s3://"):
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
                file_url = await generate_presigned_s3_url(aclient, bucket_name, thumb_key)
            elif uri.startswith(("http://", "https://")):
                file_url = uri
            else:
                file_url = ""
            results.append(file_url)
    return GetURLResponse(urls=results)
