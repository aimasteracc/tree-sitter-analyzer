"""Code-graph context formatter helpers — Phase 3 REQ-CLEAN-002.

Response formatting and related-symbol classification for CodeGraphContextTool.

Functions:
    _looks_like_trace
    _next_step
    _next_step_lean
    _build_related_symbols
"""

from __future__ import annotations

from typing import Any

from .codegraph_context_helpers import _is_non_prod_file


def _looks_like_trace(task: str) -> bool:
    lowered = task.lower()
    return any(
        word in lowered for word in ("trace", "flow", "through", "pipeline", "how does")
    )


def _next_step(has_code: bool, has_entry_points: bool) -> str:
    if has_code:
        return (
            "Answer from code_blocks and the graph now. Only call a narrower "
            "codegraph tool if a specific edge or symbol is missing."
        )
    if has_entry_points:
        return "Use the nodes and edges to answer; code snippets were not available."
    return "Try codegraph_symbol_search with an exact symbol name or broaden the task."


def _next_step_lean(
    has_code: bool,
    has_entry_points: bool,
    entry_points: list[dict[str, Any]] | None = None,
) -> str:
    """Next-step hint for the lean (default) response path."""
    if has_code:
        if entry_points and all(
            _is_non_prod_file(ep.get("file", "")) for ep in entry_points
        ):
            top = entry_points[0]
            top_name = top.get("name", "")
            top_file = top.get("file", "")
            return (
                f"Matches found only in non-production files (e.g. {top_name!r} "
                f"in {top_file!r}). These are examples/scripts, not the "
                "production implementation. Use search action=symbol or "
                "search action=content with a more specific term to find the "
                "production code. For the full call graph add include_graph=true."
            )
        top_name = entry_points[0].get("name", "") if entry_points else ""
        anchor = f" (starting from {top_name!r})" if top_name else ""
        return (
            f"Answer from code_blocks now{anchor}. "
            "For the full call graph (nodes/edges) add include_graph=true."
        )
    if has_entry_points:
        return (
            "Entry points found; code snippets were not available. "
            "For the full call graph add include_graph=true."
        )
    return "Try codegraph_symbol_search with an exact symbol name or broaden the task."


def _build_related_symbols(
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a compact CG-style related-symbols list grouped by file."""
    by_file: dict[str, list[tuple[int, str]]] = {}
    for node in nodes:
        file_path = node.get("file", "")
        name = node.get("name", "")
        if not file_path or not name:
            continue
        line = int(node.get("line", 0) or 0)
        by_file.setdefault(file_path, []).append((line, name))

    groups: list[dict[str, Any]] = []
    for file_path in sorted(by_file):
        entries = sorted(by_file[file_path])
        symbols = [f"{name}:{line}" for line, name in entries]
        groups.append({"file": file_path, "symbols": symbols})
    return groups
