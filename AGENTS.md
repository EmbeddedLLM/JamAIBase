# Guide for AI agents

This `AGENTS.md` file provides comprehensive guidance for OpenAI Codex, Claude Code, and other AI agents working with this codebase.

The user's job as a senior software engineer is dependent on you implementing clean code with elegant architecture.

## Repository Structure

```text
.
├── .github/workflows/  # CI, release, and documentation workflows
├── clients/
│   ├── python/        # Python SDK and shared API types
│   └── typescript/    # TypeScript SDK
├── docker/            # Dockerfiles and Compose configurations
├── docs/              # Project documentation
├── examples/          # Example integrations
├── k8s/               # Kubernetes deployment configuration
├── libs/polylm/       # Language-model integration library
├── scripts/           # Development and maintenance scripts
└── services/
    ├── api/           # FastAPI/SQLModel backend and tests
    ├── app/           # Svelte frontend
    ├── gateway/       # Kong gateway configuration
    └── replication/   # Replication and restore tooling
```

## Core Principles

- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Simplicity First**: Make every change as simple as possible. Only touch what's necessary. Impact minimal code. Over-complication leads to bugs.
  1. Always start with thorough understanding of the problem and motivation
  2. Does this functionality need to exist? → no: challenge or skip it (YAGNI)
  3. Already in this codebase? → reuse or extend it, don't rewrite
  4. Stdlib does it? → use it
  5. Native platform feature? → use it
  6. Installed dependency? → use it
  7. One line? → one line
  8. Only then: the minimum that works
- **Validate the Approach Before Implementing**: For non-trivial changes, distinguish the required outcome from the proposed implementation. Treat implementation suggestions as hypotheses, including those in issues and plans.

  1. Identify the behavior and existing state that must be preserved.
  2. Check whether existing code or native platform capabilities can achieve the outcome with less change.
  3. When the choice depends on uncertain behavior, resolve that uncertainty with authoritative documentation or a focused experiment before coding.
  4. Require evidence that a simpler approach is insufficient before adding complexity or choosing a destructive operation.
  5. Derive tests from the required behavior and preservation guarantees, rather than assumptions specific to the chosen implementation.

  Keep this checkpoint proportional to the task; straightforward changes do not require a written alternatives analysis.

- **Simplify After Implementation**: Treat the first working version and the requirements behind it as drafts.
  1. Run relevant tests to uncover hidden requirements and assumptions.
  2. Relate every code path back to a concrete requirement, and challenge whether that requirement is truly necessary (first principles approach).
  3. Review the full diff for unnecessary abstractions, branches, defensive code, and overly strict guarantees.
  4. Prefer sufficient correctness over absolute correctness: for example, eventual consistency when acceptable, or simple retries when failure is cheap and recoverable.
  5. Remove or relax requirements that do not justify their complexity. Simplify immediately when behavior is preserved; otherwise present the proposed change, benefits, and trade-offs to the user.
- **Protect Secrets in Command Output**: When validating Compose files that use environment files, use `docker compose config --quiet`. Do not print fully resolved Compose configuration because it expands secret environment values into command output.

## Workflow Orchestration

### 1. Planning

- For non-trivial work, create a concise implementation plan before editing.
- Proceed without waiting for approval when the requested outcome is clear and the changes are low-risk.
- Ask for clarification only when ambiguity would materially change behavior, public interfaces, data, security, or architecture.
- Re-plan when evidence invalidates the current approach.
- Keep planning proportional to the task; do not create process overhead for straightforward changes.

### 2. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution
- Ask reviewers to challenge the necessity of the proposed mechanism and identify simpler existing alternatives, as well as checking correctness.

### 3. Task Tracking

- Use `tasks/todo.md` for substantial, multi-stage work when persistent tracking is useful.
- Do not create or modify `tasks/todo.md` for small or routine changes; the completion record below is still required.
- At the end of every feature, bug fix, or task, before the final handoff, create `tasks/YYYY-MM-DD-<task-name>.md`. Use the completion date and a short, descriptive, lowercase task name with hyphens.
- Write the completion record using the structure and wording rules in [PR Descriptions](#pr-descriptions).
- Record only durable, project-specific lessons in `tasks/lessons.md`.
- Do not record one-off user preferences, speculative conclusions, or conversational details.
- A user correction is evidence to reconsider the approach, not an automatic reason to create a permanent rule.

### 4. Verification Before Done

- Run the strongest applicable verification available in the current environment.
- Never claim that a check passed unless it was actually run and passed.
- When a check cannot be run, report the exact command not run and the reason.
- Distinguish failures introduced by the current change from pre-existing or environment-dependent failures.
- Verify the behavior affected by the change, not merely that the code compiles.
- Add or update regression tests when fixing a reproducible defect.
- All tests must have a docstring stating their intention, goal, purpose, or the regression they guard against. For example: "Ensures ..." or "Asserts that ...".
- Compare behavior before and after the change when practical.
- Run the applicable checks defined in the Linting Workflow.
- Always check whether any project documentation needs updating, even when documentation was not mentioned in the task. Update all affected docs before reporting completion.
- Keep verification proportional to the scope and risk of the change.

#### Local development environment

- Use `uv` when available.
- Follow `services/api/README.md` for local service setup and `.github/workflows/ci.yml` for the current test environment. CI installs the `test` extras from both `clients/python` and `services/api`.
- Run backend tests from `services/api`, where pytest reads `pyproject.toml`, with the required `.env` available there as in CI.
- Select tests for the configured deployment mode: `pytest --timeout 300 -m "not (cloud or stripe)" <test-path>` for OSS, or `pytest --timeout 300 -m "not (oss or stripe)" <test-path>` for cloud. Perform CI's cloud-only module removal for OSS runs only in a disposable checkout, because it deletes tracked files. Follow the CI setup for Stripe credentials and webhook prerequisites.
- See `services/api/tests/README.md` for shared and cloud-only test conventions. Do not run service-backed tests without their required services and configuration.

For backend changes requiring running services, run Compose commands from the repository root:

1. Validate the Compose configuration without exposing secrets: `docker compose -p jm --env-file .env -f docker/compose.dev.yml config --quiet`.
2. Start only the services required by the affected tests. Local development uses `docker/compose.dev.yml`; CI uses `docker/compose.ci.yml`.
3. Rebuild or force-recreate services only when the change requires it.
4. Verify readiness using configured health checks, service status, relevant logs, or an explicit endpoint probe.
5. Run the narrowest relevant tests first.
6. For substantial or shared backend changes, run the applicable deployment-mode suite following `.github/workflows/ci.yml` when its prerequisites are available.

Before reporting completion, review the final diff and ask:

- Does every change relate to a requirement?
- Did the change introduce unnecessary complexity or scope?
- Would a staff engineer approve the implementation and verification evidence?

#### Python Tests

- Run tests (especially async tests that invoke the OpenAI or Anthropic SDK) with escalated permissions on the first attempt. Their first-request platform detection uses `asyncio.to_thread()`, while the sandbox blocks the Unix socketpair wakeup that asyncio uses to deliver the worker result. Inside the sandbox these tests can therefore stall before reaching `MockTransport`; this is an environment limitation, not a cassette or SDK parsing failure.

### 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes – don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests – then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

### 7. Task Management

1. **Plan First**: For substantial, multi-stage work, write a plan to `tasks/todo.md` with checkable items.
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Create the dated completion record in `tasks/` using the required [PR description format](#pr-descriptions).
6. **Capture Lessons**: Update `tasks/lessons.md` when corrections reveal durable, project-specific lessons.

### 8. Linting Workflow

- Run formatting, linting, and static analysis after implementation and before reporting completion.
- The `.github/workflows/lint.yml` workflow is the source of truth. Before running checks, inspect it and use the commands, installation method, configuration, and tool versions selected by that workflow. Do not substitute globally installed tools or copy version numbers into this document.
- Start with changed files for fast feedback, then run the applicable repository-wide checks used by CI.
- When editing or creating Markdown files, run every applicable formatting or linting checks.

Always run `npx prettier` commands with escalated permissions on the first attempt. Do not try them in the sandbox first because `npx` requires registry and cache access to resolve Prettier.

Do not format unrelated files merely to make a repository-wide check pass.

#### Backend

From the repository root:

1. Inspect the Ruff installation and check steps in `.github/workflows/lint.yml`.
2. Install Ruff using the workflow's `lint` extra from `clients/python`; use `clients/python/pyproject.toml` as the lint configuration for the repository.
3. Confirm the selected version: `ruff --version`
4. Format changed Python files: `ruff format --config clients/python/pyproject.toml <changed-python-files>`
5. Check changed Python files: `ruff check --config clients/python/pyproject.toml <changed-python-files>`
6. Run the same repository-wide Ruff format check and lint check configured in CI.

Do not run automatic fixes across the entire repository unless explicitly required by the task.

#### Frontend and SDK formatting

- The repository-wide Prettier check in `.github/workflows/lint.yml` covers Markdown and other included files. Use the version and invocation selected by that workflow.
- The root `.prettierignore` excludes `services/app` and `clients/typescript`; the root check does not verify those packages.
- For changes in `services/app`, install dependencies from its lockfile with `npm ci`, use its locally installed Prettier and configuration to format and check changed files, then run `npm run lint` and `npm run check` from that directory.
- For changes in `clients/typescript`, follow its package scripts and configuration. Do not treat a formatting command that writes files as a check.

Do not format unrelated files merely to make a repository-wide check pass.

#### Failure Handling

- When a project-wide check fails, rerun the narrowest relevant command to determine whether the failure was caused by the current change.
- Fix failures introduced by the current change.
- Do not modify unrelated code to resolve pre-existing failures.
- Report pre-existing, infrastructure-dependent, or environment-dependent failures with the exact command and relevant error.
- Never describe a skipped, incomplete, or failing check as passing.
- In the final handoff, list the verification, test, formatting, linting, and static-analysis commands run, together with their outcomes.

### 9. Repository Safety

- Inspect `git status` and the relevant diff before editing.
- Preserve existing uncommitted changes and never overwrite work you did not create.
- Do not use destructive Git commands such as `reset --hard`, `clean`, or broad checkout/restore operations unless explicitly requested.
- Do not commit, push, create branches, or open pull requests unless requested.
- Avoid modifying generated files unless the project workflow requires regeneration.
- Keep unrelated formatting, refactors, dependency updates, and lockfile changes out of the diff.

## Closing Issues

- Before closing an issue as completed, review its requirements, the merged changes, and the current source on the default branch to confirm it is fully resolved.
- Leave a brief closing comment stating where the fix is available, summarizing the resulting behavior, and linking the merged PRs and commit URLs. State what was verified and any remaining limitations.
- Close as completed only when the issue is resolved. For duplicates, superseded work, or declined requests, explain the reason and link the replacement issue when applicable.

## PR Descriptions

- Use the structure below for GitHub PR descriptions and dated task completion records.
- Start PR descriptions with `## Summary`; do not repeat the PR title in the description. Dated task completion records should prepend a `# <task title>` heading.
- Before choosing a PR title, review the latest commits on the remote main branch (`git fetch origin main`, then `git log origin/main -10 --format=%s`) and follow the style of comparable changes, preferring area prefixes found in that history.
- Use declarative statements to describe completed changes, their purpose, and resulting behavior. For example "Replaced ..." or "The workflow now uses ...".
- Lead with the concrete problem and resulting behavior. Write for a reviewer who has not read the conversation, and keep details proportional to the change.
- Keep the title and description aligned with the final diff. Omit conversational history and abandoned approaches unless they explain a necessary trade-off.
- When updating a PR, review and rewrite the Summary section as needed to reflect the latest state of the entire PR. Do not merely append a bullet for each new commit pushed; consolidate or remove outdated bullets so the summary describes the current changes coherently.
- List verification commands and their actual outcomes. Include failed or skipped checks and their reasons; never claim an unrun check passed. Distinguish completed implementation from unverified deployment or runtime behavior.

```markdown
## Summary

- <Completed change and its purpose>

## Verification

- `<command>`: <outcome, or reason it was not run>
```

## Coding Conventions

### General Conventions

- When writing prompts, avoid using non-ASCII symbols.
- Follow the existing code style in each file.
- Use meaningful variable and function names.

### Code Comments

- Prefer clear code, meaningful names, and straightforward structure over comments that merely describe what the code does.
- Add comments when the reason behind an implementation would not be obvious to another developer.
- In particular, comment logic that:

  - may be surprising or counter-intuitive;
  - encodes a business rule or architectural decision;
  - intentionally deviates from established conventions or the most obvious implementation;
  - reflects an accepted trade-off, limitation, workaround, or compatibility constraint;
  - depends on subtle assumptions, ordering requirements, external behaviour, or non-obvious invariants;
  - is sufficiently complex that its intent or correctness would otherwise be difficult to verify.

- Comments should explain **why** the implementation exists, what constraint or decision led to it, and — when useful — what could go wrong if it is changed.
- Do not add comments that simply restate the code, narrate each operation, or compensate for unnecessarily complicated implementation.
- Keep comments accurate when modifying the associated code. Remove comments that are obsolete, misleading, or no longer useful.

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

## Code Review and Refactoring Guidelines

- Prioritize correctness, security, data integrity, and behavioral regressions.
- Identify duplicated logic, unnecessary branches, and avoidable complexity.
- Keep variant-specific behavior in explicit, responsibility-focused paths.
- Place genuinely shared validation, state updates, processing, and finalization in one location.
- Preserve observable behavior, ordering, errors, and public interfaces unless a change is explicitly requested.
- Prefer straightforward control flow over premature helper abstractions.
- Ensure abstractions reduce cognitive load rather than merely moving code.
- Touch only code relevant to the review or refactor.
- Add or update regression tests for every affected path and edge case.
- Review the final diff and confirm the result is materially simpler.
- Always provide concrete findings and recommended solutions.
- Check compliance with this `AGENTS.md` and project conventions.

### Publishing PR review findings

- When publishing a GitHub PR review, prefer inline review comments attached to the affected diff lines for actionable, code-specific findings.
- Anchor each finding to the smallest relevant line range on the reviewed commit. Explain the problem, its concrete impact or reproduction, and the recommended fix. Include severity when the repository's review format uses it.
- Keep separate findings in separate inline threads. Before posting, check existing comments to avoid duplicating the same finding.
- Use the review body for a concise overall assessment, verification results, and findings that cannot reasonably be attached to a diff line. Reference inline threads instead of repeating their full contents.
- If GitHub cannot anchor a finding to the relevant code, use a review-level comment with an explicit file/line or commit permalink. Do not attach it to unrelated changed lines merely to make it inline.
- Follow an explicit user request for a different review format. A request to review code does not by itself authorize publishing a review on GitHub.
