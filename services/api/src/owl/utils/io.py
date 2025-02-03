import asyncio
import contextlib
import os
import pathlib
import zipfile
from io import BytesIO
from os import listdir, walk
from os.path import abspath, dirname, getsize, isdir, islink, join, relpath
from typing import AsyncGenerator, BinaryIO, Generator

import aioboto3
import aiofiles
import boto3
from botocore.exceptions import ClientError
from loguru import logger

from jamaibase.exceptions import BadInputError, ResourceNotFoundError
from jamaibase.utils.io import generate_audio_thumbnail, generate_image_thumbnail
from owl.configs.manager import ENV_CONFIG
from owl.utils import uuid7_str

if ENV_CONFIG.owl_file_dir.startswith("s3://"):
    S3_CLIENT = boto3.client(
        "s3",
        aws_access_key_id=ENV_CONFIG.s3_access_key_id,
        aws_secret_access_key=ENV_CONFIG.s3_secret_access_key_plain,
        endpoint_url=ENV_CONFIG.s3_endpoint,
    )
    S3_BUCKET_NAME = ENV_CONFIG.owl_file_dir.replace("s3://", "")
    LOCAL_FILE_DIR = ""
    logger.info(f"Starting with S3 File Storage: {S3_BUCKET_NAME}")
else:
    S3_CLIENT = None
    S3_BUCKET_NAME = ""
    LOCAL_FILE_DIR = ENV_CONFIG.owl_file_dir.replace("file://", "")
    logger.info(f"Starting with Local File Storage: {LOCAL_FILE_DIR}")

EMBED_WHITE_LIST = {
    "application/pdf": [".pdf"],
    "application/xml": [".xml"],
    "application/json": [".json"],
    "application/jsonl": [".jsonl"],
    "application/x-ndjson": [".jsonl"],
    "application/json-lines": [".jsonl"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "application/msword": [".doc"],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
    "application/vnd.ms-powerpoint": [".ppt"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    "application/vnd.ms-excel": [".xls"],
    "text/markdown": [".md"],
    "text/plain": [".txt"],
    "text/html": [".html"],
    "text/tab-separated-values": [".tsv"],
    "text/csv": [".csv"],
    "text/xml": [".xml"],
}
IMAGE_WHITE_LIST = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/gif": [".gif"],
    "image/webp": [".webp"],
}
AUDIO_WHITE_LIST = {
    "audio/mpeg": [".mp3"],
    "audio/vnd.wav": [".wav"],
    "audio/x-wav": [".wav"],
    "audio/x-pn-wav": [".wav"],
    "audio/wave": [".wav"],
    "audio/vnd.wave": [".wav"],
}
UPLOAD_WHITE_LIST = {**EMBED_WHITE_LIST, **IMAGE_WHITE_LIST, **AUDIO_WHITE_LIST}

EMBED_WHITE_LIST_MIME = set(EMBED_WHITE_LIST.keys())
EMBED_WHITE_LIST_EXT = set(ext for exts in EMBED_WHITE_LIST.values() for ext in exts)
IMAGE_WHITE_LIST_MIME = set(IMAGE_WHITE_LIST.keys())
IMAGE_WHITE_LIST_EXT = set(ext for exts in IMAGE_WHITE_LIST.values() for ext in exts)
AUDIO_WHITE_LIST_MIME = set(AUDIO_WHITE_LIST.keys())
AUDIO_WHITE_LIST_EXT = set(ext for exts in AUDIO_WHITE_LIST.values() for ext in exts)
UPLOAD_WHITE_LIST_MIME = set(UPLOAD_WHITE_LIST.keys())
UPLOAD_WHITE_LIST_EXT = set(ext for exts in UPLOAD_WHITE_LIST.values() for ext in exts)


def get_db_usage(db_dir: str) -> float:
    """Returns the DB storage used in bytes (B)."""
    db_usage = 0.0
    for root, dirs, filenames in walk(abspath(db_dir), topdown=True):
        # Don't visit Lance version directories
        if root.endswith(".lance") and "_versions" in dirs:
            dirs.remove("_versions")
        for f in filenames:
            fp = join(root, f)
            if islink(fp):
                continue
            db_usage += getsize(fp)
    return db_usage


def get_storage_usage(db_dir: str) -> dict[str, float]:
    """Returns the DB storage used by each organisation in GiB."""
    db_usage = {}
    for org_id in listdir(db_dir):
        org_dir = join(db_dir, org_id)
        if not (isdir(org_dir) and org_id.startswith("org_")):
            continue
        db_usage[org_id] = get_db_usage(org_dir)
    db_usage = {k: v / (1024**3) for k, v in db_usage.items()}
    return db_usage


def get_file_usage(db_dir: str) -> dict[str, float]:
    """Returns the File storage used by each organisation in GiB."""
    file_usage = {}
    if S3_CLIENT:
        paginator = S3_CLIENT.get_paginator("list_objects_v2")
        for org_id in listdir(db_dir):
            org_dir = join(db_dir, org_id)
            if not (isdir(org_dir) and org_id.startswith("org_")):
                continue

            total_size = 0
            for prefix in [f"raw/{org_id}/", f"thumb/{org_id}/"]:
                for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        total_size += obj["Size"]

            file_usage[org_id] = total_size / (1024**3)  # Convert to GiB
    else:
        for org_id in listdir(db_dir):
            org_dir = join(db_dir, org_id)
            print(org_id)
            if not (isdir(org_dir) and org_id.startswith(("org_", "default"))):
                continue
            total_size = 0
            for subdir in ["raw", "thumb"]:
                file_dir = join(LOCAL_FILE_DIR, subdir, org_id)
                print(LOCAL_FILE_DIR)
                if os.path.exists(file_dir):
                    for root, _, files in os.walk(file_dir):
                        for file in files:
                            file_path = join(root, file)
                            total_size += os.path.getsize(file_path)

            file_usage[org_id] = total_size / (1024**3)  # Convert to GiB

    return file_usage


def zip_directory_content(root_dir: str, output_filepath: str) -> None:
    root_dir = abspath(root_dir)
    output_filepath = abspath(output_filepath)
    if dirname(output_filepath) == root_dir:
        raise ValueError("Output directory cannot be the zipped directory.")
    with zipfile.ZipFile(output_filepath, "w", zipfile.ZIP_DEFLATED) as f:
        for dir_name, _, filenames in walk(root_dir):
            for filename in filenames:
                filepath = join(dir_name, filename)
                # Create a relative path for the file in the zip archive
                arcname = relpath(filepath, root_dir)
                f.write(filepath, arcname)


@contextlib.asynccontextmanager
async def get_s3_aclient():
    async with aioboto3.Session().client(
        "s3",
        aws_access_key_id=ENV_CONFIG.s3_access_key_id,
        aws_secret_access_key=ENV_CONFIG.s3_secret_access_key_plain,
        endpoint_url=ENV_CONFIG.s3_endpoint,
    ) as aclient:
        yield aclient


# Synchronous version
@contextlib.contextmanager
def open_uri_sync(uri: str) -> Generator[BinaryIO | BytesIO, None, None]:
    if S3_CLIENT:
        if uri.startswith("s3://"):
            try:
                bucket_name, key = uri[5:].split("/", 1)
                response = S3_CLIENT.get_object(Bucket=bucket_name, Key=key)
                yield response["Body"]
            except ClientError as e:
                logger.warning(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
            except Exception as e:
                logger.exception(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
        else:
            raise ResourceNotFoundError(f'File "{uri}" is not found.')
    else:
        if uri.startswith("file://"):
            try:
                local_path = os.path.abspath(uri[7:])
                with open(local_path, "rb") as file:
                    yield file
            except FileNotFoundError as e:
                logger.warning(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
            except Exception as e:
                logger.exception(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
        else:
            raise ResourceNotFoundError(f'File "{uri}" is not found.')


# Asynchronous version
@contextlib.asynccontextmanager
async def open_uri_async(uri: str) -> AsyncGenerator[BinaryIO | BytesIO, None]:
    if S3_CLIENT:
        if uri.startswith("s3://"):
            try:
                bucket_name, key = uri[5:].split("/", 1)
                async with get_s3_aclient() as aclient:
                    response = await aclient.get_object(Bucket=bucket_name, Key=key)
                    yield response["Body"]
            except ClientError as e:
                logger.warning(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
            except Exception as e:
                logger.exception(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
        else:
            raise ResourceNotFoundError(f'File "{uri}" is not found.')
    else:
        if uri.startswith("file://"):
            try:
                local_path = os.path.abspath(uri[7:])
                async with aiofiles.open(local_path, "rb") as file:
                    yield file
            except FileNotFoundError as e:
                logger.warning(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
            except Exception as e:
                logger.exception(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
        else:
            raise ResourceNotFoundError(f'File "{uri}" is not found.')


def os_path_to_s3_key(path: pathlib.Path | str) -> str:
    # Convert path to string if it's a PathLike object
    path_str = str(path)
    # Replace backslashes with forward slashes
    s3_key = path_str.replace(os.path.sep, "/")
    # Remove leading slash if present
    return s3_key.lstrip("/")


async def upload_file_to_s3(
    organization_id: str,
    project_id: str,
    content: bytes,
    content_type: str,
    filename: str,
) -> str:
    if content_type not in UPLOAD_WHITE_LIST_MIME:
        raise BadInputError(
            f"Unsupported file MIME type: {content_type}. Allowed types are: {', '.join(UPLOAD_WHITE_LIST_MIME)}"
        )
    file_extension = os.path.splitext(filename)[1].lower()
    if file_extension not in UPLOAD_WHITE_LIST_EXT:
        raise BadInputError(
            f"Unsupported file extension: {file_extension}. Allowed types are: {', '.join(UPLOAD_WHITE_LIST_EXT)}"
        )
    else:
        if (
            file_extension in EMBED_WHITE_LIST_EXT
            and len(content) > ENV_CONFIG.owl_embed_file_upload_max_bytes
        ):
            raise BadInputError(
                f"File size exceeds {ENV_CONFIG.owl_embed_file_upload_max_bytes / 1024**2} MB limit: {len(content) / 1024**2} MB"
            )
        elif (
            file_extension in AUDIO_WHITE_LIST_EXT
            and len(content) > ENV_CONFIG.owl_audio_file_upload_max_bytes
        ):
            raise BadInputError(
                f"File size exceeds {ENV_CONFIG.owl_audio_file_upload_max_bytes / 1024**2} MB limit: {len(content) / 1024**2} MB"
            )
        elif (
            file_extension in IMAGE_WHITE_LIST_EXT
            and len(content) > ENV_CONFIG.owl_image_file_upload_max_bytes
        ):
            raise BadInputError(
                f"File size exceeds {ENV_CONFIG.owl_image_file_upload_max_bytes / 1024**2} MB limit: {len(content) / 1024**2} MB"
            )

    uuid = uuid7_str()
    raw_path = os.path.join("raw", organization_id, project_id, uuid, filename)
    raw_key = os_path_to_s3_key(raw_path)
    thumb_ext = "mp3" if file_extension in AUDIO_WHITE_LIST_EXT else "webp"
    thumb_filename = f"{os.path.splitext(filename)[0]}.{thumb_ext}"
    thumb_path = os.path.join("thumb", organization_id, project_id, uuid, thumb_filename)
    thumb_key = os_path_to_s3_key(thumb_path)
    if file_extension in AUDIO_WHITE_LIST_EXT:
        thumbnail_task = asyncio.create_task(asyncio.to_thread(generate_audio_thumbnail, content))
    else:
        thumbnail_task = asyncio.create_task(asyncio.to_thread(generate_image_thumbnail, content))
    thumbnail = await thumbnail_task

    if S3_CLIENT:
        async with get_s3_aclient() as aclient:
            # Upload raw file
            await aclient.put_object(
                Body=content,
                Bucket=S3_BUCKET_NAME,
                Key=raw_key,
                ContentType=content_type,
            )
            if len(thumbnail) > 0:
                await aclient.put_object(
                    Body=thumbnail,
                    Bucket=S3_BUCKET_NAME,
                    Key=thumb_key,
                    ContentType=f"{content_type.split('/')[0]}/{"mpeg" if thumb_ext == "mp3" else thumb_ext}",
                )
        logger.info(
            f"File Uploaded: [{organization_id}/{project_id}] "
            f"Location: s3://{S3_BUCKET_NAME}/{raw_key} "
            f"File name: {filename}, MIME type: {content_type}. "
        )
        return f"s3://{S3_BUCKET_NAME}/{raw_key}"
    else:
        raw_file_path = os.path.join(LOCAL_FILE_DIR, raw_path)
        thumb_file_path = os.path.join(LOCAL_FILE_DIR, thumb_path)

        os.makedirs(os.path.dirname(raw_file_path))
        os.makedirs(os.path.dirname(thumb_file_path))

        async with aiofiles.open(raw_file_path, "wb") as out_file:
            await out_file.write(content)

        if len(thumbnail) > 0:
            async with aiofiles.open(thumb_file_path, "wb") as thumb_file:
                await thumb_file.write(thumbnail)

        logger.info(
            f"File Uploaded: [{organization_id}/{project_id}] "
            f"Location: file://{raw_file_path} "
            f"File name: {filename}, MIME type: {content_type}. "
        )
        return f"file://{raw_file_path}"
