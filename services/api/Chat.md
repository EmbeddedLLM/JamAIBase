# JamAI Chat

# Chat Message Format

A user message can include:

- Text
- Images (zero or more)
- Audio (zero or more)
- Document (zero or more)

User can also request for RAG to be used so that the model can get context from a Knowledge Table. In this case, the assistant's reply will have references attached.

## RAG References

RAG references contain the following data:

- Search query (text sentence) used to retrieve the chunks/data
- A list of chunks/data, each containing:
  - Title: Text sentence
  - Text: Text sentences/paragraphs
  - Page: Integer or null
  - Chunk ID: UUID text-string, can be empty
  - Context:
    - Any arbitrary number of <col-name>: <col-content>
  - Metadata:
    - Any arbitrary number of <score-name>: <match-score>
    - Project ID
    - Knowledge Table ID (can be used together with Project ID to display a hyperlink to the user)

For example:

```json
{
  "search_query": "pet rabbit name",
  "chunks": [
    {
      "title": "Pet names",
      "text": "My rabbit's name is Latte.",
      "page": 1,
      "chunk_id": "066a8a49-6dcc-764f-8000-a7bfc34f863c",
      "context": {
        "Colour": "White",
        "Weight": "1 kg"
      },
      "metadata": {
        "bm25-score": 1.5,
        "rrf-score": 0.8,
        "project_id": "proj_f37ff1cf46aaa453143ca50b",
        "table_id": "pet-names"
      }
    },
    {
      "title": "Pet names",
      "text": "My deer's name is Daisy.",
      "page": null,
      "chunk_id": "066a8a49-6dcc-764f-8000-a7bfc34f864c",
      "context": {
        "Colour": "Brown",
        "Weight": "8 kg"
      },
      "metadata": {
        "bm25-score": 1.95,
        "rrf-score": 0.6,
        "project_id": "proj_f37ff1cf46aaa453143ca50b",
        "table_id": "pet-names"
      }
    }
  ]
}
```
