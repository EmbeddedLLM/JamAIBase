import re
import sys
from os.path import join, splitext
from tempfile import TemporaryDirectory

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents.base import Document
from loguru import logger

from owl.configs.manager import ENV_CONFIG
from owl.docio import DocIOAPIFileLoader
from owl.protocol import Chunk, SplitChunksParams, SplitChunksRequest
from owl.unstructuredio import UnstructuredAPIFileLoader

# build a table mapping all non-printable characters to None
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


def format_chunks(documents: list[Document], file_name: str) -> list[Chunk]:
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


async def load_file(
    file_name: str, content: bytes, chunk_size: int, chunk_overlap: int
) -> list[Chunk]:
    """
    Asynchronously loads and processes a file, converting its content into a list of Chunk objects.

    Args:
        file_name (str): The name of the file to be loaded.
        content (bytes): The binary content of the file.
        chunk_size (int): The desired size of each chunk.
        chunk_overlap (int): The amount of overlap between chunks.

    Returns:
        list[Chunk]: A list of Chunk objects representing the processed file content.

    Raises:
        ValueError: If the file type is not supported.
    """

    ext = splitext(file_name)[1].lower()
    with TemporaryDirectory() as tmp_dir_path:
        tmp_path = join(tmp_dir_path, f"tmpfile{ext}")
        with open(tmp_path, "wb") as tmp:
            tmp.write(content)
            tmp.flush()
        logger.debug(f"Loading from temporary file: {tmp_path}")

        if ext in (".csv", ".tsv", ".json", ".jsonl"):
            loader = DocIOAPIFileLoader(tmp_path, ENV_CONFIG.docio_url)
            documents = loader.load()
            logger.debug("File '{file_name}' loaded: {docs}", file_name=file_name, docs=documents)

            chunks = format_chunks(documents, file_name)

            if ext == ".json":
                chunks = split_chunks(
                    SplitChunksRequest(
                        chunks=chunks,
                        params=SplitChunksParams(
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                        ),
                    )
                )

        elif ext in (".html", ".xml", ".pptx", ".ppt", ".xlsx", ".xls", ".docx", ".doc"):
            loader = UnstructuredAPIFileLoader(
                tmp_path,
                url=ENV_CONFIG.unstructuredio_url,
                api_key=ENV_CONFIG.unstructuredio_api_key_plain,
                mode="paged",
                xml_keep_tags=True,
            )
            documents = await loader.aload()
            logger.debug("File '{file_name}' loaded: {docs}", file_name=file_name, docs=documents)

            chunks = format_chunks(documents, file_name)

            chunks = split_chunks(
                SplitChunksRequest(
                    chunks=chunks,
                    params=SplitChunksParams(
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                    ),
                )
            )

        elif ext in (".md", ".txt"):
            loader = UnstructuredAPIFileLoader(
                tmp_path,
                url=ENV_CONFIG.unstructuredio_url,
                api_key=ENV_CONFIG.unstructuredio_api_key_plain,
                mode="elements",
                chunking_strategy="by_title",
                max_characters=chunk_size,
                overlap=chunk_overlap,
            )
            documents = await loader.aload()
            logger.debug("File '{file_name}' loaded: {docs}", file_name=file_name, docs=documents)

            chunks = format_chunks(documents, file_name)

        elif ext == ".pdf":
            logger.info(f"pdf file: {file_name}")
            loader = UnstructuredAPIFileLoader(
                tmp_path,
                url=ENV_CONFIG.unstructuredio_url,
                api_key=ENV_CONFIG.unstructuredio_api_key_plain,
                mode="elements",
                strategy="hi_res",
                chunking_strategy="by_title",
                max_characters=chunk_size,
                overlap=chunk_overlap,
                multipage_sections=False,  # respect page boundaries
                include_page_breaks=True,
            )
            documents = await loader.aload()
            logger.debug("File '{file_name}' loaded: {docs}", file_name=file_name, docs=documents)
            logger.info(f"Load documents: {documents}")

            chunks = format_chunks(documents, file_name)

            chunks = combine_table_chunks(chunks=chunks)

        else:
            raise ValueError(f"Unsupported file type: {ext}")

    return chunks


def combine_table_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Combines chunks identified as parts of a table into a single chunk.

    This function iterates through the chunks and identifies consecutive chunks that
    belong to the same table based on the presence of "text_as_html" and "is_continuation"
    metadata flags. It then merges these chunks into a single chunk, preserving the
    table's HTML structure.

    Args:
        chunks (List[Chunk]): A list of Chunk objects.

    Returns:
        List[Chunk]: A list of Chunk objects with table chunks combined.
    """
    table_chunk_idx_groups = {}
    current_table_start_idx = 0
    for i, chunk in enumerate(chunks):
        if "text_as_html" in chunk.metadata and chunk.metadata.get("is_continuation", False):
            table_chunk_idx_groups[current_table_start_idx].append(i)
        elif "text_as_html" in chunk.metadata:
            current_table_start_idx = i
            table_chunk_idx_groups[current_table_start_idx] = [current_table_start_idx]
        chunk.metadata.pop("orig_elements", None)

    table_indexes = table_chunk_idx_groups.keys()
    processed_chunks = []
    current_table_start_idx = 0
    current_table_end_idx = 0
    table_chunk = Chunk(text="")
    for i, chunk in enumerate(chunks):
        if i in table_indexes:
            current_table_start_idx = i
            current_table_end_idx = table_chunk_idx_groups[i][-1]
            table_chunk = Chunk(
                text=chunk.metadata.get("text_as_html", chunk.text),
                title=chunk.title,
                page=chunk.page,
                file_name=chunk.file_name,
                file_path=chunk.file_path,
                metadata=chunk.metadata.copy(),
            )
            table_chunk.metadata.pop("text_as_html", None)
            if current_table_end_idx == current_table_start_idx:
                processed_chunks.append(table_chunk)
        elif i > current_table_start_idx and i <= current_table_end_idx:
            table_chunk.text += chunk.metadata.get("text_as_html", chunk.text)
            if i == current_table_end_idx:
                processed_chunks.append(table_chunk)
        else:
            processed_chunks.append(chunk)

    return processed_chunks


def split_chunks(request: SplitChunksRequest) -> list[Chunk]:
    _id = request.id
    logger.info(f"{_id} - Split documents request: {request.str_trunc()}")
    if request.params.method == "RecursiveCharacterTextSplitter":
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=request.params.chunk_size,
            chunk_overlap=request.params.chunk_overlap,
        )
    else:
        raise ValueError(f"Split method not supported: {request.params.method}")

    try:
        chunks = []
        for chunk in request.chunks:
            # Module-level functions store compiled object in a cache
            text_tables_parts = re.split(r"(<TABLE>.*?</TABLE>)", chunk.text, flags=re.DOTALL)
            table_split_texts = [part for part in text_tables_parts if part]
            for table_split_text in table_split_texts:
                if table_split_text.startswith("<TABLE>") and table_split_text.endswith(
                    "</TABLE>"
                ):
                    chunks.append(chunk)
                else:
                    chunks += [
                        Chunk(
                            text=d.page_content,
                            title=chunk.title,
                            page=chunk.page,
                            file_name=chunk.file_name,
                            file_path=chunk.file_name,
                            metadata=chunk.metadata,
                        )
                        for d in text_splitter.split_documents(
                            [Document(page_content=chunk.text, metadata={})]
                        )
                    ]
        logger.info(
            f"{_id} - {len(request.chunks):,d} chunks split into {len(chunks):,d} chunks.",
        )
        return chunks
    except Exception:
        logger.exception("Failed to split chunks.")
        raise
