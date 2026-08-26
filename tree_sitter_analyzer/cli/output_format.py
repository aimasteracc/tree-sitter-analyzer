#!/usr/bin/env python3
"""Shared output-format detection for CLI commands."""

from __future__ import annotations

from typing import Any


def wants_json_output(args: Any) -> bool:
    """Return ``True`` when the caller asked for JSON output."""
    fmt = getattr(args, "format", None) or getattr(args, "output_format", None)
    return fmt == "json"


def resolve_output_format(args: Any, default: str = "json") -> str:
    """Return the JSON format used by every MCP-equivalent CLI command."""
    del args, default
    return "json"
