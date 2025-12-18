import ipaddress
import os
import socket
from contextlib import asynccontextmanager
from hashlib import blake2b
from io import BytesIO
from os.path import join, splitext
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urlparse, urlunparse

import aioboto3
import httpx
from botocore.exceptions import ClientError
from loguru import logger
from PIL import Image, ImageDraw, ImageFont
from sqlmodel import select

from jamaibase.utils.io import (  # noqa: F401
    AUDIO_WHITE_LIST,
    DOC_WHITE_LIST,
    EMBED_WHITE_LIST,
    IMAGE_WHITE_LIST,
    csv_to_df,
    df_to_csv,
    dump_json,
    dump_pickle,
    dump_toml,
    dump_yaml,
    guess_mime,
    json_dumps,
    json_loads,
    load_pickle,
    read_image,
    read_json,
    read_toml,
    read_yaml,
)
from owl.configs import ENV_CONFIG
from owl.types import (
    ALLOWED_FILE_EXTENSIONS,
    AUDIO_FILE_EXTENSIONS,
    DOCUMENT_FILE_EXTENSIONS,
    IMAGE_FILE_EXTENSIONS,
    DBStorageUsage,
    TableType,
)
from owl.utils import uuid7_str
from owl.utils.exceptions import BadInputError, ResourceNotFoundError

S3_BUCKET_NAME = ENV_CONFIG.file_dir.replace("s3://", "")
ASSET_DIRPATH = Path(__file__).resolve().parent.parent / "assets"
ICON_DIRPATH = ASSET_DIRPATH / "icons"
if ICON_DIRPATH.is_dir() and (ICON_DIRPATH / "csv.webp").is_file():
    logger.info(f'Documents icons will be loaded from "{ICON_DIRPATH}".')
else:
    ICON_DIRPATH = None
    logger.warning(
        f'Documents icons not found in "{ICON_DIRPATH}". Falling back to generating text-based thumbnails.'
    )
GiB = 1024**3

UPLOAD_WHITE_LIST = {**EMBED_WHITE_LIST, **IMAGE_WHITE_LIST, **AUDIO_WHITE_LIST}

EMBED_WHITE_LIST_MIME = set(EMBED_WHITE_LIST.keys())
EMBED_WHITE_LIST_EXT = set(ext for exts in EMBED_WHITE_LIST.values() for ext in exts)
DOC_WHITE_LIST_MIME = set(DOC_WHITE_LIST.keys())
DOC_WHITE_LIST_EXT = set(ext for exts in DOC_WHITE_LIST.values() for ext in exts)
NON_PDF_DOC_WHITE_LIST_EXT = set(
    ext for exts in DOC_WHITE_LIST.values() for ext in exts if ext != ".pdf"
)
IMAGE_WHITE_LIST_MIME = set(IMAGE_WHITE_LIST.keys())
IMAGE_WHITE_LIST_EXT = set(ext for exts in IMAGE_WHITE_LIST.values() for ext in exts)
AUDIO_WHITE_LIST_MIME = set(AUDIO_WHITE_LIST.keys())
AUDIO_WHITE_LIST_EXT = set(ext for exts in AUDIO_WHITE_LIST.values() for ext in exts)
UPLOAD_WHITE_LIST_MIME = set(UPLOAD_WHITE_LIST.keys())
UPLOAD_WHITE_LIST_EXT = set(ext for exts in UPLOAD_WHITE_LIST.values() for ext in exts)

HTTP_ACLIENT = httpx.AsyncClient(
    timeout=10.0,
    transport=httpx.AsyncHTTPTransport(retries=3),
    follow_redirects=False,  # Prevent redirect-based SSRF
    max_redirects=0,
)


@asynccontextmanager
async def get_s3_aclient():
    async with aioboto3.Session().client(
        "s3",
        aws_access_key_id=ENV_CONFIG.s3_access_key_id,
        aws_secret_access_key=ENV_CONFIG.s3_secret_access_key_plain,
        endpoint_url=ENV_CONFIG.s3_endpoint,
    ) as aclient:
        yield aclient


class AsyncResponse:
    """A simple wrapper for `open_uri_async` result."""

    def __init__(self, content: bytes):
        self.content = content

    async def read(self, *_, **__) -> bytes:
        return self.content


def _is_private_or_local_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # treat invalid as unsafe
    return addr.is_private or addr.is_loopback or addr.is_link_local


def validate_url(url: str, *, error_cls: type[Exception] = BadInputError) -> str:
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise error_cls(f'URL "{url}" is invalid: {e}') from e
    if parsed.scheme == "s3":
        # We only allow certain file extensions for S3 URLs
        extension = splitext(url)[1].lower()
        if extension not in ALLOWED_FILE_EXTENSIONS:
            raise error_cls(
                (
                    "Unsupported file type. Supported formats are:\n"
                    f"- Images: {IMAGE_FILE_EXTENSIONS}\n"
                    f"- Audio: {AUDIO_FILE_EXTENSIONS}\n"
                    f"- Documents: {DOCUMENT_FILE_EXTENSIONS}"
                )
            )
        return url
    if parsed.scheme != "https":
        raise error_cls(f'URL "{url}" is invalid: Scheme is not "https"')
    if not parsed.hostname:
        raise error_cls(f'URL "{url}" is invalid: Missing hostname')
    try:
        ips = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, None)}
    except socket.gaierror as e:
        raise error_cls(f'URL "{url}" is invalid: {e}') from e
    if not ips:
        raise error_cls(f'URL "{url}" is invalid: Failed to resolve hostname')
    if any(_is_private_or_local_ip(ip) for ip in ips):
        raise error_cls(f'URL "{url}" is invalid: Hostname resolves to private or local IP')
    return url


# Asynchronous version
@asynccontextmanager
async def open_uri_async(uri: str) -> AsyncGenerator[tuple[AsyncResponse, str], None]:
    if not isinstance(uri, str):
        raise BadInputError(f"URI must be a string, got {type(uri)} instead.")
    if uri.startswith("s3://"):
        try:
            bucket_name, key = uri[5:].split("/", 1)
            async with get_s3_aclient() as aclient:
                response = await aclient.get_object(Bucket=bucket_name, Key=key)
                yield response["Body"], str(response["ContentType"])
        except ClientError as e:
            if "NoSuchKey" in str(e):
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
            logger.warning(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
            raise BadInputError(f'File "{uri}" cannot be opened.') from e
        except Exception as e:
            logger.exception(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
            raise BadInputError(f'File "{uri}" cannot be opened.') from e
    elif uri.startswith("https://"):
        try:
            uri = validate_url(uri)
            response = await HTTP_ACLIENT.get(uri)
            response.raise_for_status()
            mime = response.headers.get("Content-Type", "application/octet-stream")
            yield (AsyncResponse(response.content), mime)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ResourceNotFoundError(f'File "{uri}" is not found.') from e
            logger.warning(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
            raise BadInputError(f'File "{uri}" cannot be opened.') from e
        except BadInputError as e:
            logger.warning(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
            raise BadInputError(f'File "{uri}" cannot be opened.') from e
        except Exception as e:
            logger.exception(f'Failed to open "{uri}" due to {e.__class__.__name__}: {e}')
            raise BadInputError(f'File "{uri}" cannot be opened.') from e
    else:
        raise BadInputError(f'File "{uri}" cannot be opened.')


def get_bytes_size_mb(bytes_content: bytes, decimal_places: int = 3) -> float:
    """
    Convert bytes to Mebibyte (MiB).

    Args:
        bytes_content (bytes): The content in bytes to be calculated.
        decimal_places (int, optional): Number of decimal places to round to. Defaults to 3.

    Returns:
        float: The converted value in Mebibyte (MiB)
    """
    mb_value = len(bytes_content) / (1024 * 1024)  # 1 MB = 1024 KB = 1024 * 1024 bytes
    return round(mb_value, decimal_places)


def _image_to_webp_bytes(image: Image.Image) -> bytes:
    """
    Converts an image to bytes.

    Args:
        image (Image.Image): The image.

    Returns:
        bytes: The image as bytes (WebP format).
    """
    with BytesIO() as f:
        image.save(
            f,
            format="webp",
            lossless=False,
            quality=60,
            alpha_quality=50,
            method=6,
            exact=False,
        )
        return f.getvalue()


def generate_image_thumbnail(
    file_content: bytes,
    size: tuple[float, float] = (450.0, 450.0),
) -> bytes | None:
    """
    Generates an image thumbnail.

    Args:
        file_content (bytes): The image file content.
        size (tuple[float, float]): The desired size of the thumbnail (width, height).
            Defaults to (450.0, 450.0).

    Returns:
        thumbnail (bytes | None): The thumbnail image as bytes, or None if generation fails.
    """
    try:
        with Image.open(BytesIO(file_content)) as img:
            # Check image mode
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            # Resize and save
            img.thumbnail(size=size)
            return _image_to_webp_bytes(img)
    except Exception as e:
        logger.exception(f"Failed to generate image thumbnail due to {e.__class__.__name__}: {e}")
        return None


def generate_audio_thumbnail(
    file_content: bytes,
    duration_ms: int = 30000,
) -> bytes | None:
    """
    Generates an audio thumbnail by extracting a segment from the original audio.

    Args:
        file_content (bytes): The audio file content.
        duration_ms (int): Duration of the thumbnail in milliseconds.
            Defaults to 30000 (30 seconds).

    Returns:
        thumbnail (bytes | None): The thumbnail audio as bytes, or None if generation fails.
    """
    from pydub import AudioSegment

    try:
        # Extract the first `duration_ms` milliseconds
        audio = AudioSegment.from_file(BytesIO(file_content))
        thumbnail = audio[:duration_ms]
        # Export the thumbnail to a bytes object
        with BytesIO() as output:
            thumbnail.export(output, format="mp3")
            return output.getvalue()
    except Exception as e:
        logger.exception(f"Failed to generate audio thumbnail due to {e.__class__.__name__}: {e}")
        return None


def generate_pdf_thumbnail(
    file_content: bytes,
    size: tuple[int, int] = (950, 950),
) -> bytes | None:
    """
    Generates a PDF thumbnail image.

    Args:
        file_content (bytes): The PDF file content.
        size (tuple[int, int]): The desired size of the thumbnail (width, height).
            Defaults to (950, 950).

    Returns:
        thumbnail (bytes | None): The thumbnail image as bytes, or None if generation fails.
    """
    from pdf2image import convert_from_bytes

    try:
        images = convert_from_bytes(
            file_content,
            dpi=200,
            first_page=1,
            last_page=1,  # process only the first page
        )
        if not images:
            return b""
        img = images[0]
        img.thumbnail(size=size)
        thumbnail_bytes = _image_to_webp_bytes(img)
        for image in images:
            image.close()  # release resources
        return thumbnail_bytes

    except Exception as e:
        logger.exception(f"Failed to generate PDF thumbnail: {e.__class__.__name__}: {e}")
        return None


def _generate_text_thumbnail(file_extension: str, size: tuple[int, int]) -> bytes:
    """Generates a text-based thumbnail (as a fallback)."""
    try:
        img = Image.new("RGB", size, color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        text = file_extension
        font_size = min(size) // 2
        while font_size > 1:
            try:
                font_ttf = ASSET_DIRPATH / "Roboto-Regular.ttf"
                font = ImageFont.truetype(font_ttf, font_size)
            except OSError:
                logger.warning("Roboto font not found. Using default fallback font.")
                font = ImageFont.load_default()
                break

            text_bbox = draw.textbbox((0, 0), text, font=font)
            if (
                text_bbox[2] - text_bbox[0] < size[0] * 0.9
                and text_bbox[3] - text_bbox[1] < size[1] * 0.9
            ):
                break
            font_size -= 1

        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = (size[0] - text_width) // 2
        text_y = (size[1] - text_height) // 2

        draw.text((text_x, text_y), text, fill=(0, 0, 0), font=font)

        return _image_to_webp_bytes(img)

    except Exception as e:
        logger.exception(f"Failed to generate text thumbnail: {e.__class__.__name__}: {e}")
        return b""


def generate_extension_name_thumbnail(
    file_extension: str,
    size: tuple[int, int] = (512, 512),
) -> bytes:
    """
    Loads a pre-generated thumbnail based on the file extension.
    If no icon is found, falls back to generating a text-based thumbnail.
    """
    if ICON_DIRPATH:
        icon_path = ICON_DIRPATH / f"{file_extension[1:]}.webp"
        try:
            with open(icon_path, "rb") as f:
                img = Image.open(f)
                if img.size != size:
                    img.thumbnail(size)
                return _image_to_webp_bytes(img)
        except Exception as e:
            logger.exception(f"Error loading pre-generated icon: {repr(e)}")
    # Fallback: Generate a text-based thumbnail if the icon is not found or there's an error.
    return _generate_text_thumbnail(file_extension, size)


def _os_path_to_s3_key(path: Path | str) -> str:
    # Convert path to string if it's a PathLike object
    path_str = str(path)
    # Replace backslashes with forward slashes
    s3_key = path_str.replace(os.path.sep, "/")
    # Remove leading slash if present
    return s3_key.lstrip("/")


async def s3_upload(
    organization_id: str,
    project_id: str,
    content: bytes,
    *,
    content_type: str,
    filename: str,
    generate_thumbnail: bool = True,
    key: str = "",
) -> str:
    if content_type not in UPLOAD_WHITE_LIST_MIME:
        raise BadInputError(
            f'Unsupported MIME type "{content_type}" for file "{filename}". Allowed types are: {", ".join(UPLOAD_WHITE_LIST_MIME)}'
        )
    file_extension = splitext(filename)[1].lower()
    if file_extension not in UPLOAD_WHITE_LIST_EXT:
        raise BadInputError(
            f'Unsupported extension "{file_extension}" for file "{filename}". Allowed types are: {", ".join(UPLOAD_WHITE_LIST_EXT)}'
        )
    else:
        if (
            file_extension in EMBED_WHITE_LIST_EXT
            and len(content) > ENV_CONFIG.embed_file_upload_max_bytes
        ):
            raise BadInputError(
                f"File size exceeds {ENV_CONFIG.embed_file_upload_max_bytes / 1024**2} MB limit: {len(content) / 1024**2} MB"
            )
        elif (
            file_extension in AUDIO_WHITE_LIST_EXT
            and len(content) > ENV_CONFIG.audio_file_upload_max_bytes
        ):
            raise BadInputError(
                f"File size exceeds {ENV_CONFIG.audio_file_upload_max_bytes / 1024**2} MB limit: {len(content) / 1024**2} MB"
            )
        elif (
            file_extension in IMAGE_WHITE_LIST_EXT
            and len(content) > ENV_CONFIG.image_file_upload_max_bytes
        ):
            raise BadInputError(
                f"File size exceeds {ENV_CONFIG.image_file_upload_max_bytes / 1024**2} MB limit: {len(content) / 1024**2} MB"
            )
    # Process key
    if key:
        key = key.removeprefix(f"s3://{S3_BUCKET_NAME}/").lstrip("/")
        if not key.startswith("raw/"):
            raise BadInputError(
                f'Invalid S3 key "{key}". Must start with one of ["raw/", "s3://<bucket>/raw/"].'
            )
    else:
        key = join("raw", organization_id, project_id, uuid7_str(), filename)
    raw_key = _os_path_to_s3_key(key)
    thumb_ext = "mp3" if file_extension in AUDIO_WHITE_LIST_EXT else "webp"
    thumb_key = f"{splitext(raw_key.replace('raw/', 'thumb/', 1))[0]}.{thumb_ext}"
    if generate_thumbnail:
        if file_extension == ".pdf":
            thumbnail = generate_pdf_thumbnail(content)
        elif file_extension in NON_PDF_DOC_WHITE_LIST_EXT:
            thumbnail = await generate_document_thumbnail(file_extension)
        elif file_extension in AUDIO_WHITE_LIST_EXT:
            thumbnail = generate_audio_thumbnail(content)
        else:
            thumbnail = generate_image_thumbnail(content)
    else:
        thumbnail = None

    async with get_s3_aclient() as aclient:
        # Upload raw file
        await aclient.put_object(
            Body=content,
            Bucket=S3_BUCKET_NAME,
            Key=raw_key,
            ContentType=content_type,
        )
        if thumbnail is not None:
            await aclient.put_object(
                Body=thumbnail,
                Bucket=S3_BUCKET_NAME,
                Key=thumb_key,
                ContentType=f"{content_type.split('/')[0]}/{'mpeg' if thumb_ext == 'mp3' else thumb_ext}",
            )
    logger.info(
        f"File uploaded: [{organization_id}/{project_id}] "
        f"Location: s3://{S3_BUCKET_NAME}/{raw_key} "
        f"File name: {filename}, MIME type: {content_type}. "
    )
    return f"s3://{S3_BUCKET_NAME}/{raw_key}"


# async def s3_cache_file(
#     content: bytes,
#     content_type: str,
# ) -> str:
#     content_len = len(content)
#     content_hash = blake2b(content).hexdigest()
#     s3_key = f"temp/{content_hash}-{content_len}"
#     uri = f"s3://{S3_BUCKET_NAME}/{s3_key}"
#     # Upload file
#     async with get_s3_aclient() as aclient:
#         # If file already exists, skip
#         try:
#             await aclient.head_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
#             return uri
#         except Exception:
#             pass
#         # Upload
#         await aclient.put_object(
#             Body=content,
#             Bucket=S3_BUCKET_NAME,
#             Key=s3_key,
#             ContentType=content_type,
#         )
#     logger.info(f"S3 file created: {uri}")
#     return uri


# async def s3_delete(
#     *,
#     organization_id: str = "",
#     project_id: str = "",
#     filename: str = "",
#     key: str = "",
#     delete_thumbnail: bool = True,
# ) -> str:
#     # Process key
#     if key:
#         key = key.removeprefix(f"s3://{S3_BUCKET_NAME}/").lstrip("/")
#         if not key.startswith(("raw/", "temp/")):
#             raise BadInputError(
#                 (
#                     f'Invalid S3 key "{key}". Must start with one of '
#                     '["raw/", "temp/", "s3://<bucket>/raw/", "s3://<bucket>/temp/"].'
#                 )
#             )
#     else:
#         key = join("raw", organization_id, project_id, uuid7_str(), filename)
#     raw_key = _os_path_to_s3_key(key)
#     file_extension = splitext(filename)[1].lower()
#     thumb_ext = "mp3" if file_extension in AUDIO_WHITE_LIST_EXT else "webp"
#     thumb_key = f"{splitext(raw_key.replace('raw/', 'thumb/', 1))[0]}.{thumb_ext}"

#     async with get_s3_aclient() as aclient:
#         # Delete raw file
#         await aclient.delete_object(Bucket=S3_BUCKET_NAME, Key=raw_key)
#         # Delete thumbnail
#         if delete_thumbnail:
#             try:
#                 await aclient.delete_object(Bucket=S3_BUCKET_NAME, Key=thumb_key)
#             except Exception as e:
#                 logger.warning(f'Failed to delete thumbnail "{thumb_key}": {repr(e)}')
#     logger.info(f"File deleted: s3://{S3_BUCKET_NAME}/{raw_key}")
#     return raw_key


@asynccontextmanager
async def s3_temporary_file(
    content: bytes,
    content_type: str,
) -> AsyncGenerator[str, None]:
    from owl.configs import CACHE

    content_len = len(content)
    content_hash = blake2b(content).hexdigest()
    cache_key = f"temp:{content_hash}-{content_len}"
    s3_key = cache_key.replace(":", "/")
    # This lock is so that we don't upload the same file twice
    async with CACHE.alock(f"{cache_key}:lock", blocking=True, expire=180) as lock_acquired:
        if not lock_acquired:
            raise BadInputError("Another upload of this file is in progress.")
        # Upload file
        async with get_s3_aclient() as aclient:
            await aclient.put_object(
                Body=content,
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                ContentType=content_type,
            )
        uri = f"s3://{S3_BUCKET_NAME}/{s3_key}"
        logger.info(f"Temporary S3 file created: {uri}")
        try:
            yield uri
        finally:
            # Delete file
            try:
                async with get_s3_aclient() as aclient:
                    await aclient.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
                logger.info(f"Temporary S3 file deleted: {uri}")
            except Exception as e:
                logger.warning(f'Failed to delete temporary S3 file "{uri}": {repr(e)}')


async def generate_presigned_s3_url(s3_client, bucket_name: str, key: str) -> str:
    try:
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
    except Exception as e:
        err_mssg = str(e)
        if "NoSuchBucket" in err_mssg:
            pass
        else:
            logger.exception(
                (
                    "Error generating pre-signed URL for "
                    f"(bucket='{bucket_name}' prefix='{key}') due to {e.__class__.__name__}: {e}"
                )
            )
        return ""


def get_global_thumbnail_path(extension: str) -> str:
    """Returns the path for a global thumbnail based on file extension."""
    return join("thumb", "global", f"{extension[1:]}.webp")


async def get_global_thumbnail(extension: str) -> bytes | None:
    """Retrieves a global thumbnail if it exists."""

    try:
        thumbnail_path = get_global_thumbnail_path(extension)
        async with get_s3_aclient() as aclient:
            try:
                response = await aclient.get_object(Bucket=S3_BUCKET_NAME, Key=thumbnail_path)
                return await response["Body"].read()
            except ClientError:
                return None
    except Exception as e:
        logger.warning(f"Failed to get global thumbnail: {e}")
        return None


async def save_global_thumbnail(extension: str, thumbnail: bytes) -> None:
    """Saves a global thumbnail for future use."""

    try:
        thumbnail_path = get_global_thumbnail_path(extension)
        async with get_s3_aclient() as aclient:
            await aclient.put_object(
                Body=thumbnail,
                Bucket=S3_BUCKET_NAME,
                Key=thumbnail_path,
                ContentType="image/webp",
            )
    except Exception as e:
        logger.warning(f"Failed to save global thumbnail: {e}")


async def generate_document_thumbnail(
    file_extension: str,
    size: tuple[int, int] = (512, 512),
) -> None:
    """
    Generates a thumbnail based on the given file extension with global cache.
    > if doc and non-pdf, generate global thumbnail, no local thumbnail
    > when get thumbnail url, check raw url for extension, get global thumbnail url

    Args:
        file_extension (str): The file extension (e.g., ".xlsx").
        size (tuple[int, int]): The desired size (width, height) of the thumbnail.
    """
    file_extension = file_extension.lower()
    if file_extension not in NON_PDF_DOC_WHITE_LIST_EXT:
        raise ValueError(f"Unsupported file extension: {file_extension}")
    try:
        # Check global cache first
        if (await get_global_thumbnail(file_extension)) is not None:
            return
        # Generate and cache new thumbnail
        thumbnail_path = get_global_thumbnail_path(file_extension)
        async with get_s3_aclient() as aclient:
            await aclient.put_object(
                Body=generate_extension_name_thumbnail(file_extension, size),
                Bucket=S3_BUCKET_NAME,
                Key=thumbnail_path,
                ContentType="image/webp",
            )
        return
    except Exception as e:
        logger.exception(f"Failed to generate file thumbnail due to {e.__class__.__name__}: {e}")


async def get_file_storage_usage(org_id: str) -> float | None:
    """
    Calculates the total file storage used by an organization in the S3 bucket.

    This function iterates through the S3 objects under the standard 'raw/{org_id}/'
    and 'thumb/{org_id}/' prefixes, summing their sizes. It includes error
    handling to prevent task failure if S3 is unavailable.

    Args:
        org_id (str): The ID of the organization to measure.

    Returns:
        usage_gib (float | None): The total storage used in GiB. Returns None on error.
    """
    try:
        async with get_s3_aclient() as aclient:
            paginator = aclient.get_paginator("list_objects_v2")
            total_size = 0
            for prefix in [f"raw/{org_id}/", f"thumb/{org_id}/"]:
                prefix_size = 0
                async for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        prefix_size += obj["Size"]
                total_size += prefix_size
            return total_size / GiB
    except Exception as e:
        logger.exception(
            f'Failed to compute file storage usage for organization "{org_id}": {repr(e)}'
        )
        return None


async def get_schema_storage_usage_postgres(schema_name: str) -> DBStorageUsage:
    """
    Calculates detailed storage usage for a given schema in PostgreSQL.

    This function queries PostgreSQL system tables to get the total size of all
    tables and their associated indexes within a specific schema.

    Args:
        session: The SQLAlchemy session to use for the query.
        schema_name: The name of the database schema to measure.

    Returns:
        The total size in GiB.
    """
    from owl.db import async_session, cached_text

    usage = DBStorageUsage(
        schema_name=schema_name,
        table_names=[],
        table_sizes=[],
    )
    try:
        query = cached_text(
            """
            SELECT
                nspname AS schema_name,
                array_agg(c.relname) AS names,
                array_agg(pg_total_relation_size(c.oid)::bigint) AS total_relation_sizes,
                array_agg(pg_total_relation_size(c.reltoastrelid)::bigint) AS total_toast_sizes
            FROM
                pg_class c
            LEFT JOIN
                pg_namespace n ON (n.oid = c.relnamespace)
            WHERE
                n.nspname = :schema_name
                AND c.relkind IN ('r', 'm') -- r = table, m = materialized view
            GROUP BY nspname;
        """
        )
        async with async_session() as session:
            stats = (await session.exec(query, params={"schema_name": schema_name})).one_or_none()
        if not stats:
            return usage
        return DBStorageUsage(
            schema_name=stats.schema_name,
            table_names=stats.names,
            table_sizes=[
                float(rs or 0.0) + float(ts or 0.0)
                for rs, ts in zip(stats.total_relation_sizes, stats.total_toast_sizes, strict=True)
            ],
        )
    except Exception as e:
        logger.exception(
            f'Failed to compute DB storage usage for schema "{schema_name}": {repr(e)}'
        )
        return usage


async def get_db_storage_usage(org_id: str) -> float | None:
    """
    Calculates the total DB storage used by an organization.

    Args:
        org_id (str): The ID of the organization to measure.

    Returns:
        usage_gib (float | None): The total storage used in GiB. Returns None on error.
    """
    from owl.db import async_session
    from owl.db.models import Project

    try:
        db_usage = 0.0
        async with async_session() as session:
            projects_in_org = (
                await session.exec(select(Project.id).where(Project.organization_id == org_id))
            ).all()
        for project_id in projects_in_org:
            for table_type in TableType:
                schema_name = f"{project_id}_{table_type}"
                usage = await get_schema_storage_usage_postgres(schema_name)
                db_usage += usage.total_size
        return db_usage / GiB
    except Exception as e:
        logger.exception(
            f'Failed to compute DB storage usage for organization "{org_id}": {repr(e)}'
        )
        return None
