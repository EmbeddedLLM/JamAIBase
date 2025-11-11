from owl.utils.mcp.helpers import mcp_tool


@mcp_tool
async def sum(a: int, b: int) -> int:
    return a + b
