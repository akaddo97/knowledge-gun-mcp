"""Tests for the MCP server's tool listing + dispatch.

Mocks at the ``knowledge_gun.generate_bundle`` and
``knowledge_gun.AVAILABLE_TOPICS`` boundary — verifies the server's
tool-shape contracts and call-tool dispatch without spinning up real
stdio JSON-RPC.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

import knowledge_gun_mcp.server as srv


pytestmark = pytest.mark.asyncio


async def test_list_tools_shape():
    tools = await srv._list_tools()
    names = [t.name for t in tools]
    assert "list_topics" in names
    assert "get_bundle" in names
    assert len(tools) == 2
    for t in tools:
        assert t.inputSchema["type"] == "object"
        assert "properties" in t.inputSchema
        assert isinstance(t.inputSchema.get("required", []), list)
        assert t.description and len(t.description) > 20


async def test_get_bundle_schema_requires_topic():
    tools = await srv._list_tools()
    by_name = {t.name: t for t in tools}
    assert by_name["get_bundle"].inputSchema["required"] == ["topic"]
    assert by_name["list_topics"].inputSchema["required"] == []


async def test_list_topics_returns_available():
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["career", "tech"]):
        out = await srv._call_tool("list_topics", {})
    assert out[0].type == "text"
    assert out[0].text == "career\ntech"


async def test_list_topics_sorts_topics():
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["zebra", "alpha", "mike"]):
        out = await srv._call_tool("list_topics", {})
    assert out[0].text == "alpha\nmike\nzebra"


async def test_list_topics_empty():
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", []):
        out = await srv._call_tool("list_topics", {})
    assert "(no topics configured)" in out[0].text


async def test_get_bundle_dispatches():
    with patch.object(srv.knowledge_gun, "generate_bundle", return_value="# Career\n\n..."):
        out = await srv._call_tool("get_bundle", {"topic": "career"})
    assert out[0].type == "text"
    assert out[0].text.startswith("# Career")


async def test_get_bundle_strips_topic_whitespace():
    with patch.object(srv.knowledge_gun, "generate_bundle", return_value="# T\n") as m:
        out = await srv._call_tool("get_bundle", {"topic": "  career  "})
    m.assert_called_once_with("career")
    assert out[0].text == "# T\n"


async def test_get_bundle_missing_topic_arg():
    out = await srv._call_tool("get_bundle", {})
    assert "topic required" in out[0].text


async def test_get_bundle_empty_topic_arg():
    out = await srv._call_tool("get_bundle", {"topic": ""})
    assert "topic required" in out[0].text


async def test_get_bundle_swallows_exceptions_into_text():
    with patch.object(srv.knowledge_gun, "generate_bundle", side_effect=ValueError("boom")):
        out = await srv._call_tool("get_bundle", {"topic": "career"})
    assert "ValueError" in out[0].text
    assert "boom" in out[0].text


async def test_get_bundle_handles_none_arguments():
    out = await srv._call_tool("get_bundle", None)  # type: ignore[arg-type]
    assert "topic required" in out[0].text


async def test_unknown_tool_returns_error_text():
    out = await srv._call_tool("nonexistent", {})
    assert "unknown tool" in out[0].text
    assert "nonexistent" in out[0].text


async def test_server_metadata_set():
    assert srv.server.name == "knowledge-gun-mcp"
    assert srv.server.version == "0.1.0"
