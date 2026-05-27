"""End-to-end integration test exercising the MCP stdio JSON-RPC wire.

The unit tests in ``test_server.py`` mock at the ``knowledge_gun`` boundary
and verify dispatch shape; they do not verify that the server speaks the MCP
protocol correctly over stdio. This file spawns the server as a subprocess
(``python -m knowledge_gun_mcp``) and drives it through a real
``ClientSession`` — the same code path Claude Desktop / Cursor / Claude
Code use.

Covers: initialize handshake, tools/list discovery, tools/call(list_topics)
round-trip against the bundled demo graph (4 topics: industry, projects,
studio, team).
"""
from __future__ import annotations

import sys

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


pytestmark = pytest.mark.asyncio


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "knowledge_gun_mcp"],
    )


async def test_initialize_handshake_advertises_server_metadata():
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
    assert init.serverInfo.name == "knowledge-gun-mcp"
    assert init.serverInfo.version == "0.1.0"
    # Tools capability must be advertised — the server registers tool handlers.
    assert init.capabilities.tools is not None
    # Instructions field carries the host-LLM guidance string.
    assert init.instructions is not None
    assert "list_topics" in init.instructions


async def test_tools_list_includes_core_tools():
    """Regression guard for the two core tools. Tolerant of additions so it
    keeps passing when sub 8 / future iterations expand the surface."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
    names = {t.name for t in result.tools}
    assert {"get_bundle", "list_topics"}.issubset(names)


async def test_call_list_topics_returns_demo_topics():
    """Against the bundled demo graph (no env vars set), list_topics should
    return the four indie-game-studio topics."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("list_topics", {})
    assert len(result.content) == 1
    text = result.content[0].text
    topics = text.split("\n")
    assert set(topics) == {"industry", "projects", "studio", "team"}


async def test_call_get_bundle_unknown_topic_returns_no_host_path():
    """End-to-end privacy regression guard: an unknown topic over the real
    stdio wire must not leak /Users/ or /home/ paths back to the client."""
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_bundle", {"topic": "definitely_not_a_real_topic_xyz"}
            )
    text = result.content[0].text
    assert "/Users/" not in text
    assert "/home/" not in text
    assert "unknown topic" in text
