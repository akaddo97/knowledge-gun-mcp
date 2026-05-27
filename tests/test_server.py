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
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["career"]):
        with patch.object(srv.knowledge_gun, "generate_bundle", return_value="# Career\n\n..."):
            out = await srv._call_tool("get_bundle", {"topic": "career"})
    assert out[0].type == "text"
    assert out[0].text.startswith("# Career")


async def test_get_bundle_strips_topic_whitespace():
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["career"]):
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
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["career"]):
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


# --- Privacy fix: topic validation + path sanitisation ---


async def test_get_bundle_unknown_topic_returns_error_without_dispatch():
    """Unknown topic must short-circuit before calling generate_bundle.
    The parent library's 'topic not found' markdown leaks the host filesystem
    path; validating first means generate_bundle is never reached on the
    unknown-topic path."""
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["career", "tech"]):
        with patch.object(srv.knowledge_gun, "generate_bundle") as gen:
            out = await srv._call_tool("get_bundle", {"topic": "nonexistent_xyz"})
    gen.assert_not_called()
    assert "unknown topic" in out[0].text
    assert "list_topics" in out[0].text


async def test_get_bundle_unknown_topic_suggests_close_match():
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["career", "tech"]):
        out = await srv._call_tool("get_bundle", {"topic": "carrer"})
    assert "Did you mean: career?" in out[0].text


async def test_get_bundle_unknown_topic_no_suggestion_when_no_close_match():
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["career", "tech"]):
        out = await srv._call_tool("get_bundle", {"topic": "zzzzzzz"})
    assert "Did you mean" not in out[0].text


async def test_get_bundle_unknown_topic_response_contains_no_host_path():
    """The HIGH-severity privacy regression guard. Any unknown topic must
    not surface /Users/ or /home/ filesystem paths back to the MCP client."""
    out = await srv._call_tool("get_bundle", {"topic": "nonexistent_xyz_for_path_leak_test"})
    assert "/Users/" not in out[0].text
    assert "/home/" not in out[0].text


async def test_sanitise_paths_redacts_users_directory():
    text = "FileNotFoundError: '/Users/alice/code/repo/file.md'"
    assert srv._sanitise_paths(text) == "FileNotFoundError: '/Users/<redacted>/code/repo/file.md'"


async def test_sanitise_paths_redacts_home_directory():
    text = "could not open /home/bob/notes.txt"
    assert srv._sanitise_paths(text) == "could not open /home/<redacted>/notes.txt"


async def test_sanitise_paths_leaves_other_text_untouched():
    text = "no paths here, just words"
    assert srv._sanitise_paths(text) == text


async def test_get_bundle_exception_text_path_sanitised():
    """If generate_bundle raises with a path-bearing message, the response
    must not leak the host path."""
    leaky = FileNotFoundError("'/Users/charlie/secrets/file.intro.md'")
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["career"]):
        with patch.object(srv.knowledge_gun, "generate_bundle", side_effect=leaky):
            out = await srv._call_tool("get_bundle", {"topic": "career"})
    assert "/Users/charlie/" not in out[0].text
    assert "<redacted>" in out[0].text
    assert "FileNotFoundError" in out[0].text
