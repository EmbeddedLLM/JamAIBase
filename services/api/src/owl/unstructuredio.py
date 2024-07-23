from abc import ABC, abstractmethod
from typing import IO, Any, Callable, Iterator

from langchain_community.document_loaders.base import BaseLoader
from langchain_core.documents import Document
from loguru import logger
from unstructured_client import UnstructuredClient
from unstructured_client.models import shared
from unstructured_client.models.errors import SDKError


class UnstructuredBaseLoader(BaseLoader, ABC):
    """Base Loader that uses `Unstructured`."""

    def __init__(
        self,
        mode: str = "single",
        post_processors: list[Callable] | None = None,
        **unstructured_kwargs: Any,
    ):
        """Initialize with file path."""
        # try:
        #     import unstructured  # noqa:F401
        # except ImportError:
        #     raise ValueError(
        #         "unstructured package not found, please install it with "
        #         "`pip install unstructured`"
        #     )
        _valid_modes = {"single", "elements", "paged"}
        if mode not in _valid_modes:
            raise ValueError(f"Got {mode} for `mode`, but should be one of `{_valid_modes}`")
        self.mode = mode

        # if not satisfies_min_unstructured_version("0.5.4"):
        #     if "strategy" in unstructured_kwargs:
        #         unstructured_kwargs.pop("strategy")

        self.unstructured_kwargs = unstructured_kwargs
        self.post_processors = post_processors or []

    @abstractmethod
    def _get_elements(self) -> list:
        """Get elements."""

    @abstractmethod
    def _get_metadata(self) -> dict:
        """Get metadata."""

    def _post_process_elements(self, elements: list) -> list:
        """Applies post processing functions to extracted unstructured elements.
        Post processing functions are str -> str callables are passed
        in using the post_processors kwarg when the loader is instantiated."""
        for element in elements:
            for post_processor in self.post_processors:
                element.apply(post_processor)
        return elements

    def lazy_load(self) -> Iterator[Document]:
        """Load file."""
        elements = self._get_elements()
        self._post_process_elements(elements)
        if self.mode == "elements":
            for element in elements:
                metadata = element["metadata"]
                metadata["page"] = metadata.get("page_number", 1)
                # NOTE(MthwRobinson) - the attribute check is for backward compatibility
                # with unstructured<0.4.9. The metadata attributed was added in 0.4.9.
                if hasattr(element, "metadata"):
                    metadata.update(element["metadata"])
                if hasattr(element, "type"):
                    metadata["type"] = element["NarrativeText"]
                yield Document(page_content=str(element["text"]), metadata=metadata)
        elif self.mode == "paged":
            text_dict: dict[int, str] = {}
            meta_dict: dict[int, dict] = {}

            for idx, element in enumerate(elements):
                metadata = element["metadata"]
                if hasattr(element, "metadata"):
                    metadata.update(element["metadata"])
                page_number = metadata.get("page_number", 1)
                metadata["page"] = page_number

                # Check if this page_number already exists in docs_dict
                if page_number not in text_dict:
                    # If not, create new entry with initial text and metadata
                    text_dict[page_number] = element["text"] + "\n\n"
                    meta_dict[page_number] = metadata
                else:
                    # If exists, append to text and update the metadata
                    text_dict[page_number] += element["text"] + "\n\n"
                    meta_dict[page_number].update(metadata)

            # Convert the dict to a list of Document objects
            for key in text_dict.keys():
                yield Document(page_content=text_dict[key], metadata=meta_dict[key])
        elif self.mode == "single":
            metadata = self._get_metadata()
            text = "\n\n".join([el["text"] for el in elements])
            yield Document(page_content=text, metadata=metadata)
        else:
            raise ValueError(f"mode of {self.mode} not supported.")


def partition(
    filename: str,
    unstructuredio_client,
    **unstructured_kwargs: Any,
):
    languages = unstructured_kwargs.pop("languages", ["en", "cn"])

    with open(filename, "rb") as f:
        # Note that this currently only supports a single file
        files = shared.Files(
            content=f.read(),
            file_name=filename,
        )

    req = shared.PartitionParameters(
        files=files,
        # Other partition params
        languages=languages,
        **unstructured_kwargs,
    )

    try:
        resp = unstructuredio_client.general.partition(req)
        return resp.elements
    except SDKError as e:
        logger.error(f"UnstructuredIO SDK Error: {str(e)}")
    return []


class UnstructuredAPIFileLoader(UnstructuredBaseLoader):
    """Load files using `Unstructured`.

    Example:

    UnstructuredAPIFileLoader(
        "helloworld.txt",
        mode="single",
        url="http://unstructuredio:6989/general/v0/general",
        api_key="ellm",
        languages=["en", "cn"]
    )

    """

    def __init__(
        self,
        file_path: str | list[str],
        mode: str = "single",
        url="https://api.unstructured.io/general/v0/general",
        api_key: str = "ellm",
        **unstructured_kwargs: Any,
    ):
        """Initialize with file path."""
        self.file_path = file_path
        self.url = url
        self.api_key = api_key
        super().__init__(mode=mode, **unstructured_kwargs)

    def _get_elements(self) -> list:
        s = UnstructuredClient(server_url=self.url, api_key_auth=self.api_key)

        if isinstance(self.file_path, list):
            elements = []
            for file in self.file_path:
                elements.extend(
                    partition(filename=file, unstructuredio_client=s, **self.unstructured_kwargs)
                )
            return elements
        else:
            return partition(
                filename=self.file_path, unstructuredio_client=s, **self.unstructured_kwargs
            )

    def _get_metadata(self) -> dict:
        return {"source": self.file_path}


if __name__ == "__main__":
    filename = "clients/python/tests/docx/Recommendation Letter.docx"
    doc_loader = UnstructuredAPIFileLoader(
        filename,
        mode="single",
        url="http://localhost:6989/general/v0/general",
        api_key="ellm",
        languages=["en", "cn"],
    ).load()

    doc_loader = UnstructuredAPIFileLoader(
        filename,
        mode="paged",
        url="http://localhost:6989/general/v0/general",
        api_key="ellm",
        languages=["en", "cn"],
    ).load()

    doc_loader = UnstructuredAPIFileLoader(
        filename,
        mode="elements",
        url="http://localhost:6989/general/v0/general",
        api_key="ellm",
        languages=["en", "cn"],
    ).load()
