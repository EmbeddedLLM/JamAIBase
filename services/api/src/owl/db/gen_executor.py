import asyncio
import base64
import re
from dataclasses import dataclass
from os.path import splitext
from time import time
from typing import Any, AsyncGenerator, Literal

import numpy as np
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from loguru import logger

from jamaibase.exceptions import BadInputError, JamaiException, ResourceNotFoundError
from owl.db.gen_table import GenerativeTable
from owl.llm import LLMEngine
from owl.models import CloudEmbedder
from owl.protocol import (
    GEN_CONFIG_VAR_PATTERN,
    ChatCompletionChoiceDelta,
    ChatCompletionChunk,
    ChatEntry,
    ChatRequest,
    EmbedGenConfig,
    ExternalKeys,
    GenTableChatCompletionChunks,
    GenTableRowsChatCompletionChunks,
    GenTableStreamChatCompletionChunk,
    GenTableStreamReferences,
    LLMGenConfig,
    RegenStrategy,
    RowAdd,
    RowAddRequest,
    RowRegen,
    RowRegenRequest,
    TableMeta,
)
from owl.utils import mask_string, uuid7_draft2_str
from owl.utils.io import open_uri_async


@dataclass(slots=True)
class Task:
    type: Literal["embed", "chat"]
    output_column_name: str
    body: ChatRequest | EmbedGenConfig
    dtype: str


class MultiRowsGenExecutor:
    def __init__(
        self,
        *,
        table: GenerativeTable,
        meta: TableMeta,
        request: Request,
        body: RowAddRequest | RowRegenRequest,
        rows_batch_size: int,
        cols_batch_size: int,
        max_write_batch_size: int,
    ) -> None:
        self.table = table
        self.meta = meta
        self.request = request
        self.body = body
        self.is_regen = isinstance(body, RowRegenRequest)
        self.bodies = (
            [
                RowAdd(
                    table_id=self.body.table_id,
                    data=row_data,
                    stream=self.body.stream,
                    concurrent=self.body.concurrent,
                )
                for row_data in self.body.data
            ]
            if isinstance(body, RowAddRequest)
            else [
                RowRegen(
                    table_id=body.table_id,
                    row_id=row_id,
                    regen_strategy=body.regen_strategy,
                    output_column_id=body.output_column_id,
                    stream=body.stream,
                    concurrent=self.body.concurrent,
                )
                for row_id in body.row_ids
            ]
        )
        self.rows_batch_size = rows_batch_size
        self.cols_batch_size = cols_batch_size
        self.max_write_batch_size = max_write_batch_size
        self.external_keys: ExternalKeys = request.state.external_keys

        # Accumulated rows for batch write
        self.batch_rows = []
        self.write_batch_size = self.optimal_write_batch_size()

    def _log_exception(self, exc: Exception, error_message: str):
        if not isinstance(exc, (JamaiException, RequestValidationError)):
            logger.exception(f"{self.request.state.id} - {error_message}")

    def _create_executor(self, body_: RowAdd | RowRegen):
        self.executor = GenExecutor(
            table=self.table,
            meta=self.meta,
            request=self.request,
            body=body_,
            cols_batch_size=self.cols_batch_size,
        )

    async def _execute(
        self, body_, tmp_id=None
    ) -> Any | tuple[GenTableChatCompletionChunks, dict]:
        self._create_executor(body_)
        if self.body.stream:
            try:
                async for chunk in await self.executor.gen_row():
                    await self.queue.put(chunk)
            except Exception as e:
                self._log_exception(e, f'Error executing task "{tmp_id}" with body: {body_}')
                await self.queue.put("data: [DONE]\n\n")
        else:
            return await self.executor.gen_row()

    async def _gen_stream_rows(self):
        content_length = 0
        self.queue = asyncio.Queue()
        for i in range(0, len(self.bodies), self.rows_batch_size):
            batch_bodies = self.bodies[i : i + self.rows_batch_size]
            # Accumulate rows within the row batch
            for j, body_ in enumerate(batch_bodies):
                asyncio.create_task(self._execute(body_, j))

            done_row_count = 0
            while done_row_count < len(batch_bodies):
                chunk = await self.queue.get()
                if isinstance(chunk, dict) or isinstance(chunk, tuple):
                    # Accumulate complete row
                    self.batch_rows.append(chunk)
                    if len(self.batch_rows) >= self.write_batch_size:
                        await self._write_rows_to_table()
                else:
                    if chunk == "data: [DONE]\n\n":
                        done_row_count += 1
                    else:
                        content_length += len(chunk.encode("utf-8"))
                        yield chunk

        # Write the remaining rows to table
        if len(self.batch_rows) > 0:
            await self._write_rows_to_table()
        # Final yield after writing is done
        chunk = "data: [DONE]\n\n"
        yield chunk
        content_length += len(chunk.encode("utf-8"))

        self.request.state.billing.create_egress_events(content_length / (1024**3))

    @staticmethod
    def _log_item(x: Any) -> str:
        if isinstance(x, np.ndarray):
            return f"array(shape={x.shape}, dtype={x.dtype})"
        elif isinstance(x, str):
            return mask_string(x)
        else:
            return f"type={type(x)}"

    def optimal_write_batch_size(self):
        """
        Dynamically adjust batch size for progress updates, capped at `max_write_batch_size`.
        """
        total_rows = len(self.bodies)

        # Aim for 5-10 batches, but ensure at least 10 rows per batch
        target_batches = min(max(5, total_rows // 10), 10)
        write_batch_size = max(total_rows // target_batches, 10)

        # Cap at max_write_batch_size
        write_batch_size = min(write_batch_size, self.max_write_batch_size)

        # Handle edge cases for small datasets
        if total_rows <= self.max_write_batch_size:
            write_batch_size = total_rows
            logger.info(f"Write to table: {total_rows} row(s) at once.")
        else:
            full_batches = total_rows // write_batch_size
            remainder = total_rows % write_batch_size

            logger.info(
                f"Write to table: {full_batches} batches with {write_batch_size} row(s) each."
            )

            if remainder:
                logger.info(f"Write to table: 1 additional batch with {remainder} row(s).")

        return write_batch_size

    async def _write_rows_to_table(self):
        """
        Writes accumulated rows to the table in batches.
        """
        with self.table.create_session() as session:
            if not self.is_regen:
                logger.info(
                    f"{self.request.state.id} - Writing {len(self.batch_rows)} rows to table '{self.body.table_id}'"
                )
                try:
                    await self.table.add_rows(session, self.body.table_id, self.batch_rows)
                except Exception as e:
                    _data = [
                        {k: self._log_item(v) for k, v in row.items()} for row in self.batch_rows
                    ]
                    self._log_exception(e, f"Error adding {len(self.batch_rows)} rows: {_data}")
            else:
                # Updating existing rows
                for row_id, row in self.batch_rows:
                    _data = {k: self._log_item(v) for k, v in row.items()}
                    logger.info(
                        f"{self.request.state.id} - Updating row with ID '{row_id}' in table '{self.body.table_id}': "
                        f"{_data}"
                    )
                    try:
                        self.table.update_rows(
                            session, self.body.table_id, where=f"`ID` = '{row_id}'", values=row
                        )
                    except Exception as e:
                        self._log_exception(e, f'Error updating row "{row_id}" with values: {row}')
            self.batch_rows.clear()

    async def _gen_nonstream_rows(self):
        rows: list[GenTableChatCompletionChunks] = []
        for i in range(0, len(self.bodies), self.rows_batch_size):
            batched_bodies = self.bodies[i : i + self.rows_batch_size]
            rows_and_column_dicts = await asyncio.gather(
                *[self._execute(body_) for body_ in batched_bodies]
            )
            # Accumulate generated rows
            for rows_, column_dict in rows_and_column_dicts:
                rows.append(rows_)

                if self.is_regen:
                    self.batch_rows.append((rows_.row_id, column_dict))
                else:
                    self.batch_rows.append(column_dict)

                if len(self.batch_rows) >= self.write_batch_size:
                    await self._write_rows_to_table()

        # Write the reminding rows to table
        if len(self.batch_rows) > 0:
            await self._write_rows_to_table()

        return GenTableRowsChatCompletionChunks(rows=rows)

    async def gen_rows(self) -> Any | GenTableChatCompletionChunks:
        if self.body.stream:
            return self._gen_stream_rows()
        else:
            return await self._gen_nonstream_rows()


class GenExecutor:
    def __init__(
        self,
        *,
        table: GenerativeTable,
        meta: TableMeta,
        request: Request,
        body: RowAdd | RowRegen,
        cols_batch_size: int,
    ) -> None:
        self.table = table
        self.meta = meta
        self.body = body
        self.is_row_add = isinstance(self.body, RowAdd)
        self.column_dict = {}
        self.regen_column_dict = {}
        self.tasks = []
        self.table_id = body.table_id
        self.request = request
        if isinstance(body, RowAdd):
            body.data["ID"] = body.data.get("ID", uuid7_draft2_str())
            self.row_id = body.data["ID"]
        else:
            self.row_id = body.row_id
        self.cols_batch_size = cols_batch_size if self.body.concurrent else 1
        self.external_keys: ExternalKeys = request.state.external_keys
        self.llm = LLMEngine(request=request)
        self.error_columns = []
        self.tag_regen_columns = []
        self.skip_regen_columns = []
        self.file_columns = []
        self.img_column_dict = {}
        self.doc_column_dict = {}

    def _log_exception(self, exc: Exception, error_message: str):
        if not isinstance(exc, (JamaiException, RequestValidationError)):
            logger.exception(f"{self.request.state.id} - {error_message}")

    async def _get_file_binary(self, uri: str) -> bytes:
        async with open_uri_async(uri) as file_handle:
            return await file_handle.read()

    async def gen_row(self) -> Any | tuple[GenTableChatCompletionChunks, dict]:
        cols = self.meta.cols_schema
        col_ids = set(c.id for c in cols)
        if self.is_row_add:
            self.column_dict = {k: v for k, v in self.body.data.items() if k in col_ids}
        else:
            self.column_dict = self.table.get_row(self.table_id, self.row_id)

        self.tasks = []
        for col in cols:
            # Skip info columns
            if col.id.lower() in ("id", "updated at"):
                continue
            # Skip state column
            if col.id.endswith("_"):
                continue
            # If user provides value, skip
            if self.is_row_add and col.id in self.column_dict:
                continue
            # If gen_config not defined, set None and skip
            if col.gen_config is None:
                if self.is_row_add:
                    self.column_dict[col.id] = None
                continue
            if isinstance(col.gen_config, EmbedGenConfig):
                task_type = "embed"
                if col.vlen <= 0:
                    raise ValueError(
                        f'"gen_config" is EmbedGenConfig but `col.vlen` is {col.vlen}'
                    )
                gen_config = col.gen_config
            elif isinstance(col.gen_config, LLMGenConfig):
                task_type = "chat"
                if col.gen_config.multi_turn:
                    messages = self.table.get_conversation_thread(
                        table_id=self.table_id,
                        column_id=col.id,
                        row_id="" if self.is_row_add else self.row_id,
                        include=False,
                    ).thread
                    user_message = col.gen_config.prompt
                    messages.append(ChatEntry.user(content=user_message if user_message else "."))
                    if len(messages) == 0:
                        continue
                else:
                    messages = [
                        ChatEntry.system(col.gen_config.system_prompt),
                        ChatEntry.user(col.gen_config.prompt),
                    ]
                gen_config = ChatRequest(
                    id=self.request.state.id, messages=messages, **col.gen_config.model_dump()
                )
            else:
                raise ValueError(f'Unexpected "gen_config" type: {type(col.gen_config)}')
            self.tasks.append(
                Task(type=task_type, output_column_name=col.id, body=gen_config, dtype=col.dtype)
            )

        self.file_columns = [col.id for col in cols if col.dtype == "file"]
        for col_id in self.file_columns:
            if self.column_dict.get(col_id, None) is not None:
                uri = self.column_dict[col_id]
                # uri -> file binary -> base64
                file_binary = await self._get_file_binary(uri)
                base64 = self._binary_to_base64(file_binary)

                # uri -> file extension -> prefix
                extension = splitext(uri)[1].lower()
                if extension in [".jpeg", ".jpg", ".png", ".gif", ".webp"]:
                    extension = ".jpeg" if extension == ".jpg" else extension
                    prefix = f"data:image/{extension[1:]};base64,"
                    # url = prefix + base64
                    self.img_column_dict[col_id] = prefix + base64
                else:
                    raise ValueError(
                        "Unsupported image, make sure the image belongs to "
                        "one of the following formats: ['jpeg/jpg', 'png', 'gif', 'webp']."
                    )

        column_dict_keys = set(self.column_dict.keys())
        if len(column_dict_keys - col_ids) > 0:
            raise ValueError(f"There are unexpected columns: {column_dict_keys - col_ids}")

        if self.body.stream:
            return self._stream_concurrent_execution()
        else:
            return await self._nonstream_concurrent_execution()

    async def _run_embed_tasks(self):
        """
        Executes embedding tasks sequentially.
        """
        embed_tasks = [task for task in self.tasks if task.type == "embed"]
        for task in embed_tasks:
            output_column_name = task.output_column_name
            body: EmbedGenConfig = task.body
            embedding_model = body.embedding_model
            embedder = CloudEmbedder(request=self.request)
            source = self.column_dict[body.source_column]
            embedding = await embedder.embed_documents(
                embedding_model, texts=["." if source is None else source]
            )
            embedding = np.asarray(embedding.data[0].embedding, dtype=task.dtype)
            embedding = embedding / np.linalg.norm(embedding)
            self.column_dict[output_column_name] = embedding
            self.regen_column_dict[output_column_name] = embedding

    def _extract_upstream_columns(self, text: str) -> list[str]:
        matches = re.findall(GEN_CONFIG_VAR_PATTERN, text)
        # return the content inside ${...}
        return matches

    def _extract_upstream_image_columns(self, text: str) -> list[str]:
        matches = re.findall(GEN_CONFIG_VAR_PATTERN, text)
        # return the content inside ${...}
        return [match for match in matches if self.llm_tasks[matches].dtype == "img"]

    def _binary_to_base64(self, binary_data: bytes) -> str:
        return base64.b64encode(binary_data).decode("utf-8")

    def _interpolate_column(self, prompt: str) -> str | dict[str, Any]:
        """
        Replaces / interpolates column references in the prompt with their contents.

        Args:
            prompt (str): The original prompt with zero or more column references.

        Returns:
            new_prompt (str | dict[str, Any]): The prompt with column references replaced.
        """

        image_column_names = []

        def replace_match(match):
            column_name = match.group(1)  # Extract the column_name from the match
            try:
                if column_name in self.img_column_dict:
                    image_column_names.append(column_name)
                    return "<image_url>"
                elif column_name in self.doc_column_dict:
                    return self.doc_column_dict[column_name]
                return str(self.column_dict[column_name])  # Data can be non-string
            except KeyError as e:
                raise BadInputError(f"Requested column '{column_name}' is not found.") from e

        content_ = re.sub(GEN_CONFIG_VAR_PATTERN, replace_match, prompt)
        content = [{"type": "text", "text": content_}]

        if len(image_column_names) > 0:
            if len(image_column_names) > 1:
                raise BadInputError("Only one image is supported per completion.")

            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self.img_column_dict[image_column_names[0]]},
                }
            )
            return content
        else:
            return content_

    def _check_upstream_error_chunk(self, content: str) -> None:
        matches = re.findall(GEN_CONFIG_VAR_PATTERN, content)
        if any([match in self.error_columns for match in matches]):
            raise Exception

    async def _execute_task_stream(self, task: Task) -> AsyncGenerator[str, None]:
        """
        Executes a single task in a streaming manner, returning an asynchronous generator of chunks.
        """
        output_column_name = task.output_column_name
        body: ChatRequest = task.body

        try:
            logger.debug(f"Processing column: {output_column_name}")
            self._check_upstream_error_chunk(body.messages[-1].content)
            body.messages[-1].content = self._interpolate_column(body.messages[-1].content)

            if isinstance(body.messages[-1].content, list):
                for input_column_name in self.dependencies[output_column_name]:
                    if input_column_name in self.img_column_dict:
                        try:
                            body.model = self.llm.validate_model_id(body.model, ["image"])
                            break
                        except ResourceNotFoundError as e:
                            raise BadInputError(
                                f'Column "{output_column_name}" referred to image file input but using a chat model '
                                f'"{self.llm.get_model_name(body.model) if self.llm.is_browser else body.model}", '
                                "select image model instead.",
                            ) from e

            if output_column_name in self.skip_regen_columns:
                new_column_value = self.column_dict[output_column_name]
                logger.debug(
                    f"Skipped regen for `{output_column_name}`, value: {new_column_value}"
                )
            elif output_column_name in self.file_columns:
                new_column_value = None
                logger.info(
                    f"Identified output column `{output_column_name}` as file type, set value to {new_column_value}"
                )

                chunk = GenTableStreamChatCompletionChunk(
                    id=self.request.state.id,
                    object="gen_table.completion.chunk",
                    created=int(time()),
                    model="",
                    usage=None,
                    choices=[
                        ChatCompletionChoiceDelta(
                            message=ChatEntry.assistant(new_column_value),
                            index=0,
                        )
                    ],
                    output_column_name=output_column_name,
                    row_id=self.row_id,
                )
                yield f"data: {chunk.model_dump_json()}\n\n"

            else:
                new_column_value = ""
                kwargs = body.model_dump()
                messages, references = await self.llm.retrieve_references(
                    messages=kwargs.pop("messages"),
                    rag_params=kwargs.pop("rag_params", None),
                    **kwargs,
                )
                if references is not None:
                    ref = GenTableStreamReferences(
                        **references.model_dump(exclude=["object"]),
                        output_column_name=output_column_name,
                    )
                    yield f"data: {ref.model_dump_json()}\n\n"
                async for chunk in self.llm.generate_stream(messages=messages, **kwargs):
                    new_column_value += chunk.text
                    chunk = GenTableStreamChatCompletionChunk(
                        **chunk.model_dump(exclude=["object"]),
                        output_column_name=output_column_name,
                        row_id=self.row_id,
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"
                    if chunk.finish_reason == "error":
                        self.error_columns.append(output_column_name)
                logger.info(
                    (
                        f"{self.request.state.id} - Streamed completion for "
                        f"{output_column_name}: <{mask_string(new_column_value)}>"
                    )
                )

        except Exception as e:
            error_chunk = GenTableStreamChatCompletionChunk(
                id=self.request.state.id,
                object="gen_table.completion.chunk",
                created=int(time()),
                model="",
                usage=None,
                choices=[
                    ChatCompletionChoiceDelta(
                        message=ChatEntry.assistant(f"[ERROR] {e}"),
                        index=0,
                        finish_reason="error",
                    )
                ],
                output_column_name=output_column_name,
                row_id=self.row_id,
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            new_column_value = error_chunk.text
            self.error_columns.append(output_column_name)
            self._log_exception(
                e, f'Error generating completion for column "{output_column_name}": {e}'
            )
        finally:
            # Append new column data for subsequent tasks
            self.column_dict[output_column_name] = new_column_value
            self.regen_column_dict[output_column_name] = new_column_value

    async def _execute_task_nonstream(self, task: Task):
        """
        Executes a single task in a non-streaming manner.
        """
        output_column_name = task.output_column_name
        body: ChatRequest = task.body

        try:
            body.messages[-1].content = self._interpolate_column(body.messages[-1].content)
        except IndexError:
            pass
        try:
            if isinstance(body.messages[-1].content, list):
                for input_column_name in self.dependencies[output_column_name]:
                    if input_column_name in self.img_column_dict:
                        body.model = self.llm.validate_model_id(body.model, ["image"])
                        break
            if output_column_name in self.skip_regen_columns:
                new_column_value = self.column_dict[output_column_name]
                response = ChatCompletionChunk(
                    id=self.request.state.id,
                    object="chat.completion.chunk",
                    created=int(time()),
                    model="",
                    usage=None,
                    choices=[
                        ChatCompletionChoiceDelta(
                            message=ChatEntry.assistant(new_column_value),
                            index=0,
                        )
                    ],
                )
                logger.debug(
                    f"Skipped regen for `{output_column_name}`, value: {new_column_value}"
                )
            elif output_column_name in self.file_columns:
                new_column_value = None
                response = ChatCompletionChunk(
                    id=self.request.state.id,
                    object="chat.completion.chunk",
                    created=int(time()),
                    model="",
                    usage=None,
                    choices=[
                        ChatCompletionChoiceDelta(
                            message=ChatEntry.assistant(new_column_value),
                            index=0,
                        )
                    ],
                )
                logger.info(
                    f"Identified output column `{output_column_name}` as file type, set value to {new_column_value}"
                )
            else:
                response = await self.llm.rag(**body.model_dump())
                new_column_value = response.text

            # append new column data for subsequence tasks
            self.column_dict[output_column_name] = new_column_value
            self.regen_column_dict[output_column_name] = new_column_value
            logger.info(
                (
                    f"{self.request.state.id} - Generated completion for {output_column_name}: "
                    f"<{mask_string(new_column_value)}>"
                )
            )
            return response

        except Exception as e:
            error_chunk = ChatCompletionChunk(
                id=self.request.state.id,
                object="gen_table.completion.chunk",
                created=int(time()),
                model="",
                usage=None,
                choices=[
                    ChatCompletionChoiceDelta(
                        message=ChatEntry.assistant(
                            f'[ERROR] Column "{output_column_name}" referred to image file input but using a chat model '
                            f'"{self.llm.get_model_name(body.model) if self.llm.is_browser else body.model}", '
                            "select image model instead.",
                        )
                        if isinstance(e, ResourceNotFoundError)
                        else ChatEntry.assistant(f"[ERROR] {e}"),
                        index=0,
                        finish_reason="error",
                    )
                ],
            )
            new_column_value = error_chunk.text
            self.column_dict[output_column_name] = new_column_value
            self.regen_column_dict[output_column_name] = new_column_value
            self._log_exception(
                e, f'Error generating completion for column "{output_column_name}": {e}'
            )
            return error_chunk

    def _setup_dependencies(self) -> None:
        """
        Sets up dependencies for the tasks.

        This method initializes the dependencies for the tasks that need to be executed. It creates a dictionary
        called `llm_tasks` where the keys are the output column names of the tasks and the values are the tasks themselves.
        It also creates a dictionary called `dependencies` where the keys are the output column names of the tasks and the
        values are the dependencies for each task. The dependencies are extracted from the content of the last message in the task's body.

        Examples:
            ```python
            # Example usage of _setup_dependencies method
            llm_tasks = {
                "task1_output": Task(...),
                "task2_output": Task(...),
                # ...
            }
            dependencies = {
                "task1_output": self._extract_upstream_columns(task1_body["messages"][-1]["content"]),
                "task2_output": self._extract_upstream_columns(task2_body["messages"][-1]["content"]),
                # ...
            }
            ```
        """
        self.llm_tasks = {
            task.output_column_name: task for task in self.tasks if task.type == "chat"
        }
        self.dependencies = {
            task.output_column_name: self._extract_upstream_columns(task.body.messages[-1].content)
            for task in self.llm_tasks.values()
        }
        logger.debug(f"Initial dependencies: {self.dependencies}")

        self.input_column_names = [
            key for key in self.column_dict.keys() if key not in self.llm_tasks.keys()
        ]

    def _mark_regen_columns(self) -> None:
        """
        Tag columns to regenerate based on the chosen regeneration strategy.
        """
        if self.is_row_add:
            return

        if self.body.regen_strategy == RegenStrategy.RUN_ALL:
            self.tag_regen_columns = self.llm_tasks.keys()

        elif self.body.regen_strategy == RegenStrategy.RUN_SELECTED:
            self.tag_regen_columns.append(self.body.output_column_id)

        elif self.body.regen_strategy in (
            RegenStrategy.RUN_BEFORE,
            RegenStrategy.RUN_AFTER,
        ):
            if self.body.regen_strategy == RegenStrategy.RUN_BEFORE:
                for column_name in self.column_dict.keys():
                    self.tag_regen_columns.append(column_name)
                    if column_name == self.body.output_column_id:
                        break
            else:  # RegenStrategy.RUN_AFTER
                reached_column = False
                for column_name in self.column_dict.keys():
                    if column_name == self.body.output_column_id:
                        reached_column = True
                    if reached_column:
                        self.tag_regen_columns.append(column_name)

        else:
            raise ValueError(f"Invalid regeneration strategy: {self.body.regen_strategy}")

        self.skip_regen_columns = [
            column_name
            for column_name in self.column_dict.keys()
            if column_name not in self.tag_regen_columns
        ]

    async def _nonstream_concurrent_execution(self) -> tuple[GenTableChatCompletionChunks, dict]:
        """
        Executes tasks in concurrent in a non-streaming manner, respecting dependencies.
        """
        self._setup_dependencies()
        self._mark_regen_columns()

        completed = set(self.input_column_names)
        tasks_in_progress = set()
        responses = {}

        async def execute_task(task_name):
            task = self.llm_tasks[task_name]
            try:
                responses[task_name] = await self._execute_task_nonstream(task)
            except Exception as e:
                self._log_exception(e, f'Error executing task "{task_name}": {e}')
            finally:
                completed.add(task_name)
                tasks_in_progress.remove(task_name)

        while len(completed) < (len(self.llm_tasks) + len(self.input_column_names)):
            ready_tasks = [
                task_name
                for task_name, deps in self.dependencies.items()
                if all(dep in completed for dep in deps)
                and task_name not in completed
                and task_name not in tasks_in_progress
            ]

            # Process tasks in batches
            for i in range(0, len(ready_tasks), self.cols_batch_size):
                batched_tasks = ready_tasks[i : i + self.cols_batch_size]
                exe_tasks = [execute_task(task) for task in batched_tasks]
                tasks_in_progress.update(batched_tasks)
                await asyncio.gather(*exe_tasks)
                completed.update(batched_tasks)
                tasks_in_progress.difference_update(batched_tasks)

        # Post-execution steps
        await self._run_embed_tasks()

        return (
            GenTableChatCompletionChunks(columns=responses, row_id=self.row_id),
            self.column_dict if self.is_row_add else self.regen_column_dict,
        )

    async def _stream_concurrent_execution(self) -> AsyncGenerator[str, None]:
        """
        Executes tasks concurrently in a streaming manner, yielding individual chunks.
        """
        self._setup_dependencies()
        self._mark_regen_columns()

        completed = set(self.input_column_names)
        queue = asyncio.Queue()
        tasks_in_progress = set()

        async def execute_task(task_name):
            task = self.llm_tasks[task_name]
            try:
                async for chunk in self._execute_task_stream(task):
                    await queue.put((task_name, chunk))
            except Exception as e:
                self._log_exception(e, f'Error executing task "{task_name}": {e}')
            finally:
                completed.add(task_name)
                await queue.put((task_name, None))
                tasks_in_progress.remove(task_name)

        while len(completed) < (len(self.llm_tasks) + len(self.input_column_names)):
            ready_tasks = [
                task_name
                for task_name, deps in self.dependencies.items()
                if all(dep in completed for dep in deps)
                and task_name not in completed
                and task_name not in tasks_in_progress
            ]

            # Process tasks in batches
            for i in range(0, len(ready_tasks), self.cols_batch_size):
                batch_tasks = ready_tasks[i : i + self.cols_batch_size]
                for task in batch_tasks:
                    tasks_in_progress.add(task)
                    asyncio.create_task(execute_task(task))

                none_count = 0
                while none_count < len(batch_tasks):
                    task_name, chunk = await queue.get()
                    if chunk is None:
                        none_count += 1
                        continue
                    yield chunk

        # Post-execution steps
        await self._run_embed_tasks()

        # Return the complete row for accumulation in MultiRowsGenExecutor
        yield self.column_dict if self.is_row_add else (self.body.row_id, self.regen_column_dict)

        # Signal the end of stream for a row
        yield "data: [DONE]\n\n"
