#!/usr/bin/env python3
# r37ck (dogfood): deep_nesting detector counted leading whitespace
# inside multi-line docstrings as executable nesting. health_scorer.py
# was flagged as nesting=7 critical because of an indented continuation
# line inside an __init__ docstring. Skip docstring lines before
# measuring indentation.
"""Regression for r37ck deep_nesting docstring false-positive."""

from __future__ import annotations

from tree_sitter_analyzer.mcp.tools.utils.file_health_locations import (
    deepest_nesting_location,
)


class TestDeepNestingDocstringSuppression:
    """Indented continuation lines inside docstrings must not inflate depth."""

    def test_indented_docstring_continuation_does_not_count(self) -> None:
        # 28 leading spaces inside a docstring would naively register as
        # 28 // 4 = 7 — but it's just word-wrapped doc text.
        lines = [
            "def f(x):",
            '    """Short docstring.',
            "",
            "    Args:",
            "        x: this argument is documented over multiple lines,",
            "           wrapping across lines with significant indent to",
            "                            keep words readable but inflating depth.",
            '    """',
            "    return x",
        ]
        depth, _line = deepest_nesting_location(lines)
        assert depth <= 1, (
            f"r37ck: docstring continuation lines must not count as nesting. "
            f"Got depth={depth}"
        )

    def test_real_nesting_still_detected(self) -> None:
        """Sanity — the docstring skip must not blind us to actual indents."""
        lines = [
            "def f(x):",
            "    if x:",
            "        for y in x:",
            "            if y:",
            "                while y:",
            "                    print(y)",
        ]
        depth, line = deepest_nesting_location(lines)
        assert depth >= 4, (
            f"r37ck: real nested code MUST still register a high depth. "
            f"Got depth={depth} at L{line}"
        )

    def test_module_docstring_indented_arg_table_does_not_count(self) -> None:
        """The bug seen in health_scorer.py:321 — argument table inside docstring."""
        lines = [
            "class HealthScorer:",
            "    def __init__(self, weights=None):",
            '        """Initialize.',
            "",
            "        Args:",
            "            weights: Optional custom dimension weights.",
            "                    Default: size=10, complexity=25, dependencies=20,",
            "                             coverage=10, duplication=10, structure=15,",
            "                             git_hotspot=10",
            '        """',
            "        self.weights = weights or {}",
        ]
        depth, _line = deepest_nesting_location(lines)
        # The deepest real line is ``self.weights = ...`` at indent 8 → depth 2.
        assert depth <= 2, (
            f"r37ck: the health_scorer regression case must report depth ≤2. "
            f"Got depth={depth}"
        )
