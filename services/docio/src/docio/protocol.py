from pydantic import BaseModel


class Document(BaseModel):
    """Document class for compatibility with LangChain."""

    page_content: str
    metadata: dict = {}
