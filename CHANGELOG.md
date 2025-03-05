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

## [Unreleased]

## [v0.4.1] (2025-02-26)

### CHANGED / FIXED

Python SDK - jamaibase

- Remove pydub dependency for SDK `v0.4.1` #488

- GenTable
  - Bug fixes
    - Fix csv export columns ordering #487
    - Fix `search_query` rows return limit #482

## [v0.4] (2025-02-12)

### ADDED

Python SDK - jamaibase

- Add `CodeGenConfig` for python code execution #446

TS SDK - jamaibase

- Add `CodeGenConfigSchema` for code execution #446
- Support audio data type

UI

- Support chat mode multiturn option in add column and column resize #451
- Support `audio` data type #457

Backend - owl (API server)

- GenTable
  - Support `audio` input column and data type #443
  - Support python code execution column #446
  - **Breaking**: Add `Page` column to knowledge table #464
- LLM
  - Support function calling # 435
  - Support DeepSeek models #466
- Billing
  - Include background tasks for processing billing events #462
- Auth
  - Support specific user role in organization invite #446
  - Include background tasks for setting project updated at datetime #462
- Handle and allow setting of file upload size limits for `embed file`, `image` and `audio` file types #443

CI/CD

- Added a new CI workflow for cloud environments in`.github/workflows/ci.cloud.yml` #440
- Add dummy test job to pass status checks if skipped #468
- Added a `check_changes` job to the CI workflows to conditionally run SDK tests based on changes. #462

### CHANGES / FIXED

Python SDK - jamaibase

TS SDK - jamaibase

- Update the `uploadFile` method in `index.ts` to remove the trailing slash from the API endpoint #462
- Update client and node enviroment conflict in file upload

UI

- Remove unnecessary load function rerunning on client navigation #454
- Add more export options with confirmation #459
- Obfuscated external keys and credit values for non-admin users in the `+layout.server.ts` to enhance security and privacy #459
- Update `FileSelect.svelte` and `NewRow.svelte` to remove trailing slashes from the file upload API endpoint #462
- Bug fixes:
  - Fix chat table scrollbar not showing issue #459
  - Fix keyboard navigation #459
  - Fix inappropriate model not showing issue in knowledge table column settings #459

Backend - owl (API server)

- GenTable
  - **Breaking**: Change `file` data type to `image` data type #460
- LLM
  - Handle usage tracking and improve error handling #462
  - Bug fixes
    - Fix model config embedding size #441
    - Fix bug with default model choosing invalid models #442
    - Fix regen sequences issue after columns reordering #455

CI/CD

- Dockerfile: Added `ffmpeg` installation for audio processing. #443
- Dependency Updates:
  - Set `litellm` to version `1.50.0` #443
  - Add `pydub` as a dependency for audio processing #443

### REMOVED

## [v0.3] (2024-11-20)

### ADDED

Python SDK - jamaibase

- Added `missing_ok` to all delete methods
- Added Organization Admin API via `admin.organization` methods
- Added Backend Admin API via `admin.backend` methods
- Added Templates API via `template` methods
- Added File API via `file` methods
- Added `GenConfig` protocols: `LLMGenConfig` and `EmbedGenConfig`
- `list_tables` method:
  - Added `parent_id` param. Resolved #252
  - Added `search_query` param to search table IDs
- Added `timeout` and `file_upload_timeout` parameters in client init method.
- Added PAT methods

TS SDK - jamaibase

- Added `create_child_table` method to create conversation table as a child table. Resolves #283
- Grouped methods into `table`, `llm`, `file`, `template`

UI

- Electron App
  - Added script for compiling JamAIBase Electron App.
  - Added detailed instructions for building and running the JamAIBase Electron App in the `services/app/README.md`.
  - Added Electron main process initialization script.
  - Added Electron Forge configuration for packaging and making redistributables.
  - Added `.gitignore` entries for Electron build artifacts.

Backend - owl (API server)

- Projects are now available in OSS
- GenTable
  - **Breaking**: Added `version` and `meta` to table metadata and associated migration script
  - Added ability to turn any column into multi-turn chat via the `multi_turn` parameter in `LLMGenConfig`
  - Added table ID search when listing tables
  - Added `GenConfig` protocols: `LLMGenConfig` and `EmbedGenConfig`
  - Added default prompts for table creation and column add
  - Write rows to table with dynamically decided batch size, capped at `max_write_batch_size` that speeds up file uploading. Resolves #225
  - Added ability to sort by table attribute or row column in ascending or descending order when listing tables or rows
  - Support file type input column. #120
    - image file extensions: `jpeg/jpg`, `png`, `webp`, `gif`
    - restriction: single image file per output completion
- Templates gallery
- File API
- GenExecutor
  - Added regeneration mode: `run_all`, `run_before`, `run_selected` and `run_after`. #221
- LLM
  - OSS model list patch API & Cloud per-org model list API
  - Internal-only models
  - Include `name` into `EmbeddingModelConfig` and `RerankingModelConfig`
  - Added "openai/gpt-4o-mini", "openai/gpt-4-turbo", "together_ai/meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo"
  - Added model priority for default assignment
- Admin
  - Added get and set methods for internal organization ID
  - Added project list endpoint with ability to search within project names
  - Added ability to sort by attribute in ascending or descending order when listing organizations or projects
  - Added user RBAC for backend admin endpoints
- Billing
  - Added pricing and usage tracking for embedding & reranking
- Auth
  - Implement Personal Access Token, deprecate organization API keys

AIPC

- Added new models and configurations in `models_aipc.json`.

CI/CD

- Added jamaibase-app compilation CI.
- Added cloud unit tests
- Pinned `torch` dependency to version `~2.2.0` in `services/docio/pyproject.toml`. #265
- Added Lance tests
- Added TS/JS SDK tests

### CHANGES / FIXED

Python SDK - jamaibase

- **Breaking**: `get_conversation_thread()` has two new required arguments: `table_type` and `column_id`
- `duplicate_table()` arguments changed:
  - Added `create_as_child` argument, and deprecated `deploy`. Resolves #196
  - `table_id_dst` is now an optional argument
- Default values changed
  - `ChatRequest.stop`: `[]` -> `None`
  - `ChatRequest.temperature`: `1.0` -> `0.2`
  - `ChatRequest.top_p`: `1.0` -> `0.6`
- Vector columns can now be excluded from the results of `list_table_rows()`, `get_table_row()`, `hybrid_search()` methods by passing in a negative `vec_decimals` value.
- Exception classes are now moved into `jamaibase` from `owl`

TS SDK - jamaibase

- Changed COl_ID and TABLE_ID regex. #296
- Removed browser-only modules

UI

- Bump `app` version from `0.1.0` to `0.2.0`.
- Fix `CORS Error` and JamAI Base Electron App compilation steps. #260

Backend - owl (API server)

- **Breaking**: Delete endpoints will raise 404 if the resource is not found
- GenTable
  - **Breaking**: Table list endpoint now defaults to not counting table rows
  - **Breaking**: Duplicate table endpoint `/v1/gen_tables/{table_type}/duplicate/{table_id_src}/{table_id_dst}` is deprecated in favour of `/v1/gen_tables/{table_type}/duplicate/{table_id_src}`
  - **Breaking**: `/v1/gen_tables/{table_type}/{table_id}/thread` has one new required query parameter: `column_id`
    - It also supports `action` and `knowledge` table now.
  - Changed the search method for row filtering from FTS to regex
  - Add deprecation warning for `deploy` param to the "duplicate table" endpoint
  - Default models
    - If any of chat, embedding, or reranking model is set to "", then a default model is dynamically assigned
    - Prioritise ELLM models when setting default model
  - Refactor column validation
  - Allow single character table and column ID
  - Vector columns can now be excluded from the results of `list_table_rows()`, `get_table_row()`, `hybrid_search()` methods by passing in a negative `vec_decimals` value.
  - Bug fixes
    - CSV import with vector data now works correctly
    - Full-text-search (FTS) now properly executes term query rather than phrase query
    - CSV import numeric data as string now works correctly. #300
    - Ensure chat table sequential regen
- LLM
  - Default model will prefer ELLM models
  - Model list are now sorted by ID
  - Changed target of "openai/gpt-4o" to "openai/gpt-4o-2024-08-06"
  - Set `stream_options={"include_usage": True}` to fix discrepancy between stream and non-stream token usage
  - Added model availability check
  - Added support for internal models
  - Make setting `owned_by` optional in model config JSON
  - Reduce context exceed log verbosity
  - Bug fixes
    - Model config has been updated
- Billing
  - Logic has been rewritten
  - New pricing model. Resolves #235
  - Event now accepts deltas and values which can update multiple fields at once
  - Revamp LLM cost computation to be based on LiteLLM
  - Defined `owl_internal_org_id` to control internal resources
- Implement separate janitor process. Resolves #233
  - Compute storage usage
  - Perform Lance table periodic reindexing and optimisation
- DB
  - Change `NullPoll` -> `QueuePool` for better performance on admin DB
- Auth
  - Refactored auth logic to be based on FastAPI Dependency injection
  - Set auth timeout to 60s and return 503 if timeout
- Only enable logging when called via entrypoints
- Use `Annotated` with `Depends` to get DB session

Backend - starling (Janitor)

- Don't timeout for Lance periodic tasks

CI/CD

- Fix `api` and `docio`. Updated `scripts/compile_api_exe.ps1` and `scripts/compile_docio_exe.ps1` to use specific versions of `pyinstaller` and `cryptography` and install `python-magic`.
- Python lint:
  - Use Ruff instead of `black` + `flake8` + `isort`
  - Update Python lint rules
- Cancel in-progress CI jobs if there is a new push
- Set timeouts
  - PyTest per-test timeout at 90 seconds
  - GitHub Action per-job timeout at 60 minutes

### REMOVED

Python SDK - jamaibase

- Remove unused protocols
- Remove client-side gen config validation
- Removed redundant "file_name" Form fields from gen table methods

TS SDK - jamaibase

- Removed redundant "file_name" Form fields from gen table methods

Backend - owl (API server)

- Removed owl client, it is merged into `jamaibase`
- LLM
  - Removed "together_ai/Qwen/Qwen1.5" series models
- GenTable
  - Removed redundant "file_name" Form field
  - Removed File Table, raw files will be stored in S3 instead

## [Python] [v0.2.1] - 2024-08-18

### CHANGED / FIXED

Python SDK - jamaibase

- Bug fixes
  - Table type is now correctly handled in Python > 3.10

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
- Added `search_query` param in `listRows()`
- Added unit tests for the TypeScript/JavaScript SDK, including both OSS and Cloud environments
- Enhanced the Base class to generate a user agent string
- Added checks and methods to ensure the SDK works in both Node.js and browser environments

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
    - calculate recall to differentiate between digital pdf (recall > 0.9) and scanned/mixed pdf
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
  - Support forked version of `unstructured-client==0.24.1`, changed `nest-asyncio` to `ThreadPool`, fixed the conflict with `uvloop`
  - Added `tenacity`, `pandas`
  - Bumped dependency versions

Backend - docio (PDF loader)

- Bug fixes:
  - Windows: Temporary file must be closed before it can be accessed by other processes or nested contexts. Change to `TemporaryDirectory` instead. Fixes #125
  - Windows: StreamResponse from FastAPI accumulates all SSE before yielding everything all at once to the client Fixes #145

Backend - Admin (cloud)

- Improve insufficient credit error message: include quota/usage type in the message
- Storage usage update is now a background process; fixes #87
- Allow dot in the middle for project name and organization name.
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
