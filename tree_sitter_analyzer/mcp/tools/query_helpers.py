#!/usr/bin/env python3
"""
Shared helpers for query_tool.

Extracted from the monolithic tool file to reduce duplication.
"""

import re
from typing import Any

# JSON Schema: input validation for query_code tool
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # Target file to query (omit for cross-file symbol search)
        "file_path": {
            "type": "string",
            "description": "File to query. Omit for cross-file symbol search.",
        },
        # Symbol search with wildcards and fuzzy matching
        "symbol": {
            "type": "string",
            "description": "Symbol to find project-wide. Supports wildcards: *Service, handle_*, *test*. Prefix ~ for fuzzy: ~analyz.",
        },
        # Filter by symbol type
        "symbol_type": {
            "type": "string",
            "enum": ["class", "function", "method", "variable", "import"],
            "description": "Filter symbol type (optional)",
        },
        # Override auto-detected language
        "language": {"type": "string"},
        # Predefined query key or language-specific key
        "query_key": {
            "type": "string",
            "description": (
                "Query: methods|classes|functions|imports|variables, "
                "or language-specific keys. Invalid key lists available."
            ),
        },
        # Custom tree-sitter query string
        "query_string": {
            "type": "string",
            "description": "Custom tree-sitter query",
        },
        # Filter pattern for results
        "filter": {
            "type": "string",
            "description": "Filter: 'name=main', 'name=~get*'",
        },
        # Result format: full json or summary
        "result_format": {
            "type": "string",
            "enum": ["json", "summary"],
            "default": "json",
        },
        # Token-efficient toon format by default
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
        "output_file": {
            "type": "string",
            "description": "Optional filename to save output to file",
        },
        "suppress_output": {
            "type": "boolean",
            "default": False,
            "description": "If true with output_file, suppress detailed output and return metadata only",
        },
    },
}


# format_summary: implementation
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


# extract_name_from_content: implementation
def extract_name_from_content(content: str) -> str:
    """Extract name from code content using common declaration patterns."""
    first_line = content.strip().split("\n")[0].strip()
    # Loop iteration
    for pattern in _NAME_PATTERNS:
        match = re.search(pattern, first_line)
        # Conditional check
        if match:
            return match.group(1).strip()
    return "unnamed"


# build_next_steps: implementation
def build_next_steps(
    results: list[dict[str, Any]], file_path: str, query_used: str
) -> list[str]:
    """Build actionable next-step suggestions based on query results."""
    # Conditional check
    if not results:
        return []

    steps: list[str] = []
    extractable = [
        r
        for r in results
        if "start_line" in r and "end_line" in r and r["end_line"] > r["start_line"]
    ]
    # Conditional check
    if extractable:
        first = extractable[0]
        name = first.get("name", first.get("capture_name", "element"))
        steps.append(
            f"extract_code_section(file_path='{file_path}', "
            f"start_line={first['start_line']}, end_line={first['end_line']}) to read '{name}'"
        )

    # Conditional check
    if len(results) == 1:
        steps.append("Try other query keys to discover more elements in this file")
    elif len(results) > 3:
        steps.append("Add filter (e.g., 'name=~pattern') to narrow results")

    named = [r for r in results if r.get("name")]
    # Conditional check
    if named and query_used in ("methods", "functions", "method", "function"):
        names = [r["name"] for r in named[:3]]
        steps.append(
            f"search_content(query='{'|'.join(names)}') to find callers of these elements"
        )

    return steps[:3]


# validate_query_arguments: implementation
# Validates all input parameters before executing a query
def validate_query_arguments(arguments: dict[str, Any]) -> bool:
    """Validate file_path/symbol, query_key/query_string, and format options."""
    # At least one of file_path or symbol must be present
    if "file_path" not in arguments and "symbol" not in arguments:
        raise ValueError("file_path or symbol is required")
    # Validate file_path if provided
    if "file_path" in arguments:
        fp = arguments["file_path"]
        if not isinstance(fp, str):
            raise ValueError("file_path must be a string")
        if not fp.strip():
            raise ValueError("file_path cannot be empty")
    # At least one query parameter is required
    if not arguments.get("query_key") and not arguments.get("query_string"):
        raise ValueError("Either query_key or query_string must be provided")
    # Validate query_key type
    if "query_key" in arguments and not isinstance(arguments["query_key"], str):
        raise ValueError("query_key must be a string")
    # Validate query_string type
    if "query_string" in arguments and not isinstance(arguments["query_string"], str):
        raise ValueError("query_string must be a string")
    # Validate string-type optional fields
    for key in ["language", "filter"]:
        if key in arguments and not isinstance(arguments[key], str):
            raise ValueError(f"{key} must be a string")
    # Validate result_format enum
    if "result_format" in arguments:
        if not isinstance(arguments["result_format"], str):
            raise ValueError("result_format must be a string")
        if arguments["result_format"] not in ["json", "summary"]:
            raise ValueError("result_format must be one of: json, summary")
    # Validate output_format enum
    if "output_format" in arguments:
        if not isinstance(arguments["output_format"], str):
            raise ValueError("output_format must be a string")
        if arguments["output_format"] not in ["json", "toon"]:
            raise ValueError("output_format must be one of: json, toon")
    # Validate output_file path
    if "output_file" in arguments:
        if not isinstance(arguments["output_file"], str):
            raise ValueError("output_file must be a string")
        if not arguments["output_file"].strip():
            raise ValueError("output_file cannot be empty")
    # Validate suppress_output flag
    if "suppress_output" in arguments and not isinstance(
        arguments["suppress_output"], bool
    ):
        raise ValueError("suppress_output must be a boolean")
    return True


# handle_query_output: extracted from QueryTool._handle_output
# Manages file saving and output suppression for large result sets
def handle_query_output(
    formatted: dict[str, Any],
    arguments: dict[str, Any],
    file_path: str,
    language: str,
    query: str | None,
    file_output_manager: Any,
) -> dict[str, Any]:
    """Handle file output and suppress logic for query results."""
    from pathlib import Path as _Path

    from ..utils.format_helper import apply_toon_format_to_response as _apply_toon
    from ..utils.format_helper import format_for_file_output as _format_for_file

    output_file = arguments.get("output_file")
    suppress_output = arguments.get("suppress_output", False)
    output_format = arguments.get("output_format", "toon")

    if output_file:
        try:
            base_name = (
                output_file
                if output_file.strip()
                else f"{_Path(file_path).stem}_query_{query or 'custom'}"
            )
            content, _ = _format_for_file(formatted, output_format)
            saved = file_output_manager.save_to_file(
                content=content, base_name=base_name
            )
            formatted["output_file_path"] = saved
            formatted["file_saved"] = True
        except Exception as e:
            formatted["file_save_error"] = str(e)
            formatted["file_saved"] = False

    if suppress_output and output_file:
        minimal: dict[str, Any] = {
            "success": formatted.get("success", True),
            "count": formatted.get("count", 0),
            "file_path": file_path,
            "language": language,
            "query": query,
        }
        if "output_file_path" in formatted:
            minimal["output_file_path"] = formatted["output_file_path"]
        if "file_saved" in formatted:
            minimal["file_saved"] = formatted["file_saved"]
        if "file_save_error" in formatted:
            minimal["file_save_error"] = formatted["file_save_error"]
        return minimal

    return _apply_toon(formatted, output_format)
