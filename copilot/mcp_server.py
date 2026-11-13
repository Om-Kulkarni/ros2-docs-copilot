"""MCP server exposing the ROS 2 docs index to Claude Desktop, Cursor, etc.

Tools:
  search_docs(query, k)  -> raw ranked chunks with URLs (no LLM call, free)
  ask(question)          -> grounded answer with [n] citations + source list
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import config, rag

mcp = MCPServer("ros2-docs-copilot")


@mcp.tool()
def search_docs(query: str, k: int = 5) -> str:
    """Semantic search over the ROS 2 Jazzy documentation (tutorials, concepts, how-to guides).
    Returns the top-k excerpts with their docs.ros.org URLs. Use this to look up commands,
    APIs, QoS settings, launch files, tf2, colcon, rosbag2, etc."""
    hits = rag.search(query, max(1, min(k, 20)))
    return "\n\n---\n\n".join(
        f"[{h.n}] {h.title} — {h.section} (score {h.score})\n{h.url}\n\n{h.text}" for h in hits)


@mcp.tool()
def ask(question: str) -> str:
    """Answer a ROS 2 Jazzy question using retrieval-augmented generation over the official docs.
    The answer cites sources as [n]; the numbered source URLs are listed at the end."""
    r = rag.ask(question)
    refs = "\n".join(f"[{s['n']}] {s['title']} — {s['section']}: {s['url']}" for s in r["sources"])
    return f"{r['answer']}\n\nSources:\n{refs}"


def main() -> None:
    if config.CHROMA_DIR.exists() is False:
        raise SystemExit("Index not found. Run `uv run copilot-ingest` first.")
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
