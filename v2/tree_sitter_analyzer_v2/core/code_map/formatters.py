"""
Formatters for CodeMapResult — TOON and Mermaid output.

Extracted from __init__.py to follow SRP (Fowler P0 #1).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter_analyzer_v2.core.code_map.result import CodeMapResult


def format_toon(r: CodeMapResult) -> str:
    """Format CodeMapResult as token-optimized TOON for LLM consumption."""
    lines: list[str] = []
    proj_name = Path(r.project_dir).name

    # Header
    lines.append(
        f"PROJECT:{proj_name} "
        f"[{r.total_files}files {r.total_lines}LOC "
        f"{r.total_classes}cls {r.total_functions}fn]"
    )
    lines.append("")

    # Pre-build dependency-count lookup: O(n) instead of O(n×m)
    dep_incoming: Counter[str] = Counter(dst for _, dst in r.module_dependencies)

    # Modules (sorted by line count descending)
    lines.append("MODULES:")
    for m in sorted(r.modules, key=lambda x: x.lines, reverse=True):
        dep_count = dep_incoming[m.path]
        cls_names = [c.get("name", "") for c in m.classes]
        fn_names = [f.get("name", "") for f in m.functions]
        parts = [f"  {m.path} [{m.lines}L {m.language}]"]
        if dep_count:
            parts[0] += f" <-{dep_count}deps"
        if cls_names:
            for cn in cls_names:
                cls_obj = next((c for c in m.classes if c.get("name") == cn), None)
                methods = cls_obj.get("methods", []) if cls_obj else []
                mtd_str = ",".join(mt.get("name", "") for mt in methods)
                parts.append(f"    CLS {cn}" + (f" [{mtd_str}]" if mtd_str else ""))
        if fn_names:
            parts.append(f"    FN: {','.join(fn_names)}")
        lines.extend(parts)
    lines.append("")

    # Entry points
    if r.entry_points:
        lines.append("ENTRY_POINTS:")
        for ep in r.entry_points:
            lines.append(f"  {ep.file}:{ep.name}() L{ep.line_start}")
        lines.append("")

    # Module dependency graph (compact)
    if r.module_dependencies:
        lines.append("DEPENDENCIES:")
        for src, dst in sorted(set(r.module_dependencies)):
            lines.append(f"  {src} -> {dst}")
        lines.append("")

    # Hot spots
    if r.hot_spots:
        lines.append("HOT_SPOTS (change = high impact):")
        for sym, count in r.hot_spots[:10]:
            loc = f"{sym.file}:{sym.name}"
            lines.append(f"  {loc} <-{count}refs [{sym.kind}]")
        lines.append("")

    # Dead code
    if r.dead_code:
        lines.append("DEAD_CODE (0 refs, candidates for removal):")
        for sym in r.dead_code[:20]:
            lines.append(f"  {sym.file}:{sym.name}() L{sym.line_start}")
        lines.append("")

    # Quick navigation index
    lines.append("SYMBOL_INDEX:")
    for sym in sorted(r.symbols, key=lambda s: (s.file, s.line_start)):
        if sym.kind == "class":
            lines.append(f"  CLS {sym.name} {sym.file}:L{sym.line_start}-{sym.line_end}")
        elif sym.kind == "method":
            ret = f"->{sym.return_type}" if sym.return_type else ""
            lines.append(
                f"    .{sym.name}({sym.params}){ret} L{sym.line_start}"
            )
        else:
            ret = f"->{sym.return_type}" if sym.return_type else ""
            lines.append(
                f"  FN {sym.name}({sym.params}){ret} {sym.file}:L{sym.line_start}"
            )

    return "\n".join(lines)


def format_mermaid(r: CodeMapResult) -> str:
    """Format module dependencies as Mermaid flowchart."""
    lines: list[str] = ["flowchart LR"]
    if not r.module_dependencies:
        lines.append("  A[No dependencies detected]")
        return "\n".join(lines)

    # Collect unique modules
    nodes: set[str] = set()
    for src, dst in r.module_dependencies:
        nodes.add(src)
        nodes.add(dst)

    # Create node IDs (sanitize for Mermaid)
    node_ids: dict[str, str] = {}
    for i, node in enumerate(sorted(nodes)):
        safe_id = f"M{i}"
        short_name = Path(node).stem
        node_ids[node] = safe_id
        lines.append(f"  {safe_id}[{short_name}]")

    # Edges
    for src, dst in sorted(set(r.module_dependencies)):
        if src in node_ids and dst in node_ids:
            lines.append(f"  {node_ids[src]} --> {node_ids[dst]}")

    return "\n".join(lines)
