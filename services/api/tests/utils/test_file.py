import os
import re
import tempfile
from dataclasses import dataclass
from io import BytesIO
from os.path import basename, dirname, join, realpath
from urllib.parse import urlparse

import httpx
import numpy as np
import pytest
from PIL import Image

from jamaibase import JamAI
from jamaibase.types import (
    FileUploadResponse,
    GetURLResponse,
    OrganizationCreate,
)
from jamaibase.utils.exceptions import BadInputError
from owl.types import Role
from owl.utils.test import (
    create_organization,
    create_project,
    create_user,
    get_file_map,
    upload_file,
)

TEST_FILE_DIR = join(dirname(dirname(realpath(__file__))), "files")
FILES = get_file_map(TEST_FILE_DIR)
# Define the paths to your test image and audio files
IMAGE_FILES = [
    FILES["cifar10-deer.jpg"],
    FILES["rabbit.png"],
    FILES["rabbit_cifar10-deer.gif"],
    FILES["rabbit_cifar10-deer.webp"],
]
AUDIO_FILES = [
    FILES["gutter.wav"],
    FILES["gutter.mp3"],
]
DOC_FILES = [
    FILES["1970_PSS_ThAT_mechanism.pdf"],
    FILES["Claims Form.xlsx"],
]
ALL_FILES = IMAGE_FILES + AUDIO_FILES + DOC_FILES


@dataclass(slots=True)
class FileContext:
    superuser_id: str
    user_id: str
    org_id: str
    project_id: str


def _read_file_content(file_path):
    with open(file_path, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def setup():
    """
    Fixture to set up the necessary organization and projects for file tests.
    """
    with (
        # Create superuser
        create_user() as superuser,
        # Create user
        create_user({"email": "testuser@example.com", "name": "Test User"}) as user,
        # Create organization
        create_organization(
            body=OrganizationCreate(name="Clubhouse"), user_id=superuser.id
        ) as org,
        # Create project
        create_project(dict(name="Bucket A"), user_id=superuser.id, organization_id=org.id) as p0,
    ):
        assert superuser.id == "0"
        assert org.id == "0"
        client = JamAI(user_id=superuser.id)
        # Join organization and project
        client.organizations.join_organization(
            user_id=user.id, organization_id=org.id, role=Role.ADMIN
        )
        client.projects.join_project(user_id=user.id, project_id=p0.id, role=Role.ADMIN)

        yield FileContext(
            superuser_id=superuser.id, user_id=user.id, org_id=org.id, project_id=p0.id
        )


@pytest.mark.parametrize("image_file", IMAGE_FILES)
def test_upload_image(setup: FileContext, image_file: str):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # Ensure the image file exists
    assert os.path.exists(image_file), f"Test image file does not exist: {image_file}"
    # Upload the file
    upload_response = upload_file(client, image_file)
    assert isinstance(upload_response, FileUploadResponse)
    assert upload_response.uri.startswith(("file://", "s3://")), (
        f"Returned URI '{upload_response.uri}' does not start with 'file://' or 's3://'"
    )

    filename = os.path.basename(image_file)
    expected_uri_pattern = re.compile(
        rf"(file|s3)://[^/]+/raw/{setup.org_id}/{setup.project_id}/[a-f0-9-]{{36}}/"
        + re.escape(filename)
        + "$"
    )
    # Check if the returned URI matches the expected format
    assert expected_uri_pattern.match(upload_response.uri), (
        f"Returned URI '{upload_response.uri}' does not match the expected format: "
        f"(file|s3)://file/raw/{setup.org_id}/{setup.project_id}/{{UUID}}/{filename}"
    )


@pytest.mark.parametrize("audio_file", AUDIO_FILES)
def test_upload_audio(setup: FileContext, audio_file: str):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

    # Ensure the audio file exists
    assert os.path.exists(audio_file), f"Test audio file does not exist: {audio_file}"
    # Upload the file
    upload_response = upload_file(client, audio_file)
    assert isinstance(upload_response, FileUploadResponse)
    assert upload_response.uri.startswith(("file://", "s3://")), (
        f"Returned URI '{upload_response.uri}' does not start with 'file://' or 's3://'"
    )

    filename = os.path.basename(audio_file)
    expected_uri_pattern = re.compile(
        rf"(file|s3)://[^/]+/raw/{setup.org_id}/{setup.project_id}/[a-f0-9-]{{36}}/"
        + re.escape(filename)
        + "$"
    )
    # Check if the returned URI matches the expected format
    assert expected_uri_pattern.match(upload_response.uri), (
        f"Returned URI '{upload_response.uri}' does not match the expected format: "
        f"(file|s3)://file/raw/{setup.org_id}/{setup.project_id}/{{UUID}}/{filename}"
    )


@pytest.mark.parametrize("doc_file", DOC_FILES)
def test_upload_doc(setup: FileContext, doc_file: str):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

    # Ensure the doc file exists
    assert os.path.exists(doc_file), f"Test doc file does not exist: {doc_file}"
    # Upload the file
    upload_response = upload_file(client, doc_file)
    assert isinstance(upload_response, FileUploadResponse)
    assert upload_response.uri.startswith(("file://", "s3://")), (
        f"Returned URI '{upload_response.uri}' does not start with 'file://' or 's3://'"
    )

    filename = os.path.basename(doc_file)
    expected_uri_pattern = re.compile(
        rf"(file|s3)://[^/]+/raw/{setup.org_id}/{setup.project_id}/[a-f0-9-]{{36}}/"
        + re.escape(filename)
        + "$"
    )

    # Check if the returned URI matches the expected format
    assert expected_uri_pattern.match(upload_response.uri), (
        f"Returned URI '{upload_response.uri}' does not match the expected format: "
        f"(file|s3)://file/raw/{setup.org_id}/{setup.project_id}/{{UUID}}/{filename}"
    )


def test_upload_large_image_file(setup: FileContext):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

    # Create 25MB image file, assuming 3 bytes per pixel (RGB) and 8 bits per byte
    side_length = int(np.sqrt((25 * 1024 * 1024) / 3))
    data = np.random.randint(0, 256, (side_length, side_length, 3), dtype=np.uint8)
    img = Image.fromarray(data, "RGB")

    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, "large_image.png")
        img.save(file_path, format="PNG")

        pattern = re.compile("File size exceeds .+ limit")
        with pytest.raises(BadInputError, match=pattern):
            upload_file(client, file_path)


def test_get_raw_urls(setup: FileContext):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    # Upload files first
    uploaded_uris = []
    for f in ALL_FILES:
        response = upload_file(client, f)
        uploaded_uris.append(response.uri)

    # Now test get_raw_urls
    response = client.file.get_raw_urls(uploaded_uris)
    assert isinstance(response, GetURLResponse)
    assert len(response.urls) == len(ALL_FILES)
    for original_file, url in zip(ALL_FILES, response.urls, strict=True):
        downloaded_content = httpx.get(url).content
        original_content = _read_file_content(original_file)
        # Compare the contents
        assert original_content == downloaded_content, (
            f"Content mismatch for file: {original_file}"
        )

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


def test_get_thumbnail_urls(setup: FileContext):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)

    # Upload files first
    uploaded_uris = [upload_file(client, f).uri for f in ALL_FILES]

    # Test get_thumbnail_urls
    response = client.file.get_thumbnail_urls(uploaded_uris)
    assert isinstance(response, GetURLResponse)
    assert len(response.urls) == len(ALL_FILES)
    thumb_url_map = {basename(f): url for f, url in zip(ALL_FILES, response.urls, strict=True)}

    # Compare thumbnails
    for file_path in ALL_FILES:
        thumb_url = thumb_url_map[basename(file_path)]
        if file_path in IMAGE_FILES + DOC_FILES:
            expected_thumb = _read_file_content(f"{file_path}.thumb.webp")
        elif file_path in AUDIO_FILES:
            expected_thumb = _read_file_content(f"{file_path}.thumb.mp3")
        else:
            raise ValueError(f"Unexpected file: {file_path}")
        if thumb_url.startswith(("http://", "https://")):
            downloaded_thumb = httpx.get(thumb_url).content
        else:
            downloaded_thumb = _read_file_content(thumb_url)
        # Compare the contents
        if file_path in AUDIO_FILES:
            # We could find a way to strip out ID3 tags but it's easier to just compare parts of it
            expected_thumb = expected_thumb[-round(len(expected_thumb) * 0.9) :]
            downloaded_thumb = downloaded_thumb[-round(len(downloaded_thumb) * 0.9) :]
        assert expected_thumb == downloaded_thumb, f"Thumbnail mismatch for file: {file_path}"


def test_thumbnail_transparency(setup: FileContext):
    client = JamAI(user_id=setup.user_id, project_id=setup.project_id)
    response = upload_file(client, FILES["github-mark-white.png"])
    response = client.file.get_thumbnail_urls([response.uri])
    assert isinstance(response, GetURLResponse)
    assert len(response.urls) == 1
    thumb_url = response.urls[0]
    if thumb_url.startswith(("http://", "https://")):
        downloaded_thumbnail = httpx.get(thumb_url).content
    else:
        downloaded_thumbnail = _read_file_content(thumb_url)

    image = Image.open(BytesIO(downloaded_thumbnail))
    assert image.mode == "RGBA"
