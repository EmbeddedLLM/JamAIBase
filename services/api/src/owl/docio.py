from mimetypes import guess_type

import httpx
from httpx import Timeout
from langchain.docstore.document import Document

HTTP_CLIENT = httpx.Client(transport=httpx.HTTPTransport(retries=3), timeout=Timeout(5 * 60))


class DocIOAPIFileLoader:
    """Load files using docio API."""

    def __init__(
        self,
        file_path: str,
        url,
        client: httpx.Client = HTTP_CLIENT,
    ) -> None:
        """Initialize with a file path."""
        self.url = url
        self.file_path = file_path
        self.client = client

    def load(self) -> list[Document]:
        """Load file."""
        # Guess the MIME type of the file based on its extension
        mime_type, _ = guess_type(self.file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"  # Default MIME type

        # Extract the filename from the file path
        filename = self.file_path.split("/")[-1]

        # Return the response from the forwarded request
        documents = []
        # Open the file in binary mode
        with open(self.file_path, "rb") as f:
            response = self.client.post(
                f"{self.url}/v1/load_file",
                files={
                    "file": (filename, f, mime_type),
                },
                timeout=None,
            )
            if response.status_code != 200:
                err_mssg = response.text
                raise RuntimeError(err_mssg)
            for doc in response.json():
                documents.append(
                    Document(page_content=doc["page_content"], metadata=doc["metadata"])
                )
        return documents
