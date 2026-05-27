"""MCP server — stdio transport, two tools."""
from __future__ import annotations

import asyncio
import difflib
import logging
import re
from typing import Any

import knowledge_gun
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from knowledge_gun_mcp import __version__

log = logging.getLogger(__name__)

server: Server = Server(name="knowledge-gun-mcp", version=__version__)

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
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "list_topics":
        topics = sorted(knowledge_gun.AVAILABLE_TOPICS)
        text = "\n".join(topics) if topics else "(no topics configured)"
        return [types.TextContent(type="text", text=text)]
    if name == "get_bundle":
        topic = (arguments or {}).get("topic", "").strip()
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
