"""MCP server wrapping knowledge-gun's bundle generation.

Exposes two tools:
  - list_topics() -> list[str]
  - get_bundle(topic: str) -> str

Run via stdio:
  knowledge-gun-mcp
or:
  python -m knowledge_gun_mcp
"""
__version__ = "0.1.0"
