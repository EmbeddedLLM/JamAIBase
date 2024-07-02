import re
import sys
from os.path import join, splitext
from tempfile import TemporaryDirectory

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents.base import Document
from loguru import logger
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from jamaibase.protocol import Chunk, SplitChunksRequest
from owl.docio import DocIOAPIFileLoader
from owl.unstructuredio import UnstructuredAPIFileLoader


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    docio_url: str = "http://docio:6979/api/docio"
    unstructuredio_url: str = "http://unstructuredio:6989"
    unstructuredio_api_key: SecretStr = "ellm"

    @property
    def unstructuredio_api_key_plain(self):
        return self.unstructuredio_api_key.get_secret_value()


# build a table mapping all non-printable characters to None
NOPRINT_TRANS_TABLE = {
    i: None for i in range(0, sys.maxunicode + 1) if not chr(i).isprintable() and chr(i) != "\n"
}

config = Config()
logger.info(f"Loaders config: {config}")


def make_printable(s: str) -> str:
    """
    Replace non-printable characters in a string using
    `translate()` that removes characters that map to None.

    # https://stackoverflow.com/a/54451873
    """
    return s.translate(NOPRINT_TRANS_TABLE)


def load_file(file_name: str, content: bytes) -> list[Chunk]:
    ext = splitext(file_name)[1].lower()
    with TemporaryDirectory() as tmp_dir_path:
        tmp_path = join(tmp_dir_path, f"tmpfile{ext}")
        with open(tmp_path, "wb") as tmp:
            tmp.write(content)
            tmp.flush()
        logger.debug(f"Loading from temporary file: {tmp_path}")

        if ext in (".txt", ".md", ".pdf", ".csv"):
            loader = DocIOAPIFileLoader(tmp_path, config.docio_url)
            documents = loader.load()
            logger.debug("File '{file_name}' loaded: {docs}", file_name=file_name, docs=documents)
        elif ext in (".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"):
            documents = UnstructuredAPIFileLoader(
                tmp_path,
                url=config.unstructuredio_url,
                api_key=config.unstructuredio_api_key_plain,
                mode="paged",
            ).load()
            logger.debug("File '{file_name}' loaded: {docs}", file_name=file_name, docs=documents)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
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
