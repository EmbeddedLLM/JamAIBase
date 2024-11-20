from mimetypes import guess_type
from pathlib import Path

import httpx


def get_local_uri():
    return [
        Path("../../clients/python/tests/files/txt/weather.txt").as_posix(),
        Path("../../clients/python/tests/files/pdf/ca-warn-report.pdf").as_posix(),
        Path("README.md").as_posix(),
    ]


def test_file_loader_api(file_uri: str):
    # Guess the MIME type of the file based on its extension
    mime_type, _ = guess_type(file_uri)
    if mime_type is None:
        mime_type = "application/octet-stream"  # Default MIME type

    # Extract the filename from the file path
    filename = file_uri.split("/")[-1]

    # Open the file in binary mode
    with open(file_uri, "rb") as f:
        response = httpx.post(
            "http://127.0.0.1:6979/api/docio/v1/load_file",
            files={
                "file": (filename, f, mime_type),
            },
            timeout=None,
        )

    assert response.status_code == 200


if __name__ == "__main__":
    for file_url in get_local_uri():
        test_file_loader_api(file_uri=file_url)
