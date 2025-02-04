import platform
from mimetypes import guess_type
from os.path import split
from typing import Any, AsyncGenerator, BinaryIO, Generator, Literal, Type
from urllib.parse import quote
from warnings import warn

import filetype
import httpx
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import deprecated

from jamaibase.exceptions import ResourceNotFoundError
from jamaibase.protocol import (
    ActionTableSchemaCreate,
    AddActionColumnSchema,
    AddChatColumnSchema,
    AddKnowledgeColumnSchema,
    AdminOrderBy,
    ApiKeyCreate,
    ApiKeyRead,
    ChatCompletionChunk,
    ChatRequest,
    ChatTableSchemaCreate,
    ChatThread,
    ColumnDropRequest,
    ColumnRenameRequest,
    ColumnReorderRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    EventCreate,
    EventRead,
    FileUploadRequest,
    FileUploadResponse,
    GenConfigUpdateRequest,
    GenTableOrderBy,
    GenTableRowsChatCompletionChunks,
    GenTableStreamChatCompletionChunk,
    GenTableStreamReferences,
    GetURLRequest,
    GetURLResponse,
    KnowledgeTableSchemaCreate,
    ModelInfoResponse,
    ModelListConfig,
    ModelPrice,
    OkResponse,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    OrgMemberCreate,
    OrgMemberRead,
    Page,
    PATCreate,
    PATRead,
    Price,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    References,
    RowAddRequest,
    RowDeleteRequest,
    RowRegenRequest,
    RowUpdateRequest,
    SearchRequest,
    StringResponse,
    TableDataImportRequest,
    TableImportRequest,
    TableMetaResponse,
    TableType,
    Template,
    UserCreate,
    UserRead,
    UserUpdate,
)
from jamaibase.utils.io import json_loads
from jamaibase.version import __version__

USER_AGENT = f"SDK/{__version__} (Python/{platform.python_version()}; {platform.system()} {platform.release()}; {platform.machine()})"
ORG_API_KEY_DEPRECATE = "Organization API keys are deprecated, use Personal Access Tokens instead."
TABLE_METHOD_DEPRECATE = "This method is deprecated, use `client.table.<method>` instead."


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    jamai_token: SecretStr = ""
    jamai_api_key: SecretStr = ""
    jamai_api_base: str = "https://api.jamaibase.com/api"
    jamai_project_id: str = "default"
    jamai_timeout_sec: float = 5 * 60.0
    jamai_file_upload_timeout_sec: float = 60 * 60.0

    @property
    def jamai_token_plain(self):
        api_key = self.jamai_api_key.get_secret_value().strip()
        return self.jamai_token.get_secret_value().strip() or api_key


ENV_CONFIG = EnvConfig()
GenTableChatResponseType = (
    GenTableRowsChatCompletionChunks
    | Generator[GenTableStreamReferences | GenTableStreamChatCompletionChunk, None, None]
)


class _Client:
    def __init__(
        self,
        project_id: str,
        token: str,
        api_base: str,
        headers: dict | None,
        http_client: httpx.Client | httpx.AsyncClient,
        file_upload_timeout: float | None,
    ) -> None:
        """
        Base client.

        Args:
            project_id (str): The project ID.
            token (str): Personal Access Token or organization API key (deprecated) for authentication.
            api_base (str): The base URL for the API.
            headers (dict | None): Additional headers to include in requests.
            http_client (httpx.Client | httpx.AsyncClient): The HTTPX client.
            file_upload_timeout (float | None, optional): The timeout to use when sending file upload requests.
        """
        if api_base.endswith("/"):
            api_base = api_base[:-1]
        self.project_id = project_id
        self.token = token
        self.api_base = api_base
        self.headers = {"X-PROJECT-ID": project_id, "User-Agent": USER_AGENT}
        if token != "":
            self.headers["Authorization"] = f"Bearer {token}"
        if headers is not None:
            if not isinstance(headers, dict):
                raise TypeError("`headers` must be None or a dict.")
            self.headers.update(headers)
        self.http_client = http_client
        self.file_upload_timeout = file_upload_timeout

    @property
    def api_key(self) -> str:
        return self.token

    def close(self) -> None:
        """
        Close the HTTP client.
        """
        self.http_client.close()

    @staticmethod
    def raise_exception(
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
            error = response.read().decode()
        error = json_loads(error)
        err_mssg = error.get("message", error.get("detail", str(error)))
        if code == 404:
            exc = ResourceNotFoundError
        else:
            exc = RuntimeError
        raise exc(err_mssg)

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
        body: BaseModel | None,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make a POST request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            body (BaseModel | None): The request body.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.post`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        if body is not None:
            body = body.model_dump()
        response = self.http_client.post(
            f"{address}{endpoint}",
            json=body,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        )
        response = self.raise_exception(response)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)

    def _options(
        self,
        address: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an OPTIONS request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return.
            **kwargs (Any): Keyword arguments for `httpx.options`.

        Returns:
            response (httpx.Response | BaseModel): The response or Pydantic response object.
        """
        response = self.http_client.options(
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

    def _patch(
        self,
        address: str,
        endpoint: str,
        *,
        body: BaseModel | None,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make a PATCH request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            body (BaseModel | None): The request body.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.patch`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        if body is not None:
            body = body.model_dump()
        response = self.http_client.patch(
            f"{address}{endpoint}",
            json=body,
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
        body: BaseModel | None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> Generator[str, None, None]:
        """
        Make a streaming POST request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            body (BaseModel | None): The request body.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.stream`.

        Yields:
            str: The response chunks.
        """
        if body is not None:
            body = body.model_dump()
        with self.http_client.stream(
            "POST",
            f"{address}{endpoint}",
            json=body,
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
        ignore_code: int | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make a DELETE request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return.
            ignore_code (int | None, optional): HTTP code to ignore.
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
        response = self.raise_exception(response, ignore_code=ignore_code)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)


class _BackendAdminClient(_Client):
    """Backend administration methods."""

    def create_user(self, request: UserCreate) -> UserRead:
        return self._post(
            self.api_base,
            "/admin/backend/v1/users",
            body=request,
            response_model=UserRead,
        )

    def update_user(self, request: UserUpdate) -> UserRead:
        return self._patch(
            self.api_base,
            "/admin/backend/v1/users",
            body=request,
            response_model=UserRead,
        )

    def list_users(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: str = AdminOrderBy.UPDATED_AT,
        order_descending: bool = True,
    ) -> Page[UserRead]:
        """
        List users.

        Args:
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of users to return (min 1, max 100). Defaults to 100.
            order_by (str, optional): Sort users by this attribute. Defaults to "updated_at".
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.

        Returns:
            response (Page[UserRead]): The paginated user metadata response.
        """
        return self._get(
            self.api_base,
            "/admin/backend/v1/users",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_descending=order_descending,
            ),
            response_model=Page[UserRead],
        )

    def get_user(self, user_id: str) -> UserRead:
        return self._get(
            self.api_base,
            f"/admin/backend/v1/users/{quote(user_id)}",
            params=None,
            response_model=UserRead,
        )

    def delete_user(
        self,
        user_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        response = self._delete(
            self.api_base,
            f"/admin/backend/v1/users/{quote(user_id)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    def create_pat(self, request: PATCreate) -> PATRead:
        return self._post(
            self.api_base,
            "/admin/backend/v1/pats",
            body=request,
            response_model=PATRead,
        )

    def get_pat(self, pat: str) -> PATRead:
        return self._get(
            self.api_base,
            f"/admin/backend/v1/pats/{quote(pat)}",
            params=None,
            response_model=PATRead,
        )

    def delete_pat(
        self,
        pat: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        response = self._delete(
            self.api_base,
            f"/admin/backend/v1/pats/{quote(pat)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    def create_organization(self, request: OrganizationCreate) -> OrganizationRead:
        return self._post(
            self.api_base,
            "/admin/backend/v1/organizations",
            body=request,
            response_model=OrganizationRead,
        )

    def update_organization(self, request: OrganizationUpdate) -> OrganizationRead:
        return self._patch(
            self.api_base,
            "/admin/backend/v1/organizations",
            body=request,
            response_model=OrganizationRead,
        )

    def list_organizations(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: str = AdminOrderBy.UPDATED_AT,
        order_descending: bool = True,
    ) -> Page[OrganizationRead]:
        return self._get(
            self.api_base,
            "/admin/backend/v1/organizations",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_descending=order_descending,
            ),
            response_model=Page[OrganizationRead],
        )

    def get_organization(self, organization_id: str) -> OrganizationRead:
        return self._get(
            self.api_base,
            f"/admin/backend/v1/organizations/{quote(organization_id)}",
            params=None,
            response_model=OrganizationRead,
        )

    def delete_organization(
        self,
        organization_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        response = self._delete(
            self.api_base,
            f"/admin/backend/v1/organizations/{quote(organization_id)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    def generate_invite_token(
        self,
        organization_id: str,
        user_email: str = "",
        user_role: str = "",
        valid_days: int = 7,
    ) -> str:
        """
        Generates an invite token to join an organization.

        Args:
            organization_id (str): Organization ID.
            user_email (str, optional): User email.
                Leave blank to disable email check and generate a public invite. Defaults to "".
            user_role (str, optional): User role.
                Leave blank to default to guest. Defaults to "".
            valid_days (int, optional): How many days should this link be valid for. Defaults to 7.

        Returns:
            token (str): _description_
        """
        response = self._get(
            self.api_base,
            "/admin/backend/v1/invite_tokens",
            params=dict(
                organization_id=organization_id,
                user_email=user_email,
                user_role=user_role,
                valid_days=valid_days,
            ),
            response_model=None,
        )
        return response.text

    def join_organization(self, request: OrgMemberCreate) -> OrgMemberRead:
        return self._post(
            self.api_base,
            "/admin/backend/v1/organizations/link",
            body=request,
            response_model=OrgMemberRead,
        )

    def leave_organization(self, user_id: str, organization_id: str) -> OkResponse:
        return self._delete(
            self.api_base,
            f"/admin/backend/v1/organizations/link/{quote(user_id)}/{quote(organization_id)}",
            params=None,
            response_model=OkResponse,
        )

    def create_api_key(self, request: ApiKeyCreate) -> ApiKeyRead:
        warn(ORG_API_KEY_DEPRECATE, FutureWarning, stacklevel=2)
        return self._post(
            self.api_base,
            "/admin/backend/v1/api_keys",
            body=request,
            response_model=ApiKeyRead,
        )

    def get_api_key(self, api_key: str) -> ApiKeyRead:
        warn(ORG_API_KEY_DEPRECATE, FutureWarning, stacklevel=2)
        return self._get(
            self.api_base,
            f"/admin/backend/v1/api_keys/{quote(api_key)}",
            params=None,
            response_model=ApiKeyRead,
        )

    def delete_api_key(
        self,
        api_key: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        warn(ORG_API_KEY_DEPRECATE, FutureWarning, stacklevel=2)
        response = self._delete(
            self.api_base,
            f"/admin/backend/v1/api_keys/{quote(api_key)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    def refresh_quota(
        self,
        organization_id: str,
        reset_usage: bool = True,
    ) -> OrganizationRead:
        return self._post(
            self.api_base,
            f"/admin/backend/v1/quotas/refresh/{quote(organization_id)}",
            body=None,
            params=dict(reset_usage=reset_usage),
            response_model=OrganizationRead,
        )

    def get_event(self, event_id: str) -> EventRead:
        return self._get(
            self.api_base,
            f"/admin/backend/v1/events/{quote(event_id)}",
            params=None,
            response_model=EventRead,
        )

    def add_event(self, request: EventCreate) -> OkResponse:
        return self._post(
            self.api_base,
            "/admin/backend/v1/events",
            body=request,
            response_model=OkResponse,
        )

    def mark_event_as_done(self, event_id: str) -> OkResponse:
        return self._patch(
            self.api_base,
            f"/admin/backend/v1/events/done/{quote(event_id)}",
            body=None,
            response_model=OkResponse,
        )

    def get_internal_organization_id(self) -> StringResponse:
        return self._get(
            self.api_base,
            "/admin/backend/v1/internal_organization_id",
            params=None,
            response_model=StringResponse,
        )

    def set_internal_organization_id(self, organization_id: str) -> OkResponse:
        return self._patch(
            self.api_base,
            f"/admin/backend/v1/internal_organization_id/{quote(organization_id)}",
            body=None,
            response_model=OkResponse,
        )

    def get_pricing(self) -> Price:
        return self._get(
            self.api_base,
            "/public/v1/prices/plans",
            params=None,
            response_model=Price,
        )

    def set_pricing(self, request: Price) -> OkResponse:
        return self._patch(
            self.api_base,
            "/admin/backend/v1/prices/plans",
            body=request,
            response_model=OkResponse,
        )

    def get_model_pricing(self) -> ModelPrice:
        return self._get(
            self.api_base,
            "/public/v1/prices/models",
            params=None,
            response_model=ModelPrice,
        )

    def get_model_config(self) -> ModelListConfig:
        return self._get(
            self.api_base,
            "/admin/backend/v1/models",
            params=None,
            response_model=ModelListConfig,
        )

    def set_model_config(self, request: ModelListConfig) -> OkResponse:
        return self._patch(
            self.api_base,
            "/admin/backend/v1/models",
            body=request,
            response_model=OkResponse,
        )

    def add_template(
        self,
        source: str | BinaryIO,
        template_id_dst: str,
        exist_ok: bool = False,
    ) -> OkResponse:
        """
        Upload a template Parquet file to add a new template into gallery.

        Args:
            source (str | BinaryIO): The path to the template Parquet file or a file-like object.
            template_id_dst (str): The ID of the new template.
            exist_ok (bool, optional): Whether to overwrite existing template. Defaults to False.

        Returns:
            response (OkResponse): The response indicating success.
        """
        kwargs = dict(
            address=self.api_base,
            endpoint="/admin/backend/v1/templates/import",
            body=None,
            response_model=OkResponse,
            data={"template_id_dst": template_id_dst, "exist_ok": exist_ok},
            timeout=self.file_upload_timeout,
        )
        mime_type = "application/octet-stream"
        if isinstance(source, str):
            filename = split(source)[-1]
            # Open the file in binary mode
            with open(source, "rb") as f:
                return self._post(files={"file": (filename, f, mime_type)}, **kwargs)
        else:
            filename = "import.parquet"
            return self._post(files={"file": (filename, source, mime_type)}, **kwargs)

    def populate_templates(self, timeout: float = 30.0) -> OkResponse:
        """
        Re-populates the template gallery.

        Args:
            timeout (float, optional): Timeout in seconds, must be >= 0. Defaults to 30.0.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return self._post(
            self.api_base,
            "/admin/backend/v1/templates/populate",
            body=None,
            params=dict(timeout=timeout),
            response_model=OkResponse,
        )


class _OrgAdminClient(_Client):
    """Organization administration methods."""

    def get_org_model_config(self, organization_id: str) -> ModelListConfig:
        return self._get(
            self.api_base,
            f"/admin/org/v1/models/{quote(organization_id)}",
            params=None,
            response_model=ModelListConfig,
        )

    def set_org_model_config(
        self,
        organization_id: str,
        config: ModelListConfig,
    ) -> OkResponse:
        return self._patch(
            self.api_base,
            f"/admin/org/v1/models/{quote(organization_id)}",
            body=config,
            response_model=OkResponse,
        )

    def create_project(self, request: ProjectCreate) -> ProjectRead:
        return self._post(
            self.api_base,
            "/admin/org/v1/projects",
            body=request,
            response_model=ProjectRead,
        )

    def update_project(self, request: ProjectUpdate) -> ProjectRead:
        return self._patch(
            self.api_base,
            "/admin/org/v1/projects",
            body=request,
            response_model=ProjectRead,
        )

    def set_project_updated_at(
        self,
        project_id: str,
        updated_at: str | None = None,
    ) -> OkResponse:
        return self._patch(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}",
            body=None,
            params=dict(updated_at=updated_at),
            response_model=OkResponse,
        )

    def list_projects(
        self,
        organization_id: str = "default",
        search_query: str = "",
        offset: int = 0,
        limit: int = 100,
        order_by: str = AdminOrderBy.UPDATED_AT,
        order_descending: bool = True,
    ) -> Page[ProjectRead]:
        return self._get(
            self.api_base,
            "/admin/org/v1/projects",
            params=dict(
                organization_id=organization_id,
                search_query=search_query,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_descending=order_descending,
            ),
            response_model=Page[ProjectRead],
        )

    def get_project(self, project_id: str) -> ProjectRead:
        return self._get(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}",
            params=None,
            response_model=ProjectRead,
        )

    def delete_project(
        self,
        project_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        response = self._delete(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    def import_project(
        self,
        source: str | BinaryIO,
        organization_id: str,
        project_id_dst: str = "",
    ) -> ProjectRead:
        """
        Imports a project.

        Args:
            source (str | BinaryIO): The parquet file path or file-like object.
                It can be a Project or Template file.
            organization_id (str): Organization ID "org_xxx".
            project_id_dst (str, optional): ID of the project to import tables into.
                Defaults to creating new project.

        Returns:
            response (ProjectRead): The imported project.
        """
        kwargs = dict(
            address=self.api_base,
            endpoint=f"/admin/org/v1/projects/import/{quote(organization_id)}",
            body=None,
            response_model=ProjectRead,
            data={"project_id_dst": project_id_dst},
            timeout=self.file_upload_timeout,
        )
        mime_type = "application/octet-stream"
        if isinstance(source, str):
            filename = split(source)[-1]
            # Open the file in binary mode
            with open(source, "rb") as f:
                return self._post(files={"file": (filename, f, mime_type)}, **kwargs)
        else:
            filename = "import.parquet"
            return self._post(files={"file": (filename, source, mime_type)}, **kwargs)

    def export_project(
        self,
        project_id: str,
        compression: Literal["NONE", "ZSTD", "LZ4", "SNAPPY"] = "ZSTD",
    ) -> bytes:
        """
        Exports a project as a Project Parquet file.

        Args:
            project_id (str): Project ID "proj_xxx".
            compression (str, optional): Parquet compression codec. Defaults to "ZSTD".

        Returns:
            response (bytes): The Parquet file.
        """
        response = self._get(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}/export",
            params=dict(compression=compression),
            response_model=None,
        )
        return response.content

    def import_project_from_template(
        self,
        organization_id: str,
        template_id: str,
        project_id_dst: str = "",
    ) -> ProjectRead:
        """
        Imports a project from a template.

        Args:
            organization_id (str): Organization ID "org_xxx".
            template_id (str): ID of the template to import from.
            project_id_dst (str, optional): ID of the project to import tables into.
                Defaults to creating new project.

        Returns:
            response (ProjectRead): The imported project.
        """
        return self._post(
            self.api_base,
            f"/admin/org/v1/projects/import/{quote(organization_id)}/templates/{quote(template_id)}",
            body=None,
            params=dict(project_id_dst=project_id_dst),
            response_model=ProjectRead,
        )

    def export_project_as_template(
        self,
        project_id: str,
        *,
        name: str,
        tags: list[str],
        description: str,
        compression: Literal["NONE", "ZSTD", "LZ4", "SNAPPY"] = "ZSTD",
    ) -> bytes:
        """
        Exports a project as a template Parquet file.

        Args:
            project_id (str): Project ID "proj_xxx".
            name (str): Template name.
            tags (list[str]): Template tags.
            description (str): Template description.
            compression (str, optional): Parquet compression codec. Defaults to "ZSTD".

        Returns:
            response (bytes): The template Parquet file.
        """
        response = self._get(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}/export/template",
            params=dict(
                name=name,
                tags=tags,
                description=description,
                compression=compression,
            ),
            response_model=None,
        )
        return response.content


class _AdminClient(_Client):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.backend = _BackendAdminClient(*args, **kwargs)
        self.organization = _OrgAdminClient(*args, **kwargs)


class _TemplateClient(_Client):
    """Template methods."""

    def list_templates(self, search_query: str = "") -> Page[Template]:
        """
        List all templates.

        Args:
            search_query (str, optional): A string to search for within template names.

        Returns:
            templates (Page[Template]): A page of templates.
        """
        return self._get(
            self.api_base,
            "/public/v1/templates",
            params=dict(search_query=search_query),
            response_model=Page[Template],
        )

    def get_template(self, template_id: str) -> Template:
        """
        Get a template by its ID.

        Args:
            template_id (str): Template ID.

        Returns:
            template (Template): The template.
        """
        return self._get(
            self.api_base,
            f"/public/v1/templates/{quote(template_id)}",
            params=None,
            response_model=Template,
        )

    def list_tables(
        self,
        template_id: str,
        table_type: str,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        order_by: str = GenTableOrderBy.UPDATED_AT,
        order_descending: bool = True,
    ) -> Page[TableMetaResponse]:
        """
        List all tables in a template.

        Args:
            template_id (str): Template ID.
            table_type (str): Table type.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).
            order_by (str, optional): Sort tables by this attribute. Defaults to "updated_at".
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.

        Returns:
            tables (Page[TableMetaResponse]): A page of tables.
        """
        return self._get(
            self.api_base,
            f"/public/v1/templates/{quote(template_id)}/gen_tables/{quote(table_type)}",
            params=dict(
                offset=offset,
                limit=limit,
                search_query=search_query,
                order_by=order_by,
                order_descending=order_descending,
            ),
            response_model=Page[TableMetaResponse],
        )

    def get_table(self, template_id: str, table_type: str, table_id: str) -> TableMetaResponse:
        """
        Get a table in a template.

        Args:
            template_id (str): Template ID.
            table_type (str): Table type.
            table_id (str): Table ID.

        Returns:
            table (TableMetaResponse): The table.
        """
        return self._get(
            self.api_base,
            f"/public/v1/templates/{quote(template_id)}/gen_tables/{quote(table_type)}/{quote(table_id)}",
            params=None,
            response_model=TableMetaResponse,
        )

    def list_table_rows(
        self,
        template_id: str,
        table_type: str,
        table_id: str,
        *,
        starting_after: str | None = None,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "Updated at",
        order_descending: bool = True,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a template table.

        Args:
            template_id (str): Template ID.
            table_type (str): Table type.
            table_id (str): Table ID.
            starting_after (str | None, optional): A cursor for use in pagination.
                Only rows with ID > `starting_after` will be returned.
                For instance, if your call receives 100 rows ending with ID "x",
                your subsequent call can include `starting_after="x"` in order to fetch the next page of the list.
                Defaults to None.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            order_by (str, optional): Sort rows by this column. Defaults to "Updated at".
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).

        Returns:
            rows (Page[dict[str, Any]]): The rows.
        """
        return self._get(
            self.api_base,
            f"/public/v1/templates/{quote(template_id)}/gen_tables/{quote(table_type)}/{quote(table_id)}/rows",
            params=dict(
                starting_after=starting_after,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_descending=order_descending,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=Page[dict[str, Any]],
        )


class _FileClient(_Client):
    """File methods."""

    def upload_file(self, file_path: str) -> FileUploadResponse:
        """
        Uploads a file to the server.

        Args:
            file_path (str): Path to the file to be uploaded.

        Returns:
            response (FileUploadResponse): The response containing the file URI.
        """
        filename = split(file_path)[-1]
        mime_type = filetype.guess(file_path).mime
        if mime_type is None:
            mime_type = "application/octet-stream"  # Default MIME type

        with open(file_path, "rb") as f:
            return self._post(
                self.api_base,
                "/v1/files/upload",
                body=None,
                response_model=FileUploadResponse,
                files={
                    "file": (filename, f, mime_type),
                },
                timeout=self.file_upload_timeout,
            )

    def get_raw_urls(self, uris: list[str]) -> GetURLResponse:
        """
        Get download URLs for raw files.

        Args:
            uris (List[str]): List of file URIs to download.

        Returns:
            response (GetURLResponse): The response containing download information for the files.
        """
        return self._post(
            self.api_base,
            "/v1/files/url/raw",
            body=GetURLRequest(uris=uris),
            response_model=GetURLResponse,
        )

    def get_thumbnail_urls(self, uris: list[str]) -> GetURLResponse:
        """
        Get download URLs for file thumbnails.

        Args:
            uris (List[str]): List of file URIs to get thumbnails for.

        Returns:
            response (GetURLResponse): The response containing download information for the thumbnails.
        """
        return self._post(
            self.api_base,
            "/v1/files/url/thumb",
            body=GetURLRequest(uris=uris),
            response_model=GetURLResponse,
        )


class _GenTableClient(_Client):
    """Generative Table methods."""

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
            body=request,
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
            body=request,
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
            body=request,
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
        *,
        offset: int = 0,
        limit: int = 100,
        parent_id: str | None = None,
        search_query: str = "",
        order_by: str = GenTableOrderBy.UPDATED_AT,
        order_descending: bool = True,
        count_rows: bool = False,
    ) -> Page[TableMetaResponse]:
        """
        List Generative Tables of a specific type.

        Args:
            table_type (str | TableType): The type of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            parent_id (str | None, optional): Parent ID of tables to return.
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
                Defaults to None (return all tables).
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).
            order_by (str, optional): Sort tables by this attribute. Defaults to "updated_at".
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.
            count_rows (bool, optional): Whether to count the rows of the tables. Defaults to False.

        Returns:
            response (Page[TableMetaResponse]): The paginated table metadata response.
        """
        return self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}",
            params=dict(
                offset=offset,
                limit=limit,
                parent_id=parent_id,
                search_query=search_query,
                order_by=order_by,
                order_descending=order_descending,
                count_rows=count_rows,
            ),
            response_model=Page[TableMetaResponse],
        )

    def delete_table(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        """
        Delete a specific table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            missing_ok (bool, optional): Ignore resource not found error.

        Returns:
            response (OkResponse): The response indicating success.
        """
        response = self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    def duplicate_table(
        self,
        table_type: str | TableType,
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
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str | None, optional): The destination / new table ID.
                Defaults to None (create a new table ID automatically).
            include_data (bool, optional): Whether to include data in the duplicated table. Defaults to True.
            create_as_child (bool, optional): Whether the new table is a child table.
                If this is True, then `include_data` will be set to True. Defaults to False.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        if "deploy" in kwargs:
            warn(
                'The "deploy" argument is deprecated, use "create_as_child" instead.',
                FutureWarning,
                stacklevel=2,
            )
            create_as_child = create_as_child or kwargs.pop("deploy")
        return self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/duplicate/{quote(table_id_src)}",
            body=None,
            params=dict(
                table_id_dst=table_id_dst,
                include_data=include_data,
                create_as_child=create_as_child,
            ),
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
            body=None,
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
            body=request,
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
            body=request,
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
            body=request,
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
            body=request,
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
            body=request,
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
            body=request,
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
            body=request,
            response_model=TableMetaResponse,
        )

    def list_table_rows(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        order_descending: bool = True,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.

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
                order_descending=order_descending,
            ),
            response_model=Page[dict[str, Any]],
        )

    def get_table_row(
        self,
        table_type: str | TableType,
        table_id: str,
        row_id: str,
        *,
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
                    body=request,
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
                body=request,
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
                    body=request,
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
                body=request,
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
            body=request,
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
            body=request,
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
        table_type: str | TableType,
        table_id: str,
        column_id: str,
        *,
        row_id: str = "",
        include: bool = True,
    ) -> ChatThread:
        """
        Get the conversation thread for a chat table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): ID / name of the chat table.
            column_id (str): ID / name of the column to fetch.
            row_id (str, optional): ID / name of the last row in the thread.
                Defaults to "" (export all rows).
            include (bool, optional): Whether to include the row specified by `row_id`.
                Defaults to True.

        Returns:
            response (ChatThread): The conversation thread.
        """
        return self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/thread",
            params=dict(column_id=column_id, row_id=row_id, include=include),
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
            body=request,
            response_model=None,
        )
        return json_loads(response.text)

    def embed_file_options(self) -> httpx.Response:
        """
        Get options for embedding a file to a Knowledge Table.

        Returns:
            response (httpx.Response): The response containing options information.
        """
        response = self._options(
            self.api_base,
            "/v1/gen_tables/knowledge/embed_file",
        )
        return response

    def embed_file(
        self,
        file_path: str,
        table_id: str,
        *,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
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
        # Guess the MIME type of the file based on its extension
        mime_type, _ = guess_type(file_path)
        if mime_type is None:
            mime_type = (
                "application/jsonl" if file_path.endswith(".jsonl") else "application/octet-stream"
            )  # Default MIME type
        # Extract the filename from the file path
        filename = split(file_path)[-1]
        # Open the file in binary mode
        with open(file_path, "rb") as f:
            response = self._post(
                self.api_base,
                "/v1/gen_tables/knowledge/embed_file",
                body=None,
                response_model=OkResponse,
                files={
                    "file": (filename, f, mime_type),
                },
                data={
                    "table_id": table_id,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    # "overwrite": request.overwrite,
                },
                timeout=self.file_upload_timeout,
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
                        body=None,
                        files={
                            "file": (filename, f, mime_type),
                        },
                        data=data,
                        timeout=self.file_upload_timeout,
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
                    body=None,
                    response_model=GenTableRowsChatCompletionChunks,
                    files={
                        "file": (filename, f, mime_type),
                    },
                    data=data,
                    timeout=self.file_upload_timeout,
                )

    def export_table_data(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        columns: list[str] | None = None,
        delimiter: Literal[",", "\t"] = ",",
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
        Imports a table (data and schema) from a parquet file.

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
                body=None,
                response_model=TableMetaResponse,
                files={
                    "file": (filename, f, mime_type),
                },
                data=data,
                timeout=self.file_upload_timeout,
            )

    def export_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> bytes:
        """
        Exports a table (data and schema) as a parquet file.

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


class JamAI(_Client):
    def __init__(
        self,
        project_id: str = ENV_CONFIG.jamai_project_id,
        token: str = ENV_CONFIG.jamai_token_plain,
        api_base: str = ENV_CONFIG.jamai_api_base,
        headers: dict | None = None,
        timeout: float | None = ENV_CONFIG.jamai_timeout_sec,
        file_upload_timeout: float | None = ENV_CONFIG.jamai_file_upload_timeout_sec,
        *,
        api_key: str = "",
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
            api_key (str, optional): (Deprecated) Organization API key for authentication.
        """
        if api_key:
            warn(ORG_API_KEY_DEPRECATE, FutureWarning, stacklevel=2)
        http_client = httpx.Client(
            timeout=timeout,
            transport=httpx.HTTPTransport(retries=3),
        )
        kwargs = dict(
            project_id=project_id,
            token=token or api_key,
            api_base=api_base,
            headers=headers,
            http_client=http_client,
            file_upload_timeout=file_upload_timeout,
        )
        super().__init__(**kwargs)
        self.admin = _AdminClient(**kwargs)
        self.template = _TemplateClient(**kwargs)
        self.file = _FileClient(**kwargs)
        self.table = _GenTableClient(**kwargs)

    def health(self) -> dict[str, Any]:
        """
        Get health status.

        Returns:
            response (dict[str, Any]): Health status.
        """
        response = self._get(self.api_base, "/health", response_model=None)
        return json_loads(response.text)

    # --- Models and chat --- #

    def model_info(
        self,
        name: str = "",
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "tool", "embed", "rerank"]
        ]
        | None = None,
    ) -> ModelInfoResponse:
        """
        Get information about available models.

        Args:
            name (str, optional): The model name. Defaults to "".
            capabilities (list[Literal["completion", "chat", "image", "audio", "tool", "embed", "rerank"]] | None, optional):
                List of model capabilities to filter by. Defaults to None.

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
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "tool", "embed", "rerank"]
        ]
        | None = None,
    ) -> list[str]:
        """
        Get the names of available models.

        Args:
            prefer (str, optional): Preferred model name. Defaults to "".
            capabilities (list[Literal["completion", "chat", "image", "audio", "tool", "embed", "rerank"]] | None, optional):
                List of model capabilities to filter by. Defaults to None.

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
                    body=request,
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
                body=request,
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
            body=request,
            response_model=EmbeddingResponse,
        )

    # --- Gen Table --- #

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def create_action_table(self, request: ActionTableSchemaCreate) -> TableMetaResponse:
        """
        Create an Action Table.

        Args:
            request (ActionTableSchemaCreate): The action table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self.table.create_action_table(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def create_knowledge_table(self, request: KnowledgeTableSchemaCreate) -> TableMetaResponse:
        """
        Create a Knowledge Table.

        Args:
            request (KnowledgeTableSchemaCreate): The knowledge table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self.table.create_knowledge_table(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def create_chat_table(self, request: ChatTableSchemaCreate) -> TableMetaResponse:
        """
        Create a Chat Table.

        Args:
            request (ChatTableSchemaCreate): The chat table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self.table.create_chat_table(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.get_table(table_type, table_id)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def list_tables(
        self,
        table_type: str | TableType,
        offset: int = 0,
        limit: int = 100,
        parent_id: str | None = None,
        search_query: str = "",
        order_by: str = GenTableOrderBy.UPDATED_AT,
        order_descending: bool = True,
        count_rows: bool = False,
    ) -> Page[TableMetaResponse]:
        """
        List Generative Tables of a specific type.

        Args:
            table_type (str | TableType): The type of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            parent_id (str | None, optional): Parent ID of tables to return.
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
                Defaults to None (return all tables).
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).
            order_by (str, optional): Sort tables by this attribute. Defaults to "updated_at".
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.
            count_rows (bool, optional): Whether to count the rows of the tables. Defaults to False.

        Returns:
            response (Page[TableMetaResponse]): The paginated table metadata response.
        """
        return self.table.list_tables(
            table_type,
            offset=offset,
            limit=limit,
            parent_id=parent_id,
            search_query=search_query,
            order_by=order_by,
            order_descending=order_descending,
            count_rows=count_rows,
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def delete_table(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        """
        Delete a specific table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            missing_ok (bool, optional): Ignore resource not found error.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return self.table.delete_table(table_type, table_id, missing_ok=missing_ok)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def duplicate_table(
        self,
        table_type: str | TableType,
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
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str | None, optional): The destination / new table ID.
                Defaults to None (create a new table ID automatically).
            include_data (bool, optional): Whether to include data in the duplicated table. Defaults to True.
            create_as_child (bool, optional): Whether the new table is a child table.
                If this is True, then `include_data` will be set to True. Defaults to False.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self.table.duplicate_table(
            table_type,
            table_id_src,
            table_id_dst,
            include_data=include_data,
            create_as_child=create_as_child,
            **kwargs,
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.rename_table(table_type, table_id_src, table_id_dst)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.update_gen_config(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def add_action_columns(self, request: AddActionColumnSchema) -> TableMetaResponse:
        """
        Add columns to an Action Table.

        Args:
            request (AddActionColumnSchema): The action column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self.table.add_action_columns(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def add_knowledge_columns(self, request: AddKnowledgeColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Knowledge Table.

        Args:
            request (AddKnowledgeColumnSchema): The knowledge column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self.table.add_knowledge_columns(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def add_chat_columns(self, request: AddChatColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Chat Table.

        Args:
            request (AddChatColumnSchema): The chat column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self.table.add_chat_columns(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.drop_columns(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.rename_columns(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.reorder_columns(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def list_table_rows(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        order_descending: bool = True,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.
        """
        return self.table.list_table_rows(
            table_type,
            table_id,
            offset=offset,
            limit=limit,
            search_query=search_query,
            columns=columns,
            float_decimals=float_decimals,
            vec_decimals=vec_decimals,
            order_descending=order_descending,
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def get_table_row(
        self,
        table_type: str | TableType,
        table_id: str,
        row_id: str,
        *,
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
        return self.table.get_table_row(
            table_type,
            table_id,
            row_id,
            columns=columns,
            float_decimals=float_decimals,
            vec_decimals=vec_decimals,
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def add_table_rows(
        self,
        table_type: str | TableType,
        request: RowAddRequest,
    ) -> (
        GenTableRowsChatCompletionChunks
        | AsyncGenerator[GenTableStreamReferences | GenTableStreamChatCompletionChunk, None]
    ):
        """
        Add rows to a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowAddRequest): The row add request.

        Returns:
            response (GenTableRowsChatCompletionChunks | AsyncGenerator): The row completion.
                In streaming mode, it is a generator that yields a `GenTableStreamReferences` object
                followed by zero or more `GenTableStreamChatCompletionChunk` objects.
                In non-streaming mode, it is a `GenTableRowsChatCompletionChunks` object.
        """
        return self.table.add_table_rows(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def regen_table_rows(
        self,
        table_type: str | TableType,
        request: RowRegenRequest,
    ) -> (
        GenTableRowsChatCompletionChunks
        | AsyncGenerator[GenTableStreamReferences | GenTableStreamChatCompletionChunk, None]
    ):
        """
        Regenerate rows in a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowRegenRequest): The row regenerate request.

        Returns:
            response (GenTableRowsChatCompletionChunks | AsyncGenerator): The row completion.
                In streaming mode, it is a generator that yields a `GenTableStreamReferences` object
                followed by zero or more `GenTableStreamChatCompletionChunk` objects.
                In non-streaming mode, it is a `GenTableRowsChatCompletionChunks` object.
        """
        return self.table.regen_table_rows(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.update_table_row(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.delete_table_rows(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.delete_table_row(table_type, table_id, row_id)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def get_conversation_thread(
        self,
        table_type: str | TableType,
        table_id: str,
        column_id: str,
        row_id: str = "",
        include: bool = True,
    ) -> ChatThread:
        """
        Get the conversation thread for a chat table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): ID / name of the chat table.
            column_id (str): ID / name of the column to fetch.
            row_id (str, optional): ID / name of the last row in the thread.
                Defaults to "" (export all rows).
            include (bool, optional): Whether to include the row specified by `row_id`.
                Defaults to True.

        Returns:
            response (ChatThread): The conversation thread.
        """
        return self.table.get_conversation_thread(
            table_type, table_id, column_id, row_id=row_id, include=include
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.hybrid_search(table_type, request)

    @deprecated(
        "This method is deprecated, use `client.table.embed_file_options` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    def upload_file_options(self) -> httpx.Response:
        """
        Get options for uploading a file to a Knowledge Table.

        Returns:
            response (httpx.Response): The response containing options information.
        """
        return self.table.embed_file_options()

    @deprecated(
        "This method is deprecated, use `client.table.embed_file` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    def upload_file(self, request: FileUploadRequest) -> OkResponse:
        """
        Upload a file to a Knowledge Table.

        Args:
            request (FileUploadRequest): The file upload request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return self.table.embed_file(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return self.table.import_table_data(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def export_table_data(
        self,
        table_type: str | TableType,
        table_id: str,
        columns: list[str] | None = None,
        delimiter: Literal[",", "\t"] = ",",
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
        return self.table.export_table_data(
            table_type, table_id, columns=columns, delimiter=delimiter
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def import_table(
        self,
        table_type: str | TableType,
        request: TableImportRequest,
    ) -> TableMetaResponse:
        """
        Imports a table (data and schema) from a parquet file.

        Args:
            file_path (str): The parquet file path.
            table_type (str | TableType): Table type.
            request (TableImportRequest): Table import request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return self.table.import_table(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    def export_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> bytes:
        """
        Exports a table (data and schema) as a parquet file.

        Args:
            table_type (str | TableType): Table type.
            table_id (str): ID or name of the table to be exported.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        return self.table.export_table(table_type, table_id)


class _ClientAsync(_Client):
    async def close(self) -> None:
        """
        Close the HTTP async client.
        """
        await self.http_client.aclose()

    @staticmethod
    async def raise_exception(
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
        error = json_loads(error)
        err_mssg = error.get("message", error.get("detail", str(error)))
        if code == 404:
            exc = ResourceNotFoundError
        else:
            exc = RuntimeError
        raise exc(err_mssg)

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
        response = await self.raise_exception(response)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)

    async def _post(
        self,
        address: str,
        endpoint: str,
        *,
        body: BaseModel | None,
        response_model: Type[BaseModel] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous POST request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            body (BaseModel | None): The request body.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.post`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        if body is not None:
            body = body.model_dump()
        response = await self.http_client.post(
            f"{address}{endpoint}",
            json=body,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        )
        response = await self.raise_exception(response)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)

    async def _options(
        self,
        address: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        response_model: Type[BaseModel] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous OPTIONS request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return.
            **kwargs (Any): Keyword arguments for `httpx.options`.

        Returns:
            response (httpx.Response | BaseModel): The response or Pydantic response object.
        """
        response = await self.http_client.options(
            f"{address}{endpoint}",
            params=await self._filter_params(params),
            headers=self.headers,
            **kwargs,
        )
        response = await self.raise_exception(response)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)

    async def _patch(
        self,
        address: str,
        endpoint: str,
        *,
        body: BaseModel | None,
        response_model: Type[BaseModel] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make an asynchronous PATCH request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            body (BaseModel | None): The request body.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return. Defaults to None.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.patch`.

        Returns:
            response (httpx.Response | BaseModel): The response text or Pydantic response object.
        """
        if body is not None:
            body = body.model_dump()
        response = await self.http_client.patch(
            f"{address}{endpoint}",
            json=body,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        )
        response = await self.raise_exception(response)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)

    async def _stream(
        self,
        address: str,
        endpoint: str,
        *,
        body: BaseModel | None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Make an asynchronous streaming POST request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            body (BaseModel | None): The request body.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            **kwargs (Any): Keyword arguments for `httpx.stream`.

        Yields:
            str: The response chunks.
        """
        if body is not None:
            body = body.model_dump()
        async with self.http_client.stream(
            "POST",
            f"{address}{endpoint}",
            json=body,
            headers=self.headers,
            params=self._filter_params(params),
            **kwargs,
        ) as response:
            response = await self.raise_exception(response)
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
        ignore_code: int | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        """
        Make a DELETE request to the specified endpoint.

        Args:
            address (str): The base address of the API.
            endpoint (str): The API endpoint.
            params (dict[str, Any] | None, optional): Query parameters. Defaults to None.
            response_model (Type[pydantic.BaseModel] | None, optional): The response model to return.
            ignore_code (int | None, optional): HTTP code to ignore.
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
        response = await self.raise_exception(response, ignore_code=ignore_code)
        if response_model is None:
            return response
        else:
            return response_model.model_validate_json(response.text)


class _BackendAdminClientAsync(_ClientAsync):
    """Backend administration methods."""

    async def create_user(self, request: UserCreate) -> UserRead:
        return await self._post(
            self.api_base,
            "/admin/backend/v1/users",
            body=request,
            response_model=UserRead,
        )

    async def update_user(self, request: UserUpdate) -> UserRead:
        return await self._patch(
            self.api_base,
            "/admin/backend/v1/users",
            body=request,
            response_model=UserRead,
        )

    async def list_users(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: str = AdminOrderBy.UPDATED_AT,
        order_descending: bool = True,
    ) -> Page[UserRead]:
        return await self._get(
            self.api_base,
            "/admin/backend/v1/users",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_descending=order_descending,
            ),
            response_model=Page[UserRead],
        )

    async def get_user(self, user_id: str) -> UserRead:
        return await self._get(
            self.api_base,
            f"/admin/backend/v1/users/{quote(user_id)}",
            params=None,
            response_model=UserRead,
        )

    async def delete_user(
        self,
        user_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        response = await self._delete(
            self.api_base,
            f"/admin/backend/v1/users/{quote(user_id)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def create_pat(self, request: PATCreate) -> PATRead:
        return await self._post(
            self.api_base,
            "/admin/backend/v1/pats",
            body=request,
            response_model=PATRead,
        )

    async def get_pat(self, pat: str) -> PATRead:
        return await self._get(
            self.api_base,
            f"/admin/backend/v1/pats/{quote(pat)}",
            params=None,
            response_model=PATRead,
        )

    async def delete_pat(
        self,
        pat: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        response = await self._delete(
            self.api_base,
            f"/admin/backend/v1/pats/{quote(pat)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def create_organization(self, request: OrganizationCreate) -> OrganizationRead:
        return await self._post(
            self.api_base,
            "/admin/backend/v1/organizations",
            body=request,
            response_model=OrganizationRead,
        )

    async def update_organization(self, request: OrganizationUpdate) -> OrganizationRead:
        return await self._patch(
            self.api_base,
            "/admin/backend/v1/organizations",
            body=request,
            response_model=OrganizationRead,
        )

    async def list_organizations(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: str = AdminOrderBy.UPDATED_AT,
        order_descending: bool = True,
    ) -> Page[OrganizationRead]:
        return await self._get(
            self.api_base,
            "/admin/backend/v1/organizations",
            params=dict(
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_descending=order_descending,
            ),
            response_model=Page[OrganizationRead],
        )

    async def get_organization(self, organization_id: str) -> OrganizationRead:
        return await self._get(
            self.api_base,
            f"/admin/backend/v1/organizations/{quote(organization_id)}",
            params=None,
            response_model=OrganizationRead,
        )

    async def delete_organization(
        self,
        organization_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        response = await self._delete(
            self.api_base,
            f"/admin/backend/v1/organizations/{quote(organization_id)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def generate_invite_token(
        self,
        organization_id: str,
        user_email: str = "",
        valid_days: int = 7,
    ) -> str:
        """
        Generates an invite token to join an organization.

        Args:
            organization_id (str): Organization ID.
            user_email (str, optional): User email.
                Leave blank to disable email check and generate a public invite. Defaults to "".
            valid_days (int, optional): How many days should this link be valid for. Defaults to 7.

        Returns:
            token (str): _description_
        """
        response = await self._get(
            self.api_base,
            "/admin/backend/v1/invite_tokens",
            params=dict(
                organization_id=organization_id, user_email=user_email, valid_days=valid_days
            ),
            response_model=None,
        )
        return response.text

    async def join_organization(self, request: OrgMemberCreate) -> OrgMemberRead:
        return await self._post(
            self.api_base,
            "/admin/backend/v1/organizations/link",
            body=request,
            response_model=OrgMemberRead,
        )

    async def leave_organization(self, user_id: str, organization_id: str) -> OkResponse:
        return await self._delete(
            self.api_base,
            f"/admin/backend/v1/organizations/link/{quote(user_id)}/{quote(organization_id)}",
            params=None,
            response_model=OkResponse,
        )

    async def create_api_key(self, request: ApiKeyCreate) -> ApiKeyRead:
        warn(ORG_API_KEY_DEPRECATE, FutureWarning, stacklevel=2)
        return await self._post(
            self.api_base,
            "/admin/backend/v1/api_keys",
            body=request,
            response_model=ApiKeyRead,
        )

    async def get_api_key(self, api_key: str) -> ApiKeyRead:
        warn(ORG_API_KEY_DEPRECATE, FutureWarning, stacklevel=2)
        return await self._get(
            self.api_base,
            f"/admin/backend/v1/api_keys/{quote(api_key)}",
            params=None,
            response_model=ApiKeyRead,
        )

    async def delete_api_key(
        self,
        api_key: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        warn(ORG_API_KEY_DEPRECATE, FutureWarning, stacklevel=2)
        response = await self._delete(
            self.api_base,
            f"/admin/backend/v1/api_keys/{quote(api_key)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def refresh_quota(
        self,
        organization_id: str,
        reset_usage: bool = True,
    ) -> OrganizationRead:
        return await self._post(
            self.api_base,
            f"/admin/backend/v1/quotas/refresh/{quote(organization_id)}",
            body=None,
            params=dict(reset_usage=reset_usage),
            response_model=OrganizationRead,
        )

    async def get_event(self, event_id: str) -> EventRead:
        return await self._get(
            self.api_base,
            f"/admin/backend/v1/events/{quote(event_id)}",
            params=None,
            response_model=EventRead,
        )

    async def add_event(self, request: EventCreate) -> OkResponse:
        return await self._post(
            self.api_base,
            "/admin/backend/v1/events",
            body=request,
            response_model=OkResponse,
        )

    async def mark_event_as_done(self, event_id: str) -> OkResponse:
        return await self._patch(
            self.api_base,
            f"/admin/backend/v1/events/done/{quote(event_id)}",
            body=None,
            response_model=OkResponse,
        )

    async def get_internal_organization_id(self) -> StringResponse:
        return await self._get(
            self.api_base,
            "/admin/backend/v1/internal_organization_id",
            params=None,
            response_model=StringResponse,
        )

    async def set_internal_organization_id(self, organization_id: str) -> OkResponse:
        return await self._patch(
            self.api_base,
            f"/admin/backend/v1/internal_organization_id/{quote(organization_id)}",
            body=None,
            response_model=OkResponse,
        )

    async def get_pricing(self) -> Price:
        return await self._get(
            self.api_base,
            "/public/v1/prices/plans",
            params=None,
            response_model=Price,
        )

    async def set_pricing(self, request: Price) -> OkResponse:
        return await self._patch(
            self.api_base,
            "/admin/backend/v1/prices/plans",
            body=request,
            response_model=OkResponse,
        )

    async def get_model_pricing(self) -> ModelPrice:
        return await self._get(
            self.api_base,
            "/public/v1/prices/models",
            params=None,
            response_model=ModelPrice,
        )

    async def get_model_config(self) -> ModelListConfig:
        return await self._get(
            self.api_base,
            "/admin/backend/v1/models",
            params=None,
            response_model=ModelListConfig,
        )

    async def set_model_config(self, request: ModelListConfig) -> OkResponse:
        return await self._patch(
            self.api_base,
            "/admin/backend/v1/models",
            body=request,
            response_model=OkResponse,
        )

    async def add_template(
        self,
        source: str | BinaryIO,
        template_id_dst: str,
        exist_ok: bool = False,
    ) -> OkResponse:
        """
        Upload a template Parquet file to add a new template into gallery.

        Args:
            source (str | BinaryIO): The path to the template Parquet file or a file-like object.
            template_id_dst (str): The ID of the new template.
            exist_ok (bool, optional): Whether to overwrite existing template. Defaults to False.

        Returns:
            response (OkResponse): The response indicating success.
        """
        kwargs = dict(
            address=self.api_base,
            endpoint="/admin/backend/v1/templates/import",
            body=None,
            response_model=OkResponse,
            data={"template_id_dst": template_id_dst, "exist_ok": exist_ok},
            timeout=self.file_upload_timeout,
        )
        mime_type = "application/octet-stream"
        if isinstance(source, str):
            filename = split(source)[-1]
            # Open the file in binary mode
            with open(source, "rb") as f:
                return await self._post(files={"file": (filename, f, mime_type)}, **kwargs)
        else:
            filename = "import.parquet"
            return await self._post(files={"file": (filename, source, mime_type)}, **kwargs)

    async def populate_templates(self, timeout: float = 30.0) -> OkResponse:
        """
        Re-populates the template gallery.

        Args:
            timeout (float, optional): Timeout in seconds, must be >= 0. Defaults to 30.0.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self._post(
            self.api_base,
            "/admin/backend/v1/templates/populate",
            body=None,
            params=dict(timeout=timeout),
            response_model=OkResponse,
        )


class _OrgAdminClientAsync(_ClientAsync):
    """Organization administration methods."""

    async def get_org_model_config(self, organization_id: str) -> ModelListConfig:
        return await self._get(
            self.api_base,
            f"/admin/org/v1/models/{quote(organization_id)}",
            params=None,
            response_model=ModelListConfig,
        )

    async def set_org_model_config(
        self,
        organization_id: str,
        config: ModelListConfig,
    ) -> OkResponse:
        return await self._patch(
            self.api_base,
            f"/admin/org/v1/models/{quote(organization_id)}",
            body=config,
            response_model=OkResponse,
        )

    async def create_project(self, request: ProjectCreate) -> ProjectRead:
        return await self._post(
            self.api_base,
            "/admin/org/v1/projects",
            body=request,
            response_model=ProjectRead,
        )

    async def update_project(self, request: ProjectUpdate) -> ProjectRead:
        return await self._patch(
            self.api_base,
            "/admin/org/v1/projects",
            body=request,
            response_model=ProjectRead,
        )

    async def set_project_updated_at(
        self,
        project_id: str,
        updated_at: str | None = None,
    ) -> OkResponse:
        return await self._patch(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}",
            body=None,
            params=dict(updated_at=updated_at),
            response_model=OkResponse,
        )

    async def list_projects(
        self,
        organization_id: str = "default",
        search_query: str = "",
        offset: int = 0,
        limit: int = 100,
        order_by: str = AdminOrderBy.UPDATED_AT,
        order_descending: bool = True,
    ) -> Page[ProjectRead]:
        return await self._get(
            self.api_base,
            "/admin/org/v1/projects",
            params=dict(
                organization_id=organization_id,
                search_query=search_query,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_descending=order_descending,
            ),
            response_model=Page[ProjectRead],
        )

    async def get_project(self, project_id: str) -> ProjectRead:
        return await self._get(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}",
            params=None,
            response_model=ProjectRead,
        )

    async def delete_project(
        self,
        project_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        response = await self._delete(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def import_project(
        self,
        source: str | BinaryIO,
        organization_id: str,
        project_id_dst: str = "",
    ) -> ProjectRead:
        """
        Imports a project.

        Args:
            source (str | BinaryIO): The parquet file path or file-like object.
                It can be a Project or Template file.
            organization_id (str): Organization ID "org_xxx".
            project_id_dst (str, optional): ID of the project to import tables into.
                Defaults to creating new project.

        Returns:
            response (ProjectRead): The imported project.
        """
        kwargs = dict(
            address=self.api_base,
            endpoint=f"/admin/org/v1/projects/import/{quote(organization_id)}",
            body=None,
            response_model=ProjectRead,
            data={"project_id_dst": project_id_dst},
            timeout=self.file_upload_timeout,
        )
        mime_type = "application/octet-stream"
        if isinstance(source, str):
            filename = split(source)[-1]
            # Open the file in binary mode
            with open(source, "rb") as f:
                return await self._post(files={"file": (filename, f, mime_type)}, **kwargs)
        else:
            filename = "import.parquet"
            return await self._post(files={"file": (filename, source, mime_type)}, **kwargs)

    async def export_project(
        self,
        project_id: str,
        compression: Literal["NONE", "ZSTD", "LZ4", "SNAPPY"] = "ZSTD",
    ) -> bytes:
        """
        Exports a project as a Project Parquet file.

        Args:
            project_id (str): Project ID "proj_xxx".
            compression (str, optional): Parquet compression codec. Defaults to "ZSTD".

        Returns:
            response (bytes): The Parquet file.
        """
        response = await self._get(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}/export",
            params=dict(compression=compression),
            response_model=None,
        )
        return response.content

    async def import_project_from_template(
        self,
        organization_id: str,
        template_id: str,
        project_id_dst: str = "",
    ) -> ProjectRead:
        """
        Imports a project from a template.

        Args:
            organization_id (str): Organization ID "org_xxx".
            template_id (str): ID of the template to import from.
            project_id_dst (str, optional): ID of the project to import tables into.
                Defaults to creating new project.

        Returns:
            response (ProjectRead): The imported project.
        """
        return await self._post(
            self.api_base,
            f"/admin/org/v1/projects/import/{quote(organization_id)}/templates/{quote(template_id)}",
            body=None,
            params=dict(project_id_dst=project_id_dst),
            response_model=ProjectRead,
        )

    async def export_project_as_template(
        self,
        project_id: str,
        *,
        name: str,
        tags: list[str],
        description: str,
        compression: Literal["NONE", "ZSTD", "LZ4", "SNAPPY"] = "ZSTD",
    ) -> bytes:
        """
        Exports a project as a template Parquet file.

        Args:
            project_id (str): Project ID "proj_xxx".
            name (str): Template name.
            tags (list[str]): Template tags.
            description (str): Template description.
            compression (str, optional): Parquet compression codec. Defaults to "ZSTD".

        Returns:
            response (bytes): The template Parquet file.
        """
        response = await self._get(
            self.api_base,
            f"/admin/org/v1/projects/{quote(project_id)}/export/template",
            params=dict(
                name=name,
                tags=tags,
                description=description,
                compression=compression,
            ),
            response_model=None,
        )
        return response.content


class _AdminClientAsync(_ClientAsync):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.backend = _BackendAdminClientAsync(*args, **kwargs)
        self.organization = _OrgAdminClientAsync(*args, **kwargs)


class _TemplateClientAsync(_ClientAsync):
    """Template methods."""

    async def list_templates(self, search_query: str = "") -> Page[Template]:
        """
        List all templates.

        Args:
            search_query (str, optional): A string to search for within template names.

        Returns:
            templates (Page[Template]): A page of templates.
        """
        return await self._get(
            self.api_base,
            "/public/v1/templates",
            params=dict(search_query=search_query),
            response_model=Page[Template],
        )

    async def get_template(self, template_id: str) -> Template:
        """
        Get a template by its ID.

        Args:
            template_id (str): Template ID.

        Returns:
            template (Template): The template.
        """
        return await self._get(
            self.api_base,
            f"/public/v1/templates/{quote(template_id)}",
            params=None,
            response_model=Template,
        )

    async def list_tables(
        self,
        template_id: str,
        table_type: str,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        order_by: str = GenTableOrderBy.UPDATED_AT,
        order_descending: bool = True,
    ) -> Page[TableMetaResponse]:
        """
        List all tables in a template.

        Args:
            template_id (str): Template ID.
            table_type (str): Table type.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).
            order_by (str, optional): Sort tables by this attribute. Defaults to "updated_at".
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.

        Returns:
            tables (Page[TableMetaResponse]): A page of tables.
        """
        return await self._get(
            self.api_base,
            f"/public/v1/templates/{quote(template_id)}/gen_tables/{quote(table_type)}",
            params=dict(
                offset=offset,
                limit=limit,
                search_query=search_query,
                order_by=order_by,
                order_descending=order_descending,
            ),
            response_model=Page[TableMetaResponse],
        )

    async def get_table(
        self, template_id: str, table_type: str, table_id: str
    ) -> TableMetaResponse:
        """
        Get a table in a template.

        Args:
            template_id (str): Template ID.
            table_type (str): Table type.
            table_id (str): Table ID.

        Returns:
            table (TableMetaResponse): The table.
        """
        return await self._get(
            self.api_base,
            f"/public/v1/templates/{quote(template_id)}/gen_tables/{quote(table_type)}/{quote(table_id)}",
            params=None,
            response_model=TableMetaResponse,
        )

    async def list_table_rows(
        self,
        template_id: str,
        table_type: str,
        table_id: str,
        *,
        starting_after: str | None = None,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "Updated at",
        order_descending: bool = True,
        float_decimals: int = 0,
        vec_decimals: int = 0,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a template table.

        Args:
            template_id (str): Template ID.
            table_type (str): Table type.
            table_id (str): Table ID.
            starting_after (str | None, optional): A cursor for use in pagination.
                Only rows with ID > `starting_after` will be returned.
                For instance, if your call receives 100 rows ending with ID "x",
                your subsequent call can include `starting_after="x"` in order to fetch the next page of the list.
                Defaults to None.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            order_by (str, optional): Sort rows by this column. Defaults to "Updated at".
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).

        Returns:
            rows (Page[dict[str, Any]]): The rows.
        """
        return await self._get(
            self.api_base,
            f"/public/v1/templates/{quote(template_id)}/gen_tables/{quote(table_type)}/{quote(table_id)}/rows",
            params=dict(
                starting_after=starting_after,
                offset=offset,
                limit=limit,
                order_by=order_by,
                order_descending=order_descending,
                float_decimals=float_decimals,
                vec_decimals=vec_decimals,
            ),
            response_model=Page[dict[str, Any]],
        )


class _FileClientAsync(_ClientAsync):
    """File methods."""

    async def upload_file(self, file_path: str) -> FileUploadResponse:
        """
        Uploads a file to the server.

        Args:
            file_path (str): Path to the file to be uploaded.

        Returns:
            response (FileUploadResponse): The response containing the file URI.
        """
        filename = split(file_path)[-1]
        mime_type = filetype.guess(file_path).mime
        if mime_type is None:
            mime_type = "application/octet-stream"  # Default MIME type

        with open(file_path, "rb") as f:
            return await self._post(
                self.api_base,
                "/v1/files/upload",
                body=None,
                response_model=FileUploadResponse,
                files={
                    "file": (filename, f, mime_type),
                },
                timeout=self.file_upload_timeout,
            )

    async def get_raw_urls(self, uris: list[str]) -> GetURLResponse:
        """
        Get download URLs for raw files.

        Args:
            uris (List[str]): List of file URIs to download.

        Returns:
            response (GetURLResponse): The response containing download information for the files.
        """
        return await self._post(
            self.api_base,
            "/v1/files/url/raw",
            body=GetURLRequest(uris=uris),
            response_model=GetURLResponse,
        )

    async def get_thumbnail_urls(self, uris: list[str]) -> GetURLResponse:
        """
        Get download URLs for file thumbnails.

        Args:
            uris (List[str]): List of file URIs to get thumbnails for.

        Returns:
            response (GetURLResponse): The response containing download information for the thumbnails.
        """
        return await self._post(
            self.api_base,
            "/v1/files/url/thumb",
            body=GetURLRequest(uris=uris),
            response_model=GetURLResponse,
        )


class _GenTableClientAsync(_ClientAsync):
    """Generative Table methods."""

    async def create_action_table(self, request: ActionTableSchemaCreate) -> TableMetaResponse:
        """
        Create an Action Table.

        Args:
            request (ActionTableSchemaCreate): The action table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/action",
            body=request,
            response_model=TableMetaResponse,
        )

    async def create_knowledge_table(
        self, request: KnowledgeTableSchemaCreate
    ) -> TableMetaResponse:
        """
        Create a Knowledge Table.

        Args:
            request (KnowledgeTableSchemaCreate): The knowledge table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/knowledge",
            body=request,
            response_model=TableMetaResponse,
        )

    async def create_chat_table(self, request: ChatTableSchemaCreate) -> TableMetaResponse:
        """
        Create a Chat Table.

        Args:
            request (ChatTableSchemaCreate): The chat table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/chat",
            body=request,
            response_model=TableMetaResponse,
        )

    async def get_table(
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
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}",
            params=None,
            response_model=TableMetaResponse,
        )

    async def list_tables(
        self,
        table_type: str | TableType,
        *,
        offset: int = 0,
        limit: int = 100,
        parent_id: str | None = None,
        search_query: str = "",
        order_by: str = GenTableOrderBy.UPDATED_AT,
        order_descending: bool = True,
        count_rows: bool = False,
    ) -> Page[TableMetaResponse]:
        """
        List Generative Tables of a specific type.

        Args:
            table_type (str | TableType): The type of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            parent_id (str | None, optional): Parent ID of tables to return.
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
                Defaults to None (return all tables).
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).
            order_by (str, optional): Sort tables by this attribute. Defaults to "updated_at".
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.
            count_rows (bool, optional): Whether to count the rows of the tables. Defaults to False.

        Returns:
            response (Page[TableMetaResponse]): The paginated table metadata response.
        """
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}",
            params=dict(
                offset=offset,
                limit=limit,
                parent_id=parent_id,
                search_query=search_query,
                order_by=order_by,
                order_descending=order_descending,
                count_rows=count_rows,
            ),
            response_model=Page[TableMetaResponse],
        )

    async def delete_table(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        """
        Delete a specific table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            missing_ok (bool, optional): Ignore resource not found error.

        Returns:
            response (OkResponse): The response indicating success.
        """
        response = await self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}",
            params=None,
            response_model=None,
            ignore_code=404 if missing_ok else None,
        )
        if response.status_code == 404 and missing_ok:
            return OkResponse()
        else:
            return OkResponse.model_validate_json(response.text)

    async def duplicate_table(
        self,
        table_type: str | TableType,
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
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str | None, optional): The destination / new table ID.
                Defaults to None (create a new table ID automatically).
            include_data (bool, optional): Whether to include data in the duplicated table. Defaults to True.
            create_as_child (bool, optional): Whether the new table is a child table.
                If this is True, then `include_data` will be set to True. Defaults to False.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        if "deploy" in kwargs:
            warn(
                'The "deploy" argument is deprecated, use "create_as_child" instead.',
                FutureWarning,
                stacklevel=2,
            )
            create_as_child = create_as_child or kwargs.pop("deploy")
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/duplicate/{quote(table_id_src)}",
            body=None,
            params=dict(
                table_id_dst=table_id_dst,
                include_data=include_data,
                create_as_child=create_as_child,
            ),
            response_model=TableMetaResponse,
        )

    async def rename_table(
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
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/rename/{quote(table_id_src)}/{quote(table_id_dst)}",
            body=None,
            response_model=TableMetaResponse,
        )

    async def update_gen_config(
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
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/gen_config/update",
            body=request,
            response_model=TableMetaResponse,
        )

    async def add_action_columns(self, request: AddActionColumnSchema) -> TableMetaResponse:
        """
        Add columns to an Action Table.

        Args:
            request (AddActionColumnSchema): The action column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/action/columns/add",
            body=request,
            response_model=TableMetaResponse,
        )

    async def add_knowledge_columns(self, request: AddKnowledgeColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Knowledge Table.

        Args:
            request (AddKnowledgeColumnSchema): The knowledge column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/knowledge/columns/add",
            body=request,
            response_model=TableMetaResponse,
        )

    async def add_chat_columns(self, request: AddChatColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Chat Table.

        Args:
            request (AddChatColumnSchema): The chat column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self._post(
            self.api_base,
            "/v1/gen_tables/chat/columns/add",
            body=request,
            response_model=TableMetaResponse,
        )

    async def drop_columns(
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
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/columns/drop",
            body=request,
            response_model=TableMetaResponse,
        )

    async def rename_columns(
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
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/columns/rename",
            body=request,
            response_model=TableMetaResponse,
        )

    async def reorder_columns(
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
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/columns/reorder",
            body=request,
            response_model=TableMetaResponse,
        )

    async def list_table_rows(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        order_descending: bool = True,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.
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
                order_descending=order_descending,
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
        Add rows to a table.

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
                    body=request,
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
                body=request,
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
        Regenerate rows in a table.

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
                    body=request,
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
                body=request,
                response_model=GenTableRowsChatCompletionChunks,
            )

    async def update_table_row(
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
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/rows/update",
            body=request,
            response_model=OkResponse,
        )

    async def delete_table_rows(
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
        return await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/rows/delete",
            body=request,
            response_model=OkResponse,
        )

    async def delete_table_row(
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
        return await self._delete(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/rows/{quote(row_id)}",
            params=None,
            response_model=OkResponse,
        )

    async def get_conversation_thread(
        self,
        table_type: str | TableType,
        table_id: str,
        column_id: str,
        *,
        row_id: str = "",
        include: bool = True,
    ) -> ChatThread:
        """
        Get the conversation thread for a chat table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): ID / name of the chat table.
            column_id (str): ID / name of the column to fetch.
            row_id (str, optional): ID / name of the last row in the thread.
                Defaults to "" (export all rows).
            include (bool, optional): Whether to include the row specified by `row_id`.
                Defaults to True.

        Returns:
            response (ChatThread): The conversation thread.
        """
        return await self._get(
            self.api_base,
            f"/v1/gen_tables/{table_type}/{quote(table_id)}/thread",
            params=dict(column_id=column_id, row_id=row_id, include=include),
            response_model=ChatThread,
        )

    async def hybrid_search(
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
        response = await self._post(
            self.api_base,
            f"/v1/gen_tables/{table_type}/hybrid_search",
            body=request,
            response_model=None,
        )
        return json_loads(response.text)

    async def embed_file_options(self) -> httpx.Response:
        """
        Get options for embedding a file to a Knowledge Table.

        Returns:
            response (httpx.Response): The response containing options information.
        """
        response = await self._options(
            self.api_base,
            "/v1/gen_tables/knowledge/embed_file",
        )
        return response

    async def embed_file(
        self,
        file_path: str,
        table_id: str,
        *,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
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
        # Guess the MIME type of the file based on its extension
        mime_type, _ = guess_type(file_path)
        if mime_type is None:
            mime_type = (
                "application/jsonl" if file_path.endswith(".jsonl") else "application/octet-stream"
            )  # Default MIME type
        # Extract the filename from the file path
        filename = split(file_path)[-1]
        # Open the file in binary mode
        with open(file_path, "rb") as f:
            response = await self._post(
                self.api_base,
                "/v1/gen_tables/knowledge/embed_file",
                body=None,
                response_model=OkResponse,
                files={
                    "file": (filename, f, mime_type),
                },
                data={
                    "table_id": table_id,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    # "overwrite": request.overwrite,
                },
                timeout=self.file_upload_timeout,
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
                        body=None,
                        files={
                            "file": (filename, f, mime_type),
                        },
                        data=data,
                        timeout=self.file_upload_timeout,
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
                    body=None,
                    response_model=GenTableRowsChatCompletionChunks,
                    files={
                        "file": (filename, f, mime_type),
                    },
                    data=data,
                    timeout=self.file_upload_timeout,
                )

    async def export_table_data(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        columns: list[str] | None = None,
        delimiter: Literal[",", "\t"] = ",",
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
        Imports a table (data and schema) from a parquet file.

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
                body=None,
                response_model=TableMetaResponse,
                files={
                    "file": (filename, f, mime_type),
                },
                data=data,
                timeout=self.file_upload_timeout,
            )

    async def export_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> bytes:
        """
        Exports a table (data and schema) as a parquet file.

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


class JamAIAsync(_ClientAsync):
    def __init__(
        self,
        project_id: str = ENV_CONFIG.jamai_project_id,
        token: str = ENV_CONFIG.jamai_token_plain,
        api_base: str = ENV_CONFIG.jamai_api_base,
        headers: dict | None = None,
        timeout: float | None = ENV_CONFIG.jamai_timeout_sec,
        file_upload_timeout: float | None = ENV_CONFIG.jamai_file_upload_timeout_sec,
        *,
        api_key: str = "",
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
            api_key (str, optional): (Deprecated) Organization API key for authentication.
        """
        if api_key:
            warn(ORG_API_KEY_DEPRECATE, FutureWarning, stacklevel=2)
        http_client = httpx.AsyncClient(
            timeout=timeout,
            transport=httpx.AsyncHTTPTransport(retries=3),
        )
        kwargs = dict(
            project_id=project_id,
            token=token or api_key,
            api_base=api_base,
            headers=headers,
            http_client=http_client,
            file_upload_timeout=file_upload_timeout,
        )
        super().__init__(**kwargs)
        self.admin = _AdminClientAsync(**kwargs)
        self.template = _TemplateClientAsync(**kwargs)
        self.file = _FileClientAsync(**kwargs)
        self.table = _GenTableClientAsync(**kwargs)

    async def health(self) -> dict[str, Any]:
        """
        Get health status.

        Returns:
            response (dict[str, Any]): Health status.
        """
        response = await self._get(self.api_base, "/health", response_model=None)
        return json_loads(response.text)

    # --- Models and chat --- #

    async def model_info(
        self,
        name: str = "",
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "tool", "embed", "rerank"]
        ]
        | None = None,
    ) -> ModelInfoResponse:
        """
        Get information about available models.

        Args:
            name (str, optional): The model name. Defaults to "".
            capabilities (list[Literal["completion", "chat", "image", "audio", "tool", "embed", "rerank"]] | None, optional):
                List of model capabilities to filter by. Defaults to None.

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
        capabilities: list[
            Literal["completion", "chat", "image", "audio", "tool", "embed", "rerank"]
        ]
        | None = None,
    ) -> list[str]:
        """
        Get the names of available models.

        Args:
            prefer (str, optional): Preferred model name. Defaults to "".
            capabilities (list[Literal["completion", "chat", "image", "audio", "tool", "embed", "rerank"]] | None, optional):
                List of model capabilities to filter by. Defaults to None.

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
        Generates chat completions.

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
                    self.api_base, "/v1/chat/completions", body=request
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
                body=request,
                response_model=ChatCompletionChunk,
            )

    async def generate_embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """
        Generate embeddings for the given input.

        Args:
            request (EmbeddingRequest): The embedding request.

        Returns:
            response (EmbeddingResponse): The embedding response.
        """
        return await self._post(
            self.api_base,
            "/v1/embeddings",
            body=request,
            response_model=EmbeddingResponse,
        )

    # --- Gen Table --- #
    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def create_action_table(self, request: ActionTableSchemaCreate) -> TableMetaResponse:
        """
        Create an Action Table.

        Args:
            request (ActionTableSchemaCreate): The action table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self.table.create_action_table(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def create_knowledge_table(
        self, request: KnowledgeTableSchemaCreate
    ) -> TableMetaResponse:
        """
        Create a Knowledge Table.

        Args:
            request (KnowledgeTableSchemaCreate): The knowledge table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self.table.create_knowledge_table(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def create_chat_table(self, request: ChatTableSchemaCreate) -> TableMetaResponse:
        """
        Create a Chat Table.

        Args:
            request (ChatTableSchemaCreate): The chat table schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self.table.create_chat_table(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def get_table(
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
        return await self.table.get_table(table_type, table_id)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def list_tables(
        self,
        table_type: str | TableType,
        offset: int = 0,
        limit: int = 100,
        parent_id: str | None = None,
        search_query: str = "",
        order_by: str = GenTableOrderBy.UPDATED_AT,
        order_descending: bool = True,
        count_rows: bool = False,
    ) -> Page[TableMetaResponse]:
        """
        List Generative Tables of a specific type.

        Args:
            table_type (str | TableType): The type of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of tables to return (min 1, max 100). Defaults to 100.
            parent_id (str | None, optional): Parent ID of tables to return.
                Additionally for Chat Table, you can list:
                (1) all chat agents by passing in "_agent_"; or
                (2) all chats by passing in "_chat_".
                Defaults to None (return all tables).
            search_query (str, optional): A string to search for within table IDs as a filter.
                Defaults to "" (no filter).
            order_by (str, optional): Sort tables by this attribute. Defaults to "updated_at".
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.
            count_rows (bool, optional): Whether to count the rows of the tables. Defaults to False.

        Returns:
            response (Page[TableMetaResponse]): The paginated table metadata response.
        """
        return await self.table.list_tables(
            table_type,
            offset=offset,
            limit=limit,
            parent_id=parent_id,
            search_query=search_query,
            order_by=order_by,
            order_descending=order_descending,
            count_rows=count_rows,
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def delete_table(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        missing_ok: bool = True,
    ) -> OkResponse:
        """
        Delete a specific table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            missing_ok (bool, optional): Ignore resource not found error.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self.table.delete_table(table_type, table_id, missing_ok=missing_ok)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def duplicate_table(
        self,
        table_type: str | TableType,
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
            table_type (str | TableType): The type of the table.
            table_id_src (str): The source table ID.
            table_id_dst (str | None, optional): The destination / new table ID.
                Defaults to None (create a new table ID automatically).
            include_data (bool, optional): Whether to include data in the duplicated table. Defaults to True.
            create_as_child (bool, optional): Whether the new table is a child table.
                If this is True, then `include_data` will be set to True. Defaults to False.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self.table.duplicate_table(
            table_type,
            table_id_src,
            table_id_dst,
            include_data=include_data,
            create_as_child=create_as_child,
            **kwargs,
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def rename_table(
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
        return await self.table.rename_table(table_type, table_id_src, table_id_dst)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def update_gen_config(
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
        return await self.table.update_gen_config(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def add_action_columns(self, request: AddActionColumnSchema) -> TableMetaResponse:
        """
        Add columns to an Action Table.

        Args:
            request (AddActionColumnSchema): The action column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self.table.add_action_columns(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def add_knowledge_columns(self, request: AddKnowledgeColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Knowledge Table.

        Args:
            request (AddKnowledgeColumnSchema): The knowledge column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self.table.add_knowledge_columns(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def add_chat_columns(self, request: AddChatColumnSchema) -> TableMetaResponse:
        """
        Add columns to a Chat Table.

        Args:
            request (AddChatColumnSchema): The chat column schema.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self.table.add_chat_columns(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def drop_columns(
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
        return await self.table.drop_columns(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def rename_columns(
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
        return await self.table.rename_columns(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def reorder_columns(
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
        return await self.table.reorder_columns(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def list_table_rows(
        self,
        table_type: str | TableType,
        table_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        search_query: str = "",
        columns: list[str] | None = None,
        float_decimals: int = 0,
        vec_decimals: int = 0,
        order_descending: bool = True,
    ) -> Page[dict[str, Any]]:
        """
        List rows in a table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): The ID of the table.
            offset (int, optional): Item offset. Defaults to 0.
            limit (int, optional): Number of rows to return (min 1, max 100). Defaults to 100.
            search_query (str, optional): A string to search for within the rows as a filter.
                Defaults to "" (no filter).
            columns (list[str] | None, optional): List of column names to include in the response.
                Defaults to None (all columns).
            float_decimals (int, optional): Number of decimals for float values.
                Defaults to 0 (no rounding).
            vec_decimals (int, optional): Number of decimals for vectors.
                If its negative, exclude vector columns. Defaults to 0 (no rounding).
            order_descending (bool, optional): Whether to sort by descending order. Defaults to True.
        """
        return await self.table.list_table_rows(
            table_type,
            table_id,
            offset=offset,
            limit=limit,
            search_query=search_query,
            columns=columns,
            float_decimals=float_decimals,
            vec_decimals=vec_decimals,
            order_descending=order_descending,
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def get_table_row(
        self,
        table_type: str | TableType,
        table_id: str,
        row_id: str,
        *,
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
        return await self.table.get_table_row(
            table_type,
            table_id,
            row_id,
            columns=columns,
            float_decimals=float_decimals,
            vec_decimals=vec_decimals,
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def add_table_rows(
        self,
        table_type: str | TableType,
        request: RowAddRequest,
    ) -> (
        GenTableRowsChatCompletionChunks
        | AsyncGenerator[GenTableStreamReferences | GenTableStreamChatCompletionChunk, None]
    ):
        """
        Add rows to a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowAddRequest): The row add request.

        Returns:
            response (GenTableRowsChatCompletionChunks | AsyncGenerator): The row completion.
                In streaming mode, it is an async generator that yields a `GenTableStreamReferences` object
                followed by zero or more `GenTableStreamChatCompletionChunk` objects.
                In non-streaming mode, it is a `GenTableRowsChatCompletionChunks` object.
        """
        return await self.table.add_table_rows(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def regen_table_rows(
        self,
        table_type: str | TableType,
        request: RowRegenRequest,
    ) -> (
        GenTableRowsChatCompletionChunks
        | AsyncGenerator[GenTableStreamReferences | GenTableStreamChatCompletionChunk, None]
    ):
        """
        Regenerate rows in a table.

        Args:
            table_type (str | TableType): The type of the table.
            request (RowRegenRequest): The row regenerate request.

        Returns:
            response (GenTableRowsChatCompletionChunks | AsyncGenerator): The row completion.
                In streaming mode, it is an async generator that yields a `GenTableStreamReferences` object
                followed by zero or more `GenTableStreamChatCompletionChunk` objects.
                In non-streaming mode, it is a `GenTableRowsChatCompletionChunks` object.
        """
        return await self.table.regen_table_rows(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def update_table_row(
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
        return await self.table.update_table_row(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def delete_table_rows(
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
        return await self.table.delete_table_rows(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def delete_table_row(
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
        return await self.table.delete_table_row(table_type, table_id, row_id)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def get_conversation_thread(
        self,
        table_type: str | TableType,
        table_id: str,
        column_id: str,
        row_id: str = "",
        include: bool = True,
    ) -> ChatThread:
        """
        Get the conversation thread for a chat table.

        Args:
            table_type (str | TableType): The type of the table.
            table_id (str): ID / name of the chat table.
            column_id (str): ID / name of the column to fetch.
            row_id (str, optional): ID / name of the last row in the thread.
                Defaults to "" (export all rows).
            include (bool, optional): Whether to include the row specified by `row_id`.
                Defaults to True.

        Returns:
            response (ChatThread): The conversation thread.
        """
        return await self.table.get_conversation_thread(
            table_type, table_id, column_id, row_id=row_id, include=include
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def hybrid_search(
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
        return await self.table.hybrid_search(table_type, request)

    @deprecated(
        "This method is deprecated, use `client.table.embed_file_options` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    async def upload_file_options(self) -> httpx.Response:
        """
        Get options for uploading a file to a Knowledge Table.

        Returns:
            response (httpx.Response): The response containing options information.
        """
        return await self.table.embed_file_options()

    @deprecated(
        "This method is deprecated, use `client.table.embed_file` instead.",
        category=FutureWarning,
        stacklevel=1,
    )
    async def upload_file(self, request: FileUploadRequest) -> OkResponse:
        """
        Upload a file to a Knowledge Table.

        Args:
            request (FileUploadRequest): The file upload request.

        Returns:
            response (OkResponse): The response indicating success.
        """
        return await self.table.embed_file(request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
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
        return await self.table.import_table_data(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def export_table_data(
        self,
        table_type: str | TableType,
        table_id: str,
        columns: list[str] | None = None,
        delimiter: Literal[",", "\t"] = ",",
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
        return await self.table.export_table_data(
            table_type, table_id, columns=columns, delimiter=delimiter
        )

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def import_table(
        self,
        table_type: str | TableType,
        request: TableImportRequest,
    ) -> TableMetaResponse:
        """
        Imports a table (data and schema) from a parquet file.

        Args:
            file_path (str): The parquet file path.
            table_type (str | TableType): Table type.
            request (TableImportRequest): Table import request.

        Returns:
            response (TableMetaResponse): The table metadata response.
        """
        return await self.table.import_table(table_type, request)

    @deprecated(TABLE_METHOD_DEPRECATE, category=FutureWarning, stacklevel=1)
    async def export_table(
        self,
        table_type: str | TableType,
        table_id: str,
    ) -> bytes:
        """
        Exports a table (data and schema) as a parquet file.

        Args:
            table_type (str | TableType): Table type.
            table_id (str): ID or name of the table to be exported.

        Returns:
            response (list[dict[str, Any]]): The search results.
        """
        return await self.table.export_table(table_type, table_id)
