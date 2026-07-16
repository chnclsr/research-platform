from __future__ import annotations

import asyncio
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def read_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    environment = read_environment(root / ".env.office")
    url = f"http://{environment['MCP_HOST']}:{environment['MCP_PORT']}/mcp"
    headers = {"Authorization": f"Bearer {environment['MCP_BEARER_TOKEN']}"}
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            server = await session.initialize()
            tools = await session.list_tools()
            print(
                {
                    "server": server.serverInfo.name,
                    "version": server.serverInfo.version,
                    "tool_count": len(tools.tools),
                    "tools": [tool.name for tool in tools.tools],
                }
            )


if __name__ == "__main__":
    asyncio.run(main())
