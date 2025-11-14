from pydantic import BaseModel, Field

from jamaibase.types.lm import (
    Chunk,
    RAGParams,
)


class VectorSearchRequest(RAGParams):
    id: str = Field(
        default="",
        description="Request ID for logging purposes.",
        examples=["018ed5f1-6399-71f7-86af-fc18d4a3e3f5"],
    )
    search_query: str = Field(description="Query used to retrieve items from the Knowledge Table.")


class VectorSearchResponse(BaseModel):
    object: str = Field(
        default="kb.search_response",
        description="Type of API response object.",
        examples=["kb.search_response"],
    )
    chunks: list[Chunk] = Field(
        default=[],
        description="A list of `Chunk`.",
        examples=[
            [
                Chunk(
                    text="The Name of the Title is Hope\n\n...",
                    title="The Name of the Title is Hope",
                    page=0,
                    file_name="sample_tables.pdf",
                    file_path="amagpt/sample_tables.pdf",
                    metadata={
                        "total_pages": 3,
                        "Author": "Ben Trovato",
                        "CreationDate": "D:20231031072817Z",
                        "Creator": "LaTeX with acmart 2023/10/14 v1.92 Typesetting articles for the Association for Computing Machinery and hyperref 2023-07-08 v7.01b Hypertext links for LaTeX",
                        "Keywords": "Image Captioning, Deep Learning",
                        "ModDate": "D:20231031073146Z",
                        "PTEX.Fullbanner": "This is pdfTeX, Version 3.141592653-2.6-1.40.25 (TeX Live 2023) kpathsea version 6.3.5",
                        "Producer": "3-Heights(TM) PDF Security Shell 4.8.25.2 (http://www.pdf-tools.com) / pdcat (www.pdf-tools.com)",
                        "Trapped": "False",
                    },
                )
            ]
        ],
    )
