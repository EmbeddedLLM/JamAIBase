from mimetypes import guess_type

import httpx
import pytest
from docio.routers.loader import load_file


def get_s3_file_uri():
    return [
        "s3:///amagpt-test/test-directory/Report.docx",
        "s3:///amagpt-test/test-directory/constitution_id.pdf",
        "s3:///amagpt-test/test-directory/Sample markdown.md",
        # "s3:///amagpt-test/test-directory/tgzht_article_attachment_515_1.pdf.csv", # fail, not a valid csv
        "s3:///amagpt-test/test-directory/Google Finance Investment Tracker.xlsx",
        "s3:///amagpt-test/test-directory/Contracts-Act-1950.PDF",
        "s3:///amagpt-test/test-directory/Google Finance Investment Tracker - Price History.csv",
        "s3:///amagpt-test/test-directory/Photo album.pptx",
        "s3:///amagpt-test/test-directory/Photo album.pptx.pdf",
        "s3:///amagpt-test/test-directory/penal_code_my.pdf",
    ]


@pytest.mark.mute
@pytest.mark.parametrize("file_uri", get_s3_file_uri())
def test_file_loader_api_s3(file_uri: str):
    response = httpx.post(
        "http://127.0.0.1:6979/api/docio/v1/load_s3file",
        json={"uri": file_uri, "document_id": "", "access_level": 0},
        timeout=None,
    )

    assert response.status_code == 200


def get_local_uri():
    return [
        "../autopilot/tests/test_data/2205.14135_flashattention.pdf",
        "../autopilot/tests/test_data/2307.08691_flashattention2.pdf",
        "../autopilot/tests/test_data/2309.06180_vllm.pdf",
        "../autopilot/tests/test_data/2310.08560_memgpt.pdf",
        "../autopilot/tests/test_data/2310.08560_memgpt.pdf",
        "../autopilot/tests/test_data/amd-cdna2-white-paper.pdf",
        "../autopilot/tests/test_data/amd-instinct-mi200-datasheet.pdf",
        "../autopilot/tests/test_data/data.csv",
        "../autopilot/tests/test_data/data.txt",
        "../autopilot/tests/test_data/mi200 instruction set.pdf",
        "../autopilot/tests/test_data/rdna-whitepaper.pdf",
        "../autopilot/tests/test_data/tgzht_article_attachment_387_1.pdf",
        "../autopilot/tests/test_data/tgzht_article_attachment_515_1.pdf",
        "../autopilot/tests/test_data/tgzht_article_attachment_628_1.pdf",
        "../autopilot/tests/test_data/tgzht_article_attachment_763_1.pdf",
        "../autopilot/tests/test_data/tgzht_article_attachment_764_1.pdf",
        "../autopilot/tests/test_data/tgzht_article_attachment_798_1.pdf",
    ]


@pytest.mark.local
@pytest.mark.parametrize("file_uri", get_local_uri())
def test_file_loader_api_local(file_uri: str):
    unstructuredio_url = "http://localhost:6989/general/v0/general"
    unstructuredio_api_key = "LOCAL"

    load_file(file_uri, unstructuredio_url, unstructuredio_api_key)


@pytest.mark.mute
@pytest.mark.parametrize("file_uri", get_local_uri())
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
