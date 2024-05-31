import asyncio
import json
import os
from mimetypes import guess_type
from pathlib import Path

import httpx

from jamaibase import JamAI, protocol

tests_dir = Path(__file__).parent.resolve()

# PORT = 7779
PORT = 7770
client = JamAI(api_base=f"http://127.0.0.1:{PORT}/api")
# client = JamAI()


# Example usage
async def main():
    files = []
    files_to_upload = []
    i = 0
    for d in tests_dir.iterdir():
        if not d.is_dir():
            continue
        if d.name in ["__pycache__", "_loader_check"]:
            continue
        for f in d.iterdir():
            # if os.path.splitext(f)[1] not in [".docx", ".pptx", ".ppt", ".xlsx"]:
            # if os.path.splitext(f)[1] not in [".pdf"]:
            #     continue
            print(f"file: {f}")
            if not f.is_file():
                continue
            files.append(
                {
                    "uri": str(f.relative_to(tests_dir.parent)),
                    "document_id": str(i),
                    "access_level": 0,
                }
            )
            files_to_upload.append(str(f.relative_to(tests_dir.parent)))

    # Upload each file
    for file_path in files_to_upload:
        await client.upload_file_async(
            protocol.FileUploadS3Request(
                filepath=file_path,
                uri=f"s3:///amagpt/{file_path.split('/')[-1]}",
                overwrite=True,
                # overwrite=False
            )
        )
        print(f"uploaded file: {file_path}")


if __name__ == "__main__":
    asyncio.run(main())
