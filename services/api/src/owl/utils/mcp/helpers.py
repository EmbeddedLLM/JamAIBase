from typing import TYPE_CHECKING, Callable

from owl.utils.mcp.server import MCPServer

if TYPE_CHECKING:
    from fastapi import FastAPI

_mcp_singleton: MCPServer | None = None


def _get_mcp_server(app: "FastAPI") -> MCPServer:
    global _mcp_singleton
    if _mcp_singleton is None:
        _mcp_singleton = MCPServer(app)
    return _mcp_singleton


def mcp_tool(fn: Callable[..., object]) -> Callable[..., object]:
    """
    Module-level decorator that forwards to MCPServer.tool
    Must be used *after* `get_mcp_router` has been called once.
    """
    if _mcp_singleton is None:
        raise RuntimeError(
            "MCP server not initialized yet. "
            "Make sure get_mcp_router(...) is called before decorating."
        )
    return _mcp_singleton.tool(fn)
