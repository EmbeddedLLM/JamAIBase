from mimetypes import guess_type
from os.path import split
from typing import Any, AsyncGenerator, Generator, Type
from urllib.parse import quote
from warnings import warn

import httpx
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from jamaibase.protocol import (
    ActionTableSchemaCreate,
    AddActionColumnSchema,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    ChatCompletionChunk,
    ChatRequest,
    ChatTableSchemaCreate,
    ChatThread,
    ColumnDropRequest,
    ColumnRenameRequest,
    ColumnReorderRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    FileUploadRequest,
    GenConfigUpdateRequest,
    GenTableRowsChatCompletionChunks,
    GenTableStreamChatCompletionChunk,
    GenTableStreamReferences,
    KnowledgeTableSchemaCreate,
    ModelInfoResponse,
    OkResponse,
    Page,
    References,
    RowAddRequest,
    RowDeleteRequest,
    RowRegenRequest,
    RowUpdateRequest,
    SearchRequest,
    TableDataImportRequest,
    TableImportRequest,
    TableMetaResponse,
    TableType,
)
from jamaibase.utils.io import json_loads


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    jamai_api_key: SecretStr = ""
    jamai_project_id: str = "default"
    jamai_api_base: str = "https://api.jamaibase.com/api"

    @property
    def jamai_api_key_plain(self):
        return self.jamai_api_key.get_secret_value()


ENV_CONFIG = EnvConfig()
GenTableChatResponseType = (
    GenTableRowsChatCompletionChunks
    | Generator[GenTableStreamReferences | GenTableStreamChatCompletionChunk, None, None]
)


class JamAI:
    def __init__(
        self,
        project_id: str = ENV_CONFIG.jamai_project_id,
        api_key: str = ENV_CONFIG.jamai_api_key_plain,
        api_base: str = ENV_CONFIG.jamai_api_base,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> None:
        """
        Initialize the JamAI client.

        Args:
            project_id (str, optional): The project ID. Defaults to "default".
            api_key (str, optional): The API key for authentication.
                Defaults to `JAMAI_API_KEY` var in environment or `.env` file.
            api_base (str, optional): The base URL for the API.
                Defaults to `JAMAI_API_BASE` var in environment or `.env` file.
            headers (dict | None, optional): Additional headers to include in requests.
                Defaults to None.
            timeout (float | None, optional): The timeout to use when sending requests.
                Defaults to None (no timeout).
        """
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
        self.http_client = httpx.Client(
            timeout=timeout,
            transport=httpx.HTTPTransport(retries=3),
        )

    def close(self) -> None:
        """
        Close the HTTP client.
        """
        self.http_client.close()

    @staticmethod
    def raise_exception(response: httpx.Response) -> httpx.Response:
        """
        Raise an exception if the response status code is not 200.

        Args:
            response (httpx.Response): The HTTP response.

        Raises:
            RuntimeError: If the response status code is not 200.

        Returns:
            response (httpx.Response): The HTTP response.
        """
        if response.status_code == 200:
            if "warning" in response.headers:
                warn(response.headers["warning"], stacklevel=2)
            return response
        if "warning" in response.headers:
            warn(response.headers["warning"], stacklevel=2)
        try:
            err_mssg = response.text
        except httpx.ResponseNotRead:
            err_mssg = response.read().decode()
        raise RuntimeError(
            f"Endpoint {response.url} returned {response.status_code} error: {err_mssg}"
        )

    @staticmethod
    def _filter_params(params: dict[str, Any] | None):
        """
        Filter out None values from the parameters dictionary.

        Args:
            params (dict[str, Any] | None): The parameters dictionary.

        Returns:
            params (dict[str, Any] | None): The filtered parameters dictionary.
        """
        if params is not None:
            params = {k: v for k, v in params.items() if v is not None}
        return params

    def _get(
        self,
        address: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make a GET request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return.
            **kwargs (Any): Keyword arguments for `httpx.get`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        response = self.http_client.get(
            f"{address}{endpoint}",
            params=self._filter_params(params),
            headers=self.headers,
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)

    def _post(
        self,
        address: str,
        endpoint: str,
        *,
        request: BaseModel | None,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make a POST request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            request (BaseModel | None, optional): The request body.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.post`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
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
            return response
        else:
            return response_model.model_validate_json(response.text)

    def _patch(
        self,
        address: str,
        endpoint: str,
        *,
        request: BaseModel | None,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make a PATCH request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            request (BaseModel | None, optional): The request body.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.patch`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
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
            return response
        else:
            return response_model.model_validate_json(response.text)

    def _stream(
        self,
        address: str,
        endpoint: str,
        *,
        request: BaseModel | None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> Generator[str, None, None]:
        """
        Make a streaming POST request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            request (BaseModel | None, optional): The request body.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.stream`.

        Yields:
            str: The response chunks.
        """
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
        *,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make a DELETE request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return.
            **kwargs (Any): Keyword arguments for `httpx.delete`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        response = self.http_client.delete(
            f"{address}{endpoint}",
            params=self._filter_params(params),
            headers=self.headers,
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)

    # --- Models and chat --- #

    def model_info(
        self,
        name: str = "",
        capabilities: list[str] | None = None,
    ) -> ModelInfoResponse:
        """
        Get information about available models.

        Args:
            name (str, optional): The model name. Defaults to "".
            capabilities (list[str] | None, optional): List of model capabilities to filter by.
                Defaults to None.

        Returns:
            response (ModelInfoResponse): The model information response.
        """
        params = {"model": name, "capabilities": capabilities}
        return self._get(
            self.api_base,
            "/v1/models",
            params=params,
            response_model=ModelInfoResponse,
        )

    def model_names(
        self,
        prefer: str = "",
        capabilities: list[str] | None = None,
    ) -> list[str]:
        """
        Get the names of available models.

        Args:
            prefer (str, optional): Preferred model name. Defaults to "".
            capabilities (list[str] | None, optional): List of model capabilities to filter by.

        Returns:
            response (list[str]): List of model names.
        """
        params = {"prefer": prefer, "capabilities": capabilities}
        response = self._get(
            self.api_base,
            "/v1/model_names",
            params=params,
            response_model=None,
        )
        return json_loads(response.text)

    def generate_chat_completions(
        self, request: ChatRequest
    ) -> ChatCompletionChunk | Generator[References | ChatCompletionChunk, None, None]:
        """
        Generates chat completions.

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
                for chunk in self._stream(
                    self.api_base,
                    "/v1/chat/completions",
                    request=request,
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "chat.references":
                        yield References.model_validate(chunk)
                    elif chunk["object"] == "chat.completion.chunk":
                        yield ChatCompletionChunk.model_validate(chunk)
                    else:
                        raise RuntimeError(f"Unexpected SSE chunk: {chunk}")

            return gen()
        else:
            return self._post(
                self.api_base,
                "/v1/chat/completions",
                request=request,
                response_model=ChatCompletionChunk,
            )

    def generate_embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """
        Generate embeddings for the given input.

        Args:
            request (EmbeddingRequest): The embedding request.

        Returns:
            response (EmbeddingResponse): The embedding response.
        """
        return self._post(
            self.api_base,
            "/v1/embeddings",
            request=request,
            response_model=EmbeddingResponse,
        )

    # --- Gen Table --- #

    def create_action_table(self, request: ActionTableSchemaCreate) -> TableMetaResponse:
        """
        Create an Action Table.

        Args:
            request (ActionTableSchemaCreate): The action table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            "/v1/gen_tables/action",
            request=request,
            response_model=TableMetaResponse,
        )

    def create_knowledge_table(self, request: KnowledgeTableSchemaCreate) -> TableMetaResponse:
        """
        Create a Knowledge Table.

        Args:
            request (KnowledgeTableSchemaCreate): The knowledge table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            "/v1/gen_tables/knowledge",
            request=request,
            response_model=TableMetaResponse,
        )

    def create_chat_table(self, request: ChatTableSchemaCreate) -> TableMetaResponse:
        """
        Create a Chat Table.

        Args:
            request (ChatTableSchemaCreate): The chat table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            "/v1/gen_tables/chat",
            request=request,
            response_model=TableMetaResponse,
        )

    def get_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> TableMetaResponse:
        """
        Get metadata for a specific Generative Table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}",
            params=None,
            response_model=TableMetaResponse,
        )

    def list_tables(
        self,
        table_type: str | TableType,
        offset: int = 0,
        limit: int = 100,
        parent_id: str | None = None,
        search_query: str = "",
    ) -> Page[TableMetaResponse]:
        """
        List Generative Tables of a specific type.

        Args:
            table_type (str | TableType): The type of the table.
            offset (int, optional): Pagination offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            parent_id (str | None, optional): Parent ID of tables to return.
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
                Defaults to None (return all tables).
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).

        Returns:
            response (Page[TableMetaResponse]): The paginated table metadata response.
        """
        return self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}",
            params=dict(
                offset=offset, limit=limit, parent_id=parent_id, search_query=search_query
            ),
            response_model=Page[TableMetaResponse],
        )

    def delete_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> OkResponse:
        """
        Delete a specific table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}",
            params=None,
            response_model=OkResponse,
        )

    def duplicate_table(
        self,
        table_type: str | TableType,
        table_id_src: str,
        table_id_dst: str,
        include_data: bool = True,
        deploy: bool = False,
    ) -> TableMetaResponse:
        """
        Duplicate a table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str): The destination / new table ID.
            include_data (bool, optional): Whether to include data in the duplicated table. Defaults to True.
            deploy (bool, optional): Whether to deploy the duplicated table. Defaults to False.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/duplicate/{quote(table_id_src)}/{quote(table_id_dst)}",
            request=None,
            params=dict(include_data=include_data, deploy=deploy),
            response_model=TableMetaResponse,
        )

    def create_child_table(
        self,
        table_type: str | TableType,
        table_id_src: str,
        table_id_dst: str | None = None,
    ) -> TableMetaResponse:
        """
        Create a child table from a parent chat table.
        Schema and existing rows are copied over from the parent.

        Args:
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str | None, optional): The destination / new table ID.
                Will be generated if not provided.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/child/{table_id_src}",
            request=None,
            params=dict(table_id_dst=table_id_dst),
            response_model=TableMetaResponse,
        )

    def rename_table(
        self,
        table_type: str | TableType,
        table_id_src: str,
        table_id_dst: str,
    ) -> TableMetaResponse:
        """
        Rename a table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str): The destination / new table ID.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/rename/{quote(table_id_src)}/{quote(table_id_dst)}",
            request=None,
            response_model=TableMetaResponse,
        )

    def update_gen_config(
        self,
        table_type: str | TableType,
        request: GenConfigUpdateRequest,
    ) -> TableMetaResponse:
        """
        Update the generation configuration for a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (GenConfigUpdateRequest): The generation configuration update request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/gen_config/update",
            request=request,
            response_model=TableMetaResponse,
        )

    def add_action_columns(self, request: AddActionColumnSchema) -> TableMetaResponse:
        """
        Add columns to an Action Table.

        Args:
            request (AddActionColumnSchema): The action column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            "/v1/gen_tables/action/columns/add",
            request=request,
            response_model=TableMetaResponse,
        )

    def add_knowledge_columns(self, request: AddKnowledgeColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Knowledge Table.

        Args:
            request (AddKnowledgeColumnSchema): The knowledge column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            "/v1/gen_tables/knowledge/columns/add",
            request=request,
            response_model=TableMetaResponse,
        )

    def add_chat_columns(self, request: AddChatColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Chat Table.

        Args:
            request (AddChatColumnSchema): The chat column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            "/v1/gen_tables/chat/columns/add",
            request=request,
            response_model=TableMetaResponse,
        )

    def drop_columns(
        self,
        table_type: str | TableType,
        request: ColumnDropRequest,
    ) -> TableMetaResponse:
        """
        Drop columns from a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (ColumnDropRequest): The column drop request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/columns/drop",
            request=request,
            response_model=TableMetaResponse,
        )

    def rename_columns(
        self,
        table_type: str | TableType,
        request: ColumnRenameRequest,
    ) -> TableMetaResponse:
        """
        Rename columns in a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (ColumnRenameRequest): The column rename request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/columns/rename",
            request=request,
            response_model=TableMetaResponse,
        )

    def reorder_columns(
        self,
        table_type: str | TableType,
        request: ColumnReorderRequest,
    ) -> TableMetaResponse:
        """
        Reorder columns in a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (ColumnReorderRequest): The column reorder request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/columns/reorder",
            request=request,
            response_model=TableMetaResponse,
        )

    def list_table_rows(
        self,
        table_type: str | TableType,
        table_id: str,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Pagination offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).

        Returns:
            response (Page[dict[str, Any]]): The paginated rows response.
        """
        return self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows",
            params=dict(
                offset=offset,
                limit=limit,
                search_query=search_query,
                columns=columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=Page[dict[str, Any]],
        )

    def get_table_row(
        self,
        table_type: str | TableType,
        table_id: str,
        row_id: str,
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ) -> dict[str, Any]:
        """
        Get a specific row in a table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            row_id (str): The ID of the row.
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).

        Returns:
            response (dict[str, Any]): The row data.
        """
        response = self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows/{quote(row_id)}",
            params=dict(
                columns=columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=None,
        )
        return json_loads(response.text)

    def add_table_rows(
        self,
        table_type: str | TableType,
        request: RowAddRequest,
    ) -> GenTableChatResponseType:
        """
        Add rows to a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowAddRequest): The row add request.

        Returns:
            response (GenTableChatResponseType): The row completion.
                In streaming mode, it is a generator that yields a `GenTableStreamReferences` object
                followed by zero or more `GenTableStreamChatCompletionChunk` objects.
                In non-streaming mode, it is a `GenTableRowsChatCompletionChunks` object.
        """
        if request.stream:

            def gen():
                for chunk in self._stream(
                    self.api_base,
                    f"/v1/gen_tables/{table_type}/rows/add",
                    request=request,
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "gen_table.references":
                        yield GenTableStreamReferences.model_validate(chunk)
                    elif chunk["object"] == "gen_table.completion.chunk":
                        yield GenTableStreamChatCompletionChunk.model_validate(chunk)
                    else:
                        raise RuntimeError(f"Unexpected SSE chunk: {chunk}")

            return gen()
        else:
            return self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type}/rows/add",
                request=request,
                response_model=GenTableRowsChatCompletionChunks,
            )

    def regen_table_rows(
        self,
        table_type: str | TableType,
        request: RowRegenRequest,
    ) -> GenTableChatResponseType:
        """
        Regenerate rows in a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowRegenRequest): The row regenerate request.

        Returns:
            response (GenTableChatResponseType): The row completion.
                In streaming mode, it is a generator that yields a `GenTableStreamReferences` object
                followed by zero or more `GenTableStreamChatCompletionChunk` objects.
                In non-streaming mode, it is a `GenTableRowsChatCompletionChunks` object.
        """
        if request.stream:

            def gen():
                for chunk in self._stream(
                    self.api_base,
                    f"/v1/gen_tables/{table_type}/rows/regen",
                    request=request,
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "gen_table.references":
                        yield GenTableStreamReferences.model_validate(chunk)
                    elif chunk["object"] == "gen_table.completion.chunk":
                        yield GenTableStreamChatCompletionChunk.model_validate(chunk)
                    else:
                        raise RuntimeError(f"Unexpected SSE chunk: {chunk}")

            return gen()
        else:
            return self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type}/rows/regen",
                request=request,
                response_model=GenTableRowsChatCompletionChunks,
            )

    def update_table_row(
        self,
        table_type: str | TableType,
        request: RowUpdateRequest,
    ) -> OkResponse:
        """
        Update a specific row in a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowUpdateRequest): The row update request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/rows/update",
            request=request,
            response_model=OkResponse,
        )

    def delete_table_rows(
        self,
        table_type: str | TableType,
        request: RowDeleteRequest,
    ) -> OkResponse:
        """
        Delete rows from a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowDeleteRequest): The row delete request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/rows/delete",
            request=request,
            response_model=OkResponse,
        )

    def delete_table_row(
        self,
        table_type: str | TableType,
        table_id: str,
        row_id: str,
    ) -> OkResponse:
        """
        Delete a specific row from a table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            row_id (str): The ID of the row.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows/{quote(row_id)}",
            params=None,
            response_model=OkResponse,
        )

    def get_conversation_thread(
        self,
        table_id: str,
        row_id: str = "",
        include: bool = True,
    ) -> ChatThread:
        """
        Get the conversation thread for a chat table.

        Args:
            table_id (str): The ID of the chat table.
            row_id (str, optional): Row ID for filtering. Defaults to "" (export all rows).
            include (bool, optional): Whether to include the row specified by `row_id`. Defaults to True.

        Returns:
            response (ChatThread): The conversation thread.
        """
        return self._get(
            self.api_base,
            f"/v1/gen_tables/chat/{quote(table_id)}/thread",
            params=dict(row_id=row_id, include=include),
            response_model=ChatThread,
        )

    def hybrid_search(
        self,
        table_type: str | TableType,
        request: SearchRequest,
    ) -> list[dict[str, Any]]:
        """
        Perform a hybrid search on a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (SearchRequest): The search request.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        response = self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/hybrid_search",
            request=request,
            response_model=None,
        )
        return json_loads(response.text)

    def upload_file(self, request: FileUploadRequest) -> OkResponse:
        """
        Upload a file to a Knowledge Table.

        Args:
            request (FileUploadRequest): The file upload request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        file_path = request.file_path
        # Guess the MIME type of the file based on its extension
        mime_type, _ = guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"  # Default MIME type
        # Extract the filename from the file path
        filename = split(file_path)[-1]
        # Open the file in binary mode
        with open(file_path, "rb") as f:
            response = self._post(
                self.api_base,
                "/v1/gen_tables/knowledge/upload_file",
                request=None,
                response_model=OkResponse,
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
        return response

    def import_table_data(
        self,
        table_type: str | TableType,
        request: TableDataImportRequest,
    ) -> GenTableChatResponseType:
        """
        Imports CSV or TSV data into a table.

        Args:
            file_path (str): CSV or TSV file path.
            table_type (str | TableType): Table type.
            request (TableDataImportRequest): Data import request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        # Guess the MIME type of the file based on its extension
        mime_type, _ = guess_type(request.file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"  # Default MIME type
        # Extract the filename from the file path
        filename = split(request.file_path)[-1]
        data = {
            "file_name": filename,
            "table_id": request.table_id,
            "stream": request.stream,
            # "column_names": request.column_names,
            # "columns": request.columns,
            "delimiter": request.delimiter,
        }
        if request.stream:

            def gen():
                # Open the file in binary mode
                with open(request.file_path, "rb") as f:
                    for chunk in self._stream(
                        self.api_base,
                        f"/v1/gen_tables/{table_type}/import_data",
                        request=None,
                        files={
                            "file": (filename, f, mime_type),
                        },
                        data=data,
                        timeout=None,
                    ):
                        chunk = json_loads(chunk[5:])
                        if chunk["object"] == "gen_table.references":
                            yield GenTableStreamReferences.model_validate(chunk)
                        elif chunk["object"] == "gen_table.completion.chunk":
                            yield GenTableStreamChatCompletionChunk.model_validate(chunk)
                        else:
                            raise RuntimeError(f"Unexpected SSE chunk: {chunk}")

            return gen()
        else:
            # Open the file in binary mode
            with open(request.file_path, "rb") as f:
                return self._post(
                    self.api_base,
                    f"/v1/gen_tables/{table_type}/import_data",
                    request=None,
                    response_model=GenTableRowsChatCompletionChunks,
                    files={
                        "file": (filename, f, mime_type),
                    },
                    data=data,
                    timeout=None,
                )

    def export_table_data(
        self,
        table_type: str | TableType,
        table_id: str,
        columns: list[str] | None = None,
        delimiter: str = ",",
    ) -> bytes:
        """
        Exports the row data of a table as a CSV or TSV file.

        Args:
            table_type (str | TableType): Table type.
            table_id (str): ID or name of the table to be exported.
            delimiter (str, optional): The delimiter of the file: can be "," or "\\t". Defaults to ",".
            columns (list[str], optional): A list of columns to be exported. Defaults to None (export all columns).

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        response = self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/export_data",
            params=dict(delimiter=delimiter, columns=columns),
            response_model=None,
        )
        return response.content

    def import_table(
        self,
        table_type: str | TableType,
        request: TableImportRequest,
    ) -> TableMetaResponse:
        """
        Imports a table with its schema and data from a parquet file.

        Args:
            file_path (str): The parquet file path.
            table_type (str | TableType): Table type.
            request (TableImportRequest): Table import request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        mime_type = "application/octet-stream"
        filename = split(request.file_path)[-1]
        data = {"table_id_dst": request.table_id_dst}
        # Open the file in binary mode
        with open(request.file_path, "rb") as f:
            return self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type}/import",
                request=None,
                response_model=TableMetaResponse,
                files={
                    "file": (filename, f, mime_type),
                },
                data=data,
                timeout=None,
            )

    def export_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> bytes:
        """
        Exports the row data of a table as a parquet file.

        Args:
            table_type (str | TableType): Table type.
            table_id (str): ID or name of the table to be exported.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        response = self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/export",
            params=None,
            response_model=None,
        )
        return response.content


class JamAIAsync(JamAI):
    def __init__(
        self,
        project_id: str = ENV_CONFIG.jamai_project_id,
        api_key: str = ENV_CONFIG.jamai_api_key_plain,
        api_base: str = ENV_CONFIG.jamai_api_base,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> None:
        """
        Initialize the JamAI asynchronous client.

        Args:
            project_id (str, optional): The project ID. Defaults to "default".
            api_key (str, optional): The API key for authentication.
                Defaults to `JAMAI_API_KEY` var in environment or `.env` file.
            api_base (str, optional): The base URL for the API.
                Defaults to `JAMAI_API_BASE` var in environment or `.env` file.
            headers (dict | None, optional): Additional headers to include in requests.
                Defaults to None.
            timeout (float | None, optional): The timeout to use when sending requests.
                Defaults to None (no timeout).
        """
        super().__init__(
            project_id=project_id,
            api_key=api_key,
            api_base=api_base,
            headers=headers,
        )
        self.http_client = httpx.AsyncClient(
            timeout=timeout,
            transport=httpx.AsyncHTTPTransport(retries=3),
        )

    async def close(self) -> None:
        """
        Close the HTTP async client.
        """
        await self.http_client.aclose()

    async def _get(
        self,
        address: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous GET request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return.
            **kwargs (Any): Keyword arguments for `httpx.get`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        response = await self.http_client.get(
            f"{address}{endpoint}",
            params=self._filter_params(params),
            headers=self.headers,
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)

    async def _post(
        self,
        address: str,
        endpoint: str,
        *,
        request: BaseModel | None,
        response_model: Type[BaseModel] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous POST request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            request (BaseModel | None, optional): The request body.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.post`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
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
            return response
        else:
            return response_model.model_validate_json(response.text)

    async def _patch(
        self,
        address: str,
        endpoint: str,
        *,
        request: BaseModel | None,
        response_model: Type[BaseModel] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous PATCH request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            request (BaseModel | None, optional): The request body.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.patch`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
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
            return response
        else:
            return response_model.model_validate_json(response.text)

    async def _stream(
        self,
        address: str,
        endpoint: str,
        *,
        request: BaseModel | None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Make an asynchronous streaming POST request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            request (BaseModel | None, optional): The request body.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.stream`.

        Yields:
            str: The response chunks.
        """
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
        *,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous DELETE request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return.
            **kwargs (Any): Keyword arguments for `httpx.delete`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        response = await self.http_client.delete(
            f"{address}{endpoint}",
            params=self._filter_params(params),
            headers=self.headers,
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)

    # --- Models and chat --- #

    async def model_info(
        self,
        name: str = "",
        capabilities: list[str] | None = None,
    ) -> ModelInfoResponse:
        """
        Get information about available models asynchronously.

        Args:
            name (str, optional): The model name. Defaults to "".
            capabilities (list[str] | None, optional): List of model capabilities to filter by.
                Defaults to None.

        Returns:
            response (ModelInfoResponse): The model information response.
        """
        params = {"model": name, "capabilities": capabilities}
        return await self._get(
            self.api_base,
            "/v1/models",
            params=params,
            response_model=ModelInfoResponse,
        )

    async def model_names(
        self,
        prefer: str = "",
        capabilities: list[str] | None = None,
    ) -> list[str]:
        """
        Get the names of available models asynchronously.

        Args:
            prefer (str, optional): Preferred model name. Defaults to "".
            capabilities (list[str] | None, optional): List of model capabilities to filter by.

        Returns:
            response (list[str]): List of model names.
        """
        params = {"prefer": prefer, "capabilities": capabilities}
        response = await self._get(
            self.api_base,
            "/v1/model_names",
            params=params,
            response_model=None,
        )
        return json_loads(response.text)

    async def generate_chat_completions(
        self, request: ChatRequest
    ) -> ChatCompletionChunk | AsyncGenerator[References | ChatCompletionChunk, None]:
        """
        Generates chat completions asynchronously.

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
                async for chunk in self._stream(
                    self.api_base, "/v1/chat/completions", request=request
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "chat.references":
                        yield References.model_validate(chunk)
                    elif chunk["object"] == "chat.completion.chunk":
                        yield ChatCompletionChunk.model_validate(chunk)

            return gen()
        else:
            return await self._post(
                self.api_base,
                "/v1/chat/completions",
                request=request,
                response_model=ChatCompletionChunk,
            )

    async def generate_embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """
        Generate embeddings for the given input asynchronously.

        Args:
            request (EmbeddingRequest): The embedding request.

        Returns:
            response (EmbeddingResponse): The embedding response.
        """
        return await self._post(
            self.api_base,
            "/v1/embeddings",
            request=request,
            response_model=EmbeddingResponse,
        )

    # --- Gen Table --- #
    async def create_action_table(self, request: ActionTableSchemaCreate) -> TableMetaResponse:
        """
        Create an Action Table asynchronously.

        Args:
            request (ActionTableSchemaCreate): The action table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/action",
            request=request,
            response_model=TableMetaResponse,
        )

    async def create_knowledge_table(
        self, request: KnowledgeTableSchemaCreate
    ) -> TableMetaResponse:
        """
        Create a Knowledge Table asynchronously.

        Args:
            request (KnowledgeTableSchemaCreate): The knowledge table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/knowledge",
            request=request,
            response_model=TableMetaResponse,
        )

    async def create_chat_table(self, request: ChatTableSchemaCreate) -> TableMetaResponse:
        """
        Create a Chat Table asynchronously.

        Args:
            request (ChatTableSchemaCreate): The chat table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/chat",
            request=request,
            response_model=TableMetaResponse,
        )

    async def get_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> TableMetaResponse:
        """
        Get metadata for a specific Generative Table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}",
            params=None,
            response_model=TableMetaResponse,
        )

    async def list_tables(
        self,
        table_type: str | TableType,
        offset: int = 0,
        limit: int = 100,
        parent_id: str | None = None,
        search_query: str = "",
    ) -> Page[TableMetaResponse]:
        """
        List Generative Tables of a specific type asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            offset (int, optional): Pagination offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            parent_id (str | None, optional): Parent ID of tables to return.
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
                Defaults to None (return all tables).
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).

        Returns:
            response (Page[TableMetaResponse]): The paginated table metadata response.
        """
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}",
            params=dict(
                offset=offset, limit=limit, parent_id=parent_id, search_query=search_query
            ),
            response_model=Page[TableMetaResponse],
        )

    async def delete_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> OkResponse:
        """
        Delete a specific table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}",
            params=None,
            response_model=OkResponse,
        )

    async def duplicate_table(
        self,
        table_type: str | TableType,
        table_id_src: str,
        table_id_dst: str,
        include_data: bool = True,
        deploy: bool = False,
    ) -> TableMetaResponse:
        """
        Duplicate a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str): The destination / new table ID.
            include_data (bool, optional): Whether to include data in the duplicated table. Defaults to True.
            deploy (bool, optional): Whether to deploy the duplicated table. Defaults to False.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/duplicate/{quote(table_id_src)}/{quote(table_id_dst)}",
            request=None,
            params=dict(include_data=include_data, deploy=deploy),
            response_model=TableMetaResponse,
        )

    async def create_child_table(
        self,
        table_type: str | TableType,
        table_id_src: str,
        table_id_dst: str | None = None,
    ) -> TableMetaResponse:
        """
        Create a child table from a parent chat table.
        Schema and existing rows are copied over from the parent.

        Args:
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str | None, optional): The destination / new table ID.
                Will be generated if not provided.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """

        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/child/{table_id_src}",
            request=None,
            params=dict(table_id_dst=table_id_dst),
            response_model=TableMetaResponse,
        )

    async def rename_table(
        self,
        table_type: str | TableType,
        table_id_src: str,
        table_id_dst: str,
    ) -> TableMetaResponse:
        """
        Rename a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str): The destination / new table ID.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/rename/{quote(table_id_src)}/{quote(table_id_dst)}",
            request=None,
            response_model=TableMetaResponse,
        )

    async def update_gen_config(
        self,
        table_type: str | TableType,
        request: GenConfigUpdateRequest,
    ) -> TableMetaResponse:
        """
        Update the generation configuration for a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            request (GenConfigUpdateRequest): The generation configuration update request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/gen_config/update",
            request=request,
            response_model=TableMetaResponse,
        )

    async def add_action_columns(self, request: AddActionColumnSchema) -> TableMetaResponse:
        """
        Add columns to an Action Table asynchronously.

        Args:
            request (AddActionColumnSchema): The action column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/action/columns/add",
            request=request,
            response_model=TableMetaResponse,
        )

    async def add_knowledge_columns(self, request: AddKnowledgeColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Knowledge Table asynchronously.

        Args:
            request (AddKnowledgeColumnSchema): The knowledge column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/knowledge/columns/add",
            request=request,
            response_model=TableMetaResponse,
        )

    async def add_chat_columns(self, request: AddChatColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Chat Table asynchronously.

        Args:
            request (AddChatColumnSchema): The chat column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/chat/columns/add",
            request=request,
            response_model=TableMetaResponse,
        )

    async def drop_columns(
        self,
        table_type: str | TableType,
        request: ColumnDropRequest,
    ) -> TableMetaResponse:
        """
        Drop columns from a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            request (ColumnDropRequest): The column drop request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/columns/drop",
            request=request,
            response_model=TableMetaResponse,
        )

    async def rename_columns(
        self,
        table_type: str | TableType,
        request: ColumnRenameRequest,
    ) -> TableMetaResponse:
        """
        Rename columns in a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            request (ColumnRenameRequest): The column rename request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/columns/rename",
            request=request,
            response_model=TableMetaResponse,
        )

    async def reorder_columns(
        self,
        table_type: str | TableType,
        request: ColumnReorderRequest,
    ) -> TableMetaResponse:
        """
        Reorder columns in a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            request (ColumnReorderRequest): The column reorder request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/columns/reorder",
            request=request,
            response_model=TableMetaResponse,
        )

    async def list_table_rows(
        self,
        table_type: str | TableType,
        table_id: str,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Pagination offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).
        """
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows",
            params=dict(
                offset=offset,
                limit=limit,
                search_query=search_query,
                columns=columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=Page[dict[str, Any]],
        )

    async def get_table_row(
        self,
        table_type: str | TableType,
        table_id: str,
        row_id: str,
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ) -> dict[str, Any]:
        """
        Get a specific row in a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            row_id (str): The ID of the row.
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).

        Returns:
            response (dict[str, Any]): The row data.
        """
        response = await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows/{quote(row_id)}",
            params=dict(
                columns=columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=None,
        )
        return json_loads(response.text)

    async def add_table_rows(
        self,
        table_type: str | TableType,
        request: RowAddRequest,
    ) -> (
        GenTableRowsChatCompletionChunks
        | AsyncGenerator[GenTableStreamReferences | GenTableStreamChatCompletionChunk, None]
    ):
        """
        Add rows to a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowAddRequest): The row add request.

        Returns:
            response (GenTableRowsChatCompletionChunks | AsyncGenerator): The row completion.
                In streaming mode, it is an async generator that yields a `GenTableStreamReferences` object
                followed by zero or more `GenTableStreamChatCompletionChunk` objects.
                In non-streaming mode, it is a `GenTableRowsChatCompletionChunks` object.
        """
        if request.stream:

            async def gen():
                async for chunk in self._stream(
                    self.api_base,
                    f"/v1/gen_tables/{table_type}/rows/add",
                    request=request,
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "gen_table.references":
                        yield GenTableStreamReferences.model_validate(chunk)
                    elif chunk["object"] == "gen_table.completion.chunk":
                        yield GenTableStreamChatCompletionChunk.model_validate(chunk)

            return gen()
        else:
            return await self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type}/rows/add",
                request=request,
                response_model=GenTableRowsChatCompletionChunks,
            )

    async def regen_table_rows(
        self,
        table_type: str | TableType,
        request: RowRegenRequest,
    ) -> (
        GenTableRowsChatCompletionChunks
        | AsyncGenerator[GenTableStreamReferences | GenTableStreamChatCompletionChunk, None]
    ):
        """
        Regenerate rows in a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowRegenRequest): The row regenerate request.

        Returns:
            response (GenTableRowsChatCompletionChunks | AsyncGenerator): The row completion.
                In streaming mode, it is an async generator that yields a `GenTableStreamReferences` object
                followed by zero or more `GenTableStreamChatCompletionChunk` objects.
                In non-streaming mode, it is a `GenTableRowsChatCompletionChunks` object.
        """
        if request.stream:

            async def gen():
                async for chunk in self._stream(
                    self.api_base,
                    f"/v1/gen_tables/{table_type}/rows/regen",
                    request=request,
                ):
                    chunk = json_loads(chunk[5:])
                    if chunk["object"] == "gen_table.references":
                        yield GenTableStreamReferences.model_validate(chunk)
                    elif chunk["object"] == "gen_table.completion.chunk":
                        yield GenTableStreamChatCompletionChunk.model_validate(chunk)

            return gen()
        else:
            return await self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type}/rows/regen",
                request=request,
                response_model=GenTableRowsChatCompletionChunks,
            )

    async def update_table_row(
        self,
        table_type: str | TableType,
        request: RowUpdateRequest,
    ) -> OkResponse:
        """
        Update a specific row in a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowUpdateRequest): The row update request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/rows/update",
            request=request,
            response_model=OkResponse,
        )

    async def delete_table_rows(
        self,
        table_type: str | TableType,
        request: RowDeleteRequest,
    ) -> OkResponse:
        """
        Delete rows from a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowDeleteRequest): The row delete request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/rows/delete",
            request=request,
            response_model=OkResponse,
        )

    async def delete_table_row(
        self,
        table_type: str | TableType,
        table_id: str,
        row_id: str,
    ) -> OkResponse:
        """
        Delete a specific row from a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            row_id (str): The ID of the row.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows/{quote(row_id)}",
            params=None,
            response_model=OkResponse,
        )

    async def get_conversation_thread(self, table_id: str) -> ChatThread:
        """
        Get the conversation thread for a chat table asynchronously.

        Args:
            table_id (str): The ID of the chat table.

        Returns:
            response (ChatThread): The conversation thread.
        """
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/chat/{quote(table_id)}/thread",
            params=None,
            response_model=ChatThread,
        )

    async def hybrid_search(
        self,
        table_type: str | TableType,
        request: SearchRequest,
    ) -> list[dict[str, Any]]:
        """
        Perform a hybrid search on a table asynchronously.

        Args:
            table_type (str | TableType): The type of the table.
            request (SearchRequest): The search request.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        response = await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/hybrid_search",
            request=request,
            response_model=None,
        )
        return json_loads(response.text)

    async def upload_file(self, request: FileUploadRequest) -> OkResponse:
        """
        Upload a file to a Knowledge Table asynchronously.

        Args:
            request (FileUploadRequest): The file upload request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        file_path = request.file_path
        # Guess the MIME type of the file based on its extension
        mime_type, _ = guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"  # Default MIME type
        # Extract the filename from the file path
        filename = split(file_path)[-1]
        # Open the file in binary mode
        with open(file_path, "rb") as f:
            response = await self._post(
                self.api_base,
                "/v1/gen_tables/knowledge/upload_file",
                request=None,
                response_model=OkResponse,
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
        return response

    async def import_table_data(
        self,
        table_type: str | TableType,
        request: TableDataImportRequest,
    ) -> GenTableChatResponseType:
        """
        Imports CSV or TSV data into a table.

        Args:
            file_path (str): CSV or TSV file path.
            table_type (str | TableType): Table type.
            request (TableDataImportRequest): Data import request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        # Guess the MIME type of the file based on its extension
        mime_type, _ = guess_type(request.file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"  # Default MIME type
        # Extract the filename from the file path
        filename = split(request.file_path)[-1]
        data = {
            "file_name": filename,
            "table_id": request.table_id,
            "stream": request.stream,
            # "column_names": request.column_names,
            # "columns": request.columns,
            "delimiter": request.delimiter,
        }
        if request.stream:

            async def gen():
                # Open the file in binary mode
                with open(request.file_path, "rb") as f:
                    async for chunk in self._stream(
                        self.api_base,
                        f"/v1/gen_tables/{table_type}/import_data",
                        request=None,
                        files={
                            "file": (filename, f, mime_type),
                        },
                        data=data,
                        timeout=None,
                    ):
                        chunk = json_loads(chunk[5:])
                        if chunk["object"] == "gen_table.references":
                            yield GenTableStreamReferences.model_validate(chunk)
                        elif chunk["object"] == "gen_table.completion.chunk":
                            yield GenTableStreamChatCompletionChunk.model_validate(chunk)
                        else:
                            raise RuntimeError(f"Unexpected SSE chunk: {chunk}")

            return gen()
        else:
            # Open the file in binary mode
            with open(request.file_path, "rb") as f:
                return await self._post(
                    self.api_base,
                    f"/v1/gen_tables/{table_type}/import_data",
                    request=None,
                    response_model=GenTableRowsChatCompletionChunks,
                    files={
                        "file": (filename, f, mime_type),
                    },
                    data=data,
                    timeout=None,
                )

    async def export_table_data(
        self,
        table_type: str | TableType,
        table_id: str,
        columns: list[str] | None = None,
        delimiter: str = ",",
    ) -> bytes:
        """
        Exports the row data of a table as a CSV or TSV file.

        Args:
            table_type (str | TableType): Table type.
            table_id (str): ID or name of the table to be exported.
            delimiter (str, optional): The delimiter of the file: can be "," or "\\t". Defaults to ",".
            columns (list[str], optional): A list of columns to be exported. Defaults to None (export all columns).

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        response = await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/export_data",
            params=dict(delimiter=delimiter, columns=columns),
            response_model=None,
        )
        return response.content

    async def import_table(
        self,
        table_type: str | TableType,
        request: TableImportRequest,
    ) -> TableMetaResponse:
        """
        Imports a table with its schema and data from a parquet file.

        Args:
            file_path (str): The parquet file path.
            table_type (str | TableType): Table type.
            request (TableImportRequest): Table import request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        mime_type = "application/octet-stream"
        filename = split(request.file_path)[-1]
        data = {"table_id_dst": request.table_id_dst}
        # Open the file in binary mode
        with open(request.file_path, "rb") as f:
            return await self._post(
                self.api_base,
                f"/v1/gen_tables/{table_type}/import",
                request=None,
                response_model=TableMetaResponse,
                files={
                    "file": (filename, f, mime_type),
                },
                data=data,
                timeout=None,
            )

    async def export_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> bytes:
        """
        Exports the row data of a table as a parquet file.

        Args:
            table_type (str | TableType): Table type.
            table_id (str): ID or name of the table to be exported.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        response = await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/export",
            params=None,
            response_model=None,
        )
        return response.content
