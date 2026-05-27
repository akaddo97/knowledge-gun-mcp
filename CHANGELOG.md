# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- README: status badges (CI, Python, License) under the title.
- README: `Tools` catalogue table — drop-in scannable replacement for the prose list, with per-tool sections kept beneath as expanded references.
- README: `Troubleshooting` section covering the three classic stdio gotchas (`PATH`, env-vars unset, host not fully restarted).
- `examples/example_bundle_output.md` — captured `knowledge-gun --topic studio` output against the bundled demo graph (fictional Lantern-Bough Games). Lets readers see the shape and tone of a bundle without running anything.
- New read-only tools: `search_nodes`, `get_node`, `get_topic_anchors`. Substring discovery, single-node drill-in, and anchor-id exposure for a topic — see the **Tools** section.
- GitHub repository topics: `python`, `mcp-server`, `claude`.

### Changed
- README: `list_topics` example output now uses the bundled demo topics (`industry`, `projects`, `studio`, `team`) with a footnote that the user's own topics will differ — fixes a small drift against the parent [`knowledge-gun`](https://github.com/akaddo97/knowledge-gun) README.

### Removed
- GitHub repository topic: `context` — too broad, crowded out by stronger tags.

### Security
- _See sub 7's commit notes on the `chore/refresh-2026-05-27` branch for the privacy + dependency hardening that lands alongside this README polish._

## [0.1.0] — 2026-05-07

### Added
- Initial extract from internal tooling.
- MCP server wrapping [`knowledge-gun`](https://github.com/akaddo97/knowledge-gun) over the stdio transport.
- Two tools exposed to MCP clients:
  - `list_topics()` — returns the topic names configured for the current graph.
  - `get_bundle(topic)` — returns the paste-ready markdown bundle for a topic.
- Per-client install snippets for Claude Desktop, Cursor, VS Code (Copilot Chat), and Claude Code.
- MIT license.
- GitHub Actions CI: pytest matrix across `ubuntu-latest` × `macos-latest` × Python 3.11 / 3.12 / 3.13.

[Unreleased]: https://github.com/akaddo97/knowledge-gun-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/akaddo97/knowledge-gun-mcp/releases/tag/v0.1.0
