import hashlib
import json
import os
from os.path import basename, dirname, join, realpath

import pytest

from owl.docparse import DoclingLoader
from owl.utils.test import get_file_map

TEST_FILE_DIR = join(dirname(realpath(__file__)), "files")
FILES = get_file_map(TEST_FILE_DIR)

GT_FILE_DIR = join(dirname(realpath(__file__)), "docling_ground_truth")
GT_FILES = get_file_map(GT_FILE_DIR)


def get_canonical_json_hash(data: dict) -> str:
    """
    Calculates a SHA256 hash of a dictionary after canonical JSON serialization.
    Ensures keys are sorted and spacing is compact for consistent hashing.
    """
    if not isinstance(data, dict):
        # If data is not a dict (e.g., an error string or None from .get("document", {})),
        # we still need a consistent way to hash it. Converting to string is a simple way.
        # However, for this test, 'document' should ideally always be a dict or an empty dict.
        # If it can be None or other types, this part might need more specific handling
        # based on expected behavior.
        stable_representation = str(data)
    else:
        # sort_keys=True: Essential for canonical form.
        # separators=(',', ':'): Creates the most compact JSON, removing unnecessary whitespace.
        stable_representation = json.dumps(data, sort_keys=True, separators=(",", ":"))

    json_bytes = stable_representation.encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest()


@pytest.mark.timeout(180)
@pytest.mark.parametrize(
    "doc_path",
    [
        FILES["Swire_AR22_e_230406_sample.pdf"],
        FILES["GitHub 表单架构语法 - GitHub 文档.pdf"],
    ],
    ids=lambda x: basename(x),
)
async def test_convert_pdf_document_to_markdown(doc_path: str):
    """
    Test the conversion of various document types to markdown.
    """
    loader = DoclingLoader(
        request_id="test_request",
        docling_serve_url="http://localhost:5001",
    )
    with open(doc_path, "rb") as f:
        doc_content_bytes = f.read()

    api_response_data = await loader._parse_document(basename(doc_path), doc_content_bytes)

    api_document_content = api_response_data.get("document", {})

    # Sanity check on md_content from the API response
    md_content_from_api = api_document_content.get("md_content", "")
    assert isinstance(md_content_from_api, str)

    # --- Ground Truth Comparison ---
    gt_file_path = GT_FILES[f"{os.path.splitext(basename(doc_path))[0]}.json"]

    with open(gt_file_path, "r", encoding="utf-8") as f_gt:
        expected_document_content = json.load(f_gt).get("document", {})

    api_content_hash = get_canonical_json_hash(api_document_content)
    gt_content_hash = get_canonical_json_hash(expected_document_content)

    assert api_content_hash == gt_content_hash, (
        f"Hash mismatch for the 'document' content of '{basename(doc_path)}'.\n"
        f"API Hash: {api_content_hash}\n"
        f"GT Hash : {gt_content_hash}\n"
        f"API 'document' part:\n{json.dumps(api_document_content, sort_keys=True, indent=2, ensure_ascii=False)}\n"
        f"Expected 'document' part (from {basename(gt_file_path)}):\n{json.dumps(expected_document_content, sort_keys=True, indent=2, ensure_ascii=False)}"
    )
