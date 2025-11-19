# Guide for AI agents

This Agents.md file provides comprehensive guidance for OpenAI Codex and other AI agents working with this codebase.

## Project Structure for OpenAI Codex Navigation

- `/services/api/src`: Source code
  - `/api`: Backend API service implemented using FastAPI, sqlmodel
  - `/app`: Frontend service implemented using Svelte
  - `/docio`: Document parsing service
- `/clients`: SDK
  - `/python`: Python SDK
  - `/typescript`: TS SDK
- `/docker`: Docker files

## Coding Conventions

### General Conventions

- Follow the existing code style in each file
- Use meaningful variable and function names
- Add comments for complex logic

### Backend Conventions

- Data models:
  - Most of the Pydantic models are imported from `clients/python/src/jamaibase/types` via `jamaibase.types`
  - `sqlmodel` (DB models) live in `services/api/src/owl/db/models`
  - All SQL tables should have the same name and capitalisation as its corresponding DB class, and under `jamai` schema
  - Each DB class will have a corresponding Pydantic class with name ending with underscore, for example `Organization` and `Organization_`. This is to provide separation between DB classes (does not validate input) and Pydantic classes (validates input).
- For CRUD endpoints:
  - Strongly prefer Query parameter over Path parameters for REST API
  - Implement `FooUpdate`, `FooCreate`, `Foo_`, `FooRead` Pydantic models for input and output validation

## Pull Request Review Guidelines

- Always prioritise any security issues
- Always provide solution or suggestions for any issues found
