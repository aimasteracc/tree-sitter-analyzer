#!/usr/bin/env python3
"""
Demo test showing the full validator workflow

This demonstrates how the grammar coverage validator works end-to-end.
"""

import pytest

from tree_sitter_analyzer.grammar_coverage.validator import (
    generate_coverage_report,
    validate_plugin_coverage_sync,
)


@pytest.mark.skipif(
    True, reason="Demo test - enable manually to see coverage reports"
)
class TestValidatorDemo:
    """Demo tests to showcase validator functionality"""

    def test_python_coverage_report(self):
        """
        Generate and print a full Python coverage report.

        This test is skipped by default but can be enabled to see
        actual coverage percentages for the Python plugin.
        """
        # Run validation
        report = validate_plugin_coverage_sync("python")

        # Print the formatted report
        print("\n" + "=" * 70)
        print("PYTHON PLUGIN GRAMMAR COVERAGE REPORT")
        print("=" * 70)
        print(generate_coverage_report(report))
        print("=" * 70)

        # Show some statistics
        print(f"\nTotal node types in grammar: {report.total_node_types}")
        print(f"Node types covered by plugin: {report.covered_node_types}")
        print(f"Coverage percentage: {report.coverage_percentage:.2f}%")
        print(f"Uncovered types: {len(report.uncovered_types)}")

        # Verify structure
        assert report.language == "python"
        assert report.total_node_types > 0
        assert 0.0 <= report.coverage_percentage <= 100.0
