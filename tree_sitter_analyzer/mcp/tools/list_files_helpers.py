#!/usr/bin/env python3
"""Shared helpers for list_files_tool — extracted schema and output handling."""

from __future__ import annotations

from typing import Any

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "roots": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Dirs to search. E.g. ['src/', 'tests/']",
        },
        "pattern": {
            "type": "string",
            "description": "Filename pattern. E.g. '*.py', 'test_*'",
        },
        "glob": {
            "type": "boolean",
            "default": False,
            "description": "Treat pattern as glob, not regex",
        },
        "types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Types: f=files, d=dirs, l=symlinks, x=exec",
        },
        "extensions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Extensions (no dots). E.g. ['py', 'js']",
        },
        "exclude": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exclude patterns",
        },
        "depth": {
            "type": "integer",
            "description": "Max depth. 1=current only",
        },
        "follow_symlinks": {
            "type": "boolean",
            "default": False,
            "description": "Follow symlinks",
        },
        "hidden": {
            "type": "boolean",
            "default": False,
            "description": "Include hidden files",
        },
        "no_ignore": {
            "type": "boolean",
            "default": False,
            "description": "Ignore .gitignore",
        },
        "size": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Size filter. E.g. '+10M', '-1K'",
        },
        "changed_within": {
            "type": "string",
            "description": "Modified within. E.g. '1d', '2h'",
        },
        "changed_before": {
            "type": "string",
            "description": "Modified before. Same format",
        },
        "full_path_match": {
            "type": "boolean",
            "default": False,
            "description": "Match full path, not just filename",
        },
        "absolute": {
            "type": "boolean",
            "default": True,
            "description": "Return absolute paths",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (def 2000, max 10000)",
        },
        "count_only": {
            "type": "boolean",
            "default": False,
            "description": "Return only count, not file details",
        },
        "output_file": {
            "type": "string",
            "description": "Save output to file",
        },
        "suppress_output": {
            "type": "boolean",
            "default": False,
            "description": "Suppress response when output_file set",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
            "description": "'toon' (default, ~60% smaller) or 'json'",
        },
    },
    "required": ["roots"],
    "additionalProperties": False,
}


def build_query_info(
    arguments: dict[str, Any], limit: int, no_ignore: bool
) -> dict[str, Any]:
    return {
        "roots": arguments.get("roots", []),
        "pattern": arguments.get("pattern"),
        "glob": arguments.get("glob", False),
        "types": arguments.get("types"),
        "extensions": arguments.get("extensions"),
        "exclude": arguments.get("exclude"),
        "depth": arguments.get("depth"),
        "follow_symlinks": arguments.get("follow_symlinks", False),
        "hidden": arguments.get("hidden", False),
        "no_ignore": no_ignore,
        "size": arguments.get("size"),
        "changed_within": arguments.get("changed_within"),
        "changed_before": arguments.get("changed_before"),
        "full_path_match": arguments.get("full_path_match", False),
        "absolute": arguments.get("absolute", True),
        "limit": limit,
    }
