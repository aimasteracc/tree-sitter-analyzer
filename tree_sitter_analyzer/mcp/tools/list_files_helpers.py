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
            "description": "Search dirs",
        },
        "pattern": {
            "type": "string",
            "description": "Filename pattern",
        },
        "glob": {"type": "boolean", "default": False},
        "types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "fd types: f/d/l/x",
        },
        "extensions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "File extensions, no dots",
        },
        "exclude": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exclude patterns",
        },
        "depth": {"type": "integer", "description": "Max depth. 1=here only"},
        "follow_symlinks": {"type": "boolean", "default": False},
        "hidden": {"type": "boolean", "default": False},
        "no_ignore": {"type": "boolean", "default": False},
        "size": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Size filter: +10M, -1K",
        },
        "changed_within": {"type": "string"},
        "changed_before": {"type": "string"},
        "full_path_match": {"type": "boolean", "default": False},
        "absolute": {"type": "boolean", "default": True},
        "limit": {"type": "integer"},
        "count_only": {"type": "boolean", "default": False},
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
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
