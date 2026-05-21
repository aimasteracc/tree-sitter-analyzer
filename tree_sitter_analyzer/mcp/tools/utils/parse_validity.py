#!/usr/bin/env python3
"""Syntax-validity gate for tree-sitter-based MCP tools (M3).

Three detection tools — code_patterns, file_health, safe_to_edit — used
to grade a file containing only ``def broken(:`` as ``SAFE`` / ``A`` /
``safe``. Tree-sitter is permissive: it builds *something* for any
input, sprinkling ``ERROR`` nodes through the tree. The downstream
analysis (smells, dimensions, dependency walk) then runs against that
garbled tree and produces a clean-bill-of-health number that an agent
might happily act on — i.e. "proceed with planned change" on a file
that fails to parse.

This module gives the three tools a single, shared way to ask
"did the parser actually understand the file?" and a single canonical
shape for the short-circuit response so the three tools agree on the
signal name (``syntax_error``) and the verdict (``ERROR``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def is_parse_broken(tree: Any) -> bool:
    """Return ``True`` when tree-sitter detected syntax errors.

    Tree-sitter exposes two booleans on the root node:

    * ``has_error`` — true when **any** ``ERROR`` node exists anywhere
      in the tree. This is the canonical "did the file parse?" signal.
    * ``is_error`` — true only when the root node itself is an error,
      which mostly happens for completely-empty input.

    We use ``has_error`` because syntax errors deep in the tree should
    still disable downstream analysis: a function body with a half-typed
    statement gives meaningless smell/dimension scores.

    Defensive defaults: a missing tree or root counts as "broken" so the
    caller can short-circuit safely; the calling tool already has a
    separate empty-file / non-code branch for the truly-trivial cases.
    """
    if tree is None:
        return True
    root = getattr(tree, "root_node", None)
    if root is None:
        return True
    return bool(getattr(root, "has_error", False))


def is_file_parse_broken(file_path: str, language: str | None = None) -> bool:
    """Convenience wrapper that parses ``file_path`` and checks the tree.

    The three syntax-gated tools each have their own preferred entry
    point (``extract_elements``, ``HealthScorer.score_file``, the
    dependency graph), so they wire ``is_parse_broken`` into whichever
    tree they already build. This helper exists for callers that need a
    fresh parse — primarily the ``safe_to_edit`` tool, which doesn't
    otherwise materialise a tree-sitter tree at its boundary.

    Returns ``True`` when the parser reports errors, or when language
    detection / parsing itself failed. Returns ``False`` only on a
    confirmed clean parse.
    """
    if not file_path or not Path(file_path).is_file():
        # Caller already handles missing files via its own validation;
        # we don't want to overlap with that branch by returning True.
        return False

    detected = language
    if not detected or detected == "unknown":
        try:
            from ....language_detector import detect_language_from_file

            detected = detect_language_from_file(file_path)
        except Exception:
            return False
        if not detected or detected == "unknown":
            # Unknown language — let the caller's own non-code / binary
            # branches handle it. We refuse to claim "broken" when we
            # couldn't even try to parse.
            return False

    try:
        from ....core.parser import Parser

        result = Parser().parse_file(file_path, detected)
    except Exception:
        return False
    if not getattr(result, "success", False):
        # Parser failure (encoding, language load, etc.) is not the same
        # signal as a syntax error. Caller's existing error branches own
        # those cases.
        return False
    return is_parse_broken(result.tree)


def syntax_error_envelope(
    file_path: str,
    *,
    tool: str,
    output_format: str = "toon",
) -> dict[str, Any]:
    """Build the canonical short-circuit envelope for a syntax error.

    Cross-tool consistency: all three tools agree on the same
    ``signal`` value and the same ``verdict`` so an agent that
    branches on either field gets the same answer from every tool.

    Per-tool fields:
    * ``code_patterns``: needs the smell-detection envelope shape
      (count / results / by_category / summary).
    * ``file_health``: needs the grade-style envelope (grade / dimensions
      / code_smells / recommendation).
    * ``safe_to_edit``: needs the risk envelope (risk_level / file_path).

    Rather than try to pre-shape all three from this helper, the caller
    overlays its own envelope on top of the common keys returned here.
    """
    summary_line = f"{file_path} signal=syntax_error verdict=ERROR"
    payload: dict[str, Any] = {
        "success": True,
        "file_path": file_path,
        "verdict": "ERROR",
        "signal": "syntax_error",
        "summary_line": summary_line,
        "agent_summary": {
            "summary_line": summary_line,
            "next_step": ("file fails to parse — fix syntax before further analysis"),
            "verdict": "ERROR",
            "risk": "high",
        },
    }
    # Round-trip ``output_format`` so envelope auditors can see what the
    # caller requested even though syntax errors don't depend on it.
    if tool:
        payload["tool"] = tool
    if output_format:
        payload["output_format"] = output_format
    return payload


__all__ = [
    "is_parse_broken",
    "is_file_parse_broken",
    "syntax_error_envelope",
]
