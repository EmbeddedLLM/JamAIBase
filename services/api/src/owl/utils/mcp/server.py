import asyncio
import inspect
from collections import defaultdict
from functools import cached_property
from typing import Any, Callable, get_type_hints
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import ORJSONResponse
from loguru import logger
from pydantic import BaseModel, ValidationError, create_model

from jamaibase.types.db import RankedRole, UserAuth
from jamaibase.types.mcp import (
    CallToolRequest,
    CallToolResult,
    ErrorData,
    Implementation,
    InitializeResult,
    JSONRPCEmptyResponse,
    JSONRPCError,
    JSONRPCErrorCode,
    JSONRPCResponse,
    ListToolsResult,
    ServerCapabilities,
    TextContent,
    ToolAPI,
    ToolAPIInfo,
    ToolInputSchema,
)
from owl.client import JamaiASGIAsync
from owl.utils.auth import has_permissions
from owl.utils.exceptions import (
    BadInputError,
    ForbiddenError,
    JamaiException,
    MethodNotAllowedError,
    ResourceNotFoundError,
)
from owl.utils.handlers import INTERNAL_ERROR_MESSAGE

MCP_TOOL_TAG = "mcp_tool"


class MCPServer:
    _custom_tools: list[ToolAPI] = []
    _custom_callables: dict[str, Callable[..., Any]] = {}
    _custom_models: dict[str, BaseModel] = {}

    def __init__(
        self,
        app: FastAPI,
        *,
        include_headers_in_input: bool = False,
    ):
        self.app = app
        self.include_headers_in_input = include_headers_in_input
        self.openapi_schema = get_openapi(
            title=self.app.title,
            version=self.app.version,
            description=self.app.description,
            routes=self.app.routes,
        )
        self.init_result = InitializeResult(
            capabilities=ServerCapabilities(),
            serverInfo=Implementation(
                name=self.app.title,
                version=self.app.version,
            ),
        )
        self.client = JamaiASGIAsync(app=self.app)
        _ = self.tools

    def tool(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """
        Decorator that turns any sync/async function into an MCP tool.
        Arguments are validated through a dynamically created Pydantic model.
        """
        sig = inspect.signature(fn)
        type_hints = get_type_hints(fn)

        # Build Pydantic model from signature
        fields = {}
        required = []
        for name, param in sig.parameters.items():
            annotation = type_hints.get(name, Any)
            default = ... if param.default is inspect.Parameter.empty else param.default
            fields[name] = (annotation, default)
            if param.default is inspect.Parameter.empty:
                required.append(name)

        Model = create_model(f"{fn.__name__}Schema", **fields)

        # Register
        tool = ToolAPI(
            name=fn.__name__,
            description=fn.__doc__ or "",
            inputSchema=ToolInputSchema(
                properties=Model.model_json_schema()["properties"],
                required=required,
            ),
            api_info=None,
        )

        self._custom_tools.append(tool)
        self._custom_callables[fn.__name__] = fn
        self._custom_models[fn.__name__] = Model
        return fn

    @cached_property
    def tools(self) -> list[ToolAPI]:
        tools = []
        operation_ids = set()  # Track operation IDs to detect duplicates

        # dump_json(openapi_schema, "openapi_schema.json")
        paths: dict[str, Any] = self.openapi_schema.get("paths", {})
        if len(paths) == 0:
            logger.warning("Failed to extract paths from OpenAPI schema.")
        schemas: dict[str, Any] = self.openapi_schema.get("components", {}).get("schemas", {})
        if len(schemas) == 0:
            logger.warning("Failed to extract schemas from OpenAPI schema.")
        # Extract tools
        for path, methods in paths.items():
            args_types: dict[str, str] = {}
            for method, method_info in methods.items():
                tags = method_info.get("tags", [])
                if MCP_TOOL_TAG not in tags:
                    continue

                # Check for duplicate operation IDs
                operation_id = method_info.get("operationId", method_info.get("summary", ""))
                assert operation_id not in operation_ids, (
                    f"Duplicate operation ID found: '{operation_id}' in {method.upper()} {path}"
                )
                operation_ids.add(operation_id)

                schema = {
                    "title": operation_id,
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
                # Process path and query parameters (optional headers)
                parameters: dict[str, Any] = method_info.get("parameters", {})
                for param in parameters:
                    if param["in"] == "header" and not self.include_headers_in_input:
                        continue
                    param_name = param["name"]
                    schema["properties"][param_name] = param["schema"]
                    # self._add_schema_to_properties(
                    #     properties=schema["properties"],
                    #     schema=param["schema"],
                    #     name=param_name,
                    # )
                    if param.get("required", False):
                        schema["required"].append(param_name)
                    args_types[param_name] = param["in"]
                # Process body
                body_schema_ref: str = (
                    method_info.get("requestBody", {})
                    .get("content", {})
                    .get("application/json", {})
                    .get("schema", {})
                    .get("$ref", "")
                )
                body = schemas.get(body_schema_ref.replace("#/components/schemas/", ""), {})
                for param_name, param_schema in body.get("properties", {}).items():
                    # Maybe need to resolve reference
                    if "$ref" in param_schema:
                        param_schema = schemas.get(
                            body_schema_ref.replace("#/components/schemas/", ""), {}
                        )
                    schema["properties"][param_name] = param_schema
                    # self._add_schema_to_properties(
                    #     properties=schema["properties"],
                    #     schema=param_schema,
                    #     name=param_name,
                    # )
                    args_types[param_name] = "body"
                schema["required"] += body.get("required", [])
                # Create the tool definition
                summary = method_info.get("summary", schema.get("title", "")).strip()
                if not summary.endswith("."):
                    summary += "."
                description = method_info.get("description", None)
                description = summary if description is None else f"{summary}\n{description}"
                if method_info.get("deprecated", False):
                    description += " (Deprecated)"
                tool = ToolAPI(
                    name=schema["title"],
                    description=description,
                    inputSchema=ToolInputSchema(
                        properties=schema["properties"],
                        required=schema["required"],
                    ),
                    api_info=ToolAPIInfo(
                        path=path,
                        method=method,
                        args_types=args_types,
                        method_info=method_info,
                    ),
                )
                # logger.info(f"{tool=}")
                tools.append(tool)
        return tools

    @cached_property
    def tools_map(self) -> dict[str, ToolAPI]:
        return {tool.name: tool for tool in self.tools}

    @cached_property
    def permission_tool_map(self) -> dict[frozenset[str], list[ToolAPI]]:
        # {frozenset(["system.models", "organization.models"]): [ToolAPI(name="list_models", ...)]}
        tool_map = defaultdict(list)
        for t in self.tools:
            permissions = [
                permission
                for permission in t.api_info.method_info["tags"]
                if permission.startswith(("system", "organization", "project"))
            ]
            key = frozenset(permissions)
            tool_map[key].append(t)
        return tool_map

    def list_tools(
        self,
        *,
        user: UserAuth,
    ) -> ListToolsResult:
        has_sys_membership = has_permissions(user, ["system"], raise_error=False)
        has_org_membership = len(user.org_memberships) > 0
        has_proj_membership = len(user.proj_memberships) > 0

        org_permission = (
            max([r.role.rank for r in user.org_memberships])
            if has_org_membership
            else RankedRole.GUEST
        )  # Guest has basically no permissions
        proj_permission = (
            max([r.role.rank for r in user.proj_memberships])
            if has_proj_membership
            else RankedRole.GUEST
        )  # Guest has basically no permissions
        tool_list: list[ToolAPI] = []
        for permissions, tools in self.permission_tool_map.items():
            if has_sys_membership and "system" in permissions:
                tool_list.extend(tools)
            elif has_org_membership and "organization" in permissions:
                tool_list.extend(tools)
            elif has_proj_membership and "project" in permissions:
                tool_list.extend(tools)
            else:
                for permission in permissions:
                    if (
                        permission.startswith(("system.", "organization."))
                        and RankedRole[permission.split(".")[1]] <= org_permission
                    ):
                        tool_list.extend(tools)
                        break
                    elif (
                        permission.startswith("project.")
                        and RankedRole[permission.split(".")[1]] <= proj_permission
                    ):
                        tool_list.extend(tools)
                        break
        # include all custom tools
        tool_list.extend(self._custom_tools)
        return ListToolsResult(tools=tool_list)

    async def call_tool(
        self,
        body: CallToolRequest,
        *,
        headers: dict[str, Any] | None = None,
    ) -> CallToolResult:
        # Call custom tools
        if body.params.name in self._custom_models:
            return await self._call_custom_tool(
                tool_name=body.params.name,
                tool_args=body.params.arguments,
                headers=headers,
            )
        tool = self.tools_map.get(body.params.name, None)
        if tool is None:
            raise ResourceNotFoundError(f'Tool "{body.params.name}" is not found.')
        # Call the tool
        path = tool.api_info.path
        args_types = tool.api_info.args_types
        args = body.params.arguments
        # Process parameters
        query_params = None
        body_params = None
        if args is not None:
            if headers is None:
                headers = {}
            query_params = {}
            body_params = {}
            for arg_name, arg_value in args.items():
                args_type = args_types.get(arg_name, "")
                # Path parameters
                if args_type == "path" and f"{{{arg_name}}}" in path:
                    path = path.replace(f"{{{arg_name}}}", quote(arg_value))
                # Headers
                elif args_type == "header":
                    headers[arg_name] = arg_value
                # Query parameters
                elif args_type == "query":
                    query_params[arg_name] = arg_value
                # Body parameters
                elif args_type == "body":
                    body_params[arg_name] = arg_value
            if len(headers) == 0:
                headers = None
            if len(query_params) == 0:
                query_params = None
            if len(body_params) == 0:
                body_params = None
            if body.params.name == "chat_completion" and len(body_params) != 0:
                body_params["stream"] = False

        response = await self.client.request(
            tool.api_info.method,
            path,
            headers=headers,
            params=query_params,
            body=body_params,
        )
        return CallToolResult(content=[TextContent(text=response.text)])

    async def _call_custom_tool(
        self,
        tool_name: str,
        *,
        tool_args: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
    ) -> CallToolResult:
        Model = self._custom_models[tool_name]
        fn = self._custom_callables[tool_name]

        try:
            validated = Model.model_validate(tool_args)
        except ValidationError as e:
            raise BadInputError(errors=e.errors()) from e

        kwargs = validated.model_dump()
        if asyncio.iscoroutinefunction(fn):
            out = await fn(**kwargs)
        else:
            out = fn(**kwargs)
        return CallToolResult(content=[TextContent(text=str(out))])

    async def _handle_request(
        self,
        user: UserAuth,
        body: dict[str, Any],
        *,
        headers: dict[str, Any] | None = None,
    ) -> JSONRPCResponse | JSONRPCEmptyResponse | JSONRPCError | None:
        request_id = body.get("id", "")
        method = body.get("method", "")
        try:
            if method.startswith("notifications/"):
                return None
            elif method == "ping":
                response = JSONRPCEmptyResponse(
                    id=request_id,
                )
            elif method == "initialize":
                response = JSONRPCResponse[InitializeResult](
                    id=request_id,
                    result=self.init_result,
                )
            elif method == "tools/list":
                response = JSONRPCResponse[ListToolsResult](
                    id=request_id,
                    result=self.list_tools(user=user),
                )
            elif method == "tools/call":
                body = CallToolRequest.model_validate(body)
                response = JSONRPCResponse[CallToolResult](
                    id=request_id,
                    result=await self.call_tool(body, headers=headers),
                )
            else:
                response = JSONRPCError(
                    id=request_id,
                    error=ErrorData(
                        code=JSONRPCErrorCode.METHOD_NOT_FOUND,
                        message=f'Method "{method}" is not supported.',
                        data=None,
                    ),
                )
        except BadInputError as e:
            response = JSONRPCError(
                id=request_id,
                error=ErrorData(
                    code=JSONRPCErrorCode.INVALID_PARAMS,
                    message=str(e),
                    data=None,
                ),
            )
        except ForbiddenError as e:
            response = JSONRPCError(
                id=request_id,
                error=ErrorData(
                    code=JSONRPCErrorCode.FORBIDDEN,
                    message=str(e),
                    data=None,
                ),
            )
        except JamaiException as e:
            response = JSONRPCError(
                id=request_id,
                error=ErrorData(
                    code=JSONRPCErrorCode.INVALID_REQUEST,
                    message=str(e),
                    data=None,
                ),
            )
        except ValidationError as e:
            logger.error(f"Failed to parse JSON-RPC body: {repr(e)}")
            response = JSONRPCError(
                id=request_id,
                error=ErrorData(
                    code=JSONRPCErrorCode.PARSE_ERROR,
                    message=str(e),
                    data=None,
                ),
            )
        except Exception as e:
            logger.exception(f"Unexpected error: {repr(e)}")
            response = JSONRPCError(
                id=request_id,
                error=ErrorData(
                    code=JSONRPCErrorCode.INTERNAL_ERROR,
                    message=INTERNAL_ERROR_MESSAGE,
                    data=None,
                ),
            )
        return response

    async def get(self):
        """Return 405 for GET requests to /mcp"""
        raise MethodNotAllowedError("SSE is not supported.")

    async def post(
        self,
        user: UserAuth,
        body: dict[str, Any] | list[dict[str, Any]],
        *,
        headers: dict[str, Any] | None = None,
    ) -> ORJSONResponse:
        logger.debug("MCP request: {body}", body=body)
        if isinstance(body, list):
            response = [
                await self._handle_request(user=user, body=req, headers=headers) for req in body
            ]
            if any(r is None for r in response):
                return ORJSONResponse(
                    status_code=202,
                    content={},
                    media_type="application/json",
                )
            else:
                return ORJSONResponse(
                    status_code=200,
                    content=[
                        r.model_dump(mode="json", by_alias=True, exclude_none=True)
                        for r in response
                    ],
                    media_type="application/json",
                )
        else:
            response = await self._handle_request(user=user, body=body, headers=headers)
            if response is None:
                return ORJSONResponse(status_code=202, content={})
            else:
                return ORJSONResponse(
                    status_code=200,
                    content=response.model_dump(mode="json", by_alias=True, exclude_none=True),
                    media_type="application/json",
                )
