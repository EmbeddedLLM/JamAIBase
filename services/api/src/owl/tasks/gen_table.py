import asyncio
from io import BytesIO

from loguru import logger

from owl.configs import celery_app
from owl.db.gen_table import ActionTable, ChatTable, KnowledgeTable
from owl.types import TableType
from owl.utils.exceptions import JamaiException, ResourceExistsError
from owl.utils.io import open_uri_async

TABLE_CLS: dict[TableType, ActionTable | KnowledgeTable | ChatTable] = {
    TableType.ACTION: ActionTable,
    TableType.KNOWLEDGE: KnowledgeTable,
    TableType.CHAT: ChatTable,
}


@celery_app.task
def import_gen_table(
    source: str | bytes,
    *,
    project_id: str,
    table_type: str,
    table_id_dst: str | None,
    reupload_files: bool = True,
    progress_key: str = "",
    verbose: bool = False,
) -> str:
    async def _task():
        if isinstance(source, str):
            async with open_uri_async(source) as (f, _):
                data = await f.read()
        else:
            data = source
        with BytesIO(data) as f:
            try:
                return await TABLE_CLS[table_type].import_table(
                    project_id=project_id,
                    source=f,
                    table_id_dst=table_id_dst,
                    reupload_files=reupload_files,
                    progress_key=progress_key,
                    verbose=verbose,
                )
            except ResourceExistsError:
                raise
            except JamaiException as e:
                logger.error(
                    f'Failed to import table "{table_id_dst}" into project "{project_id}": {repr(e)}'
                )
                raise
            except Exception as e:
                logger.exception(
                    f'Failed to import table "{table_id_dst}" into project "{project_id}": {repr(e)}'
                )
                raise

    logger.info("Generative Table import task started.")
    table = asyncio.get_event_loop().run_until_complete(_task())
    logger.info("Generative Table import task completed.")
    return table.v1_meta_response.model_dump_json()
