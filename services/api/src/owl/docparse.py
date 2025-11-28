import asyncio
import sys
from hashlib import blake2b
from io import BytesIO
from os.path import basename, splitext

import httpx
import orjson
import pandas as pd
import xmltodict
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents.base import Document
from loguru import logger

from owl.configs import CACHE, ENV_CONFIG
from owl.types import Chunk, SplitChunksParams, SplitChunksRequest
from owl.utils.exceptions import BadInputError, JamaiException, UnexpectedError
from owl.utils.io import get_bytes_size_mb, json_dumps, json_loads

# Table mapping all non-printable characters to None
NOPRINT_TRANS_TABLE = {
    i: None for i in range(0, sys.maxunicode + 1) if not chr(i).isprintable() and chr(i) != "\n"
}


def make_printable(s: str) -> str:
    """
    Replace non-printable characters in a string using
    `translate()` that removes characters that map to None.

    # https://stackoverflow.com/a/54451873
    """
    return s.translate(NOPRINT_TRANS_TABLE)


def format_chunks(documents: list[Document], file_name: str, page: int = None) -> list[Chunk]:
    if page is not None:
        for d in documents:
            d.metadata["page"] = page
    chunks = [
        # TODO: Probably can use regex for this
        # Replace vertical tabs, form feed, Unicode replacement character
        # page_content=d.page_content.replace("\x0c", " ")
        # .replace("\x0b", " ")
        # .replace("\uFFFD", ""),
        # For now we use a more aggressive strategy
        Chunk(
            text=make_printable(d.page_content),
            title=d.metadata.get("title", ""),
            page=d.metadata.get("page", 0),
            file_name=file_name,
            file_path=file_name,
            metadata=d.metadata,
        )
        for d in documents
    ]
    return chunks


class BaseLoader:
    """Base loader class for loading documents."""

    def __init__(self, request_id: str = ""):
        """
        Initialize the BaseLoader class.

        Args:
            request_id (str, optional): Request ID for logging. Defaults to "".
        """
        self.request_id = request_id

    def split_chunks(
        self, request: SplitChunksRequest, page_break_placeholder: str | None = None
    ) -> list[Chunk]:
        """Split a list of chunks using RecursiveCharacterTextSplitter.

        Args:
            request (SplitChunksRequest): Request containing chunks and splitting parameters.
            page_break_placeholder (str | None): The string that signifies a page break.

        Returns:
            list[Chunk]: A list of split chunks.

        Raises:
            BadInputError: If the split method is not supported.
            BadInputError: If chunk splitting fails.
        """
        _id = request.id
        logger.info(f"{_id} - Split documents request: {request.str_trunc()}")
        if request.params.method == "RecursiveCharacterTextSplitter":
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=request.params.chunk_size,
                chunk_overlap=request.params.chunk_overlap,
            )
        else:
            raise BadInputError(f"Split method not supported: {request.params.method}")

        # Pre-process chunks to handle page breaks before splitting by character count.
        if page_break_placeholder is not None:
            doc_chunks = []
            page_counter = 0
            for chunk in request.chunks:
                texts_from_pages = chunk.text.split(page_break_placeholder)
                for text in texts_from_pages:
                    page_counter += 1

                    new_metadata = chunk.metadata.copy()
                    new_metadata["page"] = page_counter

                    doc_chunks.append(
                        Chunk(
                            text=text.strip(),
                            title=chunk.title,
                            page=page_counter,  # Update page number
                            file_name=chunk.file_name,
                            file_path=chunk.file_name,
                            metadata=new_metadata,
                        )
                    )
        else:
            # If no page break handling is needed, use the chunks as they are.
            doc_chunks = request.chunks

        try:
            # Now, split the processed chunks (doc_chunks) by character count.
            chunks = []
            for chunk in doc_chunks:
                chunks += [
                    Chunk(
                        text=d.page_content,
                        title=chunk.title,
                        page=chunk.page,
                        file_name=chunk.file_name,
                        file_path=chunk.file_name,
                        metadata=chunk.metadata,
                    )
                    for d in text_splitter.split_documents([Document(page_content=chunk.text)])
                ]
            logger.info(
                f"{len(request.chunks):,d} chunks split into {len(chunks):,d} chunks. ({_id})",
            )
            return chunks
        except Exception as e:
            logger.exception(f"Failed to split chunks. ({_id})")
            raise BadInputError("Failed to split chunks.") from e


class GeneralDocLoader(BaseLoader):
    """
    General document loader class supporting various file extensions.

    This loader intelligently handles different file types, using DoclingLoader for
    formats it supports and falling back to other methods for text-based and structured
    data formats like JSON, XML, CSV, and TSV.
    """

    def __init__(self, request_id: str = ""):
        """
        Initialize the GeneralDocLoader class.

        Args:
            request_id (str, optional): Request ID for logging. Defaults to "".
        """
        super().__init__(request_id=request_id)

    async def load_document(
        self,
        file_name: str,
        content: bytes,
    ) -> str:
        """
        Loads and processes a file, converting it to Markdown format.

        Supports file types: PDF, DOCX, PPTX, XLSX, HTML, MD, TXT, JSON, JSONL, XML, CSV, TSV.
        - PDF, DOCX, PPTX, XLSX, HTML: Parsed into Markdown using `DoclingLoader`.
        - MD, TXT: Read directly.
        - JSON: Formatted as a string with 2-space indenting.
        - JSONL: Converted into Markdown table format using `pandas`.
        - XML: Formatted as a JSON string with 2-space indenting.
        - CSV, TSV: Converted into Markdown table format using `pandas`.

        Args:
            file_name (str): The name of the file.
            content (bytes): The binary content of the file.

        Returns:
            str: The document content in Markdown format, or JSON string for JSON/XML.

        Raises:
            BadInputError: If the parsing fails due to unsupported type or other errors.
        """
        if len(content) == 0:
            raise BadInputError(f'Input file "{file_name}" is empty.')
        # Check cache
        cache_ttl = ENV_CONFIG.document_loader_cache_ttl_sec
        cache_key = ""
        if cache_ttl > 0:
            content_len = len(content)
            content_hash = blake2b(content).hexdigest()
            cache_key = f"document:{basename(file_name)}:{content_hash}:{content_len}"
        # If multiple rows reference the same file, this lock prevents concurrent parsing
        # Only the first row will trigger parsing, the rest will read from cache
        # The lock expires after 2 minutes automatically if not released
        async with CACHE.alock(f"{cache_key}:lock", blocking=cache_ttl > 0, expire=120):
            md = None
            if cache_key != "":
                md = await CACHE.get(cache_key)
            if md is not None:
                # Extend cache TTL
                await CACHE._redis_async.expire(
                    cache_key, ENV_CONFIG.document_loader_cache_ttl_sec
                )
                logger.info(f'File "{file_name}" loaded from cache (cache key="{cache_key}").')
                return md
            try:
                ext = splitext(file_name)[1].lower()
                if ext in [".pdf", ".docx", ".pptx", ".xlsx", ".html"]:
                    doc_loader = DoclingLoader(self.request_id)
                    md = await doc_loader.document_to_markdown(
                        file_name=file_name, content=content
                    )
                elif ext in [".md", ".txt"]:
                    md = content.decode("utf-8")
                elif ext in [".json"]:
                    md = json_dumps(
                        json_loads(content.decode("utf-8")), option=orjson.OPT_INDENT_2
                    )
                elif ext in [".jsonl"]:
                    md = pd.read_json(
                        BytesIO(content),
                        lines=True,
                    ).to_markdown()
                elif ext in [".xml"]:
                    md = json_dumps(xmltodict.parse(content), option=orjson.OPT_INDENT_2)
                elif ext in [".csv", ".tsv"]:
                    md = pd.read_csv(
                        BytesIO(content),
                        sep="\t" if ext == ".tsv" else ",",
                    ).to_markdown()
                else:
                    raise BadInputError(f'File type "{ext}" is not supported at the moment.')
                if len(md.strip()) == 0:
                    raise BadInputError(f'Input file "{file_name}" is empty.')
                # Set cache
                if cache_ttl > 0:
                    await CACHE.set(cache_key, md, ex=cache_ttl)
                    logger.info(
                        f'File "{file_name}" successfully parsed into markdown. (cache key="{cache_key}")'
                    )
                else:
                    logger.info(f'File "{file_name}" successfully parsed into markdown.')
                return md

            except JamaiException:
                raise
            except pd.errors.EmptyDataError as e:
                raise BadInputError(f'Input file "{file_name}" is empty.') from e
            except Exception as e:
                logger.error(f'Failed to parse file "{file_name}": {repr(e)}')
                raise BadInputError(f'Failed to parse file "{file_name}".') from e

    async def load_document_chunks(
        self,
        file_name: str,
        content: bytes,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> list[Chunk]:
        """
        Loads and processes a file, splitting it into chunks.

        Supports file types: PDF, DOCX, PPTX, XLSX, HTML, MD, TXT, JSON, JSONL, XML, CSV, TSV.
        - PDF, DOCX, PPTX, XLSX, HTML: Parsed and chunked using `DoclingLoader`.
        - MD, TXT: Read directly and chunked using `RecursiveCharacterTextSplitter`.
        - JSON, JSONL: Each JSON is formatted as a chunk with 2-space indenting.
        - CSV, TSV: Each row is parsed into a JSON and formatted as a chunk with 2-space indenting.
        - XML: Each XML is formatted as a JSON chunk with 2-space indenting.

        Args:
            file_name (str): The name of the file.
            content (bytes): The binary content of the file.
            chunk_size (int): The desired size of each chunk in tokens.
            chunk_overlap (int): The number of tokens to overlap between chunks.

        Returns:
            list[Chunk]: A list of Chunk objects representing the processed file content.

        Raises:
            BadInputError: If the parsing and splitting fails due to unsupported type or other errors.
        """
        if len(content) == 0:
            raise BadInputError(f'Input file "{file_name}" is empty.')
        # Check cache
        cache_ttl = ENV_CONFIG.document_loader_cache_ttl_sec
        cache_key = ""
        if cache_ttl > 0:
            content_len = len(content)
            content_hash = blake2b(content).hexdigest()
            cache_key = f"chunks:{basename(file_name)}:{content_hash}:{content_len}"
        # If multiple rows reference the same file, this lock prevents concurrent parsing
        # Only the first row will trigger parsing, the rest will read from cache
        # The lock expires after 2 minutes automatically if not released
        async with CACHE.alock(f"{cache_key}:lock", blocking=cache_ttl > 0, expire=120):
            chunk_json_str = None
            if cache_key != "":
                chunk_json_str = await CACHE.get(cache_key)
            if chunk_json_str is not None:
                # Extend cache TTL
                await CACHE._redis_async.expire(cache_key, cache_ttl)
                logger.info(
                    f'File chunks "{file_name}" loaded from cache (cache key="{cache_key}").'
                )
                return [Chunk.model_validate(chunk) for chunk in json_loads(chunk_json_str)]
            try:
                ext = splitext(file_name)[1].lower()
                if ext in [".pdf", ".docx", ".pptx", ".xlsx", ".html"]:
                    if ext in [".pdf", ".pptx", ".xlsx"]:
                        doc_loader = DoclingLoader(
                            self.request_id, page_break_placeholder="=====Page===Break====="
                        )
                    else:
                        doc_loader = DoclingLoader(self.request_id, page_break_placeholder=None)
                    chunks = await doc_loader.document_to_chunks(
                        file_name=file_name,
                        content=content,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                    )
                elif ext in [".md", ".txt"]:
                    content = content.decode("utf-8")
                    if len(content.strip()) == 0:
                        raise BadInputError(f'Input file "{file_name}" is empty.')
                    chunks = format_chunks(
                        [Document(page_content=content, metadata={"page": 1})],
                        file_name,
                    )
                    chunks = self.split_chunks(
                        SplitChunksRequest(
                            chunks=chunks,
                            params=SplitChunksParams(
                                chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap,
                            ),
                        )
                    )
                elif ext in [".json", ".jsonl", ".csv", ".tsv"]:
                    if ext in [".csv", ".tsv"]:
                        json_list = pd.read_csv(
                            BytesIO(content),
                            sep="\t" if ext == ".tsv" else ",",
                        ).to_dict(orient="records")
                    else:
                        content = content.decode("utf-8")
                        if ext == ".jsonl":
                            json_list = [
                                json_loads(line)
                                for line in content.split("\n")
                                if line.strip() != ""
                            ]
                        else:
                            json_list = [json_loads(content)]
                    docs = [
                        Document(
                            page_content=json_dumps(js, option=orjson.OPT_INDENT_2),
                            metadata={"page": 1, "row": i},
                        )
                        for i, js in enumerate(json_list)
                    ]
                    chunks = format_chunks(docs, file_name)
                elif ext in [".xml"]:
                    chunks = format_chunks(
                        [
                            Document(
                                page_content=json_dumps(
                                    xmltodict.parse(content), option=orjson.OPT_INDENT_2
                                ),
                                metadata={"page": 1},
                            )
                        ],
                        file_name,
                    )
                else:
                    raise BadInputError(f'File type "{ext}" is not supported at the moment.')
                if len(chunks) == 0:
                    raise BadInputError(f'Input file "{file_name}" is empty.')
                # Set cache
                if cache_ttl > 0:
                    chunk_json_str = json_dumps([chunk.model_dump() for chunk in chunks])
                    await CACHE.set(cache_key, chunk_json_str, ex=cache_ttl)
                    logger.info(
                        (
                            f'File "{file_name}" successfully parsed and split into '
                            f'{len(chunks):,d} chunks (cache key="{cache_key}").'
                        )
                    )
                else:
                    logger.info(
                        (
                            f'File "{file_name}" successfully parsed and split into '
                            f"{len(chunks):,d} chunks."
                        )
                    )
                return chunks

            except JamaiException:
                raise
            except pd.errors.EmptyDataError as e:
                raise BadInputError(f'Input file "{file_name}" is empty.') from e
            except Exception as e:
                logger.error(f'Failed to parse and split file "{file_name}": {repr(e)}')
                raise BadInputError(f'Failed to parse and split file "{file_name}".') from e


class DoclingLoader(BaseLoader):
    """
    A class for loading and processing documents using Docling-Serve API.
    """

    API_VERSION = "v1"

    def __init__(
        self,
        request_id: str = "",
        docling_serve_url: str | None = None,
        page_break_placeholder: str | None = None,
    ):
        """
        Initialize the DoclingLoader class.

        Args:
            request_id (str, optional): Request ID for logging. Defaults to "".
        """
        super().__init__(request_id=request_id)
        self.http_aclient = httpx.AsyncClient(
            timeout=60.0 * 10,
            transport=httpx.AsyncHTTPTransport(retries=3),
        )
        self.docling_serve_url = (
            ENV_CONFIG.docling_url if docling_serve_url is None else docling_serve_url
        )
        self.page_break_placeholder = page_break_placeholder

    async def _parse_document(
        self,
        file_name: str,
        content: bytes,
    ) -> dict:
        """
        Parse the document using Docling-Serve API (async pattern).

        Args:
            file_path (str): Path to the document file to be parsed (local temp path).
            file_name (str): Original file name.
            content (bytes): Binary content of the file.
            force_full_page_ocr (bool): Whether to force full-page OCR.

        Returns:
            dict: The JSON response from docling-serve.

        Raises:
            HTTPException: If the document conversion fails via docling-serve.
        """
        size_mb = get_bytes_size_mb(content)
        logger.info(
            f'Calling Docling-Serve for file "{file_name}" with size {size_mb:.3f} MiB. ({self.request_id})'
        )

        files = {"files": (file_name, content, "application/octet-stream")}
        data = {
            "to_formats": ["md"],
            "image_export_mode": "placeholder",
            "pipeline": "standard",
            "ocr": True,
            "force_ocr": False,
            "ocr_engine": "easyocr",
            "pdf_backend": "dlparse_v4",
            "table_mode": "accurate",
            "abort_on_error": False,
            "return_as_file": False,
        }

        if self.page_break_placeholder is not None:
            data["md_page_break_placeholder"] = self.page_break_placeholder

        try:
            # Step 1: Start async conversion
            response = await self.http_aclient.post(
                f"{self.docling_serve_url}/{self.API_VERSION}/convert/file/async",
                files=files,
                data=data,
            )
            response.raise_for_status()
            task_id_data = response.json()
            task_id = task_id_data.get("task_id")
            if not task_id:
                raise UnexpectedError("Docling-Serve did not return a task_id.")

            # Step 2: Poll for completion
            poll_url = f"{self.docling_serve_url}/{self.API_VERSION}/status/poll/{task_id}"
            time_slept = 0
            sleep_for = 1
            task_status = None
            while time_slept < ENV_CONFIG.docling_timeout_sec:
                try:
                    poll_resp = await self.http_aclient.get(poll_url, timeout=20)
                    poll_resp.raise_for_status()
                    status_data = poll_resp.json()
                    task_status = status_data.get("task_status")
                except Exception as e:
                    logger.error(f"Polling API error: {e}")

                if task_status == "success":
                    break  # Exit polling loop
                elif task_status in ("failure", "revoked"):
                    error_info = status_data.get("task_result", {}).get("error", "Unknown error")
                    logger.error(
                        (
                            f'Docling-Serve task "{task_id}" for document "{file_name}" '
                            f"with size {size_mb:.3f} MiB failed: {error_info}. ({self.request_id})"
                        )
                    )
                    raise BadInputError(f'Your document "{file_name}" cannot be parsed.')
                # If not success, failure, or revoked, it's still processing or in another state
                await asyncio.sleep(sleep_for)
                time_slept += sleep_for
            else:  # Executed if the while loop completes without a 'break'
                logger.error(
                    (
                        f'Docling-Serve task "{task_id}" for document "{file_name}" with size {size_mb:.3f} MiB '
                        f"timed out after polling for {time_slept} seconds. ({self.request_id})"
                    )
                )
                raise BadInputError(f'Your document "{file_name}" took too long to parse.')

            # Step 3: Fetch result
            result_url = f"{self.docling_serve_url}/{self.API_VERSION}/result/{task_id}"
            result_resp = await self.http_aclient.get(result_url, timeout=60)
            result_resp.raise_for_status()
            return result_resp.json()

        except httpx.TimeoutException as e:
            logger.error(f"Docling-Serve API timeout error: {e}")
            raise BadInputError(f'Your document "{file_name}" took too long to parse.') from e
        except httpx.HTTPError as e:
            logger.error(f"Docling-Serve API error: {e}")
            raise UnexpectedError(f"Docling-Serve API error: {e}") from e
        except Exception as e:
            raise UnexpectedError(f"Docling-Serve API error: {e}") from e

    async def document_to_markdown(self, file_name: str, content: bytes) -> str:
        """
        Converts a document to Markdown format using Docling-Serve.
        """
        docling_response = await self._parse_document(file_name, content)
        return docling_response.get("document", {}).get("md_content", "")

    async def document_to_chunks(
        self, file_name: str, content: bytes, chunk_size: int, chunk_overlap: int
    ) -> list[Chunk]:
        """
        Converts a document to chunks, respecting page and table boundaries, using Docling-Serve.
        """
        docling_response = await self._parse_document(file_name, content)
        md_content = docling_response.get("document", {}).get("md_content", "")

        documents = [Document(page_content=md_content, metadata={"page": 1})]
        chunks = format_chunks(documents, file_name)

        chunks = self.split_chunks(
            SplitChunksRequest(
                chunks=chunks,
                params=SplitChunksParams(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                ),
            ),
            page_break_placeholder=self.page_break_placeholder,
        )

        return chunks
