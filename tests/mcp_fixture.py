from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server = FastMCP('research-fixture')


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def lookup(symbol: str) -> str:
    """Return a deterministic public fixture."""
    return f'{symbol}: fixture'


if __name__ == '__main__':
    server.run(transport='stdio')
