#!/usr/bin/env python3
"""
Integration test for Python plugin 100% grammar coverage.

Validates that the Python plugin achieves 100% grammar coverage (57/57 node types).
Uses the grammar_coverage validator with real tree-sitter parsing.
"""

import pytest

from tree_sitter_analyzer.grammar_coverage.validator import (
    validate_plugin_coverage_sync,
)


@pytest.mark.integration
def test_python_plugin_100_percent_coverage() -> None:
    """Validate that Python plugin achieves 100% grammar coverage (57/57 node types)."""
    report = validate_plugin_coverage_sync("python")

    assert report.language == "python"
    assert report.total_node_types == 57
    assert report.covered_node_types == 57
    assert report.coverage_percentage == 100.0
    assert (
        len(report.uncovered_types) == 0
    ), f"Uncovered types: {report.uncovered_types}"
