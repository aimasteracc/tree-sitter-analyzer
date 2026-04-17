"""Measure token cost of MCP tool schemas.

Run with: uv run python scripts/measure_schema_tokens.py
"""

from __future__ import annotations

import json
import sys

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for CJK."""
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    ascii_chars = len(text) - cjk
    return int(ascii_chars / 4 + cjk / 2)


async def _get_tools() -> list[Any]:
    """Get tool definitions from MCP server."""
    server = TreeSitterAnalyzerMCPServer()
    mcp_server = server.create_server()
    result = await mcp_server.list_tools()
    return result.tools if hasattr(result, "tools") else []


def main() -> None:
    import asyncio

    tools = asyncio.run(_get_tools())
    if not tools:
        print("No tools found")
        sys.exit(1)

    print(f"Total tools: {len(tools.tools)}\n")
    print(f"{'Tool Name':<35} {'Desc Tokens':>12} {'Param Tokens':>13} {'Total':>8}")
    print("-" * 70)

    total_desc = 0
    total_params = 0
    total_total = 0
    longest_tools: list[tuple[str, int]] = []

    for tool in tools.tools:
        desc_tokens = _estimate_tokens(tool.description or "")
        params_json = json.dumps(tool.inputSchema, separators=(",", ":"))
        param_tokens = _estimate_tokens(params_json)
        tool_total = desc_tokens + param_tokens

        total_desc += desc_tokens
        total_params += param_tokens
        total_total += tool_total

        print(
            f"{tool.name:<35} {desc_tokens:>10} t  {param_tokens:>11} t  {tool_total:>6} t"
        )
        longest_tools.append((tool.name, tool_total))

    print("-" * 70)
    print(
        f"{'TOTAL':<35} {total_desc:>10} t  {total_params:>11} t  {total_total:>6} t"
    )

    print(f"\nTop 5 heaviest tools:")
    for name, cost in sorted(longest_tools, key=lambda x: -x[1])[:5]:
        print(f"  {name}: {cost} tokens")


if __name__ == "__main__":
    main()
