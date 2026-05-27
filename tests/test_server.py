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
    assert "search_nodes" in names
    assert "get_node" in names
    assert "get_topic_anchors" in names
    assert "get_graph_summary" in names
    assert len(tools) == 6
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


# --- Robustness: type validation on topic argument ---


async def test_get_bundle_rejects_non_string_topic():
    """A client violating the JSON-schema (topic as int) must surface as a
    clean error, not an unhandled AttributeError from .strip()."""
    out = await srv._call_tool("get_bundle", {"topic": 123})
    assert "topic must be a string" in out[0].text


# --- MCP polish: instructions field in init options ---


async def test_server_advertises_instructions():
    opts = srv.server.create_initialization_options()
    assert opts.instructions is not None
    assert "list_topics" in opts.instructions
    assert "get_bundle" in opts.instructions


# --- search_nodes ---


_FAKE_GRAPH = {
    "nodes": [
        {"id": "person_alice", "label": "Alice Walker", "file_type": "person"},
        {"id": "person_bob", "label": "Bob Schmidt", "file_type": "person"},
        {"id": "company_acme", "label": "Acme Corp", "file_type": "company"},
        {"id": "project_paper", "label": "Paper Lanterns", "file_type": "project"},
        {"id": "skill_godot", "label": "Godot Engine", "file_type": "skill"},
    ],
    "edges": [
        {"source": "person_alice", "target": "company_acme", "relation": "works_at"},
        {"source": "person_alice", "target": "project_paper", "relation": "leads"},
    ],
}


async def test_search_nodes_schema_requires_query():
    tools = await srv._list_tools()
    by_name = {t.name: t for t in tools}
    assert by_name["search_nodes"].inputSchema["required"] == ["query"]


async def test_search_nodes_substring_match_on_label():
    with patch.object(srv.knowledge_gun, "_load_graph", return_value=_FAKE_GRAPH):
        out = await srv._call_tool("search_nodes", {"query": "alice"})
    assert "person_alice" in out[0].text
    assert "Alice Walker" in out[0].text


async def test_search_nodes_case_insensitive():
    with patch.object(srv.knowledge_gun, "_load_graph", return_value=_FAKE_GRAPH):
        out = await srv._call_tool("search_nodes", {"query": "ACME"})
    assert "company_acme" in out[0].text


async def test_search_nodes_matches_on_id_too():
    with patch.object(srv.knowledge_gun, "_load_graph", return_value=_FAKE_GRAPH):
        out = await srv._call_tool("search_nodes", {"query": "skill_"})
    assert "Godot Engine" in out[0].text


async def test_search_nodes_respects_limit():
    with patch.object(srv.knowledge_gun, "_load_graph", return_value=_FAKE_GRAPH):
        out = await srv._call_tool("search_nodes", {"query": "person_", "limit": 1})
    text = out[0].text
    # 2 header rows + 1 data row = 3 lines
    assert len(text.strip().split("\n")) == 3


async def test_search_nodes_returns_markdown_table():
    with patch.object(srv.knowledge_gun, "_load_graph", return_value=_FAKE_GRAPH):
        out = await srv._call_tool("search_nodes", {"query": "alice"})
    assert "| id | label | file_type |" in out[0].text
    assert "|---|---|---|" in out[0].text


async def test_search_nodes_no_matches_returns_placeholder():
    with patch.object(srv.knowledge_gun, "_load_graph", return_value=_FAKE_GRAPH):
        out = await srv._call_tool("search_nodes", {"query": "xyzzz_no_such_node"})
    assert "no matches" in out[0].text


async def test_search_nodes_rejects_missing_query():
    out = await srv._call_tool("search_nodes", {})
    assert "query required" in out[0].text


async def test_search_nodes_rejects_empty_query():
    out = await srv._call_tool("search_nodes", {"query": "   "})
    assert "query required" in out[0].text


async def test_search_nodes_rejects_non_string_query():
    out = await srv._call_tool("search_nodes", {"query": 42})
    assert "query required" in out[0].text


async def test_search_nodes_clamps_limit_to_max():
    """Limit > 50 must be clamped, not crash."""
    with patch.object(srv.knowledge_gun, "_load_graph", return_value=_FAKE_GRAPH):
        out = await srv._call_tool("search_nodes", {"query": "person_", "limit": 999})
    assert "person_alice" in out[0].text


# --- get_node ---


async def test_get_node_schema_requires_node_id():
    tools = await srv._list_tools()
    by_name = {t.name: t for t in tools}
    assert by_name["get_node"].inputSchema["required"] == ["node_id"]


async def test_get_node_returns_rendered_neighbourhood():
    fake_nb = {
        "nodes": [{"id": "person_alice", "label": "Alice", "file_type": "person"}],
        "edges": [],
    }
    with patch.object(srv.knowledge_gun, "graph_neighbourhood", return_value=fake_nb):
        with patch.object(srv.knowledge_gun, "render_neighbourhood_md", return_value="# rendered\n"):
            out = await srv._call_tool("get_node", {"node_id": "person_alice"})
    assert out[0].text.startswith("# rendered")


async def test_get_node_not_found_returns_error():
    empty_nb = {"nodes": [], "edges": []}
    with patch.object(srv.knowledge_gun, "graph_neighbourhood", return_value=empty_nb):
        out = await srv._call_tool("get_node", {"node_id": "person_ghost"})
    assert "not found" in out[0].text
    assert "person_ghost" in out[0].text


async def test_get_node_missing_id_returns_error():
    out = await srv._call_tool("get_node", {})
    assert "node_id required" in out[0].text


async def test_get_node_empty_id_returns_error():
    out = await srv._call_tool("get_node", {"node_id": ""})
    assert "node_id required" in out[0].text


async def test_get_node_strips_whitespace():
    fake_nb = {
        "nodes": [{"id": "person_alice", "label": "Alice", "file_type": "person"}],
        "edges": [],
    }
    with patch.object(srv.knowledge_gun, "graph_neighbourhood", return_value=fake_nb) as gn:
        with patch.object(srv.knowledge_gun, "render_neighbourhood_md", return_value="x"):
            await srv._call_tool("get_node", {"node_id": "  person_alice  "})
    gn.assert_called_once()
    assert gn.call_args.args[0] == ["person_alice"]


async def test_get_node_sanitises_paths_in_output():
    """Any path-bearing string in render output must be redacted before
    leaving the server."""
    fake_nb = {"nodes": [{"id": "x"}], "edges": []}
    leaky_md = "node loaded from /Users/dave/graph.json"
    with patch.object(srv.knowledge_gun, "graph_neighbourhood", return_value=fake_nb):
        with patch.object(srv.knowledge_gun, "render_neighbourhood_md", return_value=leaky_md):
            out = await srv._call_tool("get_node", {"node_id": "x"})
    assert "/Users/dave/" not in out[0].text
    assert "<redacted>" in out[0].text


# --- get_topic_anchors ---


async def test_get_topic_anchors_schema_requires_topic():
    tools = await srv._list_tools()
    by_name = {t.name: t for t in tools}
    assert by_name["get_topic_anchors"].inputSchema["required"] == ["topic"]


async def test_get_topic_anchors_returns_anchor_ids():
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["studio"]):
        with patch.object(srv.knowledge_gun, "load_roots", return_value=["person_alice", "project_paper"]):
            out = await srv._call_tool("get_topic_anchors", {"topic": "studio"})
    assert out[0].text == "person_alice\nproject_paper"


async def test_get_topic_anchors_unknown_topic_short_circuits():
    """Same privacy posture as get_bundle — never call load_roots on an
    unknown topic (the parent library could leak filesystem paths in
    error paths)."""
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["studio"]):
        with patch.object(srv.knowledge_gun, "load_roots") as lr:
            out = await srv._call_tool("get_topic_anchors", {"topic": "nonexistent"})
    lr.assert_not_called()
    assert "unknown topic" in out[0].text


async def test_get_topic_anchors_suggests_close_match():
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["studio", "team"]):
        out = await srv._call_tool("get_topic_anchors", {"topic": "stdio"})
    assert "Did you mean: studio?" in out[0].text


async def test_get_topic_anchors_missing_topic_returns_error():
    out = await srv._call_tool("get_topic_anchors", {})
    assert "topic required" in out[0].text


async def test_get_topic_anchors_empty_anchors_returns_placeholder():
    with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["studio"]):
        with patch.object(srv.knowledge_gun, "load_roots", return_value=[]):
            out = await srv._call_tool("get_topic_anchors", {"topic": "studio"})
    assert "no anchors configured" in out[0].text


# --- get_graph_summary ---


async def test_get_graph_summary_schema_takes_no_args():
    tools = await srv._list_tools()
    by_name = {t.name: t for t in tools}
    assert by_name["get_graph_summary"].inputSchema["required"] == []
    assert by_name["get_graph_summary"].inputSchema["properties"] == {}


async def test_get_graph_summary_returns_counts():
    with patch.object(srv.knowledge_gun, "_load_graph", return_value=_FAKE_GRAPH):
        with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", ["studio", "team"]):
            out = await srv._call_tool("get_graph_summary", {})
    text = out[0].text
    assert "nodes: 5" in text
    assert "edges: 2" in text
    assert "topics: studio, team" in text


async def test_get_graph_summary_groups_by_file_type():
    with patch.object(srv.knowledge_gun, "_load_graph", return_value=_FAKE_GRAPH):
        with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", []):
            out = await srv._call_tool("get_graph_summary", {})
    text = out[0].text
    assert "person: 2" in text
    assert "company: 1" in text
    assert "project: 1" in text
    assert "skill: 1" in text


async def test_get_graph_summary_handles_empty_graph():
    with patch.object(srv.knowledge_gun, "_load_graph", return_value={"nodes": [], "edges": []}):
        with patch.object(srv.knowledge_gun, "AVAILABLE_TOPICS", []):
            out = await srv._call_tool("get_graph_summary", {})
    text = out[0].text
    assert "nodes: 0" in text
    assert "edges: 0" in text
    assert "(none configured)" in text
