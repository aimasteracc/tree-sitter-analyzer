"""Regression test for Issue #779 — deeply nested Python functions silently truncated.

With _MAX_TRAVERSAL_DEPTH = 50, Python nesting level N has its function_definition
node at AST depth 2N+1. Level 25 reaches depth 51 > 50 and was silently dropped.
Fix: raise the limit to 200 (supports ~99 Python nesting levels).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.languages.python_plugin._traversal import (
    _MAX_TRAVERSAL_DEPTH,
)
from tree_sitter_analyzer.languages.python_plugin.plugin import PythonPlugin

pytestmark = pytest.mark.unit


def _extract_function_names(source: str) -> list[str]:
    """Extract function names from Python source via PythonPlugin."""
    import tree_sitter

    plugin = PythonPlugin()
    lang = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source.encode())
    elements = plugin.extract_elements(tree, source)
    return [getattr(fn, "name", None) for fn in elements.get("functions", [])]


def _build_nested_source(n: int) -> str:
    """Generate Python source with n deeply nested functions L0..L(n-1)."""
    indent = "    "
    lines = ["def L0():"]
    for i in range(1, n):
        lines.append(indent * i + f"def L{i}():")
    lines.append(indent * n + "return 1")
    return "\n".join(lines) + "\n"


class TestMaxTraversalDepthConstant:
    """The depth limit must support at least 99 Python nesting levels."""

    def test_max_traversal_depth_is_at_least_200(self):
        # Each Python nesting level uses 2 AST depth units (function_def + block).
        # 200 supports floor((200-1)/2) = 99 nesting levels.
        assert _MAX_TRAVERSAL_DEPTH == 200, (
            f"_MAX_TRAVERSAL_DEPTH={_MAX_TRAVERSAL_DEPTH}; expected 200 "
            "to support 99+ Python nesting levels without silent drops"
        )


class TestDeepNestedFunctionExtraction:
    """Deeply nested Python functions must all be extracted without silent truncation."""

    def test_25_nested_functions_all_extracted(self):
        """L0..L24 (25 levels) — the old threshold boundary."""
        names = _extract_function_names(_build_nested_source(25))
        assert len(names) == 25

    def test_26_nested_functions_all_extracted(self):
        """L0..L25 (26 levels) — one beyond the old limit (#779 repro start)."""
        names = _extract_function_names(_build_nested_source(26))
        assert len(names) == 26

    def test_30_nested_functions_all_extracted(self):
        """L0..L29 (30 levels) — the exact repro from #779."""
        names = _extract_function_names(_build_nested_source(30))
        assert len(names) == 30, (
            f"Expected 30 functions but got {len(names)}: {names!r}. "
            "Deeply nested functions are being silently dropped."
        )

    def test_50_nested_functions_all_extracted(self):
        """L0..L49 (50 levels) — well into territory that previously failed."""
        names = _extract_function_names(_build_nested_source(50))
        assert len(names) == 50

    def test_deepest_function_name_is_correct(self):
        """The last extracted name must be the deepest level, not an earlier one."""
        n = 30
        names = _extract_function_names(_build_nested_source(n))
        assert f"L{n - 1}" in names, (
            f"L{n - 1} (the deepest function) is missing from extracted names: {names!r}"
        )
