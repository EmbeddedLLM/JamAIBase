import base64
import re
from asyncio import Queue, TaskGroup
from collections import defaultdict, deque
from os.path import basename, splitext
from time import perf_counter, time
from typing import Any, AsyncGenerator, Literal, Sequence

import numpy as np
from async_lru import alru_cache
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from loguru import logger
from pydantic import BaseModel

from owl.configs import ENV_CONFIG
from owl.db.gen_table import (
    ColumnMetadata,
    GenerativeTableCore,
    KnowledgeTable,
)
from owl.docparse import GeneralDocLoader
from owl.types import (
    AUDIO_FILE_EXTENSIONS,
    DOCUMENT_FILE_EXTENSIONS,
    GEN_CONFIG_VAR_PATTERN,
    IMAGE_FILE_EXTENSIONS,
    AudioContent,
    AudioContentData,
    CellCompletionResponse,
    CellReferencesResponse,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatEntry,
    ChatRequest,
    ChatRole,
    ChatThreadEntry,
    Chunk,
    CodeGenConfig,
    ColumnDtype,
    DiscriminatedGenConfig,
    EmbedGenConfig,
    ImageContent,
    ImageContentData,
    LLMGenConfig,
    MultiRowAddRequest,
    MultiRowCompletionResponse,
    MultiRowRegenRequest,
    OrganizationRead,
    ProjectRead,
    PythonGenConfig,
    References,
    RegenStrategy,
    RowAdd,
    RowCompletionResponse,
    RowRegen,
    TextContent,
)
from owl.utils import mask_string, uuid7_draft2_str
from owl.utils.billing import BillingManager
from owl.utils.code import code_executor
from owl.utils.concurrency import determine_concurrent_batches
from owl.utils.exceptions import (
    BadInputError,
    JamaiException,
    ResourceNotFoundError,
    UpStreamError,
)
from owl.utils.io import open_uri_async
from owl.utils.lm import LMEngine


class Task(BaseModel, validate_assignment=True):
    output_column_name: str
    dtype: str
    body: DiscriminatedGenConfig
    status: Literal["pending", "running", "done"] = "pending"


class Result(BaseModel, validate_assignment=True):
    row_id: str


class TaskResult(Result):
    response: CellReferencesResponse | CellCompletionResponse | ChatCompletionResponse
    output_column_name: str


class RowResult(Result):
    data: dict[str, Any]


ResultT = TaskResult | RowResult


class _Executor:
    def __init__(
        self,
        *,
        request: Request,
        table: GenerativeTableCore,
        organization: OrganizationRead,
        project: ProjectRead,
        body: MultiRowAddRequest | MultiRowRegenRequest | RowAdd | RowRegen,
        col_batch_size: int,
        row_batch_size: int,
    ) -> None:
        self.request = request
        self._request_id: str = request.state.id
        self.table = table
        self._table_id = table.table_id
        self._col_map = {c.column_id: c for c in self.table.column_metadata}
        self.organization = organization
        self.project = project
        if body.table_id != table.table_id:
            raise ValueError(f"{body.table_id=} but {table.table_id=}")
        self.body = body
        self._stream = self.body.stream

        self._multi_turn = (
            sum(getattr(col.gen_config, "multi_turn", False) for col in table.column_metadata) > 0
        )
        self._col_batch_size = col_batch_size
        self._row_batch_size = row_batch_size

    @classmethod
    def _log(cls, msg: str, level: str = "INFO", request_id: str = "", **kwargs):
        _log = f"{cls.__name__}: {msg}"
        if request_id:
            _log = f"{request_id} - {_log}"
        logger.log(level, _log, **kwargs)

    def log(self, msg: str, level: str = "INFO", **kwargs):
        self._log(msg, level, request_id=self._request_id, **kwargs)

    def log_exception(self, message: str, exc: Exception, **kwargs) -> None:
        if isinstance(exc, (JamaiException, RequestValidationError)):
            logger.info(f"{self._request_id} - {self.__class__.__name__}: {message}", **kwargs)
        else:
            logger.exception(
                f"{self._request_id} - {self.__class__.__name__}: {message}", **kwargs
            )

    @staticmethod
    def _log_item(x: Any) -> str:
        if isinstance(x, np.ndarray):
            return f"array(shape={x.shape}, dtype={x.dtype})"
        elif isinstance(x, str):
            return mask_string(x)
        else:
            return f"type={type(x)}"

    @staticmethod
    def _parse_prompt_dependencies(prompt: str | None) -> list[str]:
        if not prompt:
            return []
        return re.findall(GEN_CONFIG_VAR_PATTERN, prompt)

    def _extract_upstream_columns(self, prompt: str | None) -> list[str]:
        return self._parse_prompt_dependencies(prompt)

    def _extract_all_upstream_columns(self, output_column_name: str) -> list[str]:
        return self._extract_all_upstream_columns_from(
            self.table.column_metadata, output_column_name
        )

    @staticmethod
    def _extract_all_upstream_columns_from(
        columns: Sequence[ColumnMetadata], output_column_name: str
    ) -> list[str]:
        try:
            idx = next(i for i, c in enumerate(columns) if c.column_id == output_column_name)
        except StopIteration:
            return []
        return [
            c.column_id
            for c in columns[:idx]
            if not (c.is_info_column or c.is_state_column or c.is_vector_column)
        ]

    @classmethod
    def _collect_column_dependencies(
        cls,
        column: ColumnMetadata,
        *,
        columns: Sequence[ColumnMetadata],
        output_column_ids: set[str],
    ) -> list[str]:
        gen_config = column.gen_config
        if gen_config is None:
            return []

        dependencies: list[str]
        if isinstance(gen_config, PythonGenConfig):
            dependencies = cls._extract_all_upstream_columns_from(columns, column.column_id)
        elif isinstance(gen_config, (CodeGenConfig, EmbedGenConfig)):
            dependencies = [gen_config.source_column]
        elif isinstance(gen_config, LLMGenConfig):
            dependencies = cls._parse_prompt_dependencies(gen_config.prompt)
        else:
            dependencies = []

        return [dep for dep in dependencies if dep in output_column_ids]

    @classmethod
    def build_dependency_levels(cls, columns: Sequence[ColumnMetadata]) -> list[list[str]]:
        output_columns = [col for col in columns if col.is_output_column]
        if not output_columns:
            return []

        adjacency: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = defaultdict(int)
        output_column_ids = {col.column_id for col in output_columns}

        for column in output_columns:
            in_degree[column.column_id] = 0

        for column in output_columns:
            dependencies = cls._collect_column_dependencies(
                column,
                columns=columns,
                output_column_ids=output_column_ids,
            )
            for dep in dependencies:
                adjacency[dep].append(column.column_id)
                in_degree[column.column_id] += 1

        queue = deque([col.column_id for col in output_columns if in_degree[col.column_id] == 0])
        levels: list[list[str]] = []

        while queue:
            current_level = list(queue)
            levels.append(current_level)
            queue = deque()

            for col_id in current_level:
                for dependent in adjacency[col_id]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        return levels

    @classmethod
    def get_max_concurrent_columns(cls, columns: Sequence[ColumnMetadata]) -> int:
        dependency_levels = cls.build_dependency_levels(columns)
        if not dependency_levels:
            return 1
        return max(len(level) for level in dependency_levels)


class MultiRowGenExecutor(_Executor):
    def __init__(
        self,
        *,
        request: Request,
        table: GenerativeTableCore,
        organization: OrganizationRead,
        project: ProjectRead,
        body: MultiRowAddRequest | MultiRowRegenRequest,
    ) -> None:
        concurrent = body.concurrent
        multi_turn = (
            sum(getattr(col.gen_config, "multi_turn", False) for col in table.column_metadata) > 0
        )
        max_concurrent_cols = self.get_max_concurrent_columns(table.column_metadata)
        col_batch_size, row_batch_size = determine_concurrent_batches(
            columns=table.column_metadata,
            body=body,
            concurrent=concurrent,
            multi_turn=multi_turn,
            cell_limit=ENV_CONFIG.concurrent_cell_batch_size,
            max_concurrent_cols=max_concurrent_cols,
        )

        _context = dict(
            request=request,
            table=table,
            organization=organization,
            project=project,
        )
        super().__init__(
            body=body,
            col_batch_size=col_batch_size,
            row_batch_size=row_batch_size,
            **_context,
        )
        self.log(
            (
                "Concurrency plan determined: "
                f"columns={col_batch_size}, rows={row_batch_size}, multi_turn={multi_turn}, concurrent={concurrent}"
            ),
            level="DEBUG",
            columns=col_batch_size,
            rows=row_batch_size,
            multi_turn=multi_turn,
            concurrent=concurrent,
        )

        # Store pre-computed sizes for child executors
        self._col_batch_size = col_batch_size
        self._row_batch_size = row_batch_size

        # Executors
        if isinstance(body, MultiRowAddRequest):
            self._is_regen = False
            self._executors = [
                GenExecutor(
                    body=RowAdd(
                        table_id=body.table_id,
                        data=row_data,
                        stream=body.stream,
                        concurrent=body.concurrent,
                    ),
                    col_batch_size=self._col_batch_size,
                    row_batch_size=self._row_batch_size,
                    **_context,
                )
                for row_data in body.data
            ]
        else:
            self._is_regen = True
            self._executors = [
                GenExecutor(
                    body=RowRegen(
                        table_id=body.table_id,
                        row_id=row_id,
                        regen_strategy=body.regen_strategy,
                        output_column_id=body.output_column_id,
                        stream=body.stream,
                        concurrent=body.concurrent,
                    ),
                    col_batch_size=self._col_batch_size,
                    row_batch_size=self._row_batch_size,
                    **_context,
                )
                for row_id in body.row_ids
            ]
        # Determine write batch size
        if self._multi_turn:
            self._write_batch_size = 1
        else:
            # Write batch size will be [10, max_write_batch_size]
            _bs = len(self._executors) // 10
            self._write_batch_size = max(min(_bs, ENV_CONFIG.max_write_batch_size), 10)
        # Task result queue
        self._queue: Queue[ResultT | None] = Queue()
        # Accumulated rows for batch write
        self._batch_rows: list[dict[str, Any]] = []
        # Billing
        self.content_length = 0
        self._billing: BillingManager = self.request.state.billing

    async def generate(self) -> AsyncGenerator[str, None] | MultiRowCompletionResponse:
        if self._stream:
            return self._generate()
        else:
            return await anext(self._generate())

    async def _generate(self) -> AsyncGenerator[str | MultiRowCompletionResponse, None]:
        rows = {
            exe.row_id: RowCompletionResponse(columns={}, row_id=exe.row_id)
            for exe in self._executors
        }
        async with TaskGroup() as tg:
            pending_executors = [exe for exe in self._executors]
            while len(pending_executors) > 0:
                _execs = pending_executors[: self._row_batch_size]
                for exe in _execs:
                    tg.create_task(exe.generate(self._queue))
                done_rows = 0
                while done_rows < len(_execs):
                    res = await self._queue.get()
                    self.log(
                        "len(_execs)={a} done_rows={b}  res={c}",
                        "DEBUG",
                        a=len(_execs),
                        b=done_rows,
                        c=res,
                    )
                    if res is None:
                        pass
                    elif isinstance(res, TaskResult):
                        # logger.debug(f"{res.response.content=}")
                        if self._stream:
                            _sse = f"data: {res.response.model_dump_json()}\n\n"
                            self.content_length += len(_sse.encode("utf-8"))
                            yield _sse
                        else:
                            rows[res.row_id].columns[res.output_column_name] = res.response
                    else:
                        self._batch_rows.append(res.data)
                        if len(self._batch_rows) >= self._write_batch_size:
                            await self._write_rows_to_table()
                        done_rows += 1
                pending_executors = pending_executors[self._row_batch_size :]
        # Write any remaining rows
        await self._write_rows_to_table()
        # End of all tasks
        if self._stream:
            _sse = "data: [DONE]\n\n"
            yield _sse
            self.content_length += len(_sse.encode("utf-8"))
            self._billing.create_egress_events(self.content_length / (1024**3))
        else:
            yield MultiRowCompletionResponse(rows=list(rows.values()))

    async def _write_rows_to_table(self) -> None:
        """
        Writes accumulated rows to the table in batches.
        """
        if len(self._batch_rows) == 0:
            return
        if self._is_regen:
            self.log(f'Table "{self._table_id}": Updating {len(self._batch_rows):,d} rows.')
            try:
                await self.table.update_rows(
                    {row["ID"]: row for row in self._batch_rows}, ignore_state_columns=False
                )
            except Exception as e:
                _data = [
                    {k: self._log_item(v) for k, v in row.items()} for row in self._batch_rows
                ]
                self.log_exception(
                    f'Table "{self._table_id}": Failed to update {len(self._batch_rows):,d} rows: {_data}',
                    e,
                )
        else:
            self.log(f'Table "{self._table_id}": Writing {len(self._batch_rows):,d} rows.')
            try:
                await self.table.add_rows(
                    self._batch_rows, ignore_info_columns=False, ignore_state_columns=False
                )
            except Exception as e:
                _data = [
                    {k: self._log_item(v) for k, v in row.items()} for row in self._batch_rows
                ]
                self.log_exception(
                    f'Table "{self._table_id}": Failed to add {len(self._batch_rows):,d} rows: {_data}',
                    e,
                )
        self._batch_rows.clear()


class GenExecutor(_Executor):
    def __init__(
        self,
        *,
        request: Request,
        table: GenerativeTableCore,
        organization: OrganizationRead,
        project: ProjectRead,
        body: RowAdd | RowRegen,
        col_batch_size: int,
        row_batch_size: int,
    ) -> None:
        super().__init__(
            request=request,
            table=table,
            organization=organization,
            project=project,
            body=body,
            col_batch_size=col_batch_size,
            row_batch_size=row_batch_size,
        )

        # Engines
        self.lm = LMEngine(organization=organization, project=project, request=request)
        # Tasks
        self._tasks: list[Task] = []
        if isinstance(self.body, RowAdd):
            self.body.data["ID"] = uuid7_draft2_str()
            self.body.data.pop("Updated at", None)
            self._row_id = self.body.data["ID"]
            self._regen_strategy = None
        else:
            self._row_id = self.body.row_id
            self._regen_strategy = self.body.regen_strategy
            if not self.body.output_column_id:
                if self._regen_strategy != RegenStrategy.RUN_ALL:
                    raise BadInputError(
                        f'`output_column_id` is required when `regen_strategy` is not "{str(RegenStrategy.RUN_ALL)}".'
                    )
            else:
                output_column_ids = [
                    col.column_id for col in self.table.column_metadata if col.is_output_column
                ]
                if self.body.output_column_id not in output_column_ids:
                    output_column_ids = [f'"{c}"' for c in output_column_ids]
                    raise ResourceNotFoundError(
                        (
                            f'Column "{self.body.output_column_id}" not found in table "{self._table_id}". '
                            f"Available output columns: {output_column_ids}"
                        )
                    )
        self._column_dict: dict[str, Any] = {}
        self._error_columns: list[str] = []
        self._task_signal: Queue[None] = Queue()

    @property
    def row_id(self) -> str:
        return self._row_id

    @property
    def tasks(self) -> list[Task]:
        return self._tasks

    @property
    def column_dict(self) -> dict[str, Any]:
        return self._column_dict

    # @property
    # def done(self) -> bool:
    #     return all(task.status == "done" for task in self._tasks)

    async def _setup_tasks(self) -> None:
        cols = self.table.column_metadata
        # Process inputs and dependencies
        if self._regen_strategy is None:
            _body: RowAdd = self.body
            self._column_dict = {
                k: v for k, v in _body.data.items() if k in self._col_map and not k.endswith("_")
            }
        else:
            _body: RowRegen = self.body
            _row = await self.table.get_row(self._row_id)
            match self._regen_strategy:
                case RegenStrategy.RUN_ALL:
                    # Keep all input columns
                    self._column_dict = {
                        k: v
                        for k, v in _row.items()
                        if not (
                            self._col_map[k].is_output_column
                            or self._col_map[k.rstrip("_")].is_output_column
                        )
                    }
                case RegenStrategy.RUN_SELECTED:
                    # Keep all columns except the one being generated
                    self._column_dict = {
                        k: v
                        for k, v in _row.items()
                        if k not in (_body.output_column_id, f"{_body.output_column_id}_")
                    }
                case RegenStrategy.RUN_BEFORE | RegenStrategy.RUN_AFTER:
                    _cols = [col.column_id for col in cols if col.is_output_column]
                    try:
                        idx = _cols.index(_body.output_column_id)
                    except ValueError as e:
                        raise BadInputError(
                            f'Column "{_body.output_column_id}" not found in table "{self._table_id}".'
                        ) from e
                    # Keep columns that are not being generated
                    if self._regen_strategy == RegenStrategy.RUN_BEFORE:
                        _cols = _cols[idx + 1 :]
                    else:
                        _cols = _cols[:idx]
                    _cols += [f"{c}_" for c in _cols]
                    _cols += [col.column_id for col in cols if not col.is_output_column]
                    self._column_dict = {
                        k: v for k, v in _row.items() if k in _cols or k.lower() == "id"
                    }
                case _:
                    raise BadInputError(f'Invalid regen strategy: "{str(self._regen_strategy)}".')
        # # Filter out state columns
        # self._column_dict = {k: v for k, v in self._column_dict.items() if not k.endswith("_")}
        self.log("self._column_dict={column_dict}", "DEBUG", column_dict=self._column_dict)

        self._tasks = []
        for col in cols:
            # Skip info and state columns
            if col.is_info_column or col.is_state_column:
                continue
            # Create task
            if col.gen_config is None:
                # Default value for missing column during row add
                # Even though this is also handled by `GenerativeTableCore`,
                # we need this to avoid hanging tasks due to missing inputs
                self._column_dict[col.column_id] = self._column_dict.get(col.column_id)
                continue
            if col.column_id in self._column_dict:
                self.log(f'Skipped generation for column "{col.column_id}".')
                continue
            self._tasks.append(
                Task(
                    output_column_name=col.column_id,
                    dtype=col.dtype,
                    body=col.gen_config,
                )
            )
        self.log("self._tasks={tasks}", "DEBUG", tasks=self._tasks)
        column_dict_keys = set(self._column_dict.keys())
        col_ids = set(self._col_map.keys())
        if len(column_dict_keys - col_ids) > 0:
            logger.warning(
                f'Table "{self._table_id}": There are unexpected columns: {column_dict_keys - col_ids}'
            )
        self.log(f"Prepared {len(self._tasks):,d} tasks.", "DEBUG")

    async def generate(self, q: Queue[ResultT | None]) -> None:
        await self._setup_tasks()
        async with TaskGroup() as tg:
            pending_tasks = [task for task in self._tasks if task.status == "pending"]
            self.log("Pending tasks: {pending_tasks}", "DEBUG", pending_tasks=pending_tasks)
            while len(pending_tasks) > 0:
                # Go through pending tasks
                ready_tasks = [task for task in pending_tasks if self._is_task_ready(task)]
                for task in ready_tasks[: self._col_batch_size]:
                    if not self._is_task_ready(task):
                        continue
                    task.status = "running"
                    tg.create_task(self._execute_task(task, q))
                # Wait for a task to complete
                await self._task_signal.get()
                pending_tasks = [task for task in self._tasks if task.status == "pending"]
                self.log("Pending tasks: {pending_tasks}", "DEBUG", pending_tasks=pending_tasks)
        # Put row data
        await q.put(RowResult(data=self._column_dict, row_id=self._row_id))
        self.log("All tasks completed.", "DEBUG")

    def _is_task_ready(self, task: Task) -> bool:
        match task.body:
            case LLMGenConfig():
                inputs = self._extract_upstream_columns(task.body.prompt)
            case EmbedGenConfig() | CodeGenConfig():
                inputs = [task.body.source_column]
            case PythonGenConfig():
                inputs = self._extract_all_upstream_columns(task.output_column_name)
            case _:
                raise ValueError(f'Table "{self._table_id}": Unexpected task type: {task.body}')
        # Only consider input references that exist in table
        inputs = [i for i in inputs if i in self._col_map]
        task_ready = all(col in self._column_dict for col in inputs)
        return task_ready

    async def _execute_task(self, task: Task, q: Queue[ResultT | None]) -> None:
        logger.debug(f"Processing column: {task.output_column_name}")
        match task.body:
            case LLMGenConfig():
                await self._execute_chat_task(task, q)
            case EmbedGenConfig():
                await self._execute_embed_task(task, q)
            case CodeGenConfig():
                await self._execute_code_task(task, q)
            case PythonGenConfig():
                await self._execute_python_task(task, q)
            case _:
                raise ValueError(f'Table "{self._table_id}": Unexpected task type: {task.body}')

    async def _execute_chat_task(self, task: Task, q: Queue[ResultT | None]) -> None:
        output_column = task.output_column_name
        body: LLMGenConfig = task.body
        # Check if a value is provided
        try:
            # TODO: Perhaps we need to emit references too
            result = self._column_dict[output_column]
            # response_kwargs = dict(
            #     id=self._request_id,
            #     created=int(time()),
            #     model="",
            #     usage=ChatCompletionUsage(),
            #     choices=[
            #         ChatCompletionChoice(
            #             message=ChatCompletionMessage(content=result),
            #             index=0,
            #         )
            #     ],
            # )
            # if self._stream:
            #     response = CellCompletionResponse(
            #         **response_kwargs,
            #         output_column_name=output_column,
            #         row_id=self._row_id,
            #     )
            # else:
            #     response = ChatCompletionResponse(**response_kwargs)
            # self.log(f'Skipped completion for column "{output_column}".')
            # if self._regen_strategy is not None:
            #     # TODO: Perhaps we should always emit column value even if it is provided?
            #     await q.put(
            #         TaskResult(
            #             response=response,
            #             output_column_name=output_column,
            #             row_id=self._row_id,
            #         )
            #     )
            await q.put(None)
            await self._signal_task_completion(task, result)
            return
        except KeyError:
            pass

        # Perform completion
        result = ""
        reasoning = ""
        references = None
        reasoning_time = None
        try:
            # Error circuit breaker
            self._check_upstream_error(self._extract_upstream_columns(body.prompt))
            # Form the request body
            if body.multi_turn:
                messages = (
                    await self.table.get_conversation_thread(
                        column_id=output_column,
                        row_id="" if self._regen_strategy is None else self._row_id,
                        include_row=False,
                    )
                ).thread
            else:
                messages = [ChatThreadEntry.system(body.system_prompt)]
            messages.append(
                ChatThreadEntry.user(
                    content=self.table.interpolate_column(
                        body.prompt if body.prompt else ".", self._column_dict
                    )
                )
            )
            # Load files for each user message
            messages = [await self._load_files(m) for m in messages]
            req = ChatRequest(
                id=self._request_id,
                messages=[ChatEntry.model_validate(m.model_dump()) for m in messages],
                **body.model_dump(),
            )
            req, references = await self._setup_rag(req)
            if self._stream:
                if references is not None:
                    ref = CellReferencesResponse(
                        **references.model_dump(exclude=["object"]),
                        output_column_name=output_column,
                        row_id=self._row_id,
                    )
                    await q.put(
                        TaskResult(
                            response=ref,
                            output_column_name=output_column,
                            row_id=self._row_id,
                        )
                    )

                t0 = perf_counter()
                async for chunk in self.lm.chat_completion_stream(
                    messages=req.messages,
                    **req.hyperparams,
                ):
                    reasoning += chunk.reasoning_content
                    result += chunk.content
                    if chunk.content and reasoning_time is None:
                        reasoning_time = perf_counter() - t0
                    # if chunk.content is None and chunk.usage is None:
                    #     continue
                    chunk = CellCompletionResponse(
                        **chunk.model_dump(exclude={"object"}),
                        output_column_name=output_column,
                        row_id=self._row_id,
                    )
                    await q.put(
                        TaskResult(
                            response=chunk,
                            output_column_name=output_column,
                            row_id=self._row_id,
                        )
                    )
                    if chunk.finish_reason == "error":
                        self._error_columns.append(output_column)
            else:
                response = await self.lm.chat_completion(
                    messages=req.messages,
                    **req.hyperparams,
                )
                response.references = references
                await q.put(
                    TaskResult(
                        response=response,
                        output_column_name=output_column,
                        row_id=self._row_id,
                    )
                )
                result = response.content
                reasoning = response.reasoning_content

        except Exception as e:
            response_kwargs = dict(
                id=self._request_id,
                created=int(time()),
                model="",
                usage=ChatCompletionUsage(),
                choices=[
                    ChatCompletionChoice(
                        message=ChatCompletionMessage(content=f"[ERROR] {str(e)}"),
                        index=0,
                        finish_reason="error",
                    )
                ],
            )
            if self._stream:
                response = CellCompletionResponse(
                    **response_kwargs,
                    output_column_name=output_column,
                    row_id=self._row_id,
                )
            else:
                response = ChatCompletionResponse(**response_kwargs)
            await q.put(
                TaskResult(
                    response=response,
                    output_column_name=output_column,
                    row_id=self._row_id,
                )
            )
            result = response.content
            reasoning = response.reasoning_content
            self._error_columns.append(output_column)
            self.log_exception(
                f'Table "{self._table_id}": Failed to generate completion for column "{output_column}": {repr(e)}',
                e,
            )
        finally:
            await q.put(None)
            state_col = f"{task.output_column_name}_"
            state = self._column_dict.get(state_col, {})
            if references is not None:
                state["references"] = references.model_dump(mode="json")
            if reasoning:
                state["reasoning_content"] = reasoning
            if reasoning_time is not None:
                state["reasoning_time"] = reasoning_time
            self._column_dict[state_col] = state
            await self._signal_task_completion(task, result)
            self.log(f'Streamed completion for column "{output_column}": <{mask_string(result)}>.')

    async def _execute_embed_task(self, task: Task, q: Queue[ResultT | None]) -> None:
        output_column = task.output_column_name
        # Check if a value is provided
        try:
            embedding = self._column_dict[output_column]
            if isinstance(embedding, np.ndarray):
                pass
            elif isinstance(embedding, list):
                embedding = np.asarray(embedding)
            else:
                raise TypeError(
                    f"Unexpected embedding type, expected `np.ndarray` or `list`, got `{type(embedding)}`."
                )
        # Perform embedding
        except (KeyError, TypeError):
            body: EmbedGenConfig = task.body
            try:
                # Error circuit breaker
                self._check_upstream_error([body.source_column])
                # TODO: We can find a way to batch embedding tasks
                source = self._column_dict.get(body.source_column, None)
                embedding = await self.lm.embed_documents(
                    model=body.embedding_model,
                    texts=["." if source is None else source],
                )
                embedding = np.asarray(embedding.data[0].embedding, dtype=task.dtype)
                embedding = embedding / np.linalg.norm(embedding)
            except Exception as e:
                self.log_exception(
                    f'Table "{self._table_id}": Failed to embed for column "{output_column}": {repr(e)}',
                    e,
                )
                embedding = None
        # TODO: Perhaps we need to emit embeddings
        await q.put(None)
        await self._signal_task_completion(task, embedding)

    async def _execute_code_task(self, task: Task, q: Queue[ResultT | None]) -> None:
        output_column = task.output_column_name
        body: CodeGenConfig = task.body

        # Check if a value is provided
        try:
            result = self._column_dict[output_column]
            # response_kwargs = dict(
            #     id=self._request_id,
            #     created=int(time()),
            #     model="code_execution",
            #     usage=ChatCompletionUsage(),
            #     choices=[
            #         ChatCompletionChoice(
            #             message=ChatCompletionMessage(content=result),
            #             index=0,
            #         )
            #     ],
            # )
            # if self._stream:
            #     response = CellCompletionResponse(
            #         **response_kwargs,
            #         output_column_name=output_column,
            #         row_id=self._row_id,
            #     )
            # else:
            #     response = ChatCompletionResponse(**response_kwargs)

            # self.log(f'Skipped code execution for column "{output_column}".')
            # if self._regen_strategy is not None:
            #     await q.put(
            #         TaskResult(
            #             response=response,
            #             output_column_name=output_column,
            #             row_id=self._row_id,
            #         )
            #     )
            await q.put(None)
            await self._signal_task_completion(task, result)
            return
        except KeyError:
            pass

        # Perform code execution
        result = ""
        try:
            # Error circuit breaker
            self._check_upstream_error([body.source_column])
            source_code = self._column_dict.get(body.source_column, "")

            # Extract bytes from ColumnDtype.AUDIO and ColumnDtype.IMAGE and put it into a dictionary
            row_data = self._column_dict.copy()
            self.table.postprocess_rows([row_data], include_state=False)
            for k, v in row_data.items():
                col = next((col for col in self.table.column_metadata if col.column_id == k), None)
                if col and (col.dtype == ColumnDtype.AUDIO or col.dtype == ColumnDtype.IMAGE):
                    row_data[k] = await _load_uri_as_bytes(v)

            if source_code and row_data:
                result = await code_executor(
                    request=self.request,
                    organization_id=self.organization.id,
                    project_id=self.project.id,
                    source_code=source_code,
                    output_column=output_column,
                    row_data=row_data,
                    dtype=task.dtype,
                )
            else:
                result = ""

            response_kwargs = dict(
                id=self._request_id,
                created=int(time()),
                model="code_execution",
                usage=ChatCompletionUsage(),
                choices=[
                    ChatCompletionChoice(
                        message=ChatCompletionMessage(content=result),
                        index=0,
                    )
                ],
            )
            if self._stream:
                response = CellCompletionResponse(
                    **response_kwargs,
                    output_column_name=output_column,
                    row_id=self._row_id,
                )
            else:
                response = ChatCompletionResponse(**response_kwargs)

            await q.put(
                TaskResult(
                    response=response,
                    output_column_name=output_column,
                    row_id=self._row_id,
                )
            )

            self.log(f'Executed code for column "{output_column}": <{mask_string(result)}>.')

        except Exception as e:
            response_kwargs = dict(
                id=self._request_id,
                created=int(time()),
                model="code_execution",
                usage=ChatCompletionUsage(),
                choices=[
                    ChatCompletionChoice(
                        message=ChatCompletionMessage(content=f"[ERROR] {str(e)}"),
                        index=0,
                        finish_reason="error",
                    )
                ],
            )
            response = (
                CellCompletionResponse(
                    **response_kwargs, output_column_name=output_column, row_id=self._row_id
                )
                if self._stream
                else ChatCompletionResponse(**response_kwargs)
            )

            await q.put(
                TaskResult(
                    response=response,
                    output_column_name=output_column,
                    row_id=self._row_id,
                )
            )
            result = response.content
            self._error_columns.append(output_column)
            self.log_exception(
                f'Table "{self._table_id}": Failed to execute code for column "{output_column}": {repr(e)}',
                e,
            )
        finally:
            await q.put(None)
            await self._signal_task_completion(task, result)

    async def _execute_python_task(self, task: Task, q: Queue[ResultT | None]) -> None:
        output_column = task.output_column_name
        body: PythonGenConfig = task.body

        # Check if a value is provided
        try:
            result = self._column_dict[output_column]
            # response_kwargs = dict(
            #     id=self._request_id,
            #     created=int(time()),
            #     model="python_fixed_function",
            #     usage=ChatCompletionUsage(),
            #     choices=[
            #         ChatCompletionChoice(
            #             message=ChatCompletionMessage(content=result),
            #             index=0,
            #         )
            #     ],
            # )
            # if self._stream:
            #     response = CellCompletionResponse(
            #         **response_kwargs,
            #         output_column_name=output_column,
            #         row_id=self._row_id,
            #     )
            # else:
            #     response = ChatCompletionResponse(**response_kwargs)

            # self.log(f'Skipped python fixed function execution for column "{output_column}".')
            # if self._regen_strategy is not None:
            #     await q.put(
            #         TaskResult(
            #             response=response,
            #             output_column_name=output_column,
            #             row_id=self._row_id,
            #         )
            #     )
            await q.put(None)
            await self._signal_task_completion(task, result)
            return
        except KeyError:
            pass

        # Perform python fixed function execution
        result = ""
        try:
            # Error circuit breaker
            # Extract all columns to the left and check for upstream errors
            self._check_upstream_error(self._extract_all_upstream_columns(output_column))

            # Extract bytes from ColumnDtype.AUDIO and ColumnDtype.IMAGE and put it into a dictionary
            row_data = self._column_dict.copy()
            self.table.postprocess_rows([row_data], include_state=False)
            for k, v in row_data.items():
                col = next((col for col in self.table.column_metadata if col.column_id == k), None)
                if col and (col.dtype == ColumnDtype.AUDIO or col.dtype == ColumnDtype.IMAGE):
                    row_data[k] = await _load_uri_as_bytes(v)

            if body.python_code and row_data:
                result = await code_executor(
                    request=self.request,
                    organization_id=self.organization.id,
                    project_id=self.project.id,
                    source_code=body.python_code,
                    output_column=output_column,
                    row_data=row_data,
                    dtype=task.dtype,
                )

            response_kwargs = dict(
                id=self._request_id,
                created=int(time()),
                model="python_fixed_function",
                usage=ChatCompletionUsage(),
                choices=[
                    ChatCompletionChoice(
                        message=ChatCompletionMessage(content=result),
                        index=0,
                    )
                ],
            )
            response = (
                CellCompletionResponse(
                    **response_kwargs, output_column_name=output_column, row_id=self._row_id
                )
                if self._stream
                else ChatCompletionResponse(**response_kwargs)
            )

            await q.put(
                TaskResult(
                    response=response,
                    output_column_name=output_column,
                    row_id=self._row_id,
                )
            )

            self.log(
                f'Executed python code for column "{output_column}": <{mask_string(result)}>.'
            )

        except Exception as e:
            response_kwargs = dict(
                id=self._request_id,
                created=int(time()),
                model="python_fixed_function",
                usage=ChatCompletionUsage(),
                choices=[
                    ChatCompletionChoice(
                        message=ChatCompletionMessage(content=f"[ERROR] {str(e)}"),
                        index=0,
                        finish_reason="error",
                    )
                ],
            )
            response = (
                CellCompletionResponse(
                    **response_kwargs, output_column_name=output_column, row_id=self._row_id
                )
                if self._stream
                else ChatCompletionResponse(**response_kwargs)
            )

            await q.put(
                TaskResult(
                    response=response,
                    output_column_name=output_column,
                    row_id=self._row_id,
                )
            )
            result = response.content
            self._error_columns.append(output_column)
            self.log_exception(
                f'Table "{self._table_id}": Failed to execute python code for column "{output_column}": {repr(e)}',
                e,
            )
        finally:
            await q.put(None)
            await self._signal_task_completion(task, result)

    async def _signal_task_completion(self, task: Task, result: Any) -> None:
        self._column_dict[task.output_column_name] = result
        task.status = "done"
        await self._task_signal.put(None)

    async def _load_files(self, message: ChatThreadEntry) -> ChatThreadEntry | ChatEntry:
        if not isinstance(message, ChatThreadEntry):
            raise TypeError(f"Unexpected message type: {type(message)}")
        if message.role != ChatRole.USER:
            return message
        ### Text-only
        if isinstance(message.content, str):
            # logger.error(f"{message.content=}")
            return ChatEntry.user(content=message.content.strip())
        else:
            content = message.content
        ### Multi-modal
        contents: list[TextContent, ImageContent, AudioContent] = []
        replacements: dict[str, str] = {}
        # Load file
        # logger.error(f"{content=}")
        for c in content:
            if isinstance(c, TextContent):
                contents.append(c)
            else:
                data = await _load_uri_as_base64(c.uri)
                if getattr(self._col_map.get(c.column_name, None), "is_document_column", False):
                    # Document (data could be None)
                    replacements[c.column_name] = str(data)
                    # prompt = re.sub(_regex, str(data), prompt)
                else:
                    # Image or audio
                    if isinstance(data, (ImageContent, AudioContent)):
                        contents.append(data)
                    replacements[c.column_name] = ""
                    # prompt = re.sub(_regex, "", prompt)
        # Replace column references
        for c in contents:
            if not isinstance(c, TextContent):
                continue
            for col_name, data in replacements.items():
                _regex = r"(?<!\\)\${" + re.escape(col_name) + r"}"
                c.text = re.sub(_regex, data, c.text)
            c.text = c.text.strip()
        # Re-assemble
        message = ChatEntry.user(content=contents)
        # logger.warning(f"{message=}")
        return message

    def _check_upstream_error(self, upstream_cols: list[str]) -> None:
        if not isinstance(upstream_cols, list):
            raise TypeError(f"`upstream_cols` must be a list, got: {type(upstream_cols)}")
        error_cols = [f'"{col}"' for col in upstream_cols if col in self._error_columns]
        if len(error_cols) > 0:
            raise UpStreamError(f"Upstream columns errored out: {', '.join(error_cols)}")

    @classmethod
    async def setup_rag(
        cls,
        *,
        project: ProjectRead,
        lm: LMEngine,
        body: ChatRequest,
        request_id: str = "",
    ) -> tuple[ChatRequest, References | None]:
        if body.rag_params is None:
            return body, None
        kt_id = body.rag_params.table_id.strip()
        if kt_id == "":
            raise BadInputError(
                "`rag_params.table_id` is required when `rag_params` is specified."
            )
        kt = await KnowledgeTable.open_table(
            project_id=project.id, table_id=kt_id, request_id=request_id
        )
        kt_cols = {c.column_id for c in kt.column_metadata if not c.is_state_column}
        try:
            t0 = perf_counter()
            fts_query, vs_query = await lm.generate_search_query(
                messages=body.messages,
                rag_params=body.rag_params,
                **body.hyperparams,
            )
            cls._log(
                f'Query rewrite using "{body.model}" took t={(perf_counter() - t0) * 1e3:,.2f} ms.',
                request_id=request_id,
            )
        except Exception as e:
            cls._log(
                f"Query rewrite failed with error: {repr(e)}. Using last user message as query.",
                request_id=request_id,
            )
            # Fallback: use last user message
            for msg in reversed(body.messages):
                if msg.role == ChatRole.USER:
                    fts_query = msg.text_content
                    vs_query = msg.text_content
                    break
        rows = await kt.hybrid_search(
            fts_query=fts_query,
            vs_query=vs_query,
            embedding_fn=lm.embed_query_as_vector,
            vector_column_names=None,
            limit=body.rag_params.k,
            offset=0,
            remove_state_cols=True,
        )
        chunks = [
            Chunk(
                text=row.get("Text", "") or "",  # could be None
                title=row.get("Title", "") or "",  # could be None
                page=row.get("Page", None),
                document_id=row.get("File ID", "") or "",  # could be None
                chunk_id=str(row.get("ID", "")),
                # Context will contain extra columns
                context={
                    k: str(v)
                    for k, v in row.items()
                    if k not in kt.FIXED_COLUMN_IDS and k in kt_cols
                },
                # Metadata will contain things like RRF score
                metadata={
                    k: str(v)
                    for k, v in row.items()
                    if k not in kt.FIXED_COLUMN_IDS and k not in kt_cols
                },
            )
            for row in rows
        ]
        # Add project and table ID
        for chunk in chunks:
            chunk.metadata["project_id"] = project.id
            chunk.metadata["table_id"] = body.rag_params.table_id
        if len(rows) > 0 and body.rag_params.reranking_model is not None:
            try:
                order = (
                    await lm.rerank_documents(
                        model=body.rag_params.reranking_model,
                        query=vs_query,
                        documents=kt.rows_to_documents(rows),
                    )
                ).results
                chunks = [chunks[i.index] for i in order]
            except Exception as e:
                cls._log(
                    f"Reranking failed with error: {repr(e)}. Proceeding with original order.",
                    request_id=request_id,
                )
        chunks = chunks[: body.rag_params.k]
        references = References(chunks=chunks, search_query=vs_query)
        if body.messages[-1].role == ChatRole.USER:
            replacement_idx = -1
        elif body.messages[-2].role == ChatRole.USER:
            replacement_idx = -2
        else:
            raise BadInputError("The message list should end with user or assistant message.")
        rag_prompt = await lm.make_rag_prompt(
            messages=body.messages,
            references=references,
            inline_citations=body.rag_params.inline_citations,
        )
        body.messages[replacement_idx].content = rag_prompt
        return body, references

    async def _setup_rag(self, body: ChatRequest) -> tuple[ChatRequest, References | None]:
        return await self.setup_rag(
            project=self.project,
            lm=self.lm,
            body=body,
            request_id=self._request_id,
        )


@alru_cache(maxsize=ENV_CONFIG.max_file_cache_size, ttl=ENV_CONFIG.document_loader_cache_ttl_sec)
async def _load_uri_as_bytes(uri: str | None) -> bytes | None:
    """
    Loads a file from URI as raw bytes.
    Args:
        uri (str): The URI of the file.
    Returns:
        content (bytes | None): The raw file content as bytes, or None if loading fails.
    Raises:
        BadInputError: If the URI is invalid or file cannot be accessed.
    """
    if not uri:
        return None

    try:
        async with open_uri_async(str(uri)) as (file_handle, _):
            file_binary = await file_handle.read()
            return file_binary
    except (BadInputError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.warning(f'Failed to load file "{uri}" due to error: {repr(e)}')
        return None


async def _load_uri_as_base64(uri: str | None) -> str | AudioContent | ImageContent | None:
    """
    Loads a file from URI for LLM inference.

    Args:
        uri (str | None): The URI of the file.

    Returns:
        content (str | AudioContent | ImageContent): The file content.

    Raises:
        BadInputError: If the file format is unsupported.
    """
    if not uri:
        return None
    file_binary = await _load_uri_as_bytes(uri)
    if file_binary is None:
        return None
    extension = splitext(uri)[1].lower()
    try:
        # Load as document
        if extension in DOCUMENT_FILE_EXTENSIONS:
            return await GeneralDocLoader().load_document(basename(uri), file_binary)
        # Load as audio or image
        else:
            base64_data = base64.b64encode(file_binary).decode("utf-8")
            if extension in AUDIO_FILE_EXTENSIONS:
                return AudioContent(
                    input_audio=AudioContentData(data=base64_data, format=extension[1:])
                )
            elif extension in IMAGE_FILE_EXTENSIONS:
                extension = ".jpeg" if extension == ".jpg" else extension
                prefix = f"data:image/{extension[1:]};base64,"
                return ImageContent(image_url=ImageContentData(url=prefix + base64_data))
            else:
                raise BadInputError(
                    (
                        "Unsupported file type. Supported formats are: "
                        f"{', '.join(DOCUMENT_FILE_EXTENSIONS + AUDIO_FILE_EXTENSIONS + IMAGE_FILE_EXTENSIONS)}"
                    )
                )
    except BadInputError as e:
        logger.warning(f'Failed to parse file "{uri}" due to error: {repr(e)}')
        raise
    except Exception as e:
        logger.warning(f'Failed to parse file "{uri}" due to error: {repr(e)}')
        return None
