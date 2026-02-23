import asyncio
import base64
import sys
from hashlib import blake2b
from io import BytesIO
from os.path import splitext

import httpx
import orjson
import pandas as pd
import xmltodict
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents.base import Document
from loguru import logger
from pdf2image import convert_from_bytes, pdfinfo_from_bytes

from owl.configs import CACHE, ENV_CONFIG
from owl.types import (
    ChatEntry,
    Chunk,
    ImageContent,
    ImageContentData,
    ModelConfigRead,
    SplitChunksParams,
    SplitChunksRequest,
    TextContent,
)
from owl.utils.exceptions import (
    BadInputError,
    JamaiException,
    ResourceNotFoundError,
    UnexpectedError,
)
from owl.utils.io import EXT_TO_MIME, get_async_client, get_bytes_size_mb, json_dumps, json_loads
from owl.utils.lm import LMEngine

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

    This loader intelligently handles different file types, using VLMDocLoader
    (when ENV_CONFIG.use_vlm_ocr is True and lm_engine is provided) or DoclingLoader
    (default) for document formats. Falls back to other methods for text-based and
    structured data formats like JSON, XML, CSV, and TSV.
    """

    def __init__(
        self,
        request_id: str = "",
        lm_engine: "LMEngine | None" = None,
        vlm_temperature: float = 0.01,
        vlm_max_tokens: int = 10000,
        vlm_batch_size: int = 10,
    ):
        """
        Initialize the GeneralDocLoader class.

        Args:
            request_id (str, optional): Request ID for logging. Defaults to "".
            lm_engine (LMEngine | None): LMEngine instance for VLM OCR. Required when
                ENV_CONFIG.use_vlm_ocr is True to enable VLMDocLoader.
            vlm_temperature (float): Temperature for VLM OCR completions. Defaults to 0.01.
            vlm_max_tokens (int): Max tokens for VLM OCR responses. Defaults to 10000.
            vlm_batch_size (int): Batch size for processing large documents. Defaults to 10.
        """
        super().__init__(request_id=request_id)
        self.lm_engine = lm_engine
        self.vlm_temperature = vlm_temperature
        self.vlm_max_tokens = vlm_max_tokens
        self.vlm_batch_size = vlm_batch_size

    async def load_document(
        self,
        file_name: str,
        content: bytes,
    ) -> str:
        """
        Loads and processes a file, converting it to Markdown format.

        Supports file types: PDF, DOCX, PPTX, XLSX, HTML, MD, TXT, JSON, JSONL, XML, CSV, TSV.
        - PDF, HTML, DOCX, PPTX, XLSX: Parsed using `VLMDocLoader` (if ENV_CONFIG.use_vlm_ocr
          is True and lm_engine provided) via Gotenberg → PDF → VLM OCR, or `DoclingLoader` (default).
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
        ext = splitext(file_name)[1].lower()
        if cache_ttl > 0:
            content_len = len(content)
            content_hash = blake2b(content).hexdigest()
            parser_type = "vlm" if (ENV_CONFIG.use_vlm_ocr and self.lm_engine) else "docling"
            cache_key = f"document:{ext}:{parser_type}:{content_hash}:{content_len}"
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
                logger.debug(f'File "{file_name}" loaded from cache (cache key="{cache_key}").')
                return md
            try:
                if ext in [".pdf", ".docx", ".pptx", ".xlsx", ".html"]:
                    # Use VLM OCR if enabled in ENV_CONFIG and lm_engine is provided
                    # Supports: PDF (direct), HTML/DOCX/PPTX/XLSX (via Gotenberg → PDF)
                    if ENV_CONFIG.use_vlm_ocr and self.lm_engine:
                        doc_loader = VLMDocLoader(
                            request_id=self.request_id,
                            lm_engine=self.lm_engine,
                            vlm_temperature=self.vlm_temperature,
                            vlm_max_tokens=self.vlm_max_tokens,
                            batch_size=self.vlm_batch_size,
                        )
                    else:
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
        - PDF, HTML, DOCX, PPTX, XLSX: Parsed using `VLMDocLoader` (if ENV_CONFIG.use_vlm_ocr
          is True and lm_engine provided) via Gotenberg → PDF → VLM OCR, or `DoclingLoader` (default),
          then chunked.
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
        ext = splitext(file_name)[1].lower()
        if cache_ttl > 0:
            content_len = len(content)
            content_hash = blake2b(content).hexdigest()
            parser_type = "vlm" if (ENV_CONFIG.use_vlm_ocr and self.lm_engine) else "docling"
            cache_key = f"chunks:{ext}:{parser_type}:{content_hash}:{content_len}:{chunk_size}:{chunk_overlap}"
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
                if ext in [".pdf", ".docx", ".pptx", ".xlsx", ".html"]:
                    # Use VLM OCR if enabled in ENV_CONFIG and lm_engine is provided
                    # Supports: PDF (direct), HTML/DOCX/PPTX/XLSX (via Gotenberg → PDF)
                    if ENV_CONFIG.use_vlm_ocr and self.lm_engine:
                        doc_loader = VLMDocLoader(
                            request_id=self.request_id,
                            lm_engine=self.lm_engine,
                            page_break_placeholder="=====Page===Break=====",
                            vlm_temperature=self.vlm_temperature,
                            vlm_max_tokens=self.vlm_max_tokens,
                            batch_size=self.vlm_batch_size,
                        )
                    else:
                        if ext in [".pdf", ".pptx", ".xlsx"]:
                            doc_loader = DoclingLoader(
                                self.request_id, page_break_placeholder="=====Page===Break====="
                            )
                        else:
                            doc_loader = DoclingLoader(
                                self.request_id, page_break_placeholder=None
                            )

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
        self.http_aclient = get_async_client(timeout=60.0 * 10)
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


class VLMDocLoader(BaseLoader):
    """
    A class for loading and processing documents using VLM (Vision Language Model) OCR.

    This loader converts documents to images and uses VLM chat completion for OCR,
    providing better document understanding compared to traditional OCR engines.

    Supported formats:
    - PDF: Direct conversion to images
    - HTML: Gotenberg (HTML → PDF) → images → VLM OCR
    - DOCX: Gotenberg (DOCX → PDF) → images → VLM OCR
    - PPTX: Gotenberg (PPTX → PDF) → images → VLM OCR
    - XLSX: Gotenberg (XLSX → PDF) → images → VLM OCR
    """

    def __init__(
        self,
        request_id: str = "",
        lm_engine: "LMEngine" = LMEngine,
        page_break_placeholder: str | None = None,
        gotenberg_url: str | None = None,
        vlm_temperature: float = 0.01,
        vlm_max_tokens: int = 10000,
        batch_size: int = 10,
    ):
        """
        Initialize the VLMDocLoader class.

        Args:
            request_id (str, optional): Request ID for logging. Defaults to "".
            lm_engine (LMEngine): LMEngine instance for VLM calls. Required.
            page_break_placeholder (str | None): The string that signifies a page break.
            gotenberg_url (str | None): URL for Gotenberg service. Defaults to ENV_CONFIG.gotenberg_url.
            vlm_temperature (float): Temperature parameter for VLM completion. Defaults to 0.01 for deterministic OCR.
            vlm_max_tokens (int): Maximum tokens for VLM completion response. Defaults to 10000.
            batch_size (int): Number of pages to convert and process in each batch for memory efficiency. Defaults to 10.
        """
        super().__init__(request_id=request_id)
        if lm_engine is None:
            raise ValueError("VLMDocLoader requires an LMEngine instance.")
        self.lm_engine = lm_engine
        self.page_break_placeholder = page_break_placeholder
        self.gotenberg_url = gotenberg_url or ENV_CONFIG.gotenberg_url
        self.vlm_temperature = vlm_temperature
        self.vlm_max_tokens = vlm_max_tokens
        self.batch_size = batch_size
        self.http_aclient = get_async_client(timeout=ENV_CONFIG.gotenberg_timeout_sec)

    async def _select_vlm_model(self) -> ModelConfigRead:
        """
        Select VLM model for OCR.

        Args:
            vlm_models: List of VLM models

        Returns:
            Selected ModelConfigRead
        """

        vlm_models = await self.lm_engine._get_models(capabilities=["image", "chat"])
        if not vlm_models:
            raise BadInputError("No VLM models available for OCR")

        target_id = ENV_CONFIG.vlm_model_id

        if target_id:
            vlm_model = next((m for m in vlm_models if m.id == target_id), None)

            if vlm_model is None:
                raise ResourceNotFoundError(
                    f"Configured VLM model '{target_id}' not found. ({self.request_id})"
                )
            logger.debug(
                f"Using VLM model: {vlm_model.name} (id: {vlm_model.id}). ({self.request_id})"
            )
            return vlm_model

    async def _convert_pdf_to_images_batched(self, content: bytes, batch_size: int):
        """
        Convert PDF pages to images in batches for memory efficiency.
        This is a generator that yields batches of image bytes.

        Args:
            content (bytes): PDF file content
            batch_size (int): Number of pages per batch

        Yields:
            tuple[int, list[bytes]]: Tuple of (starting_page_index, list of image bytes)
        """
        try:
            # Get total page count first
            info = pdfinfo_from_bytes(content)
            total_pages = info.get("Pages", 0)

            logger.debug(
                f"Converting PDF with {total_pages} pages in batches of {batch_size}. ({self.request_id})"
            )

            # Process pages in batches
            for start_page in range(1, total_pages + 1, batch_size):
                end_page = min(start_page + batch_size - 1, total_pages)

                images = convert_from_bytes(
                    content,
                    dpi=200,
                    fmt="jpeg",
                    first_page=start_page,
                    last_page=end_page,
                )

                image_bytes_list = []
                for img in images:
                    img_buffer = BytesIO()
                    img.save(img_buffer, format="JPEG", quality=95)
                    image_bytes_list.append(img_buffer.getvalue())
                    img.close()

                # Yield batch with starting index
                yield start_page - 1, image_bytes_list  # 0-indexed

        except Exception as e:
            logger.error(f"Failed to convert PDF to images in batches: {repr(e)}")
            raise BadInputError("Failed to convert PDF to images for OCR.") from e

    async def _convert_html_to_pdf_via_gotenberg(self, content: bytes) -> bytes:
        """
        Convert HTML to PDF using Gotenberg service.

        HTML files must be named 'index.html' according to Gotenberg requirements.

        Args:
            content (bytes): HTML file content

        Returns:
            bytes: PDF file content
        """
        try:
            logger.debug(f"Converting HTML to PDF via Gotenberg. ({self.request_id})")

            # Gotenberg requires HTML files to be named 'index.html'
            files = {
                "files": ("index.html", content, "text/html"),
            }

            response = await self.http_aclient.post(
                f"{self.gotenberg_url}/forms/chromium/convert/html",
                files=files,
            )
            response.raise_for_status()

            pdf_content = response.content
            logger.debug(
                f"HTML to PDF conversion successful, PDF size: {len(pdf_content)} bytes. ({self.request_id})"
            )
            return pdf_content

        except httpx.HTTPError as e:
            logger.error(f"Gotenberg HTML to PDF conversion failed: {repr(e)}")
            raise BadInputError("Failed to convert HTML to PDF using Gotenberg.") from e
        except Exception as e:
            logger.error(f"HTML to PDF conversion error: {repr(e)}")
            raise BadInputError("Failed to convert HTML to PDF.") from e

    async def _convert_office_to_pdf_via_gotenberg(self, content: bytes, file_name: str) -> bytes:
        """
        Convert Office documents (DOCX, PPTX, XLSX) to PDF using Gotenberg.

        Args:
            content (bytes): Office document content
            file_name (str): Original file name (needed to preserve extension)

        Returns:
            bytes: PDF file content
        """
        try:
            logger.debug(f"Converting {file_name} to PDF via Gotenberg. ({self.request_id})")

            ext = splitext(file_name)[1].lower()
            mime_types = {
                k: EXT_TO_MIME.get(k, "application/octet-stream")
                for k in [".docx", ".pptx", ".xlsx"]
            }
            mime_type = mime_types.get(ext, "application/octet-stream")

            files = {
                "files": (file_name, content, mime_type),
            }

            response = await self.http_aclient.post(
                f"{self.gotenberg_url}/forms/libreoffice/convert",
                files=files,
            )
            response.raise_for_status()

            pdf_content = response.content
            logger.debug(
                f"Office to PDF conversion successful for {file_name}, PDF size: {len(pdf_content)} bytes. ({self.request_id})"
            )
            return pdf_content

        except httpx.HTTPError as e:
            logger.error(f"Gotenberg Office to PDF conversion failed for {file_name}: {repr(e)}")
            raise BadInputError(f"Failed to convert {file_name} to PDF using Gotenberg.") from e
        except Exception as e:
            logger.error(f"Office to PDF conversion error for {file_name}: {repr(e)}")
            raise BadInputError(f"Failed to convert {file_name} to PDF.") from e

    async def _convert_to_pdf(self, file_name: str, content: bytes) -> bytes:
        """
        Ensure content is in PDF format, converting if necessary.

        Args:
            file_name (str): File name
            content (bytes): File content

        Returns:
            bytes: PDF content

        Raises:
            BadInputError: If file type is not supported
        """
        ext = splitext(file_name)[1].lower()

        if ext == ".pdf":
            return content
        elif ext == ".html":
            return await self._convert_html_to_pdf_via_gotenberg(content)
        elif ext in [".docx", ".pptx", ".xlsx"]:
            return await self._convert_office_to_pdf_via_gotenberg(content, file_name)
        else:
            raise BadInputError(f"Unsupported file type for VLM OCR: {ext}")

    async def _convert_document_to_images_batched(
        self, file_name: str, content: bytes, batch_size: int
    ):
        """
        Convert document to images in batches for memory efficiency.
        This is a generator that yields batches of images.

        For non-PDF formats (HTML, Office docs), they are first converted to PDF via Gotenberg,
        then processed in batches.

        Args:
            file_name (str): File name
            content (bytes): File content
            batch_size (int): Number of pages per batch

        Returns:
            Async generator yielding tuple[int, list[bytes]]: (starting_page_index, list of image bytes)

        Raises:
            BadInputError: If file type is not supported or conversion fails
        """
        # Ensure content is in PDF format
        pdf_content = await self._convert_to_pdf(file_name, content)
        # Convert PDF to images in batches
        return self._convert_pdf_to_images_batched(pdf_content, batch_size)

    async def _ocr_image_with_vlm(self, image_bytes: bytes, page_num: int) -> str:
        """
        Perform OCR on an image using VLM via LMEngine.

        Args:
            image_bytes (bytes): Image bytes (JPEG format)
            page_num (int): Page number (for logging)

        Returns:
            str: Extracted text in Markdown format

        Raises:
            BadInputError: If VLM OCR fails
        """

        selected_model = await self._select_vlm_model()

        prompt = (
            "Extract all information from the main body of the document image and represent it in markdown format, "
            "ignoring headers and footers. Tables should be expressed in HTML format, formulas in the document "
            "should be represented using LaTeX format, and the parsing should be organized according to the reading order."
        )
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        messages = [
            ChatEntry.user(
                content=[
                    TextContent(text=prompt),
                    ImageContent(
                        image_url=ImageContentData(url=f"data:image/jpeg;base64,{base64_image}")
                    ),
                ]
            )
        ]

        logger.debug(
            f"Calling VLM OCR for page {page_num} with model {selected_model.id}. ({self.request_id})"
        )

        response = await self.lm_engine.chat_completion(
            model=selected_model.id,
            messages=messages,
            temperature=self.vlm_temperature,
            max_tokens=self.vlm_max_tokens,
        )

        if response and response.choices:
            extracted_text = response.choices[0].message.content.strip()
            logger.debug(
                f"VLM OCR completed for page {page_num}, extracted {len(extracted_text)} chars. ({self.request_id})"
            )
            return extracted_text

        logger.warning(f"Empty VLM response for page {page_num}. ({self.request_id})")
        return ""

    async def _parse_document(self, file_name: str, content: bytes) -> str:
        """
        Parse the document using VLM OCR with memory-efficient batch processing.

        Args:
            file_name (str): Original file name
            content (bytes): Binary content of the file

        Returns:
            str: The extracted Markdown content

        Raises:
            BadInputError: If parsing fails
        """
        size_mb = get_bytes_size_mb(content)

        logger.debug(
            f'Calling VLM OCR for file "{file_name}" with size {size_mb:.3f} MiB. ({self.request_id})'
        )

        try:
            all_results = []

            # Process document in batches
            total_pages_processed = 0
            async for start_idx, image_batch in await self._convert_document_to_images_batched(
                file_name, content, self.batch_size
            ):
                # Create tasks for this batch
                batch_tasks = [
                    self._ocr_image_with_vlm(img_bytes, start_idx + i + 1)
                    for i, img_bytes in enumerate(image_batch)
                ]

                # Wait for batch to complete before loading next batch
                batch_texts = await asyncio.gather(*batch_tasks)
                all_results.extend((start_idx + i, text) for i, text in enumerate(batch_texts))
                total_pages_processed += len(image_batch)

                logger.debug(
                    f'Processed {total_pages_processed} pages so far for "{file_name}". ({self.request_id})'
                )

            logger.info(
                f'Converted and processed "{file_name}" with {total_pages_processed} page images. ({self.request_id})'
            )

            # Sort by page index and extract texts
            all_results.sort(key=lambda x: x[0])
            page_texts = [text for _, text in all_results]

            # Assemble markdown with page breaks
            if self.page_break_placeholder:
                md_content = f"\n{self.page_break_placeholder}\n".join(page_texts)
            else:
                md_content = "\n\n".join(page_texts)
            return md_content

        except BadInputError:
            raise
        except Exception as e:
            logger.error(f'VLM OCR failed for file "{file_name}": {repr(e)} ({self.request_id})')
            raise BadInputError(f'Failed to process file "{file_name}" with VLM OCR.') from e

    async def document_to_markdown(self, file_name: str, content: bytes) -> str:
        """
        Converts a document to Markdown format using VLM OCR.

        Args:
            file_name (str): Original file name
            content (bytes): Binary content of the file

        Returns:
            str: Markdown content
        """
        return await self._parse_document(file_name, content)

    async def document_to_chunks(
        self, file_name: str, content: bytes, chunk_size: int, chunk_overlap: int
    ) -> list[Chunk]:
        """
        Converts a document to chunks using VLM OCR.

        Args:
            file_name (str): Original file name
            content (bytes): Binary content of the file
            chunk_size (int): The desired size of each chunk
            chunk_overlap (int): The number of tokens to overlap between chunks

        Returns:
            list[Chunk]: List of chunks
        """
        md_content = await self._parse_document(file_name, content)

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
