#!/usr/bin/env python3
"""
JSON Formatter

Formats JSON analysis results showing document structure, top-level properties,
and nested object/array statistics.
"""

import json
from typing import Any

from .base_formatter import BaseFormatter


class JSONFormatter(BaseFormatter):
    """Formatter for JSON files."""

    def __init__(self) -> None:
        self.language = "json"

    # ------------------------------------------------------------------
    # Public interface (called by analyze_code_structure_tool)
    # ------------------------------------------------------------------

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """Short summary: root type + top-level key count."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])

        doc = next((e for e in elements if e.get("element_type") == "document"), None)
        props = [e for e in elements if e.get("element_type") in ("property", "pair")]
        top_level = [p for p in props if p.get("nesting_level", 0) == 1]

        root_type = doc.get("value_type", "unknown") if doc else "unknown"
        summary = {
            "file_path": file_path,
            "language": "json",
            "root_type": root_type,
            "total_properties": len(props),
            "top_level_keys": len(top_level),
        }
        return self._format_json_output("JSON Summary", summary)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """Main structure table used by analyze_code_structure."""
        file_path = analysis_result.get("file_path", "")
        elements = analysis_result.get("elements", [])
        # line_count may live at top level or inside statistics (depends on call path)
        line_count = analysis_result.get("line_count", 0) or (
            analysis_result.get("statistics") or {}
        ).get("total_lines", 0)

        doc = next((e for e in elements if e.get("element_type") == "document"), None)
        props = [e for e in elements if e.get("element_type") in ("property", "pair")]

        if not props and doc is None:
            return f"# {file_path}\n\nNo JSON elements found."

        root_type = doc.get("value_type", "unknown") if doc else "unknown"
        root_children = doc.get("child_count") if doc else None

        lines: list[str] = []
        lines.append(f"# {file_path.split('/')[-1]}")
        lines.append("")
        lines.append("## Document Info")
        lines.append(f"- **Root type**: `{root_type}`")
        if root_children is not None:
            label = "properties" if root_type == "object" else "items"
            lines.append(f"- **Top-level {label}**: {root_children}")
        lines.append(f"- **Total properties**: {len(props)}")
        lines.append(f"- **Total lines**: {line_count}")
        lines.append("")

        # Group properties by nesting level
        by_level: dict[int, list[Any]] = {}
        for p in props:
            lvl = p.get("nesting_level", 0)
            by_level.setdefault(lvl, []).append(p)

        max_show_level = 2  # show levels 1 and 2 only to keep output concise

        for level in sorted(k for k in by_level if k <= max_show_level):
            label = "Top-level" if level == 1 else f"Level-{level}"
            group = by_level[level]
            lines.append(f"## {label} Properties ({len(group)})")
            lines.append("")
            lines.append("| Key | Type | Value / Children | Lines |")
            lines.append("|-----|------|-----------------|-------|")
            for p in group:
                key = p.get("key") or p.get("name") or "?"
                vtype = p.get("value_type", "")
                val = p.get("value") or ""
                children = p.get("child_count")
                if children is not None:
                    display = f"({children} {'props' if vtype == 'object' else 'items'})"
                elif val:
                    trimmed = val[:40] + "…" if len(val) > 40 else val
                    display = f"`{trimmed}`"
                else:
                    display = ""
                start = p.get("start_line", 0)
                end = p.get("end_line", 0)
                line_range = f"{start}" if start == end else f"{start}-{end}"
                lines.append(f"| `{key}` | {vtype} | {display} | {line_range} |")
            lines.append("")

        deeper = sum(len(v) for k, v in by_level.items() if k > max_show_level)
        if deeper:
            lines.append(f"*({deeper} deeper properties not shown)*")

        return "\n".join(lines)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        """Advanced analysis: nesting distribution + value-type breakdown."""
        elements = analysis_result.get("elements", [])
        props = [e for e in elements if e.get("element_type") in ("property", "pair")]

        vtype_counts: dict[str, int] = {}
        level_counts: dict[int, int] = {}
        max_depth = 0

        for p in props:
            vtype = p.get("value_type") or "unknown"
            vtype_counts[vtype] = vtype_counts.get(vtype, 0) + 1
            lvl = p.get("nesting_level", 0)
            level_counts[lvl] = level_counts.get(lvl, 0) + 1
            if lvl > max_depth:
                max_depth = lvl

        result = {
            "file_path": analysis_result.get("file_path", ""),
            "language": "json",
            "total_properties": len(props),
            "max_nesting_depth": max_depth,
            "value_type_distribution": vtype_counts,
            "properties_per_level": {str(k): v for k, v in sorted(level_counts.items())},
        }
        return self._format_json_output("JSON Advanced Analysis", result)

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        return self.format_structure(analysis_result)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _format_json_output(self, title: str, data: dict[str, Any]) -> str:
        """Format data as a titled JSON block (matches BaseFormatter convention)."""
        sep = "--- " + title + " ---"
        return sep + "\n" + json.dumps(data, indent=2, ensure_ascii=False)
