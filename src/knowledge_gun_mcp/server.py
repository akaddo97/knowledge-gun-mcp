"""MCP server — stdio transport, six tools."""
from __future__ import annotations

import asyncio
import difflib
import logging
import re
from collections import Counter
from typing import Any

import knowledge_gun
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from knowledge_gun_mcp import __version__

log = logging.getLogger(__name__)

server: Server = Server(
    name="knowledge-gun-mcp",
    version=__version__,
    instructions=(
        "Surfaces a curated knowledge graph as paste-ready context bundles. "
        "Call list_topics to discover the configured topic names, then call "
        "get_bundle(topic) to retrieve the markdown bundle for that topic. "
        "Use get_bundle whenever the user asks for context, briefing, or "
        "background; call list_topics first if the topic name is unknown."
    ),
)

# Strip absolute home-directory paths from any text leaving the server.
# macOS (/Users/<x>/) and Linux (/home/<x>/) only — Windows is a v0.2 TODO.
_HOME_PATH_RE = re.compile(r"(/Users/|/home/)[^/\s'\"`]+/")


def _sanitise_paths(text: str) -> str:
    """Redact host home-directory paths from text bound for the MCP client."""
    return _HOME_PATH_RE.sub(r"\1<redacted>/", text)


@server.list_tools()
async def _list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_topics",
            description=(
                "List all knowledge-gun bundle topics configured for the "
                "current graph. Returns a list of topic names like "
                "['career', 'tech', 'networking']. Call this before "
                "get_bundle if you don't know the topic name."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_bundle",
            description=(
                "Get the paste-ready knowledge-graph context bundle for a "
                "topic. Returns markdown — typically 1,500-4,000 words — "
                "containing a curated intro plus a 2-hop graph neighbourhood "
                "rendered as readable structure. Use this when the user "
                "asks for context, briefing, background, or 'tell me about "
                "<their X>'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic name. Use list_topics() to discover.",
                    },
                },
                "required": ["topic"],
            },
        ),
        types.Tool(
            name="search_nodes",
            description=(
                "Search the configured graph for nodes whose label or id "
                "contains the query (case-insensitive substring). Returns "
                "up to `limit` matches as a markdown table of (id, label, "
                "file_type). Use this when the user names someone or "
                "something and you want to confirm they're in the graph "
                "before drilling in with get_node or fetching a bundle."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Substring to match against node label or id.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max matches to return (1-50).",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_node",
            description=(
                "Get a single node's attributes and its 1-hop neighbourhood "
                "as markdown. Useful for follow-up questions after a bundle "
                "('tell me more about <node>'). Returns the node grouped "
                "with its immediate neighbours under file_type headers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Exact node id. Use search_nodes to discover.",
                    },
                },
                "required": ["node_id"],
            },
        ),
        types.Tool(
            name="get_topic_anchors",
            description=(
                "List the anchor node ids that seed the 2-hop walk for a "
                "topic. Returns each anchor on its own line. Use this when "
                "a bundle's scope surprises the user and you want to show "
                "*why* it scoped that way, or when you need raw ids to feed "
                "into get_node."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic name. Use list_topics() to discover.",
                    },
                },
                "required": ["topic"],
            },
        ),
        types.Tool(
            name="get_graph_summary",
            description=(
                "Return a one-shot orientation snapshot of the configured "
                "graph: total node count, total edge count, configured "
                "topic names, and per-file_type node counts. Use this as "
                "the first call after connecting to confirm the server is "
                "pointing at the graph you expect."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "list_topics":
        topics = sorted(knowledge_gun.AVAILABLE_TOPICS)
        text = "\n".join(topics) if topics else "(no topics configured)"
        return [types.TextContent(type="text", text=text)]
    if name == "get_bundle":
        raw = (arguments or {}).get("topic")
        if raw is None:
            return [types.TextContent(type="text", text="error: topic required")]
        if not isinstance(raw, str):
            return [types.TextContent(type="text", text="error: topic must be a string")]
        topic = raw.strip()
        if not topic:
            return [types.TextContent(type="text", text="error: topic required")]
        # Validate against AVAILABLE_TOPICS before dispatch — otherwise the
        # parent library's "topic not found" markdown leaks the host's
        # absolute filesystem path back to the MCP client.
        available = sorted(knowledge_gun.AVAILABLE_TOPICS)
        if topic not in available:
            close = difflib.get_close_matches(topic, available, n=1, cutoff=0.6)
            hint = f" Did you mean: {close[0]}?" if close else ""
            return [types.TextContent(
                type="text",
                text=f"error: unknown topic {topic!r}.{hint} Use list_topics to discover.",
            )]
        try:
            md = knowledge_gun.generate_bundle(topic)
        except Exception as exc:
            log.exception("get_bundle failed for %s", topic)
            msg = _sanitise_paths(f"{type(exc).__name__}: {exc}")
            return [types.TextContent(type="text", text=f"error: {msg}")]
        return [types.TextContent(type="text", text=md)]
    if name == "search_nodes":
        raw = (arguments or {}).get("query")
        if not isinstance(raw, str):
            return [types.TextContent(type="text", text="error: query required")]
        query = raw.strip()
        if not query:
            return [types.TextContent(type="text", text="error: query required")]
        limit_raw = (arguments or {}).get("limit", 10)
        if not isinstance(limit_raw, int) or isinstance(limit_raw, bool):
            return [types.TextContent(type="text", text="error: limit must be an integer")]
        limit = max(1, min(50, limit_raw))
        q = query.lower()
        try:
            graph = knowledge_gun._load_graph()
        except Exception as exc:
            log.exception("search_nodes failed loading graph")
            msg = _sanitise_paths(f"{type(exc).__name__}: {exc}")
            return [types.TextContent(type="text", text=f"error: {msg}")]
        matches: list[dict] = []
        for n in graph.get("nodes", []):
            label = str(n.get("label", ""))
            node_id = str(n.get("id", ""))
            if q in label.lower() or q in node_id.lower():
                matches.append(n)
                if len(matches) >= limit:
                    break
        if not matches:
            return [types.TextContent(type="text", text=f"(no matches for {query!r})")]
        matches.sort(key=lambda n: str(n.get("label", n.get("id", ""))).lower())
        lines = ["| id | label | file_type |", "|---|---|---|"]
        for n in matches:
            nid = str(n.get("id", "?"))
            label = str(n.get("label", "?"))
            ftype = str(n.get("file_type", "unknown"))
            lines.append(f"| `{nid}` | {label} | {ftype} |")
        return [types.TextContent(type="text", text="\n".join(lines))]
    if name == "get_node":
        raw = (arguments or {}).get("node_id")
        if not isinstance(raw, str):
            return [types.TextContent(type="text", text="error: node_id required")]
        node_id = raw.strip()
        if not node_id:
            return [types.TextContent(type="text", text="error: node_id required")]
        try:
            nb = knowledge_gun.graph_neighbourhood([node_id], depth=1)
        except Exception as exc:
            log.exception("get_node failed for %s", node_id)
            msg = _sanitise_paths(f"{type(exc).__name__}: {exc}")
            return [types.TextContent(type="text", text=f"error: {msg}")]
        if not nb.get("nodes"):
            return [types.TextContent(
                type="text",
                text=f"error: node {node_id!r} not found in graph",
            )]
        md = knowledge_gun.render_neighbourhood_md(nb)
        return [types.TextContent(type="text", text=_sanitise_paths(md))]
    if name == "get_topic_anchors":
        raw = (arguments or {}).get("topic")
        if not isinstance(raw, str):
            return [types.TextContent(type="text", text="error: topic required")]
        topic = raw.strip()
        if not topic:
            return [types.TextContent(type="text", text="error: topic required")]
        available = sorted(knowledge_gun.AVAILABLE_TOPICS)
        if topic not in available:
            close = difflib.get_close_matches(topic, available, n=1, cutoff=0.6)
            hint = f" Did you mean: {close[0]}?" if close else ""
            return [types.TextContent(
                type="text",
                text=f"error: unknown topic {topic!r}.{hint} Use list_topics to discover.",
            )]
        anchors = knowledge_gun.load_roots(topic)
        if not anchors:
            return [types.TextContent(
                type="text",
                text=f"(no anchors configured for {topic!r})",
            )]
        return [types.TextContent(type="text", text="\n".join(anchors))]
    if name == "get_graph_summary":
        try:
            graph = knowledge_gun._load_graph()
        except Exception as exc:
            log.exception("get_graph_summary failed loading graph")
            msg = _sanitise_paths(f"{type(exc).__name__}: {exc}")
            return [types.TextContent(type="text", text=f"error: {msg}")]
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", graph.get("links", []))
        types_count = Counter(
            str(n.get("file_type", "unknown")) for n in nodes
        )
        topics = sorted(knowledge_gun.AVAILABLE_TOPICS)
        lines = [
            f"- nodes: {len(nodes)}",
            f"- edges: {len(edges)}",
            f"- topics: {', '.join(topics) if topics else '(none configured)'}",
            "",
            "by file_type:",
        ]
        for ftype, count in types_count.most_common():
            lines.append(f"- {ftype}: {count}")
        return [types.TextContent(type="text", text="\n".join(lines))]
    return [types.TextContent(type="text", text=f"error: unknown tool {name!r}")]


async def _serve_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run() -> None:
    """Entry point for the ``knowledge-gun-mcp`` console script."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_serve_stdio())


if __name__ == "__main__":
    run()
