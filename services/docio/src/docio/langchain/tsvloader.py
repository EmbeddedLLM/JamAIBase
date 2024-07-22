import csv
from tempfile import TemporaryDirectory
from os.path import join, splitext
from loguru import logger
import pandas as pd
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

from langchain_core.documents import Document
from langchain_community.document_loaders.base import BaseLoader
from langchain_community.document_loaders.helpers import detect_file_encodings


class TSVLoader(BaseLoader):
    """
    Load a TSV file into a list of Documents.

    Each document represents one row of the TSV file. Every row is converted into a
    key/value pair and outputted to a new line in the document's page_content.

    The source for each document loaded from the TSV file is set to the value of the
    `file_path` argument for all documents by default. You can override this by setting
    the `source_column` argument to the name of a column in the TSV file. The source of
    each document will then be set to the value of the column with the name specified in
    `source_column`.

    Output Example:
        .. code-block:: txt

            column1: value1
            column2: value2
            column3: value3
    """

    def __init__(
        self,
        file_path: Union[str, Path],
        source_column: Optional[str] = None,
        metadata_columns: Sequence[str] = (),
        csv_args: Optional[Dict] = None,
        encoding: Optional[str] = None,
        autodetect_encoding: bool = False,
    ):
        """
        Initialize the TSVLoader.

        Args:
            file_path: The path to the TSV file.
            source_column: The name of the column in the TSV file to use as the source.
              Optional. Defaults to None.
            metadata_columns: A sequence of column names to use as metadata. Optional.
            csv_args: A dictionary of arguments to pass to the csv.DictReader.
              Optional. Defaults to None.
            encoding: The encoding of the TSV file. Optional. Defaults to None.
            autodetect_encoding: Whether to try to autodetect the file encoding.
        """
        self.file_path = file_path
        self.source_column = source_column
        self.metadata_columns = metadata_columns
        self.encoding = encoding
        self.csv_args = csv_args or {}
        self.autodetect_encoding = autodetect_encoding

    def lazy_load(self) -> Iterator[Document]:
        """
        Lazily load documents from the TSV file.

        Yields:
            Document: A document representing a row in the TSV file.
        """
        try:
            with open(self.file_path, newline="", encoding=self.encoding) as csvfile:
                yield from self.__read_file(csvfile)
        except UnicodeDecodeError as e:
            if self.autodetect_encoding:
                detected_encodings = detect_file_encodings(self.file_path)
                for encoding in detected_encodings:
                    try:
                        with open(
                            self.file_path, newline="", encoding=encoding.encoding
                        ) as csvfile:
                            yield from self.__read_file(csvfile)
                            break
                    except UnicodeDecodeError:
                        continue
            else:
                raise RuntimeError(f"Error loading {self.file_path}") from e
        except Exception as e:
            raise RuntimeError(f"Error loading {self.file_path}") from e

    def __read_file(self, tsvfile: TextIOWrapper) -> Iterator[Document]:
        """
        Read the TSV file and convert each row into a Document.

        Args:
            tsvfile: A file object representing the TSV file.

        Yields:
            Document: A document representing a row in the TSV file.
        """
        with TemporaryDirectory() as tmp_dir_path:
            tmp_csv_path = join(tmp_dir_path, "tmpfile.csv")
            content = pd.read_csv(tsvfile, sep="\t")
            content.to_csv(tmp_csv_path, index=False)

            logger.debug(f"Loading from temporary file: {tmp_csv_path}")

            with open(tmp_csv_path, "r") as tmp_csv:
                csv_reader = csv.DictReader(tmp_csv, **self.csv_args)

                for i, row in enumerate(csv_reader):
                    try:
                        source = (
                            row[self.source_column]
                            if self.source_column is not None
                            else str(self.file_path)
                        )
                    except KeyError:
                        raise ValueError(
                            f"Source column '{self.source_column}' not found in TSV file."
                        )
                    content = "\n".join(
                        f"{k.strip()}: {v.strip() if v is not None else v}"
                        for k, v in row.items()
                        if k not in self.metadata_columns
                    )
                    metadata = {"source": source, "row": i}
                    for col in self.metadata_columns:
                        try:
                            metadata[col] = row[col]
                        except KeyError:
                            raise ValueError(f"Metadata column '{col}' not found in TSV file.")
                    yield Document(page_content=content, metadata=metadata)
