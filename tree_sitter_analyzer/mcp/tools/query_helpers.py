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
            "description": "Symbol to find project-wide. Supports wildcards: *Service, handle_*, *test*. Prefix ~ for fuzzy: ~analyz. Use find_references=true to find call sites instead of just definitions.",
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
        "find_references": {
            "type": "boolean",
            "default": False,
            "description": "Find all call sites / usages of the symbol (not just definitions). Requires symbol parameter.",
        },
        "suppress_output": {
            "type": "boolean",
            "default": False,
            "description": "If true with output_file, suppress detailed output and return metadata only",
        },
        # Cap result count — implementation lives in _apply_max_count_cap.
        # Declared here so additionalProperties=False does not reject it.
        "max_count": {
            "type": "integer",
            "minimum": 1,
            "description": (
                "Cap result count. Returns first N matches plus "
                "truncated=true / total_count metadata."
            ),
        },
    },
    # F5: refuse unknown keys with did-you-mean. Enforced centrally by
    # BaseMCPTool.__init_subclass__ — declared here for completeness.
    "additionalProperties": False,
}


def _query_risk_and_step(
    count: int,
    file_path: str,
    truncated: bool,
) -> tuple[str, str]:
    """Return (risk, next_step) based on query result count and truncation status."""
    if count == 0:
        return (
            "low",
            "Try a broader query_key, or use search_content to find the symbol by text.",
        )
    if truncated:
        return (
            "high",
            f"Tighten the query (add filter=) before opening {count} results.",
        )
    if count == 1:
        _msg = (
            f"extract_code_section(file_path='{file_path}', ...) to read the one match."
        )
        return "low", _msg
    if count > 50:
        return (
            "medium",
            "Add filter (e.g., 'name=~pattern') to narrow before opening all matches.",
        )
    return (
        "low",
        "Inspect listed start_line/end_line ranges, then read_partial for details.",
    )


def _risk_to_verdict(risk: str) -> str:
    """Map risk level to canonical verdict string (low→INFO, medium→CAUTION, high→REVIEW)."""
    if risk == "high":
        return "REVIEW"
    if risk == "medium":
        return "CAUTION"
    return "INFO"


def build_query_agent_summary(
    *,
    file_path: str,
    language: str,
    query: str,
    count: int,
    elapsed_ms: float,
    truncated: bool,
) -> dict[str, Any]:
    """Build a compact agent summary for a query_code response.

    Returns a dict containing ``summary_line`` and ``next_step`` at minimum.
    """
    from pathlib import Path as _Path

    file_name = _Path(file_path).name if file_path else "<unknown>"
    _trunc_part = " (truncated)" if truncated else ""
    summary_line = (
        f"{language} query '{query}': {count} results in {file_name}{_trunc_part}"
    )
    risk, next_step = _query_risk_and_step(count, file_path, truncated)
    verdict = _risk_to_verdict(risk)
    return {
        "risk": risk,
        "verdict": verdict,
        "mode": "query",
        "count": count,
        "elapsed_ms": elapsed_ms,
        "truncated": truncated,
        "language": language,
        "query": query,
        "file": file_name,
        "next_step": next_step,
        "summary_line": summary_line,
    }


def _format_capture_item(item: dict[str, Any]) -> dict[str, Any]:
    """Build a single summary entry for one query-result item."""
    name = item.get("name") or extract_name_from_content(item["content"])
    _span = item["end_line"] - item["start_line"] + 1
    lines = item.get("line_span", _span)
    line_range = f"{item['start_line']}-{item['end_line']}"
    return {
        "name": name,
        "line_range": line_range,
        "lines": lines,
        "node_type": item["node_type"],
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
        all_items = [_format_capture_item(item) for item in items]
        summary["captures"][capture_name] = {
            "count": len(items),
            "items": all_items,
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
    stripped = content.strip()
    first_line = stripped.split("\n")[0].strip()
    for pattern in _NAME_PATTERNS:
        match = re.search(pattern, first_line)
        if match:
            raw = match.group(1)
            return raw.strip()
    return "unnamed"


# build_next_steps: implementation
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
        _sl = first["start_line"]
        _el = first["end_line"]
        steps.append(
            f"extract_code_section(file_path='{file_path}', "
            f"start_line={_sl}, end_line={_el}) to read '{name}'"
        )

    if len(results) == 1:
        steps.append("Try other query keys to discover more elements in this file")
    elif len(results) > 3:
        steps.append("Add filter (e.g., 'name=~pattern') to narrow results")

    named = [r for r in results if r.get("name")]
    _query_types = ("methods", "functions", "method", "function")
    if named and query_used in _query_types:
        names = [r["name"] for r in named[:3]]
        steps.append(
            f"search_content(query='{'|'.join(names)}') to find callers of these elements"
        )

    return steps[:3]


def _validate_string_arg(
    arguments: dict[str, Any],
    key: str,
    *,
    non_empty: bool = False,
    allowed: list[str] | None = None,
) -> None:
    """Raise ValueError if ``key`` is present but fails type/value constraints."""
    if key not in arguments:
        return
    val = arguments[key]
    if not isinstance(val, str):
        raise ValueError(f"{key} must be a string")
    if non_empty and not val.strip():
        raise ValueError(f"{key} cannot be empty")
    if allowed and val not in allowed:
        raise ValueError(f"{key} must be one of: {', '.join(allowed)}")


# validate_query_arguments: implementation
# Validates all input parameters before executing a query
def validate_query_arguments(arguments: dict[str, Any]) -> bool:
    """Validate file_path/symbol, query_key/query_string, and format options."""
    if "file_path" not in arguments and "symbol" not in arguments:
        raise ValueError("file_path or symbol is required")
    _validate_string_arg(arguments, "file_path", non_empty=True)
    if not arguments.get("query_key") and not arguments.get("query_string"):
        raise ValueError("Either query_key or query_string must be provided")
    _validate_string_arg(arguments, "query_key")
    _validate_string_arg(arguments, "query_string")
    _validate_string_arg(arguments, "language")
    _validate_string_arg(arguments, "filter")
    _validate_string_arg(arguments, "result_format", allowed=["json", "summary"])
    _validate_string_arg(arguments, "output_format", allowed=["json", "toon"])
    _validate_string_arg(arguments, "output_file", non_empty=True)
    if "suppress_output" in arguments and not isinstance(
        arguments["suppress_output"], bool
    ):
        raise ValueError("suppress_output must be a boolean")
    return True


def _copy_agent_summary_to(
    source: dict[str, Any],
    target: dict[str, Any],
) -> None:
    """Copy agent_summary (and summary_line) from source dict into target envelope."""
    if "agent_summary" not in source:
        return
    target["agent_summary"] = source["agent_summary"]
    agent_summary = source["agent_summary"]
    _is_dict = isinstance(agent_summary, dict)
    _has_line = _is_dict and isinstance(agent_summary.get("summary_line"), str)
    if _has_line:
        target["summary_line"] = agent_summary["summary_line"]


def _build_suppress_envelope(
    formatted: dict[str, Any],
    file_path: str,
    language: str,
    query: str | None,
) -> dict[str, Any]:
    """Build the minimal suppress envelope returned when suppress_output=True."""
    _count_raw = formatted.get("count", 0)
    _total_count = int(_count_raw or 0)
    minimal: dict[str, Any] = {
        "success": formatted.get("success", True),
        "count": formatted.get("count", 0),
        "file_path": file_path,
        "language": language,
        "query": query,
        "elapsed_ms": formatted.get("elapsed_ms", 0.0),
        "truncated": formatted.get("truncated", False),
        "displayed_count": 0,
        "total_count": _total_count,
    }
    _copy_agent_summary_to(formatted, minimal)
    for key in ("next_steps", "output_file_path", "file_saved", "file_save_error"):
        if key in formatted:
            minimal[key] = formatted[key]
    return minimal


def _save_query_output(
    formatted: dict[str, Any],
    output_file: str,
    file_path: str,
    query: str | None,
    output_format: str,
    file_output_manager: Any,
) -> None:
    """Save formatted query output to a file and record metadata in formatted."""
    from pathlib import Path as _Path

    from ..utils.format_helper import format_for_file_output as _format_for_file

    try:
        _stem = _Path(file_path).stem
        _default = f"{_stem}_query_{query or 'custom'}"
        base_name = output_file if output_file.strip() else _default
        content, _ = _format_for_file(formatted, output_format)
        saved = file_output_manager.save_to_file(content=content, base_name=base_name)
        formatted["output_file_path"] = saved
        formatted["file_saved"] = True
    except Exception as e:
        formatted["file_save_error"] = str(e)
        formatted["file_saved"] = False


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
    from ..utils.format_helper import apply_toon_format_to_response as _apply_toon

    output_file = arguments.get("output_file")
    suppress_output = arguments.get("suppress_output", False)
    output_format = arguments.get("output_format", "toon")

    if output_file:
        _save_query_output(
            formatted, output_file, file_path, query, output_format, file_output_manager
        )

    if suppress_output and output_file:
        return _build_suppress_envelope(formatted, file_path, language, query)

    return _apply_toon(formatted, output_format)
