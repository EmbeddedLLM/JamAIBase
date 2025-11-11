#!/usr/bin/env python3
"""
A script to update model IDs with a clear, subcommand-based interface.

Usage:
  python update.py one-to-one <old_model_id> <new_model_id>
  python update.py many-to-one <old_id_1> <old_id_2>... --to <new_id>
  python update.py file <path_to_mapping.json>
"""

import asyncio
import json
import pathlib
import sys
from typing import Dict, List, Optional, Tuple

import typer
from asyncpg import Connection, Record
from loguru import logger

from owl.db import async_session
from owl.db.gen_table import (
    GENTABLE_ENGINE,
    ActionTable,
    ChatTable,
    KnowledgeTable,
    TableType,
)
from owl.db.models import ModelConfig, Organization, Project
from owl.types import (
    CodeGenConfig,
    DiscriminatedGenConfig,
    EmbedGenConfig,
    LLMGenConfig,
    OrganizationRead,
    ProjectRead,
)

# Typer app with subcommands
app = typer.Typer(
    help="A tool to update model IDs using different modes.",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)

# Common options that can be used with any subcommand
_DRY_RUN_OPTION = typer.Option(
    False, "--dry-run", "-n", help="Show what would be updated without making changes."
)
_ORGANIZATIONS_OPTION = typer.Option(
    None,
    "--organizations",
    "-o",
    help="Comma-separated list of specific organization IDs to target.",
)


# ------------------------------------------------------------------
# 1. HELPER FUNCTIONS
# ------------------------------------------------------------------


async def validate_models(mapping: Dict[str, str]) -> bool:
    """
    Check that all new models exist
    Check that no embedding models.
    """
    async with async_session() as session:
        # Use a set to check each new ID only once, improving efficiency
        for new_id in set(mapping.values()):
            new_model = await ModelConfig.get(session, new_id)
            if not new_model:
                logger.error(
                    f"Validation failed: New model ID '{new_id}' does not exist in the system."
                )
                return False
            if "embed" in new_model.capabilities:
                logger.error(f"Validation failed: New model ID '{new_id}' is an embedding model.")
                return False
        for old_id in set(mapping.keys()):
            old_model = await ModelConfig.get(session, old_id)
            if not old_model:
                logger.warning(
                    f"Old Model ID '{old_id}' does not exist in the system, assumed to be deleted. Skipping validation."
                )
                continue
            if "embed" in old_model.capabilities:
                logger.error(f"Validation failed: Old model ID '{old_id}' is an embedding model.")
                return False
    logger.success("All new models validated successfully.")
    return True


async def validate_model_mapping(mapping: Dict[str, str]) -> bool:
    """Check that all new models has at least the same capability as old models, and not embedding models."""
    async with async_session() as session:
        # Use a set to check each new ID only once, improving efficiency
        for old_id, new_id in mapping.items():
            new_model = await ModelConfig.get(session, new_id)
            old_model = await ModelConfig.get(session, old_id)
            if not new_model:
                logger.error(
                    f"Validation failed: New model ID '{new_id}' does not exist in the system."
                )
                return False
            if not old_model:
                logger.warning(
                    f"Old Model ID '{old_id}' does not exist in the system, assumed to be deleted. Skipping validation."
                )
                continue
            if "embed" in new_model.capabilities:
                logger.error(f"Validation failed: New model ID '{new_id}' is an embedding model.")
                return False
            if not [c for c in old_model.capabilities if c in new_model.capabilities]:
                logger.error(
                    f"Validation failed: New model ID '{new_id}' does not have the same capabilities as old model ID '{old_id}'."
                )
                return False
    logger.success("All new model IDs validated successfully.")
    return True


# ------------------------------------------------------------------
# 2. CORE PROCESSING LOGIC
# ------------------------------------------------------------------


class ModelIDUpdater:
    """The engine that performs the single-pass update. This is generic and works with any mapping."""

    def __init__(
        self,
        model_mapping: Dict[str, str],
        dry_run: bool = False,
        organization_ids: Optional[List[str]] = None,
    ):
        self.model_mapping = model_mapping
        self.dry_run = dry_run
        self.organization_ids = organization_ids
        self.updated_count = 0

    @staticmethod
    def _gen_config_model_validate(gen_config_json: dict) -> Optional[DiscriminatedGenConfig]:
        obj_type = gen_config_json.get("object")
        try:
            if obj_type in ("gen_config.llm", "gen_config.chat"):
                return LLMGenConfig.model_validate(gen_config_json)
            elif obj_type == "gen_config.embed":
                return EmbedGenConfig.model_validate(gen_config_json)
            elif obj_type == "gen_config.code":
                return CodeGenConfig.model_validate(gen_config_json)
        except Exception as e:
            logger.warning(f"Skipping column due to validation error in its gen_config: {e}")
        return None

    async def get_all_organizations(
        self, organization_ids: Optional[List[str]] = None
    ) -> List[OrganizationRead]:
        """Retrieve all organizations from the database, optionally filtered."""
        async with async_session() as session:
            if not organization_ids:
                orgs = await Organization.list_(session=session, return_type=OrganizationRead)
                return orgs.items

            all_organizations = []
            for org_id in organization_ids:
                org = await Organization.get(session, org_id)
                org = OrganizationRead.model_validate(org)
                if org:
                    all_organizations.append(org)
                else:
                    logger.warning(f"Organization with ID '{org_id}' not found. Skipping.")
            return all_organizations

    async def get_all_projects_from_org(self, organization_id: str) -> List[ProjectRead]:
        """Retrieve all projects from a specific organization."""
        async with async_session() as session:
            projects = await Project.list_(
                session=session,
                return_type=ProjectRead,
                filters=dict(organization_id=organization_id),
            )
        return projects.items

    async def get_tables_for_project(
        self, conn: Connection, project_id: str, table_type: TableType
    ) -> List[Record]:
        """Get all tables for a project and table type."""
        schema_id = f"{project_id}_{table_type.value}"
        try:
            return await conn.fetch(f'SELECT table_id FROM "{schema_id}"."TableMetadata"')
        except Exception as e:
            logger.warning(f"Could not access schema '{schema_id}': {e}")
            return []

    async def get_columns_with_gen_config(
        self, conn: Connection, project_id: str, table_type: TableType, table_id: str
    ) -> List[Record]:
        """Get all columns with gen_config for a specific table."""
        schema_id = f"{project_id}_{table_type.value}"
        return await conn.fetch(
            f'SELECT column_id, gen_config FROM "{schema_id}"."ColumnMetadata" '
            "WHERE table_id = $1 AND gen_config IS NOT NULL",
            table_id,
        )

    def update_model_id_in_config(
        self, gen_config: DiscriminatedGenConfig
    ) -> Tuple[bool, DiscriminatedGenConfig]:
        """Update model IDs in a gen_config if they match the mapping."""
        updated = False
        config = gen_config.model_copy(deep=True)

        if isinstance(config, LLMGenConfig):
            if config.model in self.model_mapping:
                config.model = self.model_mapping[config.model]
                updated = True
            if config.rag_params and config.rag_params.reranking_model in self.model_mapping:
                config.rag_params.reranking_model = self.model_mapping[
                    config.rag_params.reranking_model
                ]
                updated = True
        elif isinstance(config, EmbedGenConfig):
            if config.embedding_model in self.model_mapping:
                config.embedding_model = self.model_mapping[config.embedding_model]
                updated = True

        return updated, config

    @staticmethod
    async def get_table_instance(
        project_id: str, table_type: TableType, table_id: str
    ) -> ActionTable | KnowledgeTable | ChatTable:
        table_classes = {
            TableType.ACTION: ActionTable,
            TableType.KNOWLEDGE: KnowledgeTable,
            TableType.CHAT: ChatTable,
        }
        table_class = table_classes[table_type]
        return await table_class.open_table(project_id=project_id, table_id=table_id)

    async def update_column_gen_config(
        self,
        project_id: str,
        table_type: TableType,
        table_id: str,
        update_mapping: dict[str, DiscriminatedGenConfig],
    ):
        """Update the gen_config for a specific column in the database."""
        if self.dry_run:
            return

        table = await self.get_table_instance(project_id, table_type, table_id)
        await table.update_gen_config(update_mapping=update_mapping, allow_nonexistent_refs=True)

    async def process_organization(self, organization: OrganizationRead):
        """Iterate through all projects and tables in an organization and update them."""
        logger.info(f"Processing organization: {organization.id}")
        projects = await self.get_all_projects_from_org(organization.id)

        for project in projects:
            logger.info(f"  Processing project: {project.id}")
            for table_type in [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]:
                col_updated_count = 0
                async with GENTABLE_ENGINE.transaction() as conn:
                    tables = await self.get_tables_for_project(conn, project.id, table_type)
                    if not tables:
                        continue

                    for table in tables:
                        table_id = table["table_id"]
                        columns = await self.get_columns_with_gen_config(
                            conn, project.id, table_type, table_id
                        )
                        to_be_update = {}
                        for column in columns:
                            gen_config = self._gen_config_model_validate(column["gen_config"])
                            if not gen_config:
                                continue
                            was_updated, updated_config = self.update_model_id_in_config(
                                gen_config
                            )
                            if was_updated:
                                found_old_model = None
                                if isinstance(gen_config, LLMGenConfig):
                                    if gen_config.model in self.model_mapping:
                                        found_old_model = gen_config.model
                                    elif (
                                        gen_config.rag_params
                                        and gen_config.rag_params.reranking_model
                                        in self.model_mapping
                                    ):
                                        found_old_model = gen_config.rag_params.reranking_model
                                elif isinstance(gen_config, EmbedGenConfig):
                                    if gen_config.embedding_model in self.model_mapping:
                                        found_old_model = gen_config.embedding_model

                                log_msg = (
                                    f"      - Found '{found_old_model}' in column '{column['column_id']}' (table: {table_id})"
                                    if found_old_model
                                    else f"      - Updating column '{column['column_id']}' in table '{table_id}'"
                                )
                                logger.info(log_msg)
                                to_be_update[column["column_id"]] = updated_config
                        if len(to_be_update) > 0:
                            await self.update_column_gen_config(
                                project.id,
                                table_type,
                                table_id,
                                to_be_update,
                            )
                            col_updated_count += len(to_be_update)

                if col_updated_count > 0:
                    self.updated_count += col_updated_count
                    logger.info(
                        f"    Updated {col_updated_count} columns in {table_type.value} tables for this project."
                    )

    async def run(self):
        """Run the entire model ID update process."""
        mode = "DRY RUN" if self.dry_run else "UPDATE MODE"
        logger.info(f"Starting model ID update in {mode}.")
        logger.info(
            f"Applying {len(self.model_mapping)} model mapping(s): {json.dumps(self.model_mapping, indent=2)}"
        )

        organizations = await self.get_all_organizations(self.organization_ids)
        logger.info(f"Found {len(organizations)} organization(s) to process.")

        for organization in organizations:
            await self.process_organization(organization)

        summary = "Dry run complete" if self.dry_run else "Update complete"
        logger.success(
            f"{summary}. Total columns affected across all organizations: {self.updated_count}"
        )


# ------------------------------------------------------------------
# 3. CLI SUBCOMMANDS
# ------------------------------------------------------------------


@app.command("one-to-one")
def cmd_one(
    old_model_id: str = typer.Argument(..., help="The single old model ID to be replaced."),
    new_model_id: str = typer.Argument(..., help="The single new model ID to use."),
    dry_run: bool = _DRY_RUN_OPTION,
    organizations: Optional[str] = _ORGANIZATIONS_OPTION,
):
    """Replaces one model ID with another."""
    mapping = {old_model_id: new_model_id}
    run_update(mapping, dry_run, organizations)


@app.command("many-to-one")
def cmd_many_to_one(
    old_model_ids: List[str] = typer.Argument(..., help="A list of old model IDs to be replaced."),  # noqa: B008
    new_model_id: str = typer.Option(
        ..., "--to", "-t", help="The target model ID that will replace all old models. (Required)"
    ),
    dry_run: bool = _DRY_RUN_OPTION,
    organizations: Optional[str] = _ORGANIZATIONS_OPTION,
):
    """Maps many old model IDs to a single new model ID."""
    mapping = {old_id: new_model_id for old_id in old_model_ids}
    run_update(mapping, dry_run, organizations)


@app.command("file")
def cmd_file(
    mapping_file: pathlib.Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to a JSON file with {old_id: new_id} mappings.",
        exists=True,
        readable=True,
        dir_okay=False,
    ),
    dry_run: bool = _DRY_RUN_OPTION,
    organizations: Optional[str] = _ORGANIZATIONS_OPTION,
):
    """Replaces model IDs based on a JSON mapping file."""
    try:
        mapping = json.loads(mapping_file.read_text())
        if not isinstance(mapping, dict):
            raise TypeError("Mapping file must contain a JSON object (a dictionary).")
    except Exception as e:
        logger.error(f"Cannot read or parse mapping file '{mapping_file}': {type(e)}")
        raise typer.Exit(code=1) from None
    run_update(mapping, dry_run, organizations)


# ------------------------------------------------------------------
# 4. SHARED RUNNER
# ------------------------------------------------------------------


def run_update(mapping: Dict[str, str], dry_run: bool, org_string: Optional[str]):
    """A central runner that validates and executes the update process."""

    if not mapping:
        logger.warning("The model mapping is empty. Nothing to do.")
        return

    organization_ids = org_string.split(",") if org_string else None

    async def _inner():
        # 1. Validate models before doing anything else
        if not await validate_models(mapping):
            raise typer.Exit(code=1)

        # 2. Create and run the updater
        updater = ModelIDUpdater(mapping, dry_run, organization_ids)
        await updater.run()

    try:
        asyncio.run(_inner())
    except Exception as e:
        logger.error(f"An unexpected error occurred during the update process: {type(e)} {str(e)}")
        sys.exit(1)


# ------------------------------------------------------------------
# 5. SCRIPT ENTRYPOINT
# ------------------------------------------------------------------

if __name__ == "__main__":
    app()
