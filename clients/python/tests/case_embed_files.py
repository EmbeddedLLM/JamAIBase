from pathlib import Path

import httpx
import pytest

from jamaibase import protocol

tests_dir = Path(__file__).parent.resolve()

PORT = 7770


@pytest.mark.asyncio
async def test_list_dir() -> None:
    async_client = httpx.AsyncClient(timeout=None)
    response = await async_client.get(
        url=f"http://127.0.0.1:{PORT}/api/v1/list_dir", params={"path": "amagpt"}, timeout=None
    )
    print(response)
    print(response.text)
    assert response.status_code == 200
    assert len(response.json()) > 0


# Example usage
def get_s3_filepath():
    files = []
    for d in tests_dir.iterdir():
        if not d.is_dir():
            continue
        if d.name in ["__pycache__", "_loader_check"]:
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            filepath = str(f.relative_to(tests_dir.parent))

            files.append(f"s3:///amagpt/{filepath.split('/')[-1]}")

    return files


@pytest.mark.asyncio
async def test_load_file() -> None:
    async_client = httpx.AsyncClient(timeout=None)
    s3_uri_list = get_s3_filepath()
    print(s3_uri_list)
    for i, s3_uri in enumerate(s3_uri_list):
        response = await async_client.post(
            url=f"http://127.0.0.1:{PORT}/api/v1/load_s3file",
            json=protocol.File(
                **{"uri": s3_uri, "document_id": str(i), "access_level": 0}
            ).model_dump(),
            timeout=None,
        )
        print(response.text)
        print(response.json())
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_embed_files() -> None:
    async_client = httpx.AsyncClient(timeout=None)
    s3_uri_list = get_s3_filepath()
    print(s3_uri_list)
    for i, s3_uri in enumerate(s3_uri_list):
        response = await async_client.post(
            url=f"http://127.0.0.1:{PORT}/api/v1/embed_files",
            json=protocol.EmbedFileRequest(
                files=[protocol.File(**{"uri": s3_uri, "document_id": str(i), "access_level": 0})]
            ).model_dump(),
            timeout=None,
        )
        print(response.text)
        print(response)
        assert response.status_code == 200


# if __name__ == '__main__':
# from loguru import logger
# async_client = httpx.AsyncClient(timeout=None)
# logger.info("Test /api/v1/list_dir endpoint")
# asyncio.run(test_list_dir(async_client))
# async_client = httpx.AsyncClient(timeout=None)
# logger.info("Test /api/v1/load_file endpoint")
# asyncio.run(test_load_file(async_client))
# async_client = httpx.AsyncClient(timeout=None)
# logger.info("Test /api/v1/embed_files endpoint")
# asyncio.run(test_embed_files(async_client))
