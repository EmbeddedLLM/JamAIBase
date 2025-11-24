# Guide for AI agents

This Agents.md file provides comprehensive guidance for OpenAI Codex and other AI agents working with this codebase.

## Project Structure for OpenAI Codex Navigation

- `/services`: Source code for various services
  - `/api`: Backend API service implemented using FastAPI, SQLModel
    - `/src`: Backend source code
    - `/tests`: Backend test suite
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
  - DB models or classes live in `services/api/src/owl/db/models` (implemented using SQLModel)
  - All SQL tables should have the same name and capitalisation as its corresponding DB class, and under `jamai` schema
  - Each DB class will have a corresponding Pydantic class with name ending with underscore, for example `Organization` and `Organization_`. This provides a separation between the database schema model (SQLModel, does not validate input) and the API data transfer object (Pydantic model, validates inputs, suitable for API boundaries).
  - Pydantic models are imported from `clients/python/src/jamaibase/types/*` via `jamaibase.types`, with some overridden in `services/api/src/owl/types/*`
    - `jamaibase/types/*` contains all classes
    - `owl/types/*` additionally inject attributes, methods, validations that are useful only for backend
- For CRUD endpoints:
  - Strongly prefer Query parameter over Path parameters for REST API
  - Implement `FooUpdate`, `FooCreate`, `Foo_`, `FooRead` Pydantic models for input and output validation
  - `FooUpdate` models should contain only fields that can be updated by the user (usually fields that are not primary key)
  - If an endpoint or function involves long external network calls (long execution time), avoid using FastAPI dependency injection (`session: Annotated[AsyncSession, Depends(yield_async_session)]`) to provide DB `session`, instead manually create a session using either `async with async_session() as session` or `with sync_session() as session`
- Pydantic tips:
  - Prefer `field_validator` over `model_validator`, especially when using `mode="before"`.
- Always prefer single SQL statement over multi-step statements or Python loops whenever possible, for example:
  - Avoid:
    ```python
    async with async_session() as session:
        secrets_dict = {}
        project = await session.get(Project, project_id)
        if project is None:
            return secrets_dict
        # Fetch all secrets
        secrets = (await session.exec(select(Secret))).all()
        # Filter secrets to only those belonging to the same organization
        secrets = [s for s in secrets if s.organization_id == project.organization_id]
        for secret in secrets:
            # Check if secret is accessible to this project
            # - allowed_projects == None means all projects are allowed
            # - allowed_projects == [] means no projects are allowed
            # - allowed_projects == ["proj1"] means only specific projects are allowed
            if secret.allowed_projects is None:
                # Secret is accessible to all projects
                decrypted_value = decrypt(secret.value, ENV_CONFIG.encryption_key_plain)
                secrets_dict[secret.name] = decrypted_value
            elif secret.allowed_projects is not None and project_id in secret.allowed_projects:
                # Check if this project is in the allowed list
                decrypted_value = decrypt(secret.value, ENV_CONFIG.encryption_key_plain)
                secrets_dict[secret.name] = decrypted_value
    ```
  - Good:
    ```python
    async with async_session() as session:
        # Single query using JOIN and filtering
        statement = (
            select(Secret)
            .join(Project, Secret.organization_id == Project.organization_id)
            .where(
                Project.id == project_id,
                or_(
                    Secret.allowed_projects.is_(None),
                    Secret.allowed_projects.contains([project_id]),
                ),
            )
        )
        secrets = (await session.exec(statement)).all()
        # Assemble using a dictionary comprehension
        secrets_dict = {
            secret.name: decrypt(secret.value, ENV_CONFIG.encryption_key_plain)
            for secret in secrets
        }
    ```

## Pull Request Review Guidelines

- Always prioritise any security issues
- Always provide solution or suggestions for any issues found
- Check whether the code aligns with Coding Conventions stated in `Agents.md`
