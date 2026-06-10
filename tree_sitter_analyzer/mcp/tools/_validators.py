#!/usr/bin/env python3
"""Shared validation utilities for MCP tool argument validation.

Extracted from per-tool inline guards so all tools that accept positive-integer
params share the same float-handling and bool-guard path (P1-B, RFC-0015).
"""

from __future__ import annotations


def _validate_positive_int(arguments: dict, key: str) -> None:
    """Validate and in-place coerce a positive-integer argument.

    Accepts non-bool int >= 1 and whole-number float >= 1 (coerced to int).
    Rejects booleans, fractional floats, non-numeric values, and zero/negative
    inputs with a precise ValueError.

    In-place coercion is safe because validate_arguments always runs before
    execute and the facade passes a projected copy, so the mutation is contained.

    Two failure modes fixed (RFC-0015 P1-B, reproduced 2026-06-11):
    1. Float input from LLM: LLM clients emit 30.0 even with "type": "integer"
       in the schema. isinstance(30.0, int) is False, so the old guard raised
       a spurious ValueError for valid caller intent.
    2. Bool pass-through: isinstance(True, int) is True and True < 1 is False
       (True == 1), so max_edges=True silently produced max_edges=1 with no
       error. This guard now explicitly rejects booleans.
    """
    value = arguments.get(key)
    if value is None:
        return
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a positive integer, got bool {value!r}")
    if isinstance(value, float):
        if value != int(value) or value < 1:
            raise ValueError(f"{key} must be a positive integer, got float {value!r}")
        arguments[key] = int(value)
        return
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer, got {value!r}")
