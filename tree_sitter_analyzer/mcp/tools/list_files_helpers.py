#!/usr/bin/env python3
"""Shared helpers for list_files_tool — extracted schema and output handling."""

from __future__ import annotations

from typing import Any

# JSON Schema: input validation for list_files tool
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # Required: directories to search in
        "roots": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Search dirs",
        },
        # Filename pattern (supports glob if glob=true)
        "pattern": {
            "type": "string",
            "description": "Filename pattern",
        },
        # Treat pattern as a glob expression
        "glob": {"type": "boolean", "default": False},
        # File type filter: f=file, d=dir, l=symlink, x=executable
        "types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "fd types: f/d/l/x",
        },
        # File extensions without dots (e.g., ["py", "js"])
        "extensions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "File extensions, no dots",
        },
        # Exclude patterns for filtering
        "exclude": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exclude patterns",
        },
        # Maximum search depth (1 = current directory only)
        "depth": {"type": "integer", "description": "Max depth. 1=here only"},
        # Follow symbolic links during traversal
        "follow_symlinks": {"type": "boolean", "default": False},
        # Include hidden files (dotfiles)
        "hidden": {"type": "boolean", "default": False},
        # Bypass .gitignore rules
        "no_ignore": {"type": "boolean", "default": False},
        # Size filter expressions: +10M, -1K, etc.
        "size": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Size filter: +10M, -1K",
        },
        # Time-based filters for file modification
        "changed_within": {"type": "string"},
        "changed_before": {"type": "string"},
        # Match against full path instead of filename
        "full_path_match": {"type": "boolean", "default": False},
        # Return absolute paths
        "absolute": {"type": "boolean", "default": True},
        # Maximum number of results to return
        "limit": {"type": "integer"},
        # Return only the count, not the file list
        "count_only": {"type": "boolean", "default": False},
        # Token-efficient toon format by default
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
    },
    # roots is the only required field
    "required": ["roots"],
    "additionalProperties": False,
}


# build_query_info: implementation
def build_query_info(
    arguments: dict[str, Any], limit: int, no_ignore: bool
) -> dict[str, Any]:
    # Return result
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
