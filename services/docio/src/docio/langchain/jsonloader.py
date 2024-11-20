import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, Union

from langchain_community.document_loaders.base import BaseLoader
from langchain_core.documents import Document


class JSONLoader(BaseLoader):
    """Load a `JSON` file generically."""

    def __init__(
        self,
        file_path: Union[str, Path],
        content_key: Optional[str] = None,
        metadata_func: Optional[Callable[[Dict, Dict], Dict]] = None,
        text_content: bool = True,
        json_lines: bool = False,
    ):
        """Initialize the JSONLoader.

        Args:
            file_path (Union[str, Path]): The path to the JSON or JSON Lines file.
            content_key (str): The key to use to extract the content from
                the JSON if the result is a list of objects (dict).
                This should be a simple string key.
            metadata_func (Callable[Dict, Dict]): A function that takes in the JSON
                object and the default metadata and returns a dict of the updated metadata.
            text_content (bool): Boolean flag to indicate whether the content is in
                string format, default to True.
            json_lines (bool): Boolean flag to indicate whether the input is in
                JSON Lines format.
        """
        self.file_path = Path(file_path).resolve()
        self._content_key = content_key
        self._metadata_func = metadata_func
        self._text_content = text_content
        self._json_lines = json_lines

    def lazy_load(self) -> Iterator[Document]:
        """Load and return documents from the JSON file."""
        index = 0
        if self._json_lines:
            with self.file_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        for doc in self._parse(line, index):
                            yield doc
                            index += 1
        else:
            for doc in self._parse(self.file_path.read_text(encoding="utf-8"), index):
                yield doc
                index += 1

    def _parse(self, content: str, index: int) -> Iterator[Document]:
        """Convert given content to documents."""
        data = json.loads(content)

        # Perform some validation
        # This is not a perfect validation, but it should catch most cases
        # and prevent the user from getting a cryptic error later on.
        if self._content_key is not None:
            self._validate_content_key(data)
        if self._metadata_func is not None:
            self._validate_metadata_func(data)

        # If the data is a dictionary, treat it as a single document
        if isinstance(data, dict):
            text = self._get_text(sample=data)
            metadata = self._get_metadata(
                sample=data, source=str(self.file_path), seq_num=index + 1
            )
            yield Document(page_content=text, metadata=metadata)
        else:
            for i, sample in enumerate(data, index + 1):
                text = self._get_text(sample=sample)
                metadata = self._get_metadata(sample=sample, source=str(self.file_path), seq_num=i)
                yield Document(page_content=text, metadata=metadata)

    def _get_text(self, sample: Any) -> str:
        """Convert sample to string format"""
        if self._content_key is not None:
            content = sample[self._content_key]
        else:
            content = sample

        if self._text_content and not isinstance(content, str):
            raise ValueError(
                f"Expected page_content is string, got {type(content)} instead. \
                    Set `text_content=False` if the desired input for \
                    `page_content` is not a string"
            )

        # In case the text is None, set it to an empty string
        elif isinstance(content, str):
            return content
        elif isinstance(content, dict):
            return json.dumps(content, ensure_ascii=False) if content else ""
        else:
            return str(content) if content is not None else ""

    def _get_metadata(self, sample: Dict[str, Any], **additional_fields: Any) -> Dict[str, Any]:
        """
        Return a metadata dictionary base on the existence of metadata_func
        :param sample: single data payload
        :param additional_fields: key-word arguments to be added as metadata values
        :return:
        """
        if self._metadata_func is not None:
            return self._metadata_func(sample, additional_fields)
        else:
            return additional_fields

    def _validate_content_key(self, data: Any) -> None:
        """Check if a content key is valid"""

        sample = data[0] if isinstance(data, list) else data
        if not isinstance(sample, dict):
            raise ValueError(
                f"Expected the JSON to result in a list of objects (dict), \
                    so sample must be a dict but got `{type(sample)}`"
            )

        if sample.get(self._content_key) is None:
            raise ValueError(
                f"Expected the JSON to result in a list of objects (dict) \
                    with the key `{self._content_key}`"
            )

    def _validate_metadata_func(self, data: Any) -> None:
        """Check if the metadata_func output is valid"""

        sample = data[0] if isinstance(data, list) else data
        if self._metadata_func is not None:
            sample_metadata = self._metadata_func(sample, {})
            if not isinstance(sample_metadata, dict):
                raise ValueError(
                    f"Expected the metadata_func to return a dict but got \
                        `{type(sample_metadata)}`"
                )
