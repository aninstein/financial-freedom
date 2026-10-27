"""stdio MCP server. The web/worker process supplies the authenticated owner."""
from __future__ import annotations

import os
import sys

from mcp.server.fastmcp import FastMCP

from app import platform_mcp

server = FastMCP("finch-platform")


def _owner() -> str:
    owner = os.getenv("FINCH_MCP_OWNER_ID", "")
    if not owner or len(owner) > 64:
        raise PermissionError("Finch MCP requires a trusted owner binding")
    return owner


@server.tool(description="List platform data sources and supported owner content changes.")
def catalog() -> dict:
    _owner()
    return platform_mcp.catalog()


@server.tool(description="Read a named Finch page data source for the authenticated owner.")
async def read(resource: str, params: dict | None = None) -> object:
    return await platform_mcp.read(_owner(), resource, params)


@server.tool(description="Change owner-authored Finch workspace content; requires an explicit user request.")
async def write(resource: str, action: str, data: dict) -> object:
    return await platform_mcp.write(_owner(), resource, action, data)


if __name__ == "__main__":
    # Futu's console logger writes to stdout by default. MCP stdio reserves
    # stdout for JSON-RPC, so keep broker diagnostics on stderr.
    try:
        from futu.common.ft_logger import FTLog
        FTLog().consoleHandler.setStream(sys.stderr)
    except ImportError:
        pass
    server.run(transport="stdio")
