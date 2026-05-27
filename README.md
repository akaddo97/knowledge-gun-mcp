# Knowledge Gun MCP

[![tests](https://github.com/akaddo97/knowledge-gun-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/akaddo97/knowledge-gun-mcp/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

MCP server wrapping [`knowledge-gun`](https://github.com/akaddo97/knowledge-gun). Exposes paste-ready knowledge-graph context bundles as tools any MCP-aware LLM client can call. Stdio transport, two tools, ~150 lines.

## What this is

`knowledge-gun` is a Python library and CLI that turns a curated knowledge graph into a single markdown context bundle for the opening turn of a fresh chat. The friction today: terminal → `knowledge-gun --topic career` → copy → paste into your chat client.

This wrapper closes the loop. Drop it into your Claude Desktop, Claude Code, Cursor, VS Code, or any other MCP-aware client config, and your bundles become callable from chat — no terminal, no copy, no paste.

```
your chat ── MCP stdio ──▶ knowledge-gun-mcp ──▶ knowledge-gun ──▶ your graph + intros
```

## Install

```bash
uv pip install git+https://github.com/akaddo97/knowledge-gun-mcp
```

Requires Python 3.11+. **macOS users** — if your `python3` on PATH is Homebrew Python 3.13 or 3.14, you may hit a `platform.mac_ver()` returned empty value error from `uv` or pip. The fix is to use Python 3.12 explicitly:

```bash
uv venv --python /opt/homebrew/opt/python@3.12/bin/python3.12 .venv
source .venv/bin/activate
uv pip install git+https://github.com/akaddo97/knowledge-gun-mcp
```

This installs the `knowledge-gun-mcp` console script and pulls `knowledge-gun` as a dependency.

## Register with your client

Each MCP-aware client has its own config file but uses near-identical schema. Drop the snippet under your client's `mcpServers` key.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the equivalent path on your platform:

```json
{
  "mcpServers": {
    "knowledge-gun": {
      "command": "knowledge-gun-mcp",
      "env": {
        "KNOWLEDGE_GUN_GRAPH_PATH": "/Users/<you>/path/to/your/graph.json",
        "KNOWLEDGE_GUN_INTRO_DIR": "/Users/<you>/path/to/intros/",
        "KNOWLEDGE_GUN_ROOTS_DIR": "/Users/<you>/path/to/roots/"
      }
    }
  }
}
```

Restart Claude Desktop. The tools `list_topics` and `get_bundle` will appear under the MCP indicator in the chat input.

### Cursor

Edit `.cursor/mcp.json` (per-project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "knowledge-gun": {
      "command": "knowledge-gun-mcp",
      "env": {
        "KNOWLEDGE_GUN_GRAPH_PATH": "/Users/<you>/path/to/your/graph.json",
        "KNOWLEDGE_GUN_INTRO_DIR": "/Users/<you>/path/to/intros/",
        "KNOWLEDGE_GUN_ROOTS_DIR": "/Users/<you>/path/to/roots/"
      }
    }
  }
}
```

### VS Code (Copilot Chat)

Edit `.vscode/mcp.json`:

```json
{
  "servers": {
    "knowledge-gun": {
      "type": "stdio",
      "command": "knowledge-gun-mcp",
      "env": {
        "KNOWLEDGE_GUN_GRAPH_PATH": "/Users/<you>/path/to/your/graph.json",
        "KNOWLEDGE_GUN_INTRO_DIR": "/Users/<you>/path/to/intros/",
        "KNOWLEDGE_GUN_ROOTS_DIR": "/Users/<you>/path/to/roots/"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add knowledge-gun \
  --env KNOWLEDGE_GUN_GRAPH_PATH=/Users/<you>/path/to/your/graph.json \
  --env KNOWLEDGE_GUN_INTRO_DIR=/Users/<you>/path/to/intros/ \
  --env KNOWLEDGE_GUN_ROOTS_DIR=/Users/<you>/path/to/roots/ \
  -- knowledge-gun-mcp
```

Or paste the equivalent block into `~/.config/claude-code/config.json`.

A copy-paste sample lives in [`examples/claude_desktop_config.json`](examples/claude_desktop_config.json).

## Tools

The server exposes a narrow surface — read-only, no fuzz.

| Tool | Arguments | Returns | Use when |
|---|---|---|---|
| `list_topics` | — | newline-separated topic names | you don't know which topic to ask for |
| `get_bundle` | `topic` (string) | paste-ready markdown bundle (~1,500-4,000 words) | the user asks for context, a briefing, or background on `<their X>` |

### `list_topics()`

Returns the topic names configured for the current graph. No arguments. Use this first if you don't know which topic to ask for.

Example output (against the bundled demo graph):

```
industry
projects
studio
team
```

Your topics will differ — they are derived from whichever `<topic>.intro.md` and `<topic>.roots.json` files are present in your configured intro and roots directories.

### `get_bundle(topic)`

Returns the paste-ready markdown bundle for a topic. Typically 1,500-4,000 words. The bundle contains:

- a hand-written intro for the topic,
- a 2-hop graph neighbourhood walked from anchor node ids configured for the topic,
- a usage footer pointing at sibling topics.

Argument: `topic` (string, required). Use `list_topics` if you don't know the value.

A captured sample bundle from the bundled demo graph (fictional indie game studio) lives in [`examples/example_bundle_output.md`](examples/example_bundle_output.md).

## Bring your own graph

The server reads three things from environment variables (set in your client's MCP `env` block — see above):

| Variable | Points at |
|---|---|
| `KNOWLEDGE_GUN_GRAPH_PATH` | Your graph JSON file (`{"nodes": [...], "edges": [...]}`) |
| `KNOWLEDGE_GUN_INTRO_DIR` | Directory of `<topic>.intro.md` files |
| `KNOWLEDGE_GUN_ROOTS_DIR` | Directory of `<topic>.roots.json` files (lists of seed node ids) |

If unset, the server falls back to the demo graph that ships with `knowledge-gun` (a fictional indie game studio with four topics: `studio`, `team`, `projects`, `industry`). Useful for verifying the wiring before pointing at your real graph.

The graph schema and bundle generator are documented in the [`knowledge-gun`](https://github.com/akaddo97/knowledge-gun) README.

## Verify with the inspector

Before wiring into a real client, smoke-test the server with the official MCP Inspector:

```bash
npx @modelcontextprotocol/inspector knowledge-gun-mcp
```

The inspector opens a web UI; you can list the tools, call `list_topics`, then call `get_bundle` against the demo graph and read the output inline.

## Limits

- **Stdio only.** Single-machine, single-user. The server runs as a child process of the host and inherits its environment. HTTP/SSE transport (for shared / hosted use across devices) is on the roadmap for v0.2.
- **No write tools.** This server is read-only over your graph. To mutate the graph, use `knowledge-gun`'s sibling tooling.
- **Bundles regenerate per call.** No caching. A `get_bundle` call reads the graph file, walks the neighbourhood, and assembles the markdown each time. Sub-second on graphs up to ~10k nodes.

## Troubleshooting

**Tools don't appear in the host's MCP indicator after restart.** Three classic stdio gotchas, in likely order:

1. **`knowledge-gun-mcp` not on PATH.** The host launches the command in its own environment, not your shell's. Use an absolute path in the `command` field (e.g. `/Users/<you>/.venvs/kg/bin/knowledge-gun-mcp`) or ensure the venv's `bin/` is on the global PATH the host sees.
2. **No env vars set, no demo fallback.** Without `KNOWLEDGE_GUN_GRAPH_PATH` / `KNOWLEDGE_GUN_INTRO_DIR` / `KNOWLEDGE_GUN_ROOTS_DIR`, the server falls back to the bundled demo graph. If you expected your own graph, recheck the env block in your client's MCP config.
3. **Host not fully restarted.** Some clients (Claude Desktop in particular) cache the MCP server registry; a quit-from-menu beats a window close. Verify with the MCP Inspector first (see above) — if Inspector lists the tools, the server is fine and the gap is on the host side.

If the tools appear but `get_bundle` returns `error: ...`, run `knowledge-gun --list` from the same shell the host inherits to confirm the configured topics resolve correctly.

## Architecture

```
┌─────────────────────┐     stdio JSON-RPC     ┌──────────────────────┐
│  MCP host           │ ◀────────────────────▶ │  knowledge-gun-mcp   │
│  (Claude Desktop /  │                        │  (this server)       │
│   Cursor / VS Code  │                        └──────────┬───────────┘
│   / Claude Code)    │                                   │
└─────────────────────┘                                   │
                                                          ▼
                                                ┌──────────────────────┐
                                                │  knowledge-gun       │
                                                │  (bundle generator)  │
                                                └──────────┬───────────┘
                                                           │
                                                           ▼
                                                ┌──────────────────────┐
                                                │  graph.json          │
                                                │  intros/*.intro.md   │
                                                │  roots/*.roots.json  │
                                                └──────────────────────┘
```

The MCP server is a thin facade. The real work — graph traversal, intro composition, markdown rendering — lives in `knowledge-gun`. Adding a topic means dropping new intro + roots files in their respective directories; the server picks them up on the next `list_topics` call.

## Development

```bash
git clone https://github.com/akaddo97/knowledge-gun-mcp
cd knowledge-gun-mcp

uv venv --python /opt/homebrew/opt/python@3.12/bin/python3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

pytest tests/ -v
```

Tests mock at the `knowledge_gun.generate_bundle` boundary — they verify dispatch, error handling, and tool-shape contracts without spinning up real stdio.

## License

MIT. See [LICENSE](LICENSE).
