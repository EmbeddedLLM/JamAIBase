# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

- Each section is broken into:

  - `ADDED`: New features.
  - `CHANGED / FIXED`: Changes in existing functionality, or any bug fixes.
  - `DEPRECATED`: Soon-to-be removed features.
  - `REMOVED`: Removed features.
  - `SECURITY`: Anything related to vulnerabilities.

- The version number mentioned here refers to the cloud version.

## [Unreleased]

### ADDED

`Embeddings` endpoint

- Get a vector representation of a given input that can be easily consumed by machine learning models and algorithms. Note that the vectors are NOT normalized.
- Similar to OpenAI's embeddings endpoint
- Resolves #86

Generative Table

- Check existence of Knowledge Table when creating reference in either table creation or update gen_config. Resolves #142.
- Full row data logging when error occurred in table rows add or update. Resolves #140.
- Handle streaming exception by setting `ChatCompletionChunk.finish_reason` as "error". Also applies to chat endpoint.

UI

- Added button to delete projects
- Added title to dashboard
- Added config for building frontend into single-page application
- Setup frontend auth test for future tests

### CHANGED / FIXED

Generative Table

- Conversation Chat table generation config can now be modified. Previously only Agent Chat table can be modified. Resolves #188
- When creating a new table, a LLM model will be assigned dynamically if not specified in its `gen_config`. Resolves #190
- Vector search
  - Change default metric to `cosine`; fixes #110
  - Reduce default `refine_factor` from 50 to 20 to speed up search
- Hybrid search
  - Only do FTS once instead of looping through indexed col one by one (Lance/Tanvity FTS unable to specify search columns); fixes #138
  - Added Reciprocal Rank Fusion (RRF) to merge FTS and VS search results without using reranker; fixes #112
  - Added retry to search query, to handle possible failure case during FTS index build; fixes #111
  - Removed hybrid search with linear score combination (only uses RRF if without reranker)
- Improved handling of mid-stream error
  - Any errors encountered mid-stream will yield a completion chunk with error details as `text` and "error" as `finish_reason`
  - Errored table column will have its cell value set to `None`
- Missing columns in table row data are filled with `None`. It used to cause row add failure.
- Retrieval Augmented Generation (RAG) is now more robust against missing column data.
- Remap internal `ValidationError` to `RequestValidationError`. Fixes #162
- Improved handling of Timeout errors
- More aggressive Lance DB version cleanup: cleanup versions older than 5 minutes by default. Fixes #163
- Added more tests
- Bug fixes
  - If RAG query contains certain keyword in uppercase, it may be interpreted as term search and may lead to `SyntaxError`. It is now escaped. Fixes #187
  - Streaming response was not returning token usage. This also applies to chat endpoint.
  - Reference chunk `object` field value was incorrectly set as "chat.references" instead of "gen_table.references".
  - GenTable column reordering may produce tables with invalid generation config. Fixes #135
  - Stricter generation config validation

jamaibase

- Bug fixes: Fix type hinting
- Removed dependency on `uuid-utils`

UI

- Standardize & improve UI errors, including validation errors
- UI design changes
- Obfuscate org secrets
- Allow org members to view jamai keys
- Refactor UI code
- Fix edge case where organization team page would fail to load
- Fix change password button not working
- Fix missing project ID error when performing certain actions
- Fix pagination arrows not working in large tables
- Improve file upload status component
- Display column dtype on the header
- Fix tables page not redirecting after switching organizations
- Improve UX for renaming table columns

Backend - owl (API server)

- Refactor cache into `Cache` class that abstracts away `redis`
- Refactor LLM logic into `LLMEngine` class.
- Rename `owl.utils.get_api_key` -> `owl.utils.filter_external_api_key`
- Limit the number of rows that can be added at one time to 100. Fixes #157
- Chat completion
  - Search query rewrite max token increased from 256 to 512.
  - If context length is exceeded and stream is False, completion usage is set to `None`.
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
- Dependencies
  - Pin `unstructured-client` to 0.22.0

Backend - docio (PDF loader)

- Bug fixes:
  - Windows: Temporary file must be closed before it can be accessed by other processes or nested contexts. Change to `TemporaryDirectory` instead. Fixes #125

Backend - Admin (cloud)

- Improve insufficient credit error message: include quota/usage type in the message
- Storage usage update is now a background process; fixes #87
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

Dependencies

- Added `tenacity` to `owl`
- Bumped `owl` dependency versions

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
