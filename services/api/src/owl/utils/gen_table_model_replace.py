import asyncio
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Iterator

from loguru import logger
from pydantic import TypeAdapter

from owl.configs import CACHE
from owl.db import async_session
from owl.db.gen_table import (
    GENTABLE_ENGINE,
    ActionTable,
    ChatTable,
    KnowledgeTable,
)
from owl.db.models import Organization, Project
from owl.types import (
    DiscriminatedGenConfig,
    ImageGenConfig,
    LLMGenConfig,
    OrganizationRead,
    Progress,
    ProgressState,
    ProjectRead,
    TableType,
)

MODEL_REPLACE_PROGRESS_TTL_SEC = 60 * 60 * 3
MODEL_REPLACE_LOCK_KEY = "gen_table_model_replace:lock"
MODEL_REPLACE_RECENT_PROGRESS_KEYS_KEY = "gen_table_model_replace:recent_progress_keys"
TABLE_CONCURRENCY = 8
TABLE_BATCH_SIZE = 100
ORG_PROJECT_PAGE_SIZE = 1_000
GEN_CONFIG_ADAPTER = TypeAdapter(DiscriminatedGenConfig)

TABLE_CLS: dict[TableType, type[ActionTable] | type[KnowledgeTable] | type[ChatTable]] = {
    TableType.ACTION: ActionTable,
    TableType.KNOWLEDGE: KnowledgeTable,
    TableType.CHAT: ChatTable,
}


def chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def model_replace_progress_data(
    *,
    mapping: dict[str, str],
    organization_ids: list[str] | None,
    requested_by: str,
    stats: dict[str, bool | int],
) -> dict[str, Any]:
    return {
        "request": {
            "mapping": deepcopy(mapping),
            "organization_ids": deepcopy(organization_ids),
            "requested_by": requested_by,
        },
        "stats": stats,
    }


@dataclass(slots=True)
class ReplacementHit:
    organization_id: str
    project_id: str
    table_type: TableType
    table_id: str
    column_id: str
    old_model_id: str
    new_model_id: str


@dataclass(slots=True)
class ModelReplaceStats:
    organizations_scanned: int = 0
    projects_scanned: int = 0
    tables_scanned: int = 0
    tables_updated: int = 0
    tables_failed: int = 0
    updated_columns: int = 0
    failed_columns: int = 0

    def to_dict(self) -> dict[str, bool | int]:
        return asdict(self)


async def acquire_model_replace_lock(progress_key: str) -> bool:
    return await CACHE.acquire_lock_value(
        MODEL_REPLACE_LOCK_KEY,
        progress_key,
        ex=MODEL_REPLACE_PROGRESS_TTL_SEC,
    )


async def get_model_replace_lock() -> str | None:
    return await CACHE.get_lock_value(MODEL_REPLACE_LOCK_KEY)


async def release_model_replace_lock(progress_key: str) -> bool:
    if not progress_key:
        return False
    return await CACHE.release_lock_value(
        MODEL_REPLACE_LOCK_KEY,
        progress_key,
    )


async def add_recent_model_replace_progress_key(progress_key: str) -> None:
    await CACHE.add_recent_progress_key(
        MODEL_REPLACE_RECENT_PROGRESS_KEYS_KEY,
        progress_key,
        ttl_sec=MODEL_REPLACE_PROGRESS_TTL_SEC,
    )


async def initialize_model_replace_progress(
    *,
    progress_key: str,
    mapping: dict[str, str],
    organization_ids: list[str] | None,
    requested_by: str,
) -> None:
    stats = ModelReplaceStats()
    progress = Progress(
        key=progress_key,
        data=model_replace_progress_data(
            mapping=mapping,
            organization_ids=organization_ids,
            requested_by=requested_by,
            stats=stats.to_dict(),
        ),
    )
    await CACHE.set_progress(progress, ex=MODEL_REPLACE_PROGRESS_TTL_SEC)
    await add_recent_model_replace_progress_key(progress_key)


async def remove_recent_model_replace_progress_key(progress_key: str) -> None:
    await CACHE.remove_recent_progress_key(
        MODEL_REPLACE_RECENT_PROGRESS_KEYS_KEY,
        progress_key,
    )


async def delete_model_replace_progress(progress_key: str) -> None:
    await remove_recent_model_replace_progress_key(progress_key)
    await CACHE.delete(progress_key)


async def list_recent_model_replace_progress_keys() -> list[str]:
    return await CACHE.list_recent_progress_keys(
        MODEL_REPLACE_RECENT_PROGRESS_KEYS_KEY,
        ttl_sec=MODEL_REPLACE_PROGRESS_TTL_SEC,
    )


async def refresh_model_replace_lock(progress_key: str) -> bool:
    if not progress_key:
        return False
    return await CACHE.refresh_lock_value(
        MODEL_REPLACE_LOCK_KEY,
        progress_key,
        ex=MODEL_REPLACE_PROGRESS_TTL_SEC,
    )


class GenTableModelReplacer:
    def __init__(
        self,
        *,
        mapping: dict[str, str],
        organization_ids: list[str] | None,
        progress_key: str,
        requested_by: str = "",
    ) -> None:
        self.mapping = mapping
        self.organization_ids = organization_ids
        self.stats = ModelReplaceStats()
        self.progress = Progress(
            key=progress_key,
            data=model_replace_progress_data(
                mapping=mapping,
                organization_ids=organization_ids,
                requested_by=requested_by,
                stats=self.stats.to_dict(),
            ),
        )

    async def _publish_progress(self) -> None:
        self.progress.data["stats"] = self.stats.to_dict()
        await CACHE.set_progress(self.progress, ex=MODEL_REPLACE_PROGRESS_TTL_SEC)
        await refresh_model_replace_lock(self.progress.key)
        await add_recent_model_replace_progress_key(self.progress.key)

    async def _list_organizations(self) -> list[OrganizationRead]:
        async with async_session() as session:
            if self.organization_ids is None:
                organizations: list[OrganizationRead] = []
                offset = 0
                while True:
                    page = await Organization.list_(
                        session=session,
                        return_type=OrganizationRead,
                        offset=offset,
                        limit=ORG_PROJECT_PAGE_SIZE,
                    )
                    organizations.extend(page.items)
                    offset += len(page.items)
                    if offset >= page.total or not page.items:
                        return organizations

            organizations: list[OrganizationRead] = []
            for organization_id in self.organization_ids:
                org = await Organization.get(session, organization_id, name="Organization")
                organizations.append(OrganizationRead.model_validate(org))
        return organizations

    @staticmethod
    async def _list_projects(organization_id: str) -> list[ProjectRead]:
        async with async_session() as session:
            projects: list[ProjectRead] = []
            offset = 0
            while True:
                page = await Project.list_(
                    session=session,
                    return_type=ProjectRead,
                    filters=dict(organization_id=organization_id),
                    offset=offset,
                    limit=ORG_PROJECT_PAGE_SIZE,
                )
                projects.extend(page.items)
                offset += len(page.items)
                if offset >= page.total or not page.items:
                    return projects

    @staticmethod
    async def _list_table_ids(project_id: str, table_type: TableType) -> list[str]:
        schema_id = f"{project_id}_{table_type.value}"
        async with GENTABLE_ENGINE.transaction() as conn:
            try:
                rows = await conn.fetch(f'SELECT table_id FROM "{schema_id}"."TableMetadata"')
            except Exception as e:
                logger.warning(
                    f'Could not scan GenTable schema "{schema_id}" during model replace: {repr(e)}'
                )
                return []
        return [row["table_id"] for row in rows]

    @staticmethod
    async def _list_columns_with_gen_config(
        project_id: str, table_type: TableType, table_id: str
    ) -> list[dict[str, Any]]:
        schema_id = f"{project_id}_{table_type.value}"
        async with GENTABLE_ENGINE.transaction() as conn:
            rows = await conn.fetch(
                f'SELECT column_id, gen_config FROM "{schema_id}"."ColumnMetadata" '
                "WHERE table_id = $1 AND gen_config IS NOT NULL",
                table_id,
            )
        return [dict(row) for row in rows]

    @staticmethod
    def _validate_gen_config(gen_config_json: Any) -> DiscriminatedGenConfig | None:
        try:
            return GEN_CONFIG_ADAPTER.validate_python(gen_config_json)
        except Exception as e:
            logger.warning(
                f"Skipping column with invalid gen_config during model replace: {repr(e)}"
            )
            return None

    def _replace_config_fields(
        self,
        *,
        organization_id: str,
        project_id: str,
        table_type: TableType,
        table_id: str,
        column_id: str,
        gen_config: DiscriminatedGenConfig,
    ) -> tuple[DiscriminatedGenConfig | None, list[ReplacementHit]]:
        updated_config = gen_config.model_copy(deep=True)
        hits: list[ReplacementHit] = []

        def add_hit(
            *,
            old_model_id: str,
            new_model_id: str,
        ) -> None:
            hits.append(
                ReplacementHit(
                    organization_id=organization_id,
                    project_id=project_id,
                    table_type=table_type,
                    table_id=table_id,
                    column_id=column_id,
                    old_model_id=old_model_id,
                    new_model_id=new_model_id,
                )
            )

        if isinstance(updated_config, LLMGenConfig):
            if updated_config.model in self.mapping:
                old_model_id = updated_config.model
                updated_config.model = self.mapping[old_model_id]
                add_hit(
                    old_model_id=old_model_id,
                    new_model_id=updated_config.model,
                )
            if (
                updated_config.rag_params is not None
                and updated_config.rag_params.reranking_model in self.mapping
            ):
                old_model_id = updated_config.rag_params.reranking_model
                new_model_id = self.mapping[old_model_id]
                updated_config.rag_params.reranking_model = new_model_id
                add_hit(
                    old_model_id=old_model_id,
                    new_model_id=new_model_id,
                )
        elif isinstance(updated_config, ImageGenConfig):
            if updated_config.model in self.mapping:
                old_model_id = updated_config.model
                updated_config.model = self.mapping[old_model_id]
                add_hit(
                    old_model_id=old_model_id,
                    new_model_id=updated_config.model,
                )

        if not hits:
            return None, hits
        return updated_config, hits

    async def _process_table(
        self,
        *,
        organization_id: str,
        project_id: str,
        table_type: TableType,
        table_id: str,
    ) -> None:
        update_mapping: dict[str, DiscriminatedGenConfig] = {}
        hits: list[ReplacementHit] = []

        try:
            logger.info(
                f'Processing GenTable model replace table organization_id="{organization_id}" project_id="{project_id}" '
                f'table_type="{table_type}" table_id="{table_id}"'
            )
            columns = await self._list_columns_with_gen_config(project_id, table_type, table_id)

            for column in columns:
                column_id = column["column_id"]
                gen_config = self._validate_gen_config(column["gen_config"])
                if gen_config is None:
                    continue
                updated_config, column_hits = self._replace_config_fields(
                    organization_id=organization_id,
                    project_id=project_id,
                    table_type=table_type,
                    table_id=table_id,
                    column_id=column_id,
                    gen_config=gen_config,
                )
                if not column_hits:
                    continue
                hits.extend(column_hits)
                if updated_config is not None:
                    update_mapping[column_id] = updated_config

            if not hits:
                return

            table = await TABLE_CLS[table_type].open_table(
                project_id=project_id, table_id=table_id
            )
            await table.update_gen_config(
                update_mapping=update_mapping,
                allow_nonexistent_refs=True,
            )
        except Exception as e:
            failed_columns = set(update_mapping)
            self.stats.tables_failed += 1
            self.stats.failed_columns += len(failed_columns)
            logger.warning(
                f'Skipped failed GenTable model replace table: organization_id="{organization_id}" '
                f'project_id="{project_id}" table_type="{table_type}" table_id="{table_id}" '
                f"replacements={
                    [
                        {
                            'column_id': hit.column_id,
                            'old_model_id': hit.old_model_id,
                            'new_model_id': hit.new_model_id,
                        }
                        for hit in hits
                    ]
                } error={repr(e)}"
            )
            return
        self.stats.updated_columns += len(hits)
        self.stats.tables_updated += 1

    async def _process_table_with_limit(
        self,
        *,
        semaphore: asyncio.Semaphore,
        organization_id: str,
        project_id: str,
        table_type: TableType,
        table_id: str,
    ) -> None:
        async with semaphore:
            await self._process_table(
                organization_id=organization_id,
                project_id=project_id,
                table_type=table_type,
                table_id=table_id,
            )
            await self._publish_progress()

    async def run(self) -> ModelReplaceStats:
        await self._publish_progress()
        try:
            semaphore = asyncio.Semaphore(TABLE_CONCURRENCY)
            organizations = await self._list_organizations()
            for organization in organizations:
                self.stats.organizations_scanned += 1
                projects = await self._list_projects(organization.id)
                self.stats.projects_scanned += len(projects)
                await self._publish_progress()

                for project in projects:
                    for table_type in (TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT):
                        table_ids = await self._list_table_ids(project.id, table_type)
                        self.stats.tables_scanned += len(table_ids)
                        for table_id_batch in chunks(table_ids, TABLE_BATCH_SIZE):
                            await asyncio.gather(
                                *[
                                    self._process_table_with_limit(
                                        semaphore=semaphore,
                                        organization_id=organization.id,
                                        project_id=project.id,
                                        table_type=table_type,
                                        table_id=table_id,
                                    )
                                    for table_id in table_id_batch
                                ]
                            )

            self.progress.state = ProgressState.COMPLETED
            await self._publish_progress()
            logger.success(
                f'GenTable model replace completed progress_key="{self.progress.key}" stats={self.stats.to_dict()}'
            )
            return self.stats
        except Exception as e:
            self.progress.state = ProgressState.FAILED
            self.progress.error = repr(e)
            await self._publish_progress()
            raise
