# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

- Each section is broken into:

  - `ADDED`: New features.
  - `CHANGED / FIXED`: Changes in existing functionality, or any bug fixes. This can include breaking changes for v0.x releases.
  - `DEPRECATED`: Soon-to-be removed features.
  - `REMOVED`: Removed features.
  - `SECURITY`: Anything related to vulnerabilities.

- The version number mentioned here refers to the cloud version. For each release, all SDKs will have the same major and minor version, but their patch version may differ. For example, latest Python SDK might be `v0.2.0` whereas TS SDK might be `v0.2.1`, but both will be compatible with release `v0.2`.

## [v0.2] - 2024-07-23

### ADDED

Python SDK - jamaibase

- New method for generating embeddings: `generate_embeddings()`
- New methods for importing and exporting table data via CSV (comma-separated) or TSV (tab-separated)
  - `import_table_data()`
  - `export_table_data()`
- `get_conversation_thread` method now accepts 2 additional optional parameters for filtering by `row_id` and specifying whether to include the row in the returned thread.
- `list_table_rows()` and `get_table_row()` methods and `hybrid_search()` request body now accepts 2 additional arguments:
  - `float_decimals` (int, optional): Number of decimals for float values. Defaults to 0 (no rounding).
  - `vec_decimals` (int, optional): Number of decimals for vectors. Defaults to 0 (no rounding).
- Implement `utils.io.csv_to_df()` and `utils.io.df_to_csv()` for CSV reading and exporting.

TS/JS SDK - jamaibase

- New method for generating embeddings: `generateEmbeddings()`
- New methods for importing and exporting table data via CSV (comma-separated) or TSV (tab-separated)
  - `importTableData()`
  - `exportTableData()`
- `listRows()` and `getRow()` methods and `hybridSearch()` request body now accepts 2 additional arguments:
  - `float_decimals` (int, optional): Number of decimals for float values. Defaults to 0 (no rounding).
  - `vec_decimals` (int, optional): Number of decimals for vectors. Defaults to 0 (no rounding).
- Add `search_query` param in `listRows()`

`Embeddings` endpoint

- Get a vector representation of a given input that can be easily consumed by machine learning models and algorithms. Note that the vectors are NOT normalized. Similar to OpenAI's embeddings endpoint.
- Resolves #86

Generative Table

- Table data import and export via CSV (comma-separated) or TSV (tab-separated) file. Resolves #98
- Table import and export via Parquet file.
- Row deletion now accepts a list of row IDs.
- Added ability to shortlist rows via Full-Text-Search (FTS) when listing table rows. Resolves #156
- Full row data logging when error occurred in table rows add or update. Resolves #140.
- Handle streaming exception by setting `ChatCompletionChunk.finish_reason` as "error". Also applies to chat endpoint.

UI

- Added button to delete projects
- Added title to dashboard
- Added config for building frontend into single-page application
- Added dialogue to import files and match columns
- Setup frontend auth test for future tests

CI/CD

- Added api and docio windows pyinstaller compilation CI. Detect missing DLL. Fixes #107, #108 .

TS/JS Client

- Added exportTableData method to export table data in csv and tsv

### CHANGED / FIXED

Python SDK - jamaibase

- `ChatRequest`
  - `messages` is now a required parameter and no longer defaults to empty list. It must also be at least length 1.
  - `model` now defaults to empty string.
- `table_type` can now be a regular string.
- `utils.io` has been cleanup up, unused methods removed.
- Bug fixes
  - Fixed type hinting
  - Fixed the description of `limit` in `SearchRequest`, fixes #155
  - File upload didn't include auth headers
  - LLM: Handle cases where chat endpoint returns `None` as `content`
- Removed dependencies:
  - `pyarrow`
  - `sqlmodel`
  - `tqdm`
  - `uuid-utils`
  - `uuid7`

Generative Table

- Conversation Chat table generation config can now be modified. Previously only Agent Chat table can be modified. Resolves #188
- When creating a new table, adding a new column, or updating generation config:
  - An LLM model will be assigned dynamically if not specified in its `gen_config`. Resolves #190, #251.
  - Check existence of Knowledge Table. Resolves #142, #143, #251.
  - Check availability of reranking model. Resolves #143, #251.
- Allow table names with "." (dot).
- Vector search
  - Change default metric to `cosine`; fixes #110
  - Reduce default `refine_factor` from 50 to 20 to speed up search
- Hybrid search
  - Only do FTS once instead of looping through indexed col one by one (Lance/Tantivy FTS unable to specify search columns); fixes #138
  - Added Reciprocal Rank Fusion (RRF) to merge FTS and VS search results without using reranker; fixes #112
  - Added retry to search query, to handle possible failure case during FTS index build; fixes #111
  - Removed hybrid search with linear score combination (only uses RRF if without reranker)
  - Query rewrite previously silently replaced user-provided system message with a generic message.
- Improved handling of mid-stream error
  - Any errors encountered mid-stream will yield a completion chunk with error details as `text` and "error" as `finish_reason`
  - Errored table column will have its cell value set to `None`
- Missing columns in table row data are filled with `None`. It used to cause row add failure.
- Retrieval Augmented Generation (RAG) is now more robust against missing column data.
- Remap internal `ValidationError` to `RequestValidationError`. Fixes #162
- Improved handling of Timeout errors
- Increase robustness against missing Lance tables during table listing
- More aggressive Lance DB version cleanup: cleanup versions older than 5 minutes by default. Fixes #163
- Added more tests
- Bug fixes
  - If RAG query contains certain keyword in uppercase, it may be interpreted as term search and may lead to `SyntaxError`. It is now escaped. Fixes #187
  - Streaming response was not returning token usage. This also applies to chat endpoint.
  - Reference chunk `object` field value was incorrectly set as "chat.references" instead of "gen_table.references".
  - Column reordering may produce tables with invalid generation config. Fixes #135
  - Reindexing datetime recorded into the table metadata should be when the operation was started not when it has ended.
  - FTS search may fail if there isn't an index, in this case we will force reindex.
  - Generation config source column check should not include the column itself.
  - Stricter generation config validation.
  - GenExecutor may hang when provided with columns that do not exist in the table.
  - When regenerating middle rows of a Chat Table, the chat history should not include "future" rows.

UI

- UI design changes
- Refactor UI code
- Standardize & improve UI errors, including validation errors
- Fix issue where incorrect models would show in select menu
- Fix issue when navigating table tabs quickly, resulting in duplicate fetch requests
- Fix missing project ID error when performing certain actions
- Fix multiple bugs related to infinite scrolling
- Organization settings
  - Obfuscate org secrets
  - Allow org members to view jamai keys
  - Fix edge case where organization team page would fail to load
- User settings
  - Fix change password button not working
- Generative Tables
  - Display column dtype on the header
  - Improve file upload status component
  - Improve UX for renaming table columns
  - Fix pagination arrows not working in large tables
  - Fix tables page not redirecting after switching organizations
  - Fix incorrect project ID error when queueing multiple file uploads
  - Fix unnecessary data invalidation during upload

Backend - owl (API server)

- Support document upload types:
  - csv, tsv, jsonl
    - docio loader (split line by lines)
  - json
    - docio loader, recursive character text splitter
  - html, xml, pptx, ppt, xlsx, xls, docs, doc
    - unstructured-io loader, recursive character text splitter
  - md, txt
    - unstructured-io loader with elements chunker
  - pdf: digital/scanned/mixed
    - docio loader and unstructured-io loader with (elements) `fast`, `ocr_only` and `hi_res` chunkers
    - enabled `split_pdf_pages` setting to speed up partitioning
    - calculate recall to differenciate between digital pdf (recall > 0.9) and scanned/mixed pdf
    - digital pdf
      - `fast` chunks and `hi_res` table only chunks
    - scanned/mixed pdf
      - `ocr_only` chunks and `hi_res` table only chunks
- Refactor cache into `Cache` class that abstracts away `redis`
- Refactor LLM logic into `LLMEngine` class.
- Rename `owl.utils.get_api_key` -> `owl.utils.filter_external_api_key`
- Limit the number of rows that can be added at one time to 100. Fixes #157
- Chat completion
  - Search query rewrite max token increased from 256 to 512.
  - If context length is exceeded and stream is False, completion usage is set to `None`.
  - Fix Llama3 generation bug due to incorrect default `stop` param.
- Env var
  - `owl_redis_purge` changed to `owl_cache_purge`
  - `owl_remove_version_older_than_days` changed to `owl_remove_version_older_than_mins`
- Logging
  - Add logging into exception handlers
  - Suppress `openmeter` logs
  - Improve exception logging
  - Reduce verbosity of regular logs
- Bug fixes:
  - File loading extension checking was case-sensitive. Fixes #164
  - Windows: Temporary file must be closed before it can be accessed by other processes or nested contexts. Change to `TemporaryDirectory` instead. Fixes #125
  - Better validation error message
  - Removed `openai/gpt-4-vision-preview`
  - Windows: StreamResponse from FastAPI accumulates all SSE before yielding everything all at once to the client Fixes #145
  - Enabled scanned pdf upload. Fixes #131
- Dependencies
  - Support forked version of `unstructured-client==0.24.1`, changed nest-asyncio to ThreadPool, fixed the conflict with uvloop
  - Added `tenacity`, `pandas`
  - Bumped dependency versions

Backend - docio (PDF loader)

- Bug fixes:
  - Windows: Temporary file must be closed before it can be accessed by other processes or nested contexts. Change to `TemporaryDirectory` instead. Fixes #125
  - Windows: StreamResponse from FastAPI accumulates all SSE before yielding everything all at once to the client Fixes #145

Backend - Admin (cloud)

- Improve insufficient credit error message: include quota/usage type in the message
- Storage usage update is now a background process; fixes #87
- Allow dot in the middle for project name and organization name.
- Update `models.json` in `set_model_config()`
- Billing: Don't include Lance version directories in storage usage computation
- Bug fixes
  - Org update previously failed due to incorrect default param for `db_storage_gb` and `file_storage_gb`
  - User invite email validation is now case-insensitive
  - If self-hosted model is not found in price list, return zero cost.

CI / CD / OSS

- Use our private Dragonfly container to avoid frequent timeouts
- Bug fixes
  - Cloud removal script
  - Docker Compose health checks (`curl` was removed from `unstructured-io/unstructured-api`)
  - Fixed CORS error when uploading files

Windows

- [FEAT] [Windows] [Tech Day] DocIO Windows Executable #107

Misc

- Error responses now have "object" field with value "error"
- Bug fix for cloud removal script
- Mask LLM generations during logging; fixes #96
- Added scripts
  - Update DB schema
  - Add credit to org
  - Update and rename quota reset script
- Sync `owl` version with `jamaibase`
- Documentation fix

## [v0.1] - 2024-06-03

This is our first release 🚀
