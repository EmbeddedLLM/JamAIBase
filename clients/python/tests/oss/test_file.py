import os
import re
import tempfile
from io import BytesIO
from typing import Type
from urllib.parse import urlparse

import httpx
import numpy as np
import pytest
from PIL import Image

from jamaibase import JamAI, JamAIAsync
from jamaibase.protocol import (
    FileUploadResponse,
    GetURLResponse,
)
from jamaibase.utils import run
from jamaibase.utils.io import generate_thumbnail


def read_file_content(file_path):
    with open(file_path, "rb") as f:
        return f.read()


# Define the paths to your test image files
IMAGE_FILES = [
    "clients/python/tests/files/jpeg/cifar10-deer.jpg",
    "clients/python/tests/files/png/rabbit.png",
    "clients/python/tests/files/gif/rabbit_cifar10-deer.gif",
    "clients/python/tests/files/webp/rabbit_cifar10-deer.webp",
]

CLIENT_CLS = [JamAI, JamAIAsync]


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
@pytest.mark.parametrize("image_file", IMAGE_FILES)
async def test_upload(client_cls: Type[JamAI | JamAIAsync], image_file: str):
    # Initialize the client
    jamai = client_cls()

    # Ensure the image file exists
    assert os.path.exists(image_file), f"Test image file does not exist: {image_file}"
    # Upload the file
    upload_response = await run(jamai.file.upload_file, image_file)
    assert isinstance(upload_response, FileUploadResponse)
    assert upload_response.uri.startswith(
        ("file://", "s3://")
    ), f"Returned URI '{upload_response.uri}' does not start with 'file://' or 's3://'"

    filename = os.path.basename(image_file)
    expected_uri_pattern = re.compile(
        r"(file|s3)://[^/]+/raw/default/default/[a-f0-9-]{36}/" + re.escape(filename) + "$"
    )

    # Check if the returned URI matches the expected format
    assert expected_uri_pattern.match(upload_response.uri), (
        f"Returned URI '{upload_response.uri}' does not match the expected format: "
        f"(file|s3)://file/raw/default/default/{{UUID}}/{filename}"
    )

    print(f"Returned URI matches the expected format: {upload_response.uri}")


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_upload_large_image_file(client_cls: Type[JamAI | JamAIAsync]):
    jamai = client_cls()

    # Create 25MB image file, assuming 3 bytes per pixel (RGB) and 8 bits per byte
    side_length = int(np.sqrt((25 * 1024 * 1024) / 3))
    data = np.random.randint(0, 256, (side_length, side_length, 3), dtype=np.uint8)
    img = Image.fromarray(data, "RGB")

    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, "large_image.png")
        img.save(file_path, format="PNG")

        pattern = re.compile("File size exceeds .+ limit")
        with pytest.raises(RuntimeError, match=pattern):
            await run(jamai.file.upload_file, file_path)


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_get_raw_urls(client_cls: Type[JamAI | JamAIAsync]):
    jamai = client_cls()
    # Upload files first
    uploaded_uris = []
    for file in IMAGE_FILES:
        response = await run(jamai.file.upload_file, file)
        uploaded_uris.append(response.uri)

    # Now test get_raw_urls
    response = await run(jamai.file.get_raw_urls, uploaded_uris)
    assert isinstance(response, GetURLResponse)
    assert len(response.urls) == len(IMAGE_FILES)
    for original_file, url in zip(IMAGE_FILES, response.urls, strict=True):
        if url.startswith(("http://", "https://")):
            # Handle HTTP/HTTPS URLs
            HEADERS = {"X-PROJECT-ID": "default"}
            with httpx.Client() as client:
                downloaded_content = client.get(url, headers=HEADERS).content

        # Read the original file content
        original_content = read_file_content(original_file)

        # Compare the contents
        assert (
            original_content == downloaded_content
        ), f"Content mismatch for file: {original_file}"

    # Check if the returned URIs are absolute paths
    for url in response.urls:
        parsed_uri = urlparse(url)

        if parsed_uri.scheme in ("http", "https"):
            assert parsed_uri.netloc, f"Invalid HTTP/HTTPS URL: {url}"
        elif parsed_uri.scheme == "file" or not parsed_uri.scheme:
            file_path = parsed_uri.path if parsed_uri.scheme == "file" else url
            assert os.path.isabs(file_path), f"File path is not absolute: {url}"
        else:
            raise ValueError(f"Unsupported URI or file not found: {url}")


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_get_thumbnail_urls(client_cls: Type[JamAI | JamAIAsync]):
    jamai = client_cls()

    # Upload files first
    uploaded_uris = []
    for file in IMAGE_FILES:
        response = await run(jamai.file.upload_file, file)
        uploaded_uris.append(response.uri)

    # Now test get_thumbnail_urls
    response = await run(jamai.file.get_thumbnail_urls, uploaded_uris)
    assert isinstance(response, GetURLResponse)
    assert len(response.urls) == len(IMAGE_FILES)

    # Generate thumbnails and compare
    for original_file, url in zip(IMAGE_FILES, response.urls, strict=True):
        # Read original file content
        original_content = read_file_content(original_file)

        # Generate thumbnail
        expected_thumbnail = generate_thumbnail(original_content)
        assert expected_thumbnail is not None, f"Failed to generate thumbnail for {original_file}"

        if url.startswith(("http://", "https://")):
            downloaded_thumbnail = httpx.get(url, headers={"X-PROJECT-ID": "default"}).content
        else:
            downloaded_thumbnail = read_file_content(url)

        # Compare thumbnails
        assert (
            expected_thumbnail == downloaded_thumbnail
        ), f"Thumbnail mismatch for file: {original_file}"

    # Check if the returned URIs are valid
    for url in response.urls:
        parsed_uri = urlparse(url)

        if parsed_uri.scheme in ("http", "https"):
            assert parsed_uri.netloc, f"Invalid HTTP/HTTPS URL: {url}"
        else:
            raise ValueError(f"Unsupported URI or file not found: {url}")


@pytest.mark.parametrize("client_cls", CLIENT_CLS)
async def test_thumbnail_transparency(client_cls: Type[JamAI | JamAIAsync]):
    jamai = client_cls()
    response = await run(
        jamai.file.upload_file, "clients/python/tests/files/png/github-mark-white.png"
    )
    response = await run(jamai.file.get_thumbnail_urls, [response.uri])
    assert isinstance(response, GetURLResponse)
    assert len(response.urls) == 1
    thumb_url = response.urls[0]
    if thumb_url.startswith(("http://", "https://")):
        downloaded_thumbnail = httpx.get(thumb_url, headers={"X-PROJECT-ID": "default"}).content
    else:
        downloaded_thumbnail = read_file_content(thumb_url)

    image = Image.open(BytesIO(downloaded_thumbnail))
    assert image.mode == "RGBA"
