#!/usr/bin/env python3
"""
Shared helpers for query_tool.

Extracted from the monolithic tool file to reduce duplication.
"""

import re
from typing import Any

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "File to query. Omit for cross-file symbol search.",
        },
        "symbol": {
            "type": "string",
            "description": "Symbol to find project-wide. Omit file_path.",
        },
        "language": {"type": "string"},
        "query_key": {
            "type": "string",
            "description": (
                "Query: methods|classes|functions|imports|variables, "
                "or language-specific keys. Invalid key lists available."
            ),
        },
        "query_string": {
            "type": "string",
            "description": "Custom tree-sitter query",
        },
        "filter": {
            "type": "string",
            "description": "Filter: 'name=main', 'name=~get*'",
        },
        "result_format": {
            "type": "string",
            "enum": ["json", "summary"],
            "default": "json",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
    },
}


def format_summary(
    results: list[dict[str, Any]], query_type: str, language: str
) -> dict[str, Any]:
    """Format query results as a summary grouped by capture name."""
    by_capture: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_capture.setdefault(r["capture_name"], []).append(r)

    summary: dict[str, Any] = {
        "success": True,
        "query_type": query_type,
        "language": language,
        "total_count": len(results),
        "captures": {},
    }
    for capture_name, items in by_capture.items():
        summary["captures"][capture_name] = {
            "count": len(items),
            "items": [
                {
                    "name": item.get("name")
                    or extract_name_from_content(item["content"]),
                    "line_range": f"{item['start_line']}-{item['end_line']}",
                    "lines": item.get(
                        "line_span", item["end_line"] - item["start_line"] + 1
                    ),
                    "node_type": item["node_type"],
                }
                for item in items
            ],
        }
    return summary


_NAME_PATTERNS = [
    r"^#{1,6}\s+(.+)$",
    r"(?:public|private|protected)?\s*(?:static)?\s*(?:class|interface)\s+(\w+)",
    r"(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(",
    r"(\w+)\s*\(",
]


def extract_name_from_content(content: str) -> str:
    """Extract name from code content using common declaration patterns."""
    first_line = content.strip().split("\n")[0].strip()
    for pattern in _NAME_PATTERNS:
        match = re.search(pattern, first_line)
        if match:
            return match.group(1).strip()
    return "unnamed"


def build_next_steps(
    results: list[dict[str, Any]], file_path: str, query_used: str
) -> list[str]:
    """Build actionable next-step suggestions based on query results."""
    if not results:
        return []

    steps: list[str] = []
    extractable = [
        r
        for r in results
        if "start_line" in r and "end_line" in r and r["end_line"] > r["start_line"]
    ]
    if extractable:
        first = extractable[0]
        name = first.get("name", first.get("capture_name", "element"))
        steps.append(
            f"extract_code_section(file_path='{file_path}', "
            f"start_line={first['start_line']}, end_line={first['end_line']}) to read '{name}'"
        )

    if len(results) == 1:
        steps.append("Try other query keys to discover more elements in this file")
    elif len(results) > 3:
        steps.append("Add filter (e.g., 'name=~pattern') to narrow results")

    named = [r for r in results if r.get("name")]
    if named and query_used in ("methods", "functions", "method", "function"):
        names = [r["name"] for r in named[:3]]
        steps.append(
            f"search_content(query='{'|'.join(names)}') to find callers of these elements"
        )

    return steps[:3]
