import asyncio
import re
from copy import deepcopy
from dataclasses import dataclass
from time import time
from typing import Any, AsyncGenerator

import numpy as np
from fastapi import Request
from loguru import logger
from uuid_extensions import uuid7str

from owl.db.gen_table import ChatTable, GenerativeTable
from owl.llm import LLMEngine
from owl.models import CloudEmbedder
from owl.protocol import (
    GEN_CONFIG_VAR_PATTERN,
    ChatCompletionChoiceDelta,
    ChatEntry,
    GenTableChatCompletionChunks,
    GenTableRowsChatCompletionChunks,
    GenTableStreamChatCompletionChunk,
    GenTableStreamReferences,
    RowAdd,
    RowAddRequest,
    RowRegen,
    RowRegenRequest,
    TableMeta,
)
from owl.utils import mask_string
from owl.utils.exceptions import ResourceNotFoundError


@dataclass(slots=True)
class Task:
    output_column_name: str
    body: dict
    is_embed: bool
    dtype: str


class MultiRowsGenExecutor:
    def __init__(
        self,
        table: GenerativeTable,
        request: Request,
        body: RowAddRequest | RowRegenRequest,
        rows_batch_size: int,
        cols_batch_size: int,
        openai_api_key: str = "",
        anthropic_api_key: str = "",
        gemini_api_key: str = "",
        cohere_api_key: str = "",
        groq_api_key: str = "",
        together_api_key: str = "",
        jina_api_key: str = "",
        voyage_api_key: str = "",
    ) -> None:
        self.table = table
        self.request = request
        self.body = body
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
                    stream=body.stream,
                    concurrent=body.concurrent,
                )
                for row_id in body.row_ids
            ]
        )
        self.rows_batch_size = rows_batch_size
        self.cols_batch_size = cols_batch_size
        self.openai_api_key = openai_api_key
        self.anthropic_api_key = anthropic_api_key
        self.gemini_api_key = gemini_api_key
        self.cohere_api_key = cohere_api_key
        self.groq_api_key = groq_api_key
        self.together_api_key = together_api_key
        self.jina_api_key = jina_api_key
        self.voyage_api_key = voyage_api_key

    def _create_executor(self, body_: RowAdd | RowRegen):
        self.executor = GenExecutor(
            table=self.table,
            request=self.request,
            body=body_,
            cols_batch_size=self.cols_batch_size,
            openai_api_key=self.openai_api_key,
            anthropic_api_key=self.anthropic_api_key,
            gemini_api_key=self.gemini_api_key,
            cohere_api_key=self.cohere_api_key,
            groq_api_key=self.groq_api_key,
            together_api_key=self.together_api_key,
            jina_api_key=self.jina_api_key,
            voyage_api_key=self.voyage_api_key,
        )
        # logger.debug(body_)

    async def _execute(self, body_, tmp_id=None) -> Any | GenTableChatCompletionChunks:
        self._create_executor(body_)
        if self.body.stream:
            try:
                async for chunk in await self.executor.gen_row():
                    await self.queue.put(chunk)
            except Exception:
                logger.exception(f"Error executing task {tmp_id}: {body_}")
                await self.queue.put("data: [DONE]\n\n")
        else:
            return await self.executor.gen_row()

    async def _gen_stream_rows(self):
        content_length = 0
        self.queue = asyncio.Queue()
        for i in range(0, len(self.bodies), self.rows_batch_size):
            batch_bodies = self.bodies[i : i + self.rows_batch_size]
            for i, body_ in enumerate(batch_bodies):
                asyncio.create_task(self._execute(body_, i))

            done_row_count = 0
            while done_row_count < len(batch_bodies):
                chunk = await self.queue.get()
                if chunk == "data: [DONE]\n\n":
                    done_row_count += 1
                content_length += len(chunk.encode("utf-8"))
                yield chunk
        self.request.state.billing_manager.create_egress_events(content_length / (1024**3))

    async def _gen_nonstream_rows(self):
        rows = []
        for i in range(0, len(self.bodies), self.rows_batch_size):
            batched_bodies = self.bodies[i : i + self.rows_batch_size]
            rows += await asyncio.gather(*[self._execute(body_) for body_ in batched_bodies])
        return GenTableRowsChatCompletionChunks(rows=rows)

    async def gen_rows(self) -> Any | GenTableChatCompletionChunks:
        if self.body.stream:
            return self._gen_stream_rows()
        else:
            return await self._gen_nonstream_rows()


class GenExecutor:
    def __init__(
        self,
        table: GenerativeTable,
        request: Request,
        body: RowAdd | RowRegen,
        cols_batch_size: int,
        openai_api_key: str = "",
        anthropic_api_key: str = "",
        gemini_api_key: str = "",
        cohere_api_key: str = "",
        groq_api_key: str = "",
        together_api_key: str = "",
        jina_api_key: str = "",
        voyage_api_key: str = "",
    ) -> None:
        self.table = table
        self.body = body
        self.is_row_add = isinstance(self.body, RowAdd)
        self.column_dict = {}
        self.regen_column_dict = {}
        self.tasks = []
        self.table_id = body.table_id
        self.request = request
        if isinstance(body, RowAdd):
            body.data["ID"] = body.data.get("ID", uuid7str())
            self.row_id = body.data["ID"]
        else:
            self.row_id = body.row_id
        self.is_chat = isinstance(self.table, ChatTable)
        self.cols_batch_size = cols_batch_size
        self.llm = LLMEngine(
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            gemini_api_key=gemini_api_key,
            cohere_api_key=cohere_api_key,
            groq_api_key=groq_api_key,
            together_api_key=together_api_key,
            jina_api_key=jina_api_key,
            voyage_api_key=voyage_api_key,
        )
        self.openai_api_key = openai_api_key
        self.anthropic_api_key = anthropic_api_key
        self.gemini_api_key = gemini_api_key
        self.cohere_api_key = cohere_api_key
        self.groq_api_key = groq_api_key
        self.together_api_key = together_api_key
        self.jina_api_key = jina_api_key
        self.voyage_api_key = voyage_api_key
        self.error_columns = []

    async def gen_row(self) -> Any | GenTableChatCompletionChunks:
        with self.table.create_session() as session:
            meta = session.get(TableMeta, self.table_id)

        col_ids = set(c["id"] for c in meta.cols)
        if self.is_row_add:
            self.column_dict = {k: v for k, v in self.body.data.items() if k in col_ids}
        else:
            self.column_dict = self.table.get_row(self.table_id, self.row_id)

        self.tasks = []
        for col in meta.cols:
            gen_config = deepcopy(col["gen_config"])
            col_id = col["id"]
            # Skip info columns
            if col_id.lower() in ("id", "updated at"):
                continue
            # Skip state column
            if col_id.endswith("_"):
                continue
            # If user provides value, skip
            if self.is_row_add and col_id in self.column_dict:
                continue
            # If gen_config not defined, set None and skip
            if gen_config is None:
                if self.is_row_add:
                    self.column_dict[col_id] = None
                continue
            if self.is_chat and col_id.lower() == "ai":
                messages = self.table.get_conversation_thread(
                    table_id=self.table_id,
                    row_id="" if self.is_row_add else self.row_id,
                    include=False,
                ).thread
                user_message = self.column_dict["User"]
                messages.append(ChatEntry.user(content=user_message if user_message else "."))
                if len(messages) == 0:
                    continue
                gen_config["messages"] = [m.model_dump() for m in messages]
            self.tasks.append(
                Task(col_id, gen_config, is_embed=col["vlen"] > 0, dtype=col["dtype"])
            )

        column_dict_keys = set(self.column_dict.keys())
        if len(column_dict_keys - col_ids) > 0:
            raise ValueError(f"There are unexpected columns: {column_dict_keys - col_ids}")

        if self.body.stream:
            if self.body.concurrent:
                return self._stream_concurrent_execution()
            else:
                return self._stream_sequent_execution()
        else:
            if self.body.concurrent:
                return await self._nonstream_concurrent_execution()
            else:
                return await self._nonstream_sequent_execution()

    def _run_embed_tasks(self):
        """
        Executes embedding tasks sequentially.
        """
        embed_tasks = [task for task in self.tasks if task.is_embed is True]
        for task in embed_tasks:
            output_column_name = task.output_column_name
            body = task.body
            embedding_model = body["embedding_model"]
            embedder = CloudEmbedder(
                embedder_name=embedding_model,
                openai_api_key=self.openai_api_key,
                anthropic_api_key=self.anthropic_api_key,
                gemini_api_key=self.gemini_api_key,
                cohere_api_key=self.cohere_api_key,
                groq_api_key=self.groq_api_key,
                together_api_key=self.together_api_key,
                jina_api_key=self.jina_api_key,
                voyage_api_key=self.voyage_api_key,
            )
            source = self.column_dict[body["source_column"]]
            embedding = embedder.embed_documents(texts=["." if source is None else source])
            embedding = np.asarray(embedding.data[0].embedding, dtype=task.dtype)
            embedding = embedding / np.linalg.norm(embedding)
            self.column_dict[output_column_name] = embedding
            self.regen_column_dict[output_column_name] = embedding

    @staticmethod
    def _log_item(x: Any) -> str:
        if isinstance(x, np.ndarray):
            return f"array(shape={x.shape}, dtype={x.dtype})"
        elif isinstance(x, str):
            return mask_string(x)
        else:
            return f"type={type(x)}"

    def _write_to_table(self):
        """
        Writes the generated data to the table.
        """
        with self.table.create_session() as session:
            if self.is_row_add:
                _data = {k: self._log_item(v) for k, v in self.column_dict.items()}
                logger.info(
                    (
                        f"{self.request.state.id} - Writing row to table '{self.table_id}': "
                        f"{_data}"
                    )
                )
                try:
                    self.table.add_rows(session, self.table_id, [self.column_dict])
                except Exception:
                    _data = [
                        {
                            k: (
                                {"type": type(v), "shape": v.shape, "dtype": v.dtype}
                                if isinstance(v, np.ndarray)
                                else v
                            )
                        }
                        for k, v in self.column_dict.items()
                    ]
                    logger.exception((f"{self.request.state.id} - Error adding rows {[_data]}"))
            else:
                _data = {k: self._log_item(v) for k, v in self.regen_column_dict.items()}
                logger.info(
                    (
                        f"{self.request.state.id} - Updating row of table '{self.table_id}': "
                        f"{_data}"
                    )
                )
                try:
                    self.table.update_rows(
                        session,
                        self.table_id,
                        where=f"`ID` = '{self.body.row_id}'",
                        values=self.regen_column_dict,
                    )
                except Exception:
                    logger.exception(
                        f"{self.request.state.id} - Error update rows, where `ID` = '{self.body.row_id}', "
                        f"values: {self.regen_column_dict}"
                    )

    def _extract_upstream_columns(self, text: str) -> list[str]:
        matches = re.findall(GEN_CONFIG_VAR_PATTERN, text)
        # return the content inside ${...}
        return matches

    def _substitute_data(self, content: str) -> dict[str, Any]:
        """
        Substitutes placeholders in the content with actual column values.

        Args:
            content (str): The content with placeholders.

        Returns:
            dict[str, Any]: The content with placeholders replaced.
        """

        def replace_match(match):
            key = match.group(1)  # Extract the key from the match
            try:
                return str(self.column_dict[key])  # Data can be non-string
            except KeyError:
                raise KeyError(f"Requested column '{key}' not found.")

        return re.sub(GEN_CONFIG_VAR_PATTERN, replace_match, content)

    def _check_upstream_error_chunk(self, content: str) -> Exception:
        matches = re.findall(GEN_CONFIG_VAR_PATTERN, content)

        if any([match in self.error_columns for match in matches]):
            raise Exception
        else:
            pass

    async def _execute_task_stream(self, task: Task) -> AsyncGenerator[str, None]:
        """
        Executes a single task in a streaming manner, returning an asynchronous generator.
        """
        output_column_name = task.output_column_name
        body = task.body
        body["id"] = self.request.state.id

        try:
            logger.debug(f"Processing column: {output_column_name}")
            self._check_upstream_error_chunk(body["messages"][-1]["content"])

            body["messages"][-1]["content"] = self._substitute_data(
                body["messages"][-1]["content"]
            )
            new_column_value = ""
            messages, references = await self.llm.retrieve_references(
                request=self.request,
                messages=body.pop("messages"),
                rag_params=body.pop("rag_params", None),
                **body,
            )
            if references is not None:
                ref = GenTableStreamReferences(
                    **references.model_dump(exclude=["object"]),
                    output_column_name=output_column_name,
                )
                yield f"data: {ref.model_dump_json()}\n\n"
            async for chunk in self.llm.generate_stream(
                request=self.request,
                messages=messages,
                **body,
            ):
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

        except Exception as exc:
            error_chunk = GenTableStreamChatCompletionChunk(
                id=self.request.state.id,
                object="gen_table.completion.chunk",
                created=int(time()),
                model="",
                usage=None,
                choices=[
                    ChatCompletionChoiceDelta(
                        message=ChatEntry.assistant(f"[ERROR] {exc}"),
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
            logger.exception(f"{self.request.state.id} - LLM generation failed for column: {task}")
        finally:
            # Append new column data for subsequence tasks
            self.column_dict[output_column_name] = new_column_value
            self.regen_column_dict[output_column_name] = new_column_value

    async def _execute_task_nonstream(self, task: Task):
        """
        Executes a single task in a non-streaming manner.
        """
        output_column_name = task.output_column_name
        body = task.body
        body["id"] = self.request.state.id

        try:
            body["messages"][-1]["content"] = self._substitute_data(
                body["messages"][-1]["content"]
            )
        except (IndexError, KeyError):
            pass
        try:
            response = await self.llm.rag(request=self.request, **body)
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

        except Exception:
            logger.exception(f"LLM generation failed for column: {task}")
            raise

    async def _stream_sequent_execution(self) -> AsyncGenerator[str, None]:
        """
        Executes tasks sequentially in a streaming manner.
        """
        llm_tasks = [task for task in self.tasks if not task.is_embed]
        for task in llm_tasks:
            async for chunk in self._execute_task_stream(task):
                yield chunk
        yield "data: [DONE]\n\n"
        self._run_embed_tasks()
        self._write_to_table()

    async def _nonstream_sequent_execution(self) -> GenTableChatCompletionChunks:
        """
        Executes tasks sequentially in a non-streaming manner.
        """
        responses = {}
        llm_tasks = [task for task in self.tasks if not task.is_embed]

        for task in llm_tasks:
            responses[task.output_column_name] = await self._execute_task_nonstream(task)

        self._run_embed_tasks()
        self._write_to_table()
        return GenTableChatCompletionChunks(columns=responses, row_id=self.row_id)

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
            task.output_column_name: task for task in self.tasks if not task.is_embed
        }
        self.dependencies = {
            task.output_column_name: self._extract_upstream_columns(
                task.body["messages"][-1]["content"]
            )
            for task in self.llm_tasks.values()
        }
        logger.debug(f"Initial dependencies: {self.dependencies}")

        self.input_column_names = [
            key for key in self.column_dict.keys() if key not in self.llm_tasks.keys()
        ]

    async def _nonstream_concurrent_execution(self) -> GenTableChatCompletionChunks:
        """
        Executes tasks in concurrent in a non-streaming manner, respecting dependencies.
        """
        self._setup_dependencies()

        completed = set(self.input_column_names)
        tasks_in_progress = set()
        responses = {}

        async def execute_task(task_name):
            task = self.llm_tasks[task_name]
            try:
                responses[task_name] = await self._execute_task_nonstream(task)
            except Exception:
                logger.exception(f"Error executing task: {task}")
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
                exetasks = [execute_task(task) for task in batched_tasks]
                tasks_in_progress.update(batched_tasks)
                await asyncio.gather(*exetasks)
                completed.update(batched_tasks)
                tasks_in_progress.difference_update(batched_tasks)

        # Post-execution steps
        self._run_embed_tasks()
        self._write_to_table()
        return GenTableChatCompletionChunks(columns=responses, row_id=self.row_id)

    async def _stream_concurrent_execution(self) -> AsyncGenerator[str, None]:
        """
        Executes tasks in concurrent in a streaming manner, respecting dependencies.
        """
        self._setup_dependencies()

        completed = set(self.input_column_names)
        queue = asyncio.Queue()
        tasks_in_progress = set()

        async def execute_task(task_name):
            task = self.llm_tasks[task_name]
            try:
                async for chunk in self._execute_task_stream(task):
                    await queue.put((task_name, chunk))
            except Exception:
                logger.exception(f"Error executing task: {task}")
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

        yield "data: [DONE]\n\n"

        # Post-execution steps
        self._run_embed_tasks()
        self._write_to_table()
