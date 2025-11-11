from typing import Literal

from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    object: Literal["file.upload"] = Field(
        "file.upload",
        description='The object type, which is always "file.upload".',
        examples=["file.upload"],
    )
    uri: str = Field(
        description="The URI of the uploaded file.",
        examples=[
            "s3://bucket-name/raw/org_id/project_id/uuid/filename.ext",
            "file:///path/to/raw/file.ext",
        ],
    )


class GetURLRequest(BaseModel):
    uris: list[str] = Field(
        description=(
            "A list of file URIs for which pre-signed URLs or local file paths are requested. "
            "The service will return a corresponding list of pre-signed URLs or local file paths."
        ),
    )


class GetURLResponse(BaseModel):
    object: Literal["file.urls"] = Field(
        "file.urls",
        description='The object type, which is always "file.urls".',
        examples=["file.urls"],
    )
    urls: list[str] = Field(
        description="A list of pre-signed URLs or local file paths.",
        examples=[
            "https://presigned-url-for-file1.ext",
            "/path/to/file2.ext",
        ],
    )
