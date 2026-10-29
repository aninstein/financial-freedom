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
        raise PermissionError("finfreedom MCP requires a trusted owner binding")
    return owner


@server.tool(description="List platform data sources and supported owner content changes.")
def catalog() -> dict:
    _owner()
    return platform_mcp.catalog()


@server.tool(description="Read a named finfreedom page data source for the authenticated owner.")
async def read(resource: str, params: dict | None = None) -> object:
    return await platform_mcp.read(_owner(), resource, params)


@server.tool(description="Change owner-authored finfreedom workspace content; requires an explicit user request.")
async def write(resource: str, action: str, data: dict) -> object:
    return await platform_mcp.write(_owner(), resource, action, data)


@server.tool(description="Prepare an owner-scoped holdings review draft from conversation text or an image; never save positions.")
async def prepare_holdings_import(currency: str = "CNY", text: str | None = None,
                                  image_id: str | None = None, session_id: str | None = None) -> object:
    return await platform_mcp.prepare_holdings_import(_owner(), currency, text, image_id, session_id)


@server.tool(description="Run a named finfreedom research tool using the authenticated owner's scope and tool-specific parameters.")
async def research(name: str, args: dict | None = None, session_id: str | None = None) -> object:
    return await platform_mcp.research(_owner(), name, args, session_id)


@server.tool(description="Install a user-requested Skill or private MCP configuration after trusted reauthentication.")
async def manage_extension(action: str, source: str | None = None, name: str | None = None,
                           private_input: str | None = None, current_message: str | None = None,
                           reauth_valid: bool = False) -> object:
    return await platform_mcp.manage_extension(_owner(), action, source, name, private_input,
                                               current_message, reauth_valid)


if __name__ == "__main__":
    # Futu's console logger writes to stdout by default. MCP stdio reserves
    # stdout for JSON-RPC, so keep broker diagnostics on stderr.
    try:
        from futu.common.ft_logger import FTLog
        FTLog().consoleHandler.setStream(sys.stderr)
    except ImportError:
        pass
    server.run(transport="stdio")
