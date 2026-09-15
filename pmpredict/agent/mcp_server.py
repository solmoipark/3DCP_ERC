"""stdio MCP server exposing the tool registry (used by the Codex provider and any MCP client).

  python -m pmpredict.agent.mcp_server        (env PMPREDICT_SESSION selects the artifact directory)
stdout is the MCP channel: all logging goes to stderr. Written against the mcp 2.x low-level server API (explicit
request handlers, so the registry's JSON schemas are served verbatim).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys


def build_server():
    from mcp import types
    from mcp.server.lowlevel import Server

    from .tools import REGISTRY, call_tool  # noqa: F401  (registers tools)
    from .tools.registry import ToolContext, result_for_llm, to_mcp_tools
    from .tools.runtime import get_runtime

    session_id = os.environ.get("PMPREDICT_SESSION", "mcp")
    server = Server("pmpredict")

    async def list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=to_mcp_tools())

    async def call(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        rt = get_runtime()
        tctx = ToolContext(runtime=rt, session_id=session_id, artifact_dir=rt.session_artifact_dir(session_id))
        res = await asyncio.get_running_loop().run_in_executor(None, call_tool, params.name, params.arguments or {}, tctx)
        return types.CallToolResult(content=[types.TextContent(type="text", text=result_for_llm(res))], is_error=bool(res.is_error))

    server.add_request_handler("tools/list", types.PaginatedRequestParams, list_tools)
    server.add_request_handler("tools/call", types.CallToolRequestParams, call)
    return server


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s mcp %(levelname)s %(message)s")
    from mcp.server.stdio import stdio_server
    server = build_server()

    async def run():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
