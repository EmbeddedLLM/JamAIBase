from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import ORJSONResponse

from owl.types import UserAuth
from owl.utils.auth import auth_user_service_key
from owl.utils.exceptions import handle_exception
from owl.utils.mcp.helpers import _get_mcp_server
from owl.utils.mcp.server import MCP_TOOL_TAG  # noqa: F401

router = APIRouter()


def get_mcp_router(app: FastAPI) -> APIRouter:
    """Get the MCP router."""
    mcp_server = _get_mcp_server(app)
    import owl.utils.mcp.custom_tools  # noqa: F401

    @router.get("/v1/mcp/http", summary="MCP Streamable HTTP endpoint")
    @router.post("/v1/mcp/http", summary="MCP Streamable HTTP endpoint")
    @handle_exception
    async def mcp_streamable(
        request: Request,
        user: Annotated[UserAuth, Depends(auth_user_service_key)],
    ) -> ORJSONResponse:
        if request.method == "GET":
            return await mcp_server.get()
        return await mcp_server.post(
            user=user,
            body=await request.json(),
            headers=dict(request.headers),
        )

    return router
