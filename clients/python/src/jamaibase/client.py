from mimetypes import guess_type
from typing import Any, AsyncGenerator, Generator, Type
from urllib.parse import quote

import httpx
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from jamaibase import protocol as p
from jamaibase.utils.io import json_loads


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    jamai_api_base: str = "https://api.jamaibase.com/api"
    jamai_api_key: SecretStr = ""

    @property
    def jamai_api_key_plain(self):
        return self.jamai_api_key.get_secret_value()


CONFIG = Config()
GenTableChatResponseType = (
    p.GenTableRowsChatCompletionChunks
    | Generator[p.GenTableStreamReferences | p.GenTableStreamChatCompletionChunk, None, None]
)


class JamAI:
    def __init__(
        self,
        project_id: str = "default",
        api_key: str = CONFIG.jamai_api_key_plain,
        api_base: str = CONFIG.jamai_api_base,
        headers: dict | None = None,
    ) -> None:
        if api_base.endswith("/"):
            api_base = api_base[:-1]
        self.project_id = project_id
        self.api_key = api_key
        self.api_base = api_base
        self.headers = {"X-PROJECT-ID": project_id}
        if api_key != "":
            self.headers["Authorization"] = f"Bearer {api_key}"
        if headers is not None:
            if not isinstance(headers, dict):
                raise TypeError("`headers` must be None or a dict.")
            self.headers.update(headers)
        self.http_client = httpx.Client(timeout=None, transport=httpx.HTTPTransport(retries=3))

    def close(self):
        self.http_client.close()

    @staticmethod
    def raise_exception(response: httpx.Response):
        if response.status_code == 200:
            return response
        try:
            err_mssg = response.text
        except httpx.ResponseNotRead:
            err_mssg = response.read().decode()
        raise RuntimeError(
            f"Endpoint {response.url} returned {response.status_code} error: {err_mssg}"
        )

    @staticmethod
    def _filter_params(params: dict[str, Any] | None):
        if params is not None:
            params = {k: v for k, v in params.items() if v is not None}
        return params

    def _get(
        self,
        address: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> str | BaseModel:
        response = self.http_client.get(
            f"{address}{endpoint}",
            params=self._filter_params(params),
            headers=self.headers,
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response.text
        else:
            return response_model.model_validate_json(response.text)

    def _post(
        self,
        address: str,
        endpoint: str,
        request: BaseModel | None,
        response_model: Type[BaseModel] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> str | BaseModel:
        if request is not None:
            request = request.model_dump()
        response = self.http_client.post(
            f"{address}{endpoint}",
            json=request,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response.text
        else:
            return response_model.model_validate_json(response.text)

    def _patch(
        self,
        address: str,
        endpoint: str,
        request: BaseModel | None,
        response_model: Type[BaseModel] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> str | BaseModel:
        if request is not None:
            request = request.model_dump()
        response = self.http_client.patch(
            f"{address}{endpoint}",
            json=request,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response.text
        else:
            return response_model.model_validate_json(response.text)

    def _stream(
        self,
        address: str,
        endpoint: str,
        request: BaseModel | None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> Generator[str, None, None]:
        if request is not None:
            request = request.model_dump()
        with self.http_client.stream(
            "POST",
            f"{address}{endpoint}",
            json=request,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        ) as response:
            response = self.raise_exception(response)
            for chunk in response.iter_lines():
                chunk = chunk.strip()
                if chunk == "" or chunk == "data: [DONE]":
                    continue
                yield chunk

    def _delete(
        self,
        address: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> str | BaseModel:
        response = self.http_client.delete(
            f"{address}{endpoint}",
            params=self._filter_params(params),
            headers=self.headers,
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response.text
        else:
            return response_model.model_validate_json(response.text)

    # --- Models and chat --- #

    def model_info(
        self,
        name: str = "",
        capabilities: list[str] | None = None,
    ) -> p.ModelInfoResponse:
        params = {"model": name, "capabilities": capabilities}
        return self._get(self.api_base, "/v1/models", params, p.ModelInfoResponse)

    def model_names(
        self,
        prefer: str = "",
        capabilities: list[str] | None = None,
    ) -> list[str]:
        params = {"prefer": prefer, "capabilities": capabilities}
        return json_loads(self._get(self.api_base, "/v1/model_names", params))

    def generate_chat_completions(
        self, request: p.ChatRequest
    ) -> p.ChatCompletionChunk | Generator[p.References | p.ChatCompletionChunk, None, None]:
        """Generates chat completions.

        Args:
            request (ChatRequest): The request.

        Returns:
            completion (ChatCompletionChunk | Generator): The chat completion.
                In streaming mode, it is a generator that yields a `References` object
                followed by zero or more `ChatCompletionChunk` objects.
                In non-streaming mode, it is a `ChatCompletionChunk` object.
        """
        if request.stream:

            def gen():
                gen_stream = self._stream(self.api_base, "/v1/chat/completions", request)
                for chunk in gen_stream:
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "chat.references":
                        yield p.References.model_validate(chunk)
                    elif chunk["object"] == "chat.completion.chunk":
                        yield p.ChatCompletionChunk.model_validate(chunk)
                    else:
                        raise RuntimeError(f"Unexpected SSE chunk: {chunk}")

            return gen()
        else:
            return self._post(
                self.api_base, "/v1/chat/completions", request, p.ChatCompletionChunk
            )

    def generate_embeddings(self, request: p.EmbeddingRequest) -> p.EmbeddingResponse:
        return self._post(self.api_base, "/v1/embeddings", request, p.EmbeddingResponse)

    # --- Gen Table --- #
    def create_action_table(self, request: p.ActionTableSchemaCreate) -> p.TableMetaResponse:
        return self._post(self.api_base, "/v1/gen_tables/action", request, p.TableMetaResponse)

    def create_knowledge_table(self, request: p.KnowledgeTableSchemaCreate) -> p.TableMetaResponse:
        return self._post(self.api_base, "/v1/gen_tables/knowledge", request, p.TableMetaResponse)

    def create_chat_table(self, request: p.ChatTableSchemaCreate) -> p.TableMetaResponse:
        return self._post(self.api_base, "/v1/gen_tables/chat", request, p.TableMetaResponse)

    def get_table(self, table_type: p.TableType, table_id: p.TableName) -> p.TableMetaResponse:
        return self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}",
            None,
            p.TableMetaResponse,
        )

    def list_tables(
        self,
        table_type: p.TableType,
        offset: int = 0,
        limit: int = 100,
    ) -> p.Page[p.TableMetaResponse]:
        return self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}",
            dict(offset=offset, limit=limit),
            p.Page[p.TableMetaResponse],
        )

    def delete_table(self, table_type: p.TableType, table_id: p.TableName) -> p.OkResponse:
        return self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}",
            None,
            p.OkResponse,
        )

    def duplicate_table(
        self,
        table_type: p.TableType,
        table_id_src: str,
        table_id_dst: str,
        include_data: bool = True,
        deploy: bool = False,
    ) -> p.TableMetaResponse:
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/duplicate/{quote(table_id_src)}/{quote(table_id_dst)}",
            None,
            p.TableMetaResponse,
            dict(include_data=include_data, deploy=deploy),
        )

    def rename_table(
        self, table_type: p.TableType, table_id_src: str, table_id_dst: str
    ) -> p.TableMetaResponse:
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/rename/{quote(table_id_src)}/{quote(table_id_dst)}",
            None,
            p.TableMetaResponse,
        )

    def update_gen_config(
        self, table_type: p.TableType, request: p.GenConfigUpdateRequest
    ) -> p.TableMetaResponse:
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/gen_config/update",
            request,
            p.TableMetaResponse,
        )

    def add_action_columns(self, request: p.AddActionColumnSchema) -> p.TableMetaResponse:
        return self._post(
            self.api_base,
            "/v1/gen_tables/action/columns/add",
            request,
            p.TableMetaResponse,
        )

    def add_knowledge_columns(self, request: p.AddKnowledgeColumnSchema) -> p.TableMetaResponse:
        return self._post(
            self.api_base,
            "/v1/gen_tables/knowledge/columns/add",
            request,
            p.TableMetaResponse,
        )

    def add_chat_columns(self, request: p.AddChatColumnSchema) -> p.TableMetaResponse:
        return self._post(
            self.api_base,
            "/v1/gen_tables/chat/columns/add",
            request,
            p.TableMetaResponse,
        )

    def drop_columns(
        self, table_type: p.TableType, request: p.ColumnDropRequest
    ) -> p.TableMetaResponse:
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/columns/drop",
            request,
            p.TableMetaResponse,
        )

    def rename_columns(
        self, table_type: p.TableType, request: p.ColumnRenameRequest
    ) -> p.TableMetaResponse:
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/columns/rename",
            request,
            p.TableMetaResponse,
        )

    def reorder_columns(
        self, table_type: p.TableType, request: p.ColumnReorderRequest
    ) -> p.TableMetaResponse:
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/columns/reorder",
            request,
            p.TableMetaResponse,
        )

    def list_table_rows(
        self,
        table_type: p.TableType,
        table_id: p.TableName,
        offset: int = 0,
        limit: int = 100,
        columns: list[p.Name] | None = None,
    ) -> p.Page[dict[p.Name, Any]]:
        return self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}/rows",
            dict(offset=offset, limit=limit, columns=columns),
            p.Page[dict[p.Name, Any]],
        )

    def get_table_row(
        self,
        table_type: p.TableType,
        table_id: p.TableName,
        row_id: str,
        columns: list[p.Name] | None = None,
    ) -> dict[p.Name, Any]:
        response = self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}/rows/{quote(row_id)}",
            dict(columns=columns),
            None,
        )
        return json_loads(response)

    def add_table_rows(
        self, table_type: p.TableType, request: p.RowAddRequest
    ) -> GenTableChatResponseType:
        if request.stream:

            def gen():
                for chunk in self._stream(
                    self.api_base,
                    f"/v1/gen_tables/{table_type.value}/rows/add",
                    request,
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "gen_table.references":
                        yield p.GenTableStreamReferences.model_validate(chunk)
                    elif chunk["object"] == "gen_table.completion.chunk":
                        yield p.GenTableStreamChatCompletionChunk.model_validate(chunk)
                    else:
                        raise RuntimeError(f"Unexpected SSE chunk: {chunk}")

            return gen()
        else:
            return self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type.value}/rows/add",
                request,
                p.GenTableRowsChatCompletionChunks,
            )

    def regen_table_rows(
        self, table_type: p.TableType, request: p.RowRegenRequest
    ) -> GenTableChatResponseType:
        if request.stream:

            def gen():
                for chunk in self._stream(
                    self.api_base,
                    f"/v1/gen_tables/{table_type.value}/rows/regen",
                    request,
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "gen_table.references":
                        yield p.GenTableStreamReferences.model_validate(chunk)
                    elif chunk["object"] == "gen_table.completion.chunk":
                        yield p.GenTableStreamChatCompletionChunk.model_validate(chunk)
                    else:
                        raise RuntimeError(f"Unexpected SSE chunk: {chunk}")

            return gen()
        else:
            return self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type.value}/rows/regen",
                request,
                p.GenTableRowsChatCompletionChunks,
            )

    def update_table_row(
        self, table_type: p.TableType, request: p.RowUpdateRequest
    ) -> p.OkResponse:
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/rows/update",
            request,
            p.OkResponse,
        )

    def delete_table_rows(
        self, table_type: p.TableType, request: p.RowDeleteRequest
    ) -> p.OkResponse:
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/rows/delete",
            request,
            p.OkResponse,
        )

    def delete_table_row(
        self, table_type: p.TableType, table_id: p.TableName, row_id: str
    ) -> p.OkResponse:
        return self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}/rows/{quote(row_id)}",
            None,
            p.OkResponse,
        )

    def get_conversation_thread(self, table_id: p.TableName) -> p.ChatThread:
        return self._get(
            self.api_base,
            f"/v1/gen_tables/chat/{quote(table_id)}/thread",
            None,
            p.ChatThread,
        )

    def hybrid_search(
        self,
        table_type: p.TableType,
        request: p.SearchRequest,
    ) -> list[dict[p.Name, Any]]:
        response = self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/hybrid_search",
            request,
            None,
        )
        return json_loads(response)

    def upload_file(self, request: p.FileUploadRequest) -> p.OkResponse:
        file_path = request.file_path
        # Guess the MIME type of the file based on its extension
        mime_type, _ = guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"  # Default MIME type
        # Extract the filename from the file path
        filename = file_path.split("/")[-1]
        # Open the file in binary mode
        with open(file_path, "rb") as f:
            # Make an asynchronous POST request to upload the file
            response = self.http_client.post(
                f"{self.api_base}/v1/gen_tables/knowledge/upload_file",
                files={
                    "file": (filename, f, mime_type),
                },
                data={
                    "file_name": filename,
                    "table_id": request.table_id,
                    "chunk_size": request.chunk_size,
                    "chunk_overlap": request.chunk_overlap,
                    # "overwrite": request.overwrite,
                },
                timeout=None,
            )
        response = self.raise_exception(response)
        return p.OkResponse.model_validate_json(response.text)


class JamAIAsync(JamAI):
    def __init__(
        self,
        project_id: str = "default",
        api_key: str = CONFIG.jamai_api_key_plain,
        api_base: str = CONFIG.jamai_api_base,
        headers: dict | None = None,
    ) -> None:
        super().__init__(
            project_id=project_id,
            api_key=api_key,
            api_base=api_base,
            headers=headers,
        )
        self.http_client = httpx.AsyncClient(
            timeout=None, transport=httpx.AsyncHTTPTransport(retries=3)
        )

    async def close(self):
        await self.http_client.aclose()

    async def _get(
        self,
        address: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> str | BaseModel:
        response = await self.http_client.get(
            f"{address}{endpoint}",
            params=self._filter_params(params),
            headers=self.headers,
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response.text
        else:
            return response_model.model_validate_json(response.text)

    async def _post(
        self,
        address: str,
        endpoint: str,
        request: BaseModel | None,
        response_model: Type[BaseModel] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> str | BaseModel:
        if request is not None:
            request = request.model_dump()
        response = await self.http_client.post(
            f"{address}{endpoint}",
            json=request,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response.text
        else:
            return response_model.model_validate_json(response.text)

    async def _patch(
        self,
        address: str,
        endpoint: str,
        request: BaseModel | None,
        response_model: Type[BaseModel] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> str | BaseModel:
        if request is not None:
            request = request.model_dump()
        response = await self.http_client.patch(
            f"{address}{endpoint}",
            json=request,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response.text
        else:
            return response_model.model_validate_json(response.text)

    async def _stream(
        self,
        address: str,
        endpoint: str,
        request: BaseModel | None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        if request is not None:
            request = request.model_dump()
        async with self.http_client.stream(
            "POST",
            f"{address}{endpoint}",
            json=request,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        ) as response:
            response = self.raise_exception(response)
            async for chunk in response.aiter_lines():
                chunk = chunk.strip()
                if chunk == "" or chunk == "data: [DONE]":
                    continue
                yield chunk

    async def _delete(
        self,
        address: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> str | BaseModel:
        response = await self.http_client.delete(
            f"{address}{endpoint}",
            params=self._filter_params(params),
            headers=self.headers,
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response.text
        else:
            return response_model.model_validate_json(response.text)

    # --- Models and chat --- #

    async def model_info(
        self,
        name: str = "",
        capabilities: list[str] | None = None,
    ) -> p.ModelInfoResponse:
        params = {"model": name, "capabilities": capabilities}
        return await self._get(self.api_base, "/v1/models", params, p.ModelInfoResponse)

    async def model_names(
        self,
        prefer: str = "",
        capabilities: list[str] | None = None,
    ) -> list[str]:
        params = {"prefer": prefer, "capabilities": capabilities}
        return json_loads(await self._get(self.api_base, "/v1/model_names", params))

    async def generate_chat_completions(
        self, request: p.ChatRequest
    ) -> p.ChatCompletionChunk | AsyncGenerator[p.References | p.ChatCompletionChunk, None]:
        """Generates chat completions.

        Args:
            request (ChatRequest): The request.

        Returns:
            completion (ChatCompletionChunk | AsyncGenerator): The chat completion.
                In streaming mode, it is an async generator that yields a `References` object
                followed by zero or more `ChatCompletionChunk` objects.
                In non-streaming mode, it is a `ChatCompletionChunk` object.
        """
        if request.stream:

            async def gen():
                gen_stream = self._stream(self.api_base, "/v1/chat/completions", request)
                async for chunk in gen_stream:
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "chat.references":
                        yield p.References.model_validate(chunk)
                    elif chunk["object"] == "chat.completion.chunk":
                        yield p.ChatCompletionChunk.model_validate(chunk)

            return gen()
        else:
            return await self._post(
                self.api_base, "/v1/chat/completions", request, p.ChatCompletionChunk
            )

    async def generate_embeddings(self, request: p.EmbeddingRequest) -> p.EmbeddingResponse:
        return await self._post(self.api_base, "/v1/embeddings", request, p.EmbeddingResponse)

    # --- Gen Table --- #
    async def create_action_table(self, request: p.ActionTableSchemaCreate) -> p.TableMetaResponse:
        return await self._post(
            self.api_base, "/v1/gen_tables/action", request, p.TableMetaResponse
        )

    async def create_knowledge_table(
        self, request: p.KnowledgeTableSchemaCreate
    ) -> p.TableMetaResponse:
        return await self._post(
            self.api_base, "/v1/gen_tables/knowledge", request, p.TableMetaResponse
        )

    async def create_chat_table(self, request: p.ChatTableSchemaCreate) -> p.TableMetaResponse:
        return await self._post(self.api_base, "/v1/gen_tables/chat", request, p.TableMetaResponse)

    async def get_table(
        self, table_type: p.TableType, table_id: p.TableName
    ) -> p.TableMetaResponse:
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}",
            None,
            p.TableMetaResponse,
        )

    async def list_tables(
        self,
        table_type: p.TableType,
        offset: int = 0,
        limit: int = 100,
    ) -> p.Page[p.TableMetaResponse]:
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}",
            dict(offset=offset, limit=limit),
            p.Page[p.TableMetaResponse],
        )

    async def delete_table(self, table_type: p.TableType, table_id: p.TableName) -> p.OkResponse:
        return await self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}",
            None,
            p.OkResponse,
        )

    async def duplicate_table(
        self,
        table_type: p.TableType,
        table_id_src: str,
        table_id_dst: str,
        include_data: bool = True,
        deploy: bool = False,
    ) -> p.TableMetaResponse:
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/duplicate/{quote(table_id_src)}/{quote(table_id_dst)}",
            None,
            p.TableMetaResponse,
            dict(include_data=include_data, deploy=deploy),
        )

    async def rename_table(
        self, table_type: p.TableType, table_id_src: str, table_id_dst: str
    ) -> p.TableMetaResponse:
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/rename/{quote(table_id_src)}/{quote(table_id_dst)}",
            None,
            p.TableMetaResponse,
        )

    async def update_gen_config(
        self, table_type: p.TableType, request: p.GenConfigUpdateRequest
    ) -> p.TableMetaResponse:
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/gen_config/update",
            request,
            p.TableMetaResponse,
        )

    async def add_action_columns(self, request: p.AddActionColumnSchema) -> p.TableMetaResponse:
        return await self._post(
            self.api_base,
            "/v1/gen_tables/action/columns/add",
            request,
            p.TableMetaResponse,
        )

    async def add_knowledge_columns(
        self, request: p.AddKnowledgeColumnSchema
    ) -> p.TableMetaResponse:
        return await self._post(
            self.api_base,
            "/v1/gen_tables/knowledge/columns/add",
            request,
            p.TableMetaResponse,
        )

    async def add_chat_columns(self, request: p.AddChatColumnSchema) -> p.TableMetaResponse:
        return await self._post(
            self.api_base,
            "/v1/gen_tables/chat/columns/add",
            request,
            p.TableMetaResponse,
        )

    async def drop_columns(
        self, table_type: p.TableType, request: p.ColumnDropRequest
    ) -> p.TableMetaResponse:
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/columns/drop",
            request,
            p.TableMetaResponse,
        )

    async def rename_columns(
        self, table_type: p.TableType, request: p.ColumnRenameRequest
    ) -> p.TableMetaResponse:
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/columns/rename",
            request,
            p.TableMetaResponse,
        )

    async def reorder_columns(
        self, table_type: p.TableType, request: p.ColumnReorderRequest
    ) -> p.TableMetaResponse:
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/columns/reorder",
            request,
            p.TableMetaResponse,
        )

    async def list_table_rows(
        self,
        table_type: p.TableType,
        table_id: p.TableName,
        offset: int = 0,
        limit: int = 100,
        columns: list[p.Name] | None = None,
    ) -> p.Page[dict[p.Name, Any]]:
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}/rows",
            dict(offset=offset, limit=limit, columns=columns),
            p.Page[dict[p.Name, Any]],
        )

    async def get_table_row(
        self,
        table_type: p.TableType,
        table_id: p.TableName,
        row_id: str,
        columns: list[p.Name] | None = None,
    ) -> dict[p.Name, Any]:
        response = await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}/rows/{quote(row_id)}",
            dict(columns=columns),
            None,
        )
        return json_loads(response)

    async def add_table_rows(
        self, table_type: p.TableType, request: p.RowAddRequest
    ) -> (
        p.GenTableRowsChatCompletionChunks
        | AsyncGenerator[p.GenTableStreamReferences | p.GenTableStreamChatCompletionChunk, None]
    ):
        if request.stream:

            async def gen():
                async for chunk in self._stream(
                    self.api_base,
                    f"/v1/gen_tables/{table_type.value}/rows/add",
                    request,
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "gen_table.references":
                        yield p.GenTableStreamReferences.model_validate(chunk)
                    elif chunk["object"] == "gen_table.completion.chunk":
                        yield p.GenTableStreamChatCompletionChunk.model_validate(chunk)

            return gen()
        else:
            return await self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type.value}/rows/add",
                request,
                p.GenTableRowsChatCompletionChunks,
            )

    async def regen_table_rows(
        self, table_type: p.TableType, request: p.RowRegenRequest
    ) -> (
        p.GenTableRowsChatCompletionChunks
        | AsyncGenerator[p.GenTableStreamReferences | p.GenTableStreamChatCompletionChunk, None]
    ):
        if request.stream:

            async def gen():
                async for chunk in self._stream(
                    self.api_base,
                    f"/v1/gen_tables/{table_type.value}/rows/regen",
                    request,
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "gen_table.references":
                        yield p.GenTableStreamReferences.model_validate(chunk)
                    elif chunk["object"] == "gen_table.completion.chunk":
                        yield p.GenTableStreamChatCompletionChunk.model_validate(chunk)

            return gen()
        else:
            return await self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type.value}/rows/regen",
                request,
                p.GenTableRowsChatCompletionChunks,
            )

    async def update_table_row(
        self, table_type: p.TableType, request: p.RowUpdateRequest
    ) -> p.OkResponse:
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/rows/update",
            request,
            p.OkResponse,
        )

    async def delete_table_rows(
        self, table_type: p.TableType, request: p.RowDeleteRequest
    ) -> p.OkResponse:
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/rows/delete",
            request,
            p.OkResponse,
        )

    async def delete_table_row(
        self, table_type: p.TableType, table_id: p.TableName, row_id: str
    ) -> p.OkResponse:
        return await self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/{quote(table_id)}/rows/{quote(row_id)}",
            None,
            p.OkResponse,
        )

    async def get_conversation_thread(self, table_id: p.TableName) -> p.ChatThread:
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/chat/{quote(table_id)}/thread",
            None,
            p.ChatThread,
        )

    async def hybrid_search(
        self,
        table_type: p.TableType,
        request: p.SearchRequest,
    ) -> list[dict[p.Name, Any]]:
        response = await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type.value}/hybrid_search",
            request,
            None,
        )
        return json_loads(response)
