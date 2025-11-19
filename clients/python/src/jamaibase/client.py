import platform
import warnings
from contextlib import contextmanager
from datetime import datetime
from os.path import basename, split
from time import perf_counter
from typing import Any, AsyncGenerator, BinaryIO, Generator, Literal, Type
from urllib.parse import quote
from warnings import warn

import httpx
import orjson
from loguru import logger
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import deprecated

from jamaibase.types import (
    ActionTableSchemaCreate,
    AddActionColumnSchema,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    AgentMetaResponse,
    CellCompletionResponse,
    CellReferencesResponse,
    ChatCompletionChunkResponse,
    ChatCompletionResponse,
    ChatRequest,
    ChatTableSchemaCreate,
    ChatThreadResponse,
    ChatThreadsResponse,
    ColumnDropRequest,
    ColumnRenameRequest,
    ColumnReorderRequest,
    ConversationCreateRequest,
    ConversationMetaResponse,
    ConversationThreadsResponse,
    DeploymentCreate,
    DeploymentRead,
    DeploymentUpdate,
    EmbeddingRequest,
    EmbeddingResponse,
    FileUploadResponse,
    GenConfigUpdateRequest,
    GetURLRequest,
    GetURLResponse,
    KnowledgeTableSchemaCreate,
    MessageAddRequest,
    MessagesRegenRequest,
    MessageUpdateRequest,
    ModelConfigCreate,
    ModelConfigRead,
    ModelConfigUpdate,
    ModelInfoListResponse,
    ModelPrice,
    MultiRowAddRequest,
    MultiRowCompletionResponse,
    MultiRowDeleteRequest,
    MultiRowRegenRequest,
    MultiRowUpdateRequest,
    OkResponse,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    OrgMemberRead,
    Page,
    PasswordChangeRequest,
    PasswordLoginRequest,
    PricePlanCreate,
    PricePlanRead,
    PricePlanUpdate,
    ProgressState,
    ProjectCreate,
    ProjectKeyCreate,
    ProjectKeyRead,
    ProjectKeyUpdate,
    ProjectMemberRead,
    ProjectRead,
    ProjectUpdate,
    References,
    RerankingRequest,
    RerankingResponse,
    Role,
    RowUpdateRequest,
    SearchRequest,
    StripePaymentInfo,
    TableDataImportRequest,
    TableImportRequest,
    TableMetaResponse,
    UsageResponse,
    UserCreate,
    UserRead,
    UserUpdate,
    VerificationCodeRead,
)
from jamaibase.utils import uuid7_str
from jamaibase.utils.background_loop import LOOP
from jamaibase.utils.exceptions import (
    AuthorizationError,
    BadInputError,
    ForbiddenError,
    JamaiException,
    RateLimitExceedError,
    ResourceExistsError,
    ResourceNotFoundError,
    ServerBusyError,
    UnexpectedError,
)
from jamaibase.utils.io import guess_mime, json_loads
from jamaibase.version import __version__

USER_AGENT = f"SDK/{__version__} (Python/{platform.python_version()}; {platform.system()} {platform.release()}; {platform.machine()})"
ORG_API_KEY_DEPRECATE = "Organization API keys are deprecated, use Personal Access Tokens instead."
TABLE_METHOD_DEPRECATE = "This method is deprecated, use `client.table.<method>` instead."


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="jamai_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    token: SecretStr = ""
    api_base: str = "https://api.jamaibase.com/api"
    project_id: str = "default"
    timeout_sec: float = 60.0 * 5  # Default to 5 minutes
    file_upload_timeout_sec: float = 60.0 * 15  # Default to 15 minutes

    @property
    def token_plain(self):
        return self.token.get_secret_value().strip()


ENV_CONFIG = EnvConfig()
GenTableChatResponseType = (
    MultiRowCompletionResponse
    | Generator[CellReferencesResponse | CellCompletionResponse, None, None]
)


class _ClientAsync:
    def __init__(
        self,
        user_id: str,
        project_id: str,
        token: str,
        api_base: str,
        headers: dict | None,
        http_client: httpx.Client | httpx.AsyncClient,
        timeout: float | None,
        file_upload_timeout: float | None = None,
    ) -> None:
        """
        Base client.

        Args:
            user_id (str): User ID.
            project_id (str): Project ID.
            token (str): Personal Access Token or organization API key (deprecated) for authentication.
            api_base (str): The base URL for the API.
            headers (dict | None): Additional headers to include in requests.
            http_client (httpx.Client | httpx.AsyncClient): The HTTPX client.
        """
        if api_base.endswith("/"):
            api_base = api_base[:-1]
        self.user_id = user_id
        self.project_id = project_id
        self.token = token
        self.api_base = api_base
        self.headers = {
            "X-USER-ID": user_id,
            "X-PROJECT-ID": project_id,
            "User-Agent": USER_AGENT,
        }
        if token != "":
            self.headers["Authorization"] = f"Bearer {token}"
        if headers is not None:
            if not isinstance(headers, dict):
                raise TypeError("`headers` must be None or a dict.")
            self.headers.update(headers)
        self.http_client = http_client
        self.timeout = timeout
        self.file_upload_timeout = file_upload_timeout

    async def close(self) -> None:
        """
        Close the HTTP async client.
        """
        await self.http_client.aclose()

    @staticmethod
    def _filter_params(params: dict[str, Any] | BaseModel | None) -> dict[str, Any] | None:
        """
        Filter out None values from query parameters dictionary or Pydantic model.

        Args:
            params (dict[str, Any] | BaseModel | None): Query parameters dictionary or Pydantic model.

        Returns:
            params (dict[str, Any] | None): Filtered query parameters dictionary.
        """
        if isinstance(params, BaseModel):
            params = params.model_dump()
        if params is not None:
            params = {k: v for k, v in params.items() if v is not None}
        return params

    @staticmethod
    def _process_body(
        body: dict[str, Any] | BaseModel | None,
        **kwargs,
    ) -> dict[str, Any] | None:
        """
        Create a dictionary from request body.

        Args:
            body (dict[str, Any] | BaseModel | None): JSON body dictionary or Pydantic model.
            **kwargs: Keyword arguments to be pass into `model_dump`.

        Returns:
            params (dict[str, Any] | None): JSON body dictionary.
        """
        if body is not None:
            body = body if isinstance(body, dict) else body.model_dump(mode="json", **kwargs)
        return body

    @contextmanager
    def _log_call(self):
        request_id = uuid7_str()
        self.headers["X-REQUEST-ID"] = request_id
        try:
            yield
        except JamaiException:
            raise
        except Exception as e:
            raise JamaiException(f"Request {request_id} failed. {repr(e)}") from e

    @staticmethod
    async def _raise_exception(
        response: httpx.Response,
        *,
        ignore_code: int | None = None,
    ) -> httpx.Response:
        """
        Raise an exception if the response status code is not 200.

        Args:
            response (httpx.Response): The HTTP response.
            ignore_code (int | None, optional): HTTP code to ignore.

        Raises:
            RuntimeError: If the response status code is not 200 and is not ignored by `ignore_code`.

        Returns:
            response (httpx.Response): The HTTP response.
        """
        if "warning" in response.headers:
            warn(response.headers["warning"], stacklevel=2)
        code = response.status_code
        if (200 <= code < 300) or code == ignore_code:
            return response
        try:
            error = response.text
        except httpx.ResponseNotRead:
            error = (await response.aread()).decode()
        try:
            error = json_loads(error)
            err_mssg = error.get("message", error.get("detail", str(error)))
        except Exception:
            err_mssg = error
        request_id = response.headers.get("x-request-id", "<no-request-id>")
        err_mssg = f"Request {request_id} failed. {err_mssg}"
        if code == 401:
            exc_class = AuthorizationError
        elif code == 403:
            exc_class = ForbiddenError
        elif code == 404:
            exc_class = ResourceNotFoundError
        elif code == 409:
            exc_class = ResourceExistsError
        elif code == 422:
            exc_class = BadInputError
        elif code == 429:
            _headers = response.headers
            used = _headers.get("x-ratelimit-used", None)
            retry_after = _headers.get("retry-after", None)
            meta = _headers.get("x-ratelimit-meta", None)
            raise RateLimitExceedError(
                err_mssg,
                limit=int(_headers.get("x-ratelimit-limit", 0)),
                remaining=int(_headers.get("x-ratelimit-remaining", 0)),
                reset_at=int(_headers.get("x-ratelimit-reset", 0)),
                used=None if used is None else int(used),
                retry_after=None if retry_after is None else int(retry_after),
                meta=None if meta is None else orjson.loads(meta),
            )
        elif code == 500:
            exc_class = UnexpectedError
        elif code == 503:
            exc_class = ServerBusyError
        else:
            exc_class = JamaiException
        raise exc_class(err_mssg)

    async def _request(
        self,
        method: str,
        address: str,
        endpoint: str,
        *,
        headers: dict[str, Any] | None = None,
        params: dict[str, Any] | BaseModel | None = None,
        body: BaseModel | dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        timeout: float | None = None,
        ignore_code: int | None = None,
        process_body_kwargs: dict[str, Any] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous request to the specified endpoint.

        Args:
            method (str): The HTTP method to use (e.g., "GET", "POST").
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            headers (dict[str, Any] | None, optional): Headers to include in the request. Defaults to None.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            body (BaseModel | dict[str, Any] | None, optional): The body to send in the request. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            timeout (float | None, optional): Timeout for the request. Defaults to None.
            ignore_code (int | None, optional): HTTP error code to ignore.
            process_body_kwargs (dict[str, Any] | None, optional): Additional keyword arguments for processing the body.
            **kwargs (Any): Keyword arguments for `httpx.request`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        with self._log_call():
            if process_body_kwargs is None:
                process_body_kwargs = {}
            response = await self.http_client.request(
                method,
                f"{address}{endpoint}",
                headers=headers,
                params=self._filter_params(params),
                json=self._process_body(body, **process_body_kwargs),
                timeout=timeout or self.timeout,
                **kwargs,
            )
            response = await self._raise_exception(response, ignore_code=ignore_code)
        if response_model is None:
            return response
        try:
            return response_model.model_validate_json(response.text)
        except Exception as e:
            raise JamaiException(
                f"Failed to parse response (code={response.status_code}): {response.text}"
            ) from e

    async def _get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | BaseModel | None = None,
        response_model: Type[BaseModel] | None = None,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous GET request to the specified endpoint.

        Args:
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            timeout (float | None, optional): Timeout for the request. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.request`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        return await self._request(
            "GET",
            self.api_base,
            endpoint,
            headers=self.headers,
            params=params,
            body=None,
            response_model=response_model,
            timeout=timeout,
            **kwargs,
        )

    async def _post(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | BaseModel | None = None,
        body: BaseModel | None = None,
        response_model: Type[BaseModel] | None = None,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous POST request to the specified endpoint.

        Args:
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            body (BaseModel | None, optional): The body to send in the request. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            timeout (float | None, optional): Timeout for the request. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.request`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        return await self._request(
            "POST",
            self.api_base,
            endpoint,
            headers=self.headers,
            params=params,
            body=body,
            response_model=response_model,
            timeout=timeout,
            **kwargs,
        )

    async def _options(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | BaseModel | None = None,
        response_model: Type[BaseModel] | None = None,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous OPTIONS request to the specified endpoint.

        Args:
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            timeout (float | None, optional): Timeout for the request. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.request`.

        Returns:
            response (httpx.Response | BaseModel): The response or Pydantic response object.
        """
        return await self._request(
            "OPTIONS",
            self.api_base,
            endpoint,
            headers=self.headers,
            params=params,
            body=None,
            response_model=response_model,
            timeout=timeout,
            **kwargs,
        )

    async def _patch(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | BaseModel | None = None,
        body: BaseModel | None = None,
        response_model: Type[BaseModel] | None = None,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous PATCH request to the specified endpoint.

        Args:
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            body (BaseModel | None, optional): The body to send in the request. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            timeout (float | None, optional): Timeout for the request. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.request`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        return await self._request(
            "PATCH",
            self.api_base,
            endpoint,
            headers=self.headers,
            params=params,
            body=body,
            response_model=response_model,
            timeout=timeout,
            process_body_kwargs={"exclude_unset": True},
            **kwargs,
        )

    async def _put(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | BaseModel | None = None,
        body: BaseModel | None = None,
        response_model: Type[BaseModel] | None = None,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous PUT request to the specified endpoint.

        Args:
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            body (BaseModel | None, optional): The body to send in the request. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            timeout (float | None, optional): Timeout for the request. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.request`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        return await self._request(
            "PUT",
            self.api_base,
            endpoint,
            headers=self.headers,
            params=params,
            body=body,
            response_model=response_model,
            timeout=timeout,
            process_body_kwargs={"exclude_unset": True},
            **kwargs,
        )

    async def _stream(
        self,
        endpoint: str,
        *,
        body: BaseModel | None,
        params: dict[str, Any] | BaseModel | None = None,
        timeout: float | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Make an asynchronous streaming POST request to the specified endpoint.

        Args:
            endpoint (str): The API endpoint.
            body (BaseModel | None): The body body.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.stream`.

        Yields:
            str: The response chunks.
        """
        with self._log_call():
            async with self.http_client.stream(
                "POST",
                f"{self.api_base}{endpoint}",
                headers=self.headers,
                params=self._filter_params(params),
                json=self._process_body(body),
                timeout=timeout or self.timeout,
                **kwargs,
            ) as response:
                response = await self._raise_exception(response)
                async for chunk in response.aiter_lines():
                    chunk = chunk.strip()
                    if chunk == "" or chunk == "data: [DONE]":
                        continue
                    yield chunk

    async def _delete(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | BaseModel | None = None,
        response_model: Type[BaseModel] | None = None,
        timeout: float | None = None,
        ignore_code: int | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous DELETE request to the specified endpoint.

        Args:
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            timeout (float | None, optional): Timeout for the request. Defaults to None.
            ignore_code (int | None, optional): HTTP error code to ignore.
            **kwargs (Any): Keyword arguments for `httpx.request`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        return await self._request(
            "DELETE",
            self.api_base,
            endpoint,
            headers=self.headers,
            params=params,
            body=None,
            response_model=response_model,
            timeout=timeout,
            ignore_code=ignore_code,
            **kwargs,
        )

    @staticmethod
    async def _empty_async_generator():
        """Returns an empty asynchronous generator."""
        return
        # This line is never reached, but makes it an async generator
        yield

    @staticmethod
    def _empty_sync_generator():
        """Returns an empty synchronous generator."""
        return
        # This line is never reached, but makes it a sync generator
        yield

    async def _return_async_iterator(
        self,
        agen: AsyncGenerator[Any, None],
        stream_models: list[Type[BaseModel]] | None = None,
    ) -> AsyncGenerator[Any, None]:
        # Get the first chunk outside of the loop so that errors can be raised immediately
        try:
            chunk = await anext(agen)
        except StopAsyncIteration:
            # Return empty async generator
            return self._empty_async_generator()

        def _process(_chunk: str) -> BaseModel | str:
            if stream_models is None:
                return _chunk
            for m in stream_models:
                try:
                    return m.model_validate_json(_chunk[5:])
                except Exception:
                    pass
            raise RuntimeError(f"Unexpected SSE chunk: {chunk}")

        # For streaming responses, return an asynchronous generator
        async def gen():
            nonlocal chunk
            yield _process(chunk)
            async for chunk in agen:
                yield _process(chunk)

        # Directly return the asynchronous generator
        return gen()

    def _return_iterator(
        self,
        agen: AsyncGenerator[Any, None] | Any,
        stream: bool,
    ) -> Generator[Any, None, None] | Any:
        if stream:
            # Get the first chunk outside of the loop so that errors can be raised immediately
            try:
                chunk = LOOP.run(anext(agen))
            except StopAsyncIteration:
                # Return empty sync generator
                return self._empty_sync_generator()

            def gen():
                nonlocal chunk
                yield chunk
                while True:
                    try:
                        yield LOOP.run(anext(agen))
                    except StopAsyncIteration:
                        break

            return gen()
        else:
            return agen


class _AuthAsync(_ClientAsync):
    """Auth methods."""

    async def register_password(self, body: UserCreate, **kwargs) -> UserRead:
        return await self._post(
            "/v2/auth/register/password",
            body=body,
            response_model=UserRead,
            **kwargs,
        )

    async def login_password(self, body: PasswordLoginRequest, **kwargs) -> UserRead:
        return await self._post(
            "/v2/auth/login/password",
            body=body,
            response_model=UserRead,
            **kwargs,
        )

    async def change_password(self, body: PasswordChangeRequest, **kwargs) -> UserRead:
        return await self._patch(
            "/v2/auth/login/password",
            body=body,
            response_model=UserRead,
            **kwargs,
        )


class _PricesAsync(_ClientAsync):
    """Prices methods."""

    async def create_price_plan(self, body: PricePlanCreate, **kwargs) -> PricePlanRead:
        return await self._post(
            "/v2/prices/plans",
            body=body,
            response_model=PricePlanRead,
            **kwargs,
        )

    async def list_price_plans(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[PricePlanRead]:
        return await self._get(
            "/v2/prices/plans/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
            ),
            response_model=Page[PricePlanRead],
            **kwargs,
        )

    async def get_price_plan(
        self,
        plan_id: str,
        **kwargs,
    ) -> PricePlanRead:
        return await self._get(
            "/v2/prices/plans",
            params=dict(price_plan_id=plan_id),
            response_model=PricePlanRead,
            **kwargs,
        )

    async def update_price_plan(
        self,
        plan_id: str,
        body: PricePlanUpdate,
        **kwargs,
    ) -> PricePlanRead:
        return await self._patch(
            "/v2/prices/plans",
            params=dict(price_plan_id=plan_id),
            body=body,
            response_model=PricePlanRead,
            **kwargs,
        )

    async def delete_price_plan(
        self,
        price_plan_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        response = await self._delete(
            "/v2/prices/plans",
            params=dict(price_plan_id=price_plan_id),
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def list_model_prices(self, **kwargs) -> ModelPrice:
        return await self._get(
            "/v2/prices/models/list",
            response_model=ModelPrice,
            **kwargs,
        )


class _UsersAsync(_ClientAsync):
    """Users methods."""

    async def create_user(self, body: UserCreate, **kwargs) -> UserRead:
        return await self._post(
            "/v2/users",
            body=body,
            response_model=UserRead,
            process_body_kwargs={"exclude_unset": True},
            **kwargs,
        )

    async def list_users(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        search_columns: list[str] | None = None,
        after: str | None = None,
        **kwargs,
    ) -> Page[UserRead]:
        params = dict(
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_ascending=order_ascending,
            search_query=search_query,
            after=after,
        )
        if search_columns:
            params["search_columns"] = search_columns
        return await self._get(
            "/v2/users/list",
            params=params,
            response_model=Page[UserRead],
            **kwargs,
        )

    async def get_user(
        self,
        user_id: str | None = None,
        **kwargs,
    ) -> UserRead:
        return await self._get(
            "/v2/users",
            params=dict(user_id=user_id),
            response_model=UserRead,
            **kwargs,
        )

    async def update_user(
        self,
        body: UserUpdate,
        **kwargs,
    ) -> UserRead:
        return await self._patch(
            "/v2/users",
            body=body,
            response_model=UserRead,
            **kwargs,
        )

    async def delete_user(
        self,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        response = await self._delete(
            "/v2/users",
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def create_pat(self, body: ProjectKeyCreate, **kwargs) -> ProjectKeyRead:
        return await self._post(
            "/v2/pats",
            body=body,
            response_model=ProjectKeyRead,
            **kwargs,
        )

    async def list_pats(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ProjectKeyRead]:
        return await self._get(
            "/v2/pats/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
            ),
            response_model=Page[ProjectKeyRead],
            **kwargs,
        )

    async def update_pat(
        self,
        pat_id: str,
        body: ProjectKeyUpdate,
        **kwargs,
    ) -> ProjectKeyRead:
        return await self._patch(
            "/v2/pats",
            params=dict(pat_id=pat_id),
            body=body,
            response_model=ProjectKeyRead,
            **kwargs,
        )

    async def delete_pat(
        self,
        pat_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        response = await self._delete(
            "/v2/pats",
            params=dict(pat_id=pat_id),
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def create_email_verification_code(
        self,
        *,
        valid_days: int = 7,
        **kwargs,
    ) -> VerificationCodeRead:
        """
        Generates an email verification code.

        Args:
            valid_days (int, optional): Code validity in days. Defaults to 7.

        Returns:
            code (InviteCodeRead): Verification code.
        """
        return await self._post(
            "/v2/users/verify/email/code",
            params=dict(valid_days=valid_days),
            body=None,
            response_model=VerificationCodeRead,
            **kwargs,
        )

    async def list_email_verification_codes(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        search_columns: list[str] | None = None,
        after: str | None = None,
        **kwargs,
    ) -> Page[VerificationCodeRead]:
        params = dict(
            offset=offset,
            limit=limit,
            order_by=order_by,
            order_ascending=order_ascending,
            search_query=search_query,
            after=after,
        )
        if search_columns:
            params["search_columns"] = search_columns
        return await self._get(
            "/v2/users/verify/email/code/list",
            params=params,
            response_model=Page[VerificationCodeRead],
            **kwargs,
        )

    async def get_email_verification_code(
        self,
        verification_code: str,
        **kwargs,
    ) -> VerificationCodeRead:
        return await self._get(
            "/v2/users/verify/email/code",
            params=dict(verification_code=verification_code),
            response_model=VerificationCodeRead,
            **kwargs,
        )

    async def revoke_email_verification_code(
        self,
        verification_code: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        response = await self._delete(
            "/v2/users/verify/email/code",
            params=dict(verification_code=verification_code),
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    @deprecated(
        "`delete_email_verification_code` is deprecated, use `revoke_email_verification_code` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    async def delete_email_verification_code(
        self,
        verification_code: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return await self.revoke_email_verification_code(
            verification_code=verification_code,
            missing_ok=missing_ok,
            **kwargs,
        )

    async def verify_email(
        self,
        verification_code: str,
        **kwargs,
    ) -> OkResponse:
        """
        Verify and update user email.

        Args:
            verification_code (str): Verification code.

        Returns:
            ok (OkResponse): Success.
        """
        return await self._post(
            "/v2/users/verify/email",
            params=dict(verification_code=verification_code),
            response_model=OkResponse,
            **kwargs,
        )


class _ModelsAsync(_ClientAsync):
    """Models methods."""

    async def create_model_config(self, body: ModelConfigCreate, **kwargs) -> ModelConfigRead:
        return await self._post(
            "/v2/models/configs",
            body=body,
            response_model=ModelConfigRead,
            **kwargs,
        )

    async def list_model_configs(
        self,
        *,
        organization_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ModelConfigRead]:
        return await self._get(
            "/v2/models/configs/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                organization_id=organization_id,
            ),
            response_model=Page[ModelConfigRead],
            **kwargs,
        )

    async def get_model_config(
        self,
        model_id: str,
        **kwargs,
    ) -> ModelConfigRead:
        return await self._get(
            "/v2/models/configs",
            params=dict(model_id=model_id),
            response_model=ModelConfigRead,
            **kwargs,
        )

    async def update_model_config(
        self,
        model_id: str,
        body: ModelConfigUpdate,
        **kwargs,
    ) -> ModelConfigRead:
        return await self._patch(
            "/v2/models/configs",
            params=dict(model_id=model_id),
            body=body,
            response_model=ModelConfigRead,
            **kwargs,
        )

    async def delete_model_config(
        self,
        model_id: str,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        response = await self._delete(
            "/v2/models/configs",
            params=dict(model_id=model_id),
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def create_deployment(
        self,
        body: DeploymentCreate,
        timeout: float | None = 300.0,
        **kwargs,
    ) -> DeploymentRead:
        return await self._post(
            "/v2/models/deployments/cloud",
            body=body,
            response_model=DeploymentRead,
            timeout=self.timeout if timeout is None else timeout,
            **kwargs,
        )

    async def list_deployments(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[DeploymentRead]:
        return await self._get(
            "/v2/models/deployments/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
            ),
            response_model=Page[DeploymentRead],
            **kwargs,
        )

    async def get_deployment(
        self,
        deployment_id: str,
        **kwargs,
    ) -> DeploymentRead:
        return await self._get(
            "/v2/models/deployments",
            params=dict(deployment_id=deployment_id),
            response_model=DeploymentRead,
            **kwargs,
        )

    async def update_deployment(
        self,
        deployment_id: str,
        body: DeploymentUpdate,
        **kwargs,
    ) -> DeploymentRead:
        return await self._patch(
            "/v2/models/deployments",
            params=dict(deployment_id=deployment_id),
            body=body,
            response_model=DeploymentRead,
            **kwargs,
        )

    async def delete_deployment(self, deployment_id: str, **kwargs) -> OkResponse:
        return await self._delete(
            "/v2/models/deployments",
            params=dict(deployment_id=deployment_id),
            response_model=OkResponse,
            **kwargs,
        )


class _OrganizationsAsync(_ClientAsync):
    """Organization methods."""

    async def create_organization(
        self,
        body: OrganizationCreate,
        **kwargs,
    ) -> OrganizationRead:
        return await self._post(
            "/v2/organizations",
            body=body,
            response_model=OrganizationRead,
            **kwargs,
        )

    async def list_organizations(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[OrganizationRead]:
        return await self._get(
            "/v2/organizations/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
            ),
            response_model=Page[OrganizationRead],
            **kwargs,
        )

    async def get_organization(
        self,
        organization_id: str,
        **kwargs,
    ) -> OrganizationRead:
        return await self._get(
            "/v2/organizations",
            params=dict(organization_id=organization_id),
            response_model=OrganizationRead,
            **kwargs,
        )

    async def update_organization(
        self,
        organization_id: str,
        body: OrganizationUpdate,
        **kwargs,
    ) -> OrganizationRead:
        return await self._patch(
            "/v2/organizations",
            body=body,
            params=dict(organization_id=organization_id),
            response_model=OrganizationRead,
            **kwargs,
        )

    async def delete_organization(
        self,
        organization_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        response = await self._delete(
            "/v2/organizations",
            params=dict(organization_id=organization_id),
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def join_organization(
        self,
        user_id: str,
        *,
        invite_code: str | None = None,
        organization_id: str | None = None,
        role: str | None = None,
        **kwargs,
    ) -> OrgMemberRead:
        return await self._post(
            "/v2/organizations/members",
            params=dict(
                user_id=user_id,
                organization_id=organization_id,
                role=role,
                invite_code=invite_code,
            ),
            body=None,
            response_model=OrgMemberRead,
            **kwargs,
        )

    async def list_members(
        self,
        organization_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[OrgMemberRead]:
        return await self._get(
            "/v2/organizations/members/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                organization_id=organization_id,
            ),
            response_model=Page[OrgMemberRead],
            **kwargs,
        )

    async def get_member(
        self,
        *,
        user_id: str,
        organization_id: str,
        **kwargs,
    ) -> OrgMemberRead:
        return await self._get(
            "/v2/organizations/members",
            params=dict(user_id=user_id, organization_id=organization_id),
            response_model=OrgMemberRead,
            **kwargs,
        )

    async def update_member_role(
        self,
        *,
        user_id: str,
        organization_id: str,
        role: Role,
        **kwargs,
    ) -> OrgMemberRead:
        return await self._patch(
            "/v2/organizations/members/role",
            params=dict(user_id=user_id, organization_id=organization_id, role=role),
            response_model=OrgMemberRead,
            **kwargs,
        )

    async def leave_organization(
        self,
        user_id: str,
        organization_id: str,
        **kwargs,
    ) -> OkResponse:
        return await self._delete(
            "/v2/organizations/members",
            params=dict(
                user_id=user_id,
                organization_id=organization_id,
            ),
            response_model=OkResponse,
            **kwargs,
        )

    async def model_catalogue(
        self,
        *,
        organization_id: str,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ModelConfigRead]:
        return await self._get(
            "/v2/organizations/models/catalogue",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                organization_id=organization_id,
            ),
            response_model=Page[ModelConfigRead],
            **kwargs,
        )

    async def create_invite(
        self,
        *,
        user_email: str,
        organization_id: str,
        role: str,
        valid_days: int = 7,
        **kwargs,
    ) -> VerificationCodeRead:
        """
        Generates an invite token to join an organization.

        Args:
            user_email (str): User email.
            organization_id (str): Organization ID.
            role (str): Organization role.
            valid_days (int, optional): Code validity in days. Defaults to 7.

        Returns:
            code (InviteCodeRead): Invite code.
        """
        return await self._post(
            "/v2/organizations/invites",
            params=dict(
                user_email=user_email,
                organization_id=organization_id,
                role=role,
                valid_days=valid_days,
            ),
            body=None,
            response_model=VerificationCodeRead,
            **kwargs,
        )

    async def generate_invite_token(self, *_, **__):
        raise NotImplementedError("This method is deprecated, use `create_invite` instead.")

    async def list_invites(
        self,
        organization_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[VerificationCodeRead]:
        return await self._get(
            "/v2/organizations/invites/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                organization_id=organization_id,
            ),
            response_model=Page[VerificationCodeRead],
            **kwargs,
        )

    async def revoke_invite(
        self,
        invite_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        response = await self._delete(
            "/v2/organizations/invites",
            params=dict(invite_id=invite_id),
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    @deprecated(
        "`delete_invite` is deprecated, use `revoke_invite` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    async def delete_invite(
        self,
        invite_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return await self.revoke_invite(invite_id=invite_id, missing_ok=missing_ok, **kwargs)

    async def subscribe_plan(
        self,
        organization_id: str,
        price_plan_id: str,
        **kwargs,
    ) -> StripePaymentInfo:
        return await self._patch(
            "/v2/organizations/plan",
            params=dict(organization_id=organization_id, price_plan_id=price_plan_id),
            body=None,
            response_model=StripePaymentInfo,
            **kwargs,
        )

    async def refresh_quota(
        self,
        organization_id: str,
        **kwargs,
    ) -> OrganizationRead:
        return await self._post(
            "/v2/organizations/plan/refresh",
            params=dict(organization_id=organization_id),
            body=None,
            response_model=OrganizationRead,
            **kwargs,
        )

    async def purchase_credits(
        self,
        organization_id: str,
        amount: float,
        *,
        confirm: bool = False,
        off_session: bool = False,
        **kwargs,
    ) -> StripePaymentInfo:
        return await self._post(
            "/v2/organizations/credits",
            params=dict(
                organization_id=organization_id,
                amount=amount,
                confirm=confirm,
                off_session=off_session,
            ),
            body=None,
            response_model=StripePaymentInfo,
            **kwargs,
        )

    async def set_credit_grant(
        self,
        organization_id: str,
        amount: float,
        **kwargs,
    ) -> OkResponse:
        return await self._put(
            "/v2/organizations/credit_grant",
            params=dict(organization_id=organization_id, amount=amount),
            body=None,
            response_model=OkResponse,
            **kwargs,
        )

    async def add_credit_grant(
        self,
        organization_id: str,
        amount: float,
        **kwargs,
    ) -> OkResponse:
        return await self._patch(
            "/v2/organizations/credit_grant",
            params=dict(organization_id=organization_id, amount=amount),
            body=None,
            response_model=OkResponse,
            **kwargs,
        )

    async def get_organization_metrics(
        self,
        metric_id: str,
        from_: datetime,
        org_id: str,
        window_size: str | None = None,
        proj_ids: list[str] | None = None,
        to: datetime | None = None,
        group_by: list[str] | None = None,
        data_source: Literal["clickhouse", "victoriametrics"] = "clickhouse",
        **kwargs,
    ) -> UsageResponse:
        params = {
            "metricId": metric_id,
            "from": from_.isoformat(),  # Use string key to avoid keyword conflict
            "orgId": org_id,
            "windowSize": window_size,
            "projIds": proj_ids,
            "to": to.isoformat() if to else None,
            "groupBy": group_by,
            "dataSource": data_source,
        }
        return await self._get(
            "/v2/organizations/meters/query",
            params=params,
            response_model=UsageResponse,
        )

    # async def get_billing_metrics(
    #     self,
    #     from_: datetime,
    #     window_size: str,
    #     org_id: str,
    #     proj_ids: list[str] | None = None,
    #     to: datetime | None = None,
    #     group_by: list[str] | None = None,
    #     **kwargs,
    # ) -> dict:
    #     params = {
    #         "from": from_.isoformat(),
    #         "window_size": window_size,
    #         "org_id": org_id,
    #         "proj_ids": proj_ids,
    #         "to": to,
    #         "group_by": group_by,
    #     }
    #     return await self._get(
    #         "/v2/organizations/meters/billings",
    #         params=params,
    #         **kwargs,
    #     )


class _ProjectsAsync(_ClientAsync):
    """Project methods."""

    async def create_project(self, body: ProjectCreate, **kwargs) -> ProjectRead:
        return await self._post(
            "/v2/projects",
            body=body,
            response_model=ProjectRead,
            **kwargs,
        )

    async def list_projects(
        self,
        organization_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        order_by: str = "updated_at",
        order_ascending: bool = True,
        list_chat_agents: bool = False,
        **kwargs,
    ) -> Page[ProjectRead]:
        return await self._get(
            "/v2/projects/list",
            params=dict(
                offset=offset,
                limit=limit,
                search_query=search_query,
                order_by=order_by,
                order_ascending=order_ascending,
                organization_id=organization_id,
                list_chat_agents=list_chat_agents,
            ),
            response_model=Page[ProjectRead],
            **kwargs,
        )

    async def get_project(
        self,
        project_id: str,
        **kwargs,
    ) -> ProjectRead:
        return await self._get(
            "/v2/projects",
            params=dict(project_id=project_id),
            response_model=ProjectRead,
            **kwargs,
        )

    async def update_project(
        self,
        project_id: str,
        body: ProjectUpdate,
        **kwargs,
    ) -> ProjectRead:
        return await self._patch(
            "/v2/projects",
            body=body,
            params=dict(project_id=project_id),
            response_model=ProjectRead,
            **kwargs,
        )

    async def delete_project(
        self,
        project_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        response = await self._delete(
            "/v2/projects",
            params=dict(project_id=project_id),
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def create_invite(
        self,
        *,
        user_email: str,
        project_id: str,
        role: str,
        valid_days: int = 7,
        **kwargs,
    ) -> VerificationCodeRead:
        """
        Generates an invite token to join a project.

        Args:
            user_email (str): User email.
            project_id (str): Project ID.
            role (str): Project role.
            valid_days (int, optional): Code validity in days. Defaults to 7.

        Returns:
            code (InviteCodeRead): Invite code.
        """
        return await self._post(
            "/v2/projects/invites",
            params=dict(
                user_email=user_email,
                project_id=project_id,
                role=role,
                valid_days=valid_days,
            ),
            body=None,
            response_model=VerificationCodeRead,
            **kwargs,
        )

    async def list_invites(
        self,
        project_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[VerificationCodeRead]:
        return await self._get(
            "/v2/projects/invites/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                project_id=project_id,
            ),
            response_model=Page[VerificationCodeRead],
            **kwargs,
        )

    async def revoke_invite(
        self,
        invite_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        response = await self._delete(
            "/v2/projects/invites",
            params=dict(invite_id=invite_id),
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    @deprecated(
        "`delete_invite` is deprecated, use `revoke_invite` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    async def delete_invite(
        self,
        invite_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return await self.revoke_invite(invite_id, missing_ok=missing_ok, **kwargs)

    async def join_project(
        self,
        user_id: str,
        *,
        invite_code: str | None = None,
        project_id: str | None = None,
        role: str | None = None,
        **kwargs,
    ) -> ProjectMemberRead:
        return await self._post(
            "/v2/projects/members",
            params=dict(
                user_id=user_id,
                project_id=project_id,
                role=role,
                invite_code=invite_code,
            ),
            body=None,
            response_model=ProjectMemberRead,
            **kwargs,
        )

    async def list_members(
        self,
        project_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ProjectMemberRead]:
        return await self._get(
            "/v2/projects/members/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                project_id=project_id,
            ),
            response_model=Page[ProjectMemberRead],
            **kwargs,
        )

    async def get_member(
        self,
        *,
        user_id: str,
        project_id: str,
        **kwargs,
    ) -> ProjectMemberRead:
        return await self._get(
            "/v2/projects/members",
            params=dict(user_id=user_id, project_id=project_id),
            response_model=ProjectMemberRead,
            **kwargs,
        )

    async def update_member_role(
        self,
        *,
        user_id: str,
        project_id: str,
        role: Role,
        **kwargs,
    ) -> ProjectMemberRead:
        return await self._patch(
            "/v2/projects/members/role",
            params=dict(user_id=user_id, project_id=project_id, role=role),
            response_model=ProjectMemberRead,
            **kwargs,
        )

    async def leave_project(
        self,
        user_id: str,
        project_id: str,
        **kwargs,
    ) -> OkResponse:
        return await self._delete(
            "/v2/projects/members",
            params=dict(
                user_id=user_id,
                project_id=project_id,
            ),
            response_model=OkResponse,
            **kwargs,
        )

    async def import_project(
        self,
        source: str | BinaryIO,
        *,
        project_id: str = "",
        organization_id: str = "",
        **kwargs,
    ) -> ProjectRead:
        """
        Import a project.

        Args:
            source (str | BinaryIO): The parquet file path or file-like object.
                It can be a Project or Template file.
            project_id (str, optional): If given, import tables into this project.
                Defaults to "" (create new project).
            organization_id (str): Organization ID of the new project.
                Only required if creating a new project.

        Returns:
            response (ProjectRead): The imported project.
        """
        migrate = kwargs.pop("migrate", False)  # Temporary, may be removed anytime
        timeout = None if migrate else (kwargs.pop("timeout", None) or self.file_upload_timeout)
        kw = dict(
            endpoint=f"/v2/projects/import/parquet{'/migration' if migrate else ''}",
            body=None,
            response_model=ProjectRead,
            data=dict(project_id=project_id, organization_id=organization_id),
            timeout=timeout,
            **kwargs,
        )
        mime_type = "application/octet-stream"
        if isinstance(source, str):
            filename = split(source)[-1]
            # Open the file in binary mode
            with open(source, "rb") as f:
                return await self._post(
                    files={"file": (filename, f, mime_type)},
                    **kw,
                )
        else:
            filename = "import.parquet"
            return await self._post(
                files={"file": (filename, source, mime_type)},
                **kw,
            )

    async def export_project(
        self,
        project_id: str,
        **kwargs,
    ) -> bytes:
        """
        Export a project as a Project Parquet file.

        Args:
            project_id (str): Project ID "proj_xxx".

        Returns:
            response (bytes): The Parquet file.
        """
        response = await self._get(
            "/v2/projects/export",
            params=dict(project_id=project_id),
            response_model=None,
            **kwargs,
        )
        return response.content

    async def import_template(
        self,
        template_id: str,
        *,
        project_id: str = "",
        organization_id: str = "",
        **kwargs,
    ) -> ProjectRead:
        """
        Import a Template.

        Args:
            template_id (str): Template ID "proj_xxx".
            project_id (str, optional): If given, import tables into this project.
                Defaults to "" (create new project).
            organization_id (str): Organization ID of the new project.
                Only required if creating a new project.

        Returns:
            response (ProjectRead): The imported project.
        """
        return await self._post(
            "/v2/projects/import/template",
            body=None,
            params=dict(
                template_id=template_id,
                project_id=project_id,
                organization_id=organization_id,
            ),
            response_model=ProjectRead,
            **kwargs,
        )

    # async def get_usage_metrics(
    #     self,
    #     type: str,
    #     from_: datetime,
    #     window_size: str,
    #     proj_id: str,
    #     to: datetime | None = None,
    #     group_by: list[str] | None = None,
    #     **kwargs,
    # ) -> dict:
    #     params = {
    #         "type": type,
    #         "from": from_.isoformat(),
    #         "window_size": window_size,
    #         "proj_id": proj_id,
    #         "to": to,
    #         "group_by": group_by,
    #     }
    #     return await self._get(
    #         "/v2/projects/meters/usages",
    #         params=params,
    #         **kwargs,
    #     )

    # async def get_billing_metrics(
    #     self,
    #     from_: datetime,
    #     window_size: str,
    #     proj_id: str,
    #     to: datetime | None = None,
    #     group_by: list[str] | None = None,
    #     **kwargs,
    # ) -> dict:
    #     params = {
    #         "from": from_.isoformat(),
    #         "window_size": window_size,
    #         "proj_id": proj_id,
    #         "to": to,
    #         "group_by": group_by,
    #     }
    #     return await self._get(
    #         "/v2/projects/meters/billings",
    #         params=params,
    #         **kwargs,
    #     )


class _TemplatesAsync(_ClientAsync):
    """Template methods."""

    async def list_templates(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ProjectRead]:
        return await self._get(
            "/v2/templates/list",
            params=dict(
                offset=offset,
                limit=limit,
                search_query=search_query,
                order_by=order_by,
                order_ascending=order_ascending,
            ),
            response_model=Page[ProjectRead],
            **kwargs,
        )

    async def get_template(self, template_id: str, **kwargs) -> ProjectRead:
        return await self._get(
            "/v2/templates",
            params=dict(template_id=template_id),
            response_model=ProjectRead,
            **kwargs,
        )

    async def list_tables(
        self,
        template_id: str,
        table_type: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        parent_id: str | None = None,
        count_rows: bool = False,
        **kwargs,
    ) -> Page[TableMetaResponse]:
        return await self._get(
            f"/v2/templates/gen_tables/{table_type}/list",
            params=dict(
                template_id=template_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                search_query=search_query,
                parent_id=parent_id,
                count_rows=count_rows,
            ),
            response_model=Page[TableMetaResponse],
            **kwargs,
        )

    async def get_table(
        self,
        template_id: str,
        table_type: str,
        table_id: str,
        **kwargs,
    ) -> TableMetaResponse:
        return await self._get(
            f"/v2/templates/gen_tables/{table_type}",
            params=dict(
                template_id=template_id,
                table_id=table_id,
            ),
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def list_table_rows(
        self,
        template_id: str,
        table_type: str,
        table_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "ID",
        order_ascending: bool = True,
        columns: list[str] | None = None,
        search_query: str = "",
        search_columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table.

        Args:
            template_id (str): The ID of the template.
            table_type (str): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            order_by (str, optional): Column name to order by. Defaults to "ID".
            order_ascending (bool, optional): Whether to sort by ascending order. Defaults to True.
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            search_columns (list[str] | None, optional): A list of column names to search for `search_query`.
                Defaults to None (search all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).
        """
        if columns is not None and not isinstance(columns, list):
            raise TypeError("`columns` must be None or a list.")
        return await self._get(
            f"/v2/templates/gen_tables/{table_type}/rows/list",
            params=dict(
                template_id=template_id,
                table_id=table_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                columns=columns,
                search_query=search_query,
                search_columns=search_columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=Page[dict[str, Any]],
            **kwargs,
        )

    async def get_table_row(
        self,
        template_id: str,
        table_type: str,
        table_id: str,
        row_id: str,
        *,
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Get a specific row in a table.

        Args:
            template_id (str): The ID of the template.
            table_type (str): The type of the table.
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
        if columns is not None and not isinstance(columns, list):
            raise TypeError("`columns` must be None or a list.")
        response = await self._get(
            f"/v2/templates/gen_tables/{table_type}/rows",
            params=dict(
                template_id=template_id,
                table_id=table_id,
                row_id=row_id,
                columns=columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=None,
            **kwargs,
        )
        return json_loads(response.text)


class _FileClientAsync(_ClientAsync):
    """File methods."""

    async def upload_file(self, file_path: str, **kwargs) -> FileUploadResponse:
        """
        Uploads a file to the server.

        Args:
            file_path (str): Path to the file to be uploaded.

        Returns:
            response (FileUploadResponse): The response containing the file URI.
        """
        with open(file_path, "rb") as f:
            return await self._post(
                "/v2/files/upload",
                body=None,
                response_model=FileUploadResponse,
                files={
                    "file": (basename(file_path), f, guess_mime(file_path)),
                },
                timeout=self.file_upload_timeout,
                **kwargs,
            )

    async def get_raw_urls(self, uris: list[str], **kwargs) -> GetURLResponse:
        """
        Get download URLs for raw files.

        Args:
            uris (list[str]): List of file URIs to download.

        Returns:
            response (GetURLResponse): The response containing download information for the files.
        """
        return await self._post(
            "/v2/files/url/raw",
            body=GetURLRequest(uris=uris),
            response_model=GetURLResponse,
            **kwargs,
        )

    async def get_thumbnail_urls(self, uris: list[str], **kwargs) -> GetURLResponse:
        """
        Get download URLs for file thumbnails.

        Args:
            uris (list[str]): List of file URIs to get thumbnails for.

        Returns:
            response (GetURLResponse): The response containing download information for the thumbnails.
        """
        return await self._post(
            "/v2/files/url/thumb",
            body=GetURLRequest(uris=uris),
            response_model=GetURLResponse,
            **kwargs,
        )


class _GenTableClientAsync(_ClientAsync):
    """Generative Table methods."""

    # Table CRUD
    async def create_action_table(
        self,
        request: ActionTableSchemaCreate,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Create an Action Table.

        Args:
            request (ActionTableSchemaCreate): The action table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/action",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def create_knowledge_table(
        self,
        request: KnowledgeTableSchemaCreate,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Create a Knowledge Table.

        Args:
            request (KnowledgeTableSchemaCreate): The knowledge table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/knowledge",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def create_chat_table(
        self,
        request: ChatTableSchemaCreate,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Create a Chat Table.

        Args:
            request (ChatTableSchemaCreate): The chat table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/chat",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def duplicate_table(
        self,
        table_type: str,
        table_id_src: str,
        table_id_dst: str | None = None,
        *,
        include_data: bool = True,
        create_as_child: bool = False,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Duplicate a table.

        Args:
            table_type (str): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str | None, optional): The destination / new table ID.
                Defaults to None (create a new table ID automatically).
            include_data (bool, optional): Whether to include data in the duplicated table. Defaults to True.
            create_as_child (bool, optional): Whether the new table is a child table.
                If this is True, then `include_data` will be set to True. Defaults to False.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        if (deploy := kwargs.pop("deploy", None)) is not None:
            warn(
                'The "deploy" argument is deprecated, use "create_as_child" instead.',
                FutureWarning,
                stacklevel=2,
            )
            create_as_child = create_as_child or deploy
        return await self._post(
            f"/v1/gen_tables/{table_type}/duplicate/{quote(table_id_src)}"
            if kwargs.pop("v1", False)
            else f"/v2/gen_tables/{table_type}/duplicate",
            body=None,
            params=dict(
                table_id_src=table_id_src,
                table_id_dst=table_id_dst,
                include_data=include_data,
                create_as_child=create_as_child,
            ),
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def get_table(
        self,
        table_type: str,
        table_id: str,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Get metadata for a specific Generative Table.

        Args:
            table_type (str): The type of the table.
            table_id (str): The ID of the table.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._get(
            f"/v1/gen_tables/{table_type}/{quote(table_id)}"
            if kwargs.pop("v1", False)
            else f"/v2/gen_tables/{table_type}",
            params=dict(table_id=table_id),
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def list_tables(
        self,
        table_type: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        created_by: str | None = None,
        parent_id: str | None = None,
        search_query: str = "",
        count_rows: bool = False,
        **kwargs,
    ) -> Page[TableMetaResponse]:
        """
        List Generative Tables of a specific type.

        Args:
            table_type (str): The type of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            order_by (str, optional): Sort tables by this attribute. Defaults to "updated_at".
            order_ascending (bool, optional): Whether to sort by ascending order. Defaults to True.
            created_by (str | None, optional): Return tables created by this user.
                Defaults to None (return all tables).
            parent_id (str | None, optional): Parent ID of tables to return.
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
                Defaults to None (return all tables).
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).
            count_rows (bool, optional): Whether to count the rows of the tables. Defaults to False.

        Returns:
            response (Page[TableMetaResponse]): The paginated table metadata response.
        """
        if (order_descending := kwargs.pop("order_descending", None)) is not None:
            warn(
                'The "order_descending" argument is deprecated, use "order_ascending" instead.',
                FutureWarning,
                stacklevel=2,
            )
            order_ascending = not order_descending
        return await self._get(
            f"/v1/gen_tables/{table_type}"
            if kwargs.pop("v1", False)
            else f"/v2/gen_tables/{table_type}/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                created_by=created_by,
                parent_id=parent_id,
                search_query=search_query,
                count_rows=count_rows,
            ),
            response_model=Page[TableMetaResponse],
            **kwargs,
        )

    async def rename_table(
        self,
        table_type: str,
        table_id_src: str,
        table_id_dst: str,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Rename a table.

        Args:
            table_type (str): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str): The destination / new table ID.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            f"/v1/gen_tables/{table_type}/rename/{quote(table_id_src)}/{quote(table_id_dst)}"
            if kwargs.pop("v1", False)
            else f"/v2/gen_tables/{table_type}/rename",
            params=dict(
                table_id_src=table_id_src,
                table_id_dst=table_id_dst,
            ),
            body=None,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def delete_table(
        self,
        table_type: str,
        table_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        """
        Delete a specific table.

        Args:
            table_type (str): The type of the table.
            table_id (str): The ID of the table.
            missing_ok (bool, optional): Ignore resource not found error.

        Returns:
            response (OkResponse): The response indicating success.
        """
        response = await self._delete(
            f"/v1/gen_tables/{table_type}/{quote(table_id)}"
            if kwargs.pop("v1", False)
            else f"/v2/gen_tables/{table_type}",
            params=dict(table_id=table_id),
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    # Column CRUD
    async def add_action_columns(
        self,
        request: AddActionColumnSchema,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Add columns to an Action Table.

        Args:
            request (AddActionColumnSchema): The action column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/action/columns/add",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def add_knowledge_columns(
        self,
        request: AddKnowledgeColumnSchema,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Add columns to a Knowledge Table.

        Args:
            request (AddKnowledgeColumnSchema): The knowledge column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/knowledge/columns/add",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def add_chat_columns(
        self,
        request: AddChatColumnSchema,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Add columns to a Chat Table.

        Args:
            request (AddChatColumnSchema): The chat column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/chat/columns/add",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def rename_columns(
        self,
        table_type: str,
        request: ColumnRenameRequest,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Rename columns in a table.

        Args:
            table_type (str): The type of the table.
            request (ColumnRenameRequest): The column rename request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/{table_type}/columns/rename",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def update_gen_config(
        self,
        table_type: str,
        request: GenConfigUpdateRequest,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Update the generation configuration for a table.

        Args:
            table_type (str): The type of the table.
            request (GenConfigUpdateRequest): The generation configuration update request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        if kwargs.pop("v1", False):
            return await self._post(
                f"/v1/gen_tables/{table_type}/gen_config/update",
                body=request,
                response_model=TableMetaResponse,
                process_body_kwargs={"exclude_unset": True},
                **kwargs,
            )
        return await self._patch(
            f"/v2/gen_tables/{table_type}/gen_config",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def reorder_columns(
        self,
        table_type: str,
        request: ColumnReorderRequest,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Reorder columns in a table.

        Args:
            table_type (str): The type of the table.
            request (ColumnReorderRequest): The column reorder request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/{table_type}/columns/reorder",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    async def drop_columns(
        self,
        table_type: str,
        request: ColumnDropRequest,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Drop columns from a table.

        Args:
            table_type (str): The type of the table.
            request (ColumnDropRequest): The column drop request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/{table_type}/columns/drop",
            body=request,
            response_model=TableMetaResponse,
            **kwargs,
        )

    # Row CRUD
    async def add_table_rows(
        self,
        table_type: str,
        request: MultiRowAddRequest,
        **kwargs,
    ) -> (
        MultiRowCompletionResponse
        | AsyncGenerator[CellReferencesResponse | CellCompletionResponse, None]
    ):
        """
        Add rows to a table.

        Args:
            table_type (str): The type of the table.
            request (MultiRowAddRequest): The row add request.

        Returns:
            response (MultiRowCompletionResponse | AsyncGenerator): The row completion.
                In streaming mode, it is an async generator that yields a `CellReferencesResponse` object
                followed by zero or more `CellCompletionResponse` objects.
                In non-streaming mode, it is a `MultiRowCompletionResponse` object.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        if request.stream:
            agen = self._stream(
                f"/{v}/gen_tables/{table_type}/rows/add",
                body=request,
                **kwargs,
            )
            return await self._return_async_iterator(
                agen, [CellCompletionResponse, CellReferencesResponse]
            )
        else:
            return await self._post(
                f"/{v}/gen_tables/{table_type}/rows/add",
                body=request,
                response_model=MultiRowCompletionResponse,
                **kwargs,
            )

    async def list_table_rows(
        self,
        table_type: str,
        table_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "ID",
        order_ascending: bool = True,
        columns: list[str] | None = None,
        where: str = "",
        search_query: str = "",
        search_columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table.

        Args:
            table_type (str): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            order_by (str, optional): Column name to order by. Defaults to "ID".
            order_ascending (bool, optional): Whether to sort by ascending order. Defaults to True.
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            where (str, optional): SQL where clause. Can be nested ie `x = '1' AND ("y (1)" = 2 OR z = '3')`.
                It will be combined other filters using `AND`. Defaults to "" (no filter).
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            search_columns (list[str] | None, optional): A list of column names to search for `search_query`.
                Defaults to None (search all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).
        """
        if (order_descending := kwargs.pop("order_descending", None)) is not None:
            warn(
                'The "order_descending" argument is deprecated, use "order_ascending" instead.',
                FutureWarning,
                stacklevel=2,
            )
            order_ascending = not order_descending
        if columns is not None and not isinstance(columns, list):
            raise TypeError("`columns` must be None or a list.")
        if search_columns is not None and not isinstance(search_columns, list):
            raise TypeError("`search_columns` must be None or a list.")
        return await self._get(
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows"
            if kwargs.pop("v1", False)
            else f"/v2/gen_tables/{table_type}/rows/list",
            params=dict(
                table_id=table_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                columns=columns,
                where=where,
                search_query=search_query,
                search_columns=search_columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=Page[dict[str, Any]],
            **kwargs,
        )

    async def get_table_row(
        self,
        table_type: str,
        table_id: str,
        row_id: str,
        *,
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Get a specific row in a table.

        Args:
            table_type (str): The type of the table.
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
        if columns is not None and not isinstance(columns, list):
            raise TypeError("`columns` must be None or a list.")
        response = await self._get(
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows/{quote(row_id)}"
            if kwargs.pop("v1", False)
            else f"/v2/gen_tables/{table_type}/rows",
            params=dict(
                table_id=table_id,
                row_id=row_id,
                columns=columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=None,
            **kwargs,
        )
        return json_loads(response.text)

    @deprecated(
        "This method is deprecated, use `get_conversation_threads` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    async def get_conversation_thread(
        self,
        table_type: str,
        table_id: str,
        column_id: str,
        *,
        row_id: str = "",
        include: bool = True,
        **kwargs,
    ) -> ChatThreadResponse:
        """
        Get the conversation thread for a column in a table.

        Args:
            table_type (str): The type of the table.
            table_id (str): ID / name of the chat table.
            column_id (str): ID / name of the column to fetch.
            row_id (str, optional): ID / name of the last row in the thread.
                Defaults to "" (export all rows).
            include (bool, optional): Whether to include the row specified by `row_id`.
                Defaults to True.

        Returns:
            response (ChatThreadResponse): The conversation thread.
        """
        return await self._get(
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/thread",
            params=dict(
                table_id=table_id,
                column_id=column_id,
                row_id=row_id,
                include=include,
            ),
            response_model=ChatThreadResponse,
            **kwargs,
        )

    async def get_conversation_threads(
        self,
        table_type: str,
        table_id: str,
        column_ids: list[str] | None = None,
        *,
        row_id: str = "",
        include_row: bool = True,
        **kwargs,
    ) -> ChatThreadsResponse:
        """
        Get all multi-turn / conversation threads from a table.

        Args:
            table_type (str): The type of the table.
            table_id (str): ID / name of the chat table.
            column_ids (list[str] | None): Columns to fetch as conversation threads.
            row_id (str, optional): ID / name of the last row in the thread.
                Defaults to "" (export all rows).
            include_row (bool, optional): Whether to include the row specified by `row_id`.
                Defaults to True.

        Returns:
            response (ChatThreadsResponse): The conversation threads.
        """
        return await self._get(
            f"/v2/gen_tables/{table_type}/threads",
            params=dict(
                table_id=table_id,
                column_ids=column_ids,
                row_id=row_id,
                include_row=include_row,
            ),
            response_model=ChatThreadsResponse,
            **kwargs,
        )

    async def hybrid_search(
        self,
        table_type: str,
        request: SearchRequest,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """
        Perform a hybrid search on a table.

        Args:
            table_type (str): The type of the table.
            request (SearchRequest): The search request.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        response = await self._post(
            f"/{v}/gen_tables/{table_type}/hybrid_search",
            body=request,
            response_model=None,
            **kwargs,
        )
        return json_loads(response.text)

    async def regen_table_rows(
        self,
        table_type: str,
        request: MultiRowRegenRequest,
        **kwargs,
    ) -> (
        MultiRowCompletionResponse
        | AsyncGenerator[CellReferencesResponse | CellCompletionResponse, None]
    ):
        """
        Regenerate rows in a table.

        Args:
            table_type (str): The type of the table.
            request (MultiRowRegenRequest): The row regenerate request.

        Returns:
            response (MultiRowCompletionResponse | AsyncGenerator): The row completion.
                In streaming mode, it is an async generator that yields a `CellReferencesResponse` object
                followed by zero or more `CellCompletionResponse` objects.
                In non-streaming mode, it is a `MultiRowCompletionResponse` object.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        if request.stream:
            agen = self._stream(
                f"/{v}/gen_tables/{table_type}/rows/regen",
                body=request,
                **kwargs,
            )
            return await self._return_async_iterator(
                agen, [CellCompletionResponse, CellReferencesResponse]
            )
        else:
            return await self._post(
                f"/{v}/gen_tables/{table_type}/rows/regen",
                body=request,
                response_model=MultiRowCompletionResponse,
                **kwargs,
            )

    async def update_table_rows(
        self,
        table_type: str,
        request: MultiRowUpdateRequest,
        **kwargs,
    ) -> OkResponse:
        """
        Update rows in a table.

        Args:
            table_type (str): The type of the table.
            request (MultiRowUpdateRequest): The row update request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self._patch(
            f"/v2/gen_tables/{table_type}/rows",
            body=request,
            response_model=OkResponse,
            **kwargs,
        )

    @deprecated(
        "This method is deprecated, use `update_table_rows` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    async def update_table_row(
        self,
        table_type: str,
        request: RowUpdateRequest,
        **kwargs,
    ) -> OkResponse:
        """
        Update a specific row in a table.

        Args:
            table_type (str): The type of the table.
            request (RowUpdateRequest): The row update request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self._post(
            f"/v1/gen_tables/{table_type}/rows/update",
            body=request,
            response_model=OkResponse,
            **kwargs,
        )

    async def delete_table_rows(
        self,
        table_type: str,
        request: MultiRowDeleteRequest,
        **kwargs,
    ) -> OkResponse:
        """
        Delete rows from a table.

        Args:
            table_type (str): The type of the table.
            request (MultiRowDeleteRequest): The row delete request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        return await self._post(
            f"/{v}/gen_tables/{table_type}/rows/delete",
            body=request,
            response_model=OkResponse,
            **kwargs,
        )

    @deprecated(
        "This method is deprecated, use `delete_table_rows` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    async def delete_table_row(
        self,
        table_type: str,
        table_id: str,
        row_id: str,
        **kwargs,
    ) -> OkResponse:
        """
        Delete a specific row from a table.

        Args:
            table_type (str): The type of the table.
            table_id (str): The ID of the table.
            row_id (str): The ID of the row.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self._delete(
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows/{quote(row_id)}",
            params=None,
            response_model=OkResponse,
            **kwargs,
        )

    async def embed_file_options(self, **kwargs) -> httpx.Response:
        """
        Get CORS preflight options for file embedding endpoint.

        Returns:
            response (httpx.Response): The response containing options information.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        response = await self._options(
            f"/{v}/gen_tables/knowledge/embed_file",
            **kwargs,
        )
        return response

    async def embed_file(
        self,
        file_path: str,
        table_id: str,
        *,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        **kwargs,
    ) -> OkResponse:
        """
        Embed a file into a Knowledge Table.

        Args:
            file_path (str): File path of the document to be embedded.
            table_id (str): Knowledge Table ID / name.
            chunk_size (int, optional): Maximum chunk size (number of characters). Must be > 0.
                Defaults to 1000.
            chunk_overlap (int, optional): Overlap in characters between chunks. Must be >= 0.
                Defaults to 200.

        Returns:
            response (OkResponse): The response indicating success.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        # Open the file in binary mode
        with open(file_path, "rb") as f:
            response = await self._post(
                f"/{v}/gen_tables/knowledge/embed_file",
                body=None,
                response_model=OkResponse,
                files={
                    "file": (basename(file_path), f, guess_mime(file_path)),
                },
                data={
                    "table_id": table_id,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    # "overwrite": request.overwrite,
                },
                timeout=self.file_upload_timeout,
                **kwargs,
            )
        return response

    # Import export
    async def import_table_data(
        self,
        table_type: str,
        request: TableDataImportRequest,
        **kwargs,
    ) -> GenTableChatResponseType:
        """
        Imports CSV or TSV data into a table.

        Args:
            file_path (str): CSV or TSV file path.
            table_type (str): Table type.
            request (TableDataImportRequest): Data import request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        v = "v1" if kwargs.pop("v1", False) else "v2"
        data = {
            "table_id": request.table_id,
            "stream": request.stream,
            # "column_names": request.column_names,
            # "columns": request.columns,
            "delimiter": request.delimiter,
        }
        file_path = request.file_path
        if request.stream:
            # Open the file in binary mode
            with open(file_path, "rb") as f:
                agen = self._stream(
                    f"/{v}/gen_tables/{table_type}/import_data",
                    body=None,
                    files={"file": (basename(file_path), f, guess_mime(file_path))},
                    data=data,
                    timeout=self.file_upload_timeout,
                    **kwargs,
                )
                return await self._return_async_iterator(
                    agen, [CellCompletionResponse, CellReferencesResponse]
                )
        else:
            # Open the file in binary mode
            with open(request.file_path, "rb") as f:
                return await self._post(
                    f"/{v}/gen_tables/{table_type}/import_data",
                    body=None,
                    response_model=MultiRowCompletionResponse,
                    files={
                        "file": (basename(file_path), f, guess_mime(file_path)),
                    },
                    data=data,
                    timeout=self.file_upload_timeout,
                    **kwargs,
                )

    async def export_table_data(
        self,
        table_type: str,
        table_id: str,
        *,
        columns: list[str] | None = None,
        delimiter: Literal[",", "\t"] = ",",
        **kwargs,
    ) -> bytes:
        """
        Exports the row data of a table as a CSV or TSV file.

        Args:
            table_type (str): Table type.
            table_id (str): ID or name of the table to be exported.
            delimiter (str, optional): The delimiter of the file: can be "," or "\\t". Defaults to ",".
            columns (list[str], optional): A list of columns to be exported. Defaults to None (export all columns).

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        if columns is not None and not isinstance(columns, list):
            raise TypeError("`columns` must be None or a list.")
        response = await self._get(
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/export_data"
            if kwargs.pop("v1", False)
            else f"/v2/gen_tables/{table_type}/export_data",
            params=dict(table_id=table_id, delimiter=delimiter, columns=columns),
            response_model=None,
            **kwargs,
        )
        return response.content

    async def import_table(
        self,
        table_type: str,
        request: TableImportRequest,
        **kwargs,
    ) -> TableMetaResponse | OkResponse:
        """
        Imports a table (data and schema) from a parquet file.

        Args:
            file_path (str): The parquet file path.
            table_type (str): Table type.
            request (TableImportRequest): Table import request.

        Returns:
            response (TableMetaResponse | OkResponse): The table metadata response if blocking is True,
                otherwise OkResponse.
        """
        migrate = kwargs.pop("migrate", False)  # Temporary, may be removed anytime
        reupload = (
            kwargs.pop("reupload", False) or not migrate
        )  # Temporary, may be removed anytime, but if migrate == False then this must be True
        timeout = None if migrate else (kwargs.pop("timeout", None) or self.file_upload_timeout)
        v = "v1" if kwargs.pop("v1", False) else "v2"
        mime_type = "application/octet-stream"
        filename = split(request.file_path)[-1]
        # Open the file in binary mode
        with open(request.file_path, "rb") as f:
            return await self._post(
                f"/{v}/gen_tables/{table_type}/import",
                body=None,
                response_model=TableMetaResponse if request.blocking else OkResponse,
                files={
                    "file": (filename, f, mime_type),
                },
                data=dict(**self._process_body(request), migrate=migrate, reupload=reupload),
                timeout=timeout,
                **kwargs,
            )

    async def export_table(
        self,
        table_type: str,
        table_id: str,
        **kwargs,
    ) -> bytes:
        """
        Exports a table (data and schema) as a parquet file.

        Args:
            table_type (str): Table type.
            table_id (str): ID or name of the table to be exported.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        response = await self._get(
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/export"
            if kwargs.pop("v1", False)
            else f"/v2/gen_tables/{table_type}/export",
            params=dict(table_id=table_id),
            response_model=None,
            **kwargs,
        )
        return response.content


class _MeterClientAsync(_ClientAsync):
    """Meter methods."""

    async def get_usage_metrics(
        self,
        type: Literal["llm", "embedding", "reranking"],
        from_: datetime,
        window_size: str,
        org_ids: list[str] | None = None,
        proj_ids: list[str] | None = None,
        to: datetime | None = None,
        group_by: list[str] | None = None,
        data_source: Literal["clickhouse", "victoriametrics"] = "clickhouse",
    ) -> UsageResponse:
        params = {
            "type": type,
            "from": from_.isoformat(),  # Use string key to avoid keyword conflict
            "orgIds": org_ids,
            "windowSize": window_size,
            "projIds": proj_ids,
            "to": to.isoformat() if to else None,
            "groupBy": group_by,
            "dataSource": data_source,
        }
        return await self._get(
            "/v2/meters/usages",
            params=params,
            response_model=UsageResponse,
        )

    async def get_billing_metrics(
        self,
        from_: datetime,
        window_size: str,
        org_ids: list[str] | None = None,
        proj_ids: list[str] | None = None,
        to: datetime | None = None,
        group_by: list[str] | None = None,
        data_source: Literal["clickhouse", "victoriametrics"] = "clickhouse",
    ) -> UsageResponse:
        params = {
            "from": from_.isoformat(),  # Use string key to avoid keyword conflict
            "orgIds": org_ids,
            "windowSize": window_size,
            "projIds": proj_ids,
            "to": to.isoformat() if to else None,
            "groupBy": group_by,
            "dataSource": data_source,
        }
        return await self._get(
            "/v2/meters/billings",
            params=params,
            response_model=UsageResponse,
        )

    async def get_bandwidth_metrics(
        self,
        from_: datetime,
        window_size: str,
        org_ids: list[str] | None = None,
        proj_ids: list[str] | None = None,
        to: datetime | None = None,
        group_by: list[str] | None = None,
        data_source: Literal["clickhouse", "victoriametrics"] = "clickhouse",
    ) -> UsageResponse:
        params = {
            "from": from_.isoformat(),  # Use string key to avoid keyword conflict
            "orgIds": org_ids,
            "windowSize": window_size,
            "projIds": proj_ids,
            "to": to.isoformat() if to else None,
            "groupBy": group_by,
            "dataSource": data_source,
        }
        return await self._get(
            "/v2/meters/bandwidths",
            params=params,
            response_model=UsageResponse,
        )

    async def get_storage_metrics(
        self,
        from_: datetime,
        window_size: str,
        org_ids: list[str] | None = None,
        proj_ids: list[str] | None = None,
        to: datetime | None = None,
        group_by: list[str] | None = None,
    ) -> UsageResponse:
        params = {
            "from": from_.isoformat(),  # Use string key to avoid keyword conflict
            "orgIds": org_ids,
            "windowSize": window_size,
            "projIds": proj_ids,
            "to": to.isoformat() if to else None,
            "groupBy": group_by,
        }
        return await self._get(
            "/v2/meters/storages",
            params=params,
            response_model=UsageResponse,
        )


class _TaskClientAsync(_ClientAsync):
    """Task methods."""

    async def get_progress(
        self,
        key: str,
        **kwargs,
    ) -> dict[str, Any]:
        response = await self._get(
            "/v2/progress",
            params=dict(key=key),
            response_model=None,
            **kwargs,
        )
        return json_loads(response.text)

    async def poll_progress(
        self,
        key: str,
        *,
        initial_wait: float = 0.5,
        max_wait: float = 30 * 60.0,
        verbose: bool = False,
        **kwargs,
    ) -> dict[str, Any] | None:
        from asyncio import sleep

        i = 1
        t0 = perf_counter()
        while (perf_counter() - t0) < max_wait:
            await sleep(min(initial_wait * i, 5.0))
            prog = await self.get_progress(key, **kwargs)
            state = prog.get("state", None)
            error = prog.get("error", None)
            if verbose:
                logger.info(
                    f"{self.__class__.__name__}: Progress: key={key} state={state}"
                    + (f" error={error}" if error else "")
                )
            if state == ProgressState.COMPLETED:
                return prog
            elif state == ProgressState.FAILED:
                raise JamaiException(prog.get("error", "Unknown error"))
            i += 1
        return None


class _ConversationClientAsync(_ClientAsync):
    """Conversation methods."""

    async def create_conversation(
        self,
        request: ConversationCreateRequest,
        **kwargs,
    ) -> AsyncGenerator[
        ConversationMetaResponse | CellReferencesResponse | CellCompletionResponse, None
    ]:
        """
        Creates a new conversation and sends the first message.
        Yields metadata first, then the message stream.
        """
        agen = self._stream("/v2/conversations", body=request, **kwargs)
        current_event = None
        # Get the first chunk outside of the loop so that errors can be raised immediately
        try:
            chunk = await anext(agen)
        except StopAsyncIteration:
            # Return empty async generator
            return self._empty_async_generator()

        def _process(
            _chunk: str,
        ) -> ConversationMetaResponse | CellCompletionResponse | CellReferencesResponse | None:
            nonlocal current_event
            if _chunk.startswith("event:"):
                current_event = _chunk[6:].strip()
                return None

            if _chunk.startswith("data:"):
                data_obj = json_loads(_chunk[5:])

                if current_event == "metadata":
                    # This is the special metadata event
                    current_event = None  # Reset for next events
                    return ConversationMetaResponse.model_validate(data_obj)
                else:
                    # This is a standard gen_table chunk
                    if data_obj.get("object") == "gen_table.completion.chunk":
                        return CellCompletionResponse.model_validate(data_obj)
                    elif data_obj.get("object") == "gen_table.references":
                        return CellReferencesResponse.model_validate(data_obj)
                    else:
                        pass

        async def gen():
            nonlocal chunk
            res = _process(chunk)
            if res is not None:
                yield res
            async for chunk in agen:
                res = _process(chunk)
                if res is not None:
                    yield res

        return gen()

    async def list_conversations(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        **kwargs,
    ) -> Page[ConversationMetaResponse]:
        """Lists all conversations for the authenticated user."""
        return await self._get(
            "/v2/conversations/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                search_query=search_query,
            ),
            response_model=Page[ConversationMetaResponse],
            **kwargs,
        )

    async def list_agents(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        **kwargs,
    ) -> Page[ConversationMetaResponse]:
        """Lists all available agents for the authenticated user."""
        return await self._get(
            "/v2/conversations/agents/list",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                search_query=search_query,
            ),
            response_model=Page[ConversationMetaResponse],
            **kwargs,
        )

    async def get_conversation(self, conversation_id: str, **kwargs) -> ConversationMetaResponse:
        """Fetches metadata for a single conversation."""
        return await self._get(
            "/v2/conversations",
            params={"conversation_id": conversation_id},
            response_model=ConversationMetaResponse,
            **kwargs,
        )

    async def get_agent(self, agent_id: str, **kwargs) -> AgentMetaResponse:
        """Fetches metadata for a single agent."""
        return await self._get(
            "/v2/conversations/agents",
            params={"agent_id": agent_id},
            response_model=AgentMetaResponse,
            **kwargs,
        )

    async def generate_title(
        self,
        conversation_id: str,
        **kwargs,
    ) -> ConversationMetaResponse:
        """Generates a title for a conversation."""
        return await self._post(
            "/v2/conversations/title",
            params=dict(conversation_id=conversation_id),
            body=None,
            response_model=ConversationMetaResponse,
            **kwargs,
        )

    async def rename_conversation_title(
        self,
        conversation_id: str,
        title: str,
        **kwargs,
    ) -> ConversationMetaResponse:
        """Renames conversation title."""
        return await self._patch(
            "/v2/conversations/title",
            params=dict(conversation_id=conversation_id, title=title),
            body=None,
            response_model=ConversationMetaResponse,
            **kwargs,
        )

    async def delete_conversation(
        self,
        conversation_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        """Deletes a conversation permanently."""
        response = await self._delete(
            "/v2/conversations",
            params={"conversation_id": conversation_id},
            response_model=None,
            ignore_code=404 if missing_ok else None,
            **kwargs,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def send_message(
        self,
        request: MessageAddRequest,
        **kwargs,
    ) -> AsyncGenerator[CellReferencesResponse | CellCompletionResponse, None]:
        """
        Sends a message to a conversation and streams back the response.
        Note: This endpoint currently only supports streaming responses from the server.
        """
        agen = self._stream(
            "/v2/conversations/messages",
            body=request,
            **kwargs,
        )
        return await self._return_async_iterator(
            agen, [CellCompletionResponse, CellReferencesResponse]
        )

    async def list_messages(
        self,
        conversation_id: str,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "ID",
        order_ascending: bool = True,
        columns: list[str] | None = None,
        search_query: str = "",
        search_columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> Page[dict[str, Any]]:
        """Fetches all messages in a conversation."""
        return await self._get(
            "/v2/conversations/messages/list",
            params=dict(
                conversation_id=conversation_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                columns=columns,
                search_query=search_query,
                search_columns=search_columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=Page[dict[str, Any]],
            **kwargs,
        )

    async def regen_message(
        self,
        request: MessagesRegenRequest,
        **kwargs,
    ) -> AsyncGenerator[CellReferencesResponse | CellCompletionResponse, None]:
        """
        Regenerates a message in a conversation and streams back the response.
        """
        agen = self._stream(
            "/v2/conversations/messages/regen",
            body=request,
            **kwargs,
        )
        return await self._return_async_iterator(
            agen, [CellCompletionResponse, CellReferencesResponse]
        )

    async def update_message(
        self,
        request: MessageUpdateRequest,
        **kwargs,
    ) -> OkResponse:
        """Updates a specific message within a conversation."""
        return await self._patch(
            "/v2/conversations/messages",
            body=request,
            response_model=OkResponse,
            **kwargs,
        )

    async def get_threads(
        self,
        conversation_id: str,
        column_ids: list[str] | None = None,
        **kwargs,
    ) -> ConversationThreadsResponse:
        """
        Get all threads from a conversation.

        Args:
            conversation_id (str): Conversation ID.
            column_ids (list[str] | None): Columns to fetch as conversation threads.

        Returns:
            response (ConversationThreadsResponse): The conversation threads.
        """
        return await self._get(
            "/v2/conversations/threads",
            params=dict(
                conversation_id=conversation_id,
                column_ids=column_ids,
            ),
            response_model=ConversationThreadsResponse,
            **kwargs,
        )


class JamAIAsync(_ClientAsync):
    def __init__(
        self,
        project_id: str = ENV_CONFIG.project_id,
        token: str = ENV_CONFIG.token_plain,
        api_base: str = ENV_CONFIG.api_base,
        headers: dict | None = None,
        timeout: float | None = ENV_CONFIG.timeout_sec,
        file_upload_timeout: float | None = ENV_CONFIG.file_upload_timeout_sec,
        *,
        user_id: str = "",
    ) -> None:
        """
        Initialize the JamAI async client.

        Args:
            project_id (str, optional): The project ID.
                Defaults to "default", but can be overridden via
                `JAMAI_PROJECT_ID` var in environment or `.env` file.
            token (str, optional): Your Personal Access Token or organization API key (deprecated) for authentication.
                Defaults to "", but can be overridden via
                `JAMAI_TOKEN` var in environment or `.env` file.
            api_base (str, optional): The base URL for the API.
                Defaults to "https://api.jamaibase.com/api", but can be overridden via
                `JAMAI_API_BASE` var in environment or `.env` file.
            headers (dict | None, optional): Additional headers to include in requests.
                Defaults to None.
            timeout (float | None, optional): The timeout to use when sending requests.
                Defaults to 15 minutes, but can be overridden via
                `JAMAI_TIMEOUT_SEC` var in environment or `.env` file.
            file_upload_timeout (float | None, optional): The timeout to use when sending file upload requests.
                Defaults to 60 minutes, but can be overridden via
                `JAMAI_FILE_UPLOAD_TIMEOUT_SEC` var in environment or `.env` file.
            user_id (str, optional): User ID. For development purposes.
                Defaults to "".
        """
        if not isinstance(project_id, str):
            raise TypeError("`project_id` must be a string.")
        if not isinstance(token, str):
            raise TypeError("`token` must be a string.")
        if not isinstance(api_base, str):
            raise TypeError("`api_base` must be a string.")
        if not (isinstance(headers, dict) or headers is None):
            raise TypeError("`headers` must be a dict or None.")
        if not (isinstance(timeout, (float, int)) or timeout is None):
            raise TypeError("`timeout` must be a float, int or None.")
        if not (isinstance(file_upload_timeout, (float, int)) or file_upload_timeout is None):
            raise TypeError("`file_upload_timeout` must be a float, int or None.")
        if not isinstance(user_id, str):
            raise TypeError("`user_id` must be a string.")
        http_client = httpx.AsyncClient(
            timeout=timeout,
            transport=httpx.AsyncHTTPTransport(retries=3),
        )
        kwargs = dict(
            user_id=user_id,
            project_id=project_id,
            token=token,
            api_base=api_base,
            headers=headers,
            http_client=http_client,
            timeout=timeout,
            file_upload_timeout=file_upload_timeout,
        )
        super().__init__(**kwargs)
        self.auth = _AuthAsync(**kwargs)
        self.prices = _PricesAsync(**kwargs)
        self.users = _UsersAsync(**kwargs)
        self.models = _ModelsAsync(**kwargs)
        self.organizations = _OrganizationsAsync(**kwargs)
        self.projects = _ProjectsAsync(**kwargs)
        self.templates = _TemplatesAsync(**kwargs)
        self.file = _FileClientAsync(**kwargs)
        self.table = _GenTableClientAsync(**kwargs)
        self.meters = _MeterClientAsync(**kwargs)
        self.tasks = _TaskClientAsync(**kwargs)
        self.conversations = _ConversationClientAsync(**kwargs)

    async def health(self) -> dict[str, Any]:
        """
        Get health status.

        Returns:
            response (dict[str, Any]): Health status.
        """
        response = await self._get("/health", response_model=None)
        return json_loads(response.text)

    # --- Models and chat --- #

    async def model_info(
        self,
        model: str = "",
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]
        ]
        | None = None,
        **kwargs,
    ) -> ModelInfoListResponse:
        """
        Get information about available models.

        Args:
            name (str, optional): The model name. Defaults to "".
            capabilities (list[Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]] | None, optional):
                List of model capabilities to filter by. Defaults to None.

        Returns:
            response (ModelInfoListResponse): The model information response.
        """
        if (name := kwargs.pop("name", None)) is not None:
            warnings.warn(
                "'name' parameter is deprecated, use 'model' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            model = name
        return await self._get(
            "/v1/models",
            params=dict(model=model, capabilities=capabilities),
            response_model=ModelInfoListResponse,
            **kwargs,
        )

    async def model_ids(
        self,
        prefer: str = "",
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]
        ]
        | None = None,
        **kwargs,
    ) -> list[str]:
        """
        Get the IDs of available models.

        Args:
            prefer (str, optional): Preferred model ID. Defaults to "".
            capabilities (list[Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]] | None, optional):
                List of model capabilities to filter by. Defaults to None.

        Returns:
            response (list[str]): List of model IDs.
        """
        params = {"prefer": prefer, "capabilities": capabilities}
        response = await self._get(
            "/v1/models/ids",
            params=params,
            response_model=None,
            **kwargs,
        )
        return json_loads(response.text)

    @deprecated(
        "This method is deprecated, use `model_ids` instead.", category=FutureWarning, stacklevel=1
    )
    async def model_names(
        self,
        prefer: str = "",
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]
        ]
        | None = None,
        **kwargs,
    ) -> list[str]:
        return await self.model_ids(prefer=prefer, capabilities=capabilities, **kwargs)

    async def generate_chat_completions(
        self,
        request: ChatRequest,
        **kwargs,
    ) -> ChatCompletionResponse | AsyncGenerator[References | ChatCompletionChunkResponse, None]:
        """
        Generates chat completions.

        Args:
            request (ChatRequest): The request.

        Returns:
            completion (ChatCompletionChunkResponse | AsyncGenerator): The chat completion.
                In streaming mode, it is an async generator that yields a `References` object
                followed by zero or more `ChatCompletionChunkResponse` objects.
                In non-streaming mode, it is a `ChatCompletionChunkResponse` object.
        """
        body = self._process_body(request)
        if request.stream:
            agen = self._stream("/v1/chat/completions", body=body, **kwargs)
            return await self._return_async_iterator(
                agen, [ChatCompletionChunkResponse, References]
            )
        else:
            return await self._post(
                "/v1/chat/completions",
                body=body,
                response_model=ChatCompletionResponse,
                **kwargs,
            )

    async def generate_embeddings(
        self,
        request: EmbeddingRequest,
        **kwargs,
    ) -> EmbeddingResponse:
        """
        Generate embeddings for the given input.

        Args:
            request (EmbeddingRequest): The embedding request.

        Returns:
            response (EmbeddingResponse): The embedding response.
        """
        return await self._post(
            "/v1/embeddings",
            body=request,
            response_model=EmbeddingResponse,
            **kwargs,
        )

    async def rerank(self, request: RerankingRequest, **kwargs) -> RerankingResponse:
        """
        Generate similarity rankings for the given query and documents.

        Args:
            request (RerankingRequest): The reranking request body.

        Returns:
            RerankingResponse: The reranking response.
        """
        return await self._post(
            "/v1/rerank",
            body=request,
            response_model=RerankingResponse,
            **kwargs,
        )


class _Auth(_AuthAsync):
    """Auth methods."""

    def register_password(self, body: UserCreate, **kwargs) -> UserRead:
        return LOOP.run(super().register_password(body, **kwargs))

    def login_password(self, body: PasswordLoginRequest, **kwargs) -> UserRead:
        return LOOP.run(super().login_password(body, **kwargs))

    def change_password(self, body: PasswordChangeRequest, **kwargs) -> UserRead:
        return LOOP.run(super().change_password(body, **kwargs))


class _Prices(_PricesAsync):
    """Prices methods."""

    def create_price_plan(
        self,
        body: PricePlanCreate,
        **kwargs,
    ) -> PricePlanRead:
        return LOOP.run(super().create_price_plan(body, **kwargs))

    def list_price_plans(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[PricePlanRead]:
        return LOOP.run(
            super().list_price_plans(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def get_price_plan(
        self,
        plan_id: str,
        **kwargs,
    ) -> PricePlanRead:
        return LOOP.run(super().get_price_plan(plan_id=plan_id, **kwargs))

    def update_price_plan(
        self,
        plan_id: str,
        body: PricePlanUpdate,
        **kwargs,
    ) -> PricePlanRead:
        return LOOP.run(super().update_price_plan(plan_id, body, **kwargs))

    def delete_price_plan(
        self,
        price_plan_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> None:
        return LOOP.run(super().delete_price_plan(price_plan_id, missing_ok=missing_ok, **kwargs))

    def list_model_prices(self, **kwargs) -> ModelPrice:
        return LOOP.run(super().list_model_prices(**kwargs))


class _Users(_UsersAsync):
    """Users methods."""

    def create_user(self, body: UserCreate, **kwargs) -> UserRead:
        return LOOP.run(super().create_user(body, **kwargs))

    def list_users(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        search_columns: list[str] | None = None,
        after: str | None = None,
        **kwargs,
    ) -> Page[UserRead]:
        return LOOP.run(
            super().list_users(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                search_query=search_query,
                search_columns=search_columns,
                after=after,
                **kwargs,
            )
        )

    def get_user(
        self,
        user_id: str | None = None,
        **kwargs,
    ) -> UserRead:
        return LOOP.run(super().get_user(user_id, **kwargs))

    def update_user(
        self,
        body: UserUpdate,
        **kwargs,
    ) -> UserRead:
        return LOOP.run(super().update_user(body, **kwargs))

    def delete_user(
        self,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(super().delete_user(missing_ok=missing_ok, **kwargs))

    def create_pat(self, body: ProjectKeyCreate, **kwargs) -> ProjectKeyRead:
        return LOOP.run(super().create_pat(body, **kwargs))

    def list_pats(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ProjectKeyRead]:
        return LOOP.run(
            super().list_pats(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def update_pat(
        self,
        pat_id: str,
        body: ProjectKeyUpdate,
        **kwargs,
    ) -> ProjectKeyRead:
        return LOOP.run(super().update_pat(pat_id, body, **kwargs))

    def delete_pat(
        self,
        pat_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(super().delete_pat(pat_id, missing_ok=missing_ok, **kwargs))

    def create_email_verification_code(
        self,
        *,
        valid_days: int = 7,
        **kwargs,
    ) -> VerificationCodeRead:
        """
        Generates an email verification code.

        Args:
            valid_days (int, optional): Code validity in days. Defaults to 7.

        Returns:
            code (InviteCodeRead): Verification code.
        """
        return LOOP.run(super().create_email_verification_code(valid_days=valid_days, **kwargs))

    def list_email_verification_codes(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        search_columns: list[str] | None = None,
        after: str | None = None,
        **kwargs,
    ) -> Page[VerificationCodeRead]:
        return LOOP.run(
            super().list_email_verification_codes(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                search_query=search_query,
                search_columns=search_columns,
                after=after,
                **kwargs,
            )
        )

    def get_email_verification_code(
        self,
        verification_code: str,
        **kwargs,
    ) -> VerificationCodeRead:
        return LOOP.run(
            super().get_email_verification_code(
                verification_code=verification_code,
                **kwargs,
            )
        )

    def revoke_email_verification_code(
        self,
        verification_code: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().revoke_email_verification_code(
                verification_code=verification_code,
                missing_ok=missing_ok,
                **kwargs,
            )
        )

    @deprecated(
        "`delete_email_verification_code` is deprecated, use `revoke_email_verification_code` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    def delete_email_verification_code(
        self,
        verification_code: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().delete_email_verification_code(
                verification_code=verification_code,
                missing_ok=missing_ok,
                **kwargs,
            )
        )

    def verify_email(
        self,
        verification_code: str,
        **kwargs,
    ) -> OkResponse:
        """
        Verify and update user email.

        Args:
            verification_code (str): Verification code.

        Returns:
            ok (OkResponse): Success.
        """
        return LOOP.run(super().verify_email(verification_code=verification_code, **kwargs))


class _Models(_ModelsAsync):
    """Models methods."""

    def create_model_config(self, body: ModelConfigCreate, **kwargs) -> ModelConfigRead:
        return LOOP.run(super().create_model_config(body, **kwargs))

    def list_model_configs(
        self,
        *,
        organization_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ModelConfigRead]:
        return LOOP.run(
            super().list_model_configs(
                organization_id=organization_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def get_model_config(
        self,
        model_id: str,
        **kwargs,
    ) -> ModelConfigRead:
        return LOOP.run(super().get_model_config(model_id, **kwargs))

    def update_model_config(
        self,
        model_id: str,
        body: ModelConfigUpdate,
        **kwargs,
    ) -> ModelConfigRead:
        return LOOP.run(super().update_model_config(model_id, body, **kwargs))

    def delete_model_config(
        self,
        model_id: str,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(super().delete_model_config(model_id, missing_ok=missing_ok, **kwargs))

    def create_deployment(
        self,
        body: DeploymentCreate,
        timeout: float | None = 300.0,
        **kwargs,
    ) -> DeploymentRead:
        return LOOP.run(super().create_deployment(body, timeout=timeout, **kwargs))

    def list_deployments(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[DeploymentRead]:
        return LOOP.run(
            super().list_deployments(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def get_deployment(
        self,
        deployment_id: str,
        **kwargs,
    ) -> DeploymentRead:
        return LOOP.run(super().get_deployment(deployment_id, **kwargs))

    def update_deployment(
        self,
        deployment_id: str,
        body: DeploymentUpdate,
        **kwargs,
    ) -> DeploymentRead:
        return LOOP.run(super().update_deployment(deployment_id, body, **kwargs))

    def delete_deployment(self, deployment_id: str, **kwargs) -> OkResponse:
        return LOOP.run(super().delete_deployment(deployment_id, **kwargs))


class _Organizations(_OrganizationsAsync):
    """Organization methods."""

    def create_organization(
        self,
        body: OrganizationCreate,
        **kwargs,
    ) -> OrganizationRead:
        return LOOP.run(super().create_organization(body, **kwargs))

    def list_organizations(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[OrganizationRead]:
        return LOOP.run(
            super().list_organizations(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def get_organization(
        self,
        organization_id: str,
        **kwargs,
    ) -> OrganizationRead:
        return LOOP.run(super().get_organization(organization_id, **kwargs))

    def update_organization(
        self,
        organization_id: str,
        body: OrganizationUpdate,
        **kwargs,
    ) -> OrganizationRead:
        return LOOP.run(super().update_organization(organization_id, body, **kwargs))

    def delete_organization(
        self,
        organization_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().delete_organization(organization_id, missing_ok=missing_ok, **kwargs)
        )

    def join_organization(
        self,
        user_id: str,
        *,
        invite_code: str | None = None,
        organization_id: str | None = None,
        role: str | None = None,
        **kwargs,
    ) -> OrgMemberRead:
        return LOOP.run(
            super().join_organization(
                user_id=user_id,
                invite_code=invite_code,
                organization_id=organization_id,
                role=role,
                **kwargs,
            )
        )

    def list_members(
        self,
        organization_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[OrgMemberRead]:
        return LOOP.run(
            super().list_members(
                organization_id=organization_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def get_member(
        self,
        *,
        user_id: str,
        organization_id: str,
        **kwargs,
    ) -> OrgMemberRead:
        return LOOP.run(
            super().get_member(
                user_id=user_id,
                organization_id=organization_id,
                **kwargs,
            )
        )

    def update_member_role(
        self,
        *,
        user_id: str,
        organization_id: str,
        role: Role,
        **kwargs,
    ) -> OrgMemberRead:
        return LOOP.run(
            super().update_member_role(
                user_id=user_id,
                organization_id=organization_id,
                role=role,
                **kwargs,
            )
        )

    def leave_organization(
        self,
        user_id: str,
        organization_id: str,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().leave_organization(
                user_id=user_id,
                organization_id=organization_id,
                **kwargs,
            )
        )

    def model_catalogue(
        self,
        *,
        organization_id: str,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ModelConfigRead]:
        return LOOP.run(
            super().model_catalogue(
                organization_id=organization_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def create_invite(
        self,
        *,
        user_email: str,
        organization_id: str,
        role: str,
        valid_days: int = 7,
        **kwargs,
    ) -> VerificationCodeRead:
        return LOOP.run(
            super().create_invite(
                user_email=user_email,
                organization_id=organization_id,
                role=role,
                valid_days=valid_days,
                **kwargs,
            )
        )

    def generate_invite_token(self, *_, **__):
        raise NotImplementedError("This method is deprecated, use `create_invite` instead.")

    def list_invites(
        self,
        organization_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[VerificationCodeRead]:
        return LOOP.run(
            super().list_invites(
                organization_id=organization_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def revoke_invite(
        self,
        invite_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ):
        return LOOP.run(
            super().revoke_invite(invite_id=invite_id, missing_ok=missing_ok, **kwargs)
        )

    @deprecated(
        "`delete_invite` is deprecated, use `revoke_invite` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    def delete_invite(
        self,
        invite_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().delete_invite(
                invite_id=invite_id,
                missing_ok=missing_ok,
                **kwargs,
            )
        )

    def subscribe_plan(
        self,
        organization_id: str,
        price_plan_id: str,
        **kwargs,
    ) -> StripePaymentInfo:
        return LOOP.run(
            super().subscribe_plan(
                organization_id=organization_id,
                price_plan_id=price_plan_id,
                **kwargs,
            )
        )

    def refresh_quota(
        self,
        organization_id: str,
        **kwargs,
    ) -> OrganizationRead:
        return LOOP.run(
            super().refresh_quota(
                organization_id=organization_id,
                **kwargs,
            )
        )

    def purchase_credits(
        self,
        organization_id: str,
        amount: float,
        *,
        confirm: bool = False,
        off_session: bool = False,
        **kwargs,
    ) -> StripePaymentInfo:
        return LOOP.run(
            super().purchase_credits(
                organization_id=organization_id,
                amount=amount,
                confirm=confirm,
                off_session=off_session,
                **kwargs,
            )
        )

    def set_credit_grant(
        self,
        organization_id: str,
        amount: float,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().set_credit_grant(
                organization_id=organization_id,
                amount=amount,
                **kwargs,
            )
        )

    def add_credit_grant(
        self,
        organization_id: str,
        amount: float,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().add_credit_grant(
                organization_id=organization_id,
                amount=amount,
                **kwargs,
            )
        )

    def get_organization_metrics(
        self,
        metric_id: str,
        from_: datetime,
        org_id: str,
        window_size: str | None = None,
        proj_ids: list[str] | None = None,
        to: datetime | None = None,
        group_by: list[str] | None = None,
        data_source: Literal["clickhouse", "victoriametrics"] = "clickhouse",
        **kwargs,
    ) -> UsageResponse:
        return LOOP.run(
            super().get_organization_metrics(
                metric_id=metric_id,
                from_=from_,
                org_id=org_id,
                window_size=window_size,
                proj_ids=proj_ids,
                to=to,
                group_by=group_by,
                data_source=data_source,
                **kwargs,
            )
        )

    # def get_billing_metrics(
    #     self,
    #     from_: datetime,
    #     window_size: str,
    #     org_id: str,
    #     proj_ids: list[str] | None = None,
    #     to: datetime | None = None,
    #     group_by: list[str] | None = None,
    #     **kwargs,
    # ) -> dict:
    #     return LOOP.run(
    #         super().get_billing_metrics(
    #             from_=from_,
    #             window_size=window_size,
    #             org_id=org_id,
    #             proj_ids=proj_ids,
    #             to=to,
    #             group_by=group_by,
    #             **kwargs,
    #         )
    #     )


class _Projects(_ProjectsAsync):
    """Project methods."""

    def create_project(self, body: ProjectCreate, **kwargs) -> ProjectRead:
        return LOOP.run(super().create_project(body, **kwargs))

    def list_projects(
        self,
        organization_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        order_by: str = "updated_at",
        order_ascending: bool = True,
        list_chat_agents: bool = False,
        **kwargs,
    ) -> Page[ProjectRead]:
        return LOOP.run(
            super().list_projects(
                organization_id=organization_id,
                offset=offset,
                limit=limit,
                search_query=search_query,
                order_by=order_by,
                order_ascending=order_ascending,
                list_chat_agents=list_chat_agents,
                **kwargs,
            )
        )

    def get_project(
        self,
        project_id: str,
        **kwargs,
    ) -> ProjectRead:
        return LOOP.run(super().get_project(project_id, **kwargs))

    def update_project(
        self,
        project_id: str,
        body: ProjectUpdate,
        **kwargs,
    ) -> ProjectRead:
        return LOOP.run(super().update_project(project_id, body, **kwargs))

    def delete_project(
        self,
        project_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(super().delete_project(project_id, missing_ok=missing_ok, **kwargs))

    def join_project(
        self,
        user_id: str,
        *,
        invite_code: str | None = None,
        project_id: str | None = None,
        role: str | None = None,
        **kwargs,
    ) -> ProjectMemberRead:
        return LOOP.run(
            super().join_project(
                user_id=user_id,
                invite_code=invite_code,
                project_id=project_id,
                role=role,
                **kwargs,
            )
        )

    def list_members(
        self,
        project_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ProjectMemberRead]:
        return LOOP.run(
            super().list_members(
                project_id=project_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def get_member(
        self,
        *,
        user_id: str,
        project_id: str,
        **kwargs,
    ) -> ProjectMemberRead:
        return LOOP.run(
            super().get_member(
                user_id=user_id,
                project_id=project_id,
                **kwargs,
            )
        )

    def update_member_role(
        self,
        *,
        user_id: str,
        project_id: str,
        role: Role,
        **kwargs,
    ) -> ProjectMemberRead:
        return LOOP.run(
            super().update_member_role(
                user_id=user_id,
                project_id=project_id,
                role=role,
                **kwargs,
            )
        )

    def leave_project(
        self,
        user_id: str,
        project_id: str,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().leave_project(
                user_id=user_id,
                project_id=project_id,
                **kwargs,
            )
        )

    def import_project(
        self,
        source: str | BinaryIO,
        *,
        project_id: str = "",
        organization_id: str = "",
        **kwargs,
    ) -> ProjectRead:
        return LOOP.run(
            super().import_project(
                source=source,
                project_id=project_id,
                organization_id=organization_id,
                **kwargs,
            )
        )

    def export_project(
        self,
        project_id: str,
        **kwargs,
    ) -> bytes:
        return LOOP.run(
            super().export_project(
                project_id=project_id,
                **kwargs,
            )
        )

    def import_template(
        self,
        template_id: str,
        *,
        project_id: str = "",
        organization_id: str = "",
        **kwargs,
    ) -> ProjectRead:
        return LOOP.run(
            super().import_template(
                template_id=template_id,
                project_id=project_id,
                organization_id=organization_id,
                **kwargs,
            )
        )

    def create_invite(
        self,
        *,
        user_email: str,
        project_id: str,
        role: str,
        valid_days: int = 7,
        **kwargs,
    ) -> VerificationCodeRead:
        return LOOP.run(
            super().create_invite(
                user_email=user_email,
                project_id=project_id,
                role=role,
                valid_days=valid_days,
                **kwargs,
            )
        )

    def list_invites(
        self,
        project_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[VerificationCodeRead]:
        return LOOP.run(
            super().list_invites(
                project_id=project_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def revoke_invite(
        self,
        invite_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ):
        return LOOP.run(
            super().revoke_invite(invite_id=invite_id, missing_ok=missing_ok, **kwargs)
        )

    @deprecated(
        "`delete_invite` is deprecated, use `revoke_invite` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    def delete_invite(
        self,
        invite_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().delete_invite(
                invite_id=invite_id,
                missing_ok=missing_ok,
                **kwargs,
            )
        )


class _Templates(_TemplatesAsync):
    """Template methods."""

    def list_templates(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        order_by: str = "updated_at",
        order_ascending: bool = True,
        **kwargs,
    ) -> Page[ProjectRead]:
        return LOOP.run(
            super().list_templates(
                offset=offset,
                limit=limit,
                search_query=search_query,
                order_by=order_by,
                order_ascending=order_ascending,
                **kwargs,
            )
        )

    def get_template(self, template_id: str, **kwargs) -> ProjectRead:
        return LOOP.run(super().get_template(template_id, **kwargs))

    def list_tables(
        self,
        template_id: str,
        table_type: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        parent_id: str | None = None,
        count_rows: bool = False,
        **kwargs,
    ) -> Page[TableMetaResponse]:
        return LOOP.run(
            super().list_tables(
                template_id=template_id,
                table_type=table_type,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                search_query=search_query,
                parent_id=parent_id,
                count_rows=count_rows,
                **kwargs,
            )
        )

    def get_table(
        self,
        template_id: str,
        table_type: str,
        table_id: str,
        **kwargs,
    ) -> TableMetaResponse:
        return LOOP.run(
            super().get_table(
                template_id=template_id,
                table_type=table_type,
                table_id=table_id,
                **kwargs,
            )
        )

    def list_table_rows(
        self,
        template_id: str,
        table_type: str,
        table_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "ID",
        order_ascending: bool = True,
        columns: list[str] | None = None,
        search_query: str = "",
        search_columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table.

        Args:
            template_id (str): The ID of the template.
            table_type (str): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            order_by (str, optional): Column name to order by. Defaults to "ID".
            order_ascending (bool, optional): Whether to sort by ascending order. Defaults to True.
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            search_columns (list[str] | None, optional): A list of column names to search for `search_query`.
                Defaults to None (search all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).
        """
        return LOOP.run(
            super().list_table_rows(
                template_id=template_id,
                table_type=table_type,
                table_id=table_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                columns=columns,
                search_query=search_query,
                search_columns=search_columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
                **kwargs,
            )
        )

    def get_table_row(
        self,
        template_id: str,
        table_type: str,
        table_id: str,
        row_id: str,
        *,
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Get a specific row in a table.

        Args:
            template_id (str): The ID of the template.
            table_type (str): The type of the table.
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
        return LOOP.run(
            super().get_table_row(
                template_id=template_id,
                table_type=table_type,
                table_id=table_id,
                row_id=row_id,
                columns=columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
                **kwargs,
            )
        )


class _FileClient(_FileClientAsync):
    """File methods (synchronous version)."""

    def upload_file(self, file_path: str, **kwargs) -> FileUploadResponse:
        return LOOP.run(super().upload_file(file_path, **kwargs))

    def get_raw_urls(self, uris: list[str], **kwargs) -> GetURLResponse:
        return LOOP.run(super().get_raw_urls(uris, **kwargs))

    def get_thumbnail_urls(self, uris: list[str], **kwargs) -> GetURLResponse:
        return LOOP.run(super().get_thumbnail_urls(uris, **kwargs))


class _GenTableClient(_GenTableClientAsync):
    """Generative Table methods (synchronous version)."""

    # Table CRUD
    def create_action_table(
        self,
        request: ActionTableSchemaCreate,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Create an Action Table.

        Args:
            request (ActionTableSchemaCreate): The action table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().create_action_table(request, **kwargs))

    def create_knowledge_table(
        self,
        request: KnowledgeTableSchemaCreate,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Create a Knowledge Table.

        Args:
            request (KnowledgeTableSchemaCreate): The knowledge table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().create_knowledge_table(request, **kwargs))

    def create_chat_table(
        self,
        request: ChatTableSchemaCreate,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Create a Chat Table.

        Args:
            request (ChatTableSchemaCreate): The chat table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().create_chat_table(request, **kwargs))

    def duplicate_table(
        self,
        table_type: str,
        table_id_src: str,
        table_id_dst: str | None = None,
        *,
        include_data: bool = True,
        create_as_child: bool = False,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Duplicate a table.

        Args:
            table_type (str): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str | None, optional): The destination / new table ID.
                Defaults to None (create a new table ID automatically).
            include_data (bool, optional): Whether to include data in the duplicated table. Defaults to True.
            create_as_child (bool, optional): Whether the new table is a child table.
                If this is True, then `include_data` will be set to True. Defaults to False.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(
            super().duplicate_table(
                table_type,
                table_id_src,
                table_id_dst=table_id_dst,
                include_data=include_data,
                create_as_child=create_as_child,
                **kwargs,
            )
        )

    def get_table(
        self,
        table_type: str,
        table_id: str,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Get metadata for a specific Generative Table.

        Args:
            table_type (str): The type of the table.
            table_id (str): The ID of the table.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().get_table(table_type, table_id, **kwargs))

    def list_tables(
        self,
        table_type: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        created_by: str | None = None,
        parent_id: str | None = None,
        search_query: str = "",
        count_rows: bool = False,
        **kwargs,
    ) -> Page[TableMetaResponse]:
        """
        List Generative Tables of a specific type.

        Args:
            table_type (str): The type of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            order_by (str, optional): Sort tables by this attribute. Defaults to "updated_at".
            order_ascending (bool, optional): Whether to sort by ascending order. Defaults to True.
            created_by (str | None, optional): Return tables created by this user.
                Defaults to None (return all tables).
            parent_id (str | None, optional): Parent ID of tables to return.
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
                Defaults to None (return all tables).
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).
            count_rows (bool, optional): Whether to count the rows of the tables. Defaults to False.

        Returns:
            response (Page[TableMetaResponse]): The paginated table metadata response.
        """
        return LOOP.run(
            super().list_tables(
                table_type,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                created_by=created_by,
                parent_id=parent_id,
                search_query=search_query,
                count_rows=count_rows,
                **kwargs,
            )
        )

    def rename_table(
        self,
        table_type: str,
        table_id_src: str,
        table_id_dst: str,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Rename a table.

        Args:
            table_type (str): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str): The destination / new table ID.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().rename_table(table_type, table_id_src, table_id_dst, **kwargs))

    def delete_table(
        self,
        table_type: str,
        table_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        """
        Delete a specific table.

        Args:
            table_type (str): The type of the table.
            table_id (str): The ID of the table.
            missing_ok (bool, optional): Ignore resource not found error.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return LOOP.run(
            super().delete_table(
                table_type,
                table_id,
                missing_ok=missing_ok,
                **kwargs,
            )
        )

    # Column CRUD
    def add_action_columns(
        self,
        request: AddActionColumnSchema,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Add columns to an Action Table.

        Args:
            request (AddActionColumnSchema): The action column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().add_action_columns(request, **kwargs))

    def add_knowledge_columns(
        self,
        request: AddKnowledgeColumnSchema,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Add columns to a Knowledge Table.

        Args:
            request (AddKnowledgeColumnSchema): The knowledge column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().add_knowledge_columns(request, **kwargs))

    def add_chat_columns(
        self,
        request: AddChatColumnSchema,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Add columns to a Chat Table.

        Args:
            request (AddChatColumnSchema): The chat column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().add_chat_columns(request, **kwargs))

    def rename_columns(
        self,
        table_type: str,
        request: ColumnRenameRequest,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Rename columns in a table.

        Args:
            table_type (str): The type of the table.
            request (ColumnRenameRequest): The column rename request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().rename_columns(table_type, request, **kwargs))

    def update_gen_config(
        self,
        table_type: str,
        request: GenConfigUpdateRequest,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Update the generation configuration for a table.

        Args:
            table_type (str): The type of the table.
            request (GenConfigUpdateRequest): The generation configuration update request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().update_gen_config(table_type, request, **kwargs))

    def reorder_columns(
        self,
        table_type: str,
        request: ColumnReorderRequest,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Reorder columns in a table.

        Args:
            table_type (str): The type of the table.
            request (ColumnReorderRequest): The column reorder request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().reorder_columns(table_type, request, **kwargs))

    def drop_columns(
        self,
        table_type: str,
        request: ColumnDropRequest,
        **kwargs,
    ) -> TableMetaResponse:
        """
        Drop columns from a table.

        Args:
            table_type (str): The type of the table.
            request (ColumnDropRequest): The column drop request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return LOOP.run(super().drop_columns(table_type, request, **kwargs))

    # Row CRUD
    def add_table_rows(
        self,
        table_type: str,
        request: MultiRowAddRequest,
        **kwargs,
    ) -> (
        MultiRowCompletionResponse
        | Generator[CellReferencesResponse | CellCompletionResponse, None, None]
    ):
        """
        Add rows to a table.

        Args:
            table_type (str): The type of the table.
            request (MultiRowAddRequest): The row add request.

        Returns:
            response (MultiRowCompletionResponse | AsyncGenerator): The row completion.
                In streaming mode, it is an async generator that yields a `CellReferencesResponse` object
                followed by zero or more `CellCompletionResponse` objects.
                In non-streaming mode, it is a `MultiRowCompletionResponse` object.
        """
        agen = LOOP.run(super().add_table_rows(table_type, request, **kwargs))
        return self._return_iterator(agen, request.stream)

    def list_table_rows(
        self,
        table_type: str,
        table_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "ID",
        order_ascending: bool = True,
        columns: list[str] | None = None,
        where: str = "",
        search_query: str = "",
        search_columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table.

        Args:
            table_type (str): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            order_by (str, optional): Column name to order by. Defaults to "ID".
            order_ascending (bool, optional): Whether to sort by ascending order. Defaults to True.
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            where (str, optional): SQL where clause. Can be nested ie `x = '1' AND ("y (1)" = 2 OR z = '3')`.
                It will be combined other filters using `AND`. Defaults to "" (no filter).
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            search_columns (list[str] | None, optional): A list of column names to search for `search_query`.
                Defaults to None (search all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).
        """
        return LOOP.run(
            super().list_table_rows(
                table_type,
                table_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                columns=columns,
                where=where,
                search_query=search_query,
                search_columns=search_columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
                **kwargs,
            )
        )

    def get_table_row(
        self,
        table_type: str,
        table_id: str,
        row_id: str,
        *,
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Get a specific row in a table.

        Args:
            table_type (str): The type of the table.
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
        return LOOP.run(
            super().get_table_row(
                table_type,
                table_id,
                row_id,
                columns=columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
                **kwargs,
            )
        )

    @deprecated(
        "This method is deprecated, use `get_conversation_threads` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    def get_conversation_thread(
        self,
        table_type: str,
        table_id: str,
        column_id: str,
        *,
        row_id: str = "",
        include: bool = True,
        **kwargs,
    ) -> ChatThreadResponse:
        """
        Get the conversation thread for a column in a table.

        Args:
            table_type (str): The type of the table.
            table_id (str): ID / name of the chat table.
            column_id (str): ID / name of the column to fetch.
            row_id (str, optional): ID / name of the last row in the thread.
                Defaults to "" (export all rows).
            include (bool, optional): Whether to include the row specified by `row_id`.
                Defaults to True.

        Returns:
            response (ChatThreadResponse): The conversation thread.
        """
        return LOOP.run(
            super().get_conversation_thread(
                table_type,
                table_id,
                column_id,
                row_id=row_id,
                include=include,
                **kwargs,
            )
        )

    def get_conversation_threads(
        self,
        table_type: str,
        table_id: str,
        column_ids: list[str] | None = None,
        *,
        row_id: str = "",
        include_row: bool = True,
        **kwargs,
    ) -> ChatThreadsResponse:
        """
        Get all multi-turn / conversation threads from a table.

        Args:
            table_type (str): The type of the table.
            table_id (str): ID / name of the chat table.
            column_ids (list[str] | None): Columns to fetch as conversation threads.
            row_id (str, optional): ID / name of the last row in the thread.
                Defaults to "" (export all rows).
            include_row (bool, optional): Whether to include the row specified by `row_id`.
                Defaults to True.

        Returns:
            response (ChatThreadsResponse): The conversation threads.
        """
        return LOOP.run(
            super().get_conversation_threads(
                table_type,
                table_id,
                column_ids,
                row_id=row_id,
                include_row=include_row,
                **kwargs,
            )
        )

    def hybrid_search(
        self,
        table_type: str,
        request: SearchRequest,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """
        Perform a hybrid search on a table.

        Args:
            table_type (str): The type of the table.
            request (SearchRequest): The search request.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        return LOOP.run(super().hybrid_search(table_type, request, **kwargs))

    def regen_table_rows(
        self,
        table_type: str,
        request: MultiRowRegenRequest,
        **kwargs,
    ) -> (
        MultiRowCompletionResponse
        | Generator[CellReferencesResponse | CellCompletionResponse, None, None]
    ):
        """
        Regenerate rows in a table.

        Args:
            table_type (str): The type of the table.
            request (MultiRowRegenRequest): The row regenerate request.

        Returns:
            response (MultiRowCompletionResponse | AsyncGenerator): The row completion.
                In streaming mode, it is an async generator that yields a `CellReferencesResponse` object
                followed by zero or more `CellCompletionResponse` objects.
                In non-streaming mode, it is a `MultiRowCompletionResponse` object.
        """
        agen = LOOP.run(super().regen_table_rows(table_type, request, **kwargs))
        return self._return_iterator(agen, request.stream)

    def update_table_rows(
        self,
        table_type: str,
        request: MultiRowUpdateRequest,
        **kwargs,
    ) -> OkResponse:
        """
        Update rows in a table.

        Args:
            table_type (str): The type of the table.
            request (MultiRowUpdateRequest): The row update request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return LOOP.run(super().update_table_rows(table_type, request, **kwargs))

    @deprecated(
        "This method is deprecated, use `update_table_rows` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    def update_table_row(
        self,
        table_type: str,
        request: RowUpdateRequest,
        **kwargs,
    ) -> OkResponse:
        """
        Update a specific row in a table.

        Args:
            table_type (str): The type of the table.
            request (RowUpdateRequest): The row update request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return LOOP.run(super().update_table_row(table_type, request, **kwargs))

    def delete_table_rows(
        self,
        table_type: str,
        request: MultiRowDeleteRequest,
        **kwargs,
    ) -> OkResponse:
        """
        Delete rows from a table.

        Args:
            table_type (str): The type of the table.
            request (MultiRowDeleteRequest): The row delete request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return LOOP.run(super().delete_table_rows(table_type, request, **kwargs))

    @deprecated(
        "This method is deprecated, use `delete_table_rows` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    def delete_table_row(
        self,
        table_type: str,
        table_id: str,
        row_id: str,
        **kwargs,
    ) -> OkResponse:
        """
        Delete a specific row from a table.

        Args:
            table_type (str): The type of the table.
            table_id (str): The ID of the table.
            row_id (str): The ID of the row.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return LOOP.run(super().delete_table_row(table_type, table_id, row_id, **kwargs))

    def embed_file_options(self, **kwargs) -> httpx.Response:
        """
        Get CORS preflight options for file embedding endpoint.

        Returns:
            response (httpx.Response): The response containing options information.
        """
        return LOOP.run(super().embed_file_options(**kwargs))

    def embed_file(
        self,
        file_path: str,
        table_id: str,
        *,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        **kwargs,
    ) -> OkResponse:
        """
        Embed a file into a Knowledge Table.

        Args:
            file_path (str): File path of the document to be embedded.
            table_id (str): Knowledge Table ID / name.
            chunk_size (int, optional): Maximum chunk size (number of characters). Must be > 0.
                Defaults to 1000.
            chunk_overlap (int, optional): Overlap in characters between chunks. Must be >= 0.
                Defaults to 200.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return LOOP.run(
            super().embed_file(
                file_path, table_id, chunk_size=chunk_size, chunk_overlap=chunk_overlap, **kwargs
            )
        )

    # Import export
    def import_table_data(
        self,
        table_type: str,
        request: TableDataImportRequest,
        **kwargs,
    ) -> GenTableChatResponseType:
        """
        Imports CSV or TSV data into a table.

        Args:
            file_path (str): CSV or TSV file path.
            table_type (str): Table type.
            request (TableDataImportRequest): Data import request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        agen = LOOP.run(super().import_table_data(table_type, request, **kwargs))
        return self._return_iterator(agen, request.stream)

    def export_table_data(
        self,
        table_type: str,
        table_id: str,
        *,
        columns: list[str] | None = None,
        delimiter: Literal[",", "\t"] = ",",
        **kwargs,
    ) -> bytes:
        """
        Exports the row data of a table as a CSV or TSV file.

        Args:
            table_type (str): Table type.
            table_id (str): ID or name of the table to be exported.
            delimiter (str, optional): The delimiter of the file: can be "," or "\\t". Defaults to ",".
            columns (list[str], optional): A list of columns to be exported. Defaults to None (export all columns).

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        return LOOP.run(
            super().export_table_data(
                table_type, table_id, columns=columns, delimiter=delimiter, **kwargs
            )
        )

    def import_table(
        self,
        table_type: str,
        request: TableImportRequest,
        **kwargs,
    ) -> TableMetaResponse | OkResponse:
        """
        Imports a table (data and schema) from a parquet file.

        Args:
            file_path (str): The parquet file path.
            table_type (str): Table type.
            request (TableImportRequest): Table import request.

        Returns:
            response (TableMetaResponse | OkResponse): The table metadata response if blocking is True,
                otherwise OkResponse.
        """
        return LOOP.run(super().import_table(table_type, request, **kwargs))

    def export_table(
        self,
        table_type: str,
        table_id: str,
        **kwargs,
    ) -> bytes:
        """
        Exports a table (data and schema) as a parquet file.

        Args:
            table_type (str): Table type.
            table_id (str): ID or name of the table to be exported.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        return LOOP.run(super().export_table(table_type, table_id, **kwargs))


class _MeterClient(_MeterClientAsync):
    def get_usage_metrics(
        self,
        type,
        from_,
        window_size,
        org_ids=None,
        proj_ids=None,
        to=None,
        group_by=None,
        data_source=None,
    ) -> UsageResponse:
        return LOOP.run(
            super().get_usage_metrics(
                type, from_, window_size, org_ids, proj_ids, to, group_by, data_source
            )
        )

    def get_billing_metrics(
        self,
        from_,
        window_size,
        org_ids=None,
        proj_ids=None,
        to=None,
        group_by=None,
        data_source=None,
    ) -> UsageResponse:
        return LOOP.run(
            super().get_billing_metrics(
                from_, window_size, org_ids, proj_ids, to, group_by, data_source
            )
        )

    def get_bandwidth_metrics(
        self,
        from_,
        window_size,
        org_ids=None,
        proj_ids=None,
        to=None,
        group_by=None,
        data_source=None,
    ) -> UsageResponse:
        return LOOP.run(
            super().get_bandwidth_metrics(
                from_, window_size, org_ids, proj_ids, to, group_by, data_source
            )
        )

    def get_storage_metrics(
        self, from_, window_size, org_ids=None, proj_ids=None, to=None, group_by=None
    ) -> UsageResponse:
        return LOOP.run(
            super().get_storage_metrics(from_, window_size, org_ids, proj_ids, to, group_by)
        )


class _TaskClient(_TaskClientAsync):
    """Task methods."""

    def get_progress(
        self,
        key: str,
        **kwargs,
    ) -> dict[str, Any]:
        return LOOP.run(super().get_progress(key, **kwargs))

    def poll_progress(
        self,
        key: str,
        *,
        initial_wait: float = 0.5,
        max_wait: float = 30 * 60.0,
        verbose: bool = False,
        **kwargs,
    ) -> dict[str, Any] | None:
        from time import sleep

        i = 1
        t0 = perf_counter()
        while (perf_counter() - t0) < max_wait:
            sleep(min(initial_wait * i, 5.0))
            prog = self.get_progress(key, **kwargs)
            state = prog.get("state", None)
            error = prog.get("error", None)
            if verbose:
                logger.info(
                    f"{self.__class__.__name__}: Progress: key={key} state={state}"
                    + (f" error={error}" if error else "")
                )
            if state == ProgressState.COMPLETED:
                return prog
            elif state == ProgressState.FAILED:
                raise JamaiException(prog.get("error", "Unknown error"))
            i += 1
        return None

    # def poll_progress(
    #     self,
    #     key: str,
    #     *,
    #     initial_wait: float = 0.5,
    #     max_wait: float = 30 * 60.0,
    #     **kwargs,
    # ) -> dict[str, Any] | None:
    #     return LOOP.run(
    #         super().poll_progress(
    #             key,
    #             initial_wait=initial_wait,
    #             max_wait=max_wait,
    #             **kwargs,
    #         )
    #     )


class _ConversationClient(_ConversationClientAsync):
    """Conversation methods (synchronous version)."""

    def create_conversation(
        self,
        request: ConversationCreateRequest,
        **kwargs,
    ) -> Generator[
        ConversationMetaResponse | CellReferencesResponse | CellCompletionResponse, None, None
    ]:
        agen = LOOP.run(super().create_conversation(request, **kwargs))
        return self._return_iterator(agen, True)

    def list_conversations(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        **kwargs,
    ) -> Page[ConversationMetaResponse]:
        return LOOP.run(
            super().list_conversations(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                search_query=search_query,
                **kwargs,
            )
        )

    def list_agents(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        order_ascending: bool = True,
        search_query: str = "",
        **kwargs,
    ) -> Page[ConversationMetaResponse]:
        return LOOP.run(
            super().list_agents(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                search_query=search_query,
                **kwargs,
            )
        )

    def get_conversation(self, conversation_id: str, **kwargs) -> ConversationMetaResponse:
        return LOOP.run(super().get_conversation(conversation_id, **kwargs))

    def get_agent(self, agent_id: str, **kwargs) -> AgentMetaResponse:
        return LOOP.run(super().get_agent(agent_id, **kwargs))

    def generate_title(
        self,
        conversation_id: str,
        **kwargs,
    ) -> ConversationMetaResponse:
        """Generates a title for a conversation."""
        return LOOP.run(super().generate_title(conversation_id, **kwargs))

    def rename_conversation_title(
        self,
        conversation_id: str,
        title: str,
        **kwargs,
    ) -> ConversationMetaResponse:
        return LOOP.run(super().rename_conversation_title(conversation_id, title, **kwargs))

    def delete_conversation(
        self,
        conversation_id: str,
        *,
        missing_ok: bool = True,
        **kwargs,
    ) -> OkResponse:
        return LOOP.run(
            super().delete_conversation(conversation_id, missing_ok=missing_ok, **kwargs)
        )

    def send_message(
        self,
        request: MessageAddRequest,
        **kwargs,
    ) -> Generator[CellReferencesResponse | CellCompletionResponse, None, None]:
        agen = LOOP.run(super().send_message(request, **kwargs))
        return self._return_iterator(agen, True)

    def list_messages(
        self,
        conversation_id: str,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "ID",
        order_ascending: bool = True,
        columns: list[str] | None = None,
        search_query: str = "",
        search_columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        **kwargs,
    ) -> Page[dict[str, Any]]:
        return LOOP.run(
            super().list_messages(
                conversation_id=conversation_id,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_ascending=order_ascending,
                columns=columns,
                search_query=search_query,
                search_columns=search_columns,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
                **kwargs,
            )
        )

    def regen_message(
        self,
        request: MessagesRegenRequest,
        **kwargs,
    ) -> Generator[CellReferencesResponse | CellCompletionResponse, None, None]:
        """Regenerates a message in a conversation and streams back the response."""
        agen = LOOP.run(super().regen_message(request, **kwargs))
        return self._return_iterator(agen, True)

    def update_message(
        self,
        request: MessageUpdateRequest,
        **kwargs,
    ) -> OkResponse:
        """Updates a specific message within a conversation."""
        return LOOP.run(super().update_message(request, **kwargs))

    def get_threads(
        self,
        conversation_id: str,
        column_ids: list[str] | None = None,
        **kwargs,
    ) -> ConversationThreadsResponse:
        """
        Get all threads from a conversation.

        Args:
            conversation_id (str): Conversation ID.
            column_ids (list[str] | None): Columns to fetch as conversation threads.

        Returns:
            response (ConversationThreadsResponse): The conversation threads.
        """
        return LOOP.run(super().get_threads(conversation_id, column_ids, **kwargs))


class JamAI(JamAIAsync):
    def __init__(
        self,
        project_id: str = ENV_CONFIG.project_id,
        token: str = ENV_CONFIG.token_plain,
        api_base: str = ENV_CONFIG.api_base,
        headers: dict | None = None,
        timeout: float | None = ENV_CONFIG.timeout_sec,
        file_upload_timeout: float | None = ENV_CONFIG.file_upload_timeout_sec,
        *,
        user_id: str = "",
    ) -> None:
        """
        Initialize the JamAI client.

        Args:
            project_id (str, optional): The project ID.
                Defaults to "default", but can be overridden via
                `JAMAI_PROJECT_ID` var in environment or `.env` file.
            token (str, optional): Your Personal Access Token or organization API key (deprecated) for authentication.
                Defaults to "", but can be overridden via
                `JAMAI_TOKEN` var in environment or `.env` file.
            api_base (str, optional): The base URL for the API.
                Defaults to "https://api.jamaibase.com/api", but can be overridden via
                `JAMAI_API_BASE` var in environment or `.env` file.
            headers (dict | None, optional): Additional headers to include in requests.
                Defaults to None.
            timeout (float | None, optional): The timeout to use when sending requests.
                Defaults to 15 minutes, but can be overridden via
                `JAMAI_TIMEOUT_SEC` var in environment or `.env` file.
            file_upload_timeout (float | None, optional): The timeout to use when sending file upload requests.
                Defaults to 60 minutes, but can be overridden via
                `JAMAI_FILE_UPLOAD_TIMEOUT_SEC` var in environment or `.env` file.
            user_id (str, optional): User ID. For development purposes.
                Defaults to "".
        """
        super().__init__(
            project_id=project_id,
            token=token,
            api_base=api_base,
            headers=headers,
            timeout=timeout,
            file_upload_timeout=file_upload_timeout,
            user_id=user_id,
        )
        kwargs = dict(
            user_id=self.user_id,
            project_id=self.project_id,
            token=self.token,
            api_base=self.api_base,
            headers=self.headers,
            http_client=self.http_client,
            timeout=self.timeout,
            file_upload_timeout=self.file_upload_timeout,
        )
        self.auth = _Auth(**kwargs)
        self.prices = _Prices(**kwargs)
        self.users = _Users(**kwargs)
        self.models = _Models(**kwargs)
        self.organizations = _Organizations(**kwargs)
        self.projects = _Projects(**kwargs)
        self.templates = _Templates(**kwargs)
        self.file = _FileClient(**kwargs)
        self.table = _GenTableClient(**kwargs)
        self.meters = _MeterClient(**kwargs)
        self.tasks = _TaskClient(**kwargs)
        self.conversations = _ConversationClient(**kwargs)

    def health(self) -> dict[str, Any]:
        """
        Get health status.

        Returns:
            response (dict[str, Any]): Health status.
        """
        return LOOP.run(super().health())

    # --- Models and chat --- #

    def model_info(
        self,
        model: str = "",
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]
        ]
        | None = None,
        **kwargs,
    ) -> ModelInfoListResponse:
        """
        Get information about available models.

        Args:
            name (str, optional): The model name. Defaults to "".
            capabilities (list[Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]] | None, optional):
                List of model capabilities to filter by. Defaults to None.

        Returns:
            response (ModelInfoListResponse): The model information response.
        """
        return LOOP.run(super().model_info(model=model, capabilities=capabilities, **kwargs))

    def model_ids(
        self,
        prefer: str = "",
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]
        ]
        | None = None,
        **kwargs,
    ) -> list[str]:
        """
        Get the IDs of available models.

        Args:
            prefer (str, optional): Preferred model ID. Defaults to "".
            capabilities (list[Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]] | None, optional):
                List of model capabilities to filter by. Defaults to None.

        Returns:
            response (list[str]): List of model IDs.
        """
        return LOOP.run(super().model_ids(prefer=prefer, capabilities=capabilities, **kwargs))

    @deprecated(
        "This method is deprecated, use `model_ids` instead.", category=FutureWarning, stacklevel=1
    )
    def model_names(
        self,
        prefer: str = "",
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "document", "tool", "embed", "rerank"]
        ]
        | None = None,
        **kwargs,
    ) -> list[str]:
        return self.model_ids(prefer=prefer, capabilities=capabilities, **kwargs)

    def generate_chat_completions(
        self,
        request: ChatRequest,
        **kwargs,
    ) -> ChatCompletionResponse | Generator[References | ChatCompletionChunkResponse, None, None]:
        """
        Generates chat completions.

        Args:
            request (ChatRequest): The request.

        Returns:
            completion (ChatCompletionChunkResponse | AsyncGenerator): The chat completion.
                In streaming mode, it is an async generator that yields a `References` object
                followed by zero or more `ChatCompletionChunkResponse` objects.
                In non-streaming mode, it is a `ChatCompletionChunkResponse` object.
        """
        agen = LOOP.run(super().generate_chat_completions(request=request, **kwargs))
        return self._return_iterator(agen, request.stream)

    def generate_embeddings(
        self,
        request: EmbeddingRequest,
        **kwargs,
    ) -> EmbeddingResponse:
        """
        Generate embeddings for the given input.

        Args:
            request (EmbeddingRequest): The embedding request.

        Returns:
            response (EmbeddingResponse): The embedding response.
        """
        return LOOP.run(super().generate_embeddings(request=request, **kwargs))

    def rerank(self, request: RerankingRequest, **kwargs) -> RerankingResponse:
        """
        Generate similarity rankings for the given query and documents.

        Args:
            request (RerankingRequest): The reranking request body.

        Returns:
            RerankingResponse: The reranking response.
        """
        return LOOP.run(super().rerank(request=request, **kwargs))
